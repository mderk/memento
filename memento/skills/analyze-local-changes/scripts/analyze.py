#!/usr/bin/env python3
"""
analyze.py - Analyze local modifications in Memory Bank files

Modes:
  compute <file>           Compute hash for a single file
  compute-all              Compute hashes for all Memory Bank files
  compute-source <file>    Compute hash for a source prompt/static file
  detect                   Detect which files have been modified (local changes)
  detect-source-changes    Detect which plugin prompts/statics have changed
  analyze <file>           Analyze what changed in a file
  analyze-all              Analyze all modified files
  merge <file>             3-way merge: base (git) + local + new → merged content
  commit-generation        Create generation commits (base + optional merge)
  recompute-source-hashes  Recompute source-hashes.json from prompts/ and static/
  update-plan <files>      Batch-update generation-plan.md (auto-add new rows, --remove old ones)
  pre-update               Comprehensive pre-update check (combines detect + source + prompts + statics)
  copy-static              Copy applicable static files with optional merge
  check-existing           Check if Memory Bank environment exists and its state
  plan-generation          Build generation plan from prompts + manifest with conditional evaluation

All output is JSON for easy parsing by Claude.
"""

import argparse
import difflib
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


# Configuration
HASH_LENGTH = 8
GENERATION_PLAN = Path(".memory_bank/generation-plan.md")
MEMORY_BANK_DIR = Path(".memory_bank")
CLAUDE_DIR = Path(".claude")
SOURCE_HASHES_FILE = "source-hashes.json"


def compute_hash(file_path: Path, length: int = HASH_LENGTH) -> str:
    """Compute MD5 hash of file content."""
    with open(file_path, 'rb') as f:
        md5 = hashlib.md5(f.read()).hexdigest()
    return md5[:length]


def count_lines(file_path: Path) -> int:
    """Count lines in file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return sum(1 for _ in f)


def load_source_hashes(plugin_root: str) -> dict[str, str] | None:
    """Load pre-computed source hashes from source-hashes.json if it exists."""
    json_path = Path(plugin_root) / SOURCE_HASHES_FILE
    if json_path.exists():
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def target_to_source_path(gen_path: str, plugin_path: Path) -> Path | None:
    """Map a generated file path to its source path in the plugin."""
    if gen_path.startswith('.memory_bank/'):
        rel_path = gen_path[len('.memory_bank/'):]
        source_path = plugin_path / 'prompts' / 'memory_bank' / (rel_path + '.prompt')
        if not source_path.exists():
            source_path = plugin_path / 'static' / 'memory_bank' / rel_path
    elif gen_path.startswith('.claude/agents/'):
        rel_path = gen_path[len('.claude/agents/'):]
        source_path = plugin_path / 'static' / 'agents' / rel_path
    elif gen_path.startswith('.claude/commands/'):
        rel_path = gen_path[len('.claude/commands/'):]
        source_path = plugin_path / 'static' / 'commands' / rel_path
    elif gen_path.startswith('.claude/skills/'):
        rel_path = gen_path[len('.claude/skills/'):]
        source_path = plugin_path / 'static' / 'skills' / rel_path
    elif gen_path == 'CLAUDE.md':
        source_path = plugin_path / 'prompts' / 'CLAUDE.md.prompt'
    else:
        return None
    return source_path


# ============ Analysis Flattening ============


def flatten_analysis(raw: dict) -> dict:
    """Flatten nested project-analysis.json into a flat dict for conditional evaluation.

    detect-tech-stack outputs: {"status": "success", "data": {"backend": {"has_backend": true}, ...}}
    Conditionals expect flat keys: has_backend, backend_language, etc.
    """
    data = raw.get('data', raw)

    # Already flat (has boolean conditional fields at top level)
    if isinstance(data.get('has_backend'), bool) or isinstance(data.get('has_frontend'), bool):
        return data

    flat: dict = {}
    # Preserve top-level data fields
    for k, v in data.items():
        if not isinstance(v, dict):
            flat[k] = v

    backend = data.get('backend', {})
    if isinstance(backend, dict):
        flat['has_backend'] = backend.get('has_backend', False)
        flat['backend_framework'] = backend.get('framework', '')
        flat['backend_language'] = backend.get('language', '')

    frontend = data.get('frontend', {})
    if isinstance(frontend, dict):
        flat['has_frontend'] = frontend.get('has_frontend', False)
        flat['frontend_framework'] = frontend.get('framework', '')

    database = data.get('database', {})
    if isinstance(database, dict):
        flat['has_database'] = bool(database.get('primary'))

    testing = data.get('testing', {})
    if isinstance(testing, dict):
        flat['has_tests'] = testing.get('has_tests', False)
        flat['has_e2e_tests'] = testing.get('has_e2e_tests', False)

    structure = data.get('structure', {})
    if isinstance(structure, dict):
        flat['is_monorepo'] = structure.get('is_monorepo', False)
        flat['has_docker'] = structure.get('has_docker', False)
        flat['has_ci'] = structure.get('has_ci_cd', False)

    return flat


# ============ Conditional Evaluator ============

def evaluate_conditional(expr: str | None, analysis: dict) -> bool:
    """Evaluate a conditional expression against project-analysis.json data.

    Supports:
    - null/None → True
    - "has_frontend" → bool lookup
    - "backend_language == 'Python'" → equality
    - "has_frontend && has_tests" → AND
    - "!has_database" → NOT
    - "has_frontend || backend_language == 'TypeScript'" → OR
    """
    if expr is None:
        return True
    expr = str(expr).strip()
    if not expr or expr == 'null':
        return True
    return _eval_or(expr, analysis)


def _split_logical(expr: str, operator: str) -> list[str]:
    """Split by logical operator, respecting quoted strings."""
    parts = []
    current = ''
    i = 0
    in_quote = False
    quote_char = None

    while i < len(expr):
        if expr[i] in ('"', "'") and not in_quote:
            in_quote = True
            quote_char = expr[i]
            current += expr[i]
        elif in_quote and expr[i] == quote_char:
            in_quote = False
            current += expr[i]
        elif not in_quote and expr[i:i + len(operator)] == operator:
            parts.append(current.strip())
            current = ''
            i += len(operator)
            continue
        else:
            current += expr[i]
        i += 1

    if current.strip():
        parts.append(current.strip())

    return parts


def _eval_or(expr: str, analysis: dict) -> bool:
    parts = _split_logical(expr, '||')
    return any(_eval_and(p, analysis) for p in parts)


def _eval_and(expr: str, analysis: dict) -> bool:
    parts = _split_logical(expr, '&&')
    return all(_eval_not(p, analysis) for p in parts)


def _eval_not(expr: str, analysis: dict) -> bool:
    expr = expr.strip()
    if expr.startswith('!'):
        return not _eval_atom(expr[1:].strip(), analysis)
    return _eval_atom(expr, analysis)


def _eval_atom(expr: str, analysis: dict) -> bool:
    """Evaluate atomic expression: identifier or equality check."""
    expr = expr.strip()
    eq_match = re.match(r"(\w+)\s*==\s*['\"]([^'\"]*)['\"]", expr)
    if eq_match:
        field = eq_match.group(1)
        value = eq_match.group(2)
        return str(analysis.get(field, '')).lower() == value.lower()
    val = analysis.get(expr)
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return bool(val)
    return bool(val)


# ============ Parsers (no PyYAML dependency) ============

def parse_prompt_frontmatter(file_path: Path) -> dict | None:
    """Parse YAML frontmatter from a .prompt file.

    Returns dict with: file, target_path, priority, conditional, dependencies.
    Returns None if frontmatter is invalid.
    """
    try:
        content = file_path.read_text(encoding='utf-8')
    except (IOError, UnicodeDecodeError):
        return None

    if not content.startswith('---'):
        return None

    end = content.find('---', 3)
    if end == -1:
        return None

    frontmatter = content[3:end].strip()
    result = {}

    for line in frontmatter.split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        match = re.match(r'^(\w+):\s*(.*)$', line)
        if match:
            key = match.group(1)
            value = match.group(2).strip()

            if value in ('null', ''):
                result[key] = None
            elif value == 'true':
                result[key] = True
            elif value == 'false':
                result[key] = False
            elif value.startswith('"') and value.endswith('"'):
                result[key] = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                result[key] = value[1:-1]
            elif value == '[]':
                result[key] = []
            else:
                try:
                    result[key] = int(value)
                except ValueError:
                    result[key] = value

    return result if 'file' in result else None


def parse_manifest(manifest_path: Path) -> list[dict]:
    """Parse static/manifest.yaml into list of file entries.

    Each entry: {'source': str, 'target': str, 'conditional': str|None}
    """
    if not manifest_path.exists():
        return []

    def _flush(entries: list[dict], current: dict) -> None:
        if current and 'source' in current and 'target' in current:
            current.setdefault('conditional', None)
            entries.append(current)

    content = manifest_path.read_text(encoding='utf-8')
    entries: list[dict] = []
    current: dict = {}

    for line in content.split('\n'):
        stripped = line.strip()

        if not stripped or stripped.startswith('#'):
            _flush(entries, current)
            current = {}
            continue

        if stripped.startswith('- source:'):
            _flush(entries, current)
            current = {'source': stripped[len('- source:'):].strip()}
        elif stripped.startswith('target:') and current:
            current['target'] = stripped[len('target:'):].strip()
        elif stripped.startswith('conditional:') and current:
            val = stripped[len('conditional:'):].strip()
            if val == 'null':
                current['conditional'] = None
            elif val.startswith('"') and val.endswith('"'):
                current['conditional'] = val[1:-1]
            elif val.startswith("'") and val.endswith("'"):
                current['conditional'] = val[1:-1]
            else:
                current['conditional'] = val if val else None
        elif stripped == 'files:':
            continue

    _flush(entries, current)
    return entries


def load_project_analysis() -> dict | None:
    """Load project-analysis.json from .memory_bank/ and flatten for conditional evaluation."""
    analysis_path = MEMORY_BANK_DIR / 'project-analysis.json'
    if not analysis_path.exists():
        return None
    try:
        raw = json.loads(analysis_path.read_text(encoding='utf-8'))
        return flatten_analysis(raw)
    except (json.JSONDecodeError, IOError):
        return None


# ============ Classification Helpers ============

def classify_static_files(manifest: list[dict], plugin_path: Path,
                          plan_data: dict, analysis: dict,
                          source_hashes: dict | None) -> dict:
    """Classify each static file from manifest into decision-matrix categories."""
    result: dict = {
        'new': [],
        'safe_overwrite': [],
        'local_only': [],
        'merge_needed': [],
        'up_to_date': [],
        'skipped_conditional': []
    }

    for entry in manifest:
        target = entry['target']
        source_rel = 'static/' + entry['source']
        conditional = entry.get('conditional')

        if not evaluate_conditional(conditional, analysis):
            result['skipped_conditional'].append({
                'source': entry['source'],
                'target': target,
                'conditional': conditional
            })
            continue

        target_path = Path(target)
        plan_entry = plan_data.get(target)

        if not target_path.exists() or not plan_entry:
            result['new'].append({'source': entry['source'], 'target': target})
            continue

        # Check local modification
        stored_hash = plan_entry.get('hash')
        current_hash = compute_hash(target_path)
        local_modified = stored_hash != current_hash if stored_hash else False

        # Check plugin update
        stored_source_hash = plan_entry.get('source_hash')
        current_source_hash = None
        if source_hashes and source_rel in source_hashes:
            current_source_hash = source_hashes[source_rel]
        else:
            source_file = plugin_path / 'static' / entry['source']
            if source_file.exists():
                current_source_hash = compute_hash(source_file)

        if stored_source_hash and current_source_hash:
            plugin_updated = stored_source_hash != current_source_hash
        elif current_source_hash:
            # No stored source hash — compare deployed file against source directly
            plugin_updated = current_hash != current_source_hash
        else:
            plugin_updated = False

        # Decision matrix
        info = {'source': entry['source'], 'target': target}
        if not local_modified and not plugin_updated:
            result['up_to_date'].append(info)
        elif not local_modified and plugin_updated:
            result['safe_overwrite'].append(info)
        elif local_modified and not plugin_updated:
            result['local_only'].append(info)
        elif current_source_hash and current_hash == current_source_hash:
            # Both flags set, but deployed already matches source — already up to date
            # (e.g. manual copy or previous update without plan refresh)
            result['up_to_date'].append(info)
        else:
            result['merge_needed'].append(info)

    return result


def detect_obsolete_files(plugin_path: Path, plan_data: dict,
                          all_prompts: list[dict], manifest: list[dict],
                          analysis: dict) -> list[dict]:
    """Find files in generation plan that no longer have a plugin source."""
    plugin_targets = set()
    for p in all_prompts:
        if p.get('applies', True):
            plugin_targets.add(p['target'])
    for entry in manifest:
        if evaluate_conditional(entry.get('conditional'), analysis):
            plugin_targets.add(entry['target'])

    obsolete = []
    for plan_target in plan_data:
        if plan_target not in plugin_targets:
            source = target_to_source_path(plan_target, plugin_path)
            if source and not source.exists():
                obsolete.append({
                    'target': plan_target,
                    'expected_source': str(source)
                })
    return obsolete


def compare_tech_stacks(old: dict, new: dict) -> dict:
    """Compare old and new project analyses, classify impact level."""
    high: list = []
    medium: list = []
    low: list = []

    # Framework changes (HIGH impact)
    for key in ['backend_framework', 'frontend_framework']:
        old_val = old.get(key)
        new_val = new.get(key)
        if old_val != new_val:
            if old_val and new_val:
                high.append({'field': key, 'old': old_val, 'new': new_val,
                             'reason': 'framework_change'})
            elif new_val:
                medium.append({'field': key, 'old': old_val, 'new': new_val,
                               'reason': 'framework_added'})
            elif old_val:
                medium.append({'field': key, 'old': old_val, 'new': new_val,
                               'reason': 'framework_removed'})

    # Version changes
    for key in ['backend_framework_version', 'frontend_framework_version',
                'database_version']:
        old_val = old.get(key)
        new_val = new.get(key)
        if old_val and new_val and old_val != new_val:
            old_major = old_val.split('.')[0]
            new_major = new_val.split('.')[0]
            if old_major != new_major:
                medium.append({'field': key, 'old': old_val, 'new': new_val,
                               'reason': 'major_version_change'})
            else:
                low.append({'field': key, 'old': old_val, 'new': new_val,
                            'reason': 'minor_version_change'})

    # Boolean capability flags
    for key in ['has_frontend', 'has_backend', 'has_database', 'has_tests',
                'is_monorepo']:
        old_val = old.get(key)
        new_val = new.get(key)
        if old_val != new_val:
            reason = 'capability_added' if new_val else 'capability_removed'
            medium.append({'field': key, 'old': old_val, 'new': new_val,
                           'reason': reason})

    # Other fields
    for key in ['database', 'primary_language', 'api_style', 'test_command',
                'dev_command']:
        old_val = old.get(key)
        new_val = new.get(key)
        if old_val != new_val and (old_val or new_val):
            low.append({'field': key, 'old': old_val, 'new': new_val,
                        'reason': 'value_changed'})

    return {'high': high, 'medium': medium, 'low': low}


def get_all_mb_files() -> list[Path]:
    """Get all tracked files in Memory Bank and .claude directories.

    Scans all file types (not just *.md) so that non-markdown files like
    scripts (defer.py, load-context.py) are correctly detected.
    """
    files = []

    for root_dir in (MEMORY_BANK_DIR, CLAUDE_DIR):
        if root_dir.exists():
            for f in root_dir.rglob("*"):
                if f.is_file():
                    files.append(f)

    return sorted(files)


def parse_generation_plan(include_pending: bool = False) -> dict[str, dict]:
    """Parse generation-plan.md and extract file -> {hash, source_hash} mapping.

    By default only returns completed ([x]) entries with hashes.
    With include_pending=True, also returns pending ([ ]) entries (hash=None).
    """
    if not GENERATION_PLAN.exists():
        return {}

    stored_data = {}
    content = GENERATION_PLAN.read_text(encoding='utf-8')

    # Status pattern: [x] for completed, [ ] for pending
    status_re = r'\[x\]' if not include_pending else r'\[[ x]\]'

    # Format: | [x] | filename | location | lines | hash | source_hash |
    # Also support old format without source_hash: | [x] | filename | location | lines | hash |
    pattern_new = rf'\|\s*({status_re})\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|'
    pattern_old = rf'\|\s*({status_re})\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|'

    # Try new format first
    for match in re.finditer(pattern_new, content):
        filename = match.group(2).strip()
        location = match.group(3).strip()
        hash_value = match.group(5).strip()
        source_hash = match.group(6).strip()

        full_path = f"{location}{filename}"
        if hash_value and hash_value != '':
            stored_data[full_path] = {
                'hash': hash_value,
                'source_hash': source_hash if source_hash else None
            }
        elif include_pending:
            stored_data[full_path] = {
                'hash': None,
                'source_hash': None
            }

    # If no matches with new format, try old format
    if not stored_data:
        for match in re.finditer(pattern_old, content):
            filename = match.group(2).strip()
            location = match.group(3).strip()
            hash_value = match.group(5).strip()

            full_path = f"{location}{filename}"
            if hash_value and hash_value != '':
                stored_data[full_path] = {
                    'hash': hash_value,
                    'source_hash': None
                }
            elif include_pending:
                stored_data[full_path] = {
                    'hash': None,
                    'source_hash': None
                }

    return stored_data


def parse_markdown_sections(content: str) -> list[dict]:
    """Parse markdown into sections based on headers."""
    sections = []
    lines = content.split('\n')

    current_section = None
    current_lines = []

    for i, line in enumerate(lines):
        # Check for header
        header_match = re.match(r'^(#{1,6})\s+(.+)$', line)

        if header_match:
            # Save previous section
            if current_section:
                current_section['content'] = '\n'.join(current_lines)
                current_section['end_line'] = i - 1
                sections.append(current_section)

            level = len(header_match.group(1))
            title = header_match.group(2).strip()

            current_section = {
                'level': level,
                'header': f"{'#' * level} {title}",
                'title': title,
                'start_line': i,
                'end_line': None
            }
            current_lines = []
        else:
            current_lines.append(line)

    # Save last section
    if current_section:
        current_section['content'] = '\n'.join(current_lines)
        current_section['end_line'] = len(lines) - 1
        sections.append(current_section)

    return sections


def analyze_changes(base_content: str, current_content: str) -> list[dict]:
    """Analyze what changed between base and current content."""
    changes = []

    base_sections = parse_markdown_sections(base_content)
    current_sections = parse_markdown_sections(current_content)

    base_headers = {s['header']: s for s in base_sections}
    current_headers = {s['header']: s for s in current_sections}

    # Find new sections
    for header, section in current_headers.items():
        if header not in base_headers:
            # Find what section it comes after
            after_section = None
            for i, s in enumerate(current_sections):
                if s['header'] == header and i > 0:
                    after_section = current_sections[i - 1]['header']
                    break

            content_lines = section['content'].strip().split('\n')
            preview = content_lines[0][:80] + '...' if content_lines and len(content_lines[0]) > 80 else (content_lines[0] if content_lines else '')

            changes.append({
                'type': 'new_section',
                'header': header,
                'level': section['level'],
                'after_section': after_section,
                'lines': len(content_lines),
                'content_preview': preview
            })

    # Find deleted sections
    for header, section in base_headers.items():
        if header not in current_headers:
            changes.append({
                'type': 'deleted_section',
                'header': header,
                'level': section['level'],
                'lines': len(section['content'].strip().split('\n'))
            })

    # Find modified sections
    for header in set(base_headers.keys()) & set(current_headers.keys()):
        base_section = base_headers[header]
        current_section = current_headers[header]

        base_lines = base_section['content'].strip().split('\n')
        current_lines = current_section['content'].strip().split('\n')

        if base_lines != current_lines:
            # Compute diff
            diff = list(difflib.unified_diff(
                base_lines,
                current_lines,
                lineterm='',
                n=0  # No context lines
            ))

            # Skip header lines of diff
            diff_content = [ln for ln in diff if not ln.startswith('---') and not ln.startswith('+++') and not ln.startswith('@@')]

            added_lines = [ln[1:] for ln in diff_content if ln.startswith('+')]
            removed_lines = [ln[1:] for ln in diff_content if ln.startswith('-')]

            # Determine change type
            if not removed_lines and added_lines:
                # Only additions - likely added at end
                changes.append({
                    'type': 'added_lines',
                    'in_section': header,
                    'lines_added': len(added_lines),
                    'content': added_lines[:5]  # First 5 lines as preview
                })
            elif removed_lines and added_lines:
                # Both additions and removals - content modified
                diff_str = '\n'.join(diff_content[:10])  # First 10 diff lines
                changes.append({
                    'type': 'modified_content',
                    'in_section': header,
                    'lines_added': len(added_lines),
                    'lines_removed': len(removed_lines),
                    'diff': diff_str,
                    'conflict': True
                })
            elif removed_lines and not added_lines:
                # Only removals
                changes.append({
                    'type': 'deleted_lines',
                    'in_section': header,
                    'lines_removed': len(removed_lines),
                    'content': removed_lines[:5]
                })

    return changes


def determine_merge_strategy(changes: list[dict]) -> dict:
    """Determine which changes can be auto-merged and which need review."""
    auto_mergeable = []
    requires_review = []

    for change in changes:
        change_summary = {
            'type': change['type'],
        }

        if change['type'] == 'new_section':
            change_summary['header'] = change['header']
            auto_mergeable.append(change_summary)

        elif change['type'] == 'added_lines':
            change_summary['in_section'] = change['in_section']
            auto_mergeable.append(change_summary)

        elif change['type'] == 'modified_content':
            change_summary['in_section'] = change['in_section']
            change_summary['reason'] = 'Content conflict - existing lines modified'
            requires_review.append(change_summary)

        elif change['type'] == 'deleted_section':
            change_summary['header'] = change['header']
            change_summary['reason'] = 'Section deleted locally'
            requires_review.append(change_summary)

        elif change['type'] == 'deleted_lines':
            change_summary['in_section'] = change['in_section']
            change_summary['reason'] = 'Lines deleted locally'
            requires_review.append(change_summary)

    return {
        'auto_mergeable': auto_mergeable,
        'requires_review': requires_review
    }


# ============ 3-Way Merge ============

def parse_sections_for_merge(content: str) -> list[dict]:
    """Parse markdown into sections for merge, including preamble before first header."""
    sections = []
    lines = content.split('\n')

    current_header = ''  # empty = preamble
    current_lines = []

    for line in lines:
        header_match = re.match(r'^(#{1,6})\s+(.+)$', line)

        if header_match:
            section_content = '\n'.join(current_lines)
            if current_header or section_content.strip():
                sections.append({'header': current_header, 'content': section_content})

            level = len(header_match.group(1))
            title = header_match.group(2).strip()
            current_header = f"{'#' * level} {title}"
            current_lines = []
        else:
            current_lines.append(line)

    section_content = '\n'.join(current_lines)
    if current_header or section_content.strip():
        sections.append({'header': current_header, 'content': section_content})

    return sections


def sections_content_equal(a: dict, b: dict) -> bool:
    """Compare two sections' content, ignoring trailing whitespace."""
    return a['content'].rstrip() == b['content'].rstrip()


def render_sections(sections: list[dict]) -> str:
    """Render sections back into markdown."""
    parts = []
    for s in sections:
        if s['header']:
            parts.append(s['header'])
        parts.append(s['content'])
    return '\n'.join(parts)


def merge_markdown_3way(base_content: str, local_content: str, new_content: str) -> dict:
    """Section-level 3-way merge of markdown files.

    Uses Generation Base (clean plugin output before user merge) as base.
    This ensures user additions from previous merges are preserved.
    """
    base_secs = parse_sections_for_merge(base_content)
    local_secs = parse_sections_for_merge(local_content)
    new_secs = parse_sections_for_merge(new_content)

    base_map = {s['header']: s for s in base_secs}
    local_map = {s['header']: s for s in local_secs}
    new_map = {s['header']: s for s in new_secs}

    # User-added sections: in local, not in base, not in new
    user_added = [s for s in local_secs
                  if s['header'] not in base_map and s['header'] not in new_map]

    # For each user section, find anchor (previous section in local that exists in new)
    user_anchors = {}
    for i, s in enumerate(local_secs):
        if any(s['header'] == ua['header'] for ua in user_added):
            for j in range(i - 1, -1, -1):
                if local_secs[j]['header'] in new_map:
                    user_anchors[s['header']] = local_secs[j]['header']
                    break

    merged = []
    conflicts = []
    stats = {'from_new': 0, 'from_local': 0, 'unchanged': 0, 'user_added': 0, 'conflicts': 0}
    used_user = set()

    for section in new_secs:
        h = section['header']
        base_s = base_map.get(h)
        local_s = local_map.get(h)

        if base_s is None:
            # New from plugin
            if local_s and not sections_content_equal(local_s, section):
                conflicts.append({'section': h, 'type': 'both_added',
                                   'local': local_s['content'], 'new': section['content']})
                merged.append(section)
                stats['conflicts'] += 1
            else:
                merged.append(section)
                stats['from_new'] += 1
        elif local_s is None:
            # User deleted section that plugin still has
            conflicts.append({'section': h, 'type': 'user_deleted',
                               'base': base_s['content'], 'new': section['content']})
            merged.append(section)
            stats['conflicts'] += 1
        elif sections_content_equal(base_s, local_s):
            # User didn't change → take new
            merged.append(section)
            if not sections_content_equal(base_s, section):
                stats['from_new'] += 1
            else:
                stats['unchanged'] += 1
        elif sections_content_equal(base_s, section):
            # Plugin didn't change → keep local
            merged.append(local_s)
            stats['from_local'] += 1
        else:
            # Both changed → conflict, default keep local
            conflicts.append({'section': h, 'type': 'both_modified',
                               'base': base_s['content'], 'local': local_s['content'],
                               'new': section['content']})
            merged.append(local_s)
            stats['conflicts'] += 1

        # Insert user-added sections anchored after this section
        for ua in user_added:
            if ua['header'] not in used_user and user_anchors.get(ua['header']) == h:
                merged.append(ua)
                used_user.add(ua['header'])
                stats['user_added'] += 1

    # User sections with no anchor go at end
    for ua in user_added:
        if ua['header'] not in used_user:
            merged.append(ua)
            used_user.add(ua['header'])
            stats['user_added'] += 1

    # Handle sections removed by plugin (in base+local but not in new)
    for section in base_secs:
        h = section['header']
        if h not in new_map and h in local_map:
            local_s = local_map[h]
            if not sections_content_equal(section, local_s):
                # User modified a section that plugin removed → conflict
                conflicts.append({'section': h, 'type': 'plugin_removed_user_modified',
                                   'base': section['content'], 'local': local_s['content']})
                merged.append(local_s)
                stats['conflicts'] += 1
            # else: user didn't touch, plugin removed → silently drop (correct)

    return {
        'status': 'merged' if not conflicts else 'conflicts',
        'merged_content': render_sections(merged),
        'conflicts': conflicts,
        'stats': stats
    }


# ============ Git & Metadata Helpers ============

def git_show(commit: str, file_path: str) -> str | None:
    """Get file content from a git commit."""
    try:
        result = subprocess.run(
            ['git', 'show', f'{commit}:{file_path}'],
            capture_output=True, text=True, check=True
        )
        return result.stdout
    except subprocess.CalledProcessError:
        return None


def parse_plan_metadata() -> dict:
    """Parse Metadata section from generation-plan.md."""
    if not GENERATION_PLAN.exists():
        return {}

    content = GENERATION_PLAN.read_text(encoding='utf-8')
    metadata = {}
    in_metadata = False

    for line in content.split('\n'):
        if line.strip() == '## Metadata':
            in_metadata = True
            continue
        if in_metadata:
            if line.startswith('## '):
                break
            match = re.match(r'^([^:]+):\s*(.+)$', line.strip())
            if match:
                metadata[match.group(1).strip()] = match.group(2).strip()

    return metadata


def update_plan_metadata(key: str, value: str):
    """Update a single metadata field in generation-plan.md."""
    if not GENERATION_PLAN.exists():
        return

    content = GENERATION_PLAN.read_text(encoding='utf-8')
    pattern = re.compile(r'^(' + re.escape(key) + r'):\s*.*$', re.MULTILINE)

    if pattern.search(content):
        content = pattern.sub(f'{key}: {value}', content)
    else:
        content = content.replace('## Metadata\n', f'## Metadata\n\n{key}: {value}\n', 1)

    GENERATION_PLAN.write_text(content, encoding='utf-8')


# ============ Commands ============

def cmd_compute(files: list[str]) -> dict:
    """Compute hashes for specified files."""
    results = []

    for file_str in files:
        file_path = Path(file_str)
        if file_path.exists():
            results.append({
                'path': str(file_path),
                'hash': compute_hash(file_path),
                'lines': count_lines(file_path)
            })
        else:
            results.append({
                'path': str(file_path),
                'error': 'File not found'
            })

    return {'status': 'success', 'files': results}


def cmd_compute_all() -> dict:
    """Compute hashes for all Memory Bank files."""
    files = get_all_mb_files()
    return cmd_compute([str(f) for f in files])


def cmd_compute_source(files: list[str], plugin_root: str) -> dict:
    """Compute hashes for source prompt/static files in plugin.

    If source-hashes.json exists in plugin_root, looks up hash there first.
    Falls back to computing from file if not found in JSON.
    """
    results = []
    source_hashes = load_source_hashes(plugin_root)

    for file_str in files:
        # Resolve path relative to plugin root
        if file_str.startswith('/'):
            file_path = Path(file_str)
            rel_path = file_str
        else:
            file_path = Path(plugin_root) / file_str
            rel_path = file_str

        # Try source-hashes.json first
        if source_hashes and rel_path in source_hashes:
            entry: dict[str, str | int] = {
                'path': str(file_path),
                'relative_path': rel_path,
                'hash': source_hashes[rel_path],
            }
            if file_path.exists():
                entry['lines'] = count_lines(file_path)
            results.append(entry)
        elif file_path.exists():
            results.append({
                'path': str(file_path),
                'relative_path': rel_path,
                'hash': compute_hash(file_path),
                'lines': count_lines(file_path)
            })
        else:
            results.append({
                'path': str(file_path),
                'relative_path': rel_path,
                'error': 'File not found'
            })

    return {'status': 'success', 'files': results}


def cmd_detect() -> dict:
    """Detect which files have been modified (local changes)."""
    if not GENERATION_PLAN.exists():
        return {'status': 'error', 'message': 'generation-plan.md not found'}

    stored_data = parse_generation_plan()
    current_files = {str(f): f for f in get_all_mb_files()}

    modified = []
    unchanged = []
    missing = []
    new_files = []

    # Check stored files
    for path, data in stored_data.items():
        stored_hash = data['hash']
        if path in current_files:
            current_hash = compute_hash(current_files[path])
            if current_hash == stored_hash:
                unchanged.append(path)
            else:
                modified.append(path)
        else:
            missing.append(path)

    # Find new files (not in stored)
    for path in current_files:
        if path not in stored_data:
            new_files.append(path)

    total = len(stored_data)

    return {
        'status': 'success',
        'modified': modified,
        'unchanged': unchanged,
        'missing': missing,
        'new': new_files,
        'summary': {
            'total': total,
            'modified': len(modified),
            'unchanged': len(unchanged),
            'missing': len(missing),
            'new': len(new_files)
        }
    }


def cmd_detect_source_changes(plugin_root: str) -> dict:
    """Detect which plugin prompts/statics have changed since generation.

    If source-hashes.json exists, uses pre-computed hashes for current source state.
    Falls back to computing hashes from files if JSON is absent.
    """
    if not GENERATION_PLAN.exists():
        return {'status': 'error', 'message': 'generation-plan.md not found'}

    stored_data = parse_generation_plan()
    plugin_path = Path(plugin_root)
    source_hashes = load_source_hashes(plugin_root)

    changed = []
    unchanged = []
    missing_source = []
    no_source_hash = []

    for gen_path, data in stored_data.items():
        stored_source_hash = data.get('source_hash')

        if not stored_source_hash:
            no_source_hash.append(gen_path)
            continue

        source_path = target_to_source_path(gen_path, plugin_path)

        if source_path:
            # Try pre-computed hash from JSON first
            current_hash = None
            if source_hashes:
                rel_source = str(source_path.relative_to(plugin_path))
                current_hash = source_hashes.get(rel_source)

            # Fallback: compute from file
            if current_hash is None and source_path.exists():
                current_hash = compute_hash(source_path)

            if current_hash is not None:
                if current_hash == stored_source_hash:
                    unchanged.append({
                        'generated': gen_path,
                        'source': str(source_path)
                    })
                else:
                    changed.append({
                        'generated': gen_path,
                        'source': str(source_path),
                        'stored_hash': stored_source_hash,
                        'current_hash': current_hash
                    })
            else:
                missing_source.append({
                    'generated': gen_path,
                    'expected_source': str(source_path)
                })

    return {
        'status': 'success',
        'changed': changed,
        'unchanged': unchanged,
        'missing_source': missing_source,
        'no_source_hash': no_source_hash,
        'summary': {
            'total': len(stored_data),
            'changed': len(changed),
            'unchanged': len(unchanged),
            'missing_source': len(missing_source),
            'no_source_hash': len(no_source_hash)
        }
    }


def cmd_analyze(file_path: str, base_content: str | None = None) -> dict:
    """Analyze what changed in a specific file."""
    path = Path(file_path)

    if not path.exists():
        return {'status': 'error', 'message': f'File not found: {file_path}'}

    stored_data = parse_generation_plan()
    file_data = stored_data.get(str(path), stored_data.get(file_path, {}))
    stored_hash = file_data.get('hash') if file_data else None
    current_hash = compute_hash(path)

    # Read current content
    current_content = path.read_text(encoding='utf-8')

    # If base_content not provided, we can't do detailed analysis
    # In real usage, base would come from regenerating file to temp
    if base_content is None:
        # For now, return basic info without detailed change analysis
        return {
            'status': 'success',
            'path': str(path),
            'hash': {
                'stored': stored_hash,
                'current': current_hash
            },
            'modified': stored_hash != current_hash if stored_hash else None,
            'lines': count_lines(path),
            'note': 'Provide base_content for detailed change analysis'
        }

    # Detailed analysis with base content
    changes = analyze_changes(base_content, current_content)
    merge_strategy = determine_merge_strategy(changes)

    return {
        'status': 'success',
        'path': str(path),
        'hash': {
            'stored': stored_hash,
            'current': current_hash
        },
        'changes': changes,
        'merge_strategy': merge_strategy
    }


def cmd_analyze_all() -> dict:
    """Analyze all modified files."""
    detect_result = cmd_detect()

    if detect_result['status'] != 'success':
        return detect_result

    modified_files = detect_result['modified']

    if not modified_files:
        return {
            'status': 'success',
            'message': 'No modified files found',
            'files': []
        }

    results = []
    for file_path in modified_files:
        result = cmd_analyze(file_path)
        results.append(result)

    return {
        'status': 'success',
        'files': results,
        'summary': {
            'analyzed': len(results),
            'modified': len(modified_files)
        }
    }


def cmd_merge(target_path: str, base_commit: str, new_file: str,
              write: bool = False) -> dict:
    """3-way merge: recover base from git, read local, read new, merge.

    With --write: if merge succeeds (no conflicts), writes merged content
    directly to target file. Saves LLM from reading + writing separately.
    """
    target = Path(target_path)
    new = Path(new_file)

    if not target.exists():
        return {'status': 'error', 'message': f'Target file not found: {target_path}'}
    if not new.exists():
        return {'status': 'error', 'message': f'New file not found: {new_file}'}

    local_content = target.read_text(encoding='utf-8')
    new_content = new.read_text(encoding='utf-8')

    base_content = git_show(base_commit, target_path)
    if base_content is None:
        return {'status': 'error',
                'message': f'Cannot recover base: git show {base_commit}:{target_path} failed'}

    # No local changes → just use new
    if local_content.rstrip() == base_content.rstrip():
        if write:
            target.write_text(new_content, encoding='utf-8')
        return {
            'status': 'no_local_changes',
            'merged_content': new_content,
            'conflicts': [],
            'stats': {'message': 'No local changes, using new version as-is'},
            'written': write
        }

    result = merge_markdown_3way(base_content, local_content, new_content)
    result['target'] = target_path
    result['base_commit'] = base_commit

    if write and result['status'] in ('merged', 'no_local_changes'):
        target.write_text(result['merged_content'], encoding='utf-8')
        result['written'] = True
    else:
        result['written'] = False

    return result


def cmd_commit_generation(plugin_version: str, clean_dir: str | None = None) -> dict:
    """Create generation commits (base + optional merge).

    Without --clean-dir: single commit (base = commit).
    With --clean-dir: swaps clean versions in, commits base, restores merged, commits merge.
    """
    try:
        merge_applied = False
        merged_backups = {}

        if clean_dir:
            clean_path = Path(clean_dir)
            if not clean_path.exists():
                return {'status': 'error', 'message': f'Clean dir not found: {clean_dir}'}

            # Find files where merged differs from clean
            for clean_file in clean_path.rglob('*'):
                if clean_file.is_dir():
                    continue
                rel = clean_file.relative_to(clean_path)
                target = Path(str(rel))

                if target.exists():
                    current = target.read_text(encoding='utf-8')
                    clean = clean_file.read_text(encoding='utf-8')
                    if current != clean:
                        merged_backups[str(target)] = current
                        target.write_text(clean, encoding='utf-8')

            merge_applied = len(merged_backups) > 0

        # Stage and create base commit
        subprocess.run(
            ['git', 'add', '.memory_bank/', '.claude/', 'CLAUDE.md'],
            check=True, capture_output=True
        )

        status = subprocess.run(['git', 'diff', '--cached', '--quiet'], capture_output=True)
        if status.returncode == 0:
            return {'status': 'error', 'message': 'No changes to commit'}

        base_msg = f'[memento] Environment base\n\nPlugin version: {plugin_version}'
        subprocess.run(['git', 'commit', '-m', base_msg], check=True, capture_output=True)
        base_hash = subprocess.run(
            ['git', 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True
        ).stdout.strip()

        commit_hash = base_hash

        # If merge was applied, restore merged versions and create merge commit
        if merge_applied:
            for target_str, merged_content in merged_backups.items():
                Path(target_str).write_text(merged_content, encoding='utf-8')

            subprocess.run(
                ['git', 'add', '.memory_bank/', '.claude/', 'CLAUDE.md'],
                check=True, capture_output=True
            )
            subprocess.run(
                ['git', 'commit', '-m', '[memento] Environment merged with user changes'],
                check=True, capture_output=True
            )
            commit_hash = subprocess.run(
                ['git', 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True
            ).stdout.strip()

        # Update metadata and commit
        update_plan_metadata('Generation Base', base_hash)
        update_plan_metadata('Generation Commit', commit_hash)

        subprocess.run(
            ['git', 'add', str(GENERATION_PLAN)], check=True, capture_output=True
        )
        subprocess.run(
            ['git', 'commit', '-m', '[memento] Update generation metadata'],
            check=True, capture_output=True
        )

        return {
            'status': 'success',
            'generation_base': base_hash,
            'generation_commit': commit_hash,
            'merge_applied': merge_applied,
            'files_merged': list(merged_backups.keys())
        }

    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else str(e.stderr or e)
        return {'status': 'error', 'message': f'Git command failed: {stderr}'}


def cmd_recompute_source_hashes(plugin_root: str) -> dict:
    """Recompute source-hashes.json from prompts/ and static/ directories."""
    plugin_path = Path(plugin_root)
    hashes = {}

    # Scan prompts/ recursively for *.prompt files
    prompts_dir = plugin_path / 'prompts'
    if prompts_dir.exists():
        for f in prompts_dir.rglob('*.prompt'):
            rel = str(f.relative_to(plugin_path))
            hashes[rel] = compute_hash(f)

    # Scan static/ recursively for all files (exclude manifest.yaml and __pycache__)
    static_dir = plugin_path / 'static'
    if static_dir.exists():
        for f in static_dir.rglob('*'):
            if f.is_dir():
                continue
            if f.name == 'manifest.yaml':
                continue
            if '__pycache__' in f.parts:
                continue
            rel = str(f.relative_to(plugin_path))
            hashes[rel] = compute_hash(f)

    # Write sorted JSON
    sorted_hashes = dict(sorted(hashes.items()))
    output_path = plugin_path / SOURCE_HASHES_FILE
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(sorted_hashes, f, indent=2, ensure_ascii=False)
        f.write('\n')

    return {
        'status': 'success',
        'files': len(sorted_hashes),
        'written': SOURCE_HASHES_FILE
    }


def _file_location(file_str: str) -> tuple[str, str]:
    """Derive (file_name, location/) from a file path string."""
    p = Path(file_str)
    name = p.name
    location = './' if str(p.parent) == '.' else str(p.parent) + '/'
    return name, location


def _find_plan_row(content: str, file_name: str, location: str) -> re.Match | None:
    """Find a table row in generation-plan.md matching file_name + location."""
    escaped_name = re.escape(file_name)
    escaped_location = re.escape(location)
    pattern = re.compile(
        r'(\|\s*)\[[ x]\](\s*\|\s*)' + escaped_name + r'(\s*\|\s*)'
        + escaped_location + r'(\s*\|\s*)[^|]*(\s*\|\s*)[^|]*(\s*\|\s*)[^|]*(\s*\|)',
        re.MULTILINE
    )
    return pattern.search(content)


def _resolve_source_hash(file_str: str, plugin_path: Path,
                         source_hashes: dict | None) -> tuple[str, str | None]:
    """Resolve the source hash for a generated file. Returns (hash_str, warning_or_None)."""
    source_path = target_to_source_path(file_str, plugin_path)
    if not source_path:
        return '', None
    rel_source = str(source_path.relative_to(plugin_path))
    if source_hashes and rel_source in source_hashes:
        return source_hashes[rel_source], None
    if source_path.exists():
        return compute_hash(source_path), 'Source hash computed on-the-fly (not in source-hashes.json)'
    return '', None


def _location_to_section(location: str) -> str:
    """Map a file location to the generation-plan section header it belongs to."""
    if location.startswith('.memory_bank/guides/'):
        return '### Guides'
    if location.startswith('.memory_bank/workflows/'):
        return '### Workflows'
    if location.startswith('.memory_bank/patterns/'):
        return '### Patterns'
    if location.startswith('.claude/agents/'):
        return '### Agents'
    if location.startswith('.claude/commands/'):
        return '### Commands'
    if location.startswith('.claude/skills/'):
        return '### Skills'
    if location.startswith('.memory_bank/'):
        return '## Files'
    return '## Files'


def _insert_row_into_section(content: str, section_header: str, row: str) -> str:
    """Insert a table row at the end of the table in the given section."""
    # Find section header
    section_idx = content.find(section_header)
    if section_idx == -1:
        # Section doesn't exist — find last table row in entire ## Files
        section_idx = content.find('## Files')
        if section_idx == -1:
            return content

    # Find the last table row (| ... |) in this section, before next section header
    search_start = section_idx + len(section_header)
    # Find next section header (## or ###) after current section
    next_section = re.search(r'^#{2,3}\s+', content[search_start:], re.MULTILINE)
    search_end = search_start + next_section.start() if next_section else len(content)

    # Find last table row in range
    last_row_end = None
    for m in re.finditer(r'^\|.+\|$', content[search_start:search_end], re.MULTILINE):
        last_row_end = search_start + m.end()

    if last_row_end is not None:
        content = content[:last_row_end] + '\n' + row + content[last_row_end:]
    else:
        # No table rows found in section — append after section header line
        line_end = content.index('\n', section_idx)
        content = content[:line_end + 1] + '\n' + row + '\n' + content[line_end + 1:]

    return content


def cmd_update_plan(files: list[str], plugin_root: str,
                    remove_files: list[str] | None = None) -> dict:
    """Batch-update generation-plan.md: mark files complete with hashes and line counts.

    Auto-adds rows for files not already in the table.
    Removes rows for files listed in remove_files.
    """
    if not GENERATION_PLAN.exists():
        return {'status': 'error', 'message': 'generation-plan.md not found'}

    plugin_path = Path(plugin_root)
    source_hashes = load_source_hashes(plugin_root)

    content = GENERATION_PLAN.read_text(encoding='utf-8')
    updated = []
    added = []
    removed = []
    warnings = []

    for file_str in files:
        file_path = Path(file_str)
        if not file_path.exists():
            warnings.append({'file': file_str, 'warning': 'File not found'})
            continue

        file_hash = compute_hash(file_path)
        lines = count_lines(file_path)

        source_hash, src_warning = _resolve_source_hash(file_str, plugin_path, source_hashes)
        if src_warning:
            warnings.append({'file': file_str, 'warning': src_warning})

        file_name, location = _file_location(file_str)

        match = _find_plan_row(content, file_name, location)
        if match:
            replacement = (
                f'{match.group(1)}[x]{match.group(2)}{file_name}{match.group(3)}'
                f'{location}{match.group(4)}{lines}{match.group(5)}{file_hash}'
                f'{match.group(6)}{source_hash}{match.group(7)}'
            )
            content = content[:match.start()] + replacement + content[match.end():]
            updated.append({
                'file': file_str,
                'lines': lines,
                'hash': file_hash,
                'source_hash': source_hash if source_hash else None
            })
        else:
            # Auto-add: insert new row into the appropriate section
            new_row = f'| [x] | {file_name} | {location} | {lines} | {file_hash} | {source_hash} |'
            section = _location_to_section(location)
            content = _insert_row_into_section(content, section, new_row)
            added.append({
                'file': file_str,
                'lines': lines,
                'hash': file_hash,
                'source_hash': source_hash if source_hash else None
            })

    # Handle removals
    for file_str in (remove_files or []):
        file_name, location = _file_location(file_str)
        match = _find_plan_row(content, file_name, location)
        if match:
            # Remove the entire line (including trailing newline)
            start = match.start()
            end = match.end()
            if end < len(content) and content[end] == '\n':
                end += 1
            content = content[:start] + content[end:]
            removed.append({'file': file_str})
        else:
            warnings.append({'file': file_str, 'warning': 'Row not found for removal'})

    GENERATION_PLAN.write_text(content, encoding='utf-8')

    result: dict = {'status': 'success', 'updated': updated}
    if added:
        result['added'] = added
    if removed:
        result['removed'] = removed
    if warnings:
        result['warnings'] = warnings
    return result


def cmd_clean_obsolete(plugin_root: str) -> dict:
    """Remove obsolete entries from generation-plan.md and delete files from disk."""
    plugin_path = Path(plugin_root)
    analysis = load_project_analysis()
    if analysis is None:
        return {'status': 'error', 'message': 'project-analysis.json not found'}

    plan_data = parse_generation_plan()
    prompts_dir = plugin_path / 'prompts'
    all_prompts = []
    if prompts_dir.exists():
        for pf in sorted(prompts_dir.rglob('*.prompt')):
            fm = parse_prompt_frontmatter(pf)
            if fm:
                target = (fm.get('target_path', '') or '') + (fm.get('file', '') or '')
                applies = evaluate_conditional(fm.get('conditional'), analysis)
                all_prompts.append({'target': target, 'applies': applies})

    manifest = parse_manifest(plugin_path / 'static' / 'manifest.yaml')
    obsolete = detect_obsolete_files(plugin_path, plan_data, all_prompts, manifest, analysis)

    if not obsolete:
        return {'status': 'success', 'removed': [], 'deleted': []}

    # Remove from generation-plan.md
    targets = [o['target'] for o in obsolete]
    content = GENERATION_PLAN.read_text(encoding='utf-8')
    removed = []
    for target in targets:
        file_name, location = _file_location(target)
        match = _find_plan_row(content, file_name, location)
        if match:
            start = match.start()
            end = match.end()
            if end < len(content) and content[end] == '\n':
                end += 1
            content = content[:start] + content[end:]
            removed.append(target)
    GENERATION_PLAN.write_text(content, encoding='utf-8')

    # Delete files from disk
    deleted = []
    for target in targets:
        p = Path(target)
        if p.exists():
            p.unlink()
            deleted.append(target)

    return {'status': 'success', 'removed': removed, 'deleted': deleted}


def cmd_pre_update(plugin_root: str, new_analysis: str | None = None) -> dict:
    """Comprehensive pre-update check combining all detection steps.

    Combines: detect (local), detect-source-changes (plugin), prompt scan,
    manifest scan, obsolete detection, and optional tech-stack diff.
    """
    plugin_path = Path(plugin_root)

    analysis = load_project_analysis()
    if analysis is None:
        return {'status': 'error', 'message': 'project-analysis.json not found'}

    # Use new analysis for conditional evaluation if available
    # (detects files that become applicable after tech stack changes)
    eval_analysis = analysis
    if new_analysis:
        new_path = Path(new_analysis)
        if new_path.exists():
            try:
                eval_analysis = flatten_analysis(
                    json.loads(new_path.read_text(encoding='utf-8'))
                )
            except (json.JSONDecodeError, IOError):
                pass

    # 1. Detect local changes
    local_result = cmd_detect()

    # 2. Detect source changes
    source_result = cmd_detect_source_changes(plugin_root)

    # 3. Scan prompts for new/removed (include pending to avoid false "new" reports)
    plan_data = parse_generation_plan(include_pending=True)
    prompts_dir = plugin_path / 'prompts'
    all_prompts = []

    if prompts_dir.exists():
        for pf in sorted(prompts_dir.rglob('*.prompt')):
            fm = parse_prompt_frontmatter(pf)
            if fm:
                target = (fm.get('target_path', '') or '') + (fm.get('file', '') or '')
                applies = evaluate_conditional(fm.get('conditional'), eval_analysis)
                all_prompts.append({
                    'prompt_path': str(pf.relative_to(plugin_path)),
                    'target': target,
                    'conditional': fm.get('conditional'),
                    'applies': applies,
                    'priority': fm.get('priority', 99)
                })

    plan_targets = set(plan_data.keys())
    prompt_targets = {p['target'] for p in all_prompts}

    new_prompts = [p for p in all_prompts
                   if p['target'] not in plan_targets and p['applies']]

    removed_prompts = []
    for plan_target in plan_data:
        source = target_to_source_path(plan_target, plugin_path)
        if source and str(source).endswith('.prompt') and plan_target not in prompt_targets:
            removed_prompts.append({
                'target': plan_target,
                'expected_source': str(source)
            })

    # 4. Classify static files
    manifest = parse_manifest(plugin_path / 'static' / 'manifest.yaml')
    source_hashes = load_source_hashes(plugin_root)
    static_files = classify_static_files(
        manifest, plugin_path, plan_data, eval_analysis, source_hashes
    )

    # 5. Detect obsolete files
    obsolete = detect_obsolete_files(
        plugin_path, plan_data, all_prompts, manifest, eval_analysis
    )

    # 6. Optional tech-stack diff
    tech_diff = None
    tech_diff_error = None
    if new_analysis:
        new_path = Path(new_analysis)
        if not new_path.exists():
            tech_diff_error = f'File not found: {new_analysis}'
        else:
            try:
                new_data = json.loads(new_path.read_text(encoding='utf-8'))
                tech_diff = compare_tech_stacks(analysis, new_data)
            except (json.JSONDecodeError, IOError) as e:
                tech_diff_error = f'Failed to read {new_analysis}: {e}'

    summary = {
        'local_modified': local_result.get('summary', {}).get('modified', 0),
        'source_changed': source_result.get('summary', {}).get('changed', 0),
        'new_prompts': len(new_prompts),
        'removed_prompts': len(removed_prompts),
        'static_new': len(static_files.get('new', [])),
        'static_safe_overwrite': len(static_files.get('safe_overwrite', [])),
        'static_merge_needed': len(static_files.get('merge_needed', [])),
        'static_local_only': len(static_files.get('local_only', [])),
        'static_up_to_date': len(static_files.get('up_to_date', [])),
        'obsolete': len(obsolete)
    }

    # Build human-readable summary (only non-zero categories)
    summary_parts: list[str] = []
    if summary['source_changed']:
        summary_parts.append(f"Prompts changed ({summary['source_changed']})")
    if summary['new_prompts']:
        summary_parts.append(f"New prompts ({summary['new_prompts']})")
    static_bits: list[str] = []
    if summary['static_safe_overwrite']:
        static_bits.append(f"update ({summary['static_safe_overwrite']})")
    if summary['static_merge_needed']:
        static_bits.append(f"merge ({summary['static_merge_needed']})")
    if summary['static_new']:
        static_bits.append(f"new ({summary['static_new']})")
    if static_bits:
        summary_parts.append("Statics: " + ", ".join(static_bits))
    if summary['local_modified']:
        summary_parts.append(f"Local modified ({summary['local_modified']})")
    if summary['obsolete']:
        summary_parts.append(f"Obsolete ({summary['obsolete']})")
    summary_text = ", ".join(summary_parts) if summary_parts else "No changes detected"

    # Get base commit for 3-way merge
    metadata = parse_plan_metadata()
    base_commit = metadata.get('Generation Base')

    return {
        'status': 'success',
        'base_commit': base_commit,
        'local_changes': {
            'modified': local_result.get('modified', []),
            'unchanged': local_result.get('unchanged', [])
        },
        'source_changes': {
            'changed': source_result.get('changed', []),
            'unchanged': source_result.get('unchanged', [])
        },
        'new_prompts': new_prompts,
        'removed_prompts': removed_prompts,
        'static_files': static_files,
        'obsolete_files': obsolete,
        'tech_stack_diff': tech_diff,
        'tech_stack_diff_error': tech_diff_error,
        'summary': summary,
        'summary_text': summary_text
    }


def cmd_copy_static(plugin_root: str, clean_dir: str | None = None,
                    filter_categories: str | None = None,
                    base_commit: str | None = None) -> dict:
    """Copy applicable static files from plugin to project with optional merge.

    Categories: new, safe_overwrite, merge_needed, local_only, up_to_date.
    Default filter: new,safe_overwrite,merge_needed
    """
    plugin_path = Path(plugin_root)

    analysis = load_project_analysis()
    if analysis is None:
        return {'status': 'error', 'message': 'project-analysis.json not found'}

    manifest_path = plugin_path / 'static' / 'manifest.yaml'
    manifest = parse_manifest(manifest_path)
    if not manifest:
        return {'status': 'error', 'message': 'manifest.yaml not found or empty'}

    plan_data = parse_generation_plan()
    source_hashes = load_source_hashes(plugin_root)
    classified = classify_static_files(
        manifest, plugin_path, plan_data, analysis, source_hashes
    )

    cats = (['new', 'safe_overwrite', 'merge_needed']
            if filter_categories is None
            else [c.strip() for c in filter_categories.split(',')])

    clean_path = Path(clean_dir) if clean_dir else None

    copied: list = []
    auto_merged: list = []
    has_conflicts: list = []
    skipped: list = []

    for cat in cats:
        files = classified.get(cat, [])
        for entry in files:
            source_file = plugin_path / 'static' / entry['source']
            target_path = Path(entry['target'])

            if not source_file.exists():
                skipped.append({
                    'source': entry['source'], 'target': entry['target'],
                    'reason': 'source_not_found'
                })
                continue

            source_content = source_file.read_text(encoding='utf-8')
            target_path.parent.mkdir(parents=True, exist_ok=True)

            if clean_path:
                clean_target = clean_path / entry['target']
                clean_target.parent.mkdir(parents=True, exist_ok=True)
                clean_target.write_text(source_content, encoding='utf-8')

            if cat in ('new', 'safe_overwrite'):
                target_path.write_text(source_content, encoding='utf-8')
                copied.append({
                    'source': entry['source'], 'target': entry['target'],
                    'action': cat
                })

            elif cat == 'merge_needed':
                if base_commit and target_path.exists():
                    local_content = target_path.read_text(encoding='utf-8')
                    base_content = git_show(base_commit, entry['target'])

                    if base_content is None:
                        has_conflicts.append({
                            'target': entry['target'],
                            'reason': 'no_base_content',
                            'message': f'git show {base_commit}:{entry["target"]} failed'
                        })
                        continue

                    merge_result = merge_markdown_3way(
                        base_content, local_content, source_content
                    )

                    if merge_result['status'] == 'merged':
                        target_path.write_text(
                            merge_result['merged_content'], encoding='utf-8'
                        )
                        auto_merged.append({
                            'target': entry['target'],
                            'stats': merge_result['stats']
                        })
                    else:
                        # Don't write on conflicts — leave local file intact
                        # for LLM/user resolution (consistent with merge --write)
                        has_conflicts.append({
                            'target': entry['target'],
                            'conflicts': merge_result['conflicts'],
                            'stats': merge_result['stats']
                        })
                else:
                    target_path.write_text(source_content, encoding='utf-8')
                    copied.append({
                        'source': entry['source'], 'target': entry['target'],
                        'action': 'overwrite_no_base'
                    })

            elif cat in ('local_only', 'up_to_date'):
                skipped.append({
                    'source': entry['source'], 'target': entry['target'],
                    'reason': cat
                })

    # Report skipped-conditional files always
    for entry in classified.get('skipped_conditional', []):
        skipped.append({
            'source': entry.get('source', ''),
            'target': entry.get('target', ''),
            'reason': 'condition_false'
        })

    return {
        'status': 'success',
        'copied': copied,
        'auto_merged': auto_merged,
        'has_conflicts': has_conflicts,
        'skipped': skipped,
        'summary': {
            'copied': len(copied),
            'auto_merged': len(auto_merged),
            'conflicts': len(has_conflicts),
            'skipped': len(skipped)
        }
    }


def cmd_check_existing(memory_bank: str = '.memory_bank') -> dict:
    """Check if a Memory Bank environment exists and its state.

    Returns: {exists, modified_count, base_commit}
    """
    mb_path = Path(memory_bank)
    plan_path = mb_path / 'generation-plan.md'

    if not mb_path.exists() or not plan_path.exists():
        return {'exists': False, 'modified_count': 0, 'base_commit': None}

    # Count modifications
    stored_data = parse_generation_plan()
    modified_count = 0
    for path, data in stored_data.items():
        target = Path(path)
        if target.exists():
            stored_hash = data.get('hash')
            if stored_hash and compute_hash(target) != stored_hash:
                modified_count += 1

    # Get base commit from plan metadata
    metadata = parse_plan_metadata()
    base_commit = metadata.get('Generation Base')

    return {
        'exists': True,
        'modified_count': modified_count,
        'base_commit': base_commit,
        'total_files': len(stored_data),
    }


def cmd_plan_generation(plugin_root: str, analysis_path: str,
                        output: str | None = None,
                        only_changed: bool = False) -> dict:
    """Build generation plan: scan prompts + manifest, evaluate conditionals.

    Returns JSON list of [{prompt_path, target, priority, type}] for files that
    pass their conditional checks, plus writes a human-readable generation-plan.md.

    If only_changed=True, filters prompt_items to only include prompts whose
    source has changed since last generation (compares source hashes in
    generation-plan.md vs current source-hashes.json).
    """
    plugin_path = Path(plugin_root)
    analysis_file = Path(analysis_path)

    if not analysis_file.exists():
        return {'status': 'error', 'message': f'Analysis file not found: {analysis_path}'}

    analysis = flatten_analysis(json.loads(analysis_file.read_text(encoding='utf-8')))
    source_hashes = load_source_hashes(plugin_root)

    plan_items: list[dict] = []

    # 1. Scan prompt templates
    prompts_dir = plugin_path / 'prompts'
    if prompts_dir.exists():
        for pf in sorted(prompts_dir.rglob('*.prompt')):
            fm = parse_prompt_frontmatter(pf)
            if not fm:
                continue
            target = (fm.get('target_path', '') or '') + (fm.get('file', '') or '')
            conditional = fm.get('conditional')
            if evaluate_conditional(conditional, analysis):
                rel_prompt = str(pf.relative_to(plugin_path))
                source_hash = ''
                if source_hashes and rel_prompt in source_hashes:
                    source_hash = source_hashes[rel_prompt]
                plan_items.append({
                    'prompt_path': rel_prompt,
                    'target': target,
                    'priority': fm.get('priority', 99),
                    'type': 'prompt',
                    'conditional': conditional,
                    'source_hash': source_hash,
                })

    # 2. Scan manifest for static files
    manifest_path = plugin_path / 'static' / 'manifest.yaml'
    manifest = parse_manifest(manifest_path)
    for entry in manifest:
        conditional = entry.get('conditional')
        if evaluate_conditional(conditional, analysis):
            source_rel = 'static/' + entry['source']
            source_hash = ''
            if source_hashes and source_rel in source_hashes:
                source_hash = source_hashes[source_rel]
            plan_items.append({
                'source': source_rel,
                'target': entry['target'],
                'priority': 0,  # static files are copied first
                'type': 'static',
                'conditional': conditional,
                'source_hash': source_hash,
            })

    # Sort by priority then target
    plan_items.sort(key=lambda x: (x['priority'], x['target']))

    # Write human-readable generation-plan.md
    prompt_items = [p for p in plan_items if p['type'] == 'prompt']
    static_items = [p for p in plan_items if p['type'] == 'static']
    plan_md = _build_generation_plan_md(prompt_items, static_items)

    plan_out = Path(output) if output else GENERATION_PLAN
    plan_out.parent.mkdir(parents=True, exist_ok=True)
    plan_out.write_text(plan_md, encoding='utf-8')

    # Filter to only changed prompts if requested
    if only_changed:
        source_changes = cmd_detect_source_changes(plugin_root)
        changed_targets = {
            item['generated'] for item in source_changes.get('changed', [])
        }
        prompt_items = [p for p in prompt_items if p['target'] in changed_targets]
        plan_items = [p for p in plan_items
                      if p['type'] == 'static' or p['target'] in changed_targets]

    return {
        'status': 'success',
        'plan': plan_items,
        'prompt_items': prompt_items,
        'static_items': static_items,
        'prompts': len(prompt_items),
        'statics': len(static_items),
        'total': len(plan_items),
        'plan_file': str(plan_out),
    }


def _build_generation_plan_md(prompts: list[dict], statics: list[dict]) -> str:
    """Build the human-readable generation-plan.md content."""
    lines = ['# Generation Plan', '', '## Metadata', '', '## Files', '',
             '| Status | File | Location | Lines | Hash | Source Hash |',
             '|--------|------|----------|-------|------|-------------|']

    # Group prompts by location prefix
    for item in prompts:
        target = item['target']
        p = Path(target)
        name = p.name
        location = './' if str(p.parent) == '.' else str(p.parent) + '/'
        lines.append(f'| [ ] | {name} | {location} | | | |')

    if statics:
        lines.append('')
        lines.append('### Static Files')
        lines.append('')
        lines.append('| Status | File | Location | Lines | Hash | Source Hash |')
        lines.append('|--------|------|----------|-------|------|-------------|')
        for item in statics:
            target = item['target']
            p = Path(target)
            name = p.name
            location = './' if str(p.parent) == '.' else str(p.parent) + '/'
            lines.append(f'| [ ] | {name} | {location} | | | |')

    lines.append('')
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='Analyze local modifications in Memory Bank files'
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # compute
    compute_parser = subparsers.add_parser('compute', help='Compute hash for files')
    compute_parser.add_argument('files', nargs='+', help='Files to hash')

    # compute-all
    subparsers.add_parser('compute-all', help='Compute hashes for all MB files')

    # compute-source
    compute_source_parser = subparsers.add_parser('compute-source', help='Compute hash for source prompt/static files')
    compute_source_parser.add_argument('files', nargs='+', help='Source files to hash (relative to plugin root)')
    compute_source_parser.add_argument('--plugin-root', required=True, help='Path to plugin root directory')

    # detect
    subparsers.add_parser('detect', help='Detect modified files (local changes)')

    # detect-source-changes
    detect_source_parser = subparsers.add_parser('detect-source-changes', help='Detect changed plugin prompts/statics')
    detect_source_parser.add_argument('--plugin-root', required=True, help='Path to plugin root directory')

    # analyze
    analyze_parser = subparsers.add_parser('analyze', help='Analyze changes in file')
    analyze_parser.add_argument('file', help='File to analyze')
    analyze_parser.add_argument('--base', help='Base content file for comparison')

    # analyze-all
    subparsers.add_parser('analyze-all', help='Analyze all modified files')

    # merge
    merge_parser = subparsers.add_parser('merge', help='3-way merge of markdown file')
    merge_parser.add_argument('target', help='Target file path (reads local content)')
    merge_parser.add_argument('--base-commit', required=True, help='Generation Base commit hash')
    merge_parser.add_argument('--new-file', required=True, help='Path to new version of file')
    merge_parser.add_argument('--write', action='store_true',
                              help='Write merged content to target if no conflicts')

    # commit-generation
    commit_gen_parser = subparsers.add_parser('commit-generation', help='Create generation commits')
    commit_gen_parser.add_argument('--plugin-version', required=True, help='Plugin version')
    commit_gen_parser.add_argument('--clean-dir', help='Dir with clean versions (enables two-commit mode)')

    # recompute-source-hashes
    recompute_parser = subparsers.add_parser('recompute-source-hashes', help='Recompute source-hashes.json')
    recompute_parser.add_argument('--plugin-root', required=True, help='Path to plugin root directory')

    # update-plan
    update_plan_parser = subparsers.add_parser('update-plan', help='Batch-update generation-plan.md')
    update_plan_parser.add_argument('files', nargs='+', help='Generated files to mark complete')
    update_plan_parser.add_argument('--plugin-root', required=True, help='Path to plugin root directory')
    update_plan_parser.add_argument('--remove', nargs='+', default=None, help='Files to remove from plan')

    # clean-obsolete
    clean_obs_parser = subparsers.add_parser('clean-obsolete', help='Remove obsolete files and plan entries')
    clean_obs_parser.add_argument('--plugin-root', required=True, help='Path to plugin root directory')

    # pre-update
    pre_update_parser = subparsers.add_parser('pre-update', help='Comprehensive pre-update check')
    pre_update_parser.add_argument('--plugin-root', required=True, help='Path to plugin root directory')
    pre_update_parser.add_argument('--new-analysis', default=None,
                                   help='Path to new project-analysis.json for tech-stack diff')

    # copy-static
    copy_static_parser = subparsers.add_parser('copy-static', help='Copy applicable static files')
    copy_static_parser.add_argument('--plugin-root', required=True, help='Path to plugin root directory')
    copy_static_parser.add_argument('--clean-dir', default=None,
                                    help='Directory to save clean versions for commit-generation')
    copy_static_parser.add_argument('--filter', default=None,
                                    help='Comma-separated categories: new,safe_overwrite,merge_needed')
    copy_static_parser.add_argument('--base-commit', default=None,
                                    help='Generation Base commit hash (enables 3-way merge for merge_needed)')

    # check-existing
    check_existing_parser = subparsers.add_parser('check-existing', help='Check if Memory Bank environment exists')
    check_existing_parser.add_argument('--memory-bank', default='.memory_bank',
                                       help='Path to .memory_bank directory')

    # plan-generation
    plan_gen_parser = subparsers.add_parser('plan-generation', help='Build generation plan from prompts + manifest')
    plan_gen_parser.add_argument('--plugin-root', required=True, help='Path to plugin root directory')
    plan_gen_parser.add_argument('--analysis', required=True, help='Path to project-analysis.json')
    plan_gen_parser.add_argument('--output', default=None, help='Output path for generation-plan.md')
    plan_gen_parser.add_argument('--only-changed', action='store_true',
                                 help='Only include prompts whose source has changed')

    args = parser.parse_args()

    if args.command == 'compute':
        result = cmd_compute(args.files)
    elif args.command == 'compute-all':
        result = cmd_compute_all()
    elif args.command == 'compute-source':
        result = cmd_compute_source(args.files, args.plugin_root)
    elif args.command == 'detect':
        result = cmd_detect()
    elif args.command == 'detect-source-changes':
        result = cmd_detect_source_changes(args.plugin_root)
    elif args.command == 'analyze':
        base_content = None
        if args.base:
            base_content = Path(args.base).read_text(encoding='utf-8')
        result = cmd_analyze(args.file, base_content)
    elif args.command == 'analyze-all':
        result = cmd_analyze_all()
    elif args.command == 'merge':
        result = cmd_merge(args.target, args.base_commit, args.new_file, args.write)
    elif args.command == 'commit-generation':
        result = cmd_commit_generation(args.plugin_version, args.clean_dir)
    elif args.command == 'recompute-source-hashes':
        result = cmd_recompute_source_hashes(args.plugin_root)
    elif args.command == 'update-plan':
        result = cmd_update_plan(args.files, args.plugin_root, args.remove)
    elif args.command == 'clean-obsolete':
        result = cmd_clean_obsolete(args.plugin_root)
    elif args.command == 'pre-update':
        result = cmd_pre_update(args.plugin_root, args.new_analysis)
    elif args.command == 'copy-static':
        result = cmd_copy_static(args.plugin_root, args.clean_dir,
                                 args.filter, args.base_commit)
    elif args.command == 'check-existing':
        result = cmd_check_existing(args.memory_bank)
    elif args.command == 'plan-generation':
        result = cmd_plan_generation(args.plugin_root, args.analysis, args.output,
                                     args.only_changed)
    else:
        parser.print_help()
        sys.exit(1)

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()

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
  update-plan <files>      Batch-update generation-plan.md with hashes and line counts

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
from typing import Optional


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


def load_source_hashes(plugin_root: str) -> Optional[dict[str, str]]:
    """Load pre-computed source hashes from source-hashes.json if it exists."""
    json_path = Path(plugin_root) / SOURCE_HASHES_FILE
    if json_path.exists():
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def target_to_source_path(gen_path: str, plugin_path: Path) -> Optional[Path]:
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


def get_all_mb_files() -> list[Path]:
    """Get all markdown files in Memory Bank and .claude directories."""
    files = []

    if MEMORY_BANK_DIR.exists():
        files.extend(MEMORY_BANK_DIR.rglob("*.md"))

    if CLAUDE_DIR.exists():
        files.extend(CLAUDE_DIR.rglob("*.md"))

    return sorted(files)


def parse_generation_plan() -> dict[str, dict]:
    """Parse generation-plan.md and extract file -> {hash, source_hash} mapping."""
    if not GENERATION_PLAN.exists():
        return {}

    stored_data = {}
    content = GENERATION_PLAN.read_text(encoding='utf-8')

    # Parse markdown table rows with [x] status
    # Format: | [x] | filename | location | lines | hash | source_hash |
    # Also support old format without source_hash: | [x] | filename | location | lines | hash |
    pattern_new = r'\|\s*\[x\]\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|'
    pattern_old = r'\|\s*\[x\]\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|'

    # Try new format first
    for match in re.finditer(pattern_new, content):
        filename = match.group(1).strip()
        location = match.group(2).strip()
        hash_value = match.group(4).strip()
        source_hash = match.group(5).strip()

        if hash_value and hash_value != '':
            full_path = f"{location}{filename}"
            stored_data[full_path] = {
                'hash': hash_value,
                'source_hash': source_hash if source_hash else None
            }

    # If no matches with new format, try old format
    if not stored_data:
        for match in re.finditer(pattern_old, content):
            filename = match.group(1).strip()
            location = match.group(2).strip()
            hash_value = match.group(4).strip()

            if hash_value and hash_value != '':
                full_path = f"{location}{filename}"
                stored_data[full_path] = {
                    'hash': hash_value,
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
            diff_content = [l for l in diff if not l.startswith('---') and not l.startswith('+++') and not l.startswith('@@')]

            added_lines = [l[1:] for l in diff_content if l.startswith('+')]
            removed_lines = [l[1:] for l in diff_content if l.startswith('-')]

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

def git_show(commit: str, file_path: str) -> Optional[str]:
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
            entry = {
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


def cmd_analyze(file_path: str, base_content: Optional[str] = None) -> dict:
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


def cmd_merge(target_path: str, base_commit: str, new_file: str) -> dict:
    """3-way merge: recover base from git, read local, read new, merge."""
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
        return {
            'status': 'no_local_changes',
            'merged_content': new_content,
            'conflicts': [],
            'stats': {'message': 'No local changes, using new version as-is'}
        }

    result = merge_markdown_3way(base_content, local_content, new_content)
    result['target'] = target_path
    result['base_commit'] = base_commit
    return result


def cmd_commit_generation(plugin_version: str, clean_dir: Optional[str] = None) -> dict:
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


def cmd_update_plan(files: list[str], plugin_root: str) -> dict:
    """Batch-update generation-plan.md: mark files complete with hashes and line counts."""
    if not GENERATION_PLAN.exists():
        return {'status': 'error', 'message': 'generation-plan.md not found'}

    plugin_path = Path(plugin_root)
    source_hashes = load_source_hashes(plugin_root)

    content = GENERATION_PLAN.read_text(encoding='utf-8')
    updated = []
    warnings = []

    for file_str in files:
        file_path = Path(file_str)
        if not file_path.exists():
            warnings.append({'file': file_str, 'warning': 'File not found'})
            continue

        file_hash = compute_hash(file_path)
        lines = count_lines(file_path)

        # Determine source hash
        source_hash = ''
        source_path = target_to_source_path(file_str, plugin_path)
        if source_path:
            rel_source = str(source_path.relative_to(plugin_path))
            if source_hashes and rel_source in source_hashes:
                source_hash = source_hashes[rel_source]
            elif source_path.exists():
                source_hash = compute_hash(source_path)
                warnings.append({'file': file_str, 'warning': 'Source hash computed on-the-fly (not in source-hashes.json)'})

        # Find and update the row in generation-plan.md
        # Match row by file name and location
        # Format: | [ ] | filename | location/ | ~NNN | | |
        # or:     | [x] | filename | location/ | NNN | hash | source_hash |
        file_name = file_path.name
        # Derive location from file path (directory with trailing /)
        if str(file_path.parent) == '.':
            location = './'
        else:
            location = str(file_path.parent) + '/'

        # Build regex to match the table row for this file
        # Escape dots in filename for regex
        escaped_name = re.escape(file_name)
        escaped_location = re.escape(location)
        pattern = re.compile(
            r'(\|\s*)\[[ x]\](\s*\|\s*)' + escaped_name + r'(\s*\|\s*)' + escaped_location + r'(\s*\|\s*)[^|]*(\s*\|\s*)[^|]*(\s*\|\s*)[^|]*(\s*\|)',
            re.MULTILINE
        )

        match = pattern.search(content)
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
            warnings.append({'file': file_str, 'warning': 'Row not found in generation-plan.md'})

    GENERATION_PLAN.write_text(content, encoding='utf-8')

    result = {'status': 'success', 'updated': updated}
    if warnings:
        result['warnings'] = warnings
    return result


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
        result = cmd_merge(args.target, args.base_commit, args.new_file)
    elif args.command == 'commit-generation':
        result = cmd_commit_generation(args.plugin_version, args.clean_dir)
    elif args.command == 'recompute-source-hashes':
        result = cmd_recompute_source_hashes(args.plugin_root)
    elif args.command == 'update-plan':
        result = cmd_update_plan(args.files, args.plugin_root)
    else:
        parser.print_help()
        sys.exit(1)

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()

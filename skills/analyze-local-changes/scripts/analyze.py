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

All output is JSON for easy parsing by Claude.
"""

import argparse
import difflib
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Optional


# Configuration
HASH_LENGTH = 8
GENERATION_PLAN = Path(".memory_bank/generation-plan.md")
MEMORY_BANK_DIR = Path(".memory_bank")
CLAUDE_DIR = Path(".claude")


def compute_hash(file_path: Path, length: int = HASH_LENGTH) -> str:
    """Compute MD5 hash of file content."""
    with open(file_path, 'rb') as f:
        md5 = hashlib.md5(f.read()).hexdigest()
    return md5[:length]


def count_lines(file_path: Path) -> int:
    """Count lines in file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return sum(1 for _ in f)


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
    """Compute hashes for source prompt/static files in plugin."""
    results = []

    for file_str in files:
        # Resolve path relative to plugin root
        if file_str.startswith('/'):
            file_path = Path(file_str)
        else:
            file_path = Path(plugin_root) / file_str

        if file_path.exists():
            results.append({
                'path': str(file_path),
                'relative_path': file_str,
                'hash': compute_hash(file_path),
                'lines': count_lines(file_path)
            })
        else:
            results.append({
                'path': str(file_path),
                'relative_path': file_str,
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
    """Detect which plugin prompts/statics have changed since generation."""
    if not GENERATION_PLAN.exists():
        return {'status': 'error', 'message': 'generation-plan.md not found'}

    stored_data = parse_generation_plan()
    plugin_path = Path(plugin_root)

    changed = []
    unchanged = []
    missing_source = []
    no_source_hash = []

    # Map of generated file -> source prompt path
    # Generated files in .memory_bank/ come from prompts/memory_bank/
    # Generated files in .claude/agents/ come from prompts/agents/
    # etc.

    for gen_path, data in stored_data.items():
        source_hash = data.get('source_hash')

        if not source_hash:
            no_source_hash.append(gen_path)
            continue

        # Determine source path based on generated path
        source_path = None
        if gen_path.startswith('.memory_bank/'):
            # .memory_bank/guides/testing.md -> prompts/memory_bank/guides/testing.md.prompt
            rel_path = gen_path[len('.memory_bank/'):]
            source_path = plugin_path / 'prompts' / 'memory_bank' / (rel_path + '.prompt')
            # Also check static files
            if not source_path.exists():
                source_path = plugin_path / 'static' / 'memory_bank' / rel_path
        elif gen_path.startswith('.claude/agents/'):
            rel_path = gen_path[len('.claude/agents/'):]
            source_path = plugin_path / 'prompts' / 'agents' / (rel_path + '.prompt')
        elif gen_path.startswith('.claude/commands/'):
            rel_path = gen_path[len('.claude/commands/'):]
            source_path = plugin_path / 'prompts' / 'commands' / (rel_path + '.prompt')
        elif gen_path == 'CLAUDE.md':
            source_path = plugin_path / 'prompts' / 'CLAUDE.md.prompt'

        if source_path and source_path.exists():
            current_hash = compute_hash(source_path)
            if current_hash == source_hash:
                unchanged.append({
                    'generated': gen_path,
                    'source': str(source_path)
                })
            else:
                changed.append({
                    'generated': gen_path,
                    'source': str(source_path),
                    'stored_hash': source_hash,
                    'current_hash': current_hash
                })
        elif source_path:
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
    else:
        parser.print_help()
        sys.exit(1)

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()

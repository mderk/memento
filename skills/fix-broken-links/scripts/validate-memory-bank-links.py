#!/usr/bin/env python3
"""
Validate Memory Bank links and file integrity.

Simple validator that:
1. Scans .memory_bank/ directory
2. Validates all markdown links in index.md files
3. Validates cross-references between files
4. Reports broken links and encoding issues

Does NOT require generation-plan.md - works standalone.
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple


def find_markdown_links(file_path: Path) -> List[Tuple[str, str]]:
    """
    Extract all markdown links from a file.

    Returns: List of (link_text, link_target) tuples
    """
    if not file_path.exists():
        return []

    try:
        content = file_path.read_text(encoding='utf-8')
    except UnicodeDecodeError as e:
        rel_path = file_path.relative_to(Path.cwd()) if file_path.is_relative_to(Path.cwd()) else file_path
        print(f"\n❌ ENCODING ERROR: {rel_path}")
        print(f"   Error: {e}")
        print(f"   Memory Bank files must be valid UTF-8.")
        print(f"   Fix: Re-save file as UTF-8 or regenerate.\n")
        sys.exit(1)

    # Match markdown links: [text](target)
    pattern = r'\[([^\]]+)\]\(([^)]+)\)'
    links = []

    for match in re.finditer(pattern, content):
        link_text = match.group(1)
        link_target = match.group(2)

        # Skip external links (http://, https://, mailto:)
        if not link_target.startswith(('http://', 'https://', 'mailto:', '#')):
            links.append((link_text, link_target))

    return links


def resolve_link(source_file: Path, link_target: str, base_dir: Path) -> Path:
    """
    Resolve a relative link from source_file to absolute path.

    Handles:
    - Relative paths: ./file.md, ../file.md
    - Absolute paths from repo root: /.memory_bank/file.md
    """
    # Remove anchor fragments
    if '#' in link_target:
        link_target = link_target.split('#')[0]

    if not link_target:  # Pure anchor link
        return source_file

    # If starts with /, it's from repo root
    if link_target.startswith('/'):
        return base_dir / link_target.lstrip('/')

    # Otherwise resolve relative to source file
    return (source_file.parent / link_target).resolve()


def validate_index_links(memory_bank_dir: Path, base_dir: Path) -> Tuple[int, int, List[str]]:
    """
    Find all index.md files in Memory Bank and validate their links.

    Returns: (total_links, valid_links, broken_links_with_details)
    """
    index_files = list(memory_bank_dir.rglob('index.md'))

    total_links = 0
    valid_links = 0
    broken = []

    for index_file in index_files:
        links = find_markdown_links(index_file)

        for link_text, link_target in links:
            total_links += 1
            resolved = resolve_link(index_file, link_target, base_dir)

            if resolved.exists():
                valid_links += 1
            else:
                rel_source = index_file.relative_to(base_dir)
                rel_target = resolved.relative_to(base_dir) if resolved.is_relative_to(base_dir) else resolved
                broken.append(f"{rel_source}: [{link_text}]({link_target}) → {rel_target}")

    return total_links, valid_links, broken


def validate_cross_references(memory_bank_dir: Path, base_dir: Path) -> Tuple[int, int, List[str], List[str]]:
    """
    Check all markdown links in all .md files in Memory Bank (cross-references).

    Returns: (total_refs, valid_refs, broken_refs, placeholder_refs)
    """
    md_files = list(memory_bank_dir.rglob('*.md'))

    total_refs = 0
    valid_refs = 0
    broken = []
    placeholders = []

    for md_file in md_files:
        links = find_markdown_links(md_file)

        for link_text, link_target in links:
            total_refs += 1

            # Check for placeholder links (internal, TBD, TODO, etc.)
            if link_target in ('internal', 'TBD', 'TODO', 'tbd', 'todo'):
                rel_source = md_file.relative_to(base_dir)
                placeholders.append(f"{rel_source}: [{link_text}]({link_target})")
                continue

            resolved = resolve_link(md_file, link_target, base_dir)

            if resolved.exists():
                valid_refs += 1
            else:
                rel_source = md_file.relative_to(base_dir)
                rel_target = resolved.relative_to(base_dir) if resolved.is_relative_to(base_dir) else resolved
                broken.append(f"{rel_source}: [{link_text}]({link_target}) → {rel_target}")

    return total_refs, valid_refs, broken, placeholders


def main():
    """Main validation function."""
    # Determine base directory (where script is run from)
    base_dir = Path.cwd()

    # Find .memory_bank directory
    memory_bank_dir = base_dir / '.memory_bank'

    if not memory_bank_dir.exists():
        print(f"❌ No .memory_bank directory found at: {memory_bank_dir}")
        print(f"   Current directory: {base_dir}")
        print(f"   Run this script from project root")
        sys.exit(1)

    print(f"🔍 Validating Memory Bank links...\n")
    print(f"   Working directory: {base_dir}")
    print(f"   Memory Bank: {memory_bank_dir}\n")

    # Step 1: Validate index links
    print("1️⃣  Validating index.md links...")
    total_idx_links, valid_idx_links, broken_idx = validate_index_links(memory_bank_dir, base_dir)

    if broken_idx:
        print(f"❌ {len(broken_idx)} broken index links:")
        for link in broken_idx[:10]:
            print(f"   - {link}")
        if len(broken_idx) > 10:
            print(f"   ... and {len(broken_idx) - 10} more")
    else:
        print(f"✅ All {valid_idx_links} index links valid")

    # Step 2: Validate cross-references
    print("\n2️⃣  Validating cross-references...")
    total_refs, valid_refs, broken_refs, placeholders = validate_cross_references(memory_bank_dir, base_dir)

    if broken_refs:
        print(f"⚠️  {len(broken_refs)} broken cross-references:")
        for ref in broken_refs[:10]:
            print(f"   - {ref}")
        if len(broken_refs) > 10:
            print(f"   ... and {len(broken_refs) - 10} more")
    else:
        print(f"✅ All {valid_refs} cross-references valid")

    # Show placeholders separately (info only)
    if placeholders:
        print(f"\nℹ️  {len(placeholders)} placeholder links (intentional):")
        for ref in placeholders[:5]:
            print(f"   - {ref}")
        if len(placeholders) > 5:
            print(f"   ... and {len(placeholders) - 5} more")

    # Summary
    print("\n" + "=" * 60)
    print("📊 VALIDATION SUMMARY")
    print("=" * 60)
    print(f"Index links:      {valid_idx_links}/{total_idx_links} valid")
    print(f"Cross-references: {valid_refs}/{total_refs} valid")
    if placeholders:
        print(f"Placeholders:     {len(placeholders)} intentional")

    # Exit code - broken links = error
    has_errors = len(broken_idx) > 0 or len(broken_refs) > 0

    if has_errors:
        print("\n❌ Validation FAILED")
        if len(broken_idx) > 0:
            print(f"   - {len(broken_idx)} broken index.md links")
        if len(broken_refs) > 0:
            print(f"   - {len(broken_refs)} broken cross-references")
        print("\n⚠️  Fix or remove broken links.")
        sys.exit(1)
    else:
        print("\n✅ All validation checks passed!")
        sys.exit(0)


if __name__ == '__main__':
    main()

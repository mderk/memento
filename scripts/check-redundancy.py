#!/usr/bin/env python3
"""
Check redundancy in markdown files.

Analyzes repeated phrases and calculates redundancy percentage.
Exit codes:
  0 - Success (redundancy <= 10%)
  1 - High redundancy (> 10%)
  2 - Error
"""

import sys
import re
from collections import Counter
from pathlib import Path


def extract_phrases(text, min_words=2, max_words=5):
    """Extract phrases of 2-5 words from text."""
    # Remove markdown syntax and code blocks
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`[^`]+`', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = re.sub(r'[#*_\-]', ' ', text)

    # Tokenize into words
    words = re.findall(r'\b[a-zA-Z][a-zA-Z0-9_-]*\b', text.lower())

    phrases = []
    for n in range(min_words, max_words + 1):
        for i in range(len(words) - n + 1):
            phrase = ' '.join(words[i:i + n])
            # Skip common phrases
            if not is_common_phrase(phrase):
                phrases.append(phrase)

    return phrases


def is_common_phrase(phrase):
    """Filter out common English phrases and domain terminology."""
    common = {
        'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
        'should', 'could', 'may', 'might', 'must', 'can',
        'this is', 'that is', 'it is', 'there is', 'there are',
        'you can', 'we can', 'to the', 'in the', 'of the', 'for the',
        'and the', 'on the', 'at the', 'from the', 'with the',
    }

    # Check if phrase starts with common words
    first_word = phrase.split()[0]
    if first_word in common:
        return True

    # Check if entire phrase is common
    if phrase in common:
        return True

    return False


def calculate_redundancy(file_path):
    """Calculate redundancy percentage for a file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Extract all phrases
        phrases = extract_phrases(content)

        if not phrases:
            return 0.0, [], 0

        # Count phrase frequencies
        phrase_counts = Counter(phrases)

        # Find repeated phrases (appearing 2+ times)
        repeated = {phrase: count for phrase, count in phrase_counts.items() if count >= 2}

        # Calculate redundancy: (total repeated occurrences - unique count) / total phrases
        if repeated:
            total_repeated_occurrences = sum(repeated.values())
            unique_repeated_count = len(repeated)
            redundant_occurrences = total_repeated_occurrences - unique_repeated_count
            redundancy_pct = (redundant_occurrences / len(phrases)) * 100
        else:
            redundancy_pct = 0.0

        # Sort by frequency for reporting
        top_repeated = sorted(repeated.items(), key=lambda x: x[1], reverse=True)[:10]

        return redundancy_pct, top_repeated, len(phrases)

    except Exception as e:
        print(f"Error analyzing {file_path}: {e}", file=sys.stderr)
        return None, [], 0


def main():
    if len(sys.argv) < 2:
        print("Usage: check-redundancy.py <file>", file=sys.stderr)
        sys.exit(2)

    file_path = Path(sys.argv[1])

    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(2)

    redundancy_pct, top_repeated, total_phrases = calculate_redundancy(file_path)

    if redundancy_pct is None:
        sys.exit(2)

    # Count lines
    with open(file_path, 'r', encoding='utf-8') as f:
        line_count = sum(1 for _ in f)

    # Output results
    print(f"File: {file_path.name}")
    print(f"Lines: {line_count}")
    print(f"Total phrases analyzed: {total_phrases}")
    print(f"Redundancy: {redundancy_pct:.1f}%")

    if redundancy_pct > 10:
        print(f"\n⚠️  High redundancy detected ({redundancy_pct:.1f}% > 10%)")
        print("\nTop repeated phrases:")
        for phrase, count in top_repeated[:5]:
            print(f"  - '{phrase}' ({count} times)")
        sys.exit(1)
    else:
        print(f"✓ Redundancy optimal ({redundancy_pct:.1f}% ≤ 10%)")
        sys.exit(0)


if __name__ == '__main__':
    main()

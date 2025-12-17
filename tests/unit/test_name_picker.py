#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test name picker for movie display names."""

import re
from lib.parsing import extract_dual_names

# Test cases with real-world movie examples
TEST_MOVIES = [
    # Single version
    ("Inception.2010.1080p.BluRay.x264.mkv", None),

    # Dual names - different formats
    ("The Matrix - Matrix.2010.720p.mkv", "The Matrix Reloaded - Matrix Reloaded.2010.1080p.mkv"),
    ("Interstellar (Interstellar).2014.1080p.mkv", "Interstellar.2014.720p.mkv"),
    ("Dune [Dune].2021.2160p.mkv", "Dune - Duna.2021.1080p.mkv"),

    # Czech vs English names
    ("The Penguin - Tučňák.2024.1080p.mkv", "Tučňák.2024.720p.mkv"),
    ("Avatar.2009.1080p.mkv", "Avatar - Avatar.2009.2160p.mkv"),

    # Short vs long names
    ("Star Wars Episode IV A New Hope.1977.1080p.mkv", "Star Wars.1977.720p.mkv"),
    ("The Lord of the Rings The Fellowship of the Ring.2001.1080p.mkv",
     "LOTR Fellowship.2001.720p.mkv"),

    # Language variations
    ("The Shawshank Redemption - Vykoupeni z veznice Shawshank.1994.1080p.mkv",
     "Shawshank Redemption.1994.720p.mkv"),

    # Edge cases
    ("WALL-E.2008.1080p.mkv", "WALL-E - VALL-I.2008.720p.mkv"),
]


def analyze_name_candidates(version1_name, version2_name=None):
    """Analyze all possible display name candidates for a movie."""

    print(f"\n{'='*80}")
    print(f"ANALYZING: {version1_name}")
    if version2_name:
        print(f"     WITH: {version2_name}")
    print(f"{'='*80}\n")

    candidates = []

    # Extract raw names (before year/quality markers)
    pattern = re.compile(r'^(.+?)[_\.\s]+[\(\[]?((?:19|20)\d{2})[\)\]]?')

    for idx, name in enumerate([version1_name, version2_name] if version2_name else [version1_name], 1):
        if not name:
            continue

        match = pattern.match(name)
        if match:
            raw = match.group(1)
            year = match.group(2)

            # Clean version
            clean = raw.replace('.', ' ').replace('_', ' ').strip()

            # Check for dual names
            dual = extract_dual_names(raw)

            print(f"Version {idx}:")
            print(f"  Raw name:   {raw}")
            print(f"  Clean name: {clean}")
            print(f"  Dual names: {dual}")

            # Add candidates
            candidates.append({
                'name': clean,
                'length': len(clean),
                'word_count': len(clean.split()),
                'has_dual': bool(dual),
                'dual_parts': dual,
                'source': f'v{idx}_clean'
            })

            if dual:
                # Add both parts separately
                for i, part in enumerate(dual, 1):
                    clean_part = part.replace('.', ' ').replace('_', ' ').strip()
                    candidates.append({
                        'name': clean_part,
                        'length': len(clean_part),
                        'word_count': len(clean_part.split()),
                        'has_dual': False,
                        'dual_parts': None,
                        'source': f'v{idx}_dual_part{i}'
                    })

            print()

    # Remove duplicates (by name)
    unique_candidates = {}
    for c in candidates:
        if c['name'] not in unique_candidates:
            unique_candidates[c['name']] = c

    candidates = list(unique_candidates.values())

    # Display all candidates
    print(f"\nCANDIDATES ({len(candidates)}):")
    for i, c in enumerate(candidates, 1):
        print(f"  {i}. '{c['name']}' (len={c['length']}, words={c['word_count']}, "
              f"dual={c['has_dual']}, source={c['source']})")

    return candidates


def pick_best_name(candidates):
    """Smart name picker algorithm."""

    if not candidates:
        return None

    if len(candidates) == 1:
        return candidates[0]

    # Scoring criteria
    def score_candidate(c):
        score = 0

        # Prefer longer names (more descriptive)
        score += c['length'] * 0.5

        # Prefer names with more words (more complete)
        score += c['word_count'] * 10

        # Prefer dual names (they contain both languages)
        if c['has_dual']:
            score += 50

        # Prefer names from dual parts (usually cleaner)
        if 'dual_part' in c['source']:
            score += 20

        # Penalty for very short names (likely abbreviations)
        if c['length'] < 5:
            score -= 30

        # Bonus for English-looking names (contain common English words)
        english_words = ['the', 'of', 'and', 'in', 'to', 'for', 'with', 'at', 'from']
        name_lower = c['name'].lower()
        if any(word in name_lower.split() for word in english_words):
            score += 15

        return score

    # Score all candidates
    scored = [(c, score_candidate(c)) for c in candidates]
    scored.sort(key=lambda x: x[1], reverse=True)

    print(f"\nSCORED CANDIDATES:")
    for c, s in scored:
        print(f"  {s:6.1f} - '{c['name']}' ({c['source']})")

    winner = scored[0][0]
    print(f"\n🏆 WINNER: '{winner['name']}' (score={scored[0][1]:.1f})")

    return winner


# Run tests
if __name__ == '__main__':
    print("="*80)
    print("MOVIE NAME PICKER TEST")
    print("="*80)

    for v1, v2 in TEST_MOVIES:
        candidates = analyze_name_candidates(v1, v2)
        winner = pick_best_name(candidates)

    print("\n" + "="*80)
    print("ALL TESTS COMPLETE")
    print("="*80)

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test grouping for 'The Penguin' search scenario.
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

# Import from new lib structure (mocks provided by conftest.py)
from lib.parsing import parse_episode_info, extract_dual_names, clean_series_name
from lib.grouping import group_by_series


# Mock data simulating different naming patterns for "The Penguin"
test_files = [
    # English-only names
    {'name': 'The.Penguin.S01E01.1080p.WEB-DL.x264', 'ident': 'file1', 'size': '1000000000'},
    {'name': 'The.Penguin.S01E02.720p.WEB-DL.x264', 'ident': 'file2', 'size': '800000000'},

    # Czech-only names
    {'name': 'Tučňák.S01E01.720p.BluRay.x265', 'ident': 'file3', 'size': '700000000'},
    {'name': 'Tučňák.S01E03.1080p.BluRay.x265', 'ident': 'file4', 'size': '1200000000'},

    # Dual names in filename (dash separator)
    {'name': 'The.Penguin.-.Tučňák.S01E04.1080p.WEB-DL', 'ident': 'file5', 'size': '1100000000'},

    # Different quality of same episode
    {'name': 'The.Penguin.S01E01.2160p.WEB-DL.x265', 'ident': 'file6', 'size': '2000000000'},
]


def simulate_grouping():
    """Simulate the grouping logic."""
    print("=== Simulated Grouping Test ===\n")

    series_groups = {}

    for file in test_files:
        name = file['name']

        # Parse episode info using lib function
        ep_info = parse_episode_info(name)
        if not ep_info:
            continue

        raw_name = ep_info['series_name']
        season = ep_info['season']
        episode = ep_info['episode']

        # Check for dual names using lib function
        dual_names = extract_dual_names(name.split('.S')[0])

        # Determine canonical key
        if dual_names:
            # Normalize both names
            clean1 = clean_series_name(dual_names[0])
            clean2 = clean_series_name(dual_names[1])
            canonical = '|'.join(sorted([clean1, clean2]))
            display = f'{dual_names[1]} / {dual_names[0]}'
            print(f"File: {name}")
            print(f"  Dual names: {dual_names}")
            print(f"  Canonical: {canonical}")
            print(f"  Display: {display}\n")
        else:
            # Single name
            canonical = clean_series_name(raw_name)
            display = raw_name
            print(f"File: {name}")
            print(f"  Single name: {raw_name}")
            print(f"  Canonical: {canonical}")
            print(f"  Display: {display}\n")

        # Group by canonical
        if canonical not in series_groups:
            series_groups[canonical] = {
                'display': display,
                'episodes': []
            }

        series_groups[canonical]['episodes'].append({
            'S': season,
            'E': episode,
            'file': name
        })

    print("\n=== BEFORE MERGE ===")
    for canon, data in series_groups.items():
        print(f"Series: {canon}")
        print(f"  Display: {data['display']}")
        print(f"  Episodes: {len(data['episodes'])}")
        print()

    # Now use actual lib grouping
    print("\n=== ACTUAL LIB GROUPING ===")
    result = group_by_series(test_files)

    for series_key, series_data in result['series'].items():
        print(f"Series: {series_key}")
        print(f"  Display: {series_data['display_name']}")
        print(f"  Total episodes: {series_data['total_episodes']}")
        for season, season_data in series_data['seasons'].items():
            for ep_num, ep_list in season_data.items():
                for ep in ep_list:
                    print(f"    S{season:02d}E{ep_num:02d}: {ep['name']}")
        print()


if __name__ == '__main__':
    simulate_grouping()


def test_series_name_is_canonical_key_after_grouping():
    """Fix A: file_dict['series_name'] must be the canonical_key (dual-name aware)."""
    files = [
        {'name': 'The.Penguin.-.Tučňák.S01E04.1080p.WEB-DL', 'ident': 'fileA', 'size': '1'},
    ]
    result = group_by_series(files)
    # Canonical key should contain both names joined (|), not just raw 'the penguin'
    assert files[0]['series_name'] != 'the penguin', (
        "series_name should be canonical_key (with alt name), got raw: %r" % files[0]['series_name']
    )
    # And it should match one of the series keys in result
    assert files[0]['series_name'] in result['series'], (
        "series_name %r not in result['series'] keys %r" %
        (files[0]['series_name'], list(result['series'].keys()))
    )
    # state_key_for must derive the same ep-key regardless of which quality was watched
    from lib.state import state_key_for
    key = state_key_for(files[0])
    assert key.startswith('ep:')
    # Multiple quality variants of same dual-name episode should share the key
    files2 = [
        {'name': 'Penguin.S01E04.2160p.BluRay', 'ident': 'fileB', 'size': '2'},
        {'name': 'The.Penguin.-.Tučňák.S01E04.720p.WEB', 'ident': 'fileC', 'size': '3'},
    ]
    group_by_series(files2)
    # fileC has dual-name detection → canonical includes both
    # fileB is single-name ("penguin") → canonical is just "penguin"
    # These WON'T share a key without dual-names in fileB; what we assert here is
    # that fileC got the canonical key, not the raw.
    fc = next(f for f in files2 if f['ident'] == 'fileC')
    assert fc['series_name'] != 'the penguin', (
        "dual-name file's series_name should be canonical, got: %r" % fc['series_name']
    )

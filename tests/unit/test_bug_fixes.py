#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for bugs B1-B6 found during deep audit."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from lib.grouping import (
    _clean_movie_display_name, merge_orphan_movies, merge_crossyear_movies,
    merge_substring_movies, deduplicate_versions,
)


def _make_version(name='file.mkv', ident=None, size='1000000'):
    return {'name': name, 'ident': ident or name, 'size': size}


def _make_movie(display_name, year, num_versions=1):
    versions = [_make_version(f'{display_name}_{i}.mkv') for i in range(num_versions)]
    title = display_name.lower().replace(' ', ' ')
    key = f'{title}|{year}'
    return key, {
        'display_name': display_name,
        'year': year,
        'versions': versions,
        'canonical_key': key,
    }


# ==========================================================================
# B1: _clean_movie_display_name consecutive-only dedup
# ==========================================================================

class TestB1DisplayNameDedup:
    """Duplicate word removal must only remove CONSECUTIVE duplicates."""

    def test_consecutive_dup_blade(self):
        assert _clean_movie_display_name('Blade -Blade') == 'Blade'

    def test_consecutive_dup_matrix(self):
        assert _clean_movie_display_name('Matrix Matrix') == 'Matrix'

    def test_preserve_run_lola_run(self):
        assert _clean_movie_display_name('Run Lola Run') == 'Run Lola Run'

    def test_preserve_die_hard(self):
        assert _clean_movie_display_name('Die Hard 2 Die Harder') == 'Die Hard 2 Die Harder'

    def test_preserve_new_york_new_york(self):
        assert _clean_movie_display_name('New York New York') == 'New York New York'

    def test_consecutive_dup_sing_sing(self):
        # "Sing Sing" is consecutive identical — deduped (acceptable tradeoff
        # to fix "Blade -Blade" and "Matrix Matrix" artifacts)
        assert _clean_movie_display_name('Sing Sing') == 'Sing'

    def test_triple_consecutive(self):
        assert _clean_movie_display_name('Foo Foo Foo') == 'Foo'


# ==========================================================================
# B2: merge_orphan_movies — no bidirectional, require ≥2 words
# ==========================================================================

class TestB2OrphanMerge:
    """Orphan merge must not absorb unrelated single-word orphans."""

    def test_single_word_not_merged(self):
        """'Fast' (1v) must NOT merge into 'Fast and Furious' (2v)."""
        k1, m1 = _make_movie('Fast', 2023, num_versions=1)
        k2, m2 = _make_movie('Fast and Furious', 2023, num_versions=2)
        result = merge_orphan_movies({'movies': {k1: m1, k2: m2}})
        assert k1 in result['movies'], 'Fast should stay separate'
        assert k2 in result['movies']

    def test_multi_word_orphan_merged(self):
        """'Blade Runner [extra]' (1v) merges into 'Blade Runner' (3v)."""
        k_orphan = 'blade runner extra|2023'
        m_orphan = {
            'display_name': 'Blade Runner Extra',
            'year': 2023,
            'versions': [_make_version('br_extra.mkv')],
            'canonical_key': k_orphan,
        }
        k_group = 'blade runner|2023'
        m_group = {
            'display_name': 'Blade Runner',
            'year': 2023,
            'versions': [_make_version(f'br_{i}.mkv') for i in range(3)],
            'canonical_key': k_group,
        }
        # orphan words {blade, runner, extra} ⊃ group words {blade, runner}
        # But orphan must be SUBSET of group, not superset. So this won't merge
        # unless the orphan is 'blade runner' subset of a bigger group.
        # Let's reverse: orphan is subset of group
        k_orphan2 = 'blade runner|2023'
        m_orphan2 = {
            'display_name': 'Blade Runner',
            'year': 2023,
            'versions': [_make_version('br_lone.mkv')],
            'canonical_key': k_orphan2,
        }
        k_group2 = 'blade runner 2049|2023'
        m_group2 = {
            'display_name': 'Blade Runner 2049',
            'year': 2023,
            'versions': [_make_version(f'br2049_{i}.mkv') for i in range(3)],
            'canonical_key': k_group2,
        }
        result = merge_orphan_movies({'movies': {k_orphan2: m_orphan2, k_group2: m_group2}})
        # "blade runner" (2 words) subset of "blade runner 2049" → should merge
        assert k_orphan2 not in result['movies'], 'Multi-word orphan should merge'
        assert len(result['movies'][k_group2]['versions']) == 4

    def test_war_not_merged_into_star_wars(self):
        """'War' (1v) must NOT merge into 'Star Wars' (2v)."""
        k1, m1 = _make_movie('War', 2023, num_versions=1)
        k2 = 'star wars|2023'
        m2 = {
            'display_name': 'Star Wars',
            'year': 2023,
            'versions': [_make_version(f'sw_{i}.mkv') for i in range(2)],
            'canonical_key': k2,
        }
        result = merge_orphan_movies({'movies': {k1: m1, k2: m2}})
        assert k1 in result['movies'], 'War should stay separate'


# ==========================================================================
# B3: merge_crossyear_movies — both with 2+ versions stay separate
# ==========================================================================

class TestB3CrossYearGuard:
    """Cross-year merge guards against merging legitimate separate movies."""

    def test_both_significant_balanced_stay_separate(self):
        """Batman 2020 (5v) + Batman 2022 (4v) → 2 groups (balanced, both significant)."""
        k1 = 'batman|2020'
        m1 = {
            'display_name': 'Batman',
            'year': 2020,
            'versions': [_make_version(f'bat20_{i}.mkv') for i in range(5)],
            'canonical_key': k1,
        }
        k2 = 'batman|2022'
        m2 = {
            'display_name': 'Batman',
            'year': 2022,
            'versions': [_make_version(f'bat22_{i}.mkv') for i in range(4)],
            'canonical_key': k2,
        }
        result = merge_crossyear_movies({'movies': {k1: m1, k2: m2}})
        assert k1 in result['movies'], 'Batman 2020 should stay'
        assert k2 in result['movies'], 'Batman 2022 should stay'

    def test_single_version_merges_into_multi(self):
        """Blade 2 2000 (1v) + Blade 2 2002 (3v) → 1 group."""
        k1 = 'blade 2|2002'
        m1 = {
            'display_name': 'Blade 2',
            'year': 2002,
            'versions': [_make_version(f'b2_02_{i}.mkv') for i in range(3)],
            'canonical_key': k1,
        }
        k2 = 'blade 2|2000'
        m2 = {
            'display_name': 'Blade 2',
            'year': 2000,
            'versions': [_make_version('b2_00.mkv')],
            'canonical_key': k2,
        }
        result = merge_crossyear_movies({'movies': {k1: m1, k2: m2}})
        remaining = list(result['movies'].keys())
        assert len(remaining) == 1, f'Should merge into 1 group, got {remaining}'

    def test_lopsided_merges(self):
        """2v vs 30v → merge (lopsided = likely year error)."""
        k1 = 'blade 2|2002'
        m1 = {
            'display_name': 'Blade 2',
            'year': 2002,
            'versions': [_make_version(f'b2_02_{i}.mkv') for i in range(30)],
            'canonical_key': k1,
        }
        k2 = 'blade 2|2000'
        m2 = {
            'display_name': 'Blade 2',
            'year': 2000,
            'versions': [_make_version(f'b2_00_{i}.mkv') for i in range(2)],
            'canonical_key': k2,
        }
        result = merge_crossyear_movies({'movies': {k1: m1, k2: m2}})
        remaining = list(result['movies'].keys())
        assert len(remaining) == 1, f'Lopsided should merge, got {remaining}'


# ==========================================================================
# B4: merge_substring_movies — genre words no longer non_significant
# ==========================================================================

class TestB4GenreWords:
    """Genre words (horror, drama, etc.) must NOT be treated as non-significant."""

    def test_alien_vs_alien_horror_separate(self):
        """'Alien' + 'Alien Horror' same year → 2 groups."""
        k1, m1 = _make_movie('Alien', 2024, num_versions=1)
        k2 = 'alien horror|2024'
        m2 = {
            'display_name': 'Alien Horror',
            'year': 2024,
            'versions': [_make_version('ah.mkv')],
            'canonical_key': k2,
        }
        result = merge_substring_movies({'movies': {k1: m1, k2: m2}})
        assert k1 in result['movies'], 'Alien should stay'
        assert k2 in result['movies'], 'Alien Horror should stay'

    def test_avatar_cz_still_merges(self):
        """'Avatar' + 'Avatar CZ' same year → 1 group (cz still non-significant)."""
        k1, m1 = _make_movie('Avatar', 2009, num_versions=1)
        k2 = 'avatar cz|2009'
        m2 = {
            'display_name': 'Avatar CZ',
            'year': 2009,
            'versions': [_make_version('av_cz.mkv')],
            'canonical_key': k2,
        }
        result = merge_substring_movies({'movies': {k1: m1, k2: m2}})
        remaining = list(result['movies'].keys())
        assert len(remaining) == 1, f'Avatar CZ should merge into Avatar, got {remaining}'

    def test_comedy_not_stripped(self):
        """'Movie' + 'Movie Comedy' → 2 groups."""
        k1, m1 = _make_movie('Movie', 2024, num_versions=1)
        k2 = 'movie comedy|2024'
        m2 = {
            'display_name': 'Movie Comedy',
            'year': 2024,
            'versions': [_make_version('mc.mkv')],
            'canonical_key': k2,
        }
        result = merge_substring_movies({'movies': {k1: m1, k2: m2}})
        assert k1 in result['movies']
        assert k2 in result['movies']


# ==========================================================================
# B6: _PATTERN_EPISODE_MARKER cosmetic fix (verify it still works)
# ==========================================================================

class TestB6EpisodeMarker:
    """Episode marker pattern should still detect S##E## after \b removal."""

    def test_space_separated(self):
        import re
        from lib.grouping import _PATTERN_EPISODE_MARKER
        assert _PATTERN_EPISODE_MARKER.search('Movie S01E01 720p')

    def test_dot_separated(self):
        from lib.grouping import _PATTERN_EPISODE_MARKER
        assert _PATTERN_EPISODE_MARKER.search('Movie.S01E01.720p')

    def test_underscore_separated(self):
        from lib.grouping import _PATTERN_EPISODE_MARKER
        assert _PATTERN_EPISODE_MARKER.search('Movie_S01E01_720p')

    def test_start_of_string(self):
        from lib.grouping import _PATTERN_EPISODE_MARKER
        assert _PATTERN_EPISODE_MARKER.search('S01E01.Movie')

    def test_no_false_positive(self):
        from lib.grouping import _PATTERN_EPISODE_MARKER
        assert not _PATTERN_EPISODE_MARKER.search('Movie 2024 720p')

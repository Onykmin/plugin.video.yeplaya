#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression tests for the grouping/parsing audit fixes.

One test (or small group) per verified finding from the grouping bug-hunt.
Finding numbers (#N) refer to test-grouping/grouping-bug-hunt-findings.json.
"""

import time
import unittest

import tests.conftest  # noqa: F401 — installs Kodi mocks

from lib.parsing import (
    parse_episode_info, parse_movie_info, clean_series_name,
    extract_dual_names, extract_season_from_text,
)
from lib.grouping import (
    deduplicate_versions, _filter_irrelevant, _safe_size,
    _version_sort_key, pick_best_display_name_from_list,
    merge_word_order_series, group_by_series,
)


def _series(eps, base=1):
    return {'seasons': {1: {i: [{'ident': str(i)}] for i in range(base, base + eps)}},
            'total_episodes': eps, 'display_name': ''}


# ---------------------------------------------------------------------------
# Cluster A — crash hardening
# ---------------------------------------------------------------------------
class TestCrashHardening(unittest.TestCase):
    def test_safe_size_handles_garbage(self):  # #6, #25
        self.assertEqual(_safe_size({'size': 'N/A'}), 0)
        self.assertEqual(_safe_size({'size': ['100', '200']}), 100)
        self.assertEqual(_safe_size({'size': None}), 0)
        self.assertEqual(_safe_size({}), 0)
        self.assertEqual(_safe_size({'size': '  500 '}), 500)

    def test_version_sort_does_not_crash_on_bad_size(self):  # #6, #24, #25
        versions = [
            {'name': 'A 1080p.mkv', 'size': 'N/A'},
            {'name': 'B 720p.mkv', 'size': ['1', '2']},
            {'name': 'C.mkv', 'size': 5000},
        ]
        # Must not raise.
        ordered = sorted(versions, key=_version_sort_key, reverse=True)
        self.assertEqual(len(ordered), 3)

    def test_group_movies_tolerates_missing_name(self):  # #7
        files = [
            {'name': 'Inception (2010) 1080p.mkv', 'ident': 'm1', 'size': '5'},
            {'ident': 'x'},  # no 'name' key
        ]
        # Must not raise; movie still grouped.
        r = group_by_series(files, search_query='inception')
        self.assertIn('inception|2010', r['movies'])

    def test_missing_ident_does_not_duplicate_movie(self):  # #23
        files = [
            {'name': 'Inception (2010) 1080p.mkv', 'ident': 'm1', 'size': '5'},
            {'name': 'Inception (2010) 720p.mkv', 'ident': 'm2', 'size': '2'},
            {'name': 'inception extra clip'},  # survives filter, no ident
        ]
        r = group_by_series(files, search_query='inception')
        ns_names = [f.get('name') for f in r['non_series']]
        # The grouped movie files must NOT also appear in non_series.
        self.assertFalse(any(n and 'Inception (2010)' in n for n in ns_names))


# ---------------------------------------------------------------------------
# Cluster B — year handling
# ---------------------------------------------------------------------------
class TestYearHandling(unittest.TestCase):
    def test_bracketed_year_preferred_over_title_number(self):  # #4, #5
        m = parse_movie_info('Death Race 2000 (1975).mkv')
        self.assertIsNotNone(m)
        self.assertEqual(m['year'], 1975)

    def test_future_title_number_does_not_reject(self):  # #4, #13
        m = parse_movie_info('Blade Runner 2049 (2017).mkv')
        self.assertIsNotNone(m)
        self.assertEqual(m['year'], 2017)

    def test_normal_year_still_extracted(self):
        m = parse_movie_info('Inception (2010) 1080p.mkv')
        self.assertEqual(m['year'], 2010)
        m2 = parse_movie_info('Avatar 2009.mkv')
        self.assertEqual(m2['year'], 2009)


# ---------------------------------------------------------------------------
# movie-vs-series classification
# ---------------------------------------------------------------------------
class TestMovieVsSeries(unittest.TestCase):
    def test_bracketed_episode_marker_routes_to_series(self):  # #1
        # A bracketed S##E## with a year must still be detected as a series.
        files = [
            {'name': 'Westworld 2016 (S01E01).mkv', 'ident': 'a', 'size': '5'},
            {'name': 'Westworld 2016 (S01E02).mkv', 'ident': 'b', 'size': '5'},
        ]
        r = group_by_series(files, search_query='westworld')
        self.assertEqual(len(r['series']), 1)
        self.assertEqual(len(r['movies']), 0)

    def test_movie_sequel_no_year_not_an_episode(self):  # #2
        # These are movies, not "S01E02" of a series. With no year and no S##E##
        # marker, group_by_series should keep them out of series grouping.
        for name in ('Avatar 2.mkv', 'Frozen 2.mkv', 'Top Gun 2.mkv'):
            r = group_by_series([{'name': name, 'ident': 'i', 'size': '5'}],
                                search_query=name)
            self.assertEqual(len(r['series']), 0,
                             '{} should not be a series'.format(name))


# ---------------------------------------------------------------------------
# Cluster C — article / conjunction stripping
# ---------------------------------------------------------------------------
class TestArticleStripping(unittest.TestCase):
    def test_czech_conjunction_a_preserved(self):  # #14
        self.assertEqual(clean_series_name('Tom a Jerry'), 'tom a jerry')
        self.assertEqual(clean_series_name('Lilo a Stitch'), 'lilo a stitch')

    def test_leading_article_still_stripped_for_normal_titles(self):  # #15
        self.assertEqual(clean_series_name('The Office'), 'office')
        self.assertEqual(clean_series_name('The Boys'), 'boys')

    def test_short_title_not_eaten(self):  # #15
        self.assertEqual(clean_series_name('A-ha'), 'a ha')

    def test_trailing_the_stripped_a_kept(self):  # #31
        self.assertEqual(clean_series_name('Walking Dead The'), 'walking dead')
        self.assertEqual(clean_series_name('Quiet Place, A'), 'quiet place a')


# ---------------------------------------------------------------------------
# Cluster D — dual-name detection
# ---------------------------------------------------------------------------
class TestDualName(unittest.TestCase):
    def test_episode_title_not_treated_as_dual(self):  # #16
        self.assertIsNone(extract_dual_names('Sherlock - A Study in Pink'))
        self.assertIsNone(extract_dual_names('Sherlock - The Blind Banker'))

    def test_legit_alias_still_dual(self):  # #16 (no over-correction)
        self.assertEqual(extract_dual_names('The Penguin - Tucnak'),
                         ('The Penguin', 'Tucnak'))
        self.assertEqual(extract_dual_names('Suits - Kravataci'),
                         ('Suits', 'Kravataci'))

    def test_episode_titled_series_groups_into_one(self):  # #16 end-to-end
        names = ['Sherlock - A Study in Pink S01E01.mkv',
                 'Sherlock - The Blind Banker S01E02.mkv',
                 'Sherlock - The Great Game S01E03.mkv']
        keys = {parse_episode_info(n)['series_name'] for n in names}
        self.assertEqual(keys, {'sherlock'})

    def test_slash_branch_has_guards(self):  # #33
        self.assertIsNone(extract_dual_names('Inception / 1080p BluRay'))
        self.assertIsNone(extract_dual_names('Inception / 2010'))

    def test_norm_equality_strips_punctuation(self):  # #32
        self.assertIsNone(extract_dual_names('Spider-Man - SpiderMan'))


# ---------------------------------------------------------------------------
# Cluster E — display-name fidelity
# ---------------------------------------------------------------------------
class TestDisplayName(unittest.TestCase):
    def test_sequel_number_kept_in_display(self):  # #8
        self.assertEqual(
            pick_best_display_name_from_list(['Cobra Kai 3 S01E01', 'Cobra Kai 3 S01E02']),
            'Cobra Kai 3')

    def test_quality_noise_stripped_but_number_kept(self):  # #8, #26
        self.assertEqual(
            pick_best_display_name_from_list(['Rocky 4 1080p BluRay.mkv']), 'Rocky 4')

    def test_number_title_kept(self):  # #3 display fidelity
        self.assertEqual(
            pick_best_display_name_from_list(['The 4400 S01E01.mkv']), 'The 4400')

    def test_pure_quality_does_not_return_raw_filename(self):  # #29
        out = pick_best_display_name_from_list(['Show.S01E01.HD.4K.mkv'])
        self.assertNotIn('.mkv', out)


# ---------------------------------------------------------------------------
# Cluster H — merge determinism + guard
# ---------------------------------------------------------------------------
class TestMergeDeterminism(unittest.TestCase):
    def test_word_order_target_is_deterministic(self):  # #20
        g1 = {'series': {'south park': _series(2), 'park south': _series(1, 10)}}
        merge_word_order_series(g1)
        g2 = {'series': {'park south': _series(1, 10), 'south park': _series(2)}}
        merge_word_order_series(g2)
        self.assertEqual(list(g1['series']), list(g2['series']))
        self.assertEqual(list(g1['series']), ['south park'])


# ---------------------------------------------------------------------------
# Cluster I — regex backtracking
# ---------------------------------------------------------------------------
class TestRegexBacktracking(unittest.TestCase):
    def test_pathological_separator_run_is_fast(self):  # #19
        bad = 'Movie Title' + ' - . ' * 1400 + 'end'
        t = time.time()
        parse_episode_info(bad)
        parse_movie_info(bad)
        self.assertLess(time.time() - t, 0.5)  # was multiple seconds


# ---------------------------------------------------------------------------
# Cluster J — dedup + filter + season-dash
# ---------------------------------------------------------------------------
class TestDedupAndFilter(unittest.TestCase):
    def test_distinct_idents_kept(self):  # #9
        v = [{'ident': 'a', 'name': 'f.mkv', 'size': 1},
             {'ident': 'b', 'name': 'f.mkv', 'size': 1}]
        self.assertEqual(len(deduplicate_versions(v)), 2)

    def test_dedup_tolerates_list_size(self):  # #24
        v = [{'name': 'f.mkv', 'size': ['1', '2']},
             {'name': 'f.mkv', 'size': ['1', '2']}]
        self.assertEqual(len(deduplicate_versions(v)), 1)  # no crash, deduped

    def test_filter_no_substring_false_keep(self):  # #17
        kept = [f['name'] for f in _filter_irrelevant(
            [{'name': 'Mother S01E01.mkv'}, {'name': 'Her S01E01.mkv'}], 'her')]
        self.assertEqual(kept, ['Her S01E01.mkv'])

    def test_filter_acronym_no_false_drop(self):  # #17
        kept = [f['name'] for f in _filter_irrelevant(
            [{'name': 'C.S.I. New York S01E01.mkv'},
             {'name': 'CSI Vegas S01E01.mkv'}], 'csi')]
        self.assertEqual(len(kept), 2)

    def test_season_dash_restore_position(self):  # #34
        _, cleaned = extract_season_from_text('The Office Season 2 - 05.mkv')
        self.assertEqual(cleaned, 'The Office - 05.mkv')
        _, cleaned2 = extract_season_from_text('Babylon 5 Season 2 - 10.mkv')
        self.assertEqual(cleaned2, 'Babylon 5 - 10.mkv')


if __name__ == '__main__':
    unittest.main()

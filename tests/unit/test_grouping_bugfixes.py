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
    merge_word_order_series, merge_substring_series, group_by_series,
    merge_crossyear_movies,
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

    def test_safe_size_parses_decimal_byte_string(self):
        # A decimal-form byte string must rank by its numeric value, not
        # collapse to 0 (which desynced the modal sort from the size label).
        self.assertEqual(_safe_size({'size': '1685758999.0'}), 1685758999)
        self.assertEqual(_safe_size({'size': '4262463897'}), 4262463897)
        # And it must still order correctly relative to a plain int string.
        self.assertGreater(_safe_size({'size': '4262463897'}),
                           _safe_size({'size': '1685758999.0'}))

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

    def test_identless_movie_file_not_duplicated_in_non_series(self):
        # A movie-pattern file that itself has NO ident must not remain in
        # non_series after being grouped into movies (excluded by object id).
        files = [
            {'name': 'Inception (2010) 1080p.mkv', 'size': '5'},  # movie, no ident
        ]
        r = group_by_series(files, search_query='inception')
        self.assertIn('inception|2010', r['movies'])
        ns_names = [f.get('name') for f in r['non_series']]
        self.assertNotIn('Inception (2010) 1080p.mkv', ns_names)


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


# ===========================================================================
# Round 2 — second-pass audit fixes
# ===========================================================================
class TestRound2YearHandling(unittest.TestCase):
    def test_resolution_not_parsed_as_year(self):  # r2 #2/#3/#7
        # "1920x1080" width must not be read as the release year.
        m = parse_movie_info('The Heist 1920x1080 x264.mkv')
        # No real year present -> not classified as a movie (year is required).
        self.assertIsNone(m)

    def test_resolution_alongside_real_year(self):  # r2 #7
        m = parse_movie_info('Tenet (2020 1920x1080p) cz.mkv')
        self.assertIsNotNone(m)
        self.assertEqual(m['year'], 2020)

    def test_leading_parenthesized_year_kept(self):  # r2 #5
        # "(2010) Title" — the leading (year) is the release year, not a tag.
        m = parse_movie_info('(2010) The Movie.mkv')
        self.assertIsNotNone(m)
        self.assertEqual(m['year'], 2010)
        self.assertNotIn('mkv', m['title'])  # extension must be stripped
        m2 = parse_movie_info('(1999) Fight Club 1080p BluRay.mkv')
        self.assertEqual(m2['year'], 1999)
        self.assertEqual(m2['title'], 'fight club')

    def test_leading_year_keeps_dotted_sequel_suffix(self):  # r2 audit self-fix
        # The after-year extension strip must remove only KNOWN extensions, not
        # a dotted sequel suffix ("Rocky.IV" must not lose "IV").
        m = parse_movie_info('(2010) Rocky.IV')
        self.assertEqual(m['year'], 2010)
        self.assertEqual(m['title'], 'rocky 4')  # roman numeral normalized
        m2 = parse_movie_info('(2010) Rocky.IV.mkv')  # real ext still stripped
        self.assertEqual(m2['title'], 'rocky 4')


class TestRound2DualNameGuards(unittest.TestCase):
    def test_dash_no_space_branch_rejects_metadata(self):  # r2 #5/#20
        # Dash-without-spaces branch now applies the shared false-positive guard.
        self.assertIsNone(extract_dual_names('Inception-1080p'))
        self.assertIsNone(extract_dual_names('Movie-2010'))

    def test_multi_space_branch_rejects_metadata(self):  # r2 #5/#20
        self.assertIsNone(extract_dual_names('Inception  1080p BluRay'))
        self.assertIsNone(extract_dual_names('Movie  S01E01'))

    def test_legit_dual_still_detected_after_refactor(self):  # r2 no over-correction
        self.assertEqual(extract_dual_names('The Penguin - Tucnak'),
                         ('The Penguin', 'Tucnak'))


class TestRound2Filter(unittest.TestCase):
    def test_short_query_prefix_match_kept(self):  # r2 #6
        # 3-char query as a word-prefix is kept; the substring false-keep
        # ("man" inside "Batman") is still avoided (prefix is word-anchored).
        kept = [f['name'] for f in _filter_irrelevant(
            [{'name': 'Manifest S01E01.mkv'}, {'name': 'Batman Begins.mkv'}], 'man')]
        self.assertEqual(kept, ['Manifest S01E01.mkv'])


class TestRound2MergeDeterminism(unittest.TestCase):
    def test_spinoff_guard_order_independent(self):  # r2 #4/#11
        # The spinoff guard must read PRE-merge episode counts so the outcome
        # does not depend on dict/merge iteration order.
        def build():
            return {'series': {
                'dragon ball': _series(5),
                'dragon ball z': _series(5, 10),
                'dragon ball super': _series(5, 20),
            }}
        g1 = build()
        merge_substring_series(g1)
        g2 = build()
        # Reverse insertion order.
        g2['series'] = dict(reversed(list(g2['series'].items())))
        merge_substring_series(g2)
        self.assertEqual(set(g1['series']), set(g2['series']))


class TestRound2MovieMergeFinalize(unittest.TestCase):
    def test_crossyear_multi_source_dedup_and_sort(self):  # r2 #9/#27
        # A target absorbing multiple sources must end up deduped and
        # quality-sorted exactly as before (deferred finalize is equivalent).
        def v(name, ident, size):
            return {'name': name, 'ident': ident, 'size': size}
        result = {'movies': {
            'blade|2000': {'year': 2000, 'versions': [
                v('Blade 480p.mkv', 'a', '100')]},
            'blade|2001': {'year': 2001, 'versions': [
                v('Blade 1080p.mkv', 'b', '900'),
                v('Blade 480p.mkv', 'a', '100')]},  # dup ident of 'a'
            'blade|2002': {'year': 2002, 'versions': [
                v('Blade 720p.mkv', 'c', '500')]},
        }}
        merge_crossyear_movies(result)
        # All merged into one key.
        self.assertEqual(len(result['movies']), 1)
        versions = next(iter(result['movies'].values()))['versions']
        idents = [x['ident'] for x in versions]
        self.assertEqual(len(idents), len(set(idents)))  # deduped
        # Quality-sorted DESC: 1080p > 720p > 480p.
        quals = [x['quality_meta']['quality'] for x in versions]
        self.assertEqual(quals, ['1080p', '720p', '480p'])


if __name__ == '__main__':
    unittest.main()

# -*- coding: utf-8 -*-
"""Edge cases of the grouping/parsing pipeline that the table tests do not reach:
garbage API fields, leading-year titles, metadata that looks like a second title,
short-query relevance filtering and multi-source movie merges.
"""
import pytest

from lib.grouping import group_by_series, group_movies
from lib.parsing import extract_dual_names, parse_movie_info


def files(*specs):
    return [{'name': n, 'ident': i, 'size': z} for n, i, z in specs]


def test_garbage_sizes_do_not_break_version_order():
    r = group_by_series([
        {'name': 'Show.S01E01.1080p.mkv', 'ident': 'a', 'size': 'N/A'},
        {'name': 'Show.S01E01.720p.mkv', 'ident': 'b', 'size': ['1', '2']},
        {'name': 'Show.S01E01.mkv', 'ident': 'c', 'size': 5000},
        {'name': 'Show.S01E01.480p.mkv', 'ident': 'd', 'size': '1685758999.0'},
    ])
    assert [v['ident'] for v in r['series']['show']['seasons'][1][1]][:2] == ['a', 'b']  # by quality
    assert len(r['series']['show']['seasons'][1][1]) == 4


def test_decimal_byte_size_ranks_by_value_among_equal_quality():
    r = group_by_series(files(('Show.S01E01.1080p.A.mkv', 'a', '1685758999.0'),
                              ('Show.S01E01.1080p.B.mkv', 'b', '4262463897')))
    assert [v['ident'] for v in r['series']['show']['seasons'][1][1]] == ['b', 'a']


def test_movie_without_ident_is_grouped_once_and_not_left_in_non_series():
    r = group_by_series([{'name': 'Inception (2010) 1080p.mkv', 'size': '5'},
                         {'name': 'inception extra clip'}], search_query='inception')
    assert list(r['movies']) == ['inception|2010']
    assert [f['name'] for f in r['non_series']] == ['inception extra clip']


@pytest.mark.parametrize('name, title, year', [
    ('(2010) The Movie.mkv', 'movie', 2010),
    ('(1999) Fight Club 1080p BluRay.mkv', 'fight club', 1999),
    ('(2010) Rocky.IV', 'rocky 4', 2010),           # dotted sequel suffix is not an extension
    ('(2010) Rocky.IV.mkv', 'rocky 4', 2010),
    ('Tenet (2020 1920x1080p) cz.mkv', 'tenet', 2020),
])
def test_leading_or_bracketed_year(name, title, year):
    info = parse_movie_info(name)
    assert (info['title'], info['year']) == (title, year)


def test_resolution_width_alone_is_not_a_release_year():
    assert parse_movie_info('The Heist 1920x1080 x264.mkv') is None


@pytest.mark.parametrize('raw', ['Inception-1080p', 'Movie-2010', 'Inception  1080p BluRay', 'Movie  S01E01'])
def test_metadata_is_never_a_second_title(raw):
    assert extract_dual_names(raw) is None


@pytest.mark.parametrize('names, query, kept', [
    (['Mother S01E01.mkv', 'Her S01E01.mkv'], 'her', ['her']),
    (['Manifest S01E01.mkv', 'Batman.Begins.S01E01.mkv'], 'man', ['manifest']),  # word-anchored prefix
    (['C.S.I. New York S01E01.mkv', 'CSI Vegas S01E01.mkv'], 'csi', ['c s i new york', 'csi vegas']),
    (['Přátelé S01E01.mkv', 'Seinfeld S01E01.mkv'], 'pratele', ['pratele']),
    (['Friends S01E01.mkv', 'Seinfeld S01E01.mkv'], 'nomatchatall', ['friends', 'seinfeld']),  # nothing matches: keep all
])
def test_search_query_drops_only_unrelated_files(names, query, kept):
    r = group_by_series(files(*[(n, 'i%d' % i, '1') for i, n in enumerate(names)]), search_query=query)
    assert sorted(r['series']) == sorted(kept)


def test_movie_year_typos_across_three_years_merge_into_one_sorted_deduped_group():
    names = [('Blade.2000.480p.mkv', 'a', '100'),
             ('Blade.2001.1080p.mkv', 'b', '900'), ('Blade.2001.480p.mkv', 'a', '100'),  # mirror of 'a'
             ('Blade.2002.720p.mkv', 'c', '500')]
    (movie,) = group_movies(files(*names))['movies'].values()
    assert [v['ident'] for v in movie['versions']] == ['b', 'c', 'a']


@pytest.mark.parametrize('reverse', [False, True])
def test_spinoff_series_stay_apart_whatever_the_input_order(reverse):
    names = (['Dragon.Ball.S01E%02d.mkv' % e for e in range(1, 6)]
             + ['Dragon.Ball.Z.S01E%02d.mkv' % e for e in range(10, 15)]
             + ['Dragon.Ball.Super.S01E%02d.mkv' % e for e in range(20, 25)])
    if reverse:
        names.reverse()
    r = group_by_series(files(*[(n, 'i%d' % i, str(1000 + i)) for i, n in enumerate(names)]))
    assert sorted(r['series']) == ['dragon ball', 'dragon ball super', 'dragon ball z']


def test_playback_state_key_of_a_grouped_episode_names_its_series_bucket():
    from lib.state import state_key_for
    f = {'name': 'The.Penguin.-.Tučňák.S01E04.1080p.WEB-DL', 'ident': 'fileA', 'size': '1'}
    r = group_by_series([f])
    assert f['series_name'] in r['series']
    assert state_key_for(f).startswith('ep:')

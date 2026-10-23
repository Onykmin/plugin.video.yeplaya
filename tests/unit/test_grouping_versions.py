# -*- coding: utf-8 -*-
"""deduplicate_versions (used by the series_ui version picker) and the quality
ranking that decides which version of an episode/movie is offered first.
Kodi mocks come from tests/conftest.py.
"""
import pytest

from lib.grouping import _version_sort_key, deduplicate_versions
from lib.parsing import parse_quality_metadata


def idents(versions):
    return [v.get('ident') for v in versions]


DEDUP = [
    pytest.param([], [], id='empty'),
    pytest.param([{'ident': 'a', 'name': 'f1.mkv', 'size': 1}, {'ident': 'a', 'name': 'f2.mkv', 'size': 2}],
                 ['a'], id='same-ident-first-wins'),
    pytest.param([{'ident': 'a', 'name': 'f.mkv', 'size': 1}, {'ident': 'b', 'name': 'f.mkv', 'size': 1}],
                 ['a', 'b'], id='mirrors-with-distinct-idents-are-kept'),
    pytest.param([{'name': 'f.mkv', 'size': 1}, {'name': 'f.mkv', 'size': 1},
                  {'ident': 'unknown', 'name': 'f.mkv', 'size': 1},
                  {'ident': None, 'name': 'f.mkv', 'size': 1}],
                 [None], id='no-usable-ident-falls-back-to-name-and-size'),
    pytest.param([{'ident': 'unknown', 'name': 'f.mkv', 'size': 1}, {'ident': 'unknown', 'name': 'f.mkv', 'size': 2}],
                 ['unknown', 'unknown'], id='fallback-different-size-kept'),
    pytest.param([{'name': 'f.mkv', 'size': ['1', '2']}, {'name': 'f.mkv', 'size': ['1', '2']}],
                 [None], id='list-size-does-not-crash'),
    pytest.param([{'ident': 'a', 'name': None, 'size': 1}, {'ident': 'b', 'name': None, 'size': 1}],
                 ['a', 'b'], id='nameless-with-idents-kept'),
    pytest.param([{'ident': 'a', 'name': 'a.mkv', 'size': 1}, {'ident': 'b', 'name': 'b.mkv', 'size': 2},
                  {'ident': 'a', 'name': 'a.mkv', 'size': 1}, {'ident': 'c', 'name': 'c.mkv', 'size': 3}],
                 ['a', 'b', 'c'], id='order-preserved'),
]


@pytest.mark.parametrize('versions,expected', DEDUP)
def test_deduplicate_versions(versions, expected):
    assert idents(deduplicate_versions(versions)) == expected


def test_deduplicate_versions_does_not_mutate_input():
    versions = [{'ident': 'a'}, {'ident': 'a'}]
    deduplicate_versions(versions)
    assert len(versions) == 2


@pytest.mark.parametrize('name,expected', [
    ('South.Park.S01E01.1080p.BluRay.x265.DTS.mkv',
     {'quality': '1080p', 'source': 'BluRay', 'codec': 'x265', 'audio': 'DTS', 'quality_score': 105}),
    ('Show.S02E03.720p.WEB-DL.x264.AC3.mp4',
     {'quality': '720p', 'source': 'WEB-DL', 'codec': 'x264', 'audio': 'AC3', 'quality_score': 72}),
    ('Movie.2160p.HDTV.HEVC.AAC.mkv',
     {'quality': '2160p', 'source': 'HDTV', 'codec': 'x265', 'audio': 'AAC', 'quality_score': 111}),
    ('Episode.S01E01.mkv',
     {'quality': None, 'source': None, 'codec': None, 'audio': None, 'quality_score': 50}),
    ('show.Blu-Ray.H.265.mkv', {'source': 'BluRay', 'codec': 'x265'}),
    ('show.BLURAY.H265.mkv', {'source': 'BluRay', 'codec': 'x265'}),
    ('show.WEBDL.HEVC.mkv', {'source': 'WEB-DL', 'codec': 'x265'}),
])
def test_quality_metadata_from_filename(name, expected):
    meta = parse_quality_metadata(name)
    assert {k: meta[k] for k in expected} == expected


def test_quality_score_ranks_resolution_then_source_then_codec():
    score = lambda n: parse_quality_metadata(n)['quality_score']  # noqa: E731
    assert (score('s.1080p.BluRay.x265.mkv') > score('s.1080p.WEB-DL.x264.mkv')
            > score('s.720p.BluRay.x265.mkv') > score('s.mkv'))



def test_version_order_is_independent_of_input_order():
    # same name+size, distinct idents (mirrors): the tie must not follow input order
    vs = [{'ident': i, 'name': 'Movie.1080p.mkv', 'size': 5} for i in ('a', 'b', 'c')]
    forward = idents(sorted(vs, key=_version_sort_key, reverse=True))
    backward = idents(sorted(reversed(vs), key=_version_sort_key, reverse=True))
    assert forward == backward and sorted(forward) == ['a', 'b', 'c']


def test_version_sort_prefers_quality_then_size_over_ident():
    vs = [{'ident': 'z', 'name': 'M.720p.mkv', 'size': 9},
          {'ident': 'a', 'name': 'M.1920x1080.mkv', 'size': 1},
          {'ident': 'b', 'name': 'M.1920x1080.mkv', 'size': 2}]
    assert idents(sorted(vs, key=_version_sort_key, reverse=True)) == ['b', 'a', 'z']

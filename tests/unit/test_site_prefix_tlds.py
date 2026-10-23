# -*- coding: utf-8 -*-
"""Release-site prefixes whose TLD is an English word ("7HitMovies.best - Dune ...").

The site is dropped so the file groups under its real title; the TLDs are also words, so a
dotted title ("The.Dead.Zone - S01E01", "Danger.Zone - 05") must keep its name. Keys the files
had before the prefix was recognised stay readable: the old per-file key is a group alias and
playback state / favorites resolve through it (read-only, nothing rewritten). A key that is only
the site ("7hitmovies best") names every title the site posted, so it is never an alias.
"""
import pytest

import tests.conftest  # noqa: F401 -- installs Kodi mocks before lib imports
from lib.grouping import _site_legacy_series_keys
from lib.parsing import parse_episode_info, parse_movie_info, strip_site_prefix
from tests.unit.test_grouping_series import group, layout
from tests.unit.test_state import _StateHarness

NEW_TLDS = ['dad', 'forum', 'buzz', 'diy', 'best', 'moe', 'zone']
# S10: another word TLD pair and the two-label suffix "com.de"
S10_TLDS = ['watch', 'green', 'com.de']

# Dotted titles that end in a new TLD word: the title must survive.
WORD_TLD_TITLES = [
    ('The.Twilight.Zone - 1x01.mkv', 'twilight zone'),
    ('The.Dead.Zone - S01E01.mkv', 'dead zone'),
    ('Danger.Zone - 05.mkv', 'danger zone'),
    ('Simply.The.Best - 05.mkv', 'simply best'),
    ('Mom.And.Dad - S01E02.mkv', 'mom and dad'),
    ('Nothing.But.Buzz - S01E03.mkv', 'nothing but buzz'),
    ('the.twilight.zone - 1x01.mkv', 'twilight zone'),   # scene-lower-case spelling
    ('the.dead.zone - s01e01.mkv', 'dead zone'),
    ('danger.zone - 05.mkv', 'danger zone'),
    ('simply.the.best - 05.mkv', 'simply best'),
    ('Danger.zone - 05.mkv', 'danger zone'),
    ('Danger.Zone - S01E04.mkv', 'danger zone'),
    # S10: "watch"/"green" are words too, "com.de" is a two-label suffix
    ('The.Watch - S01E01.mkv', 'watch'),
    ('the.watch - s01e01.mkv', 'watch'),
    ('City.Watch - S01E02.mkv', 'city watch'),
    ('Big.Green - S01E03.mkv', 'big green'),
    ('Big.Green - 05.mkv', 'big green'),
    ('Fight.Club.Green - 05.mkv', 'fight club green'),
    ('Mein.Haus.com.de - S01E01.mkv', 'mein haus com'),
    ('Das.Boot.De - S01E01.mkv', 'das boot'),
    ('Show.Com.De - S01E01.mkv', 'show com'),
    ('show.com.de - S01E01.mkv', 'show com'),
    ('Dot.Show.7HitMovies.com.de - S01E01.mkv', 'dot show 7hitmovies com'),
]


@pytest.fixture
def harness():
    h = _StateHarness()
    yield h
    h.cleanup()


@pytest.mark.parametrize('tld', NEW_TLDS + S10_TLDS)
def test_prefix_is_dropped_for_series_files(tld):
    r = group(['True.Detective.S04E01.mkv', 'True.Detective.S04E02.mkv',
               '7HitMovies.%s - True.Detective.S04E05.720p.[Hin-Eng].WEB-DL.mkv' % tld])
    assert list(r['series']) == ['true detective']
    assert layout(r['series']['true detective']) == {4: [1, 2, 5]}


@pytest.mark.parametrize('tld', NEW_TLDS + S10_TLDS)
def test_prefix_is_dropped_for_movie_files(tld):
    r = group(['7HitMovies.%s - Dune Part Two (2024) Hindi   Eng 720P BluRay.mkv' % tld,
               'Dune Part Two 2024 1080p.mkv'])
    assert list(r['movies']) == ['dune part two|2024']
    assert len(r['movies']['dune part two|2024']['versions']) == 2
    assert r['series'] == {}


@pytest.mark.parametrize('tld', NEW_TLDS + S10_TLDS)
def test_prefix_with_year_and_season_only_still_names_the_title(tld):
    r = group(['7HitMovies.%s - Squid Game - S01E01.mkv' % tld, 'Squid.Game.S01E02.mkv'])
    assert list(r['series']) == ['squid game']
    assert layout(r['series']['squid game']) == {1: [1, 2]}


@pytest.mark.parametrize('name,key', WORD_TLD_TITLES)
def test_dotted_title_ending_in_a_word_tld_keeps_its_title(name, key):
    assert strip_site_prefix(name) == name
    r = group([name])
    assert key in r['series'] and len(r['series']) == 1
    assert r['non_series'] == [] and r['movies'] == {}


@pytest.mark.parametrize('name,key', [
    ('Green.Lantern - 2011.mkv', 'green lantern|2011'),
    ('Green.Book - 2018.mkv', 'green book|2018'),
    ('The.Green.Mile - 1999.mkv', 'green mile|1999'),
    ('The.Watch - 2012.mkv', 'watch|2012'),
])
def test_dotted_movie_title_ending_in_a_s10_word_keeps_its_title(name, key):
    assert strip_site_prefix(name) == name
    assert list(group([name])['movies']) == [key]


def test_s10_prefixes_are_dropped_from_the_corpus_spellings():
    for name in ('7HitMovies.watch - Interstellar (2014) 1080p.mkv',
                 '7HitMovies.green - Fight Club (1999) 1080p.mkv',
                 '7HitMovies.com.de - Dune (2021) 1080p.mkv'):
        assert strip_site_prefix(name).split(' ')[0] in ('Interstellar', 'Fight', 'Dune')
        assert strip_site_prefix(name, legacy=True) == name
    assert parse_movie_info('7HitMovies.green - Fight Club (1999) 1080p.mkv')['title'] == 'fight club'
    assert parse_movie_info('7HitMovies.com.de - Dune (2021) 1080p.mkv')['title'] == 'dune'


def test_word_tld_titles_parse_with_their_whole_name():
    assert parse_episode_info('The.Dead.Zone - S01E01.mkv')['series_name'] == 'dead zone'
    assert parse_episode_info('Danger.Zone - 05.mkv')['series_name'] == 'danger zone'
    assert parse_movie_info('Danger.Zone.1986.1080p.mkv')['title'] == 'danger zone'
    assert parse_movie_info('Simply.The.Best - 1992.mkv') is not None


# Titles ending in an old-list TLD that is an English word ("club", "me", "top", "live", ...):
# parse result and title must survive, as at the pre-prefix parser.
OLD_LIST_WORD_TLD_TITLES = [
    ('Fight.Club - 1999 1080p.mkv', 'movie', 'fight club'),
    ('Marry.Me - 2022 CZ.mkv', 'movie', 'marry me'),
    ('The.Pet.Club - S01E02.mkv', 'series', 'pet club'),
    ('Rock.Top - 2010.mkv', 'movie', 'rock top'),
    ('Lip.Sync.Live - S01E03.mkv', 'series', 'lip sync live'),
    ('Face.To - 2005.mkv', 'movie', 'face to'),
    ('The.Net - 1995 1080p.mkv', 'movie', 'net'),
    ('Mission.Info - S01E01.mkv', 'series', 'mission info'),
    ('Reality.TV - 1999.mkv', 'movie', 'reality tv'),
]


@pytest.mark.parametrize('name,kind,title', OLD_LIST_WORD_TLD_TITLES)
def test_dotted_title_ending_in_an_old_list_word_tld_keeps_its_title(name, kind, title):
    assert strip_site_prefix(name) == name
    if kind == 'movie':
        info = parse_movie_info(name)
        assert info is not None and info['title'] == title
    else:
        info = parse_episode_info(name)
        assert info is not None and info['series_name'] == title


def test_old_list_word_tld_site_prefixes_are_still_dropped():
    for tld in ('cool', 'club', 'site', 'top', 'live', 'me', 'to', 'net', 'info', 'biz', 'tv', 'vip'):
        assert strip_site_prefix('7HitMovies.%s - Show.S01E01.mkv' % tld) == 'Show.S01E01.mkv'


def test_site_prefix_is_not_a_title_even_when_a_word_tld_title_is_beside_it():
    r = group(['The.Dead.Zone - S01E01.mkv', 'The.Dead.Zone - S01E02.mkv',
               '7HitMovies.zone - The.Dead.Zone.S01E03.mkv'])
    assert list(r['series']) == ['dead zone']
    assert layout(r['series']['dead zone']) == {1: [1, 2, 3]}


def test_old_tlds_keep_their_pattern():
    assert strip_site_prefix('7HitMovies.cool - Show.S01E01.mkv') == 'Show.S01E01.mkv'
    assert strip_site_prefix('www.site.org - Show.S01E01.mkv') == 'Show.S01E01.mkv'
    # the legacy switch is the old behaviour: the new TLDs were not sites
    assert strip_site_prefix('7HitMovies.best - X.mkv', legacy=True) == '7HitMovies.best - X.mkv'
    assert strip_site_prefix('7HitMovies.cool - X.mkv', legacy=True) == 'X.mkv'


# --------------------------------------------------------------------------
# Migration: keys these files had before the prefix was recognised
# --------------------------------------------------------------------------
MOVIE_SINGLE = '7HitMovies.diy - Dune Part Two (2024) Hindi   Eng 480P BluRay.mkv'
MOVIE_DUAL = '7HitMovies.best - Dune (2021) ORG Hindi 720p BluRay.mkv'
SERIES_DUAL = '7HitMovies.dad - True.Detective.S04E05.720p.mkv'


def _movie_group(name):
    r = group([name])
    (key, data), = r['movies'].items()
    return key, data


def test_movie_group_remembers_the_key_the_old_parser_gave_it():
    key, data = _movie_group(MOVIE_SINGLE)
    assert key == 'dune part two|2024'
    assert data['aliases'] == ['7hitmovies diy dune part two|2024']
    key, data = _movie_group(MOVIE_DUAL)
    assert key == 'dune|2021'
    assert '7hitmovies best|dune|2021' in data['aliases']


def test_series_group_remembers_the_title_bearing_old_key():
    r = group([SERIES_DUAL])
    assert list(r['series']) == ['true detective']
    assert '7hitmovies dad|true detective' in r['series']['true detective']['aliases']


def test_site_only_key_is_never_an_alias():
    # "7hitmovies dad" is what ANY wordy-title file of that site was keyed as: aliasing it would let a
    # row or favorite of one show resolve for another. Non-derivable, so it stays orphaned.
    name = '7HitMovies.dad - True.Detective - Night Country - S04E06.720p.mkv'
    assert parse_episode_info(name, legacy_site=True)['series_name'] == '7hitmovies dad'
    assert _site_legacy_series_keys(name) == []
    r = group([name, '7HitMovies.dad - House.of.the.Dragon.A.Long.Title.S01E01.mkv'])
    for data in r['series'].values():
        assert '7hitmovies dad' not in data.get('aliases', [])


# the old parser read "com.de" as host "7HitMovies.com" plus the language tag "de", which it drops
S10_OLD_SITE = {'watch': '7hitmovies watch', 'green': '7hitmovies green', 'com.de': '7hitmovies com'}


@pytest.mark.parametrize('tld', S10_TLDS)
def test_s10_movie_remembers_the_old_key_and_its_row_resolves(tld, harness):
    key, data = _movie_group('7HitMovies.%s - Dune Part Two (2024) 1080p.mkv' % tld)
    old = '%s dune part two|2024' % S10_OLD_SITE[tld]
    assert key == 'dune part two|2024'
    assert data['aliases'] == [old]
    file_dict = dict(data['versions'][0], canonical_key=key)
    harness.state.mark_watched('mv:' + old)
    assert harness.state.resolve_state_key(file_dict, data['aliases']) == 'mv:' + old
    assert harness.state.get_state('mv:dune part two|2024') is None


@pytest.mark.parametrize('tld', S10_TLDS)
def test_s10_dual_movie_key_is_an_alias(tld):
    key, data = _movie_group('7HitMovies.%s - Fight Club (1999) 1080p.mkv' % tld)
    assert key == 'fight club|1999'
    assert '%s|fight club|1999' % S10_OLD_SITE[tld] in data['aliases']


def test_s10_com_de_keeps_the_older_dual_key_as_an_alias():
    # before the shared dual-key cleaning the key kept the language tag: "7hitmovies com de|dune|2021"
    _, data = _movie_group('7HitMovies.com.de - Dune (2021) ORG Hindi Dual Audio 720p BluRay.mkv')
    assert {'7hitmovies com|dune|2021', '7hitmovies com de|dune|2021'} <= set(data['aliases'])


@pytest.mark.parametrize('tld', S10_TLDS)
def test_s10_site_only_series_key_is_never_an_alias(tld, harness):
    name = '7HitMovies.%s - True.Detective - Night Country - S04E06.720p.mkv' % tld
    assert parse_episode_info(name, legacy_site=True)['series_name'] == S10_OLD_SITE[tld]
    assert _site_legacy_series_keys(name) == []
    data = group(['7HitMovies.%s - Dark.Matter.S01E01.720p.mkv' % tld])['series']['dark matter']
    assert S10_OLD_SITE[tld] not in data.get('aliases', [])
    file_dict = data['seasons'][1][1][0]
    harness.state.mark_watched('ep:%s|S01E01' % S10_OLD_SITE[tld])
    assert harness.state.resolve_state_key(file_dict, data.get('aliases')) == 'ep:dark matter|S01E01'


def test_old_movie_row_resolves_through_the_alias(harness):
    key, data = _movie_group(MOVIE_SINGLE)
    file_dict = dict(data['versions'][0], canonical_key=key)
    harness.state.mark_watched('mv:7hitmovies diy dune part two|2024')
    assert harness.state.resolve_state_key(file_dict, data['aliases']) == 'mv:7hitmovies diy dune part two|2024'


def test_old_episode_row_resolves_through_the_alias(harness):
    # the old group key was the dual "7hitmovies dad|true detective"; state keys normalize a dual key
    # to its last segment, so the row already sits under the current key: resolution agrees and
    # rewrites nothing
    r = group([SERIES_DUAL])
    data = r['series']['true detective']
    file_dict = data['seasons'][4][5][0]
    old_form = dict(file_dict, series_name='7hitmovies dad|true detective')
    old_key = harness.state.state_key_for(old_form)
    harness.state.mark_watched(old_key)
    assert harness.state.resolve_state_key(file_dict, data['aliases']) == old_key == 'ep:true detective|S04E05'


def test_resolution_is_idempotent_and_never_writes(harness):
    key, data = _movie_group(MOVIE_SINGLE)
    file_dict = dict(data['versions'][0], canonical_key=key)
    harness.state.mark_watched('mv:7hitmovies diy dune part two|2024')
    first = harness.state.resolve_state_key(file_dict, data['aliases'])
    assert harness.state.resolve_state_key(file_dict, data['aliases']) == first
    assert harness.state.get_state('mv:dune part two|2024') is None


def test_current_row_wins_and_the_old_row_is_untouched(harness):
    key, data = _movie_group(MOVIE_SINGLE)
    file_dict = dict(data['versions'][0], canonical_key=key)
    harness.state.mark_watched('mv:7hitmovies diy dune part two|2024')
    harness.state.record_playback('mv:dune part two|2024', 100, 1000)
    assert harness.state.resolve_state_key(file_dict, data['aliases']) == 'mv:dune part two|2024'
    assert harness.state.get_state('mv:7hitmovies diy dune part two|2024')['watched'] == 1


def test_row_of_a_site_only_series_key_stays_orphaned(harness):
    r = group(['7HitMovies.dad - Dark.Matter.S01E01.720p.mkv'])
    data = r['series']['dark matter']
    file_dict = data['seasons'][1][1][0]
    harness.state.mark_watched('ep:7hitmovies dad|S01E01')
    assert harness.state.resolve_state_key(file_dict, data.get('aliases')) == 'ep:dark matter|S01E01'


def test_old_favorite_is_found_through_the_alias():
    from tests.unit.test_favorites import FavoritesTestBase
    from lib.favorites import add_favorite, find_favorite_by_aliases

    class _Case(FavoritesTestBase):
        def runTest(self):
            key, data = _movie_group(MOVIE_SINGLE)
            add_favorite({'type': 'movie', 'canonical_key': '7hitmovies diy dune part two|2024',
                          'display_name': '7HitMovies diy Dune Part Two'})
            found = find_favorite_by_aliases('movie', key, data['aliases'])
            assert found['canonical_key'] == '7hitmovies diy dune part two|2024'
            # a current favorite is found by its own key and nothing is rewritten
            assert find_favorite_by_aliases('movie', key, data['aliases']) is found
            assert find_favorite_by_aliases('movie', 'other film|2024', ['x|2024']) is None

    case = _Case()
    case.setUp()
    try:
        case.runTest()
    finally:
        case.tearDown()


def test_old_favorite_resolves_to_the_live_bucket_key():
    from lib.keys import normalize_movie_key
    from lib.series_ui import _resolve_drifted_key
    key, data = _movie_group(MOVIE_SINGLE)
    bucket = {key: dict(data, display_name='Dune Part Two')}
    assert _resolve_drifted_key(bucket, '7hitmovies diy dune part two|2024', '7HitMovies diy', normalize_movie_key) == key
    # a stored key that no alias names is left alone
    assert _resolve_drifted_key(bucket, '7hitmovies best|2024', 'x', normalize_movie_key) == '7hitmovies best|2024'


def test_site_only_series_favorite_does_not_resolve_to_an_arbitrary_show():
    from lib.keys import normalize_series_key
    from lib.series_ui import _resolve_drifted_key
    r = group(['7HitMovies.best - Dark.Matter.S01E01.720p.mkv',
               '7HitMovies.best - True.Detective.S04E05.720p.mkv'])
    assert sorted(r['series']) == ['dark matter', 'true detective']
    assert _resolve_drifted_key(r['series'], '7hitmovies best', '7HitMovies best', normalize_series_key) \
        == '7hitmovies best'


def test_unaffected_files_get_no_alias():
    r = group(['7HitMovies.cool - True.Detective.S04E05.720p.mkv', 'Danger.Zone - S01E01.mkv'])
    assert not r['series']['danger zone'].get('aliases')
    assert not r['series']['true detective'].get('aliases')

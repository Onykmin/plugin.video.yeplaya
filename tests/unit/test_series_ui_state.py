#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for series_ui state integration (multi-version episode rows)."""
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from tests.conftest import reset_mock_addon


@pytest.fixture
def state_harness():
    """Fresh state module bound to a tempfile DB."""
    tmpdir = tempfile.mkdtemp()
    dbpath = os.path.join(tmpdir, 'state.db')
    reset_mock_addon()
    if 'lib.state' in sys.modules:
        del sys.modules['lib.state']
    from lib import state as _state
    _state._reset_for_tests(dbpath)
    _state._get_db_path = lambda: dbpath
    yield _state
    _state._reset_for_tests()
    try:
        os.remove(dbpath)
    except OSError:
        pass
    try:
        os.rmdir(tmpdir)
    except OSError:
        pass


def test_multi_version_episode_marks_watched(state_harness):
    """Pre-populated watched state should flow through apply_playback_state."""
    state_harness.mark_watched('ep:south park|S05E03')

    # Simulate the branch's ListItem creation
    import xbmcgui
    from lib.utils import apply_playback_state

    listitem = xbmcgui.ListItem(label='Episode 3 [3 versions]')
    listitem.setProperty('IsPlayable', 'true')
    state_key = state_harness.state_key_for({
        'series_name': 'south park',
        'season': 5,
        'episode': 3,
    })
    assert state_key == 'ep:south park|S05E03'
    cmds = apply_playback_state(listitem, state_key)

    assert listitem._info.get('playcount') == 1
    assert listitem._info.get('overlay') == 5
    # Unwatched toggle should be in the commands
    labels = [c[0] for c in cmds]
    assert any('30271' in lbl for lbl in labels)


def test_multi_version_resume_sets_properties(state_harness):
    state_harness.record_playback('ep:south park|S05E03', 600, 2400)

    import xbmcgui
    from lib.utils import apply_playback_state

    listitem = xbmcgui.ListItem(label='Episode 3')
    state_key = state_harness.state_key_for({
        'series_name': 'south park', 'season': 5, 'episode': 3,
    })
    apply_playback_state(listitem, state_key)

    assert listitem._properties.get('ResumeTime') == '600'
    assert listitem._properties.get('TotalTime') == '2400'


def test_search_ui_movie_single_version_applies_playback_state(state_harness):
    """Fix C: the movie tile must surface watched/resume metadata via apply_playback_state."""
    state_harness.mark_watched('mv:inception|2010')

    import xbmcgui
    from lib.utils import apply_playback_state

    listitem = xbmcgui.ListItem(label='Inception (2010)')
    mv_state_key = "mv:{0}".format('inception|2010')
    cmds = apply_playback_state(listitem, mv_state_key)

    assert listitem._info.get('playcount') == 1
    assert listitem._info.get('overlay') == 5
    labels = [c[0] for c in cmds]
    assert any('30271' in lbl for lbl in labels)


@pytest.mark.parametrize('item, url_args', [
    ({'series_name': 'south park', 'season': 5, 'episode': 3},
     {'series': 'south park', 'season': 5, 'episode': 3}),
    ({'canonical_key': 'inception|2010'}, {'movie_key': 'inception|2010'}),
])
def test_state_key_survives_play_url_roundtrip(state_harness, item, url_args):
    """The key a listing row uses must equal the key play() derives from that
    row's play URL, or watched/resume would never match across the handoff."""
    from urllib.parse import urlparse, parse_qsl
    from lib.utils import get_url
    from lib.playback import _build_state_key

    url = get_url(action='play', ident='abc', name='f.mkv', **url_args)
    params = dict(parse_qsl(urlparse(url).query))
    assert _build_state_key(params) == state_harness.state_key_for(dict(item, ident='abc'))


def _live_series(names):
    from lib.grouping import group_by_series
    files = [{'name': n, 'ident': 'id%d' % i, 'size': str(1000 + i)} for i, n in enumerate(names)]
    return group_by_series(files)['series']


def test_favorite_stored_with_an_old_display_still_resolves_by_key():
    """The display vote renamed groups ("Stranger Thing" -> "Stranger Things",
    "Mashle - 01" -> "Mashle"); the key is the primary identity, so a favorite
    stored under the old display resolves even though no live display equals it."""
    from lib.keys import normalize_series_key
    from lib.series_ui import _resolve_drifted_key
    live = _live_series(['Mashle - %02d.mkv' % n for n in (1, 2, 3)])
    assert [v['display_name'] for v in live.values()] == ['Mashle']
    assert _resolve_drifted_key(live, 'tucnak|mashle', 'Mashle - 01', normalize_series_key) == 'mashle'


def test_favorite_display_fallback_matches_the_voted_display():
    """When the key drifted beyond normalisation, a favorite saved with the
    current (voted, episode-number free) display still finds its group."""
    from lib.keys import normalize_series_key
    from lib.series_ui import _resolve_drifted_key
    live = _live_series(['Mashle - %02d.mkv' % n for n in (1, 2, 3)])
    assert _resolve_drifted_key(live, 'unrelated key', 'mashle', normalize_series_key) == 'mashle'


def test_favorite_stored_under_a_merged_away_key_resolves_by_alias():
    """The merge survivor used to depend on input order: a favorite stored under
    a key the live group was merged from resolves to that group."""
    from lib.keys import normalize_series_key
    from lib.series_ui import _resolve_drifted_key
    live = _live_series(['South.Park.S01E01.mkv', 'South.Park.S01E02.mkv', 'Mestecko.South.Park.S01E03.mkv'])
    assert list(live) == ['south park'] and live['south park']['aliases'] == ['mestecko south park']
    # display name does not help: the stored name differs from the live one
    assert _resolve_drifted_key(live, 'mestecko south park', 'Totally Else', normalize_series_key) == 'south park'


def test_alias_resolution_covers_movies_and_other_years():
    from lib.grouping import group_movies
    from lib.keys import normalize_movie_key
    from lib.series_ui import _resolve_drifted_key
    files = [{'name': n, 'ident': 'id%d' % i, 'size': str(10 + i)} for i, n in enumerate(
        ['Blade.2.2002.mkv', 'Blade.2.2002.720p.mkv', 'Blade.2.2000.mkv'])]
    live = group_movies(files)['movies']
    assert _resolve_drifted_key(live, 'blade 2|2000', '', normalize_movie_key) == 'blade 2|2002'


def test_normalized_identity_still_beats_an_alias_and_unknown_keys_stay():
    from lib.keys import normalize_series_key
    from lib.series_ui import _resolve_drifted_key
    live = {'a': {'aliases': ['b']}, 'b': {'aliases': []}}
    assert _resolve_drifted_key(live, 'x|b', '', normalize_series_key) == 'b'   # normalized equality first
    assert _resolve_drifted_key(live, 'zzz', '', normalize_series_key) == 'zzz'


# --- S5b: keys changed by content merges, dual-name aliases and franchise splits ---

def _group_with_sizes(names, sizes):
    from lib.grouping import group_by_series
    files = [{'name': n, 'ident': 'id%d' % i, 'size': str(sizes[i])} for i, n in enumerate(names)]
    return group_by_series(files)['series']


def _first_version(group, season=1, episode=1):
    return group['seasons'][season][episode][0]


def _suits_group():
    names = ['Suits.S01E%02d.mkv' % e for e in (1, 2, 3)] + ['Suits.Kravataci.S01E%02d.mkv' % e for e in (1, 2, 3)]
    live = _group_with_sizes(names, [1_000_000, 2_000_000, 3_000_000] * 2)
    assert list(live) == ['suits']
    return live['suits']


def test_state_row_of_a_content_merged_key_resolves_and_current_row_wins(state_harness):
    suits = _suits_group()
    v = _first_version(suits, episode=2)
    state_harness.mark_watched('ep:suits kravataci|S01E02')
    assert state_harness.resolve_state_key(v, v['series_aliases']) == 'ep:suits kravataci|S01E02'
    state_harness.record_playback('ep:suits|S01E02', 100, 1000)
    assert state_harness.resolve_state_key(v, v['series_aliases']) == 'ep:suits|S01E02'


def test_state_row_of_another_show_is_not_claimed_by_a_content_merged_group(state_harness):
    v = _first_version(_suits_group(), episode=2)
    state_harness.mark_watched('ep:suits legal|S01E02')
    state_harness.mark_watched('ep:suits kravataci|S01E09')
    assert state_harness.resolve_state_key(v, v['series_aliases']) == 'ep:suits|S01E02'


def test_state_row_under_the_plain_key_of_a_declared_alias_resolves(state_harness):
    live = _live_series(['Kimetsu no Yaiba (Demon Slayer) - %02d.mkv' % n for n in (10, 11)])
    assert list(live) == ['demon slayer|kimetsu no yaiba']
    v = _first_version(live['demon slayer|kimetsu no yaiba'], episode=10)
    state_harness.mark_watched('ep:kimetsu no yaiba|S01E10')       # key before the alias was read
    assert state_harness.resolve_state_key(v, v['series_aliases']) == 'ep:kimetsu no yaiba|S01E10'
    assert state_harness.get_state('ep:demon slayer|kimetsu no yaiba|S01E10') is None   # read-only


def test_split_sibling_does_not_inherit_rows_stored_under_the_old_franchise_key(state_harness):
    names = (['Star.Wars.S01E%02d.mkv' % e for e in (1, 2, 3)]
             + ['Star.Wars.Rebels.S01E%02d.mkv' % e for e in (1, 2, 3, 4)]
             + ['Star.Wars.Droids.S01E%02d.mkv' % e for e in (1, 2, 3, 4)])
    live = _group_with_sizes(names, list(range(1000, 1000 + len(names))))
    assert sorted(live) == ['star wars', 'star wars droids', 'star wars rebels']
    state_harness.mark_watched('ep:star wars|S01E01')               # written while one blob existed
    rebels = _first_version(live['star wars rebels'])
    assert state_harness.resolve_state_key(rebels, rebels['series_aliases']) == 'ep:star wars rebels|S01E01'
    stub = _first_version(live['star wars'])
    assert state_harness.resolve_state_key(stub, stub['series_aliases']) == 'ep:star wars|S01E01'


# --- S7: a dual group answers to every name form; no dual group claims another's rows ---

def _penguin_group():
    live = _live_series(['The.Penguin.S01E01.mkv', 'The.Penguin.S01E02.mkv', 'Tucnak.S01E03.mkv',
                         'The Penguin - Tu\u010d\u0148\u00e1k S01E04.mkv'])
    assert list(live) == ['penguin']
    return live['penguin']


def test_state_row_under_the_single_name_of_a_dual_group_resolves(state_harness):
    v = _first_version(_penguin_group(), episode=3)
    state_harness.mark_watched('ep:tucnak|S01E03')              # written while only the Czech name was known
    assert state_harness.resolve_state_key(v, v['series_aliases']) == 'ep:tucnak|S01E03'


@pytest.mark.parametrize('old', ['ep:penguin|S01E03', 'ep:tucnak|S01E03'])
def test_state_row_under_either_name_of_a_dual_key_resolves(state_harness, old):
    live = _live_series(['Tucnak.S01E03.mkv', 'The Penguin - Tu\u010d\u0148\u00e1k S01E04.mkv'])
    assert list(live) == ['penguin|tucnak']
    v = _first_version(live['penguin|tucnak'], episode=3)
    state_harness.mark_watched(old)
    assert state_harness.resolve_state_key(v, v['series_aliases']) == old


# The two fetches whose group keys differ ("penguin" vs "penguin|tucnak"): the write-side identity
# depends on which alias files came back, the read side must not.
PENGUIN_FETCHES = {
    'with-plain-file': ['The.Penguin.S01E01.mkv', 'Tu\u010d\u0148\u00e1k.S01E02.mkv',
                        'The Penguin - Tu\u010d\u0148\u00e1k S01E03.mkv'],
    'without-plain-file': ['Tu\u010d\u0148\u00e1k.S01E02.mkv', 'The Penguin - Tu\u010d\u0148\u00e1k S01E03.mkv'],
}


@pytest.mark.parametrize('stored', ['penguin', 'tucnak'])
@pytest.mark.parametrize('fetch', PENGUIN_FETCHES)
def test_state_row_of_either_fetch_identity_resolves_in_either_fetch(state_harness, fetch, stored):
    (group,) = _live_series(PENGUIN_FETCHES[fetch]).values()
    v = _first_version(group, episode=2)
    state_harness.mark_watched('ep:%s|S01E02' % stored)
    assert state_harness.resolve_state_key(v, v['series_aliases']) == 'ep:%s|S01E02' % stored


@pytest.mark.parametrize('stored', ['penguin', 'tucnak', 'penguin|tucnak'])
@pytest.mark.parametrize('fetch', PENGUIN_FETCHES)
def test_favorite_of_either_fetch_identity_resolves_in_either_fetch(fetch, stored):
    import lib.favorites as fav
    from lib.favorites import find_favorite_by_aliases
    key, group = next(iter(_live_series(PENGUIN_FETCHES[fetch]).items()))
    favs = [{'type': 'series', 'canonical_key': stored}]
    fav._cached_items = favs
    try:
        assert find_favorite_by_aliases('series', key, group['aliases']) is favs[0]
    finally:
        fav._cached_items = None


def test_current_dual_row_wins_and_resolution_is_read_only(state_harness):
    live = _live_series(['Tucnak.S01E03.mkv', 'The Penguin - Tu\u010d\u0148\u00e1k S01E04.mkv'])
    v = _first_version(live['penguin|tucnak'], episode=3)
    state_harness.mark_watched('ep:penguin|S01E03')
    state_harness.record_playback('ep:tucnak|S01E03', 100, 1000)
    before = state_harness.get_state('ep:penguin|S01E03')
    assert state_harness.resolve_state_key(v, v['series_aliases']) == 'ep:tucnak|S01E03'
    assert state_harness.resolve_state_key(v, v['series_aliases']) == 'ep:tucnak|S01E03'
    assert state_harness.get_state('ep:penguin|S01E03') == before


def test_state_row_under_the_old_csfd_spelling_of_a_dual_key_resolves(state_harness):
    # dual keys used to be cleaned by csfd_scraper (keeps roman numerals, years, commas)
    live = _live_series(['Star Wars II - Klonovani utocia S01E01.mkv', 'Star Wars II - Klonovani utocia S01E02.mkv'])
    key = next(iter(live))
    v = _first_version(live[key])
    state_harness.mark_watched('ep:star wars ii|S01E01')
    assert state_harness.resolve_state_key(v, v['series_aliases']) == 'ep:star wars ii|S01E01'


def test_favorite_under_any_name_form_of_a_dual_group_resolves():
    from lib.favorites import find_favorite_by_aliases
    live = _live_series(['Star Wars II - Klonovani utocia S01E01.mkv', 'Star Wars II - Klonovani utocia S01E02.mkv'])
    key, group = next(iter(live.items()))
    for stored in ('klonovani utocia|star wars ii', 'star wars ii', 'klonovani utocia'):
        favs = [{'type': 'series', 'canonical_key': stored}]
        import lib.favorites as fav
        fav._cached_items = favs
        try:
            assert find_favorite_by_aliases('series', key, group['aliases']) is favs[0], stored
        finally:
            fav._cached_items = None


def test_movie_row_under_the_old_csfd_spelling_of_a_dual_key_resolves(state_harness):
    from lib.grouping import group_by_series
    files = [{'name': n, 'ident': 'id%d' % i, 'size': str(1000 + i)} for i, n in enumerate(
        ['Star Wars II - Klonovani utocia (2002) Cz dab.avi', 'Star Wars II (2002).avi'])]
    (key, movie), = group_by_series(files)['movies'].items()
    state_harness.mark_watched('mv:star wars ii|2002')           # identity of "klonovani utocia|star wars ii|2002"
    assert state_harness.resolve_state_key({'canonical_key': key}, movie['aliases']) == 'mv:star wars ii|2002'


STAR_WARS_NAMES = (['Star.Wars.S01E%02d.mkv' % e for e in (1, 2, 3)]
                   + ['Star.Wars.Rebels.S01E%02d.mkv' % e for e in (1, 2, 3, 4)]
                   + ['Star.Wars.Droids.S01E%02d.mkv' % e for e in (1, 2, 3, 4)]
                   + ['Star Wars - Odboj S01E%02d.mkv' % e for e in (1, 2, 3)]
                   + ['Star Wars - Povstalci S01E%02d.mkv' % e for e in (1, 2, 3)])


def test_dual_groups_of_different_shows_do_not_claim_each_others_state_rows(state_harness):
    from lib.keys import normalize_series_key
    live = _group_with_sizes(STAR_WARS_NAMES, list(range(1000, 1000 + len(STAR_WARS_NAMES))))
    # distinct state identities: watching one show must not mark another's episode
    assert len({normalize_series_key(k) for k in live}) == len(live)
    state_harness.mark_watched('ep:star wars|S01E01')           # written while the names were one blob
    resolved = {}
    for key, group in live.items():
        v = _first_version(group)
        resolved[key] = state_harness.resolve_state_key(v, v['series_aliases'])
    owners = [k for k, r in resolved.items() if r == 'ep:star wars|S01E01']
    assert owners == ['star wars']                              # only the plain group owns it


def test_favorite_stored_under_a_content_merged_or_declared_alias_key_resolves():
    from lib.keys import normalize_series_key
    from lib.series_ui import _resolve_drifted_key
    live = {'suits': _suits_group()}
    assert _resolve_drifted_key(live, 'suits kravataci', 'Other', normalize_series_key) == 'suits'
    live = _live_series(['Kimetsu no Yaiba (Demon Slayer) - %02d.mkv' % n for n in (10, 11)])
    assert _resolve_drifted_key(live, 'kimetsu no yaiba', 'Other', normalize_series_key) \
        == 'demon slayer|kimetsu no yaiba'
    assert _resolve_drifted_key(live, 'demon slayer', 'Other', normalize_series_key) \
        == 'demon slayer|kimetsu no yaiba'
    assert _resolve_drifted_key(live, 'unrelated show', 'Other', normalize_series_key) == 'unrelated show'


def _render(monkeypatch, state, func, params, grouped):
    """Run a series_ui list handler against a prepared grouping; return the ListItems."""
    import xbmcplugin
    from lib import series_ui
    items = []
    monkeypatch.setattr(series_ui, 'revalidate', lambda: 'token')
    # series_ui binds lib.state names at import; follow the per-test state module
    for name in ('resolve_state_key', 'build_mv_state_key', 'get_states', 'state_key_for'):
        monkeypatch.setattr(series_ui, name, getattr(state, name))
    monkeypatch.setattr(series_ui, 'get_or_fetch_grouped', lambda *a, **k: ('ck', grouped))
    monkeypatch.setattr(xbmcplugin, 'addDirectoryItem',
                        lambda handle, url, li, *a, **k: items.append((url, li)), raising=False)
    func(params)
    return items


def test_browse_season_multi_version_row_reads_a_row_stored_under_an_alias(state_harness, monkeypatch):
    from lib import series_ui
    from lib.grouping import group_by_series
    files = [{'name': n, 'ident': 'id%d' % i, 'size': str(1000 + i)} for i, n in enumerate(
        ['South.Park.S01E01.1080p.mkv', 'South.Park.S01E01.720p.mkv', 'South.Park.S01E02.mkv',
         'Mestecko.South.Park.S01E03.mkv'])]
    grouped = group_by_series(files)
    assert list(grouped['series']) == ['south park']
    state_harness.mark_watched('ep:mestecko south park|S01E01')   # old survivor key of another order
    items = _render(monkeypatch, state_harness, series_ui.browse_season,
                    {'series': 'south park', 'season': '1', 'what': 'south park'}, grouped)
    watched = [url for url, li in items if li._info.get('playcount') == 1]
    assert len(watched) == 1 and 'action=select_version' in watched[0] and 'episode=1' in watched[0]
    assert state_harness.get_state('ep:south park|S01E01') is None   # read-only


def _gapped_marker_grouping():
    from lib.grouping import group_by_series
    files = [{'name': n, 'ident': 'id%d' % i, 'size': str(1000 + i)} for i, n in enumerate(
        ['Squid.Game.S03.E01.2025.1080p.mkv', 'Squid.Game.S03.E01.2025.720p.mkv', 'Squid.Game.S03.E02.2025.mkv'])]
    grouped = group_by_series(files)
    assert list(grouped['series']) == ['squid game']
    return grouped


def _watched_urls(items):
    return [url for url, li in items if li._info.get('playcount') == 1]


def test_browse_season_multi_version_row_reads_a_row_stored_under_the_files_old_movie_key(state_harness, monkeypatch):
    from lib import series_ui
    grouped = _gapped_marker_grouping()
    state_harness.mark_watched('mv:squid game s03 e01|2025')   # the file was a movie before its marker was read
    items = _render(monkeypatch, state_harness, series_ui.browse_season,
                    {'series': 'squid game', 'season': '3', 'what': 'squid game'}, grouped)
    watched = _watched_urls(items)
    assert len(watched) == 1 and 'action=select_version' in watched[0] and 'episode=1' in watched[0]
    assert state_harness.get_state('ep:squid game|S03E01') is None   # read-only


def test_browse_season_current_episode_row_wins_over_the_old_movie_row(state_harness, monkeypatch):
    from lib import series_ui
    grouped = _gapped_marker_grouping()
    state_harness.mark_watched('mv:squid game s03 e01|2025')
    state_harness.record_playback('ep:squid game|S03E01', 100, 1000)   # in progress, not watched
    items = _render(monkeypatch, state_harness, series_ui.browse_season,
                    {'series': 'squid game', 'season': '3', 'what': 'squid game'}, grouped)
    assert _watched_urls(items) == []


def test_other_files_movie_row_reads_a_row_stored_under_an_alias(state_harness, monkeypatch):
    from lib import series_ui
    from lib.grouping import group_by_series
    files = [{'name': n, 'ident': 'id%d' % i, 'size': str(1000 + i)} for i, n in enumerate(
        ['Avatar.Extended.2009.mkv', 'Avatar.2009.mkv', 'Heat.1995.mkv'])]
    grouped = group_by_series(files)
    assert sorted(grouped['movies']) == ['avatar|2009', 'heat|1995']
    state_harness.mark_watched('mv:avatar extended|2009')
    items = _render(monkeypatch, state_harness, series_ui.browse_other, {'what': 'x'}, grouped)
    watched = [url for url, li in items if li._info.get('playcount') == 1]
    assert len(watched) == 1 and 'movie_key=avatar%7C2009' in watched[0]


# --- `Name NN - MM` read as season NN: keys left from the absolute reading ("peaky blinders 02") ---

def _peaky_group():
    names = (['Peaky.Blinders.S%02dE%02d.mkv' % (s, e) for s in (1, 2, 3) for e in (1, 2, 3)]
             + ['Peaky Blinders  %02d - %02d.mkv' % (s, e) for s in (1, 2, 3) for e in (1, 2, 3)])
    live = _live_series(names)
    assert list(live) == ['peaky blinders']
    return live['peaky blinders']


def test_state_row_under_the_absolute_reading_key_resolves_for_the_season_file(state_harness):
    peaky = _peaky_group()
    v = _first_version(peaky, season=2, episode=3)
    state_harness.mark_watched('ep:peaky blinders 02|S01E03')
    assert state_harness.resolve_state_key(v, v['series_aliases']) == 'ep:peaky blinders 02|S01E03'
    # no other season's file claims it, and a current row wins without touching the old one
    other = _first_version(peaky, season=3, episode=3)
    assert state_harness.resolve_state_key(other, other['series_aliases']) == 'ep:peaky blinders|S03E03'
    state_harness.record_playback('ep:peaky blinders|S02E03', 100, 1000)
    assert state_harness.resolve_state_key(v, v['series_aliases']) == 'ep:peaky blinders|S02E03'
    assert state_harness.get_state('ep:peaky blinders 02|S01E03')['watched'] == 1


def test_favorite_stored_under_an_absolute_reading_key_resolves_to_the_show():
    import lib.favorites as fav
    from lib.favorites import find_favorite_by_aliases
    from lib.keys import normalize_series_key
    from lib.series_ui import _resolve_drifted_key
    live = {'peaky blinders': _peaky_group()}
    favs = [{'type': 'series', 'canonical_key': 'peaky blinders 02'}]
    fav._cached_items = favs
    try:
        assert find_favorite_by_aliases('series', 'peaky blinders', live['peaky blinders']['aliases']) is favs[0]
    finally:
        fav._cached_items = None
    assert _resolve_drifted_key(live, 'peaky blinders 02', 'Other', normalize_series_key) == 'peaky blinders'
    assert _resolve_drifted_key(live, 'peaky blinders 07', 'Other', normalize_series_key) == 'peaky blinders 07'


def test_genuine_season_one_file_does_not_read_a_season_alias_row_of_the_peaky_group(state_harness):
    peaky = _peaky_group()
    state_harness.mark_watched('ep:peaky blinders 02|S01E03')
    v = _first_version(peaky, season=1, episode=3)
    assert state_harness.resolve_state_key(v, v['series_aliases']) == 'ep:peaky blinders|S01E03'

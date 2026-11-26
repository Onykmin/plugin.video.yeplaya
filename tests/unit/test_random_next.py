#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Random-next: the random episode handoff carries series/season context so a
natural end can continue the chain. Mocked Kodi, no network."""
import os
import sys
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import tests.conftest  # noqa: F401 — installs Kodi mocks

from lib import series_ui
from tests.unit.test_random_episode import (
    _ScriptedDialog, _ScriptedRandom, _grouped_series, _versions,
)

_PARAMS = {'series': 'show', 'what': 'q', 'category': 'tvshow', 'sort': 'largest'}


def _drive(seasons, params, script, selections, mode, extra_patches=()):
    """Run show_random_episode_dialog with the real _play_via_handoff.

    `mode` is the raw `random_episode_next` setting string. Returns what the
    handoff did: executebuiltin URLs and save_random_played calls.
    """
    grouped = _grouped_series(seasons)
    rand = _ScriptedRandom(script)
    dialog = _ScriptedDialog(selections)
    settings = {'random_episode_next': mode}
    save = MagicMock()
    builtin = MagicMock()
    with ExitStack() as stack:
        for p in (
            patch.object(series_ui, 'revalidate', return_value='tok'),
            patch.object(series_ui, 'get_or_fetch_grouped', return_value=('ck', grouped)),
            patch.object(series_ui, 'random', rand),
            patch.object(series_ui, 'popinfo'),
            patch.object(series_ui, '_enrich_displayed_version'),
            patch.object(series_ui, 'save_random_played', save),
            patch.object(series_ui.xbmc, 'executebuiltin', builtin),
            patch.object(sys.modules['xbmcgui'], 'Dialog', lambda: dialog),
            patch.object(sys.modules['xbmcplugin'], 'setResolvedUrl'),
            patch.object(series_ui._addon, 'getSetting',
                         side_effect=lambda k: settings.get(k, '')),
            *extra_patches,
        ):
            stack.enter_context(p)
        series_ui.show_random_episode_dialog(params)
    urls = [c.args[0] for c in builtin.call_args_list]
    return SimpleNamespace(urls=urls, save=save, dialog=dialog)


def _query(builtin_arg):
    """Query dict of a `PlayMedia(<url>)` argument, single values."""
    url = builtin_arg[len('PlayMedia('):-1]
    return {k: v[0] for k, v in parse_qs(urlparse(url).query,
                                         keep_blank_values=True).items()}


# ---------------------------------------------------------------------------
# Off: nothing changes
# ---------------------------------------------------------------------------

def test_handoff_extra_none_url_is_byte_identical():
    version = {'ident': 'abc', 'name': 'ep.mkv'}
    with patch.object(series_ui.xbmc, 'executebuiltin') as b:
        series_ui._play_via_handoff(version, 'show', 1, 2)
        series_ui._play_via_handoff(version, 'show', 1, 2, extra=None)
        series_ui._play_via_handoff(version, 'show', 1, 2, extra={})
    first, second, third = (c.args[0] for c in b.call_args_list)
    assert first == second == third


def test_handoff_off_adds_no_params_and_writes_no_file():
    for mode in ('0', '', 'abc', '7'):
        r = _drive({1: {1: _versions('a')}}, _PARAMS, [(1, 1)], [0], mode)
        assert len(r.urls) == 1
        q = _query(r.urls[0])
        assert not ({'rnd', 'what', 'category', 'sort', 'rseason'} & set(q)), mode
        assert q['series'] == 'show' and q['season'] == '1' and q['episode'] == '1'
        r.save.assert_not_called()


def test_handoff_off_url_matches_pre_change_url():
    r = _drive({1: {1: _versions('a', 'ep.mkv')}}, _PARAMS, [(1, 1)], [0], '0')
    with patch.object(series_ui.xbmc, 'executebuiltin') as b:
        series_ui._play_via_handoff({'ident': 'a', 'name': 'ep.mkv'}, 'show', 1, 1)
    assert r.urls == [c.args[0] for c in b.call_args_list]


# ---------------------------------------------------------------------------
# Ask / Autoplay: context carried
# ---------------------------------------------------------------------------

def test_handoff_ask_and_autoplay_carry_context():
    for mode in ('1', '2'):
        r = _drive({1: {1: _versions('a')}}, _PARAMS, [(1, 1)], [0], mode)
        q = _query(r.urls[0])
        assert q['rnd'] == '1'
        assert q['what'] == 'q'
        assert q['category'] == 'tvshow'
        assert q['sort'] == 'largest'
        # ordinary play params are untouched
        assert q['action'] == 'play' and q['ident'] == 'a'
        assert q['series'] == 'show' and q['season'] == '1' and q['episode'] == '1'


def test_handoff_series_wide_has_no_rseason():
    r = _drive({1: {1: _versions('a')}}, _PARAMS, [(1, 1)], [0], '1')
    assert 'rseason' not in _query(r.urls[0])


def test_handoff_season_scope_carries_rseason():
    params = dict(_PARAMS, season='2')
    r = _drive({1: {1: _versions('a')}, 2: {5: _versions('b')}}, params, [(2, 5)], [0], '1')
    q = _query(r.urls[0])
    assert q['rseason'] == '2'
    assert q['season'] == '2' and q['episode'] == '5'


def test_handoff_missing_optional_params_are_dropped():
    params = {'series': 'show', 'what': 'q'}
    r = _drive({1: {1: _versions('a')}}, params, [(1, 1)], [0], '2')
    q = _query(r.urls[0])
    assert q['rnd'] == '1' and q['what'] == 'q'
    assert 'category' not in q and 'sort' not in q and 'rseason' not in q


# ---------------------------------------------------------------------------
# Played set is saved before the handoff
# ---------------------------------------------------------------------------

def test_handoff_saves_every_shown_episode_incl_rerolled():
    seasons = {1: {1: _versions('a'), 2: _versions('b'), 3: _versions('c')}}
    # rows: Play, Reroll, Cancel -> 1 = Reroll, then 0 = Play
    r = _drive(seasons, _PARAMS, [(1, 1), (1, 3)], [1, 0], '1')
    r.save.assert_called_once_with('show|all', {(1, 1), (1, 3)})
    assert len(r.urls) == 1


def test_handoff_saves_under_season_scope():
    params = dict(_PARAMS, season='2')
    r = _drive({1: {1: _versions('a')}, 2: {5: _versions('b')}}, params, [(2, 5)], [0], '2')
    r.save.assert_called_once_with('show|2', {(2, 5)})


def test_handoff_save_happens_before_playmedia():
    order = []
    seasons = {1: {1: _versions('a')}}
    save = MagicMock(side_effect=lambda *a: order.append('save'))
    builtin = MagicMock(side_effect=lambda *a: order.append('play'))
    # extra_patches are entered after _drive's own mocks, so these win.
    r_patches = (
        patch.object(series_ui, 'save_random_played', save),
        patch.object(series_ui.xbmc, 'executebuiltin', builtin),
    )
    _drive(seasons, _PARAMS, [(1, 1)], [0], '1', extra_patches=r_patches)
    assert order == ['save', 'play']


def test_handoff_cancel_plays_nothing_and_saves_nothing():
    r = _drive({1: {1: _versions('a')}}, _PARAMS, [(1, 1)], [-1], '1')
    assert r.urls == []
    r.save.assert_not_called()


# ---------------------------------------------------------------------------
# Pick version path
# ---------------------------------------------------------------------------

def test_handoff_pick_version_path_carries_context():
    versions = [
        {'ident': 'v1', 'name': 'Show.S01E01.720p.mkv', 'size': '100'},
        {'ident': 'v2', 'name': 'Show.S01E01.1080p.mkv', 'size': '900'},
    ]
    extra_patches = (
        patch.object(series_ui, '_prepare_episode_versions', side_effect=lambda v, t: v),
        patch.object(series_ui, '_build_version_listitems', return_value=[MagicMock()] * 2),
    )
    # rows: Play, Pick version, Cancel -> 1 = Pick version, then choose entry 1
    r = _drive({1: {1: versions}}, _PARAMS, [(1, 1)], [1, 1], '1',
               extra_patches=extra_patches)
    assert len(r.urls) == 1
    q = _query(r.urls[0])
    assert q['rnd'] == '1' and q['what'] == 'q'
    assert q['series'] == 'show' and q['season'] == '1' and q['episode'] == '1'
    r.save.assert_called_once_with('show|all', {(1, 1)})


def test_handoff_pick_version_back_out_then_play_still_carries_context():
    versions = [
        {'ident': 'v1', 'name': 'Show.S01E01.720p.mkv', 'size': '100'},
        {'ident': 'v2', 'name': 'Show.S01E01.1080p.mkv', 'size': '900'},
    ]
    extra_patches = (
        patch.object(series_ui, '_prepare_episode_versions', side_effect=lambda v, t: v),
        patch.object(series_ui, '_build_version_listitems', return_value=[MagicMock()] * 2),
    )
    # Pick version -> back out (-1) -> Play
    r = _drive({1: {1: versions}}, _PARAMS, [(1, 1)], [1, -1, 0], '2',
               extra_patches=extra_patches)
    assert len(r.urls) == 1
    assert _query(r.urls[0])['rnd'] == '1'

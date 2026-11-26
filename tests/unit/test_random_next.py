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


# ---------------------------------------------------------------------------
# continue_random_episode (A5)
# ---------------------------------------------------------------------------

class _HeadingDialog(_ScriptedDialog):
    """_ScriptedDialog that also records the heading of every select()."""

    def __init__(self, selections):
        super().__init__(selections)
        self.headings = []

    def select(self, heading, listitems, useDetails=False):
        self.headings.append(heading)
        return super().select(heading, listitems, useDetails)


_PLAY_PARAMS = {'ident': 'cur', 'name': 'cur.mkv', 'series': 'show', 'season': '1',
                'episode': '1', 'rnd': '1', 'what': 'q', 'category': 'tvshow',
                'sort': 'largest'}

_THREE = {1: {1: _versions('a'), 2: _versions('b'), 3: _versions('c')}}


def _continue(seasons, params, script, selections, mode, saved=(), grouped='default',
              grouped_side_effect=None):
    """Run continue_random_episode with the real _play_via_handoff.

    Returns what the continuation did: PlayMedia URLs, save calls, dialog,
    popinfo and setResolvedUrl mocks, the random stub and the grouped mock.
    """
    if grouped == 'default':
        grouped = _grouped_series(seasons)
    rand = _ScriptedRandom(script)
    dialog = _HeadingDialog(selections)
    settings = {'random_episode_next': mode}
    save = MagicMock()
    builtin = MagicMock()
    popinfo = MagicMock()
    resolved = MagicMock()
    fetch = MagicMock(return_value=('ck', grouped), side_effect=grouped_side_effect)
    with ExitStack() as stack:
        for p in (
            patch.object(series_ui, 'revalidate', return_value='tok'),
            patch.object(series_ui, 'get_or_fetch_grouped', fetch),
            patch.object(series_ui, 'load_random_played', return_value=set(saved)),
            patch.object(series_ui, 'save_random_played', save),
            patch.object(series_ui, 'random', rand),
            patch.object(series_ui, 'popinfo', popinfo),
            patch.object(series_ui, '_enrich_displayed_version'),
            patch.object(series_ui.xbmc, 'executebuiltin', builtin),
            patch.object(series_ui.xbmc, 'log'),
            patch.object(sys.modules['xbmcgui'], 'Dialog', lambda: dialog),
            patch.object(sys.modules['xbmcplugin'], 'setResolvedUrl', resolved),
            patch.object(series_ui._addon, 'getSetting',
                         side_effect=lambda k: settings.get(k, '')),
            patch.object(series_ui._addon, 'getLocalizedString',
                         side_effect=lambda i: 'S{0} {{0}}'.format(i)),
        ):
            stack.enter_context(p)
        series_ui.continue_random_episode(params)
    return SimpleNamespace(urls=[c.args[0] for c in builtin.call_args_list], save=save,
                           dialog=dialog, popinfo=popinfo, resolved=resolved,
                           rand=rand, fetch=fetch)


def test_continue_off_is_noop():
    for mode in ('0', '', 'abc', '7'):
        r = _continue(_THREE, _PLAY_PARAMS, [], [], mode)
        assert r.urls == [] and r.dialog.shown == [], mode
        r.fetch.assert_not_called()
        r.save.assert_not_called()


def test_continue_ask_shows_dialog_with_heading_and_play_hands_off():
    r = _continue(_THREE, _PLAY_PARAMS, [(1, 2)], [0], '1')
    assert r.dialog.headings == ['S30460 Show']
    assert len(r.urls) == 1
    q = _query(r.urls[0])
    assert q['action'] == 'play' and q['ident'] == 'b'
    assert q['season'] == '1' and q['episode'] == '2'
    assert q['rnd'] == '1' and q['what'] == 'q' and q['sort'] == 'largest'
    r.save.assert_called_once_with('show|all', {(1, 1), (1, 2)})


def test_continue_ask_cancel_hands_off_nothing_and_never_resolves():
    r = _continue(_THREE, _PLAY_PARAMS, [(1, 2)], [-1], '1')
    assert r.urls == []
    r.resolved.assert_not_called()
    r.save.assert_not_called()


def test_continue_ask_dialog_rows_are_play_reroll_cancel():
    r = _continue(_THREE, _PLAY_PARAMS, [(1, 2)], [-1], '1')
    assert len(r.dialog.shown[0]) == 3  # Play, Reroll, Cancel


def test_continue_ask_reroll_reuses_picker_and_excludes_both_shown():
    # Reroll -> second pick; script must come from the pool minus current + first
    r = _continue(_THREE, _PLAY_PARAMS, [(1, 2), (1, 3)], [1, 0], '1')
    assert r.rand.calls[1] == [(1, 3)]
    assert len(r.urls) == 1 and _query(r.urls[0])['episode'] == '3'
    r.resolved.assert_not_called()


def test_continue_ask_start_over_redraws_when_pool_runs_out():
    seasons = {1: {1: _versions('a'), 2: _versions('b')}}
    # pick (1,2): Reroll finds the pool empty -> rows Play, Start over, Cancel;
    # 1 = Start over clears the set and draws (1,1); 0 = Play
    r = _continue(seasons, _PLAY_PARAMS, [(1, 2), (1, 1)], [1, 1, 0], '1')
    assert len(r.dialog.shown) == 3
    assert len(r.urls) == 1 and _query(r.urls[0])['episode'] == '1'


def test_continue_autoplay_hands_off_without_dialog_and_grows_played_set():
    r = _continue(_THREE, _PLAY_PARAMS, [(1, 3)], [], '2', saved={(1, 2)})
    assert r.dialog.shown == []
    assert len(r.urls) == 1
    q = _query(r.urls[0])
    assert q['ident'] == 'c' and q['rnd'] == '1' and q['what'] == 'q'
    r.save.assert_called_once_with('show|all', {(1, 1), (1, 2), (1, 3)})
    r.resolved.assert_not_called()


def test_continue_autoplay_exhausted_notifies_and_stops():
    seasons = {1: {1: _versions('a'), 2: _versions('b')}}
    r = _continue(seasons, _PLAY_PARAMS, [], [], '2', saved={(1, 2)})
    assert r.urls == [] and r.dialog.shown == []
    r.popinfo.assert_called_once()
    assert r.popinfo.call_args.args[0] == 'S30441 {0}'
    r.save.assert_not_called()


def test_continue_ask_exhausted_notifies_and_shows_no_dialog():
    seasons = {1: {1: _versions('a'), 2: _versions('b')}}
    r = _continue(seasons, _PLAY_PARAMS, [], [], '1', saved={(1, 2)})
    assert r.urls == [] and r.dialog.shown == []
    assert r.popinfo.call_args.args[0] == 'S30441 {0}'


def test_continue_current_episode_is_excluded_from_pick():
    r = _continue(_THREE, _PLAY_PARAMS, [(1, 2)], [-1], '1')
    assert r.rand.calls[0] == [(1, 2), (1, 3)]


def test_continue_played_set_is_excluded_from_pick():
    r = _continue(_THREE, _PLAY_PARAMS, [(1, 3)], [], '2', saved={(1, 2)})
    assert r.rand.calls[0] == [(1, 3)]


def test_continue_season_scope_honoured():
    seasons = {1: {1: _versions('a')}, 2: {1: _versions('b'), 2: _versions('c')}}
    params = dict(_PLAY_PARAMS, season='2', episode='1', rseason='2')
    r = _continue(seasons, params, [(2, 2)], [], '2')
    assert r.rand.calls[0] == [(2, 2)]
    q = _query(r.urls[0])
    assert q['rseason'] == '2' and q['season'] == '2' and q['episode'] == '2'
    r.save.assert_called_once_with('show|2', {(2, 1), (2, 2)})


def test_continue_cache_miss_notifies_and_stops():
    r = _continue(_THREE, _PLAY_PARAMS, [], [], '2', grouped=None)
    assert r.urls == []
    assert r.popinfo.call_args.args[0] == 'S30431 {0}'


def test_continue_series_missing_from_grouped_notifies_and_stops():
    r = _continue(_THREE, _PLAY_PARAMS, [], [], '2', grouped={'series': {}})
    assert r.urls == [] and r.popinfo.call_args.args[0] == 'S30431 {0}'


def test_continue_exception_is_logged_never_raised():
    r = _continue(_THREE, _PLAY_PARAMS, [], [], '2',
                  grouped_side_effect=RuntimeError('boom'))
    assert r.urls == []


def test_continue_fetches_grouped_with_url_params():
    r = _continue(_THREE, _PLAY_PARAMS, [(1, 2)], [-1], '1')
    args, kwargs = r.fetch.call_args
    assert args[0]['what'] == 'q' and args[0]['category'] == 'tvshow'
    assert args[0]['sort'] == 'largest'


# ---------------------------------------------------------------------------
# resolve_and_play(on_ended=...) hook and play() wiring (A6)
# ---------------------------------------------------------------------------

from lib import playback  # noqa: E402


class _FakePlayer:
    """Stands in for YePlayer: wait_for_playback leaves `ended` as configured."""

    def __init__(self, ended):
        self.ended = ended
        self.waited = 0

    def wait_for_playback(self):
        self.waited += 1


def _resolve(ended, on_ended, link='http://x/f'):
    """Run resolve_and_play with a fake player; returns (result, player, log)."""
    player = _FakePlayer(ended)
    log = MagicMock()
    with ExitStack() as stack:
        for p in (
            patch.object(playback, 'getlink', return_value=link),
            patch.object(playback, 'popinfo'),
            patch.object(playback.xbmc, 'log', log),
            patch.object(playback.xbmcgui, 'ListItem', MagicMock()),
            patch.object(playback.xbmcplugin, 'setResolvedUrl'),
            patch('lib.player.YePlayer', lambda **kw: player),
        ):
            stack.enter_context(p)
        result = playback.resolve_and_play('id', 'n', 'tok', state_key='k', on_ended=on_ended)
    return result, player, log


def test_hook_called_once_when_playback_ended():
    hook = MagicMock()
    result, player, _ = _resolve(True, hook)
    assert result is True and player.waited == 1
    hook.assert_called_once_with()


def test_hook_not_called_when_not_ended():
    # stop, error, backstop timeout and no-callback all leave ended False
    hook = MagicMock()
    result, player, _ = _resolve(False, hook)
    assert result is True and player.waited == 1
    hook.assert_not_called()


def test_hook_default_none_is_harmless_when_ended():
    result, _, _ = _resolve(True, None)
    assert result is True


def test_hook_exception_never_breaks_playback_and_is_logged():
    hook = MagicMock(side_effect=RuntimeError('boom'))
    result, _, log = _resolve(True, hook)
    assert result is True
    hook.assert_called_once_with()
    log.assert_called()


def test_hook_not_called_when_link_fails():
    hook = MagicMock()
    result, player, _ = _resolve(True, hook, link=None)
    assert result is False and player.waited == 0
    hook.assert_not_called()


def test_hook_runs_after_wait_for_playback():
    order = []
    player = _FakePlayer(True)
    player.wait_for_playback = lambda: order.append('wait')
    hook = MagicMock(side_effect=lambda: order.append('hook'))
    with ExitStack() as stack:
        for p in (
            patch.object(playback, 'getlink', return_value='http://x/f'),
            patch.object(playback.xbmcgui, 'ListItem', MagicMock()),
            patch.object(playback.xbmcplugin, 'setResolvedUrl'),
            patch('lib.player.YePlayer', lambda **kw: player),
        ):
            stack.enter_context(p)
        playback.resolve_and_play('id', 'n', 'tok', on_ended=hook)
    assert order == ['wait', 'hook']


def _play(params, ended=True):
    """Run playback.play with a fake player; returns the continue_random_episode mock."""
    cont = MagicMock()
    player = _FakePlayer(ended)
    with ExitStack() as stack:
        for p in (
            patch.object(playback, 'revalidate', return_value='tok'),
            patch.object(playback, 'getlink', return_value='http://x/f'),
            patch.object(playback.xbmcgui, 'ListItem', MagicMock()),
            patch.object(playback.xbmcplugin, 'setResolvedUrl'),
            patch('lib.player.YePlayer', lambda **kw: player),
            patch.object(series_ui, 'continue_random_episode', cont),
        ):
            stack.enter_context(p)
        playback.play(params)
    return cont


def test_hook_play_with_rnd_continues_with_play_params_on_end():
    cont = _play(dict(_PLAY_PARAMS), ended=True)
    cont.assert_called_once_with(_PLAY_PARAMS)


def test_hook_play_with_rnd_does_not_continue_on_stop():
    cont = _play(dict(_PLAY_PARAMS), ended=False)
    cont.assert_not_called()


def test_hook_play_without_rnd_never_continues():
    params = {k: v for k, v in _PLAY_PARAMS.items() if k != 'rnd'}
    cont = _play(params, ended=True)
    cont.assert_not_called()


def test_hook_play_with_rnd_other_than_one_never_continues():
    cont = _play(dict(_PLAY_PARAMS, rnd='0'), ended=True)
    cont.assert_not_called()


def test_hook_play_without_rnd_keeps_old_call_shape():
    params = {'ident': 'abc', 'name': 'f.mkv', 'series': 'show', 'season': '1', 'episode': '2'}
    with patch.object(playback, 'revalidate', return_value='tok'), \
         patch.object(playback, 'resolve_and_play') as rp:
        playback.play(params)
    rp.assert_called_once_with('abc', 'f.mkv', 'tok', state_key='ep:show|S01E02')

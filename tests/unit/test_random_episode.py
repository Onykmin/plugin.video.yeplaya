#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Random-episode picker: key flattening, row injection in browse_series /
browse_season, and the show_random_episode_dialog Play/Reroll/Cancel loop.

Covers the infinite-loop backstop (stale/empty version lists at dialog time).
"""
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import tests.conftest  # noqa: F401 — installs Kodi mocks
from tests.conftest import get_mock_addon

from lib import series_ui


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _versions(ident, name='ep.mkv'):
    return [{'ident': ident, 'name': name}]


class _ScriptedRandom:
    """Stub for series_ui.random exposing .choice(seq).

    Pops from a scripted list of keys to return. If the scripted key is not
    actually present in the `remaining` pool handed to us, raises loudly so
    a broken exclusion set surfaces immediately instead of silently picking
    something else. Records every `remaining` list it was given.
    """

    def __init__(self, script):
        self._script = list(script)
        self.calls = []

    def choice(self, seq):
        self.calls.append(list(seq))
        if not self._script:
            raise AssertionError('ScriptedRandom exhausted its script')
        key = self._script.pop(0)
        assert key in seq, (
            'Scripted key {0} not in remaining pool {1} — exclusion set '
            'broken'.format(key, seq))
        return key


class _ScriptedDialog:
    """Stub for xbmcgui.Dialog() recording every listitems batch shown."""

    def __init__(self, selections):
        self._selections = list(selections)
        self.shown = []

    def select(self, heading, listitems, useDetails=False):
        self.shown.append(listitems)
        if not self._selections:
            raise AssertionError('ScriptedDialog ran out of scripted selections')
        return self._selections.pop(0)


def _run_dialog(grouped, params, rand_script=None, selections=None, extra_patches=None):
    """Drive show_random_episode_dialog with the standard seams patched.

    Returns (rand, dialog, resolve_mock, popinfo_mock, resolved_mock) so
    tests can assert on any of them.
    """
    rand = _ScriptedRandom(rand_script or [])
    dialog = _ScriptedDialog(selections if selections is not None else [-1])
    xbmcgui_mod = sys.modules['xbmcgui']
    xbmcplugin_mod = sys.modules['xbmcplugin']

    patches = [
        patch.object(series_ui, 'revalidate', return_value='tok'),
        patch.object(series_ui, 'get_or_fetch_grouped', return_value=('ck', grouped)),
        patch.object(series_ui, 'random', rand),
        patch.object(series_ui, 'resolve_and_play'),
        patch.object(series_ui, '_play_via_handoff'),
        patch.object(series_ui, 'popinfo'),
        patch.object(xbmcgui_mod, 'Dialog', lambda: dialog),
        patch.object(xbmcplugin_mod, 'setResolvedUrl'),
    ]
    if extra_patches:
        patches.extend(extra_patches)

    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7]:
        series_ui.show_random_episode_dialog(params)
        # Playback now goes through _play_via_handoff (a PlayMedia
        # handoff to ?action=play), NOT resolve_and_play — the picker
        # must never be the URL Kodi attributes playback to.
        resolve_mock = series_ui._play_via_handoff
        popinfo_mock = series_ui.popinfo
        resolved_mock = xbmcplugin_mod.setResolvedUrl

    return rand, dialog, resolve_mock, popinfo_mock, resolved_mock


def _grouped_series(seasons, display_name='Show', total_episodes=None):
    if total_episodes is None:
        total_episodes = sum(len(eps) for eps in seasons.values())
    return {'series': {'show': {
        'display_name': display_name,
        'seasons': seasons,
        'total_episodes': total_episodes,
    }}}


# ---------------------------------------------------------------------------
# 1-2: _flatten_episode_keys
# ---------------------------------------------------------------------------

def test_flatten_all_seasons_uniform_keys():
    series_data = {
        'seasons': {
            1: {1: _versions('a'), 2: _versions('b'), 3: []},
            2: {1: _versions('c')},
        }
    }
    keys = series_ui._flatten_episode_keys(series_data)
    assert keys == [(1, 1), (1, 2), (2, 1)]
    assert (1, 3) not in keys


def test_flatten_season_scoped():
    series_data = {
        'seasons': {
            1: {1: _versions('a'), 2: _versions('b')},
            2: {1: _versions('c'), 2: _versions('d')},
        }
    }
    keys = series_ui._flatten_episode_keys(series_data, season_num=2)
    assert keys == [(2, 1), (2, 2)]


# ---------------------------------------------------------------------------
# 3-7: browse_series / browse_season row injection
# ---------------------------------------------------------------------------

def _run_browse_series(grouped, params, setting=None):
    addon = get_mock_addon()
    if setting is not None:
        addon.setSetting('random_episode', setting)
    else:
        addon.setSetting('random_episode', 'false')
    recorded = []

    def _add(handle, url, listitem, isFolder):
        recorded.append((url, listitem, isFolder))

    xbmcplugin_mod = sys.modules['xbmcplugin']
    try:
        with patch.object(series_ui, 'revalidate', return_value='tok'), \
             patch.object(series_ui, 'get_or_fetch_grouped', return_value=('ck', grouped)), \
             patch.object(xbmcplugin_mod, 'addDirectoryItem', _add), \
             patch.object(xbmcplugin_mod, 'endOfDirectory'):
            series_ui.browse_series(params)
    finally:
        addon.setSetting('random_episode', 'false')
    return recorded


def _run_browse_season(grouped, params, setting=None):
    addon = get_mock_addon()
    if setting is not None:
        addon.setSetting('random_episode', setting)
    else:
        addon.setSetting('random_episode', 'false')
    recorded = []

    def _add(handle, url, listitem, isFolder):
        recorded.append((url, listitem, isFolder))

    xbmcplugin_mod = sys.modules['xbmcplugin']
    try:
        with patch.object(series_ui, 'revalidate', return_value='tok'), \
             patch.object(series_ui, 'get_or_fetch_grouped', return_value=('ck', grouped)), \
             patch.object(xbmcplugin_mod, 'addDirectoryItem', _add), \
             patch.object(xbmcplugin_mod, 'endOfDirectory'):
            series_ui.browse_season(params)
    finally:
        addon.setSetting('random_episode', 'false')
    return recorded


def test_setting_off_hides_series_row():
    grouped = _grouped_series({1: {1: _versions('a')}})
    params = {'series': 'show', 'what': 'q'}
    recorded = _run_browse_series(grouped, params, setting='false')
    labels = [li.label for _, li, _ in recorded]
    assert 'String_30434' not in labels


def test_setting_off_hides_season_row():
    grouped = _grouped_series({1: {1: _versions('a')}})
    params = {'series': 'show', 'season': '1', 'what': 'q'}
    recorded = _run_browse_season(grouped, params, setting='false')
    labels = [li.label for _, li, _ in recorded]
    assert 'String_30435' not in labels


def test_setting_on_injects_series_row():
    grouped = _grouped_series({1: {1: _versions('a')}})
    params = {'series': 'show', 'what': 'q'}
    recorded = _run_browse_series(grouped, params, setting='true')
    assert recorded, 'expected at least one addDirectoryItem call'
    url, listitem, is_folder = recorded[0]
    assert listitem.label == 'String_30434'
    # No IsPlayable at all: 'true' makes Kodi open the click as playback and
    # tear down the handed-off episode; 'false' breaks the dialog (handle -1).
    assert 'IsPlayable' not in listitem._properties
    assert 'ResumeTime' not in listitem._properties
    assert is_folder is False


def test_setting_on_injects_season_row():
    grouped = _grouped_series({1: {1: _versions('a')}})
    params = {'series': 'show', 'season': '1', 'what': 'q'}
    recorded = _run_browse_season(grouped, params, setting='true')
    assert recorded, 'expected at least one addDirectoryItem call'
    url, listitem, is_folder = recorded[0]
    assert listitem.label == 'String_30435'
    # No IsPlayable at all: 'true' makes Kodi open the click as playback and
    # tear down the handed-off episode; 'false' breaks the dialog (handle -1).
    assert 'IsPlayable' not in listitem._properties
    assert 'ResumeTime' not in listitem._properties
    assert is_folder is False


def test_no_episodes_hides_row():
    grouped = _grouped_series({}, total_episodes=0)
    params = {'series': 'show', 'what': 'q'}
    recorded = _run_browse_series(grouped, params, setting='true')
    labels = [li.label for _, li, _ in recorded]
    assert 'String_30434' not in labels

    grouped_season = {'series': {'show': {
        'display_name': 'Show',
        'seasons': {1: {}},
        'total_episodes': 0,
    }}}
    params_season = {'series': 'show', 'season': '1', 'what': 'q'}
    recorded_season = _run_browse_season(grouped_season, params_season, setting='true')
    labels_season = [li.label for _, li, _ in recorded_season]
    assert 'String_30435' not in labels_season


# ---------------------------------------------------------------------------
# 8: Play path
# ---------------------------------------------------------------------------

def test_play_choice_calls_resolve_and_play():
    versions = _versions('id1', 'ep1.mkv')
    grouped = _grouped_series({1: {1: versions}})
    params = {'series': 'show', 'what': 'q'}
    rand, dialog, resolve_mock, popinfo_mock, resolved_mock = _run_dialog(
        grouped, params, rand_script=[(1, 1)], selections=[0])

    resolve_mock.assert_called_once()
    args, kwargs = resolve_mock.call_args
    # _play_via_handoff takes the version dict; the per-episode state/resume
    # bookkeeping now belongs to the `play` action it hands off to.
    assert args[0]['ident'] == versions[0]['ident']
    assert args[0]['name'] == versions[0]['name']
    resolved_mock.assert_not_called()


# ---------------------------------------------------------------------------
# 9-11: Reroll / exhaustion / start-over rows
# ---------------------------------------------------------------------------

def test_reroll_avoids_repeat_until_exhausted():
    seasons = {1: {1: _versions('a'), 2: _versions('b'), 3: _versions('c')}}
    grouped = _grouped_series(seasons)
    params = {'series': 'show', 'what': 'q'}

    # 3 distinct picks, then pool exhausted on the 4th draw attempt (no key
    # left, so random.choice is not invoked a 4th time).
    rand_script = [(1, 1), (1, 2), (1, 3)]
    # Reroll after 1st and 2nd dialogs; on the 3rd dialog reroll once more
    # to trigger the (now exhausted) 4th draw attempt; the 4th dialog shows
    # Start over instead of Reroll — select -1 to terminate.
    selections = [1, 1, 1, -1]

    rand, dialog, resolve_mock, popinfo_mock, resolved_mock = _run_dialog(
        grouped, params, rand_script=rand_script, selections=selections)

    # All picks distinct: the recorded `remaining` pools shrink each time.
    assert len(rand.calls) == 3
    sizes = [len(c) for c in rand.calls]
    assert sizes == [3, 2, 1]

    # Last dialog shown (after exhaustion) offers Start over, not Reroll.
    last_shown = dialog.shown[-1]
    labels = [li.label for li in last_shown]
    assert 'String_30442' in labels
    assert 'String_30437' not in labels

    popinfo_mock.assert_not_called()


def test_single_episode_no_reroll_offered():
    grouped = _grouped_series({1: {1: _versions('a')}})
    params = {'series': 'show', 'what': 'q'}
    rand, dialog, resolve_mock, popinfo_mock, resolved_mock = _run_dialog(
        grouped, params, rand_script=[(1, 1)], selections=[-1])

    shown = dialog.shown[0]
    assert len(shown) == 2
    labels = [li.label for li in shown]
    assert labels[1] == 'String_30438'
    assert 'String_30437' not in labels
    assert 'String_30442' not in labels


def test_pool_gt1_exhausted_shows_start_over_row():
    seasons = {1: {1: _versions('a'), 2: _versions('b')}}
    grouped = _grouped_series(seasons)
    params = {'series': 'show', 'what': 'q'}

    rand_script = [(1, 1), (1, 2)]
    # First dialog: reroll -> shows 2nd pick (still 'reroll' state, since the
    # 2nd key was found). Reroll again to trigger the exhausted 3rd draw
    # attempt, whose dialog shows Start over -> cancel.
    selections = [1, 1, -1]

    rand, dialog, resolve_mock, popinfo_mock, resolved_mock = _run_dialog(
        grouped, params, rand_script=rand_script, selections=selections)

    last_shown = dialog.shown[-1]
    assert len(last_shown) == 3
    assert last_shown[1].label == 'String_30442'
    assert last_shown[1].label2 == 'String_30441'


# ---------------------------------------------------------------------------
# 12: Start over clears exclusion except current
# ---------------------------------------------------------------------------

def test_start_over_clears_exclusion_except_current():
    seasons = {1: {1: _versions('a'), 2: _versions('b'), 3: _versions('c')}}
    grouped = _grouped_series(seasons)
    params = {'series': 'show', 'what': 'q'}

    # Draws 1-3 consume all 3 keys (each dialog still in 'reroll' state,
    # since a key was found each time). The 4th draw attempt finds
    # `remaining` empty -> `_pick_random` short-circuits (no random.choice
    # call) and the dialog offers Start over instead of the current pick.
    # Selecting Start over (index 1) clears exclusion down to just the last
    # shown pick and the loop draws again -- that is the 4th random.choice
    # call, landing on (1, 1), which we then cancel out of.
    rand_script = [(1, 1), (1, 2), (1, 3), (1, 1)]
    selections = [1, 1, 1, 1, -1]

    rand, dialog, resolve_mock, popinfo_mock, resolved_mock = _run_dialog(
        grouped, params, rand_script=rand_script, selections=selections)

    # Only 4 random.choice calls total: the exhausted attempt (dialog #4)
    # returns before calling random.choice at all.
    assert len(rand.calls) == 4

    # The draw right after "Start over" was selected (the 4th recorded
    # random.choice call) must exclude only the last shown pick (1, 3),
    # i.e. remaining has exactly 2 entries.
    post_start_over_pool = rand.calls[3]
    assert len(post_start_over_pool) == 2
    assert (1, 3) not in post_start_over_pool

    # Loop continued: a 5th dialog was drawn (not an immediate return).
    assert len(dialog.shown) == 5


# ---------------------------------------------------------------------------
# 13: Cancel path
# ---------------------------------------------------------------------------

def test_cancel_resolves_false():
    grouped = _grouped_series({1: {1: _versions('a')}})
    params = {'series': 'show', 'what': 'q'}
    rand, dialog, resolve_mock, popinfo_mock, resolved_mock = _run_dialog(
        grouped, params, rand_script=[(1, 1)], selections=[-1])

    resolved_mock.assert_called_once()
    args = resolved_mock.call_args[0]
    assert args[0] == series_ui._handle
    assert args[1] is False
    resolve_mock.assert_not_called()


# ---------------------------------------------------------------------------
# 14-16: Early-exit guards
# ---------------------------------------------------------------------------

def test_malformed_season_param_shows_generic_error():
    params = {'series': 'show', 'season': 'abc', 'what': 'q'}
    rand, dialog, resolve_mock, popinfo_mock, resolved_mock = _run_dialog(
        {}, params, rand_script=[], selections=[])

    popinfo_mock.assert_called_once()
    assert popinfo_mock.call_args[0][0] == 'String_30107'
    resolved_mock.assert_called_once()
    assert resolved_mock.call_args[0][1] is False
    assert dialog.shown == []


def test_missing_series_param_shows_generic_error():
    params = {'what': 'q'}
    rand, dialog, resolve_mock, popinfo_mock, resolved_mock = _run_dialog(
        {}, params, rand_script=[], selections=[])

    popinfo_mock.assert_called_once()
    assert popinfo_mock.call_args[0][0] == 'String_30107'
    resolved_mock.assert_called_once()
    assert resolved_mock.call_args[0][1] is False
    assert dialog.shown == []


def test_no_episodes_at_entry_resolves_false():
    grouped = _grouped_series({1: {1: []}}, total_episodes=0)
    params = {'series': 'show', 'what': 'q'}
    rand, dialog, resolve_mock, popinfo_mock, resolved_mock = _run_dialog(
        grouped, params, rand_script=[], selections=[])

    popinfo_mock.assert_called_once()
    assert popinfo_mock.call_args[0][0] == 'String_30440'
    resolved_mock.assert_called_once()
    assert resolved_mock.call_args[0][1] is False
    assert dialog.shown == []


# ---------------------------------------------------------------------------
# 17: Infinite-loop backstop
# ---------------------------------------------------------------------------

def test_all_versions_empty_at_dialog_time_degrades_to_no_episodes():
    """_flatten_episode_keys claims keys exist, but by the time the loop
    dereferences series_data['seasons'][s][e] every version list is empty
    (stale dict). The handler must degrade to the no-episodes error path
    instead of looping forever trying to find a displayable pick.
    """
    seasons = {1: {1: [], 2: []}}
    grouped = _grouped_series(seasons, total_episodes=0)
    params = {'series': 'show', 'what': 'q'}

    class _CappedRandom:
        def __init__(self):
            self.calls = 0

        def choice(self, seq):
            self.calls += 1
            if self.calls > 50:
                raise AssertionError(
                    'random.choice invoked >50 times — infinite loop regression')
            return seq[0]

    rand = _CappedRandom()
    dialog_select = MagicMock()
    xbmcgui_mod = sys.modules['xbmcgui']
    xbmcplugin_mod = sys.modules['xbmcplugin']

    fake_keys = [(1, 1), (1, 2)]

    with patch.object(series_ui, 'revalidate', return_value='tok'), \
         patch.object(series_ui, 'get_or_fetch_grouped', return_value=('ck', grouped)), \
         patch.object(series_ui, '_flatten_episode_keys', return_value=fake_keys), \
         patch.object(series_ui, 'random', rand), \
         patch.object(series_ui, '_play_via_handoff') as resolve_mock, \
         patch.object(series_ui, 'popinfo') as popinfo_mock, \
         patch.object(xbmcgui_mod, 'Dialog') as dialog_cls, \
         patch.object(xbmcplugin_mod, 'setResolvedUrl') as resolved_mock:
        dialog_cls.return_value.select = dialog_select
        series_ui.show_random_episode_dialog(params)

    dialog_select.assert_not_called()
    resolve_mock.assert_not_called()
    # Every empty-versions pick along the way pops a 30440 warning (one per
    # stale key encountered), plus the final exhaustion warning -- the
    # important invariant is that it terminates and every warning fired is
    # the same "no episodes" string, never something else.
    assert popinfo_mock.call_count >= 1
    for call in popinfo_mock.call_args_list:
        assert call[0][0] == 'String_30440'
    resolved_mock.assert_called_once()
    assert resolved_mock.call_args[0][1] is False


# ---------------------------------------------------------------------------
# 18: Every exit path resolves exactly once (handler-level)
# ---------------------------------------------------------------------------

def test_every_exit_path_resolves_exactly_once():
    # Cancel path
    grouped_cancel = _grouped_series({1: {1: _versions('a')}})
    _, _, resolve_mock, _, resolved_mock = _run_dialog(
        grouped_cancel, {'series': 'show', 'what': 'q'},
        rand_script=[(1, 1)], selections=[-1])
    assert resolved_mock.call_count == 1
    assert resolved_mock.call_args[0][1] is False

    # Malformed param
    _, _, resolve_mock, _, resolved_mock = _run_dialog(
        {}, {'series': 'show', 'season': 'abc', 'what': 'q'},
        rand_script=[], selections=[])
    assert resolved_mock.call_count == 1
    assert resolved_mock.call_args[0][1] is False

    # Missing series
    _, _, resolve_mock, _, resolved_mock = _run_dialog(
        {}, {'what': 'q'}, rand_script=[], selections=[])
    assert resolved_mock.call_count == 1
    assert resolved_mock.call_args[0][1] is False

    # No episodes at entry
    grouped_empty = _grouped_series({1: {1: []}}, total_episodes=0)
    _, _, resolve_mock, _, resolved_mock = _run_dialog(
        grouped_empty, {'series': 'show', 'what': 'q'},
        rand_script=[], selections=[])
    assert resolved_mock.call_count == 1
    assert resolved_mock.call_args[0][1] is False

    # Play path: handler-level setResolvedUrl NOT called (delegated).
    versions = _versions('id1', 'ep1.mkv')
    grouped_play = _grouped_series({1: {1: versions}})
    _, _, resolve_mock, _, resolved_mock = _run_dialog(
        grouped_play, {'series': 'show', 'what': 'q'},
        rand_script=[(1, 1)], selections=[0])
    assert resolved_mock.call_count == 0
    resolve_mock.assert_called_once()


# ---------------------------------------------------------------------------
# 19: Grouped-data fetched once across reroll loop; enrichment cost is
# exactly one getinfo per pick (not zero, not per-version).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 20: main.py _RESOLVE_ACTIONS membership (hung-spinner risk item)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 21: excluded.add(picked) ordering — must happen before the empty-versions
# `continue`, not after it
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 22+: Version-picker row (_build_dialog_rows 5-arg signature) and the
# pick_version dispatch branch in show_random_episode_dialog.
# ---------------------------------------------------------------------------

def _multi_versions(*idents_and_sizes):
    """Build a list of version dicts with distinct idents/names/sizes.

    idents_and_sizes: sequence of (ident, size) tuples. First entry is meant
    to be treated as "best" by callers (versions[0] pre-sort).
    """
    out = []
    for ident, size in idents_and_sizes:
        out.append({'ident': ident, 'name': '{0}.mkv'.format(ident), 'size': size})
    return out


def test_pick_version_row_present_with_count():
    best = {'ident': 'a', 'name': 'a.mkv'}
    # Patch getLocalizedString so the count is visible in the rendered label
    # without relying on the mock's literal '.format()' no-op (see module
    # docstring context: MockAddon.getLocalizedString ignores .format args
    # because 'String_30443' has no '{0}' placeholder).
    def fake_get_string(i):
        return '{0}|{{0}}'.format(i)

    with patch.object(series_ui._addon, 'getLocalizedString', fake_get_string):
        listitems, actions = series_ui._build_dialog_rows(
            best, 1, 1, 'reroll', version_count=3)

    assert actions == ['play', 'pick_version', 'reroll', 'cancel']
    assert len(listitems) == 4
    assert listitems[1].label == '30443|3'


def test_pick_version_row_omitted_for_single_version():
    best = {'ident': 'a', 'name': 'a.mkv'}
    listitems, actions = series_ui._build_dialog_rows(
        best, 1, 1, 'reroll', version_count=1)

    assert actions == ['play', 'reroll', 'cancel']
    assert 'pick_version' not in actions
    assert len(listitems) == 3


def test_actions_map_all_pool_states():
    best = {'ident': 'a', 'name': 'a.mkv'}
    expected = {
        ('reroll', 1): ['play', 'reroll', 'cancel'],
        ('reroll', 3): ['play', 'pick_version', 'reroll', 'cancel'],
        ('start_over', 1): ['play', 'start_over', 'cancel'],
        ('start_over', 3): ['play', 'pick_version', 'start_over', 'cancel'],
        ('none', 1): ['play', 'cancel'],
        ('none', 3): ['play', 'pick_version', 'cancel'],
    }
    for (pool_state, version_count), expected_actions in expected.items():
        _, actions = series_ui._build_dialog_rows(
            best, 1, 1, pool_state, version_count=version_count)
        assert actions == expected_actions, (
            'pool_state={0} version_count={1}'.format(pool_state, version_count))


def _run_dialog_multi(grouped, params, rand_script=None, selections=None):
    """Like _run_dialog, but also patches enrich_file_metadata to a no-op
    (records calls) so version-picker tests don't hit the API seam.
    """
    rand = _ScriptedRandom(rand_script or [])
    dialog = _ScriptedDialog(selections if selections is not None else [-1])
    xbmcgui_mod = sys.modules['xbmcgui']
    xbmcplugin_mod = sys.modules['xbmcplugin']

    enrich_mock = MagicMock(return_value=False)

    with patch.object(series_ui, 'revalidate', return_value='tok'), \
         patch.object(series_ui, 'get_or_fetch_grouped', return_value=('ck', grouped)), \
         patch.object(series_ui, 'random', rand), \
         patch.object(series_ui, '_play_via_handoff') as resolve_mock, \
         patch.object(series_ui, 'popinfo') as popinfo_mock, \
         patch.object(series_ui, 'enrich_file_metadata', enrich_mock), \
         patch.object(xbmcgui_mod, 'Dialog', lambda: dialog), \
         patch.object(xbmcplugin_mod, 'setResolvedUrl') as resolved_mock:
        series_ui.show_random_episode_dialog(params)

    return rand, dialog, resolve_mock, popinfo_mock, resolved_mock, enrich_mock


def test_pick_version_plays_chosen_non_best_version():
    """The user-reported gap: picking a NON-best version in the picker must
    play that version, not silently fall back to versions[0].
    """
    versions = _multi_versions(('best', 300), ('mid', 200), ('small', 100))
    seasons = {1: {1: versions}}
    grouped = _grouped_series(seasons)
    params = {'series': 'show', 'what': 'q'}

    # Dialog 1 (random-episode dialog): rows are
    # [play, pick_version, cancel] (single episode -> pool_state 'none').
    # Select index 1 -> pick_version.
    # Dialog 2 (version picker): _prepare_episode_versions sorts by size
    # desc, so order is best(300), mid(200), small(100) -> indices 0,1,2.
    # Select index 1 -> 'mid', a NON-best version.
    rand, dialog, resolve_mock, popinfo_mock, resolved_mock, enrich_mock = _run_dialog_multi(
        grouped, params, rand_script=[(1, 1)], selections=[1, 1])

    resolve_mock.assert_called_once()
    args, kwargs = resolve_mock.call_args
    assert args[0]['ident'] == 'mid'
    assert args[0]['name'] == 'mid.mkv'
    assert args[0]['ident'] != versions[0]['ident']
    resolved_mock.assert_not_called()


def test_pick_version_back_out_returns_to_random_dialog():
    versions = _multi_versions(('best', 300), ('mid', 200), ('small', 100))
    seasons = {1: {1: versions}}
    grouped = _grouped_series(seasons)
    params = {'series': 'show', 'what': 'q'}

    # Dialog 1: select pick_version (index 1).
    # Dialog 2 (picker): back out (-1).
    # Dialog 1 again (redraw, same episode): cancel (index 2, since rows are
    # [play, pick_version, cancel] for a single-episode 'none' pool_state).
    rand, dialog, resolve_mock, popinfo_mock, resolved_mock, enrich_mock = _run_dialog_multi(
        grouped, params, rand_script=[(1, 1)], selections=[1, -1, 2])

    resolve_mock.assert_not_called()
    resolved_mock.assert_called_once()
    assert resolved_mock.call_args[0][1] is False

    # Random dialog rendered twice (dialog 2, the picker, is a separate
    # Dialog().select call using the SAME _ScriptedDialog instance, so
    # dialog.shown accumulates all three renders in order: random, picker,
    # random-redraw). Identify the two "random dialog" renders by the Play
    # row's label and assert they're identical (same episode both times).
    random_dialog_renders = [shown for shown in dialog.shown if shown[0].label.startswith('S01E01')]
    assert len(random_dialog_renders) == 2
    assert random_dialog_renders[0][0].label == random_dialog_renders[1][0].label


def test_pick_version_back_out_then_play_resolves_originally_shown_version():
    """Pins the defensive `list(shown_versions)` shallow copy at the
    pick_version call site: `_prepare_episode_versions(list(shown_versions),
    token)` ranks/enriches a COPY, so the picker can never reorder the outer
    loop's `shown_versions` in place. Backing out of the picker must
    therefore redraw the SAME episode with the SAME Play-row version as
    before the picker was opened.

    Dropping the `list(...)` copy currently survives mutation testing
    because `_rank_versions` happens to be idempotent (ranking an
    already-ranked list is a no-op reorder) — this test pins the intent so
    the copy cannot be silently dropped, independent of that idempotence.

    Fixture has 3 versions with a non-trivial ranked order (size-first:
    best=300 > mid=200 > small=100), so 'best' is the pre-picker Play row.
    """
    versions = _multi_versions(('best', 300), ('mid', 200), ('small', 100))
    seasons = {1: {1: versions}}
    grouped = _grouped_series(seasons)
    params = {'series': 'show', 'what': 'q'}

    # Dialog 1 (render #1): select pick_version (index 1).
    # Dialog 2 (picker): back out (-1).
    # Dialog 1 (redraw, render #2): select play (index 0).
    rand, dialog, resolve_mock, popinfo_mock, resolved_mock, enrich_mock = _run_dialog_multi(
        grouped, params, rand_script=[(1, 1)], selections=[1, -1, 0])

    random_dialog_renders = [
        shown for shown in dialog.shown if shown[0].label.startswith('S01E01')]
    assert len(random_dialog_renders) == 2

    # The Play row's label is byte-for-byte identical before and after the
    # picker back-out — same episode, same version shown.
    pre_picker_label = random_dialog_renders[0][0].label
    post_backout_label = random_dialog_renders[1][0].label
    assert pre_picker_label == post_backout_label
    assert pre_picker_label.endswith('best.mkv')

    # Playing from the redrawn row resolves the originally-shown best
    # version's ident/name, not something reordered by the picker's ranking
    # pass touching the outer loop's list in place.
    resolve_mock.assert_called_once()
    args, kwargs = resolve_mock.call_args
    assert args[0]['ident'] == 'best'
    assert args[0]['ident'] == versions[0]['ident']
    assert args[0]['name'] == 'best.mkv'
    resolved_mock.assert_not_called()


def test_one_enrichment_per_pick_during_reroll():
    """Successor to test_pick_version_no_enrichment_during_reroll.

    The old contract (rerolling never enriches) was deliberately superseded:
    each pick now enriches its ONE displayed version so the Play row's
    label2 can show real audio/subtitle tracks (see _enrich_displayed_version
    and lib/ui.py's _build_version_metadata). The cost guarantee that
    survives is that enrichment is O(picks), not O(picks * len(versions)) —
    rerolling through a big version pool must not enrich every version in
    every list, only the single best/displayed one per pick.
    """
    seasons = {1: {
        1: _multi_versions(('a1', 300), ('a2', 200)),
        2: _multi_versions(('b1', 300), ('b2', 200)),
        3: _multi_versions(('c1', 300), ('c2', 200)),
    }}
    grouped = _grouped_series(seasons)
    params = {'series': 'show', 'what': 'q'}

    call_count = {'n': 0}

    def _counting_fetch(*a, **k):
        call_count['n'] += 1
        return ('ck', grouped)

    rand = _ScriptedRandom([(1, 1), (1, 2), (1, 3)])
    # Reroll twice (index 2: [play, pick_version, reroll, cancel] while pool
    # > 1), then cancel on the 3rd dialog (index 3). 3 picks total: (1,1),
    # (1,2), (1,3) — the version-picker row is never opened in this phase.
    dialog = _ScriptedDialog([2, 2, 3])
    xbmcgui_mod = sys.modules['xbmcgui']
    xbmcplugin_mod = sys.modules['xbmcplugin']
    enrich_mock = MagicMock(return_value=False)

    with patch.object(series_ui, 'revalidate', return_value='tok'), \
         patch.object(series_ui, 'get_or_fetch_grouped', side_effect=_counting_fetch), \
         patch.object(series_ui, 'random', rand), \
         patch.object(series_ui, 'resolve_and_play'), \
         patch.object(series_ui, 'popinfo'), \
         patch.object(series_ui, 'enrich_file_metadata', enrich_mock), \
         patch.object(xbmcgui_mod, 'Dialog', lambda: dialog), \
         patch.object(xbmcplugin_mod, 'setResolvedUrl'):
        series_ui.show_random_episode_dialog(params)

    assert call_count['n'] == 1

    # NEW contract: exactly one enrichment call PER PICK (3 picks -> 3
    # calls), never once per version in the list (that would be 3 * 2 = 6).
    assert enrich_mock.call_count == 3
    assert enrich_mock.call_count != 3 * 2

    # Each call enriches the displayed (best/largest) version of its pick —
    # 'a1', 'b1', 'c1' — never the runner-up 'a2'/'b2'/'c2'.
    enriched_idents = [call.args[1] for call in enrich_mock.call_args_list]
    assert enriched_idents == ['a1', 'b1', 'c1']


def test_pick_version_uses_deduped_count():
    """The pick_version row's count must reflect the post-dedupe version
    list length (what the picker will actually show), not the raw list.
    """
    from lib.grouping import deduplicate_versions

    raw = [
        {'ident': 'dup', 'name': 'dup.mkv', 'size': 300},
        {'ident': 'dup', 'name': 'dup.mkv', 'size': 300},  # true duplicate (same ident)
        {'ident': 'other', 'name': 'other.mkv', 'size': 200},
    ]
    deduped = deduplicate_versions(raw)
    assert len(deduped) == 2, 'fixture sanity: dedup must collapse the true duplicate'

    seasons = {1: {1: raw}}
    grouped = _grouped_series(seasons)
    params = {'series': 'show', 'what': 'q'}

    def fake_get_string(i):
        return '{0}|{{0}}'.format(i)

    xbmcgui_mod = sys.modules['xbmcgui']
    xbmcplugin_mod = sys.modules['xbmcplugin']
    dialog = _ScriptedDialog([-1])
    rand = _ScriptedRandom([(1, 1)])

    with patch.object(series_ui, 'revalidate', return_value='tok'), \
         patch.object(series_ui, 'get_or_fetch_grouped', return_value=('ck', grouped)), \
         patch.object(series_ui, 'random', rand), \
         patch.object(series_ui, 'resolve_and_play'), \
         patch.object(series_ui, 'popinfo'), \
         patch.object(series_ui._addon, 'getLocalizedString', fake_get_string), \
         patch.object(xbmcgui_mod, 'Dialog', lambda: dialog), \
         patch.object(xbmcplugin_mod, 'setResolvedUrl'):
        series_ui.show_random_episode_dialog(params)

    shown = dialog.shown[0]
    pick_version_label = shown[1].label
    assert pick_version_label == '30443|{0}'.format(len(deduped))


# ---------------------------------------------------------------------------
# 23+: Real-metadata enrichment of the displayed Play row
# (_enrich_displayed_version / _prepare_episode_versions guard)
# ---------------------------------------------------------------------------

def _run_dialog_with_enrich(grouped, params, rand_script=None, selections=None,
                             enrich_fake=None):
    """Like _run_dialog, but installs a caller-supplied `enrich_file_metadata`
    fake (signature: (file_dict, ident, token) -> bool) instead of the
    no-seam default, and also returns the enrich mock/spy for assertions.
    """
    rand = _ScriptedRandom(rand_script or [])
    dialog = _ScriptedDialog(selections if selections is not None else [-1])
    xbmcgui_mod = sys.modules['xbmcgui']
    xbmcplugin_mod = sys.modules['xbmcplugin']

    if enrich_fake is None:
        enrich_fake = MagicMock(return_value=False)

    with patch.object(series_ui, 'revalidate', return_value='tok'), \
         patch.object(series_ui, 'get_or_fetch_grouped', return_value=('ck', grouped)), \
         patch.object(series_ui, 'random', rand), \
         patch.object(series_ui, '_play_via_handoff') as resolve_mock, \
         patch.object(series_ui, 'popinfo') as popinfo_mock, \
         patch.object(series_ui, 'enrich_file_metadata', enrich_fake), \
         patch.object(xbmcgui_mod, 'Dialog', lambda: dialog), \
         patch.object(xbmcplugin_mod, 'setResolvedUrl') as resolved_mock:
        series_ui.show_random_episode_dialog(params)

    return rand, dialog, resolve_mock, popinfo_mock, resolved_mock, enrich_fake


def test_play_row_shows_real_audio_and_subtitle_tracks():
    """The user-reported gap: the Play row's label2 must reflect the real
    audio/subtitle tracks fetched via enrich_file_metadata, not just the
    filename-parsed quality_meta. Also pins that enriched `resolution` wins
    over the filename-parsed `quality_meta['quality']` when they differ —
    proving the real data actually takes priority in _build_version_metadata
    (lib/ui.py:35-39).
    """
    versions = _versions('id1', 'ep1.1080p.mkv')
    versions[0]['quality_meta'] = {'quality': '1080p'}
    grouped = _grouped_series({1: {1: versions}})
    params = {'series': 'show', 'what': 'q'}

    def _fake_enrich(file_dict, ident, token):
        file_dict['file_info'] = {
            'audio': 'cs 5.1',
            'subtitles': 'cs, en',
            'resolution': '2160p',
            'video_codec': 'h264',
        }
        return True

    rand, dialog, resolve_mock, popinfo_mock, resolved_mock, enrich_fake = (
        _run_dialog_with_enrich(
            grouped, params, rand_script=[(1, 1)], selections=[-1],
            enrich_fake=_fake_enrich))

    shown = dialog.shown[0]
    play_row = shown[0]
    assert 'Audio: cs 5.1' in play_row.label2
    assert 'Subs: cs, en' in play_row.label2
    # Enriched resolution ('2160p') beats the filename-parsed quality_meta
    # ('1080p') — real data wins.
    assert '2160p' in play_row.label2
    assert '1080p' not in play_row.label2


def test_enrichment_failure_still_renders_row():
    """A fake that returns False WITHOUT setting file_info (a realistic
    getinfo miss) must not break rendering: the row still shows the
    filename-parsed quality_meta parts, no exception escapes, and the loop
    stays usable for a subsequent reroll + cancel.
    """
    versions = _versions('id1', 'ep1.mkv')
    versions[0]['quality_meta'] = {'quality': '1080p', 'source': 'WEB-DL'}
    seasons = {1: {1: versions, 2: _versions('id2', 'ep2.mkv')}}
    grouped = _grouped_series(seasons)
    params = {'series': 'show', 'what': 'q'}

    def _fake_enrich_miss(file_dict, ident, token):
        return False

    rand, dialog, resolve_mock, popinfo_mock, resolved_mock, enrich_fake = (
        _run_dialog_with_enrich(
            grouped, params, rand_script=[(1, 1), (1, 2)],
            selections=[1, -1], enrich_fake=_fake_enrich_miss))

    first_shown = dialog.shown[0]
    play_row = first_shown[0]
    assert '1080p' in play_row.label2
    assert 'WEB-DL' in play_row.label2

    # Loop still usable: a reroll happened (2 dialogs shown) and cancel
    # resolved exactly once.
    assert len(dialog.shown) == 2
    resolved_mock.assert_called_once()
    assert resolved_mock.call_args[0][1] is False
    resolve_mock.assert_not_called()


def test_enrichment_exception_does_not_break_loop():
    """A fake that RAISES must be absorbed by _enrich_displayed_version's
    own try/except — the dialog still renders and setResolvedUrl still
    fires exactly once on cancel.
    """
    versions = _versions('id1', 'ep1.mkv')
    grouped = _grouped_series({1: {1: versions}})
    params = {'series': 'show', 'what': 'q'}

    def _fake_enrich_raises(file_dict, ident, token):
        raise RuntimeError('boom')

    rand, dialog, resolve_mock, popinfo_mock, resolved_mock, enrich_fake = (
        _run_dialog_with_enrich(
            grouped, params, rand_script=[(1, 1)], selections=[-1],
            enrich_fake=_fake_enrich_raises))

    assert len(dialog.shown) == 1
    resolved_mock.assert_called_once()
    assert resolved_mock.call_args[0][1] is False
    resolve_mock.assert_not_called()


def test_no_duplicate_enrichment_on_picker_back_out():
    """Multi-version episode: open pick_version, back out, then cancel. The
    Play row is rendered twice (initial + redraw after back-out), but the
    BEST version's ident must only be enriched ONCE in total.

    Note: `_prepare_episode_versions` will also enrich the OTHER top-5
    versions when the picker opens (expected, separate cost) — this test
    counts calls PER IDENT so that expected picker-side enrichment of the
    non-best versions doesn't mask a regression that re-enriches the best
    version on every redraw.
    """
    versions = _multi_versions(('best', 300), ('mid', 200), ('small', 100))
    seasons = {1: {1: versions}}
    grouped = _grouped_series(seasons)
    params = {'series': 'show', 'what': 'q'}

    calls_by_ident = {}

    def _counting_enrich(file_dict, ident, token):
        calls_by_ident[ident] = calls_by_ident.get(ident, 0) + 1
        # Realistic success: sets file_info, which is what lets the
        # 'file_info' in file_dict guards (both _enrich_displayed_version's
        # own guard and _prepare_episode_versions' top-5 loop guard) skip a
        # version that was already enriched by an earlier call — the same
        # dict object is shared between `shown_best` and the picker's
        # `ordered` list (shallow copy via list(shown_versions)).
        file_dict['file_info'] = {'audio': 'cs 5.1'}
        return True

    # Dialog 1: select pick_version (index 1; single episode -> pool_state
    # 'none' -> rows [play, pick_version, cancel]).
    # Dialog 2 (picker): back out (-1).
    # Dialog 1 (redraw): cancel (index 2).
    rand, dialog, resolve_mock, popinfo_mock, resolved_mock, enrich_fake = (
        _run_dialog_with_enrich(
            grouped, params, rand_script=[(1, 1)], selections=[1, -1, 2],
            enrich_fake=_counting_enrich))

    assert calls_by_ident.get('best', 0) == 1
    resolved_mock.assert_called_once()
    assert resolved_mock.call_args[0][1] is False


def test_already_enriched_version_is_skipped():
    """_enrich_displayed_version must skip a version that already carries
    file_info (no redundant getinfo), and must not raise on a falsy
    file_dict (the guard used for defensive callers).
    """
    enrich_mock = MagicMock(return_value=True)
    with patch.object(series_ui, 'enrich_file_metadata', enrich_mock):
        already_enriched = {'ident': 'x', 'name': 'x.mkv', 'file_info': {'audio': 'en'}}
        series_ui._enrich_displayed_version(already_enriched, 'tok')
        enrich_mock.assert_not_called()

        # Falsy dict guard: must not raise.
        series_ui._enrich_displayed_version(None, 'tok')
        series_ui._enrich_displayed_version({}, 'tok')
        enrich_mock.assert_not_called()


def test_best_version_unchanged_by_enrichment():
    """Anti-creep guard: enrichment must never trigger re-ranking of
    versions by language (or any other enriched field). Language-based
    ranking and filtering were explicitly considered and rejected for this
    feature — this test exists to fail loudly if someone adds them.

    Fixture: versions[0] ('best') is 'en', versions[1] ('mid') is 'cs'. A
    naive "prefer cs audio" re-rank would promote 'mid' over 'best'. The
    fake enrichment sets file_info that, if used for ranking, would make
    'mid' look like the superior match — but the dedupe+sort winner
    (`versions[0]`, chosen purely by file size before enrichment ever runs)
    must still be the one shown and played.
    """
    versions = _multi_versions(('best', 300), ('mid', 200))
    versions[0]['language'] = 'en'
    versions[1]['language'] = 'cs'
    seasons = {1: {1: versions}}
    grouped = _grouped_series(seasons)
    params = {'series': 'show', 'what': 'q'}

    def _fake_enrich(file_dict, ident, token):
        # Make the non-best version look like the "better" match by audio
        # language — if ranking ever keyed off this, 'mid' would win.
        if ident == 'mid':
            file_dict['file_info'] = {'audio': 'cs 5.1', 'resolution': '2160p'}
        else:
            file_dict['file_info'] = {'audio': 'en 2.0', 'resolution': '720p'}
        return True

    rand, dialog, resolve_mock, popinfo_mock, resolved_mock, enrich_fake = (
        _run_dialog_with_enrich(
            grouped, params, rand_script=[(1, 1)], selections=[0],
            enrich_fake=_fake_enrich))

    shown = dialog.shown[0]
    play_row = shown[0]
    assert play_row.label.endswith('best.mkv')

    resolve_mock.assert_called_once()
    args = resolve_mock.call_args[0]
    assert args[0]['ident'] == 'best'
    assert args[0]['ident'] == versions[0]['ident']


# ---------------------------------------------------------------------------
# 32: Enrichment call-site placement — outer pick branch, not the inner
# redraw loop. Independent of the 'file_info' guard inside
# _enrich_displayed_version.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 33+: _rank_versions — SIZE-FIRST primary key, quality_score tiebreak. A
# version with no parseable size falls back to 0 via `_safe_size`, so it
# ranks last even if its quality score is higher — that is intended, not a
# defect (user-confirmed contract, see test_size_is_the_primary_key_
# unknown_size_ranks_last below).
#
# The genuine defect this section still guards against (test
# test_play_row_ranks_instead_of_taking_api_order below): the random
# dialog's Play row must RANK the versions rather than taking
# deduplicate_versions' preserved API order, which would resolve an
# arbitrary (not necessarily best) version.
# ---------------------------------------------------------------------------

def test_play_row_ranks_instead_of_taking_api_order():
    """Defect A regression: the Play row must rank the versions rather than
    blindly taking deduplicate_versions' API order (which preserves input
    order). The biggest file is second in the list, so a Play row that used
    versions[0] would resolve the small one.
    """
    versions = [
        {'ident': 'small_first', 'name': 'Show.S01E01.1080p.WEB-DL.x264.mkv', 'size': '100'},
        {'ident': 'big_second', 'name': 'Show.S01E01.720p.x264.mkv', 'size': '9000'},
    ]
    seasons = {1: {1: versions}}
    grouped = _grouped_series(seasons)
    params = {'series': 'show', 'what': 'q'}

    rand, dialog, resolve_mock, popinfo_mock, resolved_mock = _run_dialog(
        grouped, params, rand_script=[(1, 1)], selections=[0])

    resolve_mock.assert_called_once()
    args, kwargs = resolve_mock.call_args
    assert args[0]['ident'] == 'big_second'
    assert args[0]['ident'] != versions[0]['ident']


def test_size_is_the_primary_key_unknown_size_ranks_last():
    """Size-first is the intended pick-variant order: a version with a known
    size outranks one whose size is missing, even when the sizeless file
    scores higher on quality (_safe_size falls back to 0 for it).

    This is the deliberate contract, not a defect — the user confirmed
    largest-file-first is the ordering they want in the version lists.
    """
    x = {'ident': 'x', 'name': 'Gachiakuta.S01E24.1080p.WEB-DL.H264.mkv'}
    y = {'ident': 'y', 'name': 'Gachiakuta.S01E24.1080p.x264.mkv', 'size': '1535000000'}

    ranked = series_ui._rank_versions([x, y])
    assert ranked[0]['ident'] == 'y'

    # End-to-end: drive the random dialog and select Play, assert the Play
    # row resolved to the sized version.
    seasons = {1: {1: [x, y]}}
    grouped = _grouped_series(seasons)
    params = {'series': 'show', 'what': 'q'}

    rand, dialog, resolve_mock, popinfo_mock, resolved_mock = _run_dialog(
        grouped, params, rand_script=[(1, 1)], selections=[0])

    resolve_mock.assert_called_once()
    args, kwargs = resolve_mock.call_args
    assert args[0]['ident'] == 'y'


def test_rank_versions_no_sizes_falls_back_to_quality():
    versions = [
        {'ident': 'a', 'name': 'Show.S01E01.720p.x264.mkv'},
        {'ident': 'b', 'name': 'Show.S01E01.1080p.WEB-DL.x264.mkv'},
    ]
    ranked = series_ui._rank_versions(list(versions))
    assert [v['ident'] for v in ranked] == ['b', 'a']


def test_rank_versions_all_sizes_present():
    """Size wins even when it directly contradicts quality order."""
    versions = [
        {'ident': 'small_hq', 'name': 'Show.S01E01.1080p.WEB-DL.x264.mkv', 'size': '100'},
        {'ident': 'big_lq', 'name': 'Show.S01E01.720p.x264.mkv', 'size': '9000'},
    ]
    ranked = series_ui._rank_versions(list(versions))
    assert [v['ident'] for v in ranked] == ['big_lq', 'small_hq']


def test_rank_versions_equal_size_quality_breaks_tie():
    """Quality score is the tiebreak when sizes are identical."""
    versions = [
        {'ident': 'lq', 'name': 'Show.S01E01.720p.x264.mkv', 'size': '500'},
        {'ident': 'hq', 'name': 'Show.S01E01.1080p.WEB-DL.x264.mkv', 'size': '500'},
    ]
    ranked = series_ui._rank_versions(list(versions))
    assert [v['ident'] for v in ranked] == ['hq', 'lq']


def test_enrichment_budget_spent_on_top_ranked_versions():
    """Pins that `_prepare_episode_versions` ranks BEFORE it enriches.

    The enrichment budget (TOP_FILES_TO_ENRICH = 5) must land on the 5
    genuinely-best versions by quality score, not on whichever 5 versions
    happen to appear first in the (already-deduplicated) input list. If
    someone swaps the order of the two steps — enrich the first 5 entries of
    `versions`, THEN call `_rank_versions` — the FINAL returned order is
    unchanged (the list still ends up sorted by quality either way), so
    every existing order-based assertion in this file stays green. Only the
    SET of enriched idents differs, and that is exactly what this test
    checks.

    Fixture: 12 versions whose filenames give 12 strictly distinct
    `parse_quality_metadata` scores (confirmed via a throwaway snippet:
    'X.S01E01.480p.mkv'=40, 'X.S01E01.720p.mkv'=60,
    'X.S01E01.720p.AAC.mkv'=61, 'X.S01E01.720p.AC3.mkv'=62,
    'X.S01E01.720p.WEB-DL.mkv'=70, 'X.S01E01.1080p.mkv'=80,
    'X.S01E01.1080p.AAC.mkv'=81, 'X.S01E01.1080p.WEB-DL.mkv'=90,
    'X.S01E01.1080p.WEB-DL.x265.mkv'=95, 'X.S01E01.2160p.mkv'=100,
    'X.S01E01.2160p.x265.mkv'=105, 'X.S01E01.2160p.BluRay.x265.mkv'=120).
    The input/API order is deliberately the OPPOSITE of quality order: the
    7 lowest-scoring entries ('low1'..'low7') come first, then the 5
    highest-scoring entries ('top5'..'top1', ascending) come last. So "the
    first 5 in input order" (all 'low*') and "the top 5 by rank" (all
    'top*') are completely disjoint sets — there is no overlap to hide a
    regression.

    With correct rank-then-enrich ordering, only 'top1'..'top5' get
    enriched. Under the swapped mutation (enrich-then-rank), the first 5
    input-order entries ('low1'..'low5') get enriched instead — this test
    fails under that mutation even though `_prepare_episode_versions`'
    returned list order is identical in both cases.
    """
    versions = [
        {'ident': 'low1', 'name': 'X.S01E01.480p.mkv'},
        {'ident': 'low2', 'name': 'X.S01E01.720p.mkv'},
        {'ident': 'low3', 'name': 'X.S01E01.720p.AAC.mkv'},
        {'ident': 'low4', 'name': 'X.S01E01.720p.AC3.mkv'},
        {'ident': 'low5', 'name': 'X.S01E01.720p.WEB-DL.mkv'},
        {'ident': 'low6', 'name': 'X.S01E01.1080p.mkv'},
        {'ident': 'low7', 'name': 'X.S01E01.1080p.AAC.mkv'},
        {'ident': 'top5', 'name': 'X.S01E01.1080p.WEB-DL.mkv'},
        {'ident': 'top4', 'name': 'X.S01E01.1080p.WEB-DL.x265.mkv'},
        {'ident': 'top3', 'name': 'X.S01E01.2160p.mkv'},
        {'ident': 'top2', 'name': 'X.S01E01.2160p.x265.mkv'},
        {'ident': 'top1', 'name': 'X.S01E01.2160p.BluRay.x265.mkv'},
    ]

    enrich_spy = MagicMock(return_value=False)
    with patch.object(series_ui, 'enrich_file_metadata', enrich_spy):
        series_ui._prepare_episode_versions(versions, 'tok')

    enriched_idents = {call.args[1] for call in enrich_spy.call_args_list}

    assert len(enrich_spy.call_args_list) == 5
    assert enriched_idents == {'top1', 'top2', 'top3', 'top4', 'top5'}
    assert not enriched_idents & {'low1', 'low2', 'low3', 'low4', 'low5'}


def test_playback_hands_off_to_per_episode_play_url_not_picker_url():
    """Regression (user-reported twice): Kodi writes a type=1 resume bookmark
    AT STOP TIME against the URL that started playback. When the picker
    resolved the stream itself, that URL was the picker's own
    (?action=random_episode&series=...), so every episode played through it
    shared ONE bookmark and re-entering the picker offered "Continue
    watching" — verified in MyVideos131.db as 454s/1277s against
    ?action=random_episode&series=south+park.

    Setting ResumeTime/playcount on the picker ListItem does NOT fix this
    (those only affect how the row is drawn, not what the player persists),
    which is why the first attempt failed. The picker must instead hand off
    to ?action=play&ident=...&name=... so Kodi attributes playback — and the
    bookmark — to the episode.
    """
    import xbmc as _xbmc
    versions = _versions('id1', 'ep1.mkv')
    grouped = _grouped_series({1: {1: versions}})

    builtins = []
    xbmcplugin_mod = sys.modules['xbmcplugin']
    xbmcgui_mod = sys.modules['xbmcgui']
    dialog = _ScriptedDialog([0])
    rand = _ScriptedRandom([(1, 1)])

    with patch.object(series_ui, 'revalidate', return_value='tok'), \
         patch.object(series_ui, 'get_or_fetch_grouped', return_value=('ck', grouped)), \
         patch.object(series_ui, 'random', rand), \
         patch.object(series_ui, 'resolve_and_play') as direct_play, \
         patch.object(series_ui, 'popinfo'), \
         patch.object(_xbmc, 'executebuiltin', lambda c: builtins.append(c)), \
         patch.object(xbmcgui_mod, 'Dialog', lambda: dialog), \
         patch.object(xbmcplugin_mod, 'setResolvedUrl') as resolved:
        series_ui.show_random_episode_dialog({'series': 'show', 'what': 'q'})

    # The picker must NOT resolve the stream against its own URL.
    direct_play.assert_not_called()
    # It must NOT resolve its own handle as failed: PlayMedia starts real
    # playback, and a failed resolve in the same playlist makes Kodi tear it
    # down again ("Playlist Player: skipping unplayable item" in kodi.log,
    # measured — the episode opened then immediately stopped).
    resolved.assert_not_called()
    assert len(builtins) == 1, builtins
    cmd = builtins[0]
    assert cmd.startswith('PlayMedia('), cmd
    assert 'action=play' in cmd, cmd
    assert 'ident=id1' in cmd, cmd
    # And crucially: the picker's own action must not be the playing URL.
    assert 'random_episode' not in cmd, cmd
    # The handoff URL MUST also carry series/season/episode. Without them,
    # play() -> _build_state_key -> state_key_for cannot emit an
    # "ep:<series>|S..E.." key and silently falls back to "file:{ident}"
    # (lib/state.py:178), which bypasses lib/keys.py dual-name normalization
    # so watched/resume stop following the episode across re-groupings or a
    # different version of it. This assertion is the one that was MISSING
    # when that regression shipped green — asserting action+ident alone
    # cannot distinguish a correct handoff from a state-losing one.
    assert 'series=' in cmd, cmd
    assert 'season=1' in cmd, cmd
    assert 'episode=1' in cmd, cmd


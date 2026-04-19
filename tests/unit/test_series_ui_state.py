#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for series_ui state integration (multi-version episode rows)."""
import os
import sys
import tempfile
import pytest
from unittest.mock import patch

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


def _parse_url_params(url):
    """Parse '?' query string into a dict."""
    try:
        from urllib.parse import urlparse, parse_qs
    except ImportError:
        from urlparse import urlparse, parse_qs
    qs = urlparse(url).query
    return {k: v[0] for k, v in parse_qs(qs).items()}


def test_search_ui_single_version_episode_url_has_series_season_episode():
    """Fix B: single-version single-episode play URL must carry series/season/episode
    so _build_state_key produces 'ep:...' matching state_key_for."""
    from lib.utils import get_url
    from lib.playback import _build_state_key

    series_name = 'south park'
    season_num = 5
    ep_num = 3
    ep_data = {'ident': 'abc', 'name': 'south.park.s05e03.1080p.mkv'}

    url = get_url(action='play', ident=ep_data['ident'], name=ep_data['name'],
                  series=series_name, season=season_num, episode=ep_num)
    params = _parse_url_params(url)

    assert params.get('series') == series_name
    assert params.get('season') == str(season_num)
    assert params.get('episode') == str(ep_num)
    assert _build_state_key(params) == 'ep:south park|S05E03'


def test_search_ui_movie_single_version_url_has_movie_key():
    """Fix C: movie single-version play URL must carry movie_key so state_key resolves to mv:..."""
    from lib.utils import get_url
    from lib.playback import _build_state_key

    movie_key = 'inception|2010'
    versions = [{'ident': 'zzz', 'name': 'inception.2010.1080p.mkv'}]

    url = get_url(action='play', ident=versions[0]['ident'],
                  name=versions[0]['name'], movie_key=movie_key)
    params = _parse_url_params(url)

    assert params.get('movie_key') == movie_key
    assert _build_state_key(params) == 'mv:inception|2010'


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

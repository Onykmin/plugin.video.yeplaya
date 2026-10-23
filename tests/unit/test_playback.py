#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Playback: state-key derivation from play-URL params, cross-process download lock."""
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import tests.conftest  # noqa: F401 — installs Kodi mocks
from lib import playback


@pytest.mark.parametrize('params, expected', [
    # season/episode 0 are real (specials) and must not fall back to file:
    ({'series': 's', 'season': 0, 'episode': 0, 'ident': 'x'}, 'ep:s|S00E00'),
    # URL params arrive as strings
    ({'series': 's', 'season': '0', 'episode': '0', 'ident': 'x'}, 'ep:s|S00E00'),
    ({'series': 's', 'season': '', 'episode': 0, 'ident': 'x'}, 'file:x'),
    ({'ident': 'x'}, 'file:x'),
    ({'movie_key': 'inception|2010', 'ident': 'x'}, 'mv:inception|2010'),
])
def test_build_state_key(params, expected):
    assert playback._build_state_key(params) == expected


class TestCrossProcessDownloadLock:
    """The cross-process flock guard (Kodi runs each call in its own process)."""

    @pytest.fixture
    def pb(self, tmp_path, monkeypatch):
        if playback._fcntl is None:
            pytest.skip("no fcntl on this platform")
        monkeypatch.setattr(playback, 'translatePath', lambda p: str(tmp_path) + '/')
        return playback

    def test_second_acquire_blocks_while_held(self, pb):
        h1 = pb._acquire_cross_process_lock('ID1')
        assert h1 not in (None, 'noflock')
        assert pb._acquire_cross_process_lock('ID1') is None, "held lock must block"
        h1.close()
        h2 = pb._acquire_cross_process_lock('ID1')
        assert h2 not in (None, 'noflock'), "lock re-acquirable after release"
        h2.close()

    def test_distinct_idents_independent(self, pb):
        a = pb._acquire_cross_process_lock('A')
        b = pb._acquire_cross_process_lock('B')
        assert a not in (None, 'noflock') and b not in (None, 'noflock')
        a.close()
        b.close()

    def test_bad_lock_path_degrades_not_blocks(self, monkeypatch):
        """A missing/unwritable lock dir must NOT wedge downloads: degrade."""
        monkeypatch.setattr(playback, 'translatePath', lambda p: '/nonexistent_dir_xyz_zzz/')
        assert playback._acquire_cross_process_lock('X') == 'noflock'


class TestPlayEntry:
    """play(): every failure path must resolve the handle as failed (no hung
    spinner) and the happy path must hand the derived state key to playback."""

    @pytest.fixture
    def seams(self, monkeypatch):
        from unittest.mock import MagicMock
        s = type('S', (), {})()
        s.resolve = MagicMock()
        s.popinfo = MagicMock()
        s.set_resolved = MagicMock()
        monkeypatch.setattr(playback, 'resolve_and_play', s.resolve)
        monkeypatch.setattr(playback, 'popinfo', s.popinfo)
        monkeypatch.setattr(playback.xbmcplugin, 'setResolvedUrl', s.set_resolved)
        monkeypatch.setattr(playback, 'revalidate', lambda: 'tok')
        return s

    def test_success_passes_token_and_state_key(self, seams):
        playback.play({'ident': 'abc', 'name': 'f.mkv', 'series': 'show',
                       'season': '1', 'episode': '2'})
        seams.resolve.assert_called_once_with('abc', 'f.mkv', 'tok',
                                              state_key='ep:show|S01E02')
        seams.set_resolved.assert_not_called()

    def test_no_token_notifies_and_fails_resolve(self, seams, monkeypatch):
        monkeypatch.setattr(playback, 'revalidate', lambda: None)
        playback.play({'ident': 'abc', 'name': 'f.mkv'})
        seams.resolve.assert_not_called()
        seams.popinfo.assert_called_once()
        assert seams.set_resolved.call_args[0][1] is False

    def test_missing_ident_fails_resolve_without_playing(self, seams):
        playback.play({'name': 'f.mkv'})
        seams.resolve.assert_not_called()
        assert seams.set_resolved.call_args[0][1] is False

    def test_unexpected_error_notifies_and_fails_resolve(self, seams):
        seams.resolve.side_effect = RuntimeError('boom')
        playback.play({'ident': 'abc', 'name': 'f.mkv'})
        seams.popinfo.assert_called_once()
        assert seams.set_resolved.call_args[0][1] is False

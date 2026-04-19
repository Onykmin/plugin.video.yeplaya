#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for YePlayer state tracking — mocked Kodi."""
import sys
import os
import tempfile
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from tests.conftest import MockPlayer, MockMonitor, MockAddon, get_mock_addon


def _ensure_xbmc_mocks():
    xbmc = sys.modules.get('xbmc')
    if xbmc is not None:
        try:
            if not isinstance(xbmc.Player, type) or not issubclass(xbmc.Player, MockPlayer):
                xbmc.Player = MockPlayer
        except (TypeError, AttributeError):
            xbmc.Player = MockPlayer
        try:
            if not isinstance(xbmc.Monitor, type) or not issubclass(xbmc.Monitor, MockMonitor):
                xbmc.Monitor = MockMonitor
        except (TypeError, AttributeError):
            xbmc.Monitor = MockMonitor


class _Harness:
    def __init__(self, state_key='ep:x|S01E01', tracking_enabled=True, settings=None):
        _ensure_xbmc_mocks()

        # Wire addon settings (shared mock addon from conftest)
        mock_addon = get_mock_addon()
        mock_addon._settings = {}
        if settings:
            for k, v in settings.items():
                mock_addon._settings[k] = v
        # Ensure xbmcaddon.Addon() returns our configured mock (other tests may
        # have replaced it with a different MagicMock).
        xbmcaddon = sys.modules.get('xbmcaddon')
        if xbmcaddon is not None:
            xbmcaddon.Addon = MagicMock(return_value=mock_addon)
        self.mock_addon = mock_addon

        # Tempfile DB for state module
        self.tmpdir = tempfile.mkdtemp()
        self.dbpath = os.path.join(self.tmpdir, 'state.db')
        if 'lib.state' in sys.modules:
            del sys.modules['lib.state']
        from lib import state as _state
        _state._reset_for_tests(self.dbpath)
        _state._get_db_path = lambda: self.dbpath
        self.state = _state

        # Reload player module
        if 'lib.player' in sys.modules:
            del sys.modules['lib.player']
        from lib.player import YePlayer
        self.player = YePlayer(state_key=state_key, tracking_enabled=tracking_enabled)

    def cleanup(self):
        self.state._reset_for_tests()
        if 'lib.state' in sys.modules:
            del sys.modules['lib.state']
        try:
            os.remove(self.dbpath)
        except OSError:
            pass
        try:
            os.rmdir(self.tmpdir)
        except OSError:
            pass


class TestPlayerStateTracking:
    def test_stopped_writes_resume(self):
        h = _Harness()
        h.player.getTime = MagicMock(return_value=120.0)
        h.player.getTotalTime = MagicMock(return_value=1000.0)
        h.player.onPlayBackStopped()
        st = h.state.get_state('ep:x|S01E01')
        assert st is not None
        assert st['resume_seconds'] == 120
        assert st['watched'] == 0
        h.cleanup()

    def test_ended_forces_watched(self):
        h = _Harness()
        h.player.getTime = MagicMock(return_value=500.0)
        h.player.getTotalTime = MagicMock(return_value=1000.0)
        h.player.onPlayBackEnded()
        st = h.state.get_state('ep:x|S01E01')
        assert st is not None
        assert st['watched'] == 1
        h.cleanup()

    def test_error_blocks_write(self):
        h = _Harness()
        h.player.getTime = MagicMock(return_value=100.0)
        h.player.getTotalTime = MagicMock(return_value=1000.0)
        h.player.onPlayBackError()
        h.player.onPlayBackStopped()  # should NOT write
        st = h.state.get_state('ep:x|S01E01')
        assert st is None
        h.cleanup()

    def test_live_stream_total_zero(self):
        h = _Harness()
        h.player.getTime = MagicMock(return_value=100.0)
        h.player.getTotalTime = MagicMock(return_value=0.0)
        h.player.onPlayBackStopped()
        st = h.state.get_state('ep:x|S01E01')
        assert st is None
        h.cleanup()

    def test_tracking_disabled_no_write(self):
        h = _Harness(tracking_enabled=False)
        h.player.getTime = MagicMock(return_value=500.0)
        h.player.getTotalTime = MagicMock(return_value=1000.0)
        h.player.onPlayBackStopped()
        st = h.state.get_state('ep:x|S01E01')
        assert st is None
        h.cleanup()

    def test_no_state_key_no_write(self):
        h = _Harness(state_key=None)
        h.player.getTime = MagicMock(return_value=500.0)
        h.player.getTotalTime = MagicMock(return_value=1000.0)
        h.player.onPlayBackStopped()
        # Nothing to verify other than no crash; state is keyed and absent
        h.cleanup()

    def test_gettime_raises_no_crash(self):
        h = _Harness()
        h.player.getTime = MagicMock(side_effect=RuntimeError("boom"))
        h.player.getTotalTime = MagicMock(return_value=1000.0)
        # Should not raise
        h.player.onPlayBackStopped()
        h.cleanup()

    def test_ended_even_when_gettime_raises(self):
        """Fix D: onPlayBackEnded must write watched=1 even if getTime() raises."""
        h = _Harness()
        h.player.getTime = MagicMock(side_effect=RuntimeError("boom"))
        h.player.getTotalTime = MagicMock(side_effect=RuntimeError("boom"))
        h.player.onPlayBackEnded()
        st = h.state.get_state('ep:x|S01E01')
        assert st is not None, "force_watched path must persist even when getTime fails"
        assert st['watched'] == 1
        h.cleanup()


class TestPerConcernGating:
    """Fix F: track_resume and track_watched must gate independently."""

    def test_resume_disabled_watched_on_mid_playback(self):
        """resume=false, watched=true: stop at 30% → no row written."""
        h = _Harness(settings={'track_resume': 'false', 'track_watched': 'true'})
        h.player.getTime = MagicMock(return_value=300.0)
        h.player.getTotalTime = MagicMock(return_value=1000.0)
        h.player.onPlayBackStopped()
        st = h.state.get_state('ep:x|S01E01')
        assert st is None, "resume must be suppressed when track_resume=false"
        h.cleanup()

    def test_resume_disabled_watched_on_end_of_playback(self):
        """resume=false, watched=true: onPlayBackEnded → watched=1."""
        h = _Harness(settings={'track_resume': 'false', 'track_watched': 'true'})
        h.player.getTime = MagicMock(return_value=1000.0)
        h.player.getTotalTime = MagicMock(return_value=1000.0)
        h.player.onPlayBackEnded()
        st = h.state.get_state('ep:x|S01E01')
        assert st is not None
        assert st['watched'] == 1
        h.cleanup()

    def test_watched_disabled_resume_on_high_pct(self):
        """watched=false, resume=true: stop at 95% → no watched row written."""
        h = _Harness(settings={'track_resume': 'true', 'track_watched': 'false'})
        h.player.getTime = MagicMock(return_value=950.0)
        h.player.getTotalTime = MagicMock(return_value=1000.0)
        h.player.onPlayBackStopped()
        st = h.state.get_state('ep:x|S01E01')
        assert st is None, "watched must be suppressed when track_watched=false"
        h.cleanup()

    def test_watched_disabled_resume_on_mid_playback(self):
        """watched=false, resume=true: stop at 30% → resume row written."""
        h = _Harness(settings={'track_resume': 'true', 'track_watched': 'false'})
        h.player.getTime = MagicMock(return_value=300.0)
        h.player.getTotalTime = MagicMock(return_value=1000.0)
        h.player.onPlayBackStopped()
        st = h.state.get_state('ep:x|S01E01')
        assert st is not None
        assert st['watched'] == 0
        assert st['resume_seconds'] == 300
        h.cleanup()

    def test_both_disabled_no_write(self):
        """resume=false, watched=false: nothing written at any point."""
        h = _Harness(settings={'track_resume': 'false', 'track_watched': 'false'})
        h.player.getTime = MagicMock(return_value=300.0)
        h.player.getTotalTime = MagicMock(return_value=1000.0)
        h.player.onPlayBackStopped()
        h.player.onPlayBackEnded()
        assert h.state.get_state('ep:x|S01E01') is None
        h.cleanup()

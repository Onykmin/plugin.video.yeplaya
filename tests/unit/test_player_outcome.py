#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""YePlayer natural-end outcome (`ended`) and end-callback grace — mocked Kodi."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from tests.conftest import MockPlayer, MockMonitor


def _make_player():
    xbmc = sys.modules['xbmc']
    if not (isinstance(xbmc.Player, type) and issubclass(xbmc.Player, MockPlayer)):
        xbmc.Player = MockPlayer
    if not (isinstance(xbmc.Monitor, type) and issubclass(xbmc.Monitor, MockMonitor)):
        xbmc.Monitor = MockMonitor
    sys.modules.pop('lib.player', None)
    from lib.player import YePlayer
    return YePlayer(state_key=None, tracking_enabled=False)


class _ScriptedMonitor:
    """waitForAbort counts calls and runs `on_call(n)` on each (never aborts)."""

    def __init__(self, on_call=None):
        self.calls = 0
        self._on_call = on_call

    def waitForAbort(self, timeout=None):
        self.calls += 1
        if self._on_call:
            self._on_call(self.calls)
        return False


def _idle_player(on_call=None):
    """Player already started and whose isPlaying() is False."""
    p = _make_player()
    p._av_started = True
    p.isPlaying = lambda: False
    p._monitor = _ScriptedMonitor(on_call)
    return p


def test_outcome_not_ended_initially():
    assert _make_player().ended is False


def test_outcome_ended_true_after_natural_end():
    p = _make_player()
    p.onPlayBackEnded()
    assert p.ended is True


def test_outcome_ended_false_after_stop():
    p = _make_player()
    p.onPlayBackStopped()
    assert p.ended is False


def test_outcome_ended_false_after_error():
    p = _make_player()
    p.onPlayBackError()
    assert p.ended is False


def test_outcome_ended_false_when_end_follows_error():
    p = _make_player()
    p.onPlayBackError()
    p.onPlayBackEnded()
    assert p.ended is False


def test_grace_late_end_callback_is_not_lost():
    p = None

    def fire(n):
        if n == 2:
            p.onPlayBackEnded()

    p = _idle_player(fire)
    p.wait_for_playback()
    assert p.ended is True


def test_grace_no_callback_means_not_ended_and_loop_returns():
    p = _idle_player()
    p.wait_for_playback(end_grace=1.0)
    assert p.ended is False
    assert p._monitor.calls == 4


def test_grace_stop_callback_in_window_is_not_ended():
    p = None

    def fire(n):
        if n == 1:
            p.onPlayBackStopped()

    p = _idle_player(fire)
    p.wait_for_playback()
    assert p.ended is False

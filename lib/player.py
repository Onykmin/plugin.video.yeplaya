# -*- coding: utf-8 -*-
# Module: player
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

"""Custom player with automatic audio/subtitle language selection."""

import xbmc
import xbmcaddon
from lib.language import match_stream, normalize_lang, setting_to_code

_LOG = "YAWsP.player: "


class YePlayer(xbmc.Player):
    """Player subclass that selects preferred audio/subtitle streams on playback start."""

    def __init__(self):
        super(YePlayer, self).__init__()
        self._av_started = False
        self._error = False
        self._monitor = xbmc.Monitor()

    def wait_for_playback(self, timeout=30):
        """Keep script alive until onAVStarted fires, error, or timeout (seconds)."""
        for _ in range(timeout * 10):
            if self._av_started or self._error:
                return
            if self._monitor.waitForAbort(0.1):
                return
        xbmc.log(_LOG + "wait_for_playback: timeout after %ds" % timeout, xbmc.LOGWARNING)

    def onPlayBackError(self):
        self._error = True
        xbmc.log(_LOG + "playback error", xbmc.LOGERROR)

    def onPlayBackStopped(self):
        self._error = True

    def onPlayBackEnded(self):
        self._error = True

    def onAVStarted(self):
        self._av_started = True
        try:
            addon = xbmcaddon.Addon()
            raw_a = addon.getSetting('audio_lang')
            raw_a2 = addon.getSetting('audio_lang2')
            raw_s = addon.getSetting('sub_lang')
            raw_s2 = addon.getSetting('sub_lang2')
            raw_sa = addon.getSetting('sub_auto')
            xbmc.log(_LOG + "settings: audio=%s/%s sub=%s/%s auto=%s" % (raw_a, raw_a2, raw_s, raw_s2, raw_sa), xbmc.LOGINFO)
            self._select_audio(addon)
            self._select_subtitles(addon)
        except Exception as e:
            xbmc.log(_LOG + "error: " + str(e), xbmc.LOGERROR)

    def _select_audio(self, addon):
        primary = setting_to_code(addon.getSetting('audio_lang'))
        fallback = setting_to_code(addon.getSetting('audio_lang2'))
        if not primary and not fallback:
            xbmc.log(_LOG + "audio: SKIP (disabled)", xbmc.LOGINFO)
            return
        streams = self._get_audio_streams()
        xbmc.log(_LOG + "audio: streams=%s primary=%s fallback=%s" % (streams, primary, fallback), xbmc.LOGINFO)
        if len(streams) <= 1:
            xbmc.log(_LOG + "audio: SKIP (single stream)", xbmc.LOGINFO)
            return
        for i, s in enumerate(streams):
            xbmc.log(_LOG + "audio: [%d] '%s' → %s" % (i, s, normalize_lang(s)), xbmc.LOGINFO)
        idx = match_stream(streams, primary, fallback)
        if idx is not None:
            xbmc.log(_LOG + "audio: selecting index %d" % idx, xbmc.LOGINFO)
            self.setAudioStream(idx)
        else:
            xbmc.log(_LOG + "audio: no match, keeping default", xbmc.LOGINFO)

    def _select_subtitles(self, addon):
        primary = setting_to_code(addon.getSetting('sub_lang'))
        fallback = setting_to_code(addon.getSetting('sub_lang2'))
        if not primary and not fallback:
            xbmc.log(_LOG + "subs: SKIP (disabled)", xbmc.LOGINFO)
            return
        streams = self._get_subtitle_streams()
        xbmc.log(_LOG + "subs: streams=%s primary=%s fallback=%s" % (streams, primary, fallback), xbmc.LOGINFO)
        if not streams:
            xbmc.log(_LOG + "subs: SKIP (no streams)", xbmc.LOGINFO)
            return
        for i, s in enumerate(streams):
            xbmc.log(_LOG + "subs: [%d] '%s' → %s" % (i, s, normalize_lang(s)), xbmc.LOGINFO)
        idx = match_stream(streams, primary, fallback)
        if idx is not None:
            xbmc.log(_LOG + "subs: selecting index %d" % idx, xbmc.LOGINFO)
            self.setSubtitleStream(idx)
            if addon.getSetting('sub_auto') == 'true':
                xbmc.log(_LOG + "subs: showSubtitles(True)", xbmc.LOGINFO)
                self.showSubtitles(True)
        else:
            xbmc.log(_LOG + "subs: no match, keeping default", xbmc.LOGINFO)

    def _get_audio_streams(self):
        """Return list of audio stream language labels."""
        try:
            count = self.getAvailableAudioStreams()
            return count if isinstance(count, list) else []
        except Exception:
            return []

    def _get_subtitle_streams(self):
        """Return list of subtitle stream language labels."""
        try:
            count = self.getAvailableSubtitleStreams()
            return count if isinstance(count, list) else []
        except Exception:
            return []

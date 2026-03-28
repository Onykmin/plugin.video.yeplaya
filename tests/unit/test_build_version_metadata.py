# -*- coding: utf-8 -*-
"""Tests for _build_version_metadata helper."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from lib.ui import _build_version_metadata


class TestBuildVersionMetadata:
    def test_resolution_from_file_info(self):
        fd = {'file_info': {'resolution': '1920x1080'}, 'quality_meta': {}}
        parts = _build_version_metadata(fd)
        assert '1920x1080' in parts

    def test_resolution_fallback_to_quality(self):
        fd = {'file_info': {}, 'quality_meta': {'quality': '720p'}}
        parts = _build_version_metadata(fd)
        assert '720p' in parts

    def test_codec_from_file_info(self):
        fd = {'file_info': {'video_codec': 'H.265'}, 'quality_meta': {}}
        parts = _build_version_metadata(fd)
        assert 'H.265' in parts

    def test_codec_fallback(self):
        fd = {'file_info': {}, 'quality_meta': {'codec': 'x264'}}
        parts = _build_version_metadata(fd)
        assert 'x264' in parts

    def test_audio_from_file_info(self):
        fd = {'file_info': {'audio': 'EN AAC 6ch'}, 'quality_meta': {}}
        parts = _build_version_metadata(fd)
        assert 'Audio: EN AAC 6ch' in parts

    def test_subtitles(self):
        fd = {'file_info': {'subtitles': 'CZ, EN'}, 'quality_meta': {}}
        parts = _build_version_metadata(fd)
        assert 'Subs: CZ, EN' in parts

    def test_language_when_file_info_empty(self):
        fd = {'file_info': {}, 'quality_meta': {}, 'language': 'CZ'}
        # file_info is empty dict (falsy), so language IS shown
        parts = _build_version_metadata(fd)
        assert '[CZ]' in parts

    def test_language_when_file_info_missing(self):
        fd = {'quality_meta': {}, 'language': 'CZ'}
        parts = _build_version_metadata(fd)
        assert '[CZ]' in parts

    def test_size(self):
        fd = {'file_info': {}, 'quality_meta': {}, 'size': '1073741824'}
        parts = _build_version_metadata(fd)
        assert any('GB' in p or 'MB' in p or 'KB' in p for p in parts)

    def test_empty_dict(self):
        fd = {'file_info': {}, 'quality_meta': {}}
        parts = _build_version_metadata(fd)
        assert parts == []

    def test_missing_keys_defaults(self):
        fd = {}
        parts = _build_version_metadata(fd)
        assert parts == []

    def test_full_metadata(self):
        fd = {
            'file_info': {
                'resolution': '3840x2160',
                'video_codec': 'HEVC',
                'audio': 'EN DTS 6ch',
                'subtitles': 'CZ, SK'
            },
            'quality_meta': {'source': 'BluRay'},
            'size': '5368709120'
        }
        parts = _build_version_metadata(fd)
        assert '3840x2160' in parts
        assert 'BluRay' in parts
        assert 'HEVC' in parts
        assert 'Audio: EN DTS 6ch' in parts
        assert 'Subs: CZ, SK' in parts

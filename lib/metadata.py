# -*- coding: utf-8 -*-
# Module: metadata
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

from lib.logging import log_debug
from lib.api import getinfo
from lib.utils import todict


def extract_video_info(info):
    """Extract video metadata from file info dict."""
    result = {}
    if 'video' in info and 'stream' in info['video']:
        streams = info['video']['stream']
        if not isinstance(streams, list):
            streams = [streams]

        if streams:
            video = streams[0]
            width = video.get('width', '')
            height = video.get('height', '')
            if width and height:
                result['resolution'] = '{0}x{1}'.format(width, height)
            if 'format' in video:
                result['video_codec'] = video['format']

    return result


def extract_audio_info(info):
    """Extract audio metadata from file info dict."""
    result = {}
    if 'audio' in info and 'stream' in info['audio']:
        streams = info['audio']['stream']
        if not isinstance(streams, list):
            streams = [streams]

        audio_info = []
        for audio in streams:
            parts = []
            if audio.get('language'):
                parts.append(audio['language'].upper())
            if audio.get('format'):
                parts.append(audio['format'])
            if audio.get('channels'):
                parts.append('{0}ch'.format(audio['channels']))
            if parts:
                audio_info.append(' '.join(parts))

        if audio_info:
            result['audio'] = ', '.join(audio_info)

    return result


def extract_subtitle_info(info):
    """Extract subtitle metadata from file info dict."""
    result = {}
    if 'subtitle' in info and 'stream' in info['subtitle']:
        streams = info['subtitle']['stream']
        if not isinstance(streams, list):
            streams = [streams]

        sub_langs = []
        for sub in streams:
            if sub.get('language'):
                sub_langs.append(sub['language'].upper())

        if sub_langs:
            result['subtitles'] = ', '.join(sub_langs)

    return result


def enrich_file_metadata(file_dict, ident, token):
    """Fetch and enrich file_dict with metadata from API."""
    if not ident or ident == 'unknown':
        return False

    try:
        info_xml = getinfo(ident, token)
        if not info_xml:
            return False

        info = todict(info_xml)
        file_dict['file_info'] = {}

        file_dict['file_info'].update(extract_video_info(info))
        file_dict['file_info'].update(extract_audio_info(info))
        file_dict['file_info'].update(extract_subtitle_info(info))

        return True
    except Exception as e:
        log_debug('Failed to enrich metadata for {0}: {1}'.format(ident, e))
        return False

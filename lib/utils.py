# -*- coding: utf-8 -*-
# Module: utils
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

import sys
import xbmc
import xbmcgui
import xbmcaddon
import xbmcplugin

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode

# Global state
def _get_handle():
    """Get plugin handle safely, returns -1 if not in Kodi context."""
    if len(sys.argv) > 1:
        try:
            return int(sys.argv[1])
        except (ValueError, TypeError):
            return -1
    return -1

_handle = _get_handle()
_addon = xbmcaddon.Addon()


def get_label_format():
    """Get label format, refreshed from settings."""
    if 'true' == _addon.getSetting('customformat'):
        return _addon.getSetting('labelformat')
    return "{name}"


def get_filesize_enabled():
    """Get filesize display setting, refreshed from settings."""
    return 'true' == _addon.getSetting('resultsize')


# ============================================================================
# Utility Functions
# ============================================================================

def sanitize_url_param(value):
    """Sanitize a URL parameter value for safe encoding.

    Handles None, unicode, and special characters.
    """
    if value is None:
        return ''
    # Convert to string if not already
    if not isinstance(value, str):
        value = str(value)
    # Handle unicode - encode to UTF-8 compatible string
    try:
        # Python 3: strings are already unicode, just ensure it's valid
        value.encode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        # Fallback to ASCII with replacement
        value = value.encode('ascii', 'replace').decode('ascii')
    return value


def get_url(**kwargs):
    """Build plugin URL with parameters.

    Sanitizes all parameter values before encoding.
    Skips None values to keep URLs clean.
    """
    from lib.api import get_url_base
    # Sanitize all values and skip None/empty
    sanitized = {}
    for k, v in kwargs.items():
        sanitized_value = sanitize_url_param(v)
        # Include empty strings explicitly set (like category='')
        # but skip None values converted to empty
        if v is not None or sanitized_value:
            sanitized[k] = sanitized_value
    return '{0}?{1}'.format(get_url_base(), urlencode(sanitized, 'utf-8'))


def popinfo(message, heading=None, icon=xbmcgui.NOTIFICATION_INFO, time=3000, sound=False):
    """Show notification popup."""
    if heading is None:
        heading = _addon.getAddonInfo('name')
    xbmcgui.Dialog().notification(heading, message, icon, time, sound=sound)


def ask(what):
    """Show keyboard input dialog."""
    if what is None:
        what = ''
    kb = xbmc.Keyboard(what, _addon.getLocalizedString(30007))
    kb.doModal()
    if kb.isConfirmed():
        return kb.getText()
    return None


def todict(xml, skip=[]):
    """Convert XML element to dictionary."""
    result = {}
    # Capture XML attributes (ident, type, etc.)
    if xml.attrib:
        result.update(xml.attrib)
    for e in xml:
        if e.tag not in skip:
            value = e.text if len(list(e)) == 0 else todict(e, skip)
            if e.tag in result:
                if isinstance(result[e.tag], list):
                    result[e.tag].append(value)
                else:
                    result[e.tag] = [result[e.tag], value]
            else:
                result[e.tag] = value
    return result


def sizelize(txtsize, units=['B', 'KB', 'MB', 'GB']):
    """Convert bytes to human-readable size."""
    if txtsize:
        size = float(txtsize)
        if size < 1024:
            size = str(size) + units[0]
        else:
            size = size / 1024
            if size < 1024:
                size = str(int(round(size))) + units[1]
            else:
                size = size / 1024
                if size < 1024:
                    size = str(round(size, 2)) + units[2]
                else:
                    size = size / 1024
                    size = str(round(size, 2)) + units[3]
        return size
    return str(txtsize)


def labelize(file):
    """Create label for file item."""
    if 'size' in file:
        size = sizelize(file['size'])
    elif 'sizelized' in file:
        size = file['sizelized']
    else:
        size = '?'
    return get_label_format().format(name=file['name'], size=size)


def set_webshare_id(listitem, ident):
    """Set Webshare unique ID for watched status persistence."""
    if ident:
        try:
            infotag = listitem.getVideoInfoTag()
            infotag.setUniqueIDs({'webshare': ident}, 'webshare')
        except AttributeError:
            # Kodi < 20: use deprecated method
            try:
                listitem.setUniqueIDs({'webshare': ident}, 'webshare')
            except Exception:
                pass


def tolistitem(file, addcommands=[]):
    """Create Kodi ListItem from file dict."""
    label = labelize(file)
    listitem = xbmcgui.ListItem(label=label)
    infotag = listitem.getVideoInfoTag()
    infotag.setTitle(label)
    if 'ident' in file:
        set_webshare_id(listitem, file['ident'])
    if 'img' in file:
        listitem.setArt({'thumb': file['img']})
    if get_filesize_enabled() and 'size' in file and file['size'].isdigit():
        listitem.setInfo('video', {'size': int(file['size'])})
    listitem.setProperty('IsPlayable', 'true')
    commands = []
    commands.append((_addon.getLocalizedString(30211), 'RunPlugin(' + get_url(action='info', ident=file['ident']) + ')'))
    commands.append((_addon.getLocalizedString(30212), 'RunPlugin(' + get_url(action='download', ident=file['ident']) + ')'))
    if addcommands:
        commands = commands + addcommands
    listitem.addContextMenuItems(commands)
    return listitem


def infonize(data, key, process=str, showkey=True, prefix='', suffix='\n'):
    """Format info field for display."""
    if key in data:
        result = prefix
        if showkey:
            result += key + ': '
        result += process(data[key]) + suffix
        return result
    return ''


def fpsize(fps):
    """Format FPS value."""
    return str(round(float(fps), 2)) + 'fps'


def get_handle():
    """Get global plugin handle."""
    return _handle


def get_addon():
    """Get global addon object."""
    return _addon


def refresh_settings():
    """Refresh addon object to pick up setting changes."""
    global _addon
    _addon = xbmcaddon.Addon()

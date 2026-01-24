# -*- coding: utf-8 -*-
# Module: api
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

import sys
import hashlib
import string
import uuid
import xbmc
import xbmcaddon
import xbmcgui
import requests
from xml.etree import ElementTree as ET
from md5crypt import md5crypt

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode

# ============================================================================
# Configuration & Constants
# ============================================================================

BASE = 'https://webshare.cz'
API = BASE + '/api/'
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
HEADERS = {'User-Agent': UA, 'Referer': BASE}
REALM = ':Webshare:'

# Global state
_url = sys.argv[0] if len(sys.argv) > 0 else ''
_addon = xbmcaddon.Addon()
_session = requests.Session()
_session.headers = HEADERS.copy()  # Use assignment to avoid header accumulation


# ============================================================================
# API Functions
# ============================================================================

def api(fnct, data, timeout=30):
    """Make API call to Webshare."""
    try:
        response = _session.post(API + fnct + "/", data=data, timeout=timeout)
        response.raise_for_status()
        return response
    except requests.exceptions.Timeout:
        xbmc.log("YAWsP: API timeout for: " + fnct, xbmc.LOGERROR)
        return None
    except requests.exceptions.RequestException as e:
        xbmc.log("YAWsP: API error for " + fnct + ": " + str(e), xbmc.LOGERROR)
        return None


def validate_ident(ident):
    """Validate file identifier format."""
    if not ident:
        return False
    if not isinstance(ident, str):
        return False
    # Prevent injection attacks - only allow alphanumeric and common safe chars
    allowed = string.ascii_letters + string.digits + '_-'
    if not all(c in allowed for c in ident):
        xbmc.log("YAWsP: Invalid ident format: " + str(ident), xbmc.LOGWARNING)
        return False
    # Reasonable length check
    if len(ident) > 100:
        xbmc.log("YAWsP: Ident too long: " + str(len(ident)), xbmc.LOGWARNING)
        return False
    return True


def parse_xml(content):
    """Safely parse XML content with error handling."""
    try:
        # Limit XML size to prevent billion laughs attack
        if len(content) > 10 * 1024 * 1024:  # 10 MB limit
            xbmc.log("YAWsP: XML response too large: " + str(len(content)), xbmc.LOGERROR)
            return None
        return ET.fromstring(content)
    except ET.ParseError as e:
        xbmc.log("YAWsP: XML parsing error: " + str(e), xbmc.LOGERROR)
        return None
    except Exception as e:
        xbmc.log("YAWsP: Unexpected error parsing XML: " + str(e), xbmc.LOGERROR)
        return None


def is_ok(xml):
    """Check if XML response has OK status."""
    if xml is None:
        return False
    status_elem = xml.find('status')
    if status_elem is None:
        return False
    return status_elem.text == 'OK'


def login():
    """Login to Webshare and return token."""
    from lib.utils import popinfo

    username = _addon.getSetting('wsuser')
    password = _addon.getSetting('wspass')
    if username == '' or password == '':
        popinfo(_addon.getLocalizedString(30101), sound=True)
        _addon.openSettings()
        return
    response = api('salt', {'username_or_email': username})
    if response is None:
        return
    xml = parse_xml(response.content)
    if is_ok(xml):
        salt = xml.find('salt').text
        try:
            encrypted_pass = hashlib.sha1(md5crypt(password.encode('utf-8'), salt.encode('utf-8'))).hexdigest()
            pass_digest = hashlib.md5(username.encode('utf-8') + REALM + encrypted_pass.encode('utf-8')).hexdigest()
        except TypeError:
            encrypted_pass = hashlib.sha1(md5crypt(password.encode('utf-8'), salt.encode('utf-8')).encode('utf-8')).hexdigest()
            pass_digest = hashlib.md5(username.encode('utf-8') + REALM.encode('utf-8') + encrypted_pass.encode('utf-8')).hexdigest()
        response = api('login', {'username_or_email': username, 'password': encrypted_pass, 'digest': pass_digest, 'keep_logged_in': 1})
        if response is None:
            return
        xml = parse_xml(response.content)
        if is_ok(xml):
            token = xml.find('token').text
            _addon.setSetting('token', token)
            return token
        else:
            popinfo(_addon.getLocalizedString(30102), icon=xbmcgui.NOTIFICATION_ERROR, sound=True)
            _addon.openSettings()
    else:
        popinfo(_addon.getLocalizedString(30102), icon=xbmcgui.NOTIFICATION_ERROR, sound=True)
        _addon.openSettings()


def clear_token_cache():
    """Clear module-level token cache on invalidation."""
    _addon.setSetting('token', '')


def revalidate():
    """Revalidate token or login if needed."""
    from lib.utils import popinfo

    max_attempts = 3
    for attempt in range(max_attempts):
        token = _addon.getSetting('token')
        if len(token) == 0:
            if not login():
                return None
            token = _addon.getSetting('token')

        response = api('user_data', {'wst': token})
        if response is None:
            return None
        xml = parse_xml(response.content)
        if is_ok(xml):
            vip = xml.find('vip').text
            if vip != '1':
                popinfo(_addon.getLocalizedString(30103), icon=xbmcgui.NOTIFICATION_WARNING)
            return token
        else:
            # Token invalid (401-like), clear cache and retry
            clear_token_cache()
            if attempt == max_attempts - 1:
                # Last attempt failed
                return None
    return None


def getinfo(ident, wst):
    """Get file info from API."""
    from lib.utils import popinfo

    if not validate_ident(ident):
        xbmc.log("YAWsP: Invalid ident in getinfo", xbmc.LOGERROR)
        return None
    response = api('file_info', {'ident': ident, 'wst': wst})
    if response is None:
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
        return None
    xml = parse_xml(response.content)
    ok = is_ok(xml)
    if not ok:
        response = api('file_info', {'ident': ident, 'wst': wst, 'maybe_removed': 'true'})
        if response is None:
            popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
            return None
        xml = parse_xml(response.content)
        ok = is_ok(xml)
    if ok:
        return xml
    else:
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
        return None


def getlink(ident, wst, dtype='video_stream'):
    """Get download/stream link from API."""
    from lib.utils import popinfo

    if not validate_ident(ident):
        xbmc.log("YAWsP: Invalid ident in getlink", xbmc.LOGERROR)
        return None
    # UUID experiment
    duuid = _addon.getSetting('duuid')
    if not duuid:
        duuid = str(uuid.uuid4())
        _addon.setSetting('duuid', duuid)
    data = {'ident': ident, 'wst': wst, 'download_type': dtype, 'device_uuid': duuid}
    response = api('file_link', data)
    if response is None:
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
        return None
    xml = parse_xml(response.content)
    if is_ok(xml):
        return xml.find('link').text
    else:
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
        return None


def get_session():
    """Get global session object."""
    return _session


def get_addon():
    """Get global addon object."""
    return _addon


def get_url_base():
    """Get URL base for plugin."""
    return _url


def get_url(**kwargs):
    """Build plugin URL with parameters."""
    return '{0}?{1}'.format(_url, urlencode(kwargs, 'utf-8'))

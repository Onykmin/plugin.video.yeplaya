# -*- coding: utf-8 -*-
# Module: changelog
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

"""After-update changelog dialog.

Shows the current addon version's <news> section once, the first time the
root menu is invoked after an update. Fresh installs and opt-out are silent
(see addon-level product decisions D1-D3 in the routing hook caller).
"""

import os
import re
import xbmc
import xbmcaddon
import xbmcgui
from xml.etree import ElementTree as ET

# Matches a `[B]<version>[/B]` section header by its version-shaped leading
# bold (e.g. "[B]1.3.0[/B]" or "[B]v1.3.0[/B] hotfix") so inline `[B]...[/B]`
# markup inside a body line (which is never version-shaped) is never
# mistaken for the next section boundary.
_RE_SECTION_HEADER = re.compile(r'^[ \t]*\[B\]\s*v?\d+(?:\.\d+)*\s*\[/B\]', re.MULTILINE)


def _get_addon():
    """Resolve xbmcaddon.Addon() fresh on every call (not cached at import
    time) so tests that repoint xbmcaddon.Addon and live Kodi setting
    changes are both observed."""
    return xbmcaddon.Addon()


def read_news():
    """Read the raw <news> text from addon.xml. Never raises."""
    try:
        addon = _get_addon()
        addon_path = addon.getAddonInfo('path')
        xml_path = os.path.join(addon_path, 'addon.xml')
        tree = ET.parse(xml_path)
        news_elem = tree.getroot().find('.//news')
        if news_elem is None:
            return ''
        return news_elem.text or ''
    except Exception as e:
        xbmc.log("yeplaya: changelog read_news failed: " + str(e), xbmc.LOGERROR)
        return ''


def extract_section(news_text, version):
    """Return only the body of the `[B]<version>[/B]` section, stripped.

    Exact-version match only (dots are regex-escaped) so '1.2.1' never
    matches '[B]1.2.10[/B]'. Returns '' if news_text/version is falsy or the
    section isn't found.
    """
    if not news_text or not version:
        return ''
    target = re.escape(version)
    match = re.search(r'^[ \t]*\[B\]\s*v?' + target + r'\s*\[/B\]', news_text, re.MULTILINE)
    if not match:
        return ''
    start = match.end()
    next_header = _RE_SECTION_HEADER.search(news_text, start)
    end = next_header.start() if next_header else len(news_text)
    return news_text[start:end].strip()


def maybe_show_changelog():
    """Root-menu hook: show the current version's changelog once.

    D1: fresh install (no recorded version) -> record + stay silent.
    D2: only the current version's section is ever shown.
    D3: opt-out setting off -> record + stay silent.
    """
    try:
        addon = _get_addon()
        current = addon.getAddonInfo('version')
        if not current:
            return
        seen = addon.getSetting('changelog_seen_version')
        if seen == current:
            return

        # Record first: a crash/cancel below must not make this repeat.
        addon.setSetting('changelog_seen_version', current)

        if not seen:
            return  # D1: fresh install, silent

        if addon.getSetting('show_changelog') == 'false':
            return  # D3: opted out, silent but recorded

        body = extract_section(read_news(), current)
        if not body:
            return

        try:
            heading = addon.getLocalizedString(30445).format(current)
            if not heading:
                heading = addon.getAddonInfo('name')
        except Exception:
            heading = addon.getAddonInfo('name')

        xbmcgui.Dialog().ok(heading, body)
    except Exception as e:
        xbmc.log("yeplaya: changelog check failed: " + str(e), xbmc.LOGERROR)

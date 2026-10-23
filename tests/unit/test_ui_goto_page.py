# -*- coding: utf-8 -*-
"""goto_page: Container.Update target built from the redirect params."""
from unittest.mock import patch
from urllib.parse import parse_qsl, urlparse

import tests.conftest  # noqa: F401 — installs Kodi mocks
from lib import ui


def _navigated_url(params):
    with patch.object(ui.xbmcplugin, 'endOfDirectory'), \
         patch.object(ui.xbmc, 'executebuiltin') as ex:
        ui.goto_page(params)
    (cmd,), _ = ex.call_args
    assert cmd.startswith('Container.Update(') and cmd.endswith(')')
    return cmd[len('Container.Update('):-1]


def test_explicit_target_url_is_used_verbatim():
    url = 'plugin://plugin.video.yeplaya/?action=search&what=a+b'
    assert _navigated_url({'action': 'goto_page', 'target_url': url}) == url


def test_target_built_from_params_swaps_target_action_for_action():
    url = _navigated_url({'action': 'goto_page', 'target_action': 'search',
                          'what': 'south park', 'offset': '25'})
    assert dict(parse_qsl(urlparse(url).query)) == {
        'action': 'search', 'what': 'south park', 'offset': '25'}

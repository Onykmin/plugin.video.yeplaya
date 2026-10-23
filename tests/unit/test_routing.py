# -*- coding: utf-8 -*-
"""URL routing: paramstring -> which handler runs with which params."""
import sys
import os
from unittest.mock import DEFAULT, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from lib import routing
from lib.routing import router

# action -> name of the lib.routing attribute that must handle it
HANDLERS = {
    'search': 'search', 'newsearch': 'newsearch',
    'browse_series': 'browse_series', 'browse_season': 'browse_season',
    'browse_other': 'browse_other', 'select_version': 'select_version',
    'select_movie_version': 'select_movie_version',
    'random_episode': 'show_random_episode_dialog',
    'random_movie': 'show_random_movie_dialog',
    'play': 'play', 'download': 'download', 'queue': 'queue',
    'history': 'history', 'settings': 'settings', 'info': 'info',
    'db': 'db', 'goto_page': 'goto_page', 'favorites': 'favorites',
    'add_favorite': 'add_favorite_action',
    'remove_favorite': 'remove_favorite_action',
}


@pytest.mark.parametrize('action', sorted(HANDLERS))
def test_action_dispatches_only_its_handler_with_parsed_params(action):
    """Exactly the mapped handler runs, receiving the decoded query params;
    no other handler, no menu, no changelog hook."""
    others = [n for a, n in HANDLERS.items() if a != action]
    with patch.object(routing, HANDLERS[action]) as target, \
         patch.object(routing, 'menu') as menu, \
         patch.object(routing, 'maybe_show_changelog') as hook, \
         patch.multiple(routing, **{n: DEFAULT for n in others}) as rest:
        router('action={0}&series=south+park&what=caf%C3%A9'.format(action))
    target.assert_called_once_with(
        {'action': action, 'series': 'south park', 'what': 'café'})
    for m in rest.values():
        m.assert_not_called()
    menu.assert_not_called()
    hook.assert_not_called()


class TestMenuFallbacks:
    @patch.object(routing, 'maybe_show_changelog')
    @patch.object(routing, 'menu')
    def test_empty_paramstring_shows_menu_then_changelog_hook(self, menu, hook):
        router('')
        menu.assert_called_once_with()
        hook.assert_called_once_with()

    @patch.object(routing, 'maybe_show_changelog')
    @patch.object(routing, 'menu')
    def test_actionless_params_show_menu_without_keyerror_or_hook(self, menu, hook):
        """Stale bookmark like '?foo=bar': params but no 'action' key."""
        router('foo=bar')
        menu.assert_called_once_with()
        hook.assert_not_called()

    @patch.object(routing, 'maybe_show_changelog')
    @patch.object(routing, 'menu')
    def test_unknown_action_shows_menu_without_hook(self, menu, hook):
        router('action=unknown_thing')
        menu.assert_called_once_with()
        hook.assert_not_called()


@pytest.fixture
def refresh():
    with patch('lib.routing.xbmc.executebuiltin') as ex:
        yield ex


class TestSideEffectActions:
    """RunPlugin side-effect actions do the side effect, then refresh the container."""

    @patch('lib.playback.toqueue')
    @patch('lib.api.revalidate', return_value='tok')
    def test_toqueue_queues_then_refreshes(self, _rv, toqueue, refresh):
        router('action=toqueue&toqueue=abc123')
        toqueue.assert_called_once_with('abc123', 'tok')
        refresh.assert_called_once_with('Container.Refresh')

    @patch('lib.playback.toqueue')
    @patch('lib.api.revalidate', return_value=None)
    def test_toqueue_without_token_does_nothing(self, _rv, toqueue, refresh):
        router('action=toqueue&toqueue=abc123')
        toqueue.assert_not_called()
        refresh.assert_not_called()

    @patch('lib.playback.toqueue')
    @patch('lib.api.revalidate', return_value='tok')
    def test_toqueue_without_ident_does_nothing(self, _rv, toqueue, refresh):
        router('action=toqueue')
        toqueue.assert_not_called()
        refresh.assert_not_called()

    @patch('lib.playback.dequeue')
    def test_dequeue_removes_then_refreshes(self, dequeue, refresh):
        router('action=dequeue&dequeue=xyz789')
        dequeue.assert_called_once_with('xyz789')
        refresh.assert_called_once_with('Container.Refresh')

    @patch('lib.cache.removesearch')
    def test_remove_search_removes_then_refreshes(self, remove, refresh):
        router('action=remove_search&remove=avatar')
        remove.assert_called_once_with('avatar')
        refresh.assert_called_once_with('Container.Refresh')

    @pytest.mark.parametrize('action', ['mark_watched', 'mark_unwatched', 'clear_resume'])
    def test_state_actions_apply_to_key_then_refresh(self, action, refresh):
        with patch('lib.state.{0}'.format(action)) as fn:
            router('action={0}&key=ep%3Ashow%7CS01E02'.format(action))
        fn.assert_called_once_with('ep:show|S01E02')
        refresh.assert_called_once_with('Container.Refresh')

    @pytest.mark.parametrize('action', ['mark_watched', 'mark_unwatched', 'clear_resume'])
    def test_state_actions_without_key_do_nothing(self, action, refresh):
        with patch('lib.state.{0}'.format(action)) as fn:
            router('action={0}'.format(action))
        fn.assert_not_called()
        refresh.assert_not_called()

# -*- coding: utf-8 -*-
"""Tests for URL routing dispatch."""
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from lib.routing import router


class TestRouter:
    """Test that router dispatches to correct handlers."""

    @patch('lib.routing.search')
    def test_search_action(self, mock_search):
        router('action=search&what=test')
        mock_search.assert_called_once()
        assert mock_search.call_args[0][0]['action'] == 'search'
        assert mock_search.call_args[0][0]['what'] == 'test'

    @patch('lib.routing.browse_series')
    def test_browse_series_action(self, mock_fn):
        router('action=browse_series&series=south+park&what=south+park')
        mock_fn.assert_called_once()
        assert mock_fn.call_args[0][0]['series'] == 'south park'

    @patch('lib.routing.browse_season')
    def test_browse_season_action(self, mock_fn):
        router('action=browse_season&series=test&season=1')
        mock_fn.assert_called_once()

    @patch('lib.routing.select_version')
    def test_select_version_action(self, mock_fn):
        router('action=select_version&series=test&season=1&episode=5')
        mock_fn.assert_called_once()

    @patch('lib.routing.select_movie_version')
    def test_select_movie_version_action(self, mock_fn):
        router('action=select_movie_version&movie_key=test')
        mock_fn.assert_called_once()

    @patch('lib.routing.play')
    def test_play_action(self, mock_fn):
        router('action=play&ident=abc123&name=test.mkv')
        mock_fn.assert_called_once()

    @patch('lib.routing.download')
    def test_download_action(self, mock_fn):
        router('action=download&ident=abc123')
        mock_fn.assert_called_once()

    @patch('lib.routing.queue')
    def test_queue_action(self, mock_fn):
        router('action=queue')
        mock_fn.assert_called_once()

    @patch('lib.routing.history')
    def test_history_action(self, mock_fn):
        router('action=history')
        mock_fn.assert_called_once()

    @patch('lib.routing.settings')
    def test_settings_action(self, mock_fn):
        router('action=settings')
        mock_fn.assert_called_once()

    @patch('lib.routing.info')
    def test_info_action(self, mock_fn):
        router('action=info&ident=abc')
        mock_fn.assert_called_once()

    @patch('lib.routing.goto_page')
    def test_goto_page_action(self, mock_fn):
        router('action=goto_page&target_url=test')
        mock_fn.assert_called_once()

    @patch('lib.routing.newsearch')
    def test_newsearch_action(self, mock_fn):
        router('action=newsearch')
        mock_fn.assert_called_once()

    @patch('lib.routing.menu')
    def test_unknown_action_falls_to_menu(self, mock_menu):
        router('action=unknown_action')
        mock_menu.assert_called_once()

    @patch('lib.routing.menu')
    def test_empty_params_shows_menu(self, mock_menu):
        router('')
        mock_menu.assert_called_once()

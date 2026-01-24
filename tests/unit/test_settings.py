# -*- coding: utf-8 -*-
"""Tests for settings handling."""
import pytest
import xml.etree.ElementTree as ET


class TestSettingsXML:
    """Test settings.xml configuration."""

    @pytest.fixture
    def settings_xml(self):
        """Load settings.xml."""
        with open('resources/settings.xml', 'r') as f:
            return ET.parse(f).getroot()

    def test_group_movies_no_dependency(self, settings_xml):
        """group_movies should be standalone, no enable dependency."""
        group_movies = None
        for setting in settings_xml.iter('setting'):
            if setting.get('id') == 'group_movies':
                group_movies = setting
                break

        assert group_movies is not None
        assert group_movies.get('enable') is None, \
            "group_movies should not have enable dependency"
        assert group_movies.get('default') == 'true'

    def test_slast_default_empty(self, settings_xml):
        """slast default should be empty string."""
        slast = None
        for setting in settings_xml.iter('setting'):
            if setting.get('id') == 'slast':
                slast = setting
                break

        assert slast is not None
        assert slast.get('default') == '', \
            "slast default should be empty string, not sentinel"

    def test_csfd_series_only_has_enable(self, settings_xml):
        """csfd_series_only should depend on csfd_enabled."""
        csfd_series = None
        for setting in settings_xml.iter('setting'):
            if setting.get('id') == 'csfd_series_only':
                csfd_series = setting
                break

        assert csfd_series is not None
        assert csfd_series.get('enable') == 'eq(-1,true)'

    def test_labelformat_has_enable(self, settings_xml):
        """labelformat should depend on customformat."""
        labelformat = None
        for setting in settings_xml.iter('setting'):
            if setting.get('id') == 'labelformat':
                labelformat = setting
                break

        assert labelformat is not None
        assert labelformat.get('enable') == 'eq(-1,true)'


class TestSettingsReading:
    """Test settings reading via addon."""

    @pytest.fixture
    def mock_addon(self):
        """Get mock addon from conftest."""
        from tests.conftest import get_mock_addon
        return get_mock_addon()

    def test_setting_default_empty(self, mock_addon):
        """Unset setting returns empty string."""
        result = mock_addon.getSetting('nonexistent')
        assert result == ''

    def test_setting_get_set(self, mock_addon):
        """Setting can be stored and retrieved."""
        mock_addon.setSetting('test_key', 'test_value')
        assert mock_addon.getSetting('test_key') == 'test_value'

    def test_setting_overwrite(self, mock_addon):
        """Setting can be overwritten."""
        mock_addon.setSetting('key', 'value1')
        mock_addon.setSetting('key', 'value2')
        assert mock_addon.getSetting('key') == 'value2'

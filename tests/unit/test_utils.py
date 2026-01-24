# -*- coding: utf-8 -*-
"""Tests for utils module."""
import pytest
import sys

# Ensure conftest mocks are loaded first
from tests.conftest import get_mock_addon, reset_mock_addon


class TestSizelize:
    """Test size formatting."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import utils after mocks are ready."""
        from lib import utils
        self.sizelize = utils.sizelize

    def test_bytes(self):
        """Small values show as bytes."""
        assert self.sizelize('100') == '100.0B'
        assert self.sizelize('1023') == '1023.0B'

    def test_kilobytes(self):
        """KB range values."""
        assert self.sizelize('1024') == '1KB'
        assert self.sizelize('2048') == '2KB'
        assert self.sizelize(str(500 * 1024)) == '500KB'

    def test_megabytes(self):
        """MB range values."""
        assert self.sizelize(str(1024 * 1024)) == '1.0MB'
        assert self.sizelize(str(1024 * 1024 * 500)) == '500.0MB'

    def test_gigabytes(self):
        """GB range values."""
        assert self.sizelize(str(1024 * 1024 * 1024)) == '1.0GB'
        assert self.sizelize(str(1024 * 1024 * 1024 * 2)) == '2.0GB'

    def test_none_returns_str(self):
        """None input returns 'None' string."""
        assert self.sizelize(None) == 'None'

    def test_empty_returns_str(self):
        """Empty string returns empty string."""
        assert self.sizelize('') == ''


class TestLabelize:
    """Test label formatting."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup mock and import utils."""
        self.mock_addon = reset_mock_addon()
        from lib import utils
        self.labelize = utils.labelize
        self.utils = utils

    def test_default_format_name_only(self):
        """Default format shows name only."""
        file = {'name': 'movie.mkv', 'size': '1024'}
        result = self.labelize(file)
        assert result == 'movie.mkv'

    def test_custom_format_with_size(self):
        """Custom format can include size."""
        self.mock_addon.setSetting('customformat', 'true')
        self.mock_addon.setSetting('labelformat', '{name} [{size}]')

        file = {'name': 'movie.mkv', 'size': '1024'}
        result = self.labelize(file)
        assert result == 'movie.mkv [1KB]'

    def test_sizelized_field_used(self):
        """Pre-computed sizelized field is used."""
        self.mock_addon.setSetting('customformat', 'true')
        self.mock_addon.setSetting('labelformat', '{name} - {size}')

        file = {'name': 'video.mp4', 'sizelized': '2.5GB'}
        result = self.labelize(file)
        assert result == 'video.mp4 - 2.5GB'

    def test_missing_size_shows_question(self):
        """Missing size shows ? placeholder."""
        self.mock_addon.setSetting('customformat', 'true')
        self.mock_addon.setSetting('labelformat', '{name} ({size})')

        file = {'name': 'unknown.avi'}
        result = self.labelize(file)
        assert result == 'unknown.avi (?)'


class TestGetLabelFormat:
    """Test label format getter."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup mock and import utils."""
        self.mock_addon = reset_mock_addon()
        from lib import utils
        self.utils = utils

    def test_default_format(self):
        """Default format is {name}."""
        result = self.utils.get_label_format()
        assert result == '{name}'

    def test_custom_format_disabled(self):
        """Custom format off returns default."""
        self.mock_addon.setSetting('customformat', 'false')
        self.mock_addon.setSetting('labelformat', 'custom')
        result = self.utils.get_label_format()
        assert result == '{name}'

    def test_custom_format_enabled(self):
        """Custom format on returns custom."""
        self.mock_addon.setSetting('customformat', 'true')
        self.mock_addon.setSetting('labelformat', '{name} - {size}')
        result = self.utils.get_label_format()
        assert result == '{name} - {size}'


class TestGetFilesizeEnabled:
    """Test filesize enabled getter."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup mock and import utils."""
        self.mock_addon = reset_mock_addon()
        from lib import utils
        self.utils = utils

    def test_default_false(self):
        """Default (unset) returns False."""
        result = self.utils.get_filesize_enabled()
        assert result is False

    def test_enabled(self):
        """Enabled returns True."""
        self.mock_addon.setSetting('resultsize', 'true')
        result = self.utils.get_filesize_enabled()
        assert result is True

    def test_disabled(self):
        """Disabled returns False."""
        self.mock_addon.setSetting('resultsize', 'false')
        result = self.utils.get_filesize_enabled()
        assert result is False


class TestSettingsRefresh:
    """Test that settings are refreshed dynamically."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup mock and import utils."""
        self.mock_addon = reset_mock_addon()
        from lib import utils
        self.utils = utils

    def test_label_format_updates(self):
        """Label format reflects setting changes."""
        # Start with default
        assert self.utils.get_label_format() == '{name}'

        # Enable custom
        self.mock_addon.setSetting('customformat', 'true')
        self.mock_addon.setSetting('labelformat', 'NEW: {name}')

        # Should see new format without reimport
        assert self.utils.get_label_format() == 'NEW: {name}'

    def test_filesize_updates(self):
        """Filesize enabled reflects setting changes."""
        # Start with default
        assert self.utils.get_filesize_enabled() is False

        # Enable
        self.mock_addon.setSetting('resultsize', 'true')
        assert self.utils.get_filesize_enabled() is True

        # Disable
        self.mock_addon.setSetting('resultsize', 'false')
        assert self.utils.get_filesize_enabled() is False

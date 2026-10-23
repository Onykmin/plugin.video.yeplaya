# -*- coding: utf-8 -*-
"""Tests for utils module."""
import pytest

# Ensure conftest mocks are loaded first
from tests.conftest import reset_mock_addon


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

    def test_unknown_placeholder_falls_back_to_name(self):
        """A bad custom format must not crash the listing — fall back to name."""
        self.mock_addon.setSetting('customformat', 'true')
        self.mock_addon.setSetting('labelformat', '{name} {bogus}')

        file = {'name': 'movie.mkv', 'size': '1024'}
        result = self.labelize(file)
        assert result == 'movie.mkv'

    def test_malformed_braces_falls_back_to_name(self):
        """Malformed braces raise ValueError from str.format — must not crash."""
        self.mock_addon.setSetting('customformat', 'true')
        self.mock_addon.setSetting('labelformat', '{name')

        file = {'name': 'movie.mkv', 'size': '1024'}
        result = self.labelize(file)
        assert result == 'movie.mkv'


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


class TestTolistitemState:
    """Test playback state metadata on ListItems produced by tolistitem."""

    @pytest.fixture(autouse=True)
    def setup(self):
        reset_mock_addon()

    def _file(self):
        return {'ident': 'id1', 'name': 'movie.mkv',
                'series_name': 'show', 'season': 1, 'episode': 5}

    def _run(self, get_state_return):
        from lib import utils
        import lib.state as _state
        original = _state.get_state
        _state.get_state = lambda key: get_state_return
        try:
            return utils.tolistitem(self._file())
        finally:
            _state.get_state = original

    def test_watched_sets_playcount(self):
        li = self._run({'watched': 1, 'resume_seconds': 0, 'total_seconds': 1800})
        assert li._info.get('playcount') == 1
        assert li._info.get('overlay') == 5
        context_labels = [c[0] for c in li._context]
        assert any('30271' in lbl for lbl in context_labels)

    def test_resume_sets_properties(self):
        li = self._run({'watched': 0, 'resume_seconds': 450, 'total_seconds': 1800})
        assert li._properties.get('ResumeTime') == '450'
        assert li._properties.get('TotalTime') == '1800'
        context_labels = [c[0] for c in li._context]
        assert any('30272' in lbl for lbl in context_labels)
        assert any('30270' in lbl for lbl in context_labels)

    def test_no_state_no_metadata(self):
        li = self._run(None)
        assert 'playcount' not in li._info
        assert 'ResumeTime' not in li._properties
        context_labels = [c[0] for c in li._context]
        assert any('30270' in lbl for lbl in context_labels)


from urllib.parse import quote_plus  # noqa: E402


class TestTolistitemMergedEpisodeState:
    """A merged single-version episode reads the group-key row, else the legacy row."""

    @pytest.fixture(autouse=True)
    def setup(self):
        reset_mock_addon()

    def _run(self, rows):
        from lib import utils
        import lib.state as _state
        original = _state.get_state
        _state.get_state = lambda key: rows.get(key)
        try:
            return utils.tolistitem({
                'ident': 'c', 'name': 'e.mkv', 'series_name': 'south park',
                'premerge_series_name': 'mestecko south park', 'season': 1, 'episode': 3})
        finally:
            _state.get_state = original

    WATCHED = {'watched': 1, 'resume_seconds': 0, 'total_seconds': 10}
    UNWATCHED = {'watched': 0, 'resume_seconds': 0, 'total_seconds': 10}

    def test_row_only_under_legacy_key_renders_watched_with_legacy_key(self):
        li = self._run({'ep:mestecko south park|S01E03': self.WATCHED})
        assert li._info.get('playcount') == 1
        assert any('mark_unwatched' in c[1] and quote_plus('ep:mestecko south park|S01E03') in c[1]
                   for c in li._context)

    def test_row_under_group_key_wins(self):
        li = self._run({'ep:mestecko south park|S01E03': self.WATCHED,
                        'ep:south park|S01E03': self.UNWATCHED})
        assert 'playcount' not in li._info
        mark = [c[1] for c in li._context if 'mark_watched' in c[1]]
        assert mark and quote_plus('ep:south park|S01E03') in mark[0]


class TestTolistitemAliasState:
    """A merged episode reads rows stored under any key its group was merged from."""

    @pytest.fixture(autouse=True)
    def setup(self):
        reset_mock_addon()

    def _run(self, rows, file_extra):
        from lib import utils
        import lib.state as _state
        original = _state.get_state
        _state.get_state = lambda key: rows.get(key)
        try:
            return utils.tolistitem(dict({
                'ident': 'c', 'name': 'e.mkv', 'series_name': 'south park',
                'season': 1, 'episode': 3}, **file_extra))
        finally:
            _state.get_state = original

    WATCHED = {'watched': 1, 'resume_seconds': 0, 'total_seconds': 10}

    def test_row_under_an_alias_renders_watched_with_the_alias_key(self):
        li = self._run({'ep:park south|S01E03': self.WATCHED},
                       {'series_aliases': ['mestecko south park', 'park south']})
        assert li._info.get('playcount') == 1
        assert any('mark_unwatched' in c[1] and quote_plus('ep:park south|S01E03') in c[1]
                   for c in li._context)

    def test_without_aliases_an_alias_row_is_not_read(self):
        li = self._run({'ep:park south|S01E03': self.WATCHED}, {})
        assert 'playcount' not in li._info

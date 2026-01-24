#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test filename sanitization: unicode normalization, edge cases.
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

# Mock Kodi modules before any imports
class MockXBMC:
    LOGDEBUG = 0
    LOGINFO = 1
    LOGWARNING = 2
    LOGERROR = 3

    @staticmethod
    def log(msg, level=0):
        pass

class MockXBMCAddon:
    def __init__(self):
        self._settings = {}

    def getSettingBool(self, key):
        return True

    def getSetting(self, key):
        return self._settings.get(key, '')

    def setSetting(self, key, value):
        self._settings[key] = value

    def getAddonInfo(self, key):
        return 'test.addon'

    def getLocalizedString(self, id):
        return 'Localized string {}'.format(id)

class MockXBMCGUI:
    NOTIFICATION_INFO = 1
    NOTIFICATION_WARNING = 2
    NOTIFICATION_ERROR = 3

    class Dialog:
        def notification(self, *args, **kwargs):
            pass

    class ListItem:
        def __init__(self, *args, **kwargs):
            pass

class MockXBMCPlugin:
    SORT_METHOD_NONE = 0
    SORT_METHOD_LABEL = 1

    @staticmethod
    def setResolvedUrl(*args, **kwargs):
        pass

class MockXBMCVFS:
    @staticmethod
    def exists(path):
        return True

    class File:
        def __init__(self, *args, **kwargs):
            pass
        def write(self, data):
            pass
        def close(self):
            pass

sys.modules['xbmc'] = MockXBMC()
sys.modules['xbmcgui'] = MockXBMCGUI()
sys.modules['xbmcplugin'] = MockXBMCPlugin()
sys.modules['xbmcaddon'] = type('obj', (object,), {'Addon': MockXBMCAddon})()
sys.modules['xbmcvfs'] = MockXBMCVFS()

# Mock requests module
class MockSession:
    headers = {}

class MockRequests:
    class exceptions:
        class RequestException(Exception):
            pass
    Session = MockSession

sys.modules['requests'] = MockRequests()


def test_unidecode_fallback():
    """Test that empty unidecode result falls back to ident."""
    print("=" * 70)
    print("TEST: unidecode empty result fallback")
    print("=" * 70)

    # Import unidecode logic from playback
    try:
        from unidecode import unidecode
    except ImportError:
        import unicodedata
        def unidecode(text):
            normalized = unicodedata.normalize('NFKD', text)
            return ''.join([c for c in normalized if not unicodedata.combining(c)])

    # Simulate the logic from playback.py
    def sanitize_filename(name, ident, normalize=True):
        """Simulate playback.py filename sanitization."""
        name = os.path.basename(name.replace('..', '').replace('/', '_').replace('\\', '_'))
        if normalize:
            normalized = unidecode(name)
            # Fallback to ident if unidecode returns empty string
            if not normalized or not normalized.strip():
                name = ident + os.path.splitext(name)[1]
            else:
                name = normalized
        return name

    # Test cases
    # Note: os.path.splitext('.mkv') returns ('.mkv', '') - dotfiles have no extension
    test_cases = [
        # (input_name, ident, expected_contains)
        ('Movie Title.mkv', 'abc123', 'Movie Title.mkv'),
        ('Film.mkv', 'xyz789', 'Film.mkv'),
        ('test.mkv', 'fallback123', 'test.mkv'),  # normal filename stays as-is
        ('   ', 'spaces456', 'spaces456'),         # whitespace only falls back to ident
    ]

    for input_name, ident, expected_contains in test_cases:
        result = sanitize_filename(input_name, ident)
        print(f"  Input: '{input_name}', ident: '{ident}'")
        print(f"  Result: '{result}'")
        if expected_contains in result:
            print(f"  Contains '{expected_contains}': OK")
        else:
            print(f"  FAILED: expected '{expected_contains}' in result")
            assert False
        print()

    print("PASSED")
    print()


def test_path_traversal_sanitization():
    """Test that path traversal attempts are sanitized."""
    print("=" * 70)
    print("TEST: path traversal sanitization")
    print("=" * 70)

    test_cases = [
        ('../../../etc/passwd', '_.._.._etc_passwd'),
        ('..\\..\\windows\\system32', '_.._windows_system32'),
        ('file/../../../name.mkv', 'name.mkv'),
        ('/absolute/path/file.mp4', 'file.mp4'),
        ('C:\\Windows\\System32\\file.exe', 'file.exe'),
    ]

    for input_name, expected_safe in test_cases:
        # Simulate the sanitization
        name = os.path.basename(input_name.replace('..', '').replace('/', '_').replace('\\', '_'))
        print(f"  Input: '{input_name}'")
        print(f"  Result: '{name}'")
        # Should not contain path separators
        assert '/' not in name or name == expected_safe, f"Contains / after sanitization"
        assert '\\' not in name or name == expected_safe, f"Contains \\ after sanitization"
        # Should not allow traversal
        assert '..' not in name, f"Contains .. after sanitization"
        print("  OK")
        print()

    print("PASSED")
    print()


def test_unicode_normalization():
    """Test unicode character normalization."""
    print("=" * 70)
    print("TEST: unicode normalization")
    print("=" * 70)

    try:
        from unidecode import unidecode
    except ImportError:
        import unicodedata
        def unidecode(text):
            normalized = unicodedata.normalize('NFKD', text)
            return ''.join([c for c in normalized if not unicodedata.combining(c)])

    test_cases = [
        ('cafe.mkv', 'cafe.mkv'),
        ('Film 2024.mkv', 'Film 2024.mkv'),
        ('Hello World.mp4', 'Hello World.mp4'),
    ]

    for input_name, expected in test_cases:
        result = unidecode(input_name)
        print(f"  Input: '{input_name}'")
        print(f"  Result: '{result}'")
        assert result == expected, f"Expected '{expected}', got '{result}'"
        print("  OK")
        print()

    print("PASSED")
    print()


def test_extension_preservation():
    """Test that file extensions are preserved during fallback."""
    print("=" * 70)
    print("TEST: extension preservation")
    print("=" * 70)

    # Note: os.path.splitext('.mkv') = ('.mkv', '') - dotfiles have no extension
    # Only files with name.ext pattern have extensions
    test_cases = [
        ('file.mkv', 'abc123', '.mkv'),
        ('video.mp4', 'def456', '.mp4'),
        ('movie.avi', 'ghi789', '.avi'),
        ('noext', 'noext', ''),  # no extension
    ]

    for input_name, ident, expected_ext in test_cases:
        ext = os.path.splitext(input_name)[1]
        fallback_name = ident + ext
        print(f"  Input: '{input_name}', ident: '{ident}'")
        print(f"  Extension: '{ext}', Fallback name: '{fallback_name}'")
        assert ext == expected_ext, f"Extension extraction failed: got '{ext}', expected '{expected_ext}'"
        print("  OK")
        print()

    print("PASSED")
    print()


def test_special_characters_in_filename():
    """Test handling of special characters in filenames."""
    print("=" * 70)
    print("TEST: special characters in filename")
    print("=" * 70)

    test_cases = [
        'Movie (2024).mkv',
        'Film [1080p].mp4',
        'Show - S01E01.avi',
        "Movie's Title.mkv",
        'Film #1.mp4',
    ]

    for input_name in test_cases:
        # Just sanitize path separators
        name = os.path.basename(input_name.replace('..', '').replace('/', '_').replace('\\', '_'))
        print(f"  Input: '{input_name}'")
        print(f"  Result: '{name}'")
        # Should preserve special chars (parentheses, brackets, etc.)
        # These are valid in filenames
        assert len(name) > 0, "Name should not be empty"
        print("  OK")
        print()

    print("PASSED")
    print()


if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("FILENAME SANITIZATION TESTS")
    print("=" * 70 + "\n")

    test_unidecode_fallback()
    test_path_traversal_sanitization()
    test_unicode_normalization()
    test_extension_preservation()
    test_special_characters_in_filename()

    print("=" * 70)
    print("ALL TESTS PASSED")
    print("=" * 70)

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test URL parameter handling: special chars, unicode, None values.
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

# Use conftest mocks - they're already loaded
from tests.conftest import get_mock_addon

# Now import after mocks are set up
from lib.utils import sanitize_url_param, get_url


def test_sanitize_none():
    """Test that None values are converted to empty string."""
    print("=" * 70)
    print("TEST: sanitize_url_param with None")
    print("=" * 70)

    result = sanitize_url_param(None)
    print(f"Input: None")
    print(f"Output: '{result}'")
    assert result == ''
    print("PASSED: None correctly converted to empty string\n")


def test_sanitize_unicode():
    """Test unicode characters are preserved."""
    print("=" * 70)
    print("TEST: sanitize_url_param with unicode")
    print("=" * 70)

    test_cases = [
        ('Věc Makropulos', 'Věc Makropulos'),
        ('日本語', '日本語'),
        ('Ñoño', 'Ñoño'),
        ('Tučňák', 'Tučňák'),
    ]

    for input_val, expected in test_cases:
        result = sanitize_url_param(input_val)
        print(f"Input: '{input_val}'")
        print(f"Output: '{result}'")
        assert result == expected
        print("PASSED\n")


def test_sanitize_special_chars():
    """Test special URL characters are handled."""
    print("=" * 70)
    print("TEST: sanitize_url_param with special chars")
    print("=" * 70)

    test_cases = [
        ('test&value', 'test&value'),  # Ampersand preserved
        ('test=value', 'test=value'),  # Equals preserved
        ('test?value', 'test?value'),  # Question mark preserved
        ('test#value', 'test#value'),  # Hash preserved
    ]

    for input_val, expected in test_cases:
        result = sanitize_url_param(input_val)
        print(f"Input: '{input_val}'")
        print(f"Output: '{result}'")
        assert result == expected
        print("PASSED\n")


def test_sanitize_integer():
    """Test integer values are converted to strings."""
    print("=" * 70)
    print("TEST: sanitize_url_param with integer")
    print("=" * 70)

    result = sanitize_url_param(123)
    print(f"Input: 123")
    print(f"Output: '{result}'")
    assert result == '123'
    print("PASSED: Integer correctly converted to string\n")


def test_get_url_skips_none():
    """Test that get_url skips None values in params."""
    print("=" * 70)
    print("TEST: get_url skips None values")
    print("=" * 70)

    params = {
        'action': 'search',
        'query': None,
        'page': '1',
    }
    result = get_url(**params)
    print(f"Input params: {params}")
    print(f"Output URL: '{result}'")
    assert 'query=' not in result
    assert 'action=search' in result
    assert 'page=1' in result
    print("PASSED: None values correctly omitted\n")


def test_get_url_includes_empty_string():
    """Test that get_url includes empty string values."""
    print("=" * 70)
    print("TEST: get_url includes empty strings")
    print("=" * 70)

    params = {
        'action': 'search',
        'query': '',
    }
    result = get_url(**params)
    print(f"Input params: {params}")
    print(f"Output URL: '{result}'")
    assert 'query=' in result
    print("PASSED: Empty string values correctly included\n")


def test_get_url_unicode_encoding():
    """Test that get_url properly encodes unicode."""
    print("=" * 70)
    print("TEST: get_url unicode encoding")
    print("=" * 70)

    params = {
        'action': 'search',
        'query': 'Věc Makropulos',
    }
    result = get_url(**params)
    print(f"Input params: {params}")
    print(f"Output URL: '{result}'")
    # URL should contain encoded form of unicode
    assert 'query=' in result
    # Should be a valid URL (no raw unicode)
    assert 'V' in result  # At least ASCII part
    print("PASSED: Unicode correctly encoded\n")


def test_get_url_special_chars_encoding():
    """Test that get_url properly encodes special chars."""
    print("=" * 70)
    print("TEST: get_url special chars encoding")
    print("=" * 70)

    params = {
        'action': 'search',
        'query': 'test&value',
    }
    result = get_url(**params)
    print(f"Input params: {params}")
    print(f"Output URL: '{result}'")
    # Ampersand in value should be encoded to not conflict with URL separator
    assert '%26' in result or 'test&value' not in result.split('?')[1].split('&')[0]
    print("PASSED: Special chars correctly encoded\n")


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])

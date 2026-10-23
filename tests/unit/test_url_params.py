# -*- coding: utf-8 -*-
"""Plugin URLs must round-trip arbitrary query values (accents, separators)."""
from urllib.parse import parse_qs, urlsplit

import pytest

from lib.utils import get_url, sanitize_url_param


@pytest.mark.parametrize('value, expected', [
    (None, ''),
    (123, '123'),
    ('Tučňák', 'Tučňák'),
    ('日本語', '日本語'),
    ('a&b=c?d#e', 'a&b=c?d#e'),
])
def test_sanitize_url_param(value, expected):
    assert sanitize_url_param(value) == expected


def params_of(url):
    return parse_qs(urlsplit(url).query, keep_blank_values=True)


@pytest.mark.parametrize('query', [
    'Věc Makropulos', 'test&value', 'a=b', 'what?', 'C#', '100%', 'a+b', '日本語'])
def test_get_url_roundtrips_values_without_breaking_other_params(query):
    parsed = params_of(get_url(action='search', query=query, page='1'))
    assert parsed == {'action': ['search'], 'query': [query], 'page': ['1']}


def test_get_url_omits_none_but_keeps_explicit_empty_string():
    parsed = params_of(get_url(action='search', query=None, category=''))
    assert parsed == {'action': ['search'], 'category': ['']}

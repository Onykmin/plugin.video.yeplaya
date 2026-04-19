#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for leading/inline release-group bracket tag stripping in movie names.

Bug: '[FLE] Inception.2010.mkv' -> canonical '[fle] inception|2010'
     instead of 'inception|2010', splitting identical movies into groups.
Fix: clean_series_name() strips '[...]' in addition to '(...)'.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from lib.parsing import parse_movie_info, clean_series_name


class TestBracketTagStripMovie:
    """parse_movie_info must not let leading/inline bracket tags leak into title."""

    def test_leading_fle_tag(self):
        r = parse_movie_info('[FLE] Inception.2010.mkv')
        assert r is not None
        assert r['title'] == 'inception'
        assert r['year'] == 2010

    def test_leading_yify_tag(self):
        r = parse_movie_info('[YIFY] Matrix.1999.720p.mkv')
        assert r is not None
        assert r['title'] == 'matrix'

    def test_leading_tag_with_quality_suffix(self):
        r = parse_movie_info('[FLE] Avatar.2009.1080p.BluRay.mkv')
        assert r is not None
        assert r['title'] == 'avatar'
        assert r['year'] == 2009

    def test_multiple_leading_tags(self):
        r = parse_movie_info('[FLE][YIFY] Inception.2010.mkv')
        assert r is not None
        assert r['title'] == 'inception'

    def test_inline_bracket_tag(self):
        r = parse_movie_info('Inception [FLE].2010.mkv')
        assert r is not None
        assert r['title'] == 'inception'

    def test_trailing_bracket_tag_after_year(self):
        r = parse_movie_info('Inception.2010.[FLE].mkv')
        assert r is not None
        assert r['title'] == 'inception'

    def test_paren_tag_still_works(self):
        r = parse_movie_info('(Lena) Inception.2010.mkv')
        assert r is not None
        assert r['title'] == 'inception'

    def test_no_tag_unchanged(self):
        r = parse_movie_info('Inception.2010.mkv')
        assert r is not None
        assert r['title'] == 'inception'

    def test_cz_lang_tag_still_handled(self):
        r = parse_movie_info('[CZ] Inception.2010.mkv')
        assert r is not None
        assert r['title'] == 'inception'

    def test_bracket_only_returns_none(self):
        """Bracket tag + bare year ('[FLE] 2012') has no real title -> None."""
        r = parse_movie_info('[FLE] 2012.mkv')
        assert r is None

    def test_clean_series_name_strips_brackets(self):
        assert clean_series_name('[FLE] Inception') == 'inception'
        assert clean_series_name('[FLE][YIFY] Inception') == 'inception'
        assert clean_series_name('Inception [FLE]') == 'inception'

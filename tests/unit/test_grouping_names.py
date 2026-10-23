# -*- coding: utf-8 -*-
"""Name normalisation that decides grouping keys: clean_series_name,
extract_dual_names, parse_movie_info, parse_episode_info and friends, as
input -> output tables. Kodi mocks come from tests/conftest.py.
"""
import time

import pytest

from lib.parsing import (
    clean_series_name, extract_dual_names, extract_season_from_text,
    get_word_set_key, parse_episode_info, parse_movie_info,
)


@pytest.mark.parametrize('raw,key', [
    ('The Walking Dead', 'walking dead'),
    ('A Quiet Place', 'quiet place'),
    ('An American Horror Story', 'american horror story'),
    ('Walking Dead, The', 'walking dead'),
    ('Walking Dead The', 'walking dead'),
    ('The Lord of the Rings', 'lord of rings'),
    # Czech "a" = "and": must survive; trailing a/an is kept too
    ('Tom a Jerry', 'tom a jerry'),
    ('Lilo a Stitch', 'lilo a stitch'),
    ('Quiet Place, A', 'quiet place a'),
    ('A-ha', 'a ha'),
    ('Series Name [CZ]', 'series name'),
    ('[CZ] Series Name', 'series name'),
    ('Series Name (EN)', 'series name'),
    ('Series CZ Name', 'series name'),
    ('Series Name [2020]', 'series name'),
    ('Series Name (2020)', 'series name'),
    ('Series Name 2020', 'series name'),
    ('Series Name 1080p', 'series name'),
    ('Series Name 4K', 'series name'),
    ('Series Name BluRay', 'series name'),
    ('Series Name WEB-DL', 'series name'),
    ('Příliš žluťoučký kůň', 'prilis zlutoucky kun'),
    ('ÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ', 'acdeeinorstuuyz'),
])
def test_clean_series_name(raw, key):
    assert clean_series_name(raw) == key


@pytest.mark.parametrize('raw,names', [
    ('Suits - Kravataci', ('Suits', 'Kravataci')),
    ('Suits / Kravataci', ('Suits', 'Kravataci')),
    ('Kravataci (Suits)', ('Kravataci', 'Suits')),
    ('Tučňák-The Penguin', ('Tučňák', 'The Penguin')),
    ('The Penguin - Tucnak', ('The Penguin', 'Tucnak')),
    ('Suits', None),
    ('multi-word', None),
    ('Sherlock - A Study in Pink', None),
    ('Sherlock - The Blind Banker', None),
    ('Inception / 1080p BluRay', None),
    ('Inception / 2010', None),
    ('Spider-Man - SpiderMan', None),
])
def test_extract_dual_names(raw, names):
    assert extract_dual_names(raw) == names


@pytest.mark.parametrize('filename,title,year', [
    ('Inception.2010.1080p.mkv', 'inception', 2010),
    ('Avatar [2009] x264.mkv', 'avatar', 2009),
    ('The Matrix (1999) BluRay.mkv', 'matrix', 1999),
    ('Death Race 2000 (1975).mkv', 'death race', 1975),
    ('Blade Runner 2049 (2017).mkv', 'blade runner', 2017),
])
def test_parse_movie_info(filename, title, year):
    info = parse_movie_info(filename)
    assert info['year'] == year and title in info['title']


def test_parse_movie_info_dual_names_and_non_movies():
    for name in ('Inception - Počátek (2010) 1080p.mkv', 'Inception / Počátek 2010 1080p.mkv'):
        assert len(parse_movie_info(name)['dual_names']) == 2
    assert parse_movie_info('Inception.2010.1080p.mkv')['dual_names'] is None
    assert parse_movie_info('Some Random File.mkv') is None


@pytest.mark.parametrize('name,cleaned', [
    ('The Office Season 2 - 05.mkv', 'The Office - 05.mkv'),
    ('Babylon 5 Season 2 - 10.mkv', 'Babylon 5 - 10.mkv'),
])
def test_season_text_is_removed_without_eating_episode_number(name, cleaned):
    assert extract_season_from_text(name)[1] == cleaned


def test_word_set_key_is_order_and_repeat_independent():
    assert get_word_set_key('south park') == get_word_set_key('park south') == 'park south'
    assert get_word_set_key('the the office') == 'office the'


def test_pathological_separator_run_parses_quickly():
    bad = 'Movie Title' + ' - . ' * 1400 + 'end'
    start = time.time()
    parse_episode_info(bad)
    parse_movie_info(bad)
    assert time.time() - start < 0.5


@pytest.mark.parametrize('name1,name2,key', [
    ('The Penguin', 'Tučňák', 'penguin|tucnak'),
    ('South Park', 'Městečko South Park', 'mestecko south park'),   # substring -> the longer name
])
def test_dual_canonical_key(name1, name2, key):
    from lib.grouping import _dual_canonical
    assert _dual_canonical(name1, name2)[0] == key


@pytest.mark.parametrize('name1,name2,key', [
    ('Penguin, The', 'Tucnak', 'penguin|tucnak'),
    ('Lost (2004)', 'Ztraceni', 'lost|ztraceni'),
    ('Star Wars II', 'Klonovani utocia', 'klonovani utocia|star wars 2'),
    ('Kill Boy [CZ]', 'Zabij chlapce', 'kill boy|zabij chlapce'),
])
def test_dual_canonical_key_is_cleaned_like_every_series_key(name1, name2, key):
    from lib import grouping
    assert grouping._dual_canonical(name1, name2)[0] == key


@pytest.mark.parametrize('name1,name2', [
    ('Penguin, The', 'Tucnak'),
    ('Lost (2004)', 'Ztraceni'),
    ('Star Wars II', 'Klonovani utocia'),
    ('The Penguin', 'Tučňák'), ('South Park', 'Městečko South Park'),
])
def test_dual_key_is_the_same_with_and_without_csfd(monkeypatch, name1, name2):
    from lib import grouping
    with_csfd = grouping._dual_canonical(name1, name2)[0]
    monkeypatch.setattr(grouping, 'DUAL_NAMES_AVAILABLE', False)
    assert grouping._dual_canonical(name1, name2)[0] == with_csfd



@pytest.mark.parametrize('filename,display', [
    ('Stranger.Things.S01E01.1080p.mkv', 'Stranger Things'),
    ('Show 1x05 CZ.avi', 'Show'),
    ('Mashle - 01.mkv', 'Mashle'),
    ('One.Piece.009.avi', 'One Piece'),
    ('Bleach ep.01.avi', 'Bleach'),
    ('Mashle 2nd Season - 01.mkv', 'Mashle'),
    ('Cobra.Kai.3.S01E01.mkv', 'Cobra Kai 3'),
])
def test_get_display_name_is_the_title_before_the_episode_marker(filename, display):
    from lib.parsing import get_display_name
    assert get_display_name(filename) == display

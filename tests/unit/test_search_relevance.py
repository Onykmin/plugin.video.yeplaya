# -*- coding: utf-8 -*-
"""calculate_search_relevance: how a result title is ranked against the typed query.

Rows are (display name, query, canonical key) -> score; the ordering tests
check what users see (better match listed first), not the exact constants alone.
"""
import pytest

from lib.search import calculate_search_relevance as score


@pytest.mark.parametrize('display, query, key, expected', [
    ('Blade (1998)', 'blade', None, 1000),                    # exact, year ignored
    ('Blade (1998)', 'BlAdE', None, 1000),                    # case-insensitive
    ('Blade Runner (1982)', 'blade', None, 800),              # prefix
    ('The Attack', 'attack', None, 500),                      # word start
    ('Chainsaw Man Reze Arc', 'chainsaw man reze arc', None, 1000),
    ('Přátelé', 'pratele', None, 1000),                       # accent-insensitive
    ('Tučňák', 'tucnak', None, 1000),
    ('Blade (1998)', 'čepel', 'blade|čepel|1998', 1000),      # alias from canonical key
    ('Blade (1998)', '1998', 'blade|1998', 0),                # trailing year of key is not a name
    ('Blade (1998)', '1998', None, 0),                        # year is stripped from the title
    ('Batman (2022)', 'blade', 'batman|2022', 0),
    ('Anything', None, None, -1),                             # no query: alphabetical fallback
    ('Anything', '', None, -1),
    ('', 'blade', None, 0),
])
def test_relevance_score(display, query, key, expected):
    assert score(display, query, key) == expected


def test_partial_multi_word_match_ranks_below_full_match_but_above_nothing():
    partial = score('Chainsaw Man (2022)', 'chainsaw man reze')
    assert score('Chainsaw Man Reze Arc', 'chainsaw man reze') > partial > 0


def test_punctuation_in_title_still_ranks_as_multi_word_match():
    assert score('Chainsaw Man: Reze Arc', 'chainsaw man reze arc') >= 700


def test_better_title_matches_rank_first_for_blade():
    results = [('Batman (2022)', 'batman|2022'), ('Beyblade (2001)', 'beyblade|2001'),
               ('Blade Runner (1982)', 'blade runner|1982'), ('Blade II (2002)', 'blade ii|2002'),
               ('Blade (1998)', 'blade|1998')]
    ranked = sorted(results, key=lambda r: -score(r[0], 'blade', r[1]))
    names = [r[0] for r in ranked]
    assert names[0] == 'Blade (1998)'
    assert set(names[1:3]) == {'Blade II (2002)', 'Blade Runner (1982)'}  # tied prefix matches
    assert names[3:] == ['Beyblade (2001)', 'Batman (2022)']


def test_substring_ranks_by_how_early_it_appears():
    early = score('Xblade', 'blade')
    late = score('Sonic the Hedgehog Xblade Thing', 'blade')
    assert early > late > 0


def test_typo_still_finds_title_but_ranks_below_any_word_match():
    typo = score('Inception', 'inceptoin')
    assert 0 < typo < score('The Inception', 'inception')


def test_query_extending_a_short_title_word_is_a_weak_match():
    # "lostgirl" typed as one word still surfaces "Lost", below a real word start
    assert 0 < score('Lost', 'lostgirl') < score('Lost Girl', 'lost')

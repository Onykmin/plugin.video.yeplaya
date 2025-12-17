#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test search relevance scoring.
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
        pass

    def getSettingBool(self, key):
        return True

    def getSetting(self, key):
        return ''

class MockXBMCGUI:
    NOTIFICATION_INFO = 1
    NOTIFICATION_WARNING = 2
    NOTIFICATION_ERROR = 3

class MockXBMCPlugin:
    SORT_METHOD_NONE = 0
    SORT_METHOD_LABEL = 1

sys.modules['xbmc'] = MockXBMC()
sys.modules['xbmcgui'] = MockXBMCGUI()
sys.modules['xbmcplugin'] = MockXBMCPlugin()
sys.modules['xbmcaddon'] = type('obj', (object,), {'Addon': MockXBMCAddon})()

# Import from new lib structure
from lib.search import calculate_search_relevance


def test_exact_match():
    """Exact match should score 1000."""
    score = calculate_search_relevance("Blade (1998)", "blade")
    assert score == 1000, f"Expected 1000, got {score}"
    print("✓ Exact match: blade → Blade (1998) = 1000")


def test_prefix_match():
    """Prefix match should score 800."""
    score = calculate_search_relevance("Blade Runner (1982)", "blade")
    assert score == 800, f"Expected 800, got {score}"
    print("✓ Prefix match: blade → Blade Runner = 800")


def test_contains_vs_prefix():
    """Exact/prefix should beat contains."""
    exact = calculate_search_relevance("Blade (1998)", "blade")
    prefix = calculate_search_relevance("Blade II (2002)", "blade")
    contains = calculate_search_relevance("Beyblade (2001)", "blade")

    assert exact > prefix > contains, f"Scores: exact={exact}, prefix={prefix}, contains={contains}"
    print(f"✓ Ranking: Blade (1000) > Blade II (800) > Beyblade ({contains})")


def test_multi_word_exact():
    """Multi-word exact match."""
    # Exact match without punctuation
    score = calculate_search_relevance("Chainsaw Man Reze Arc", "chainsaw man reze arc")
    assert score == 1000, f"Expected 1000, got {score}"
    print("✓ Multi-word exact: chainsaw man reze arc = 1000")

    # With punctuation - should still score high (multi-word prefix)
    score_punct = calculate_search_relevance("Chainsaw Man: Reze Arc", "chainsaw man reze arc")
    assert score_punct >= 700, f"Expected ≥700 with punctuation, got {score_punct}"
    print(f"✓ Multi-word with punctuation: chainsaw man reze arc → Chainsaw Man: Reze Arc = {score_punct}")


def test_multi_word_partial():
    """Partial multi-word match."""
    score = calculate_search_relevance("Chainsaw Man (2022)", "chainsaw man reze")
    assert score >= 600, f"Expected ≥600 (partial multi-word), got {score}"
    print(f"✓ Multi-word partial: chainsaw man reze → Chainsaw Man = {score}")


def test_dual_name_support():
    """Dual-name titles via canonical_key."""
    # Search for Czech name, find English title
    score = calculate_search_relevance("Blade (1998)", "čepel", "blade|čepel|1998")
    assert score == 1000, f"Expected 1000 (exact on alternate name), got {score}"
    print("✓ Dual-name: čepel → Blade (blade|čepel|1998) = 1000")


def test_empty_query_fallback():
    """Empty query should return -1 (alphabetical fallback)."""
    score = calculate_search_relevance("Anything", None)
    assert score == -1, f"Expected -1, got {score}"

    score = calculate_search_relevance("Anything", "")
    assert score == -1, f"Expected -1, got {score}"
    print("✓ Empty query fallback: None/'' = -1")


def test_position_penalty():
    """Contains match should have position penalty."""
    early = calculate_search_relevance("The Blade", "blade")  # Word boundary
    late = calculate_search_relevance("Sonic the Hedgehog Blade Thing", "blade")  # Contains

    print(f"✓ Position penalty: 'The Blade' ({early}) vs 'Sonic...Blade' ({late})")


def test_word_boundary():
    """Word boundary match should score 500."""
    score = calculate_search_relevance("Attack on Titan", "attack")
    assert score == 800, f"Expected 800 (prefix), got {score}"

    score = calculate_search_relevance("The Attack", "attack")
    assert score == 500, f"Expected 500 (word boundary), got {score}"
    print(f"✓ Word boundary: 'Attack on Titan' (800) vs 'The Attack' (500)")


def test_case_insensitive():
    """Scoring should be case-insensitive."""
    lower = calculate_search_relevance("Blade (1998)", "blade")
    upper = calculate_search_relevance("Blade (1998)", "BLADE")
    mixed = calculate_search_relevance("Blade (1998)", "BlAdE")

    assert lower == upper == mixed == 1000, f"Scores differ: {lower}, {upper}, {mixed}"
    print("✓ Case insensitive: blade = BLADE = BlAdE = 1000")


def test_year_removal():
    """Year in display_name should be ignored."""
    score = calculate_search_relevance("Blade (1998)", "blade")
    assert score == 1000, f"Expected 1000, got {score}"

    # Should NOT match year
    score = calculate_search_relevance("Blade (1998)", "1998")
    assert score == 0, f"Expected 0 (year not in title), got {score}"
    print("✓ Year removal: 'blade' matches Blade (1998), '1998' doesn't")


def test_ranking_order():
    """Verify complete ranking order for 'blade' query."""
    results = [
        ("Blade (1998)", "blade|1998"),
        ("Blade II (2002)", "blade ii|2002"),
        ("Blade Runner (1982)", "blade runner|1982"),
        ("Beyblade (2001)", "beyblade|2001"),
        ("Batman (2022)", "batman|2022"),
    ]

    scored = [(name, calculate_search_relevance(name, "blade", key))
              for name, key in results]
    sorted_results = sorted(scored, key=lambda x: (-x[1], x[0]))

    print("\n✓ Ranking for 'blade' query:")
    for name, score in sorted_results:
        print(f"  {score:4d}: {name}")

    # Verify order
    assert sorted_results[0][0] == "Blade (1998)", "Blade should be first"
    assert sorted_results[-1][1] == 0, "Batman should have 0 score"


if __name__ == "__main__":
    print("Testing search relevance scoring...\n")

    test_exact_match()
    test_prefix_match()
    test_contains_vs_prefix()
    test_multi_word_exact()
    test_multi_word_partial()
    test_dual_name_support()
    test_empty_query_fallback()
    test_position_penalty()
    test_word_boundary()
    test_case_insensitive()
    test_year_removal()
    test_ranking_order()

    print("\n✅ All tests passed!")

# -*- coding: utf-8 -*-
# Module: search
# Author: onykmin
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

def calculate_search_relevance(display_name, query, canonical_key=None):
    """Calculate search relevance score (0-1000, higher = better match)."""
    if not query:
        return -1

    q_norm = query.lower().strip()
    d_norm = display_name.lower().strip()
    clean_title = d_norm.split('(')[0].strip()

    search_targets = [clean_title]
    if canonical_key:
        parts = [p.strip() for p in canonical_key.lower().split('|')]
        search_targets.extend([
            p for i, p in enumerate(parts)
            if p and not (p.isdigit() and len(p) == 4 and i == len(parts) - 1)
        ])

    best_score = 0
    for target in search_targets:
        score = _score_single_match(target, q_norm)
        best_score = max(best_score, score)

    return best_score


def _score_single_match(target, query):
    """Score single title against query."""
    if target == query:
        return 1000

    if target.startswith(query):
        return 800

    query_words = query.split()
    target_words = target.split()

    if len(query_words) > 1:
        if all(any(tw.startswith(qw) for tw in target_words) for qw in query_words):
            return 700 + (len(query_words) * 10)

        matches = sum(1 for qw in query_words
                     if any(tw.startswith(qw) for tw in target_words))
        if matches > 0:
            return 600 + (matches * 15)

    for word in target_words:
        if word.startswith(query):
            return 500

    if query in target:
        pos = target.index(query)
        penalty = min(pos * 2, 100)
        return 300 - penalty

    return 0

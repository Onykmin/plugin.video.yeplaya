#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Persisted played-episode set for the random episode picker — tmp profile."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import lib.cache as cache

_FILE = 'random_played.json'


@pytest.fixture
def profile(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, '_profile', str(tmp_path))
    return tmp_path


def test_round_trip(profile):
    cache.save_random_played('Show|all', {(1, 2), (3, 4)})
    assert cache.load_random_played('Show|all') == {(1, 2), (3, 4)}


def test_missing_file_is_empty(profile):
    assert cache.load_random_played('Show|all') == set()


def test_scopes_are_isolated(profile):
    cache.save_random_played('Show|all', {(1, 1)})
    cache.save_random_played('Show|2', {(2, 5)})
    cache.save_random_played('Other|all', {(9, 9)})
    assert cache.load_random_played('Show|all') == {(1, 1)}
    assert cache.load_random_played('Show|2') == {(2, 5)}
    assert cache.load_random_played('Other|all') == {(9, 9)}


def test_save_replaces_scope_set(profile):
    cache.save_random_played('Show|all', {(1, 1), (1, 2)})
    cache.save_random_played('Show|all', {(1, 3)})
    assert cache.load_random_played('Show|all') == {(1, 3)}


def test_corrupt_json_is_empty(profile):
    (profile / _FILE).write_text('{not json', encoding='utf8')
    assert cache.load_random_played('Show|all') == set()


def test_non_dict_json_is_empty(profile):
    (profile / _FILE).write_text('[[1, 2]]', encoding='utf8')
    assert cache.load_random_played('Show|all') == set()


def test_bad_items_are_dropped(profile):
    data = {'Show|all': [[1, 2], 'x', [1], [1, 'a'], None, [3, 4, 5], [5, 6]],
            'Bad|all': 'nope'}
    (profile / _FILE).write_text(json.dumps(data), encoding='utf8')
    assert cache.load_random_played('Show|all') == {(1, 2), (5, 6)}
    assert cache.load_random_played('Bad|all') == set()


def test_corrupt_file_is_overwritten_by_save(profile):
    (profile / _FILE).write_text('garbage', encoding='utf8')
    cache.save_random_played('Show|all', {(1, 1)})
    assert cache.load_random_played('Show|all') == {(1, 1)}


def test_clear_removes_only_that_scope(profile):
    cache.save_random_played('Show|all', {(1, 1)})
    cache.save_random_played('Show|2', {(2, 2)})
    cache.clear_random_played('Show|all')
    assert cache.load_random_played('Show|all') == set()
    assert cache.load_random_played('Show|2') == {(2, 2)}


def test_clear_without_file_does_not_raise(profile):
    cache.clear_random_played('Show|all')
    assert cache.load_random_played('Show|all') == set()


def test_write_failure_does_not_raise(profile, monkeypatch):
    def boom(path, text):
        raise OSError('disk full')

    monkeypatch.setattr(cache, 'atomic_write_text', boom)
    cache.save_random_played('Show|all', {(1, 1)})
    cache.clear_random_played('Show|all')
    assert cache.load_random_played('Show|all') == set()

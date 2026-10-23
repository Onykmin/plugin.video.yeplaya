# -*- coding: utf-8 -*-
"""`Name NN - MM` ("Peaky Blinders  02 - 05", "Mashle 05 - 12"): season NN episode MM, or an absolute episode?

Decision: season NN episode MM ONLY when NN <= the highest season the same show has in files that
do not carry this ambiguity (explicit S##E##/##x##/season text/plain absolute); otherwise the
absolute reading (the number stays in the name). The evidence never comes from the ambiguous
files themselves and the result does not depend on input order.

Kodi mocks come from tests/conftest.py.
"""
import random

import pytest

from lib.grouping import group_by_series
from lib.parsing import apply_season_readings, parse_episode_info


def run(names):
    files = [{'name': n, 'ident': 'id%d' % i, 'size': str(1_000_000 + i)} for i, n in enumerate(names)]
    return group_by_series(files)


def layouts(result):
    return {key: {s: sorted(e) for s, e in data['seasons'].items()} for key, data in result['series'].items()}


def explicit(show, seasons, per_season=3):
    return ['%s.S%02dE%02d.mkv' % (show, s, e) for s in range(1, seasons + 1) for e in range(1, per_season + 1)]


def dashed(show, season, episodes):
    return ['%s  %02d - %02d.mkv' % (show, season, e) for e in episodes]


# --- parse level: the file alone cannot decide, it names both readings -------------------------

def test_parser_defaults_to_the_absolute_reading_and_offers_the_season_reading():
    info = parse_episode_info('Peaky Blinders  02 - 05.mkv')
    assert (info['series_name'], info['season'], info['episode']) == ('peaky blinders 02', 1, 5)
    assert info['season_reading'] == {'series_name': 'peaky blinders', 'season': 2}


@pytest.mark.parametrize('name', [
    'Mashle - 01.mkv',                        # no number before the dash
    'Mashle 2nd Season - 01.mkv',             # the season is stated
    'Peaky Blinders S02E05.mkv',              # explicit marker
    'Peaky Blinders 02 05.mkv',               # no dash binding
    'Show 00 - 05.mkv',                       # season 0 is not a season reading
    'Peaky Blinders 123 - 05.mkv',            # three digits are a title number, not a season
])
def test_files_without_the_ambiguity_offer_no_season_reading(name):
    info = parse_episode_info(name)
    assert info is None or 'season_reading' not in info


# --- group level -------------------------------------------------------------------------------

def test_peaky_style_set_collapses_into_one_group():
    names = explicit('Peaky.Blinders', 6, 6) + [n for s in range(1, 7) for n in dashed('Peaky Blinders', s, range(1, 7))]
    result = run(names)
    assert layouts(result) == {'peaky blinders': {s: [1, 2, 3, 4, 5, 6] for s in range(1, 7)}}
    assert result['non_series'] == []
    # both spellings of one episode are versions of it
    assert all(len(v) == 2 for v in result['series']['peaky blinders']['seasons'][3].values())


def test_season_up_to_the_highest_evidenced_season_is_read_as_a_season():
    result = run(explicit('Show.Name', 2) + dashed('Show Name', 2, [7]))
    assert layouts(result) == {'show name': {1: [1, 2, 3], 2: [1, 2, 3, 7]}}


# Several colliding episodes keep the absolute-reading group apart from its base (merge guard,
# _only_collisions), so the key it was read under stays visible.
def test_season_above_the_highest_evidenced_season_stays_absolute():
    result = run(explicit('Mashle', 2) + dashed('Mashle', 5, [1, 2, 3, 4]))
    assert layouts(result) == {'mashle': {1: [1, 2, 3], 2: [1, 2, 3]}, 'mashle 05': {1: [1, 2, 3, 4]}}


def test_no_season_evidence_at_all_stays_absolute():
    result = run(dashed('Spy x Family', 2, [5, 6, 7]))
    assert layouts(result) == {'spy x family 02': {1: [5, 6, 7]}}


def test_evidence_is_the_show_s_own_files_not_another_show():
    result = run(explicit('Other.Show', 6) + dashed('Mashle', 2, [1, 2]))
    assert 'mashle 02' in result['series'] and 'mashle' not in result['series']


def test_ambiguous_files_do_not_vouch_for_each_other():
    # S01 is the only evidence: "02 - 01" and "03 - 01" must not make each other plausible seasons
    result = run(explicit('Show.Name', 1) + dashed('Show Name', 2, [1, 2, 3]) + dashed('Show Name', 3, [1, 2, 3]))
    assert set(result['series']) == {'show name', 'show name 02', 'show name 03'}


def test_plain_absolute_files_are_season_1_evidence():
    result = run(['Mashle - 0%d.mkv' % n for n in (1, 2, 3)] + dashed('Mashle', 1, [1, 2, 3]) + dashed('Mashle', 2, [1, 2, 3]))
    assert layouts(result) == {'mashle': {1: [1, 2, 3]}, 'mashle 02': {1: [1, 2, 3]}}
    assert len(result['series']['mashle']['seasons'][1][1]) == 2


def test_group_records_the_old_key_as_an_alias():
    result = run(explicit('Peaky.Blinders', 3) + dashed('Peaky Blinders', 2, [1]) + dashed('Peaky Blinders', 3, [1]))
    assert result['series']['peaky blinders']['aliases'] == ['peaky blinders 02', 'peaky blinders 03']


@pytest.mark.parametrize('order', ['forward', 'reversed', 'shuffle1', 'shuffle2', 'shuffle3', 'shuffle4'])
def test_result_does_not_depend_on_input_order(order):
    names = (explicit('Peaky.Blinders', 3) + dashed('Peaky Blinders', 2, [4, 5]) + dashed('Peaky Blinders', 3, [6])
             + dashed('Peaky Blinders', 5, [1, 2]) + dashed('Mashle', 2, [1]) + ['Mashle - 04.mkv'])
    forward = run(names)
    if order == 'reversed':
        names = names[::-1]
    elif order.startswith('shuffle'):
        random.Random(order).shuffle(names)
    result = run(names)
    assert layouts(result) == layouts(forward)
    assert {k: v.get('aliases') for k, v in result['series'].items()} == \
        {k: v.get('aliases') for k, v in forward['series'].items()}


# --- the pure decision --------------------------------------------------------------------------

def test_apply_season_readings_is_pure_in_the_evidence_set():
    def info(**kw):
        base = {'is_series': True, 'series_name': 'x', 'season': 1, 'episode': 1}
        return dict(base, **kw)

    def ambiguous():
        return info(series_name='x 02', season_reading={'series_name': 'x', 'season': 2})

    for infos in ([info(season=2), ambiguous()], [ambiguous(), info(season=2)]):
        apply_season_readings(infos)
        picked = next(i for i in infos if i['episode'] == 1 and 'season_reading' in i)
        assert (picked['series_name'], picked['season'], picked['legacy_series_name']) == ('x', 2, 'x 02')
    lone = [ambiguous(), None]
    apply_season_readings(lone)
    assert lone[0]['series_name'] == 'x 02' and lone[0]['season'] == 1

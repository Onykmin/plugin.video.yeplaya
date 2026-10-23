# -*- coding: utf-8 -*-
"""Series grouping behaviour through group_by_series (the public entry used by
search_ui/series_ui via fetch_and_group_series): which series are formed from a
realistic list of Webshare filenames, what is merged, what is deliberately kept apart,
and the season/episode layout.

Kodi mocks come from tests/conftest.py.
"""
import pytest

from lib.grouping import group_by_series


def bug(reason):
    """Known defect on this code base: strict xfail, flips to a failure once fixed."""
    return pytest.mark.xfail(strict=True, reason=reason)


BUG_ODD_MARKER = bug('"Name 2 - 05" (bare season digit before a dashed number) is not recognised by '
                     'parse_episode_info; kept as a known defect by user decision. The S8 rule (lib/parsing.py apply_season_readings) reads NN as a season only when NN <= the highest season of the same show in files without this ambiguity; with no season evidence there is nothing to compare, so NN stays absolute')


def make_files(names, sizes=None):
    """File dicts shaped like todict() output; distinct idents, distinct sizes."""
    return [{'name': n, 'ident': 'id%d' % i,
             'size': str(sizes[i] if sizes else 1_000_000 + i)}
            for i, n in enumerate(names)]


def group(names, **kw):
    return group_by_series(make_files(names), **kw)


def eps(count, title, season=1, first=1):
    return ['%s.S%02dE%02d.mkv' % (title, season, e)
            for e in range(first, first + count)]


def layout(series):
    return {s: sorted(e) for s, e in series['seasons'].items()}


# --------------------------------------------------------------------------
# Naming variants that must end up in ONE series
# --------------------------------------------------------------------------
SAME_SERIES = [
    pytest.param(
        ['South.Park.S01E01.(CZ).mkv', 'South Park - S01E02.mkv', 'South Park CZ S01E03.mkv'],
        'south park', {1: [1, 2, 3]}, id='separators-and-lang-tags'),
    pytest.param(
        ['The.Office.S01E01.1080p.mkv', 'Office S01E02 720p.mkv', 'Office, The S01E03.mkv'],
        'office', {1: [1, 2, 3]}, id='leading-and-trailing-article'),
    pytest.param(
        ['Kravaťáci.S01E01.mkv', 'Kravataci.S01E02.mkv', 'KRAVAŤÁCI.S01E03.mkv'],
        'kravataci', {1: [1, 2, 3]}, id='czech-accents-and-case'),
    pytest.param(
        ['Příběhy.života.S01E01.mkv', 'Pribehy.zivota.S01E02.mkv'],
        'pribehy zivota', {1: [1, 2]}, id='accented-vs-ascii'),
    pytest.param(
        ['Show-Name.S01E01.mkv', 'Show Name S01E02.mkv'],
        'show name', {1: [1, 2]}, id='hyphen-vs-space'),
    pytest.param(
        ['Breaking.Bad.1x05.mkv', 'Breaking.Bad.S01E05.720p.mkv', 'Breaking.Bad.S01E06.mkv'],
        'breaking bad', {1: [5, 6]}, id='NxM-and-SxxExx-markers'),
    pytest.param(
        ['Sherlock - A Study in Pink S01E01.mkv', 'Sherlock - The Blind Banker S01E02.mkv',
         'Sherlock - The Great Game S01E03.mkv'],
        'sherlock', {1: [1, 2, 3]}, id='episode-title-is-not-an-alias'),
    pytest.param(
        ['Westworld 2016 (S01E01).mkv', 'Westworld 2016 (S01E02).mkv'],
        'westworld', {1: [1, 2]}, id='bracketed-marker-beats-year'),
    pytest.param(
        ['Show.S01E01.mkv', 'Show.S02E01.mkv', 'Show.S01E02.mkv', 'Show.S01E123.mkv'],
        'show', {1: [1, 2, 123], 2: [1]}, id='seasons-and-3-digit-episode'),
]


@pytest.mark.parametrize('names,key,expected_layout', SAME_SERIES)
def test_naming_variants_form_one_series(names, key, expected_layout):
    r = group(names)
    assert list(r['series']) == [key]
    assert layout(r['series'][key]) == expected_layout
    assert r['series'][key]['total_episodes'] == sum(len(e) for e in expected_layout.values())
    assert r['movies'] == {} and r['non_series'] == []


def test_display_name_keeps_original_case_and_sequel_number():
    r = group(['Breaking.Bad.S01E01.mkv'])
    assert r['series']['breaking bad']['display_name'] == 'Breaking Bad'
    r = group(eps(2, 'Cobra.Kai.3'))
    assert r['series']['cobra kai 3']['display_name'] == 'Cobra Kai 3'


# --------------------------------------------------------------------------
# Series that look similar but must stay apart
# --------------------------------------------------------------------------
KEEP_APART = [
    pytest.param(eps(2, 'Lost') + eps(3, 'Lost.Girl'),
                 {'lost': 2, 'lost girl': 3}, id='Lost-vs-Lost-Girl'),
    pytest.param(eps(1, 'Lost') + ['Lost.Girl.S03E01.HDTV.x264.mkv'],
                 {'lost': 1, 'lost girl': 1}, id='Lost-vs-Lost-Girl-one-episode-each'),
    pytest.param(['Lost.S01E01.mkv', 'Lost-in-Austen-1x01.avi', 'Lost-in-Austen-1x02.avi',
                  'Lost.Girl.S03E01.HDTV.XviD-AFG.avi'],
                 {'lost': 1, 'lost in austen': 2, 'lost girl': 1}, id='Lost-in-Austen'),
    pytest.param(['Friends.S01E01.mkv', 'Seinfeld.S01E01.mkv'],
                 {'friends': 1, 'seinfeld': 1}, id='unrelated'),
    pytest.param(eps(3, 'Dragon.Ball') + eps(3, 'Dragon.Ball.Z'),
                 {'dragon ball': 3, 'dragon ball z': 3}, id='spinoff-short-suffix'),
    pytest.param(eps(3, 'Dragon.Ball.Z') + eps(3, 'Dragon.Ball.Super'),
                 {'dragon ball z': 3, 'dragon ball super': 3}, id='sibling-spinoffs'),
    pytest.param(eps(3, 'Office') + eps(3, 'Office.US'),
                 {'office': 3, 'office us': 3}, id='both-substantial-short-extra-word'),
    pytest.param(eps(3, 'Stranger.Things') + eps(3, 'Stranger.Thing'),
                 {'stranger things': 3, 'stranger thing': 3}, id='near-names-both-substantial'),
    pytest.param(['C.S.I. New York S01E01.mkv', 'CSI Vegas S01E01.mkv'],
                 {'c s i new york': 1, 'csi vegas': 1}, id='csi-spin-offs'),
]


@pytest.mark.parametrize('names,expected', KEEP_APART)
def test_distinct_series_are_not_merged(names, expected):
    r = group(names)
    assert {k: s['total_episodes'] for k, s in r['series'].items()} == expected


# --------------------------------------------------------------------------
# Series that must be merged
# --------------------------------------------------------------------------
MERGES = [
    pytest.param(eps(2, 'South.Park') + eps(2, 'Mestecko.South.Park', season=2),
                 'south park', {1: [1, 2], 2: [1, 2]}, id='localized-prefix'),
    pytest.param(eps(3, 'South.Park') + eps(3, 'Mestecko.South.Park', first=4),
                 'south park', {1: [1, 2, 3, 4, 5, 6]}, id='localized-prefix-both-substantial'),
    pytest.param(eps(3, 'Sherlock') + eps(2, 'Sherlock.Holmes', first=4),
                 'sherlock', {1: [1, 2, 3, 4, 5]}, id='long-extra-word'),
    pytest.param(eps(2, 'Office') + eps(2, 'Office.US', first=3),
                 'office', {1: [1, 2, 3, 4]}, id='small-groups-substring'),
    pytest.param(eps(3, 'South.Park') + eps(2, 'Park.South', first=4),
                 'south park', {1: [1, 2, 3, 4, 5]}, id='word-order'),
    pytest.param(eps(3, 'Stranger.Things') + ['Stranger.Thing.S01E04.mkv'],
                 'stranger things', {1: [1, 2, 3, 4]}, id='typo-singular'),
    pytest.param(eps(3, 'Jujutsu.Kaisen') + eps(2, 'Jujuts.Kaisen', first=4),
                 'jujutsu kaisen', {1: [1, 2, 3, 4, 5]}, id='typo-missing-letter'),
    pytest.param(['Tučňák S01E01.mkv', 'Penguin S01E02.mkv', 'Penguin - Tučňák S01E03.mkv'],
                 'penguin', {1: [1, 2, 3]}, id='alias-bridge-localized-and-original'),
    pytest.param(['Suits S01E01.mkv', 'Suits S01E02.mkv', 'Kravataci S01E03.mkv',
                  'Suits - Kravataci S01E04.mkv'],
                 'kravataci', {1: [1, 2, 3, 4]}, id='alias-bridge-2'),
]


@pytest.mark.parametrize('names,key,expected_layout', MERGES)
def test_related_names_merge_into_one_series(names, key, expected_layout):
    r = group(names)
    assert list(r['series']) == [key]
    assert layout(r['series'][key]) == expected_layout


def test_merge_is_independent_of_input_order():
    names = eps(2, 'South.Park') + eps(2, 'Park.South', first=3)
    forward = group(names)
    backward = group(list(reversed(names)))
    assert list(forward['series']) == list(backward['series']) == ['south park']
    assert layout(forward['series']['south park']) == layout(backward['series']['south park'])


def test_merged_series_pools_versions_of_the_same_episode_best_first():
    r = group(['Mestecko.South.Park.S01E01.720p.mkv', 'South.Park.S01E01.1080p.BluRay.mkv',
               'Mestecko.South.Park.S01E02.mkv'])
    sp = r['series']['south park']
    assert sp['total_episodes'] == 2
    assert [v['name'] for v in sp['seasons'][1][1]] == [
        'South.Park.S01E01.1080p.BluRay.mkv', 'Mestecko.South.Park.S01E01.720p.mkv']


def test_dual_name_files_join_localized_and_original_series():
    r = group(['The Penguin S01E01 1080p.mkv', 'The Penguin S01E02 720p.mkv',
               'Tučňák S01E01 720p.mkv', 'Tučňák S01E03 1080p.mkv',
               'The Penguin - Tučňák S01E04 1080p.mkv', 'The Penguin S01E01 2160p.mkv'])
    assert len(r['series']) == 1
    s = next(iter(r['series'].values()))
    assert layout(s) == {1: [1, 2, 3, 4]}
    assert len(s['seasons'][1][1]) == 3  # 1080p + 720p + 2160p of E01


def test_scene_style_dual_name_file_forms_single_series():
    # Real Webshare pattern: "Penguin.The-Tucnak_S01E02_..."
    r = group(['Penguin.The-Tucnak_S01E02_.Donasec.1080P.CZdab.mkv',
               'Penguin.The-Tucnak_S01E01_.Po.zavireci.1080P.CZdab.mkv'])
    assert len(r['series']) == 1
    assert layout(next(iter(r['series'].values()))) == {1: [1, 2]}


def test_dotted_dual_name_file_bridges_localized_and_original_series():
    r = group(['The.Penguin.S01E01.1080p.mkv', 'The.Penguin.S01E02.720p.mkv',
               'Tučňák.S01E03.1080p.mkv',
               'The.Penguin.-.Tučňák.S01E04.1080p.mkv'])
    assert len(r['series']) == 1


# Write-side limit (documented, not pinned): the state/favorite identity of a dual group is "penguin"
# or "tucnak" depending on which alias files a fetch returns. The read-side contract is tested in
# tests/unit/test_series_ui_state.py (test_*_of_either_fetch_identity_resolves_in_either_fetch).
STAR_WARS = (eps(3, 'Star.Wars') + eps(4, 'Star.Wars.Rebels') + eps(4, 'Star.Wars.Droids')
             + ['Star Wars - Odboj S01E%02d.mkv' % e for e in (1, 2, 3)]
             + ['Star Wars - Povstalci S01E%02d.mkv' % e for e in (1, 2, 3)])


def test_dual_groups_of_different_shows_never_share_a_state_identity():
    from lib.keys import normalize_series_key
    for names in (STAR_WARS, STAR_WARS[::-1]):
        series = group(names)['series']
        assert sorted(normalize_series_key(k) for k in series) == sorted(
            ['star wars', 'star wars rebels', 'star wars droids', 'odboj', 'povstalci'])
        for key, g in series.items():
            # no alias, and no pre-merge key of a file, reads another group's identity
            others = {normalize_series_key(k) for k in series if k != key} - {normalize_series_key(key)}
            assert not {normalize_series_key(a) for a in g['aliases']} & others
            old_keys = {normalize_series_key(v.get('premerge_series_name') or '')
                        for episodes in g['seasons'].values() for vs in episodes.values() for v in vs}
            assert not old_keys & others


def test_dual_key_keeps_its_order_when_no_other_group_shares_its_identity():
    # no plain "star wars" holding the same episodes, and a later-season collision is no collision
    assert list(group(['Star Wars - Odboj S01E%02d.mkv' % e for e in (1, 2, 3)])['series']) == ['odboj|star wars']
    names = (['Star Wars - Odboj S01E%02d.mkv' % e for e in (1, 2, 3)]
             + ['Star Wars - Povstalci S02E%02d.mkv' % e for e in (1, 2, 3)])
    assert sorted(group(names)['series']) == ['odboj|star wars', 'povstalci|star wars']


def test_language_tag_in_brackets_does_not_change_series_key():
    r = group(['The.Office.S01E01.mkv', 'OFFICE [CZ] S01E04.mkv'])
    assert list(r['series']) == ['office']


def test_number_title_series_key_keeps_the_number():
    r = group(['The.4400.S01E01.mkv'])
    assert '4400' in next(iter(r['series']))


def test_season_marker_in_name_does_not_split_the_series():
    r = group(['Dragon Ball Z - S01 E001 - A (1080p).mkv', 'Dragon Ball Z - S02 E036 - C (1080p).mkv',
               'Spy x Family S3 - 01.mkv', 'Spy.x.Family.S01E01.mkv'])
    assert sorted(r['series']) == ['dragon ball z', 'spy x family']
    assert layout(r['series']['dragon ball z']) == {1: [1], 2: [36]}
    assert layout(next(v for k, v in r['series'].items() if k.endswith('spy x family'))) == {1: [1], 3: [1]}


def test_season_marker_series_keep_their_old_keys_as_aliases():
    r = group(['Dragon Ball Z - S01 E001 - A (1080p).mkv', 'Dragon Ball Z - S02 E036 - C (1080p).mkv',
               'Dragon Ball Z - S02 E037 - D (1080p).mkv', 'Dragon.Ball.Z.S03E01.mkv'])
    assert list(r['series']) == ['dragon ball z']
    assert r['series']['dragon ball z']['aliases'] == ['dragon ball z s01', 'dragon ball z s02']
    assert layout(r['series']['dragon ball z']) == {1: [1], 2: [36, 37], 3: [1]}


def test_title_numbers_that_look_like_a_season_token_stay_in_the_key():
    r = group(['Series S1080 - 08.mkv', 'Seven S7EN - 08.mkv', 'Breaking.Bad.S01.Extra.Making.Of.mkv',
               'Fahrenheit451.mkv', 'Catch22.mkv'])
    assert sorted(r['series']) == ['series s1080', 'seven s7en']   # no season token, so no season 1 split-off


def test_zero_padded_glued_numbers_form_one_series_and_range_files_stay_with_their_first_episode():
    r = group(['Naruto005.mkv', 'Naruto006.mkv', 'Naruto066-067.mkv', 'Naruto 066 CZ.mkv'])
    assert list(r['series']) == ['naruto']
    assert layout(r['series']['naruto']) == {1: [5, 6, 66]}
    assert r['series']['naruto']['aliases'] == ['naruto066']


def test_gapped_marker_beside_a_year_is_an_episode_and_remembers_its_movie_key():
    r = group(['Squid.Game.S03.E01.2025.1080p CZ dabing.mkv', 'Squid.Game.S03.E02.2025.1080p CZ dabing.mkv',
               'Westworld.2016.S01E01.mkv'])
    assert sorted(r['series']) == ['squid game', 'westworld']
    squid = r['series']['squid game']['seasons'][3]
    assert [squid[e][0]['legacy_movie_key'] for e in (1, 2)] == ['squid game s03 e01|2025', 'squid game s03 e02|2025']
    westworld = r['series']['westworld']['seasons'][1][1][0]
    assert 'legacy_movie_key' not in westworld   # a contiguous marker was always a series


def test_site_prefixed_file_stays_in_the_real_series():
    r = group(eps(2, 'True.Detective', season=4) + [
        '7HitMovies.cool - True.Detective.S04E05.720p.[Hin-Eng].WEB-DL.mkv'])
    assert list(r['series']) == ['true detective']
    assert layout(r['series']['true detective']) == {4: [1, 2, 5]}


def test_site_prefixed_files_stay_in_the_real_series():
    r = group(eps(2, 'True.Detective', season=4) + [
        '7HitMovies.cool - True.Detective.S04.E05.720p.[Hin-Eng].WEB-DL.mkv'])
    assert list(r['series']) == ['true detective']
    assert layout(r['series']['true detective']) == {4: [1, 2, 5]}


def test_season_marked_franchise_files_do_not_join_a_different_show():
    """Star Wars Droids/Ewoks ('Star Wars (DROIDS) - S01 E12') used to be the S7 blob blocker."""
    names = (eps(4, 'Star.Wars.Rebels') + eps(4, 'Star.Wars.Rebels', season=2)
             + ['Star Wars (DROIDS) - S01 E%02d - X (1080p).mp4' % n for n in (1, 2, 3)]
             + ['Star Wars (EWOKS) - S01 E%02d - X (1080p).mp4' % n for n in (1, 2, 3)])
    r = group(names)
    assert layout(r['series']['star wars rebels']) == {1: [1, 2, 3, 4], 2: [1, 2, 3, 4]}
    assert sorted(len(v['seasons'][1]) for k, v in r['series'].items() if k != 'star wars rebels') \
        == [3, 3]


def test_typo_variant_does_not_rename_the_merged_series():
    r = group(eps(3, 'Stranger.Things') + ['Stranger.Thing.S01E04.mkv'])
    assert r['series']['stranger things']['display_name'] == 'Stranger Things'


@pytest.mark.parametrize('names,key,display', [
    pytest.param(['One.Piece.%03d.avi' % n for n in (9, 10, 100)], 'one piece', 'One Piece', id='bare-number'),
    pytest.param(['Bleach ep.%02d.avi' % n for n in (1, 2, 3)], 'bleach', 'Bleach', id='ep-prefix'),
    pytest.param(['Mashle - %02d.mkv' % n for n in (1, 2, 3)], 'mashle', 'Mashle', id='dash-number'),
    pytest.param(['Joker.Game.S01E%02d.mkv' % n for n in (1, 2)], 'joker game', 'Joker Game',
                 id='sxxexx'),
])
def test_series_display_name_has_no_episode_number(names, key, display):
    assert group(names)['series'][key]['display_name'] == display


def display_names(names):
    return {k: v['display_name'] for k, v in group(names)['series'].items()}


def test_display_name_is_the_majority_spelling_in_any_order():
    names = eps(8, 'Stranger.Things') + eps(1, 'Stranger.Thing', first=9)
    for order in (names, names[::-1]):
        assert display_names(order)['stranger things'] == 'Stranger Things'


def test_display_vote_counts_survive_several_merges():
    # two typo groups merge into the big one one after the other; a re-vote of
    # just two names per merge would let a 1-file typo win a tie
    names = (eps(5, 'Stranger.Things') + eps(1, 'Stranger.Thing', first=6)
             + eps(1, 'Strange.Things', first=7))
    for order in (names, names[::-1]):
        assert display_names(order) == {'stranger things': 'Stranger Things'}


def test_merged_group_is_named_by_the_majority_of_all_its_files():
    # "Mestecko South Park" (5 files) merges into "south park" (2 files): the
    # name most files carry wins, whichever key survived the merge
    names = eps(2, 'South.Park') + eps(5, 'Mestecko.South.Park', first=3)
    for order in (names, names[::-1]):
        assert display_names(order) == {'south park': 'Mestecko South Park'}


@pytest.mark.parametrize('name,display', [
    ('Spider-Man.S01E01.mkv', 'Spider-Man'),
    ('Mashle 2nd Season - 01.mkv', 'Mashle'),
    ('The.Office.[1.S01E01.mkv', 'The Office'),
])
def test_series_display_name_cleaning(name, display):
    assert list(display_names([name]).values()) == [display]


@pytest.mark.parametrize('names,display', [
    (['Dark-Synthwave-Night-Club', 'Dark-Synthwave-Night-Club'], 'Dark Synthwave Night Club'),
    (['Fight-Club', 'Fight Club', 'Fight Club'], 'Fight Club'),
    (['Fight-Club', 'Fight-Club', 'Fight Club'], 'Fight-Club'),
])
def test_display_vote_treats_hyphen_and_space_spellings_as_one_title(names, display):
    from lib.grouping import pick_best_display_name_from_list
    for order in (names, names[::-1]):
        assert pick_best_display_name_from_list(order) == display


def test_display_name_keeps_title_number_shared_by_every_file():
    r = group(['Cobra.Kai.3.S01E01.mkv', 'Cobra.Kai.3.S01E02.mkv'])
    assert next(iter(r['series'].values()))['display_name'] == 'Cobra Kai 3'


# --------------------------------------------------------------------------
# Versions of an episode: dedup + ordering
# --------------------------------------------------------------------------
def versions_of(names, sizes=None, key=None, season=1, episode=1):
    r = group_by_series(make_files(names, sizes))
    series = r['series'][key or next(iter(r['series']))]
    return [v['name'] for v in series['seasons'][season][episode]], series


def test_best_quality_version_comes_first_not_largest():
    names, series = versions_of(
        ['Show.S01E01.720p.HDTV.mkv', 'Show.S01E01.1080p.BluRay.x265.mkv',
         'Show.S01E01.1080p.WEB-DL.mkv', 'Show.S01E01.2160p.WEB-DL.mkv'],
        sizes=[9_000, 1_000, 2_000, 3_000])
    assert names == ['Show.S01E01.2160p.WEB-DL.mkv', 'Show.S01E01.1080p.BluRay.x265.mkv',
                     'Show.S01E01.1080p.WEB-DL.mkv', 'Show.S01E01.720p.HDTV.mkv']
    assert series['total_episodes'] == 1


def test_equal_quality_is_ordered_by_size_descending():
    names, _ = versions_of(['Show.S01E01.1080p.BluRay.v1.mkv', 'Show.S01E01.1080p.BluRay.v2.mkv',
                            'Show.S01E01.1080p.BluRay.v3.mkv'], sizes=[1, 3, 2])
    assert names == ['Show.S01E01.1080p.BluRay.v2.mkv', 'Show.S01E01.1080p.BluRay.v3.mkv',
                     'Show.S01E01.1080p.BluRay.v1.mkv']


def test_episode_versions_survive_garbage_sizes():
    files = [{'name': 'Show.S01E01.1080p.mkv', 'ident': 'a', 'size': 'N/A'},
             {'name': 'Show.S01E01.720p.mkv', 'ident': 'b', 'size': ['1', '2']},
             {'name': 'Show.S01E01.mkv', 'ident': 'c'},
             {'name': 'Show.S01E01.480p.mkv', 'ident': 'd', 'size': None}]
    versions = group_by_series(files)['series']['show']['seasons'][1][1]
    assert [v['ident'] for v in versions][:2] == ['a', 'b']  # by quality
    assert len(versions) == 4


# --------------------------------------------------------------------------
# What is NOT a series, odd input, relevance filter
# --------------------------------------------------------------------------
def test_empty_and_nameless_input():
    assert group_by_series([]) == {'series': {}, 'movies': {}, 'non_series': []}
    files = [{'name': '', 'ident': 'a'}, {'name': None, 'ident': 'b'}, {'ident': 'c'}]
    r = group_by_series(files)
    assert r['series'] == {} and r['movies'] == {}
    assert len(r['non_series']) == 3


def test_series_movies_and_unknown_files_are_split_apart():
    r = group(['Show.S01E01.mkv', 'Random.Movie.2020.1080p.mkv', 'SomeFile.mkv'])
    assert list(r['series']) == ['show']
    assert list(r['movies']) == ['random movie|2020']
    assert [f['name'] for f in r['non_series']] == ['SomeFile.mkv']


@pytest.mark.parametrize('name', ['Avatar 2.mkv', 'Frozen 2.mkv', 'Top Gun 2.mkv'])
def test_sequel_number_without_marker_is_not_an_episode(name):
    r = group([name])
    assert r['series'] == {}


@pytest.mark.parametrize('names,key,season,episodes', [
    # episode-recognition cases the series/movie gate must keep on the series side
    (['Pokémon Horizons - 104 (VOSTFR-FR 1920x1080 x264).mkv'], 'pokemon horizons', 1, [104]),
    (['[NanakoRaws] Jujutsu Kaisen S3 - 01-02 (TBS 1920x1080 x264 AAC).mkv'], 'jujutsu kaisen', 3, [1]),
    (['Lost S06E17 (CZ).mkv', "Lost S04xE13E14 - There's No Place Like Home Part 2.mkv"], 'lost', 4, [13]),
    pytest.param(['[Naruto-Kun.Hu] Spy x Family 2 - %02d [1080p].mkv' % n for n in (5, 6, 7)], 'spy x family', 2, [5, 6, 7],
                 marks=BUG_ODD_MARKER),
])
def test_episode_files_with_resolution_or_odd_markers_stay_in_their_series(names, key, season, episodes):
    r = group(names)
    assert r['movies'] == {}
    assert sorted(r['series'][key]['seasons'][season]) == episodes


def test_grouped_movies_are_not_repeated_in_flat_list():
    files = [{'name': 'Inception (2010) 1080p.mkv', 'ident': 'm1', 'size': '5'},
             {'name': 'Inception (2010) 720p.mkv', 'ident': 'm2', 'size': '2'},
             {'name': 'inception extra clip'}]
    r = group_by_series(files, search_query='inception')
    assert [v['ident'] for v in r['movies']['inception|2010']['versions']] == ['m1', 'm2']
    assert [f['name'] for f in r['non_series']] == ['inception extra clip']


@pytest.mark.parametrize('names,query,kept', [
    (['Mother S01E01.mkv', 'Her S01E01.mkv'], 'her', ['her']),
    (['C.S.I. New York S01E01.mkv', 'CSI Vegas S01E01.mkv'], 'csi', ['c s i new york', 'csi vegas']),
    (['Friends S01E01.mkv', 'Seinfeld S01E01.mkv'], 'seinfeld', ['seinfeld']),
    (['Přátelé S01E01.mkv', 'Seinfeld S01E01.mkv'], 'pratele', ['pratele']),
    (['Friends S01E01.mkv', 'Seinfeld S01E01.mkv'], 'nomatchatall', ['friends', 'seinfeld']),
])
def test_search_query_drops_only_unrelated_files(names, query, kept):
    r = group(names, search_query=query)
    assert sorted(r['series']) == sorted(kept)


# --------------------------------------------------------------------------
# Merge passes must not depend on the order files arrive from the API
# --------------------------------------------------------------------------
def key_sizes(names):
    return {k: v['total_episodes'] for k, v in group(names)['series'].items()}


ORDER_SENSITIVE_SERIES = [
    pytest.param(
        # 'penguin tucnak' is a superset of both short keys: it must go to the same
        # one whichever comes first (tie on episodes -> lexicographically first key)
        eps(2, 'Penguin') + eps(2, 'Tucnak', first=3) + eps(1, 'Penguin.Tucnak', first=5),
        {'penguin': 3, 'tucnak': 2}, id='substring-target-tie'),
    pytest.param(
        # superset key goes to the larger short group
        eps(1, 'Tucnak') + eps(2, 'Penguin', first=2) + eps(1, 'Penguin.Tucnak', first=5),
        {'penguin': 3, 'tucnak': 1}, id='substring-target-larger-group'),
    pytest.param(
        eps(1, 'Things') + eps(1, 'Thing', first=2) + eps(1, 'Thinks', first=3),
        {'things': 2, 'thinks': 1}, id='similar-tie'),
]


@pytest.mark.parametrize('names,expected', ORDER_SENSITIVE_SERIES)
def test_series_merge_survivor_does_not_depend_on_input_order(names, expected):
    assert key_sizes(names) == key_sizes(list(reversed(names))) == expected


# --------------------------------------------------------------------------
# S7 merge guards: stems, content evidence, declared aliases
# --------------------------------------------------------------------------
def sized(names, sizes):
    series = group_by_series(make_files(names, sizes))['series']
    return {k: v['total_episodes'] for k, v in series.items()}


STUB_CASES = [
    pytest.param(
        # a one-episode stub of the franchise name must not swallow three shows
        eps(1, 'Star.Wars') + eps(3, 'Star.Wars.Rebels') + eps(3, 'Star.Wars.Resistance')
        + eps(3, 'Star.Wars.Droids'),
        {'star wars': 1, 'star wars rebels': 3, 'star wars resistance': 3, 'star wars droids': 3},
        id='stub-of-three-shows'),
    pytest.param(
        eps(2, 'Barbie') + eps(4, 'Policajtka.Barbie') + eps(4, 'Barbie.Mysteries'),
        {'barbie': 2, 'policajtka barbie': 4, 'barbie mysteries': 4},
        id='stub-with-long-extra-words'),
    pytest.param(
        # one-episode neighbours are junk, not sibling shows: no stub, the lone
        # substantial long name still joins the short key as before
        # (Rebels holds other episodes: the same three episodes under both names
        # with different files would be two shows, see the collision tests)
        eps(3, 'Star.Wars') + eps(3, 'Star.Wars.Rebels', first=4) + eps(1, 'Star.Wars.Clone.Wars', season=2)
        + eps(1, 'Star.Wars.Episode', season=3),
        {'star wars': 8},
        id='junk-neighbours-do-not-make-a-stub'),
    pytest.param(
        # the key holding MORE episodes than any long name is the show, not a stub
        eps(6, 'South.Park') + eps(3, 'Mestecko.South.Park', first=7)
        + eps(3, 'South.Park.Zakladna', first=10),
        {'south park': 12},
        id='larger-key-still-absorbs-longer-names'),
]


@pytest.mark.parametrize('names,expected', STUB_CASES)
def test_franchise_stub_does_not_swallow_distinct_shows(names, expected):
    assert key_sizes(names) == key_sizes(list(reversed(names))) == expected


def test_franchise_stub_is_not_bridged_by_dual_keys_that_share_its_name():
    names = (eps(3, 'Star.Wars') + eps(4, 'Star.Wars.Rebels') + eps(4, 'Star.Wars.Droids')
             + ['Star Wars - Odboj S01E%02d.mkv' % e for e in (1, 2, 3)]
             + ['Star Wars - Povstalci S01E%02d.mkv' % e for e in (1, 2, 3)])
    got = key_sizes(names)
    assert got == key_sizes(list(reversed(names)))
    # the dual groups collide with the stub on S01E01-03: each keeps its own name last (state identity)
    assert sorted(got) == ['star wars', 'star wars droids', 'star wars rebels',
                           'star wars|odboj', 'star wars|povstalci']


def test_plain_name_shared_by_two_dual_keys_still_bridges_without_plain_siblings():
    # Czech and Slovak alias of one show: no different shows hide behind the name
    names = (eps(2, 'Big.Bang.Theory')
             + ['Big Bang Theory - Teorie velkeho tresku S01E%02d.mkv' % e for e in (3, 4, 5)]
             + ['Big Bang Theory - Teoria velkeho tresku S01E%02d.mkv' % e for e in (6, 7, 8)])
    got = key_sizes(names)
    assert got == key_sizes(list(reversed(names)))
    assert list(got.values()) == [8]


SHARED = [1_000_000, 2_000_000, 3_000_000]


@pytest.mark.parametrize('base,other', [
    pytest.param('Game.of.Thrones', 'Game.of.Thrones.Hra.o.Truny'),
    pytest.param('Suits', 'Suits.Kravataci')])
def test_same_episodes_at_same_size_under_two_names_are_one_show(base, other):
    names = eps(3, base) + eps(3, other)
    got = sized(names, SHARED + SHARED)
    assert got == sized(list(reversed(names)), list(reversed(SHARED + SHARED)))
    assert got == {base.lower().replace('.', ' '): 3}


@pytest.mark.parametrize('sizes', [
    pytest.param(SHARED + [4_000_000, 5_000_000, 6_000_000], id='no-shared-size'),
    pytest.param(SHARED + [1_000_000, 5_000_000, 6_000_000], id='only-one-shared-size'),
    pytest.param([0, 0, 0, 0, 0, 0], id='unknown-sizes'),
])
def test_without_shared_content_the_guards_still_keep_names_apart(sizes):
    names = eps(3, 'Game.of.Thrones') + eps(3, 'Game.of.Thrones.Hra.o.Truny')
    assert sized(names, sizes) == {'game of thrones': 3, 'game of thrones hra o truny': 3}


def test_alias_declared_in_parentheses_joins_an_absolute_numbered_series():
    names = ['Demon.Slayer.S01E01.mkv', 'Demon.Slayer.S01E02.mkv',
             'Kimetsu no Yaiba (Demon Slayer) - 10 (2160p) CZ titulky.mkv',
             'Kimetsu no Yaiba (Demon Slayer) - 11 (2160p) CZ titulky.mkv']
    got = key_sizes(names)
    assert got == key_sizes(list(reversed(names)))
    assert len(got) == 1 and next(iter(got.values())) == 4


def aliases_and_sizes(names, sizes=None):
    return {k: (v['total_episodes'], v['aliases'])
            for k, v in group_by_series(make_files(names, sizes)).get('series').items()}


MB = 1_000_000


def test_colliding_coordinates_without_a_shared_file_are_two_shows():
    # four coordinates held by both names, no file in common: not one show
    names = eps(4, 'Star.Wars') + eps(4, 'Star.Wars.Rebels')
    got = key_sizes(names)
    assert got == key_sizes(list(reversed(names))) == {'star wars': 4, 'star wars rebels': 4}


def test_one_shared_file_turns_the_collision_into_evidence():
    names = eps(4, 'Star.Wars') + eps(4, 'Star.Wars.Rebels')
    sizes = [MB * n for n in (1, 2, 3, 4, 1, 6, 7, 8)]      # episode 1 is the same file
    got = aliases_and_sizes(names, sizes)
    assert got == aliases_and_sizes(list(reversed(names)), list(reversed(sizes)))
    assert got == {'star wars': (4, ['star wars rebels'])}


def test_a_single_sibling_with_other_episodes_still_joins_the_short_key():
    names = eps(2, 'Star.Wars') + eps(4, 'Star.Wars.Rebels', first=3)
    assert key_sizes(names) == key_sizes(list(reversed(names))) == {'star wars': 6}


def test_franchise_pair_with_distinct_episodes_stays_apart_next_to_a_stub():
    names = (eps(2, 'Star.Wars') + eps(4, 'Star.Wars.Rebels', first=3)
             + eps(4, 'Star.Wars.Resistance', season=2))
    got = aliases_and_sizes(names)
    assert got == aliases_and_sizes(list(reversed(names)))
    assert got == {'star wars': (2, []), 'star wars rebels': (4, []), 'star wars resistance': (4, [])}


def test_dual_key_is_not_held_apart_by_colliding_coordinates():
    # the file names themselves state that the two names are one show
    names = eps(4, 'Penguin') + ['The Penguin 2024 - Tučňák S01E%02d.mkv' % e for e in (1, 2, 3, 4)]
    got = aliases_and_sizes(names)
    assert got == aliases_and_sizes(list(reversed(names)))
    assert got == {'penguin': (4, ['penguin 2024|tucnak', 'penguin|tucnak', 'tucnak'])}


def test_a_key_spelling_out_two_other_keys_is_not_held_apart_by_collisions():
    names = eps(4, 'Hra.na.Olihen') + eps(4, 'Squid.Game') + eps(4, 'Hra.na.Olihen.Squid.Game')
    got = aliases_and_sizes(names)
    assert got == aliases_and_sizes(list(reversed(names)))
    assert got == {'hra na olihen': (4, []), 'squid game': (4, ['hra na olihen squid game'])}


@pytest.mark.parametrize('episodes,shared,merged', [
    pytest.param(12, 3, True, id='three-of-twelve-is-enough'),
    pytest.param(12, 2, False, id='two-shared-files-are-a-coincidence'),
    pytest.param(13, 3, False, id='three-among-thirteen-colliding-are-a-fringe'),
])
def test_same_show_needs_enough_shared_files_and_a_fair_share(episodes, shared, merged):
    base, other = 'Game.of.Thrones', 'Game.of.Thrones.Hra.o.Truny'
    first = [MB * (i + 1) for i in range(episodes)]
    second = first[:shared] + [MB * (100 + i) for i in range(episodes - shared)]
    names = eps(episodes, base) + eps(episodes, other)
    got = sized(names, first + second)
    assert got == sized(list(reversed(names)), list(reversed(first + second)))
    expected = ({'game of thrones': episodes} if merged else
                {'game of thrones': episodes, 'game of thrones hra o truny': episodes})
    assert got == expected


def test_merged_halves_keep_the_absorbed_key_as_alias():
    names = eps(3, 'Suits') + eps(3, 'Suits.Kravataci')
    for order, sizes in ((names, SHARED * 2), (names[::-1], (SHARED * 2)[::-1])):
        assert aliases_and_sizes(order, sizes) == {'suits': (3, ['suits kravataci'])}


def test_split_siblings_do_not_claim_the_franchise_key():
    names = (eps(3, 'Star.Wars') + eps(4, 'Star.Wars.Rebels') + eps(4, 'Star.Wars.Droids')
             + ['Star Wars - Odboj S01E%02d.mkv' % e for e in (1, 2, 3)])
    got = aliases_and_sizes(names)
    assert 'star wars' not in sum((a for _, a in got.values()), [])
    assert got['star wars|odboj'] == (3, ['odboj'])


@pytest.mark.parametrize('name', ['Show.Name (2019) - 01.mkv', 'Show.Name [1080p] - 01.mkv'])
def test_year_or_tag_in_brackets_before_an_absolute_number_is_no_alias(name):
    assert all('|' not in k for k in key_sizes([name, name.replace('01', '02')]))


def test_alias_in_parentheses_keeps_every_old_key_as_alias():
    names = ['Kimetsu no Yaiba (Demon Slayer) - %02d.mkv' % e for e in (10, 11)]
    assert aliases_and_sizes(names) == {
        'demon slayer|kimetsu no yaiba': (2, ['demon slayer', 'kimetsu no yaiba'])}


def test_alias_in_parentheses_keeps_the_plain_key_the_files_had_before():
    # the key a user's rows were stored under before the alias was read
    names = ['[OECUF] Jujutsu Kaisen S3 P1 (Shimetsu Kaiyuu) - %02d [1080p].mkv' % e for e in (5, 6)]
    (key, (_, aliases)), = aliases_and_sizes(names).items()
    assert key == 'jujutsu kaisen p1|shimetsu kaiyuu'   # no season marker, no release tag in the key
    assert '[oecuf] jujutsu kaisen p1|shimetsu kaiyuu' in aliases   # the key csfd_scraper built
    assert 'jujutsu kaisen s3 p1' in aliases
    assert 'jujutsu kaisen p1' in aliases


def test_collisions_only_in_later_seasons_are_a_continuation_not_a_spinoff():
    # a distinct show or spinoff numbers from S01; "The Culling Game S03E01" does not
    names = eps(4, 'Jujutsu.Kaisen', season=3) + eps(4, 'Jujutsu.Kaisen.Culling.Game', season=3)
    got = aliases_and_sizes(names)
    assert got == aliases_and_sizes(list(reversed(names)))
    assert got == {'jujutsu kaisen': (4, ['jujutsu kaisen culling game'])}


def test_en_dash_subtitle_does_not_split_the_series():
    names = (['Peaky Blinders \u2013 Gangy z Birminghamu S01E%02d.mkv' % e for e in (1, 2, 3)]
             + eps(3, 'Peaky.Blinders', first=4))
    # rows stored under the old key (it kept the text after the dash) still resolve
    assert aliases_and_sizes(names) == {
        'peaky blinders': (6, ['peaky blinders \u2013 gangy z birminghamu'])}


def test_tiny_franchise_key_is_not_aliased_onto_a_sibling_by_similarity():
    # "barbie" (one episode) is not a typo of the junk key "barbie a"
    names = (eps(1, 'Barbie') + eps(4, 'Policajtka.Barbie') + eps(4, 'Barbie.Mysteries')
             + eps(4, 'Barbie.A', season=2))
    got = aliases_and_sizes(names)
    assert got == aliases_and_sizes(list(reversed(names)))
    assert got['barbie'] == (1, []) and got['barbie a'] == (4, [])


def _corpus_group_names(query):
    """{group key: file names} of the recorded API response for one query."""
    from tests.integration.test_baseline_regression import run_pipeline
    return {key: [v['name'] for eps in data['seasons'].values() for vs in eps.values() for v in vs]
            for key, data in run_pipeline(query)['series'].items()}


def _groups_with(groups, *needles):
    spaced = {key: [name.lower().replace('.', ' ') for name in names] for key, names in groups.items()}
    return {key for key, names in spaced.items()
            if all(any(n.lower() in name for name in names) for n in needles)}


@pytest.mark.parametrize('query,shows', [
    pytest.param('star wars', ['Star Wars Rebels', 'Star Wars Resistance', 'Star Wars Forces of Destiny',
                               'Star Wars Droids', 'Star Wars Dobrodru', 'Star Wars nTales'],
                 id='star-wars'),
    pytest.param('barbie', ['Barbie Mysteries', 'Policajtka', 'A Touch of Magic'], id='barbie'),
])
def test_recorded_franchise_shows_are_not_merged_into_one_group(query, shows):
    groups = _corpus_group_names(query)
    for i, a in enumerate(shows):
        assert _groups_with(groups, a), a
        for b in shows[i+1:]:
            assert not _groups_with(groups, a, b), (a, b)


@pytest.mark.parametrize('query,needles', [
    pytest.param('game of thrones', ('Game of Thrones S0', 'Hra-o-truny'), id='game-of-thrones'),
    pytest.param('suits', ('Suits S0', 'Krava'), id='suits'),
    pytest.param('demon slayer', ('Demon Slayer S01E01', 'Kimetsu no Yaiba (Demon Slayer)'),
                 id='demon-slayer'),
])
def test_recorded_split_shows_form_one_group(query, needles):
    groups = _corpus_group_names(query)
    assert all(_groups_with(groups, n) for n in needles), needles
    assert _groups_with(groups, *needles), needles


# --- pipeline invariants (S3): per-file state identity and the one dedup rule ---

def _south_park_files():
    return [{'name': 'South.Park.S01E01.mkv', 'ident': 'a', 'size': '1'},
            {'name': 'South.Park.S01E02.mkv', 'ident': 'b', 'size': '2'},
            {'name': 'Mestecko.South.Park.S01E03.mkv', 'ident': 'c', 'size': '3'}]


def test_merged_episode_files_carry_their_final_group_key_as_series_name():
    from lib.state import state_key_for
    files = _south_park_files()
    r = group_by_series(files)
    assert list(r['series']) == ['south park']
    # a list item built from the file must read the same state row that play() writes
    # (play uses the group key from the URL)
    play_key = state_key_for({'series_name': 'south park', 'season': 1, 'episode': 3})
    assert state_key_for(files[2]) == play_key
    for season in r['series']['south park']['seasons'].values():
        for versions in season.values():
            for v in versions:
                assert v['series_name'] == 'south park'


def test_unmerged_episode_keeps_its_own_series_name():
    files = [{'name': 'Lost.S01E01.mkv', 'ident': 'a', 'size': '1'}]
    group_by_series(files)
    assert files[0]['series_name'] == 'lost'


@pytest.mark.parametrize('same_ident,expected', [(False, ['a', 'b']), (True, ['a'])])
def test_same_name_and_size_dedup_follows_ident_for_series_episodes(same_ident, expected):
    files = [{'name': 'Show.S01E01.1080p.mkv', 'ident': 'a', 'size': '100'},
             {'name': 'Show.S01E01.1080p.mkv', 'ident': 'a' if same_ident else 'b', 'size': '100'}]
    r = group_by_series(files)
    versions = r['series']['show']['seasons'][1][1]
    assert sorted(v['ident'] for v in versions) == expected


# --------------------------------------------------------------------------
# S5a: merges are order-free and every group lists the keys it was merged from
# --------------------------------------------------------------------------
def aliases_of(names):
    return {k: v['aliases'] for k, v in group(names)['series'].items()}


def test_unmerged_group_has_empty_aliases():
    assert aliases_of(eps(2, 'Lost') + eps(2, 'Dexter')) == {'lost': [], 'dexter': []}


@pytest.mark.parametrize('names,expected', [
    pytest.param(eps(2, 'South.Park') + eps(1, 'Mestecko.South.Park', first=3),
                 {'south park': ['mestecko south park']}, id='substring'),
    pytest.param(eps(3, 'South.Park') + eps(2, 'Park.South', first=4),
                 {'south park': ['park south']}, id='word-order'),
    pytest.param(eps(3, 'Stranger.Things') + ['Stranger.Thing.S01E04.mkv'],
                 {'stranger things': ['stranger thing']}, id='typo'),
    pytest.param(['Tučňák S01E01.mkv', 'Penguin S01E02.mkv', 'Penguin - Tučňák S01E03.mkv'],
                 {'penguin': ['penguin|tucnak', 'tucnak']}, id='dual-with-normalized-form'),
    pytest.param(eps(1, 'Office') + eps(1, 'Office.US', first=2) + eps(1, 'Us.Office', first=3),
                 {'office': ['office us', 'us office']}, id='survivors-of-two-passes-accumulate'),
])
def test_merged_group_lists_every_pre_merge_key(names, expected):
    for order in (names, names[::-1]):
        assert aliases_of(order) == expected


def test_alias_of_a_merged_group_includes_keys_merged_into_its_losers():
    # 'park south' merges into 'south park' (word order), which absorbs the
    # localized key: the chain's earlier loser stays an alias of the final key
    names = eps(3, 'South.Park') + eps(2, 'Park.South', first=4) + eps(1, 'Mestecko.Park.South', first=6)
    for order in (names, names[::-1]):
        assert aliases_of(order) == {'south park': ['mestecko park south', 'park south']}


def test_dual_keys_sharing_a_component_do_not_depend_on_input_order():
    import itertools
    names = (eps(2, 'Odboj - Star Wars') + eps(2, 'Povstalci - Star Wars', first=3)
             + eps(1, 'Star Wars', first=5))
    results = {tuple(sorted((k, v['total_episodes']) for k, v in group(list(p))['series'].items()))
               for p in itertools.permutations(names)}
    # the shared stub joins exactly one dual group (the better-ordered one); the
    # two dual groups are not merged with each other
    assert results == {(('odboj|star wars', 3), ('povstalci|star wars', 2))}


def test_merge_result_is_a_fixpoint():
    from lib.grouping import (merge_substring_series, merge_word_order_series,
                              merge_dual_canonical_series, merge_similar_series,
                              merge_same_content_series)
    r = group(eps(3, 'South.Park') + eps(2, 'Park.South', first=4) + eps(1, 'Mestecko.Park.South', first=6)
              + ['Tučňák S01E01.mkv', 'Penguin S01E02.mkv', 'Penguin - Tučňák S01E03.mkv'])
    before = {k: v['total_episodes'] for k, v in r['series'].items()}
    for merge in (merge_substring_series, merge_word_order_series,
                  merge_dual_canonical_series, merge_similar_series,
                  merge_same_content_series):
        r = merge(r)
    assert {k: v['total_episodes'] for k, v in r['series'].items()} == before


def test_versions_carry_their_group_aliases_for_state_lookup():
    r = group(eps(2, 'South.Park') + eps(1, 'Mestecko.South.Park', first=3))
    versions = [v for eps_ in r['series']['south park']['seasons'].values()
                for vs in eps_.values() for v in vs]
    assert versions and all(v['series_aliases'] == ['mestecko south park'] for v in versions)

# -*- coding: utf-8 -*-
"""Movie grouping behaviour through group_movies / group_by_series: which files
become one movie, which stay separate (remakes, sequels, spin-offs), version order,
and display names. Kodi mocks come from tests/conftest.py.
"""
import pytest

from lib.grouping import group_by_series, group_movies


def make_files(names, sizes=None):
    return [{'name': n, 'ident': 'id%d' % i,
             'size': str(sizes[i] if sizes else 1_000_000 + i)}
            for i, n in enumerate(names)]


def movies(names, sizes=None):
    return group_movies(make_files(names, sizes))['movies']


def counts(m):
    return {k: len(v['versions']) for k, v in m.items()}


def numbered(title, year, n, tag):
    return ['%s.%d.%s%d.mkv' % (title, year, tag, i) for i in range(n)]


# --------------------------------------------------------------------------
# Same movie -> one group
# --------------------------------------------------------------------------
SAME_MOVIE = [
    pytest.param(['Inception.2010.1080p.mkv', 'Inception.2010.720p.mkv', 'Inception (2010) 2160p.mkv',
                  'Inception [2010] x264.mkv'],
                 {'inception|2010': 4}, id='year-notations'),
    pytest.param(['Incredibles.2004.1080p.BluRay.x264.mkv', 'The.Incredibles.2004.720p.WEB-DL.mkv',
                  'Incredibles.2004.2160p.4K.mkv'],
                 {'incredibles|2004': 3}, id='with-and-without-article'),
    pytest.param(['Inception - Počátek (2010) 1080p.mkv', 'Inception / Počátek 2010 720p.mkv'],
                 {'inception|pocatek|2010': 2}, id='dual-name-two-separators'),
    pytest.param(['Inception - Počátek (2010) 1080p.mkv', 'Inception (2010) 720p.mkv'],
                 {'inception|2010': 2}, id='dual-name-joins-plain-title'),
    pytest.param(['Blade 2 (2002).avi', 'Blade 2[2002]ArabMoviez.org.avi', 'Blade_2_2002_.avi',
                  'Blade 2 - Blade II (2002) USA Fantasy Cz dab Dvd rip.avi'],
                 {'blade 2|2002': 4}, id='blade-2-real-names'),
    pytest.param(['Blade2.2002.mkv', 'Blade.2.2002.1080p.mkv'],
                 {'blade 2|2002': 2}, id='spaceless-number'),
    pytest.param(['Avatar.2009.1080p.mkv', 'Avatar.Extended.2009.720p.mkv', 'Avatar.Cz.2009.mkv',
                  'Avatar 2009 CZ dabing.avi'],
                 {'avatar|2009': 4}, id='edition-and-language-tags'),
    pytest.param(['Blade.Runner.2049.2017.1080p.mkv', 'Blade.Runner.2017.mkv'],
                 {'blade runner|2017': 2}, id='sequel-number-same-year'),
    pytest.param(numbered('Fast.and.Furious', 2023, 2, 'v') + ['Fast.Furious.2023.mkv'],
                 {'fast and furious|2023': 3}, id='orphan-joins-bigger-group'),
    pytest.param(['Matrix.1999.1080p.mkv', 'Matrix.1999.720p.mkv', 'Matrix.1999.480p.mkv',
                  'Matrix.2000.480p.mkv'],
                 {'matrix|1999': 4}, id='uploader-year-typo-single-file'),
    pytest.param(numbered('Batman', 2002, 3, 'v') + numbered('Batman', 2000, 1, 'w'),
                 {'batman|2002': 4}, id='crossyear-small-into-big'),
    pytest.param(numbered('Batman', 2002, 2, 'v') + numbered('Batman', 2000, 30, 'w'),
                 {'batman|2000': 32}, id='crossyear-lopsided'),
]


@pytest.mark.parametrize('names,expected', SAME_MOVIE)
def test_files_of_one_movie_share_a_group(names, expected):
    assert counts(movies(names)) == expected


# --------------------------------------------------------------------------
# Different movies -> separate groups
# --------------------------------------------------------------------------
DIFFERENT_MOVIES = [
    pytest.param(['Dune.1984.1080p.mkv', 'Dune.2021.1080p.mkv'],
                 {'dune|1984': 1, 'dune|2021': 1}, id='remake-years'),
    pytest.param(['Incredibles.2004.1080p.mkv', 'Incredibles.2.2018.1080p.mkv'],
                 {'incredibles|2004': 1, 'incredibles 2|2018': 1}, id='sequel-other-year'),
    pytest.param(['Alien.2024.mkv', 'Alien.Horror.2024.mkv'],
                 {'alien|2024': 1, 'alien horror|2024': 1}, id='genre-word-is-significant'),
    pytest.param(['Movie.2024.1080p.mkv', 'Movie.Comedy.2024.mkv'],
                 {'movie|2024': 1, 'movie comedy|2024': 1}, id='comedy-word-is-significant'),
    pytest.param(['The.Matrix.Reloaded.2003.mkv', 'The.Matrix.1999.mkv'],
                 {'matrix reloaded|2003': 1, 'matrix|1999': 1}, id='sequel-other-year-the'),
    pytest.param(numbered('Fast.and.Furious', 2023, 2, 'v') + ['Fast.2023.mkv'],
                 {'fast and furious|2023': 2, 'fast|2023': 1}, id='single-word-orphan-stays-alone'),
    pytest.param(numbered('Star.Wars', 1977, 2, 'v') + ['War.1977.mkv'],
                 {'star wars|1977': 2, 'war|1977': 1}, id='War-is-not-Star-Wars'),
    pytest.param(numbered('Batman', 2020, 5, 'v') + numbered('Batman', 2022, 4, 'w'),
                 {'batman|2020': 5, 'batman|2022': 4}, id='crossyear-both-significant'),
    pytest.param(numbered('Batman', 2010, 1, 'v') + numbered('Batman', 2000, 1, 'w'),
                 {'batman|2010': 1, 'batman|2000': 1}, id='year-gap-too-large'),
    pytest.param(['Blade.Runner.2049.2017.1080p.mkv', 'Blade.Runner.2049.2017.720p.mkv',
                  'Blade.Runner.1982.mkv', 'Blade.Runner.1982.720p.mkv'],
                 {'blade runner|2017': 2, 'blade runner|1982': 2}, id='blade-runner-films'),
]


@pytest.mark.parametrize('names,expected', DIFFERENT_MOVIES)
def test_different_movies_stay_separate(names, expected):
    assert counts(movies(names)) == expected


# --------------------------------------------------------------------------
# Versions, display names, classification
# --------------------------------------------------------------------------
def test_versions_are_ordered_by_quality_then_size():
    m = movies(['Inception.2010.720p.mkv', 'Inception.2010.1080p.BluRay.mkv',
                'Inception.2010.1080p.WEB-DL.v2.mkv', 'Inception.2010.1080p.WEB-DL.v1.mkv'],
               sizes=[9_000, 1_000, 3_000, 4_000])
    assert [v['name'] for v in m['inception|2010']['versions']] == [
        'Inception.2010.1080p.BluRay.mkv', 'Inception.2010.1080p.WEB-DL.v1.mkv',
        'Inception.2010.1080p.WEB-DL.v2.mkv', 'Inception.2010.720p.mkv']


def test_duplicate_idents_are_removed_from_a_movie():
    files = [{'name': 'Inception.2010.1080p.mkv', 'ident': 'a', 'size': '1'},
             {'name': 'Inception (2010) 1080p.mkv', 'ident': 'a', 'size': '1'}]
    assert len(group_movies(files)['movies']['inception|2010']['versions']) == 1


@pytest.mark.parametrize('name,display', [
    ('Inception.2010.1080p.mkv', 'Inception'),
    ('Blade -Blade (2008).mkv', 'Blade'),
    ('Matrix.Matrix.1999.mkv', 'Matrix'),
    ('Run.Lola.Run.1998.mkv', 'Run Lola Run'),
    ('New.York.New.York.1977.mkv', 'New York New York'),
    ('Die.Hard.2.Die.Harder.1990.mkv', 'Die Hard 2 Die Harder'),
    # accepted trade-off of the consecutive-duplicate cleanup (artifacts win over "Sing Sing")
    ('Sing.Sing.2024.mkv', 'Sing'),
    ('Death Race 2000 (1975).mkv', 'Death Race 2000'),
    # scene hyphens are separators, a lone hyphen is part of the title
    ('Barbie-a-růžové-balerínky-2013.mkv', 'Barbie a růžové balerínky'),
    ('Spider-Man (2002).mkv', 'Spider-Man'),
    ('Barbie a Kouzelná dvířka-cz dabing 2014.mkv', 'Barbie a Kouzelná dvířka'),
    ('Une femme en feu EN (2019).mkv', 'Une femme en feu'),
    # release tags and an unclosed bracket tail are not part of the title
    ('Blade Runner BRrip CZ dabing 1982.avi', 'Blade Runner'),
    ('Barbie (2023 CZ dabing 1920i).avi', 'Barbie'),
    ('Joker [Joker] 2019 1080p.mkv', 'Joker'),
])
def test_movie_display_name(name, display):
    (m,) = movies([name]).values()
    assert m['display_name'] == display


def test_sibling_movies_keep_distinct_display_names():
    # the bracket tail "(N díl" is the only token separating these groups
    m = movies(['Squid Game Hra na oliheň (%d díl 2021 CZ.avi' % n for n in (1, 2, 3)])
    names = [v['display_name'] for v in m.values()]
    assert len(m) == 3 and len(set(names)) == 3


def test_merged_movie_display_name_prefers_the_title_that_is_the_key():
    # 'Avatar Extended' (3 files) merges into avatar|2009; like the series vote, only
    # titles that normalise to the bucket key vote, so the edition suffix does not
    # rename the group, in either input order.
    names = ['Avatar Extended (2009).mkv'] * 3 + ['Avatar (2009).mkv']
    for order in (names, names[::-1]):
        (m,) = movies(order).values()
        assert len(m['versions']) == 4 and m['display_name'] == 'Avatar'


def test_merged_movie_display_name_votes_by_file_count_among_fitting_titles():
    names = ['Fight Club (1999).mkv'] * 2 + ['Fight-Club (1999).mkv']
    for order in (names, names[::-1]):
        (m,) = movies(order).values()
        assert m['display_name'] == 'Fight Club'


def test_dual_name_movie_display_shows_both_names():
    (m,) = movies(['Inception - Počátek (2010) 1080p.mkv']).values()
    assert 'Inception' in m['display_name'] and 'Počátek' in m['display_name']


@pytest.mark.parametrize('name,year', [
    ('Death Race 2000 (1975).mkv', 1975),
    ('Blade Runner 2049 (2017).mkv', 2017),
    ('Avatar 2009.mkv', 2009),
    ('Pulp Fiction 1994 720p.mkv', 1994),
    ('Dune 2021 4K.mkv', 2021),
])
def test_bracketed_year_wins_over_number_in_title(name, year):
    (m,) = movies([name]).values()
    assert m['year'] == year and m['canonical_key'].endswith('|%d' % year)


def test_only_files_with_a_year_become_movies():
    m = movies(['Inception.2010.1080p.mkv', 'Some.Random.File.mkv', 'README.txt', ''])
    assert list(m) == ['inception|2010']
    assert movies([]) == {}


def test_search_keeps_a_title_glued_to_an_upload_counter():
    r = group_by_series(make_files(['1Dune.2021.V2.MULTi.1080p.BluRay.x264.mkv', 'Matrix.1999.mkv']),
                        search_query='dune')
    assert list(r['movies']) == ['1dune|2021']


def test_resolution_is_not_taken_as_the_release_year():
    assert list(movies(['Joker.2019.1920x1080.BluRay.mkv'])) == ['joker|2019']


def test_movie_with_episode_marker_is_a_series_not_a_movie():
    r = group_by_series(make_files(['Pulp.Fiction.1994.mkv', 'Pulp.Fiction.S01E01.mkv']))
    assert list(r['series']) == ['pulp fiction'] and list(r['movies']) == ['pulp fiction|1994']


# --------------------------------------------------------------------------
# Merge passes must not depend on the order files arrive from the API
# --------------------------------------------------------------------------
ORDER_SENSITIVE_MOVIES = [
    pytest.param(
        # same word set, repeated token: the larger group keeps its key
        ['Gladiator.2000.%dp.mkv' % q for q in (480, 720, 1080)] +
        ['Gladiator - Gladiátor (2000) %dp.mkv' % q for q in (480, 720)],
        {'gladiator|2000': 5}, id='equal-word-set-larger-plain'),
    pytest.param(
        ['Gladiator.2000.%dp.mkv' % q for q in (480, 720)] +
        ['Gladiator - Gladiátor (2000) %dp.mkv' % q for q in (480, 720, 1080)],
        {'gladiator gladiator|2000': 5}, id='equal-word-set-larger-repeated'),
    pytest.param(
        # 'dune 2 cut' is a superset of two incomparable titles: it joins the larger one
        ['Dune.Cut.2024.1080p.mkv'] + ['Dune.2.2024.%dp.mkv' % q for q in (480, 720, 1080)] +
        ['Dune.2.Cut.2024.mkv'],
        {'dune cut|2024': 1, 'dune 2|2024': 4}, id='subset-of-two-targets'),
]


@pytest.mark.parametrize('names,expected', ORDER_SENSITIVE_MOVIES)
def test_movie_merge_survivor_does_not_depend_on_input_order(names, expected):
    forward = counts(movies(names))
    assert counts(movies(list(reversed(names)))) == forward
    assert forward == expected


def test_merged_movie_display_keeps_the_majority_title_with_its_number():
    names = (['Dark.Web.Cicada.3301.2021.1080p.mkv', 'Dark Web Cicada 3301 2021 1080p.BluRay.mkv',
              'Dark.Web.Cicada.3301.2021.cz.sub.mkv', 'Dark Web Cicada 3301 2021 SK titulky.mkv']
             + ['Dark Web Cicada 2021 5.1 sk tit.mkv'])
    for order in (names, names[::-1]):
        (m,) = movies(order).values()
        assert len(m['versions']) == 5 and m['display_name'] == 'Dark Web Cicada 3301'


# --------------------------------------------------------------------------
# S5a: order-free merges, aliases for state/favorites migration
# --------------------------------------------------------------------------
def aliases_of(names):
    return {k: v['aliases'] for k, v in movies(names).items()}


def test_edition_tag_never_renames_the_group_whatever_its_size():
    # the majority rule applies to title numbers and repeated tokens, not to edition tags
    names = ['Avatar.Extended.2009.%dp.mkv' % q for q in (480, 720, 1080)] + ['Avatar.2009.mkv']
    for order in (names, names[::-1]):
        assert counts(movies(order)) == {'avatar|2009': 4}


@pytest.mark.parametrize('names,expected', [
    pytest.param(['Avatar.Extended.2009.1080p.mkv', 'Avatar.2009.mkv'],
                 {'avatar|2009': ['avatar extended|2009']}, id='substring'),
    pytest.param(['Dark.Web.Cicada.3301.2021.%dp.mkv' % q for q in (480, 720, 1080)]
                 + ['Dark.Web.Cicada.2021.mkv'],
                 {'dark web cicada 3301|2021': ['dark web cicada|2021']}, id='survivor-is-the-majority-key'),
    pytest.param(['Blade.2.2002.mkv', 'Blade.2.2002.720p.mkv', 'Blade.2.2000.mkv'],
                 {'blade 2|2002': ['blade 2|2000']}, id='cross-year'),
    pytest.param(['Blade 2 - Blade II (2002) Cz dab Dvd rip.avi', 'Blade 2 (2002).avi', 'Blade 2 (2002) 720p.avi'],
                 {'blade 2|2002': ['blade 2 blade 2|2002', 'blade 2|blade ii|2002', 'blade ii|2002']},
                 id='dual-key-with-normalized-form'),
])
def test_merged_movie_lists_every_pre_merge_key(names, expected):
    for order in (names, names[::-1]):
        assert aliases_of(order) == expected


def test_dual_movie_key_keeps_the_csfd_spelling_it_had_as_an_alias():
    # dual keys used to be cleaned by csfd_scraper ("star wars ii"), now like every key ("star wars 2")
    names = ['Star Wars II - Klonovani utocia (2002) Cz dab.avi', 'Star Wars II (2002).avi']
    for order in (names, names[::-1]):
        assert aliases_of(order) == {'star wars 2|2002': [
            'klonovani utocia|star wars 2|2002', 'klonovani utocia|star wars ii|2002', 'star wars ii|2002']}


def test_unmerged_movie_has_empty_aliases():
    assert aliases_of(['Heat.1995.mkv', 'Alien.1979.mkv']) == {'heat|1995': [], 'alien|1979': []}


def test_orphan_tie_goes_to_the_first_key_not_the_first_file():
    names = ['Big.Fish.Tale.2003.mkv', 'Big.Fish.Tale.2003.720p.mkv',
             'Big.Fish.Story.2003.mkv', 'Big.Fish.Story.2003.720p.mkv', 'Big.Fish.2003.mkv']
    forward = counts(movies(names))
    assert counts(movies(names[::-1])) == forward

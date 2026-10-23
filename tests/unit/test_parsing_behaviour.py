# -*- coding: utf-8 -*-
"""Behaviour tests for lib.parsing public functions, driven by real-world filenames.

Replaces the former test_series_parsing / test_parsing_edge_cases /
test_bracket_tag_stripping / test_absolute_episodes / test_series_with_articles /
test_name_picker files. Each table row: filename -> observable output.
"""

import pytest

from lib.parsing import (
    clean_series_name,
    extract_dual_names,
    extract_language_tag,
    extract_season_from_text,
    parse_episode_info,
    parse_movie_info,
    parse_quality_metadata,
)
from lib.grouping import group_by_series, group_movies


def bug_row(reason, *args):
    """Parametrize row for a known defect: strict xfail, flips to a failure once fixed."""
    return pytest.param(*args, marks=pytest.mark.xfail(strict=True, reason=reason))


BUG_BARE_SEASON = ('parse_episode_info: "Name 2 - 05" (bare season digit before a dashed number) '
                   'stays in the series name and the season stays 1; '
                   'kept as a known defect by user decision. The S8 rule (lib/parsing.py apply_season_readings) reads NN as a season only when NN <= the highest season of the same show in files without this ambiguity; with no season evidence there is nothing to compare, so NN stays absolute')


def _ep(filename):
    info = parse_episode_info(filename)
    return None if info is None else (info['series_name'], info['season'], info['episode'])


# ---------------------------------------------------------------------------
# parse_episode_info: series markers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('filename, expected', [
    # S##E## in scene / Webshare styles
    ('True.Detective.S04E02.Night.Country.Part.2.1080p.AMZN.WEB-DL.DDP5.1.H.264-NTb.mkv', ('true detective', 4, 2)),
    ('true.detective.s01e04.720p.hdtv.x264-killers.mkv', ('true detective', 1, 4)),
    ("True Detective (2014) - S01E07 - After You've Gone (1080p BluRay x265 afm72).mka", ('true detective', 1, 7)),
    ('Show.Name.2020.S01E01.mkv', ('show name', 1, 1)),
    ('Southpark_S18E01_Zafinancuj_Southpark_Si_Southpark_Sám_h265.mkv', ('southpark', 18, 1)),
    ('Lost S06E17 (CZ).mkv', ('lost', 6, 17)),
    # bracketed / dashed markers
    ('Arcane_ League of Legends (S01E01) CZ.mkv', ('arcane league of legends', 1, 1)),
    ('Series [S02E05].mkv', ('series', 2, 5)),
    ('The-Office-S05E09-The-Surplus.avi', ('office', 5, 9)),
    ('Stranger-Thing-S01E08-720p-Titulky-CZ.mkv', ('stranger thing', 1, 8)),
    # marker first
    ('S01E02 Chainsaw Man.mkv', ('chainsaw man', 1, 2)),
    # NxM
    ('South Park 12x14 - Neuvěznitelný.mkv', ('south park', 12, 14)),
    ('Series 1x05.mkv', ('series', 1, 5)),
    ('Show 2x12.mkv', ('show', 2, 12)),
    # boundaries
    ('Series S99E01.mkv', ('series', 99, 1)),
    ('Series S01E999.mkv', ('series', 1, 999)),
    ('Series S00E01.mkv', ('series', 0, 1)),
    ('Series S01E00.mkv', ('series', 1, 0)),
    # multi-episode file -> first episode
    ('Penguin S01E01-E02.mkv', ('penguin', 1, 1)),
    ("Lost S04xE13E14 - There's No Place Like Home Part 2.mkv", ('lost', 4, 13)),
    # episode-title suffix is not part of the series name
    ('Sherlock - A Study in Pink S01E01.mkv', ('sherlock', 1, 1)),
    ('Sherlock \u2013 A Study in Pink S01E01.mkv', ('sherlock', 1, 1)),   # en dash like ' - '
    # leading article dropped, trailing reordered article dropped
    ('The Walking Dead S01E01.mkv', ('walking dead', 1, 1)),
    ('Walking Dead, The S02E03.mkv', ('walking dead', 2, 3)),
    ('The.Office.US.S01E01.mkv', ('office us', 1, 1)),
    ('A Team S01E01.mkv', ('team', 1, 1)),
    # dual-name file keeps both names in the key
    ('Tučňák - The Penguin S01E03.mkv', ('tucnak penguin', 1, 3)),
    # a gap or dot between the season and episode marker is still one marker
    ('Dragon Ball Z - S01 E001 - A (1080p).mkv', ('dragon ball z', 1, 1)),
    ('Suits.S03.E13.Moot.Point.1080p.mkv', ('suits', 3, 13)),
    # ...also with EP, an x, a dotted gap, or SE
    ('Squid.Game.S03.E01.2025.1080p CZ dabing.mkv', ('squid game', 3, 1)),
    ('House of the Dragon (2024) S02 EP01 ORG Hindi 720p HD.mkv', ('house of dragon', 2, 1)),
    ('Dune Prophecy 2024 S01EP02 ORG Hindi Jio 720p HD.mkv', ('dune prophecy', 1, 2)),
    ('Aladinova dobrodružství S1x25 Písečný Don Quijote.mkv', ('aladinova dobrodruzstvi', 1, 25)),
    ("The Office S03X01 Kevin's Loan.mp4", ('office', 3, 1)),
    ('Pokémon SE1 EP035 - The Legend of Dratini.avi', ('pokemon', 1, 35)),
    ('Big.Bang.Theory-07x18 (S07E18) - Choulostivý moment.mpg', ('big bang theory', 7, 18)),  # the earlier marker wins
    # ...but a season token without an episode, or a codec / placeholder lookalike, is no marker
    ('Breaking Bad - S01 Extra - Inside Breaking Bad.mkv', None),
    ('Movie.S01x265.mkv', None),
    ('The.Office.UK.COMPLETE.S0XE01.DVD.PAL.x264.mkv', None),
    # a release-site prefix is not part of the title
    ('7HitMovies.cool - True.Detective.S04.E05.720p.[Hin-Eng].WEB-DL.mkv', ('true detective', 4, 5)),
    ('www.site.org - Show Name S01E02.mkv', ('show name', 1, 2)),
    ('7HitMovies.cool - True.Detective.S04E05.720p.mkv', ('true detective', 4, 5)),
    # ...but not when the dotted token carries the episode marker itself
    ('Akta-X-s07e20-cz.en - Fight Club.avi', ('akta x', 7, 20)),
    # ...but a Title.Case dotted name before the dash is a title, not a site
    ('The.Office - Kancl S01E03.mkv', ('office kancl', 1, 3)),
])
def test_season_episode_markers(filename, expected):
    assert _ep(filename) == expected


# ---------------------------------------------------------------------------
# parse_episode_info: absolute numbering and season text (anime style)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('filename, expected', [
    ('Mashle - 01 CZ TITULKY.mkv', ('mashle', 1, 1)),
    ('[SubsPlease] Mashle - 19 (720p) [hash].mkv', ('mashle', 1, 19)),
    ('[Horriblesubs] Attack on Titan - 25.mkv', ('attack on titan', 1, 25)),
    ('(Lena) Naruto 001 CZ.mkv', ('naruto', 1, 1)),
    ('A7 Mashle 04.mkv', ('a7 mashle', 1, 4)),
    ('mashle ep9.mp4', ('mashle', 1, 9)),
    ('Series.Name - 12.mkv', ('series name', 1, 12)),
    ('Anime Title - 99.mkv', ('anime title', 1, 99)),
    ('Naruto Shippuuden 377 CZ tit.mkv', ('naruto shippuuden', 1, 377)),
    ('One Piece 125.mkv', ('one piece', 1, 125)),
    # season text overrides default season 1
    ('Mashle 2nd Season - 01 CZ.mkv', ('mashle', 2, 1)),
    ('Series Season 3 - 12.mkv', ('series', 3, 12)),
    ('Naruto 1st Season - 05.mkv', ('naruto', 1, 5)),
    # a bare digit after the title is the season when a dashed episode number follows
    bug_row(BUG_BARE_SEASON, '[Naruto-Kun.Hu] Spy x Family 2 - 05 [1080p].mkv', ('spy x family', 2, 5)),
    bug_row(BUG_BARE_SEASON, 'Spy x Family 2 - 107.mkv', ('spy x family', 2, 107)),
    ('Attack on Titan S3 - 11 (Shingeki no Kyojin S3).mkv', ('attack on titan', 3, 11)),
    ('Pokémon S02 102 Kdepak jsi, Pokémone.avi', ('pokemon', 2, 102)),
    ('S01 Chainsaw Man - Extra Clean Ending 12.mkv', ('chainsaw man extra clean ending', 1, 12)),
    # every season text span leaves the name, the first one is the season
    ('Solo Leveling Season 2 -Arise from the Shadow- S2 (Ore dake Level Up na Ken 2nd Season) - 09 [1080p AVC].mkv',
     ('solo leveling arise from shadow', 2, 9)),
    # a single word glued to its zero-padded absolute number: the first number of a range
    ('Naruto006.mkv', ('naruto', 1, 6)),
    ('Naruto066-067.mkv', ('naruto', 1, 66)),
    # 'S3' without a space is season text too
    ('[NanakoRaws] Jujutsu Kaisen S3 - 01-02 (TBS 1920x1080 x264 AAC).mkv', ('jujutsu kaisen', 3, 1)),
    ('Spy x Family S3 Ep 05.mkv', ('spy x family', 3, 5)),
    ('Jujutsu Kaisen S3 48 (WEBv2).mkv', ('jujutsu kaisen', 3, 48)),
])
def test_absolute_episodes(filename, expected):
    assert _ep(filename) == expected


@pytest.mark.parametrize('filename', [
    '',
    '   ',
    'NoSeasonOrEpisode.mkv',
    'Random File Name',
    'Movie - 2021.mkv',        # year, not episode
    'Film - 1999.mp4',
    'Documentary - 720p.mkv',  # resolution, not episode
    'Title - 1080p.mkv',
    'Blade 01.mkv',            # short single word: movie, not episode
    'Avatar 2.mkv',            # sequel number
    'Top Gun 2.mkv',
    'Movie.AC3 5.1.mkv',       # audio channels
    'Show DD5.1 1.mkv',
    'Series 1000.mkv',         # out of 1-999 range
    'Gladiator 2 - 2000.mkv',  # sequel number, then a year
    'Rocky 2 - 720p.mkv',      # sequel number, then a resolution
    'Shrek 2 - 5.1 DTS.mkv',  # sequel number, then audio channels
    'Dune 2 - 10bit.mkv',  # sequel number, then a bit depth
    'Fahrenheit451.mkv',       # glued title number: neither zero-padded nor a range
    'Catch22.mkv',
    'Se7en.mkv',
])
def test_not_an_episode(filename):
    assert parse_episode_info(filename) is None


def test_overlong_filename_still_parses():
    assert _ep('A' * 200 + ' S01E01.mkv') == ('a' * 200, 1, 1)


@pytest.mark.parametrize('filename, season, cleaned', [
    ('Mashle 2nd Season - 01 CZ.mkv', 2, 'Mashle - 01 CZ.mkv'),
    ('Series Season 3 - 05.mkv', 3, 'Series - 05.mkv'),
    ('Show 1st Season - 12.mkv', 1, 'Show - 12.mkv'),
    ('Anime S 2 - 08.mkv', 2, 'Anime - 08.mkv'),
    ('Anime S2 - 08.mkv', 2, 'Anime - 08.mkv'),
    ('Series S1080 - 08.mkv', None, 'Series S1080 - 08.mkv'),
    ('Series S3P1 - 08.mkv', None, 'Series S3P1 - 08.mkv'),
    ('Seven S7EN - 08.mkv', None, 'Seven S7EN - 08.mkv'),
    ('Normal S01E01.mkv', None, 'Normal S01E01.mkv'),
    ('Movie - 2021.mkv', None, 'Movie - 2021.mkv'),
])
def test_extract_season_from_text(filename, season, cleaned):
    assert extract_season_from_text(filename) == (season, cleaned)


# ---------------------------------------------------------------------------
# clean_series_name
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('raw, expected', [
    ('Tučňák', 'tucnak'),
    ('Žízeň', 'zizen'),
    ('Řeka', 'reka'),
    ('Series_Name.With-Separators', 'series name with separators'),
    ('Show (2020) 1080p x265 CZ', 'show'),          # year/quality/codec/lang stripped
    ('Show-Sparks', 'show'),                         # trailing release group
    ('[FLE] Inception', 'inception'),                # bracket tags
    ('[FLE][YIFY] Inception', 'inception'),
    ('Inception [FLE]', 'inception'),
    ('The Walking Dead', 'walking dead'),
    ('Walking Dead, The', 'walking dead'),
    ('A Team', 'team'),
    ('A-ha', 'a ha'),                                # short remainder keeps article
    ('Tom a Jerry', 'tom a jerry'),                  # Czech conjunction 'a' kept
    ('Rocky IV', 'rocky 4'),                         # roman numerals
    ('Part III', 'part 3'),
    ('1883', '1883'),                                # name that is a year survives
    # only plausible release years are stripped; other 4-digit numbers are title text
    ('The.4400', '4400'),
    ('Show 1920x1080', 'show'),                      # pixel size leaves no stray "x"
    ('Show 1883 x', 'show 1883 x'),                  # only 19xx/20xx are release years
    ('Blade Runner 2049', 'blade runner'),           # 20xx stays stripped (re-keying is migration-gated)
    ('Show [2019]', 'show'),
    ('Show 1999 x', 'show x'),
    ('Show 123456 x', 'show 123456 x'),              # digits inside a longer number
])
def test_clean_series_name(raw, expected):
    assert clean_series_name(raw) == expected


def test_clean_series_name_long_article_prefixed():
    result = clean_series_name('The ' + 'Very ' * 50 + 'Long Series')
    assert result.endswith('long series')
    assert not result.startswith('the ')


# ---------------------------------------------------------------------------
# parse_movie_info
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('filename, title, year', [
    ('Inception.2010.1080p.BluRay.x264.mkv', 'inception', 2010),
    ('The Matrix (1999).mkv', 'matrix', 1999),
    ('Avatar - 2009.mkv', 'avatar', 2009),
    # in-title number is not the release year
    ('Blade Runner 2049 (2017).mkv', 'blade runner', 2017),
    ('Blade.Runner.2049.2017.mkv', 'blade runner', 2017),
    ('Death Race 2000 (1975).mkv', 'death race', 1975),
    ('2012.2009.mkv', '2012', 2009),
    ('300.2006.mkv', '300', 2006),
    # leading release-group tags never leak into the title
    ('[FLE] Inception.2010.mkv', 'inception', 2010),
    ('[YIFY] Matrix.1999.720p.mkv', 'matrix', 1999),
    ('[FLE] Avatar.2009.1080p.BluRay.mkv', 'avatar', 2009),
    ('[FLE][YIFY] Inception.2010.mkv', 'inception', 2010),
    ('(Lena) Inception.2010.mkv', 'inception', 2010),
    ('[CZ] Inception.2010.mkv', 'inception', 2010),
    ('7HitMovies.cool - Inception.2010.1080p.mkv', 'inception', 2010),
    # inline / trailing bracket tags
    ('Inception [FLE].2010.mkv', 'inception', 2010),
    ('Inception.2010.[FLE].mkv', 'inception', 2010),
    # a WxH resolution is not a year
    ('Joker.2019.1920x1080.BluRay.mkv', 'joker', 2019),
    # an interlaced/progressive token ('1920i') is not a year
    ('Barbie (2023 CZ dabing 1920i).avi', 'barbie', 2023),
])
def test_movie_title_and_year(filename, title, year):
    info = parse_movie_info(filename)
    assert info is not None
    assert (info['title'], info['year']) == (title, year)


@pytest.mark.parametrize('filename', [
    'Inception.mkv',        # no year
    '[FLE] 2012.mkv',       # only a tag and a bare year: no title
    'Movie 2030.mkv',       # implausible future year
    'Pokémon Horizons - 104 (VOSTFR-FR 1920x1080 x264).mkv',  # resolution, not a year
])
def test_not_a_movie(filename):
    assert parse_movie_info(filename) is None


@pytest.mark.parametrize('filename', [
    '20170919_175892046_Movie.mp4',     # timestamp digits, would be year 2046
    '20170919_175892013_South Park.mp4',
])
def test_timestamp_in_filename_is_not_a_movie(filename):
    assert parse_movie_info(filename) is None


def test_movie_dual_names():
    info = parse_movie_info('Tučňák - The Penguin (2024).mkv')
    assert info['dual_names'] == ('Tučňák', 'The Penguin')
    assert info['year'] == 2024


# ---------------------------------------------------------------------------
# extract_dual_names
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('raw, expected', [
    ('Tučňák - The Penguin', ('Tučňák', 'The Penguin')),
    ('Zootropolis - Zootopia', ('Zootropolis', 'Zootopia')),
    ('Original / Czech', ('Original', 'Czech')),
    ('Czech (Original)', ('Czech', 'Original')),
    ('Czech [Original]', ('Czech', 'Original')),
    ('Name  Other Name', ('Name', 'Other Name')),
    ('The.Penguin.-.Tučňák', ('The Penguin', 'Tučňák')),   # dots/underscores for spaces
    ('The_Penguin_-_Tucnak', ('The Penguin', 'Tucnak')),
    # not aliases
    ('Sherlock - A Study in Pink', None),   # wordy episode title
    ('Batman - The Batman', None),          # same title modulo article
    ('Show - 07', None),                    # episode number
    ('Show.-.07', None),
    ('Show - The Movie', None),             # release-kind label
    ('Show.-.The.Movie', None),
    ('Show - OVA', None),
    ('Spider.Man.-.Spider.Man', None),      # same title
    ('Show - 1080p', None),                 # quality
    ('Inception / 1080p', None),
    ('Inception (2010)', None),             # year
    ('Show (CZ)', None),                    # language tag
    ('Show [CZ]', None),                    # language tag in brackets
    ('Show [SK]', None),
    ('Show - CZ dabing', None),                       # upload tags are not a second title
    ('Dark.Feed.2013-CZ-NOVINKA', None),
    ('Dark-Shadows.CZ', None),                        # the tag's capitals do not make "Shadows" a name
    ('Show - En route', ('Show', 'En route')),        # a real title that merely starts like a code
    ('Show [1080p]', None),
    ('Spider-Man', None),
    ('Chainsaw Man - 07', None),
    ('Series - 06.5', None),
    ('Movie - x264 AAC', None),
    ('Chainsaw Man - 01 (720p) [88C94187]', None),   # hex hash
    ('Avatar [2009]', None),
    ('Inception / Počátek', ('Inception', 'Počátek')),
])
def test_extract_dual_names(raw, expected):
    assert extract_dual_names(raw) == expected


# ---------------------------------------------------------------------------
# parse_quality_metadata: score ordering is what grouping relies on
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('filename, quality, source, codec, audio, score', [
    ('Movie.mkv', None, None, None, None, 50),
    ('Movie.720p.HDTV.mkv', '720p', 'HDTV', None, None, 65),
    ('Movie.480p.DVDRip.XviD.AAC.mkv', '480p', 'DVDRip', 'XviD', 'AAC', 41),
    ('Movie.1080p.WEBRip.x264.AC3.mkv', '1080p', 'WEBRip', 'x264', 'AC3', 85),
    ('Movie.1080p.BluRay.x264.mkv', '1080p', 'BluRay', 'x264', None, 95),
    ('Movie.1080p.Blu-Ray.H.265.DTS-HD.mkv', '1080p', 'BluRay', 'x265', 'DTS-HD', 105),
    ('Movie.4K.WEB-DL.HEVC.DD5.1.mkv', '4k', 'WEB-DL', 'x265', 'DD5.1', 118),
    ('Movie.2160p.BluRay.x265.DTS.mkv', '2160p', 'BluRay', 'x265', 'DTS', 125),
])
def test_quality_metadata(filename, quality, source, codec, audio, score):
    assert parse_quality_metadata(filename) == {
        'quality': quality, 'source': source, 'codec': codec,
        'audio': audio, 'quality_score': score,
    }


@pytest.mark.parametrize('filename, quality', [
    ('Attack.on.Titan.S01E11.Idol.1920x1080.mkv', '1080p'),
    ('Movie 3840x2160 x265.mkv', '2160p'),
    ('Movie.1280x720.mkv', '720p'),
    ('1883-S01E01-Cz Dab-FullHD.mkv', '1080p'),
    ('Squid Game S1E1 FULL HD cz dab.mkv', '1080p'),
    ('Show S01E01 FHD.mkv', '1080p'),
    ('Pláč odevzdanosti1080p CZ Dabing.mkv', '1080p'),
    ('Duna _ Dune (2021)(CZ)_720p.mp4', '720p'),
    ('peaky_blinders.2x03.720p_hdtv_x264-fov.mkv', '720p'),
    ('Pulp Fiction (1994) UHD.mkv', '2160p'),
    ('Joker (2019) UHDR+DV cz en.mkv', '2160p'),
    ('Barbie (2023) UHDRDV cz en.mkv', '2160p'),
    ('Gladiator 2000 CZ Dabing 4K UHD HDR.mp4', '4k'),
    ('Movie_4K_cz.mkv', '4k'),
    ('Movie.1080p.UHD.BluRay.mkv', '1080p'),   # explicit p-token beats UHD source tag
])
def test_resolution_tokens_beyond_plain_p_suffix(filename, quality):
    assert parse_quality_metadata(filename)['quality'] == quality


@pytest.mark.parametrize('filename', [
    'Game.of.Thrones.S03E01.10bit.DS4K.CRAV.mkv',   # release group, not 4K
    'Fight Club (1999) R4KU OM SDR.mkv',
    'Movie 2019 S01E06_61080.mkv',                  # digits, no resolution marker
    'Movie 21080p.mkv',                             # digit-glued: not a resolution
    'Movie 1920x10800.mkv',
    'Movie UHDX cut.mkv',
    'Movie FULLHDX.mkv',
    'Movie 1080pm.mkv',
    'Show S01E04 1999.mkv',
    'Show 2x03 1080 hours.mkv',                     # episode / bare number, no p suffix
    'Movie (1920) CZ.mkv',                          # year-like number
    'Movie 1920x1080x.mkv',
    'Movie 4000x2160.mkv',                          # not a standard frame size
])
def test_resolution_tokens_no_false_positives(filename):
    assert parse_quality_metadata(filename)['quality'] is None
    assert parse_quality_metadata(filename)['quality_score'] == 50


def test_unmarked_resolution_versions_rank_by_resolution():
    score = lambda n: parse_quality_metadata(n)['quality_score']  # noqa: E731
    assert score('1883-S01E01-Cz Dab-FullHD.mkv') > score('1883.S01E01.Cz.mkv')
    assert score('Show.1920x1080.mkv') > score('Show.720p.mkv')


def test_quality_score_ranks_better_releases_higher():
    ranked = [
        'Movie.480p.DVDRip.XviD.mkv',
        'Movie.720p.HDTV.x264.mkv',
        'Movie.1080p.WEBRip.x264.mkv',
        'Movie.1080p.BluRay.x264.mkv',
        'Movie.2160p.BluRay.x265.DTS.mkv',
    ]
    scores = [parse_quality_metadata(f)['quality_score'] for f in ranked]
    assert scores == sorted(scores) and len(set(scores)) == len(scores)


def test_language_tag():
    assert extract_language_tag('Movie CZ.mkv') == 'CZ'
    assert extract_language_tag('Movie.mkv') is None


# ---------------------------------------------------------------------------
# group_by_series: parsing results feed grouping (regression net)
# ---------------------------------------------------------------------------

def _files(*names):
    return [{'name': n, 'ident': str(i), 'size': '1000000000'} for i, n in enumerate(names)]


def test_group_southpark_seasons_and_ignore_movie():
    grouped = group_by_series(_files(
        'Southpark_S18E01_Title_h265.mkv', 'Southpark_S18E02_Title_h265.mkv',
        'Southpark_S18E03_Title_h265.mkv', 'Southpark_S21E01_Title_h265.mkv',
        'Southpark_S21E02_Title_h265.mkv', 'Some_Movie_2024_1080p.mkv'))
    assert list(grouped['series']) == ['southpark']
    show = grouped['series']['southpark']
    assert show['total_episodes'] == 5
    assert sorted(show['seasons']) == [18, 21]


def test_group_mashle_absolute_and_season_text_merge():
    grouped = group_by_series(_files(
        'Mashle - 01 CZ.mkv', '[SubsPlease] Mashle - 01 (720p).mkv',
        'Mashle - 02 CZ.mkv', 'mashle ep3.mp4',
        'Mashle 2nd Season - 01 CZ.mkv', 'Mashle S02E01 CZ.mkv',
        'Mashle 2nd Season - 02 CZ.mkv'))
    assert list(grouped['series']) == ['mashle']
    show = grouped['series']['mashle']
    assert sorted(show['seasons']) == [1, 2]
    assert sorted(show['seasons'][1]) == [1, 2, 3]
    assert sorted(show['seasons'][2]) == [1, 2]
    assert show['total_episodes'] == 5
    assert len(show['seasons'][1][1]) == 2   # two versions of S01E01


def test_group_article_variants_merge():
    grouped = group_by_series(_files(
        'The.Office.S01E01.mkv', 'Office.S01E02.mkv', 'The.Office.S01E03.mkv'))
    assert list(grouped['series']) == ['office']
    assert grouped['series']['office']['total_episodes'] == 3


def test_group_the_boys_with_and_without_article():
    grouped = group_by_series(_files(
        'The.Boys.S01E01.1080p.mkv', 'The.Boys.S01E02.1080p.mkv', 'Boys.S01E03.720p.mkv'))
    assert len(grouped['series']) == 1
    (show,) = grouped['series'].values()
    assert show['total_episodes'] == 3


def test_group_dual_name_series_merges_czech_and_english():
    grouped = group_by_series(_files(
        'The.Penguin.S01E01.mkv', 'The.Penguin.S01E02.mkv',
        'Tučňák - The Penguin S01E03.mkv', 'Tučňák.S01E04.mkv'))
    assert len(grouped['series']) == 1
    (show,) = grouped['series'].values()
    assert show['total_episodes'] == 4


def test_group_tolerates_missing_or_empty_names():
    grouped = group_by_series([
        {'name': '', 'ident': 'a', 'size': '1'},
        {'name': None, 'ident': 'b', 'size': '1'},
        {'ident': 'c'},
        {'name': 'Series S01E01.mkv'},
    ])
    assert list(grouped['series']) == ['series']
    assert len(grouped['non_series']) >= 1


def test_group_movies_dual_name_merges_with_single_name_release():
    grouped = group_movies(_files(
        'Zootropolis - Zootopia.2016.1080p.mkv', 'Zootopia.2016.720p.mkv'))
    assert list(grouped['movies']) == ['zootopia|2016']
    assert len(grouped['movies']['zootopia|2016']['versions']) == 2


@pytest.mark.parametrize('filename, legacy', [
    ('Suits.S03.E13.Moot.Point.1080p.mkv', 'suits s03'),
    ('Dragon Ball Z - S01 E001 - A (1080p).mkv', 'dragon ball z s01'),
    ('Attack on Titan S3 - 11 (Shingeki no Kyojin S3).mkv', 'attack on titan s3'),
    ('Spy x Family S3 Ep 05.mkv', 'spy x family s3'),
    ('Naruto066-067.mkv', 'naruto066'),
    ('Big.Bang.Theory-07x18 (S07E18) - Choulostivý moment.mpg', 'big bang theory 07x18'),
    ('Solo Leveling Season 2 -Arise from the Shadow- S2 (Ore dake Level Up na Ken 2nd Season) - 09 [1080p AVC].mkv',
     'solo leveling arise from shadow s2'),
])
def test_changed_series_key_reports_the_key_it_had_before(filename, legacy):
    assert parse_episode_info(filename)['legacy_series_name'] == legacy


@pytest.mark.parametrize('filename', [
    'Suits S03E13.mkv',                      # contiguous marker: key unchanged
    'Mashle 2nd Season - 01.mkv',            # season text was already read
    'Naruto006.mkv',                         # was no episode at all
    'Dune Prophecy 2024 S01EP02 ORG Hindi Jio 720p HD.mkv',   # the old parser rejected it: no old key existed
    'Breaking Bad S01xE06 720p.mkv',
])
def test_unchanged_or_never_existing_key_reports_no_legacy_name(filename):
    assert 'legacy_series_name' not in parse_episode_info(filename)

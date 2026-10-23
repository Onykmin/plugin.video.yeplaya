# -*- coding: utf-8 -*-
"""Tests for state module (watched + resume persistence)."""
import os
import tempfile
import threading
import pytest
import sys

# Ensure conftest mocks are loaded first
import tests.conftest  # noqa: F401 -- installs Kodi mocks before lib imports


class _StateHarness:
    """Initialise a fresh state module bound to a tempfile DB."""

    def __init__(self):
        self.tmpdir = tempfile.mkdtemp()
        self.dbpath = os.path.join(self.tmpdir, 'state.db')
        # Reset the state module so get_db_path is re-called
        if 'lib.state' in sys.modules:
            del sys.modules['lib.state']
        from lib import state as _state
        # Override the internal path discovery
        _state._reset_for_tests(self.dbpath)
        _state._get_db_path = lambda: self.dbpath  # type: ignore
        self.state = _state

    def cleanup(self):
        self.state._reset_for_tests()
        try:
            os.remove(self.dbpath)
        except OSError:
            pass
        try:
            os.rmdir(self.tmpdir)
        except OSError:
            pass


@pytest.fixture
def harness():
    h = _StateHarness()
    yield h
    h.cleanup()


class TestStateKeyFor:
    def test_episode(self, harness):
        key = harness.state.state_key_for({
            'series_name': 'south park', 'season': 5, 'episode': 3, 'ident': 'abc',
        })
        assert key == 'ep:south park|S05E03'

    def test_episode_strings(self, harness):
        key = harness.state.state_key_for({
            'series_name': 'show', 'season': '1', 'episode': '12', 'ident': 'x',
        })
        assert key == 'ep:show|S01E12'

    def test_movie(self, harness):
        key = harness.state.state_key_for({'canonical_key': 'inception|2010', 'ident': 'z'})
        assert key == 'mv:inception|2010'

    def test_file_fallback(self, harness):
        key = harness.state.state_key_for({'ident': 'deadbeef'})
        assert key == 'file:deadbeef'

    def test_empty(self, harness):
        assert harness.state.state_key_for({}) is None


class TestStateKeyDriftNormalization:
    """State keys must survive dual-name canonical_key drift.

    Dual-name detection in grouping.py produces different canonical_keys
    across fetches when different alias files are present. If state keys
    drifted with them, resume/watched would split across multiple rows.
    Normalization strips the dual-name prefix (everything before the last
    "|" in a series key; preserves trailing |year for movies).
    """

    def test_episode_simple_key_unchanged(self, harness):
        key = harness.state.state_key_for({
            'series_name': 'south park', 'season': 1, 'episode': 5,
        })
        assert key == 'ep:south park|S01E05'

    def test_episode_dual_name_prefix_stripped(self, harness):
        """mestecko|south park drifts to pandemic special cz|south park;
        both must yield the SAME normalized state key."""
        k1 = harness.state.state_key_for({
            'series_name': 'mestecko|south park', 'season': 1, 'episode': 5,
        })
        k2 = harness.state.state_key_for({
            'series_name': 'pandemic special cz|south park', 'season': 1, 'episode': 5,
        })
        assert k1 == k2 == 'ep:south park|S01E05'

    def test_movie_simple_key_unchanged(self, harness):
        key = harness.state.state_key_for({'canonical_key': 'inception|2010'})
        assert key == 'mv:inception|2010'

    def test_movie_dual_name_prefix_stripped_preserves_year(self, harness):
        k1 = harness.state.state_key_for({'canonical_key': 'tucnak|penguin|2022'})
        k2 = harness.state.state_key_for({'canonical_key': 'penguin tucnak alias|penguin|2022'})
        assert k1 == k2 == 'mv:penguin|2022'

    def test_build_mv_state_key_helper(self, harness):
        assert harness.state.build_mv_state_key('inception|2010') == 'mv:inception|2010'
        assert harness.state.build_mv_state_key('tucnak|penguin|2022') == 'mv:penguin|2022'


class TestMigrationV1ToV2:
    """v1→v2 rewrites legacy un-normalized ep:/mv: keys so pre-upgrade
    watched/resume state for dual-name content is not orphaned."""

    def _seed_v1_db(self, harness, rows):
        """Create a user_version=1 DB with the given (key, w, r, t, updated) rows."""
        import sqlite3
        conn = sqlite3.connect(harness.dbpath)
        conn.execute('''CREATE TABLE playback_state (
            state_key TEXT PRIMARY KEY, watched INTEGER NOT NULL DEFAULT 0,
            resume_seconds INTEGER NOT NULL DEFAULT 0,
            total_seconds INTEGER NOT NULL DEFAULT 0, updated_at INTEGER NOT NULL)''')
        conn.executemany(
            'INSERT INTO playback_state VALUES (?,?,?,?,?)', rows)
        conn.execute('PRAGMA user_version = 1')
        conn.commit()
        conn.close()

    def test_legacy_dual_episode_key_rewritten(self, harness):
        self._seed_v1_db(harness, [
            ('ep:mestecko|south park|S01E05', 1, 0, 1200, 100),
        ])
        harness.state._reset_for_tests(harness.dbpath)
        harness.state._get_db_path = lambda: harness.dbpath
        # Reading the normalized key must find the migrated row.
        st = harness.state.get_state('ep:south park|S01E05')
        assert st is not None and st['watched'] == 1 and st['total_seconds'] == 1200
        # Old key gone.
        assert harness.state.get_state('ep:mestecko|south park|S01E05') is None

    def test_legacy_dual_movie_key_rewritten_keeps_year(self, harness):
        self._seed_v1_db(harness, [
            ('mv:tucnak|penguin|2022', 0, 540, 6000, 100),
        ])
        harness.state._reset_for_tests(harness.dbpath)
        harness.state._get_db_path = lambda: harness.dbpath
        st = harness.state.get_state('mv:penguin|2022')
        assert st is not None and st['resume_seconds'] == 540

    def test_simple_keys_untouched(self, harness):
        self._seed_v1_db(harness, [
            ('ep:south park|S01E05', 1, 0, 1200, 100),
            ('mv:inception|2010', 0, 30, 7000, 100),
            ('file:deadbeef', 1, 0, 100, 100),
        ])
        harness.state._reset_for_tests(harness.dbpath)
        harness.state._get_db_path = lambda: harness.dbpath
        assert harness.state.get_state('ep:south park|S01E05')['watched'] == 1
        assert harness.state.get_state('mv:inception|2010')['resume_seconds'] == 30
        assert harness.state.get_state('file:deadbeef')['watched'] == 1

    def test_collision_keeps_freshest(self, harness):
        # Legacy dual key and an already-normalized key collide; newer wins.
        self._seed_v1_db(harness, [
            ('ep:mestecko|south park|S01E05', 1, 0, 1200, 100),  # older legacy
            ('ep:south park|S01E05', 0, 333, 1200, 200),         # newer normalized
        ])
        harness.state._reset_for_tests(harness.dbpath)
        harness.state._get_db_path = lambda: harness.dbpath
        st = harness.state.get_state('ep:south park|S01E05')
        assert st['resume_seconds'] == 333 and st['watched'] == 0
        assert harness.state.get_state('ep:mestecko|south park|S01E05') is None

    def test_user_version_bumped(self, harness):
        self._seed_v1_db(harness, [('ep:south park|S01E05', 1, 0, 1200, 100)])
        harness.state._reset_for_tests(harness.dbpath)
        harness.state._get_db_path = lambda: harness.dbpath
        conn = harness.state._connect()
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 2


class TestRecordPlayback:
    def test_short_video_skip(self, harness):
        harness.state.record_playback('ep:x|S01E01', 5, 9)
        assert harness.state.get_state('ep:x|S01E01') is None

    def test_half_way_resume(self, harness):
        harness.state.record_playback('ep:x|S01E01', 500, 1000)
        st = harness.state.get_state('ep:x|S01E01')
        assert st['watched'] == 0
        assert st['resume_seconds'] == 500
        assert st['total_seconds'] == 1000

    def test_ninety_percent_watched(self, harness):
        harness.state.record_playback('ep:x|S01E01', 900, 1000)
        st = harness.state.get_state('ep:x|S01E01')
        assert st['watched'] == 1
        assert st['resume_seconds'] == 0

    def test_ninety_five_percent_watched(self, harness):
        harness.state.record_playback('ep:x|S01E01', 950, 1000)
        st = harness.state.get_state('ep:x|S01E01')
        assert st['watched'] == 1

    def test_overwrites(self, harness):
        harness.state.record_playback('ep:x|S01E01', 300, 1000)
        harness.state.record_playback('ep:x|S01E01', 600, 1000)
        st = harness.state.get_state('ep:x|S01E01')
        assert st['resume_seconds'] == 600


class TestMarkOps:
    def test_mark_watched(self, harness):
        harness.state.mark_watched('ep:x|S01E01')
        st = harness.state.get_state('ep:x|S01E01')
        assert st['watched'] == 1

    def test_mark_unwatched(self, harness):
        harness.state.mark_watched('ep:x|S01E01')
        harness.state.mark_unwatched('ep:x|S01E01')
        st = harness.state.get_state('ep:x|S01E01')
        assert st['watched'] == 0
        assert st['resume_seconds'] == 0

    def test_clear_resume(self, harness):
        harness.state.record_playback('ep:x|S01E01', 300, 1000)
        harness.state.clear_resume('ep:x|S01E01')
        st = harness.state.get_state('ep:x|S01E01')
        assert st['resume_seconds'] == 0
        assert st['watched'] == 0
        assert st['total_seconds'] == 1000

    def test_clear_resume_missing(self, harness):
        # Should not raise
        harness.state.clear_resume('ep:never|S01E01')
        assert harness.state.get_state('ep:never|S01E01') is None


class TestGetStates:
    def test_batch(self, harness):
        harness.state.record_playback('ep:a|S01E01', 500, 1000)
        harness.state.mark_watched('ep:b|S01E01')
        keys = ['ep:a|S01E01', 'ep:b|S01E01', 'ep:c|S01E01']
        result = harness.state.get_states(keys)
        assert len(result) == 2
        assert result['ep:a|S01E01']['resume_seconds'] == 500
        assert result['ep:b|S01E01']['watched'] == 1
        assert 'ep:c|S01E01' not in result

    def test_empty(self, harness):
        assert harness.state.get_states([]) == {}
        assert harness.state.get_states([None, '']) == {}

class TestThreadSafety:
    def test_concurrent_upserts(self, harness):
        errors = []

        def writer(k):
            try:
                for i in range(50):
                    harness.state.record_playback(k, i * 20, 1000)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=writer, args=('ep:a|S01E01',))
        t2 = threading.Thread(target=writer, args=('ep:a|S01E01',))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)
        assert not errors, "thread errors: %s" % errors
        st = harness.state.get_state('ep:a|S01E01')
        assert st is not None


class TestCacheInvalidation:
    def test_cache_cleared_on_write(self, harness):
        harness.state.record_playback('ep:x|S01E01', 300, 1000)
        first = harness.state.get_state('ep:x|S01E01')
        assert first['resume_seconds'] == 300
        harness.state.mark_watched('ep:x|S01E01')
        second = harness.state.get_state('ep:x|S01E01')
        assert second['watched'] == 1
        assert second['resume_seconds'] == 0


class TestResolveStateKeyLegacyMerge:
    """Rows written under a stale pre-merge series key stay readable."""

    FILE = {'series_name': 'south park', 'premerge_series_name': 'mestecko south park',
            'season': 1, 'episode': 3, 'ident': 'c'}
    NEW = 'ep:south park|S01E03'
    OLD = 'ep:mestecko south park|S01E03'

    def test_old_row_resolved(self, harness):
        harness.state.mark_watched(self.OLD)
        assert harness.state.resolve_state_key(self.FILE) == self.OLD

    def test_current_row_wins_and_old_row_untouched(self, harness):
        harness.state.mark_watched(self.OLD)
        harness.state.record_playback(self.NEW, 100, 1000)
        assert harness.state.resolve_state_key(self.FILE) == self.NEW
        assert harness.state.get_state(self.OLD)['watched'] == 1

    def test_idempotent(self, harness):
        harness.state.mark_watched(self.OLD)
        first = harness.state.resolve_state_key(self.FILE)
        assert harness.state.resolve_state_key(self.FILE) == first
        assert harness.state.get_state(self.NEW) is None

    def test_no_rows_or_no_premerge_name_is_plain_state_key(self, harness):
        assert harness.state.resolve_state_key(self.FILE) == self.NEW
        plain = {k: v for k, v in self.FILE.items() if k != 'premerge_series_name'}
        harness.state.mark_watched(self.OLD)
        assert harness.state.resolve_state_key(plain) == self.NEW

    def test_dual_prefix_normalized_on_legacy_side(self, harness):
        harness.state.mark_watched('ep:penguin|S01E01')
        f = {'series_name': 'the penguin|tucnak', 'premerge_series_name': 'penguin',
             'season': 1, 'episode': 1}
        assert harness.state.resolve_state_key(f) == 'ep:penguin|S01E01'


class TestResolveStateKeyLegacySeasonMarker:
    """Rows written while an unread season marker stayed in the series key ("suits s03").

    The old parser filed such episodes under season 1, so the row is S01 where the file
    is now S03; a plain alias lookup would miss it.
    """

    FILE = {'series_name': 'suits', 'season': 3, 'episode': 13}
    ALIASES = ['suits s03']
    NEW = 'ep:suits|S03E13'
    OLD = 'ep:suits s03|S01E13'

    def test_old_row_resolves(self, harness):
        harness.state.mark_watched(self.OLD)
        assert harness.state.resolve_state_key(self.FILE, self.ALIASES) == self.OLD

    def test_row_with_the_live_season_resolves_too(self, harness):
        harness.state.mark_watched('ep:suits s03|S03E13')
        assert harness.state.resolve_state_key(self.FILE, self.ALIASES) == 'ep:suits s03|S03E13'

    def test_current_row_wins_and_old_row_is_untouched(self, harness):
        harness.state.mark_watched(self.OLD)
        harness.state.record_playback(self.NEW, 100, 1000)
        assert harness.state.resolve_state_key(self.FILE, self.ALIASES) == self.NEW
        assert harness.state.get_state(self.OLD)['watched'] == 1

    def test_idempotent_and_never_writes(self, harness):
        harness.state.mark_watched(self.OLD)
        first = harness.state.resolve_state_key(self.FILE, self.ALIASES)
        assert harness.state.resolve_state_key(self.FILE, self.ALIASES) == first
        assert harness.state.get_state(self.NEW) is None

    def test_unrelated_rows_are_not_resolved(self, harness):
        for key in ('ep:suits s03|S01E14',      # another episode
                    'ep:suits s04|S01E13',      # another season's marker key
                    'ep:other show s03|S01E13'):
            harness.state.mark_watched(key)
        assert harness.state.resolve_state_key(self.FILE, self.ALIASES) == self.NEW
        # the season-1 fallback needs the alias to name the file's own season (s03), not s04
        assert harness.state.resolve_state_key(self.FILE, ['suits s04']) == self.NEW

    def test_alias_without_a_season_token_never_falls_back_to_season_1(self, harness):
        harness.state.mark_watched('ep:mestecko suits|S01E13')
        assert harness.state.resolve_state_key(self.FILE, ['mestecko suits']) == self.NEW

    def test_alias_naming_season_1_is_a_plain_alias(self, harness):
        harness.state.mark_watched('ep:dragon ball z s01|S01E01')
        f = {'series_name': 'dragon ball z', 'season': 1, 'episode': 1}
        assert harness.state.resolve_state_key(f, ['dragon ball z s01']) == 'ep:dragon ball z s01|S01E01'

    def test_old_movie_row_of_a_gapped_marker_file_resolves(self, harness):
        harness.state.mark_watched('mv:squid game s03 e01|2025')
        f = {'series_name': 'squid game', 'season': 3, 'episode': 1,
             'legacy_movie_key': 'squid game s03 e01|2025'}
        assert harness.state.resolve_state_key(f) == 'mv:squid game s03 e01|2025'
        assert harness.state.resolve_state_key(dict(f, legacy_movie_key=None)) == 'ep:squid game|S03E01'


class TestResolveStateKeyLegacyBareSeason:
    """Rows written while `Name NN - MM` bound the season number into the name ("peaky blinders 02").

    The old parser filed "Peaky Blinders  02 - 05" as (peaky blinders 02, S01E05); it is now
    S02E05 of "peaky blinders".
    """

    FILE = {'series_name': 'peaky blinders', 'season': 2, 'episode': 5}
    ALIASES = ['peaky blinders 02']
    NEW = 'ep:peaky blinders|S02E05'
    OLD = 'ep:peaky blinders 02|S01E05'

    def test_old_row_resolves(self, harness):
        harness.state.mark_watched(self.OLD)
        assert harness.state.resolve_state_key(self.FILE, self.ALIASES) == self.OLD

    def test_current_row_wins_and_old_row_is_untouched(self, harness):
        harness.state.mark_watched(self.OLD)
        harness.state.record_playback(self.NEW, 100, 1000)
        assert harness.state.resolve_state_key(self.FILE, self.ALIASES) == self.NEW
        assert harness.state.get_state(self.OLD)['watched'] == 1

    def test_idempotent_and_never_writes(self, harness):
        harness.state.mark_watched(self.OLD)
        first = harness.state.resolve_state_key(self.FILE, self.ALIASES)
        assert harness.state.resolve_state_key(self.FILE, self.ALIASES) == first
        assert harness.state.get_state(self.NEW) is None

    def test_row_of_another_season_or_episode_is_not_resolved(self, harness):
        for key in ('ep:peaky blinders 02|S01E06',   # another episode
                    'ep:peaky blinders 03|S01E05',   # another season's old key
                    'ep:peaky blinders 02|S03E05'):  # a season the old parser never wrote
            harness.state.mark_watched(key)
        assert harness.state.resolve_state_key(self.FILE, self.ALIASES) == self.NEW
        # the season-1 fallback needs the alias to name the file's own season, not 03
        assert harness.state.resolve_state_key(self.FILE, ['peaky blinders 03']) == self.NEW

    def test_genuine_file_of_another_season_never_reads_a_season_alias_row(self, harness):
        # S01E05 of the show has no row; the old S02E05 content row must not answer for it
        harness.state.mark_watched(self.OLD)
        f = {'series_name': 'peaky blinders', 'season': 1, 'episode': 5}
        assert harness.state.resolve_state_key(f, ['peaky blinders 02', 'peaky blinders 03']) == 'ep:peaky blinders|S01E05'
        assert harness.state.resolve_state_key(dict(f, season=3), self.ALIASES) == 'ep:peaky blinders|S03E05'

    def test_numeric_title_alias_of_another_name_keeps_resolving(self, harness):
        harness.state.mark_watched('ep:apollo 13|S01E05')
        f = {'series_name': 'apollo extended', 'season': 1, 'episode': 5}
        assert harness.state.resolve_state_key(f, ['apollo 13']) == 'ep:apollo 13|S01E05'

    def test_show_plus_number_alias_is_read_as_a_season_only_for_that_season_file(self, harness):
        # `apollo 13` on `apollo`: a group without S13 never reads the `apollo 13` row
        harness.state.mark_watched('ep:apollo 13|S01E05')
        f = {'series_name': 'apollo', 'season': 1, 'episode': 5}
        assert harness.state.resolve_state_key(f, ['apollo 13']) == 'ep:apollo|S01E05'
        assert harness.state.resolve_state_key(dict(f, season=2), ['apollo 13']) == 'ep:apollo|S02E05'
        # a group that has S13 (the file's own season) reads it as season 13
        assert harness.state.resolve_state_key(dict(f, season=13), ['apollo 13']) == 'ep:apollo 13|S01E05'

    def test_season_token_alias_serves_only_its_own_season(self, harness):
        harness.state.mark_watched('ep:suits s03|S01E13')
        f = {'series_name': 'suits', 'season': 1, 'episode': 13}
        assert harness.state.resolve_state_key(f, ['suits s03']) == 'ep:suits|S01E13'

    def test_season_one_file_reads_its_plain_old_row(self, harness):
        harness.state.mark_watched('ep:peaky blinders 01|S01E05')
        f = {'series_name': 'peaky blinders', 'season': 1, 'episode': 5}
        assert harness.state.resolve_state_key(f, ['peaky blinders 01']) == 'ep:peaky blinders 01|S01E05'


class TestResolveStateKeyAliases:
    """Rows stored under any key a merged group was built from stay readable.

    `aliases` are grouping's pre-merge keys (the old order-dependent survivor was
    one of them); resolution is read-only and a current row always wins.
    """

    EP = {'series_name': 'south park', 'season': 1, 'episode': 3}
    EP_ALIASES = ['mestecko south park', 'park south']
    NEW_EP = 'ep:south park|S01E03'
    MV = {'canonical_key': 'avatar|2009'}
    MV_ALIASES = ['avatar extended|2009', 'avatar 1|2009']
    NEW_MV = 'mv:avatar|2009'

    @pytest.mark.parametrize('old', ['ep:mestecko south park|S01E03', 'ep:park south|S01E03'])
    def test_episode_row_under_each_alias_resolves(self, harness, old):
        harness.state.mark_watched(old)
        assert harness.state.resolve_state_key(self.EP, self.EP_ALIASES) == old

    @pytest.mark.parametrize('old', ['mv:avatar extended|2009', 'mv:avatar 1|2009'])
    def test_movie_row_under_each_alias_resolves(self, harness, old):
        harness.state.mark_watched(old)
        assert harness.state.resolve_state_key(self.MV, self.MV_ALIASES) == old

    def test_dual_alias_is_read_through_its_normalized_identity(self, harness):
        harness.state.mark_watched('ep:tucnak|S01E01')
        f = {'series_name': 'penguin', 'season': 1, 'episode': 1}
        assert harness.state.resolve_state_key(f, ['penguin|tucnak', 'tucnak']) == 'ep:tucnak|S01E01'

    def test_movie_alias_of_another_year_resolves(self, harness):
        harness.state.mark_watched('mv:blade 2|2000')
        assert harness.state.resolve_state_key(
            {'canonical_key': 'blade 2|2002'}, ['blade 2|2000']) == 'mv:blade 2|2000'

    def test_current_row_wins_and_legacy_row_is_untouched(self, harness):
        harness.state.mark_watched('ep:mestecko south park|S01E03')
        harness.state.record_playback(self.NEW_EP, 100, 1000)
        assert harness.state.resolve_state_key(self.EP, self.EP_ALIASES) == self.NEW_EP
        assert harness.state.get_state('ep:mestecko south park|S01E03')['watched'] == 1

    def test_idempotent_and_never_writes(self, harness):
        harness.state.mark_watched('mv:avatar extended|2009')
        first = harness.state.resolve_state_key(self.MV, self.MV_ALIASES)
        assert harness.state.resolve_state_key(self.MV, self.MV_ALIASES) == first
        assert harness.state.get_state(self.NEW_MV) is None

    def test_newest_legacy_row_wins(self, harness):
        conn = harness.state._connect()
        for key, updated in (('ep:mestecko south park|S01E03', 100), ('ep:park south|S01E03', 200)):
            conn.execute('INSERT INTO playback_state VALUES (?, 1, 0, 10, ?)', (key, updated))
        conn.commit()
        assert harness.state.resolve_state_key(self.EP, self.EP_ALIASES) == 'ep:park south|S01E03'

    def test_unrelated_rows_and_missing_aliases_leave_the_current_key(self, harness):
        harness.state.mark_watched('ep:other show|S01E03')
        harness.state.mark_watched('ep:mestecko south park|S01E04')
        assert harness.state.resolve_state_key(self.EP, self.EP_ALIASES) == self.NEW_EP
        assert harness.state.resolve_state_key(self.EP, None) == self.NEW_EP

    def test_file_fallback_keys_are_not_aliased(self, harness):
        f = {'ident': 'abc'}
        assert harness.state.resolve_state_key(f, ['x']) == 'file:abc'

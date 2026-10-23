#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for lib.random_movie_ui — one-click random movie picker.

Covers:
- _display_title picking cs over en, falling back to en.
- _build_dialog_rows: film / Reroll / Cancel actions; year is display-only.
- show_random_movie_dialog: dialog ALWAYS shown (no more single-title
  auto-search bypass); selecting the film row hands off via storesearch() +
  Container.Update (NOT dosearch/addDirectoryItem/endOfDirectory); Reroll
  picks another film; Cancel and select()==-1 both exit without searching;
  pick_random returning None distinguishes an empty pool (30453) from a
  genuinely exhausted one (30447); picked ids accumulate in excluded so no
  film is offered twice; auto-reroll-on-empty-search is GONE (impossible
  across the Container.Update handoff — a search handoff happens at most
  once per confirmed selection).
"""

import time
import unittest
import unittest.mock as mock

import tests.conftest  # noqa: F401 — installs Kodi mocks

import lib.random_movie_ui as rmu


# ---------------------------------------------------------------------------
# _display_title
# ---------------------------------------------------------------------------

class TestDisplayTitle(unittest.TestCase):
    def test_cs_preferred_over_en(self):
        item = {'id': 'Q1', 'cs': 'Matrix', 'en': 'The Matrix'}
        self.assertEqual(rmu._display_title(item), 'Matrix')

    def test_en_used_when_cs_missing(self):
        item = {'id': 'Q2', 'cs': None, 'en': 'Some Film'}
        self.assertEqual(rmu._display_title(item), 'Some Film')

    def test_cs_only(self):
        item = {'id': 'Q3', 'cs': 'Nejaky Film', 'en': None}
        self.assertEqual(rmu._display_title(item), 'Nejaky Film')

    def test_neither_returns_none(self):
        item = {'id': 'Q4', 'cs': None, 'en': None}
        self.assertIsNone(rmu._display_title(item))

    def test_byte_identical_cs_en_returns_that_title(self):
        """Real live-pool case: Germinal/Germinal, Yossi & Jagger/Yossi & Jagger."""
        item = {'id': 'Q5', 'cs': 'Germinal', 'en': 'Germinal'}
        self.assertEqual(rmu._display_title(item), 'Germinal')


# ---------------------------------------------------------------------------
# _build_dialog_rows
# ---------------------------------------------------------------------------

class TestBuildDialogRows(unittest.TestCase):

    def test_actions_are_search_reroll_cancel_in_order(self):
        listitems, actions = rmu._build_dialog_rows('Some Title')
        self.assertEqual(actions, [
            ('search', 'Some Title'), ('reroll', None), ('cancel', None),
        ])


    def test_film_row_text_includes_year_when_known_real_format(self):
        """Use a real format-capable string (mirroring strings.po's actual
        30450 = 'Search "{}"') to verify the row text substitution itself,
        independent of the test double's plain-string limitation."""
        with mock.patch.object(rmu._addon, 'getLocalizedString',
                                side_effect=lambda i: 'Search "{0}"' if i == 30450 else 'String_{}'.format(i)):
            listitems, _ = rmu._build_dialog_rows('Godzilla', 1998)
        self.assertEqual(listitems[0].label, 'Search "Godzilla (1998)"')

    def test_film_row_text_is_bare_title_when_year_unknown_real_format(self):
        with mock.patch.object(rmu._addon, 'getLocalizedString',
                                side_effect=lambda i: 'Search "{0}"' if i == 30450 else 'String_{}'.format(i)):
            listitems, _ = rmu._build_dialog_rows('Godzilla')
        self.assertEqual(listitems[0].label, 'Search "Godzilla"')

    def test_actions_carry_bare_title_even_when_year_known(self):
        """CRITICAL: the year is display-only. actions[0] (the 'search'
        action) must carry the BARE title — appending '(1998)' would wreck
        Webshare search results."""
        _, actions = rmu._build_dialog_rows('Godzilla', 1998)
        self.assertEqual(actions[0], ('search', 'Godzilla'))


# ---------------------------------------------------------------------------
# show_random_movie_dialog — driver helper
# ---------------------------------------------------------------------------

class _ScriptedDialog(object):
    """Stub for xbmcgui.Dialog() exposing .select(...).

    Pops from a scripted list of return values (row index, or -1 for
    cancel/dismiss). Raises if scripted selections run out, so a bug that
    invokes the dialog more times than expected fails loudly.
    """

    def __init__(self, selections):
        self._selections = list(selections)
        self.shown = []

    def select(self, heading, listitems, useDetails=False):
        self.shown.append(listitems)
        if not self._selections:
            raise AssertionError('ScriptedDialog ran out of scripted selections')
        return self._selections.pop(0)


class _RecordingProgressBG(object):
    """Stub for xbmcgui.DialogProgressBG().

    Records create/update/close so tests can assert the cold-path progress
    dialog is shown AND always closed (an unclosed DialogProgressBG would
    persist for the whole Kodi session).
    """

    def __init__(self, log):
        self._log = log

    def create(self, heading, message=''):
        self._log.append(('create', heading, message))

    def update(self, percent=0, heading=None, message=None):
        self._log.append(('update', percent))

    def close(self):
        self._log.append(('close',))


def _item(qid, cs=None, en=None, y=None):
    item = {'id': qid, 'cs': cs, 'en': en}
    if y is not None:
        item['y'] = y
    return item


def _run(pick_script, params=None, selections=None, load_pool_result=None,
         extra_patches=None):
    """Drive show_random_movie_dialog with the standard seams patched.

    pick_script: list of items (or None) returned by successive pick_random
      calls, in order.
    load_pool_result: value returned by load_pool() when pick_random exits
      the loop with None (used to distinguish the 30453 vs 30447 toast).
    Returns a dict of recorded call info for assertions.
    """
    pick_calls = []

    def _fake_pick_random(excluded, *a, **k):
        pick_calls.append(set(excluded))
        if not pick_script:
            raise AssertionError('pick_random called more times than scripted')
        return pick_script.pop(0)

    dialog = _ScriptedDialog(selections if selections is not None else [-1])

    storesearch_calls = []
    executebuiltin_calls = []
    add_directory_item_calls = []
    end_of_directory_calls = []

    popinfo_calls = []
    progress_calls = []

    def _fake_popinfo(message, **kw):
        popinfo_calls.append(message)

    xbmcgui_mod = rmu.xbmcgui
    xbmcplugin_mod = rmu.xbmcplugin
    xbmc_mod = rmu.xbmc

    resolved_calls = []

    def _fake_set_resolved(handle, succeeded, listitem):
        resolved_calls.append(succeeded)

    def _fake_executebuiltin(command):
        executebuiltin_calls.append(command)

    def _fake_add_directory_item(*a, **k):
        add_directory_item_calls.append((a, k))

    def _fake_end_of_directory(*a, **k):
        end_of_directory_calls.append((a, k))

    patches = [
        mock.patch.object(rmu, 'revalidate', return_value='tok'),
        mock.patch.object(rmu, 'pick_random', _fake_pick_random),
        mock.patch.object(rmu, 'load_pool', lambda: load_pool_result),
        mock.patch.object(rmu, 'storesearch', lambda title: storesearch_calls.append(title)),
        mock.patch.object(rmu, 'popinfo', _fake_popinfo),
        mock.patch.object(xbmcgui_mod, 'Dialog', lambda: dialog),
        mock.patch.object(xbmcgui_mod, 'DialogProgressBG',
                          lambda: _RecordingProgressBG(progress_calls),
                          create=True),
        mock.patch.object(xbmcplugin_mod, 'setResolvedUrl', _fake_set_resolved),
        mock.patch.object(xbmc_mod, 'executebuiltin', _fake_executebuiltin),
        mock.patch.object(xbmcplugin_mod, 'addDirectoryItem', _fake_add_directory_item),
        mock.patch.object(xbmcplugin_mod, 'endOfDirectory', _fake_end_of_directory),
    ]
    if extra_patches:
        patches.extend(extra_patches)

    for p in patches:
        p.start()
    try:
        rmu.show_random_movie_dialog(params or {})
    finally:
        for p in reversed(patches):
            p.stop()

    return {
        'pick_calls': pick_calls,
        'dialog': dialog,
        'storesearch_calls': storesearch_calls,
        'executebuiltin_calls': executebuiltin_calls,
        'add_directory_item_calls': add_directory_item_calls,
        'end_of_directory_calls': end_of_directory_calls,
        'popinfo_calls': popinfo_calls,
        'progress_calls': progress_calls,
        'resolved_calls': resolved_calls,
    }


# ---------------------------------------------------------------------------
# Dialog is always shown, always 3 rows — no single-title bypass
# ---------------------------------------------------------------------------

class TestSingleVsTwoTitle(unittest.TestCase):
    def test_single_title_still_shows_dialog(self):
        """A single-title record must NOT bypass confirmation — the old
        auto-search-no-dialog branch (skipped confirmation on 58.7% of live
        picks, per the module docstring) is deleted. Inverted from the old
        test_single_title_auto_searches_no_dialog."""
        item = _item('Q1', en='Solo Title')
        result = _run([item], selections=[0])
        self.assertEqual(len(result['dialog'].shown), 1)
        self.assertEqual(result['storesearch_calls'], ['Solo Title'])


    def test_selecting_film_row_searches_cs_preferred_title(self):
        item = _item('Q1', cs='Cesky', en='English')
        result = _run([item], selections=[0])
        self.assertEqual(result['storesearch_calls'], ['Cesky'])


# ---------------------------------------------------------------------------
# Uniformity invariant: record shape has zero observable effect
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Year display: row TEXT changes, search/store string stays the bare title
# ---------------------------------------------------------------------------

class TestYearDisplayIsDisplayOnly(unittest.TestCase):
    """Year is DISPLAY-ONLY (Task 4): the dialog's film row may show
    "Title (Year)", but storesearch() and the Container.Update URL must
    always carry the BARE title — appending "(1998)" would wreck Webshare
    search results. Also re-confirms row count stays 3 either way."""

    def _real_30450(self, i):
        return 'Search "{0}"' if i == 30450 else 'String_{}'.format(i)

    def test_film_row_shows_title_and_year_when_known(self):
        item = _item('Q1', en='Godzilla', y=1998)
        with mock.patch.object(rmu._addon, 'getLocalizedString', side_effect=self._real_30450):
            result = _run([item], selections=[0])
        shown_label = result['dialog'].shown[0][0].label
        self.assertEqual(shown_label, 'Search "Godzilla (1998)"')
        self.assertEqual(len(result['dialog'].shown[0]), 3)

    def test_film_row_shows_bare_title_when_year_unknown(self):
        item = _item('Q2', en='Godzilla')
        with mock.patch.object(rmu._addon, 'getLocalizedString', side_effect=self._real_30450):
            result = _run([item], selections=[0])
        shown_label = result['dialog'].shown[0][0].label
        self.assertEqual(shown_label, 'Search "Godzilla"')
        self.assertEqual(len(result['dialog'].shown[0]), 3)

    def test_storesearch_receives_bare_title_when_year_known(self):
        item = _item('Q1', en='Godzilla', y=1998)
        result = _run([item], selections=[0])
        self.assertEqual(result['storesearch_calls'], ['Godzilla'])
        for call in result['storesearch_calls']:
            self.assertNotIn('(', call)
            self.assertNotIn('1998', call)

    def test_container_update_url_receives_bare_title_when_year_known(self):
        item = _item('Q1', en='Godzilla', y=1998)
        result = _run([item], selections=[0])
        self.assertEqual(len(result['executebuiltin_calls']), 1)
        builtin = result['executebuiltin_calls'][0]
        self.assertNotIn('%28', builtin)  # urlencoded '('
        self.assertNotIn('1998', builtin)

    def test_storesearch_and_url_unaffected_when_year_unknown(self):
        item = _item('Q2', en='Godzilla')
        result = _run([item], selections=[0])
        self.assertEqual(result['storesearch_calls'], ['Godzilla'])
        builtin = result['executebuiltin_calls'][0]
        self.assertNotIn('%28', builtin)  # no urlencoded '(' in the URL


# ---------------------------------------------------------------------------
# The Kodi contract: Container.Update handoff, not dosearch's directory API
# ---------------------------------------------------------------------------

class TestSearchHandoffContract(unittest.TestCase):
    """The bug that shipped: random_movie is a resolve action (PlayMedia),
    not a directory listing. The old code rendered results with
    addDirectoryItem/endOfDirectory into a handle Kodi never opened as a
    directory, so results silently vanished. This is the test that would
    have caught it: assert the actual Kodi primitives used, not a return
    value in isolation."""

    def test_confirmed_selection_uses_setresolvedurl_and_container_update(self):
        item = _item('Q1', en='Solo Title')
        result = _run([item], selections=[0])

        self.assertEqual(result['resolved_calls'], [False])
        self.assertEqual(len(result['executebuiltin_calls']), 1)
        builtin = result['executebuiltin_calls'][0]
        self.assertTrue(builtin.startswith('Container.Update('))
        self.assertIn('action=search', builtin)
        self.assertIn('Solo', builtin)  # urlencoded title fragment present

    def test_confirmed_selection_does_not_use_directory_listing_api(self):
        item = _item('Q1', en='Solo Title')
        result = _run([item], selections=[0])

        self.assertEqual(result['add_directory_item_calls'], [])
        self.assertEqual(result['end_of_directory_calls'], [])

    def test_storesearch_called_before_handoff(self):
        item = _item('Q1', en='Solo Title')
        result = _run([item], selections=[0])
        self.assertEqual(result['storesearch_calls'], ['Solo Title'])
        self.assertEqual(len(result['executebuiltin_calls']), 1)


# ---------------------------------------------------------------------------
# Reroll / Cancel
# ---------------------------------------------------------------------------

class TestRerollCancel(unittest.TestCase):
    def test_reroll_row_picks_another_film(self):
        item1 = _item('Q1', cs='A', en='B')
        item2 = _item('Q2', en='Solo')
        # First pick: select Reroll (index 1). Second pick: confirm (index 0).
        result = _run([item1, item2], selections=[1, 0])
        self.assertEqual(result['storesearch_calls'], ['Solo'])
        self.assertEqual(len(result['pick_calls']), 2)

    def test_cancel_row_exits_without_searching(self):
        item = _item('Q1', cs='A', en='B')
        result = _run([item], selections=[2])  # cancel row index
        self.assertEqual(result['storesearch_calls'], [])
        self.assertEqual(result['executebuiltin_calls'], [])
        self.assertEqual(result['resolved_calls'], [False])

    def test_select_minus_one_exits_without_searching(self):
        item = _item('Q1', cs='A', en='B')
        result = _run([item], selections=[-1])
        self.assertEqual(result['storesearch_calls'], [])
        self.assertEqual(result['executebuiltin_calls'], [])
        self.assertEqual(result['resolved_calls'], [False])


# ---------------------------------------------------------------------------
# No auto-reroll on search handoff — happens at most once per confirmation
# ---------------------------------------------------------------------------

class TestNoAutoRerollOnSearch(unittest.TestCase):
    """Auto-reroll-on-empty-search (MAX_EMPTY_REROLLS / SEARCH_EMPTY) is
    deleted — impossible across the Container.Update handoff, since the
    search's own result is never observed by this module again. Replaces
    the old TestEmptyRerollCap: assert the search handoff happens exactly
    once per confirmed selection and does not loop, regardless of what the
    (now-invisible-to-this-module) search would have found."""

    def test_confirming_selection_hands_off_exactly_once(self):
        item = _item('Q1', en='Only Title')
        result = _run([item], selections=[0])
        self.assertEqual(len(result['storesearch_calls']), 1)
        self.assertEqual(len(result['executebuiltin_calls']), 1)
        self.assertEqual(len(result['pick_calls']), 1)


# ---------------------------------------------------------------------------
# pick_random returning None: empty pool (30453) vs exhausted pool (30447)
# ---------------------------------------------------------------------------

class TestPoolExhaustedVsEmpty(unittest.TestCase):
    def test_pick_random_none_with_empty_load_pool_shows_30453(self):
        """load_pool() falsy => WDQS outage / never-fetched pool, distinct
        toast from genuine exhaustion."""
        result = _run([None], load_pool_result=[])
        self.assertEqual(result['storesearch_calls'], [])
        self.assertEqual(result['resolved_calls'], [False])
        self.assertEqual(result['popinfo_calls'],
                          [rmu._addon.getLocalizedString(30453)])

    def test_pick_random_none_with_nonempty_load_pool_shows_30447(self):
        """load_pool() truthy => every item already excluded, genuine
        exhaustion."""
        result = _run([None], load_pool_result=[{'id': 'Q1'}])
        self.assertEqual(result['storesearch_calls'], [])
        self.assertEqual(result['resolved_calls'], [False])
        self.assertEqual(result['popinfo_calls'],
                          [rmu._addon.getLocalizedString(30447)])


# ---------------------------------------------------------------------------
# Excluded accumulation
# ---------------------------------------------------------------------------

class TestExcludedAccumulation(unittest.TestCase):
    def test_picked_ids_accumulate_in_excluded_across_rerolls(self):
        item1 = _item('Q1', cs='A', en='B')  # reroll
        item2 = _item('Q2', en='C')          # reroll
        item3 = _item('Q3', en='D')          # confirm
        result = _run([item1, item2, item3], selections=[1, 1, 0])
        pick_calls = result['pick_calls']
        self.assertEqual(pick_calls[0], set())
        self.assertEqual(pick_calls[1], {'Q1'})
        self.assertEqual(pick_calls[2], {'Q1', 'Q2'})
        self.assertEqual(result['storesearch_calls'], ['D'])

    def test_none_titles_item_is_skipped_without_consuming_a_dialog_show(self):
        """Structurally shouldn't happen (movie_pool guarantees at least one
        of cs/en), but an item with neither title must never be offered in
        the dialog — it should just move on to the next pick without
        consuming a scripted dialog selection."""
        item_bad = _item('Qbad')  # neither cs nor en
        item_good = _item('Qgood', en='Fine')
        result = _run([item_bad, item_good], selections=[0])
        self.assertEqual(len(result['dialog'].shown), 1)
        self.assertEqual(result['storesearch_calls'], ['Fine'])


# ---------------------------------------------------------------------------
# main.py _RESOLVE_ACTIONS guard
# ---------------------------------------------------------------------------


class TestColdPoolProgressAnimates(unittest.TestCase):
    """Regression: a FIXED percentage renders as a frozen number beside
    Kodi's own busy spinner and reads as hung, not working (user-reported
    with screenshot: percentage stuck at 50 with a stalled second arc)."""

    def test_sweep_issues_increasing_updates_and_never_hits_100(self):
        updates = []

        class _Progress(object):
            def create(self, *a, **k):
                pass

            def update(self, percent=0, **k):
                updates.append(percent)

            def close(self):
                pass

        def _slow_pick(excluded):
            time.sleep(0.9)
            return _item('Q1', en='Slow')

        with mock.patch.object(rmu, 'pick_random', _slow_pick):
            result = rmu._pick_with_progress(set(), _Progress())

        self.assertIsNotNone(result)
        self.assertGreater(len(updates), 1,
                           'progress must animate, not sit at one value')
        self.assertEqual(updates, sorted(updates),
                         'sweep must be monotonically increasing')
        self.assertLessEqual(max(updates), 95,
                             'must not claim 100% while still waiting')

    def test_worker_exception_propagates(self):
        """A failure inside the threaded fetch must not be swallowed into a
        silent "no movies found" — it must surface like the inline call."""

        def _boom(excluded):
            raise RuntimeError('wdqs exploded')

        with mock.patch.object(rmu, 'pick_random', _boom):
            with self.assertRaises(RuntimeError):
                rmu._pick_with_progress(set(), None)


if __name__ == '__main__':
    unittest.main()

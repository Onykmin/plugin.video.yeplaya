# Random Episode Picker — Spec

Status: DRAFT spec only. No production code touched.

## 1. Summary + design decisions

Feature: "shuffle/reroll" button that random-picks one episode from a series, shows a modal
(episode + best version), lets user Play / [Reroll or Start over, state-dependent, or absent for a
pool of 1] / Cancel. Two entry points, gated by one setting.

Decisions (authoritative, not up for debate):
- Entry point A: top of series view (`browse_series`, series_ui.py:60) — random across ALL seasons.
- Entry point B: top of season view (`browse_season`, series_ui.py:107) — random within THAT season.
- NOT a context-menu item on search-results rows.
- Modal = single dialog per pick (S##E## + title + best-version quality/size), 2-3 rows depending on
  pool state (§7 table), loops on Reroll/Start over. Not a version-list picker, not two-step.
- Repeat avoidance = in-memory exclusion set, scoped to the lifetime of the reroll `while` loop in
  `show_random_episode_dialog` (**NEW**, lib/series_ui.py) — i.e. one Kodi menu-action process
  (main.py:14/17 `router(sys.argv[2][1:])` runs once per invocation; CLAUDE.md gotcha: "each menu
  action = fresh Python process → in-memory cache resets"). A later separate invocation (user backs
  out and clicks the row again) starts a fresh empty exclusion set — nothing persisted, no new storage.
  Exhaustion: when `len(excluded) >= len(all_episodes)`, the loop does NOT auto-reset — it renders a
  **Start over** row (replacing the Reroll row slot for that iteration, see §6/§7) and only resets the
  exclusion set to `{last_pick}` if the user explicitly picks it (so the very next pick can repeat
  everything except the one just shown) — never dead-ends, but never silently loops either.
  Single-episode case: exclusion bookkeeping is skipped entirely, the Reroll/Start-over row slot is
  omitted (see §10).
- Distribution: **uniform over the flattened list of all episodes**, not "pick season uniformly, then
  pick episode uniformly within it" (which is literally what the user wrote — "randomly picks one
  episode from random season"). Deliberate divergence: season-then-episode double-weights episodes in
  short seasons (e.g. a 6-episode season and a 22-episode season would each have equal ~1/N_seasons
  chance of being chosen, so a single episode in the 6-ep season is ~3.7x more likely than one in the
  22-ep season). Flatten-then-uniform gives every episode equal probability regardless of season size —
  matches the user's actual goal ("something to watch while eating, don't care which season"). User
  brief explicitly told us to note this divergence, so it's intentional, not a bug.
- Settings: one boolean toggle, `random_episode`, default **false** — CONFIRMED opt-in, matching the
  `experimental` (settings.xml:23, also `default="false"`) precedent for a new/unproven row; avoids
  surprising existing users with new UI rows on upgrade.
  When off: BOTH rows (series-view + season-view) are omitted entirely (not disabled/greyed) —
  mirrors gating precedent at lib/ui.py:189 `if 'true' == _addon.getSetting('experimental'):`.

## 2. Settings

| Field | Value |
|---|---|
| id | `random_episode` |
| type | `bool` |
| default | `false` |
| category | the single `<category label="30204">` (settings.xml:3) |
| label string | **30439** (see §3) |
| group separator label | **30433** (see §3), new `lsep` group, own section |

Exact XML insertion — **after** settings.xml:35 (`track_watched` row), **before** settings.xml:36
(`</category>`):

```xml
        <setting type="lsep" label="30433" />
        <setting label="30439" id="random_episode" type="bool" default="false" />
```

Full tail of file after edit (settings.xml:33-38, was 33-37):
```xml
        <setting type="lsep" label="30290" />
        <setting label="30291" id="track_resume" type="bool" default="true" />
        <setting label="30292" id="track_watched" type="bool" default="true" />
        <setting type="lsep" label="30433" />
        <setting label="30439" id="random_episode" type="bool" default="false" />
    </category>
</settings>
```

Read convention (utils.py:52/59 pattern): `'true' == _addon.getSetting('random_episode')`.

## 3. Localization

3 files, identical new blocks (max existing id is 30432 in all three, verified 30431/30432 are the
last entries — new ids start contiguously at **30433**, no gaps; ids now run **30433-30443** after the
§8 rework added the pick-version row):

- `resources/language/resource.language.en_gb/strings.po`
- `resources/language/resource.language.cs_cz/strings.po`
- `resources/language/resource.language.sk_sk/strings.po`

| id | purpose | en | cs | sk |
|---|---|---|---|---|
| 30433 | settings group separator | Random episode | Náhodná epizoda | Náhodná epizóda |
| 30434 | series-view row label | Random episode | Náhodná epizoda | Náhodná epizóda |
| 30435 | season-view row label | Random episode (this season) | Náhodná epizoda (tato série) | Náhodná epizóda (táto séria) |
| 30436 | dialog "Play" row label | Play | Přehrát | Prehrať |
| 30437 | dialog "Reroll" row label | Reroll | Vybrat znovu | Vybrať znova |
| 30438 | dialog "Cancel" row label | Cancel | Zrušit | Zrušiť |
| 30439 | settings toggle label | Enable random episode picker | Povolit náhodný výběr epizody | Povoliť náhodný výber epizódy |
| 30440 | "no episodes to pick" (parallels 30408 "No versions found") | No episodes available to pick | Žádné epizody k výběru | Žiadne epizódy na výber |
| 30441 | Start over row's `label2` hint (repurposed, was exhaustion popinfo — see §6) | All episodes shown, start over to see repeats | Všechny epizody zobrazeny, začněte znovu pro opakování | Všetky epizódy zobrazené, začnite znova pre opakovanie |
| 30442 | dialog "Start over" row label (exhaustion state, replaces Reroll slot — see §6) | Start over | Začít znovu | Začať znova |
| 30443 | dialog "Pick version" row label (with version count) | Pick version ({0}) | Vybrat verzi ({0}) | Vybrať verziu ({0}) |

Register modelled on: cs 30212 "Download file" → "Stáhnout soubor" and 30213 "Remove from history" →
"Smazat z historie" (infinitive verb phrases for action rows); sk 30212 → "Stiahnuť súbor" and 30213 →
"Zmazať z histórie" (same pattern, sk infinitive). Reroll deliberately does NOT translate as a bare
"Znovu"/"Znova" (adverb, no verb) — house style for action rows is an infinitive verb phrase, so
"Vybrat znovu" / "Vybrať znova" ("pick again") reads consistently with 30212/30213/30214 ("Přidat do
Chci si stáhnout" / "Pridať do Chcem si stiahnuť") rather than a bare adverb with an implied verb.
"Start over" mirrors the same infinitive-phrase register: cs "Začít znovu", sk "Začať znova" — cf. the
mandatory cs "znovu" vs sk "znova" distinction and cs "Začít" vs sk "Začať". 30441's hint text borrows
register from 30408 "No versions found" → cs "Nenalezeny žádné verze" / sk "Nenašli sa žiadne verzie"
(short declarative status line, not an imperative) and reuses cs "žádné"/sk "žiadne" per the mandatory
distinction list.

cs/sk are independently authored, not diacritic-swapped: "epizoda" (cs) vs "epizóda" (sk), "série" (cs)
vs "séria" (sk) — both match the existing cs "Série"/sk "Séria" split verified at 30403/30404 ("Season
{0} ({1} {2})" → cs "Série {0}..." / sk "Séria {0}..."), so this feature's season-scope qualifier reuses
the house term rather than a synonym; "výběru"/"výber" and "začněte"/"začnite" verb-form endings differ
per each locale's own conjugation, not a search-replace of one over the other.

30443 takes the version count as `{0}`, same placeholder convention as 30406's
`"Episode {0} [{1} versions]"` (count substituted via `.format(N)`). cs "verzi" is the accusative
singular of "verze" and sk "verziu" is the accusative singular of "verzia" — correct case for a direct
object following an infinitive ("Vybrat verzi" = "pick a version", "Vybrať verziu" = same in sk), and
independently authored per-locale (not a diacritic swap of one over the other), matching the
"epizoda"/"epizóda" and "série"/"séria" distinction already established above.

No string here is flagged unsure — all rows are modelled on a cited neighbour above.

Reused ids (no new entries): 30107 (generic param error), 30407 ("Error" heading), 30408 ("No versions
found" body — used when the picked episode itself has zero versions, mirrors series_ui.py:226-231),
30431 ("Series not found").

Convention (VERIFIED): all three files share identical `msgctxt` + `msgid` (English source text).
`resources/language/resource.language.en_gb/strings.po` leaves `msgstr ""` empty (English lives in
msgid) — verified at en_gb 30431/30432. `.../resource.language.cs_cz/strings.po` and
`.../resource.language.sk_sk/strings.po` carry the translation in `msgstr` — verified: cs_cz
`#30431 msgstr "Seriál nenalezen"`, sk_sk `#30431 msgstr "Seriál nenájdený"`; cs_cz
`#30428 msgstr "[Film]"`. Each file begins with a 4-line `#` comment header then a `msgid ""`/
`msgstr ""` metadata block carrying `"Content-Type: text/plain; charset=UTF-8\n"` and
`"Language: xx\n"` (en_gb lines 1-11) — new blocks append at end of file.

Exact `.po` block to paste into all three files (values per-locale from the table above):

en_gb:
```
msgctxt "#30433"
msgid "Random episode"
msgstr ""

msgctxt "#30434"
msgid "Random episode"
msgstr ""

msgctxt "#30435"
msgid "Random episode (this season)"
msgstr ""

msgctxt "#30436"
msgid "Play"
msgstr ""

msgctxt "#30437"
msgid "Reroll"
msgstr ""

msgctxt "#30438"
msgid "Cancel"
msgstr ""

msgctxt "#30439"
msgid "Enable random episode picker"
msgstr ""

msgctxt "#30440"
msgid "No episodes available to pick"
msgstr ""

msgctxt "#30441"
msgid "All episodes shown, start over to see repeats"
msgstr ""

msgctxt "#30442"
msgid "Start over"
msgstr ""

msgctxt "#30443"
msgid "Pick version ({0})"
msgstr ""
```

cs_cz (same msgctxt/msgid; msgstr filled):
```
msgctxt "#30433"
msgid "Random episode"
msgstr "Náhodná epizoda"

msgctxt "#30434"
msgid "Random episode"
msgstr "Náhodná epizoda"

msgctxt "#30435"
msgid "Random episode (this season)"
msgstr "Náhodná epizoda (tato série)"

msgctxt "#30436"
msgid "Play"
msgstr "Přehrát"

msgctxt "#30437"
msgid "Reroll"
msgstr "Vybrat znovu"

msgctxt "#30438"
msgid "Cancel"
msgstr "Zrušit"

msgctxt "#30439"
msgid "Enable random episode picker"
msgstr "Povolit náhodný výběr epizody"

msgctxt "#30440"
msgid "No episodes available to pick"
msgstr "Žádné epizody k výběru"

msgctxt "#30441"
msgid "All episodes shown, start over to see repeats"
msgstr "Všechny epizody zobrazeny, začněte znovu pro opakování"

msgctxt "#30442"
msgid "Start over"
msgstr "Začít znovu"

msgctxt "#30443"
msgid "Pick version ({0})"
msgstr "Vybrat verzi ({0})"
```

sk_sk (same msgctxt/msgid; msgstr filled):
```
msgctxt "#30433"
msgid "Random episode"
msgstr "Náhodná epizóda"

msgctxt "#30434"
msgid "Random episode"
msgstr "Náhodná epizóda"

msgctxt "#30435"
msgid "Random episode (this season)"
msgstr "Náhodná epizóda (táto séria)"

msgctxt "#30436"
msgid "Play"
msgstr "Prehrať"

msgctxt "#30437"
msgid "Reroll"
msgstr "Vybrať znova"

msgctxt "#30438"
msgid "Cancel"
msgstr "Zrušiť"

msgctxt "#30439"
msgid "Enable random episode picker"
msgstr "Povoliť náhodný výber epizódy"

msgctxt "#30440"
msgid "No episodes available to pick"
msgstr "Žiadne epizódy na výber"

msgctxt "#30441"
msgid "All episodes shown, start over to see repeats"
msgstr "Všetky epizódy zobrazené, začnite znova pre opakovanie"

msgctxt "#30442"
msgid "Start over"
msgstr "Začať znova"

msgctxt "#30443"
msgid "Pick version ({0})"
msgstr "Vybrať verziu ({0})"
```

## 4. Routing

New action: **`random_episode`** — one action, not two. Disambiguated by presence/absence of `season`
in params (mirrors how `browse_season` vs `browse_series` both flow through `series_name` and only
`browse_season` carries `season`, series_ui.py:107 vs 60). Rationale for one action over two: the
handler needs the exact same grouped-data fetch, exclusion-set loop, and dialog code regardless of
scope — splitting into `random_episode_series` / `random_episode_season` would duplicate the whole
reroll loop for a one-line branch (`if 'season' in params: restrict to that season else flatten all`).
One handler, `lib/series_ui.py` **NEW** `show_random_episode_dialog(params)`, branches internally.

lib/routing.py:11 — add import (append to existing series_ui import line):
```python
from lib.series_ui import browse_series, browse_season, browse_other, select_version, select_movie_version, show_random_episode_dialog
```

lib/routing.py — insert into the if/elif chain. Exact placement: immediately after the
`elif params['action'] == 'select_movie_version':` block (routing.py:80-81), before
`elif params['action'] == 'browse_other':` (routing.py:82), keeping it adjacent to the other
series_ui-owned actions:

```python
        elif params['action'] == 'select_movie_version':
            select_movie_version(params)
        elif params['action'] == 'random_episode':
            show_random_episode_dialog(params)
        elif params['action'] == 'browse_other':
            browse_other(params)
```

main.py:50-51 — **REQUIRED** change, per CLAUDE.md hard gotcha (non-folder/IsPlayable action calling
`setResolvedUrl` must be in `_RESOLVE_ACTIONS` or the fatal-error fallback calls `endOfDirectory`
instead and leaves a spinner). The dialog handler resolves the handle exactly like `show_version_dialog`
does (series_ui.py:265-274) — same contract, same requirement:

```python
            _RESOLVE_ACTIONS = {'play', 'select_version', 'select_movie_version',
                                'newsearch', 'random_episode'}
```

Checklist item — do not skip this line change.

## 5. UI injection

Row shape mirrors the inert-separator precedent (series_ui.py:363-365 / 416-418) and the playable-row
precedent at browse_season's multi-version branch (series_ui.py:162-193: `IsPlayable` property +
`set_webshare_id` + `isFolder=False`). This row IS playable (opens a dialog that itself resolves the
handle), so it follows the **multi-version pattern**, not the inert-separator pattern.

**In `browse_series` (series_ui.py:60-104)** — insert after the not-found guard (series_ui.py:81-84)
and after `series_data = grouped['series'][series_name]` (series_ui.py:86), before the
`for season_num in sorted(...)` loop (series_ui.py:88), so it is the first row in the directory
listing:

```python
    if 'true' == _addon.getSetting('random_episode') and series_data.get('total_episodes', 0) > 0:
        listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30434))
        listitem.setArt({'icon': 'DefaultTVShows.png'})
        listitem.setProperty('IsPlayable', 'true')
        url = get_url(action='random_episode', series=series_name, what=params['what'],
                       category=params.get('category'), sort=params.get('sort'))
        xbmcplugin.addDirectoryItem(_handle, url, listitem, False)
```

Suppressed when: setting off (`'true' != getSetting`), OR `total_episodes` is 0/missing (covers the
"series with zero parsed episodes" edge case, §10) — condition combines both, row simply not added,
no popinfo needed since it's a listing omission not a user action.

**In `browse_season` (series_ui.py:107-195)** — insert after `setContent(_handle, 'episodes')` (line
127) and after `episodes_dict` is available (fetched at line 129 region), before the
`for ep_num in sorted(episodes_dict.keys()):` loop (line 137), so it's the first row of the episode
list:

```python
    if 'true' == _addon.getSetting('random_episode') and episodes_dict:
        listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30435))
        listitem.setProperty('IsPlayable', 'true')
        url = get_url(action='random_episode', series=series_name, season=season_num,
                       what=params['what'], category=category, sort=sort_val)
        xbmcplugin.addDirectoryItem(_handle, url, listitem, False)
```

Both rows: `isFolder=False` (4th arg to `addDirectoryItem`) — matches series_ui.py:161/193 pattern for
playable (non-folder) rows, since clicking triggers `random_episode` action which resolves the handle
via the dialog flow (§7), not a further directory listing.

## 6. Selection algorithm

Input: `grouped['series'][series_name]['seasons']` — `{season_int: {episode_int: [version_dict,...]}}`
(grouping.py:673-697 docstring; post-merge already sorted best-first per grouping.py:836-846).

Scope:
- Series-wide (no `season` param): flatten every `(season_num, ep_num)` pair across ALL seasons.
- Season-scoped (`season` param present): flatten only `(season_num, ep_num)` pairs where
  `season_num == int(params['season'])`.

Pseudocode (**NEW**, lives in `show_random_episode_dialog`):

```python
import random  # stdlib, module-scope import at top of series_ui.py

def _flatten_episode_keys(series_data, season_num=None):
    """[(season_int, ep_int), ...] for all episodes with >=1 version,
    optionally restricted to one season."""
    keys = []
    for s_num, episodes in series_data.get('seasons', {}).items():
        if season_num is not None and s_num != season_num:
            continue
        for ep_num, versions in episodes.items():
            if versions:  # skip episodes that parsed but ended up with 0 versions
                keys.append((s_num, ep_num))
    return keys

def _pick_random(all_keys, excluded, last_pick=None):
    """Returns (picked_key, exhausted_bool). Does NOT auto-reset the exclusion
    set on exhaustion — the caller (the dialog loop, §7) decides whether to
    offer "Start over" and only clears `excluded` when the user explicitly
    picks that row. This function never mutates `excluded` itself."""
    remaining = [k for k in all_keys if k not in excluded]
    if not remaining:
        return None, True
    return random.choice(remaining), False
```

Exclusion set: plain `set()` created once per dialog invocation (local var in
`show_random_episode_dialog`, not module-level, not persisted — dies when the function returns, which
happens when the process exits per CLAUDE.md lifecycle gotcha anyway). Add each shown `(season, ep)` to
it after picking, before the reroll-loop redraws the dialog.

Exhaustion (**CHANGED** — no longer silent/automatic): `_pick_random` does NOT clear the exclusion set
itself and does NOT fire a popinfo. When `remaining` is empty, the dialog loop (§7) detects this and
renders a **Start over** row instead of a **Reroll** row for that iteration — the user must explicitly
choose it. Only when the user picks Start over does the loop clear `excluded` to `{last_pick}` (keeping
the currently-shown episode excluded so the very next pick visibly differs) and pick again. This
replaces the old auto-reset-and-`popinfo(30441)` behaviour; see §7 for the state-dependent row logic and
§3 for 30441's repurposed role as the Start over row's `label2` hint text rather than a popinfo.

## 7. Reroll dialog

API: `xbmcgui.Dialog().select(heading, list, useDetails=True)` — chosen because it is the dialog
primitive already used twice in this repo (series_ui.py:261-263, series_ui.py:336) and already
exercised by the test suite's fake `_Dlg.select` (tests/unit/test_modal_version_sort.py:20-44); index
return maps cleanly to N rows, and `-1` (back/escape) is the established cancel signal
(series_ui.py:265/273-274).

**No multiline heading.** `Dialog().select()` takes a single `heading: str` — the underlying signature
is `int select(const String& heading, const std::vector<String>& list, int autoclose=0)`, with no
line1/line2/line3 equivalent; the heading renders into one label control and an embedded `\n` is
skin-dependent, does not reliably wrap. (The "multi-line text" notes in Kodi's docs apply to the
legacy line-based dialogs — `ok()`, `yesno()`, `DialogProgress` — NOT `select()`.) So the heading stays
short and single-line, and all episode info (title, quality, size) moves into the list rows via
`useDetails=True` + `xbmcgui.ListItem` `label`/`label2`, exactly as the two existing call sites already
do.

**`useDetails=True` is established repo style, not a new pattern** — both existing `select()` call
sites already pass it: `lib/series_ui.py:261-263` (`dialog.select('{0} - S{1:02d}E{2:02d}'.format(...),
listitems, useDetails=True)`) and `lib/series_ui.py:336` (`dialog.select(display_name, listitems,
useDetails=True)`). `useDetails` predates Kodi 19 and the target is current Kodi, so no version
hedging is needed. **No new import required** — `xbmcgui` is already imported at series_ui.py:8 and
`ListItem` is always referenced as `xbmcgui.ListItem(...)` (series_ui.py:95, 166, 254, 330, 363, 386);
do not add an import checklist item for this.

Model the new dialog directly on the movie-version block at series_ui.py:326-336, which already builds
exactly the label+label2 shape needed:
```python
listitems = []
for file_dict in versions:
    label = file_dict.get('name', 'Unknown')
    meta_parts = _build_version_metadata(file_dict)
    listitem = xbmcgui.ListItem(label=label)
    if meta_parts:
        listitem.setLabel2(' | '.join(meta_parts))
    listitems.append(listitem)
dialog = xbmcgui.Dialog()
selected = dialog.select(display_name, listitems, useDetails=True)
```

New design:
- **Heading**: short, single-line — series `display_name` (or, season-scoped, the same value used
  today at series_ui.py:260-263's `'{0} - S{1:02d}E{2:02d}'` minus the per-episode suffix, since the
  episode itself now varies per redraw and belongs in the list rows, not the heading). No embedded `\n`.

**Row table (current, post version-picker fix)**:

| Row | Action | Content |
|---|---|---|
| 0 | `play` | `S##E## - <name>`, label2 = best-version metadata |
| 1 | `pick_version` | label 30443 formatted with N = version count. **Present only when N > 1** |
| 2 | `reroll` / `start_over` / absent | existing state-dependent slot, shifted down one index |
| 3 | `cancel` | label 30438, always last |

Row 0 — Play: `label` = `"S{season:02d}E{ep:02d} — {title}"` (season/ep zero-padded, `title` from
`versions[0]`'s parsed name where available), `label2` = the joined `_build_version_metadata(best)`
string, e.g. `"1080p | BluRay | 2.1 GB"` — reusing `_build_version_metadata(file_dict)` (lib/ui.py:29,
imported at series_ui.py:21) exactly as series_ui.py:251-256 does for `setLabel2`, joined with
`' | '` per series_ui.py:333-334 (not `·` — matches repo convention).

**`label2` now carries real track data, not just filename guesses.** `_build_version_metadata`
(lib/ui.py:29-63) gates the useful fields on `file_dict['file_info']`: lib/ui.py:48-50 needs
`file_info.get('audio')` for the `Audio: {...}` part, lib/ui.py:54-55 needs
`file_info.get('subtitles')` for `Subs: {...}`, and the bare `[language]` fallback at lib/ui.py:57-58
only fires when `file_info` is falsy. `file_info` only exists after `enrich_file_metadata`
(lib/metadata.py:76-96) runs on that file — without it, Row 0's `label2` was filename-parsed
`quality_meta` guesses only (resolution/source/codec), never real audio/subtitle tracks. A new helper
`_enrich_displayed_version(file_dict, token)` (lib/series_ui.py, **NEW**) enriches ONLY the one
displayed best version so the user can judge it against their language preferences before pressing
Play.

**Enrichment point in the loop.** The call sits once per pick, in the non-exhausted branch, right
after `best = versions[0]` is assigned (`shown_best`/`shown_season`/`shown_ep` in the actual
lib/series_ui.py code) and before `pool_state` is set — i.e. AFTER the best version is already
chosen (see §8: selection is unchanged) and BEFORE the first `_build_dialog_rows` call for that pick,
so the enriched `label2` is what the very first redraw shows. It is never called from inside the
inner version-picker redraw loop (§7/§8) — a picker back-out just redraws the same already-enriched
`prev_best`, no second call.

Row 1 — Pick version: label = localized 30443 formatted with `N` = `len(versions)` after
`deduplicate_versions` (see §8) for the currently-shown episode. **Omitted when N <= 1** — with a
single version the picker can only return that same file, so the row would be a provably dead
button (same reasoning §7 already applies to hiding Reroll for a pool of 1, restated below).

Row 2 — state-dependent slot (Reroll / Start over / absent), per §1/§6/§10 (pool==1 rationale below;
exhaustion rationale in §6):

| State | Row slot |
|---|---|
| pool > 1, picks remain (`remaining` non-empty) | **Reroll** (30437), `label2` empty |
| pool > 1, all seen (`remaining` empty — exhausted) | **Start over** (30442), `label2` = 30441 hint text |
| pool ≤ 1 | row absent — dialog is Play + [Pick version, if N>1] + Cancel only |

Row 3 — Cancel: `label` = localized 30438; dismissal/ESC returns `-1`, handled identically to
explicit Cancel.

This is a variable-length row list (2 to 4 rows depending on both the reroll pool state AND the
per-episode version count), not multiple dialog paths — the loop always rebuilds `listitems` (and
the parallel `actions` list, below) from scratch on every redraw and re-evaluates both state
questions independently.

**Dispatch is by ACTION NAME, not by hardcoded row index.** `_build_dialog_rows(best, season_num,
ep_num, pool_state, version_count)` returns `(listitems, actions)` — two parallel lists, where
`actions` is e.g. `['play', 'pick_version', 'reroll', 'cancel']` or `['play', 'cancel']` depending on
which optional rows are present for this redraw. Selection resolves as:
```python
selected_index = xbmcgui.Dialog().select(display_name, listitems, useDetails=True)
action = actions[selected_index] if 0 <= selected_index < len(actions) else 'cancel'
```
so `-1` (escape), an out-of-range index, and any dialog quirk all fall through to `'cancel'` by
construction, and the branch that handles each action switches on the string, never on a magic
integer. Rationale: the earlier hardcoded-index design (`selected == 0` / `selected == 1` literals
in the loop body, as originally drafted below) shifted every branch by one every time a row was
inserted or removed — inserting the pick-version row here is exactly that case — and an uncovered
ordering bug of this shape had already sat latent through a green test suite once. Name-based
dispatch makes row order and dispatch order independent, so this class of bug cannot recur.

**pool==1 → Play + Cancel only, no Reroll row.** Rationale: preserves the preview contract (the whole
feature exists to preview an episode before committing to Play), and treats a 1-episode season as
routine, not an error — final seasons, `S00` specials, and partially-released seasons on Webshare all
legitimately have exactly one episode. Rejected alternatives:
- *Auto-play without a dialog* — rejected: no preview step, and the same physical button would behave
  completely differently (skip dialog vs. show dialog) depending on an invisible pool size, which is
  surprising.
- *Show Reroll anyway, toast on press* — rejected: offers a provably dead button; pressing it can never
  produce a different result, so it's a UI lie.
- *Hide the whole row (not just Reroll)* — rejected: a 1-episode season would silently lose the entry
  point row while sibling seasons keep theirs — reads as a bug, not a deliberate state.

Loop structure — note the loop redraws with the CURRENT (not next) pick every time; a Start-over
selection loops back to draw a fresh pick on the next iteration, it never renders the dialog itself.
Dispatch is by action name (see above), via the parallel `actions` list returned by
`_build_dialog_rows`:
```python
last_pick = None
prev_best = prev_season = prev_ep = None  # last-rendered pick — always populated by the time it's
                                           # read (see §7 prose below the code block)
while True:
    picked, exhausted = _pick_random(all_keys, excluded, last_pick)
    if exhausted:
        # Pool exhausted on this draw: keep showing the CURRENT pick (still valid, still on
        # screen) but swap the state slot to Start over instead of Reroll — the user must opt in
        # explicitly before the exclusion set is cleared (§6).
        pool_state = 'start_over'
    else:
        season_num, ep_num = picked
        excluded.add((season_num, ep_num))
        last_pick = (season_num, ep_num)
        versions = deduplicate_versions(series_data['seasons'][season_num][ep_num])
        if not versions:
            popinfo(_addon.getLocalizedString(30440), icon=xbmcgui.NOTIFICATION_WARNING)
            continue  # reroll automatically rather than dead-ending
        best = versions[0]  # already best-ranked, see §8
        _enrich_displayed_version(best, token)  # NEW: real audio/subtitle tracks for label2, see §7/§9
        pool_state = 'reroll' if len(all_keys) > 1 else 'none'
        prev_best, prev_season, prev_ep = best, season_num, ep_num
        prev_versions = versions  # held so the pick_version row can reuse it without re-deduping (§8)

    listitems, actions = _build_dialog_rows(prev_best, prev_season, prev_ep, pool_state,
                                             len(prev_versions))
    selected_index = xbmcgui.Dialog().select(display_name, listitems, useDetails=True)
    action = actions[selected_index] if 0 <= selected_index < len(actions) else 'cancel'

    if action == 'play':
        ep_state_key = state_key_for({'series_name': series_name, 'season': prev_season, 'episode': prev_ep})
        resolve_and_play(prev_best['ident'], prev_best['name'], token, state_key=ep_state_key)
        return
    elif action == 'pick_version':
        # Inner redraw loop: opens the EXISTING version picker for this episode (§8). Backing out
        # (-1) returns here to redraw the SAME episode — no re-pick, no resolve (§8/§10).
        chosen = _run_version_picker(prev_versions, token, display_name, prev_season, prev_ep)
        if chosen is not None:
            ep_state_key = state_key_for({'series_name': series_name, 'season': prev_season, 'episode': prev_ep})
            resolve_and_play(chosen['ident'], chosen['name'], token, state_key=ep_state_key)
            return
        continue  # back-out: redraw the random dialog with the same prev_* pick
    elif action == 'reroll':
        continue
    elif action == 'start_over':  # user opted in
        excluded.clear()
        if last_pick is not None:
            excluded.add(last_pick)
        continue
    else:  # 'cancel', or -1/escape/out-of-range mapped to 'cancel' above
        xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
        return
```
(`_build_dialog_rows(prev_best, prev_season, prev_ep, pool_state, version_count)` is a small helper
that assembles the Play row from `prev_best`/`prev_season`/`prev_ep` as described above, appends the
Pick-version row (label 30443 formatted with `version_count`) only when `version_count > 1`, appends
Reroll/Start-over per `pool_state`, and always appends Cancel last — returning the matching `actions`
list alongside `listitems` so dispatch never depends on which optional rows ended up present. Kept
out of the main loop body for readability. `prev_best`/`prev_season`/`prev_ep`/`prev_versions` are
updated only in the non-exhausted branch, right after `best`/`versions` are computed, so on a
`pool_state == 'start_over'` iteration they simply still hold the values from the previous iteration
— the currently-displayed episode — since exhaustion is detected BEFORE a new pick is made. On entry
to the loop the pool is already known non-empty — pool==0 suppresses the `random_episode` row
entirely per §5/§10, and the "no episodes to pick" guard for an empty flatten result bails with
`popinfo(30440)` + `setResolvedUrl(_handle, False, ...)` before the loop ever starts — so the first
iteration can never be exhausted, and the `start_over` branch can never be reached before
`prev_best`/`prev_season`/`prev_ep`/`prev_versions` have been populated at least once.)

The `if not versions: ... continue` branch above adds the key to `excluded` before looping, so it
can never spin forever on one key. But if the defensive branch fired for every remaining key in the
pool — i.e. exhaustion is reached without ever rendering a Play row on this invocation — the loop
would otherwise exhaust, offer Start over, clear `excluded`, and spin again indefinitely. Guard
against this: track whether any key has been successfully rendered (`versions` non-empty) since the
loop started; if `exhausted` is reached and nothing has ever been rendered, treat it the same as
pool==0 — `popinfo(30440)` + `xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())` + return,
rather than offering Start over. `_flatten_episode_keys`'s `if versions:` filter (§6) already makes
this combination unreachable in practice (every key in `all_keys` is guaranteed to have a non-empty
version list at flatten time), so this is a defensive backstop only, not an expected runtime path.

`setResolvedUrl` contract on every exit path (mirrors series_ui.py:265-274 / lib/playback.py:51
`resolve_and_play` internals), restated for the pick-version row added by this fix:
- Play → delegated to `resolve_and_play` (playback.py:51), which itself calls `setResolvedUrl(True,...)`
  on success or `setResolvedUrl(False,...)` + `popinfo(30308)` on failure — handler does NOT double-call.
- Pick-version-then-play → same delegation to `resolve_and_play`, called on the CHOSEN version, not
  `prev_best` — ZERO direct `setResolvedUrl` calls in the handler on this path either.
- Pick-version, then back out of the picker (`-1`) → ZERO `setResolvedUrl` calls: the inner picker
  loop returns `None`, the outer loop `continue`s and redraws the random dialog with the same episode
  — no resolve, no re-pick (this is the "double-resolve trap" called out in §7's decision list: only
  the explicit `cancel` action is allowed to resolve).
- Cancel/escape/out-of-range → `xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())`
  explicitly, exactly once, via the action-name dispatch's `else` branch.
- No-episodes-at-entry (§10) → same `setResolvedUrl(False, ...)` before returning, never falls through.
- Param validation failure (missing/bad `series`/`season`) → same pattern as series_ui.py:207-211:
  `popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)` +
  `setResolvedUrl(_handle, False, xbmcgui.ListItem())` + return.

Net: exactly one `setResolvedUrl` call per invocation on every non-play exit; zero on the play and
pick-version-then-play paths (both delegate to `resolve_and_play`, which resolves internally); zero
on the picker back-out path (it loops instead of exiting).

## 8. Version handling

**Revision history — this section replaces the original decision.** The original §8 (see git history)
decided: "best = `versions[0]`; other versions not shown at all; out of scope for this feature." A
smoke test on a real install (Gachiakuta, ~27 versions of a single episode) surfaced that this
under-served the user's actual stated requirement — the user asked for a modal that "shows different
version of one episode" (plural), and the original design exposed exactly one of ~27 as reachable
from the random dialog. **This was a spec defect, not an implementation defect**: `lib/series_ui.py`
implemented `versions[0]`-only exactly as specced; the fix below is a spec correction, not a bugfix
to code that diverged from spec.

**Play row — superseded by the third correction below.** The paragraph that used to stand here
claimed "best" = `versions[0]` after `deduplicate_versions()` alone, on the assumption that
group-time sorting already left `versions[0]` best-ranked by the time it reached this handler. That
assumption is FALSE for the random dialog's own pick path — see "Third correction" below for why, and
for the actual fix (Defect A). An intermediate draft of this paragraph additionally claimed the
episode/movie pickers were unknowingly relying on an inverted sort key elsewhere in the repo ("Defect
B", below) even where a re-sort DID happen — that claim is RETRACTED by the "Fourth correction" below:
there was no inverted key, size-first is the correct and intended order, so this paragraph's claim
only fails to hold for the reason actually described in "Third correction"/"Fourth correction" (the
random dialog's own pick path never sorted before taking `versions[0]`), not because of any inverted
key elsewhere.

**Selection is deliberately UNCHANGED by the §7/§9 metadata-enrichment fix.** Whatever ranking
produces the Play row's version, `_enrich_displayed_version` (§7/§9) is called strictly AFTER that
choice is made, purely to fill in `file_info` for display — it never re-orders or re-filters
`versions`.

**Third correction — two version-ordering defects found in smoke testing, both "fixed" at the time —
SUPERSEDED by the fourth correction below.** A real-install smoke test (Gachiakuta S01E24) showed the
Play row offering a worse version than the best available. Two distinct defects were diagnosed at the
time; Defect A's fix stands, Defect B's fix was reverted (see the fourth correction block immediately
below — read that block before relying on anything about ranking order in this one):

- **Defect A, introduced by this feature — STILL VALID, not superseded.** `show_random_episode_dialog`
  did `shown_best = versions[0]` where `versions = deduplicate_versions(...)`. `deduplicate_versions`
  (grouping.py:612-623) is explicitly documented as "preserving order" — it is a seen-set filter that
  performs NO sort. So the second correction's "Play row — unchanged" claim above was FALSE for this
  path specifically: `versions[0]` is only best after a sort, and this path never sorted before
  picking. The random dialog's Play row was therefore showing whatever order the API/grouping pass
  happened to yield, not the best version. The fix (call `_rank_versions` before taking `[0]`) remains
  correct regardless of which key `_rank_versions` sorts by — see the fourth correction below.
- **Defect B — RETRACTED, this was never a defect.** At the time, the pick-variant sort in both
  `show_version_dialog`'s predecessor code and `select_movie_version` was believed to be wrong for
  using size as the PRIMARY sort field with quality score only as tiebreak. Since `_safe_size`
  (grouping.py:93-113) returns 0 for a version with an absent/unparseable size, any version lacking a
  size ranked below every version that had one, regardless of quality — e.g. a 1080p WEB-DL H264
  multi-audio file with no size sank below a lower-quality 1.43GB x264. This was diagnosed as a bug and
  "fixed" by flipping the sort to quality-first (see the "The fix" paragraph below, which described
  that now-reverted change). **The user was asked and confirmed the opposite preference: size-first
  (largest file first) is the ordering they actually want in the episode and movie pick lists, and the
  quality-first flip was rejected and reverted — see the fourth correction block below.** `_safe_size`
  itself was never changed by any of this and remains as originally shipped: mapping absent → 0 is
  correct for a tiebreak, and adding a sentinel to distinguish "absent" from "0 bytes" would complicate
  every caller for no user-visible gain.
- **The repo already agreed with the correct order — this claim was the mistake.** `_version_sort_key`
  (grouping.py:116-137) returns `(quality_score, size)` used with `reverse=True`, docstring: "quality
  first, size breaks ties" — and the grouping passes already use it (grouping.py:867, 973, 1010). At
  the time this was read as meaning the two `series_ui.py` sort sites were outliers that should be
  aligned to it. That reasoning is now explicitly rejected: `_version_sort_key` ranks the
  grouping/merge passes, not the user-facing pick lists, and the two surfaces are allowed to diverge —
  see the fourth correction below for why the divergence is intentional, not an inconsistency.

**"The fix" as originally written here — SUPERSEDED, describes the reverted quality-first change, kept
for history only; see the fourth correction below for the shipped behaviour.** New shared helper
`_rank_versions(versions)` in `lib/series_ui.py`: populates `quality_meta` for every entry first (via
`parse_quality_metadata` on the filename, same as `_version_sort_key` does), THEN sorts in place by
~~`(quality_score, size)` descending — quality first, size as tiebreak, matching
`grouping._version_sort_key`~~ **`(size, quality_score)` descending — size first, quality as tiebreak;
see the fourth correction below.** Population happens inside the same function as the sort, not at
each call site, because reading `quality_meta` lazily during the sort would silently fall back to the
default score of 50 for any entry that hadn't been populated yet and scramble the tiebreak order. Costs
ZERO API calls — `quality_score` comes from filename parsing, not from `enrich_file_metadata`.

**Fourth correction — quality-first REVERTED, size-first is final.** The third correction above flipped
`_rank_versions` (and therefore the episode and movie pick-variant dialogs) to sort
`(quality_score, size)` descending, quality-first. The user rejected this: largest-file-first is the
ordering they actually want in these version lists, and the quality-first flip was reverted. The
shipped, final contract — verified at `lib/series_ui.py`'s `_rank_versions` — sorts
`versions.sort(key=lambda v: (_safe_size(v), v.get('quality_meta', {}).get('quality_score', 50)),
reverse=True)`: **size is the PRIMARY key, quality_score is ONLY the tiebreak between equal-size
entries.** This is the long-standing behaviour of the episode and movie version pickers, matches the
`main` branch, and is not a defect. `grouping._version_sort_key` (quality-first) is pre-existing,
untouched, and feeds only the grouping/merge passes — its divergence from `_rank_versions` is
therefore INTENTIONAL: the two functions serve different audiences (internal grouping/dedup logic vs.
the user-facing pick list) and are not expected to agree. A version with an absent/unparseable size
still gets 0 from `_safe_size` and therefore ranks LAST under size-first — this is accepted and
intended, not a residual instance of the retracted "Defect B". Everything below this point in §8, and
§9, §10, §11, and §12, describes the size-first contract as shipped; read them with this correction in
mind even where an older paragraph's wording has not been individually rewritten.

Three call sites now share `_rank_versions` (all three already sorted size-first before this feature;
"replaced by `_rank_versions`" below means the population/sort code was consolidated into the shared
helper, not that the ordering behaviour changed — see the "Fourth correction" above):
1. `_prepare_episode_versions` — the old lazy-quality loop + size-first sort are replaced by
   `_rank_versions`, and ranking now happens BEFORE the top-5 enrichment (not after), so the API
   budget is spent on the five genuinely-best (largest, per the shipped size-first key) versions
   rather than whichever five the API returned first. Correct-but-different consequence: a different
   5 may now be enriched than before this fix.
2. `select_movie_version` — its inline quality-population + size-first sort block is replaced by the
   same call, so the movie picker's ranking logic is consolidated too, not just the episode picker's.
3. `show_random_episode_dialog` — calls `_rank_versions(versions)` right after dedupe and before
   `shown_best = versions[0]`, fixing Defect A directly. Free (filename-based), so the
   one-`getinfo`-per-pick cost noted in §9 is unchanged. `shown_versions` then holds the ranked list,
   so the `pick_version` picker opened from the same pick is consistently ordered, and
   `_prepare_episode_versions`'s own `_rank_versions` call on that same list is idempotent.

**This paragraph — SUPERSEDED, describes the reverted quality-first change.** It originally claimed
"Defect B's fix intentionally changes long-standing behaviour in the normal episode picker
(`show_version_dialog`) and the movie picker (`select_movie_version`)... since the inverted key was
wrong everywhere it appeared." Per the "Fourth correction" above, there was no inverted key and no
Defect B: size-first is the correct, user-confirmed, long-standing behaviour of both pickers, and it
was NOT changed. The one real, still-valid fix from this block is Defect A's — `_rank_versions` is
now called before `versions[0]` is taken on the random dialog's Play row — and that fix applies only
to the random dialog's new call path, not a repo-wide behaviour change to `show_version_dialog` or
`select_movie_version`.

**Language-aware ranking/filtering — CONSIDERED AND REJECTED.** Neither prefer-matching (re-ranking
versions by audio/subtitle language match against the user's language settings) nor
filter-to-matching (excluding non-matching-language versions from the pool) is implemented, and this
is a standing decision, not an oversight: the user explicitly rejected both when the real-track-data
enrichment (§7/§9) was proposed. The whole point of surfacing real `Audio:`/`Subs:` data on the Play
row is so the user judges by eye — the code does not decide language fit for them. A future change
that "helpfully" adds ranking or filtering by language match would contradict this decision; see §11
for the explicit guard test against it.

**Other versions — now reachable via the new Pick-version row (§7).** All versions other than
`versions[0]` are reachable by selecting the `pick_version` row, which opens the EXISTING episode
version picker for the current `(season, episode)` — the same picker `show_version_dialog` already
uses for the normal browse_season → select_version flow. This is not a new parallel picker.

**Reuse mechanism — extract, don't duplicate.** The enrich/quality/sort core of `show_version_dialog`
is split into two helpers so the random dialog can call the same code the normal browse flow uses:
- `_prepare_episode_versions(versions, token)` — ranks the list via the shared `_rank_versions`
  helper (`(size, quality_score)` descending, size-first — see the "Fourth correction" block above;
  an intermediate draft of this paragraph had it sort quality-desc then size-desc, which was the
  reverted quality-first change, not the shipped contract), THEN enriches the top
  `TOP_FILES_TO_ENRICH = 5` versions of the now-ranked list.
  Enrichment is the only step that touches the network; ranking is filename-based and free.
- `_build_version_listitems(versions)` — builds the `xbmcgui.ListItem` list: `label` = filename,
  `label2` = joined metadata (same shape as the existing picker's rows).

`show_version_dialog` is refactored to call both helpers in sequence, with identical observable
behavior for its existing callers (browse_season → select_version) — no behavior change to that flow.
The random dialog's `pick_version` action calls the same two helpers on `prev_versions` (the
already-deduplicated list for the currently-shown episode), so there is no second copy of the
enrich/sort/build logic anywhere in the codebase.

**Dedup ownership — exactly one call per caller.** Neither `_prepare_episode_versions` nor
`_build_version_listitems` calls `deduplicate_versions` itself. Each caller (the normal
`show_version_dialog` flow, and the random dialog's loop body in §7) calls `deduplicate_versions`
itself exactly once. This matters because the count `N` shown in the `pick_version` row label
(30443) is `len(prev_versions)`, i.e. the length of the SAME already-deduplicated list the picker
then displays — a second, independent dedupe call inside the helpers could silently produce a
different length than what the row advertised (e.g. if dedup logic ever became non-idempotent), so
ownership is deliberately single and explicit rather than defensive-duplicated.

## 9. Data sourcing & cost

`get_or_fetch_grouped(params, token, check_key=series_name, check_type='series')` (lib/cache.py:139-160)
called **once** at handler entry, result (`grouped`) held in a local variable for the entire reroll
`while` loop — `_pick_random` / dialog redraws never re-fetch. Cache TTL `DEFAULT_CACHE_TTL = 300`
(cache.py:55) is irrelevant within a single reroll session since the same in-memory `grouped` dict is
reused for every iteration of the loop (no repeated `cache_get`/`cache_set` calls after the first).
This part is unchanged and still matters: `get_or_fetch_grouped` stays at exactly one call per
invocation, regardless of how many times the user rerolls. Cross-process: a new invocation is always
a fresh process (per the CLAUDE.md lifecycle gotcha), so it re-runs `get_or_fetch_grouped` and
re-fetches from the API whenever the 300s TTL has expired — same as every other series_ui.py entry
point, no new behavior introduced here.

**The previous "zero additional API calls per reroll" claim NO LONGER HOLDS — corrected here.** The
§7/§9 metadata-enrichment fix (real `Audio:`/`Subs:` data on the Play row, see §7) adds exactly
**one `getinfo` call per pick**: `_enrich_displayed_version` calls `enrich_file_metadata` on the
single displayed version, once per pick, in the outer loop's non-exhausted branch (§7). This is per
PICK, not per redraw — the `'file_info' in file_dict` guard (§10) plus the outer-branch placement
mean a version-picker back-out redraw costs nothing extra, and re-displaying an already-enriched
version (e.g. after backing out of the picker) is a no-op, since it's the same `file_dict` object
still holding `file_info` from the first enrichment. The user explicitly accepted this cost in
exchange for seeing real audio/subtitle tracks on the row instead of filename-parsed guesses. Only
ONE version is enriched per pick, not all of them — an episode can have ~27 versions (§8's
Gachiakuta case), and enriching the whole list at pick time was rejected as unnecessary cost for
data the user will mostly never look at. Opening the version picker still enriches the top 5
(`TOP_FILES_TO_ENRICH = 5`, §8) exactly as the existing episode picker always did — that part is
unaffected — and `_prepare_episode_versions`'s enrich loop now skips any index whose `file_dict`
already has `'file_info'` (i.e. the one the Play row already enriched), so opening the picker after
Play-row enrichment does not re-fetch that same ident.

`deduplicate_versions` runs on every pick (cheap, in-memory, no API call), which is why the
`pick_version` row's count `N` is available for free on every redraw, including plain rerolls — this
part of the original claim is unaffected by the correction above.

**Version-ranking fix (§8 "Third correction") does not change this section's cost figures.**
`_rank_versions` is filename-based (reads/populates `quality_meta` via `parse_quality_metadata`,
same as `_version_sort_key`) and makes no API call, so ranking `versions` right before
`shown_best = versions[0]` at pick time is free — the one-`getinfo`-per-pick figure above is
unaffected. What changes is WHICH five versions the enrichment budget in
`_prepare_episode_versions` is spent on when the user opens `pick_version`: ranking now happens
before the top-5 enrich loop (not after), so the top 5 of the RANKED list are enriched, not the top
5 of whatever order the API/grouping pass returned. Still exactly 5 enrichment calls at most per
`pick_version` open, same as before — only the selection of which 5 changed.

## 10. Edge cases

| Case | Behaviour |
|---|---|
| Series has 0 parsed episodes (all failed `parse_episode_info`, parsing.py:511, landed in `non_series`) | Row not injected entirely — this is pool==0, unchanged from current behaviour (§5 guard: `total_episodes > 0` / `episodes_dict` truthy check) |
| Exactly one episode in the current pool (`len(all_keys) == 1`) — CONFIRMED, no longer an assumption | Skip exclusion bookkeeping entirely, present Play + [Pick version, if N>1] + Cancel (Reroll/Start-over row absent per §7 table) — avoids an infinite no-op reroll since the pool would always resolve to the same single key. **Diagnostic distinction (same behaviour, different meaning):** pool==1 at *season* level is routine/benign — final seasons, `S00` specials, and partially-released seasons on Webshare all legitimately have one episode. pool==1 at *series* level (whole-series flatten, no `season` param) usually signals bad parsing rather than a genuine one-episode series, and is worth a closer look if it recurs — but the UI behaviour is identical in both cases; only the operator-facing interpretation differs, so no code branch distinguishes them. |
| Picked episode has exactly 1 version (`N == 1`) | `pick_version` row omitted (§7/§8) — dialog is Play + [state slot] + Cancel; with one version the picker could only return that same file, so the row would be a provably dead button |
| User opens the version list (`pick_version`) then backs out (`-1`) | Returns to the random dialog with the SAME episode still shown (`prev_best`/`prev_season`/`prev_ep` unchanged) — no resolve, no re-pick; the inner picker loop returns `None` and the outer loop `continue`s (§7/§8) |
| User opens the version list and picks a non-best version | That version plays via `resolve_and_play(chosen['ident'], chosen['name'], ...)` — i.e. the CHOSEN version's ident, not `prev_best`'s — and the random loop returns immediately after, exactly like the plain Play path (§7) |
| A version has full metadata but NO size, vs a lower-quality version WITH a size (the screenshot case, §8 "Third correction"/"Fourth correction") | The SIZED version ranks first via `_rank_versions`'s `(size, quality_score)` key — size is primary, so the sizeless version (`_safe_size` returns 0 for it) ranks LAST regardless of its quality score. This is the shipped, user-confirmed size-first contract (§8 "Fourth correction"), not the retracted "Defect B" framing — a lower-quality sized file beating a higher-quality sizeless file is intended, not a bug |
| No version in the list has a size | Ranking falls back entirely to `quality_score` as the tiebreak, since `_safe_size` returns 0 for every entry and the primary key is constant |
| All versions have a size and their quality scores tie | `quality_score` breaks the tie (unchanged behaviour for this case — size remains primary; quality is always only the tiebreak) |
| A version dict is missing `quality_meta` when `_rank_versions` runs | `_rank_versions` populates `quality_meta` for every entry (via `parse_quality_metadata` on the filename) BEFORE sorting, so this case cannot reach the sort key unpopulated. Guards against the "silent default 50" trap — reading `quality_meta` lazily during the sort, instead of populating first, would fall back to a default score of 50 for that one entry and scramble the order relative to entries that already had a real score |
| Movies / non_series | Never enters this code path — `random_episode` action requires `series` param, only reachable from `browse_series`/`browse_season` rows which only exist for `grouped['series']` entries; movies use `select_movie_version` (routing.py:80), non_series use `browse_other` (routing.py:82). No shared surface. |
| Episode parsed into `series_data['seasons']` but that episode's version list is empty (e.g. all versions filtered elsewhere) | `_flatten_episode_keys` skips it (`if versions:` guard) — never selectable; if this empties the whole flatten result, treat as "no episodes to pick" (§10 next row) |
| No episodes to pick at all (flatten result empty) | `popinfo(_addon.getLocalizedString(30440), icon=xbmcgui.NOTIFICATION_WARNING)` + `xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())` + return — mirrors series_ui.py:226-231 "no versions found" pattern |
| Defensive `if not versions: ... continue` branch (§7) fires for every key in the pool, so exhaustion is reached without ever rendering a Play row on this invocation | Treat as pool==0: `popinfo(30440)` + `xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())` + return, instead of offering Start over — prevents an exhaust/clear/spin infinite loop. Defensive backstop only: `_flatten_episode_keys`'s `if versions:` filter (§6) already guarantees every key in `all_keys` has a non-empty version list at flatten time, so this row is unreachable in practice |
| Unparsed/ambiguous numbering (e.g. absolute-numbered file `parse_episode_info` returns None) | File never reaches `grouped['series']` (parsing.py:511 returns None → grouping.py routes to `non_series`) — invisible to this feature by construction, no special handling needed |
| Cache miss/expiry mid-loop | Cannot happen — `grouped` fetched once at entry, held in local var for the loop's lifetime (§9); TTL expiry only affects the NEXT process's fetch |
| Cancel | `setResolvedUrl(_handle, False, xbmcgui.ListItem())`, no popinfo (silent, matches series_ui.py:273-274 else-branch tone) |
| API failure mid-reroll (`resolve_and_play` fails after user picks Play) | Handled entirely inside `resolve_and_play` (playback.py:51) — it calls `popinfo(30308)` and `setResolvedUrl(False)` itself; handler just returns after calling it, no duplicate error handling |
| `int(params['season'])` / episode-count parse failure (malformed URL) | Same guard pattern as series_ui.py:207-211: catch `(ValueError, TypeError, KeyError)`, `popinfo(30107)` + `setResolvedUrl(False)` + return |
| `enrich_file_metadata` fails or returns `False` for the displayed version (bad/unknown ident, empty `getinfo`, network error) | It logs and returns `False` without raising (lib/metadata.py:76-96 already swallows its own failures) — the Play row still renders from `quality_meta` (filename-parsed guesses only, no `Audio:`/`Subs:` lines), and the dialog and reroll loop stay fully usable. Degradation is silent by design — no `popinfo` for a metadata miss |
| Asymmetry on the `getinfo`-returns-falsy path | `enrich_file_metadata` returns before setting `file_info` on that path, so the version has no `file_info` key at all (not an empty one) — `_build_version_metadata` falls back to the bare `[language]`/`quality_meta` rendering exactly as it would for a never-enriched version. The outer-branch placement (§7) still means only one enrichment attempt is made per pick; a failed attempt is not retried on the same pick |
| Same version re-displayed (user backs out of the version picker, or a `start_over`/exhaustion redraw re-shows the current pick) | No second `enrich_file_metadata` call — guarded by `'file_info' in file_dict` in `_enrich_displayed_version` (§7/§9), and by the call living in the outer pick branch, not the inner redraw loop, so a redraw of the same pick can never reach the call site again |
| Version picker (`pick_version`) opened after the Play row was already enriched | `_prepare_episode_versions`'s top-5 enrich loop (§8) skips any index where `'file_info' in versions[idx]` — that one ident (the already-enriched best version) is not re-fetched; the other entries in the top 5 still enrich normally |

## 11. Test plan

New file: `tests/unit/test_random_episode.py`. House conventions: this repo uses BOTH
`unittest.TestCase` (test_grouping_bugfixes.py:34) and bare pytest classes (test_routing.py:12) — the
new file may use either. `import tests.conftest  # noqa: F401`, dialog patched via
`patch.object(xbmcgui_mod, 'Dialog', _Dlg)` against the live `sys.modules['xbmcgui']`
(test_modal_version_sort.py:20-44 pattern), `_series()` helper style from
test_grouping_bugfixes.py:26-29.

Determinism: no test currently imports `random`. Patch it explicitly:
`patch.object(series_ui, 'random', <fake>)` (mirrors the existing `patch.object` style for
`revalidate`/`get_or_fetch_grouped`/`enrich_file_metadata`) where `<fake>` is a stand-in object
exposing `.choice(seq)` returning a scripted sequence (e.g. `itertools.cycle` or a list-popping stub) —
NOT `random.seed()`, since the algorithm calls `random.choice`, not seeded generation; patching the
call site is more reliable and matches repo style better than seeding.

Concrete tests:
1. `test_flatten_all_seasons_uniform_keys` — `_flatten_episode_keys(series_data)` returns every
   `(season, ep)` pair across seasons, episodes with empty version list excluded.
2. `test_flatten_season_scoped` — `_flatten_episode_keys(series_data, season_num=2)` restricted to
   season 2 only.
3. `test_setting_off_hides_series_row` — `browse_series` with `getSetting('random_episode') == 'false'`
   → no directory item with the 30434 label added (assert on recorded `addDirectoryItem` calls).
4. `test_setting_off_hides_season_row` — same for `browse_season` / 30435.
5. `test_setting_on_injects_series_row` — setting on, `total_episodes > 0` → row present, first item,
   `IsPlayable` property set, `isFolder=False`.
6. `test_setting_on_injects_season_row` — same for season scope.
7. `test_no_episodes_hides_row` — `total_episodes == 0` (or `episodes_dict` empty) → row absent even
   with setting on.
8. `test_play_choice_calls_resolve_and_play` — patch `random` to return a fixed key, fake `_Dlg.select`
   returns `0` → assert `resolve_and_play` called with `versions[0]['ident']`/`['name']` and correct
   `state_key_for` args.
9. `test_reroll_avoids_repeat_until_exhausted` — series with 3 episodes; script `_Dlg.select` to return
   `1` (reroll) twice; patched `random.choice` recorder asserts the 2nd and 3rd picks are never equal to
   a prior pick within the run (exclusion set works); after all 3 seen, assert the NEXT dialog redraw's
   row 1 label is 30442 ("Start over"), not 30437 ("Reroll") — no `popinfo` call (§6 change: exhaustion
   no longer fires a popinfo).
10. `test_single_episode_no_reroll_offered` — series with exactly 1 episode → dialog `listitems` length
    2 (Play/Cancel only), Reroll/Start-over row absent (§7 table, pool ≤ 1 row).
10a. `test_pool_gt1_exhausted_shows_start_over_row` — series with 2 episodes; reroll once (picks the
    other episode), then reroll again to hit exhaustion → dialog `listitems` length 3, row 1 `label` is
    the localized 30442 string and `label2` is the localized 30441 hint text (not a Reroll label, not a
    popinfo call) — distinguishes this from test 10's pool≤1 case, which omits the row entirely.
10b. `test_start_over_clears_exclusion_except_current` — series with 3 episodes; exhaust the pool (2
    rerolls), then select the Start over row (index 1) → assert `excluded == {last_pick}` immediately
    after the Start over selection (i.e. only the just-shown episode remains excluded, the other two
    re-enter the pool) and that the loop picks again rather than returning/cancelling.
11. `test_cancel_resolves_false` — `_Dlg.select` returns `-1` (or last-index) →
    `setResolvedUrl(_handle, False, ANY)` recorded, no `resolve_and_play` call.
12. `test_empty_version_list_for_picked_episode_skips_and_notifies` — flatten returns a key whose
    versions list is empty at dialog time (simulate stale dict) → `popinfo(30440)` fired, loop
    continues rather than crashing (or: covered by flatten already filtering — test documents that
    `_flatten_episode_keys` is the actual guard, and dialog-time recheck is defensive-only).
13. `test_malformed_season_param_shows_generic_error` — `params['season'] = 'abc'` →
    `popinfo(30107)` + `setResolvedUrl(False)`, mirrors series_ui.py:207-211 test coverage style.
14. `test_zero_extra_api_calls_across_reroll_loop` — **REWRITTEN, not deleted, by the §7/§9
    metadata-enrichment fix**: the old version asserted the now-superseded "zero additional API
    calls per reroll" contract; the shape of the cost guarantee still matters, so the test is kept
    under its existing name but its assertion is updated to the new contract — `get_or_fetch_grouped`
    call-count recorder, 3 reroll iterations → assert called exactly **once** (unchanged), AND
    `enrich_file_metadata` call-count recorder over the same 3 iterations → assert called exactly
    **once per pick** (3 total for 3 distinct picks), per §9's corrected cost note.
15. `test_browse_series_action`-style addition to the EXISTING `tests/unit/test_routing.py`, inside
    `class TestRouter` (test_routing.py:12, bare pytest style, matching that file's convention, not
    the new file's): `@patch('lib.routing.show_random_episode_dialog')` +
    `router('action=random_episode&series=X&what=X')` + `mock_fn.assert_called_once()`.
16. `test_main_resolve_actions_includes_random_episode` — direct assertion (string/set membership,
    reading main.py source or re-importing the literal) that `'random_episode'` is present in
    `_RESOLVE_ACTIONS` — guards against regressing the main.py:50-51 checklist item silently.

Added for the §7/§8 pick-version fix:
17. `test_pick_version_row_present_with_count` — episode with N=27 versions (post-dedup) → dialog
    `actions` contains `'pick_version'` and the corresponding `listitems` row label is the localized
    30443 string formatted with `27`.
18. `test_pick_version_row_omitted_when_n_is_one` — episode with exactly 1 version → `'pick_version'`
    absent from `actions`, `listitems` shorter by one row than the N>1 case for the same `pool_state`.
19. `test_pick_version_plays_chosen_non_best_version` — fake inner picker dialog returns an index
    corresponding to `versions[2]` (not `versions[0]`) → `resolve_and_play` called with
    `versions[2]['ident']`/`['name']`, not `versions[0]`'s — asserts the actually-played ident matches
    the picked row, not the best-ranked one.
20. `test_pick_version_back_out_returns_to_random_dialog` — inner picker dialog returns `-1` →
    outer loop `continue`s and redraws with the SAME `prev_season`/`prev_ep`/`prev_best` (assert the
    next `dialog.select` call's heading/rows reference the unchanged episode); zero
    `setResolvedUrl` calls and zero `resolve_and_play` calls on this path (guards the double-resolve
    trap called out in §7).
21. `test_pick_version_no_enrichment_during_reroll` (was `test_reroll_does_not_trigger_enrichment`) —
    **REWRITTEN, not deleted, by the §7/§9 metadata-enrichment fix**: the old assertion ("never
    called" across plain rerolls) encoded the now-superseded "reroll is zero extra API calls" claim.
    New assertion: `enrich_file_metadata` call-count recorder across several plain reroll iterations
    (no `pick_version` selection) → asserts it is called exactly **once per iteration** (one per
    pick, per §9's corrected contract), not zero, and not more than once for the same pick.
22. `test_action_dispatch_routes_all_pool_states` — parametrized over `pool_state in
    ('reroll', 'start_over', 'none')`: for each, assert selecting the state-slot's row index (when
    present) dispatches to the correct branch (`continue`-and-reroll, `continue`-and-clear-exclusion,
    or the slot is absent entirely for `'none'`) purely via the `actions` list contents, not a
    hardcoded index.
23. `test_actions_list_mutation_detects_swapped_rows` — mutation-style check: construct
    `listitems`/`actions` for a redraw with both `pick_version` and `reroll` present, then swap the
    `reroll` and `cancel` entries in `actions` (leaving `listitems` order untouched) and assert that
    dispatching the reroll row's index now incorrectly resolves as cancel — i.e. this test fails
    (catches the regression) if `actions`/`listitems` ever drift out of parallel sync, proving the
    dispatch-by-name design is actually exercised rather than coincidentally passing.

Added for the §7/§9 metadata-enrichment fix (Play row shows real audio/subtitle tracks):
24. `test_play_row_label2_has_real_track_data_after_enrichment` — build a `file_dict` whose
    `enrich_file_metadata` stub populates `file_info` with known `audio`/`subtitles` values, run the
    pick through `_enrich_displayed_version` then `_build_version_metadata` (lib/ui.py:29) → assert
    the resulting `label2` string contains the actual enriched field values (e.g. the specific
    audio-language code and subtitle flag from the stub), not merely that `enrich_file_metadata` was
    called — a call-count-only assertion would pass even if the enriched values were discarded.
25. `test_enrichment_failure_still_renders_row_and_leaves_loop_usable` — stub `enrich_file_metadata`
    to return `False` (per lib/metadata.py:76-96's documented failure contract) → assert the Play row
    still renders (from `quality_meta` only, no `Audio:`/`Subs:` segment), no exception propagates,
    no `popinfo` call, and the reroll loop's next redraw proceeds normally (guards the §10 "silent
    degradation" row).
26. `test_no_duplicate_enrichment_on_picker_back_out` — pick an episode (1st `enrich_file_metadata`
    call), select `pick_version`, back out (`-1`) so the outer loop redraws the SAME pick → assert
    `enrich_file_metadata` call count is still 1 for that pick's ident (not 2) — guards the
    `'file_info' in file_dict` skip-guard in `_enrich_displayed_version` and its outer-branch-only
    placement (§7/§9/§10).
27. `test_exactly_one_enrichment_call_per_pick_across_multi_reroll` — script several distinct picks
    across a multi-reroll sequence (no repeats, no picker opens) → assert
    `enrich_file_metadata`'s call count equals the number of distinct picks, exactly one per pick,
    confirming §9's corrected "one `getinfo` call per pick" contract end-to-end (complements test 14
    and test 21's narrower recorders).
28. `test_best_version_unchanged_by_enrichment` — explicit guard against a future accidental
    language re-rank (§8's "considered and rejected" decision): construct versions where a
    non-`versions[0]` entry has a "better" language match against a stubbed language-preference
    setting, run a full pick through `_enrich_displayed_version`, and assert `prev_best is versions[0]`
    (identity, not just equality) both before and after enrichment — a mutation that re-ranks or
    re-filters `versions` by audio/subtitle language match must fail this test.

Mutation checks (both required to hold, not just pass by coincidence): removing the
`'file_info' in file_dict` guard from `_enrich_displayed_version` must fail test 26
(`test_no_duplicate_enrichment_on_picker_back_out`); a mutation that re-ranks or filters `versions`
by audio/subtitle language match must fail test 28 (`test_best_version_unchanged_by_enrichment`).

Added for the §8 "Third correction" ranking fix (`_rank_versions`, Defect A), REVISED by the §8
"Fourth correction" revert (Defect B retracted, size-first restored):
29. `test_screenshot_regression_sized_beats_sizeless_regardless_of_quality` (description updated by
    the fourth correction — the original draft of this test asserted the reverted quality-first
    outcome; the shipped, size-first outcome is described here instead): the Gachiakuta screenshot
    case as a regression test: one version with full `quality_meta` and NO `size` key, one
    lower-quality version WITH a `size` → assert the SIZED version ranks first out of
    `_rank_versions` regardless of the other entry's quality score, AND (separately) that the random
    dialog's Play row uses it — i.e. `shown_best` after the pick is the sized version, not the
    sizeless one. This pins the size-first contract, not the retracted quality-first one.
30. `test_play_row_uses_ranked_not_raw_dedupe_order` — guards Defect A directly (Defect A's fix is
    unaffected by the fourth correction, since it concerns calling `_rank_versions` at all, not which
    key it sorts by): stub `deduplicate_versions` to return a list in an order where the genuine best
    is NOT first, run a pick → assert the Play row's version is the genuinely best-ranked one (by the
    shipped size-first key), not `deduplicate_versions`'s raw output order. Must fail if the handler
    ever reverts to reading `versions[0]` straight off `deduplicate_versions`'s return value without
    calling `_rank_versions` first.
31. `test_rank_versions_no_sizes_falls_back_to_quality_score` — every version in the list has no
    `size` key → assert order is quality-score-descending only (ties broken by original relative
    order being irrelevant, since `_safe_size` returns 0 for all of them, making the primary key
    constant and quality_score the deciding tiebreak for this all-sizeless case).
32. `test_rank_versions_all_sizes_present_ties_broken_by_quality_score` (description updated by the
    fourth correction — size is primary, so a tie in `_safe_size` is what triggers the tiebreak here,
    not a quality tie) — several versions share the same `size` and their `quality_score`s differ →
    assert the higher-quality entry ranks first among the size-tied group (quality_score breaks ties;
    size remains the primary key).
33. `test_rank_versions_populates_quality_meta_before_sort` — pass versions where none has
    `quality_meta` pre-populated → assert every entry has `quality_meta` set after
    `_rank_versions` returns, and that the resulting order matches what it would be if scores had
    been pre-populated (guards the "silent default 50" trap — a version read lazily mid-sort would
    wrongly score 50 instead of its real filename-derived score, corrupting the tiebreak).
34. `test_rank_versions_makes_no_api_call` — `enrich_file_metadata` call-count recorder spanning a
    `_rank_versions` call → assert zero calls; ranking is filename-based only, confirming §9's "still
    exactly one `getinfo` per pick" claim isn't silently broken by the ranking fix.

`tests/unit/test_modal_version_sort.py` (renamed from `test_modal_size_sort.py`) encodes the shipped
size-first contract for both the episode and movie version modals
(`test_episode_modal_size_breaks_quality_ties`, `test_movie_modal_size_breaks_quality_ties`,
`test_episode_modal_size_beats_quality`, `test_movie_modal_size_beats_quality`). During the third
correction it was briefly updated to assert a quality-first contract instead; the fourth correction's
revert restored its size-first assertions — `(size, quality_score)` descending, size primary,
quality only the tiebreak — which are the assertions that now pin this contract. Its rename away from
"size_sort" reflects that the module covers the whole ordering contract (primary key AND tiebreak),
not a change in which key is primary.

Mutation checks for the ranking fix (both required to hold, not just pass by coincidence):
flipping `_rank_versions`'s key to `(quality_score, size)` (i.e. re-introducing the reverted
quality-first change) must fail test 29
(`test_screenshot_regression_sized_beats_sizeless_regardless_of_quality`); taking `versions[0]`
before calling `_rank_versions` (i.e. re-introducing Defect A) must fail test 30
(`test_play_row_uses_ranked_not_raw_dedupe_order`).

## 12. Implementation checklist

1. `resources/settings.xml` — insert 2 lines after line 35 (§2).
2. `resources/language/resource.language.en_gb/strings.po` — append 11 msgctxt blocks 30433-30443,
   the last (30443, "Pick version ({0})") added by the §7/§8 version-picker fix (§3).
3. `resources/language/resource.language.cs_cz/strings.po` — same ids, cs strings, incl. 30443
   "Vybrat verzi ({0})" (§3).
4. `resources/language/resource.language.sk_sk/strings.po` — same ids, sk strings, incl. 30443
   "Vybrať verziu ({0})" (§3).
5. `lib/series_ui.py`:
   a. add `import random` near top (module-scope, alongside existing imports lines 8-21) — `xbmcgui`
      itself needs no new import, already present at series_ui.py:8 (§7).
   b. add `_flatten_episode_keys(series_data, season_num=None)` helper.
   c. add `show_random_episode_dialog(params)` — param validation, fetch, flatten, loop, dialog,
      exit paths (§6, §7, §10).
   d. inject row in `browse_series` (§5, after line 86-ish, before line 88 loop).
   e. inject row in `browse_season` (§5, after line 127-ish, before line 137 loop).
   f. extract `_prepare_episode_versions(versions, token)` and `_build_version_listitems(versions)`
      out of `show_version_dialog`'s existing enrich/sort/build body (§8); refactor
      `show_version_dialog` to call both with unchanged observable behavior; reuse both from
      `show_random_episode_dialog`'s `pick_version` action — no parallel picker implementation.
   g. add the `pick_version` row + action-name dispatch (`actions` parallel list) to
      `_build_dialog_rows` / the reroll loop (§7).
   h. add `_enrich_displayed_version(file_dict, token)` helper (**NEW**, §7/§9) — guards on
      `'file_info' in file_dict` (skip if already enriched), calls `enrich_file_metadata` on that
      single `file_dict`, wrapped in try/except + `log_debug` (belt-and-suspenders even though
      `enrich_file_metadata` already swallows and logs its own failures, per §10).
   i. call site: `_enrich_displayed_version(best, token)` in the reroll loop's non-exhausted branch,
      right after `best = versions[0]` is assigned and before `pool_state` is set — never inside the
      inner version-picker redraw loop (§7/§9).
   j. add the `if 'file_info' not in versions[idx]:` guard to `_prepare_episode_versions`'s top-5
      enrich loop (§8/§9/§10), so re-opening the version picker after the Play row was enriched does
      not re-fetch that ident.
   k. add shared helper `_rank_versions(versions)` (§8 "Third correction", key finalized by the
      "Fourth correction") — populates `quality_meta` for every entry (filename-based, no API call),
      then sorts in place by **`(size, quality_score)` descending — size first, quality as tiebreak**.
      This intentionally does NOT match `grouping._version_sort_key` (quality-first), which feeds
      only the grouping/merge passes — the divergence is deliberate (§8 "Fourth correction"). Fixes
      Defect A (random dialog's Play row previously read `versions[0]` off unsorted
      `deduplicate_versions` output). Defect B is RETRACTED — size-first was never a bug; it is the
      long-standing, user-confirmed order for the episode/movie pickers, and an intermediate
      quality-first flip was tried and reverted.
   l. call site: `_prepare_episode_versions` — replace its old lazy-quality-population + (already
      size-first) sort with a single `_rank_versions` call, moved BEFORE the top-5 enrich loop
      (§8/§9). No ordering-behaviour change, just consolidation onto the shared helper.
   m. call site: `select_movie_version` — replace its inline quality-population + (already
      size-first) sort block with the same `_rank_versions` call (§8). No ordering-behaviour change.
   n. call site: `show_random_episode_dialog` — call `_rank_versions(versions)` right after
      `deduplicate_versions` and before `shown_best = versions[0]` is assigned (§7/§8).
6. `lib/routing.py`:
   a. line 11 import — append `show_random_episode_dialog`.
   b. insert `elif params['action'] == 'random_episode':` branch after `select_movie_version`
      (after line 81), before `browse_other` (line 82).
7. `main.py`:
   a. line 50-51 `_RESOLVE_ACTIONS` — add `'random_episode'` to the set literal. **Do not skip.**
8. `tests/unit/test_random_episode.py` — tests 1-9, 10, 10a, 10b, 11-14, 16-34 from §11; test 15 goes
   into existing `tests/unit/test_routing.py` `class TestRouter` instead (§11). Tests 17-23 cover the
   §7/§8 pick-version fix (row presence/omission, non-best-version play, back-out, zero extra
   enrichment on reroll, action-name dispatch, and a mutation check on the `actions` list). Tests
   14 and 21 are REWRITTEN (not new) by the §7/§9 metadata-enrichment fix — see §11. Tests 24-28
   cover the §7/§9 fix itself (real track data in `label2`, enrichment-failure resilience, no
   duplicate enrichment on back-out, exactly-one-per-pick across a multi-reroll sequence, and the
   best-version-unchanged mutation guard). Tests 29-34 cover the §8 "Third correction" ranking fix
   (`_rank_versions`, Defect A) as finalized by the "Fourth correction" revert (Defect B retracted,
   size-first restored) — screenshot regression (sized beats sizeless), Play-row-uses-ranked-order
   guard, no-size/all-sizes/tie fallback ordering, quality_meta populated before sort, and zero
   extra API calls. `tests/unit/test_modal_version_sort.py` (renamed from `test_modal_size_sort.py`)
   is UPDATED (not deleted) to pin the shipped size-first contract (§11) — not a new file, but
   touched by this fix.
9. Run `pytest tests/unit/` — confirm no regressions, offline only. Baseline on current tree: **634
   passed** (was 627 before the §8 "Third correction" ranking fix added tests 29-34 and updated
   `test_modal_version_sort.py` in place; 627 was itself 619 before the §7/§9 metadata-enrichment fix
   added tests 24-28 and rewrote tests 14 and 21; 619 was itself 597 before the earlier §7/§8
   pick-version fix added tests 17-23; note `.claude/CLAUDE.md` still says 330 — that figure is
   stale, worth fixing separately).
10. Manual smoke test per CLAUDE.md dev workflow (symlink addon, exercise both entry points, verify
    Kodi log via `grep Ye-Playa` shows no errors, verify no spinner on Cancel, verify Start over row
    appears only after exhausting a pool >1 and Reroll row is absent for a pool of exactly 1).

## 13. Open questions

None outstanding — all four prior open questions (toggle default, cs/sk translations, dialog heading
mechanics, pool==1 button set) are resolved and folded into §1/§2/§3/§6/§7/§10 above.

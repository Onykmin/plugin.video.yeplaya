# Grouping validation and improvement plan

Branch `feature/quality-grouping` (off main 4b4e65a) + the uncommitted test-quality pass. Every claim
below was re-verified on this tree (anchors are `path:line` of the working tree, 2026-10-23). The
earlier stash on the stale develop base was used as a lead list only; refuted leads are marked.

Tool: `python3 tests/integration/grouping_corpus.py snapshot OUT_DIR [--order forward|reversed|shuffle:N]`
and `... diff OLD.json NEW.json` (48 recorded queries; per group: key, display, season/episode counts,
ranked version idents; diff prints added/removed/moved/meta/order changes and a SUMMARY line).
OUT_DIR must be outside the repo.

## 1. Pipeline (verified)

`fetch_and_group_series` (lib/grouping.py:1406) -> `group_by_series` (:665):
1. `_filter_irrelevant` (:149) drops files with no query-word overlap (falls back to all files if none match, :218).
2. Per file: `parse_movie_info` (lib/parsing.py:769, year via `_select_movie_year` :711) then, if not a movie or an
   S##E## marker is present (:730), `parse_episode_info` (parsing.py:511; key = `clean_series_name` :368).
3. Series key: `clean_series_name`, overridden by `_dual_canonical` (:61) when `extract_dual_names` (parsing.py:218)
   fires; `_dual_canonical` uses `csfd_scraper.create_canonical_from_dual_names` (csfd_scraper.py:298) when importable.
4. `file_dict['series_name'] = canonical_key` (:782) set BEFORE merges; inline dedup (:793-816); display-name candidate list.
5. Per-group `deduplicate_versions` (:832) and display vote `pick_best_display_name_from_list` (:843); candidates deleted (:847).
6. Merge passes, one pass each, no fixpoint, each re-votes the display name with a 2-item list:
   `merge_substring_series` (:850, def :221) -> `merge_word_order_series` (:853, :295, target deterministic: max episodes,
   :328) -> `merge_dual_canonical_series` (:856, :349, target `parts[0]`) -> `merge_similar_series` (:859, :434, ratio>0.85).
7. Single dedup + `_version_sort_key` sort (:861-871; key = (quality_score, size), :117).
8. `group_movies` (:916): key `title|year` (dual: `dual_canonical|year`) -> `merge_substring_movies` (:979, def :1287)
   -> `merge_crossyear_movies` (:982, :1223) -> `merge_dual_key_movies` (:986, :1015) -> `merge_orphan_movies` (:989, :1093)
   -> `_clean_movie_display_name` (:993).
9. Consumers: `keys.normalize_series_key` = last `|` segment (keys.py:25), `normalize_movie_key` (:38);
   `state.state_key_for` (state.py:154), `_migrate_normalize_keys` (:82), favorites `_entry_key`
   (favorites.py:66), `series_ui._resolve_drifted_key` (series_ui.py:30: normalized equality, then exact display name).

## 2. Findings

Order dependence measured (5 orders x 48 queries; `snap0`): 34/48 queries differ in at least one order:
14 queries change movie group keys/membership (barbie, dune, gladiator, joker, star wars, blade runner, penguin, ...),
2 change series keys (naruto `naruto066`; joker/`south park`), 32 change a display name, ~530 equal-(score,size)
version ties re-order (no non-tie rank change). Examples: `joker`: `folie a deux|joker|2024`(52) + `joker folie a deux|krimi,drama,...|2024`(1)
vs one `joker folie a deux|2024`(53); `dune`: `dune part two duna cast druha|2024` vs `duna cast druha dune part two|2024`.

| id | claim | verdict | evidence |
|---|---|---|---|
| F1 | Merge survivors depend on input order (substring series/movies, similar) | CONFIRMED | grouping.py:241-262 (first short key), :450-472 (pairs in key order), :1351-1376 (first key1); 6 strict xfails `merge survivor depends on the order`; corpus: naruto/joker/barbie diffs |
| F2 | `series_name` set before merges -> merged episodes lose watch markers | CONFIRMED (narrower) | grouping.py:782; `utils.tolistitem` -> `state_key_for(file)` (utils.py:264-265) uses the stale value for single-version episodes, play uses the URL group key (series_ui.py:200-203, playback.py:83). Probe: South.Park S01E01/E02 + Mestecko.South.Park S01E03 -> group `south park`, E03 file `series_name='mestecko south park'` |
| F3 | 2-name display vote lets 1-file typos rename big groups | CONFIRMED | candidates deleted grouping.py:847; merges vote 2 items :288/:342/:425/:482 (count tie -> shortest, :559-561). Probe: 8x `Stranger.Things` + 1x `Stranger.Thing` -> display `Stranger Thing` in forward AND reversed; corpus `stranger things` shows `Stranger-Thing` (hyphens also kept by `get_display_name`, parsing.py:451); joker query `Sauth Park` |
| F4 | Year regex strips any 4 digits | CONFIRMED | `_PATTERN_YEAR` parsing.py:39 applied :382. `clean_series_name('Show 123456 x')`='show 56 x', `'The.4400'`='the' |
| F5 | `1920x1080` is read as the movie year (31 keys) | REFUTED on this branch | lookahead `(?!x\d{3,4})` parsing.py:702-703. Corpus has 1 movie key with year 1920: `barbie ( dabing|1920` caused by `1920i` (unclosed bracket) , not WxH. Residual: `clean_series_name('Show 1920x1080')`='show x' (junk `x` in key) |
| F6 | Resolution regex gaps (WxH/FullHD/FHD/UHD/glued) | CONFIRMED | grouping/parsing quality regexes parsing.py:36, grouping.py:43; probe scores: 1280x720, FullHD, FHD, UHD all 50 (1080p=80, 4K=100). 168 of 17209 corpus filenames carry a resolution token yet score 50 (e.g. `Pulp Fiction (1994) UHD.mkv`, `Tucnak_The Penguin_S01E03_..._1080p.mkv`: underscore defeats `\b`) |
| F7 | Contradicting dedup rules | CONFIRMED | inline series dedup drops same name+size even with distinct idents (grouping.py:809-816); `deduplicate_versions` keeps distinct idents on purpose (:636-645, user policy 3). Probe: two series files same name+size ids a,b -> 1 version; two movie files -> 2 versions |
| F8 | Duplicate key algorithm in `_dual_canonical` | CONFIRMED (worse than stated) | the csfd branch (:74-79) cleans with `_clean_for_canonical` (csfd_scraper.py:267) which keeps brackets, years, commas, roman numerals; fallback uses `clean_series_name`. Probe: `('Penguin, The','Tucnak')` -> `penguin, the|tucnak` vs `penguin|tucnak`; `('Lost (2004)','Ztraceni')` -> `lost (2004)|ztraceni` vs `lost|ztraceni`; `('Blade Runner II','Blade Runner 2')` -> key vs None. Production uses csfd (importable), tests mostly the fallback |
| F9 | Franchise stub swallows siblings (star wars blob) | CONFIRMED | spinoff guard only blocks when ALL extra words <= 5 chars (grouping.py:281) so `rebels`, `droids`, `resistance`... pass; then `merge_dual_canonical_series` bridges (:383-403). Corpus `star wars`: group `povstalci|star wars` = 13 pre-merge keys (Rebels 265 files, Forces of Destiny 32, Droids 14, Freemaker 12, Resistance 4, Clone Wars 2 ...). `barbie`: group `barbie` named `Barbie Mysteries` = 12 pre-merge keys (Policajtka Barbie 39, Dreamhouse Adventures 17, A Touch of Magic 13 ...) |
| F10 | Same show under two names stays split | CONFIRMED | corpus: `game of thrones` (75 + 72 eps), `suits` (69 + 18), `demon slayer` / `kimetsu no yaiba`; no content-identity merge exists; 5 xfails |
| F11 | Season marker leaks into key | CONFIRMED | `_PATTERN_S00E00` parsing.py:25 needs `S01E01` contiguous. `Dragon Ball Z - S01 E001 - A (1080p).mkv` -> `dragon ball z s01`: corpus `dragon ball` 11 series groups (`dragon ball z s01..s09`); `spy x family s3`, `spy x family 2`; `Naruto066-067` -> `naruto066` (glued number) |
| F12 | Absolute-ep dash binding makes season-per-group | NEW (regression of 26f9dfb) | `Peaky Blinders  01 - 01.mkv` -> key `peaky blinders 01` (parsing.py:34 `_PATTERN_ABSOLUTE_EP_DASH`) |
| F13 | Release/site/lang junk in keys and dual names | CONFIRMED | `7HitMovies.cool - ...` prefix, `OFFICE [CZ]` -> `cz|office` (parsing.py:234 bracket branch), `Peaky-Blinders--Gangy-z-...` split at first dash into `blinders gangy z birminghamu|peaky` (parsing.py:290 dash-no-space branch), `peaky blinders tit` (`CZ tit` leaks), `Show - OVA` taken as dual |
| F14 | Movie display keeps release tags / glued counters | CONFIRMED | `_clean_movie_display_name` grouping.py:1161 (tags, unclosed bracket); `1Dune` fails `_filter_irrelevant` (:196-199) and fallback returns everything (:218) |
| F15 | Stale tests' premise `Dual identity` | NEEDS-DECISION | `keys.normalize_series_key` = last segment: `penguin|tucnak` -> `tucnak`, plain `penguin` stays `penguin`; target `parts[0]` (grouping.py:388-392) means identity depends on which alias files were fetched |

## 3. The 72 strict xfails (tests/unit/test_grouping_*.py, test_parsing_behaviour.py)

| category (marker) | n | verdict | evidence / note |
|---|---|---|---|
| resolution tokens + unmarked ranking (BUG_RES) | 14 | real bug, no key change | F6 |
| order-dependent survivors (BUG_ORDER x movies 3, series 3) | 6 | real bug, key change (policy 1) | F1 |
| franchise stub / recorded star-wars, barbie (BUG_STUB) | 5 | real bug, key change | F9 |
| same episodes same size, two names (BUG_SAME_CONTENT) | 5 | real bug (needs new rule), key change | F10; GoT/Suits/Demon Slayer named by user |
| bare season / `S3 - 01` / `Name 2 - 05` (BUG_BARE_SEASON 5, BUG_S_NO_SPACE 1, BUG_ODD_MARKER 3, BUG_XE 1) | 10 | real bug, key change with derivable migration | F11 |
| `S01 E001`, `S03.E13` (BUG_MARKER_GAP 2 + BUG_SEASON_MARKER 2) | 4 | real bug, key change with derivable migration | F11 |
| display: episode number (BUG_DISPLAY_EPISODE 3), typo rename (1), movie vote (1), movie tags/unclosed bracket (3) | 8 | real bug, no key change | F3, F14 |
| key hygiene: site prefix (BUG_SITE 3), `[CZ]` key (1), digit-run/4400 (BUG_NUM_TITLE 3), dotted dual (BUG_DOT_DUAL 1 + BUG_DUAL_SEP 2), dual labels (BUG_DUAL_LABEL 4), `1920i` (1) | 14 | real bug, junk keys only (policy 2, no migration) | F4, F13; `1920i`: nothing documents it as a year; `Movie 1920i.mkv` -> year 1920 (probe); a bare 4-digit year stays valid, only `19xx`+`i`/`p` suffix is rejected |
| audio/bit-depth taken as episode (BUG_SEQUEL_SPEC) | 2 | real bug, no key change | `Shrek 2 - 5.1 DTS`, `Dune 2 - 10bit` become episodes (parsing.py:607-692) |
| alias in parentheses + absolute number (BUG_ALIAS_PAREN) | 1 | real bug, key change (existing group stays) | `Alias (Original) - 10` |
| glued upload counter in relevance filter | 1 | real bug, no key change | F14 |
| dual identity depends on fetched alias (NEEDS-DECISION) | 1 | user decision (see NEED 1) | F15 |
| Total | 72 | 71 real bugs, 1 needs decision, 0 intended-behaviour | |

Not an xfail but decision-gated: title numbers `19xx/20xx` ("Blade Runner 2049", "Space 1999") stay stripped
(test_parsing_behaviour.py:201 comment: re-keying is migration-gated) - see NEED 2.

## 4. tests/integration/baseline_results.json (working tree vs HEAD, which dates from 2026-03-28 / commit 6d439db)

Fixtures are unchanged since, so every difference is a code change. Reproduced by running the 6d439db `lib/` (git archive,
scratch) and current `lib/` over the same XML. 33/48 queries differ in group counts (40/48 incl. version/display detail).
- peaky blinders 1 -> 8 series: REGRESSION of 26f9dfb (dash-bound absolute episodes) exposed on a long-standing wrong case.
  Old: `Peaky Blinders  01 - 01.mkv` .. `06 - 06` parsed as S1 episode NN (season number taken as episode; 36 files piled
  as extra versions: 425 = 389 + 36). New: six groups `peaky blinders 01..06` (6 eps each, display `Peaky Blinders 01 - 01`) plus
  junk dual `blinders gangy z birminghamu|peaky` (1 file, dash-split of `Peaky-Blinders--Gangy-...`). Neither is right; fix in S-b/S-d.
- penguin display `The Penguin` -> `Tucnak`: REGRESSION (display vote). Key `penguin`, 123 files unchanged. Cause F3
  (2-item vote, count tie -> shortest `tucnak` over `the penguin`, grouping.py:559-563). Fix in S2.
- joker non_series 72 -> 39: INTENDED/improvement. The 33 files now grouped are year-bearing movies
  (e.g. `Joker 2019 CZ dab 1080p.mkv`, `Joker - Folie a Deux 2024 CZ dab 1080p.mkv`) now in `joker|2019` (48 versions, was 38+1 split
  across `joker joker|2019` / `joker [joker]|2019`) and `folie a deux|joker|2024` (52). Old artefact.
- Other non_series increases (star wars 10->18, attack on titan 11->18, pokemon, naruto): INTENDED trade-off of the sequel-number
  guard (parsing.py:678-684): `Star Wars 7 Official Trailer`, `Epizoda 3.2` now loose (correct), but
  `Shingeki no Kyojin (Attack on Titan) - OVA 1 - ENG SUBS.mkv` x8 also lost (arguable regression; S-b to revisit with OVA rule).
- series_groups decreases (lost 6->5, dark, house of the dragon, the boys, severance, naruto): merges from the 22d9be3/57d13c1 audit
  passes; not individually audited (open).

## 5. Slices (mandated structural order S-a -> S-b -> S-c; prerequisites first)

Each slice: run `pytest tests/ -q`, `ruff check --select F,E4,E7,E9,B .`, then corpus snapshot forward + reversed + shuffle:1..3 and diff
against the previous slice's snapshots. Every slice must END with a corpus diff reviewed group-by-group (no unexplained key change)
and with order-dependence not increased. Baseline snapshots: `snap0` (this phase). Flip xfails only by removing their marker
(never edit expectations).

S0 (done) Corpus tool `tests/integration/grouping_corpus.py`.

S1 Resolution + version ranking (prerequisite: all later corpus diffs rank versions)
- Goal: WxH/FullHD/FHD/UHD/glued tokens/underscore recognised in `parse_quality_metadata`; version tie-break by ident (deterministic order).
- Root cause: F6 regexes with `\b`; stable sort over input order ties. Files: lib/parsing.py (quality), lib/grouping.py (`_version_sort_key`).
- Risk: 168 corpus files change score -> version order changes in many groups (expected, review via `order` lines); score scale 0-125 must stay monotonic.
- Key change: no. Migration: none. Check: BUG_RES 14 xfails flip; corpus diff shows only `order changed` lines, and order ties=0 across orders.

S2 Display-name pipeline
- Goal: display name voted over ALL candidate titles of a merged group (kept through merges), no episode number, no release tags, hyphen/underscore cleaned.
- Root cause: F3 (candidates dropped at :847, 2-item re-vote, shortest-wins); `get_display_name` does not de-hyphenate.
- Files: lib/grouping.py (`pick_best_display_name*`, `_clean_movie_display_name`, merge call sites), lib/parsing.py (`get_display_name`).
- Risk: display_name is also a favorite fallback key in `_resolve_drifted_key` (series_ui.py:48-55) -> stored `fav_display_name` may stop matching; mitigation: S-c alias path, and keep old display reachable via `aliases`. Search relevance uses display_name (search.py:23).
- Key change: no (display only). Check: 8 display xfails flip; corpus diff = only `display_name` meta lines (penguin `The Penguin`, `Stranger Things`, `Sauth Park` fixed).

S3 Pipeline invariants (no key change)
- Goal: rebind `file['series_name']` to the final group key after merges (F2); one dedup rule (distinct idents kept as mirrors, policy 3) used by inline and final dedup (F7).
- Files: lib/grouping.py only. Risk: more versions per episode shown (mirrors) - UI lists them in the version picker; resume state key derives from group key so unaffected.
- Check: new unit tests (red first): stale series_name probe, mirror pair kept in series; corpus diff: version counts up only where same name+size distinct ident.

S4 Key hygiene (policy 2: junk/colliding keys, no migration)
- Goal: drop site prefix, bracketed lang tags, `\b`-bounded year strip (`The.4400`->`4400`, `Show 123456 x` intact), resolution `x` leak, `CZ tit`/release tags;
  `extract_dual_names`: dot/underscore separators, no dash-split of scene names (`Peaky-Blinders--Gangy-z-...`), reject OVA/The Movie/[CZ]/[SK] labels;
  `1920i` not a year; `_dual_canonical` always via `clean_series_name` (single algorithm, F8) so csfd and fallback keys agree; glued upload counter in `_filter_irrelevant`.
- Files: lib/parsing.py, lib/grouping.py (`_dual_canonical`), csfd_scraper.py (stop owning key cleaning). Risk: `_dual_canonical` unification re-keys every dual group that has punctuation/brackets/years in an alias; normalised identity (last segment) can change when the sort order flips -> confirm in corpus diff, and derive-migrate per policy 1 if any `ep:`/`mv:` last segment changes (derivable by re-cleaning the old key). `19xx/20xx` stripping untouched (NEED 2).
- Check: 14 hygiene xfails + 2 search/parsing xfails flip; corpus diff lists every changed key, expected: junk keys only.

S5 (S-a) Merge-guard redesign - order-independent, collision-aware
- Goal: kill the Star Wars Rebels/Resistance/Barbie blob; merge GoT / Suits / Demon Slayer split halves; deterministic survivors.
- Root cause: F1, F9, F10: merges decided from key text only, with an ad-hoc `len(w) <= 5` guard and first-seen targets; no content signal.
- Design (proposal): compute per candidate pair (key-text relation: substring / word-order / dual / similar) a content test on (season, episode) coordinates and file sizes:
  CONFLICT if both groups contain a coordinate and no size in common; MERGE only if no conflict AND (>=3 coordinates with a shared size, OR one side <= 2 episodes with zero overlap).
  Same-size-two-names pairs with no key relation merge via content alone (>= 3 shared (coordinate,size)). Union-find over approved pairs; survivor = max (episodes, files, key) for series, (versions, key) for movies; one rule for all passes, applied to a fixpoint.
  Movies: replace first-key-wins in `merge_substring_movies` with the same survivor rule; movie keys stay `title|year`.
- Files: lib/grouping.py (all merge_* functions), lib/keys.py (alias API). Emit `group['aliases']` = every pre-merge key (including the dual-name parts) for read-side migration.
- Risk: highest. Typo variants that collide on coordinates with different sizes will now stay separate (accepted, conservative); false merge of different shows with identical sizes needs >=3 coincidences (negligible); runtime O(pairs) - restrict to key-related pairs + size-index for content-only pairs. Key change: YES (survivor of order-dependent clusters, merged halves). 
- Migration (policy 1): state rows `ep:{old}|SxxEyy` / `mv:{old}|year` and favorites under any old key must resolve: read-side fallback candidates = {group key} U `aliases` (+ `normalize_*` of each), lazy rewrite to the new key on hit (INSERT OR REPLACE keeping newest `updated_at`, as in state.py:96-112). Cover: every pre-merge key of the cluster in either order (corpus gives them via `file['series_name']` snapshots).
  Non-derivable gaps: rows whose old key was never co-fetched with the new survivor (user did not search the query again); a row that was written under a survivor that no longer shares any alias with the new group; favorites whose stored display name changed AND whose key left the cluster.
- Check: 6 order + 5 stub + 5 same-content xfails flip; corpus: forward == reversed == shuffle:N at group level (key sets, memberships; display equal); star wars `povstalci|star wars` splits into >= 8 groups; barbie `Barbie Mysteries` blob splits; GoT 1 group; new tests: alias read-fallback round trip.

S6 (S-b) Season-marker split keys + migration
- Goal: `S01 E001`, `S03.E13`, `S04xE13E14`, `S3 - 01`, `Name 2 - 05`, `Alias (Original) - 10`, `Naruto066-067` parse to (series, season, episode); no more `dragon ball z s01..s09`; decide `Peaky Blinders  01 - 01` (NEED 3); audio/bit-depth tokens rejected as episodes.
- Root cause: F11/F12: single contiguous S##E## regex (parsing.py:25-28) and absolute fallback (:29-34) binding the season number into the name.
- Files: lib/parsing.py (+ `extract_season_from_text`), lib/grouping.py unaffected except key.
- Risk: sequel numbers (`Shrek 2 - 5.1`, `Dune 2 - 10bit`) vs season numbers; the 1-digit sequel guard (parsing.py:683) must stay; movies must not become series.
- Key change: yes. Migration: derivable and unambiguous for `^(.+) s\d{1,2}$` keys (season is in the old key AND in `SxxEyy` of the row): rewrite `ep:dragon ball z s01|S01E001` -> `ep:dragon ball z|S01E001` (state.py `_renormalize_state_key` extended; PRAGMA user_version 3). Numeric-suffix keys (`spy x family 2`, `peaky blinders 02`) only when the suffix equals the row's season digit AND the stripped base exists in the same DB or corpus pass; otherwise left (gap: title numbers). Favorites: stored key mapped through the same rule + S5 `aliases`.
- Check: 10 + 4 xfails flip; corpus: `dragon ball` 11 -> <= 4 series, peaky 8 -> 1-2.

S7 (S-c) Dual-name alias identity (read-side tolerance)
- Goal: favorites/state resolve ANY alias of a dual group, independent of which alias files a fetch returned.
- Root cause: F15 - identity = last `|` segment (keys.py:25) while the group key target depends on fetched files (grouping.py:388-392).
- Design: `keys.identity_candidates(key)` = {every `|` part, last segment, group `aliases`}; `state.get_state`/`get_states`/favorites `_entry_key`/`_resolve_drifted_key` look up all candidates, newest `updated_at` wins, write path keeps ONE canonical write key (the group's normalized key) and lazily migrates hits. No stored-key rewrite pass (non-derivable offline).
- Files: lib/keys.py, lib/state.py, lib/favorites.py, lib/series_ui.py. Risk: ambiguous aliases (`penguin` also a different show) -> candidates are tried only when the candidate is a part of the currently resolved group, never globally. Key change: no (write side), migration: lazy read-side. Gap: rows stored under an alias never observed together with another alias.
- Check: new alias round-trip tests replace nothing; the NEEDS-DECISION xfail is superseded only after NEED 1.

S8 (done) `Name NN - MM` season-vs-absolute (user decision 1; closes NEED 3)
- Goal: `Peaky Blinders  01 - 01`, `Spy x Family 2 - 05`, `Mashle 05 - 12` are season NN episode MM ONLY when NN <= the highest season the same show shows in files that do not carry this ambiguity; otherwise the absolute reading stays (number in the name, as before).
- Root cause: F12 - the per-file parser (`parse_episode_info`) has no view of the show's other files, so the dash-bound absolute fallback (parsing.py `_PATTERN_ABSOLUTE_EP_DASH`) always bound NN into the name; whether NN is a season is a property of the group, not of the file.
- Design: the parser keeps the absolute reading and attaches `season_reading` ({series_name, season}) for a dash-bound `... NN - MM` (1-2 digit NN >= 1, no season text); `parsing.apply_season_readings` runs once over ALL parsed files of a `group_by_series` call (parse pass first, group pass second) and switches a file only if `NN <= max season` of the files WITHOUT `season_reading` for the same cleaned name. No circularity (evidence excludes ambiguous files, so it cannot move with the choice) and no order dependence (evidence is a max over the full set before any file is decided).
- Files: lib/parsing.py (`_season_reading`, `apply_season_readings`), lib/grouping.py (parse pass before the grouping loop), lib/keys.py (`legacy_row_seasons`: a bare numeric key suffix naming the file's season also tries season 1).
- Risk: evidence is matched on the cleaned name text before merges, so a show whose season evidence sits under another alias/dual key only sees it after a re-search with that alias (stays absolute, never wrong-way); a title ending in a number with a dashed episode ("Znovu 17 - 17 Again") reads as season only if the base title has >= that many seasons; `Mashle 05 - 12` stays `mashle 05` (merged into `mashle` by the S5 guards only when it does not collide on >= 3 coordinates).
- Key change: yes (`peaky blinders 0N` -> `peaky blinders`, `spy x family 2` -> `spy x family`). Migration: read-side only. Per file the old key goes to `legacy_series_name` -> group `aliases`; state rows `ep:{old}|S01Exx` resolve via `resolve_state_key` + `legacy_row_seasons` (old parser always wrote season 1), favorites via `find_favorite_by_aliases` / `_resolve_drifted_key` (alias identity). Nothing is rewritten.
- Check: new behaviour tests (tests/unit/test_grouping_season_reading.py, TestResolveStateKeyLegacyBareSeason, test_series_ui_state.py `_peaky_group` tests); corpus forward/reversed/shuffle:1..3 diffed against the S7 snapshot and against the new forward (results below).
- Results: corpus diff S7 -> S8, 2 of 48 queries change (peaky blinders, spy x family), identical in all 5 orders (7 groups removed, 39 files moved, 0 added, order=0, rescored=0); order diffs vs new forward = 0 for reversed, shuffle:1, shuffle:2, shuffle:3. All 7 removed groups intended (`peaky blinders 01..06` 36 files now versions of S01..S06 in `peaky blinders`; `spy x family 2` 3 files now S02E05..E07 of `spy x family`); 0 regressions. baseline_results.json re-recorded with refresh_baseline.py.
- xfails: the 3 strict xfails are NOT flipped, they conflict with the decision as written: they use files with no season evidence (parse level, or a group of only `Spy x Family 2 - NN` files), where decision 1 says absolute (`spy x family 2`, S01). They stay xfail until you decide (see NEED 4).
- Migration gaps (non-derivable): (1) rows under `ep:{old}|S01Exx` whose old name was never co-fetched with the base show (no alias on the group); (2) CLOSED by repair: an alias that is the group's own identity plus a season token (`peaky blinders 02`, also `suits s03`) now serves episode rows only for files of that season (`keys.legacy_row_seasons(alias, season, base)`, `state.resolve_state_key` passes the file's series_name); a genuine S01E05 file never reads `ep:peaky blinders 02|S01E05`. Numeric-title aliases whose stripped base differs from the group identity (`apollo 13` on `apollo extended`) keep resolving as before; an alias equal to identity + number (`apollo 13` on `apollo`) is read as season 13 only for a file of season 13, i.e. only when that season exists in the group (the rule is gated by the file's own season), so an `apollo` group without S13 never reads `ep:apollo 13|S01E05` (pinned S11: tests/unit/test_state.py `test_show_plus_number_alias_is_read_as_a_season_only_for_that_season_file`); (3) a favorite stored under `peaky blinders 02` now resolves to the whole show (the season split no longer exists).

S9 (done) Release-site prefixes `7HitMovies.<word-tld> - ` (user decision 3)
- Goal: `7HitMovies.dad|forum|buzz|diy|best|moe|zone - <title>` group under their real title; the junk groups `7hitmovies best`, `7hitmovies buzz`, ... disappear.
- Root cause: `_RE_SITE_PREFIX` (parsing.py) is a whitelist of TLDs, the new ones are unlisted, so the site stays in the name and becomes the series/movie key. Why not just list them: they are English words, `The.Twilight.Zone - 1x01`, `Danger.Zone - 05`, `Simply.The.Best - 05`, `Mom.And.Dad - S01E02` would lose their title. A word TLD therefore needs stronger site evidence than the TLD.
- Design: the seven word TLDs form a second pattern (`_RE_SITE_PREFIX_WORD`) matched case-sensitively: lowercase TLD, ONE host label (no dot before it), and that label must look like a site name (a digit or an upper-case letter after its first character: `7HitMovies`, `SkyMoviesHD`, `bolly4u`). `The.Dead.Zone`/`Danger.Zone` fail on the capital TLD; lowercase `the.dead.zone` fails on the extra dot; lowercase `danger.zone` fails on the host shape. Old TLDs keep their current pattern untouched (no change for `.cool`, `.to`, ...).
- Files: lib/parsing.py (pattern, `strip_site_prefix(legacy=)`, `parse_episode_info/parse_movie_info(legacy_site=)`, `legacy_site_prefix_key`), lib/grouping.py (per-file series key derivation extracted into `_file_series_keys`, legacy twin aliases for series and movies).
- Risk: (1) word-TLD collisions (checked by negative tests + corpus); (2) a lowercase one-label host with digit/capital and a word TLD whose title is dotted ("Area51.zone - ...") is read as a site: accepted, it is what the site pattern means; (3) hosts outside the seven TLDs seen in the corpus (`7HitMovies.watch`, `.green`, `.com.de`) are NOT covered (decision names seven): listed as open item.
- Key change: yes, movies `7hitmovies diy dune part two|2024` -> `dune part two|2024`, `7hitmovies moe|squid game|2024` -> `squid game|2024`; series junk `7hitmovies dad` -> real show.
- Migration (read-side only, nothing rewritten): per file the key the OLD parser produced (parse with the legacy prefix pattern) goes into the group `aliases` (series via `_file_series_keys`, movies in `group_movies`); state rows `mv:`/`ep:` via `resolve_state_key`, favorites via `find_favorite_by_aliases` / `_resolve_drifted_key`. Non-derivable gap: a key that is only the site (`7hitmovies best`, the junk SERIES) names every title the site posted, so it is never aliased (a favorite or `ep:7hitmovies best|S02E08` row stays orphaned rather than resolving to an arbitrary show).
- Check: behaviour tests (tests/unit/test_site_prefix_tlds.py: junk-prefix grouping per TLD, word-TLD negatives, migration old row/favorite resolved, idempotent/never writes, current row wins, site-only key not aliased); corpus forward/reversed/shuffle:1..3 diffed against the pre-change forward snapshot and against the new forward.
- Results: corpus diff before -> after, 3 of 48 queries change (dune, house of the dragon, squid game), identical in all 5 orders (8 groups removed, 2 added, 34 files moved, 2 alias lists extended, order=0, rescored=0); order diffs vs new forward = 0 for reversed, shuffle:1, shuffle:2, shuffle:3. Intended: series `7hitmovies best|buzz|dad|forum|zone` (5 junk series, 25 files) now in `house of dragon` / `duna proroctvi|dune prophecy`; movies `7hitmovies diy dune part two|2024` -> `dune part two|2024`, `7hitmovies moe|squid game|2021|2024` -> `squid game|2021|2024`; 0 neutral, 0 regressions. Word-TLD collision probe: of 16931 corpus filenames only the 34 `7HitMovies.<tld> - ` ones change; no corpus or test title ending in a new TLD word loses its name.
- Migration coverage: movies (old `mv:7hitmovies diy dune part two|2024` row and favorite resolve via `aliases`), dual series keys (already normalize to the current key), season-text keys (`7hitmovies dad house of dragon s02` alias). Gaps (non-derivable): (1) the junk SERIES keys `7hitmovies best|buzz|dad|forum|zone` / `ep:7hitmovies dad|S02E01` rows and favorites: the key names every title of the site, so aliasing it would resolve to an arbitrary show; they stay orphaned (tested); (2) rows under keys the old parser built for a fetch that never contained the file again; (3) `7HitMovies.moe - Squid Game 2024 S02 ...` is still a MOVIE `squid game|2024` (S02 with no episode marker, unchanged by S9).
- Not covered (decision names seven TLDs): corpus also holds `7HitMovies.watch - ` (interstellar), `7HitMovies.green - ` (fight club, key `7hitmovies green|fight club|2023`), `7HitMovies.com.de - ` (dune) - same junk class; follow-up decided and done in S10.

S10 (done) Release-site prefixes `7HitMovies.watch|green|com.de - ` (user decision, S9 follow-up)
- Goal: `7HitMovies.watch - Interstellar`, `7HitMovies.green - Fight Club`, `7HitMovies.com.de - Dune` group under their real title; the junk key `7hitmovies green|fight club|2023` disappears.
- Root cause: same as S9 (site TLD unlisted, so the site stays in the name). `watch` and `green` are English words ("The.Watch - S01E01", "Green.Lantern - 2011", "Green Book"), so they join the word-TLD pattern (`_RE_SITE_PREFIX_WORD_TLD`) with its guards unchanged: lowercase TLD, ONE host label, host shaped like a site name. `com.de` is a two-label SUFFIX, not a two-label host: the guard's one-label assumption is about the part IN FRONT of the suffix (`[\w-]` cannot cross a dot), so `com\.de` is just a longer alternative and `Mein.Haus.com.de`, `Show.Com.De`, `show.com.de`, `Dot.Show.7HitMovies.com.de` keep their names. Plain `.de` is NOT added (not in the corpus, no site evidence).
- Files: lib/parsing.py (alternation only), lib/grouping.py (`_site_legacy_movie_keys`, `_legacy_dual_alias`: a site-prefixed movie also gets the pre-shared-cleaning dual key of the LEGACY parse as alias, because for `com.de` the new parse has no dual names any more, so `7hitmovies com de|dune|2021` (the older key, language tag kept) would have been lost), tests/unit/test_site_prefix_tlds.py.
- Risk: (1) a one-label lowercase host with a digit/capital and TLD `watch`/`green` and a spaced dash ("BigBoy.Green - 05") is read as a site (same accepted class as S9); (2) the old parser read `com.de` as host `7HitMovies.com` + language tag `de`, so the legacy key is `7hitmovies com|...` (and `7hitmovies com de|...` via the older dual key); both are aliases.
- Key change: yes, movie `7hitmovies green|fight club|2023` -> `fight club|2023`. `7hitmovies watch|interstellar|2014` / `7hitmovies com|dune|2021` were already merged into `interstellar|2014` / `dune|2021` (no group change). Migration: read-side only, as S9 (old per-file keys -> group `aliases` via `_site_legacy_movie_keys`, series via `_site_legacy_series_keys`; rows via `resolve_state_key`, favorites via `find_favorite_by_aliases` / `_resolve_drifted_key`; nothing rewritten). A site-only series key (`7hitmovies green`) is never an alias (tested for all three).
- Check: tests/unit/test_site_prefix_tlds.py (prefix dropped series/movie per TLD, dotted-title guards incl. `.de` analogues, movie row/favorite migration, dual alias, site-only key never an alias); corpus forward/reversed/shuffle:1..3 diffed pre vs post and against each other.
- Results: corpus diff before -> after, 1 of 48 queries changes (fight club), identical in all 5 orders (1 group removed, 1 added, 3 files moved, 0 meta, order=0, rescored=0); order diffs vs new forward = 0 for reversed, shuffle:1..3. Intended: `7hitmovies green|fight club|2023` (3 files) -> `fight club|2023`; 0 neutral, 0 regressions. Of 17209 corpus filenames only 43 differ in prefix handling vs legacy: the 34 of S9 plus 9 new (3 each watch/green/com.de); no title lost its name. baseline_results.json re-recorded with refresh_baseline.py.
- Migration gaps (non-derivable): same as S9 - site-only series keys (`7hitmovies green`, `7hitmovies watch`, `7hitmovies com`) stay orphaned; rows from a fetch that never contained the file again.

S11 (done) Legacy show+number season rule only when that season exists in the group (user decision, migration false positive)
- Change: none in lib/. `keys.legacy_row_seasons` is gated by the file's own season (lib/keys.py:98-100): an alias equal to base + number (`apollo 13` on `apollo`) or base + season token (`suits s03`) is read as that season for a file of that season only, so the rule already applies only when the season exists in the group; every other file gets `[]` (the row is not read). No other consumer: favorites / `_resolve_drifted_key` use plain alias identity, not this rule. Premise "apollo 13 resolves without S13" did not reproduce (probe: S01/S02 file -> `[]`, S13 file -> `[13, 1]`).
- Risk: none for code (tests only). Literal tightening was rejected: treating an out-of-group number as a plain alias would make `ep:apollo 13|S01E05` resolve for an S01 file, the opposite of the decision.
- Check: tests/unit/test_state.py `test_show_plus_number_alias_is_read_as_a_season_only_for_that_season_file` (apollo 13: S01/S02 file no, S13 file yes); already pinned: `peaky blinders 02` on S02 (TestResolveStateKeyLegacyBareSeason test_old_row_resolves), `suits s03` (TestResolveStateKeyLegacySeasonMarker), `apollo 13` on `apollo extended` (test_numeric_title_alias_of_another_name_keeps_resolving); corpus forward snapshot pre vs post.
- Results: corpus forward pre vs post diff = 0 (no grouping code touched; other orders and baseline refresh skipped). No pinned expectation changed.
- Migration gaps (user's trade-off): a row `ep:apollo 13|S01E05` under a group `apollo` without S13 does not resolve (a genuinely separate title merged as alias); favorites follow plain alias identity unchanged.

Placement rationale: S1-S4 are independent of merge decisions, change no real stored keys (S4: junk only) and remove noise
from the S5 corpus diff; S3 must precede S5 because S5 multiplies merges (F2 becomes more visible). S-b follows S-a so
a season-marker group is merged by the new rules, S-c last because it consumes `aliases` produced by S5/S6.

## 6. Open items

NEED 1: DECIDED (user): the WRITE-side xfail `test_dual_group_identity_does_not_depend_on_which_alias_files_are_fetched` is replaced by read-side contract tests (tests/unit/test_series_ui_state.py `test_state_row_of_either_fetch_identity_resolves_in_either_fetch`, `test_favorite_of_either_fetch_identity_resolves_in_either_fetch`; existing S7 tests `test_state_row_under_either_name_of_a_dual_key_resolves` etc. stay). Known write-side limit, accepted: the state/favorite identity of a dual group (`penguin` vs `tucnak`) depends on which alias files a fetch returns; the read side resolves rows and favorites stored under either identity. No re-keying, no migration.
NEED 2: DECIDED (decision 2): title numbers 19xx/20xx (`Blade Runner 2049`, `Space 1999`, `Death Race 2000`) KEEP AS NOW: series keys strip them (`blade runner`), movies take a bare trailing year. No code change, no corpus run, no migration.
NEED 3: DECIDED (decision 1, S8): `Name NN - MM` = season NN episode MM only when NN <= the show's highest season seen in unambiguous files of the same call, else absolute.
NEED 4: DECIDED (user): KEEP the 3 strict xfails (test_parsing_behaviour.py `BUG_BARE_SEASON` x2, test_grouping_series.py `BUG_ODD_MARKER` x1) as documented known defects. `Name 2 - 05` with no season evidence stays absolute (S8: NN counts as a season only when NN <= the show's highest season in unambiguous files); rows and expectations unchanged.
NEED 5: DECIDED (decision 3, S9): extend the site-prefix TLD list (dad, forum, buzz, diy, best, moe, zone) with migration. Follow-up `7HitMovies.watch|green|com.de`: DONE (S10).
Legacy show+number season rule: DECIDED (user): apply only when that season exists in the group; verified already so (gated by the file's season), pinned in S11 (done).

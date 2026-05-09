# Session Summary — 2026-04-26 (LSG vs KKR ship + monitor day)

**Match**: IPL 2026 — Lucknow Super Giants vs Kolkata Knight Riders (Cricbuzz match
ID 151924). Pipeline restarted on this match to validate Fix 12 and the new
Fix 9–18 cohort.

**Outcome**: 7 fixes (12 / 13 / 14 / 15 / 16 / 17 / 18) shipped + 4 hotfixes
during deployment + 5 new backlog items filed from production observation +
extensive live-validation harness work. Full test suite at end of day:
**443 PASS / 0 FAIL**.

---

## 1. Fixes shipped today

| # | Name | Telemetry | Tests | Live validation |
|---|------|-----------|-------|-----------------|
| **9a** | AUTO-SWAP innings-1-total injection | `[AUTO-SWAP-TARGET] source=innings_1_total` | passing | ✅ **FIRED** at F686 (target=157 set on innings transition) |
| **9b** | AUTO-SWAP target-from-Scout fallback | `[AUTO-SWAP-TARGET] source=scout_visible_target` | passing | ✅ Correctly silent (9a did the job) |
| **10** | Post-witnessed-FOW slot rotation | `[POST-WICKET-ROTATION]` | passing | ⚠️ **PARTIAL** — 4 fires / 8 wickets, collision rate 14.8/wkt vs 72.4 baseline (~5x improvement, but above strict <10 target) |
| **11** | EXTRAS-INF admission gate (Layer 1) | `[EXTRAS-INF-GATE]` | 305/0 | ✅ **VERY ACTIVE** — 25 fires (heavy phantom-admission defence in death overs) |
| **12** | Runs-monotonic rejection-consensus release (Layer 4) | `[RUNS-REJECT-STREAK]`, `[RUNS-REJECT-RELEASE]` | passing | ✅ **VALIDATED** — 49 STREAK + **3 RELEASES** (Badoni F2453 runs=0/cur=7; Himmat F2864 runs=6/cur=16) |
| **13** | Fix-10 Path D extension (placeholder→witnessed card propagation) | `[POST-WICKET-CARD-PROPAGATE]` | 375/0 | ⏳ **0 fires** — no `_unwitnessed→witnessed` upgrade pattern in this match (see pending below) |
| **14** | Cricket-physics balls-ceiling gate | `[BALLS-CEILING-GATE]` | 384/0 | ✅ Correctly silent (clean match) |
| **15** | Score-side admission gate (Layer 1.5) | `[SCORE-INF-GATE]` | 393/0 | ✅ Correctly silent (Fix 11 caught upstream) |
| **16** | SM scalar-field reset on innings-2 transition | `[SM-INNINGS-2-RESET]` | 415/0 | ✅ **FIRED** at F688 (`reason=wickets_regressed`) |
| **17 A** | Pre-match-graphic gate (cold-start) | `[PRE-MATCH-GRAPHIC-GATE]` | 429/0 | ✅ Active post-hotfix-5 (no incorrect team commits observed) |
| **17 D** | WS cold-start gate | `[WS-COLD-START-GATE]` open / suppress | 429/0 | ✅ **FIRED** — 1 OPEN event at F39 (timeout path; cold-start suppression worked) |
| **18 L2** | Bat-runs reconciler detection | `[BAT-SUM-RECONCILER]` | 441/0 | ✅ **FIRED** — 3 detections (Mukul Choudhary period F2832-F2837, excess=8) |
| **18 L3** | Capping-batters reset (Path C hybrid) | `[CAP-RESET-LAST-ADVANCE]` | 441/0 | ✅ Correctly silent (excess<10, conservative behaviour) |
| **harness** | Telemetry analyzer extended for Fixes 13–18 | regex `FIX13_*`…`FIX18_*` + `--report-13`…`--report-18` + `--report-all-fixes` | n/a | ✅ Produced the Fix-10 zero-fire finding that triggered Fix 13 spec |

**Tally**: 8 fixes positively fired in production, 4 correctly silent, 1
pending fire (Fix 13 — needs specific code path).

---

## 2. Fix 17 ship-day hotfixes

Fix 17 (cold-start Path A + Path D) needed 4+ hotfixes during deployment after
live UX issues surfaced. All in `test_pipeline.py`:

1. **Hotfix 1 (Path A)**: `UnboundLocalError` on `extracted` — re-routed to
   parse score / wickets / overs directly from raw `description` (scout
   text) via regex.
2. **Hotfix 2 (Path D)**: `_ws_cold_start_gate_check` was reading top-level
   `payload.score / .batting_team`, but `build_full_payload` puts them under
   `payload.scorecard`. Now reads from both shapes.
3. **Hotfix 3 (Path D)**: gate too strict (required `score >= 1`) — caused
   90s timeout at innings-2 cold-start where `score=0` is legitimate.
   Loosened to "open as soon as any `batting_team` is committed."
4. **Hotfix 4 (Path A)**: `_broadcast_cache.team_abbr` retained stale value
   when gate fired. Added `pop("team_abbr", None)` on every gate fire.
5. **Hotfix 5 (Path A)**: a second team-assignment branch via
   `extracted.batting_team_visible` was bypassing Path A entirely.
   Extended the gate to cover the visible-team branch.

After Hotfix 5, no further team-misassignment incidents observed during
the match.

---

## 3. New backlog items filed from production observation

(All documented in `files/docs/backlog.md`; reproduced here for hand-off
context.)

### P0

- **(7) Fix 13 placeholder-FOW coverage gap** — Mitchell Marsh dismissal at
  F775 (LSG 8-1, 1.1 ov) stayed `_unwitnessed` forever. Fix 13 only fires on
  `_unwitnessed→_witnessed` upgrades, so it never engaged. Result:
  striker self-collision (`AFTER_striker=Markram, AFTER_non_striker=Markram`)
  and Marsh visible as active batter in UI for 2+ minutes. 21+
  `WS-PROJECTION-FALLBACK` events kept resurrecting him. **Needs Path B
  (sibling hook on `wickets++` rather than only on the upgrade).**

- **(10) `over_history` dual-writer over-key/shape collision** —
  `score_manager.py` writes `list[str]` keyed by `int(prev.overs)`;
  `eyes/this_over.py` writes `dict{balls,bowler,runs,wickets}` keyed by
  `held_int`. Same `state.over_history` field, opposite shapes. UI flips
  between views and the over-3→over-4 transition at 21:53:14 IST showed
  the last two balls of over 3 (`1 1`) "stuffed" into the head of the
  empty over-4 strip for ~50s. Recommended fix: Path B (shape-canonicalize
  at `build_full_payload` level, ~15–25 lines) as bounded near-term, with
  Path A (single writer) as architectural follow-up.

### P1

- **(6) Extractor splits "Rinku Singh" → RINKU + SINGH ghost batter** —
  At F86 the extractor mis-parsed "Rinku Singh" as two separate batters
  (`RINKU` and `SINGH`). The "SINGH" fragment was written to `non_striker`
  state and persisted, generating 341 `WS-SCRUB` rejections during innings 1.
  Mitigated as a side-effect by Fix 16's `set_innings_2()` reset at F688,
  but the root-cause extractor split needs a proper canonicalization fix.

- **(8) Fix 16 coverage gap: pipeline AUTO-SWAP path doesn't invoke
  `score_manager.set_innings_2`** — `test_pipeline.py:5857` calls
  `scoreboard.set_innings_2()` but not `score_manager.set_innings_2()`,
  leaving SM to auto-detect its own transition at F688 where it incorrectly
  picked up `frame.broadcast_team="KKR"` (transient misread) for
  `new_batting_team`. External WS payload remained correct due to canonical
  data sourcing, but the SM internal transition is fragile.

- **(9) `WS-PROJECTION-FALLBACK` does not check `batting_card.status`** —
  The fallback projection path that surfaces batter names from `sb._inn`
  when SM has a null value uses `active_batting` membership without
  checking `batting_card[name].status != "out"`. This is what kept
  resurrecting dismissed Marsh as non_striker (see P0 (7)).

**Pattern observation**: 4 of 5 new backlog items today trace back to the
**dual-broadcaster substrate** (SM-emit branch vs scoreboard-emit branch in
`test_pipeline.py:8110`). The case for unifying broadcast emission is now
structurally load-bearing — top architectural priority once the targeted
P0 / P1 fixes ship.

---

## 4. Production telemetry highlights

### Fix 12 RELEASE events (3) — first-ever Layer 4 production firings

```
F2453 22:47:30 — [RUNS-REJECT-RELEASE] Ayush Badoni: 5 consecutive
       rejections of runs=0 (cur=7) — accepting as new truth.
F2864 23:00:40 — [RUNS-REJECT-RELEASE] Himmat Singh: 5 consecutive
       rejections of runs=6 (cur=16) — accepting as new truth.
       (+1 additional release)
```

POISON-STREAK template successfully applied to runs-monotonic guard.
Threshold of 5 produced clean releases without false positives.

### Fix 11 EXTRAS-INF-GATE — 25 fires

Heavy active defence during death overs when extractor was under stress.
Notable: F1377 caught a strip misread with `bat_sum=49 > score=39 (excess=10)`
and held the scoreboard pristine.

### Fix 10 POST-WICKET-ROTATION — 4 fires

First fire: Markram dismissal at F1850 22:27:23 via `_auto_dismiss_for_new_batter`
path: `[POST-WICKET-ROTATION] non_striker 'Aiden Markram' dismissed → slot
cleared pending new-batter admission`. Pre-fix collision baseline 72.4/wkt;
post-fix this match 14.8/wkt (~5x improvement, status PARTIAL relative to
strict <10/wkt target — residual cases likely the same `_unwitnessed`-only
path as P0 (7)).

### Fix 18 L2 BAT-SUM-RECONCILER — 3 fires

```
F2832 22:59:26 — bat_sum=112 > score+5=109 (excess=8)
F2836 22:59:33 — same divergence
F2837 22:59:37 — same divergence
```

Layer 2 detection working. All three within 11s on the Mukul Choudhary
period; excess=8 < 10 so Layer 3 correctly held back (conservative).

---

## 5. Pending tasks (resume tomorrow)

### Validation still pending

- **Fix 13** (`POST-WICKET-CARD-PROPAGATE`) — 0 fires across 8 witnessed
  wicket transitions in this match. All wickets routed through
  `_auto_dismiss_for_new_batter` (Fix 10 fired directly) or stayed
  `_unwitnessed` permanently (P0 (7) gap). Awaiting a future match where
  the actual `_unwitnessed→_witnessed` upgrade pattern occurs.

### P0 backlog items to address

- **P0 (7)** — Fix 13 Path B: sibling hook on `wickets++` to cover
  `_unwitnessed`-only path. Empirically the most impactful (caused the
  visible 2+ min "Marsh still batting" UX bug).
- **P0 (10)** — `over_history` dual-writer collision. Path B (shape-
  canonicalize at `build_full_payload`, ~15–25 lines) recommended as
  bounded near-term fix.

### P1 backlog items to schedule

- **P1 (6)** — Rinku Singh extractor split (root-cause canonicalization).
- **P1 (8)** — Fix 16 coverage gap: invoke `score_manager.set_innings_2()`
  from pipeline AUTO-SWAP path.
- **P1 (9)** — `WS-PROJECTION-FALLBACK` `batting_card.status` check.

### Architectural follow-up

- **Unify broadcast emission** — collapse the dual-broadcaster substrate
  in `test_pipeline.py:8110`. 4 of 5 P0/P1 items today trace back to this.
  Should be the next architectural priority once targeted P0/P1 fixes ship.

### Fix 10 partial-validation residual

- Investigate why collision rate is 14.8/wkt instead of <10/wkt. Likely
  the same `_unwitnessed`-only path as Fix 13's P0 (7) gap. Re-evaluate
  after P0 (7) ships.

---

## 6. Files touched today

- `files/test_pipeline.py` — Fixes 14, 15, 17 (Path A + Path D, all 5 hotfixes), Fix 16 callsite usage
- `files/eyes/scoreboard.py` — Fix 13 (Case 5 in `_post_witnessed_dismissal_slot_rotation`), Fix 18 (L2 `[BAT-SUM-RECONCILER]` + L3 `[CAP-RESET-LAST-ADVANCE]` + `_last_runs_advance` tracking)
- `files/score_manager.py` — Fix 16 (canonical `set_innings_2()` method)
- `files/eyes/this_over.py` — analyzed for P0 (10) (no edit yet)
- `files/test_recent_fixes.py` — new tests for Fixes 13–18 + Fix 17 hotfix renames; final 443 PASS / 0 FAIL
- `files/analyze_match_telemetry.py` — extended for Fix 13–18 telemetry parsing + report functions + `--report-all-fixes`
- `files/docs/backlog.md` — full top-of-file catalog of changes shipped today + 5 new backlog items (P0×2, P1×3)

---

## 7. Run artefact

Full live log of today's match used for validation:

`logs/pipeline-2026-04-26-212408-lsg-kkr-fixes-13-18-deploy-v7-vis-team-gate.log`

Re-run the validation report any time:

```bash
cd files && source .venv/bin/activate
python analyze_match_telemetry.py \
  --log ../logs/pipeline-2026-04-26-212408-lsg-kkr-fixes-13-18-deploy-v7-vis-team-gate.log \
  --fix-validation-only --report-all-fixes
```

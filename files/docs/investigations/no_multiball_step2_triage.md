# STEP 2 Pre-edit Triage — no-MULTI_BALL architecture

**Purpose:** consolidate all classifications required to execute STEP 2
without breaking cold-start or under-deleting warm-path code.
**Predecessor:** `no_multiball_design.md` (memo §3 needs a second
amendment before STEP 2 — see §6 below).

---

## §1. `_infer_partial_event:604` consumer trace

- Called from `cricket_rules.py:378`:
  `return ValidationResult(ok=True, event_type=_infer_partial_event(diff))`
  inside `validate_diff`'s partial-data path (used when one or more
  striker/bowler deltas are missing).
- Returns the same `event_type` field that line 372's full-data path
  populates with the literal `"MULTI_BALL"`.
- Downstream: `event_type` feeds `score_manager._infer_event` (line
  3594) → if `"MULTI_BALL"`, an event of that type is constructed and
  flows to `_apply_event:2745` → handler at 4306; via `_apply_event:4299`
  → `_accumulate_stats_from_event` handler at 4095.

**Disposition:** rename line 604 return `"MULTI_BALL"` → `"DEFERRED_MULTI"`
for label consistency with line 372. Other return labels
(`"DOT"`, `"FOUR"`, `"SIX"`, `"WICKET"`, `"RUNS"`, `"EXTRA"`,
`"UNKNOWN"`) are unaffected. After the rename, warm-path validation
never produces the literal `"MULTI_BALL"` — only the cold-start
producer at `sm.py:1857` does (renamed to `"COLD_START_SYNTH"` per §2).

---

## §2. Audit: all reachable producers of `{"type": "MULTI_BALL", ...}` event dicts

Grep `"type":\s*"MULTI_BALL"` across `files/` found 5 sites:

| File:line | Caller | Classification | Action |
|---|---|---|---|
| `score_manager.py:1857` | `_handle_cold_start` post-`_accept_initial` block | **Cold-start producer** | Rename type → `"COLD_START_SYNTH"` |
| `eyes/commentary.py:505` | `Commentary.on_ball_event` else-branch (`elif balls_delta > 1`) | **WARM-path producer (BED)** | Per STEP 2 sub-item 4: replace with N per-ball `ABSORBED_LEGAL` events with `bowler=None, striker=None`; each enqueued into pending queue |
| `test_recent_fixes.py:11981` | Test fixture | Test | Update fixture: if asserting cold-start MULTI_BALL behavior → rename to `COLD_START_SYNTH`; if exercising warm-path → rewrite for pending-queue flow |
| `docs/investigations/multi_ball_decomposition_design.md:87` | Doc snippet | Docs | No action (historical) |
| `docs/investigations/state_integrity_f3293_f3346.md:112` | Doc snippet | Docs | No action (historical) |

**Plus indirect producer:** `_infer_event` (sm.py:3594) constructs
MULTI_BALL events when `validate_diff` returns `event_type="MULTI_BALL"`.
Per STEP 2 sub-item 6, `_infer_event` is rewired to fan out N
`ABSORBED_LEGAL` events when validator says `"DEFERRED_MULTI"`. After
this rewire, `_infer_event` ceases producing MULTI_BALL events.

---

## §3. Audit: all callers of `_apply_event` / `_accumulate_stats_from_event`

### `_apply_event` (sm.py:4285) production callers
- `score_manager.py:1865` — `_handle_cold_start` cold-start synthetic
  event applier. **Passes `type="COLD_START_SYNTH"` post-rename.**
- `score_manager.py:2745` — `_handle_warm` else-branch after
  `_infer_event` produces non-ABSORBED_LEGAL events. Post-refactor
  `_infer_event` no longer produces MULTI_BALL events (fan-out goes
  to ABSORBED_LEGAL via line 2742), so events arriving here are
  `DOT, RUNS, FOUR, SIX, WICKET, EXTRA, …` — **never** COLD_START_SYNTH
  and **never** MULTI_BALL.

Tests call `_apply_event` directly (`test_score_manager_history_preservation.py:213`,
`tests/test_this_over_dedup.py:72/81/99/104`, `tests/test_pipeline_reliability_batch.py:395`,
`test_recent_fixes.py:3500/11821/11886`). None construct MULTI_BALL
events except `test_recent_fixes.py:11981` (already covered in §2).

### `_accumulate_stats_from_event` (sm.py:4064) callers
- `_apply_event:4299` — sole production caller (chained).
- `scripts/replay_validate_stats.py:225/228/233` — replay tool,
  out of STEP 2 scope.

**Conclusion:** after rename + refactor, both MULTI_BALL handlers
(`_accumulate_stats_from_event:4095` and `_apply_event:4306`) are
**reachable only from the cold-start producer at `sm.py:1857`**.
Tightening their guards to `if etype == "COLD_START_SYNTH":` cleanly
scopes them to cold-start while leaving the bodies intact.

---

## §4. Literal `MULTI_BALL` grep classification

### `score_manager.py`

| Line | Context | Classification |
|---|---|---|
| 19 | `MULTI_BALL_MAX_BALLS,` (import) | **Delete** |
| 79–86 | `_warn_multi_ball_cap_if_cricket_reject` body | **Delete** (whole function) |
| 260 | Comment "MULTI_BALL gap if the diff passes" | Update wording (DEFERRED_MULTI / COLD_START_SYNTH) |
| 262 | Comment "MULTI_BALL_MAX_BALLS=12 because cold-start..." | Update wording (constants gone) |
| 265 | `COLD_START_MULTI_BALL_MAX_BALLS = 3` | **Keep** (cold-start constant) |
| 391, 535 | Comments "no-MULTI_BALL architecture" | Keep (new architecture markers) |
| 1481 | Comment "MULTI_BALL decomposition" in cold-start synth docstring | Update wording |
| 1780, 1782 | Comments "treat as a MULTI_BALL gap" in `_handle_cold_start` | Update wording → COLD_START_SYNTH |
| 1801 | `if 0 < _d_balls <= COLD_START_MULTI_BALL_MAX_BALLS:` | **Keep** (cold-start gate) |
| 1820 | log "committing card as MULTI_BALL gap" | Update wording → COLD_START_SYNTH |
| 1851–1852 | Comments "Construct + apply the synthetic MULTI_BALL event" | Update wording → COLD_START_SYNTH |
| **1857** | `"type": "MULTI_BALL"` | **Rename → `"COLD_START_SYNTH"`** |
| 1881 | log refs `COLD_START_MULTI_BALL_MAX_BALLS` | Keep |
| 3559 | Docstring ref to `cricket_rules.MULTI_BALL_MAX_BALLS` | Update — constants deleted |
| **3570** | log `[MULTI_BALL_DECOMPOSED]` | **Delete** (warm-path log) |
| **3601** | Comment "MULTI_BALL: skipped deliveries" | **Delete** (warm-path comment) |
| 3952–3953 | Comments "MULTI_BALL gap decomposition" / "MULTI_BALL hook" in `_apply_absorbed_event` | **Delete** with the warm-path callsite at 3961–3966 |
| **3961–3966** | warm-path gap-token lookup inside `_apply_absorbed_event` | **Delete** — pending queue's `runs_delta` makes this redundant for ABSORBED_LEGAL processing |
| 4071 | Comment "for MULTI_BALL or no-SB tests" | Investigate context (likely deletable warm-path comment) |
| **4089** | Comment "A1 part 2: MULTI_BALL decomposition" — intro to block | **Update wording** (block stays, renamed) |
| **4095** | `if etype == "MULTI_BALL":` in `_accumulate_stats_from_event` | **Rename guard → `if etype == "COLD_START_SYNTH":`** — KEEP body (cold-start needs it) |
| **4306** | `if event["type"] == "MULTI_BALL":` in `_apply_event` | **Rename guard → `if event["type"] == "COLD_START_SYNTH":`** — KEEP body (cold-start needs it) |

### `eyes/this_over.py`

| Line | Context | Classification |
|---|---|---|
| 530 | Comment "applies to MULTI_BALL and DRS_* events" | Update wording |
| **592** | `elif event.get("type") == "MULTI_BALL":` handler block 592–619 | **Open question** — does cold-start producer at sm.py:1857 reach this handler? The cold-start path calls `self._apply_event(_mb_event)` which updates `self.this_over` directly (sm.py:4314); it's unclear whether the `over_mgr` ThisOverManager instance is ALSO invoked with the same event. **Recommended:** read sm.py around the `over_mgr.on_event(...)` call site to confirm. If cold-start does NOT touch `over_mgr`, DELETE block 592–619 per the spec. If cold-start does touch `over_mgr`, RENAME guard to COLD_START_SYNTH instead. |
| 810 | Comment "from on_ball_event or MULTI_BALL placeholders" | Update wording |
| 927 | Docstring "MULTI_BALL gaps, etc." | Update wording |

### `test_pipeline.py`

| Line | Context | Classification |
|---|---|---|
| 339, 383, 537 | Comments about commentary engine filtering MULTI_BALL (`certain=False`) | Update wording (DEFERRED_MULTI / COLD_START_SYNTH; commentary now sees ABSORBED_LEGAL from pending queue) |
| 6991 | Comment "19-ball MULTI_BALL jump" | Update wording |
| **9468–9475** | imports `MULTI_BALL_MAX_BALLS`, uses in delta-balls check | **Delete** (constant being removed; the check is duplicated cap logic that the new pending queue makes irrelevant) |
| 11429 | Comment "MULTI_BALL catchup" | Update wording |

---

## §5. Folded-in dispositions from prior memo §3 amendment

The 4 `_infer_gap_tokens` call sites previously classified:

| Site | Prior amendment | Re-validated |
|---|---|---|
| `sm.py:2365` (`_accept_initial`) | Cold-start adjacent — KEEP | ✅ Same — KEEP; call switches to renamed `_cold_start_infer_gap_tokens` |
| `sm.py:3961` (`_apply_absorbed_event`) | WARM — DELETE | ✅ Same — DELETE (warm-only; cold-start path doesn't reach `_apply_absorbed_event`) |
| `sm.py:4104` (inside `_accumulate_stats_from_event` block 4089–4128) | WARM — DELETE entire block | ❌ **CORRECTED** — RENAME block's guard to COLD_START_SYNTH, KEEP body. Cold-start producer at 1857 reaches this handler via `_apply_event:4299` → `_accumulate_stats_from_event`. |
| `sm.py:4314` (inside `_apply_event` block 4306–4319) | WARM — DELETE entire block | ❌ **CORRECTED** — RENAME block's guard to COLD_START_SYNTH, KEEP body. Same reachability path as 4095. |

---

## §6. Required memo §3 re-amendment before STEP 2

Two rows in the prior amendment's **Delete / rename** table are wrong
and must be corrected from "Delete" to "Rename guard, keep body":

```
- files/score_manager.py | 4089–4128 | Delete entire MULTI_BALL block
+ files/score_manager.py | 4089–4128 | Rename guard `if etype == "MULTI_BALL"` to `"COLD_START_SYNTH"`; KEEP body (cold-start producer at 1857 reaches this via _apply_event → _accumulate_stats_from_event chain)
- files/score_manager.py | 4306–4319 | Delete entire `if event["type"] == "MULTI_BALL"` block
+ files/score_manager.py | 4306–4319 | Rename guard `if event["type"] == "MULTI_BALL"` to `"COLD_START_SYNTH"`; KEEP body (same reachability)
```

The earlier amendment was based on the incomplete model that
MULTI_BALL handlers are purely warm-path consumers. The audit in §3
confirms cold-start reaches both handlers — they must stay alive
with tightened guards.

---

## §7. Recommended STEP 2 plan (revised)

**A. `cricket_rules.py`**
- Delete `MULTI_BALL_MAX_BALLS`, `MULTI_BALL_MAX_WKT` (lines 37–38).
- Rename `infer_gap_tokens` → `_cold_start_infer_gap_tokens` (lines
  649–704).
- `validate_diff:372`: `event_type="MULTI_BALL"` → `"DEFERRED_MULTI"`.
- `_infer_partial_event:604`: `return "MULTI_BALL"` → `return "DEFERRED_MULTI"`.

**B. `score_manager.py`**
- Delete `_warn_multi_ball_cap_if_cricket_reject` (lines 79–86).
- Delete import of `MULTI_BALL_MAX_*` constants (line 19).
- Update conditional import (line 28):
  `from cricket_rules import _cold_start_infer_gap_tokens as _infer_gap_tokens`.
- Rewire `_infer_event`: on `DEFERRED_MULTI`, fan out N events of
  type `ABSORBED_LEGAL` with `bowler=None, striker=None`; each calls
  `self._enqueue_pending_ball(placeholder_token="?")`.
- Line 1857: `"type": "MULTI_BALL"` → `"type": "COLD_START_SYNTH"`.
- Line 4095: guard `if etype == "MULTI_BALL":` → `if etype == "COLD_START_SYNTH":`.
- Line 4306: guard `if event["type"] == "MULTI_BALL":` → `if event["type"] == "COLD_START_SYNTH":`.
- Delete lines 3961–3966 (warm-path gap-token lookup in
  `_apply_absorbed_event`); delete the lead-in comment at 3952–3958.
- Delete log/comment refs at 3570, 3601, 4089-intro.
- Update wording at 260, 262, 1481, 1780, 1782, 1820, 1851–1852, 3559.

**C. `eyes/this_over.py`**
- **Pending §4 open question:** handler block 592–619: DELETE (warm
  only) OR RENAME guard (cold-start reaches too)?
- Add `_pending_slots: dict[int, PendingBall]` instance var.
- On `ABSORBED_LEGAL` event with `placeholder_token="?"`: append `"?"`
  to `self.this_over`; record `slot_idx` via `_pending_slots`.
- Add `rewrite_token(slot_idx, token)` method (in-place update, pop
  from `_pending_slots`).
- Update import at 1307: `from cricket_rules import _cold_start_infer_gap_tokens as infer_gap_tokens`.

**D. `eyes/commentary.py`**
- Line 505 BED warm-path producer: replace
  `{"type": "MULTI_BALL", "balls_missed": balls_delta, ...}` with N
  per-ball `ABSORBED_LEGAL` events (one per ball in the gap), each
  with `bowler=None, striker=None`. SM consumer at `_handle_warm:2742`
  enqueues into pending queue.

**E. `test_pipeline.py`**
- Delete 9468–9475 block (constant import + cap check).
- Update wording at 339, 383, 537, 6991, 11429.

**F. Tests**
- `test_anomaly_rules.py`: update for `DEFERRED_MULTI` rename if
  consumed by anomaly rules.
- `test_recent_fixes.py:11981`: update for new flow.
- New `test_this_over_pending.py`: verify `"?"` → real token rewrite
  via `rewrite_token`.

---

## §8. One open question requiring code-read before STEP 2 starts

`eyes/this_over.py:592–619` handler — is it reached by cold-start
producer at `sm.py:1857`? Depends on whether the cold-start
`_apply_event` call at sm.py:1865 transitively invokes
`over_mgr.on_event(_mb_event)` (or similar), where `over_mgr` is
the ThisOverManager instance. If yes: rename guard. If no: delete.

Recommended check: grep `over_mgr.*on_event\|over_mgr\..*append`
in `score_manager.py` and read the call-site context.

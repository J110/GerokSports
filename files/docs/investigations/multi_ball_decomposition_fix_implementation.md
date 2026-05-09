# MULTI_BALL decomposition (Issue 3, Direction B / Policy U) — implementation note

Shipped replacement of a single `MULTI_BALL` emission with **N** `ABSORBED_LEGAL` events, **`ball_events`** on the ScoreManager payload (**D1**), **no Layer 2 enqueue** for absorbed balls (**D2**), and **no striker rotation across the absorbed gap** (**D3**). Design: `multi_ball_decomposition_design.md`.

---

## §1 Implementation summary

| Item | Detail |
|------|--------|
| **D1 API** | `on_frame` / `_build_payload` expose **`ball_events`** (full list) and **`ball_event`** (last event, backward compatible). |
| **D2 Layer 2** | `test_pipeline`: `_layer2_enqueue_blocked_absorbed` runs **before** `_evt_is_real` in the enqueue `if`; **`[LAYER2-SKIP-ABSORBED]`** DEBUG on skip. |
| **D3 Strike** | Absorbed path uses `_apply_absorbed_event` only; `_apply_event` strike-rotation block documents that **`ABSORBED_LEGAL` never reaches it**. |
| **`MULTI_BALL_MAX_BALLS`** | **12** — **`files/cricket_rules.py`** line ~37 (single definition). Read only from **`_check_invariants`** / **`validate_diff`**. **`score_manager`** imports the symbol for cap-hit telemetry. |
| **Cap-exceeded behavior** | **(b) REJECT**: **`_decompose_multi_ball` does not clamp**; it is not reached when `d_balls > cap` because **`validate_diff`** fails first (**`emitted_count=0`**). Existing **`[SM] REJECT`** WARN unchanged. |
| **Cap telemetry** | **`[MULTI_BALL_CAP_EXCEEDED]`** includes **`d_balls`**, **`cap`**, **`emitted_count=0`**, **`reason=reject`**, **`context`** (`warm_on_frame` / `cold_start_stale_recovery`), **`cricket_reject`**. |
| **Rationale (12)** | **F3293-class** (~9 balls). **F5054-class** (~25) stays carousel/post-match (**`state_integrity_f5054_f5240.md`** §6); **`test_recent_fixes`** still patches cap **>** production for the 25-ball fixture. |
| **Files changed** | `cricket_rules.py`, `score_manager.py`, `test_pipeline.py`, `eyes/this_over.py`, `eyes/cricket_logger.py`, `wire.py`, `test_recent_fixes.py`, this note, `INDEX.md`. |
| **New tests** | Six under **`pytest -k multi_ball_decompose`** (incl. cap-exceeded). |

**Reviewer overrides (from task memo):** If product requires per-ball UI animations via separate WS payloads, revise **D1** before further investment. If Layer 2 retrospective accuracy justifies cost, replace skip with **one batched enqueue per gap**. If striker drift across gaps is user-visible, add a post-gap realignment pass (explicit follow-up, not part of this ship).

---

## §2 Files modified

### `files/cricket_rules.py`

- **`MULTI_BALL_MAX_BALLS = 12`** — sole definition; enforced in **`_check_invariants`** only.

### `files/eyes/cricket_logger.py`

- **`CricketLogger.debug(msg)`** routes to **`logging.getLogger(component).debug`** so **`log.debug(f"...")`** call sites do not require printf-style varargs (which `info`/`warn` do not support).

### `files/score_manager.py`

- **`MULTI_BALL_MAX_BALLS`** import; **`_warn_multi_ball_cap_if_cricket_reject`** (**`[MULTI_BALL_CAP_EXCEEDED]`**) on warm reject + cold stale-recovery reject when cricket **`d_balts_*_>_multi_max_*`**.
- **`ABSORBED_LEGAL`** constant; **`_decompose_multi_ball`** with **`[MULTI_BALL_DECOMPOSED]`** INFO and per-ball **`[ABSORBED_LEGAL]`** DEBUG.
- **`_infer_event`**: `d_balls > 1` → list of absorbed events (not `MULTI_BALL`).
- **`_handle_warm`**: normalize inferred to `events`; per absorbed ball set **`over`**, call **`_apply_absorbed_event`**; payload via **`_build_payload(..., ball_events=events)`**.
- **`_apply_absorbed_event`**: partnership **`balls += 1`** each step; **`runs`** from gap meta on **last** ball only; **`gap_finalize_wicket`** → **`_apply_wicket_fall_only`**.
- **`_apply_event`**: guard if type is **`ABSORBED_LEGAL`**; strike-rotation comment for **D3**.

### `files/test_pipeline.py`

- **`_layer2_enqueue_blocked_absorbed`**; enqueue condition orders **absorbed gate before `_evt_is_real`**.
- Fan-out **`ball_events`** to **`ThisOverManager`** / analytics; shadow **`[SHADOW-DECOMPOSED]`** when SM emits multiple absorbed balls vs BED single `MULTI_BALL`.
- Wire: **`format_absorbed_gap_wire`** for gap summary; **`format_wire`** returns **`None`** per absorbed ball.

### `files/eyes/this_over.py`

- **`ABSORBED_LEGAL`**: one **`?`** (or **`W`** if **`gap_finalize_wicket`**).
- **`MULTI_BALL`**: **`balls_missed` / `balls_skipped`**, **`total_runs` / `runs`**.

### `files/wire.py`

- **`format_absorbed_gap_wire`**, **`format_wire`** → **`None`** for **`ABSORBED_LEGAL`**.

### `files/test_recent_fixes.py`

- Six **`multi_ball_decompose`** tests (gap helper + **`cricket_rules`** patch where **`d_balls > MULTI_BALL_MAX_BALLS`** production cap — **25-ball** fixture only).

---

## §3 Test results

Run from repo root:

```bash
python3 -m pytest files/test_recent_fixes.py -k multi_ball_decompose -v
python3 -m pytest files/test_recent_fixes.py -k align_extractor_batters_fixture -v
```

Expect **6** (`multi_ball_decompose`) and **6** (`align_extractor_batters_fixture`) passed (verified locally).

---

## §4 Cross-match validation

- **GT–RCB / F5054 class gaps:** decomposition improves partnership ball accounting vs a single `MULTI_BALL`; **no per-ball run attribution** (Policy U).
- **Shadow / BED:** `[SHADOW-DECOMPOSED]` distinguishes list-vs-single from a hard mismatch.

---

## §5 Telemetry

| Tag | Level | Where |
|-----|-------|--------|
| **`[MULTI_BALL_DECOMPOSED]`** | INFO | `_decompose_multi_ball` (single-string `CricketLogger.info`). |
| **`[MULTI_BALL_CAP_EXCEEDED]`** | WARN | `_warn_multi_ball_cap_if_cricket_reject` (`score_manager`) when **`validate_diff`** rejects Δballs over cap. |
| **`[ABSORBED_LEGAL]`** | DEBUG | Per synthetic ball (`CricketLogger.debug` → stdlib logging). |
| **`[LAYER2-SKIP-ABSORBED]`** | DEBUG | `_layer2_enqueue_blocked_absorbed` |
| **`[SHADOW-DECOMPOSED]`** | INFO | shadow compare (`test_pipeline`) |

---

## §6 Rollback

Revert the Issue 3 commit(s): restores single **`MULTI_BALL`** inference and prior enqueue ordering. No schema migration.

---

## §7 Next-match validation criteria

1. **`[MULTI_BALL_DECOMPOSED]`** volume correlates with graphic gaps; no spike in **`[SM] REJECT`** for legitimate large gaps — if so, consider raising **`MULTI_BALL_MAX_BALLS`** in **`cricket_rules`** with product sign-off.
2. Partnership **`balls`** no longer under-count across missed stretches vs logs.
3. **`pytest -k multi_ball_decompose`** and **`-k align_extractor_batters_fixture`** stay green.

---

## References

- `multi_ball_decomposition_design.md`
- `state_integrity_f5054_f5240.md` (F5054 `d_balls=25` context)

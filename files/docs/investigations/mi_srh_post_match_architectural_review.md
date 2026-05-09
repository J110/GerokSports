# MI vs SRH — Post-match architectural review (2026-04-30)

**Match:** MI vs SRH, IPL 2026 match 151954  
**Log:** `logs/pipeline-2026-04-29-194416-mi-srh-live.log`  
**Innings 1:** MI 239-5 (20.0 overs)  
**Innings 2:** SRH chase, pipeline failed F2695–F2998 (~11 min)  
**Author:** Sonnet 4.6 post-match architectural review agent  
**Handoff from:** `mi_srh_innings_break_analysis.md` + backlog entry (2026-04-29 22:05 IST)  
**Status:** §P0-A and §P0-B are mechanical (call-site additions); §P0-C is this document's subject.

---

## §1 — Three P0 bugs from innings-2 transition failure

| Bug | Label | Mechanical? | Fix location |
|---|---|---|---|
| `SM.set_innings_2()` not called on `overs_complete_20` path | **P0-A** | Yes | Add `score_mgr.set_innings_2(...)` inside `execute_innings_change()` |
| TRACKING overs consensus not reset on innings change | **P0-B** | Yes | Add `overs_tracker.reset()` inside `execute_innings_change()` or `reset_for_innings()` |
| Team-swap trusts visible strip during innings break | **P0-C** | No — design decisions required | `test_pipeline.py:5016–5128` (`execute_innings_change`) + `test_pipeline.py:8259–8265` (latch site) |

**P0-A summary:** `execute_innings_change()` calls `scoreboard.set_innings_2()` but NOT `score_mgr.set_innings_2()`. Fix 16 added `score_mgr.set_innings_2()` only on the SCORER `innings_change=True` path (`test_pipeline.py:6835`). The `overs_complete_20` + timeout path fires through `execute_innings_change()` and never reaches that callsite. Fix: inside `execute_innings_change()`, after the non-cold-start swap (line ~5106), add `score_mgr.set_innings_2(target=derived_target, batting_team=new_bat, reason=source)`.

**P0-B summary:** `reset_for_innings()` (`test_pipeline.py:5001`) calls `ball_detector.reset()`, `partnership_tracker.reset()`, `over_mgr.reset()` but does NOT reset the TRACKING overs `ConsistentReadTracker` floor. After innings 1 (overs=20.0), the tracker's confirmed floor is 20.0. Innings 2 reads overs 0.x–5.x are rejected as "regression" against the 20.0 floor. Fix: add `tracker.reset()` (or `tracker.force_cold_start()`) inside `reset_for_innings()` scoped to the overs field only.

**P0-C:** The remainder of this document.

---

## §2 — P0-C root cause reconstruction

### §2.1 Failure sequence in the MI vs SRH log

| Frame | Time | Event |
|---|---|---|
| F2346 | ~21:32:51 | Last confirmed innings-1 read (MI 239-5 20.0) |
| F2347 | ~21:32:55 | `[INNINGS-BREAK]` latched — `overs_complete_20`; `_inn_break_pending=True` |
| F2347–F2694 | ~21:32 → 22:01 | **Innings break carousel.** Strip shows MI recap graphics. POISON-RECAL fires 3 times (F2483, F2855, F2954). Each sets `scoreboard._inn["overs"] = None`, `score = None`, `wickets = None`. |
| F2695 | ~22:01:xx | **`[INNINGS-CHANGE] Firing — source=overs_complete_20 trigger=timeout`** (~348-frame timeout). `execute_innings_change("overs_complete_20")` called. |
| Inside execute_innings_change | — | `scoreboard._inn.get("overs")` → **None** (POISON-RECAL wiped it). `_prev_overs_f = 0.0`. `_prev_overs_f < 18.0 AND prev_wkts < 8` → **`cold_start_inn2_by_state = True`**. Enters cold-start path. **NO TEAM SWAP executed.** |
| F2695–F2998 | ~22:01 → 22:12 | MI stays as batting team. SRH correctly scores runs but strip label shows MI. "MI 0/0 (- ov)" persisted ~11 min. |
| Pipeline restart | 22:12 IST | Operator manually restarted. SRH state was clean (score, batters, bowler correct). Recovery ~30 frames. |

### §2.2 The `cold_start_inn2_by_state` false positive

The `cold_start_inn2` guard exists to handle a legitimate case: the pipeline starts mid-innings-2 and mistakenly believes it has been watching innings 1 all along. In that case, wiping the accumulated (actually innings-2) state would break everything.

The MI/SRH failure demonstrates a **structurally different case** that fools the same guard:

```
Innings 1 actually completed (overs=20.0 confirmed) 
  → _inn_break_pending = True (legitimate innings-end signal)
  → POISON-RECAL fires during innings break
  → scoreboard._inn["overs"] = None
  → execute_innings_change reads _prev_overs_f = 0.0
  → cold_start_inn2_by_state = True   ← FALSE POSITIVE
  → cold-start path: relabel inn1→inn2 without swap
  → MI stays batting (WRONG)
```

The guard cannot distinguish "SM state wiped by POISON-RECAL during a legitimate innings break" from "SM state reflects genuine cold-start mid-chase". The distinguishing signal is `_inn_break_pending_source ∈ {"overs_complete_20", "all_out_10"}` — these are **deterministic, physics-based innings-end triggers** that do not require SM state to be intact.

### §2.3 What the strip read during the break

`team_locked = True` was set during innings 1 play. The `assign_teams()` guard at `test_pipeline.py:4619–4622` rejects team flips when locked:

```python
if team_locked and bat_name != batting_team:
    log.info(f"  [GUARD] Team flip rejected — locked ...")
    return
```

So during the innings break, `batting_team = MI` and `bowling_team = SRH` closure variables were **not** contaminated by strip reads. The contamination happened upstream: **POISON-RECAL zeroed `scoreboard._inn["overs"]`, which made `cold_start_inn2_by_state = True`**, causing the cold-start path to run without a team swap.

The original P0-C statement ("do not read visible batting team from the strip when FRAME_POISONED rate > 50%") is directionally correct but attacks a proximate symptom. The structural fix is to gate the cold-start override on `_inn_break_pending_source`.

---

## §P0-C Design Contract

### §3 — Detection logic

#### §3.1 Primary gate: innings-1-completion determinism flag

**Algorithm:** On the frame where `_inn_break_pending` transitions from False → True (at `test_pipeline.py:8259–8265`), set a new boolean `_inn1_completed_deterministic = True` when `_src_tag in ("overs_complete_20", "all_out_10")`.

At this same frame, latch the current team assignments into two new non-local variables:

```
_inn1_batting_team_latched: str | None = None   # set once, never cleared
_inn1_bowling_team_latched: str | None = None   # set once, never cleared
```

These capture `batting_team` and `bowling_team` at the **last moment before the innings break begins** — when `team_locked = True` is still in effect and the values are confirmed from innings-1 strip reads.

**Why this is reliable:** `team_locked` is set after 3 consecutive strip confirmations during innings 1. By the time `overs_complete_20` fires (ball 20.0), `batting_team` and `bowling_team` have been locked for O(hundreds) of frames. POISON-RECAL events during the break do not unlock teams (they reset SM scalars, not `team_locked`).

#### §3.2 Secondary gate: FRAME_POISONED rolling rate

For trigger paths where `_inn_break_pending_source` is not a deterministic innings-end signal (i.e., the path entered via `to_win_N_off_M`, `scorer_target_toss`, or `target_after_inn1_done`), a FRAME_POISONED rate check provides an additional signal.

**Algorithm:**

```
Window: last _POISON_RATE_WINDOW = 30 frames (≈ 90s at 3s/frame)
Counter: _poisoned_in_window: deque[bool]  (maxlen=30, append per frame)
Rate: sum(_poisoned_in_window) / len(_poisoned_in_window)
```

A rate > `_FRAME_POISONED_STRIP_TRUST_THRESHOLD = 0.50` (50%) indicates the strip is currently unreliable (innings-break carousel, replay overlay, or persistent OCR failure). In this state, the visible `batting_team` from recent strip reads is not trustworthy as a team-swap signal.

**Threshold rationale:** The 50% value is not empirically validated against historical log data. It is a conservative starting point based on the known failure mode (innings-break carousel poisons frames continuously). **Required validation before shipping:** run `analyze_match_telemetry.py` against `pipeline-2026-04-29-194416-mi-srh-live.log` over F2347–F2694 (the actual innings break window) to measure the observed FRAME_POISONED rate. If the rate in that window is < 50%, lower the threshold; the production value must exceed the observed rate in that failure window by at least 10 percentage points.

**New infrastructure required:** The `_poisoned_in_window` deque is new. There is no existing rolling FRAME_POISONED rate tracker in the codebase. Each frame appends `_frame_poisoned` (the boolean set at `test_pipeline.py:6467`) to the deque.

**For the primary path (P0-C fix), this rate is NOT the decision gate.** It is emitted as telemetry only: `[TEAM-ATTRIBUTION-POISON-RATE] rate={rate:.2f} window={_POISON_RATE_WINDOW}`.

#### §3.3 Innings-change cold-start path detection (existing logic)

The `cold_start_inn2` heuristic currently has two components (`test_pipeline.py:5057–5067`):

| Component | Lines | Condition | Purpose |
|---|---|---|---|
| `cold_start_inn2_by_frame` | 5057 | `frame_count <= 20` | Pipeline started ≤20 frames ago — no innings 1 observed |
| `cold_start_inn2_by_state` | 5064–5065 | `_prev_overs_f < 18.0 and prev_wkts < 8` | SM state shows physically incomplete innings 1 |

**P0-C adds a third component that OVERRIDES both:**

```
cold_start_inn2_override = _inn1_completed_deterministic
```

When this flag is set, `cold_start_inn2` MUST be False regardless of the SM state. Innings 1 physically completed; the SM state inconsistency is an artifact of POISON-RECAL.

The full updated expression:
```python
cold_start_inn2 = (
    (cold_start_inn2_by_frame or cold_start_inn2_by_state)
    and not _inn1_completed_deterministic   # P0-C gate
)
```

---

### §4 — Decision logic

#### §4.1 When to trust strip vs cricket rules

| Scenario | Condition | Attribution source | Emit tag |
|---|---|---|---|
| Normal innings 1 play | `_inn_break_pending = False`, `team_locked = True` | Strip (existing `assign_teams` path) | — (existing) |
| Innings break deferral window | `_inn_break_pending = True`, not yet fired | Strip for `batting_team`/`bowling_team` locked — unchanged | `[TEAM-ATTRIBUTION-POISON-RATE]` once per 30 frames |
| Innings-change deterministic path | `execute_innings_change(source ∈ {"overs_complete_20","all_out_10"})` AND `_inn1_completed_deterministic = True` | **Cricket rules:** `new_bat = _inn1_bowling_team_latched`, `new_bowl = _inn1_batting_team_latched` | `[TEAM-ATTRIBUTION-CRICKET-RULES]` |
| Innings-change non-deterministic path (target-derived) | `execute_innings_change(source ∈ {"to_win_N_off_M","scorer_target_toss","target_after_inn1_done"})` AND `_inn1_completed_deterministic = False` | Strip — existing `bowling_team`/`batting_team` closure variables | Existing log lines (no new tag) |
| Cold-start mid-chase path | `cold_start_inn2 = True` after P0-C override applied | Preserve accumulated state; no team swap (existing cold-start relabel) | Existing `[INNINGS-CHANGE] cold-start path` log |

#### §4.2 How long cricket-rules attribution persists

Cricket-rules attribution applies **exactly once**: at the moment `execute_innings_change()` runs and calls `assign_teams(new_bat, new_bowl, innings=2)`. After that, `team_locked` is set True at `test_pipeline.py:5112`, and all subsequent team attributions are governed by the existing strip-based `assign_teams` lock mechanism (which now has SRH correctly locked as the innings-2 batting team).

There is no ongoing "trust cricket rules" mode. The fix is a one-shot correction at the transition boundary. If the strip subsequently shows SRH batting (as it should during innings 2), `assign_teams` will confirm the correct assignment. If the strip shows something else, the `team_locked` guard will reject it as before.

**No "until first clean strip read" or "permanent for this innings" modes needed.** One-shot at transition is sufficient and safe.

---

### §5 — Implementation locations

#### §5.1 New non-local variables (add near `test_pipeline.py:4317–4318`)

| Variable | Type | Initial value | Semantics |
|---|---|---|---|
| `_inn1_batting_team_latched` | `str \| None` | `None` | `batting_team` at the frame where `_inn_break_pending` first becomes True |
| `_inn1_bowling_team_latched` | `str \| None` | `None` | `bowling_team` at same frame |
| `_inn1_completed_deterministic` | `bool` | `False` | True iff innings 1 ended via `overs_complete_20` or `all_out_10` |
| `_poisoned_in_window` | `deque[bool]` | `deque(maxlen=_POISON_RATE_WINDOW)` | Rolling FRAME_POISONED history |

New constants (add near top of `run()` function or at module level adjacent to `_INN_BREAK_MAX_FRAMES`):

```python
_POISON_RATE_WINDOW: int = 30          # frames ≈ 90s; validate against MI-SRH log
_FRAME_POISONED_STRIP_TRUST_THRESHOLD: float = 0.50  # revisit after §3.2 validation
```

#### §5.2 Latch site — `test_pipeline.py:8259–8265`

**Existing code:**
```python
if _det_innings_end and not _inn_break_pending:
    _src_tag = (
        "all_out_10" if _det_all_out
        else "overs_complete_20")
    _inn_break_pending = True
    _inn_break_pending_frame = frame_count
    _inn_break_pending_source = _src_tag
    log.info(...)
```

**P0-C adds three lines inside this block**, after `_inn_break_pending = True`:
```python
    # P0-C: latch confirmed innings-1 team assignment before innings break
    # can corrupt strip reads or POISON-RECAL can wipe SM state.
    if _src_tag in ("overs_complete_20", "all_out_10"):
        _inn1_completed_deterministic = True
        _inn1_batting_team_latched = batting_team
        _inn1_bowling_team_latched = bowling_team
        log.info(
            f"  [INN1-TEAM-LATCH] Latching innings-1 teams: "
            f"bat={_inn1_batting_team_latched} "
            f"bowl={_inn1_bowling_team_latched} "
            f"source={_src_tag} frame={frame_count}")
```

#### §5.3 Rolling FRAME_POISONED update (per-frame, after `test_pipeline.py:8522`)

Inside the `if _frame_poisoned:` / `else:` block, append to the deque **unconditionally** (before the branch, so both poisoned and clean frames are recorded):

```python
# P0-C: track rolling FRAME_POISONED rate for telemetry
_poisoned_in_window.append(_frame_poisoned)
```

Emit rate telemetry every 30 frames when `_inn_break_pending`:
```python
if (_inn_break_pending
        and len(_poisoned_in_window) >= _POISON_RATE_WINDOW
        and frame_count % _POISON_RATE_WINDOW == 0):
    _cur_poison_rate = sum(_poisoned_in_window) / len(_poisoned_in_window)
    log.info(
        f"  [TEAM-ATTRIBUTION-POISON-RATE] "
        f"rate={_cur_poison_rate:.2f} "
        f"window={_POISON_RATE_WINDOW} "
        f"inn_break_pending={_inn_break_pending} "
        f"frame={frame_count}")
```

#### §5.4 `execute_innings_change()` — P0-C override

**File:** `test_pipeline.py:5016–5128`

**Step 1: Declare latched-team non-locals** (add to lines 5017–5021):
```python
nonlocal _inn1_batting_team_latched, _inn1_bowling_team_latched
nonlocal _inn1_completed_deterministic
```

**Step 2: Override `cold_start_inn2` (replace existing lines 5066–5067):**

Current:
```python
cold_start_inn2 = (
    cold_start_inn2_by_frame or cold_start_inn2_by_state)
```

P0-C replacement:
```python
cold_start_inn2 = (
    (cold_start_inn2_by_frame or cold_start_inn2_by_state)
    and not _inn1_completed_deterministic)
log.info(
    f"  [INNINGS-CHANGE] cold_start_inn2={cold_start_inn2} "
    f"(by_frame={cold_start_inn2_by_frame} "
    f"by_state={cold_start_inn2_by_state} "
    f"overridden_by_inn1_completed={_inn1_completed_deterministic})")
```

**Step 3: Use latched teams in the swap path (modify lines 5107–5112):**

Current:
```python
scoreboard.set_innings_2(derived_target)
team_locked = False
new_bat = bowling_team
new_bowl = batting_team
if new_bat and new_bowl:
    assign_teams(new_bat, new_bowl, innings=2)
    team_locked = True
```

P0-C replacement:
```python
scoreboard.set_innings_2(derived_target)
team_locked = False
# P0-C: prefer latched innings-1 teams (set at _inn_break_pending latch
# site) over the live closure variables, which POISON-RECAL events or
# strip reads during the innings break may have contaminated.
if _inn1_bowling_team_latched and _inn1_batting_team_latched:
    new_bat = _inn1_bowling_team_latched
    new_bowl = _inn1_batting_team_latched
    log.info(
        f"  [TEAM-ATTRIBUTION-CRICKET-RULES] "
        f"Using latched inn1 teams for swap: "
        f"new_bat={new_bat} new_bowl={new_bowl} "
        f"(latched_bat={_inn1_batting_team_latched} "
        f"latched_bowl={_inn1_bowling_team_latched}) "
        f"source={source}")
else:
    new_bat = bowling_team
    new_bowl = batting_team
    log.info(
        f"  [TEAM-ATTRIBUTION-STRIP-FALLBACK] "
        f"No latched inn1 teams — using closure vars: "
        f"new_bat={new_bat} new_bowl={new_bowl} "
        f"source={source}")
if new_bat and new_bowl:
    assign_teams(new_bat, new_bowl, innings=2)
    team_locked = True
else:
    log.warn(
        "  [INNINGS-CHANGE] Teams unknown at transition "
        "— leaving null; cold-start will re-derive from "
        "innings-2 broadcast.")
```

**Step 4: Also add `score_mgr.set_innings_2()` here (P0-A, for completeness):**

After `assign_teams(...)`:
```python
# P0-A: SM reset on all innings-change paths (Fix 16 coverage gap)
score_mgr.set_innings_2(
    target=derived_target,
    batting_team=new_bat,
    reason=source)
```

**Note:** The P0-A call must happen AFTER `assign_teams` (which sets `batting_team` closure var) and only in the non-cold-start path. The cold-start path already calls `scoreboard.set_innings_2()` which internally handles SM via the `_set_innings_2_logged` monkey-patch wrapper. Verify this interaction is not a double-reset before committing. The check at `score_manager.py:1733` (`if self.innings == 2: return`) makes the call idempotent.

---

### §6 — Cricket-rules data source

#### §6.1 Where innings-1 bowling team is stored

| Store | Location | Reliably set? | Available at execute_innings_change? |
|---|---|---|---|
| `bowling_team` closure var | `test_pipeline.py:4318`, `4635` | Yes — set by `assign_teams()`, protected by `team_locked` | Yes — accessed via nonlocal |
| `_inn1_bowling_team_latched` | New var; set at `test_pipeline.py:8263–8265` | Yes — set before innings break begins | Yes — via nonlocal (P0-C addition) |
| `scoreboard.bowling_team` | `eyes/scoreboard.py:189`, `715–720` | Yes — set by `setup_innings()` at team assignment time | Yes — via `scoreboard` reference |
| `SM.innings_history[-1]` | `score_manager.py:1750` | **No** — requires P0-A to fire first; pre-P0-A, history is empty | No — `SM.set_innings_2()` was never called in the MI/SRH failure |

**Recommended primary source:** `_inn1_bowling_team_latched` (the new latch variable). It is set at the deterministic innings-end moment, before any POISON-RECAL can affect the closure variables, and before the innings break carousel can confuse `assign_teams`.

**Fallback source:** `bowling_team` closure variable (unchanged by `team_locked` guard). Identical to `_inn1_bowling_team_latched` in the normal case; may differ only if a team-flip was somehow accepted after the latch point (should not happen while `team_locked = True`, but provides defense-in-depth via the `else:` branch in §5.4 Step 3).

#### §6.2 Field types and structures

```python
# All three consistent sources are: str | None
_inn1_bowling_team_latched: str | None   # e.g. "Sunrisers Hyderabad"
bowling_team: str | None                  # same canonical team name
scoreboard.bowling_team: str | None       # same canonical team name

# Accessor from execute_innings_change (no change needed):
new_bat = _inn1_bowling_team_latched or bowling_team
new_bowl = _inn1_batting_team_latched or batting_team
```

The canonical team name format is the full name string used as keys in `squads` dict (e.g. `"Mumbai Indians"`, `"Sunrisers Hyderabad"`). No normalization is needed — `assign_teams()` already handles lookup.

#### §6.3 When is it reliable?

`_inn1_bowling_team_latched` is reliable when ALL of the following hold:
1. `team_locked = True` was in effect during innings 1 (confirmed by `assign_teams` 3-frame lock)
2. `_inn_break_pending` first fired via `overs_complete_20` or `all_out_10` (not a cold-start)
3. The latch runs at line 8263 before any subsequent frames can modify `bowling_team`

Condition 3 is guaranteed by the placement of the latch code (inside the `if _det_innings_end and not _inn_break_pending:` block, which fires exactly once per match).

**If `_inn1_bowling_team_latched = None`** (latch never set — pipeline started in innings 2 or innings 1 ended via a non-deterministic path): the `else:` branch falls back to `bowling_team` closure variable, which is the pre-existing behavior. The `[TEAM-ATTRIBUTION-STRIP-FALLBACK]` tag will fire, providing diagnostic visibility.

---

### §7 — Test fixtures

All fixtures use the frame range F2660–F2900 from `logs/pipeline-2026-04-29-194416-mi-srh-live.log` as the reference scenario.

#### §7.1 Fixture A — FRAME_POISONED during innings break → cricket-rules swap (primary regression)

**What it tests:** The exact MI/SRH failure. P0-C must produce SRH batting after execute_innings_change even when SM state was wiped by POISON-RECAL.

**Setup:**
```python
# Scoreboard state simulating post-POISON-RECAL at transition frame F2695
scoreboard = Scoreboard()
scoreboard.batting_team = "Mumbai Indians"  # innings 1 batting
scoreboard.bowling_team = "Sunrisers Hyderabad"
scoreboard._inn = {"score": None, "wickets": None, "overs": None, "batting_team": "Mumbai Indians"}
scoreboard.current_innings = 1

batting_team = "Mumbai Indians"
bowling_team = "Sunrisers Hyderabad"
team_locked = True

_inn_break_pending = True
_inn_break_pending_source = "overs_complete_20"
_inn1_completed_deterministic = True
_inn1_batting_team_latched = "Mumbai Indians"
_inn1_bowling_team_latched = "Sunrisers Hyderabad"
frame_count = 2695
```

**Assertion targets:**
- `execute_innings_change("overs_complete_20")` returns `True`
- `scoreboard.current_innings == 2`
- `batting_team == "Sunrisers Hyderabad"` (cricket-rules swap)
- `bowling_team == "Mumbai Indians"`
- Log contains `[TEAM-ATTRIBUTION-CRICKET-RULES]`
- Log does NOT contain `cold-start path: relabelled` (cold_start override worked)

#### §7.2 Fixture B — Cricket-rules attribution produces correct team (positive case)

**What it tests:** The `_inn1_bowling_team_latched` mechanism correctly identifies the chasing team.

**Setup:** Same as Fixture A but with completed SM state:
```python
scoreboard._inn = {"score": 239, "wickets": 5, "overs": "20.0", ...}
```

**Assertion targets:** Same as Fixture A (both paths should produce SRH batting).

#### §7.3 Fixture C — Normal mid-innings play does not trigger cricket-rules (no-false-positive)

**What it tests:** P0-C does not fire during normal innings 1 play.

**Setup:**
```python
_inn_break_pending = False
_inn1_completed_deterministic = False
scoreboard.current_innings = 1
# Normal innings-1 state: overs=12.3, score=145, wickets=2
```

**Assertion targets:**
- `execute_innings_change("scorer_target_toss", target=200)` with a cold-start scenario
- `cold_start_inn2 = True` (normal cold-start path — no override)
- Log does NOT contain `[TEAM-ATTRIBUTION-CRICKET-RULES]`

#### §7.4 Fixture D — Latch not available (pipeline started mid-innings-2)

**What it tests:** Fallback to strip-based attribution when `_inn1_bowling_team_latched = None`.

**Setup:**
```python
_inn1_completed_deterministic = False
_inn1_batting_team_latched = None
_inn1_bowling_team_latched = None
bowling_team = "Sunrisers Hyderabad"  # set from strip during cold-start
```

**Assertion targets:**
- `execute_innings_change("to_win_N_off_M", target=244)` takes the else-branch
- Log contains `[TEAM-ATTRIBUTION-STRIP-FALLBACK]`
- Swap uses `bowling_team = "Sunrisers Hyderabad"` (fallback correct)

#### §7.5 Fixture E — Recovery post-cricket-rules swap (no regression to strip)

**What it tests:** After cricket-rules swap, normal innings-2 strip reads confirm SRH as batting and do not trigger a re-swap.

**Setup:** Run Fixture A; then simulate 5 subsequent frames with `extracted["visible_team"] = "Sunrisers Hyderabad"`.

**Assertion targets:**
- `assign_teams("Sunrisers Hyderabad", "Mumbai Indians", innings=2)` called after swap
- `team_locked = True`
- Subsequent strip reads with `visible_team = "Sunrisers Hyderabad"` increment `team_confirm_count` (no flip)
- `batting_team = "Sunrisers Hyderabad"` persists

---

### §8 — Telemetry

Two new log tags to emit:

#### §8.1 `[TEAM-ATTRIBUTION-CRICKET-RULES]`

Emitted when cricket-rules attribution path is taken in `execute_innings_change()`.

**Fields:**
```
[TEAM-ATTRIBUTION-CRICKET-RULES] 
  new_bat={new_bat}                    # innings-2 batting team (cricket rules)
  new_bowl={new_bowl}                  # innings-2 bowling team (cricket rules)
  latched_bat={_inn1_batting_team_latched}
  latched_bowl={_inn1_bowling_team_latched}
  source={source}                      # execute_innings_change source param
  cold_start_overridden=True           # confirms the override fired
  frame={frame_count}
```

#### §8.2 `[TEAM-ATTRIBUTION-STRIP-FALLBACK]`

Emitted when latch is unavailable and closure variables are used instead.

**Fields:**
```
[TEAM-ATTRIBUTION-STRIP-FALLBACK]
  new_bat={new_bat}                    # from bowling_team closure var
  new_bowl={new_bowl}                  # from batting_team closure var
  latch_unavailable=True               # confirms latched teams were None
  source={source}
  frame={frame_count}
```

#### §8.3 `[INN1-TEAM-LATCH]`

Emitted at the latch site when `_inn_break_pending = True` fires.

**Fields:**
```
[INN1-TEAM-LATCH]
  bat={_inn1_batting_team_latched}
  bowl={_inn1_bowling_team_latched}
  source={_src_tag}                    # overs_complete_20 or all_out_10
  frame={frame_count}
```

#### §8.4 `[TEAM-ATTRIBUTION-POISON-RATE]`

Emitted every `_POISON_RATE_WINDOW` frames when `_inn_break_pending = True`.

**Fields:**
```
[TEAM-ATTRIBUTION-POISON-RATE]
  rate={rate:.2f}                      # 0.0–1.0; 0.5+ = strip unreliable
  window={_POISON_RATE_WINDOW}
  poisoned_count={sum(_poisoned_in_window)}
  inn_break_pending={_inn_break_pending}
  frame={frame_count}
```

**Analyzer pattern to add to Bundle B/C:**
```python
"team_attribution_cricket_rules": re.compile(
    r"\[TEAM-ATTRIBUTION-CRICKET-RULES\]"),
"team_attribution_strip_fallback": re.compile(
    r"\[TEAM-ATTRIBUTION-STRIP-FALLBACK\]"),
"inn1_team_latch": re.compile(r"\[INN1-TEAM-LATCH\]"),
```

---

### §9 — Risk assessment

#### §9.1 What could go wrong with this design

| Risk | Scenario | Mitigant |
|---|---|---|
| **False latch** | `batting_team`/`bowling_team` set incorrectly during innings 1 (wrong team locked) | `team_locked` requires 3 consecutive strip confirmations before locking. If the lock was wrong, the latched values are wrong, and cricket-rules swap will produce the wrong teams — but this was ALSO wrong with the old code; P0-C does not make this worse. |
| **Latch fires before teams confirmed** | `overs_complete_20` fires with `team_locked = False` (team never locked in innings 1) | `_inn1_bowling_team_latched = None` (bowling_team is None). Falls back to `[TEAM-ATTRIBUTION-STRIP-FALLBACK]`. Existing log warning "Teams unknown at transition" fires as before. |
| **`_inn1_completed_deterministic` flip multiple times** | Multiple `overs_complete_20` fires (e.g., duplicate events) | Latch is inside `if not _inn_break_pending:` guard — fires exactly once per match. `_inn1_completed_deterministic` is a one-way flag (never reset). |
| **Post-P0-C cold-start path bypassed for legitimate cold-start** | Pipeline starts mid-innings-2, somehow `_inn1_completed_deterministic = True` from a prior session | This cannot happen: `_inn1_completed_deterministic` is initialized to `False` at the start of each `run()` invocation. Each pipeline start is a fresh Python process. |
| **assign_teams not called in non-cold-start path** | `new_bat` or `new_bowl` is None after latch | This is handled by the existing `else: log.warn("Teams unknown")` path. No new risk. |
| **cricket-rules swap wrong due to corrupt match metadata** | Very rare: innings-1 bowling team was itself attributed wrongly and locked to the wrong name | If `_inn1_bowling_team_latched` is wrong, cricket-rules swap produces wrong teams. Fallback: operator can restart pipeline, which re-enters cold-start mid-innings-2 detection. No silent corruption path — the `[TEAM-ATTRIBUTION-CRICKET-RULES]` tag makes the decision visible for post-match audit. |

#### §9.2 Edge cases requiring explicit handling

1. **All-out innings-1 end (`all_out_10`):** The latch fires for `_src_tag = "all_out_10"` as well. Same logic applies. No special case needed.

2. **`_inn_break_pending_source` is None when `execute_innings_change` fires:** This can happen if `execute_innings_change` is called from a path that does NOT go through the `_inn_break_pending` mechanism (e.g., `to_win_N_off_M` fast path at line 8781). In this case `_inn1_completed_deterministic = False`, the override is not applied, and the existing logic runs. Correct behavior.

3. **Back-to-back cold-start events (POISON-RECAL) during execute_innings_change:** After P0-C, `execute_innings_change` will proceed to the non-cold-start path. `scoreboard.set_innings_2(derived_target)` is called. If `scoreboard.current_innings >= 2` was somehow already true (e.g., from a POISON-RECAL that triggered `set_innings_2`), `execute_innings_change` returns `False` early (line 5022). This is the existing idempotency guard — not affected by P0-C.

4. **`derived_target = None`:** When `overs_complete_20` fires as the timeout trigger and `prev_score = 0` (POISON-RECAL wiped score), `derived_target = None`. `scoreboard.set_innings_2(None)` is called. Target will be `None` until Fix 9a/9b's `innings_1_total` latched value provides it. This is an existing behavior — not a P0-C regression.

5. **Scorer `innings_change=True` path (line 2920–2926):** This path DEFERS — it sets `changes.append("INNINGS CHANGE (deferred)")` and returns. Actual execution still goes through the `_inn_break_pending` mechanism at lines 8276–8306. Therefore P0-C's latch-based override applies here too, via the normal path.

#### §9.3 Failure mode if cricket-rules data is wrong

If `_inn1_bowling_team_latched` contains the wrong team name:

- `assign_teams(wrong_team, other_team, innings=2)` is called
- `team_locked = True` for wrong_team
- Strip reads showing correct chasing team will be **rejected** by the `[GUARD] Team flip rejected — locked` guard
- The pipeline will be stuck with the wrong batting team until a restart

This is the same failure mode as pre-P0-C wrong team attribution, just with a different wrong-attribution source. Mitigation: if `[TEAM-ATTRIBUTION-CRICKET-RULES]` fires with wrong teams visible in the post-match log, add a fallback that auto-unlocks if the chasing-squad check (lines 8218–8228) consistently rejects the locked team for N frames. This is a future hardening item, not required for the initial P0-C fix.

---

### §10 — Interaction with P0-A and P0-B

| P0 bug | Interaction with P0-C |
|---|---|
| **P0-A** (`score_mgr.set_innings_2()` call site) | P0-A and P0-C share `execute_innings_change()` as the fix location. P0-A adds `score_mgr.set_innings_2()` call. P0-C adds the cold-start override and cricket-rules swap. Both can ship in the same PR if the interaction is verified (§5.4 Step 4 note). |
| **P0-B** (overs tracker reset) | P0-B adds reset inside `reset_for_innings()` at `test_pipeline.py:5001`. `reset_for_innings(2)` is called at `test_pipeline.py:5120` inside `execute_innings_change()`. P0-B fires regardless of whether P0-C's cold-start override was applied (reset is unconditional). No interaction. |

**Execution order for Composer 2:** P0-A and P0-B are single call-site additions. Recommend shipping all three together in one PR to avoid a partial-fix state where SM reset is still missing. P0-C is the architecturally nuanced change; P0-A and P0-B are its mechanical companions.

---

### §11 — Composer 2 execution checklist

Before executing code changes against this design contract:

1. **Validate FRAME_POISONED rate in MI/SRH log F2347–F2694.** Run:
   ```bash
   grep -c "FRAME_POISONED" logs/pipeline-2026-04-29-194416-mi-srh-live.log | ...
   ```
   Compare against total frames in that window (~348 frames). If observed rate < 50%, update `_FRAME_POISONED_STRIP_TRUST_THRESHOLD` before shipping the telemetry constant.

2. **Confirm team-lock state at F2347.** Check log for last `[TEAM] Locked:` line before F2347 — must show `MI batting, SRH bowling` with correct canonical names.

3. **Confirm `scoreboard.bowling_team` class attribute exists** (`eyes/scoreboard.py:189`). Verify it is set by `setup_innings()` (line 715) and not cleared by `full_reset()` or `set_innings_2()`.

4. **Verify `_inn_break_pending_source` is already a nonlocal** in `execute_innings_change()` (line 5021). It is — no new nonlocal declaration needed for this variable.

5. **Verify `score_mgr.set_innings_2()` idempotency** when called from execute_innings_change: check `score_manager.py:1733` guard (`if self.innings == 2: return`). Confirm the call at line 6835 (Fix 16) and the new call in execute_innings_change don't double-reset.

6. **Run full `just test` after changes.** Path A WS-payload baseline must remain unchanged.

---

**Cross-references:**
- `mi_srh_innings_break_analysis.md` — §8 innings-2 monitoring strategy; §7 pending-validation
- `files/docs/backlog.md` — "Innings 2 transition failure" section (2026-04-29 22:05 IST entry)
- `full_reset_fow_extras_verification.md` — POISON-RECAL behavior reference
- `thread7_rediagnosis_multi_ball_gap.md` — FRAME_POISONED mechanism detail (H1/H2)
- `score_manager.py:1710–1770` — `set_innings_2()` and `innings_history` structure
- `test_pipeline.py:5016–5128` — `execute_innings_change()` full body
- `test_pipeline.py:8259–8306` — `_inn_break_pending` latch and fire sequence
- `test_pipeline.py:4608–4676` — `assign_teams()` and `team_locked` guard

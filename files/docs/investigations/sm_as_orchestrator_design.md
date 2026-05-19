# SM-as-Orchestrator + Secondary Text LLM — Design Memo

**Status:** Proposal. Pre-implementation.
**Date:** 2026-05-19
**Author:** J110
**Supersedes:** the corpus + adversarial mutator foundation work paused as of this memo.
**Related:** `files/docs/investigations/trace_and_detect_system_design.md` (trace schema), audit chat preceding this memo (5-primitive contract).

## 1. Problem

The current pipeline is *passive* relative to Scout: SM accepts whatever delta Scout reports per frame and back-fills missing structure via a pending-ball queue plus `?` placeholders that wait for `broadcast_this_over` to fill them in later. This produces three failure modes that are structural, not tunable:

1. **Multi-ball compression.** Camera-cut / overlay gaps cause Scout to skip from `(N.M)` to `(N.M+2)` in one frame. Today the queue enqueues `(Δruns, Δballs=2)` and defers; if Δruns is ambiguous (e.g., 6 = 4+2 vs 6+0 vs 2+4), the queue eventually force-flushes at the 40-frame deadline with the wrong attribution or with `?` placeholders that never resolve.
2. **Deferred attribution drift.** Pending balls live across over boundaries; archive is parked in `_over_archive_pending` (`score_manager.py:5048, 5296`), and bowler/striker locks acquired late can credit the wrong over.
3. **Broadcast wholesale-accept hazards.** `on_broadcast_override` (`this_over.py:797-920`) trusts `this_over_broadcast` to fill gaps but the broadcast strip itself is flaky during ribbon overlays; we have a `MAX_THIS_OVER_LEN=9` guard and a `_merge_broadcast` normalizer specifically to defend against this — the existence of those guards is the symptom.

Two architectural shifts close all three:

- **SM becomes active.** SM holds `expected_next_ball` and refuses frames that imply a skipped ball.
- **Synchronous gap resolution via secondary LLM.** When SM detects a gap, it invokes a cheap text-only LLM (Haiku or similar) with Scout's raw context to resolve ball N.M before the new frame's state is committed.

## 2. Architecture

```
Frame in → on_frame(FrameInput)
              │
              ├─ compute implied_ball from FrameInput.overs
              ├─ if implied_ball == expected_next_ball: accept (common case, no LLM call)
              ├─ if implied_ball < expected_next_ball: reject (regression — drift guard)
              └─ if implied_ball > expected_next_ball: GAP DETECTED
                     │
                     └─ _resolve_gap(prev_state, FrameInput, gap_size)
                            │
                            ├─ for each missing ball B in [expected_next_ball .. implied_ball-1]:
                            │     ├─ call secondary LLM with Scout context + B
                            │     ├─ receive {event_type, runs_off_bat, wicket, confidence}
                            │     ├─ if confidence >= τ: commit synthetic ball B, advance expected_next_ball
                            │     └─ else: emit BALL-UNRESOLVED, apply deterministic last-resort, advance
                            │
                            └─ now expected_next_ball == implied_ball: re-enter _accept_update with original frame
```

Everything synchronous. No queue, no deferred archive, no `?` placeholders.

## 3. `expected_next_ball` state machine

### 3.1 State

```python
@dataclass
class ExpectedBall:
    over: int           # 0-indexed within innings (0..max_over-1)
    ball: int           # 1-indexed within over (1..6, can go higher with extras)
    legal_ball_count: int  # for striker-rotation derivation
```

`expected_next_ball: ExpectedBall | None` on `ScoreManager`. `None` only before the first ball of any innings is committed.

### 3.2 Init / reset

| Event | Effect | Site |
|---|---|---|
| `__init__()` | `expected_next_ball = ExpectedBall(over=0, ball=1, legal_ball_count=0)` if known cold-start, else `None` | `score_manager.py:337-465` |
| First legal ball of innings observed | `expected_next_ball = ExpectedBall(0, 1, 0)` | new branch in `on_frame` |
| `set_innings_2()` | reset to `ExpectedBall(0, 1, 0)` | `score_manager.py:3546` |
| `_accept_update()` commits ball | advance: `legal_ball_count += 1`; if extras, `ball += 1` without `legal_ball_count++`; if end-of-over, `over += 1, ball = 1` | new method `_advance_expected()` |

### 3.3 Advance rules

```
on commit of ball (event_type, runs, is_legal):
    if is_legal:
        legal_ball_count += 1
        if (legal_ball_count % 6) == 0:
            over += 1
            ball = 1
        else:
            ball += 1
    else:
        ball += 1  # extras advance the ball-in-over counter but not legal count
```

Wicket commits **do not** reset `expected_next_ball` — the next ball is still expected, with a new striker. The "new batter to crease" delay is observable via Scout but doesn't change the ball-number expectation.

### 3.4 Gap detection

```python
implied = ExpectedBall.from_overs(frame.overs)  # 4.2 → over=4, ball=3, legal_ball_count=24+2
if implied == expected_next_ball:
    accept()
elif implied < expected_next_ball:
    reject("REGRESSION")  # SM-DRIFT-GUARD; existing pattern at score_manager.py:3669
elif gap := implied - expected_next_ball:
    _resolve_gap(gap)
```

Conversion `from_overs`: `overs=4.2` → `over=4, ball=3, legal_ball_count=4*6+2=26`. T20=6 legal balls per over; extras don't appear in `overs` so the conversion is unambiguous from the float.

## 4. Secondary LLM interface

### 4.1 Contract

**Inputs** (assembled by `_resolve_gap` per missing ball):

```json
{
  "expected_ball": {"over": 4, "ball": 3, "legal_ball_count": 26},
  "scout_context": {
    "visible_text": "<from Scout VLM>",
    "info_panel":   "<from Scout VLM>",
    "strip":        "<from Scout VLM>",
    "frame_type":   "SCOREBOARD",
    "camera_view":  "...",
    "frame_phase":  "..."
  },
  "match_state": {
    "innings": 2,
    "score_before": 47, "wickets_before": 1, "overs_before": 4.2,
    "score_after":  53, "wickets_after":  1, "overs_after":  4.4,
    "striker":   "Kohli",
    "non_striker":"Gill",
    "bowler":    "Bumrah"
  },
  "delta_observed": {
    "runs": 6,
    "wickets": 0,
    "balls": 2
  }
}
```

**Output**:

```json
{
  "event_type": "FOUR" | "SIX" | "ZERO" | "ONE" | "TWO" | "THREE" |
                "FIVE" | "WIDE" | "NO_BALL" | "BYE" | "LEG_BYE" |
                "WICKET" | "UNRESOLVED",
  "runs_off_bat": 0..6,
  "extras": {"type": "wd"|"nb"|"b"|"lb"|null, "runs": 0..6},
  "wicket": {
    "dismissed": "Kohli" | null,
    "type": "bowled" | "caught" | "lbw" | "runout" | "stumped" | null,
    "fielder": "..." | null
  } | null,
  "confidence": 0.0..1.0,
  "rationale": "<one sentence, for trace>"
}
```

### 4.2 Model & cost

**Stage 2b implementation (shipped):** Groq `llama-3.1-8b-instant` via the existing Groq client. Single-provider with Scout (`AsyncGroq` at `files/eyes/vision.py:450`); reuses `GROQ_API_KEY` env var. Sync `Groq()` client instantiated lazily inside the resolver to avoid async-context juggling in SM.

Model configurable via `GAP_RESOLVER_MODEL` env var (default `llama-3.1-8b-instant`). Escalation path: `llama-3.3-70b-versatile` if 8B eval accuracy is insufficient. Haiku 4.5 (`claude-haiku-4-5`) remains a fallback option if both Groq models fail accuracy gates.

Typical input ~600-800 tokens, output ~50 tokens. ~$0.0005/match at 8B vs ~3¢ at Haiku — 60× cheaper. Eval-corpus iteration is essentially free at 8B cost.

Cost telemetry: `GAP-RESOLVER-LLM-CALL` trace tag includes `model`, `input_tokens`, `output_tokens`, `latency_ms`. Enables A/B comparison of 8B vs 70B from production traces without trace-schema changes.

### 4.3 Confidence handling

- `confidence >= 0.7`: commit the LLM's resolution.
- `0.4 <= confidence < 0.7`: commit but emit `BALL-RESOLVED-LOW-CONFIDENCE` trace tag for review.
- `confidence < 0.4` **or** `event_type == "UNRESOLVED"`: fall through to deterministic heuristic (§4.4), emit `BALL-UNRESOLVED-LLM`.

### 4.4 Deterministic heuristic (last resort)

When the LLM can't resolve, distribute the multi-ball delta with these rules:

1. Place wickets (from `Δwickets`) on the last ball of the gap unless context (e.g., VISIBLE_TEXT contains "OUT" before a "FOUR") suggests otherwise.
2. Distribute `Δruns` across remaining balls: prefer one-boundary-plus-dots over even split (broadcast-strip behavior pattern from corpus analysis — boundaries are over-represented in gap frames because they coincide with replay cuts).
3. Tag every synthesized ball with `derivation_source = "heuristic"` and per-ball `confidence = 0.0`.

### 4.5 Cross-check guard

Before committing the LLM's resolution, sanity-check:

```
if claimed_event == "FOUR" and Δscore != 4: reject as BALL-UNRESOLVED-LLM-INCONSISTENT
if claimed_event == "WICKET" and Δwickets != 1: reject
if claimed_event in {ZERO, DOT} and runs_off_bat != 0: reject
```

This is what catches "secondary LLM returns wrong answer" (item 10 of the audit).

## 5. Frame fate ledger

(Originally framed as "Frame accounting queue" — a Scout response tracker. Stage 1 retrospective on the DC-vs-KKR Tier 1 corpus reframed the role: existing SM/SB rejection guards silently drop ~6.3% of frames (66 SM-level + 45 SB-level vs 5 surfaced gaps in the same corpus), an order of magnitude more than the visible commit-side gaps. The ledger's primary job is therefore tracking every frame's **fate across all rejection paths** — Scout-level, SM-level, SB-level — not just Scout response/timeout. Without that ledger, Mode 1 silent drops stay invisible.)

Every frame dispatched to Scout, AND every Scout response processed by SM, gets a tracked fate. SM's gap detection plus the secondary-LLM cost gate consult the ledger to distinguish among: (a) ball was skipped on a frame we accepted (commit-side gap, fires `[GAP-DETECTED]`), (b) ball happened during a frame whose Scout response was lost/late (`TIMEOUT`/`ERROR`), (c) ball happened during a frame whose response SM/SB rejected (`REJECTED_BY_*`), (d) frame was a normal between-balls observation (`ACCEPTED_NOOP`).

### 5.1 Schema

```python
@dataclass
class FrameLedgerEntry:
    frame_id: int
    dispatched_at: float                # wall time
    scout_response: dict | None
    scout_status: Literal["PENDING", "RESPONDED", "TIMEOUT",
                          "ERROR", "CORRUPT", "RETRY-EXHAUSTED"]
    sm_outcome: Literal["NOT_YET_SEEN", "ACCEPTED_COMMIT",
                        "ACCEPTED_NOOP", "REJECTED_COLD_EXIT",
                        "REJECTED_WARM_CONSENSUS",
                        "REJECTED_SB_JUMP_LIMIT",
                        "REJECTED_DISMISSED_GUARD",
                        "REJECTED_STRIP_ROW_MISMATCH",
                        "REJECTED_OTHER"]
    rejection_payload: dict | None      # proposed/current overs+score, delta_balls
    retry_count: int
    resolved_at: float | None
```

Two-dimensional fate: `scout_status` × `sm_outcome`. A frame can be `RESPONDED` + `REJECTED_WARM_CONSENSUS` (Scout came back fine; SM rejected the jump). A frame can be `TIMEOUT` + `NOT_YET_SEEN` (no response, SM never got to evaluate). All combinations are first-class.

### 5.2 Lifecycle

| Event | Effect on entry |
|---|---|
| Scout dispatch | Create entry; `scout_status=PENDING`, `sm_outcome=NOT_YET_SEEN`, `dispatched_at=now()` |
| Scout response (200, valid JSON) | `scout_status=RESPONDED`; store response; set `resolved_at` |
| Timeout (default 5s — `_SCOUT_TIMEOUT` at `files/eyes/vision.py:31`) | `scout_status=TIMEOUT`; if `retry_count < N`, re-dispatch with backoff |
| Non-recoverable error (5xx, network) | `scout_status=ERROR`; same retry policy |
| Response unparseable | `scout_status=CORRUPT`; same retry policy |
| Retry budget exhausted | `scout_status=RETRY-EXHAUSTED`; emit `FRAME-ACCOUNTING-UNRESOLVED` |
| SM commits the frame (`_accept_update` advances state) | `sm_outcome=ACCEPTED_COMMIT` |
| SM accepts but no state advance (between-balls observation) | `sm_outcome=ACCEPTED_NOOP` |
| SM cold-start-exit rejects (`OVERS-JUMP-IMPLAUSIBLE-REJECTED source=cold_start_exit_vs_last_warm`) | `sm_outcome=REJECTED_COLD_EXIT`; store `[GAP-AT-REJECTION]` payload (added in stage 2a) |
| SM warm-consensus rejects (`source=warm_consensus`) | `sm_outcome=REJECTED_WARM_CONSENSUS`; store `[GAP-AT-REJECTION]` payload |
| SB jump-limit rejects (`source=scoreboard_jump_limit`) | `sm_outcome=REJECTED_SB_JUMP_LIMIT`; store `[GAP-AT-REJECTION]` payload |
| Other SM rejects (dismissed-batter, strip-row mismatch) | `sm_outcome=REJECTED_*` with specific tag |

Capacity bounded; oldest entries beyond N (default ~200, ~10 min of frames) evicted with `FRAME-ACCOUNTING-EVICTED`.

### 5.2.1 Stage 2a foundation

The `[GAP-AT-REJECTION]` trace tag (shipped in stage 2a) is the ledger's down-payment: it surfaces SM-level + SB-level rejections with a uniform structured payload (`delta_balls`, `proposed_overs`, `current_overs`, `proposed_score`, `current_score`, `source`) without yet building the full ledger data structure. Three emission sites: `score_manager.py` cold-start-exit (`source=cold_start_exit_vs_last_warm`), `score_manager.py` warm-consensus (`source=warm_consensus`), `eyes/scoreboard.py` jump-limit (`source=scoreboard_jump_limit`). Future stages turn these emissions into ledger entries; until then they accumulate in trace records for post-hoc analysis.

### 5.3 Integration with existing retry infrastructure

Both existing retry paths fold into this queue, not the other way around:

- **Track 1 — in-call retry** (commit `5e4ff8a`, single retry on Groq 429 inside `Vision.describe`, `files/eyes/vision.py:512`). Today invisible to SM. After this change, both attempts are recorded so retry rate is observable.
- **Track 2 — `_ScoutRetryBuffer`** (`files/eyes/openscout_loop.py:74`; capacity 3, staleness 5s, max attempts 2; constants at `:60-62`; instantiated at `:262`). Becomes a *view over* the accounting queue (`status == "TIMEOUT" AND retry_count < N AND now - dispatched_at < staleness_s`), not a separate data structure. Existing tests at `files/tests/test_openscout_loop.py:346` port to queue-status assertions.

### 5.4 SM consultation pattern

When `on_frame` detects `implied_ball > expected_next_ball`, before invoking `_resolve_gap()`:

```python
gap_window = accounting.entries_between(
    expected_next_ball.legal_ball_count,
    implied_ball.legal_ball_count,
)
unresolved = [e for e in gap_window
              if e.status in {"TIMEOUT", "ERROR", "CORRUPT", "RETRY-EXHAUSTED"}]
if unresolved:
    trace.emit("GAP-EXPLAINED-BY-SCOUT-FAILURE",
               unresolved_count=len(unresolved),
               statuses=[e.status for e in unresolved])
```

Two benefits:

1. **Diagnosability.** Today a multi-ball gap is silent — the trace records the effect but not the cause. After this, gaps caused by Scout failures (3 consecutive timeouts around 4.2-4.4) are distinguishable from gaps caused by camera-cut compression (Scout returned cleanly but jumped 4.2 → 4.4 in one read).
2. **Secondary-LLM cost gate.** If the gap is fully explained by Scout failures, we have no source text to feed to the LLM — skip the LLM call and route directly to the deterministic heuristic with `derivation_source = "scout-blackout"`. Saves cost and avoids hallucinated LLM output on blank input.

### 5.5 Trace tags (added)

| Tag | When emitted |
|---|---|
| `FRAME-DISPATCHED` | Per dispatch (high volume; opt-in via verbose flag) |
| `FRAME-RESOLVED` | Per successful response, with latency_ms |
| `FRAME-ACCOUNTING-TIMEOUT` | On timeout, with retry_count |
| `FRAME-ACCOUNTING-UNRESOLVED` | On retry exhaustion |
| `FRAME-ACCOUNTING-EVICTED` | On capacity eviction |
| `GAP-EXPLAINED-BY-SCOUT-FAILURE` | SM consultation found unresolved entries in gap window |

### 5.6 Sequencing

- **Not blocking for orchestrator stage 1.** Stage 1 (additive `expected_next_ball`) doesn't depend on knowing *why* a gap exists.
- **Build alongside orchestrator stage 2 or stage 3.** Pure infrastructure with no derivation-logic dependency. Equally compatible with the 5-primitive contract's stage 2/3 (striker derivation, overs scalar guard) — the queue is upstream of both refactors.
- **Layer 1.5 unchanged.** Surfaces data; ledger comparison is unaffected.
- **Layer 2 needs an explicit test pattern.** Captured fixtures are by definition `RESPONDED`. A new fixture shape — `frame_id` with `status=TIMEOUT, scout_response=None` — is needed to exercise the consultation path. Add to `files/tests/fixtures/scout_blackout/`.

### 5.7 Open question

Should `_ScoutRetryBuffer` be deleted once this lands, or kept as the thin view described in §5.3? Recommend delete: queue subsumes it, one source of truth is easier to reason about.

## 6. Integration points

| Site | Change | File:line (today) |
|---|---|---|
| `ScoreManager.__init__` | add `self.expected_next_ball: ExpectedBall \| None = None` | `score_manager.py:337-465` |
| `set_innings_2` | reset `expected_next_ball = ExpectedBall(0, 1, 0)` | `:3546` |
| `on_frame` | insert gap-detection branch before warm-mode dispatch | `:1417, 1450, 1452` |
| new `_resolve_gap(gap_size, frame)` method | calls secondary LLM, synthesizes balls, advances state | new |
| new `_advance_expected(committed_event)` method | applies advance rules from §3.3 | new |
| `_accept_update` | append `_advance_expected(...)` after the three mutations | `:3655-3659` |
| new `secondary_llm.py` module | `class SecondaryResolver: def resolve(req) -> Response`; replay-aware via `TEST_SECONDARY_LLM_REPLAY` | new under `files/eyes/` |
| `trace_emitter.py` | add tags: `GAP-DETECTED`, `BALL-RESOLVED-LLM`, `BALL-RESOLVED-LOW-CONFIDENCE`, `BALL-UNRESOLVED-LLM`, `BALL-UNRESOLVED-HEURISTIC`, `BALL-UNRESOLVED-LLM-INCONSISTENT` | `:54-106` |

## 7. Mocking pattern for tests

Same env-gated replay as Scout:

```bash
TEST_SECONDARY_LLM_REPLAY=files/tests/fixtures/secondary_llm_<session>.jsonl
```

JSONL shape:

```json
{"frame_id": "...", "expected_ball": {...}, "response": {...}}
```

`SecondaryResolver.resolve()` keys on `frame_id + expected_ball.legal_ball_count`; falls back to live call if env var is unset and `--allow-live` flag passed. Layer 1.5 always uses replay (deterministic). Layer 2 uses replay by default; live-call mode is for capturing new fixtures only.

## 8. Harness implications

| Layer | Today | After refactor |
|---|---|---|
| Layer 1 (unit) | per-method tests, mostly unchanged | unchanged |
| Layer 1.5 (derivation ledger) | ledger ↔ SM committed-state parity | + `expected_next_ball` monotonicity assertion; + per-ball `derivation_source ∈ {scout, llm, heuristic}` tagged in ledger |
| Layer 2 (captured-replay) | Scout JSONL replay + WS assertion | + secondary-LLM JSONL replay; + ledger annotates which balls were LLM-resolved |
| Adversarial mutators (paused) | broadcast-strip mutations, ribbon overlays | new "ambiguous Scout text" category; new "secondary LLM lies" category — most prior mutator work *becomes unnecessary* because the surface mutated against (this_over_broadcast, broadcast_striker) is being deleted |
| New: secondary-LLM evaluation | n/a | offline corpus of "real gap → ground-truth ball" pairs, used to tune confidence threshold τ; lives at `files/tests/secondary_llm_eval/` |

## 9. Scar tissue obsolescence (revised from prior audit)

**Delete:**

- `PendingBall` dataclass and `_pending_ball_queue` (`score_manager.py:238-250, 405, 553-604, 669-710`)
- `_PENDING_BOWLER_BALL_CREDIT_MAX_LAG` constant + force-flush (`:77, 800, 5444`)
- `_over_archive_pending` deferred archive (`:5048, 5296`)
- `_pending_slots` dict + "?" placeholder logic (`this_over.py:85-91, 847-920, 1340-1360`)
- `on_broadcast_override` wholesale-accept (`this_over.py:797-920`)
- `_merge_broadcast` normalizer (`this_over.py:1134-1161`)
- `MAX_THIS_OVER_LEN=9` anti-ribbon guard (`this_over.py:1089-1115`)
- MULTI_BALL gap decomposition (`score_manager.py:2095-2125` and downstream)
- `MULTI-BALL-DERIVATION-EXPANDED` trace tag (`trace_emitter.py:64`, already deprecated)
- P1 striker-indicator matcher (`score_manager.py:4368, 4484`)
- `[SM-W8-DISMISSED-GUARD]` re-introduction suppression (`:3870`)
- `broadcast_this_over`, `broadcast_striker`, `broadcast_extra` fields from Scout output (`extract_regex.py:390-392, 317, 386-388`)

**Keep:**

- `_PENDING_WICKET_MAX_FRAME_LAG=40` (`:65, 5363`) — orthogonal to Scout schema; bowler-lock latency from tracker is independent of this refactor. Recent tuning commits (5638eb4, 5b25e59, 31dc8b9) stand.
- `broadcast_team`, `broadcast_target`, `broadcast_venue`, `broadcast_match_info` — cold-start metadata, not frame-by-frame; out of scope.
- `extras_type` (renamed from wholesale `broadcast_extra`) — promoted to sub-primitive per the 5-primitive contract audit; needed because wide/no-ball/bye is not derivable from deltas alone.

## 10. Risks and edge cases

1. **Secondary-LLM cost explosion.** If gap rate is higher than expected, cost grows linearly. Mitigation: rate-limit at 1 call per 3 frames; if exceeded, fall through to heuristic and tag `LLM-RATE-LIMITED`. Audit the rate weekly via trace analysis.
2. **Innings-1 to innings-2 transition.** The first frame of innings 2 looks like a massive regression (`expected_next_ball` was 19.6, frame says 0.1). `set_innings_2()` reset must precede gap detection; the transition is gated by `broadcast_target` change + `wickets→0` + `score→0` (existing detection at `score_manager.py:3335-3486`).
3. **Free-hit balls.** A free-hit can produce 6 runs without a legal ball counting. Sub-primitive `is_free_hit: bool` may need promotion, or the secondary LLM handles it via `extras` typing. Defer to a follow-up; not blocking.
4. **DRS reviews and TV-umpire pauses.** Scout pauses emitting STRIP for 10-30 seconds. No new balls during pause, no gap detection fires. Resume frame has same `overs` as pause-entry; common-case acceptance.
5. **Bowler-change-mid-over edge cases** (injury, mankad, suspended over): treat as normal; bowler-lock latency handled by the preserved `_PENDING_WICKET_MAX_FRAME_LAG` path. The 40-frame constant is tunable independently of this refactor.
6. **Heuristic-resolved balls in commentary.** A ball with `derivation_source=heuristic` and `confidence=0` should be flagged downstream; commentary should hedge ("appears to have been a boundary"). Out of scope for this memo but coordinate with commentary team before stage 4 ships.

7. **Rejection-source distribution varies across broadcasts (observed 2026-05-19).** DC-vs-KKR Tier 1 ~60/40 `warm_consensus` / `scoreboard_jump_limit`; GT-vs-RR 8a0c6c14 was 97/3. Dominant rejection source (`warm_consensus`) generalizes; broadcast-style variance affects only the SB hard-guard tail. SecondaryResolver consumes from `warm_consensus` regardless, so this doesn't change wiring — recorded for future telemetry comparison. **Δ=0 score-only rejections** (~13% of rejection events in GT-vs-RR) are filtered as a precondition in the resolver (`SecondaryResolver.resolve` returns `UNRESOLVED source=precondition` when `delta_observed.balls < 2`), never reach the LLM call site or eval corpus.

## 11. Phased rollout

Each stage gated by Layer 1.5 (ledger parity) and Layer 2 (captured replay) staying green. Each stage is its own commit.

| Stage | Scope | Gate |
|---|---|---|
| **1** | Add `expected_next_ball` state + `_advance_expected()` purely additive (track but don't gate). Trace `GAP-DETECTED` events from existing fixture corpus; quantify gap rate. | Layer 1.5 + Layer 2 green; new trace tag visible; **no behavior change yet** |
| **2** | Build `SecondaryResolver` + replay infra. Hand-author replay JSONL for the gap frames found in stage 1. Wire `_resolve_gap()` but keep behind feature flag `SM_ORCHESTRATOR=0`. Build frame-accounting queue (§5) in parallel; fold Track 1 + Track 2 retry paths into it. | Unit tests for resolver mock; offline eval against hand-labeled corpus; queue test pattern with `TIMEOUT` fixture |
| **3** | Flip `SM_ORCHESTRATOR=1` in test harness. Run full Layer 2 corpus; compare ledger parity vs the legacy pending-queue path. Tune confidence threshold τ. SM consults accounting queue (§5.4) to short-circuit LLM call on scout-blackout gaps. | Layer 2 must match or exceed legacy parity on all fixtures |
| **4** | Production cutover. Delete pending-queue, `?` placeholder, wholesale-accept paths, MULTI_BALL infrastructure listed in §8. | Layer 2 green; staged rollout via existing pipeline feature-flag pattern (see `USE_OPEN_SCOUT` precedent in `CLAUDE.md`) |
| **5** | Shrink Scout output to primitives only (per prior 5-primitive contract memo). Promote `extras_type` to sub-primitive. Shrink Layer 2 fixture corpus. Retire most adversarial mutators. | Layer 1.5 ledger parity must hold |

## 12. Open questions for review

1. **Confidence threshold τ.** Should this be a single global threshold or per-event-type (e.g., higher bar for WICKET than for DOT)? Recommend per-event; finalize in stage 3.
2. **Secondary LLM provider.** Haiku is the obvious default but Groq's `llama-3.1-8b-instant` is faster and likely sufficient for text-only structured output. A/B in stage 2.
3. **Free-hit support.** Phase-2 follow-up or baked into stage 4?
4. **Commentary hedging for heuristic balls.** Coordinate before stage 4 — needs a `derivation_source` field on the WS payload and a commentary-side branch.
5. **Live-call fallback policy.** When replay misses (new frame, no fixture), should Layer 2 fail-loud or silently fall through to live Haiku? Recommend fail-loud — forces fixture coverage discipline.

## 13. Out of scope

- Crossed-batters-on-catch detection (rare; tag `STRIKER-DERIVATION-AMBIGUOUS` and accept).
- Retired-hurt / retired-out (low frequency; existing logic suffices).
- Innings-2 super-over / DLS recalculation (separate subsystem).
- Player-style commentary data flow.

---

**Decision sought:** approval to proceed with stage 1 (additive `expected_next_ball` tracking + `GAP-DETECTED` trace tagging). Stages 2-5 contingent on stage 1 findings.

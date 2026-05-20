# SM-as-Orchestrator + Frame Fate Ledger — Design Memo

**Status:** Stage 1 + 2a + 2a' + 2c shipped. Stage 2b (Secondary LLM resolution) reverted 2026-05-19 — multi-ball gap resolution is the wrong abstraction; gaps are bugs to diagnose and fix at root cause, not classes the architecture must accommodate. Frame Fate Ledger (§4) shipped as `files/eyes/frame_ledger.py` with sm_outcome wiring at 5 sites (4 SM-side + 1 SB-side + 1 pipeline-side CORRECTION_BLOCKED). Dispatch-side scout_status wiring (PENDING/TIMEOUT/RESPONDED) deferred to a follow-up commit.
**Date:** 2026-05-19
**Author:** J110
**Supersedes:** the corpus + adversarial mutator foundation work paused as of this memo. Also supersedes the Secondary LLM design (former §4) and its eval-corpus / heuristic-fallback content.
**Related:** `files/docs/investigations/trace_and_detect_system_design.md` (trace schema), audit chat preceding this memo (5-primitive contract).

## 1. Problem

The current pipeline is *passive* relative to Scout: SM accepts whatever delta Scout reports per frame and back-fills missing structure via a pending-ball queue plus `?` placeholders that wait for `broadcast_this_over` to fill them in later. Three failure modes drove this proposal — all are now classified as **bugs to diagnose and fix at root cause**, not load-bearing conditions the architecture must accommodate:

1. **Multi-ball compression.** Camera-cut / overlay gaps cause Scout to skip from `(N.M)` to `(N.M+2)` in one frame. The Stage 1 retrospective showed every Δ≥2 commit decomposes into one of: (a) Scout cadence drop (rate-limit / latency / retry), (b) Scout response classified as non-SCOREBOARD (graphic / replay / overlay), (c) SCOREBOARD frame rejected by an SM/SB guard despite readable strip, (d) genuine OCR miss, (e) measurement artifact (no actual gap). Each category is a fix, not an accommodation.
2. **Deferred attribution drift.** Pending balls live across over boundaries; archive is parked in `_over_archive_pending` (`score_manager.py:5048, 5296`), and bowler/striker locks acquired late can credit the wrong over. Same treatment: fix the bowler-lock latency root cause, not the queue.
3. **Broadcast wholesale-accept hazards.** `on_broadcast_override` (`this_over.py:797-920`) trusts `this_over_broadcast` to fill gaps but the broadcast strip itself is flaky during ribbon overlays; the `MAX_THIS_OVER_LEN=9` guard and `_merge_broadcast` normalizer exist specifically to defend against this — the guards are the symptom. **Treatment:** ship the 5-primitive contract; derive `this_over` from per-frame deltas; delete the wholesale-accept path entirely.

The architectural shift:

- **SM becomes active.** SM holds `expected_next_ball` (shipped stage 1, `a57cdbd`) and emits diagnostic `[GAP-DETECTED]` whenever a Δ≥2 commit occurs. Stage 2a (`185bc39`) added `[GAP-AT-REJECTION]` at the three pre-`_accept_update` rejection sites. Stage 2a' (`ca85dd9`) closed the instrumentation hole at hot-resume + cold-exit. **All additive; no behavior change.**
- **Frame Fate Ledger** (§4) becomes the diagnostic surface that explains WHY each frame failed to commit. Every multi-ball-gap event is traced to its rejection class so root-cause fixes can target the dominant source.

A previously-proposed synchronous gap-resolution path (Secondary LLM via Groq llama-3.1-8b-instant) was implemented in stage 2b (`5fe6768`, `97671cc`) and evaluated against hand-labeled ground truth in `310bfe8`. **Both 8B and 70B failed the ≥80% case-level / ≥90% consistency gate** — root cause is data-bound, not prompt-bound: Scout's `THIS OVER` field is null at gap frames, so the LLM has start/end state but no per-ball sequence signal. Reverted 2026-05-19. The gaps shouldn't exist in the first place; resolving them after the fact is the wrong shape.

## 2. Architecture

```
Frame in → on_frame(FrameInput)
              │
              ├─ compute implied_ball from FrameInput.overs
              ├─ if implied_ball == expected_next_ball: accept (canonical path)
              ├─ if implied_ball < expected_next_ball: existing drift guards
              └─ if implied_ball > expected_next_ball: emit [GAP-DETECTED]
                     │
                     └─ (future) consult Frame Fate Ledger: emit
                        [GAP-EXPLAINED-BY-*] with the rejection class
                        (cold_exit / warm_consensus / scoreboard_jump_limit /
                        scout_failure / extractor_filter / etc.)
                     │
                     └─ accept the new state as before (instrumentation is
                        additive until root-cause fixes drive Δ≥2 to ~0)
```

No synchronous resolution. No deferred queue, no `?` placeholders, no secondary LLM, no deterministic heuristic. The architecture is to **diagnose** gaps (Stage 1 telemetry + Stage 2c ledger), **investigate** root causes per-class, and **fix** them at source until Δ≥2 rate falls to ~0. Any residual gap class that proves structurally unfixable (e.g., strip-not-visible during DRS pauses at <1% steady-state rate) is flagged explicitly and re-evaluated.

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
| `__init__()` | `expected_next_ball = None` initially; advances on first overs commit | `score_manager.py:337-465` |
| First legal ball of innings observed | Initialize from observed overs | `_track_overs_advance` |
| `set_innings_2()` | Reset via `self.__init__(shadow=self.shadow)` | `score_manager.py:3546` |
| `_accept_update()` commits ball | Advance `legal_ball_count` to match new committed overs | `_track_overs_advance` |
| `hot_resume_from_cache()` | Same advance call | stage 2a' wiring |
| `_accept_initial()` (cold-start exit) | Same advance call | stage 2a' wiring |

### 3.3 Advance rules

```
on each _accept_update / hot_resume / cold-exit commit of overs:
    prev_legal = legal_balls(prev_overs)
    new_legal  = legal_balls(new_overs)
    delta = new_legal - prev_legal
    if delta >= 2:
        log.info("[GAP-DETECTED] Δballs={delta} ...")  # diagnostic only
    if delta != 0:
        expected_next_ball.legal_ball_count = new_legal
        expected_next_ball.over = new_legal // 6
        expected_next_ball.ball = (new_legal % 6) + 1
```

Wicket commits **do not** reset `expected_next_ball` — the next ball is still expected, with a new striker. The "new batter to crease" delay is observable via Scout but doesn't change the ball-number expectation.

### 3.4 Gap detection (current, observation-only)

Today the state machine is purely additive: any Δ≥2 commit fires `[GAP-DETECTED]` (auto-promoted to `decisions[]`) and SM accepts the new state unchanged. The detection is a diagnostic surface, not a gate. Once root-cause fixes drive the Δ≥2 rate to ~0, the question of "should SM refuse Δ≥2 frames" can be revisited — but in the bug-fix framing, the goal is to never see them, not to handle them.

## 4. Frame fate ledger

(Originally framed as "Frame accounting queue" — a Scout response tracker. Stage 1 retrospective on the DC-vs-KKR Tier 1 corpus reframed the role: existing SM/SB rejection guards silently drop ~6.3% of frames (66 SM-level + 45 SB-level vs 5 surfaced gaps in the same corpus), an order of magnitude more than the visible commit-side gaps. The ledger's primary job is therefore tracking every frame's **fate across all rejection paths** — Scout-level, SM-level, SB-level — not just Scout response/timeout. Without that ledger, root-cause investigation can't attribute Δ≥2 gaps to their actual source.)

Every frame dispatched to Scout, AND every Scout response processed by SM, gets a tracked fate. Root-cause investigation queries the ledger to attribute each `[GAP-DETECTED]` to one of: (a) ball was skipped on a frame we accepted (commit-side gap — investigate extractor reject or measurement artifact), (b) ball happened during a frame whose Scout response was lost/late (`TIMEOUT`/`ERROR` — investigate Scout cadence/retry), (c) ball happened during a frame whose response SM/SB rejected (`REJECTED_BY_*` — investigate the guard threshold), (d) frame was normal between-balls observation (`ACCEPTED_NOOP`).

### 4.1 Schema

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

Two-dimensional fate: `scout_status` × `sm_outcome`. A frame can be `RESPONDED` + `REJECTED_WARM_CONSENSUS` (Scout came back fine; SM rejected the jump). A frame can be `TIMEOUT` + `NOT_YET_SEEN` (no response, SM never got to evaluate).

### 4.2 Lifecycle

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
| SM cold-start-exit rejects (`OVERS-JUMP-IMPLAUSIBLE-REJECTED source=cold_start_exit_vs_last_warm`) | `sm_outcome=REJECTED_COLD_EXIT`; store `[GAP-AT-REJECTION]` payload (shipped stage 2a) |
| SM warm-consensus rejects (`source=warm_consensus`) | `sm_outcome=REJECTED_WARM_CONSENSUS`; store `[GAP-AT-REJECTION]` payload |
| SB jump-limit rejects (`source=scoreboard_jump_limit`) | `sm_outcome=REJECTED_SB_JUMP_LIMIT`; store `[GAP-AT-REJECTION]` payload |
| Other SM rejects (dismissed-batter, strip-row mismatch) | `sm_outcome=REJECTED_*` with specific tag |

Capacity bounded; oldest entries beyond N (default ~200, ~10 min of frames) evicted with `FRAME-ACCOUNTING-EVICTED`.

### 4.3 Stage 2a foundation

The `[GAP-AT-REJECTION]` trace tag (shipped in stage 2a, `185bc39`) is the ledger's down-payment: surfaces SM-level + SB-level rejections with a uniform structured payload (`delta_balls`, `proposed_overs`, `current_overs`, `proposed_score`, `current_score`, `source`) without yet building the full ledger data structure. Three emission sites: `score_manager.py` cold-start-exit (`source=cold_start_exit_vs_last_warm`), `score_manager.py` warm-consensus (`source=warm_consensus`), `eyes/scoreboard.py` jump-limit (`source=scoreboard_jump_limit`). Stage 2c turns these emissions into ledger entries.

### 4.4 Integration with existing retry infrastructure

Both existing retry paths fold into the ledger, not the other way around:

- **Track 1 — in-call retry** (commit `5e4ff8a`, single retry on Groq 429 inside `Vision.describe`, `files/eyes/vision.py:512`). Today invisible to SM. After ledger lands, both attempts are recorded so retry rate is observable.
- **Track 2 — `_ScoutRetryBuffer`** (`files/eyes/openscout_loop.py:74`; capacity 3, staleness 5s, max attempts 2; constants at `:60-62`; instantiated at `:262`). Recommendation: delete after ledger lands — ledger subsumes the buffer's role; one source of truth. Existing tests at `files/tests/test_openscout_loop.py:346` port to ledger-status assertions.

### 4.5 Diagnostic consultation pattern

When `[GAP-DETECTED]` fires, the ledger is consulted to attribute the gap:

```python
gap_window = ledger.entries_between(
    expected_next_ball.legal_ball_count,
    implied_ball.legal_ball_count,
)
scout_failures = [e for e in gap_window
                  if e.scout_status in {"TIMEOUT", "ERROR",
                                        "CORRUPT", "RETRY-EXHAUSTED"}]
sm_rejections = [e for e in gap_window
                 if e.sm_outcome.startswith("REJECTED_")]
emit("GAP-EXPLAINED",
     scout_failure_count=len(scout_failures),
     sm_rejection_count=len(sm_rejections),
     rejection_classes=[e.sm_outcome for e in sm_rejections])
```

This is diagnostic-only — feeds the root-cause investigation. No resolution, no remediation at runtime.

### 4.6 Trace tags

| Tag | When emitted |
|---|---|
| `FRAME-DISPATCHED` | Per dispatch (high volume; opt-in via verbose flag) |
| `FRAME-RESOLVED` | Per successful response, with latency_ms |
| `FRAME-ACCOUNTING-TIMEOUT` | On timeout, with retry_count |
| `FRAME-ACCOUNTING-UNRESOLVED` | On retry exhaustion |
| `FRAME-ACCOUNTING-EVICTED` | On capacity eviction |
| `GAP-EXPLAINED` | Diagnostic consultation result |

## 5. Integration points

| Site | Change | File:line (today) |
|---|---|---|
| `ScoreManager.__init__` | `self._expected_next_ball: ExpectedBall \| None = None` (shipped) | `score_manager.py:415` area |
| `set_innings_2` | Auto-resets via `self.__init__()` (shipped) | `score_manager.py:3546` |
| `_accept_update` | Calls `_track_overs_advance` after overs mutation (shipped) | `score_manager.py:3686` area |
| `hot_resume_from_cache` | Same advance call (shipped stage 2a') | `score_manager.py:2455` area |
| `_accept_initial` | Same advance call (shipped stage 2a') | `score_manager.py:2535` area |
| Rejection sites (×3) | Emit `[GAP-AT-REJECTION]` (shipped stage 2a) | `score_manager.py:2376, 2863`; `eyes/scoreboard.py:1418` |
| **Stage 2c**: new `frame_ledger.py` module | `class FrameLedger` with dispatch/response/reject hooks | new under `files/eyes/` |
| **Stage 2c**: dispatch wrap | `Vision.describe` opens a ledger entry; response closes it | `files/eyes/vision.py:512` |
| **Stage 2c**: SM consultation | `[GAP-DETECTED]` triggers `ledger.explain_window(...)` | `score_manager.py:_track_overs_advance` |
| `trace_emitter.py` | Tags listed in §4.6 | `:54-106` |

## 6. Harness implications

| Layer | Today | After Stage 2c |
|---|---|---|
| Layer 1 (unit) | per-method tests | + `FrameLedger` unit tests |
| Layer 1.5 (derivation ledger) | ledger ↔ SM committed-state parity | unchanged; ledger consultation is observation-only |
| Layer 2 (captured-replay) | Scout JSONL replay + WS assertion | + ledger consistency assertion (every frame has an entry; no orphan rejections) |
| Adversarial mutators (paused) | broadcast-strip mutations, ribbon overlays | scope shrinks — many mutator targets (`this_over_broadcast`, `broadcast_striker`) deleted by the 5-primitive contract pass; remaining mutators focus on rejection-class triggers |

## 7. Scar tissue obsolescence (revised from prior audit)

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
- `_ScoutRetryBuffer` (`files/eyes/openscout_loop.py:74`) — subsumed by Frame Fate Ledger

**Keep:**

- `_PENDING_WICKET_MAX_FRAME_LAG=40` (`:65, 5363`) — orthogonal to Scout schema; bowler-lock latency from tracker is independent. Recent tuning commits (5638eb4, 5b25e59, 31dc8b9) stand.
- `broadcast_team`, `broadcast_target`, `broadcast_venue`, `broadcast_match_info` — cold-start metadata, not frame-by-frame; out of scope.
- `extras_type` (renamed from wholesale `broadcast_extra`) — promoted to sub-primitive per the 5-primitive contract audit; needed because wide/no-ball/bye is not derivable from deltas alone.

## 8. Risks and edge cases

1. **Innings-1 to innings-2 transition.** The first frame of innings 2 looks like a massive regression (`expected_next_ball` was 19.6, frame says 0.1). `set_innings_2()` reset must precede gap detection; existing detection at `score_manager.py:3335-3486` handles this.
2. **Free-hit balls.** A free-hit can produce 6 runs without a legal ball counting. Sub-primitive `is_free_hit: bool` may need promotion. Not blocking for diagnostic infrastructure; relevant for the eventual root-cause fixes.
3. **DRS reviews and TV-umpire pauses.** Scout pauses emitting STRIP for 10-30 seconds. No new balls during pause, no Δ≥2 at resume (same overs). Common-case acceptance.
4. **Bowler-change-mid-over edge cases** (injury, mankad, suspended over): bowler-lock latency handled by the preserved `_PENDING_WICKET_MAX_FRAME_LAG` path. Tunable independently.
5. **Rejection-source distribution varies across broadcasts (observed 2026-05-19).** DC-vs-KKR Tier 1 ~60/40 `warm_consensus` / `scoreboard_jump_limit`; GT-vs-RR 8a0c6c14 was 97/3. Dominant rejection source (`warm_consensus`) generalizes; broadcast-style variance affects only the SB hard-guard tail. Root-cause investigation should sample both broadcasts to avoid bias toward one rejection class.
6. **Structurally unfixable Δ≥2 residual.** If after root-cause fixes a small residual remains (e.g., DRS pause-resume frames where Scout legitimately couldn't read scoreboard for 10+ seconds), flag explicitly. Until proven unfixable, treat every Δ≥2 as a bug.

## 9. Phased rollout

| Stage | Scope | Status |
|---|---|---|
| **1** | `expected_next_ball` state + `[GAP-DETECTED]` trace tag (additive, no behavior change) | **shipped** `a57cdbd` |
| **2a** | `[GAP-AT-REJECTION]` tag at the three pre-`_accept_update` rejection sites | **shipped** `185bc39` |
| **2a'** | Route hot-resume + cold-exit commits through `_track_overs_advance` (close Stage 1 instrumentation hole) | **shipped** `ca85dd9` |
| **2b** | Secondary LLM resolution via Groq llama-3.1-8b-instant | **reverted** `5fe6768` / `97671cc` / `310bfe8` — failed eval gate (8B 33% / 70B 17% case-level vs 80% target). Root cause data-bound: Scout's `THIS OVER` null at gap frames. |
| **2c** | Frame Fate Ledger module + SM-side outcome wiring at 5 sites (`_accept_update` ACCEPTED_COMMIT, 2 OVERS-JUMP-IMPLAUSIBLE-REJECTED sites, SB jump-limit, pipeline CORRECTION_BLOCKED, team-change-pending). Audit hook shows 0 NOT_YET_SEEN across 9 fixtures = wiring complete. | **shipped** |
| **2d** | Dispatch-side scout_status wiring: `Vision.describe` records dispatch + response/timeout/error; `parse_strip` stamps extractor_outcome + scout_response_class (incl. DEGENERATE_NULL); SM `on_frame` lagged-by-one ACCEPTED_NOOP backfill. Audit refresh: 0 silent drops across 9 fixtures (3077/3077 frames have ledger entries). `_ScoutRetryBuffer` deletion deferred — orthogonal refactor, separate commit. | **shipped** |
| **3** | Steady-state Δ≥2 root-cause investigation: sample 20-30 events from the audit's 114, group by rejection class, propose per-class fix. | shipped (Stage 3 sample showed bimodal 52% scout_cadence_drop / 48% ocr_miss; Stage 3a sub-classification of ocr_miss showed 75% extractor/VLM-prompt fixable, of which the c-1 sub-class turned out to already be handled by current `parse_strip`) |
| **4** | Per-class root-cause fixes based on Ledger production data. Targets surface as ledger entries accumulate in real runs: `REJECTED_SCORE_CONSENSUS` → tune scorer correction threshold; `REJECTED_WARM_CONSENSUS` → tune `_OVERS_JUMP_CONSENSUS_FRAMES`; etc. | follows stage 2d + production-data collection |
| **5** | 5-primitive contract cutover. Delete pending-queue, `?` placeholder, wholesale-accept paths, MULTI_BALL infrastructure listed in §7. | follows stage 4 |

## 10. Open questions for review

1. **Structurally unfixable residual policy.** If a Δ≥2 class proves unfixable (e.g., DRS pauses), what's the SLA? Tag-and-accept, or fail-loud?
2. **Ledger persistence.** Per-session in-memory only, or written alongside trace records for post-hoc analysis? Recommend in-memory + dump-on-session-end for trace correlation.
3. **Root-cause investigation sample size.** 20-30 events is the minimum signal; more if any one class dominates. Should we also sample DC-vs-KKR rejection events (~111) since they're 3× the volume of GT-vs-RR rejection events (~38)?

## 11. Out of scope

- Crossed-batters-on-catch detection (rare; tag `STRIKER-DERIVATION-AMBIGUOUS` and accept).
- Retired-hurt / retired-out (low frequency; existing logic suffices).
- Innings-2 super-over / DLS recalculation (separate subsystem).
- Player-style commentary data flow.
- Synchronous gap resolution (deleted — see Stage 2b revert).

---

**Decision sought:** approval to proceed with stage 2c (Frame Fate Ledger build) and concurrent stage 3 (root-cause investigation of the audit's 114 steady-state Δ≥2 events).

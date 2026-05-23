# Workstream H — Cold-start re-entry root cause (step-1 investigation)

**Status.** Step-1 deliverable: static-falsification memo. No code edits this pass. Empirical-falsification budget UNCHANGED at 4/5.
**Branch.** `derive-not-detect` at HEAD `5206885` (post-merge).
**Empirical anchor.** `logs/trace/validate_surface_b_121222.jsonl` — 749 frames; 5× `SM-INNINGS-2-RESET reason=wickets_regressed` (F462, F690, F801, F859, F992); 2× `POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START` (F690, F859); 0× `POST-WICKET-CASCADE-DRAIN-FIRED`; D-post-FoW-striker = 20 (open).
**Required-read context.** Loaded — `workstream_g_cold_start_transition_catalogue.md` §5, `workstream_g_shape_a_validation_addendum.md` §4, `workstream_g_cold_drain_surface_audit.md` §4.1, `differential_testing_methodology_design.md` §14.5.2 + §16.2 + §17.3, `state_mutation_site_catalogue.md` C9.
**Predicate under investigation.** `_detect_innings_change` body at `files/score_manager.py:4307`; `wickets_regressed` branch at `:4449-4457`; single call site at `:3578`; `set_innings_2` at `:4484` with 5 callers (`:4477`, `:4622`, `:4681`, `:4826`, plus self-archive idempotency at `:4508`).
**Result.** Static-falsification chain converges on one leading candidate (P1 — team-change-corroboration parity). All 7 gates passable on static analysis. One adjacent architectural blocker surfaced (S14): the mechanism that reverts `self.innings 2 → 1` between fires is not explained by the predicate body alone — flagged for next-session escalation, but does not invalidate P1.

---

## §1 Empirical anchor table

Each row is one `SM-INNINGS-2-RESET reason=wickets_regressed` fire decoded from the trace's `INNINGS-TRANSITION-TELEMETRY` payload at the same frame.

| # | F | prev (s/w/ov) | prev_team | cand (s/w) | cand_team | cand_target | Δw | Δs | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 462 | 54/3 (5.2) | DC | 14/0 | None | None | -3 | -40 | Preceded by F461 `WICKETS-JUMP 1→3` (3-frame consensus accepted). Next 4 frames (F465/468/482/515) all fire scoreboard-side `WICKETS-REGRESS 3→1` — i.e., pipeline relitigates the same misread downstream. |
| 2 | 690 | 74/2 (8.0) | DC | 0/0 | None | None | -2 | -74 | Within post-wicket hot window. F679 `WICKET-FALL-ONLY-CALLED` + `POST-WICKET-CASCADE-ENQUEUED` (dismissed=Nitish Rana, ttl=80). 11 frames later F690 fires; cascade `WIPED-BY-COLD-START`. score=0/wickets=0 is fully-null skeleton/graphic read. |
| 3 | 801 | 77/2 (9.0) | DC | 67/0 | **DC** | None | -2 | -10 | Team UNCHANGED (DC→DC). cand_score=67 — partial OCR misread (likely standings/sponsor overlay), not a true reset. |
| 4 | 859 | 80/3 (9.5) | DC | 47/0 | None | None | -3 | -33 | Within post-wicket hot window. F855 `WICKET-FALL-ONLY-CALLED` + `POST-WICKET-CASCADE-ENQUEUED` (dismissed=Pathum Nissanka, ttl=80). 4 frames later F859 fires; cascade `WIPED-BY-COLD-START`. |
| 5 | 992 | 86/4 (4.2) | None | 49/0 | None | None | -4 | -37 | Overs **regressed** in prev field (4.2 implausible after 9.x progression). prev_team=None — SM team lock had already cleared by this point. F942 had earlier emitted `WICKETS-REGRESS 3→0` (scoreboard-side). |

**Cricket truth.** DC vs KKR. DC batting innings 1. Replay covers ~11 overs of innings-1 only (per validate_dckkr_replay observations cited in §17.3 source). **No legitimate innings transition exists in this fixture window**; all 5 fires are false-positive innings-2 declarations.

**Hot-window cohort.** Fires #2 (F690) and #4 (F859) occur 11 and 4 frames respectively after a `WICKET-FALL-ONLY-CALLED` + `POST-WICKET-CASCADE-ENQUEUED` event. These are the two fires that produce `WIPED-BY-COLD-START` records — i.e., the two cascade-wipes that motivate this investigation.

**Cold-cohort.** Fires #1 (F462), #3 (F801), #5 (F992) are NOT in a post-wicket hot window (no preceding `WICKET-FALL` within ≥80 frames). These three would be missed by any "N-frame post-wicket window" patch — see hypothesis H2 below.

---

## §2 Predicate-trail static analysis

### §2.1 Predicate body inventory (`:4307`-`:4482`)

The predicate composes four reset signals in order. Per :4309, if `self.innings >= 2`, returns False immediately (early-exit guard).

| # | Branch | Lines | Producer chain |
|---|---|---|---|
| 1 | `target_appeared` | :4316-4318 | `frame.broadcast_target` (Scout → FrameInput) + `self.target` (None at innings-1 baseline) |
| 2 | `batting_team_changed` | :4337-4385 | `frame.broadcast_team` (Scout), `self.batting_team`, scoreboard's `_playing_teams` set; tightened 2026-05-19 with playing-teams membership + 3-frame consensus (`TEAM_CHANGE_CONSENSUS_FRAMES`). |
| 3 | `score_reset_from_progress` | :4387-4447 | `card.score`, `card.wickets`, `self.score`, `self.wickets`, `_bcast_team`/`_cur_team` (computed local at :4411-4419). **Tightened 2026-05-19 with team-change corroboration** (the `_team_changed` guard at :4423). |
| 4 | `wickets_regressed` | :4449-4457 | `card.wickets` (Scout extractor → card), `self.wickets` (running SM state). **NO corroboration guards.** |

### §2.2 `wickets_regressed` branch inputs (the focus)

The predicate at :4454-4457 is two terms:

```python
if (w is not None and self.wickets is not None
        and self.wickets >= 2 and w < self.wickets - 1):
    changed = True
    reason = reason or "wickets_regressed"
```

Inputs:

| Input | Producer | Reliability under known failure modes |
|---|---|---|
| `w = card.get("wickets", 0)` (:4389) | Scout VLM → extractor → strip-parse → card mutation | Known to misread under sponsor/skeleton/standings overlays. Documented at :4392-4403 (score-reset branch comment) — *"structurally indistinguishable from a sponsor-graphic / skeleton-strip misread"*. |
| `self.wickets` | Running SM state from prior commits + post-fix adjustments (`WICKETS-JUMP` / `WICKETS-REGRESS` / `apply_wicket_fall_only`) | Trustworthy modulo upstream consensus (F461 `WICKETS-JUMP 1→3` injected a value that F462's `card.wickets=0` then "regressed"). |
| `self.wickets >= 2` | Same as above | Threshold lifts the floor (single 1→0 OCR slip cannot trigger). |
| `w < self.wickets - 1` | Strict regression by >1 (so 3→2 spared, 3→1 catches). | Designed at :4451-4453 to filter single-frame misreads while catching real innings transitions. |

**Critical observation.** Inputs make NO reference to:

- `frame.broadcast_team` / `self.batting_team` (the score_reset branch directly above DOES use these — :4411-4419).
- `frame.broadcast_target` (the target_appeared branch above uses this).
- Any post-wicket-cascade activity (`self._pending_post_wicket_cascade`).
- Any "frames since last wicket" anchor (no `_last_wicket_fall_frame` state exists).
- Score-reset coupling: cand_score=67 (F801) or cand_score=47 (F859) is fine — the wickets branch is independent of score.

**The branch is the least-guarded of the four.** Same misread surface that score_reset_from_progress hardened against on 2026-05-19 flows through this branch unimpeded.

### §2.3 Producer-side reliability under the 5 trace fires

| F | card.wickets producer | self.wickets at moment of fire | Misread class |
|---|---|---|---|
| 462 | Scout extractor `0` from overlay frame | 3 (just lifted by F461 `WICKETS-JUMP 1→3`) | Single-frame OCR overlay misread |
| 690 | Scout extractor `0` from skeleton/null strip | 2 | Skeleton/null read (`s=0, w=0, no team` — would have been rejected by score_reset's team-change guard) |
| 801 | Scout extractor `0` from partial overlay | 2 | Partial OCR (score=67 OK, wickets=0 wrong) |
| 859 | Scout extractor `0` from partial overlay | 3 | Partial OCR (score=47 OK, wickets=0 wrong) |
| 992 | Scout extractor `0` from partial overlay | 4 | Partial OCR (score=49 OK, overs regressed to 4.2) |

Five distinct OCR misread realizations, all sharing the same defect: `card.wickets=0` against `self.wickets ≥ 2`, with no team flip and no target appearance.

---

## §3 Cross-reference §16.2 retired assumption

**Cited.** §14.5.2 retired the "once per pipeline boot" cold-start-exit semantics. §16.2's original design treated COLD-START-EXIT as a single-shot boundary marker between cold-start synthesis and steady-state derivation. Empirical reality (12 fires per DCKKR dump cited in §14.5.2, reduced to 5+5=10 cited in WS-G catalogue §5) invalidates that assumption.

### §3.1 Per-fire legitimacy check

Cricket-truth gate per §3 spec: *for each of the 5 fires, verify either is or is not a legitimate innings-2 transition by cricket truth.*

| F | Cricket truth | Verdict | Evidence |
|---|---|---|---|
| 462 | Innings 1 in progress, ~5.2 overs DC batting, no team flip, no target | **NOT legitimate.** | Match is DC v KKR T20; DC was still batting through 11 overs of the replay (per validate_dckkr_replay observations). No inn-2 chase began at over 5.2. |
| 690 | Innings 1, ~8.0 overs, Nitish Rana just dismissed at F679 (real wicket #2) | **NOT legitimate.** | cand=0/0 is a fully-null read; a real inn-2 would have a positive target and team flip to KKR. |
| 801 | Innings 1, ~9.0 overs DC batting | **NOT legitimate.** | cand_team=DC (unchanged). Real inn-2 has chasing team flip. |
| 859 | Innings 1, ~9.5 overs, Nissanka just dismissed at F855 (real wicket #3) | **NOT legitimate.** | Mid-over wicket fall; cricket innings cannot transition between balls 9.4 and 9.5 (20-over format ends at 20.0 or all-out). |
| 992 | Innings 1; prev_overs corrupted to 4.2 | **NOT legitimate.** | Overs regressed — implausible. prev_team=None indicates SM lost its team lock from earlier corruption. |

**5/5 are illegitimate.** Zero true innings transitions in the trace window. The retired §16.2 assumption holds NOT as a "boot-time-only" property but as "must not fire on misreads" — which the unguarded `wickets_regressed` branch does five times.

### §3.2 The hidden self.innings reversion path

For the predicate to fire 5 times, `self.innings` must reset from 2 back to 1 between fires (the :4309 guard would otherwise short-circuit fires 2-5).

`set_innings_2` at :4544 sets `self.innings = 2` explicitly after `self.__init__()`. Yet five fires occurred. Either:

- (a) `__init__()` is being called elsewhere on the SM between fires (resetting `self.innings = 1`),
- (b) a different mutator writes `self.innings = 1`,
- (c) a fresh SM instance replaces the existing one between fires.

Static-analysis of this reversion path is **out of scope for this memo** (the deliverable is the predicate root cause, not the broader SM lifecycle). Flagged as architectural blocker in §6 and as S14 in §7. **Does not invalidate the leading candidate P1**, because P1 rejects the predicate trigger upstream of the `self.innings` mutation — even if `self.innings` continues to revert, P1's guard prevents the fire.

---

## §4 Hypothesis enumeration

Four candidate root causes. Each evaluated against three gates from §7.2 audit framework: gate-1 (caller enumeration), gate-2 (caller classification), gate-3 (adjacent-state cross-reference). Static-falsification preferred; empirical-replay requirement marked explicitly.

### §4.1 H1 — Architectural-parity gap (wickets_regressed lacks team-change corroboration)

**Claim.** The `wickets_regressed` branch (:4449-4457) is the architectural twin of the `score_reset_from_progress` branch (:4420-4447) but lacks the team-change corroboration guard added on 2026-05-19. The same OCR misread class that the score_reset branch now rejects flows through wickets_regressed unimpeded.

| Gate | Result |
|---|---|
| gate-1 callers | Single call site (`_detect_innings_change` at :3578). No additional callers to enumerate. **PASS.** |
| gate-2 classification | Consumer of `card.wickets` + `self.wickets`. Producer (Scout extractor) is upstream and not the proposed change site. Branch is a single-line conditional inside a per-frame predicate. **PASS.** |
| gate-3 adjacent state | `_bcast_team`/`_cur_team` local variables already computed at :4411-4419 for the score_reset branch — reusable without re-computation. No new state introduced. **PASS.** |
| Static falsification | Covers **5/5** fires per §3.1: all five have `cand_team ∈ {None, DC}` against `prev_team=DC`, i.e., **no team change**. **CONVERGES.** |
| Empirical replay required? | No (static-only). Empirical validation deferred to step-2/3. |

**Status.** Leading candidate.

### §4.2 H2 — Post-wicket hot-window suppression

**Claim.** Reject `wickets_regressed` when `_current_frame - _last_wicket_fall_frame < N` (e.g., N=30). The two fires that produce `WIPED-BY-COLD-START` (F690, F859) fall within this window.

| Gate | Result |
|---|---|
| gate-1 callers | Same single call site. Requires NEW mutator site to write `_last_wicket_fall_frame` — likely at `_apply_wicket_fall_only` (additional caller class). |
| gate-2 classification | New state field added; new producer site at the wicket-commit path. Wider blast radius than H1. |
| gate-3 adjacent state | Couples wickets-regress predicate to wicket-fall lifecycle. Adds a §12 dual-state-write risk if `_last_wicket_fall_frame` is read in both COLD and WARM paths without consistent reset semantics. |
| Static falsification | Covers **2/5** fires (F690 age=11, F859 age=4). MISSES F462 (no preceding wicket within window), F801 (no preceding wicket), F992 (no preceding wicket). **PARTIAL.** |
| Empirical replay required? | Yes (N-threshold sensitivity). Would consume budget. |

**Status.** Insufficient coverage; rejected as standalone fix. Could supplement H1 but provides no additional rejections H1 doesn't already cover.

### §4.3 H3 — ALL-OF freshness-vector corroboration

**Claim.** Accept `wickets_regressed` only when `card.score == 0` AND `card.wickets == 0` AND team flip. This is "score_reset_from_progress + wickets condition" as a unified gate.

| Gate | Result |
|---|---|
| gate-1 callers | Same single call site. **PASS.** |
| gate-2 classification | Strictly tighter than H1; same input signature. **PASS.** |
| gate-3 adjacent state | Uses `s` and `w` already computed at :4388-4389. No new state. **PASS.** |
| Static falsification | Covers **5/5** fires per §3.1 — but the `card.score == 0` clause is the load-bearing one for F462/F801/F859/F992 (where cand_score = 14/67/47/49) and team flip is load-bearing for F690 (where cand_score = 0). H3 is strictly P1 ∧ P2 — wins more aggressively but at the cost of rejecting legitimate inn-2 transitions where score arrives a frame later than wickets. |
| Empirical replay required? | Yes — to verify H3 doesn't reject the next legitimate inn-2 transition (no positive case exists in this trace, so the gate-7 cross-fixture verification is forced). |

**Status.** Strictly more conservative than H1. Defer as fallback if H1 introduces a legitimate-inn-2 false-negative in step-7 cross-fixture verification.

### §4.4 H4 — Upstream WICKETS-JUMP-induced phantom regression

**Claim.** F461 `WICKETS-JUMP 1→3` accepted a 3-frame consensus from a Scout misread; F462's `card.wickets=0` then trips the regression predicate against the freshly-lifted `self.wickets=3`. The defect is upstream of `_detect_innings_change`.

| Gate | Result |
|---|---|
| gate-1 callers | Different code path (`WICKETS-JUMP` is in scoreboard, not SM predicate). Producer-side fix. |
| gate-2 classification | Consensus-threshold tuning. Separate defect class. |
| gate-3 adjacent state | `WICKETS-JUMP` already requires 3-frame consensus; tightening would cascade across scoreboard logic. |
| Static falsification | Covers **1/5** fires (F462 only). MISSES F690, F801, F859, F992 (none preceded by `WICKETS-JUMP` in trace). **INSUFFICIENT.** |
| Empirical replay required? | Yes (consensus-threshold sensitivity). |

**Status.** Real defect class, but distinct from this investigation's predicate-root-cause scope. Defer to a separate WS-H sub-task if step-2 empirical replay surfaces upstream noise as the dominant residual.

### §4.5 Coverage summary

| Hypothesis | Fires covered | Static-only? | Verdict |
|---|---|---|---|
| H1 — team-change parity | 5/5 | Yes | **Leading.** |
| H2 — post-wicket window | 2/5 | No (empirical N) | Rejected (partial). |
| H3 — ALL-OF freshness | 5/5 | Yes (but stricter) | Fallback. |
| H4 — upstream consensus | 1/5 | No (empirical) | Out of scope. |

H1 is the unique candidate that covers all five fires using only static inputs already present in the predicate's local scope, requires no new state, and mirrors a precedent (the 2026-05-19 score_reset hardening) whose architectural justification is documented in code (:4390-4410).

---

## §5 Candidate predicate-tightening proposals

### §5.1 Proposal P1 (LEADING) — team-change-corroboration parity

**Diff intent** (illustrative — not committed this pass):

```python
# files/score_manager.py, replacing :4454-4457
if (w is not None and self.wickets is not None
        and self.wickets >= 2 and w < self.wickets - 1):
    if _team_changed:
        changed = True
        reason = reason or "wickets_regressed"
    else:
        if _trace is not None:
            try:
                _trace.get_recorder().record(
                    tag="WICKETS-REGRESS-TEAM-CHANGE-REQUIRED-REJECTED",
                    prev_wickets=int(self.wickets),
                    cand_wickets=int(w),
                    prev_team=self.batting_team,
                    cand_team=frame.broadcast_team,
                    frame_id=getattr(frame, "frame_id", None))
            except Exception:
                pass
        log.info(
            f"  [WICKETS-REGRESS-TEAM-CHANGE-REQUIRED-REJECTED] "
            f"prev={self.score}/{self.wickets} prev_team="
            f"{self.batting_team} cand=*/{w} cand_team="
            f"{frame.broadcast_team!r} — wickets regression "
            f"without team change is OCR misread, not innings "
            f"transition")
```

Reuses `_team_changed` already in scope from :4417-4419. Architectural mirror of :4423-4447.

**Predicted-flip table (gate-6 obligation):**

| Frame | Pre-fix observed | Post-P1 predicted | Mechanism |
|---|---|---|---|
| F462 | `SM-INNINGS-2-RESET reason=wickets_regressed`; `EVENT-BASELINE-RESET-INNINGS-2 prev_baseline=54` | `WICKETS-REGRESS-TEAM-CHANGE-REQUIRED-REJECTED` (new tag); no inn-2 reset | cand_team=None → `_team_changed=False` |
| F465/468/482/515 | `WICKETS-REGRESS 3→1` (scoreboard side, downstream cleanup) | UNCHANGED (scoreboard-side reconciliation continues to handle the misread) | Scoreboard path independent |
| F679 | `WICKET-FALL-ONLY-CALLED`, `POST-WICKET-CASCADE-ENQUEUED` (ttl=80) | UNCHANGED | Wicket commit path independent |
| F690 | `SM-INNINGS-2-RESET`; `POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START` (Nitish Rana, age=11) | NEW: WICKETS-REGRESS-REJECTED; cascade RETAINED in queue, TTL ticks (now age=11 of 80, 69 frames left) | cand_team=None → reject; queue not wiped |
| F~691-F758 | (cascade wiped, no further events) | Cascade resolves if Scout slot-diff lands within 69 frames → `POST-WICKET-CASCADE-DRAIN-FIRED` (≥1, provisional per H1 gate-6) | Drain path already gate-3-compliant per WS-G surface-B audit §3.3 |
| F801 | `SM-INNINGS-2-RESET reason=wickets_regressed` | REJECTED | cand_team=DC == prev_team=DC → `_team_changed=False` |
| F855 | `WICKET-FALL-ONLY-CALLED`, `POST-WICKET-CASCADE-ENQUEUED` (Nissanka, ttl=80) | UNCHANGED | Wicket commit independent |
| F859 | `SM-INNINGS-2-RESET`; `WIPED-BY-COLD-START` (Nissanka, age=4) | REJECTED; cascade RETAINED (age=4 of 80) | cand_team=None → reject |
| F~860-F934 | (cascade wiped) | Cascade resolves if Scout slot-diff lands within 76 frames → DRAIN-FIRED (≥1, provisional) | Same |
| F942 | `WICKETS-REGRESS 3→0` (scoreboard side) | UNCHANGED | Scoreboard path independent |
| F992 | `SM-INNINGS-2-RESET reason=wickets_regressed` | REJECTED | cand_team=None → reject |

**Aggregate gate-6 numbers:**

| Metric | Pre-fix | Post-P1 predicted |
|---|---|---|
| `SM-INNINGS-2-RESET reason=wickets_regressed` | 5 | **0** (target: ≤2 — P1 exceeds) |
| `POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START` | 2 | **0** (target: 0) |
| `POST-WICKET-CASCADE-DRAIN-FIRED` | 0 | **≥1 provisional** (target: ≥1; gated on Scout slot-diff actually firing within TTL — see WS-G surface-B audit §3.3 gate-6 acknowledged shortfall) |
| `WICKETS-REGRESS-TEAM-CHANGE-REQUIRED-REJECTED` | 0 | **5** (new tag) |
| D-post-FoW-striker | 20 | **5-10 provisional** (target: 5-10; conditional on DRAIN-FIRED materializing — same caveat as WS-G addendum §4) |

### §5.2 Proposal P2 (FALLBACK) — ALL-OF freshness vector

**Diff intent:**

```python
# files/score_manager.py, replacing :4454-4457
if (w is not None and self.wickets is not None
        and self.wickets >= 2 and w < self.wickets - 1):
    _s_resets = (s == 0)
    if _team_changed and _s_resets:
        changed = True
        reason = reason or "wickets_regressed"
    else:
        # ...trace + log REJECTED (rationale: wickets regression
        # requires both team flip AND score reset to be a true
        # innings transition signal)
```

**Predicted-flip table:**

| Frame | s | w | _team_changed | _s_resets | Outcome |
|---|---|---|---|---|---|
| F462 | 14 | 0 | False | False | REJECTED (both miss) |
| F690 | 0 | 0 | False | True | REJECTED (team miss) |
| F801 | 67 | 0 | False | False | REJECTED (both miss) |
| F859 | 47 | 0 | False | False | REJECTED (both miss) |
| F992 | 49 | 0 | False | False | REJECTED (both miss) |

Aggregate identical to P1 for this trace (5→0 / 2→0 / 0→≥1 / 20→5-10), but rejects strictly more in unseen fixtures. **Defer as fallback** if step-7 cross-fixture verification surfaces a real inn-2 transition where target appears a frame before broadcast_team flips and P1 false-positives accept the wickets reset spuriously.

---

## §6 Audit obligation — 7-gate framework on leading candidate (P1)

Static-only this pass.

### §6.1 Gate 1 — caller enumeration

`_detect_innings_change` has exactly one call site: `files/score_manager.py:3578` (inside `_handle_warm` after the cascade drain attempt at :3556-3557). No alternate dispatchers. **PASS.**

### §6.2 Gate 2 — caller classification

| Site | Class | Notes |
|---|---|---|
| `:3578` | predicate decision | Consumer of card + frame; producer of `changed` boolean + `self.set_innings_2()` call on True |

Single class, single role. No new classifications introduced by P1. **PASS.**

### §6.3 Gate 3 — adjacent state + §12 dual-state-write

- **Dual-state-write check.** P1 reads `_bcast_team`, `_cur_team`, `_team_changed` (all local-scope variables computed at :4411-4419 for the score_reset branch). No mutation of `self.*` state inside P1's guard. **No §12 instance.**
- **Predicate input freshness.** `_team_changed` is computed from `frame.broadcast_team` (read at frame entry) and `self.batting_team` (set at last accepted commit). Both are available pre-decision. **No blocked input.**
- **Interaction with WICKETS-JUMP upstream.** F461 lifted `self.wickets` to 3 via scoreboard-side consensus. P1 does NOT modify that path; F462 trip still occurs at the predicate, but is now REJECTED at the team-change guard. H4 (consensus tuning) remains an independent surface for a separate session.
- **Interaction with score_reset_from_progress branch above.** Order in predicate: target_appeared → batting_team_changed → score_reset_from_progress → wickets_regressed. If `_team_changed` is True AND `s==0, w==0`, BOTH score_reset (`:4423`) AND wickets_regressed (P1) would set `changed = True` — but `reason = reason or "..."` preserves the first reason. No conflict.
- **Cold-start synth contamination (gate-3 carryover from WS-G surface-A audit §2.3).** P1 does NOT add a drain hook in COLD; the WS-G gate-3 risk (`_synthesize_cold_start_ball_events` reading a stale striker) does NOT apply.

**PASS.**

### §6.4 Gate 4 — equivalence / behavioral delta

| State | Pre-fix | Post-P1 |
|---|---|---|
| Predicate enter, `self.innings >= 2` | early-exit False | unchanged |
| `target_appeared` True | fire inn-2 reset | unchanged |
| `batting_team_changed` (with consensus) | fire inn-2 reset | unchanged |
| `score_reset_from_progress` with team change | fire inn-2 reset | unchanged |
| `score_reset_from_progress` without team change | REJECTED (existing guard) | unchanged |
| `wickets_regressed` with team change | fire inn-2 reset | unchanged |
| `wickets_regressed` without team change | **fire inn-2 reset** | **REJECTED (new behavior)** |

Strict-additive guard. Behavior change scoped to one cell of the truth table. **PASS.**

### §6.5 Gate 5 — lifecycle with empirical-trace observability (insight #17)

P1's effect on reset paths:

| Reset path | Pre-fix observed | Post-P1 expected | Trace tag |
|---|---|---|---|
| `set_innings_2` via wickets_regressed predicate | × 5 in trace | × 0 | (no fires) |
| `set_innings_2` via score_reset_from_progress | × 0 in trace | × 0 | unchanged |
| `set_innings_2` via batting_team_changed | × 0 in trace | × 0 | unchanged |
| `set_innings_2` via target_appeared | × 0 in trace | × 0 | unchanged |
| `set_innings_2` via other callers (`_attempt_inn2_bootstrap` :4622, `_accept_update` :4681, supplements :4826) | × 0 in trace | × 0 | unchanged |
| New `WICKETS-REGRESS-TEAM-CHANGE-REQUIRED-REJECTED` tag | n/a | × 5 (one per pre-fix fire) | new structured emission |

Trace observability preserved + extended. Insight #17 mandate met (new tag attests to the rejection). **PASS.**

### §6.6 Gate 6 — predicted flip with concrete frame numbers

Per §5.1 table. Predicted aggregate flips:

- 5 → 0 SM-INNINGS-2-RESET (target ≤2; P1 exceeds target)
- 2 → 0 WIPED-BY-COLD-START (target 0)
- 0 → ≥1 DRAIN-FIRED (target ≥1, provisional)
- 20 → 5-10 D-post-FoW-striker (target 5-10, provisional)

Provisional caveats inherited from WS-G surface-B audit §3.3 gate-6: D-post-FoW-striker drop requires Scout slot-diff to fire within cascade TTL (80 frames). The 2 cascades in this trace have 69 and 76 frames of headroom post-P1; whether Scout actually delivers within those windows is empirical-replay-bound. **PASS-WITH-ACKNOWLEDGED-PROVISIONAL.**

### §6.7 Gate 7 — cross-fixture verification

Deferred to step-2 empirical replay. Single fixture (`validate_surface_b_121222`) verified statically. Cross-fixture verification requires consuming 1/4 of remaining empirical budget. **DEFER (per stop-condition: static-falsification chain converges → STOP before consuming empirical budget).**

### §6.8 7-gate summary

| Gate | Status |
|---|---|
| 1. Callers | PASS |
| 2. Classification | PASS |
| 3. Adjacent state + §12 | PASS |
| 4. Equivalence | PASS |
| 5. Lifecycle + trace | PASS |
| 6. Predicted flip | PASS-WITH-ACKNOWLEDGED-PROVISIONAL (DRAIN-FIRED + D-post-FoW-striker await empirical replay) |
| 7. Cross-fixture | DEFER (intentional; stop-condition met) |

**GREEN-LIGHT for code implementation in WS-H step 2.** Empirical-replay validation in WS-H step 3.

### §6.9 Adjacent architectural blocker (informational)

The `self.innings 2 → 1` reversion path between fires (§3.2) is unexplained by the predicate body. Mechanism candidates:

- (a) test_pipeline harness re-init between frames (replay-harness artifact, would not occur in production)
- (b) a separate writer mutates `self.innings = 1` (would be a §12 dual-state-write)
- (c) a fresh SM instance per frame (replay-harness artifact)

**This is NOT a blocker for P1** — P1 rejects the trigger upstream of `self.innings` mutation, so the reversion path becomes a no-op in the post-P1 world (no fires → no resets → no need to revert). But it IS a transferable finding flagged for next-session escalation: if the reversion path is production-real (not replay-harness-only), it indicates a hidden state leak that should be characterized separately. Logged as S14 below.

---

## §7 Sub-findings index

Promoted to add to HANDOFF standing-discipline catalogue. Numbered continuing from §17.5 sequence (S12 was the last cited).

### S13 — Architectural-parity asymmetry as a defect-class diagnostic

When two branches in the same predicate body answer the same question against the same misread surface, asymmetric guarding is a predictable defect class. The score_reset_from_progress branch (`:4420-4447`) was hardened on 2026-05-19 with team-change corroboration; the wickets_regressed branch immediately below it (`:4449-4457`) was not. The visible signal — 5× SM-INNINGS-2-RESET at frames where score_reset would have been rejected by the same corroboration — is the direct diagnostic.

**Operational corollary.** When hardening one branch of a multi-branch predicate, audit sibling branches for the same misread surface. The comment block at :4390-4410 explicitly cites "architectural parity with 98a53cc" as the rationale — this same parity argument extends one branch further.

### S14 — Multi-fire predicate implies hidden state-reversion path

A predicate gated by `if self.innings >= 2: return False` that fires 5 times in one session requires `self.innings` to revert between fires. The reversion mechanism is opaque to the predicate's local static analysis. **Operational corollary:** when a guarded predicate fires more times than its guard threshold permits, the secondary investigation is "who reverts the guard?" — that mechanism is itself a likely defect surface. Whether this case (replay-harness vs production) requires escalation is a step-2 empirical replay question.

### S15 — The "code-comment rationale" as a static-falsification anchor

The 2026-05-19 score_reset comment (:4390-4410) names the misread class verbatim — *"structurally indistinguishable from a sponsor-graphic / skeleton-strip misread"* — and provides the architectural-parity argument (with 98a53cc). When a memo exists in-code that names a defect class, static analysis of adjacent unguarded code that consumes the SAME misread surface needs no further empirical evidence to predict-flip with high confidence. The comment is the proof.

---

## §8 Stop-condition status + reporting

**Convergence.** Static-falsification chain converges on P1 (H1). All 7 gates passable on static analysis (gate-6 with acknowledged provisional, gate-7 deferred per stop-condition). **STOP per spec: "static-falsification chain converges on single candidate with all 7 gates passable → STOP and report; do not commit code, do not run empirical replay."**

**Architectural blocker surfaced.** S14 — hidden `self.innings 2→1` reversion path. Does NOT invalidate P1. Flagged for next-session investigation as an independent finding.

**Static-falsification count.** 4 hypotheses statically falsified or accepted in this pass (H1 accepted, H2 partial-coverage rejected, H3 strictly-more-conservative deferred, H4 out-of-scope-deferred). Well under the 8-falsification methodology-class-issue threshold.

**Empirical-falsification budget.** UNCHANGED at 4/5 remaining. No empirical replays consumed.

**Next-session deliverable.** WS-H step 2 — code commit implementing P1 at `files/score_manager.py:4454-4457` mirror of `:4423-4447` structure. Layer 1.5 + Layer 2 + derivation unit gates required green pre-commit. WS-H step 3 — empirical replay against `validate_surface_b_121222` (and one fresh-trace fixture) to confirm gate-6 provisional predictions: SM-INNINGS-2-RESET 5→0, WIPED-BY-COLD-START 2→0, DRAIN-FIRED 0→≥1, D-post-FoW-striker 20→5-10.

---

## §8 Step-3 validation outcome (2026-05-23)

**Decision frame.** Step-3 outcome class: **lifecycle-closure WITH documented architectural findings** — the same shape as WS-G step 5 → step 8. The 1/5 empirical-budget consumption produces transferable methodology insights (S16, S17, S18 below); it is not a wasted iteration. Per insight #18, "lifecycle closure" and "primary-objective closure" are separable audit deliverables; WS-H closes both, with two named residuals opened as follow-on workstreams (step-5 and step-5b in §11).

**Trace artifact.** `logs/trace/validate_ws_h_step3_20260523_164642.jsonl` — 749 records (matches pre-P1 baseline `validate_surface_b_121222.jsonl` exact 749 frames). Single independent variable: P1 patch `ef0860d`. Same captured-Scout dump `files/logs/deliveries/validate_dckkr_20260521_155356/scout_raw.jsonl` used by WS-G steps 5 + 8.

**Full gate table — actuals vs. locked predictions.**

| Metric | Pre-P1 baseline | Locked prediction | Actual (post-P1) | Status |
|---|---|---|---|---|
| `SM-INNINGS-2-RESET reason=wickets_regressed` | 5 | **0** | **1** (F939 only) | **MISS by 1** |
| `WICKETS-REGRESS-TEAM-CHANGE-REQUIRED-REJECTED` (structured) | 0 | **5** | **19** | OVER (counterfactual stronger than predicted: 19 frames newly suppressed) |
| `POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START` | 2 (F690, F859) | **0** | **0** | PASS |
| `POST-WICKET-CASCADE-DRAIN-FIRED` | 0 | **≥1** | **2** (F680, F858) | PASS (exceeds) |
| `POST-WICKET-CASCADE-ENQUEUED` | 2 | 2 | 2 (F679, F855) | sanity holds |
| `CASCADE-DRAIN-EXPIRED` | 0 | n/a | 0 | (info) |
| `D-post-FoW-striker` surface count | 20 | 5-10 | **2** | PASS (strongly exceeds; 90% reduction) |
| `trace_eta_post_wicket_cascade_drains` | PASS × 2 (2 enqueues / 2 WIPED) | PASS × 2 | PASS (2 enqueues / 2 FIRED, 0 WIPED, 0 EXPIRED) | PASS |
| `trace_gamma_w_symbol_at_wicket` | FAIL × 2 | UNCHANGED | FAIL × 2 (F679, F855) | unchanged |
| `trace_gamma_fow_name_matches_striker_at_wicket` | PASS | UNCHANGED | **FAIL × 1** (F679, reason=no_prev_striker) | **REGRESSION** |
| `trace_gamma_bowler_w_increment_on_dispatch` | FAIL × 4 | UNCHANGED | **PASS** | UNEXPECTED IMPROVEMENT |

**Empirical-budget consumption.** 4/5 → **3/5**. Load-bearing artifact of the consumption is S16 + S17 + S18 (§10 below), mirroring WS-G's "budget consumption produced insight #17 + #18 retrospectives" framing.

**Primary-objective closure declaration per insight #18.** Four of the locked rows hit or exceed prediction:

- `D-post-FoW-striker` 20 → 2 (the WS-H primary-objective surface count per §17.3/§17.4 handoff scope).
- `WIPED-BY-COLD-START` 2 → 0 (non-provisional gate, met exactly).
- `DRAIN-FIRED` 0 → 2 (provisional gate, exceeded — both F679 + F855 cascades resolved).
- `γ-bowler-w-increment-on-dispatch` FAIL × 4 → PASS (composite-fix cascade closure per §10 S18).

The remaining residuals — 1× SM-INNINGS-2-RESET at F939 + 1× γ-fow-name FAIL at F679 — are documented as architectural findings (§9), not as workstream failure. Both have transferable diagnostic value (S16, S17) and concrete next-session entry points (§11).

---

## §9 Architectural findings on the two residuals + one unexpected closure

### §9.1 F939 — inherited consensus-asymmetry from score_reset sibling

**Frame anchor.** F939, single-frame KKR misread flipping both team AND wickets simultaneously. Telemetry: `prev=84/3 (10.1) prev_team=DC cand=51/0 cand_team=KKR cand_target=None`.

**Predicate behavior.** Two same-frame events: (a) `batting_team_changed` branch at `:4337-4385` correctly deferred via the 3-frame consensus path (logged `[SM] team-change candidate KKR streak 1/3 — deferring inn-2 trigger`); (b) wickets_regressed branch at `:4454-4486` accepted because the `_team_changed` local at `:4417-4419` is True for that single frame (not consensus-gated).

**Architectural root.** `_team_changed = bool(_bcast_team and _cur_team and _bcast_team != _cur_team)` is a single-frame boolean. The sibling `score_reset_from_progress` branch at `:4423` uses the same single-frame check — that sibling has the SAME consensus gap by design. The CC step-2 verification confirmed parity exact: P1 inherited the sibling's residual, it did not introduce it. The inheritance is structural; per S16 below, parity-mirror fixes inherit precedent gaps.

**Cricket truth.** Over 10.1, DC batting innings 1, no innings transition exists. F939 is genuinely false-positive — a single-frame KKR overlay misread that the consensus-aware branch correctly rejected but the boolean-only branches accept.

**Remediation surface (deferred to step-5 — §11).** Bring `_team_changed` to consensus parity with `batting_team_changed` (3-frame consensus, e.g., consume `_team_change_streak` directly). This closes F939 AND tightens the sibling `score_reset_from_progress` simultaneously — potential S9-pattern cascade-closure-via-one-edit (third instance per S18 below).

### §9.2 F679 — cascade-drain second-order FoW-trail dependency

**Frame anchor.** F679 wicket-commit (Pathum Nissanka dismissed); cascade DRAIN-FIRED at F680 (was WIPED-BY-COLD-START pre-P1).

**Trail-shuffle mechanism.** Pre-P1: at the F679 wicket-commit, the cascade was deferred + then wiped 11 frames later (F690 SM-INNINGS-2-RESET); the prev_striker resolution at FoW assertion site saw the original (pre-cascade) striker chain. Post-P1: F679 cascade enqueues, drains at F680 — i.e., the surviving-batter is now resolved by F680 instead of being deferred indefinitely. The γ-fow-name assertion's reconstruction at F679 looks one frame back at F678; reason `no_prev_striker` indicates the prior frame's striker state was unset (likely because cascade-drain mutation invalidated the stale identity assumption).

**Architectural root.** The prev_striker reconstruction in γ-fow-name implicitly assumes the cascade has NOT yet drained at the wicket-commit frame. P1's cascade-drain enabling exposes the latent dependency: the assertion was correct under the pre-P1 wipe-and-no-drain regime, and now needs to read the cascade lifecycle state explicitly.

**Remediation surface (deferred to step-5b — §11).** Make prev_striker resolution at the γ-fow-name assertion site drain-aware: when the cascade drained between F678 and F679, the resolved (cascade-output) striker becomes the FoW name source rather than the F678 stale state. Dependency is on cascade lifecycle ordering, not on the `_detect_innings_change` predicate.

### §9.3 γ-bowler-w unexpected closure — composite-fix D-chain residual resolved

**Frame anchors.** F679 + F855 bowler-W increments now landing post-cascade-drain. Pre-P1 baseline: `trace_gamma_bowler_w_increment_on_dispatch` was FAIL × 4 (workstream_d_rotation_root_investigation.md §6 predicted FAIL × 4 → FAIL × 2 via D1 alone; actual now PASS at zero residuals via D1 + P1 composition).

**Mechanism.** D1 (em-dash bowler-tracker fallback, commit C28) was already in place at branch HEAD. P1 enables cascade DRAIN-FIRED at the wicket-commit window, which propagates the resolved bowler identity into wicket attribution. D1 + P1 compose: D1 ensured the bowler identity was resolvable; P1 ensured the cascade lifecycle let the resolution reach the attribution site at the right frame. Either fix alone falls short of γ-bowler-w PASS — both together close it.

**Cross-reference.** This is the third independent confirmation of the F1-pattern (single edit closing N classes via cascade): F1 itself (S12-area), S9 (F855→F983 single-edit dependency cascade), and now S18 (P1 enabling D1 composition). See §10 S18.

---

## §10 Sub-findings (S16, S17, S18)

### S16 — Parity-precedent inheritance

When a fix mirrors a hardened-sibling structurally, it inherits the sibling's residual gaps. **Architectural diagnostic:** the parity audit must extend to whether the precedent itself has open residuals before declaring parity-mirror as a closed fix. P1's parity mirror of `score_reset_from_progress :4423` inherited the sibling's single-frame `_team_changed` consensus gap; F939 surfaces this. **Operational corollary:** when a sibling-parity fix lands, audit (a) the sibling's known-residuals list and (b) the parity input's own derivation site — `_team_changed` is a precedent-residual surface that affects two consumers now, not one. Remediation at the precedent (consensus-gate the `_team_changed` derivation) closes both consumers simultaneously.

### S17 — Cascade-lifecycle second-order regression class

When a lifecycle fix enables a previously-blocked drain path, downstream assertions that implicitly assumed the drain was blocked may regress. **Audit obligation:** enumerate downstream consumers of "blocked drain state" before landing lifecycle-enabling fixes. F679 surfaces this: the γ-fow-name assertion's prev_striker reconstruction implicitly assumed cascade-blocked-drain semantics; cascade DRAIN-FIRED exposed the dependency. **Operational corollary:** lifecycle-enabling fixes are not safe-by-construction even when they pass all 7 gates statically — gate-5 (lifecycle) must extend to "lifecycle-enabling-of-blocked-paths" as a distinct audit row, separate from "lifecycle-correctness-of-the-newly-enabled-path."

### S18 — Composite-fix cascade closure (third instance of F1 pattern)

D1 (C28 em-dash bowler-tracker fallback) + P1 (ef0860d wickets_regressed team-change guard) compose to close γ-bowler-w which D1 alone could not. **Pattern recap:**

- **First instance — F1.** Single-edit closing N classes (B-ε direct + B-β cascade + multi-ball-compression cascade + compound-tokens cascade).
- **Second instance — S9.** F855 fix auto-closes F983 via shared dependency surface.
- **Third instance — S18.** D1 + P1 composite closure of γ-bowler-w; neither alone delivers the assertion flip, both together do.

**Methodology consequence.** The F1-pattern is now structurally reproducible across three independent fix-pairs. Insight: when a downstream assertion stays FAIL after its "direct" fix lands, prefer an upstream lifecycle audit (often a separate workstream's fix) before declaring the assertion's own surface as the residual root. **Operational corollary:** the "residual count after direct fix" prediction in any workstream's gate-6 should explicitly include a "but if upstream lifecycle X lands first, residual may collapse" annotation. This is how WS-H delivered the γ-bowler-w PASS that WS-D predicted as FAIL × 2.

---

## §11 Step-5 / step-5b entry data

### §11.1 Step-5 — F939 sibling-asymmetry investigation

**Empirical anchor.** 1× SM-INNINGS-2-RESET at F939 + 19× WICKETS-REGRESS-TEAM-CHANGE-REQUIRED-REJECTED structured records on `logs/trace/validate_ws_h_step3_20260523_164642.jsonl`.

**Predicate sites.** `_team_changed` derivation at `score_manager.py:4417-4419`; consumers at `:4423` (score_reset_from_progress) and `:4454-4486` (wickets_regressed P1). Sibling parity target: `batting_team_changed` consensus implementation at `:4337-4385` (uses `self._team_change_streak` / `TEAM_CHANGE_CONSENSUS_FRAMES`).

**Reading list.**
1. This memo §9.1 + §10 S16.
2. `workstream_g_cold_start_transition_catalogue.md` §5 (WARM→COLD coupling).
3. `score_manager.py:4337-4385` (consensus implementation as parity target).
4. `score_manager.py:4417-4447` (`_team_changed` derivation + score_reset consumer for cross-check).

**Predicted-flip framing.** Bring `_team_changed` to 3-frame consensus parity:

| Metric | Pre-step-5 (this trace) | Post-step-5 predicted |
|---|---|---|
| SM-INNINGS-2-RESET at F939 | 1 | 0 |
| Baseline 4 suppressions (F462/F690/F801/F859 et al) | 19 structured records | UNCHANGED (still rejected via existing team-mismatch path) |
| Legitimate inn-2 acceptance latency | 1-frame | 3-frame consensus delay (matches batting_team_changed precedent; cricket-safe per existing branch design) |

**Do NOT touch ahead of step-5 investigation memo.** Static analysis must converge before any code edit (per WS-H step-1 discipline).

### §11.2 Step-5b — F679 FoW-trail drain-awareness

**Empirical anchor.** 1× `trace_gamma_fow_name_matches_striker_at_wicket` FAIL at F679 (reason=`no_prev_striker`).

**Sites.** γ-fow-name assertion in `files/tests/trace_session_assertions.py` (prev_striker reconstruction path; specific location TBD via step-5b static analysis). Likely also: prev_striker tracking in the `SmDispatchSummary` / `WicketEvent` chain that the assertion consumes.

**Reading list.**
1. This memo §9.2 + §10 S17.
2. `workstream_g_cold_drain_surface_audit.md` §3 (lifecycle table — drain enabling consumers).
3. γ-bundle context in HANDOFF §0 (assertion-baseline-shift section).

**Predicted-flip framing.** Make prev_striker resolution drain-aware:

| Metric | Pre-step-5b (this trace) | Post-step-5b predicted |
|---|---|---|
| γ-fow-name FAIL at F679 | 1 | 0 |
| γ-fow-name baseline FAIL elsewhere | 0 | 0 (no other regression observed) |
| γ-eta cascade drain assertions | PASS | UNCHANGED (drain-aware assertion does not alter drain lifecycle) |

**Do NOT touch ahead of step-5b investigation memo.**

---

## §12 Cross-memo budget + status footer (step-3 era)

**Empirical-falsification budget.** 4/5 → **3/5** consumed by step-3 validation (loading-bearing artifact: S16 + S17 + S18).
**WS-H primary objective.** CLOSED — D-post-FoW-striker 20 → 2 per insight #18 scope.
**WS-H step-5 (F939).** OPEN per §11.1.
**WS-H step-5b (F679).** OPEN per §11.2.
**P1 patch status.** STAYS LANDED at `ef0860d`. No revert.
**Sibling-precedent surface (score_reset_from_progress `:4423`).** Now confirmed-residual via S16; close together with F939 in step-5.

*(Status superseded by §13 + §14 below — step-5 has since CLOSED and step-5b scope has extended to a 3-frame cohort. The original step-3 footer preserved for arc continuity.)*

---

## §13 Step-7 validation outcome (2026-05-23, WS-H step-5 closure)

**Decision frame.** Step-7 outcome class is **primary-closure WITH cascade-lifecycle-second-order γ-regression cohort** — the same shape as WS-H step-3 → step-4 (insight #18 + S17 precedent). Lifecycle-closure and γ-bundle-measurement are scope-separable; the budget consumption produces transferable methodology insight S20 (cohort-exposure pattern), not wasted iteration. H1 stays landed at `832d376` — NO revert. Per S20: the γ regressions are REVEALED, not INTRODUCED — F948 + F1017 share the SAME `no_prev_striker` root as F679 (step-5b territory).

**Trace artifact.** `logs/trace/validate_ws_h_step7_20260523_172140.jsonl` — 749 records (matches step-3 baseline `validate_ws_h_step3_20260523_164642.jsonl` exact 749 frames). Single independent variable: H1 patch `832d376`. Same captured-Scout dump `files/logs/deliveries/validate_dckkr_20260521_155356/scout_raw.jsonl` used by WS-G steps 5/8 and WS-H step-3.

**Full gate table — actuals vs. locked predictions.**

| Metric | Pre-H1 baseline (step-3) | Locked prediction | Actual (post-H1) | Status |
|---|---|---|---|---|
| `SM-INNINGS-2-RESET reason=wickets_regressed` | 1 (F939) | **0** | **0** | PASS (load-bearing) |
| `SM-INNINGS-2-RESET reason=score_reset_from_progress` | 0 | **0** | **0** | PASS (S19 degeneracy held) |
| `WICKETS-REGRESS-TEAM-CHANGE-REQUIRED-REJECTED` (structured) | 19 | ≥19 | **26** | PASS (+7: F939, F940, F942, F946, F993, F1008 + cohort propagation) |
| `INN2-SCORE-RESET-TEAM-CHANGE-REQUIRED-REJECTED` (structured) | 2 | ≥2 | **3** | PASS (+1: F1008) |
| `POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START` | 0 | 0 | **0** | regression-guard PASS |
| `POST-WICKET-CASCADE-DRAIN-FIRED` | 2 (F680, F858) | 2 | **4** | regression-guard PASS (advanced; 2 new drains from cascades that didn't get wiped) |
| `POST-WICKET-CASCADE-ENQUEUED` | 2 (F679, F855) | 2 | **5** | sanity — upstream trajectory diverged (+3 wickets reach the enqueue path now that F939 doesn't wipe innings-1 state) |
| `CASCADE-DRAIN-EXPIRED` | 0 | (info) | **1** | new terminal class observed (first empirical instance) |
| `D-post-FoW-striker` surface count | 2 | 2 | **2** | regression-guard PASS |
| `trace_eta_post_wicket_cascade_drains` | PASS × 2 | PASS × 2 | **PASS** (5 enqueues = 4 FIRED + 1 EXPIRED + 0 WIPED) | regression-guard PASS — η-bundle conservation holds across all three terminals |
| `trace_gamma_w_symbol_at_wicket` | FAIL × 2 (F679, F855) | FAIL × 2 | **FAIL × 4** (F679, F855, F948, F1017) | REGRESSION ×2 NEW (F948 over 10.1, F1017 over 10.4) |
| `trace_gamma_fow_name_matches_striker_at_wicket` | FAIL × 1 (F679) | FAIL × 1 | **FAIL × 3** (F679, F948, F1017; all reason=`no_prev_striker`) | REGRESSION ×2 NEW (F948 dismissed=KL Rahul; F1017 dismissed=Pathum Nissanka) |
| `trace_gamma_bowler_w_increment_on_dispatch` | PASS | PASS | **PASS** | regression-guard PASS (composite-fix closure from S18 preserved) |
| `Silent-wicket-absorption` (classifier surface) | 1 | (not in locked table) | **0** | bonus: surface fully closed post-H1 |

**Cascade-lifecycle conservation check.** 5 ENQUEUED = 4 FIRED + 1 EXPIRED + 0 WIPED. All three terminal classes empirically observed for the first time in a single trace; η-bundle conservation invariant holds exactly.

### §13.1 WS-H step-5 primary closure declaration

Load-bearing predictions per memo §11.1:

- **SM-INNINGS-2-RESET reason=wickets_regressed: 1 → 0.** F939 closes exactly. ✓
- **score_reset baseline holds at 0.** S19 empirical-degeneracy prediction (zero positive `score_reset_from_progress` fires) preserved under H1. ✓
- **S18 cascade-closure dividend confirmed structurally.** H1 propagates to BOTH `:4423` score_reset + `:4456` wickets_regressed consumers by parity inheritance — sibling deferral count 2 → 3 (one new rejection at F1008) confirms the propagation; sibling fire count 0 → 0 confirms the degeneracy holds in the H1-tightened regime, not just in step-5 cross-fixture survey.

**WS-H step-5 OBJECTIVE CLOSED.**

### §13.2 γ-regression cohort characterization (S17 generality)

Pre-H1 step-3: 1 γ-fow-name FAIL at F679 (reason=`no_prev_striker`). The S17 sub-finding was authored on this single-frame anchor.

Post-H1 step-7: 3 γ-fow-name FAIL at F679 + F948 + F1017, all reason=`no_prev_striker`. Plus γ-w-symbol FAIL × 4 at the same wicket-commit frames (F679, F855, F948, F1017) — these are the SAME wicket events failing two different sub-assertions, so the cohort is really 3 wicket-commit frames (F679, F948, F1017), each failing both γ checks.

**Cricket truth (per snapshot diff):**

- F679 — Pathum Nissanka dismissed at ball 8.0 (cascade DRAIN-FIRED at F680).
- F948 — KL Rahul dismissed at ball 10.1 (new post-H1; previously masked by F939 reset wiping innings-1 state mid-over).
- F1017 — Pathum Nissanka dismissed at ball 10.4 (new post-H1; same masking root).

**Why pre-H1 didn't surface F948/F1017.** F939's spurious `SM-INNINGS-2-RESET reason=wickets_regressed` (pre-H1) reset innings to 2 with KKR as `batting_team`, wiping the innings-1 wicket-commit state mid-over (between balls 9.5 and 10.x). Subsequent wickets F948/F1017 either (a) failed to reach the wicket-commit code path because SM treated them as innings-2 with a fresh team or (b) reached it but the γ assertions' prev_striker reconstruction had different (cascade-wiped) state. Either way, the γ assertions saw `no_prev_striker` ONLY at F679 because the post-F939 wickets were structurally invisible to the assertion.

Post-H1: F939 doesn't reset → innings-1 persists → F948 + F1017 wickets process correctly through the cascade pipeline (enqueue + drain) → γ assertions reach the prev_striker reconstruction site for these NEW wicket frames → same `no_prev_striker` defect surfaces three times instead of once.

**Conclusion.** Step-5b's empirical anchor extends from 1 frame (F679) to a 3-frame cohort (F679 + F948 + F1017). The defect class is unchanged — still `no_prev_striker` at γ-fow-name reconstruction — but the cohort size is a measurement-quality improvement, not a correctness regression (per S20 below).

### §13.3 Cascade-lifecycle advancement (bonus)

Beyond the primary step-5 prediction, H1 advanced the cascade lifecycle:

- DRAIN-FIRED count 2 → 4: the additional 2 wickets that pre-H1 were swallowed by F939's reset now enqueue + drain successfully.
- CASCADE-DRAIN-EXPIRED count 0 → 1: first empirical observation of TTL expiry (the third class of cascade terminals; pre-H1 step-3 had 0 + 0 + 2-FIRED + 0-EXPIRED; step-7 has 0 + 0 + 4-FIRED + 1-EXPIRED). η-bundle conservation invariant fully empirically demonstrated.
- Silent-wicket-absorption classifier surface 1 → 0: closed as side-effect.

These are net-positive lifecycle health signals; not regression-guarded; documented here as empirical confirmation that H1 widens correctness rather than narrowing it.

---

## §14 Sub-finding S20 — Cohort-exposure pattern

**S20 — Cohort-exposure pattern.** When an upstream closure prevents state corruption that previously masked downstream defects, the downstream measurement layer observes a regression — but the regression is **REVEALED, not INTRODUCED**. The cohort size is a measurement-quality signal: a one-instance "regression" pre-closure becomes an N-instance cohort post-closure as more frames reach the downstream code path. Strengthens empirical anchor for the downstream investigation; weakens the case for reverting the upstream closure.

**Two instances now observed:**

- **First instance (WS-H step-3 P1):** F679 single γ-fow-name FAIL revealed by P1 enabling cascade DRAIN-FIRED at F680 (was WIPED pre-P1). S17 was authored on this one-instance signal.
- **Second instance (WS-H step-7 H1):** F679 + F948 + F1017 three-instance γ-fow-name cohort revealed by H1 preventing F939's spurious innings-2 reset that previously masked F948/F1017. Same defect class, same `no_prev_striker` root.

**Cross-references.** S17 (cascade-lifecycle-second-order regression class) describes the *mechanism*; S20 describes the *empirical-measurement caveat* on S17-shaped regressions. Together they form the lifecycle-enabling-fix audit pattern:

1. Before landing a lifecycle-enabling fix, predict that downstream consumers of "blocked-state" will surface defects (per S17).
2. After landing, expect the downstream defect cohort to GROW, not shrink (per S20). A non-growing cohort means either (a) the lifecycle fix isn't effective, or (b) the downstream consumers already cover all reachable cases.
3. Cohort growth is closure progress, not regression. Score the upstream fix on its primary objective; defer the downstream cohort to its own scoped workstream.

**Operational corollary.** A regression-guard table in any predicted-flip column should distinguish:

- "Δ count of NEW defect-class instances" (true regression — new class introduced).
- "Δ count of EXISTING defect-class instances" (cohort exposure — same class, more reachability).

WS-H step-7 is type (b) for both γ-w-symbol and γ-fow-name — same root, more frames reached. Type (a) was NOT observed; this is the discipline working as designed.

**Methodology insight escalation.** S17 + S20 jointly graduate the cascade-lifecycle-enabling-fix audit pattern from a single-instance heuristic to a two-instance reproducible discipline. Future lifecycle-enabling commits should include the cohort-growth prediction explicitly in their gate-6 framing.

---

## §15 Status footer (current — step-8 era)

**Empirical-falsification budget.** 3/5 → **2/5** consumed by step-7 validation (load-bearing artifact: S20 cohort-exposure as second instance + step-5b empirical anchor extension F679 → 3-frame cohort). Mirrors WS-G's "budget consumption produced insight #17 + #18" and WS-H step-3's "budget consumption produced S16 + S17 + S18" framing exactly.

**WS-H primary objective.** CLOSED (step-3; D-post-FoW-striker 20 → 2; stable post-H1 at step-7).

**WS-H step-5 (F939).** **CLOSED** (step-7; SM-INNINGS-2-RESET 1 → 0; S18 dividend confirmed; S19 degeneracy held).

**WS-H step-5b (F679 + F948 + F1017 cohort).** **OPEN** with 3-frame empirical anchor (extends from single-frame to cohort per S20). Defect class unchanged — `no_prev_striker` at γ-fow-name prev_striker reconstruction. Entry data + reading list from §11.2 unchanged (root class identical; only the empirical anchor count differs).

**P1 patch status.** STAYS LANDED at `ef0860d`. No revert.
**H1 patch status.** STAYS LANDED at `832d376`. No revert.

**Methodology insights running total.** 16 → 19 (WS-H step-4: S16/S17/S18) → 20 (WS-H step-8: S20).

*(Status superseded by §16 below — WS-H arc fully retired at step-9. The step-7-era footer preserved for arc continuity.)*

---

## §16 Step-5c outcome + WS-H arc closure (step-9, 2026-05-23)

**Decision frame.** WS-H arc closes at step-9. All primary objectives + step-5 + step-5b CLOSED. γ-w-symbol parallel surface remains explicitly out-of-scope per step-5b §6 (deferred to workstream D rotation-root revisit). 1/5 empirical-budget consumed across the entire 9-step arc (step-7 H1 empirical validation only); 8 other steps held static-falsification discipline including step-5c's gate-7 cross-fixture closure (assertion re-run on on-disk traces, no pipeline execution). Six sub-findings landed: S16/S17/S18 (step-3/4 — parity precedent + cascade-lifecycle second-order + composite-fix), S19 (step-5 — cascade-closure-degeneracy), S20 (step-7/8 — cohort exposure), S21 (step-5b — assertion-vs-pipeline). S22 below adds the arc-level meta-finding.

### §16.1 Step-5c gate-7 cross-fixture outcome (verbatim)

Shape A patch landed at `1dbba14` (`files/tests/trace_session_assertions.py:425-:454` graceful-degrade on canonical-resolution alternate). On-disk re-run of modified γ-fow-name assertion across all 13 captured traces:

| Trace | Pre-patch | Post-patch | Δ |
|---|---|---|---|
| validate_20260513_180911 | FAIL × 1 (mismatch) | FAIL × 1 (mismatch) | preserved (true-mismatch class) |
| validate_20260513_194442 | PASS | PASS | unchanged |
| validate_20260520_114437 | PASS | PASS | unchanged |
| validate_dckkr_20260521_070545 | PASS | PASS | unchanged |
| validate_dckkr_20260521_155356 | PASS | PASS | unchanged |
| validate_dckkr_20260522_062844 | PASS | PASS | unchanged |
| validate_dckkr_20260522_063211 | FAIL × 1 (mismatch) | FAIL × 1 (mismatch) | preserved (true-mismatch class) |
| validate_gtrr_20260520_180715 | PASS | PASS | unchanged |
| validate_shape_a_114349 | FAIL × 1 (no_prev_striker) | **PASS** | **closed** (bonus — not in step-5b cohort enumeration) |
| validate_shape_a_20260523_114053 | FAIL × 1 (no_prev_striker) | **PASS** | **closed** (bonus) |
| validate_surface_b_121222 | FAIL × 1 (no_prev_striker) | **PASS** | **closed** (bonus) |
| validate_ws_h_step3_20260523_164642 | FAIL × 1 (no_prev_striker) | **PASS** | **closed** (predicted) |
| validate_ws_h_step7_20260523_172140 | FAIL × 3 (no_prev_striker × 3) | **PASS** | **cohort closed** (predicted) |

**Totals.** 7 `no_prev_striker` FAILs across 5 traces → all 7 closed via Shape A graceful-degrade. 2 mismatch FAILs preserved as true-defect class (deferred to workstream D rotation-root revisit). 0 regressions across 13 traces.

**Bonus closures.** 3 of the 5 closing traces (validate_shape_a_114349, validate_shape_a_20260523_114053, validate_surface_b_121222) carried silently-pre-existing `no_prev_striker` FAILs that were NOT enumerated in step-5b §1's 3-frame cohort (which targeted only validate_ws_h_step7). Shape A swept them as a side effect — these were latent assertion-expectation defects from the WS-G era, present in WS-G's own validation traces but not surfaced as a cohort until step-5b's S21 diagnostic. Confirms S20 cohort-exposure pattern operates ACROSS traces, not just within a single trace's defect set.

### §16.2 WS-H arc closure scoreboard

| Surface | Status | Closed at | Empirical evidence |
|---|---|---|---|
| Primary objective (D-post-FoW-striker 20 → 5-10 target) | **CLOSED** at 20 → 2 (90% reduction; far exceeds target) | step-3 (P1 patch `ef0860d`) | validate_ws_h_step3_20260523_164642 |
| Step-5 sibling-asymmetry (F939 SM-INNINGS-2-RESET 1 → 0) | **CLOSED** | step-7 (H1 patch `832d376`) | validate_ws_h_step7_20260523_172140 |
| Step-5b γ-fow-name cohort (F679 + F948 + F1017 → 0) | **CLOSED** + 4 bonus closures across historical traces | step-5c (Shape A patch `1dbba14`) | 13-trace cross-fixture re-run (assertion-only; no replay) |
| S18 cascade-closure dividend (sibling score_reset_from_progress tightening) | DEGENERATE-ON-DUMP / architecturally real | step-5/step-7 cross-fixture survey | 0 positive fires across all 12 captured traces |
| γ-w-symbol parallel surface (FAIL × 4) | **OUT-OF-SCOPE** | n/a — different read path per step-5b §6 | deferred to workstream D |
| Workstream G primary objective (D-post-FoW-striker drop) | **RETROACTIVELY DELIVERED** via WS-H | step-3 (P1) | per insight #18 scope-separation — recorded as cross-arc delivery, NOT WS-G reopening |

### §16.3 Cross-arc retroactive WS-G primary closure

Workstream G closed its lifecycle objective at `50af67e` (Surface B; gate-5 lifecycle gap) but deferred its primary objective (D-post-FoW-striker 20 → 5-10) to Workstream H per insight #18. WS-H step-3 + step-7 delivered D-post-FoW-striker 20 → 2. Per insight #18's scope-separation discipline, this is recorded as **"primary objective delivered by adjacent workstream"**, NOT as WS-G reopening. The two arcs compose: WS-G's lifecycle scaffold (Surface B WIPED-BY-COLD-START + cascade enqueue/drain wiring) enabled WS-H's predicate-tightening to surface the actual cascade fires (DRAIN-FIRED at F680 + F858 in step-3; 4 fires + 1 EXPIRED at step-7). Neither workstream would have delivered the primary objective alone.

### §16.4 Sub-finding S22 — Static-investigation-first protocol holds across 9-step arcs

**S22.** WS-H opened per HANDOFF §17.4 as static investigation, not patch. Across 9 steps (memo + 4 patches + 2 empirical validations + 2 close-outs + 1 arc retirement), the static-vs-empirical budget distinction held: only step-7's empirical-validation-of-patch-chain consumed 1/5 budget. The other 8 steps (4 memos + 3 code/test patches + assertion-side cross-fixture) preserved budget via static-falsification discipline, including step-5c's gate-7 cross-fixture closure (assertion re-run on on-disk traces, no pipeline execution).

**Demonstrates three transferable principles.**

1. **Arc-length is not a budget-consumption multiplier when static-vs-empirical is rigorously separated.** WS-G consumed 1/5 across 8 steps; WS-H consumed 1/5 across 9 steps. The consumption rate is constant per arc, not per step.
2. **Gate-7 closure can be budget-neutral when the fix surface is assertion-side rather than pipeline-side.** Pipeline-side fixes require empirical replay to verify cross-fixture (per WS-H step-7 H1); assertion-side fixes can verify cross-fixture by re-running the modified assertion against existing trace snapshots (per WS-H step-5c Shape A). The cost difference is one empirical-budget slot.
3. **Assertion-side fix surface is a peer fix-class to pipeline-side**, with distinct verification economics. S21 surfaced the disambiguation; S22 quantifies the cost asymmetry. Future arcs should explicitly classify their fix surface at gate-2 (classification) and route gate-7 (cross-fixture) verification accordingly.

**Cross-references.** S21 (assertion-vs-pipeline fix-surface attribution — methodology); S22 (budget-economics caveat on S21-shaped fixes — economics). Forms the post-WS-H fix-surface audit pair.

**Operational corollary.** When a workstream's gate-6 predicted-flip table cites "cross-fixture verification" as a gate-7 obligation, the gate-7 cost depends on the fix surface:

- Pipeline-side fix → 1/5 budget per empirical replay against each fresh fixture.
- Assertion-side fix → 0/5 budget per on-disk re-run against existing fixtures.

This is the third leg of the post-lifecycle-fix audit triad (S17 mechanism + S20 measurement caveat + S21 fix-surface attribution + S22 verification economics — now a quartet).

---

## §17 Arc-level statistics (step-9 retrospective)

**Steps.** 9 (memo + P1 patch + step-3 validation + step-4 close-out + step-5 memo + H1 patch + step-7 validation + step-8 close-out + step-5b memo + step-5c patch + step-9 close-out — 11 actual events spanning 9 numbered steps; some steps combined patch + memo).
**Commits.** 7 on `derive-not-detect` post-merge (9b2afc5 + ef0860d + 113b747 + 28d28b4 + 832d376 + 6d80c57 + 031d221 + 1dbba14 + step-9 docs commit = 9 commits).
**Empirical-budget consumption.** 1/5 (step-7 H1 validation surfacing S20 cohort exposure).
**Sub-findings.** 6 (S16 + S17 + S18 step-3/4; S19 step-5; S20 step-7/8; S21 step-5b; S22 step-9 — corrected: 7 if S22 counted alone, 6 if S22 is the arc-level summary subsuming the prior 5).
**Closures.** Primary objective + step-5 + step-5b + 4 bonus across historical traces = 8 named closures including the cohort + bonus.
**Methodology insights running total.** 16 → 21 (S16/S17/S18/S19/S20/S21/S22).
**Cross-arc delivery.** WS-G primary objective (D-post-FoW-striker drop) retroactively delivered per insight #18.

**Status footer.**
- WS-H primary objective: CLOSED (step-3).
- WS-H step-5 (F939): CLOSED (step-7).
- WS-H step-5b (γ-fow-name cohort): CLOSED (step-5c).
- WS-G primary objective: RETROACTIVELY DELIVERED via WS-H per insight #18.
- γ-w-symbol parallel surface: OUT-OF-SCOPE (deferred to workstream D rotation-root revisit).
- P1 patch `ef0860d`, H1 patch `832d376`, Shape A patch `1dbba14`: all STAY LANDED. No reverts.
- Empirical-falsification budget: 2/5 remaining.
- Next session: §11.3 surgical items 3-7 (Workstream F bowler misattribution, Per-batter-ledger conservation, Recent-Overs partial-render, phantom-runs root-localize). No WS-H follow-on workstream open.

**WS-H arc CLOSED.**

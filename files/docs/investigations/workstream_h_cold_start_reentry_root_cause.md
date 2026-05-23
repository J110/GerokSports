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

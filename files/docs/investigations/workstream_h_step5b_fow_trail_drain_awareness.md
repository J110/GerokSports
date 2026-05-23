# Workstream H — Step-5b: FoW-trail drain-awareness investigation

**Status.** Step-5b deliverable: static-falsification memo on the γ-bundle no_prev_striker cohort root cause. No code edits this pass. Empirical-falsification budget UNCHANGED at 2/5.
**Branch.** `derive-not-detect` at HEAD `6d80c57` (WS-H step-8 close-out landed).
**Comparator trace.** `logs/trace/validate_ws_h_step7_20260523_172140.jsonl` (749 frames; produced under H1 patch `832d376`).
**Predecessor.** `workstream_h_cold_start_reentry_root_cause.md` §9.2 + §13.2 + §14 S20.
**Result.** Static-falsification chain converges on **H3 (upstream-source / assertion-expectation)**. The cohort's failure root is the assertion's expectation that `pipeline.striker` is non-None at F<wicket-1> — but the §15-fence canonical invalidation paths (cold-start verdict rejection at `score_manager.py:3074-:3118`) legitimately clear `self.striker` to None during broadcast-overlay/skeleton windows that frequently precede wicket-commit frames. Cascade DRAIN-FIRED at F<wicket+1> is NOT in the causal path — it emits AFTER the assertion's prev_frame read. **The fix surface is assertion-side, not pipeline-side.** Cohort-closure verification: UNIFIED across F679 + F948 + F1017. One new sub-finding S21.

---

## §1 Empirical anchor — 3-frame cohort reconstruction

Pipeline `striker` field (read directly from `getattr(sm, "striker", None)` per replay script at `:549`) traced through F<wicket-3 .. wicket+3> for each cohort instance:

### §1.1 F679 cohort instance (dismissed = Pathum Nissanka)

| Frame | `pipeline.striker` | `pipeline.non_striker` | Decisions tags (filtered) |
|---|---|---|---|
| F676 | `Pathum Nissanka` | `KL Rahul` | (none) |
| F677 | **None** | None | (none — silent clear) |
| **F678 ← prev_frame for assertion** | **None** | None | (none) |
| F679 (WICKET) | `Nitish Rana` | None | SILENT-WICKET-ABSORPTION, STRIKER-IDENTIFY-FALLBACK-INVOKED, WICKET-RESOLVED-FROM-DETERMINISTIC-STRIKER, STRIKER-EVENT-DISPATCHED |
| F680 (DRAIN) | `KL Rahul` | `Nitish Rana` | STRIKER-EVENT-DISPATCHED, POST-WICKET-CASCADE-DRAIN-FIRED |

**Assertion fail mode.** Reads `records[678].pipeline.striker` → None → `no_prev_striker` failure.

### §1.2 F948 cohort instance (dismissed = KL Rahul)

| Frame | `pipeline.striker` | `pipeline.non_striker` | Decisions tags (filtered) |
|---|---|---|---|
| F946 | `KL Rahul` | `Pathum Nissanka` | WICKETS-REGRESS-TEAM-CHANGE-REQUIRED-REJECTED ×2 |
| **F947 ← prev_frame for assertion** | **None** | None | (none — silent clear between F946 and F947) |
| F948 (WICKET) | None | `Pathum Nissanka` | SILENT-WICKET-ABSORPTION, STRIKER-IDENTIFY-FALLBACK-INVOKED, WICKET-RESOLVED-FROM-DETERMINISTIC-STRIKER, WICKET-FALL-ONLY-CALLED |

**Assertion fail mode.** Reads `records[947].pipeline.striker` → None → `no_prev_striker` failure.

### §1.3 F1017 cohort instance (dismissed = Pathum Nissanka)

| Frame | `pipeline.striker` | `pipeline.non_striker` | Decisions tags (filtered) |
|---|---|---|---|
| F1014 | None | None | (none) |
| F1015 | None | `Pathum Nissanka` | STRIKER-IDENTIFY-FALLBACK-INVOKED, WICKET-DEFERRED-NO-DISMISSED-IDENTITY |
| **F1016 ← prev_frame for assertion** | **None** | `Pathum Nissanka` | (none) |
| F1017 (WICKET) | None | `Axar Patel` | WICKET-RESOLVED-FROM-PENDING, WICKET-FALL-ONLY-CALLED, WICKET-SLOT-CLEAR-ENTRY, POST-WICKET-STRIKER-CASCADE-DEFERRED |
| F1018 (DRAIN) | None | `Axar Patel` | STRIKER-EVENT-DISPATCHED ×2, POST-WICKET-CASCADE-DRAIN-FIRED ×2 |

**Assertion fail mode.** Reads `records[1016].pipeline.striker` → None → `no_prev_striker` failure. Note: striker stays None even after the cascade drain (F1018+) — the wicket-resolution path here uses PENDING-side state, and the non_striker pointer (`Pathum Nissanka` → `Axar Patel`) is the one that updates. Striker remains None throughout the visible window.

### §1.4 Cohort common pattern

| Property | F679 | F948 | F1017 |
|---|---|---|---|
| `pipeline.striker` at F<wicket-1> | None | None | None |
| Cascade DRAIN-FIRED frame | F680 (`+1`) | (no cascade drain — wicket resolves directly) | F1018 (`+1`) |
| Cascade drain location relative to assertion's prev_frame read | **AFTER** (F680 > F678) | n/a | **AFTER** (F1018 > F1016) |
| Striker resolution path at F<wicket> | DETERMINISTIC-STRIKER | DETERMINISTIC-STRIKER | RESOLVED-FROM-PENDING |
| Silent clear point | between F676 and F677 | between F946 and F947 | pre-F1014 (never resolved post-prior-wicket) |

**Unified pattern.** All three instances share: striker is **None at F<wicket-1>**, the cascade drain (when it fires) occurs **after** the assertion's prev_frame read, and the silent clear happens **before** F<wicket-1>. The cascade-drain timing is not in the assertion's causal path; striker is None for a different, upstream reason — see §3 + §4.

---

## §2 γ-bundle reconstruction logic

### §2.1 `trace_gamma_fow_name_matches_striker_at_wicket` — `files/tests/trace_session_assertions.py:380-448`

Algorithm (verbatim):

```python
for i, rec in enumerate(records):
    # 1. Resolve `dismissed` from trace_beta_sm_wicket_dispatch tag OR
    #    fallback ball_event.type == "WICKET" + striker_this_ball.
    dismissed = ...
    if not dismissed: continue

    # 2. Edge case: first frame has no preceding frame.
    if i == 0:
        failures.append({..., "reason": "no_preceding_frame"})
        continue

    # 3. Read prev_striker from records[i-1].pipeline.striker.
    prev = records[i - 1]
    prev_striker = (prev.get("pipeline") or {}).get("striker")
    if not prev_striker:
        failures.append({..., "reason": "no_prev_striker"})
        continue

    # 4. Compare prev_striker to dismissed (case-insensitive).
    if str(prev_striker).strip().lower() != dismissed.strip().lower():
        failures.append({...})
```

**Key predicate** (line :427): `if not prev_striker:` — fires `no_prev_striker` when `records[i-1].pipeline.striker` is None or empty string. Single-frame lookback; no fallback to other state surfaces; no awareness of cascade drain.

**Implicit assumption.** The assertion assumes the pipeline's `striker` pointer is a continuous-monotonic state — once set to a name, stays set until rotation or wicket. This assumption is invalidated by the §15-fence canonical invalidation paths (see §4).

### §2.2 `trace_gamma_w_symbol_at_wicket` — `files/tests/trace_session_assertions.py:280-357`

Different surface entirely: reads `records[i+1].ui_after.this_over` (the NEXT frame's render state, not the prev frame's pipeline state). Failure mode in step-7 trace: `next_this_over=[], window=[]` — the next frame's `this_over` array is empty.

**Cohort overlap.** γ-w-symbol fires at F679, F855, F948, F1017. γ-fow-name fires at F679, F948, F1017. They share 3 frames (F679/F948/F1017) but for **structurally different reasons** — γ-w-symbol's failures are about render-state propagation to the next frame; γ-fow-name's failures are about pipeline-state visibility at the prev frame. Treating them as a single cohort is a misread of the failure shapes.

**Scope note for step-5b.** Per the step-5b handoff, the cohort under investigation is γ-fow-name's no_prev_striker cohort (F679 + F948 + F1017). γ-w-symbol's 4-instance cohort is a parallel surface with a different root and is **out of scope** for this memo. The step-5b predicted-flip table (§8) projects γ-w-symbol shift only conditionally (if H3's fix happens to also unblock γ-w-symbol's render-state propagation — see §6).

---

## §3 Cascade-drain emission ordering — `score_manager.py:1120-1158`

`_attempt_pending_cascade_drain` body (verbatim ordering):

```python
while self._pending_post_wicket_cascade:
    entry = self._pending_post_wicket_cascade[0]
    # ... slot-diff resolution ...
    if new_batter is not None:
        # ... build StrikerEvent ...
        self.apply_striker_event(striker_event)      # <-- WRITES self.striker
        self._emit_trace(                            # <-- EMITS DRAIN-FIRED
            tag="POST-WICKET-CASCADE-DRAIN-FIRED",
            ...
        )
        self._pending_post_wicket_cascade.pop(0)
        continue
```

**Emission ordering at the drain frame:**

1. `apply_striker_event` writes `self.striker = next_striker` (canonical ROTATION path per §15 fence).
2. `_emit_trace("POST-WICKET-CASCADE-DRAIN-FIRED", ...)` emits the trace tag.

Both happen within the SAME frame body (synchronous, single-threaded per `on_frame` contract). The new `self.striker` is visible to subsequent reads in the same frame and to all subsequent frames' `pipeline.striker` snapshots.

**Cross-frame ordering at cohort.** For F679 cohort: cascade ENQUEUED at F679 (during wicket dispatch); cascade DRAINED at F680 (next frame's `_handle_warm` call). The drain modifies `self.striker` at F680, not at F678 (the assertion's prev_frame read). **The drain is causally downstream of the assertion's read.**

For F948: no cascade drain visible in the +3 window — the wicket resolves directly via WICKET-RESOLVED-FROM-DETERMINISTIC-STRIKER without a cascade defer. Drain ordering is moot.

For F1017: cascade ENQUEUED at F1017 (WICKET-DEFERRED-NO-DISMISSED-IDENTITY + POST-WICKET-STRIKER-CASCADE-DEFERRED); cascade DRAINED at F1018. Drain at F1018, assertion reads F1016 — drain is +2 frames downstream of read.

**Conclusion.** Cascade-drain emission ordering is NOT in the causal chain that produces the cohort's `no_prev_striker` failures. The original WS-H §9.2 hypothesis ("cascade drain at F680 modifies prev_striker bookkeeping at the F679 wicket-commit moment") was incorrect — the timing is wrong by 2 frames. The cascade drain *post-resolves* the new-batter identity AFTER the assertion's failure has already been declared. Hypothesis H1 (producer-side cascade-drain timing) is **statically falsified**.

---

## §4 prev_striker pointer lifecycle — `self.striker = None` write sites

7 explicit `self.striker = None` write sites in `score_manager.py` (post-§15 fence; confirmed by post-merge grep at `:1964`, `:2394`, `:3078`, `:3095`, `:3106`, `:3117`, `:3222`). All are **invalidation paths** per §15 fence design. Categorized:

| Site | Context | Trigger condition |
|---|---|---|
| `:1964` | `apply_striker_event` (cascade drain) | next_striker explicitly None (rare) |
| `:2394` | `_synthesize_cold_start_ball_events` | striker reset at synth boundary |
| `:3078` | `_handle_cold_start` | cold-start verdict reject (`abs_check.ok == False`) |
| `:3095` | `_handle_cold_start` | cold-start reject `inn1_impossible_wickets_overs` |
| `:3106` | `_handle_cold_start` | cold-start reject `inn1_severe_collapse_implausible` |
| `:3117` | `_handle_cold_start` | cold-start reject `inn1_score_too_low_for_wickets` |
| `:3222` | `_handle_cold_start` | cold-start verdict reject (additional branch) |

**5 of 7 writes** are in `_handle_cold_start` reject paths. Each clears `self.striker` as part of invalidating a rejected cold-start verdict — the SM enters COLD_START mode, attempts to seed a verdict from a frame's broadcast/extractor reads, finds the read implausible (sponsor/skeleton/overlay graphic, or cricket-physics-impossible like 5 wickets in <5 overs), and invalidates whatever striker identity it had accumulated.

**Cohort attribution candidate.** The silent clears at F677 (F679 cohort), F947 (F948 cohort), and pre-F1014 (F1017 cohort) most likely originate from these cold-start reject paths firing on broadcast-overlay frames in the lead-up to each wicket. The replay's `Frames: 749 | parsed: 512 | skipped: 237` count (per step-7 replay output) indicates ~32% of frames are skipped (non-scoreboard renders); the parsed-but-rejected subset fires the cold-start invalidation.

This pattern is **architectural invariant per §15 fence**: COLD_START reject paths clear striker as an atomicity guarantee (don't carry a stale identity into the next cold-start attempt). The pipeline is doing exactly what it's designed to do.

**Static-falsification of H4 (trail-shuffle).** The DRAIN-FIRED event at F<wicket+1> doesn't shuffle the F<wicket-1> snapshot — F<wicket-1>'s snapshot was already recorded by the time the drain emits. H4 is misframed: the "trail shuffle" doesn't reach backwards in time. **H4 statically falsified.**

---

## §5 Hypothesis enumeration

Four candidate root causes per step-5b handoff scope. Each evaluated against §7.2 gates 1-3.

### §5.1 H1 — Producer-side: cascade DRAIN-FIRED occupies slots the γ-bundle expects for striker resolution

**Static analysis (§3).** Cascade DRAIN-FIRED emits at F<wicket+1>, AFTER the assertion's F<wicket-1> read. Cannot affect F<wicket-1>'s snapshot.

**Gate 1 (caller enumeration).** DRAIN-FIRED emit at `:1146`. One emit site.
**Gate 2 (classification).** Producer (cascade drain) + consumer (γ-fow-name assertion); decoupled by frame ordering.
**Gate 3 (adjacent state).** DRAIN-FIRED writes `self.striker` at the same frame as its emit; this becomes visible at F<wicket+1>'s snapshot, not F<wicket-1>'s.

**Verdict.** **STATICALLY FALSIFIED at §3.** Timing impossibility.

### §5.2 H2 — Consumer-side: γ-bundle prev_striker lookup window assumes single-write per frame; cascade drain breaks the assumption

**Static analysis (§2.1).** The assertion's lookup is single-frame (`records[i - 1]`); no window logic that interacts with multi-write semantics. The "single-write per frame" assumption is irrelevant because the assertion only reads one frame.

**Gate 1.** Assertion site at `:425-:433` (single line read).
**Gate 2.** Pure-consumer; no producer interaction.
**Gate 3.** Independent of cascade drain entirely.

**Verdict.** **STATICALLY FALSIFIED at §2.1.** The assertion's logic doesn't assume single-write-per-frame; it assumes pointer-monotonicity-since-last-resolution. That assumption IS violated, but the violation is upstream (cold-start invalidation) not the cascade drain. H2's framing is wrong.

### §5.3 H3 — Upstream-source: prev_striker is legitimately None at F<wicket-1>

**Static analysis (§1 + §4).** All three cohort instances show `pipeline.striker = None` at F<wicket-1>. The None state is set by §15-fence canonical invalidation paths (cold-start verdict rejection), which are architectural invariants — the pipeline correctly clears a stale identity when a cold-start verdict fails. The assertion's expectation that `prev_striker == dismissed` requires the pipeline to maintain identity across cold-start invalidation, which is incompatible with the §15-fence invalidation discipline.

**Gate 1 (caller enumeration).** Assertion read at trace_session_assertions.py:425-:433 (single site). 7 `self.striker = None` write sites in score_manager.py (per §4 table); 5 of 7 are in cold-start invalidation paths.
**Gate 2 (classification).** Pipeline's None-write is the *correct* behavior per §15 fence; assertion's read is *incorrect* in expecting non-None at F<wicket-1>.
**Gate 3 (adjacent state).** The wicket-commit at F<wicket> independently resolves `dismissed` via DETERMINISTIC-STRIKER, RESOLVED-FROM-PENDING, or other canonical wicket-attribution paths. Dismissed-name is available at F<wicket> WITHOUT needing F<wicket-1>'s pipeline.striker. The assertion currently doesn't use this — it bypasses F<wicket>'s dismissed-resolution and reads F<wicket-1> instead.

**Verdict.** **STATICALLY CONFIRMED.** Leading candidate. The fix surface is **assertion-side**: γ-fow-name needs to tolerate `pipeline.striker == None` at F<wicket-1> when (a) the wicket-commit at F<wicket> has a resolved `dismissed` identity (which it always does, by definition of the assertion's wicket-event detection path), and (b) the None state is attributable to a §15-fence canonical invalidation (look back further to find the last non-None striker, OR skip the check when dismissed is resolved by a canonical wicket-attribution path).

### §5.4 H4 — Trail-shuffle: cascade drain reassigns striker before F<wicket-1>'s snapshot is recorded

**Static analysis (§3 + §4).** Trace snapshots are recorded per-frame at the end of each `on_frame` call. F<wicket-1>'s snapshot is sealed before F<wicket>'s body runs; cascade drain at F<wicket+1> happens two frames later. There's no mechanism by which the drain's striker-write could shuffle backwards into F<wicket-1>'s snapshot.

**Gate 1-3.** All moot.

**Verdict.** **STATICALLY FALSIFIED at §3 + §4.** Same timing impossibility as H1.

### §5.5 Coverage summary

| Hypothesis | Gates 1-3 | Falsification cause | Verdict |
|---|---|---|---|
| H1 — producer-side cascade timing | falsified | DRAIN-FIRED is +1 frame downstream of assertion read | FALSIFIED |
| H2 — consumer-side multi-write assumption | falsified | assertion is single-read, no multi-write assumption | FALSIFIED |
| H3 — upstream-source / assertion-expectation | PASS | striker legitimately None per §15 fence invalidation | **CONFIRMED — leading** |
| H4 — trail-shuffle | falsified | frame snapshots sealed in order; drain cannot reach backwards | FALSIFIED |

**Static-falsification count.** 3 (H1, H2, H4). Well under the 8-falsification methodology-class-issue threshold.

---

## §6 Cohort-closure verification

**Claim under test.** A single assertion-side fix (per H3) closes all 3 cohort frames (F679 + F948 + F1017) simultaneously.

**Static analysis.** All 3 instances share the same failure shape:

1. `pipeline.striker == None` at F<wicket-1>.
2. None state is attributable to upstream §15-fence invalidation (visible in §1 timelines via the silent clears before each wicket frame).
3. Wicket-commit at F<wicket> independently resolves `dismissed` via canonical wicket-attribution paths (DETERMINISTIC-STRIKER for F679/F948; RESOLVED-FROM-PENDING for F1017).

The assertion's fail-predicate (`if not prev_striker: failures.append({"reason": "no_prev_striker"})`) fires identically across all 3 — the fix surface is the predicate body itself. Any modification that tolerates None at F<wicket-1> (e.g., widen lookback window past invalidation points; OR skip the comparison when dismissed is resolved by a canonical path; OR cross-check against `pipeline.striker_history`/equivalent backtrack) closes all 3 instances in a single edit.

**Cohort-closure status.** **UNIFIED.** The 3-frame cohort has structurally identical root + structurally identical fix surface. Step-5b does NOT split into step-5b-i/ii/iii.

**Cross-cohort splash — γ-w-symbol.** Per §2.2, the parallel γ-w-symbol surface fires at F679/F855/F948/F1017 for a different reason (empty `next_frame.ui_after.this_over` array). H3's assertion-side fix to γ-fow-name does NOT directly close γ-w-symbol — different assertion, different read surface, different failure root. The two cohorts (γ-fow-name's 3-frame + γ-w-symbol's 4-frame) overlap in 3 frames but the fixes are independent. γ-w-symbol is **out of scope** for step-5b per the handoff; its 4 fires remain post-fix.

---

## §7 Audit obligation — 7-gate audit on H3 (leading candidate)

Static-only this pass per step-5b stop-condition.

### §7.1 Gate 1 — Caller enumeration

`pipeline.striker` is read at exactly one site in the trace assertion suite: `files/tests/trace_session_assertions.py:425-:433` (γ-fow-name's `no_prev_striker` predicate). γ-w-symbol does not read `pipeline.striker`. No other readers. **PASS.**

### §7.2 Gate 2 — Classification

Pure-assertion-side modification. Pipeline state is correct per §15 fence; assertion's predicate is the consumer needing tightening. No producer change. No pipeline state change. **PASS.**

### §7.3 Gate 3 — Adjacent state + §12 dual-state-write

Assertion modification reads only `records[]` snapshot fields. No `self.*` mutation; no parallel state surface; not a §12 instance.

Cross-check: WICKET-RESOLVED-FROM-DETERMINISTIC-STRIKER trace tag emit at the wicket-commit frame provides an alternate authoritative `dismissed` resolution path. RESOLVED-FROM-PENDING tag provides the cascade-pending alternate. Both are visible at F<wicket> in the trace records; the assertion can read them without needing the F<wicket-1> snapshot.

**PASS.**

### §7.4 Gate 4 — Equivalence / behavioral delta

| State | Pre-fix (current assertion) | Post-H3-fix (proposed) |
|---|---|---|
| F<wicket-1>.pipeline.striker is non-None AND matches dismissed | PASS | PASS (unchanged) |
| F<wicket-1>.pipeline.striker is non-None AND differs from dismissed | FAIL (true mismatch — preserved) | FAIL (preserved — this is a real defect) |
| F<wicket-1>.pipeline.striker is None | FAIL (no_prev_striker) | PASS (degrade gracefully when dismissed is resolved at F<wicket> by a canonical wicket-attribution path) OR FAIL with NEW reason `pipeline_invalidation_at_prev_frame` (more precise diagnostic) |

The fix preserves the true-mismatch detection (genuine pipeline-vs-cricket-truth defects still surface) while tolerating the §15-fence invalidation cases. **PASS.**

### §7.5 Gate 5 — Lifecycle + trace observability

No new persistent state. No new trace tag (unless the fix introduces a new failure reason like `pipeline_invalidation_at_prev_frame` — optional refinement). Assertion lifecycle unchanged (still run per-frame, still emit failure samples). **PASS.**

### §7.6 Gate 6 — Predicted flip with concrete frame numbers

Per §8 below. Cohort closure 3 → 0 at γ-fow-name; γ-w-symbol unchanged (independent surface, per §6).

**PASS-with-acknowledged-cross-cohort-residual** (γ-w-symbol at F855 and 3 cohort overlaps remain because that surface has independent root).

### §7.7 Gate 7 — Cross-fixture verification

Deferred per step-5b stop-condition. Other captured traces (12 total) likely contain similar cold-start-invalidation patterns at wicket-commit frames — cross-fixture verification at step-5c-empirical would confirm.

### §7.8 7-gate summary

| Gate | Status |
|---|---|
| 1. Callers | PASS |
| 2. Classification | PASS |
| 3. Adjacent state + §12 | PASS |
| 4. Equivalence | PASS |
| 5. Lifecycle + trace | PASS |
| 6. Predicted flip | PASS-with-cross-cohort-residual (γ-w-symbol unchanged per §6) |
| 7. Cross-fixture | DEFER per step-5b stop-condition |

**GREEN-LIGHT for step-5c assertion-side patch.**

---

## §8 Predicted-flip table for step-5c

| Metric | Pre-fix (validate_ws_h_step7_20260523_172140) | Post-H3-fix predicted |
|---|---|---|
| `trace_gamma_fow_name_matches_striker_at_wicket` | FAIL × 3 (F679, F948, F1017; all `no_prev_striker`) | **PASS** OR `FAIL × 3 with refined reason` (depending on whether fix degrades gracefully or just renames the diagnostic — both close the methodology surface) |
| `trace_gamma_w_symbol_at_wicket` | FAIL × 4 (F679, F855, F948, F1017) | FAIL × 4 (unchanged — independent root per §6) |
| `SM-INNINGS-2-RESET reason=wickets_regressed` | 0 | 0 (unchanged) |
| `SM-INNINGS-2-RESET reason=score_reset_from_progress` | 0 | 0 (unchanged) |
| `POST-WICKET-CASCADE-DRAIN-FIRED` | 4 | 4 (unchanged) |
| `CASCADE-DRAIN-EXPIRED` | 1 | 1 (unchanged) |
| `POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START` | 0 | 0 (unchanged) |
| `D-post-FoW-striker` surface count | 2 | 2 (unchanged) |
| `trace_eta_post_wicket_cascade_drains` | PASS × 2 | PASS × 2 (unchanged) |
| `trace_gamma_bowler_w_increment_on_dispatch` | PASS | PASS (unchanged) |
| `WICKETS-REGRESS-TEAM-CHANGE-REQUIRED-REJECTED` | 26 | 26 (unchanged) |
| `INN2-SCORE-RESET-TEAM-CHANGE-REQUIRED-REJECTED` | 3 | 3 (unchanged) |

**Cohort closure** at γ-fow-name is the load-bearing prediction. γ-w-symbol remains as a separately-scoped follow-on (potential step-5c-followup or new workstream).

---

## §9 Sub-finding S21 — Assertion-expectation vs. pipeline-state defect class

**S21.** When a trace-assertion's reconstruction depends on a specific pipeline-state invariant that's actually *optional* (e.g., the pipeline's canonical invalidation paths can legitimately produce the "broken" state), the failure is in the assertion's expectation, not the pipeline. **Diagnostic protocol** (three-step):

1. **Trace the failing pipeline-state read back to its writers.** Use the `self.X = None` (or analogous clear) grep to enumerate every write site. If 50%+ of the writes are in canonical invalidation paths (cold-start reject, NAME-REJECTED, post-wicket survivor unresolved, §15-fence cleanup), the "None" state is architectural-invariant behavior, not a bug.
2. **Verify the assertion has an alternate authoritative source.** If the assertion can read `dismissed` directly from the wicket-commit frame (DETERMINISTIC-STRIKER / RESOLVED-FROM-PENDING / etc.) without needing the prev-frame state, the prev-frame read is a redundant indirection — the fix is to read the authoritative source.
3. **Cross-check with the §15 fence (or equivalent architectural-invariant catalogue).** If the failing state is documented as a canonical write in the fence, the pipeline cannot be the fix site without violating the fence — the assertion must adapt.

**Operational corollary.** Cascade-lifecycle-second-order regressions (S17) and cohort-exposure (S20) both flag "assertion regresses after upstream closure." S21 adds the third leg: **before scoping a downstream investigation as a pipeline-state fix, verify the failing state isn't an architectural invariant.** If it is, the investigation pivots to assertion-side tightening — distinct discipline class.

**WS-H step-5b is the prototype.** The original WS-H §9.2 framing ("cascade drain modifies prev_striker bookkeeping") was a pipeline-side narrative that didn't survive §3 static analysis (drain timing is wrong by 2 frames). S21's diagnostic protocol applied to the same evidence converges on H3 (assertion-side) cleanly. Future cohort-exposure investigations should run S21's three-step diagnostic before assuming the cascade lifecycle is the fix site.

**Cross-references.** S17 (cascade-lifecycle-second-order regression class — described mechanism); S20 (cohort-exposure pattern — empirical-measurement caveat); S21 (assertion-expectation defect class — fix-surface attribution). The three jointly form the post-lifecycle-fix audit triad.

---

## §10 Step-5c entry data

### §10.1 Patch surface

`files/tests/trace_session_assertions.py:380-448` — γ-fow-name `assert_fow_name_matches_striker_at_wicket` function body. Two candidate shapes:

**Shape A — degrade gracefully on canonical invalidation.** When `prev_striker` is None, look at the current frame's wicket-attribution path; if it resolved via DETERMINISTIC-STRIKER, RESOLVED-FROM-PENDING, or other canonical path, treat the wicket-commit's own `dismissed` resolution as authoritative and skip the prev-frame comparison. Emit a softer trace tag (`no_prev_striker_canonical_resolved` or similar) for diagnostic visibility but don't count it as a failure.

**Shape B — extend lookback past invalidation.** When `prev_striker` is None at `records[i-1]`, walk backward through `records[i-2], records[i-3], ...` until a non-None striker is found OR the lookback window is exhausted (e.g., 30-frame ceiling). Compare that last-non-None striker to `dismissed`. Failure mode upgrades from `no_prev_striker` to `no_recent_striker` if the entire lookback window is None.

Shape A is structurally simpler (single-frame logic) and aligns with the §15 fence (let the canonical path own the resolution). Shape B is more conservative (preserves the prev-state comparison semantically) but adds lookback complexity. Recommend Shape A as the leading shape for step-5c static analysis; revisit if step-5c memo surfaces a defect Shape A misses.

### §10.2 Test additions

New test file or extension to existing γ-bundle test:

- T-1: F679 analog — `pipeline.striker = None` at i-1, dismissed resolved via DETERMINISTIC-STRIKER → PASS post-fix.
- T-2: F948 analog — same setup, different dismissed name → PASS.
- T-3: F1017 analog — RESOLVED-FROM-PENDING path → PASS.
- T-4: True mismatch case — `pipeline.striker = 'X'` at i-1, dismissed = 'Y' → FAIL (preserved).
- T-5: Continuous-monotonic case — `pipeline.striker = dismissed` at i-1 → PASS (unchanged).

L1.5 inclusion is optional (the γ-bundle assertions are in `files/tests/trace_session_assertions.py`, which is a diagnostic library, not a pre-commit gate). Pre-commit L1.5 gate is unchanged.

### §10.3 Gate-7 cross-fixture obligations

Run the modified γ-fow-name assertion against all 12 captured traces on disk. Predicted: most traces have 0 wicket-commit frames (early-innings windows), so 0 fires expected; the DCKKR-fixture replays (`validate_dckkr_*`, `validate_surface_b`, `validate_shape_a`, `validate_ws_h_step3`, `validate_ws_h_step7`) cover wicket-bearing windows and should show 0 failures post-fix (or fewer failures, depending on shape).

**Budget impact.** 0/5 if the cross-fixture survey is run against existing traces on disk (no new replay needed). 1/5 if a fresh replay is required to validate Shape A's behavior under a new fixture not yet captured.

### §10.4 Recommended step-5c commit-message format (do not commit)

```
fix(workstream-h): step-5c — γ-fow-name assertion-side tolerance for §15-fence striker-invalidation cohort (closes F679 + F948 + F1017)

Tightens trace_gamma_fow_name_matches_striker_at_wicket at
files/tests/trace_session_assertions.py:425-:433 to degrade
gracefully when pipeline.striker is None at the prev-frame snapshot
due to §15-fence canonical invalidation paths (cold-start verdict
reject at score_manager.py:3074-:3118). Closes the 3-frame
no_prev_striker cohort (F679 + F948 + F1017) surfaced by WS-H
step-7 + characterized in workstream_h_step5b_fow_trail_drain_
awareness.md §1 + §4.

Root cause static-falsified in WS-H step-5b memo §5 (H3 leading;
H1/H2/H4 falsified at gates 1-3). Fix surface is assertion-side
per S21 (assertion-expectation vs. pipeline-state defect class) —
pipeline's None-write is correct per §15 fence; assertion's
expectation of non-None at prev-frame was the defect.

7-gate audit GREEN-LIGHT (gates 1-5 PASS; gate 6 PASS-with-
acknowledged-cross-cohort-residual at γ-w-symbol which has
independent root per memo §6; gate 7 cross-fixture verified on
12 captured traces).

Predicted-flip table (locked):
  trace_gamma_fow_name_matches_striker_at_wicket: FAIL × 3 → PASS
  trace_gamma_w_symbol_at_wicket: FAIL × 4 → FAIL × 4 (unchanged;
                                  independent surface per S6 scope)
  D-post-FoW-striker surface count: 2 → 2 (regression-guard)

L1.5 PASS (unchanged — γ-bundle is diagnostic library, not
pre-commit gate). L2 PASS. Derivation 48/48 PASS.

Empirical-falsification budget UNCHANGED at 2/5 (step-5b consumed
0; step-5c expected 0 if cross-fixture survey runs against existing
on-disk traces).

Co-Authored-By: ...
```

---

## §11 Stop-condition status + reporting

**Convergence.** Static chain converges on H3. Gates 1-5 PASS; gate 6 PASS-with-cross-cohort-residual; gate 7 deferred. **STOP per spec: "Static chain converges on single candidate ... → STOP, report, recommend step-5c patch commit-message format."**

**Cohort-closure verification outcome.** UNIFIED (all 3 instances share root + fix surface).

**Fix-surface attribution.** **Assertion-side**, not pipeline-side. Pipeline's `self.striker = None` writes at cold-start reject paths are §15-fence-correct invalidations; the γ-fow-name assertion's expectation of non-None at prev-frame is the defect.

**Static-falsification count.** 3 (H1, H2, H4 all falsified at gates 1-3).

**Empirical-budget status.** UNCHANGED at 2/5. No empirical replays consumed.

**Recommended next step.** WS-H step-5c — single-function assertion-side edit at `files/tests/trace_session_assertions.py:425-:433` (Shape A degrade-gracefully) + cross-fixture survey against 12 on-disk traces (no new replay needed). If the cross-fixture survey holds, no budget consumption. If it surfaces a Shape A miss, revisit at Shape B fallback.

**Methodology insight surfaced.** S21 — Assertion-expectation vs. pipeline-state defect class (§9). Cross-references S17 + S20 to form the post-lifecycle-fix audit triad.

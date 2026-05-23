# Workstream G — Cold-start transition-site catalogue

**Status.** Step-6 deliverable A (catalogue + observability matrix).
**Predecessor.** `workstream_g_shape_a_validation_addendum.md` (step-5
empirical falsification; gate-5 lifecycle gap identified).
**Sibling.** `workstream_g_cold_drain_surface_audit.md` (step-6
deliverable B — Surface A vs Surface B audit consumes this catalogue).
**Branch.** `obs/silent-wicket-absorption` (HEAD `5484cdb`).
**Empirical substrate.** `logs/trace/validate_shape_a_114349.jsonl`
(replay against `validate_dckkr_20260521_155356/scout_raw.jsonl` under
Shape A code f09fc38). 0/5 → 1/5 empirical-falsification budget already
consumed in step 5; this catalogue is observational over that trace.
**Pattern.** Mirrors `state_mutation_site_catalogue.md` C9 §7 column
structure. Insight #17 baked into §3 — every queue-wipe site must be
trace-tag observable, not just static-analysis-visible.

---

## §1 WARM→COLD transition sites

Grep performed: `self.mode = "COLD_START"` + `force_cold_start_recalibration`
+ `_handle_innings_change` reset paths in `files/score_manager.py`.
Four sites total.

### §1.1 W1 — `_handle_warm` overs-regress threshold

| Field | Value |
|---|---|
| Site | `score_manager.py:3859` |
| Trigger | `_overs_regress_streak >= _OVERS_REGRESS_THRESHOLD` (after consecutive overs regressions) |
| Pre-state | WARM with anomalous regress streak |
| Post-state | `mode="COLD_START"`, `_last_warm_state = self._snapshot()`, cold-state counters reset (`cold_candidate`, `cold_candidate_streak`, `cold_frames`, `_cold_pipeline_frames`, `_cold_last_viable`, `_stale_reject_count`, `_deferred_score`, `_overs_regress_*`, `_regression_streak`) |
| Trace tag at this site | **NONE** (log only: `"[SM] Overs regression … confirmed … re-entering COLD_START"`) |
| Step-5 trace fires | 0 detected |
| Wipe coverage | Does NOT call `_clear_per_innings_sm_surface`; queue persists |

### §1.2 W2 — `_handle_warm` cricket-rules stale-reject threshold

| Field | Value |
|---|---|
| Site | `score_manager.py:3919` |
| Trigger | `_stale_reject_count > 10` (10+ consecutive `validate_diff` rejections) |
| Pre-state | WARM with persistent reject streak |
| Post-state | `mode="COLD_START"`, `_last_warm_state = snapshot`, cold-state counters reset (subset of W1) |
| Trace tag at this site | **NONE** (log only: `"[SM] Too many consecutive rejections — re-entering COLD_START to re-calibrate"`) |
| Step-5 trace fires | 0 detected |
| Wipe coverage | Does NOT call `_clear_per_innings_sm_surface`; queue persists |

### §1.3 W3 — `force_cold_start_recalibration` external escape hatch

| Field | Value |
|---|---|
| Site | `score_manager.py:4103` |
| Trigger | External caller (pipeline POISON-guard residual) |
| Pre-state | Any state, including WARM |
| Post-state | `mode="COLD_START"`, full counter reset; `_last_warm_state = snapshot` IF `self.score is not None` |
| Trace tag at this site | **NONE** (log only: `"[SM] FORCE_COLD_START_RECALIBRATION: was … → COLD_START (reason=…)"`) |
| Step-5 trace fires | 0 detected (this trace doesn't reach the pipeline POISON escape) |
| Wipe coverage | Does NOT call `_clear_per_innings_sm_surface`; queue persists |

### §1.4 W4 — `set_innings_2` (`_handle_innings_change`)

| Field | Value |
|---|---|
| Site | `score_manager.py:4487` (inside `set_innings_2` at `:4280`) |
| Trigger | `_detect_innings_change` returns True (e.g., wickets regression from innings-1 final state) |
| Pre-state | WARM, end of an innings or innings-2 cold-init |
| Post-state | `self.__init__(shadow=shadow)` re-runs (line 4479) → default-inits ALL per-instance attributes including `_pending_post_wicket_cascade = []`; then `mode="COLD_START"`; restores `innings_history`, `scoreboard`, `innings=2`, `target`, `batting_team` |
| Trace tag at this site | `SM-INNINGS-2-RESET` (log emit auto-promoted; `known=False`) + `EVENT-BASELINE-RESET-INNINGS-2` (structured; `known=True` per KNOWN_TAGS) |
| Step-5 trace fires | **5 instances**: F462, F690, F801, F859, F992. Each carries `reason=wickets_regressed`. |
| Wipe coverage | **YES via `self.__init__()` re-run** — but the wipe is SILENT (no `POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START` tag fires). Insight #17 trap. |

**Aggregate WARM→COLD finding.** Four sites. **Zero** structured trace
tags announce the transition itself; W4 fires a structured tag but for
an adjacent semantic (`SM-INNINGS-2-RESET`), and its queue-wipe is
observationally indistinguishable from a no-op because no
`POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START` fires.

---

## §2 COLD→WARM transition sites

Grep performed: `self.mode = "WARM"` in `files/score_manager.py`.
Six sites total.

### §2.1 C1 — `_handle_cold_start` physics-promote path

| Field | Value |
|---|---|
| Site | `score_manager.py:2840` |
| Trigger | Cold-start candidate flip survives physics check (multi-ball-promote eligible) |
| Pre-state | COLD_START with `cold_candidate` + viable physics gap |
| Post-state | `_accept_initial(_candidate_for_seed, frame)` then `mode="WARM"`; then synth ball-events fire via the explicit dispatch at `:2862` |
| Trace tag at this site | `COLD-START-PHYSICS-PROMOTE` (structured; `known=True`) fires at `:2820` BEFORE the mode flip |
| Step-5 trace fires | 0 detected |
| Wipe coverage | None (cold→warm shouldn't wipe queue; if queue is non-empty here, drain has an opportunity) |

### §2.2 C2 — `_handle_cold_start` give-up path (with last-warm reference)

| Field | Value |
|---|---|
| Site | `score_manager.py:2905` |
| Trigger | `cold_frames >= max_f` (where `max_f = COLD_MAX_FRAMES_WITH_REF` if `_last_warm_state` else `COLD_MAX_FRAMES`); validate_absolute passes; `_cold_start_plausible(card)` passes |
| Pre-state | COLD_START exhausted, give-up adoption |
| Post-state | `_accept_initial(card, frame)` then `mode="WARM"`; `_maybe_synthesize_cold_start_gap()` runs |
| Trace tag at this site | **NONE** (log only: `"[SM] COLD_START → WARM (max frames, ref cleared) …"`) |
| Step-5 trace fires | 0 detected |
| Wipe coverage | None |

### §2.3 C3 — `_handle_cold_start` give-up path (second branch)

| Field | Value |
|---|---|
| Site | `score_manager.py:2941` |
| Trigger | Symmetric to C2 but inside the consensus-fail branch (`not _cold_start_plausible(card)` → reset candidate → second max-frames check) |
| Pre-state | Same as C2 |
| Post-state | Same as C2 |
| Trace tag | **NONE** (log only — same message as C2) |
| Step-5 trace fires | 0 detected |
| Wipe coverage | None |

### §2.4 C4 — `_handle_cold_start` consensus reached

| Field | Value |
|---|---|
| Site | `score_manager.py:2950` |
| Trigger | `cold_candidate_streak >= COLD_START_CONSENSUS_FRAMES` AND `_cold_start_plausible(card)` |
| Pre-state | COLD_START, consensus achieved |
| Post-state | `_accept_initial(card, frame)` then `mode="WARM"`; `_maybe_synthesize_cold_start_gap()` runs |
| Trace tag | **NONE** (log only: `"[SM] COLD_START → WARM (consensus …)"`) |
| Step-5 trace fires | 0 detected — but the SIBLING `INN2-COLD-START-CONSENSUS` (known=True) fires × 2 from the inn2 sub-branch |
| Wipe coverage | None |

### §2.5 C5 — `_cold_start_maybe_pipeline_fallback` watchdog-forced

| Field | Value |
|---|---|
| Site | `score_manager.py:2993` |
| Trigger | `_cold_pipeline_frames >= _cold_pipeline_fallback_starvation` (starvation watchdog) OR `_cold_pipeline_frames >= _cold_pipeline_fallback_after AND cold_frames >= COLD_MAX_FRAMES` (heavy-flip watchdog); plus `_cold_start_plausible(snap)` |
| Pre-state | COLD_START with no consensus reachable |
| Post-state | `_accept_initial(snap, frame)`; `cold_candidate=None`, `cold_candidate_streak=0`; `mode="WARM"` |
| Trace tag | `COLD-START-FORCED-RECOVER` (log emit auto-promoted; `known=False`) at `:2981` BEFORE the mode flip |
| Step-5 trace fires | **5 instances**: F544, F739, F843, F946, F1062 |
| Wipe coverage | None — pre-condition: queue may still hold entries enqueued before the cold entry |

### §2.6 C6 — `_handle_hot_resume` from cache

| Field | Value |
|---|---|
| Site | `score_manager.py:3263` |
| Trigger | Hot-resume cache present + warm-restart eligible |
| Pre-state | Fresh init from cache (cold→warm semantically, but startup-only) |
| Post-state | `mode="WARM"`; counters reset |
| Trace tag | **NONE** (log only: `"[SM] HOT-RESUME from cache …"`; the sibling `EVENT-BASELINE-SEEDED-HOT-RESUME` is registered but conditional) |
| Step-5 trace fires | 0 detected (no hot-resume in replay) |
| Wipe coverage | None |

**Aggregate COLD→WARM finding.** Six sites. Two have structured trace
emissions (C1 `COLD-START-PHYSICS-PROMOTE`, C5 `COLD-START-FORCED-
RECOVER` auto-promoted), four are log-only. **No site invokes any
drain on the cold→warm boundary** — by design, drains are inside the
WARM frame loop, not at the transition.

---

## §3 Reset-path coverage matrix

Per insight #17, columns (a)–(e) must each be empirically traceable in
the validation trace, not derivable from `__init__` re-runs alone.

### §3.1 WARM→COLD coverage

| Site | (a) `_clear_per_innings_sm_surface`? | (b) Trace tag fires? | (c) Wipes `_pending_post_wicket_cascade`? | (d) Wipes `_pending_bowler_ball_credits`? | (e) Wipes `_over_archive_pending`? |
|---|---|---|---|---|---|
| W1 (`:3859`) | NO | NO (log-only) | NO (queue persists) | NO | NO |
| W2 (`:3919`) | NO | NO (log-only) | NO | NO | NO |
| W3 (`:4103`) | NO | NO (log-only) | NO | NO | NO |
| W4 (`:4487` via `set_innings_2`) | NO (uses `__init__` re-run instead) | YES — `SM-INNINGS-2-RESET` + `EVENT-BASELINE-RESET-INNINGS-2` | YES (silent — `__init__` default-inits to `[]`) | YES (silent) | YES (silent) |

**Critical findings.**

1. **W1/W2/W3 do not wipe the queue at all.** A cascade enqueued just
   before these transitions persists through the cold window and
   could be drained on the cold→warm side (if a drain path exists).
2. **W4 wipes via `__init__` BUT silently** — no
   `POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START` fires. This is
   the audit §2.5 gate-5 mis-attribution that step 5 falsified.
   Insight #17: the wipe is observationally indistinguishable from
   no-wipe in `trace_eta`.

### §3.2 COLD→WARM coverage

COLD→WARM sites do NOT wipe by design; they are drain-opportunity
sites. Columns (a)–(e) are universally NO. The relevant matrix is
drain reachability in §4.

---

## §4 Drain-hook reachability matrix

Per Shape A wiring (f09fc38): `_attempt_pending_cascade_drain` is
invoked only from `_handle_warm` at the top of every warm frame
(`score_manager.py:3357` in the post-commit file).

| Caller | Reached during COLD frames? | Reached during transition frames? | Reached during WARM frames? |
|---|---|---|---|
| `_attempt_pending_cascade_drain` | NO | NO | YES (every warm frame) |
| `_attempt_pending_archive_drain` (mirror site) | NO | NO | YES (when `_over_archive_pending` is set) |
| `_try_resolve_pending` (pending extra / wicket) | NO | NO | YES |
| `_identify_and_set` | NO | NO | YES |

**Aggregate finding.** All four warm-frame consumers (drain hooks +
identity resolution) are mode-gated on `_handle_warm`. The mirror
site `_attempt_pending_archive_drain` has the same structural gap —
this is not specific to the cascade scaffold. Per `_handle_warm:3357`
the archive drain depends on `_over_archive_pending`, which is set
via warm-only code paths — so the archive gap is latent but not yet
manifested empirically.

The mirror site's pattern is what step 2 audit §1.4 modeled Shape A
against; the model held in the audit's mental trace where SM stays
WARM after wicket-commit. Step 5 empirics show that assumption fails.

---

## §5 Cross-workstream coupling sites

Workstream G has three parent issues per HANDOFF §17.3:

1. **Item 1 (Shape A).** Scout extraction timing at wicket-commit
   frames. Addressed by f09fc38 enqueue path; drain path falsified
   in step 5.
2. **Item 2.** Cold-start re-entry frequency root cause (12
   COLD-START-EXIT fires in dump per HANDOFF — that count refers to
   pre-Shape-A traces; step-5 replay shows 5× `SM-INNINGS-2-RESET` +
   5× `COLD-START-FORCED-RECOVER` = 10 re-entries).
3. **Item 3.** `COLD-START-EXIT` semantics redesign per §14.5.2 of
   `differential_testing_methodology_design.md`.

### §5.1 Item 1 ↔ Item 2 coupling

W4 (`SM-INNINGS-2-RESET`, 5 fires in step-5 trace at F462, F690, F801,
F859, F992) is the dominant WARM→COLD path on this dump. Its trigger
is `reason=wickets_regressed`. The wicket-counter regress is induced
by the bad-Scout-read window post-wicket: between F680 and F708 the
strip carries junk content (per step-1 §3.3 evidence), so the
scoreboard's accumulated `wickets` field gets reset by the SM's
`_detect_innings_change` → `wickets_regressed`.

**This is the cold-start re-entry root cause manifesting concretely.**
Item 2 is not a separate phenomenon — it's the cold-start frequency
caused by the same broadcast-strip-render-lag root that drives the
G2 enqueue scenarios.

### §5.2 Item 2 ↔ Item 3 coupling

The `SM-INNINGS-2-RESET` tag fires for both **legitimate** innings-2
transitions AND **erroneous** wickets-regressed-mid-innings-1
transitions. Both call `set_innings_2`, both go through `__init__`
re-run, both silently wipe the queue. Tag bifurcation per §14.5.2
would split:

- `SM-INNINGS-2-RESET reason=natural` — innings actually concluded
- `SM-INNINGS-2-RESET reason=wickets_regressed` — false positive
  triggered by Scout misread (Workstream G primary target)

The second class is what's wiping the cascade queue in this trace.

### §5.3 Cross-workstream scope statement

This catalogue documents **all** transition sites for Item 2 / Item 3
investigation. Surface A vs Surface B audit in step-6 deliverable B
operates strictly within the existing transitions (does not redesign
them). A future workstream addressing Item 2 root cause may need to
modify the `_detect_innings_change` predicate (`score_manager.py`
caller of `set_innings_2`) to reject `wickets_regressed` triggers
post-wicket-commit within a hot window.

---

## §6 Bottom-line empirical findings (insight #17 closure)

Per the step-5 brief's insight #17 mandate — every reset path
empirically verified against `validate_shape_a_114349`:

| Reset path | Static-visible | Empirically observed in step-5 trace | Structured-tag-fires |
|---|---|---|---|
| `__init__` (constructor) | Yes | Yes (session-init) | No tag at init time |
| `_clear_per_innings_sm_surface` direct call | Yes | **NO** — called only from `full_reset`; `full_reset` callers (`stuck_tracker_*` at `:3672 / :3683`) never fire in step-5 trace | No tag fires |
| `full_reset` → `_clear_per_innings_sm_surface` | Yes | NO | No (would emit `POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START` per Shape A wiring) |
| `set_innings_2` → `__init__` body re-run | Yes | YES × 5 (F462, F690, F801, F859, F992) | `SM-INNINGS-2-RESET` + `EVENT-BASELINE-RESET-INNINGS-2` (but NEITHER includes the queue-wipe attestation) |
| `force_cold_start_recalibration` | Yes | NO (this trace) | No |
| W1 overs-regress | Yes | NO (this trace) | No |
| W2 stale-reject | Yes | NO (this trace) | No |

**The gate-5 lifecycle gap is now characterized.** The Shape A audit
assumed `_clear_per_innings_sm_surface` was the cold-start wipe
site, anchored on `full_reset` as the caller. Empirically the
dominant cold-start re-entry path in this regime is `set_innings_2`
which bypasses `_clear_per_innings_sm_surface` entirely and wipes via
the `__init__` body — silent in trace.

Two of the four WARM→COLD sites (W1, W2) do not wipe the queue at
all, leaving cascades persistent across the cold window. The mirror
site `_attempt_pending_archive_drain` has the same structural mode-
gating gap; not yet manifested because the archive path's queue is
typically empty by the time cold-start fires.

This catalogue is the substrate for the Surface A vs Surface B audit
in step-6 deliverable B.

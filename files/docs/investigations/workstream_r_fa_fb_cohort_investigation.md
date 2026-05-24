# Workstream R — F-A-commit-lag + F-B-ad-occlusion cohort investigation (step-1)

**Date.** 2026-05-24.
**Branch.** `derive-not-detect` @ HEAD = `80aa01b` (WS-Q step-3 arc close-out).
**Validated baseline.** 34 divergences (post-WS-Q step-2d).
**Outcome.** **RA LEADING with caveat — bowler-card-lifecycle-never-invoked is the shared root; "ad-occlusion" classifier label is empirically a misnomer on this post-WS-Q residue.** **S9-strict 4th-instance CANDIDATE** if step-2 patch closes both F-A + F-B simultaneously. Recommended next step: **step-1b instrumentation** (NO-OP log-only) to confirm why BOWLING-CARD-CREATED never fires on dckkr-264 replay; step-2 patch design depends on that root attribution.

---

## §1 Empirical anchor — per-divergence frame table (S35 methodology applied FIRST)

Baseline source: `files/tests/baselines/dckkr_diff_post_ws_q_step2d_baseline.md`. Trace source: `logs/trace/dckkr_post_ws_q_step2d_20260524_172440.jsonl`. Snapshot source: `/tmp/dckkr_post_ws_q_step2d_snapshots.jsonl`. Scout dump source: `files/logs/deliveries/watch_20260519_121701/scout_raw.jsonl`.

| over.ball | F-A? | F-B? | Pipeline bowler_name | Pipeline bowler_overs | Pipeline bowler_runs | GT bowler_name | GT bowler_overs | GT bowler_runs |
|---|---|---|---|---|---|---|---|---|
| 0.6 | ✓ | ✓ | None | None | 0 | Roy | 1.0 | 7 |
| 1.6 | ✓ | ✓ | None | None | 0 | Arora | 1.0 | 10 |
| 2.6 | ✓ | ✓ | None | None | 0 | Roy | 2.0 | 18 |
| 3.1 | ✓ | ✓ | None | None | 0 | Narine | 0.1 | 1 |
| 3.6 | ✓ | ✓ | None | None | 0 | Narine | 1.0 | 11 |
| 4.1 | ✓ | ✓ | None | None | 0 | Tyagi | 0.1 | 4 |
| 4.2 | ✓ | ✓ | None | None | 0 | Tyagi | 0.2 | 5 |
| 4.3 | ✓ | ✓ | None | None | 0 | Tyagi | 0.3 | 5 |
| 4.4 | ✓ | ✗ | **Tyagi** | **0.2** | 1 | Tyagi | 0.4 | 6 |
| 4.5 | ✓ | ✗ | **Tyagi** | **0.3** | 5 | Tyagi | 0.5 | 10 |

**Empirical observations.**
- **F-A and F-B co-occur at 8/8 F-B frames (100% co-occurrence).** F-A has 2 additional frames at 4.4 + 4.5 where bowler_name is populated ('Tyagi') but bowler_overs lags by 2 balls (0.2/0.3 vs GT 0.4/0.5).
- **Pipeline bowler_name is None across 8 consecutive boundary frames (0.6-4.3)** spanning 4 actual bowler changes (Roy → Arora → Roy → Narine → Tyagi).
- **`bowler_runs` (unclassified surface) shares the same per-frame pattern** — 0 across the 8 F-B frames; 1/5 vs GT 6/10 at 4.4-4.5 (consistent lag with bowler_overs).
- **Three separate fields (bowler_name F-B, bowler_overs F-A, bowler_runs unclassified) all diverge at the same over.ball positions** — strong cascade signal indicating shared upstream root.

---

## §2 F-A predicate behavior analysis

**Classifier rule** (per `files/scripts/replay_diff_harness.py:120-121`): any `bowler_overs` divergence → F-A-commit-lag.

**Runbook §7 description** (`files/docs/operations/differential_testing_runbook.md`): "MISSING-BALL on prev-over bowler + extra ball on next-over bowler at over-boundary."

**Empirical lag amount per frame.**
- 0.6, 1.6, 2.6, 3.1, 3.6, 4.1, 4.2, 4.3 (8 frames): full MISSING — bowler_overs is None.
- 4.4, 4.5 (2 frames): bowler_overs present but lagged by **2 legal balls** (0.2 vs 0.4; 0.3 vs 0.5). Tyagi's first 2 balls (4.1 + 4.2 in GT, 0.1 + 0.2 in Tyagi's per-bowler count) were not committed to bowler_overs.

**Pattern.** All F-A divergences are pipeline showing UNDER-COUNTED bowler progress (or no progress). No F-A frame shows pipeline > GT. Predicate behavior is asymmetric: F-A surfaces commit-lag direction only.

---

## §3 F-B predicate behavior analysis

**Classifier rule** (per `replay_diff_harness.py:118-119`): any `bowler_name` divergence → F-B-ad-occlusion.

**Runbook §7 description**: "Entire over's `bowler_name` DIVERGENT."

**Empirical ad-occlusion analysis on dckkr-264 capture.**

Camera-view distribution across all 264 scout records (parsed from `raw_response`):
- closeup: 98 (37%)
- bowlers_end: 102 (39%)
- graphic: 43 (16%)
- other: 11 (4%)
- **ad: 5 (1.9%)** ← only 5 ad frames in entire capture
- between_play: 3 (1%)
- side_on: 2 (1%)

Frame-phase distribution:
- between_play: 163 (62%)
- graphic: 43 (16%)
- release: 29 (11%)
- shot: 11 (4%)
- **advertisement: 4 + ad: 1 = 5 (1.9%)**
- post_shot/flight/other: 13 (5%)

**Verdict.** "Ad-occlusion" classifier label is **empirically a misnomer** on this post-WS-Q residue. 5 ad frames cannot explain 8 F-B divergence frames spanning bowler changes Roy → Arora → Roy → Narine → Tyagi. The 8 F-B frames are at over-boundary positions (X.6 or X.1) where bowler transitions, not ad-windows.

---

## §4 Cascade hypothesis verification (S9-strict test)

**Co-occurrence test.** For each F-A frame, look for adjacent F-B-ad-occlusion within K=0 frames (same over.ball). For each F-B frame, look for downstream F-A within K=0 frames.

| Direction | Co-occurrences | Total target frames |
|---|---|---|
| F-A → F-B at same over.ball | 8/10 (8 of 10 F-A frames co-occur with F-B) | 10 |
| F-B → F-A at same over.ball | 8/8 (100%) | 8 |

**Verdict.** **Cascade hypothesis EMPIRICALLY ANCHORED at 8/8 F-B coverage + 8/10 F-A coverage.** The 2 F-A frames without F-B co-occurrence (4.4 + 4.5) are within the same WARM-mode + bowler-known window — they represent a **bowler_overs lag at the per-ball-credit downstream**, while 0.6-4.3 represent a **bowler_name + bowler_overs joint failure at the canonical bowler-card establishment upstream**.

**Sub-cohort partition empirically suggested.**
- **Sub-cohort RA-1 (8 frames; 0.6 + 1.6 + 2.6 + 3.1 + 3.6 + 4.1 + 4.2 + 4.3):** bowler_name = None + bowler_overs = None co-occurring with bowler_runs = 0. **Root: BOWLING-CARD-CREATED never fires on this fixture (canonical bowler-card lifecycle absent).**
- **Sub-cohort RA-2 (2 frames; 4.4 + 4.5):** bowler_name = 'Tyagi' (populated from downstream extractor surface), but bowler_overs / bowler_runs lagged by 2 balls. **Root: per-ball credit pathway disconnected from the established bowler context for Tyagi's first 2 balls.**

Both sub-cohorts have a SHARED upstream contributing factor (bowler lifecycle not via canonical write paths), but distinct downstream failure modes.

---

## §5 Write-site attribution

### §5.1 BOWLING-CARD-CREATED canonical write-site (sub-cohort RA-1)

Trace inspection: **BOWLING-CARD-CREATED tag count = 0** across the full 264-frame dckkr-264 trace. BOWLING-CARD-RESUMED count = 0. BOWLER-LOCK count = 5 (suggests some bowler-tracking activity but no card creation).

Production write-site:
- Tag registered in `trace_emitter.py:63` (`BOWLING-CARD-CREATED`) + `:64` (`BOWLING-CARD-RESUMED`).
- Production emission grep: deferred to step-1b (requires reading `score_manager.py` for the conditional firing rules + Scoreboard.update_bowler path).

**Hypothesis-of-mechanism (NOT yet empirically validated; defer to step-1b instrumentation):**
- Pipeline reaches WARM mode (190 frames) but **canonical bowling-card initialization is gated by a condition not satisfied on dckkr-264** — likely Scout extractor must surface bowler_name in a structured field that this short capture doesn't carry.
- Alternative: BOWLING-CARD-CREATED requires `frame_count >= N` consensus OR specific frame_phase pattern absent from the short capture.

### §5.2 bowler_runs UNDER-COUNT (sub-cohort RA-2)

Snapshot evidence: at 4.4 pipeline shows `bowler_runs=1`; GT shows `bowler_runs=6`. The 4-run gap is Tyagi's first 2 ball deliveries (over 4 ball 1 + ball 2 in GT credit 4 + 5 runs = 9 runs combined, while pipeline at 4.4 shows 1 run = third-ball-only). Pipeline's bowler_runs incremented from 4.3 (5 runs) to 4.4 (1 run) — that's a RESET, not an increment.

Possible mechanism: bowler context switched mid-over (Tyagi attribution reset on a frame where ad/graphic occluded the canonical card). Defer to step-1b.

### §5.3 Cross-module wiring (deferred)

- `score_manager.py:_increment_bowler_wickets` at `:834`; uses `scoreboard.update_bowler` at `:846`.
- 6+ other `scoreboard.update_bowler` call sites at `:2753 / :6308 / :6546 / :6626` (per Grep results).
- Cross-module wiring + which call-site fires when is the load-bearing piece for step-2 patch design. Defer.

---

## §6 Hypothesis enumeration

### RA — F-A and F-B share architectural surface (bowler-card lifecycle root)

- **Mechanism.** BOWLING-CARD-CREATED canonical lifecycle never fires (or fires too late) on this fixture. Both F-B (bowler_name=None) and F-A (bowler_overs=None) cascade from the same upstream defect.
- **§7.2 gate-1.** PASS — addresses shared root.
- **§7.2 gate-2.** PASS — fix surface is the canonical bowler-card-creation path in `score_manager.py` / `scoreboard.py`.
- **§7.2 gate-3.** PARTIAL — fix surface architecturally clear (BOWLING-CARD-CREATED predicate); per-ball credit pathway needs separate analysis for RA-2 sub-cohort.
- **Cohort-closure prediction.** F-A 10 → 0-2; F-B 8 → 0-2; cascade closure 16-18 rows under shared-root fix.
- **Status.** **LEADING.** Empirical co-occurrence + zero canonical-tag firings + low ad-frame count (5/264) point to shared bowler-lifecycle root.

### RB — F-A and F-B are orthogonal

- **Mechanism.** F-A is per-ball-credit commit-lag (e.g., Scoreboard.update_bowler timing); F-B is canonical-bowler-card-establishment latency (e.g., card creation requires multi-frame consensus). Different roots.
- **§7.2 gate-1.** PARTIAL — would require two separate fixes.
- **§7.2 gate-2.** PASS — both fixes are at canonical surfaces, but disjoint.
- **§7.2 gate-3.** PASS — both fix surfaces enumerable.
- **Cohort-closure prediction.** F-A 10 → variable; F-B 8 → variable; closure non-cascade.
- **Status.** **FALSIFY** at gate-1 — the 8/8 F-B co-occurrence with F-A and the joint None-state pattern (bowler_name + bowler_overs + bowler_runs all 0/None at same frames) is incompatible with orthogonal roots.

### RC — F-A and F-B partially share (sub-cohort partition)

- **Mechanism.** RA-1 (8 frames; 0.6-4.3) has shared root = BOWLING-CARD-CREATED never fires. RA-2 (2 frames; 4.4-4.5) has distinct root = per-ball credit pathway disconnected from established bowler context.
- **§7.2 gate-1.** PASS — RC is actually more empirically anchored than RA (which assumes single fix closes both sub-cohorts).
- **§7.2 gate-2.** PASS — RA-1 fix targets card-creation predicate; RA-2 fix targets per-ball credit wiring.
- **§7.2 gate-3.** PASS — both fix surfaces at canonical surfaces.
- **Cohort-closure prediction.** RA-1 fix closes 8 F-B + 8 F-A frames (sub-cohort RA-1); RA-2 fix closes 2 F-A frames (sub-cohort RA-2). Joint closure: 18 of 18 cohort rows.
- **Status.** **EMPIRICALLY ANCHORED but architecturally less elegant than RA.** Two fixes needed but each targets a distinct write-site.

### RD — Root is upstream of pipeline (Scout VLM cadence)

- **Mechanism.** Scout extractor doesn't surface bowler_name in structured form on this fixture; downstream pipeline can't establish bowler card.
- **§7.2 gate-1.** PARTIAL — would fix at Scout extractor / parse_strip layer, OUTSIDE pipeline scope.
- **§7.2 gate-2.** FAIL — Scout layer is the corroboration source per "broadcast IS the corroboration" directive; modifying Scout extraction is out of WS-R scope.
- **§7.2 gate-3.** FAIL — fix surface outside pipeline.
- **Status.** **FALSIFY** at gate-2 + gate-3.

### RE — Cohort-split with multiple roots

- Combines RC + additional unknown roots. Speculative without step-1b empirical evidence.
- **Status.** **FALSIFY (speculative)** — RC adequately partitions; RE adds no anchor.

---

## §7 §7.2 audit on leading candidate (RA / RC mixed verdict)

Leading verdict: **RC empirically (sub-cohort partition) with RA as architectural-cleanup variant.** Gates 1-5:

1. **Defect-class fit:** PASS — both sub-cohorts target bowler-state canonical surfaces.
2. **Backward-compat:** PASS — fix at bowler-card creation + per-ball credit pathway preserves canonical bowler-state semantics; L2 30/30 unaffected.
3. **Fix-surface attribution:** PIPELINE-DIRECT — both sub-cohorts in `score_manager.py` + `scoreboard.py:update_bowler` chain. Defer per-site enumeration to step-1b.
4. **Equivalence proof:** DEFER to step-2 (predicate + fix exact form needs step-1b empirical data).
5. **State lifecycle:** PASS — bowling_card lifecycle is canonical state owned by `Scoreboard.bowling_card`; no §15 fence interaction; no WS-G PendingCascade interaction.
6. **Predicted flip:** RA-1 fix → -16 rows (8 F-B + 8 F-A at 0.6-4.3); RA-2 fix → -2 rows (4.4 + 4.5 F-A); joint → -18 rows; diff baseline 34 → 16.
7. **Cross-fixture gate:** DEFER. WS-Q step-2c.5 cross-fixture audit observed Bowler-W-credit-failure on larger captures (7 on dckkr-749; 13 on dckkr-618) — bowler-domain residue scales with capture. Cross-fixture verification at step-2c or step-3 close-out.

---

## §8 Predicted-closure prediction

| Sub-cohort | Mechanism | Frames | Predicted closure |
|---|---|---|---|
| RA-1 (bowler-card lifecycle absent) | BOWLING-CARD-CREATED never fires; bowler_name/overs/runs all None | 0.6 / 1.6 / 2.6 / 3.1 / 3.6 / 4.1 / 4.2 / 4.3 | 16 rows (8 F-A + 8 F-B) |
| RA-2 (per-ball credit pathway disconnect) | bowler_name='Tyagi' present but bowler_overs/runs lagged | 4.4 / 4.5 | 2 rows (F-A only) |
| **Joint** | **Both fixes at canonical bowler-state surfaces** | **All 18 cohort rows** | **-18 rows (34 → 16)** |

bowler_runs unclassified surface (10 frames at same positions) is likely cascade-closed by RA-1 + RA-2 fixes (same root). If so, joint closure exceeds 18 rows.

Per-batter-ledger-drift was already closed via WS-Q cascade — no overlap expected.

---

## §9 Regression-guard enumeration

Standard contract for step-2 patch:
- L2 30/30 PASS preserved.
- L1.5 broader 619 PASS preserved + step-2 adds 2-5 new cases.
- 9 closed surfaces stay 0.
- Other 5 active surfaces (G-pipeline-lag / Recent-overs-drop / unclassified non-bowler rows) UNCHANGED.
- All shipped defensive gates landed:
  - PA WARM-mode magnitude gate
  - Shape A pending-cascade
  - D1 bowler em-dash sentinel + D2-Layer-1a broadcast-vs-deterministic
  - H1 team-changed consensus-parity
  - H3 γ-fow-name graceful-degradation
  - OA cold-start magnitude gate
  - sm.set_score canonical API + WS-Q step-2c regression-rejection predicate (cricket-physics + confidence)
- A1 event-firing defense at `score_manager.py:3828` (`_event_baseline_score`) preserved (FA already retired at WS-Q step-2d).

---

## §10 Step-2 vs step-1b recommendation

**Recommendation: STEP-1B INSTRUMENTATION FIRST.**

Static evidence converges on RC (sub-cohort partition with RA-1 + RA-2 roots) BUT the load-bearing piece — **why BOWLING-CARD-CREATED never fires on dckkr-264** — is NOT empirically attributable from static reading alone. Step-2 patch design requires:

1. **Step-1b NO-OP instrumentation patch** (S33 pattern):
   - Add log-only emission at each branch of bowling-card-creation predicate in `score_manager.py`.
   - Re-run dckkr-264 replay; observe which branch returns early.
   - 5-10 LOC instrumentation; flag-gated.
2. **Cross-fixture spot-check** on dckkr-749 + dckkr-618: do those captures fire BOWLING-CARD-CREATED? If yes, the dckkr-264 capture is below-threshold for the predicate; if no, the predicate has a structural defect.
3. **Step-2 patch design** informed by step-1b empirical attribution.

**Alternative (lower-cost): step-2 with broader fix-surface hypothesis.** If user prefers single-commit progress + accepts iteration risk: hypothesize the BOWLING-CARD-CREATED predicate's frame-count threshold is too restrictive; lower it; observe. But this is S35-vulnerable (mechanism walkthrough without empirical anchor). Step-1b is methodology-recommended.

**S9-strict 4th-instance candidate FLAGGED.** If step-2 lands a single architectural fix that closes both F-A + F-B + bowler_runs unclassified (all bowler-state surfaces), WS-R becomes the 4th instance of "architectural cure closes multiple defect classes simultaneously" (F1 + S18 + WS-Q + WS-R). Per WS-Q step-3 close-out, S9-strict was promoted on 3-instance evidence — 4th instance would corroborate the methodology further. Cross-reference at step-3 close-out if cascade closure holds.

**Audit caveat for next session.** The 264-frame dckkr capture is dominated by pipeline-lag artifacts: 94 of 122 GT balls are missing-in-pipeline (overs 4.6 onwards entirely missing). The "34-row residue" includes 18 bowler-cohort rows that may be artifacts of the short-capture / pipeline-not-caught-up state. Cross-fixture validation on a fuller capture (dckkr-749, gtrr) is recommended before step-2 patch commit ships.

---

## §11 Report-back summary

- Memo path: `files/docs/investigations/workstream_r_fa_fb_cohort_investigation.md`
- Section count: 11 (§1-§11).
- Per-divergence empirical anchor table: 10 F-A + 8 F-B frames documented (§1).
- F-A predicate behavior: `bowler_overs` divergence; asymmetric under-count direction; lag 2-balls on 2 frames + full-MISSING on 8 frames (§2).
- F-B predicate behavior: `bowler_name` divergence; **classifier label "ad-occlusion" empirically a misnomer** on this residue (only 5 ad frames in 264; 8 F-B at non-ad boundary frames) (§3).
- Cascade hypothesis verdict: **EMPIRICALLY ANCHORED — 8/8 F-B co-occur with F-A; 8/10 F-A co-occur with F-B**; sub-cohort partition (RA-1 8 frames + RA-2 2 frames) (§4).
- Write-site attribution: **BOWLING-CARD-CREATED count = 0** in dckkr-264 trace (canonical bowler-card lifecycle never fires); per-ball credit pathway disconnect at 4.4-4.5 (§5).
- Hypothesis count: 5 (RA / RB / RC / RD / RE).
- Leading candidate: **RC empirically (sub-cohort partition with RA-1 + RA-2 roots) — RA as architectural-cleanup variant if single fix closes both sub-cohorts.**
- Static-falsification count: 3 (RB gate-1 / RD gate-2-3 / RE speculative).
- Predicted-closure prediction: -18 rows (34 → 16); bowler_runs unclassified surface likely cascade-closed.
- **Step-2 vs step-1b recommendation: STEP-1B INSTRUMENTATION FIRST.** S33 NO-OP instrumentation pattern; lowers patch risk per S35 lesson.
- S9-strict 4th-instance candidate **FLAGGED** for step-3 close-out cross-reference.
- Working tree state: docs-only memo at this commit; no production code touched.

# Workstream K — Phantom-wicket state-machine investigation (step-1)

**Date.** 2026-05-23.
**Branch.** `derive-not-detect` @ HEAD = `a4f91f5` (Surface E retirement docs).
**Empirical-budget status.** 2/5 — UNCHANGED (static-only this step).
**Outcome.** **WS-K state-machine layer ALSO STATICALLY FALSIFIED.** State-machine signal stack derives from the same Scout-OCR source as detection-layer signals; the OCR-noise-uniformity finding from Surface E §15 GENERALIZES upward — F1017 phantom is structurally undiscriminable from genuine cohort across BOTH detection and state-machine layers within the current Scout primitive set. **Five candidates (KA / KB / KC / KD / KE) statically falsified at gate 1; KF (external Cricbuzz-commentary corroboration) requires architectural pivot beyond Phase 1 scope; KG (cohort-split) unavailable on single-instance cohort.** Recommendation: **accept-and-document-known-limitation** — F1017 retires as architectural-known-defect (Surface E `a4f91f5` framing VALIDATED by WS-K step-1 convergence). Candidate S27 surfaced: **multi-layer falsification convergence** — when sequential investigation layers all falsify on shared signal source, the defect class is structurally beyond current pipeline scope; continued layer-search is methodology waste.

---

## §1 Empirical anchor — F1017 frame reconstruction + at-crease-pair stability across cohort

**Phantom F1017 window** (verbatim from `files/logs/deliveries/validate_dckkr_20260521_155356/scout_raw.jsonl` STRIP parsing):

| Frame | Striker slot | Non-striker slot | Wickets | Overs |
|---|---|---|---|---|
| F1015 | null | null | 6 (OCR spike) | 10.4 |
| F1016 | (strip absent) | (absent) | 4 (regression) | 10.4 |
| **F1017** | **AXAR 1*(1)** | **STUBBS 2*(4)** | 5 | 10.5 |
| F1018 | (strip absent — noisy) | (absent) | 5 | 10.5 |
| F1019 | **AXAR 1(2)** | **STUBBS 4(4)** | 5 | 10.5 |
| F1020-F1025 | null | null | null (strip lost) | null |

**Critical state-signal observation.** Strip at-crease pair (AXAR / STUBBS) PERSISTS across F1017-F1019 — there is NO walk-off, NO new batter arriving in the strip OCR. By cricket-truth, this is correct (no wicket actually occurred). But this signal is identical to what we observe at genuine wickets (see §1.2 below).

### §1.1 Genuine wicket cohort at-crease comparator

**F400 (Rahul ov 5.0 — genuine wicket per cricket-truth):**

| Frame | Striker | Non-striker | Note |
|---|---|---|---|
| F398-F399 | null | null | (pre-wicket noisy) |
| **F400** | **PATHUM 26(16)** | **RAHUL 23(14)** | Wicket commit frame; both shown at-crease |
| F401 | PATHUM 26(16) | RAHUL 23(14) | Strip persists with dismissed batter still shown |
| F402-F409 | null/noisy | null/noisy | Strip lost during walk-off |
| F410 | KL RAHUL 23(14) | null | Strip RE-SHOWS Rahul as striker post-dismissal (OCR pickup of FoW or batsmen-list panel) |

**F855 (Nissanka ov 9.5 — actually Rizvi-dismissed per WS-D cricket-truth):**

| Frame | Striker | Non-striker | Note |
|---|---|---|---|
| F853 | PATHUM 46(28) | RIZVI 3(6) | Pre-wicket at-crease pair |
| F854 | PATHUM > RIZVI 46(28) | null 3(6) | Strip rotation transient |
| **F855** | **PATHUM 46(28)** | **RIZVI 3(7)** | Wicket commit frame; both still shown at-crease |
| F856 | null | null | strip absent |
| F857 | PATHUM 46(28) | RIZVI 3(7) | Strip persists with dismissed batter |
| F858-F862 | null/noisy | null/noisy | Walk-off lag |

**Pattern observed across BOTH phantom and genuine cohorts.** The strip's at-crease pair PERSISTS at the dismissed batter for MULTIPLE frames after the wicket-event (in genuine cases) AND for multiple frames when no wicket occurred (in the phantom case). The walk-off lag in genuine cases is structurally identical to the at-crease persistence in phantom cases — both share the same OCR snapshot semantics of "the strip lags physical reality by 5-30 seconds (300-1800 frames at 60fpm)."

**Critical implication for KC.** "At-crease-pair-change within K frames" cannot discriminate phantom from genuine because BOTH cohorts exhibit multi-frame at-crease persistence. The signal is OCR-derived; OCR snapshots show the same strip state regardless of cricket-truth.

---

## §2 State-machine signal enumeration at `apply_wicket_event` entry

`files/score_manager.py:846-905` — canonical wicket-dispatch path inputs:

| Signal | Source | Multi-frame-resilient? | OCR-derived? |
|---|---|---|---|
| `event.dismissed_batter` | Derived in `_attribute_dismissed_with_broadcast_override` at `test_pipeline.py:3152` from `_striker_this_ball` (pre-rotation snapshot of `score_mgr.striker`) | Multi-frame via Mitigation A capture | Indirectly (striker pointer ultimately derives from strip OCR via `apply_striker_identity_proposed` per `:1211/1213` §15 canonical) |
| `event.bowler_name` | `score_mgr.bowler_name` (from prior frame's strip + bowler-tracker reconciliation) | Multi-frame via consensus tracker | Indirectly |
| `event.wicket_type` | `ball_event["wicket_type"]` defaulted to "bowler_wicket" | Single-frame | Yes |
| `event.over_ball` | Current strip `overs` field at the wicket frame | Single-frame | Yes |
| `event.wicket_number` | `self.wickets + 1` at dispatch time | Single-frame (counter that drives the wicket-event itself) | Yes — IS THE OCR SIGNAL that fired the phantom |
| `self.score` | Cumulative state from strip OCR runs | Multi-frame | Yes |
| `self.striker / self.non` | Pipeline-internal striker pointer; deterministic-rotation override per `:4411` (WS-D §3.4c.1 S8 root) | Multi-frame ostensibly but rotation-lock-starvation-corrupted per WS-D | Yes (rooted in strip OCR via canonical writes) |
| `self.batting_card[*].status` | Slot status tracked across frames; status="batting" set on strip-confirmed names | Multi-frame | Yes |
| `self._fow_writable()` accumulated state | FoW table appended on every prior apply_wicket_event | Multi-frame | Indirectly (each FoW entry derives from a prior wicket-event commit) |
| `partnership_*` state | Reset on each wicket-event; accumulates between | Multi-frame | Indirectly |

**Classification.**

- **Multi-frame-resilient (in principle):** striker pointer + partnership + bowler tracker + batting-card status. These are pipeline-internal state machines.
- **But ALL pipeline-internal state ultimately derives from strip OCR via canonical write paths.** There is no signal in the state machine that is independent of Scout-OCR provenance.
- **External signals available:** none currently. Cricbuzz commentary (KF candidate) would be external — requires architectural pivot.

**Implication.** The state-machine layer's "multi-frame resilience" is illusory at the discriminator level. Every state-machine signal is downstream of strip OCR. When OCR is noisy (F1015 wkts=6 spike → F1016 regression → F1017 wkts=5 settled-wrong), the state-machine signals are noisy in the SAME WAY. The OCR-noise-uniformity finding from Surface E §15 propagates upward through the canonical write-path fence into the state-machine layer.

---

## §3 Cricket-physics invariant catalogue + discriminator analysis

Per memo §1+§2 + cohort comparator data:

| Cricket invariant | Multi-frame-resilient? | Discriminates F1017 phantom from genuine cohort? | Falsification basis |
|---|---|---|---|
| Dismissed batter must be in at-crease pair pre-wicket | Multi-frame (Mitigation A pre-fall capture) | **NO** | F1017: Axar IS in pre-wicket at-crease pair (per cricket truth AND per pipeline state). Genuine wickets: dismissed batter IS in pre-wicket at-crease pair. **Identical signature.** |
| Partnership must end | Multi-frame | **NO** (consequence-of-commit, not pre-commit input) | Partnership state UPDATES upon `apply_wicket_event` commit. Pre-commit, partnership has the same value in phantom + genuine cases. |
| Bowler-W must increment | Multi-frame | **NO** (same consequence-of-commit) | `_increment_bowler_wickets` fires on every dispatch. Pre-commit, no discriminative signal. |
| Striker pointer must update | Multi-frame (per `:4337-4385` consensus-parity gate) | **NO** | Phantom F1017: `STRIKER-WRITE: non Axar Patel → None` updates pointer same way as genuine wicket. Discriminative only post-commit (and even then, both cohorts produce a STRIKER-WRITE). |
| `this_over` symbol transitions to 'W' at expected position | Single-frame | **NO** | F1017 this_over already has W at multiple positions (per the strip oscillation around the over boundary); genuine wicket frames also show W at expected position. Identical. |
| Bat-slot churn (slot resolution refreshes) | Multi-frame | **NO** | At F1017 the bat-slots show AXAR/STUBBS continuing (no churn) — but genuine wicket frames ALSO show no immediate churn (per §1.1 — dismissed batter persists at-crease for many frames). Same multi-frame strip-lag pattern. |
| At-crease pair must change within K frames | Multi-frame OCR | **NO** | §1 + §1.1 cohort comparator: phantom and genuine BOTH show multi-frame at-crease persistence; walk-off lag is structurally identical. |

**Conclusion.** No multi-frame-resilient cricket-physics invariant discriminates phantom F1017 from the genuine cohort at the state-machine layer. The OCR-noise-uniformity finding (Surface E §15) is now **demonstrated to generalize** to the state-machine layer because every state-machine signal is downstream of strip OCR.

---

## §4 Hypothesis enumeration + static falsification (5 candidates falsified at gate 1)

### KA — At-crease-name-equality (HD reformulation) — **FALSIFIED**

**Shape.** Refuse wicket if `event.dismissed_batter` not in current at-crease pair (`self.striker`, `self.non`).

**Gate 1.** FAIL. At F1017: pipeline state shows striker=Axar + non=Stubbs; `_attribute_dismissed_with_broadcast_override` returns `_striker_this_ball = Axar`. Axar IS in the at-crease pair → KA admits. Discriminative power zero.

**Status.** Falsified at gate 1 (static).

### KB — Multi-frame striker-pointer-stability gate — **FALSIFIED**

**Shape.** Refuse wicket if `pipeline.striker` has been stable for >N frames AND wicket-event would not cause striker change.

**Gate 1.** FAIL. At F1017, the wicket-event WOULD cause striker change (`STRIKER-WRITE: non Axar Patel → None` followed by post-rotation). The predicate "would NOT cause a striker change" evaluates False at F1017 → KB admits. Same shape as genuine wickets (each causes a striker change). Zero discriminative power.

**Status.** Falsified at gate 1.

### KC — Deferred-commit corroboration (at-crease-pair-change verification within K frames) — **FALSIFIED**

**Shape.** Queue wicket-event; require corroborating at-crease-pair change within K frames; commit on corroboration, drop on timeout.

**Gate 1.** FAIL. Per §1+§1.1 cohort comparator: both phantom F1017 (AXAR/STUBBS persists F1017-F1019) AND genuine cases (PATHUM/RAHUL persists F400-F401; PATHUM/RIZVI persists F853-F857) show multi-frame at-crease persistence post-wicket. Walk-off lag is identical to phantom persistence. K-tuning cannot rescue: K=1 too tight (drops genuine F855 because F856 strip absent); K=10 admits both (genuine F410 strip eventually changes within window; phantom F1017's window also has strip-lost frames that mask any change). **Discriminator fails on the actual cohort data.**

**Status.** Falsified at gate 1 (data-empirical falsification; no budget cost — Scout-dump-on-disk inspection).

### KD — Bowler-tracker-state-consistency — **FALSIFIED**

**Shape.** Bowler-W increment at wicket frame must match bowler-tracker's accumulated state pre-commit.

**Gate 1.** FAIL. Bowler-tracker accumulates from strip OCR. At F1017, `pipeline.current_bowler = "Anukul Roy"` (per the trace's WICKET-RESOLVED-FROM-PENDING dispatch); his cumulative wickets state is consistent with the pipeline thinking he just took a wicket. Same shape as genuine wickets (each bowler's tracker state is consistent with the wicket they're credited for). Zero discriminative power.

**Status.** Falsified at gate 1.

### KE — Bat-slot-churn requirement — **FALSIFIED (subsumed by KC)**

**Shape.** Refuse wicket if bat-slot resolution at the wicket frame doesn't show churn (slot stays at same names = no actual personnel change = phantom).

**Gate 1.** FAIL. Bat-slot resolution is the same data source as at-crease pair per §3 (both derive from strip OCR's batting-card slots). Same multi-frame persistence pattern across phantom + genuine. Bat-slot churn fails to discriminate for the same reason KC fails: walk-off lag is multi-frame in BOTH cases. KE is functionally a relabeling of KC.

**Status.** Falsified at gate 1 (subsumed by KC).

### KF — External Cricbuzz-commentary corroboration — **REQUIRES ARCHITECTURAL PIVOT BEYOND PHASE 1 SCOPE**

**Shape.** Require commentary confirmation within K seconds. Cricbuzz commentary is an EXTERNAL signal independent of Scout OCR; would actually discriminate phantom from genuine.

**Gate 1.** PASS (in principle — external signal IS discriminating).

**Gate 3 (fix-surface attribution).** **FAIL for Phase 1 scope.** Cricbuzz commentary is not currently consumed by the pipeline; requires:
- New external API integration (Cricbuzz API or scraping infrastructure).
- Real-time corroboration logic at `apply_wicket_event` site.
- Latency tolerance (commentary lags broadcast by N seconds).
- Reliability handling (Cricbuzz availability, rate limits).
- Cost ($/match or rate-limit consumption).
- Failure-mode handling (commentary unavailable → fall back to current behavior, which means phantom still admits).

This is architecturally large. Per user stop condition: "KF (external corroboration) becomes leading candidate → STOP, report; this is a major architectural investment requiring separate scoping decision."

**Status.** Deferred to architectural decision. Not in current Phase 1 scope.

### KG — Cohort-split (F1017 distinct mechanism from other phantoms) — **UNAVAILABLE**

**Shape.** F1017 has unique mechanism; not part of a generalizable defect class.

**Gate 1.** Cohort is 1 confirmed instance (F1017 on validate_dckkr_20260521_155356) + 1 candidate ghost on validate_ws_h_step7. Single-instance cohort cannot be split. KG is structurally inapplicable.

**Status.** Inapplicable (cohort too small).

---

## §5 Cohort-closure verification — N/A under universal falsification

**Standard cohort-closure verification framing assumes a leading candidate.** All KA-KE statically falsified; KF requires architectural pivot; KG inapplicable. No leading candidate → no cohort-closure verification.

**The architectural finding IS the cohort-closure verification.** F1017 phantom is structurally undiscriminable from genuine cohort at both detection-layer (Surface E §15) AND state-machine layer (WS-K §3+§4) within the current Scout primitive set. The "cohort" closes by exhaustion of the discriminator search space.

---

## §6 §7.2 audit on the only-surviving-candidate KF (Cricbuzz commentary)

KF survives gate 1 (discriminating signal IS available) but fails gate 3 (fix-surface attribution requires Phase-2-class architectural investment). For documentation only:

| Gate | KF status |
|---|---|
| **1** | PASS — external Cricbuzz commentary is structurally discriminative |
| **2** | PASS conditional — if commentary correctly flags wickets, the corroboration gate preserves genuine cohort |
| **3** | **FAIL for Phase 1 scope** — requires new external integration + real-time corroboration + latency-tolerance + failure-mode handling + cost commitment |
| **4** | Hypothetical PASS — commentary corroborates wickets at real-time delivery boundaries |
| **5** | Hypothetical FAIL — introduces new persistent state for commentary feed + corroboration queue; not analogous to any current state machine |
| **6** | n/a (no patch surface) |
| **7** | n/a (no patch) |

**Decision frame for KF.** Architectural pivot would be Phase 2-class investment with delivery profile measured in weeks, not days. The F1017 cohort is 1 instance on 1 fixture. **The ROI economics do not justify KF in Phase 1.** Defer until either (a) the phantom-wicket cohort grows via natural production accumulation; OR (b) Cricbuzz integration becomes required for an independent strategic reason (live-stats overlay, commentary annotations).

---

## §7 False-negative risk assessment — N/A under universal falsification

No candidate has a "false-negative risk" because no candidate is being landed. The risk assessment that applies is the **inverse**: leaving F1017 phantom unsuppressed has **zero false-negative cost** (no genuine wicket is missed) and **bounded false-positive cost** (1 phantom event on 1 fixture; downstream-recoverable via UI re-render or operator intervention per Surface E §16).

---

## §8 Predicted-flip table — VOID under universal falsification

No patch lands at WS-K step-1. Predicted-flip table is VOID.

---

## §9 Sub-findings index — candidate S27 surfaced

### S27 — Multi-layer falsification convergence (CANDIDATE — single instance)

**Statement (CANDIDATE — not yet promoted to numbered insight).** When sequential investigation layers all falsify on a defect class while operating from a shared signal source, the defect class is structurally beyond current pipeline scope. Continued layer-search is methodology waste; the discipline outcome is to **promote to architectural-known-defect and defer until external signal access expands**.

**Single-instance evidence (this step's load-bearing observation).** Surface E (detection layer, OCR-noise-uniformity finding §15) + WS-K (state-machine layer, state-signal-OCR-derivation finding §3) both falsified on F1017 phantom. The state-machine layer was the natural "next layer up" — yet it derives all signal from the same OCR source, so the OCR-noise-uniformity finding propagates upward. The shared-signal-source IS the structural barrier; investigation layers operating downstream of the source share its limitations.

**Why this is distinct from S26 (static-investigation-rounds compound).** S26 says "more layers → more falsification of intermediate claims → higher confidence in surviving conclusions." S27 says "when ALL layers falsify on a shared signal source, the conclusion that survives is 'no fix exists within current signal scope.'" S26 is about WITHIN-workstream layer compounding; S27 is about ACROSS-workstream convergence on a shared signal-source barrier.

**Promotion threshold.** Single-instance — defer to candidate status. Promotion to numbered insight requires second-instance confirmation (a future workstream where multiple layers converge on a shared-source falsification). When promoted, suggested canonical statement: *"Multi-layer falsification convergence — when sequential investigation layers falsify a defect class on a shared signal source, the defect is structurally beyond current scope; promote to architectural-known-defect and defer external-signal-access expansion until cohort growth or independent strategic justification triggers it."*

**Operational corollary if S27 confirms.** At each layer's step-1 close-out, identify the layer's signal-source provenance. If the next-layer's signal-source is downstream of the current layer's signal-source, predict shared-barrier falsification BEFORE committing the next-layer investigation. Saves investigation time.

### Candidate S26 (PROMOTED at Surface E retirement) — no new evidence this step

S26 status unchanged: numbered insight, three-instance evidence as of `a4f91f5`.

### Candidate S25 (strategic-framing-vs-source-modality) — second-instance unchanged

S25 status unchanged: candidate at 2 instances (C29b step-1 + Surface E step-1 cohort-sizing). WS-K step-1 is a DIFFERENT mechanism (within-pipeline shared-signal-source rather than upstream-modality access).

### Candidate S24 (arc-length-by-fix-surface-category) — unchanged

S24 status unchanged: candidate at 2 instances (WS-H 9-step + WS-I 3-step). WS-K step-1 is a 1-step terminating-at-falsification arc; not a fix-shipping arc, so doesn't fit the S24 framing directly.

---

## §10 Step-2 entry data + recommendation

**WS-K step-2 VOID — no patch surface.** All candidates statically falsified. F1017 phantom retires as architectural-known-defect.

### Three-fork decision (user authorization required)

**Fork 1 — Accept-and-document-known-limitation (RECOMMENDED).** F1017 catalogued at `surface_pair_defect_class_family.md` §2.10 (already landed at `a4f91f5` with "architectural-known-defect" framing — VALIDATED by WS-K step-1 convergent falsification). Phase 1 second-pillar slot re-opens for re-selection (per HANDOFF `a4f91f5` next-session pointer at §11.3 item 5 Recent-Overs partial-render). No additional code, no additional commit beyond WS-K step-1 memo itself.

**Fork 2 — Cricbuzz-commentary architectural pivot (DEFER).** Phase 2-class investment; requires standalone scoping memo + cost-benefit analysis. Defer until phantom-wicket cohort grows via natural production OR independent strategic justification for commentary integration emerges.

**Fork 3 — Continue layer search (NOT RECOMMENDED).** Hypothetical next layer (?) doesn't exist within current architecture. Per S27 candidate framing: continued layer-search at shared-signal-source is methodology waste.

**Recommendation: Fork 1.** Surface E retirement framing was correct ex-ante; WS-K step-1 has now confirmed it via convergent falsification. The catalogued `surface_pair §2.10` entry stands. No code changes. Phase 1 re-selection proceeds per HANDOFF `a4f91f5`.

---

## §11 Status footer + recommended commit-message format

**WS-K step-1 status.** **FALSIFIED at static analysis** — all 5 within-Phase-1-scope candidates (KA / KB / KC / KD / KE) statically falsified at gate 1; KF requires Phase 2 architectural pivot; KG inapplicable on single-instance cohort. Multi-layer convergent falsification with Surface E confirms F1017 as architectural-known-defect.

**Recommended next step.** Land WS-K step-1 memo (this commit). Phase 1 second-pillar re-selection proceeds per HANDOFF `a4f91f5` (§11.3 item 5 Recent-Overs partial-render recommended). No WS-K step-2.

**Sub-findings.** Candidate S27 (multi-layer falsification convergence) surfaced — single instance, awaits second-instance confirmation before promotion.

**Empirical-budget status.** **2/5 — UNCHANGED across WS-K step-1.**

**Methodology insights running total.** 23 (unchanged — S27 is candidate, not promoted).

**Recommended commit message (DO NOT auto-commit; user authorizes explicitly):**

```
docs(workstream-k): step-1 investigation memo — phantom-wicket state-machine cricket-physics; F1017 inherited from Surface E retirement

WS-K state-machine layer ALSO STATICALLY FALSIFIED. Five candidates
(KA at-crease-name-equality + KB striker-pointer-stability +
KC at-crease-pair-change + KD bowler-tracker-consistency +
KE bat-slot-churn) all falsified at gate 1 on F1017 phantom on
validate_dckkr_20260521_155356.

Cohort comparator data (Scout dump on-disk inspection; zero empirical
budget cost):
  Phantom F1017: AXAR/STUBBS at-crease pair persists F1017-F1019
    (3 frames; strip lost F1020+).
  Genuine F400 (Rahul ov 5.0): PATHUM/RAHUL persists F400-F401 +
    strip lost F402-F409 + RAHUL re-appears at F410.
  Genuine F855 (Nissanka ov 9.5): PATHUM/RIZVI persists F853-F857 +
    strip lost F858-F862.
  Multi-frame at-crease persistence is structurally IDENTICAL across
  phantom and genuine cohort — walk-off lag (genuine) is indistinguish-
  able from at-crease-stays-stable (phantom) at the OCR-snapshot level.

Architectural finding (LOAD-BEARING): the OCR-noise-uniformity finding
from Surface E §15 GENERALIZES to the state-machine layer. Every
state-machine signal (striker pointer + partnership + bowler tracker +
batting-card status + bat-slot resolution) is downstream of strip OCR
via the §15 canonical write-path fence. When OCR is noisy at the
phantom frame, ALL pipeline-internal state derived from that OCR is
noisy in the same way. The "multi-frame resilience" of the state-
machine layer is illusory at the discriminator level.

KF (external Cricbuzz-commentary corroboration) survives gate 1 but
fails gate 3 (Phase 2 architectural investment; new API integration +
real-time corroboration + latency tolerance + failure-mode handling +
cost). Deferred until F1017 cohort grows OR independent strategic
justification surfaces.

KG (cohort-split) inapplicable — cohort is 1 confirmed + 1 candidate.

S27 candidate surfaced (NOT yet promoted; single instance): Multi-layer
falsification convergence — when sequential investigation layers
falsify a defect class on a shared signal source, the defect is
structurally beyond current scope; continued layer-search is method-
ology waste. Distinct from S26 (within-workstream layer compounding);
S27 is across-workstream convergence on shared-signal-source barrier.
Awaits second-instance confirmation.

Surface E retirement framing at a4f91f5 (architectural-known-defect at
surface_pair §2.10) VALIDATED by WS-K step-1 convergent falsification.
No reconciliation needed. F1017 retires definitively; no WS-K step-2;
Phase 1 second-pillar re-selection proceeds per HANDOFF a4f91f5 next-
session pointer (§11.3 item 5 Recent-Overs partial-render recommended).

Empirical-budget status: 2/5 → 2/5 (UNCHANGED).
Static-falsification count this step: 5 (KA + KB + KC + KD + KE).
Methodology insights running total: 23 (S26 promoted at a4f91f5;
S27 candidate awaiting second instance).

Memo: files/docs/investigations/workstream_k_phantom_wicket_state_machine_investigation.md (11 sections, ~470 lines).
```

---

## §12 Retirement declaration

**WS-K closes at step-1 with universal-candidate-exhaustion.** F1017 phantom-wicket confirmed as architectural-known-defect at **every pipeline-internal layer** (detection per Surface E §15 + state-machine per WS-K §3+§4). The Surface E `a4f91f5` retirement framing was correct ex-ante; WS-K step-1 has now validated it via convergent falsification.

**Cost-benefit of WS-K step-1 as a discipline data point.** Single static-investigation cycle (zero empirical-budget consumed) bought two architectural-significance returns:
- Confirmation that F1017 is structurally undiscriminable at state-machine layer (not just detection) — load-bearing for any future re-investigation decisions.
- Surfacing of S27 candidate (shared-signal-source structural barrier) as a transferable methodology insight distinct from S26.

**KF (Cricbuzz-commentary external corroboration) DEFERRED to Phase 2 architectural-pivot queue.** Not opened as a workstream this session. Re-opening prerequisites:
1. Phantom-wicket cohort grows beyond 1-confirmed via natural production telemetry accumulation, OR
2. Independent strategic justification surfaces for real-time Cricbuzz commentary integration (live-stats overlay, commentary annotations, real-time fact-checking layer, etc.), OR
3. New Scout primitive emerges that provides discriminating signal NOT downstream of strip OCR (e.g., a `graphic_state` field parsing FoW-overlay text on `camera_view=graphic` frames — flagged here as hypothetical; not investigated).

Per the user's KF stop condition: "this is a major architectural investment requiring separate scoping decision." Deferred.

**No WS-K step-2.** No patch surface within Phase 1 scope. Phase 1 second-pillar re-selection proceeds per HANDOFF `a4f91f5` next-session pointer.

## §13 S27 candidate consolidation

**S27 — Shared-signal-source structural barrier (CANDIDATE — single instance).**

**Statement.** When sequential investigation layers (detection, state-machine, etc.) all derive their signals from a shared upstream source, falsifications at any layer propagate upward into all downstream layers. The "multi-frame resilience" or "downstream filtering" or "cross-component reconciliation" framing of higher layers is illusory at the discriminator level — every signal is ultimately bounded by the upstream source's discriminative capacity. The structural barrier is the shared source itself; investigation layers cannot exceed its discriminative ceiling.

**Single-instance evidence (this step's load-bearing finding).** The §15 canonical write-path fence guarantees that every state-machine signal (striker pointer + partnership + bowler tracker + batting-card status + bat-slot resolution + this_over) flows through canonical write paths from strip OCR. When OCR is noisy at F1015-F1017 (wkts=6 spike → wkts=4 regression → wkts=5 settled-wrong), every downstream state-machine signal inherits the same noise envelope. The fence is correctness-preserving (no non-canonical writes) but discriminator-limiting (no signal can exceed strip OCR's discriminative capacity).

**Distinction from S26 (process-level peer).** S26 ("static-investigation-rounds compound") is about the methodology process: more static layers → more falsification of intermediate claims → higher confidence in surviving conclusions. S27 (proposed: "shared-signal-source structural barrier") is the structural-cause peer: WHY do multi-layer falsifications converge? Because layers share an upstream source whose discriminative capacity bounds all downstream layers. S26 describes the discipline; S27 describes the structural reason the discipline produces convergent falsification.

**Promotion threshold.** Single instance — defer to candidate status. Second-instance confirmation would require a future workstream where layers converge on a shared-source falsification (different from this one — e.g., a defect class where pipeline + UI both falsify on shared WebSocket-payload source, or extractor + state-machine both falsify on shared OCR field).

**Operational corollary if S27 confirms.** At step-1 close-out of any layered-investigation, identify the layer's signal-source provenance. If the next-layer's signal-source is downstream of the current layer's source, predict shared-barrier falsification BEFORE committing the next-layer investigation cycle. Saves investigation time at near-zero cost (the prediction itself is static).

**Cross-reference to S26.** S26 says: "more static layers → higher confidence." S27 says: "when multi-layer falsifications converge on shared source, the surviving conclusion is 'no fix exists within current signal scope.'" Together: S26 + S27 jointly mature the multi-layer-investigation discipline into a standing audit framework.

## §14 Future re-investigation prerequisites

F1017 phantom-wicket retires definitively for Phase 1 scope. Future re-investigation requires one of:

1. **Cohort growth via natural production accumulation.** Current cohort: 1 confirmed (validate_dckkr_20260521_155356) + 1 candidate ghost (validate_ws_h_step7). Future production sessions may surface additional phantom-wicket instances. When cohort grows to N ≥ 3 distinct instances across distinct fixtures, KF architectural-pivot ROI economics shift to justify the investment.

2. **Scout primitive set expansion to include a signal NOT downstream of strip OCR.** Candidate (hypothetical; not investigated this session): a `graphic_state` Scout field parsing FoW-overlay text on `camera_view=graphic` frames. Such a field would extract dismissed-batter name + dismissal timing from the broadcast's FoW graphic overlay, which is rendered seconds-to-minutes after the wicket-event and provides external corroboration independent of the strip OCR that fired the phantom. Re-opens the C29b Scout-prompt-extension question on a narrower scope (graphic-frame extraction, NOT per-frame strip extension).

3. **External corroboration architecture (KF — Cricbuzz commentary real-time discriminator).** Major Phase 2 investment. `files/scripts/ingest_cricbuzz_ground_truth.py` already ingests Cricbuzz commentary for post-hoc regression-fixture purposes; wiring as a real-time discriminator at `apply_wicket_event` site requires fresh scoping memo + new latency-tolerance + failure-mode + cost-commitment architecture. Defer until cohort growth (prereq 1) or strategic justification surfaces.

4. **Operator-side post-hoc retraction workflow.** Accept pipeline-side phantom emission; provide downstream UI for operator to flag and retract phantom wicket-events. This is a Phase 3 UI/operational concern; out of pipeline scope.

**Recommendation: prerequisite (1) is the lowest-friction monitoring path.** Watch natural production traces for additional phantom-wicket instances. Surface E's `surface_pair §2.10` catalogue entry + WS-K's retirement declaration are the standing observability surfaces. No active monitoring infrastructure needed beyond existing trace assertion library.

**Arc retired.**


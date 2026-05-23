# Workstream Recent-Overs — Partial-render investigation (step-1)

**Date.** 2026-05-23.
**Branch.** `derive-not-detect` @ HEAD = `df64e84` (WS-K retirement docs).
**Empirical-budget status.** 2/5 — UNCHANGED (static-only this step).
**Outcome.** **DEFERRED to Phase 3 UI render layer scope** per HANDOFF line 725 standing classification + ambiguous pipeline-vs-UI signal correspondence. The on-disk over_history pipeline-side anomaly cohort (OVER-ARCHIVE-INVALID-TOKEN-COUNT ×2 + OVER-ARCHIVE-DEFERRED-QUEUE-NONEMPTY ×2 on `validate_dckkr_20260521_155356`) is real but its correspondence to the operator-reported B-γ "Recent Overs panel drops entries" UI defect is unverified at static analysis. **Phase 1 second-pillar slot RE-OPENS again** — recommend **§11.3 item 4 (Per-batter-ledger conservation)** as next candidate. Zero budget consumed; cohort growth or operator-reported frame anchors required before pipeline-side investigation can usefully proceed.

---

## §1 Defect characterization — B-γ standing classification

**HANDOFF line 725 (verbatim):** "B-γ (Recent Overs panel drops entries), B-δ (UI bottom-strip striker), `trace_extras_total` UI inconsistency — out of scope for SM/pipeline workstream."

The B-γ surface is catalogued in the SAME-LINE-as-B-δ standing classification as **UI render layer bugs (separate workstream — unchanged from prior session)** (HANDOFF line 724 section header). The classification predates Surface E, WS-K, and the current Phase 1 plan; it reflects the prior-session architectural division between pipeline (SM-managed state derivation) and UI render layer (WebSocket-payload → React consumer rendering).

**Operator-reported defect signature (from prior-session context).** Recent Overs panel on the scorecard UI drops entries — e.g., "Ov 9 entirely missing from Recent Overs panel through replay-end; pattern: 11, 10, 8, 7, 6 — no Ov 9" per `surface_pair_defect_class_family.md` §2.9 Obs 20 anchor. The defect is observed at the rendered UI; no frame-level pipeline-state corruption anchor is provided.

## §2 Cross-fixture survey — pipeline-side over_history anomaly enumeration

On-disk trace inspection (5 representative `validate_*.jsonl` fixtures sampled):

| Trace | OVER-ARCHIVE-WRITE | OVER-ARCHIVE-INVALID-TOKEN-COUNT | OVER-ARCHIVE-DEFERRED-QUEUE-NONEMPTY |
|---|---|---|---|
| `validate_20260520_114437` | 7 | 0 | 1 |
| `validate_dckkr_20260521_070545` | 11 | 2 | 3 |
| `validate_dckkr_20260521_155356` | 10 | 2 | 2 |

**Pipeline-side signal IS present.** `OVER-ARCHIVE-INVALID-TOKEN-COUNT` fires on overs whose token count doesn't match the expected 6-legal-balls. `OVER-ARCHIVE-DEFERRED-QUEUE-NONEMPTY` fires on over-rollover when the pending-ball queue still has unresolved entries. Both are observability tags (not error-blockers); over_history accepts the anomalous over and writes it.

**Correspondence to B-γ "Recent Overs panel drops entries" UNVERIFIED.** Without operator-reported frame anchors mapping a specific dropped-over instance to a specific pipeline-side over_history anomaly, the relationship is ambiguous:
- Option A — Pipeline-side root: `OVER-ARCHIVE-INVALID-TOKEN-COUNT` causes the UI to skip rendering that over (e.g., UI consumer rejects malformed payload entries).
- Option B — UI-side root: pipeline writes over_history correctly; UI render-layer drops the entry on its own (React state-stale, deepMerge edge case, panel-size-overflow eviction).
- Option C — Composite: both pipeline AND UI contribute; either root closure would partially fix.

Static analysis cannot disambiguate. The user's stop condition explicitly covers this: "Static analysis cannot disambiguate fix-surface without empirical replay → STOP, flag, defer empirical step to user authorization."

## §3 Pipeline-vs-UI fix-surface localization (C21 precedent)

**C21 forcing-function finding (Architecture §0.4):** "UI-layer vs state-layer disambiguation. Nissanka's W→· revert at Obs 17b was in the WebSocket-render path, not the pipeline state. Trace state preserved W correctly at frame 855 position 4. §2.1 surface-pair scope refined: state-layer reverts (Rahul/Rana) vs UI-render-layer reverts (Nissanka) are distinct sub-cases."

**Analog for Recent-Overs:** Without frame-anchored evidence that pipeline `over_history` is corrupted at the specific over the UI is dropping, the C21-pattern presumption is: **UI-render-layer-only**. The standing HANDOFF line 725 classification reflects this presumption.

**Evidence-of-pipeline-root would require:**
1. Operator-reported frame anchor for a specific dropped-over instance (e.g., "Ov 9 missing on validate_X.jsonl at frame Y").
2. Trace inspection at frame Y showing `over_history[over_idx]` either missing OR corrupted at the SM layer.
3. WebSocket payload inspection at frame Y showing the over either absent OR malformed in the published payload.

None of these anchors are currently available. The OVER-ARCHIVE-INVALID-TOKEN-COUNT firings exist but aren't tied to operator-reported B-γ instances.

## §4 Hypothesis enumeration

### HA — Assertion-side gate for over_history INTERNAL consistency

**Shape.** Add `trace_recent_overs_history_consistent` assertion: every over committed to `over_history` must have exactly 6 legal balls (or documented variant). Detect pipeline-side anomalies regardless of UI correspondence.

**Gate 1.** PASS at observability level — would catch OVER-ARCHIVE-INVALID-TOKEN-COUNT firings as assertion FAILs.

**Gate 2.** PASS — internal-consistency invariant.

**Gate 3 (fix-surface attribution).** This is a NEW assertion, not a fix. It would surface the cohort but NOT close the B-γ UI defect (UI render layer remains untouched). Closes the wrong question.

**Status.** Useful as a regression-detector addition (Phase 4 catalogue candidate) but does NOT close B-γ. Not a leading Phase 1 candidate.

### HB — Pipeline-side over_history corruption root-localize

**Shape.** Investigate `OVER-ARCHIVE-INVALID-TOKEN-COUNT` firings at `score_manager.py` over-archive-write sites. Identify root cause + propose pipeline-side fix.

**Gate 1.** UNVERIFIED — without B-γ frame anchor, can't prove pipeline anomaly causes UI dropped-over.

**Gate 3.** Even if pipeline anomaly is fixed, B-γ may persist (UI render-layer may have independent root). The fix would be necessary-but-not-sufficient.

**Status.** Possibly load-bearing for over_history correctness but doesn't close B-γ without UI-side investigation. Deferred until frame anchor surfaces.

### HC — UI-render-layer-only (C21 pattern)

**Shape.** Phase 3 deferral. Investigation moves to `scorecard-ui/app/components/` Recent Overs panel render code.

**Gate 1.** PASS as default per HANDOFF line 725 standing classification + C21 precedent + ambiguous-correspondence finding at §3.

**Gate 3.** Out of Phase 1 pipeline scope by definition.

**Status.** Aligned with standing classification. **Recommended as the deferral pivot.**

### HD — Composite (pipeline + UI both contribute)

**Shape.** Both pipeline-side over_history anomalies AND UI-side render dropouts contribute. Requires coordinated fix at both layers.

**Gate 1.** PASS in principle, but requires frame-anchored evidence to verify.

**Status.** Inapplicable until evidence surfaces.

### HE — Already-closed by prior work

**Shape.** Some prior commit (P1/H1/Shape A/Shape B/D1/D2/WS-G lifecycle) may have already fixed pipeline-side over_history corruption as a side-effect. Verify B-γ baseline is unchanged.

**Gate 1.** UNVERIFIED — would require comparing pre- vs post-prior-commit over_history anomaly counts. The 2-fire baseline on `validate_dckkr_20260521_155356` (a post-`5206885` merge trace) suggests pipeline anomalies persist post all WS-G/WS-H/WS-I closures.

**Status.** Partially falsified by trace persistence; not a leading candidate.

## §5 Cohort-closure verification

**Standard framing assumes leading candidate.** No leading Phase 1 candidate identified. Per user stop condition: "Static analysis cannot disambiguate fix-surface without empirical replay → STOP, flag, defer empirical step to user authorization." **Deferred.**

## §6 §7.2 audit — N/A under deferral

No leading candidate to audit. The investigation surfaces the architectural ambiguity but does not propose a Phase 1 patch.

## §7 Predicted-flip table — VOID under deferral

No patch lands.

## §8 Sub-findings

**No new sub-findings.** Investigation reproduces HANDOFF line 725 standing classification + C21 precedent; surfaces pipeline-side over_history anomaly cohort (OVER-ARCHIVE-INVALID-TOKEN-COUNT × 2-3 per trace) as Phase 4 catalogue candidate for `trace_recent_overs_history_consistent` assertion-side addition. Not promoted; logged for future Phase 4 sweep.

## §9 Step-2 entry data + recommendation

### Recommendation: DEFER B-γ Recent Overs to Phase 3 UI render layer; re-pick Phase 1 candidate

**B-γ Recent Overs partial-render** stays catalogued at `surface_pair §2.9` + HANDOFF line 725 as UI render layer scope. No Phase 1 pipeline-side patch authorized. Investigation re-opening prerequisites:
1. **Operator-reported frame anchor** mapping a specific dropped-over instance to a specific pipeline-side over_history anomaly (would enable HD composite investigation).
2. **Cohort growth** if multiple UI-side B-γ instances surface from natural production (would justify Phase 3 UI investigation prioritization).
3. **Phase 4 over_history assertion addition** as a side-effort regression-detector — independent of B-γ closure, would catch pipeline-side anomaly cohort and aid future correspondence verification.

### Next Phase 1 second-pillar candidate

Per WS-K retirement (`df64e84` HANDOFF update), remaining Phase 1 second-pillar candidates (Recent-Overs now ruled out):

| Candidate | Fix surface category | Expected arc | Budget cost |
|---|---|---|---|
| **§11.3 item 4 — Per-batter-ledger conservation** (RECOMMENDED) | TBD per step-1 investigation; possibly pipeline-side narrow scope | 3-5 step | 0-1/5 |
| WS-D §3.5 Layer 1a — `_derive_dismissed_name` (HE survivor from C29b) | Pipeline-side; S12 plumbing concern | 9+ step multi-arc | 1-2/5 |
| WS-F bowler-misattribution — γ-bowler-w adjacent surfaces | Narrow pipeline-side | 5-9 step | 1-2/5 |

**Recommended next session: §11.3 item 4 (Per-batter-ledger conservation) step-1 investigation memo.** Smallest projected scope + lowest budget risk among remaining candidates.

---

## §10 Status footer + recommended commit-message format

**WS-Recent-Overs step-1 status.** **DEFERRED to Phase 3 UI scope** per HANDOFF line 725 standing classification + ambiguous pipeline-vs-UI correspondence. No patch surface authorized at Phase 1.

**Recommended next step.** Re-pick Phase 1 second-pillar candidate. Recommend **§11.3 item 4 (Per-batter-ledger conservation)** at next session.

**Sub-findings.** None promoted. Phase 4 catalogue candidate logged (over_history internal-consistency assertion `trace_recent_overs_history_consistent`).

**Empirical-budget status.** **2/5 — UNCHANGED.**

**Methodology insights running total.** 23 (unchanged).

**Recommended commit message (DO NOT auto-commit; user authorizes explicitly):**

```
docs(workstream-recent-overs): step-1 investigation memo — B-γ Recent Overs partial-render DEFERRED to Phase 3 UI scope per standing classification + ambiguous correspondence

§7.2 static-falsification chain on B-γ Recent Overs panel drops
entries (per surface_pair §2.9 Obs 20 anchor: "Ov 9 entirely
missing from Recent Overs panel through replay-end; pattern: 11,
10, 8, 7, 6 — no Ov 9"). HANDOFF line 725 standing classification:
"B-γ (Recent Overs panel drops entries) ... out of scope for SM/
pipeline workstream."

Cross-fixture survey of on-disk traces surfaces pipeline-side over_
history anomaly cohort (OVER-ARCHIVE-INVALID-TOKEN-COUNT × 2 +
OVER-ARCHIVE-DEFERRED-QUEUE-NONEMPTY × 2 on validate_dckkr_
20260521_155356; analogous 2-3 firings on other validate fixtures).
Pipeline-side anomalies are REAL but their correspondence to the
operator-reported B-γ UI defect is UNVERIFIED — no frame anchor
links a specific dropped-over instance to a specific over_history
anomaly.

C21-pattern precedent (UI-layer vs state-layer disambiguation,
Architecture §0.4): when state-layer evidence is preserved at the
trace but UI displays divergent state, the defect is UI-render-
layer-only. Applied here: pipeline writes over_history (with
occasional internal anomalies), UI may independently drop entries
in render-layer logic. Cannot disambiguate without frame anchor.

Recommendation: DEFER B-γ Recent Overs to Phase 3 UI render layer
investigation. Re-opening prerequisites: (1) operator-reported
frame anchor for a specific dropped-over instance; OR
(2) cohort growth from natural production; OR (3) Phase 4 over_
history assertion addition (`trace_recent_overs_history_consistent`)
as independent regression-detector.

Phase 1 second-pillar slot RE-OPENS AGAIN. Recommended next-
session candidate: §11.3 item 4 (Per-batter-ledger conservation)
— smallest projected scope + lowest budget risk among remaining
candidates (WS-D §3.5 Layer 1a 9+ step + 1-2/5 budget; WS-F
bowler-misattribution 5-9 step + 1-2/5 budget).

No leading Phase 1 candidate; no patch authorized; no sub-findings
promoted. Phase 4 catalogue candidate logged (over_history
internal-consistency assertion).

Empirical-budget status: 2/5 → 2/5 (UNCHANGED).
Methodology insights running total: 23 (unchanged).
Memo: files/docs/investigations/workstream_recent_overs_partial_render_investigation.md (10 sections, ~200 lines).
```

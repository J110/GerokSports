# Handoff — Session continuation document

**Last update**: 2026-05-21 (post-C31, workstream D fix-chain landed)
**Branch**: `derive-not-detect`
**Status**: Workstream D's investigation-then-fix chain closed across 8 commits (C26 memo skeleton → C27 D1-prelim → C28 D1-fix → C29 D2-prelim cross-fixture → C30 D2-prelim refinement → C30b D2-fix structural-surface check → C31 D2-fix code → C32 this docs close-out). D1 (bowler em-dash sentinel at over-end-coincident wickets) and D2-Layer-1a (broadcast-vs-deterministic dismissed-name attribution at WICKET-ATTRIB) both shipped as code. Empirical validation gated on next DCKKR replay; predicted flips locked at §6 of `workstream_d_rotation_root_investigation.md`. Falsification budget unconsumed (0/5 across entire chain — all advances static).

**Next session entry point: empirical validation of D1 + D2 predicted flips on next DCKKR replay.** Secondary unblocked paths (independent of replay status): §12 catalogue extension (override-as-4th-instance + S12 non-discriminable-predicate-signature), C20b surface_pair populate, workstream E skeleton (F1017 phantom-wicket), C29b Scout schema extension. See "## Session continuation — C26–C31" section below for the full context.

Entry point for next Cowork session. Read this file first, then `CLAUDE.md`, then `Architecture_HANDOFF.md`, then the design memos at:
- `files/docs/investigations/temporal_coupling_investigation_brief.md` (C10–C12.5b: the static-analysis methodology + cascade-root localization)
- `files/docs/investigations/c13_fc5_audit_memo.md` (the §7.2 7-gate audit on 4 shapes + Shape B selection)
- `files/docs/investigations/stream_gap_reconciliation_design.md` (B-η chain §1–§13: 5 empirical falsifications + investigation-strategy pivot)
- `files/docs/investigations/state_mutation_site_catalogue.md` (C9: 38 mutation sites + 2 async callbacks)
- `files/docs/investigations/dckkr_20260521_cc_investigation_brief.md` (the operator-side brief + §0 reframe)
- `files/docs/investigations/sm_as_orchestrator_design.md` §7 (the standing 7-gate audit framework) + §12 (dual-state-write defect-class catalogue — C17, cross-referenced from §12.7 to the new memo below)
- **`files/docs/investigations/surface_pair_defect_class_family.md`** (NEW C20: family-level instance catalogue, 9 placeholder rows from DCKKR replay, per-row populate deferred to C20b)
- **`validate_dckkr_replay_observations.md`** (21-frame observation log — entry data for workstream D)

## Session continuation — C19–C24 (workstream B closure)

This session ran 2026-05-21 post-C18. Eight commits landed
(C19A1/A3/A4/A5, C20, C21, C22, C23). Session opened with operational
validation of the C14 Shape B fix and closes with workstream B's
wicket-correctness γ-bundle landed at empirical baseline.

### Validation gate result — DCKKR 2026-05-21 (validate_dckkr_20260521_155356)

Two distinct CROSS-FIELD-PAIRING-REJECT events fired in production
during the validation replay (~58 min wall time, ov 0.0 → 11.5):

- **F210** at 16:06:35 — Δscore=+6 / Δballs=-8 (backwards-overs
  cross-field; proposed 28-0(1.3) vs current 22-0(2.5))
- **F1015** at 16:47:14 — Δscore=0 / Δballs=0 / Δwkts=+2
  (zero-time double-wicket; proposed 89-6(10.4) vs current 89-4(10.4))

C14 Shape B predicate is doing load-bearing work — caught two
orthogonal Shape-B-class defects (backwards-overs + zero-time
double-wicket). The F-η-pattern (forward Δscore=+5, Δballs=+10) did
NOT surface in this replay window; the gate caught different defect
classes than its design memo emphasized. C14 sign-off accepted on
"predicate is correct, gate position is correct, gate is reachable
via apply_scorer_decision call site" basis.

Three trace-emission gaps surfaced during validation diagnostics:
- DIRECT-SCORE-COMMIT emissions = 0 (BOARD-side path not exercised)
- trace_beta_sm_wicket_dispatch tag absent from codebase (deleted
  between C15 authoring and HEAD)
- No typed wicket-event trace tags emitted

All three addressed in C19A1–A5 (counterfactual framing tightened on
the legitimate_pair comment, trace_beta restored at
_apply_wicket_fall_only, trace schema note added to operations doc,
preflight tag-existence check added as a launch-checklist step).

### Gate bundle baseline (validate_dckkr_20260521_155356)

```
4 trace_beta_sm_wicket_dispatch emissions detected via
  ball_event.type == "WICKET" fallback (captured trace pre-dates
  C19A3's typed emission landing).

trace_gamma_w_symbol_at_wicket:                 FAIL × 2  (Rahul, Rana)
trace_gamma_fow_name_matches_striker_at_wicket: PASS      (internal-consistency only)
trace_gamma_bowler_w_increment_on_dispatch:     FAIL × 4
```

Total: **5 PASS / 3 FAIL across 8 assertions** (3 existing + 3 new γ
+ 2 reused existing as gate-bundle members). Detection in the new
assertions uses fallback paths for the pre-C19A3 captured trace;
future replays will exercise the C19A3 typed emission path.

### Three forcing-function findings — skeleton-then-assertion methodology

- **C21 — Nissanka W→· revert is UI-layer, not state-layer
  (refines §2.1).** The trace's `ui_after.this_over` preserved W
  correctly at frame 855 position 4 in `next_this_over[4:]`. The UI
  revert observed at Obs 17b happens downstream of trace emission, in
  the WebSocket-render layer. The §2.1 surface-pair scope therefore
  splits: Surface B canonical (pipeline state, holds) vs Surface A
  weaker (UI render path, reverts) — not within the pipeline state
  itself. (Distinct from Obs 4 / Obs 11 reverts which ARE in trace
  state — those remain in §2.1 proper.)
- **C22 — both surfaces stale at same striker pointer value
  (refines §2.5).** `trace_gamma_fow_name_matches_striker_at_wicket`
  PASS × all detected wickets — pipeline-internal consistency holds
  even though cricket reality diverged 3/3 times per Obs 16/18/19/21.
  Rotation-lock-starvation corrupts both adjacent surfaces
  (`ball_event.striker_this_ball` at wicket frame N AND
  `pipeline.striker` at frame N-1) at the SAME stale value.
  Cricket-vs-pipeline divergence requires ground-truth assertion
  infrastructure outside the trace data — scoped as workstream D.
- **C23 — bowler identity = em-dash sentinel at 2/3 captured wicket frames
  (refines §2.6).** At wicket frames the pipeline's
  `current_bowler` often reads as the literal `—` placeholder
  (frame 400 Rahul, frame 679 Rana). Only frame 855 (Nissanka)
  resolved a real bowler name (`Sunil Narine`). The
  rotation-lock-starvation root therefore extends to BOWLER identity,
  not just batter-striker. Surfaced via the assertion's FAIL output
  itself — would not have been visible from the observation log alone.

### Workstream D — promoted to highest-impact unblocked workstream

**Original framing** (per the C19/B2 scope note): D = rotation-root
revisit (batter-striker pointer staleness causing FOW name swap per
Obs 16/18/19/21).

**Expanded scope after C22 + C23 findings:** D now encompasses
- Batter-striker pointer staleness at wicket frames (original scope)
- Bowler identity unresolved (em-dash sentinel) at wicket frames (new)
- Both share the same upstream root — rotation-lock fires on neither
  pointer at wicket-event boundaries.

**C23b (bowler-W fix) is BLOCKED on D.** Adding `update_bowler` at
the wicket-dispatch path would credit an em-dash entry in 2/3 of
captured cases — worse than no credit (pollutes bowler-card
namespace with a sentinel). The bowler-identity-resolution defect
must close before C23b can land cleanly.

Workstream D's entry data:
- `files/logs/deliveries/validate_dckkr_20260521_155356/` — full
  captured artifact (trace JSONL, pipeline.log, scout dump, mp4)
- `validate_dckkr_replay_observations.md` — 21-frame replay log
- C19A3's `trace_beta_sm_wicket_dispatch.resolution_src` payload
  discriminates P2 (event.dismissed) vs P3 (SM.self.striker fallback)
  attribution paths — informs root localization
- `files/docs/investigations/state_mutation_site_catalogue.md` (C9)
  — candidate sites for bowler-identity-lock failures

### Methodology track record — 7 transferable insights across 3 sessions

The discipline's insight-accumulation rate is itself load-bearing.
Four insights from prior sessions; three new this session:

**Prior sessions:**
1. **F1 cascade-closure pattern** — one-edit fix can close N bug
   classes (F1 session).
2. **Predicate-trail / static-analysis methodology** — full
   cascade-root localization at near-zero commit cost (B-η session).
3. **Commit-design drift** — design memos can predict FAIL→PASS
   flips on tags that have been deleted between memo-authoring and
   HEAD; pre-validation tag-existence check needed. C19A5 delivers
   the preflight check; the meta-finding was the C14 validation's
   trace_beta-absent surprise.
4. **Budget-class mismatch in brief authoring** — code sub-tasks
   fit 5-call budgets; memo/comparative-analysis sub-tasks need
   8–12. Brief authoring needs to differentiate; this session's
   Phase 1 split into 1a/1b after the budget exceeded.

**New (this session, C19–C24):**
5. **Skeleton-then-populate forcing function** — instance-catalogue
   skeletons surface observation-discipline gaps when populate-time
   work discovers Obs entries lack data for (a)-(e) axes. Demonstrated
   3× in C21/C22/C23 findings above; planned populate path for C20b.
6. **UI-layer vs state-layer disambiguation via trace** — operator
   observations from UI render may not match trace state; assertions
   that read trace data exclude UI-render defects. C21's Nissanka
   case is the canonical example.
7. **Both-surfaces-stale-at-same-value** — internal-consistency
   assertions PASS when rotation-lock corrupts adjacent surfaces in
   sync; cricket-vs-pipeline ground-truth assertions are a separate
   infrastructure layer not in trace scope. C22's finding scopes
   workstream D and bounds B2's value as a regression detector.

Pattern continues to accumulate at the meaningful rate flagged in
prior HANDOFFs. Each session contributes 1–3 transferable insights;
the track record is itself a load-bearing artifact.

### This session's commits

```
4f79613 C23: B3 — trace_gamma_bowler_w_increment_on_dispatch assertion (no fix; deferred to C23b)
6817481 C22: B2 — trace_gamma_fow_name_matches_striker_at_wicket assertion
b327ed1 C21: B1 — trace_gamma_w_symbol_at_wicket assertion (surface_pair_defect_class_family §2.1)
e051cfa C20: surface_pair_defect_class_family.md skeleton — 9 instance placeholders
74e90dd C19A5: preflight tag-existence check before validation launch
ceeb4e0 C19A4: schema note — tags nested under scorer.decisions[].tag
7557d47 C19A3: restore trace_beta_sm_wicket_dispatch emission at _apply_wicket_fall_only
5a80b8f C19A1: tighten counterfactual framing on legitimate_pair predicate provenance
```

### Next session's first action — SUPERSEDES PRIOR "Next session's first action" SECTION

The prior "If a fresh production trace exists..." framing further
down in this document is superseded: **open workstream D investigation.**
No fresh-replay-as-validation-gate is the unblocked next move —
the gate already fired on DCKKR 2026-05-21 with results above.

Workstream D entry session sequence:
1. Read `surface_pair_defect_class_family.md` §2.5 + §2.6 plus the
   three forcing-function findings above
2. Read `validate_dckkr_replay_observations.md` Obs 2/3/9/16/17/18/19/21
   (the rotation-lock and bowler-identity moments)
3. Examine the captured trace for `resolution_src` distribution
   across wicket events — how many P2 vs P3 attributions?
4. Examine `pipeline.current_bowler` transitions across the captured
   trace — when does it enter/exit the em-dash sentinel?
5. Derive candidate root-localization hypotheses per the standard
   temporal-coupling investigation methodology (C10 brief + C9
   mutation-site catalogue), with §12.4 detection methodology + §12.6
   audit obligation cross-referenced

Deferred work tracked elsewhere:
- **C20b** — per-row (a)-(e) populate of `surface_pair_defect_class_family.md`
  §2.1–§2.9 with full evidence from Obs N anchors. Independent of D;
  can land anytime; will likely produce more forcing-function findings.
- **C21b** — W→· revert site identification in the symbol-commit path.
  Most plausible candidate per static analysis:
  `_rewrite_eyes_this_over_from_event` at `score_manager.py:695`
  ("Fix A: SM-authoritative rewrite of eyes-side `over_mgr.this_over`").
  Needs fresh replay with C19A3 emission firing for per-frame
  `this_over` diff inspection.
- **C23b** — bowler-W increment in the actual wicket-dispatch path
  (NOT `_apply_wicket_fall_only`, which the trace confirms is not
  being reached for these captured wickets — they dispatch via
  ABSORBED_LEGAL gap_finalize_wicket per the docstring). BLOCKED on
  workstream D resolving the em-dash bowler-identity case.

## Session continuation — C26–C31 (workstream D fix chain)

This chain ran 2026-05-21 post-C25. **8 commits landed** (C26, C27, C28, C29, C30, C30b, C31, C32). Pre-commit Layer 1.5 (now 36 ledger + 6 cross-field + 3 D1 + 3 D2 = 48 cases) + Layer 2 (30 balls) held on every commit. **Falsification budget unconsumed: 0/5 empirical cap across the entire chain.** All advances static (predicate-trail, cross-fixture grep, structural-surface check) per Meta-finding #1 (static-analysis methodology at near-zero commit cost).

### Workstream D chain — commit ledger

```
e04324f C31:  H-D2-Layer-1a fix — broadcast-vs-deterministic override at WICKET-ATTRIB
4c50344 C30b: D2-fix structural-surface check — override gate ruled out, WICKET-ATTRIB site confirmed single-site
d7c7bdf C30:  D2-prelim refinement — Signal 1 falsified, fix surface relocated, S8/S9/S10
151ee49 C29:  D2-prelim — Scout dismissed-field cross-fixture absence verified, H-D2-Layer-1 bifurcated
7553473 C28:  H-D1 fix — Candidate C dual-source consensus at wicket-dispatch bowler read
6d0bac9 C27:  D1-prelim — static-falsification verdicts on Candidates A/B/C
85b3169 C26:  workstream D investigation memo — 2 hypotheses + sub-finding S1
```

### Predicted-flip claims (locked at §6 of workstream_d memo; gated on next DCKKR replay)

| Assertion | Pre-fix baseline (C24) | Post-C31 predicted (next replay) |
|---|---|---|
| `trace_gamma_bowler_w_increment_on_dispatch` | FAIL × 4 | **FAIL × 2** (F400 + F679 close via tracker fallback; F855 + F1017 require D2 ladder + W-W7 phantom-wicket split-off) |
| `trace_gamma_w_symbol_at_wicket` | FAIL × 2 | **PASS** + cricket-truth FOW flips at F855 (direct broadcast-override) + F983 (S9 cascade closure). F1017 unchanged (workstream surface E split-off per S10). |
| `trace_gamma_fow_name_matches_striker_at_wicket` | PASS (internal-consistency) | PASS (unchanged — invariant tests internal consistency, not cricket truth) |

### Sub-findings index (S5–S12, all static)

- **S5** — Scout-contract gap is architecturally distinct from rotation-lock-starvation root. Two non-overlapping fixes (Layer 1a downstream / Layer 1b upstream).
- **S6** — Predicate-trail static-falsification at zero empirical cost extends beyond temporal-coupling defect class to Scout-contract gaps. Audit pattern transferable across hypothesis types.
- **S7** — D-chain empirical-falsification budget unconsumed (0/5 cap) across ~2.6k frames surveyed read-only.
- **S8** — Signal 1 (tracker LEADER cross-check) statically falsified at F855/F983/F1017. Trackers are NOT independent of the rotation-lock-starvation root; deterministic-rotation override is the BW07-analog for the striker side.
- **S9** — F855 → F983 cascade closure. F855 misattribution makes F983 structurally underivable; closing F855 auto-closes F983 with no independent fix surface. **Second instance of F1-session cascade-closure-via-one-edit pattern** (Meta-finding #1 from prior session).
- **S10** — F1017 is phantom-wicket detection, not misattribution. Qualitatively different defect class. Split off to workstream surface E candidate.
- **S11** — Signal/site decoupling pattern. Predicate-trail reformulation can move the predictive signal (tracker LEADER → broadcast-striker) without moving the implementation surface (`test_pipeline.py:13063` stable from §3.5 through C31). Transferable across audits where the predicate-trail produces a "wrong signal, right site" finding.
- **S12** — Non-discriminable-predicate-signature defect-class pattern. When two cases (one regression-protected, one investigation-target) share the same observable predicate at a site, single-site fix is structurally impossible without plumbing. Peer entry to dual-state-write in `sm_as_orchestrator_design.md` §12.

### Deferred-work index update

- **C29b (or successor)** — Scout prompt schema extension to emit structured `dismissed` field. Closes contract gap at source. OUT of D-scope; candidate for separate workstream surface. Empirical basis: 0/182 wicket-signal frames across 4 fixtures.
- **Workstream surface E** — phantom-wicket detection (F1017 case). Defect class qualitatively distinct from F855/F983 misattribution. Root-localization needed on the wicket-event-detection path (`ball_detector.detect` or upstream wicket-signal aggregation).
- **§12 catalogue extensions** — (a) `STRIKER-SM-BROADCAST-DISAGREES-DETERMINISTIC` override as the 4th instance of dual-state-write (after F-α-shadow / F1-B-ε / B-η-FC5 / D1-BW07-bowler-em-dash); (b) S12 non-discriminable-predicate-signature as a new peer defect-class entry.
- **C23b** — bowler-W increment in the wicket-dispatch path. Unblocked once next replay validates D1 + D2-Layer-1a predicted flips.

### Methodology track record extension

Four new transferable insights from this chain bring the running total to **11** (7 from prior sessions + 4 from C26-C31):

- **S6** — predicate-trail extends beyond temporal-coupling defect class to Scout-contract gaps.
- **S9** — cascade-closure-via-one-edit pattern, second instance. F1 was first; S9 is the second.
- **S11** — signal/site decoupling pattern.
- **S12** — non-discriminable-predicate-signature defect class.

## The objective

Shift the pipeline from a detection-heavy architecture to a derivation-first architecture that consumes a strict 5-primitive Scout contract:
1. Runs (cumulative score)
2. Overs (current over notation)
3. Batter identities (names from squad list, not raw OCR strings)
4. Bowler identity
5. First striker after innings start / new batter after wicket

Everything else on the UI is deducible from these primitives plus per-frame deltas. The session's discipline: any classification of code as "scar tissue" or "defect class" is a hypothesis pending the §7.2 seven-gate audit. The audit is the load-bearing safety mechanism.

## Headline result this session — F-η cascade-root localization via static analysis + Shape B fix

**Shape B cross-field pairing gate (`ad151fd`)** at `apply_scorer_decision` (test_pipeline.py:4517) closes the B-η cascade root that produced the DC vs KKR session's f304 anchor corruption + downstream wicket-dispatch failures.

**Cascade root concretely localized via production `/tmp/pipeline.log` audit (C12.5b):**

```
F302 TRACK score: 45 → 49 (post-event immediate, grace=1)
F302 TRACK overs: 4.4 → 4.5 (fast-confirm, natural overs increment F302)
F303 POISONED                                                  (upstream block)
F304 TRACK score: 49 → 54 (post-event immediate, grace=1)      ← CASCADE ROOT
F304 TRACK overs: 4.5 → 6.3 (post-event immediate, grace=0)    ← CASCADE ROOT
```

The `(post-event immediate, grace=N)` suffix is the FC5 log signature from `consistent_tracker.py:304-305`. Two FC5 fires at F304 admit both halves of the bad PANT/WARD/SHAMI overlay frame's reading via `_post_event_grace=2` inherited from f302's `on_ball_event()` reset, combined with `_is_suspicious` returning False for upward score jumps under +30 and forward overs jumps.

**Empirical pairing criterion (C13 §2.1):**

```
legitimate_pair(d_score, d_balls, d_wickets) ≡
    (d_balls == 1 AND 0 ≤ d_score ≤ 7 AND d_wickets ∈ {0, 1})  -- legal delivery
  OR
    (d_balls == 0 AND 0 ≤ d_score ≤ 5 AND d_wickets ∈ {0, 1})  -- extras-only
```

Verified empirically: 127/127 benign DIRECT-SCORE-COMMIT firings (GTRR 80 + DCKKR 47) satisfy `legitimate_pair`. F304 fails (d_balls=10, d_score=+5).

## Session meta-findings — two architectural insights worth headlining

This session's accumulating discipline track record produced two transferable methodology insights, alongside the prior session's F1 cascade-closure headline:

### Meta-finding 1 — Static-analysis methodology at near-zero commit cost

Predicate-trail reading + cross-fixture empirical verification produces full cascade-root localization without an instrumentation cycle per hypothesis. The C9 catalogue + C10 static analysis + C11 predicate semantics + C12 sub-candidate elimination + C12.5b pipeline.log parse = **full cascade-root localization at near-zero commit cost** (5 docs commits, zero behavior change), followed by C13 audit + C14 fix at 2 functional commits.

The previous methodology (instrument → replay → fix) had a budget cost of one diagnostic commit per hypothesis. The static-analysis methodology had a budget cost of one docs commit per hypothesis-class. **This is a defect-class identification methodology distinct from "instrument-replay-then-fix", suited specifically to temporal-coupling defect classes that captured-replay flattens (per §0.3 of the C8 brief reframe).**

### Meta-finding 2 — Falsification cascade as methodology signal-of-correctness

Five empirical + eight static falsifications + one acceptance is the methodology's signal of correctness, not its signal of failure. The discipline rule "every classification is a hypothesis pending empirical verification" produces a falsification cascade BY DESIGN; the budget mechanism (5-empirical-falsification methodology-retirement trigger from C9 §11 + C10 §1.2) ensures the cascade terminates productively rather than open-loop. **A complete falsification chain is an architectural finding, not a failure.**

These two meta-findings join F1's cascade-closure (prior session) and the §7.2 7-gate audit (prior session) as the workstream's accumulating discipline track record.

## Architectural posture

### Detection vs Derivation (unchanged from prior session)
- **Detection (5 primitives only)**: vision provides runs, overs, batter names, bowler name, first-striker/new-batter signals.
- **Derivation (everything else)**: this_over tokens derive from per-frame (Δruns, Δovers, wicket events). Striker rotation derives deterministically from first-striker + per-ball runs sequence + wicket events.
- Squad-canonical name resolver enforces that raw Scout name tokens get rejected if they don't fuzzy-match to a squad member.

### SM as sole UI authority (unchanged + reinforced)
- WS payload reads Recent Overs from SM's `over_history`.
- Striker rotation determined by SM; broadcast indicator is corroboration only.
- Squad-canonical name resolver enforced at all bat1_name / bat2_name / broadcast_striker / bowler_name commit sites.
- Initial striker at cold-start exit reads `broadcast_striker` field correctly (F1, `437d952`).
- **New (C14): cross-field pairing gate at `apply_scorer_decision` rejects single-frame commits whose (Δscore, Δballs, Δwickets) tuple violates `legitimate_pair`.**

### No-speculative-fixes discipline (refined further this session)
Every fix commit must cite specific trace evidence — concrete frame numbers — that proves the diagnosed cause. "Likely" / "probably" language is investigation-only, never authorization to commit. If diagnosis can't be confirmed from existing data, add static-analysis + pipeline.log audit first, re-run, then fix.

**The "captured-replay drives investigation" assumption is RETIRED** for temporal-coupling defects (per C8 §0.3). Captured-replay remains canonical as a falsification mechanism and regression-detection substrate; it does NOT drive root-localization for defect classes where the temporal signature flattens under deterministic replay.

### §7.2 seven-gate audit checklist (standing precondition; gates 1–7 unchanged)

The framework added gate 7 (cross-fixture verification) in the prior session per F1 closure. This session applied all 7 gates to 4 candidate shapes (A/B/C/D) at C13 — first deep multi-shape audit in the chain. Gate-6 (predicted-flip with concrete frame numbers, applied recursively) is non-negotiable per the falsification track record.

**New discipline nuance — static vs empirical falsification:**

- **Empirical falsification** counts against the methodology-retirement budget (5-falsification cap per C9 §11 / C10 §1.2). Replay or instrumentation cycle empirically disproves a hypothesis.
- **Static falsification** does NOT count against the budget. Code-reading or predicate-trail pass conclusively proves a hypothesis is impossible at the proposed site. Zero-cost; apply liberally before any instrumentation commit.

This session: 5 empirical falsifications (B-η chain) + 8 static falsifications (C10 + C11 + C12) + 1 acceptance (Shape B). Without the static-vs-empirical distinction, the chain would have hit the retirement budget at C11.

## This session's commit ledger — chronological

This session ran 2026-05-21. **16 commits total.** Pre-commit gate (Layer 1.5 + Layer 2) held on every commit. Predicted-flip claims empirically validated or statically falsified at each step.

```
b49e48b chore(diagnostics): B-η instrumentation pass — three additive trace tags + replay scaffold
e3171eb chore(diagnostics): replay-scaffold warm-seed mode for f304-anchor reproduction
86299e0 docs(design): B-η stream-gap reconciliation memo + post-instrumentation empirical findings
78b4835 chore(diagnostics): replay-only LLM-extractor fallback for f304-anchor reproduction
ac06fa6 docs(design): B-η memo §10 — empirical f304 evidence + cascade-root pivot
237d227 chore(diagnostics): DIRECT-SCORE-COMMIT instrumentation + GTRR fixture support
e19f72a docs(design): B-η memo §11-§13 — fifth falsification + investigation-strategy pivot + meta-finding
a99d82c docs(brief): C8 reframe — Step 1 retarget + temporal-coupling block on Steps 2/3
af19dd2 docs(design): C9 state-mutation site catalogue — 38 write sites + 2 async callbacks
2df4061 docs(brief): C10 temporal-coupling investigation — sixth hypothesis, static analysis
5833857 docs(brief): C11 static-analysis pass — Outcome A (qualified) on FC5 post-event grace
b6e3c70 docs(brief): C12 overs-side static-analysis closure — score-side fully localized, overs-side narrowed
c05c4b6 docs(brief): C12.5b — pipeline.log audit closes gate 6 with concrete frame numbers
639fa4a docs(audit): C13 §7.2 7-gate audit on FC5 candidate fix shapes — Shape B selected
ad151fd fix(test_pipeline): C14 cross-field pairing gate at apply_scorer_decision — closes B-η F304 cascade root
770db98 test(C15): permanent gate-6 verification + baseline + predicted-flip claim for C14 fix
```

## Trace assertion library (UPDATED post-C24)

Eight empirically-grounded invariants in `files/tests/trace_session_assertions.py` (5 existing + 3 new γ-bundle members from C21/C22/C23). Baseline on `validate_dckkr_20260521_155356`:

| Assertion | Pre-C19 baseline | Post-C24 baseline on DCKKR 2026-05-21 |
|---|---|---|
| `trace_alpha_bowler_runs_sum` | FAIL gap=4 (DCKKR pre-fix) | PASS |
| `trace_beta_sm_wicket_dispatch` | FAIL — 3 misses | FAIL × 4 (4 wickets detected via ball_event fallback; typed emission landed C19A3 — next replay validates) |
| `trace_epsilon_initial_striker` | PASS | PASS |
| `trace_compound_tokens` | PASS | PASS |
| `trace_extras_total` | PASS | PASS |
| `trace_gamma_w_symbol_at_wicket` (NEW C21) | — | **FAIL × 2** (Rahul ov 5.0 / Rana ov 8.0 — W→· revert in this_over state) |
| `trace_gamma_fow_name_matches_striker_at_wicket` (NEW C22) | — | PASS (internal-consistency only; cricket-vs-pipeline divergence undetectable here, scoped to D) |
| `trace_gamma_bowler_w_increment_on_dispatch` (NEW C23) | — | **FAIL × 4** (no bowler-W increment within 30-frame lookahead at any captured wicket) |

**Total post-C24: 5 PASS / 3 FAIL across 8 assertions.** The γ-bundle (3 new assertions) supersedes `trace_beta_sm_wicket_dispatch` as the wicket-correctness gate signal — trace_beta tests dispatch occurrence; the γ-bundle tests dispatch correctness across W-symbol, FOW-name, and bowler-W surfaces.

Runner: `python files/scripts/run_trace_session_assertions.py <trace.jsonl>`.

## Validation gate — STATUS: FIRED on DCKKR 2026-05-21 (see top-of-document Session continuation section)

The C14 validation gate **already fired** on `validate_dckkr_20260521_155356` (full results in the C19–C24 session continuation section above). C14 sign-off accepted on "predicate is correct, gate reachable, two distinct Shape-B-class defects caught" basis — F-η pattern specifically did not surface but the predicate's generality is empirically established.

Standing pattern for future sessions remains: ship with predicted-flip claim, validate on next natural production session. The original "predicted: PASS on trace_beta" framing is **SUPERSEDED** by the γ-bundle baseline above — the new gate signal is FAIL × 2 (w_symbol) + FAIL × 4 (bowler_w) → expected PASS after workstream D resolves the rotation-lock-starvation root and C21b/C23b land. C19's "extend Shape B coverage to catch-up branch + end-of-over hook" alternative is also retired: empirical evidence from DCKKR shows the root is upstream (rotation pointer staleness at wicket frames), not coverage gaps in the gate's call sites.

## Workstream status by area

### F-η Shape B fix (shipped C14, VALIDATED 2026-05-21)
Cross-field pairing gate at `apply_scorer_decision` (test_pipeline.py:4602/4617/4631). Empirically validated on DCKKR 2026-05-21 — 2 distinct CROSS-FIELD-PAIRING-REJECT events fired in production (F210 backwards-overs, F1015 zero-time double-wicket). The gate's call site is `test_pipeline.py:12466` (non-poisoned SCORER path). DSC path was NOT exercised in the validation replay; gate-coverage of DSC remains counterfactual per C19A1's tightened comment. Permanent gate-6 test at `files/tests/test_cross_field_pairing_gate.py` (6 cases) wired into Layer 1.5.

### B-ι (locked-SM-state prevents resync) — RETIRED as standalone workstream
Per DCKKR 2026-05-21 evidence: `trace_alpha_bowler_runs_sum` flipped PASS post-C14, indicating no resync-prevention symptom in production. B-ι hypothesis dissolved as cascade symptom of B-η, consistent with the dual-state-write defect-class pattern. **No standalone B-ι memo needed.**

### B-θ (over-boundary bowler credit) — RETIRED as standalone workstream
Same as B-ι. trace_alpha gap closed post-C14. B-θ collapsed as cascade symptom of B-η. The bowler-W increment defect surfaced via `trace_gamma_bowler_w_increment_on_dispatch` is a SEPARATE defect (wicket-event commit path, not over-boundary bowler credit) and is the target of workstream D + C23b, not a B-θ reopening.

### Workstream D (rotation-root revisit) — D1 + D2-Layer-1a CODE SHIPPED (empirical validation gated on next replay)
See "Session continuation — C26-C31" section above for full chain. D1 (over-end-coincident bowler em-dash sentinel at `_apply_wicket_fall_only`) and D2-Layer-1a (broadcast-vs-deterministic dismissed-name attribution at WICKET-ATTRIB) both shipped as code. Predicted flips: `trace_gamma_bowler_w_increment_on_dispatch` FAIL×4 → FAIL×2; `trace_gamma_w_symbol_at_wicket` FAIL×2 → PASS + cricket-truth FOW at F855 + F983 (S9 cascade closure). F1017 split off to workstream surface E (S10 phantom-wicket detection class). C23b (bowler-W increment in wicket-dispatch path) unblocked once next replay validates these predicted flips.

### Captured-replay scaffold (commits b49e48b–237d227)
- `files/scripts/replay_captured_scout_trace.py` — captured-Scout replay scaffold
- Supports `--seed-frame / --seed-striker / --seed-non-striker / --seed-bowler` (warm-seed mode)
- Supports `--enable-llm-extractor` (production Extractor.extract() via Groq Llama)
- Supports `--fixture {dckkr, gtrr}` (cross-fixture)
- Emits four observation tags: `FRAME-TRUST-GATE`, `OVERS-JUMP-STREAK-STATE`, `POISON-STREAK-AT-COMMIT`, `DIRECT-SCORE-COMMIT`
- **Limitation (§0.3 retired-assumption):** does NOT drive `apply_scorer_decision` — only SM-side `on_frame()`. Captured-replay cannot reproduce temporal-coupling defects; serves as falsification mechanism + regression detector, not localization tool.

### State-mutation-site catalogue (C9)
`files/docs/investigations/state_mutation_site_catalogue.md`: 38 write sites + 2 async callbacks across `score_manager.py`, `test_pipeline.py`, `eyes/scoreboard.py`. Score, wickets, overs, batter-identity, bowler-identity primitives.

**Three gate-bypass classes surfaced:**
- §7.1 `_inn[*]` direct-write bypass (6 sites) — state-recovery Phase-2 + POISON-RECAL forced reset
- §7.2 async-callback writes (2 sites: striker/bowler on_lock) — falsified statically in C10 §3 (not actually async)
- §7.3 hot-resume path (5 sites) — startup-only, deprioritized

**Catalogue is itself a gate-6 instrument** (per C9 §11): future "the defect is at site X" hypotheses can be checked against the table for whether X is a real mutation site, what gates protect it, what the invocation pattern is.

### UI render layer bugs (separate workstream — unchanged from prior session)
- B-γ (Recent Overs panel drops entries), B-δ (UI bottom-strip striker), `trace_extras_total` UI inconsistency — out of scope for SM/pipeline workstream.

## Pipeline tracks (unchanged)

### Track 1 — State derivation (production pipeline)
Entry: `files/test_pipeline.py` main loop. Frame source: `files/eyes/capture/udp_frame_source.py` (UDP MPEG-TS via ffmpeg subprocess).

Status: C14 fix in place; operational validation pending; cascade-root localized at F302/F304 via static analysis + pipeline.log empirical evidence.

### Track 2 — Clip extraction (OpenScout)
Disabled (`USE_OPEN_SCOUT=0`). Will not enable until Track 1 fully validated.

## File paths

```
files/test_pipeline.py             # Main pipeline; apply_scorer_decision at :4356
                                   # C14 cross-field pairing gate at :4517
files/score_manager.py             # State machine (~6500 lines)
files/eyes/scoreboard.py           # Scoreboard + sb.set bottleneck at :1188-1481
                                   # DIRECT-SCORE-COMMIT emission at :1481 (C6)
files/eyes/consistent_tracker.py   # ConsistentReadTracker — 5 fast-confirm paths
                                   # FC5 post-event grace at :294-306 (cascade root)
files/eyes/scoreboard.py           # batting_card / bowling_card / squad resolution
files/confidence_tracker.py        # ConfidenceTracker (team / striker / bowler)
                                   # NOT the FC5 site (don't confuse with consistent_tracker.py)
files/eyes/vision.py               # SCOUT_PROMPT_SHORT (default), SCOUT_PROMPT (verbose)
files/eyes/agent.py                # Extractor.extract() — LLM fallback path
                                   # Uses int|None syntax (Python 3.10+)
files/eyes/extract_regex.py        # Regex-primary parse_strip (returns None on STRIP miss)
files/eyes/frame_ledger.py         # Frame Fate Ledger
files/eyes/udp_frame_source.py     # UDP MPEG-TS frame source
files/cricket_rules.py             # validate_diff invariants
files/trace_emitter.py             # KNOWN_TAGS registry (180+ tags incl. C6/C10/C14)

scorecard-ui/app/page.tsx          # Main UI
scorecard-ui/app/components/BattingCard.tsx

files/tests/symptom_class_assertions.py    # 11 assertion functions (12 classes)
files/tests/trace_session_assertions.py    # 5 trace-session assertions
files/tests/test_sm_derivation_ledger.py   # Layer 1.5 — 36 balls + 6 cross-field gate cases
files/tests/test_pipeline_captured_replay.py  # Layer 2 — captured-Scout replay
files/tests/test_cross_field_pairing_gate.py  # C15 permanent gate-6 (6 cases)
files/tests/fixtures/dc_vs_kkr_2026_152064_ledger.json
files/tests/fixtures/gt_vs_rr_2026_commentary_first_innings.md

files/scripts/run_trace_session_assertions.py     # Trace session assertion runner
files/scripts/replay_captured_scout_trace.py      # Captured-replay scaffold (C-commits)
files/scripts/analyze_gap_detected_retro.py
files/scripts/audit_scar_tissue_targets.py

files/docs/investigations/temporal_coupling_investigation_brief.md  # C10–C12.5b chain
files/docs/investigations/c13_fc5_audit_memo.md                     # C13 7-gate audit
files/docs/investigations/stream_gap_reconciliation_design.md       # B-η chain §1–§13
files/docs/investigations/state_mutation_site_catalogue.md          # C9 catalogue
files/docs/investigations/dckkr_20260521_cc_investigation_brief.md  # operator brief + §0 reframe
files/docs/investigations/dckkr_20260521_session_observations.md    # observations + C15 §
files/docs/investigations/sm_as_orchestrator_design.md              # §7 framework + §12 (C17 dual-state-write catalogue)

deploy/systemd/*.service           # pipeline, recorder, live-clips, ui
deploy/Caddyfile
.github/workflows/deploy.yml
.git/hooks/pre-commit              # Layer 1.5 + Layer 2 gate; venv-Python preference (C15)
```

## Launch sequence (operational reference, unchanged)

```bash
cd ~/Projects/SportsComm

# Clear stale state
rm -f files/match_state_cache.json logs/openscout-local_*.jsonl
rm -f /tmp/pipeline.log /tmp/ffmpeg.log

# Terminal A — UI
cd ~/Projects/SportsComm/scorecard-ui && npm run dev

# Terminal B — pipeline (Python 3.12 venv)
cd ~/Projects/SportsComm
export FRAME_SOURCE=udp
export FRAME_SOURCE_UDP_URL='udp://0.0.0.0:9999?fifo_size=10000000&buffer_size=2097152&overrun_nonfatal=1'
export FRAME_SOURCE_UDP_ALLOWED_DIMENSIONS='1920x1080,1280x720'
export CRICBUZZ_MATCH_ID=<match_id>
export CRICBUZZ_MATCH_SLUG=<slug>
export BMF_SESSION_ID="validate_$(date +%Y%m%d_%H%M%S)"
export USE_OPEN_SCOUT=0
export SCOUT_PROMPT_MODE=verbose
export SCOUT_RAW_DUMP=1
export PYTHONUNBUFFERED=1
export SCOUT_DEDUP_SHADOW=1
export SKIP_PREMATCH_S=0
files/.venv/bin/python files/test_pipeline.py 2>&1 | tee /tmp/pipeline.log

# Terminal C, D — see prior HANDOFF for ffplay viewer + ffmpeg dual-output stream
```

UI: http://localhost:3000. Validation fixtures:
- DC vs KKR (`files/logs/deliveries/20260508_191946/match_4621b9f8.mp4`, start ~09:30)
- GT vs RR (`files/logs/deliveries/8a0c6c14/match_8a0c6c14.mp4`, start ~40:30)

## Fresh-checkout setup

The pre-commit hook at `.git/hooks/pre-commit` prefers the project venv Python (`files/.venv/bin/python`, 3.12) over system `python3` (3.9 on most macOS). This is necessary because the C15 cross-field-pairing-gate test imports `eyes/agent.py` which uses `int | None` syntax (Python 3.10+).

The hook lives outside the tracked git tree (`.git/hooks/` is gitignored). **Run `scripts/setup_precommit.sh` after a fresh clone** (or after the canonical hook content changes). The script:

- Verifies `files/.venv/bin/python` exists; fails loudly with a clear setup-instruction message if not (does NOT silently fall back to system `python3`)
- Writes the canonical hook content (Layer 1.5 + Layer 2 + venv preference) idempotently to `.git/hooks/pre-commit`
- Marks it executable
- Prints verification instructions

Verify post-install by running any `git commit` (hook fires automatically) OR by invoking the harnesses directly under venv:

```sh
files/.venv/bin/python files/tests/test_sm_derivation_ledger.py
files/.venv/bin/python files/tests/test_pipeline_captured_replay.py
```

## What NOT to touch

Per prior session + this session's findings:

- Queue B (`_pending_bowler_ball_credits`) — load-bearing 3-way-race resolver per §7.1
- `_ScoutRetryBuffer` — active queue across Groq 429 backoff per §7.1
- `broadcast_extra` / `extras_type` — parallel fields per §7.5
- Cold-start synth token-distribution heuristic in `_synthesize_cold_start_ball_events`
- `confidence_tracker.py` ConfidenceTracker class — battle-tested, foundational
- Existing deterministic-rotation override at `score_manager.py:4295-4325` — load-bearing
- **NEW: C14 cross-field pairing gate at `apply_scorer_decision` (`test_pipeline.py:4517`)** — the cascade-closer for B-η
- **NEW: Permanent gate-6 test at `files/tests/test_cross_field_pairing_gate.py`** — the empirical regression detector for C14
- F1's field-name fix at `_accept_initial:2789-2808`
- F-α-shadow fix in `_capture_multi_ball_shadow_state:4515+`
- F-α-queue in `_apply_absorbed_event` (5310-5358)
- Pre-commit hook venv preference — deviating from this will silently break L1.5 imports

## What's in flight behind feature flags (unchanged)

- `SM_INLINE_MULTI_BALL` — default off
- `SM_POST_WICKET_SLOT_DIFF` — default off
- `USE_OPEN_SCOUT` / `USE_OPEN_SCOUT_SPANS`

## Next session's first action

1. Read this HANDOFF.md
2. Read `Architecture_HANDOFF.md` + `CLAUDE.md`
3. Read `files/docs/investigations/workstream_d_rotation_root_investigation.md` (the C26-C31 investigation memo, ~10kB)
4. `git log --oneline derive-not-detect | head -15` for full session context — expected HEAD chain: C32 → C31 → C30b → C30 → C29 → C28 → C27 → C26 → C25 → C24

**Primary unblocked path — empirical validation of D1 + D2 predicted flips on next DCKKR replay.** Run a fresh DCKKR replay (or any fixture with sufficient wicket density) and check the γ-bundle assertions:
- `trace_gamma_bowler_w_increment_on_dispatch` — predicted FAIL × 4 → FAIL × 2 (F400 + F679 close via D1 tracker fallback)
- `trace_gamma_w_symbol_at_wicket` — predicted FAIL × 2 → PASS + cricket-truth FOW name flips at F855 (D2 broadcast-override direct) + F983 (S9 cascade closure)
- If predicted flips land → C23b unblocks; close D chain in a C33-tier docs commit
- If predicted flips do not land → **first empirical falsification** for the D chain (budget cap 5/5 still open); next move is plumbing at `score_manager.py:4411` (the override gate ruled out as single-site at C30b, but the empirical falsification authorizes the escalation per §3.4d.6)

**Secondary unblocked paths (independent of replay status; all static, all C20b-tier):**
- **§12 catalogue extension** — landed in `sm_as_orchestrator_design.md`: (a) `STRIKER-SM-BROADCAST-DISAGREES-DETERMINISTIC` override as 4th dual-state-write instance, (b) S12 non-discriminable-predicate-signature as new peer defect-class entry. Skeleton-then-populate pattern (Meta-finding #5).
- **C20b** — `surface_pair_defect_class_family.md` §2.1–§2.9 per-row (a)-(e) populate. Independent of D; can land anytime; will likely produce more forcing-function findings (the skeleton-then-populate pattern was the #5 meta-finding source — populate-time discovers Obs gaps).
- **Workstream surface E skeleton** — F1017 phantom-wicket detection class memo (parallels C26's structure: open a `workstream_e_phantom_wicket_detection.md`, hypothesis-then-fix discipline).
- **C29b** — Scout prompt schema extension (`dismissed_batter` field). Out of D-scope but unblocked.

**Do NOT:** open B-ι / B-θ memos (retired pre-C26); attempt C23b before D1 + D2 empirical validation; touch BW07 clear ordering at `score_manager.py:5965` (Candidate A territory, retired by risk-surface argument at C27); attempt single-site fix at `score_manager.py:4411` without the empirical-falsification trigger from a failed replay (ruled out by S12 / non-discriminable predicate signature at C30b).

## Standing discipline (refined this session)

Architecture principles user repeatedly enforces (carried from prior session, refined this session):

- "Detection establishes identity, derivation maintains state"
- "SM is the final authority on the UI; everything else should not have a say"
- "Once high confidence reached, LOCKED — only explicit events unlock"
- "Real-time first, no offline-only solutions"
- "Consolidate and validate together — minimize ping-pong validation cycles"
- **"No speculative fixes. Find the root cause and confirm. Always."** — this session: 5 empirical + 8 static falsifications enforced the rule recursively across 16 commits.
- Any "scar tissue" / "defect class" label is a hypothesis pending the §7.2 audit.
- **Static-falsification ≠ empirical-falsification.** Static is zero-cost; apply liberally before any instrumentation commit. Empirical counts against the methodology-retirement budget (cap: 5 per session per defect-class chain).
- **Captured-replay does NOT drive root-localization for temporal-coupling defects.** It remains canonical as falsification + regression-detection substrate.
- **A complete falsification chain is an architectural finding, not a failure.** Document each chain's meta-finding in HANDOFF alongside the positive cascade-closure findings (F1, etc.).

## Trace-and-Detect (v1, unchanged)

Per CLAUDE.md trace-and-detect section. Per-frame trace records to `logs/trace/<SESSION_ID>.jsonl`. New trace tags this session:

- `FRAME-TRUST-GATE`, `OVERS-JUMP-STREAK-STATE`, `POISON-STREAK-AT-COMMIT` (C6 instrumentation pass)
- `DIRECT-SCORE-COMMIT` (C12 — at sb.set bottleneck)
- `CROSS-FIELD-PAIRING-REJECT` (C14 — at apply_scorer_decision gate)
- `REPLAY-LLM-EXTRACT-RECOVERED` (replay-scaffold-only, not in production)

## Pipeline feature flags (unchanged)

- `USE_OPEN_SCOUT` (default 0): disabled until Track 1 fully validated
- `USE_OPEN_SCOUT_SPANS` (default 0)
- `SM_INLINE_MULTI_BALL` (default 0): flag flip blocked pending fresh trace
- `SM_POST_WICKET_SLOT_DIFF` (default 0)

## Working venv

Project venv at `files/.venv/bin/python` (Python 3.12). **Pre-commit hook uses this venv** (C15 change). System `python3` (Python 3.9 on macOS) does not support the Python 3.10+ syntax used in `eyes/agent.py`.

## Session-end architectural insight

This session's most important architectural insights, validated empirically across 16 commits:

**(1) Static-analysis methodology + predicate-trail reading + pipeline.log audit produces full cascade-root localization at near-zero commit cost.** The chain C9 + C10 + C11 + C12 + C12.5b produced 8 static falsifications and concrete F302/F304 localization with zero behavior change. Followed by C13 audit + C14 fix at 2 functional commits.

**(2) A complete falsification cascade is an architectural finding, not a failure.** Five empirical + eight static falsifications + one acceptance is the discipline working as designed. The budget mechanism (5-empirical-falsification cap per defect-class chain) ensures the cascade terminates productively rather than open-loop.

**(3) Two-parallel-state-surfaces is a recurring defect class.** Three instances confirmed across two sessions: F-α-shadow (`sb.bowling_card` vs `sb._inn["bowling_card"]`), F1/B-ε (`card.get("broadcast")` vs `card.get("broadcast_striker")`), B-η/FC5 (`sb._tracker.confirmed` vs SM `_handle_warm` streak gate). To be catalogued in `sm_as_orchestrator_design.md` §12 in C17 with detection-signal + remediation-pattern documented.

The workstream pauses cleanly at the operational validation gate. Next move is operational, not engineering. The trace assertion library + 16-commit investigation chain are the standing data-collection + verification mechanisms for any future production session.

Track record of architectural insights accumulated across sessions (**11 transferable insights total**):

- **F1 session (3 sessions back)**: cascade-closure pattern — one-edit fix can close N bug classes; §7.2 gate 7 (cross-fixture verification) catches cascade reach.
- **B-η session (2 sessions back)**: static-analysis-with-predicate-trail methodology + falsification-chain-as-architectural-finding + dual-state-write defect class.
- **C19-C24 session (prior)**: commit-design drift (preflight tag-existence check) + budget-class mismatch (memo work needs 8–12 calls, code work fits 5) + skeleton-then-populate forcing function + UI-layer vs state-layer disambiguation via trace + both-surfaces-stale-at-same-value (internal-consistency PASS when rotation-lock corrupts adjacent surfaces in sync).
- **C26-C31 session (this one — workstream D fix chain)**:
  - **S6** — predicate-trail static-falsification extends beyond temporal-coupling defect class to Scout-contract gaps.
  - **S9** — cascade-closure-via-one-edit pattern, second instance (F1 was first); F855 fix auto-closes F983 with no independent surface.
  - **S11** — signal/site decoupling pattern: predicate-trail reformulation moves the predictive signal but not necessarily the fix site.
  - **S12** — non-discriminable-predicate-signature defect class: when two cases share an observable predicate at a site, single-site fix structurally impossible without plumbing.

Each session contributes one or more transferable methodology insights that survive into the next session's discipline. **The discipline track record is itself a load-bearing artifact** — preserve it; document new insights as they accumulate.

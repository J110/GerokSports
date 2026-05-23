# Workstream C29b — Scout dismissed-schema extension static investigation (step-1)

**Date.** 2026-05-23.
**Branch.** `derive-not-detect` @ HEAD = `0a1b4d2` (WS-I step-3 close-out).
**Empirical-budget status.** 2/5 — UNCHANGED (static-only this step; no replay consumed).
**Outcome.** **C29b cascade-closure dividend statically FALSIFIES on TWO independent axes — workstream should NOT proceed as Phase 1 second pillar.** Axis 1: **source modality blocker** (the bottom-strip pixel content does not render dismissed-batter names; the Scout VLM has no pixels to extract — HA + HB prompt-only and prompt+extractor candidates falsify at gate 1). Axis 2: **cascade-closure misframing** (none of the 3 stated downstream targets — surface E phantom-wicket, phantom-runs, WS-F bowler-misattribution — depends on dismissed-batter ground truth; the strategic argument was misframed at Phase 1 plan-lock). **Recommendation: DEFER C29b** and re-select Phase 1 second pillar (candidates enumerated in §10). HE (downstream `_derive_dismissed_name` defer) remains viable as **WS-D §3.5 Layer 1a** with a narrower target (γ-w-symbol cricket-truth FOW on F855/F983, workstream D scope) — but that is NOT the C29b cascade-closure dividend.

---

## §1 Current Scout contract — exhaustive enumeration

**Scout STRIP grammar (canonical output format, both prompts).**

`SCOUT_PROMPT_VERBOSE` at `files/eyes/vision.py:246-248`:

```
STRIP: <team_or_null> <runs>-<wkts> (<overs>) | extras=<n_or_null> | this_over=<symbols_or_null> | <striker> <r>(<b>) | <nonstriker> <r>(<b>) | <bowler> <w>-<r> (<o>)
```

`SCOUT_PROMPT_SHORT` at `files/eyes/vision.py:349-351`: identical STRIP grammar. Plus optional `CHASE: TARGET <n> | REQUIRED RUN-RATE <f> | NEED <n> FROM <n> BALLS` for innings-2.

**Fields emitted:**

| Field | Type | Source pixel modality | Wicket-related? |
|---|---|---|---|
| `team` | string\|null | Team abbreviation in strip | No |
| `runs`-`wkts` | int-int | Score header (e.g., `74-2`) | **Yes — wickets COUNT only, no dismissed-batter name** |
| `overs` | float-style | Strip overs counter | No |
| `extras` | int\|null | Strip extras token | No |
| `this_over` | string\|null | Strip per-ball symbols (e.g., `Wd 1 6 . W`) | Indirectly via `W` symbol position |
| `striker` (name + r(b)) | string-string-string\|null | Strip striker row | **Yes — striker pre-wicket; post-wicket the row vanishes or rotates** |
| `non_striker` (name + r(b)) | string-string-string\|null | Strip non-striker row | **Yes — non-striker pre-wicket; post-wicket the row may rotate** |
| `bowler` (name + w-r overs) | string-string-string\|null | Strip bowler row | Indirectly via bowler-W increment (`w` field) |
| `frame_phase` | enum | LLM classification | Yes (`fielder_reaction` post-wicket) |
| `camera_view` | enum | LLM classification | No |

**Absent fields.** `dismissed_batter`, `dismissed`, `out_batter`, `last_wicket_name`, `fow_name` — **none in the grammar, on either prompt variant**.

**Anti-priming guards (load-bearing for falsification).** `SCOUT_PROMPT_VERBOSE:265-279` + `SCOUT_PROMPT_SHORT:365-376`: "Output ONLY names you literally transcribed in VISIBLE_TEXT this frame. NEVER from training data, NEVER from the hint, NEVER from a previous frame." The prompt explicitly forbids hallucinating names not present in the source pixels. The 2026-05-11/12 hallucination regression (cited in both prompts) is the post-mortem anchor that drove this guard.

**How wickets are currently detected.** Per `test_pipeline.py:13083-13097` (`WICKET-ATTRIB` site):

1. Wicket DETECTION via `ball_detector.detect()` returning `ball_event.type ∈ {"WICKET", "WICKET_LATE"}` — driven by `wickets`-counter increment in the strip score-header (NOT by dismissed-name extraction).
2. Wicket NAME via `_attribute_dismissed_with_broadcast_override` (`test_pipeline.py:3152`) — synthesizes `ball_event.dismissed` from `_striker_this_ball` (the pre-rotation snapshot captured at `:13065`) + `_pending_bcast_striker_key` (broadcast override hint). **No Scout-emitted dismissed field consumed here — there is no such field.**
3. Wicket SLOT clear via `scoreboard.apply_known_wicket_increment(ball_event.dismissed)` + `score_manager._infer_wicket` chain.

**Current dismissed-name source chain:**

```
ball_event.dismissed
  ←  _attribute_dismissed_with_broadcast_override(_striker_this_ball, _pending_bcast_striker_key, ...)
  ←  _canonical_active_slot(score_mgr, scoreboard, "striker")
  ←  score_mgr.self.striker  ←  apply_striker_event / apply_striker_identity_resolved / apply_striker_identity_proposed
```

The current pipeline derives dismissed-name from the pipeline's own striker pointer (which is the WS-D rotation-lock-starvation root). No Scout primitive in the STRIP grammar would alter this chain.

---

## §2 Empirical anchor — 0/182 baseline verified + side-channel rule-out

**WS-D §3.4b cross-fixture survey verified** (read-only, no re-replay):

| Fixture | Frames | Wicket-signal frames | `dismissed`-field present in `raw_response` |
|---|---|---|---|
| `validate_gtrr_20260520_180715` | 841 | 51 | **0** |
| `validate_dckkr_20260521_155356` | 749 | 64 | **0** |
| `validate_dckkr_20260521_070545` | 618 | 49 | **0** |
| `validate_20260520_114437` | 415 | 18 | **0** |

**Total: 0/182 wicket-signal frames** carry any structured `dismissed` / `dismissed_batter` field. This is the WS-D-locked baseline; no re-survey needed.

**Side-channel inference rule-out (HC pre-check).** Does any existing Scout output contain a name string parseable as dismissed_batter via post-processing? The strip grammar emits 3 name slots (striker / non_striker / bowler). On post-wicket frames, the striker row typically vanishes or transitions to the new batter — leaving no trace of the dismissed name in the current frame's STRIP output. The dismissed name appears ONLY in:

- **Full-screen FoW graphic overlays** (camera_view="graphic", frame_phase="graphic"). Sparse (1-3 per innings); timing-delayed 5-30s post-wicket; the Scout currently sets `has_strip=false` on these frames and DOES NOT extract overlay text into structured fields. The overlay name list (e.g., "Pathum Nissanka c & b Cameron Green 40 (27)") is NOT in the STRIP grammar.
- **Wicket-replay overlays** (camera_view="replay") — even sparser; not currently parsed.
- **Player profile pop-ups** during between-play — career-stat overlays; not currently parsed.

**Conclusion.** No existing Scout structured output contains a dismissed-batter name that could be salvaged via downstream post-processing of the current contract. HC (side-channel inference from existing primitives) collapses to HE (downstream derive from striker pointer + broadcast override) — they are functionally equivalent; both fall back to the pipeline's own striker pointer, which is the WS-D root.

---

## §3 Downstream consumer enumeration

Every site reading dismissed-batter identity, categorized:

### (a) Wicket-event commit (canonical §15 path)

- `apply_wicket_event(event: WicketEvent)` — `score_manager.py:880, 922` reads `event.dismissed_batter` for FoW append + slot-clear payload. Source: `event` builder consumes `ball_event.dismissed` set at `test_pipeline.py:13091`.
- `_infer_wicket` → `_set_dismissed` at `score_manager.py:5841-5875` — uses `event.dismissed` as P2 path; falls back to `self.striker` as P3 path. **The P2 path is structurally unreachable today** (0/182 wicket-signal frames carry the field).
- `score_manager.py:5979` — `dismissed_batter=best_dismissed` writes into the WicketEvent dataclass during inline construction.

### (b) UI render

- `score_manager.py:6946` — `"dismissed_batter": dismissed` in the post-commit card payload (consumed by UI mirror via `build_full_payload`).
- `score_manager.py:6955, 6977` — WicketEvent dataclass kwargs at canonical-construction sites.

### (c) Bowler-W attribution (WS-F territory)

- `score_manager.py:881` — `"batter": event.dismissed_batter` in the bowling-card delta payload. Used for FoW table emission, NOT for bowler-W increment.
- **No coupling to bowler identity.** Bowler-W increment lives in `_apply_wicket_fall_only` and reads `event.bowler`, not `event.dismissed_batter`. Surface §2.6 (FOW-count vs bowler-card-W increment) has zero dependency on dismissed-batter ground truth.

### (d) Striker rotation (post-wicket cascade via WS-G)

- WS-G PendingCascade (`apply_wicket_event` cascade-defer path) reads `event.dismissed_batter` to identify which slot to clear and which survivor to retain. But the rotation decision is driven by `event.new_batter` (presence/absence determines defer vs immediate-rotate), not by dismissed-batter identity per se.
- **Functional impact of wrong dismissed-name on rotation:** The wrong batter is removed from the at-the-crease pair; subsequent rotations cascade incorrectly. This IS the WS-D rotation-lock-starvation surface — closed at WS-D §3.5 Layer 1a (downstream derive), NOT at C29b prompt extension.

### (e) Phantom-wicket detection (surface E candidate)

- **NO consumer.** Surface E phantom-wicket detection lives on the wicket-event-DETECTION path (`ball_detector.detect`, `scoreboard.apply_known_wicket_increment`), not the dismissed-name derivation path. A phantom-wicket is a wicket-COUNT misread (strip OCR `1` mistaken as `4` or similar). The pipeline detects a wicket where no cricket-wicket occurred; dismissed-batter ground truth doesn't enter the decision.

**Cascade-closure candidates by consumer category:**

| Consumer | Current source | Would C29b structured field help? |
|---|---|---|
| (a) `apply_wicket_event` FoW append | striker pointer via override + broadcast | Marginal — if pixels existed, ground truth could override striker pointer. But pixels don't exist on strip. |
| (b) UI render `dismissed_batter` payload | event.dismissed_batter (downstream) | No source improvement |
| (c) Bowler-W increment | event.bowler (independent) | **No — different field entirely** |
| (d) Striker rotation / WS-G cascade | event.new_batter (presence/absence, not name) | No — name doesn't drive rotation decision |
| (e) Phantom-wicket detection | wickets-counter increment (upstream of dismissed-name) | **No — different code path entirely** |

Only category (a) marginally benefits, and only if source pixels existed. They don't.

---

## §4 Hypothesis enumeration + static falsification

### HA — Prompt-only extension (add `dismissed_batter` to STRIP grammar) — **FALSIFIED at gate 1**

**Shape.** Add `| dismissed=<name_or_null>` to STRIP format in both prompts; extractors read through unchanged.

**Gate 1 — predicate closes a meaningful surface.** FAIL. The bottom-strip scoreboard pixel content does NOT render dismissed-batter names (the strip shows score header + striker + non-striker + bowler + this_over symbols; no dismissed-name field exists in the broadcast graphic on per-frame strip frames). Adding the field to the prompt would either:
- (a) Always return `null` (0/182 → 0/182 — no improvement), because the Scout's anti-priming rules forbid hallucinating names not in VISIBLE_TEXT and the source pixels don't contain a dismissed-name string.
- (b) Hallucinate from training data — explicitly forbidden by the anti-priming rules (the 2026-05-11/12 hallucination regression post-mortem closed this loophole). Re-opening it would re-introduce a known catastrophic regression class.

**Status.** Falsified at gate 1 (static). Source-modality blocker. No empirical-budget cost.

### HB — Prompt + extractor coordinated extension — **FALSIFIED at gate 1 (same blocker as HA)**

**Shape.** Prompt change as HA + regex/agent extractor updated to parse the new field and populate it through the card mutation chain.

**Gate 1.** FAIL (same reason as HA — the source pixels don't contain dismissed-name on strip frames). Updating the extractor doesn't help because the prompt can't extract what isn't rendered.

**Caveat.** HB would be marginally better than HA on FOW-graphic frames IF the prompt also added structured-overlay parsing (which is HD's territory). Without HD's overlay-parsing scaffolding, HB is functionally identical to HA on the dominant per-frame strip modality.

**Status.** Falsified at gate 1 (static).

### HC — Side-channel inference from existing primitives — **COLLAPSES TO HE**

**Shape.** Leave Scout prompt unchanged; add downstream derivation that infers dismissed_batter from cross-signals (striker pre-fall capture, broadcast_striker drop, FoW pattern recognition).

**Gate 1 — distinct from HE?** FAIL. HC is functionally identical to HE: both derive dismissed-batter downstream from the pipeline's own state (striker pointer + broadcast override). The current pipeline ALREADY does this at `_attribute_dismissed_with_broadcast_override` (`test_pipeline.py:3152`). HC ≡ HE in mechanism.

**Status.** Collapses to HE; not a distinct candidate. Falsified as a separate shape.

### HD — Multi-prompt (dedicated wicket-graphic prompt) — **STATICALLY FALSIFIED at gate 1 for the cascade-closure dividend; viable only as a sparse-coverage adjunct**

**Shape.** Trigger a second Scout call on `camera_view="graphic"` + `frame_phase="graphic"` frames post-wicket-signal, using a dedicated prompt that parses FoW graphic overlay text (e.g., "Fall of Wickets: Pathum Nissanka c & b Green 40 (27), Sameer Rizvi b Narine 4 (8), ..."). Extract the most-recent FoW row's dismissed-batter name.

**Gate 1 — predicate closes a meaningful surface.** FAIL for the cascade-closure dividend. Even if HD extracts ground truth from FoW graphic frames, the extraction is:
- **Sparse**: FoW graphics appear 1-3 times per innings, not on every wicket.
- **Timing-delayed**: 5-30 seconds post-wicket. The wicket-event commit at `apply_wicket_event` has already fired with the wrong dismissed-name by then; HD's late ground truth would require a retroactive correction path (separate workstream-class fix; not in scope).
- **Architecturally heavy**: Doubles Scout LLM cost on graphic frames; adds a parallel extraction path; new schema; new caller surface; new failure modes.
- **Cascade-closure-orthogonal**: HD closes (a) marginally on FoW-graphic frames (would override the post-hoc FoW table entry) but does NOT close (c) bowler-W, (d) striker rotation in real-time, or (e) phantom-wicket.

**Status.** Falsified at gate 1 for the cascade-closure dividend. Viable as a separate workstream for FoW table correctness only; not a Phase 1 second-pillar candidate.

### HE — Defer prompt; close downstream `_derive_dismissed_name` — **LEADING candidate (but with narrower scope than C29b's stated cascade-closure)**

**Shape.** Leave Scout prompt unchanged. Close the dismissed-name derivation downstream at `_attribute_dismissed_with_broadcast_override` (`test_pipeline.py:3152`) and the `STRIKER-SM-BROADCAST-DISAGREES-DETERMINISTIC` override gate at `score_manager.py:4411`. This is the WS-D §3.5 Layer 1a fix.

**Gate 1 — predicate closes a meaningful surface.** PASS for the WS-D-scoped γ-w-symbol cricket-truth FOW on F855 (and F983 via S9 cascade closure per WS-D §3.4c.2). Does NOT close C29b's cascade-closure targets (see §5 below).

**Gate 2 — distinct from currently-shipped behavior.** PASS. The current override at `:4411` is the WS-D S8 root (deterministic-rotation wins when it shouldn't on wicket-pending). HE closes that gate.

**Gate 3 — fix-surface attribution.** Mixed. The fix is pipeline-side (production code `score_manager.py`), not assertion-side. Per WS-I candidate-S24 framing, this is a pipeline-side arc — expect ~9 steps + 1/5 budget per the WS-H precedent.

**Status.** Viable but NOT the C29b cascade-closure dividend. **HE is WS-D Layer 1a, not C29b.** Renaming/relabeling would drift the plan.

---

## §5 Cascade-closure verification — LOAD-BEARING audit step

Per the user's decisive factor: if structured `dismissed_batter` cannot statically close at least 2 of the 3 downstream targets, the strategic argument for C29b collapses.

### Target 1 — Surface E phantom-wicket (F1017 case): **FALSIFIES**

**Mechanism.** Surface E is a wicket-COUNT misread at the strip OCR layer (or downstream wicket-event-detection): `ball_detector.detect()` emits `ball_event.type == "WICKET"` based on the wickets-counter strip field incrementing. F1017 fabricated a wicket because the wickets-counter strip OCR jumped (per WS-D §3.4c.3 S10: "no cricket wicket, fabricated dismissal event").

**Does dismissed-batter ground truth help?** **NO.** Even with perfect dismissed-batter extraction:
- If Scout returns `dismissed_batter=null` on F1017 because no FoW graphic ever appeared (no real wicket happened), the pipeline still has `ball_event.type="WICKET"` set from the wickets-counter increment. The downstream commit would either fail closed (null dismissed → ABSORBED) or proceed with the same legacy fallback (`_attribute_dismissed_with_broadcast_override` → `_striker_this_ball`). Either way, the phantom-wicket detection NEEDS a fix at the wicket-event-DETECTION path (`ball_detector.detect`), not at the dismissed-name derivation path.
- WS-D §3.4c.3 S10 explicitly: "Root-localization needed on the wicket-event-detection path (`ball_detector.detect` or upstream wicket-signal aggregation), not the dismissed-name derivation path that H-D2 lives on."

**Verdict.** **FALSIFIED.** Surface E is a different code-path; C29b dismissed-batter doesn't enter the decision.

### Target 2 — Phantom-runs root-localize (§11.3 item 6): **INDEPENDENT (FALSIFIES on dismissed-batter dependency)**

**Mechanism.** Runs appearing without corresponding deliveries — strip score-counter increments outpace ball-detector delivery emissions. Belongs to delivery-detection (`ball_detector.detect()` legal-ball-vs-extras classification), not to dismissed-name derivation.

**Does dismissed-batter ground truth help?** **NO.** Phantom-runs cohort overlaps wicket-frames only incidentally (a wicket-ball can also be a wide / no-ball with attached runs). The phantom-runs root is in the runs-counter delivery-classification path, not the dismissed-name path. Even if some phantom-runs cases happen to coincide with wicket frames, the structural fix sits in `ball_detector` or upstream OCR consistency-checks — not at the dismissed-batter schema layer.

**Verdict.** **INDEPENDENT** (read: dismissed-batter ground truth does NOT close phantom-runs). Effectively a FALSIFY for cascade-closure-dependency purposes.

### Target 3 — WS-F bowler-misattribution residual surfaces (§11.3 item 3): **FALSIFIES**

**Mechanism.** Per `surface_pair_defect_class_family.md` §2.6: "Bowler-card W field — no increment fires on dismissal." Wickets accumulate in FoW but bowler-card W stays 0 (Obs 17, 19, 21 anchors). The defect is in the bowler-W increment path (`_apply_wicket_fall_only` not reached because wickets dispatch via `ABSORBED_LEGAL gap_finalize_wicket`).

**Does dismissed-batter ground truth help?** **NO.** Bowler-W increment reads `event.bowler`, not `event.dismissed_batter`. They are independent fields on the same WicketEvent. Per `score_manager.py:881` the dismissed_batter populates the `"batter"` key in the bowling-card delta payload (FoW table emission), but the bowler-W increment lives separately at `_apply_wicket_fall_only` reading `event.bowler`. The two fields don't intersect.

C23b (per Architecture §0.6) explicitly states: "bowler-W increment in the actual wicket-dispatch path. The `_apply_wicket_fall_only` function is NOT reached for the captured wickets (they dispatch via `ABSORBED_LEGAL gap_finalize_wicket`)." This is a dispatch-path-reachability problem, orthogonal to dismissed-batter identity.

**Verdict.** **FALSIFIED.** WS-F bowler-misattribution is on a different field of the same event; the dismissed-batter schema extension doesn't touch the bowler-W increment path.

### Summary

| Target | Cascade-closure under C29b? | Reason |
|---|---|---|
| Surface E phantom-wicket | **FALSIFIES** | Different code path (wicket-event-detection, not dismissed-name) |
| Phantom-runs | **INDEPENDENT (FALSIFIES on dependency)** | Different code path (runs-counter delivery-classification) |
| WS-F bowler-misattribution | **FALSIFIES** | Different field on same event (bowler vs dismissed_batter) |

**Cascade-closure dividend: 0/3 targets close. The strategic argument for C29b as Phase 1 second pillar collapses.**

Per the user's decisive factor and the stop conditions: **"Cascade-closure dividend statically FALSIFIED for ALL 3 targets → STOP, report; C29b's strategic value collapses; recommend deferral or scope narrowing to single downstream surface."**

---

## §6 §7.2 7-gate audit on the LEADING REMAINING candidate (HE — WS-D §3.5 Layer 1a — NOT C29b)

Since HA/HB/HC/HD are falsified and HE collapses to a different workstream (WS-D Layer 1a) with a NARROWER target (γ-w-symbol cricket-truth FOW on F855/F983, NOT the C29b cascade-closure targets), the 7-gate audit on HE is for documentation only — it does not justify proceeding with C29b under its stated scope. If user authorizes a pivot to HE as a renamed sub-workstream targeting γ-w-symbol cricket-truth FOW, the gates below apply.

| Gate | HE / WS-D §3.5 Layer 1a status |
|---|---|
| **1** | Static-falsifies cricket-truth FOW on F855 (direct via override gate inversion) + F983 (cascade closure per WS-D §3.4c.2 S9). PASS conditional on §3.4d.5 plumbing-required discriminator. |
| **2** | Override gate at `score_manager.py:4411` is load-bearing for DC-vs-KKR ball-4.6 regression protection (Rahul-dismissed-attribution). PASS only with the lookahead/persistence/drift-detection plumbing flagged at WS-D §3.4d.5; without plumbing, single-site fix is structurally impossible (S12 non-discriminable-predicate-signature pattern). |
| **3** | Pipeline-side fix at `test_pipeline.py:13083-13097` + `score_manager.py:4411`. Pipeline-side per S22/S24 framing → 1/5 budget per empirical replay. |
| **4** | Regression-direction posture: new override behavior could regress the DC-vs-KKR ball-4.6 case. Permanent gate-6 regression detector REQUIRED. |
| **5** | State lifecycle: no new persistent state required if plumbing uses event-scoped lookahead. New persistent state required if drift-detection is chosen — would need a new lifecycle integration with WS-G PendingCascade or §15-fence. |
| **6** | Predicted-flip: γ-w-symbol on validate_dckkr_20260521_155356 LIVE-cohort FAIL × 2 (Rahul + Rana) → ? — closes Rana via override gate; Rahul stays (different sub-class per C21 finding). γ-fow-name: PASS preserved (Shape A handles None case). |
| **7** | Cross-fixture verification: requires empirical replay (DC-vs-KKR ball-4.6 regression cohort + 14 other live-cohort fixtures). 1/5 budget cost expected. |

**Gate 2 + Gate 5 are the load-bearing risks.** Per WS-D §3.4d.5: the override gate sits at a non-discriminable predicate signature site (S12 pattern). Single-site fix is structurally impossible; plumbing required. The plumbing surface (lookahead vs persistence vs drift-detection) is itself a step-1-investigation-class question. **HE is a multi-step pipeline-side workstream, not a Phase 1 second-pillar candidate.**

---

## §7 Risk assessment — Scout prompt blast radius (HA/HB/HD residual)

Even though HA/HB/HD are falsified at gate 1, document the blast radius for completeness in case a future workstream re-opens the prompt-extension question:

### Non-wicket-frame regression risk

- **SCOUT_PROMPT_VERBOSE caller count:** 1 (the `prompt = SCOUT_PROMPT.format(vision_hint=hint)` call at `vision.py:534`).
- **Single Scout call per frame**: every camera_view, every frame_phase, every wicket / non-wicket frame triggers the same prompt. Adding `dismissed_batter` to the STRIP grammar would force the LLM to emit the field on EVERY frame, not just wicket frames.
- **Expected emission rate on non-wicket frames:** null (anti-priming rules forbid hallucinating). Non-zero hallucination rate would be a catastrophic regression class.
- **Token-budget impact:** SCOUT_PROMPT_SHORT was deliberately tuned to ~1.5K input tokens to stay under Groq's 300K TPM cap at 60fpm. Adding a dismissed-batter slot expands the schema; the per-frame output token cost increases marginally; the prompt token cost increases by ~30-50 tokens. Manageable but non-trivial — would require re-tuning.

### Regex-extractor blast radius

- `extract_regex.py` regex at `:44` (`_STRIP_LINE`) and downstream tokenizers parse the STRIP body. Adding a new pipe-separated slot would break the regex if the slot count is hard-coded. Verification at `parse_strip()` (`:234`) required before any prompt change.

### LLM agent fallback (`agent.py`)

- LLM fallback triggers on regex-parse failure. Extending the schema means the agent JSON schema must include `dismissed_batter`; current schema does not. New field on every frame → LLM JSON output expands → JSON validation surface grows → new failure modes.

### Schema-compatibility with existing trace fixtures

- All 166 on-disk traces in `logs/trace/` were captured under the current Scout schema. None contain dismissed_batter primitives. Any new assertion that REQUIRED dismissed_batter would be inapplicable on every historical trace — a worse Shape B (S23) than the current γ-w-symbol case.

**Blast-radius verdict.** Non-trivial. The prompt-extension blast radius alone would warrant scope-narrowing even if the source modality blocker (HA/HB falsified at gate 1) did not exist.

---

## §8 Predicted-flip table for step-2 — VOID under falsification

C29b step-2 (prompt + extractor patch) is FALSIFIED before step-2 can be sketched. No predicted-flip table can be locked because:
- HA/HB cannot extract what isn't rendered → no predicted flip on dismissed_batter source rate.
- HC ≡ HE → HE's predicted flips belong to WS-D Layer 1a, not C29b.
- HD predicted flips on FoW table correctness only — orthogonal to the cascade-closure dividend.

**Pseudo-predicted flips if user authorizes scope narrowing to HE (= WS-D §3.5 Layer 1a):**

| Detector | Trace | Pre | Post (HE) |
|---|---|---|---|
| γ-w-symbol LIVE-cohort | `validate_dckkr_20260521_155356` | FAIL × 2 (Rahul + Rana) | FAIL × 1 (Rana closes; Rahul stays — different sub-class per WS-D §3.4c.5) |
| γ-w-symbol other 14 LIVE-cohort fixtures | (per WS-I step-3 baseline) | 17 FAILs | Some subset closes; case-by-case classification at HE step-2 |
| γ-fow-name | all traces | PASS / true-mismatch | UNCHANGED (Shape A handles None; HE strengthens populated case) |
| γ-bowler-w | all traces | PASS | UNCHANGED (independent field) |
| η-cascade | all traces | PASS | UNCHANGED (orthogonal) |
| L1.5 ledger / L2 captured-replay | all | PASS | UNCHANGED |

But again: this is HE / WS-D Layer 1a's predicted-flip table, NOT C29b's. The cascade-closure dividend (surface E + phantom-runs + WS-F) is 0/3.

---

## §9 Sub-findings index (S24+) — candidate S24 NOT confirmed; new candidate S25 surfaced

### Candidate S24 (arc-length-by-fix-surface-category) — NO new evidence this step

The WS-I step-3 candidate-S24 framing (arc length scales with fix-surface category — pipeline-side ~9 steps + 1/5 budget vs assertion-side ~3 steps + 0/5 budget) is NOT directly tested by C29b step-1, which is a static investigation that converged to FALSIFICATION (not a fix-surface-category data point). S24 remains a 2-instance candidate awaiting 3rd-instance confirmation from a future workstream that actually lands a fix.

### Candidate S25 (NEW) — Strategic-framing-vs-source-modality static check

**Statement (CANDIDATE — not yet promoted).** When a workstream's strategic argument hinges on "ground truth from upstream contract closure," the gate-2 audit must include a **source-modality precondition check**: does the upstream contract have access to the pixel/data modality needed to produce the claimed ground truth? In C29b's case, the strategic argument assumed the Scout VLM could extract dismissed-batter names by adding the field to the STRIP schema — but the bottom-strip pixel modality does not render dismissed-batter names anywhere on per-frame frames; the dismissed name appears only on sparse FoW graphic overlays that are a different extraction surface entirely. The strategic argument was misframed because the source-modality precondition was not audited at Phase 1 plan-lock.

**Why this matters.** S22 (WS-H step-9 static-investigation-first protocol) prevented an empirical-budget burn on a fix that would have failed; S25 extends the discipline upstream to prevent strategic-plan-lock burns on workstreams whose framing is structurally impossible. The cost of S25-class burn is plan drift + opportunity cost (Phase 1 second pillar reserved for a workstream that cannot deliver), not empirical-budget consumption — but is potentially larger in calendar-time impact.

**How to apply.** At every Phase-1-plan-lock OR workstream-promotion decision, add a source-modality precondition check to the gate-2 audit: explicitly enumerate the pixel/data modality the proposed fix would consume, verify the modality contains the required signal on the relevant frame cohort, and only then promote.

**Promote to numbered insight?** Single instance. Defer to candidate-S25 status pending second instance. If a future workstream surfaces a similar strategic-vs-modality mismatch, promote at that point.

### Cross-reference to S21 + S23 family

S25 is a **planning-level analog** to S23 (assertion-level schema-precondition). S23: assertion must precondition on schema-presence to avoid silent-FAIL-via-data-absence. S25: workstream-strategy must precondition on source-modality-presence to avoid plan-lock on structurally-impossible objectives. Same mechanical pattern, different scope (assertion-time vs plan-time).

---

## §10 Step-2 entry data — VOID under falsification; Phase 1 second-pillar re-selection required

### C29b step-2 patch surface: **VOID**

No patch surface enumeration. C29b step-2 is not authorized under static-falsification.

### Phase 1 second-pillar re-selection candidates

Per the user's decisive factor + stop conditions, recommendation is **DEFER C29b** and re-select Phase 1 second pillar from the following candidates (ordered by expected payoff + budget economics):

1. **Surface E phantom-wicket investigation** (workstream surface E per Architecture §0.6).
   - Targets the F1017-class defect (wicket-event-detection at `ball_detector.detect` mis-firing on wickets-counter strip OCR drift).
   - Fix surface: pipeline-side (`ball_detector` or upstream OCR consistency-checks).
   - Expected arc: pipeline-side, ~9 steps, 1/5 budget consumption.
   - Cascade-closure dividend: closes phantom-wicket cohort (F1017 + cross-fixture instances); does NOT close WS-F or phantom-runs.

2. **WS-F bowler-misattribution** (§11.3 item 3 + surface_pair §2.6).
   - Targets the C23b dispatch-path-reachability defect (`_apply_wicket_fall_only` not reached because wickets dispatch via `ABSORBED_LEGAL gap_finalize_wicket`).
   - Fix surface: pipeline-side (`apply_wicket_event` cascade routing).
   - Expected arc: pipeline-side, ~6-9 steps, 1/5 budget.
   - Cascade-closure dividend: closes bowler-W increment + FOW-table-vs-bowler-card consistency.

3. **WS-D §3.5 Layer 1a** (downstream `_derive_dismissed_name` + override gate at `score_manager.py:4411`).
   - HE shape per §6 above.
   - Fix surface: pipeline-side.
   - Expected arc: pipeline-side, ~9+ steps (S12 non-discriminable-predicate-signature plumbing required), 1-2/5 budget.
   - Cascade-closure dividend: closes γ-w-symbol cricket-truth FOW on F855 (+ F983 via S9 cascade). Does NOT close surface E or WS-F.

4. **§11.3 surgical items 3-7** (workstream F bowler misattribution / per-batter-ledger conservation / recent-overs partial-render / phantom-runs root-localize).
   - Mixed fix-surface; multiple sub-investigations.

5. **Phase 4 catalogue items** (S23-corollary multi-wicket-per-frame undercount + S23-extension `_final_extras_total` silent-stricter-bound + §12 dual-state-write 4th instance + C20b).
   - Assertion-side or docs-only.
   - Expected arc: short (3-step) per S24 candidate framing.
   - Cascade-closure dividend: zero (architectural cleanup only).
   - **Could provide S24 third-instance confirmation** if landed as a small assertion-side arc.

**Recommended re-selection:** **Surface E phantom-wicket investigation** as Phase 1 second pillar — most aligned with the original C29b cascade-closure framing (surface E was one of C29b's 3 stated targets), but on the correct fix surface (wicket-event-detection, not dismissed-name extraction). Expected delivery profile mirrors WS-H: ~9-step pipeline-side arc consuming 1/5 budget, closing the phantom-wicket cohort.

---

## §11 Status footer + recommended commit-message format

**WS-C29b step-1 status.** **FALSIFIED at static analysis.** C29b cascade-closure dividend collapses on two independent axes (source-modality blocker for HA/HB + cascade-closure misframing for all 3 targets). HE viable but is WS-D §3.5 Layer 1a with a narrower target (γ-w-symbol cricket-truth FOW on F855/F983, NOT the C29b cascade-closure targets).

**Recommended next step.** **DEFER C29b.** Re-select Phase 1 second pillar from §10 candidates. **Surface E phantom-wicket investigation** is the most aligned re-selection (preserves one of C29b's original 3 targets on its correct fix surface).

**Sub-findings added.** Candidate S25 (strategic-framing-vs-source-modality precondition check) — NOT promoted (single instance, awaits second instance). Candidate S24 unchanged (2 instances, awaits third).

**Empirical-budget status.** **2/5 — UNCHANGED.**

**Recommended commit message (docs-only memo commit; DO NOT auto-commit; user authorizes explicitly):**

```
docs(workstream-c29b): step-1 static investigation — C29b FALSIFIED on source-modality blocker + cascade-closure misframing; recommend defer + re-select Phase 1 second pillar

Static-falsification chain on C29b Scout schema extension converges on
FALSIFICATION at two independent axes:

Axis 1 — Source-modality blocker (HA + HB fail at gate 1):
  Bottom-strip pixel content does not render dismissed-batter names.
  Per `files/eyes/vision.py:246-248` (verbose) + `:349-351` (short),
  the STRIP grammar emits striker + non_striker + bowler name slots
  but NO dismissed-batter slot. The dismissed name appears only on
  sparse FoW graphic overlays (camera_view='graphic'), not on the
  per-frame strip modality the Scout currently extracts. Adding the
  field to the prompt would either always be null (Scout's anti-priming
  rules forbid hallucinating names not in VISIBLE_TEXT — re-opening
  this loophole would re-introduce the 2026-05-11/12 hallucination
  regression class) OR catastrophically hallucinate. HC collapses to
  HE (both derive downstream from striker pointer). HD multi-prompt
  on FoW-graphic frames would extract sparse + delayed ground truth
  that cannot drive real-time wicket-commit decisions.

Axis 2 — Cascade-closure misframing (all 3 targets falsify):
  Surface E phantom-wicket — different code path (wicket-event-
    detection at `ball_detector.detect`, NOT dismissed-name
    derivation; per WS-D §3.4c.3 S10).
  Phantom-runs — different code path (runs-counter delivery-
    classification at `ball_detector`, NOT dismissed-name).
  WS-F bowler-misattribution — different field on same event
    (event.bowler, NOT event.dismissed_batter; per surface_pair §2.6
    + Architecture §0.6 C23b).

C29b cascade-closure dividend = 0/3 targets. The strategic argument
for C29b as Phase 1 second pillar collapses.

HE (downstream `_derive_dismissed_name` + override gate at
`score_manager.py:4411`) remains viable but is WS-D §3.5 Layer 1a with
a narrower target (γ-w-symbol cricket-truth FOW on F855 + F983 via S9
cascade closure). Pipeline-side arc with S12 non-discriminable-
predicate-signature plumbing required — ~9-step pipeline-side arc per
S22/S24 framing; 1-2/5 budget. NOT the C29b dividend.

Recommend: DEFER C29b. Re-select Phase 1 second pillar from §10
candidates. Most-aligned recommendation: SURFACE E phantom-wicket
investigation (preserves one of C29b's stated targets on its correct
fix surface — wicket-event-detection, not dismissed-name extraction).

Candidate S25 (NEW; NOT yet promoted): Strategic-framing-vs-source-
modality static check. When a workstream's strategic argument hinges
on "ground truth from upstream contract closure," gate-2 audit must
include a source-modality precondition: does the upstream contract
have access to the pixel/data modality needed to produce the claimed
ground truth? S25 is the planning-level analog to S23 (assertion-level
schema-precondition). Awaits second-instance confirmation before
promotion to numbered insight.

Empirical-budget status: 2/5 → 2/5 (UNCHANGED).
Static-falsification count: 4 (HA + HB + HC≡HE collapse + HD).
Cascade-closure verification: 0/3 targets close.
Memo: files/docs/investigations/workstream_c29b_scout_dismissed_schema_extension.md (11 sections, ~370 lines).
```

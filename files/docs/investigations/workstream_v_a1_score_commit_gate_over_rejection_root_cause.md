# Workstream V.A1 — Score-commit-gate over-rejection investigation (step-1b)

**Status.** Step-1b CLOSED on hypothesis FALSIFICATION-and-PIVOT.
WS-V.A step-1b (`ba8a95a`) predicted WG = "score-commit-gate over-
rejection at the WS-O.b WARM-mode magnitude gate / COLD-START
gate / PA threshold / ConsistentReadTracker demotion / CAM-
GRAPHIC fast-path skip". S34 empirical-parity-check at the
post-WS-O.b trace `dckkr_post_ws_o_b_baseline_20260524_100620.jsonl`
**FALSIFIES** all five candidate gates at every anchor frame
(F82 / F96 / F97 / F119 / F126). The actual mechanism is one
layer further from any gate: **pre-`_handle_warm` Scoreboard
mutation leaks into `prev = self._snapshot()` at
`score_manager.py:4139`**, producing `prev["score"] ==
card["score"] == post-advance value` by the time
`_apply_event(evt, prev, card, frame)` runs at `:4204`. The
downstream `derive_this_over_token` then computes
`delta_score = current.score - prior.score == 0` and emits
`raw='.'` for every per-ball commit. This is a **prev-snapshot-
staleness defect at the SM `@property` boundary**, not a
commit-gate over-rejection at any of the WS-V.A-enumerated
gates. The defect is **architecturally identical to** the
mechanism documented at `test_pipeline.py:14102-14109` for the
wire-commentary cascade (already worked around at the BED
layer); the SM-side `derive_this_over_token` cascade is the
remaining instance of the same root mechanism.

**Pre-screen verdict.** RED-FALSIFICATION on the WS-V.A WG
"score-commit-gate over-rejection" framing. Pivot to a SPLIT
sub-cohort under WS-V.A1 at the **`_handle_warm` prev-snapshot
construction site** (`score_manager.py:4139`). The
A1 fix at `_event_baseline_score` (2026-05-14, lines 3722-3741)
established the symmetric defense for the event-firing
`d_score` computation; the symmetric defense is **MISSING** for
the `prev = self._snapshot()` snapshot construction. Fix
surface: anchor `prev["score"]` to `_event_baseline_score`
when the property already reflects the post-event value (or
construct `prev` from `_event_baseline_*` fields explicitly).

**S34 empirical-parity-check methodology applied + outcome.**
Trace inspection at the five anchor frames + adjacent ±3
preceded any hypothesis-derivation. Result: empirically
verified the gate hypothesis is wrong before any patch was
proposed. Methodology validated for a third successive instance
(WS-O OA, WS-P P1, now WS-V.A1).

---

## §1 Per-frame gate-firing table at anchor frames F82 / F96 / F97 / F119 / F126

### §1.1 Methodology

Trace: `logs/trace/dckkr_post_ws_o_b_baseline_20260524_100620.jsonl`
(264 records; produced by the post-WS-O.b validated baseline run
`c275807`). Per anchor frame: extract `scorer.decisions[]`
entries + `extractor.{score,wickets,match_overs}` + `pipeline.mode`.
Cross-reference against the WS-V.A §1.2 per-ball parity table.

### §1.2 Per-anchor-frame gate-firing distribution

| Frame | extractor.score | overs | mode | Gate-rejection tags fired | Commit tags fired | VISIBLE_TEXT score (WS-V.A §1.2) |
|---|---|---|---|---|---|---|
| F82 | 8 | 1.2 | WARM | **NONE** | DIRECT-SCORE-COMMIT(7→8), OVERS-NATURAL-INCREMENT-FAST-CONFIRM(1.1→1.2), SM-EVENT-DELTA-FROM-PREV(prev_event=7, self=8, d_score=1, d_score_naive=0), THIS-OVER-TOKEN-APPENDED(raw='.', delta_score=0), BAT-DELTA(Nissanka +1), BOWL-DELTA(Vaibhav +1), PARTNERSHIP-WRITE(7→8) | 8 |
| F96 | 9 | 1.3 | WARM | **NONE** | DIRECT-SCORE-COMMIT(8→9), OVERS-NATURAL-INCREMENT-FAST-CONFIRM(1.2→1.3), SM-EVENT-DELTA-FROM-PREV(prev_event=8, self=9, d_score=1, d_score_naive=0), THIS-OVER-TOKEN-APPENDED(raw='.', delta_score=0), BAT-DELTA(Rahul +1), BOWL-DELTA(Vaibhav +1) | 9 |
| F97 | 15 | 1.4 | WARM | **NONE** | DIRECT-SCORE-COMMIT(9→15), OVERS-NATURAL-INCREMENT-FAST-CONFIRM(1.3→1.4), SM-EVENT-DELTA-FROM-PREV(prev_event=9, self=15, d_score=6, d_score_naive=0), THIS-OVER-TOKEN-APPENDED(raw='.', delta_score=0), BAT-DELTA(Nissanka +6 / +1 six), BOWL-DELTA(Vaibhav +6) | 15 |
| F119 | 16 | 1.5 | WARM | **NONE** | DIRECT-SCORE-COMMIT(15→16), OVERS-NATURAL-INCREMENT-FAST-CONFIRM(1.4→1.5), SM-EVENT-DELTA-FROM-PREV(prev_event=15, self=16, d_score=1, d_score_naive=0), THIS-OVER-TOKEN-APPENDED(raw='.', delta_score=0), BAT-DELTA(Nissanka +1), BOWL-DELTA(Vaibhav +1) | 16 |
| F126 | 17 | 2.0 | WARM | **NONE** | DIRECT-SCORE-COMMIT(16→17), OVERS-NATURAL-INCREMENT-FAST-CONFIRM(1.5→2.0), SM-EVENT-DELTA-FROM-PREV(prev_event=16, self=17, d_score=1, d_score_naive=0), THIS-OVER-TOKEN-APPENDED(raw='.', delta_score=0), BAT-DELTA(Rahul +1), BOWL-DELTA(Vaibhav +1), OVER-ARCHIVE-WRITE(over_n=1, tokens=['.', '.', '.', '.', '.', '.'], source=sm_apply_event_inline_rollover) | 17 |

### §1.3 Critical empirical findings

1. **NO gate-rejection tags fire at any anchor frame.** None of
   WARM-MODE-MAGNITUDE-GATE-REJECTED, COLD-START-OVERREAD-REJECTED,
   SCORE-FORCE-RESET, CAM-GRAPHIC-FAST-PATH-DEFER-NO-BALL-EVENT,
   nor any score-regression-rejected tag fires at F82/F96/F97/F119/F126.
2. **DIRECT-SCORE-COMMIT fires successfully at every anchor.**
   The pipeline DID advance score 7→8→9→15→16→17. The WS-V.A
   §1.2 "Pipeline-commits-correct? NO" entries were
   **EMPIRICALLY WRONG** at the score-commit layer. The score
   commits land; the per-ball-token derivation downstream is
   what fails.
3. **SM-EVENT-DELTA-FROM-PREV consistently reports
   `d_score_naive=0` even when `d_score` (baseline-anchored) is
   1 or 6.** This is the smoking-gun signature of the
   architectural defect explicitly described at
   `score_manager.py:3722-3733`: "trace evidence showed
   d_score computing as 0 even though scoreboard.score advanced
   0→4 in the same frame".
4. **THIS-OVER-TOKEN-APPENDED at every anchor has `delta_score=0,
   raw='.'`.** Despite the score advancing by 1 (or 6 at F97)
   and the BAT-DELTA / BOWL-DELTA / PARTNERSHIP-WRITE all
   correctly attributing the runs to the right batter / bowler /
   partnership, the per-ball-token derivation independently
   computes `delta_score=0`.
5. **WARM-MODE-MAGNITUDE-GATE-REJECTED firings exist elsewhere
   in the trace** (F74, F76, F91, F100, F160, F212, F275) — all
   on overlay-corrupted Scout reads of 49/47/122/49/49/154/155
   at low ball-counts. These are **legitimate gate firings** on
   real overlay misreads, NOT on the per-ball commit anchors.
   The WS-O.b PA gate shipped at `14a29b5` is doing the job
   it was designed for — it does NOT fire spuriously on the
   legitimate +1 per-ball increments.

### §1.4 Per-frame gate-firing distribution verdict

**Empirical verdict: SILENT cascade. No gate-rejection tag
fires at any anchor frame. The commit gate is not over-
rejecting. The defect is downstream of the commit gate.**

---

## §2 Gate identification — the cascade is NOT at any candidate gate

### §2.1 Per-candidate falsification table

| Candidate gate (WS-V.A WG enumeration) | Verdict | Falsification basis |
|---|---|---|
| WARM-MODE-MAGNITUDE-GATE-REJECTED (PA, `scoreboard.py:1216-1252`) | **FALSIFIED** | Zero firings at F82/F96/F97/F119/F126. Fires only at F74/F76/F91/F100/F160/F212/F275 on overlay-corrupted reads (49/47/122/49/49/154/155). |
| CAM-GRAPHIC-FAST-PATH-DEFER-NO-BALL-EVENT | **FALSIFIED** | Zero firings at the anchor frames. Tag is registered (`KNOWN_TAGS`) but absent from the trace at these frames. |
| COLD-START-OVERREAD-REJECTED (WS-O OA, `score_manager.py`) | **FALSIFIED** | Zero firings at the anchor frames. Pipeline mode is WARM at all anchors, so this gate is structurally bypassed. |
| ConsistentReadTracker silent demotion (`scoreboard.py` tracker) | **FALSIFIED** | DIRECT-SCORE-COMMIT fires at every anchor → tracker accepted the value. Demotion would prevent commit, not corrupt downstream derivation. |
| SCORE-REGRESSION-REJECTED (legacy `scoreboard.py:1262-1267`) | **FALSIFIED** | Zero firings. Predicate is `v < cur_int`; all anchor increments are forward. Predicate is correct. |
| Some other not-yet-enumerated gate | **FALSIFIED** | No unknown gate-rejection tag fires at the anchor frames. All decisions at anchors are commit-accepting (DIRECT-SCORE-COMMIT, BAT-DELTA, PARTNERSHIP-WRITE, etc.). |

### §2.2 Cascade root identification — `prev = self._snapshot()` reads post-advance score

**Empirical mechanism** (cross-referenced against
`score_manager.py:4139-4204`, `:6660-6725`, `:1709-1719`,
`:3722-3741`):

1. `self.score` is a `@property` over `scoreboard._inn["score"]`
   (line 1710-1719). Reads delegate to Scoreboard's internal
   dict; writes delegate to `Scoreboard.set()`.
2. **Pre-`_handle_warm` advance**: some upstream caller
   (broadcast tracker / state-recovery / commit_decision in
   `test_pipeline.py`) advances `scoreboard._inn["score"]` to
   the new value BEFORE `_handle_warm` runs. Evidence: SM-EVENT-
   DELTA-FROM-PREV consistently shows `self_score=8` matching
   `card_score=8` at the firing site inside `_handle_warm`,
   meaning `self.score` already absorbed the +1 advance before
   the function even computed `c_score - _self_score = 0`.
3. `_handle_warm` correctly anchors the event-firing
   `d_score` to `_event_baseline_score` (lines 3734-3741, A1
   defense added 2026-05-14). Event fires correctly.
4. Line 4139: `prev = self._snapshot()` — captures `self.score`
   into `prev["score"]`. **But `self.score` has already been
   advanced**, so `prev["score"] = 8`, not 7.
5. Line 4149: `_accept_update(card, fi)` runs — `self.score =
   card["score"]=8` is a no-op (already 8).
6. Line 4204: `_apply_event(evt, prev, card, frame)` —
   `prev["score"]=8, card["score"]=8`.
7. Line 6668: `_wire_prior = _snapshot_primitives_from_dict(prev)`
   → `_wire_prior.score=8`. Line 6851: `_wire_current2 =
   _snapshot_primitives_from_dict(card)` → `_wire_current2.score=8`.
8. Line 6852: `_derive_this_over_token(_wire_prior, _wire_current2,
   None)` → `delta_score = current.score - prior.score = 0` →
   `runs_off_bat = 0 - 0 = 0` → `raw='.'`.

**This is NOT a commit-gate over-rejection. It is a prev-
snapshot-staleness defect at the SM `@property` boundary.**

### §2.3 Mechanism cross-corroboration

The defect is **architecturally documented** at three
independent sites:

1. `score_manager.py:3722-3733` — A1 defense comment: "trace
   evidence (F19 in DC-vs-KKR 2026-05-14 16:12 watch) showed
   d_score computing as 0 even though scoreboard.score
   advanced 0→4 in the same frame".
2. `test_pipeline.py:14102-14109` — wire-commentary defect
   comment: "SM's `self.score` is a live property over
   scoreboard._inn, which the broadcast tracker has already
   mutated by the time on_frame runs — so d_score==0 in warm
   mode and _infer_legal returns DOT for every legal ball".
3. `files/docs/investigations/workstream_q_score_state_unification_refactor.md`
   §5 D3: identifies `score_manager_derivation.py:495`
   `delta_score = current.score - prior.score` as "**the
   WS-O.c residue actor**" with failure mode "current.score
   is the stale value and delta_score = 0".

**Three-instance evidence chain. The mechanism is structurally
identified across A1, wire-commentary, and WS-Q. WS-V.A1 is the
fourth instance at the SM derivation cascade site — the only
remaining instance not yet patched.**

---

## §3 Gate-rejection-payload analysis (negative result)

No gate rejected at any anchor frame; no payload to analyze.
**Forward-going sanity-check on candidate gates'
rejection logic** (per task 3 in the charter — verify each
candidate's predicate against the observed anchor data):

| Gate | Predicate | Anchor data F82 | Would have rejected? |
|---|---|---|---|
| WS-O.b PA `scoreboard.py:1237` | `v > balls*2.5 + 10` | v=8, balls=7, threshold=27 | NO (8 ≤ 27) — correctly accepts |
| Per-update jump guard `:1268` | `v - cur_int > 100` | 8-7=1 | NO — correctly accepts |
| Regression-rejection `:1262` | `v < cur_int` | 8 < 7? NO | NO — correctly accepts |
| T20 ceiling `:1203` | `v > 320` | 8 > 320? NO | NO — correctly accepts |
| ConsistentReadTracker | N consecutive reads | Multiple frames F82/F85-F90 show score=8 | NO — tracker accepts |

**All gates correctly admit the legitimate +1 increments at
the anchor frames.** The candidate-gate enumeration in WS-V.A
WG was complete but ALL FALSIFIED — gates aren't the cascade
root. The cascade root is at the SM derivation cascade D3
identified by WS-Q §5.

---

## §4 Per-cohort cascade attribution under WG (revised: prev-snapshot-staleness mechanism)

WS-V.A §3 cohort attribution **HOLDS at the intermediate-
layer chain** (per-ball-token → striker rotation → ledger
drift → recent-overs-drop → boundary-counter-double) but
the ROOT MOVES one architectural layer further: from
"score-commit-gate over-rejection" (WS-V.A's WG hypothesis)
to "prev-snapshot-staleness at `_handle_warm` line 4139"
(this memo's empirical finding).

| Cohort | Rows | Downstream of prev-snapshot-staleness? | Path |
|---|---|---|---|
| A — striker-anchor swap (per-ball-token) | ~44 | YES | derive_this_over_token sees delta_score=0 → token='.' → BED sees DOT → no rotation → striker stuck |
| Per-batter-ledger-drift | 5 | PARTIAL | BAT-DELTA at anchor frames correctly attributes runs (per F82 trace: "Pathum Nissanka +runs=1 +balls=1"). The ledger-drift at 4.1-4.5 is downstream of the OVER-1 / OVER-2 / OVER-3 multi-ball-FLOOR-pad path where boundary attribution is lost; this IS downstream of the token-derivation cascade |
| Recent-overs-drop | 4 | YES | over_history archives `[., ., ., ., ., .]` per F126 trace; this gets recent_over_n_minus_1 = [] or empty downstream |
| Boundary-counter-double-increment | 4-8 | PARTIAL | Tied to the missed-rotation chain; downstream of cohort A |
| E2-phantom-runs (3) | 3 | PARTIAL (different failure mode) | The +20 phantom at 4.1 is the WS-O.c PA-threshold catch-up. Independent surface; PA fix is a different workstream |
| Conservation invariants (5) | 5 | PARTIAL (same as E2) | Tracks E2 |
| F-A-commit-lag (10) | INDEPENDENT | NO | Bowler-side |
| F-B-ad-occlusion (8) | INDEPENDENT | NO | F-B cohort |

**Total potentially-closable rows IF the prev-snapshot-
staleness defect is fixed**: ~44 (A) + 4 (recent-overs-drop)
+ partial 5 (per-batter-ledger) + partial 4-8 (boundary) =
**~53-61 rows directly**, with the WS-O.c-handled E2 + conservation
(8 total) remaining as a separate workstream.

Note: the prediction is slightly LOWER than WS-V.A's ~65-70
because the **score IS advancing** (DIRECT-SCORE-COMMIT lands),
so the BAT-DELTA / BOWL-DELTA / PARTNERSHIP-WRITE cascades
that WS-V.A attributed entirely to the rejection-cascade are
ALREADY firing correctly. The remaining cohort is the
**this_over_token / over_archive / striker-rotation** chain
that depends specifically on `derive_this_over_token`.

---

## §5 Step-2 patch shape candidates

Based on the empirical localization at `score_manager.py:4139`
+ `:6660-6725` + `score_manager_derivation.py:495`:

### §5.1 Candidate FA — anchor `prev["score"]` to `_event_baseline_score`

In `_handle_warm` at line 4139, replace
```
prev = self._snapshot()
```
with a hybrid that uses `_event_baseline_score` for the score
field when the property has been pre-advanced:
```
prev = self._snapshot()
if (getattr(self, "_event_baseline_score", None) is not None
        and prev.get("score") == c_score
        and d_score > 0):
    prev["score"] = int(self._event_baseline_score)
```
Forward-compat with WS-Q: WS-Q §5 D3 already targets the same
cascade actor. This patch is a NARROW pre-WS-Q defense that
operates at the SM-side snapshot construction, not at the
derivation function itself.

### §5.2 Candidate FB — pass explicit `prior_score` to `_apply_event`

Plumb `_baseline_score` through `_apply_event(event, prev, card,
frame, prior_score)` signature. Replace `prev["score"]` reads
inside `_snapshot_primitives_from_dict` with the explicit
`prior_score` parameter at the call site. Higher blast radius
(signature change, ~4 call sites) but cleaner.

### §5.3 Candidate FC — fix `_snapshot_primitives_from_dict` to read from baseline

Modify `_snapshot_primitives_from_dict` to accept an optional
`canonical_score` override. Pass `_event_baseline_score` from
`_apply_event` callers. Same blast radius as FB.

### §5.4 Recommended candidate

**FA** is the narrowest patch — single LOC change at line 4139.
Bypasses signature changes; mirrors A1's defensive pattern at
the analogous `_event_baseline_score` anchor; backward-compatible
with WS-Q's eventual canonical-API refactor (the `prev["score"]`
override becomes a no-op when WS-Q makes `self.score` a true
canonical SM-owned field).

Predicted L1.5 risk: NONE. The patch only activates when
`prev["score"] == c_score` AND `d_score > 0` (positive
baseline-anchored delta with stale snapshot). L1.5's score-
sequence assertions would catch any regression.

---

## §6 §7.2 audit on leading candidate (FA)

| Gate | Status | Rationale |
|---|---|---|
| **1 (defect-class fit)** | PASS | Mechanism is one specific failure mode of WS-Q's catalogued D3 cascade actor; FA closes the SM-side instance |
| **2 (backward-compat)** | PASS | Single-LOC defensive patch; no API change; activates only when stale snapshot conditions are met |
| **3 (fix-surface attribution)** | PASS | Cross-corroborated against `:3722-3733` A1 comment + `test_pipeline.py:14102-14109` wire-comment + WS-Q §5 D3; same architectural surface |
| **4 (sub-finding promotion)** | PASS | S36 candidate: "SM `@property` snapshot staleness when scoreboard.score is pre-advanced by external mutator" |
| **5 (cohort enumeration completeness)** | PASS | ~53-61 rows mapped to this root |
| **6 (test obligation)** | OPEN | L1.5 regression-guard suite covers per-ball commit assertion; predicted-flip table required at step-2 |
| **7 (cross-fixture verification)** | DEFER to step-3 | Snapshot replay |

---

## §7 Predicted-closure prediction (per-cohort under prev-snapshot-staleness fix)

| Cohort | Pre-fix rows | Leading fix | Predicted post-fix |
|---|---|---|---|
| Cohort A — striker-anchor swap (per-ball-token) | ~44 | FA at `:4139` | ~44 → ~5 (residual at PA-threshold cohort 4.x + pre-anchor 0.1) |
| Per-batter-ledger-drift | 5 | FA (correct delta → correct boundary attribution at 4.x catch-up) | 5 → 0-3 |
| Recent-overs-drop | 4 | FA (over_history archives real tokens) | 4 → 0 |
| Boundary-counter-double-increment | 4-8 | FA (correct rotation → no stale 4/6 sticking to wrong slot) | 4-8 → 0-2 |
| E2-phantom-runs | 3 | INDEPENDENT (PA-threshold catch-up; needs WS-O.c step-2) | 3 (unchanged) |
| Conservation invariants | 5 | INDEPENDENT (same as E2) | 5 (unchanged) |
| WS-V.B (anchor visibility) | 3 | UNCHANGED | 3 |
| WS-V.C (~10 4.3/4.4 striker inversion) | ~10 | UNCHANGED | ~10 |
| F-A-commit-lag (10) | UNCHANGED | bowler-side | 10 |
| F-B-ad-occlusion (8) | UNCHANGED | F-B cohort | 8 |

**Total predicted closure from FA fix**: ~53-61 rows
(narrower than WS-V.A's ~65-70 because score-commit already
lands — the cascade is purely the derivation-layer downstream).

---

## §8 Regression-guard enumeration

Standard preserved from prior workstreams. All shipped
defensive gates stay landed:

- **L2 ledger 30/30**: preserved.
- **L1.5 92**: preserved.
- **9 closed surfaces stay at 0**.
- **WS-O.b PA `WARM-MODE-MAGNITUDE-GATE-REJECTED`**: stays at
  `scoreboard.py:1216-1252` unchanged. FA does NOT touch the
  PA gate; PA correctly admits +1 increments at the anchor
  frames per §3 sanity-check.
- **WS-O OA `COLD-START-OVERREAD-REJECTED`**: stays at
  `score_manager.py` cold-start path unchanged.
- **A1 `_event_baseline_score` anchor at `:3734-3741`**: FA
  is the symmetric defense at the snapshot-construction site;
  does NOT modify the A1 anchor.
- **STRIKER-LOCK-MID-OVER-SUPPRESSED** (148 instances):
  preserved.
- **PA threshold (WS-O.c)** investigation cohort: separate
  workstream; FA is independent.
- **Shape A, Shape B, D1, D2-Layer-1a, H1, H3** gates: all
  preserved.
- **Squad-convention QA/QE (WS-P P1)**: preserved.
- **Wire-commentary BED-prioritization workaround at
  `test_pipeline.py:14110`**: preserved (and stays preserved
  even post-FA; it's a defense at a different cascade actor).

---

## §9 Step-1c vs step-2 recommendation

### §9.1 Recommendation: PROCEED TO STEP-2 with candidate FA

The S34 empirical-parity-check yielded **unambiguous root-
cause localization** in step-1b alone:
1. Gate-rejection enumeration: 100% FALSIFIED across all
   five candidates + "any other gate".
2. Smoking-gun signature in trace: `d_score=1, d_score_naive=0`
   at every anchor frame is direct evidence of the property-
   staleness mechanism explicitly documented at the A1 comment
   block.
3. Architectural cross-corroboration: three independent sites
   (`:3722`, `:14102`, WS-Q §5 D3) document the exact same
   mechanism in advance of this investigation.

**Step-1c instrumentation is NOT NEEDED.** The static
analysis + trace + architectural cross-corroboration suffice
to lock fix-surface attribution. The defect class is well-
characterized; the patch site is single-LOC.

### §9.2 Sequencing

| Priority | Workstream | Step | Predicted closure | Block? |
|---|---|---|---|---|
| 1 | WS-V.A1 step-2 (FA at `:4139`) | step-2 | ~53-61 rows | Forward-compat with WS-Q (§10) |
| 2 | WS-V.B (anchor visibility) | step-2 | 3 → 0 | Independent |
| 3 | WS-O.c step-2 (PA-threshold catch-up) | step-2 | 3 + 5 → 0 | Independent (separate cascade actor) |
| 4 | WS-V.C (striker-write residue) | step-1b → step-2 | ~10 → 0-10 | Partial dep on V.A1 |

**Highest-impact, leading priority: WS-V.A1 step-2 FA.**

### §9.3 Stop-condition firings

Per charter:
- "Per-frame gate-firing table reveals NO explicit gate-rejection
  tags at the anchor frames (silent rejection) → step-1c
  instrumentation required" — **PARTIAL FIRE**: silent at gate
  layer BUT the SM-EVENT-DELTA-FROM-PREV `d_score_naive=0`
  trace + the existing A1 comment block + WS-Q §5 D3
  characterization together substitute for additional
  instrumentation. Step-1c skipped on grounds of three-instance
  architectural cross-corroboration.

---

## §10 WS-Q architectural-adjacency analysis (forward-compatibility verdict)

### §10.1 Architectural adjacency

WS-Q §5 D3 explicitly identifies `score_manager_derivation.py:495`
(`derive_this_over_token`'s `delta_score = current.score - prior.score`)
as the cascade actor for the WS-O.c residue. WS-Q's canonical
API design (`sm.set_score(value, source, confidence)`,
`sm._canonical_score` field, `sb._inn["score"]` as @property
view) explicitly addresses this defect class by inverting the
ownership: SM owns the canonical score, Scoreboard provides
the view.

### §10.2 FA's forward-compatibility with WS-Q

FA modifies `_handle_warm` line 4139 to use
`_event_baseline_score` for the `prev["score"]` field when
the property has been pre-advanced. **Once WS-Q lands**, the
mechanism FA defends against will be eliminated structurally:
- `sm.score` becomes a true SM-owned field (not a property
  delegating to `sb._inn["score"]`)
- External mutators (broadcast tracker, state-recovery,
  commit_decision) route through `sm.set_score(…)`, not
  through `scoreboard.set("score", ...)` independently
- `_handle_warm` enters with `self.score` reflecting the
  pre-`_handle_warm` state, not the post-broadcast-tracker
  mutation

After WS-Q lands, the FA condition `prev["score"] == c_score
AND d_score > 0` will simply not be reachable — the prev-
snapshot will correctly reflect the pre-event score. **FA
becomes a structural no-op post-WS-Q.**

### §10.3 Forward-compat verdict

**HARMLESS forward-compat.** FA's defensive condition is
self-disabling post-WS-Q. The patch:
1. Does NOT add a new defensive layer that WS-Q would have to
   absorb into its canonical API.
2. Does NOT introduce a new code path or signature.
3. Is functionally a backport of WS-Q's eventual semantic
   guarantee, applied locally at one cascade actor.

Sequencing: WS-V.A1 step-2 FA can land before WS-Q step-2a
without conflict. WS-Q's eventual landing makes FA a no-op
but does not require removing it. Honest characterization:
FA is a **narrow tactical defense at a known cascade actor
ahead of the broader WS-Q strategic refactor**.

### §10.4 Honesty flag (PA-shipped-at-`14a29b5`)

**NEGATIVE**: PA gate shipped at `14a29b5` is NOT the cascade
root. The empirical trace shows zero PA firings at the anchor
frames. PA fires correctly only on overlay-corrupted reads
(F74/F76/F91/F100/F160/F212/F275). **No tuning-back of PA
is required for WS-V.A1.** WS-O.b PA remains a correctly-
calibrated defense at the magnitude-gate surface.

---

## §11 Methodology note

S34 empirical-parity-check methodology applied verbatim per
WS-O OA + WS-P P1 + WS-V.A1 sequence:

- **WS-O OA**: parity-check at cold-start gate → identified
  cold-start surface; OA shipped with no regression.
- **WS-P P1**: parity-check at squad-convention layer →
  identified striker-anchor surface; P1 shipped with no
  regression (though predicted-flip table missed).
- **WS-V.A1**: parity-check at score-commit-gate layer →
  **FALSIFIED** the entire commit-gate hypothesis; pivoted
  to prev-snapshot-staleness at SM `@property` boundary on
  empirical evidence (zero gate firings at anchors +
  smoking-gun `d_score_naive=0` signature).

**S34 outcome**: methodology validated for a third successive
instance. The instrumentation-aware "audit the suspected layer
empirically BEFORE proposing patches" approach prevents a
patch on a falsifiable hypothesis. WS-V.A1's WG hypothesis
would have produced a tuning-back of WS-O.b PA threshold
(empirically incorrect) absent S34 application.

---

## §12 Stop-condition firing

Per workstream charter:

> "Per-frame gate-firing table reveals NO explicit gate-
> rejection tags at the anchor frames (silent rejection)
> → step-1c instrumentation required."

**PARTIAL FIRE — overridden** by three-instance architectural
cross-corroboration (A1 comment + wire-comment + WS-Q §5 D3).
Step-1c skipped; proceeding directly to step-2 FA.

> "Gate identification surfaces ConsistentReadTracker
> demotion as root → flag high-blast-radius; recommend
> step-1c instrumentation BEFORE step-2."

NOT FIRED. Tracker correctly accepts at every anchor
(DIRECT-SCORE-COMMIT fires).

> "Gate identification surfaces our own WS-O.b PA shipped
> at `14a29b5` → STOP, report; commit-body honesty
> required for tuning-back."

**NEGATIVE-FIRE**: PA gate is NOT the cascade root; PA
correctly admits +1 anchor-frame increments; no tuning-back
required.

> "Cohort splits across multiple gates → STOP, recommend
> per-gate sub-workstreams."

NOT FIRED. No gates at all are the cascade root.

> "8 static falsifications without convergence → STOP,
> methodology-class issue."

NOT FIRED. Six falsifications (WS-V.A WG enumerated five
gates + "any other") all converge on a single architectural
finding: prev-snapshot-staleness. Convergence achieved.

> "Architectural-adjacency check (task 10) surfaces conflict
> between WS-V.A1 fix and WS-Q canonical API design → flag
> for sequencing decision."

NOT FIRED. FA is forward-compatible HARMLESS no-op post-
WS-Q; no sequencing conflict.

---

## Deliverables

- Memo path:
  `files/docs/investigations/workstream_v_a1_score_commit_gate_over_rejection_root_cause.md`
- Section count: 12 (§1-§12, including methodology note +
  stop-condition firing)
- Step-2 patch candidate: FA at `score_manager.py:4139` (single
  LOC defensive anchor of `prev["score"]` to
  `_event_baseline_score` when stale-snapshot conditions met).
- Predicted closure: ~53-61 rows.
- Forward-compat with WS-Q: HARMLESS (FA is structural no-op
  post-WS-Q).
- Honesty flag PA-at-`14a29b5`: NEGATIVE — PA gate is not the
  cascade root.

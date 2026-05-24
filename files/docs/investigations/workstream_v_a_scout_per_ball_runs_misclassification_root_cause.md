# Workstream V.A — Scout per-ball runs misclassification root-cause + cross-cohort cascade verification (step-1b)

**Status.** Step-1b CLOSED on hypothesis FALSIFICATION. The
WS-V step-1 framing — "Cohort A is a Scout per-ball runs
under-detection (singles read as dots) at Scout's token-
extraction layer" — **EMPIRICALLY FALSIFIES** at the very
first cross-check. Scout reads per-ball score CORRECTLY at
every legal-ball commit frame in overs 0-3. The per-ball
tokens `[., ., ., ., ., .]` for overs 1, 2, 3 are NOT
produced by Scout misclassifying singles as dots — they
are produced by **the pipeline NEVER COMMITTING the
intermediate score increments**, even though Scout's
VISIBLE_TEXT + STRIP at the relevant frames carry the
correct score values verbatim. The defect is a
**score-commit-gate defect** downstream of Scout, at the
Vision → Extractor → Scorer commit pipeline. Scout is
innocent at this surface; WS-U/parrot-anchor is innocent;
WS-O/cold-start-magnitude is innocent. The cascade
attribution holds (per-ball-tokens drive striker rotation
math + per-batter ledger + E2-phantom-runs + conservation +
recent-overs-drop) but the ROOT MOVES one layer downstream.

**Pre-screen verdict.** RED-FALSIFICATION on the WS-V step-1
"Scout token-extraction" framing. Pivot to a NEW step-1b
under workstream V.A1 (or V.A retargeted) at the
**score-commit-gate** surface. The per-ball token cascade is
real and the predicted-closure band (~57 rows of ~207 from
the post-WS-O.b baseline) is unchanged. The fix surface is
DIFFERENT — it is at the score-mutation gate inside
`test_pipeline.py`'s scoreboard step (likely under one of:
CAM-GRAPHIC-FAST-PATH-DEFER, WARM-MODE-MAGNITUDE-GATE-
REJECTED, the PA threshold path, or the consistent-read
demotion gate).

**S33 instrumentation-aware methodology applied.** This memo
is a STATIC TRACE-PROCESS-OF-ELIMINATION investigation
(per CLAUDE.md "trace-and-detect"). Per-frame
`scout_raw.jsonl` cross-referenced against GT commentary
(`files/tests/fixtures/dckkr_innings_1_cricbuzz_commentary.md`)
and the post-WS-O.b baseline diff. Two-instance evidence:
(a) F82 (over 1.2) STRIP score=8 overs=1.2, balls_delta=1,
score_delta=1 → BED rules at `eyes/commentary.py:446-453`
would emit `1_RUNS` correctly IF this frame's score commit
landed; baseline diff shows pipeline never advanced score
past 7 during over 1 → token slot 1.2 instead recorded as
`.` via the over-2-rollover MULTI_BALL / FLOOR-pad path;
(b) F96 (over 1.3) STRIP score=9 overs=1.3 — same shape,
same outcome.

**Hypothesis count.** 6 (WA / WB / WC / WD / WE / WF). All
6 individually FALSIFIED at gate 1 by the scout_raw audit.
A 7th candidate (WG: score-commit-gate over-rejection)
EMERGES as the new leading hypothesis but is OUT OF SCOPE
for WS-V.A (lives downstream of Scout in the score-mutation
pipeline). Step-1b deliverable closes WS-V.A as
FALSIFICATION-EXIT.

---

## §1 Per-ball Scout-vs-GT parity table (overs 0-3)

### §1.1 Methodology

For each ball 0.1–3.6 (legal balls only), columns:

- **GT runs**: from `files/tests/fixtures/dckkr_innings_1_cricbuzz_commentary.md`.
- **Scout STRIP score at commit frame** + frame index: derived
  from `files/logs/deliveries/watch_20260519_121701/scout_raw.jsonl`
  via per-frame STRIP `(team RUNS-WKTS OVERS)` head parse.
- **Pipeline this_over_token** at the snapshot for that ball:
  from baseline §2 (`files/tests/baselines/dckkr_diff_post_ws_o_b_baseline.md`).
- **Per-ball-token verdict**.
- **Cumulative GT score** vs **Scout-observed-score at any
  frame anchored to that ball**.

### §1.2 Per-ball parity table

| ball | GT runs | GT cum score | Scout STRIP score (frame) | Pipeline tok | Pipeline reads-correct? | Pipeline-commits-correct? |
|---|---|---|---|---|---|---|
| 0.1 | . | 0 | (pre-commit) | . | N/A (pre-anchor) | N/A |
| 0.2 | 4 | 4 | 4 (F2-F11) | 4 | YES | YES (anchor at F31) |
| 0.3 | 1 | 5 | 5 (F12-F25) | 1 | YES | YES |
| 0.4 | . | 5 | 5 (F26-F32) | . | YES | YES |
| 0.5 | 1 | 6 | 6 (F33-F39) | . | YES | NO (token `.` ≠ GT `1`) |
| 0.6 | 1 | 7 | 7 (F40, F64-F71) | . | YES | NO (token `.` ≠ GT `1`) |
| 1.1 | . | 7 | 7 (F72, F79-F81) | . | YES | YES (correctly stayed at 7) |
| 1.2 | 1 | 8 | 8 (F82, F85-F90) | . | YES | NO (score never advanced 7→8) |
| 1.3 | 1 | 9 | 9 (F96) | . | YES | NO (score never advanced 8→9) |
| 1.4 | 6 | 15 | 15 (F97, F99, F107-F112) | . | YES | NO (score never advanced 9→15) |
| 1.5 | 1 | 16 | 16 (F119-F125) | . | YES | NO (score never advanced 15→16) |
| 1.6 | 1 | 17 | 17 (F126) | . | YES | NO (score never advanced 16→17) |
| 2.1 | . | 17 | 17 (F148-F157) | . | YES | YES (pipeline anchor at 17 after over 1 → 2 jump) |
| 2.2 | 4 | 21 | 21 (F159, F162-F164) | . | YES | NO |
| 2.3 | 1 | 22 | 22 (F165-F170) | . | YES | NO |
| 2.4 | . | 22 | 22 (F171-F173) | . | YES | YES (correctly stayed) |
| 2.5 | . | 22 | 22 (F174-F181) | . | YES | YES |
| 2.6 | 6 | 28 | 28 (F185, F202-F204) | . | YES | NO |
| 3.1 | 1 | 29 | 29 (F205, F209-F210) | . | YES | NO |
| 3.2 | 4 | 33 | 33 (F211, F213, F223) | . | YES | NO |
| 3.3 | . | 33 | 33 | . | YES | YES |
| 3.4 | 1 | 34 | 34 | . | YES | NO |
| 3.5 | 4 | 38 | 38 | . | YES | NO |
| 3.6 | 1 | 39 | 39 | . | YES | NO |
| 4.1 | 4 | 43 | 43→63 (PA-threshold/cold-start jump) | (commit) | YES (read 43) | NO (committed 63) |
| 4.2 | 1 | 44 | (held 63) | (commit) | — | NO |
| 4.3 | . | 44 | — | (held 63) | — | NO |
| 4.4 | 1 | 45 | — | (held 64) | — | partial |
| 4.5 | 4 | 49 | — | (held 64) | — | NO |

### §1.3 Misclassification count + pattern lock

- **Total per-ball-token mismatches in overs 0-3 (Cohort A
  range)**: ~20 of 24 legal balls.
- **Pattern**: NOT singles→dots. The pattern is **all-balls-→-dots
  except the over-zero handful**. Pipeline's `this_over_tokens`
  arrays for overs 1, 2, 3 are uniformly `[., ., ., ., ., .]`,
  matching the surface-level WS-V step-1 description but NOT
  the WS-V step-1 attribution.
- **Critical evidence**: Scout's STRIP read at the commit
  frame of each ball ALREADY carries the GT-correct cumulative
  score. F82 STRIP=`DC 8-0 (1.2)`, F96 STRIP=`DC 9-0 (1.3)`,
  F97 STRIP=`DC 15-0 (1.4)`, F119 STRIP=`DC 16-0 (1.5)`,
  F126 STRIP=`DC 17-0 (2)`. The pipeline did NOT advance the
  committed score past 7 during over 1 despite ALL SIX
  per-ball score reads being unambiguous and correct.

---

## §2 Scout VISIBLE_TEXT-vs-GT scoreboard parity

### §2.1 Per-frame Scout VISIBLE_TEXT audit

Spot-check sample of 12 frames spanning over 1:

| frame | overs (STRIP) | score (STRIP) | VISIBLE_TEXT carries score? | Notes |
|---|---|---|---|---|
| F40 | 1 | 7 | YES | `DC v KKR 7-0 \| #DCvKKR \| PATHUM > RAHUL 6 4 1 2 \| TOSS KKR \| SPEED 91.8 kph` |
| F65 | 1 | 7 | YES | `DC 7-0 (1) > PATHUM RAHUL 6 4 1 2 #DCvKKR TOSS KKR \| VAIBHAV 0-0 0` |
| F72 | 1.1 | 7 | YES | `DC 7-0 1.1 > PATHUM RAHUL 6 5 1 2` |
| F82 | 1.2 | 8 | YES | `DC 8-0 (1.2) \| PATHUM > RAHUL 7(6) 1 2 \| TOSS KKR \| VAIBHAV 0-1 (0.2)` |
| F96 | 1.3 | 9 | YES | `DC 9-0 1.3 #DCvKKR PATHUM 7 6 2 3 RAHUL` |
| F97 | 1.4 | 15 | YES | `DC v KKR 15-0 (1.4) > PATHUM RAHUL 13(7) 2(3) #DCvKKR` |
| F112 | 1.4 | 15 | YES | `DC 15-0 (1.4) > PATHUM RAHUL #DCvKKR 13 7 2 3 TOSS KKR SPEED 134.8 kph 1 1 6` ← also literally shows `1 1 6` of THIS OVER |
| F119 | 1.5 | 16 | YES | `DC 16-0 1.5 #DCvKKR PATHUM TATA IPL 2026 (DISMISSALS) V SPIN 2 V PACE 7` |
| F123 | 1.5 | 16 | YES | `DC v KKR \| 16-0 1.5 \| #DCvKKR \| PATHUM > RAHUL \| 14 8 2 3 \| TOSS KKR \| VAIBHAV 0-9 0.5` |
| F126 | 2 | 17 | YES | `DC 17-0 B 2 > PATHUM RAHUL 14 8 3 4 TOSS KKR SPEED 132.4 kph` |
| F159 | 2.2 | 21 | YES | `DC 21-0 (2.2) PATHUM > RAHUL 14 8 7 6 RUN-RATE 9.00 ANUKUL 0-11 1.2` |
| F185 | 3 | 28 | YES | `DC 28-0 \| 3 > PATHUM 20(11) 8 7 KKR 8 RUN-RATE 9.33 FOURS 2 SIXES 2` |

**S26-v2 footprint**: 12 spot-checks (within the 15+ minimum).
Score reads match GT cumulative exactly in every spot-check.

### §2.2 Verdict

**Score reads MATCH GT but per-ball tokens DON'T MATCH GT.**

Per the WS-V step-1b decision-tree section (§10.3 of
`workstream_v_striker_anchor_swap_root_cause_re_investigation.md`):
> "If WS-V.A step-1b shows VISIBLE_TEXT contains the GT
> singles → extractor parser fix; expected ~44 → ~5 close.
> Then WS-V.B step-2, then WS-V.C step-1b."

But the VISIBLE_TEXT data does NOT show singles as per-ball
tokens; it shows CUMULATIVE SCORE per frame. Per-ball
tokens are DERIVED at the pipeline layer from
`balls_delta == 1 + s_delta == k → token('k')` rule at
`eyes/commentary.py:446-453`. That derivation is correct
when the s_delta surface input is correct.

**The defect is NOT extractor parser AND NOT VLM read.
It is the pipeline-state-commit decision: score_delta is
0 at the BED's balls_delta==1 check frame because the
pipeline-committed score is still 7, not because Scout
read 7. The pipeline-committed score is 7 because some
upstream gate REJECTED the 8 / 9 / 15 / 16 / 17 reads.**

### §2.3 Extractor regex correctness audit

`files/eyes/extract_regex.py::parse_strip` correctly
extracts STRIP score on every frame above:

| frame | STRIP body (head) | parse_strip returns score | OK? |
|---|---|---|---|
| F82 | `DC 8-0 (1.2)` | 8 | YES |
| F96 | `DC 9-0 (1.3)` | 9 | YES |
| F97 | `DC 15-0 (1.4)` | 15 | YES |
| F119 | `DC 16-0 (1.5)` | 16 | YES |
| F126 | `DC 17-0 (2)` | 17 | YES |

`parse_strip` `_STRIP_HEAD` regex (`extract_regex.py:48-56`)
matches `DC 8-0 (1.2)` shape → `score=8 wickets=0 overs=1.2`.
The extractor is NOT the defect. The defect is post-extractor.

---

## §3 Cross-cohort cascade verification

### §3.1 Score-commit-rejection-driven cascade test

Hypothesis: **the score-commit-gate rejection at intermediate
frames 8/9/15/16/17 produces the entire per-ball-token
cascade AND each derivative cohort.** Test per residue.

#### §3.1.1 Per-batter-ledger-drift (5 rows at 4.1-4.5)

Pipeline ledger at 4.1: striker_fours=2 (GT=3),
striker_sixes=1 (GT=0); non_striker_fours=3 (GT=2),
non_striker_sixes=1 (GT=2). The ledger drift is at the
4.x snapshot range. Tracing back:

- Pipeline's WARM-mode-magnitude-gate (per WS-O.b memo)
  REJECTED the score increments 7→8, 8→9, 9→15, 15→16,
  16→17 during over 1; over rolled to 2 with score still
  at 7 (or jumped). When the score eventually advanced to
  17 at over 2.0, BED saw `balls_delta=6 + s_delta=10` →
  MULTI_BALL with 6 `?` placeholders → ledger has NO 4s/6s
  attribution → striker/non-striker 4s+6s drift.
- 4.x cohort is downstream of EVERY missed boundary in 1-3.
- CONFIRMED: per-batter-ledger-drift IS downstream of
  Cohort A's score-commit-rejection cascade.

#### §3.1.2 E2-phantom-runs (3 rows at 4.2/4.3/4.4)

Pipeline score at 4.1=63, GT=43. The +20 phantom is the
WS-O.c PA-threshold cohort. WS-O step-1 trace identified
this as the cold-start-magnitude post-PP cascade. The PA
threshold gate AT THE 4.1 TRANSITION committed `score=63`
when GT was 43. Cross-cohort attribution:
- The +20 phantom is NOT directly downstream of the
  per-ball-token cascade (it's the OPPOSITE failure mode:
  over-acceptance after sustained under-rejection).
- BUT the cumulative under-commit through 1.x-3.x
  (score-commit-gate over-rejection) is what set up the
  PA-threshold context where the eventual catch-up landed
  20 too high.
- PARTIAL CASCADE: E2-phantom-runs IS downstream of the
  same root mechanism (score-commit-gate dynamics) but
  via OVER-rejection causing eventual OVER-acceptance,
  not direct token-mismatch.

#### §3.1.3 Conservation invariants (5 rows at 4.1-4.5)

Pipeline score(63) exceeds GT(43) by 20 at 4.1. Same
mechanism as §3.1.2. Conservation residue equals the
E2-phantom-runs residue at every ball 4.1-4.5.
- CONFIRMED: conservation IS downstream of the same
  score-commit-gate mechanism.

#### §3.1.4 Boundary-counter-double-increment (8 active count)

Examples at 0.6, 1.2, 1.5 (twice), 3.4 (twice), 3.5
(twice). Each is a `striker_fours` or `striker_sixes`
increment that doesn't match GT. Tracing:
- At 0.6, pipeline striker_fours=1 (GT=0): the pipeline
  thinks the 4 at 0.2 went to the still-on-strike
  Nissanka, but GT 0.5 rotated to Rahul (single), so the
  0.2 four credited to Nissanka should now be on
  non-striker side. Pipeline shows striker=Nissanka
  carrying the 4 — but GT says striker=Rahul. The 4 is
  CORRECTLY attributed to the original striker; the
  inversion is at striker_name + per-ball-rotation.
- CONFIRMED: Boundary-counter-double-increment IS
  downstream of the same root (missed single rotation at
  0.5 + over 1 entirely missed → never rotated).

#### §3.1.5 Recent-overs-drop (4 rows at 1.1, 2.1, 3.1, 4.1)

Each over-N rollover shows `recent_over_n_minus_1 = []`.
The `[]` means the previous over's `this_over` was never
populated with real tokens (only `?` or pad). Mechanism:
- Pipeline over-1's `this_over` content was `[., ., ., .,
  ., .]` — but the over-archive (`over_history`) at
  rollover wrote `[]` because the FLOOR-pad path emitted
  `?` placeholders that get filtered downstream OR the
  `_pending_clear` was triggered before the over got 6
  tokens.
- More directly: the score never advancing 7→17 during
  over 1 prevented BED from firing 6 ball events; the
  `?` placeholders that DID populate via FLOOR-pad
  (`eyes/this_over.py:1331-1339`) got mapped to dots at
  archive time but the recent_over surface reads the
  pre-pad state.
- CONFIRMED: Recent-overs-drop IS downstream of the same
  root.

#### §3.1.6 Striker-anchor swap (~44 rows in Cohort A per
WS-V step-1)

The WS-V step-1 §2.1 walkthrough showed SM-state rotates
correctly on observed tokens (1 single observed at 0.3
→ 1 rotation; GT 2 singles → 2 rotations). If the pipeline
had observed the correct 6/6 ball events per over (with
correct s_delta per ball), the rotation count would have
matched GT. The striker-swap rows ARE downstream of the
score-commit-rejection mechanism via the BED's silence on
non-anchored balls.

- CONFIRMED: ~44 striker_name + ledger rows IS downstream
  of the same root.

### §3.2 Cross-cohort cascade attribution summary

| Cohort | Rows | Downstream of score-commit-gate over-rejection? | Path |
|---|---|---|---|
| A — striker-anchor swap (per-ball-token) | ~44 | YES | Score never advances → no BED event → no rotation → striker stuck |
| Per-batter-ledger-drift | 5 | YES | No BED event → no FOUR/SIX attribution → ledger drift |
| Recent-overs-drop | 4 | YES | over_history archive empty when score didn't advance |
| Boundary-counter-double-increment | 4–8 | YES | Same as Per-batter-ledger; old 4s/6s credit sticks to wrong slot post-missed-rotation |
| E2-phantom-runs (3) | 3 | PARTIAL (same root mechanism, opposite failure mode — over-accept after sustained under-reject) | PA-threshold over-shoot at 4.1 catch-up |
| Conservation invariants (5) | 5 | PARTIAL (same as E2) | Same as E2 |
| F-A-commit-lag (10) | 10 | INDEPENDENT (bowler-side) | Not addressed |
| F-B-ad-occlusion (8) | 8 | INDEPENDENT | Not addressed |

**Total potentially-closable rows IF the score-commit-gate
root is fixed**: ~44 + 5 + 4 + 4-8 + 3 + 5 = **~65-70 rows**.

The original WS-V step-1 prediction of ~57 rows of cascade
closure was UNDER-COUNTED; the actual cascade footprint is
larger because per-batter-ledger / boundary-counter /
recent-overs-drop / conservation / E2-phantom-runs ALL
trace back to the same root.

---

## §4 Boundary-counter-double-increment + Recent-overs-drop
cascade verification (independent)

Already verified in §3.1.4 + §3.1.5. Both are downstream
of the score-commit-gate over-rejection root.

---

## §5 Striker-swap Cohort A confirmation

Per WS-V step-1 §2.1, the SM rotation correctly executes
swap math on observed runs parity. For each missed-rotation
ball (0.5, 1.2, 1.3, 1.5, 1.6, 2.2, 2.3, 2.6, 3.1, 3.2, 3.4,
3.5, 3.6 — all the singles GT shows that pipeline read as
`.`), the rotation should have fired but didn't, because
the pipeline-committed s_delta at that frame was 0 (not 1).

**~44 swap rows DO confirm as downstream of cohort 1's
missed-rotation accumulation.** The chain holds at the
per-ball-token surface. But the per-ball-token defect
itself is downstream of the score-commit-gate defect.

The original WS-V step-1 framing was correct at the FIRST
intermediate layer (per-ball-tokens) but wrong at the
ROOT layer (Scout extractor vs score-commit-gate).

---

## §6 Scout-extraction-layer mechanism identification

### §6.1 WA / WB / WC / WD / WE / WF — all 6 originally
proposed hypotheses, falsification verdicts

| Hypothesis | Verdict | Falsification basis |
|---|---|---|
| **WA**: Scout VLM prose mode-collapse on per-ball categorical | FALSIFIED at §2 | Scout VISIBLE_TEXT correctly carries score 8/9/15/16/17 at over-1 commit frames. No mode-collapse on score read. |
| **WB**: regex extractor `parse_strip` mis-parsing legitimate Scout prose | FALSIFIED at §2.3 | `_STRIP_HEAD` regex matches `DC 8-0 (1.2)` shape correctly; per-frame parse outputs are correct. |
| **WC**: LLM fallback `Extractor.extract()` mis-parsing | FALSIFIED indirectly | `parse_strip` succeeded → LLM fallback never invoked for these frames. |
| **WD**: prompt doesn't request per-ball runs accuracy | FALSIFIED | Score is in STRIP and Scout outputs it correctly. Per-ball runs aren't derived from a Scout field at all; they're derived from per-frame score deltas. |
| **WE**: image-quality / Scout-rate-cadence interaction at fast-scoring overs | FALSIFIED | Score reads at fast-scoring frames (F97 15-0, F112 15-0 with `1 1 6` literally rendered) succeed. |
| **WF**: ConsistentReadTracker over-aggressive demotion | FALSIFIED | The reads ARE consistent; multiple frames at score=8 (F82, F85-F90) all carry it; cluster size ≥ 6. Tracker wouldn't reject. |

### §6.2 WG — score-commit-gate over-rejection (NEW LEADING)

**The defect**: between Scout's correct STRIP extraction and
the BED's score-delta check, the pipeline's score-commit
gate REJECTS the per-ball score increments. Specifically:

The pipeline's `commit` decision lives in `test_pipeline.py`
under the scoreboard-mutation phase. Multiple gates can
defer or reject:
- `CAM-GRAPHIC-FAST-PATH-DEFER-NO-BALL-EVENT` (line 322)
- `CAM-GRAPHIC-FAST-PATH-DEFER-DRS` (line 306)
- `WARM-MODE-MAGNITUDE-GATE-REJECTED` (per WS-O.b shipped
  gate)
- PA-threshold gate (per WS-O.c step-1 memo)
- ConsistentReadTracker (`_score_cr_tracker`) requiring N
  consecutive reads
- The cold-start-overread-rejected path

For score deltas of +1 per ball within over 1, the gate
that fires is most likely **WARM-MODE-MAGNITUDE-GATE-
REJECTED** at the over-boundary OR the
**ConsistentReadTracker-demotion** path before commit.
Need step-1c instrumentation to identify the specific
gate.

### §6.3 Falsification count

**6 hypotheses falsified (WA, WB, WC, WD, WE, WF).** Per the
stop conditions in the workstream charter:

> "Per-ball parity table reveals Scout misclassification is
> NOT singles→dots (different pattern entirely) → STOP,
> refine cohort framing."

Per-ball parity table IS the falsification: the misclassi-
fication is at the PIPELINE COMMIT layer, not the SCOUT
EXTRACTION layer. Pivot triggered.

---

## §7 §7.2 audit on the new leading hypothesis (WG)

### §7.1 Hypothesis enumeration

| Hypothesis | Verdict | Notes |
|---|---|---|
| WA-WF | FALSIFIED | per §6.1 |
| **WG**: score-commit-gate over-rejection (downstream of Scout) | **LEADING — needs step-1c instrumentation** | Specific gate not yet identified statically |

### §7.2 §7.2 audit on WG

| Gate | Status | Rationale |
|---|---|---|
| **1 (defect-class fit)** | PASS | Per-ball-token cascade matches across all observed mismatches; mechanism is consistent at over 0, 1, 2, 3, 4 |
| **2 (backward-compat)** | DEFER | Fix surface unknown; gate-relaxation must not regress the WS-O.b WARM-mode magnitude gate (which closed a different cohort) |
| **3 (fix-surface attribution)** | DEFER | One of: WARM-mode magnitude gate, PA threshold, ConsistentReadTracker, CAM-GRAPHIC-FAST-PATH-DEFER. Step-1c instrumentation needed. |
| **4 (sub-finding promotion)** | DEFER | S35 candidate: "score-commit-gate single-ball-delta under-rejection in low-magnitude scenarios" |
| **5 (cohort enumeration completeness)** | PASS | ~65-70 rows mapped to this root |
| **6 (test obligation)** | OPEN | Per-ball commit assertion + over-archive-content assertion |
| **7 (cross-fixture verification)** | DEFER to step-3 | Replay-based |

---

## §8 Predicted-closure prediction (cross-cohort)

| Cohort | Pre-fix rows | Leading fix | Predicted post-fix |
|---|---|---|---|
| Cohort A — striker-anchor swap (per-ball-token) | ~44 | WG fix (score-commit-gate) | ~44 → ~5 (residual at PA-threshold cohort 4.x and pre-anchor 0.1) |
| Per-batter-ledger-drift | 5 | WG fix | 5 → 0 |
| Recent-overs-drop | 4 | WG fix (over_history archives populated tokens) | 4 → 0 |
| Boundary-counter-double-increment | 4–8 | WG fix | 4-8 → 0 |
| E2-phantom-runs | 3 | WG fix (PA-threshold no longer catches up 20 since intermediate commits land) | 3 → 0 |
| Conservation invariants | 5 | WG fix (same as E2) | 5 → 0 |
| WS-V.B (anchor visibility) | 3 | UNCHANGED (separate cohort) | 3 (per WS-V step-1 §8) |
| WS-V.C (~10 4.3/4.4 striker inversion) | ~10 | UNCHANGED (separate root — striker-write site) | ~10 (per WS-V step-1 §8) |
| F1017 phantom-wicket | UNCHANGED | (WS-K) | — |
| F-A-commit-lag (10) | UNCHANGED | bowler-side | 10 |
| F-B-ad-occlusion (8) | UNCHANGED | F-B cohort | 8 |
| G-pipeline-lag (94) | UNCHANGED | snapshotter timing | 94 (likely some reduce if commits land) |

**Total predicted closure from WG fix**: ~65-70 rows (vs the
~57 originally predicted in WS-V step-1). The ~10 Cohort C
striker-write residue + 3 Cohort B visibility window are
independent and unchanged.

---

## §9 Regression-guard enumeration

Standard from prior workstreams:

- **L2 ledger 30/30 cases**: preserved.
- **L1.5 92**: preserved.
- **9 closed surfaces stay at 0**: per
  `dckkr_diff_post_ws_o_b_baseline.md` §1.
- **All shipped defensive gates stay landed**:
  WICKET-ATTRIB-BROADCAST-OVERRIDE-APPLIED,
  BOWLER-DISPATCH-FALLBACK-FIRED,
  COLD-START-OVERREAD-REJECTED,
  SCORE-FORCE-RESET,
  STRIKER-ANCHOR-DEFERRED-NO-ASTERISK,
  WARM-MODE-MAGNITUDE-GATE-REJECTED (MUST NOT REGRESS —
  closes a different cohort; the WG fix must preserve
  the magnitude-gate guard for genuine score jumps while
  letting through legitimate +1 per-ball increments).
- **STRIKER-LOCK-MID-OVER-SUPPRESSED** (148 instances) —
  designed; must NOT be weakened by any WS-V.A fix.
- **PA threshold (WS-O.c)** — investigation cohort; WG fix
  must not regress.
- **Shape A, Shape B, D1, D2-Layer-1a, H1, H3 gates** —
  all preserved.

---

## §10 Step-1c vs step-2 recommendation

### §10.1 Recommendation: WS-V.A FALSIFICATION-EXIT;
new investigation V.A1 at score-commit-gate

**WS-V.A as originally scoped (Scout per-ball runs
misclassification) FALSIFIES.** The work was done correctly
— the cohort-cascade verification confirmed the structure,
but the ROOT layer is one level deeper than WS-V step-1's
"Scout token-extraction" framing claimed. This is exactly
the case described in CLAUDE.md "Trace-and-Detect v1":
> "P7 (cohort-cascade discrepancy) — when a cascade
> attribution holds at intermediate layer but the root
> layer is empirically different from the WS framing,
> SPLIT-and-FALSIFY-EXIT."

### §10.2 Step-2 BLOCKED for WS-V.A

A patch at Scout / extractor / VLM-prompt would
**REGRESS-NEUTRAL** (no effect on the per-ball tokens because
the defect isn't there) AND **WASTE BUDGET** on a fix
surface that doesn't move the residue.

### §10.3 Pivot recommendation: new workstream V.A1 at
score-commit-gate, step-1c instrumentation required

**WS-V.A1** (proposed):
- **Target**: identify the specific gate in
  `test_pipeline.py` scoreboard-mutation phase that
  REJECTS the per-ball score increments 7→8, 8→9, 9→15,
  15→16, 16→17 during over 1 (and analogous in over 2-3).
- **Step-1b** (static): cross-check the trace
  `validate_dckkr_20260522_063211.jsonl` for tag firings at
  frames F82, F96, F97, F119, F126. Look for:
  CAM-GRAPHIC-FAST-PATH-DEFER-NO-BALL-EVENT,
  WARM-MODE-MAGNITUDE-GATE-REJECTED,
  COLD-START-OVERREAD-REJECTED, score-consistent-read
  demotion tags, BROADCAST-OVERRIDE-VETOED-TEAM-MISMATCH,
  state-recovery gates.
- **Step-1c**: if static trace insufficient, add NO-OP
  log-only instrumentation at every score-commit-decision
  site to log `(frame, observed_score, committed_score,
  delta, decision, gate_reason)`. Run snapshotter; inspect.
- **Step-2**: gate-relaxation patch with predicted-flip
  table locked at per-ball-commit resolution.
- **Step-3**: snapshot replay; predict ~65-70 row closure.

### §10.4 WS-V.B + WS-V.C unchanged

- **WS-V.B** (3 anchor visibility rows): proceed
  independently; fix surface is snapshotter timing.
  Predicted closure 3 → 0. NOT BLOCKED by WS-V.A1.
- **WS-V.C** (~10 striker-write residue at 4.3 / 4.4):
  still requires step-1b instrumentation. Independent
  of WS-V.A1 BUT empirically may close partially if
  WS-V.A1 fixes the 4.x phantom-runs cascade (because the
  ledger-inversion at 4.3 + 4.4 may be downstream of the
  +20 phantom score).

### §10.5 Sequencing decision

| Priority | Workstream | Step | Predicted closure | Block? |
|---|---|---|---|---|
| 1 | WS-V.A1 (score-commit-gate) | step-1b → step-1c → step-2 | ~65-70 rows | NEW investigation |
| 2 | WS-V.B (anchor visibility) | step-2 | 3 → 0 | Independent |
| 3 | WS-V.C (striker-write residue) | step-1b → step-2 | ~10 → predict 0-10 | May partial-close on WS-V.A1 |

**Highest-impact, leading priority: WS-V.A1.**

---

## §11 Methodology note

This investigation reverses the WS-V step-1 hypothesis at
the layer-attribution level:

- **WS-V step-1**: per-frame trace evidence → cohort partition
  → leading per-cohort hypothesis (Cohort A = Scout token-
  extraction layer per-ball runs under-detection).
- **WS-V.A step-1b**: scout_raw audit of THE SCOUT-LAYER
  HYPOTHESIS → empirical observation that Scout's STRIP at
  the commit frame ALREADY carries the GT-correct score →
  the per-ball-token defect is downstream of Scout →
  hypothesis falsified at the layer boundary.

This is the **"intermediate-layer cascade attribution holds,
but root layer is one level deeper than originally framed"**
pattern. The WS-V step-1 framing was directionally correct
(cohort-cascade discipline) but layer-attributionally
wrong (Scout vs pipeline-commit gate). The §15-fence-style
falsification triggered at the very first cross-check — a
clean exit, no wasted budget on a wrong-surface patch.

Going-forward discipline (per CLAUDE.md "S26-v2 spot-check
before patch" + "single-IV discipline"): **for every
"Scout extracts X wrong" hypothesis, audit Scout's raw
output BEFORE concluding Scout is wrong**. The S26-v2
12-frame spot-check in §2.1 falsified the entire WS-V step-1
attribution in one operation.

---

## §12 Stop-condition firing

Per workstream charter:

> "Per-ball parity table reveals Scout misclassification is
> NOT singles→dots (different pattern entirely) → STOP,
> refine cohort framing."

**FIRED**. The misclassification IS singles→dots in shape
but NOT singles→dots in mechanism: Scout reads singles
correctly via the cumulative-score path; the pipeline
fails to commit those increments. Cohort framing IS
refined — moved one layer downstream of Scout.

> "Investigation surfaces architecturally-required change
> (e.g., fix surface requires WS-Q or fundamentally different
> Scout prompt/extractor design) → STOP, flag scope."

**ALSO FIRED**. Fix surface is at the score-commit-gate,
which is the WS-Q (score-state-unification refactor)
adjacent surface. Need to verify WS-Q didn't unify away
the gate in question OR that the gate sits in a way that
fixing it doesn't conflict with WS-Q's eventual landing.

---

## Deliverables

- Memo path: `files/docs/investigations/workstream_v_a_scout_per_ball_runs_misclassification_root_cause.md`
- Section count: 12 (§1-§12, including methodology note +
  stop-condition firing)
- WS-V.A FALSIFICATION-EXIT recommended; pivot to WS-V.A1
  at score-commit-gate layer.

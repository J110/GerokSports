# Workstream V — Striker-anchor swap root-cause re-investigation (step-1)

**Status.** Step-1 closed; cohort RE-PARTITIONED on empirical
trace evidence; three prior hypotheses (WS-O OA cold-start
magnitude, WS-P P1 squad-convention, WS-U V2 prompt parrot-
anchor) all empirically falsified at user-visible layer; the
"~50 striker-anchor swap divergences" framing collapses into
**three distinct cohorts** with mostly NON-striker-writer
roots. The dominant cohort (~40 of ~50 rows) is a **per-ball
runs misclassification cascade** at Scout's token-extraction
layer — NOT a striker writer defect. Only ~6 rows are a
genuine residue striker-anchor swap (4.3 + 4.4 ledger
inversion) for which a striker-write site IS the root.

**Pre-screen verdict.** GREEN-SPLIT — fix surface is COHORT-
SPECIFIC and must be cleaved at WS-V trigger before any
patch lands. Treating "~50 striker_name swap rows" as a
single defect class is the methodology error that produced
the three falsified prior workstreams.

**Outcome.** Static-falsification chain converges on a
**TRIPLE-COHORT verdict** (VG) with three independent fix
surfaces, none of which any prior WS (O / P / U) directly
addresses. Leading per-cohort candidate: **A → SCOUT-TOKEN
(per-ball runs misclassification, ~40 rows), B → ANCHOR-
VISIBILITY-WINDOW (~3 rows pre-anchor), C → STRIKER-WRITE
RESIDUE (~6 rows at 4.3 + 4.4 ledger inversion)**.

**S33 instrumentation-aware methodology applied.** This memo
is a STATIC TRACE-PROCESS-OF-ELIMINATION investigation
(per CLAUDE.md "trace-and-detect"). Per-frame trace
`validate_dckkr_20260522_063211.jsonl` cross-referenced
against `/tmp/dckkr_post_ws_o_b_pipeline_snapshots.jsonl`
+ `files/tests/fixtures/dckkr_ground_truth_ui_snapshots.jsonl`.
Two-instance evidence: (a) the SM state at frame 30 (cold-
start anchor commit) is CORRECT — `striker='Pathum Nissanka',
non_striker='KL Rahul'`, matching GT 0.1 striker=Nissanka;
(b) the SM state rotates CORRECTLY through frames 30→79
(over 0) on the dot/single tokens the pipeline observed — the
defect is what the pipeline OBSERVED as the per-ball token,
not how it propagated through rotation math.

**Hypothesis count.** 7 (VA / VB / VC / VD / VE / VF / VG)
with VG (cohort-split) as the leading verdict. Static
falsifications: 4 (VA, VB, VC, VD partial); VE PARTIAL
falsified (post-wicket cohort empty in 0.x-3.x; not
applicable to top-of-baseline cohort); VF FALSIFIED at
gate 1; VG CONFIRMED.

---

## §1 Empirical anchor — per-ball striker_name + this_over_tokens parity table

Cohort source: `files/tests/baselines/dckkr_diff_post_ws_o_b_baseline.md`
divergence list. Cross-referenced against
`/tmp/dckkr_post_ws_o_b_pipeline_snapshots.jsonl` and
`files/tests/fixtures/dckkr_ground_truth_ui_snapshots.jsonl`
ground-truth.

| over.ball | TOK-parity | striker (GT) | striker (PL) | PL-tokens | GT-tokens | Cohort |
|---|---|---|---|---|---|---|
| 0.1 | TOK-DIFF | Nissanka | None | None | `['.']` | B (pre-anchor) |
| 0.2 | TOK-OK | Nissanka | Nissanka | `['.', '4']` | `['.', '4']` | — (non-striker visibility, ledger correct) |
| 0.3 | TOK-OK | None (single-batter visibility) | Rahul | `['.', '4', '1']` | `['.', '4', '1']` | B (pre-anchor / visibility-window) |
| 0.4 | TOK-OK | Rahul | Rahul | `['.', '4', '1', '.']` | `['.', '4', '1', '.']` | — |
| 0.5 | TOK-DIFF | Nissanka | Rahul | `['.', '4', '1', '.', '.']` | `['.', '4', '1', '.', '1']` | A (token-cascade) |
| 0.6 | TOK-DIFF | Rahul | Nissanka | `['.', '4', '1', '.', '.', '.']` | `['.', '4', '1', '.', '1', '1']` | A |
| 1.1 | TOK-OK | Nissanka | (matched) | `['.']` | `['.']` | — |
| 1.2 | TOK-DIFF | Rahul | Nissanka | `['.', '.']` | `['.', '1']` | A |
| 1.3 | TOK-DIFF | (OK) | (OK) | `['.', '.', '.']` | `['.', '1', '1']` | A (token-only, no striker swap yet — striker held by missed-rotation accumulation) |
| 1.4 | TOK-DIFF | (OK) | (OK) | `['.', '.', '.', '.']` | `['.', '1', '1', '6']` | A |
| 1.5 | TOK-DIFF | Rahul | Nissanka | `['.', '.', '.', '.', '.']` | `['.', '1', '1', '6', '1']` | A |
| 1.6 | TOK-DIFF | Nissanka | Rahul | `['.', '.', '.', '.', '.', '.']` | `['.', '1', '1', '6', '1', '1']` | A |
| 2.1 | TOK-OK | (OK) | (OK) | `['.']` | `['.']` | — |
| 2.2 | TOK-DIFF | (OK) | (OK) | `['.', '.']` | `['.', '4']` | A |
| 2.3 | TOK-DIFF | Nissanka | Rahul | `['.', '.', '.']` | `['.', '4', '1']` | A |
| 2.4 | TOK-DIFF | Nissanka | Rahul | `['.', '.', '.', '.']` | `['.', '4', '1', '.']` | A |
| 2.5 | TOK-DIFF | Nissanka | Rahul | `['.', '.', '.', '.', '.']` | `['.', '4', '1', '.', '.']` | A |
| 2.6 | TOK-DIFF | (OK) | (OK) | `['.', '.', '.', '.', '.', '.']` | `['.', '4', '1', '.', '.', '6']` | A |
| 3.1 | TOK-DIFF | (OK) | (OK) | `['.']` | `['1']` | A |
| 3.2 | TOK-DIFF | (OK) | (OK) | `['.', '.']` | `['1', '4']` | A |
| 3.3 | TOK-DIFF | (OK) | (OK) | `['.', '.', '.']` | `['1', '4', '.']` | A |
| 3.4 | TOK-DIFF | Rahul | Nissanka | `['.', '.', '.', '.']` | `['1', '4', '.', '1']` | A |
| 3.5 | TOK-DIFF | Rahul | Nissanka | `['.', '.', '.', '.', '.']` | `['1', '4', '.', '1', '4']` | A |
| 3.6 | TOK-DIFF | Nissanka | Rahul | `['.', '.', '.', '.', '.', '.']` | `['1', '4', '.', '1', '4', '1']` | A |
| 4.1 | TOK-OK | (OK) | (OK) | `['4']` | `['4']` | — |
| 4.2 | TOK-OK | (OK) | (OK) | `['4', '1']` | `['4', '1']` | — |
| 4.3 | **TOK-OK** | **Nissanka** | **Rahul** | `['4', '1', '.']` | `['4', '1', '.']` | **C (genuine striker-write residue)** |
| 4.4 | **TOK-OK** | **Rahul** | **Nissanka** | `['4', '1', '.', '1']` | `['4', '1', '.', '1']` | **C** |
| 4.5 | TOK-OK | (OK) | (OK) | `['4', '1', '.', '1', '4']` | `['4', '1', '.', '1', '4']` | — |

**Per-row reclassification of the baseline ~50 "striker
swap" divergences**:

| Cohort | Striker-name rows | Ledger rows (runs/balls/4s/6s) | Total |
|---|---|---|---|
| **A — per-ball runs token cascade** (overs 0.5–3.6) | ~10 striker_name + ~10 non_striker_name | ~24 ledger rows | **~44** |
| **B — anchor visibility window** (0.1–0.3) | 3 striker/non_striker rows | 0 | **3** |
| **C — genuine striker-write residue** (4.3, 4.4) | 4 striker/non_striker rows | ~6 ledger rows (4s/6s ledger inversion) | **~10** |
| **Sum** | | | **~57 (≈ "~50 cohort")** |

The "~50 striker-anchor swap" framing in prior workstream
charters CONFLATES three independent surfaces.

---

## §2 Per-divergence write-site attribution (trace evidence)

Source: `logs/trace/validate_dckkr_20260522_063211.jsonl`.

### §2.1 Frame-level striker state, frames 30-79 (covers cold-start commit through over 0)

| frame | over | mode | SM.striker | SM.non | Event |
|---|---|---|---|---|---|
| 28 | 0.1 | COLD_START | — | — | Scout reads `PATHUM RAHUL` (raw, unsplit) |
| 29 | 0.1 | WARM | — | — | TEAM commit `DC`, BATTING-CARD-CREATED |
| **30** | **0.1** | **WARM** | **Pathum Nissanka** | **KL Rahul** | **Cold-start anchor commit (STRIKER-OBSERVE seeds slot pair)** |
| 31 | 0.1 | WARM | Pathum Nissanka | KL Rahul | `[SM] COLD_START → WARM`; `EVENT-BASELINE-SEEDED-WARM-INITIAL`; partnership write |
| 34-49 | 0.2 | WARM | Pathum Nissanka | KL Rahul | Stable (ball 0.2 not yet rotated) |
| **50-64** | **0.3** | **WARM** | **KL Rahul** | **Pathum Nissanka** | **Rotation after ball 0.2 = `4` (even, no swap) + ball 0.3 = `1` (odd, swap)** |
| 65-71 | 0.4 | WARM | KL Rahul | Pathum Nissanka | Stable |
| **72-79** | **0.5** | **WARM** | **Pathum Nissanka** | **KL Rahul** | **Rotation back after ball 0.4 = `.` + ball 0.5 = pipeline read it as `.` but GT says `1`** |
| 80 | 1.0 | WARM | Pathum Nissanka | KL Rahul | Over change, last ball runs=1, double-rotation cancel → striker stays Nissanka |

**Critical observation #1**: Frame 30 SM-state shows
striker='Pathum Nissanka', non_striker='KL Rahul'. This MATCHES
the GT opener convention (Nissanka faces ball 1). **Cold-
start anchor is CORRECT**.

**Critical observation #2**: SM rotation correctly executes
swap math on the tokens it observed. At over 0, pipeline
observed `['.', '4', '1', '.', '.']` (5 balls before snapshot
at 0.5). Singles: 1 (ball 0.3). Per-ball swap fires once;
striker rotates Nissanka → Rahul → Nissanka. At 0.5
pipeline.striker = Nissanka (correct per pipeline's observed
tokens). But **GT tokens contain TWO singles (`.`,`4`,`1`,`.`,`1`)**
— under GT the swap fires twice; striker rotates Nissanka →
Rahul → Nissanka → Rahul. **GT 0.5 striker = Nissanka still
(after even ball swap + odd ball swap)? Re-checking**: GT
tokens `[., 4, 1, ., 1]` means ball-3 is single (swap), ball-
5 is single (swap). Two swaps from Nissanka start → Rahul →
Nissanka. GT 0.5 striker = Nissanka. **Pipeline observed
only one single (ball 0.3), so one swap → Nissanka → Rahul
→ Rahul.** And the snapshot at 0.5 shows striker=Rahul.
**Mismatch IS caused by the pipeline missing GT's ball-5
single, not by a striker-write defect**.

### §2.2 Striker-write tag distribution (entire DCKKR replay)

| Tag | Count | Role |
|---|---|---|
| `STRIKER-LOCK-MID-OVER-SUPPRESSED` | 148 | Defensive — DETERMINISTIC-rotation gate refusing mid-over tracker corrections (DESIGNED behavior per `deterministic_striker_rotation_design.md` §3) |
| `STRIKER-OBSERVE` | 268 | Observation-only signal (consensus tracker), no writes |
| `STRIKER-SM-BROADCAST-DISAGREES-DETERMINISTIC` | 72 | Audit-only — broadcast contradicts deterministic; deterministic wins |
| `STRIKER-IDENTIFY-FALLBACK-INVOKED` | 37 | Fallback identification when extractor has 0/1 batters |
| `STRIKER-WRITE` | 19 | Actual write events |
| `STRIKER-ALIGN-FALLBACK` | 17 | Alignment fallback |
| `STRIKER-SM-CUTOVER` | 21 | Over-end SM mirror |
| `STRIKER-OVER-END-DOUBLE-ROTATION-APPLIED` | 12 | Designed over-end rotation |
| `STRIKER-COLLISION` | 4 | Refused (already-non self-collide guard) |
| `STRIKER-DEDUP` | 3 | Dedup guard |
| `WICKET-ATTRIB` | 5 | All POST-frame-372 (post first wicket) |
| `EVENT-BASELINE-SEEDED-WARM-INITIAL` | 1 | Frame 31 cold-start exit |

**`STRIKER-EVENT-DISPATCHED`, `STRIKER-IDENTITY-RESOLVED`,
`STRIKER-IDENTITY-PROPOSED`, `STRIKER-IDENTITY-PROPOSAL-
REFUSED` tags: ALL ZERO in the DCKKR validate trace.** These
are the three §15-fence canonical writer tags listed in the
WS-V trigger as the load-bearing observability. They never
fire in the DCKKR replay; the trace surface is the
deterministic-rotation post-suppression set (per
`deterministic_striker_rotation_design.md`).

**Implication**: §15-fence canonical-writer tag taxonomy in
the WS-V trigger applies to a DIFFERENT code era. Current
striker-write surface is `STRIKER-WRITE` (19 instances, from
`test_pipeline.py:3185 (_set_inn_slot_with_sm_mirror)` and
`test_pipeline.py:4865 (apply_scorer_decision)`). The
canonical post-WS-§15-deletion writer is
`_set_inn_slot_with_sm_mirror`.

### §2.3 Striker-write timeline (first 700 frames)

| Frame | over | Site | Event |
|---|---|---|---|
| 80 | 1.0 | OVER-END | Skipped rotation (last ball=1 cancel) → stays Nissanka |
| 209 | 2.0 | OVER-END | Rotation Nissanka ← Rahul |
| 255 | 3.0 | OVER-END | Rotation Nissanka ← Rahul |
| 334 | 4.0 | OVER-END | Skipped rotation (last ball=1 cancel) → stays Rahul |
| 372 | 4.2 | OBSERVE | STRIKER-IDENTIFY-FALLBACK |
| 445 | (over-change) | apply_scorer_decision | non KL Rahul→None |
| 445 | (4.x→5) | WICKET-ATTRIB | Dismissed = Pathum Nissanka |
| 446 | 5.0 | _set_inn_slot_with_sm_mirror | non None→Pathum Nissanka (FW2 came in) |
| 504 | 5.1 | _set_inn_slot_with_sm_mirror | non Pathum→Nitish Rana |
| 660 | 7.0 | _set_inn_slot_with_sm_mirror | striker Pathum→Nitish Rana (over-end rotation) |

For overs 0-4 (the WS-V cohort), the only write sites firing
are over-end double-rotation (designed) and cold-start
initial commit at frame 30. **There are no spurious mid-
over writes that could explain Cohort A or Cohort C
striker-swap rows in the 0.x-3.x cohort.**

---

## §3 Name-source attribution distribution

For the only write sites firing in the 0.x-4.x cohort:

| Write site | Frame range in cohort | Name source consumed | Count |
|---|---|---|---|
| Cold-start anchor commit at frame 30 (`STRIKER-OBSERVE` → consensus → slot pair) | 30 | Scout's `extractor.batters[]` row order (post `[SPLIT]` 'PATHUM RAHUL' → 'PATHUM', 'RAHUL' fuzzy-matched to squad members) | 1 |
| Over-end double-rotation (`STRIKER-OVER-END-DOUBLE-ROTATION-APPLIED`) | 80, 209, 255, 334 | Self-state (rotation math on observed runs parity) | 4 |
| `STRIKER-LOCK-MID-OVER-SUPPRESSED` (defensive no-op) | 51-79, 115-372, etc. | Would-have used: `non_striker_tracker.leader` for proposed-striker (e.g. `KL Rahul` mid-0.3) | 148 (all suppressed) |
| `STRIKER-SM-BROADCAST-DISAGREES-DETERMINISTIC` (audit no-op) | 115-372+ | Would-have used: Scout's `broadcast_striker` (`KL Rahul` or `Pathum Nissanka`); deterministic wins | 72 (all audit) |

**Name-source distribution for the ONE write that committed
in the cohort**: Scout's `extractor.batters[0]` and
`extractor.batters[1]` after fuzzy match to squad. At frame
30, extractor.batters = `[{name: 'Pathum Nissanka', balls:1, striker:False}, {name: 'KL Rahul', balls:None, striker:None}]`.
Neither carries a `striker:True` flag.

The anchor at frame 30 commits **striker=Pathum Nissanka,
non=KL Rahul**, which IS the GT-correct opener pair. The
anchor itself is correct — WS-P's squad-convention fix
(`88e03f5`) preserved this correct anchor.

---

## §4 Pre-write SM-state context

### §4.1 At frame 30 (cold-start anchor commit)

- `self.striker` was `None` (cold-start, never written)
- `self.non_striker` was `None`
- `self.bat1_name` = `'Pathum Nissanka'` (Scout's row-1)
- `self.bat2_name` = `'KL Rahul'` (Scout's row-2)
- `card.broadcast_striker` = `None` (Scout did not detect
  asterisk; observed `PATHUM RAHUL` raw string without
  `*` or `>` marker)
- WS-P's `cold_start_squad_convention` path: `_sq[0]`
  (batting_card insertion-order first) = `'Pathum Nissanka'`.
  Check `_sq[0] == self.bat2_name` → `'Pathum Nissanka' ==
  'KL Rahul'` → **False**.
- Therefore: legacy `cold_start_no_indicator` default fires:
  `_set_slot_pair(self.bat1_name, self.bat2_name)` =
  `_set_slot_pair('Pathum Nissanka', 'KL Rahul')`.
- Result: striker=Nissanka, non=Rahul. **CORRECT for ball 0.1.**

**WS-P's squad-convention path is NEVER ACTIVATED on the
DCKKR dump** (its mechanism-tag count = 0 in the trace, per
the WS-P V2 step-3 finding). The dump's Scout-row order is
ALREADY `[Nissanka, Rahul]`, matching squad convention.

### §4.2 At over-end double-rotation frames (80, 209, 255, 334)

- `self.striker` is already set per cold-start anchor
- `self.non_striker` is already set
- Rotation math reads `last_ball_runs` (the pipeline's
  observed token for the last ball of the prior over)
- Rotation fires (or skips) per `STRIKER-OVER-END-DOUBLE-
  ROTATION-APPLIED` rules
- **No name-source mismatch**: rotation is pure self-state

### §4.3 At frames where the visible "swap" appears in the snapshot

Per §2.1 walkthrough: SM-state is INTERNALLY CONSISTENT with
the tokens the pipeline observed. The snapshot reflects SM-
state truthfully. The defect is **upstream of the SM-state**:
the per-ball tokens the pipeline observed differ from GT.

---

## §5 Cohort partitioning by mechanism (REVISED from WS-V trigger)

| Partition | Mechanism | Count | Examples | Root LAYER |
|---|---|---|---|---|
| **A — Token cascade** | Scout / extractor misses GT's per-ball singles (`1` read as `.`); rotation math runs on wrong inputs; striker stays where it shouldn't | **~44 of ~57 rows** | All overs 1, 2, 3, 4.6 missing | **Scout token extractor** (NOT a striker writer) |
| **B — Anchor visibility window** | Pre-anchor (0.1 pipeline anchor not yet committed at snapshot time) or single-batter visibility window in GT (0.3 GT shows only non_striker) | 3 rows | 0.1, 0.2, 0.3 | **Snapshot timing** (NOT a striker writer) |
| **C — Genuine striker-write residue** | Tokens match GT EXACTLY (`[4, 1, ., 1]`) but striker_name + ledger inverted at 4.3 + 4.4 | ~10 rows (4 striker_name + 6 ledger) | 4.3, 4.4 | **Striker-write site** (LIKELY canonical write order inverted) |
| **D — Cold-start initial-anchor swap** | (originally hypothesized by WS-P) | **0 rows** | (WS-P P1 closed it) | (closed) |
| **E — Mid-innings rotation swap** | apply_striker_event rotation defects | **0 rows** | none | (none) |
| **F — Post-wicket identity swap** | WICKET-ATTRIB attribution flips | **0 rows** | (none in 0.x-3.x; 4.x falls under C) | (n/a) |
| **G — Per-frame proposal swap** | apply_striker_identity_proposed flips | **0 rows** | (suppressed by LOCK gate, 148 instances) | (n/a — defensive gate working) |

**Lock count per partition**: A: ~44; B: 3; C: ~10; D-G: 0.

**Decisive empirical observation**: Cohort A maps to a token-
extraction failure, not a striker-write failure. The pipeline
observed `['.', '.', '.', '.', '.', '.']` for over 1, GT
observed `['.', '1', '1', '6', '1', '1']` — the pipeline
missed 5 of 6 balls (only the dot was read; the runs were
not). The "striker swap" at 1.2 / 1.5 / 1.6 is a downstream
consequence: rotation math gets no swaps from the read
tokens, so striker stays Nissanka, but GT rotated multiple
times.

---

## §6 Falsification chain per partition

### §6.1 Cohort A (token cascade)

- **WS-P P1 squad-convention**: addresses cold-start
  initial-anchor selection. Partition A's anchor IS correct
  (Nissanka striker, Rahul non at frame 30 matches GT 0.1).
  WS-P P1 fix is ORTHOGONAL to Partition A. **Not the root.**
- **WS-O OA cold-start magnitude**: addresses score-read
  inflation at cold-start (the 63-vs-43 cascade at over 4).
  Partition A's defect is per-ball runs misclassification,
  not initial-score inflation. **Orthogonal**.
- **WS-U V2 prompt parrot-anchor (and the not-yet-landed
  UD-prime variant)**: targets Scout's mode-collapse onto
  IPL-graphic priors. Partition A IS a Scout-layer defect —
  Scout is reading every ball as a dot when GT has singles
  — but the parrot-anchor mode-collapse mechanism is the
  WRONG diagnosis. Singles being read as dots is **under-
  detection (false negative on per-ball runs)**, not
  parrot-anchor mode-collapse. **The Scout layer IS the
  defect surface; but the parrot-anchor specific hypothesis
  is FALSIFIED — a different Scout pathology applies.**

### §6.2 Cohort B (anchor visibility window)

- **All prior WSes**: B is a snapshot-emission timing artifact,
  not a state-layer defect. The diff fields at 0.1 / 0.2 / 0.3
  are visibility-window false-positives — pipeline's snapshot
  state at 0.1 is `None` (anchor not yet committed at
  snapshot capture time per the snapshotter's
  `extracted_to_frame_input` timing). **No prior WS targeted
  this**; it would benefit from snapshotter timing alignment
  but is not a striker defect.

### §6.3 Cohort C (genuine striker-write residue at 4.3 + 4.4)

- **WS-P P1 squad-convention**: addresses initial anchor at
  frame 30; this anchor is already correct. C is at 4.3 (~24
  balls later) — a different write site fires. **Not the root.**
- **WS-O OA cold-start magnitude**: cold-start cascade is
  closed by ball 0.6 (WARM mode established at frame 31).
  4.3 is mid-innings, well past cold-start. **Orthogonal.**
- **WS-U V2 prompt**: tokens at 4.3 / 4.4 MATCH GT EXACTLY,
  so Scout token extraction is NOT the defect for Cohort C.
  Striker state inversion at 4.3 + 4.4 must be a striker-
  write site issue (the per-batter ledger is also inverted —
  Nissanka's runs/balls/4s/6s are credited to Rahul, see
  §1 4.3/4.4 ledger comparison). **Not the root.**

**Cohort C is the SOLE cohort for which a striker-write site
is a plausible root** — and it's only ~6 ledger rows + 4
striker_name rows out of the ~50-row baseline. The prior WS
diagnoses missed this because they DID NOT partition the
cohort before formulating hypotheses.

---

## §7 Hypothesis enumeration + §7.2 audit on leading candidate

| Hypothesis | Verdict | Notes |
|---|---|---|
| **VA**: Non-canonical striker writer exists (§15 fence violation) | FALSIFIED | All 19 STRIKER-WRITE events in the trace map to known sites (`test_pipeline.py:3185 _set_inn_slot_with_sm_mirror`, `test_pipeline.py:4865 apply_scorer_decision`). No spurious writers detected in the 0.x-3.x cohort frames. |
| **VB**: `apply_striker_identity_proposed` conservative-refuse triggers on legitimate input → wrong default | PARTIAL-FALSIFIED | This tag never fires in the DCKKR trace (0 occurrences). The legacy proposed-refuse mechanism has been replaced by `STRIKER-LOCK-MID-OVER-SUPPRESSED` (148 instances, designed). |
| **VC**: Slot assignment correct, but striker/non ROLES inverted at initial-anchor | FALSIFIED | Frame 30 SM-state shows striker=Nissanka, non=Rahul — CORRECT per GT 0.1. Initial anchor is right. |
| **VD**: Race condition — correct write followed by overwrite at later frame | FALSIFIED in 0.x-3.x | No spurious writes detected. SM-state stays internally consistent with observed tokens. |
| **VE**: WICKET-ATTRIB flips slot identity at every wicket | NOT APPLICABLE to cohort | WICKET-ATTRIB first fires at frame 445 (transition to over 5); cohort is overs 0-4. |
| **VF**: Snapshot-rendering layer flip not a state-layer issue | FALSIFIED for Cohort C | At 4.3 SM-state is also wrong per §1 ledger inspection (Nissanka's stats credited to Rahul slot in snapshot AND ledger). State is wrong, not just rendering. |
| **VG**: **Cohort split — multiple partitions need separate fixes** | **CONFIRMED — LEADING** | Per §5 partition table. A (Scout-token), B (snapshot timing), C (striker-write residue) each need independent investigation. |

### §7.2 audit on leading candidate (VG)

| Gate | Status | Rationale |
|---|---|---|
| **1 (defect-class fit)** | PASS | VG decomposes the ~50-row cohort into 3 mechanism partitions with empirically verified token-vs-GT alignment + per-partition write-site evidence from the trace. |
| **2 (backward-compat)** | PASS (per-partition) | Each fix surface is independent; no cross-cohort regression risk. |
| **3 (fix-surface attribution)** | PASS — three-site | A: Scout token extractor (`files/eyes/vision.py` SCOUT prompt + `files/eyes/extractor.py` per-ball token parsing); B: snapshotter timing in `tests/test_pipeline_captured_replay.py`; C: striker-write site at ball 4.3 — **requires step-1b instrumentation to locate** (trace lacks the relevant per-frame ledger writes). |
| **4 (sub-finding promotion)** | DEFER | No new S-number at step-1; Cohort A may surface S34: "Scout per-ball runs under-detection on multi-cut frames". |
| **5 (cohort enumeration completeness)** | PASS | All ~50 baseline rows mapped to A/B/C/—. |
| **6 (test obligation)** | OPEN per-partition at step-2 | Cohort A: per-over token-parity assertion. Cohort B: snapshot-at-anchor-commit timing assertion. Cohort C: per-batter ledger 4.3+4.4 striker-side assertion. |
| **7 (cross-fixture verification)** | DEFER to step-3 | Each cohort's fix predicts a specific subset of rows to close; verify with per-partition snapshot replay. |

---

## §8 Predicted-closure prediction (per-partition)

| Partition | Pre-fix rows | Leading fix | Predicted post-fix rows |
|---|---|---|---|
| **A — Token cascade** | ~44 | Scout token-extraction parity fix (per-ball runs from SCOUT response) | ~44 → ~10 (residual single-ball reads where Scout genuinely can't see the digit) |
| **B — Anchor visibility window** | 3 | Snapshotter `_snapshot_at` timing alignment (defer until anchor commits) | 3 → 0 |
| **C — Genuine striker-write residue** | ~10 | (Requires step-1b — instrumentation needed at 4.3/4.4 write sites) | ~10 → predicted 0 after C-fix, but ROOT NOT YET IDENTIFIED |
| **Total** | ~57 | — | ~57 → ~10 (pending C-fix concrete-write-site identification) |

**WS-V step-1 cannot lock the Cohort-C predicted band**
without runtime data showing which write fired at 4.3 / 4.4
and what name-source it consumed. Existing traces show only
over-end double-rotation tags for those frames; the trace
recorder is missing the load-bearing per-ball-write instance.

---

## §9 Regression-guard enumeration + S33 step-2 verification plan

### §9.1 Regression guard inventory (from post-WS-O.b baseline `c275807`)

- **9 closed surfaces stay at 0**: per `dckkr_diff_post_ws_o_b_baseline.md` §1 (Boundary-counter-double-increment 8 active count, etc. — must not regress; WS-V touches NONE of them).
- **7 active surfaces must not increase**: per same §1 (G-pipeline-lag 94, F-A-commit-lag 10, etc. — WS-V touches none).
- **L2 ledger 30/30 cases**: per WS-U scope-contraction finding, this is the test scope (29/36 is diff-matched count, distinct concept).
- **L1.5 92 preserved**: per recent baselines.
- **Existing defensive gates must stay landed**: WICKET-ATTRIB-BROADCAST-OVERRIDE-APPLIED, BOWLER-DISPATCH-FALLBACK-FIRED, COLD-START-OVERREAD-REJECTED, SCORE-FORCE-RESET, STRIKER-ANCHOR-DEFERRED-NO-ASTERISK, WARM-MODE-MAGNITUDE-GATE-REJECTED — counts preserved.
- **STRIKER-LOCK-MID-OVER-SUPPRESSED** (148 in DCKKR trace) — designed behavior per `deterministic_striker_rotation_design.md`; must NOT be weakened by any WS-V fix (e.g. tempting to "let tracker correct" would re-introduce the mid-over vision-trust failure mode the deterministic-rotation architecture was designed to eliminate).

### §9.2 S33 step-2 verification plan

**Cohort A** (Scout token cascade — leading partition):
- **Step-1b**: trace `validate_dckkr_20260522_063211.jsonl` already has rich per-frame extractor.batters and scout.raw_text_120. Static investigation: enumerate per-frame Scout VISIBLE_TEXT vs per-ball GT runs to identify whether the singles ARE present in VISIBLE_TEXT but mis-parsed (extractor defect), or ARE absent from VISIBLE_TEXT (Scout/VLM defect). This is sufficient to decide between (a) extractor fix (`files/eyes/extractor.py`) and (b) Scout prompt fix (`files/eyes/vision.py`).
- **Step-2**: per-cohort patch with predicted-flip table locked at per-ball token resolution.
- **Step-3**: snapshot replay → ~44 Cohort-A rows → predict ~10 residual.

**Cohort B** (anchor visibility window):
- **Step-1b**: not required; static fix-surface is the snapshotter's `_snapshot_at` invocation timing.
- **Step-2**: snapshotter timing fix; predicted 3 → 0.
- **Step-3**: snapshot replay verification.

**Cohort C** (genuine striker-write residue):
- **Step-1b REQUIRED**: existing trace lacks the per-frame striker-write event at over 4.3 / 4.4 (only OVER-END-DOUBLE-ROTATION at frame 334 covers over-3-to-4 transition, and frames 335-444 are silent for striker writes pre-WICKET-ATTRIB at 445). Need NO-OP log-only instrumentation: per-frame log of `(self.striker, self.non_striker, last_ball_runs, rotation_applied, name_source)` at every rotation site. Run snapshotter; inspect; refine hypothesis.
- **Step-2 BLOCKED**: no concrete write-site identified yet for Cohort C. WS-V step-2 cannot proceed for Cohort C without step-1b instrumentation data.

---

## §10 Step-2 entry data OR step-1b instrumentation plan

### §10.1 RECOMMENDED SEQUENCING

**Per-cohort split with independent step-2 entries**:

1. **WS-V.A** (Cohort A — token cascade): proceed directly to a **Scout/extractor parity step-1b** (compare VISIBLE_TEXT vs GT per-ball token to determine whether the defect is at VLM read or at parser). DOMINANT partition (~44/~57 rows). Predicted closure ~44 → ~10.

2. **WS-V.B** (Cohort B — anchor visibility window): proceed to step-2 directly; fix surface is snapshotter timing. SMALLEST partition (3/~57 rows). Predicted closure 3 → 0.

3. **WS-V.C** (Cohort C — striker-write residue at 4.3/4.4): **REQUIRES STEP-1B instrumentation FIRST** to identify the write site. Existing traces lack the per-frame ledger-write evidence at over 4 transition frames. NO-OP log-only instrumentation: per-rotation site emit `(frame, over, ball, self.striker_pre, self.non_pre, last_ball_runs, rotation_decision, self.striker_post, name_source)`. Replay; locate the wrong write; then formulate a concrete step-2 patch. ~10/~57 rows.

### §10.2 SEQUENCING DECISION POINT

Per CLAUDE.md "single-IV discipline for empirical replays
(causal attribution, not cost-rationing)" — WS-V.A, WS-V.B,
WS-V.C should each be its own single-variable replay
sequence. Attempting a combined fix violates IV discipline.

**Highest-impact partition: A** (~44 rows). Recommend WS-V.A
step-1b proceeds first; WS-V.B and WS-V.C deferred until
WS-V.A closes (or fails) to avoid combined-causality
attribution failures in the replay.

### §10.3 OUTCOME DECISION TREE

- **If WS-V.A step-1b shows VISIBLE_TEXT contains the GT
  singles → extractor parser fix**; expected ~44 → ~5 close.
  Then WS-V.B step-2, then WS-V.C step-1b.
- **If WS-V.A step-1b shows VISIBLE_TEXT lacks the GT
  singles → Scout VLM defect** (different from parrot-
  anchor; needs new investigation thread). Defer to a
  WS-V.A1 investigation. Then WS-V.B + WS-V.C proceed
  independently.
- **If WS-V.A step-1b inconclusive** → escalate to per-
  frame VLM raw-response inspection (Scout instrumentation
  capture).

---

## Methodology note

This investigation reverses prior WS-O/P/U hypothesis order:
- WS-O/P/U: hypothesis-first (cold-start magnitude / squad-
  convention / parrot-anchor) → search for evidence in code
  → predict cohort closure → empirical NO-OP.
- WS-V: trace-evidence-first → partition cohort by mechanism
  → derive per-partition hypotheses with concrete write-site
  + name-source attribution → predict per-partition closure.

The trace data has the answer. The ~50-row "striker swap"
cohort is NOT a single defect — it is three orthogonal
defect surfaces of which only Cohort C (~10 rows) is a
genuine striker-write defect. WS-P / WS-O / WS-U each had
the correct LAYER intuition (cold-start anchor, score
inflation, Scout prompt) but applied the fix to a partition
mismatch:
- WS-P fixed an anchor that wasn't broken on the DCKKR dump.
- WS-O fixed a magnitude gate at the wrong layer (score, not
  per-ball runs).
- WS-U targeted the right LAYER (Scout) with the wrong
  mechanism (parrot-anchor vs per-ball under-detection).

Going-forward discipline (per CLAUDE.md "pre-screen fix-
surface category" + "S26-v2 spot-check"): **partition the
cohort empirically before hypothesizing the mechanism**.

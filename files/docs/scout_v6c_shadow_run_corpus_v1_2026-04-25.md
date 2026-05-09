# V6c shadow run — corpus_v1 regression filter (2026-04-25)

## Purpose

This is **Step 2** of Path C from the 2026-04-25 V6c plan: a corpus_v1
regression filter that decides whether V6c is eligible to proceed to
tomorrow's combined-corpus shadow run (corpus_v1 + freshly relabeled
prod-eval frames from match 2). It is **not** the ship/no-ship decision.

The original 65-frame plan (corpus_v1 + 23 prod-eval + F976) was
blocked by a separate operational issue: the 2026-04-25 18:36:49
pipeline restart (which deployed P0-A / P0-B / Pass-2 async) cleared
`debug_frames/` before the prod-eval images could be archived, and the
prod-eval JSON's `path` field pointed at the live capture dir. All 23
production frames were lost. The frame-archival fix shipped in this
same session prevents this from recurring; tomorrow's match-2 sample
will be durable.

## Decision criteria (regression filter only)

V6c clears the filter iff all of the following hold against V5 on
the 41-frame corpus_v1:

1. Strict `bowlers_end` precision ≥ V5 baseline (31.2%).
2. Strict `bowlers_end` recall on the 5 human-labeled bowlers_end
   frames stays at 100%.
3. `closeup` recall does not regress.
4. Closeup-share distribution shift is modest (no >15 pp swing).

Pass = eligible for tomorrow's combined-corpus run (this is necessary
but not sufficient). Fail = V6c is dead, fall back to V6a / V6b.

## Run shape

- Variants: V6c (new). V0/V1/V2a/V2b/V3/V4/V4b/V5 already cached on
  this corpus from earlier sessions.
- Replicates: 3 per (frame, variant), temperature=0,
  `meta-llama/llama-4-scout-17b-16e-instruct`, max_tokens=600,
  timeout 7s, retry-on-429.
- Corpus: `docs/scout_corpus_v1.json` (41 frames, v1.1 schema).
- Output: `docs/shadow_run_v1.json` (V6c results appended; existing
  variants untouched via the harness's resume logic).
- Wall-clock: ~142s for 123 V6c calls, 0 errors.

Harness change: `shadow_eval/run_shadow.py` now accepts `--variants
V6c` (comma-separated) so a single new variant can be added without
re-running the cached ones. Verified equivalence: same `_call`,
`_run_one`, parsing, alias table, and resume-key as the original
multi-variant pass.

## Headline numbers

|                              | V5 (baseline)        | V6c                  | Delta            |
| ---------------------------- | -------------------- | -------------------- | ---------------- |
| Strict `bowlers_end` prec    | **31.2%** (5/16)     | **33.3%** (5/15)     | **+2.1 pp**      |
| `bowlers_end` recall (N=5)   | **100%** (5/5)       | **100%** (5/5)       | 0                |
| `closeup` strict precision   | 62.5% (10/16)        | 55.6% (10/18)        | −6.9 pp          |
| `closeup` recall (N=12)      | 83.3% (10/12)        | 83.3% (10/12)        | 0                |
| `graphic` strict precision   | 42.9% (3/7)          | 50.0% (3/6)          | +7.1 pp          |
| Coverage-weighted precision  | 36.2%                | 37.1%                | +0.9 pp          |
| Net frame accuracy (41-frame)| 48.8% (20/41)        | 48.8% (20/41)        | 0                |
| Cam flip rate                | 7.3%                 | 9.8%                 | +2.5 pp          |

All four regression-filter criteria pass:

1. BE strict precision: 31.2 → 33.3 → **PASS** (improvement).
2. BE recall on 5: 100% → 100% → **PASS** (floor preserved).
3. Closeup recall: 83.3% → 83.3% → **PASS** (no regression).
4. Distribution shift: closeup share 39.0% → 43.9% (+4.9 pp) →
   **PASS** (modest, within tolerance).

Net frame accuracy is unchanged (20/41 in both): V6c reshapes the
errors rather than reducing them. This is the predicted
"pass-through" outcome on a 41-frame corpus that doesn't densely
sample the production failure mode V6c targets — the user's stated
expectation: corpus_v1 is necessary but not sufficient.

## Per-frame migrations (V5 → V6c)

Only 4 frames changed votes between V5 and V6c. The full diff:

| frame | human   | V5 vote     | V6c vote    | V5 outcome | V6c outcome | net effect on prod severity |
| ----- | ------- | ----------- | ----------- | ---------- | ----------- | --------------------------- |
| f748  | side_on | bowlers_end | closeup     | BE FP      | closeup FP  | **win** (BE FP → closeup FP) |
| f205  | side_on | bowlers_end | closeup     | BE FP      | closeup FP  | **win** (BE FP → closeup FP) |
| f941  | other   | closeup     | bowlers_end | closeup FP | BE FP       | **loss** (closeup FP → BE FP) |
| f020  | other   | graphic     | closeup     | graphic FP | closeup FP  | neutral (FP → FP, low severity both) |

Two of the four migrations (f748, f205) match V6c's design intent
exactly: side-on frames where V5 read the bowler's-end-direction
geometry as `bowlers_end` and V6c correctly demoted them to
`closeup` once the "no full pitch receding away" anchor was in
place. Net BE-FP count drops from 11 to 10 because of these two
migrations.

The f941 migration is the concerning one: a non-cricket `other`
frame went from closeup-FP to BE-FP. BE-FPs trigger downstream
pipeline behaviors (bowler-change pickup, dwell-and-watch), so
operationally this is a worse outcome than a closeup-FP on the same
frame. This is the exact failure mode the user warned about under
"failure mode 1 (over-shift to closeup)" — except the over-shift
went the other way and there's now an over-shift INTO `bowlers_end`
on at least one corpus_v1 frame. To track for tomorrow:

- Watch for the f941 pattern on prod-eval frames: did V6c flip any
  non-cricket / `other` / `ad` frames from closeup or graphic into
  bowlers_end? Any such flip is a strict regression in production.
- Watch for the side_on frames: did the f748 / f205 migration
  reproduce on the prod sample's side_on emissions? That's the
  evidence for the targeted improvement.

## Closeup FP composition shift

|              | V5 closeup FPs                                | V6c closeup FPs                                |
| ------------ | ---------------------------------------------- | ----------------------------------------------- |
| from `other` | 3                                              | 3                                              |
| from `graphic` | 2                                              | 2                                              |
| from `side_on` | 1                                              | 3 (+2: f748, f205)                              |
| total        | 6                                              | 8                                              |

V6c's added closeup-FPs are entirely the side-on frames it pulled
out of bowlers_end — same frames, different bucket. The `other` and
`graphic` source FPs are unchanged, so V6c does not appear to be
broadening closeup over non-closeup-like content (failure mode 3:
graphic break did not occur).

## Phase precision check

Phase precision on the 5 BE TPs is 0/5 (= 0.0%) for both V5 and V6c.

This is **not** a labeling artefact — the corpus_v1 BE TPs do have
`human_frame_phase` populated (f169=release, f955=release, f754=runup,
f945=runup, f946=running_between_wickets). The 0/5 result is real:
both V5 and V6c emit `between_play` as the phase on every BE TP
across all 3 replicates. This is the V5 closeup-example phase
attractor regression already tracked as a P1 backlog item ("Phase
regression from V5 multi-example prompt"): V5's STEP-1 closeup
example uses `frame_phase=between_play`, and Scout copies that phase
literal even when it correctly emits `camera_view=bowlers_end` on a
delivery frame. V6c didn't change the closeup example's phase value
(only the scenario sentence), so it inherits the same regression.

The discrepancy with the V5 prod-eval finding (75% delivery-context
on TPs) is real and worth understanding before tomorrow's combined
run:

- corpus_v1's 5 BE TPs are mostly `batter_closeup_with_background`
  subset frames (f754, f945, f946) — frames where the camera is from
  bowler's-end direction with pitch visible but the action signature
  is ambiguous (running between wickets, batter taking guard). On
  these, `between_play` is arguably defensible even if the human
  rubric called it `runup`.
- Prod-eval's 8 BE TPs were stratified across powerplay / middle and
  selected from frames Scout had already tagged `bowlers_end` in
  production. Selection bias toward "Scout-confident" frames
  probably skews them toward cleaner delivery action where the
  phase correctly fires `release` / `flight` even with the
  closeup-attractor present.
- Net: corpus_v1 phase precision is a worst-case measurement. Prod
  is closer to typical-case. Both are real signal; they answer
  different questions.

V6c's phase emission is unchanged from V5 by design, so phase
precision is **not** a ship criterion for V6c. The phase regression
fix is a separate P1 prompt iteration (add a delivery-context
example with `frame_phase=release`, or remove `frame_phase` from the
STEP-1 examples entirely). M-1 from the rubric (TP-conditional vs
population phase precision) remains the right long-term framing for
how to evaluate that fix when it lands.

## Verdict

**V6c PASSES the corpus_v1 regression filter.** All four criteria
clear. The targeted failure mode (Pattern 1: bowler's-end-direction
closeup) is reproduced and corrected on 2 of the 3 side_on frames V5
misclassified as bowlers_end. Net frame accuracy is unchanged on
this corpus, which is consistent with corpus_v1 not densely sampling
the production failure distribution (only 3 candidate side_on
frames; only 11 BE FPs total).

V6c proceeds to **tomorrow's combined-corpus shadow run** for the
ship/no-ship decision. The plan:

1. Match 2 captures fresh frames (durable to the next restart now
   that the archival fix is in).
2. Stratified sample ~25 BE emissions across powerplay / middle /
   death (with the M-2 sampler bucket-coverage check) and label
   under the v1.2 rubric.
3. Run V6c on the new prod-eval frames; combine with this corpus_v1
   result for a 65-ish-frame combined view.
4. Apply ship criteria: precision >40% on combined → ship; 35-40%
   marginal → tiebreak on net frame accuracy and operational-severity
   FP count (watch the f941 pattern); <35% or recall regresses →
   don't ship, investigate V6a/V6b.

V6c is **NOT** shipped to `vision.py` from this run. The production
prompt remains V5 until tomorrow's combined-corpus result clears
the ship criteria.

## Watch items for tomorrow

- f941-pattern: any closeup/graphic → bowlers_end migration on
  non-cricket prod frames is a strict regression in production (BE-FP
  has higher operational severity than closeup/graphic-FP).
- Closeup precision: V6c's corpus_v1 closeup precision dropped 6.9 pp
  because side_on frames migrated into closeup. If prod-distribution
  shows the same migration is correct (i.e. V5 was BE-FP on those
  side_on prod frames), V6c is a clean win on prod even if corpus_v1
  closeup precision regressed. If prod shows the closeup migration is
  also wrong, V6c is just trading bucket addresses without improving
  classification.
- Cam flip rate rose 7.3% → 9.8%. Modest, but worth watching for
  whether the new closeup-vs-BE boundary destabilises Scout on the
  prod sample's edge cases.

## Files touched

- `files/shadow_eval/variants.py` — added `PROMPT_V6C` (V5 base with
  closeup example sentence rewritten on the discrimination boundary).
- `files/shadow_eval/run_shadow.py` — added `--variants` CLI filter
  for incremental single-variant additions.
- `files/shadow_eval/analyze.py` — added V6c to the variants list.
- `files/docs/shadow_run_v1.json` — appended 123 V6c results
  (variant=V6c, frames=41, replicates=3, errors=0).
- `files/docs/scout_shadow_run_v1_analysis.md` — regenerated with
  V6c included in tables 1-9.

`files/eyes/vision.py` is **deliberately untouched** until tomorrow's
combined-corpus result.

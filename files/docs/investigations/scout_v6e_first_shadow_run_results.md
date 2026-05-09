# Scout V6e — first combined-corpus shadow (K=5) — results

**Date:** 2026-04-30  
**Sequence:** Validate-first **Step 5** (after harness Outcome A + `scout_v6e_design.md`).  
**Code:** `PROMPT_V6E` in `files/shadow_eval/variants.py` (single `.replace()` on `_V6D_BOWLERS_END_EXAMPLE`).  
**Corpus:** `files/docs/scout_corpus_combined_v1.json` (**50** frames).

---

## §1 Executive summary

| Axis | Finding |
|------|---------|
| **Target `pbks_rr_f600`** | **Fixed vs V6d:** pooled plurality **`side_on`** (**11**/**14** successful votes; **3** `bowlers_end`), vs V6d post-harness **`bowlers_end`**. |
| **V6d “other / graphic” cohort** | **Mixed:** `rcb_gt_f937` stays **`other`** vs V6c (preserves V6d). **`rcb_gt_f1455` regresses to unanimous `bowlers_end`** among successful calls — conflicts with V6d plurality **`other`** (the combined-corpus row that represented V6d’s lift off V6c `graphic`). |
| **Operational health** | **Poor during this window:** pooled **503** overload **≈15.9%** rows (**119**/750). Not timeout-shaped; contrasts with **~0.53%** for V6d post-harness. |
| **`f941` / `f205` / `f748`** | **`scout_corpus_combined_v1` does not contain** `f941`, `f205`, `f748`, `f942` IDs — **PRIMARY P2/P3 / secondary S1** from `scout_v6e_design.md` §8 are **not directly re-litigated** here; reliance falls on byte-preservation (`test_v6*` in `files/test_recent_fixes.py`) **plus** the on-corpus regressions noted above. |

**Disposition:** **`V6e` ambiguous → do not ship to production verbatim.** The **`f600`** mechanism is partially validated, but **`rcb_gt_f1455` → `bowlers_end`** is a serious interaction with the expanded bowlers_end STEP‑1 prose (hypothesis: model maps wide/stadium/board-adjacent graphics to false “delivery + field geometry” positives). Prefer **narrower exclusion copy (V6f)** or **Option C / non-prompt** before paste.

Tables: **`files/docs/scout_v6e_ensemble_analysis_autogen.md`**.

---

## §2 Run inventory

| Run | Output | Rows | Errors |
|:---:|--------|-----:|-------:|
| 1 | `shadow_run_v6e_combined_20260430_173344_run1.json` | 150 | 23 |
| 2 | `shadow_run_v6e_combined_20260430_173916_run2.json` | 150 | 23 |
| 3 | `shadow_run_v6e_combined_20260430_174357_run3.json` | 150 | 27 |
| 4 | `shadow_run_v6e_combined_20260430_174803_run4.json` | 150 | 22 |
| 5 | `shadow_run_v6e_combined_20260430_175228_run5.json` | 150 | 24 |

**Groq telemetry (successful rows, representative run 1):** `groq_finish_reason` **stop**; **distinct** non-null **`groq_response_id`** across successes (no duplicates within-run). Error rows carry **503** text, null completion metadata.

Harness defaults unchanged: **`run_shadow`** **`--timeout-s` 15.0**, timeout retry (**`scout_v6d_postharness_rerun_results.md`**).

Wall times were broadly in-band with historical combined runs modulo provider failures (sequential **`sleep 6`** between shells as specified).

Validation expectations from the execution brief:

| Check | Result |
|-------|--------|
| 150 rows / run | **Pass** |
| `<1%` errors / run | **Fail** (**503** storm) |
| Operational interpretability | **503** saturation — **not** S2.1 “prompt structure” absent further evidence |

---

## §3 Migration hash distribution (V6e vs V6d post-harness)

**V6e** per-run hashes: `6521d78e38c985d1` (runs **1,2,4**), `8ebd96fea71fb1f2` (run **3**), `83ecb635b22bb647` (run **5**) → **3** distinct (**S2** “≤2” nominal target: **miss** at headline count — acceptable variance vs V6d’s **3**).

**V6d** post-harness combined set likewise showed **3** distinct hashes (`scout_v6d_postharness_rerun_results.md` narrative + replicate tooling).

Cross-run disagreement driver is dominated by infra-missing replicate slots on V6e (vote depth uneven), not a second deterministic prompt fork.

---

## §4 PRIMARY criteria (`scout_v6e_design.md` §8)

| ID | Status | Evidence |
|----|:------:|----------|
| **P1** `pbks_rr_f600` ≠ `bowlers_end` | **Pass** | Pooled plurality **`side_on`**. |
| **P2** `f941` ≠ `bowlers_end` | **Indeterminate (corpus)** | **`f941` absent** from combined JSON. Proxy risk: **`rcb_gt_f1455`** (**V6d `other`** → **`V6e bowlers_end`**) violates the *spirit* of preserving V6d’s **`other`/no-pitch** landing zone beyond raw rulebook substring tests. |
| **P3** `f205` = `closeup` | **Indeterminate (corpus)** | **`f205` absent.** Construction: `_V6C_CLOSEUP_EXAMPLE` byte-preserved (**unit tests**). |
| **P4** Net accuracy proxy ≥ V6d | **Pass (tie)** | Agreement with **V6c** ensemble plurality:**47**/50 frames for **both** V6d post-harness **and** V6e (**`scout_v6e_ensemble_analysis_autogen.md`**). |
| **P5** BE recall ≥ V6d on BE TPs | **Pass** | **17**/17 frames with **V6c∩V6d** plurality `bowlers_end` remain **`bowlers_end`** under V6e plurality. |

**Net:** Formal P1+P4+P5 pass **on-combined**, with **P2/P3 unscored** absent v1 adjudication rerun.

---

## §5 SECONDARY criteria

| ID | Status | Notes |
|----|:------:|-------|
| **S1** `f748` | **N/A** | Frame absent on combined corpus. |
| **S2** hash count ≤2/run set | **Borderline fail** (**3**) | Matches **V6d** post-harness multiplicity; treat as noisy, not decisive. |
| **S3** pooled error <1% | **Fail** | **15.87%** — **503** overload class; treat as **S3.4-class operational spike** (rerun off-peak / backoff) before condemning prompt length. |
| **S4** accuracy improvement | **No** | Same **47**/50 vs V6c as V6d. |

---

## §6 Watch-frame stability (available combined IDs)

| Frame | V6d post-harness (5-run pl.) | V6e (5-run pl.) | Stable? |
|-------|------------------------------|----------------|---------|
| `pbks_rr_f600` | `bowlers_end` | **`side_on`** | **Intended move** |
| `rcb_gt_f1455` | `other` | **`bowlers_end`** | **Regression** |
| `rcb_gt_f937` | `other` | `other` | **Stable** |
| `f941` / `f205` / `f748` | — | — | **Not on corpus** |

---

## §7 V6e vs V6d discriminating analysis

Only **three** frames change plurality **V6d → V6e** (both sides non-null): **`pbks_rr_f600`**, **`rcb_gt_f1455`**, **`pbks_rr_f931`**.

- **`pbks_rr_f600`:** intended **side_on** routing (third **NOT** clause).
- **`rcb_gt_f1455`:** **undesired** collapse to **`bowlers_end`** — indicates the new clause (or longer STEP‑1 anchor) couples with delivery attractor **even when atmospheric / graphic cues** had been routed to **`other`** under V6d.
- **`pbks_rr_f931`:** `graphic`→`closeup` — collateral topology shift; secondary.

---

## §8 Aggregate metrics (combined)

| Metric | V6e | V6d post-harness (ref.) |
|--------|-----|-------------------------|
| Pooled error rate | **15.87%** | **~0.53%** |
| vs V6c plurality agreement | **47**/50 | **47**/50 |
| BE TP recall (17-frame definition) | **100%** | **100%** |
| Frames plurality-different vs V6d | **3** | baseline |

---

## §9 Decision

**Classify as `V6e ambiguous` tending toward **`V6e fails`** for production paste.**

- **`f600` evidence supports Edit C efficacy** where votes exist.
- **`rcb_gt_f1455` breaks the combined-corpus story** that V6d fixed a graphics→`other` slice — this is analogous to **`S3.2`/investigate prompt interaction** in the Composer brief (different frame than `f941`, same risk class).
- **503 noise** prevents treating non-watch frames at full **15**/15 fidelity; schedule **retry** before any marginal call.

Does **not** yet trigger **`S2` stop** (“`f600` still `bowlers_end`”), but **does** argue against shipping without follow-up edits.

---

## §10 Recommended next steps

1. **Off-peak V6e K=5 rerun** (same harness) until pooled errors **≤1–2%** — confirm `rcb_gt_f1455` behaviour is **not** an artifact of missing votes.
2. If stable: **narrow Edit C** (e.g., require simultaneous **boundary-fielding motion** cues before firing side_on exclusion) — **or** **belt-and suspenders Edit D** (rulebook) *only after* STEP‑1 tightened to avoid **`other`→BE** regressions (**design §3.3** already cautious).
3. **`scout_corpus_v1`** spot-check **`f941` / `f205` / `f748`** under V6e once combined stability is reclaimed.
4. If narrow prompt fails → **`scout_v6e_design.md` §9 Option C / post-hoc discriminator**.

---

## §11 Limitations

- **`replicate_analysis.py` `--runs` ingestion rejected** (`S1.3 >10%` errors/run) → autogen Markdown produced by equivalent offline aggregation.
- **Combined corpus lacks v1 discriminators (`f941`…)** — PRIMARY table incomplete without an additional **`run_shadow`** on **`scout_corpus_v1.json`**.
- **503** dominates — conclusions on non-watch frames weaker where vote depth dips (**min 8**/15 successes observed).

---

## Cross-references

- `scout_v6e_design.md` — §4 paste spec, §8 acceptance matrix, §9 stop/routings.  
- `scout_v6d_postharness_rerun_results.md` — baseline error/latency.  
- `discriminating_frames_v6c_vs_v6d_combined.md` — three on-corpus disagreements defining this evaluation slice.  

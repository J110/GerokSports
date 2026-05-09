# Scout V6d — first ensemble shadow run (K=5, corpus_v1)

**Date:** 2026-04-30  
**Design:** `files/docs/investigations/scout_v6d_design.md` (§7 implementation, §8 acceptance).  
**Methodology:** `files/docs/investigations/scout_v6c_determinism_decision.md` (ensemble / modal metrics, **K≥5**).  
**Machine tables:** `files/docs/scout_v6d_ensemble_analysis_autogen.md` (from `replicate_analysis.py` on five independent **`--no-resume`** runs).

---

## §1 Executive summary

- **Five** offline **`V6d`** shadow envelopes on **`files/docs/scout_corpus_v1.json`**: **123** rows each, **0** **`error`** rows, **`groq_response_id`** unique per run (**S2** checks passed).
- **Headline vs V5 / V6c (per-run majority vote, same 41-frame corpus):**

| Ensemble / baseline | Median net accuracy (vote = human) | Median strict `bowlers_end` precision | Internal flip (avg across 5 runs) | Distinct migration hashes (5 runs) |
|---------------------|-------------------------------------|---------------------------------------|-------------------------------------|--------------------------------------|
| **V5** (single `shadow_run_v1.json`) | **20 / 41** | **31.2%** | 7.3% | n/a |
| **V6c** (5 historical runs) | **19 / 41** | varies (see autogen / per-run table) | ~9.8% (avg of prior autogen) | **4** hashes |
| **V6d** (this session, 5 runs) | **27 / 41** | **35.7%** (every run) | **3.9%** | **2** hashes |

- **PRIMARY criteria (design §8)** — **all five satisfied** on ensemble definitions below (§4). **`f941`** is stable **`other`** on **all five** runs (**operational escalation from V6c cleared**). **`f205`** remains **`closeup`** **5 / 5**.
- **Regression watch:** **`f748`** (human `side_on`) is **`bowlers_end`** on **all five** **`V6d`** runs — loss of V6c-style **`closeup`** plurality on this frame. This is **not** a PRIMARY blocker but is a **major trade-off** versus the V6c remediation pattern.
- **Decision (§7):** **Ship-candidate** per §8 matrix (**all PRIMARY**, multiple SECONDARY hits incl. S1/S4/S5) — **do not** declare production-safe without combined-corpus / live-distribution review; **`f748`** and **`f942`** behaviours need explicit sign-off.

---

## §2 Run inventory (V6d K=5)

| Run | Output file | Wall (observer) | Rows | Errors |
|-----|-------------|-------------------|------|--------|
| d1 | `files/docs/shadow_run_v6d_20260430_145931_run1.json` | 118 s | 123 | 0 |
| d2 | `files/docs/shadow_run_v6d_20260430_150135_run2.json` | 153 s | 123 | 0 |
| d3 | `files/docs/shadow_run_v6d_20260430_150414_run3.json` | 159 s | 123 | 0 |
| d4 | `files/docs/shadow_run_v6d_20260430_150659_run4.json` | 159 s | 123 | 0 |
| d5 | `files/docs/shadow_run_v6d_20260430_150944_run5.json` | 169 s | 123 | 0 |

**Harness:** `python3 shadow_eval/run_shadow.py --variants V6d --corpus docs/scout_corpus_v1.json --output docs/shadow_run_v6d_<TS>_run<i>.json --no-resume` from **`files/`**, **≥6** s gap between launches.

**Metadata:** **`groq_finish_reason`** **`stop`** on all rows in all five runs sampled; **`groq_attempt_count`** often **>** **1** with empty **`error`** (rate-limit retry path), consistent with prior V6c runs.

---

## §3 Migration hash distribution (V6d vs V6c, K=5)

**Definition:** `migration_hash` = SHA-256 first 16 hex chars of canonical JSON of sorted **`(frame_id, vote_cam)`** pairs (tooling in `replicate_analysis.py`; same as determinism session).

| Variant | Distinct hashes (5 runs) | Values (short) |
|---------|--------------------------|----------------|
| **V6d** | **2** | `95fee3489ba0410c` (4×), `b77b83ba73c9c246` (1×, run d3) |
| **V6c** | **4** | see `scout_v6c_determinism_analysis_autogen.md` |

**Interpretation:** **`V6d` does not widen** the hash state space versus **`V6c`** on this evidence — **narrower** (**2** vs **4**). §8 S3.1-style concern (“V6d wider variance”) **did not** occur.

**Cross-run flip (modal vote differs across runs):** **`V6d` 2.4%** (1 / 41 frames) vs **`V6c` 7.3%** in the pooled five-run determinism autogen — **lower** discord on this corpus slice.

---

## §4 PRIMARY criteria evaluation (§8)

Ensemble rule: **per-run** metrics use majority vote over three replicates inside each JSON; **PRIMARY 1 / 4 / 5** use **median across the five runs** where applicable. **PRIMARY 2 / 3** use **plurality vote across the five runs’** per-run majority labels (standard K-ensemble mode from the determinism memo).

| ID | Criterion | Result | Pass? |
|----|-----------|--------|-------|
| **P1** | Median net accuracy **≥ 20 / 41** (V5 floor) | Per-run net: **27, 27, 26, 27, 27** → median **27 / 41** | **Yes** |
| **P2** | **`f941`** ensemble plurality **≠ `bowlers_end`** | **`other`** **5 / 5** runs | **Yes** |
| **P3** | **`f205`** ensemble plurality **`closeup`** | **`closeup`** **5 / 5** | **Yes** |
| **P4** | Median strict `bowlers_end` precision **≥ 31.2%** | **35.7%** every run → median **35.7%** | **Yes** |
| **P5** | `bowlers_end` recall on **five** human-labelled BE TPs **100%** each run | TPs `f169,f955,f754,f945,f946` — **`vote_cam == bowlers_end`** on **all five** runs | **Yes** |

---

## §5 Watch frame stability (five-run majority vote per run)

| Frame | Human | V6d (5 runs) | V6c plurality (5 hist. runs) | Note |
|-------|-------|--------------|-------------------------------|------|
| **f941** | `other` | `other` ×5 | `bowlers_end` (plurality) | V6d meets P2. |
| **f205** | `side_on` | `closeup` ×5 | `closeup` | P3 preserved. |
| **f748** | `side_on` | **`bowlers_end` ×5** | `closeup` (3/5 modal) | **Regression vs V6c** on this anchor. |
| **f942** | `other` | `bowlers_end` ×5 | `bowlers_end` (plurality) | No improvement vs V6c plurality; not PRIMARY. |

---

## §6 Aggregate metrics

**Per-run net accuracy (V6d):** 27, 27, 26, 27, 27 — **median 27**, **min 26**, **max 27**.  
**Per-run strict `bowlers_end` precision:** **35.7%** (**5 / 14** TP on **14** emitted) — **constant** across runs.  
**Internal cam flip rate:** **0% – 7.3%** per run — **mean 3.9%** (**well below** V5 **7.3%** on this ensemble).

**Compared to V6c five-run ensemble:** median net **+8** frames (**27 vs 19**); migration hash count **2 vs 4**; **`f941`** **`other`** unanimous vs mixed V6c **`bowlers_end`/`closeup`**.

---

## §7 Decision

- **Classification:** **V6d meets all PRIMARY acceptance criteria (§8)** on this **K=5** corpus_v1 ensemble.
- **§8 decision matrix row:** **All PRIMARY hit**, and **SECONDARY** items **S1** (net **≥ 21**), **S4** (BE prec **≥ 33.3%**), **S5** (flip **≤ 7.3%**) **also** hold. **S2** (**`f748`** → `closeup`) and **S3** (**`f942`** not `bowlers_end`) **do not**.
- **Disposition:** **Ship-candidate** — proceed under **combined-corpus / production-distribution gating** (`scout_v6c_shadow_run_scoping.md`, backlog **M‑2**), **not** blind paste into `vision.py`.

---

## §8 Recommended next steps

1. **Human / strategy review of `f748`:** confirm whether reverting side_on-adjacent remediation is acceptable vs **`f941`** win and global net lift.
2. **Optional V6e / targeted tweak:** if **`f748`** must recover **`closeup`** without losing **`f941`**, treat as a **narrow second lever** (outside this session per design §8 if PRIMARY had failed — PRIMARY did not fail, so this is **product prioritisation**, not session-gate).
3. **Run combined-corpus shadow** only after **sampler M‑2** enforcement (unchanged backlog prerequisite).
4. **Keep `groq_*` metadata** on future runs for parity with determinism methodology.

---

## §9 Limitations

- **N=41**, **K=5** — variance bands exist; **`f748`** unanimity suggests structural shift, not luck, but still one frame.
- **`V6d` net uplift** (**27 / 41**) is large vs **`V6c`** — merits **distribution retest** before production trust.
- **No** edits to **`vision.py`** in this session — prompts remain **`shadow_eval` only**.

---

## Cross references

| Path | Role |
|------|------|
| `files/docs/scout_v6d_ensemble_analysis_autogen.md` | Five-run aggregates |
| `files/shadow_eval/variants.py` | **`PROMPT_V6D`** implementation |
| `files/docs/scout_v6d_design.md` | Hypotheses + acceptance |

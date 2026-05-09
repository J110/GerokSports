# Scout V6c first shadow run — results (corpus_v1, 41 frames)

**Date:** 2026-04-30  
**Scope:** Offline shadow only (production `files/eyes/vision.py` unchanged).

---

## §1 Executive summary

- **Run completed:** 2026-04-30, **41-frame** corpus (`files/docs/scout_corpus_v1.json`), **`V6c` only**, **3** replicates per frame → **`123`** Groq calls, **wall-clock ~107s**, **errors: 0** (no timeout / HTTP failures in captured `error` field).
- **Output:** `files/docs/shadow_run_v6c_20260430_140220.json` (timestamped bucket for collision avoidance with `shadow_run_v1.json`).
- **Headline vs V5 (majority vote, same corpus):**

| Metric (from merged analysis — see §2) | V5 | V6c (this run) | Δ |
|----------------------------------------|----|----------------|---|
| Strict `bowlers_end` precision (emissions with label `bowlers_end`) | 31.2% (16) | 33.3% (15) | **+2.1 pp** (matches 2026-04-25 doc headline) |
| Coverage-weighted precision | 36.2% | 37.0% | **+0.8 pp** |
| **Net frame accuracy** (vote_cam == human label, N=41) | **20/41** | **19/41** | **−1 frame** (**regression**) |
| **Cam replicate flip rate** (variance across 3 reps / frame) | **7.3%** | **14.6%** | **+7.3 pp** (material **unstable** vs prior art; see §6) |

- **Recommendation:** Treat this run as **mixed / cautious**, **not** a clean endorsement to ship **`V6c`** to **`SCOUT_PROMPT`** yet. **`bowlers_end` precision nominally improves** versus **V5** on headline strict precision, aligning with **`docs/scout_v6c_shadow_run_corpus_v1_2026-04-25.md`**, but **this execution shows (a) worse net labeling accuracy**, **(b) doubled flip-rate instability**, **(c) persistent `f941`-class concern** (**`other`** human → **`bowlers_end`** vote). **Next moves:** reconcile flip-rate divergence against the archived 2026-04-25 JSON (determinism / provider drift), rerun V6c with repeatability probes if needed; **combined-corpus expansion** remains **conditionally valuable** **only after** flip + **f941** watch-list reconciliation — **sampler M-2** bucket coverage unchanged in urgency (still required before trusting stratified expansions).

---

## §2 Run details

| Item | Value |
|------|--------|
| **Corpus** | `files/docs/scout_corpus_v1.json` (metadata `v1.1`, **41** frame records) |
| **V6c raw output** | `files/docs/shadow_run_v6c_20260430_140220.json` |
| **V5 baseline shadow rows** | `files/docs/shadow_run_v1.json` (immutable reference; **`V6c` rows substituted** logically by timestamped overlay per `analyze.merge_shadow_overlay`) |
| **Model** | `meta-llama/llama-4-scout-17b-16e-instruct` (matches `shadow_eval/run_shadow.py` `MODEL` constant and `eyes/config.py` `GROQ_PRIMARY_MODEL`) |
| **Harness** | `files/shadow_eval/run_shadow.py` with **`--variants V6c --output docs/shadow_run_v6c_20260430_140220.json --corpus docs/scout_corpus_v1.json --resume`** (Commit 1 path flags) |
| **Failures** | **0 / 123** (`error` field empty across results) → **within S2.3 “&lt;10% failure” guard** |

**Structural parity:** Set equality of JSON row keys versus a **`V5`** row sampled from **`shadow_run_v1.json`** — **passed** (**S2.4** satisfied).

---

## §3 Per-field / per-signal outcomes

### 3.1 `camera_view` (canonical, majority vote)

Full tables for **V0**, **V5**, **V6c** alongside merged **984-row** shadow assembly are machine-generated:

- **`files/docs/scout_v6c_first_shadow_analysis_autogen.md`**

Abbreviated excerpts (consistent with corpus narrative):

**Strict precision (fraction of emitted tag X equal to human X):**

| Label | V5 | V6c |
|-------|-----|-----|
| `bowlers_end` | 31.2% | 33.3% |
| `closeup` | 62.5% | 55.6% |
| `graphic` | 42.9% | 42.9% |

**Recall on human **`bowlers_end`** (floor N=5 in this corpus):** **100%** for **both V5** and **V6c** (no regression on labeled BE positives).

### 3.2 `frame_phase` (canonical)

Harness stores phases; **`analyze.py`** table 8 shows phase agreement on BE–TP overlaps. **Important:** Corpus narrative states **phase is not a ship criterion for V6c** (STEP-1 `between_play` attractor persists). Treat phase deltas as **separate backlog** item.

### 3.3 Strip text (`STRIP:`), `has_strip`, `has_overlay_stats`

**Not scored in this toolchain:** `shadow_eval/run_shadow.py` persists only **`raw_first_200`**, not deterministic parse parity vs human for strip OCR or booleans (**§6 limitations**). Do **not** infer strip or overlay regressions/progress here.

---

## §4 Notable cases (vote migrations vs 2026-04-25 narrative)

Compared **majority_vote(`canon_camera_view`) V5 ↔ V6c** merged from **`shadow_run_v1.json`** + fresh **`shadow_run_v6c_*.json`**:

| Frame | Human `camera_view` | V5 vote | V6c vote |
|-------|---------------------|---------|---------|
| **f748** | `side_on` | `bowlers_end` | **`bowlers_end`** (no improvement vs **V6c** hypothesis in this rerun) |
| **f205** | `side_on` | `bowlers_end` | **`closeup`** (maps to intended “boundary closeup vs BE” remediation) |
| **f941** | `other` | `closeup` | **`bowlers_end`** (**operational‑severity escalation** versus closeup‑FP watch item in corpus doc) |
| **f942** | `other` | `bowlers_end` | **`closeup`** |
| **f020** | `other` | `graphic` | **`closeup`** |
| **f022** | `other` | `other` | **`graphic`** |

Compared to **`docs/scout_v6c_shadow_run_corpus_v1_2026-04-25.md` per-frame roster** (four listed migrations centered on **`f748`/`f205`/`f941`/`f020`**) **this rerun diverges materially on `f748` (still stuck `bowlers_end`)** **and expands additional migrations (`f942`, `f022`)**, underscoring **non-stationarity or provider variance** assumptions.

---

## §5 Recommendation

1. **Do not declare V6c “ready to paste into `vision.py`” solely from camera precision uptick.** Net accuracy and flip-rate degraded vs **V5** in **this dated execution**.
2. **Invest before combined corpus spend:** replicate **two** successive **V6c** shadows (same corpus, disjoint output files) comparing **migration hash + flip-rate** distributions; escalate if divergence remains.
3. **Combined corpus expansion:** retain on roadmap **conditionally** — **sampler M-2 enforcement** prerequisite unchanged (`files/docs/backlog.md` infra notes); treat **combined run** as **distribution test**, not blocker for reconciling rerun stability.
4. **If stability returns to 2026-04-25 profile:** revive positive reading of **f205** remediation and reconsider ship bands from **`scout_v6c_shadow_run_corpus_v1_2026-04-25.md` §Verdict**.
5. **Otherwise:** classify **prompt-only V6c** iteration as **paused** pending either **engineering controls** on inference determinism exploration or **`V6d`** hypotheses (out of explicit scope).

---

## §6 Limitations

- **Corpus lineage:** principally **RCB–GT-derived** **`scout_corpus_v1`** — lacks **MI–SRH / PBKS–RR** contemporaneous broadcasts named in scouting docs.
- **N=41** → limited statistical inferential strength.
- **`shadow_run_v1.json` V6c archival rows** coexist with refreshed timestamped runs; **`merge_shadow_overlay`** ensures analysis rows come from freshest overlay artifact but **historic rows remain in baseline file**.
- **`has_overlay_stats`/strip fidelity** unseen at evaluation layer (see §3.3).

---

## §7 Cross references

| Path | Purpose |
|------|---------|
| `files/docs/investigations/scout_codebase_discovery.md` | Harness + codebase map |
| `files/docs/investigations/scout_v6c_shadow_run_scoping.md` | Phase / promotion framing |
| `files/docs/scout_v6c_shadow_run_corpus_v1_2026-04-25.md` | Prior corpus-only narrative benchmarks |
| `files/docs/scout_v6c_first_shadow_analysis_autogen.md` | Automated markdown mirror of **`analyze.run_analysis`** headline tables |

---

**Run command echoes (historical fidelity):**

```bash
python3 shadow_eval/run_shadow.py \
  --variants V6c \
  --output docs/shadow_run_v6c_20260430_140220.json \
  --corpus docs/scout_corpus_v1.json \
  --resume

python3 shadow_eval/analyze.py \
  --shadow docs/shadow_run_v6c_20260430_140220.json \
  --baseline-shadow docs/shadow_run_v1.json \
  --variants V5,V6c \
  --out-md docs/scout_v6c_first_shadow_analysis_autogen.md
```

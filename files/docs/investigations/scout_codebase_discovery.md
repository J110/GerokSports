# Scout codebase discovery (V6c shadow run scoping prep)

Discovery session: **2026-04-30**. Goal: factual baseline for a future **V6c combined-corpus shadow run** scoping document. No architecture or implementation here.

References use repository-root paths as in the workspace.

---

## 1. Executive summary

| Topic | Finding |
|-------|---------|
| **Scout codebase location** | No separate **`scout/`** or **`eyes-extractor/`** repo or directory appears under **`/Users/anmolmohan/Projects/`** sibling projects (**Gamolution**, **bliss**, **flutter_app**, **graphify**) or **`SportsComm`**. Scout-related behavior lives **inside SportsComm**, primarily **`files/eyes/`** (vision layer) calling Groq's **Llama 4 Scout 17B** instruct model via **`AsyncGroq`**. Colloquially "Scout" = that model plus the **`SCOUT_PROMPT`** contract in **`files/eyes/vision.py`**. |
| **Current production Scout "version"** | **Model:** `meta-llama/llama-4-scout-17b-16e-instruct` in **`files/eyes/config.py`** (**`GROQ_PRIMARY_MODEL`**, approximately lines 15–16). **Prompt lineage:** Comments and **`files/shadow_eval/variants.py`** treat **`SCOUT_PROMPT`** in **`vision.py`** as the **V5**-class production prompt (see **`vision.py`** header and comment block circa lines 61–82). **`V6c` is defined as a prompt variant**, not a different upstream repo — see **`VARIANTS["V6c"]`** in **`files/shadow_eval/variants.py`** (approximately lines 416–477). Corpus doc states V6c is **not yet shipped** to **`vision.py`** (see **`files/docs/scout_v6c_shadow_run_corpus_v1_2026-04-25.md`**, ship paragraph near end). |
| **V6c references** | Present in-repo: **`files/shadow_eval/variants.py`**, **`files/shadow_eval/analyze.py`** (variant list), **`files/docs/scout_v6c_shadow_run_corpus_v1_2026-04-25.md`**, **`files/docs/scout_shadow_run_v1_analysis.md`**, **`files/docs/backlog.md`**, and comments in **`files/eyes/vision.py`**. No hits from a quick search of sibling project trees for `v6c` / `V6c` (empty). |
| **Pipeline–Scout integration** | **Direct import:** **`from eyes.vision import Vision`** in **`files/test_pipeline.py`** (import near line 26; **`Vision()`** circa line 5235). **Invocation:** async **`Vision.describe()`** (**`files/eyes/vision.py`**, class **`Vision`** circa lines 218–380) performs one Groq multimodal call (**`_scout_call`**) and returns **`(frame_type, description, action_description)`** with side effects on **`last_camera_view`**, **`last_frame_phase`**, **`last_strip_flag`**, **`last_overlay_flag`**, etc. **Not** subprocess, **not** separate HTTP service for the main path (Groq client in-process). |
| **Readiness for next-session scoping** | **Sufficient in-repo context exists** to scope *shadow-run mechanics* (corpus JSON, frame snapshots, **`run_shadow.py`** harness, **`variants.py`**). **Remaining gaps** are operational (what "combined corpus" paths are, bucket-coverage enforcement, pass-2 / prod-eval archival) — partially documented in **`scout_v6c_shadow_run_corpus_v1_2026-04-25.md`** and **`backlog.md`**, not in a single executor checklist. |

---

## 2. Scout codebase

### 2.1 Location

- **Sibling directories** (`ls -la /Users/anmolmohan/Projects/`): **Gamolution**, **SportsComm**, **bliss**, **flutter_app**, **graphify** — **no** directory named `scout`, `vision`, or `extractor` at that level.
- **SportsComm root** (`ls -la`): **no** top-level **`scout/`** directory; **`files/`**, **`scorecard-ui/`**, **`logs/`**, etc. as expected.

### 2.2 What “Scout” is in this repository

Implementation is **`files/eyes/vision.py`**:

```1:7:files/eyes/vision.py
"""Vision — Single-provider Scout 17B cricket stream watcher.

Scout 17B (Groq): ONE call does tag + read.
  max_tokens=600, ~1.0s, $0.09/match.
  Outputs a 3-boolean classification line, then reads the strip.

Returns (frame_type, description, action_description).
```

Key surface:

- **`SCOUT_PROMPT`**: large f-string template (classification JSON on first line + strip + overlays + action); begins circa line 83.
- **`Vision`**: main class (**`describe`**, **`_scout_call`**, **`_parse_tag`**, normalization).

### 2.3 Is `files/eyes/` “the Scout codebase”?

**Yes, for SportsComm.** The vision package (`vision.py`, `scoreboard.py`, `main.py`, etc.) is the consumer-facing “extractor”: it performs the Groq Scout call and parsing. **It is not a second repository** branded Scout; naming refers to **Meta's Llama 4 Scout** model hosted on Groq.

---

## 3. Current Scout version

### 3.1 Model ID (upstream “binary” version)

```9:16:files/eyes/config.py
# Groq Scout 17B — sole vision provider: tags + reads in one call
# ~1.0s per frame, $0.09/match
GROQ_API_KEY = os.environ.get(
    "GROQ_API_KEY",
    "<REDACTED — read from GROQ_API_KEY env var>",
)
GROQ_PRIMARY_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
GROQ_FALLBACK_MODEL = "llama-3.1-8b-instant"
```

**Configurable?** **`GROQ_PRIMARY_MODEL`** is a **constant** here (not **`os.environ`**-driven unlike some other keys). Changing production model means editing **`config.py`** (no separate `scout_version` key found).

### 3.2 Prompt “versions” (V1 … V6c)

- Shadow evaluation defines **`VARIANTS`** in **`files/shadow_eval/variants.py`** with keys **`V1`** … **`V5`**, **`V6c`** (**`VARIANTS` dict** circa lines **469–477**).
- **`shadow_eval/run_shadow.py`** uses **`MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"`** (line **42**) and compares prompt variants, not separate codebases.

### 3.3 Configuration files mentioning `scout` + version

- **`rg "scout_version|SCOUT_VERSION"`** and **`PROD_VERSION|prod_version`** over **`files/`**: **no** matches beyond unrelated graphify caches (not summarized here).

---

## 4. V6c specifics

### 4.1 Where V6c is defined (code)

**`files/shadow_eval/variants.py`** (comments and strings approximately **417–477**):

- **V6c** = **`PROMPT_V5`** with the **STEP-1 closeup bullet** replaced (`_V5_CLOSEUP_EXAMPLE` → **`_V6C_CLOSEUP_EXAMPLE`**), then **`PROMPT_V6C = PROMPT_V5.replace(...)`**.
- Explicit comment intent: discriminate **bowlers_end** vs **closeup** when geometry is ambiguous (pitch not receding vs face dominant).

### 4.2 Where V6c is documented

- **`files/docs/scout_v6c_shadow_run_corpus_v1_2026-04-25.md`**: corpus_v1 **regression filter** (Step 2); criteria vs V5; notes **combined-corpus shadow run** as next step; mentions **Pass-2 async** and **`debug_frames/`** archival incident (**lines 11–17** in the read sample).
- **`files/docs/backlog.md`**: extensive cross-links (filters, urgency, sampler, side_on, combined corpus).
- **`files/docs/scout_shadow_run_v1_analysis.md`**: analysis output for **`shadow_run_v1.json`** (referenced from **`files/shadow_eval/analyze.py`**, **`OUT_MD`** circa line **32**).

### 4.3 Sibling workspaces

Quick **`rg`** for **`v6c|V6c|V6C`** across **Gamolution / flutter_app / graphify / bliss**: **no** paths returned in this environment (finding: **no** V6c string outside SportsComm among those dirs).

### 4.4 Inferred nature of V6c (labeled inference)

Based **only** on **`variants.py`** comments and corpus doc:

- **Inference:** V6c is a **prompt-only** delta on the **V5** three-example **`STEP 1`** block, preserving structure so the shadow harness can compare like-for-like against **V5** on frozen frames — **not** a new neural checkpoint or repository.

---

## 5. Pipeline–Scout integration

### 5.1 How the pipeline invokes Scout

- **Mechanism:** **In-process async** **`groq.AsyncGroq.chat.completions.create`** from **`Vision._scout_call`** (**`files/eyes/vision.py`**, traceback from grep; **`_scout_call`** around lines **466+** below **`describe`**).
- **tests / pipeline entry:** **`files/test_pipeline.py`** imports **`Vision`** and constructs **`vision = Vision()`** (approximately line **5235**).

Not observed as primary path here: **`subprocess`** to Scout, separate microservice Scout server, or message queue — the hot path is **Groq API** from **`vision.py`**.

### 5.2 Scout output shape (contract)

First line: **JSON object** with fields such as **`has_strip`**, **`has_overlay_stats`**, **`drs_review`**, **`camera_view`**, **`frame_phase`**, **`ball_position`** (**`SCOUT_PROMPT`** exemplars **`vision.py`** circa lines **92–136**).

**`Vision.describe`** returns **`(frame_type, description, action_description)`** and sets:

- **`last_camera_view`**, **`last_frame_phase`**, **`last_ball_position`**
- **`last_strip_flag`** / **`last_overlay_flag`** (from tag **`has_strip`**, **`has_overlay_stats`** — see assignment block circa **`vision.py` lines 347–353**).

### 5.3 Downstream parsing in **`test_pipeline.py`**

- **`extract_broadcast_data(scout_text: str, ...)`** (**circa lines 1321+** per grep summary): regex extraction from **Scout’s raw strip text**.
- **`_parse_this_over_from_scout`** (**circa line 1266**): pulls **THIS OVER** from Scout text.

### 5.4 Critical fields tied to backlog / Thread 7

- **`has_overlay_stats`** — documented pipeline use (e.g. **G2** path, **`test_pipeline.py`** comments circa **167–189** in grep hits); **`vision.py`** prompt definition **circa 104–107**.
- **`camera_view`** / **`frame_phase`** — cadence, dead-time, BallAnalyzer tagging (**`vision.py`** **`describe`** docstring and **`test_pipeline.py`** scout gate comments circa **854–962** region).

---

## 6. Existing Scout-related work

### 6.1 Prior investigations **`files/docs/investigations/`**

- **`thread7_rediagnosis_multi_ball_gap.md`** — INDEX cites `"scout" OCR`; strip-level diagnosis.
- **`thread7_fix2_cam_graphic_fast_path_design.md`** — extensive **Scout** tag/strip **`has_strip`**, **`has_overlay_stats`**, **`cam=graphic`** design (many cross-refs **`files/eyes/vision.py`**, **`test_pipeline.py`**).
- **`INDEX.md`** (2026-04-30) listed **21** markdown files — **before** this document.

### 6.2 No dedicated Scout-codebase exploration doc existed

This file (**`scout_codebase_discovery.md`**) is the first **investigations/** entry whose purpose is **Scout locality + shadow-run surface** enumeration.

### 6.3 Backlog

**`files/docs/backlog.md`** aggregates **scout-side** backlog (V6c shadow run, phase regression, **side_on** canary — see hygiene snapshot line in header region and later V6c / combined-corpus blocks). Detailed scope exceeds this discovery; keywords are indexed for next session.

---

## 7. Shadow run infrastructure

### 7.1 Tools

| Asset | Role |
|-------|------|
| **`files/shadow_eval/run_shadow.py`** | Loads **`files/docs/scout_corpus_v1.json`**, encodes JPEGs, runs **Groq** with **`VARIANTS`**, writes **`files/docs/shadow_run_v1.json`**, **`--variants`** filter (**lines 251–261** docstring/help). Timeout **7.0s**, retry on **429** (**lines 94–139** region). |
| **`files/shadow_eval/analyze.py`** | Builds **`files/docs/scout_shadow_run_v1_analysis.md`** from corpus + **`shadow_run_v1.json`**. Variant list includes **`V6c`** (**`analyze.py`**, variant list circa line **171** in grep). |
| **`files/shadow_eval/frame_diff.py`** | Reads **`shadow_run_v1.json`** (grep hit). |

### 7.2 Corpus artifacts

- **`files/docs/scout_corpus_v1.json`** — frame list (**`run_shadow.py`**, **`CORPUS`** line **38**).
- **`files/docs/corpus_frames_v1/`** — **41 JPEG snapshots** referenced by harness (**`FRAMES_DIR`** in **`run_shadow.py`**, line **40**); directory exists with **`f*_scoreboard.jpg`** style names (spot-check **`ls`** 2026-04-30).
- **`files/docs/shadow_run_v1.json`** — machine output (**`shadow_eval`**).
- Auxiliary: **`files/select_corpus_candidates.py`**, **`files/replay_corpus_builder.py`**, **`files/corpus_candidates.json`**, **`files/docs/corpus_frame_inventory.json`** (glob discovery).

### 7.3 Comparison framework

**`analyze.py`** implements majority vote across replicates, per-variant precision/recall vs human labels in corpus (**module docstring lines 1–12**).

### 7.4 “Combined-corpus shadow run” (in-repo text only)

Referenced in **`scout_v6c_shadow_run_corpus_v1_2026-04-25.md`** and **`backlog.md`** as **corpus_v1 + freshly relabeled prod-eval** frames. **Concrete path list / builder invocation** for the combined corpus is **not fully centralized** in one code pointer from this sweep — treat as **open operational detail** for scoping.

---

## 8. Gaps for V6c combined-corpus shadow run scoping

### 8.1 Known

- V6c prompt delta location (**`variants.py`**).
- Shadow harness (**`run_shadow.py`**) and analysis (**`analyze.py`**).
- Baseline corpuses and **`corpus_frames_v1`** snapshot dir.
- Production uses **`Vision`** plus **`SCOUT_PROMPT`** (V5-class) in **`vision.py`**; corpus doc explicitly says **V6c not merged** until ship decision (**`scout_v6c`** doc conclusion section).

### 8.2 Unknown / need confirmation next session or from operator

- **Exact artifact layout** for “combined corpus” **after** archival fixes (paths, labeling JSON schema, overlap with corpus_v1.1 schema).
- **Bucket-coverage enforcement** mentioned in backlog (avoid under-sampling) — requirement level and implementation owner (pipeline vs scout batch job).
- **Pass-2 async** interplay with shadow sampling (referenced in **`scout_v6c`** doc as historical context — whether any **constraints remain** today).
- **side_on canary**: backlog **`backlog.md`** section **### P1: Scout never emits `side_on`** (**circa lines 6384+**) — orthogonal prompt-roadmap item vs V6c closeup edit.

### 8.3 Questions for Anmol (if scout context spans tools not in repo)

1. Does **combined-corpus** mean a **specific script** invocation or a **hand-assembled JSON** merging two corpora — and where should the authoritative frame list live?
2. Will V6c combined-corpus run **only** **`run_shadow.py --variants V6c`** (plus whichever baseline deltas are needed), or is a **`vision.py`** merge **in scope for the same release train**?

---

## 9. Recommended next step

**Proceed to write the V6c combined-corpus shadow run scoping document in a follow-on session**, using **`files/shadow_eval/*`**, **`files/docs/scout_v6c_shadow_run_corpus_v1_2026-04-25.md`**, **`backlog.md`**, **`vision.py`** + **`variants.py`** as primary citations.

No separate Scout repository was found — **scout-side work means prompt + harness + corpus ops inside this repo** (plus Groq account limits), unless new remote context appears.

If **`combined corpus`** tooling is still partly tribal knowledge, dedicate the first chunk of scoping to **frozen inputs** (path list + human-label columns + success metrics) — the repo already proves **negative finding**: uncertainty is operational, **not** “missing Scout source tree.”

---

## Appendix: Stop-and-route conditions (from briefing)

| ID | Applies? |
|----|----------|
| **S1** Multi-repo split | **No** — Scout implementation is **localized** (`files/eyes/`, **`shadow_eval/`**). Gamolution **etc.** showed **no** Scout duplication in string search for V6c. |
| **S2** V6c semantics need human lore | **Partially** — **Code + `variants.py`** comments define V6c; **combined corpus** procedural meaning still merges doc + backlog narrative. |
| **S3** Work outside workspace | **No** — primary engineering artifacts are **here**; external dependency is **Groq API**, not unseen Scout codebase. |

---

*End of discovery document.*

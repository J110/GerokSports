# Session summary — 2026-04-24

Part B (Scout prompt tightening) shipped.  Project state snapshot,
future improvements, production monitoring checklist.

---

## 1. What we did today

### Part B: Scout prompt V5 + V1 alias re-point

The whole day was a single focused workstream: investigate and fix
Scout's `camera_view` taxonomy collapse, where the multimodal LLM
was emitting `bowlers_end` on ~83% of frames regardless of actual
content.  Target: ≥90% strict precision on `camera_view`.

**Step-by-step:**

1. **Corpus build (stratified grep-based, 41 frames).**
   Script: `build_frame_inventory.py` parsed RC9 logs to identify
   Scout records + ball events; `select_corpus_candidates.py`
   selected frames into three stratified subsets targeting specific
   failure modes:
   - Subset 1: batter closeups with pitch in background (wicket
     reactions, over transitions)
   - Subset 2: disambiguation candidates (between-play closeups)
   - Subset 3: delivery-context frames (action-phase controls)

2. **Rubric v1.1.**
   `docs/scout_labeling_rubric_v1.md` refined with:
   - Clarification: persistent broadcaster overlays covering >30%
     of frame qualify as `graphic` even with live action visible in
     the remainder.
   - New EC-6: wide elevated shots with pitch off-axis are
     `side_on`, not `bowlers_end` (consumer-alignment rationale —
     DWR opening a window on such a frame would cut a broken clip).
   - Note: interview frames with sponsor/logo backgrounds are
     `closeup`, not `graphic` (the subject is a person).

3. **Labeling + low-confidence review.**
   41 frames hand-labeled.  6 medium-confidence frames surfaced for
   review; user confirmed 5 as-labeled, flipped F175 from
   `bowlers_end` → `graphic`.  Corpus frozen at v1.1.

4. **Baseline audit — taxonomy collapse confirmed.**
   - V0 (live Scout) `bowlers_end` strict precision: **15.2% (5/33)**
     — much lower than the ~50% estimate from Part A spot-checks.
   - V0 `closeup` and `graphic` precision: **100%** — Scout knows
     the non-default categories; it just doesn't use them.
   - A3 audit of 5 production sessions: zero emissions of
     `wide_shot` or `wide` aliases, so the V1 alias re-point is
     defensive hygiene with no observable traffic impact.

5. **Prompt variant ladder (cumulative, V1 → V5).**
   - **V1:** alias re-point only (`wide_shot`/`wide` → `side_on`),
     prompt unchanged.
   - **V2a:** V1 + harden `bowlers_end` / `release` / `flight` /
     `shot` with "pitch extends away from the camera" gates.
   - **V2b:** V2a + broaden `closeup` (face/body dominant even with
     pitch in background).
   - **V3:** V2b + explicit disambiguation block ("these frames are
     NEVER `bowlers_end`: batter close-up at striker's end, …").
   - **V4 (diagnostic):** swap STEP 1 example camera_view from
     `"bowlers_end"` → `"other"` as a single-character falsifiable
     test.  Rulebook unchanged.
   - **V4b:** V2a rulebook + V4 neutral example.
   - **V5 (winner):** V2b rulebook + three-example STEP 1 block
     (bowlers_end / closeup / graphic) with explicit "DO NOT copy
     the values" instruction.

6. **Shadow run.**
   41 frames × 7 variants × 3 replicates = **861 Groq calls** at
   `temperature=0` against `meta-llama/llama-4-scout-17b-16e-instruct`.
   Harness: `files/shadow_eval/run_shadow.py` (with retry + rate
   limit backoff).  Corpus frames snapshotted to
   `docs/corpus_frames_v1/` so the run is fully reproducible.

7. **Key finding — the example is the control surface, not the rulebook.**
   V1–V3 all produced the same output distribution as V0
   (`bowlers_end` strict precision ±1pp from baseline).  V4's
   single-character swap caused Scout to emit `"other"` on 36/41
   frames.  **The rulebook was being ignored; the STEP 1 example was
   the sole lever.**  This is the key insight of the day — future
   Scout iterations should start by interrogating the example block,
   not rewriting prose.

8. **V5 results (Pareto improvement over V0).**

   | Metric | V0 | V5 | Δ |
   |---|---|---|---|
   | `bowlers_end` strict precision | 15.2% (5/33) | **31.2%** (5/16) | +16.0pp (2.05×) |
   | `bowlers_end` recall (human N=5) | 100% | **100%** | unchanged |
   | `closeup` recall (human N=12) | 50% | **83.3%** | +33.3pp |
   | `graphic` recall (human N=7) | 28.6% | **42.9%** | +14.3pp |
   | Coverage-weighted precision | 28.2% | **36.2%** | +8.0pp |
   | Truth-improving frame shifts | — | **7** | — |
   | Regressions | — | **0** | — |

9. **Shipped.**
   - `files/eyes/vision.py` `SCOUT_PROMPT` → V5 (byte-identical to
     shadow-harness `PROMPT_V5`, 6783 chars).
   - `files/eyes/vision.py` `_CAMERA_VIEW_ALIASES` → V1 re-point
     (`wide_shot` / `wide` → `side_on`).
   - `files/docs/backlog.md` created with phase regression,
     precision ceiling + escalation paths, and infrastructure items.
   - No git repo in the project, so the bundle lives in the working
     tree.  Initialize git + commit whenever convenient.

---

## 2. Where the project stands today

### Shipped & validated

| Workstream | Status | Evidence |
|---|---|---|
| Fix #1 BAT-PHYSICS | Shipped, validated | (prior sessions) |
| Commentary cluster (Fix 2+3+1) | Shipped, validated | (prior sessions) |
| P0-2 through P1-5 cluster | Shipped, validated | (prior sessions) |
| Part A (RC-7 DWR phase gate) | Shipped, validated | (prior sessions) |

### Shipped today, pending production validation

| Workstream | Status | Evidence |
|---|---|---|
| Part B — Scout prompt V5 | Shipped (working tree) | `docs/scout_shadow_run_v1_analysis.md` |
| V1 alias re-point (`wide_shot`/`wide` → `side_on`) | Bundled with V5 | same |

### Queued (not blocked)

- **RC-1 / RC-2 corpus building.**
- **L2 re-bakeoff** on clips from Part A + Part B DWR output.
- **Step 1 / Step 2 densification decision** — blocked on L2
  re-bakeoff.

### Artifacts produced today

```
files/docs/scout_corpus_v1.json                 (41 frames, v1.1)
files/docs/corpus_frames_v1/*.jpg               (snapshotted frames)
files/docs/scout_labeling_rubric_v1.md          (rubric v1.1)
files/docs/scout_corpus_v1_low_confidence.md    (review log)
files/docs/scout_shadow_run_v1_analysis.md      (full analysis)
files/docs/shadow_run_v1.json                   (861 call raws)
files/docs/backlog.md                           (new)
files/shadow_eval/variants.py                   (V1–V5 prompt defs)
files/shadow_eval/run_shadow.py                 (harness)
files/shadow_eval/analyze.py                    (metrics + report)
files/shadow_eval/frame_diff.py                 (variant-pair diff)
files/build_frame_inventory.py                  (corpus tooling)
files/select_corpus_candidates.py               (stratified selector)
```

---

## 3. Future improvements

Everything below is captured in `files/docs/backlog.md` with
priority + size estimates.  Summary here for planning.

### P1 — Part B follow-ups

**Phase regression from V5.**  V5's closeup example uses
`"frame_phase": "between_play"`, which bleeds into delivery-context
frames.  Frame-phase emission on bowlers_end true positives dropped
from 2/5 (V0) → 0/5 (V5) in the shadow run.  Acceptable short-term
(DWR uses `camera_view` primarily, phase precision was already 40%,
Part A has fallback handling), but worth fixing with a fourth
delivery-context example or by removing phase from examples entirely.
~30–45 min prompt iteration + mini shadow run.

**Precision ceiling (31.2% `bowlers_end`).**  V5 cannot reach ≥90%
via prompt engineering on `llama-4-scout-17b-16e-instruct`.  The 11
remaining false positives are frames where pitch-receding geometry
is genuinely visible even though consumer-alignment requires a
different label.  Three escalation paths, in cost order:

1. **Temperature > 0 with majority-vote ensembling.**  Cheapest.
   Run Scout 3× at t=0.3 per frame and take the mode.  Worth testing
   before anything else.
2. **Post-hoc verification layer.**  Second cheap call confirms
   pitch-axis geometry on bowlers_end-tagged frames.  Adds latency.
3. **Stronger vision model.**  `llama-4-maverick`, `gpt-5-vision`,
   or similar.  Highest expected quality lift, biggest operational
   cost.

Don't start any of these until production V5 behavior is observed
for ≥1 full session.  If downstream quality is acceptable at V5's
level, the escalations stay in backlog.

### P2 — Infrastructure

- **Debug frame archival** instead of deletion on pipeline startup
  (`test_pipeline.py:3715-3719` currently wipes `debug_frames/`).
  Archive to `debug_frames_archive/<timestamp>/` with a cap of the
  last 5 sessions.  ~15-30 min.  This blocked Part B corpus reuse
  and would block the phase-regression mini shadow run.
- **`CLOSEUP` frame persistence.**  `test_pipeline.py` has explicit
  `imwrite` for `SCOREBOARD` frames but not `CLOSEUP`.  Makes
  closeup misclassifications non-auditable after the fact.  ~5-10 min.

### P1/P2 — Pipeline behavior (from prior sessions, unchanged)

- **Bowler-change pickup latency** (~30-45s).  No analysis doc yet.
- **Element checker stale header cleanup.**  No analysis doc yet.
- **FOW placeholder upgrade mechanism.**  No analysis doc yet.

### Queued work

- **RC-1 / RC-2 corpus** — not blocked.
- **L2 re-bakeoff on post-B clips** — not blocked.
- **Step 1 / 2 densification decision** — blocked on L2 re-bakeoff.

---

## 4. Production monitoring — V5 validation checklist

Run when the pipeline comes back up tomorrow.

### Step 1: restart

Launch the full stack — pipeline + element checker + parity monitor
+ UI.  V5 prompt is already in `files/eyes/vision.py`; no code
changes needed at restart.

### Step 2: camera_view bucket distribution (30 min)

```bash
# After ~30 min of live play
grep -E '"camera_view":\s*"[^"]+"' logs/pipeline.log \
  | grep -oE '"camera_view":\s*"[^"]+"' \
  | sort | uniq -c | sort -rn
```

**Expected shift** vs V0 baseline (A3 audit: 83.8% `bowlers_end`,
13.5% `closeup`, 1.7% `graphic`, 0.9% `other`/`ad`, 0% `side_on`):

| Bucket | V0 share | V5 expected | Primary signal |
|---|---|---|---|
| `bowlers_end` | 83.8% | **40–55%** | ← biggest shift |
| `closeup` | 13.5% | **25–35%** | rises |
| `graphic` | 1.7% | **3–7%** | rises |
| `side_on` | 0% | **small but nonzero** | ← key qualitative signal |
| `other` / `ad` | 0.9% | ~stable | — |

**Pass:** shares land in the expected ranges and `side_on` becomes
non-zero.
**Fail:** `bowlers_end` stays >70% → pull 10-20 fresh frames,
re-run through V5 in the shadow harness to localize whether it's
LLM variance or broadcast-context drift.

### Step 3: downstream regression watch (~60 min of play)

- **DWR window selection.**  Are clips opening around real
  deliveries and closing correctly?  Any new failure mode?
- **XI-REJECT override.**  New rejection patterns?
- **AdaptiveSleep cadence.**  Is the reduced `bowlers_end` emission
  causing the sleeper to over-wait?
- **Parity monitor.**  Any new divergence between pipeline UI state
  and Cricbuzz ground truth tied to camera_view changes?
- **Commentary correctness.**  Spot-check 3-5 deliveries end-to-end
  — the V5 prompt affects what frames reach DWR, which affects
  commentary generation.

### Step 4: decision point after one full session

- **All green:** V5 stays, escalation tracks (temperature ensembling,
  post-hoc verification, stronger model) stay in backlog.
- **Downstream regression in a specific way:** pick the cheapest
  matching escalation from the backlog (temperature ensembling is
  first) and iterate.
- **Production distribution matches but downstream unaffected:**
  consider the phase-regression fix as the next Scout iteration.

---

## 5. Key insights worth remembering

1. **The example is the dominant control surface for this model,
   not the rulebook.**  V4's single-character example swap moved the
   output distribution more than the entire V2/V3 rulebook rewrite.
   Future Scout iterations should interrogate the example block
   first.

2. **Taxonomy collapse was worse than estimated.**  Part A
   spot-checks suggested ~50% baseline `bowlers_end` precision.
   Rigorous 41-frame labeling put it at **15.2%** — a 3× gap.
   Spot-checks are not a substitute for labeled corpora.

3. **Scout *knows* the non-default categories.**  100% precision on
   `closeup` and `graphic` at V0 proves Scout can identify them
   correctly when it emits them; it just defaults to `bowlers_end`
   instead of looking.  This is why the "break the default attractor"
   framing (balanced multi-example) beat every rulebook-hardening
   attempt.

4. **Rubric consumer-alignment matters more than visual similarity.**
   Elevated side shots with pitch visible off-axis look like
   bowlers_end but cannot support a delivery window downstream, so
   they must be labeled `side_on`.  Future rubric iterations should
   start from "what downstream decision does this label drive?"
   rather than "what does the frame look like?"

5. **A diagnostic experiment is worth more than a tightening
   attempt.**  V4 took one character to design and produced the
   insight that made V5 possible.  Any future prompt-tuning
   investigation should budget for at least one falsifiable
   diagnostic variant, not just a ladder of incremental tightenings.

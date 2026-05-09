# Scout V6c combined-corpus shadow run — execution scoping

**Date:** 2026-04-30  
**Type:** synthesis of existing docs + code traces (no new architecture invented here).  
**Prerequisites read:**  
`scout_codebase_discovery.md`,  
`scout_v6c_shadow_run_corpus_v1_2026-04-25.md`,  
`files/shadow_eval/variants.py`,  
`files/shadow_eval/run_shadow.py`,  
`files/eyes/vision.py` (through `Vision.describe`),  
`files/eyes/config.py`,  
backlog excerpts (V6c, Pass-2, sampler/M-2, `debug_frames`, side_on ~L6384),  
sample of `files/docs/shadow_run_v1.json`.

---

## §1 Executive summary

### Goal

Run a **combined-corpus shadow evaluation** comparing **V6c** versus **V5** (production-class prompt on the frozen frame set **corpus_v1 + newly captured prod-eval frames**) to make a **ship / no-ship / marginal** decision for promoting **V6c** into **`files/eyes/vision.py`** (`SCOUT_PROMPT`). This is explicitly the **ship/no-ship** step — the corpus_v1-only run was **Step 2** (regression filter), already passing per `scout_v6c_shadow_run_corpus_v1_2026-04-25.md`.

### Approach

1. Build or assemble a single **labeled JSON corpus** merging **existing `scout_corpus_v1`** frames (~41) with **~25 stratified prod-eval frames** (plan from corpus doc §“Verdict” / step 3: “65-ish-frame combined view”), plus **JPEG snapshots under `files/docs/corpus_frames_v1/`** (or equivalent naming convention) so `run_shadow.py` resolution (`FRAMES_DIR / path.name`, `run_shadow.py:147–148`) survives `debug_frames/` churn.
2. Run Groq **`meta-llama/llama-4-scout-17b-16e-instruct`** with **temperature 0**, **600 max tokens**, identical alias canonicalisation as **`shadow_eval/variants.py`**, **3 replicates** per (frame, variant), for **both V5 and V6c**.
3. Recompute headline metrics grounded in **`human_*` labels** plus **severity-weighted error analysis** documented in corpus doc (especially **f941-pattern**: non-cricket / `other` / `graphic` → `bowlers_end`).

### Predicted scope (order-of-magnitude)

| Workstream | Effort drivers | Estimate |
|------------|----------------|----------|
| **Corpus + labeling** | New match captures, stratified sampler, dual human review (`v1.2` rubric in plan), archival discipline | Dominant wall-clock (**hours–days**, operator-dependent); not automatable blindly |
| **Harness runs** | ~65 frames × 2 variants × 3 reps ≈ **390 API calls** if both variants run exclusively on merged set — often less if **`shadow_run_v1.json`** already retains V5 on corpus_v1 and only new tuples are appended | Wall-clock comparable to corpus_v1 solo V6c run (**~few minutes** scaled by Groq TPM; corpus doc cites **~142s** for **123** V6c-only calls — `scout_v6c_shadow_run_corpus_v1_2026-04-25.md:L43`). |
| **Analysis + write-up** | Extend or fork `analyze.py` logic vs fixed paths; regenerate markdown akin to **`scout_shadow_run_v1_analysis.md`**; apply backlog ship bands | ~1–2 engineering sessions |

**Production code churn for ship:** mechanically small — **`SCOUT_PROMPT`** in **`vision.py:83–214`** aligned to **`VARIANTS`** text (parity obligation documented in **`variants.py:67–71`** and **`variants.py:458–465`** for `{{`/`}}` vs `_unescape`). No separate LOC estimate for parity beyond careful copy-diff + sanity tests (execution session owns).

### Promotion path

As stated in corpus doc (**`scout_v6c_shadow_run_corpus_v1_2026-04-25.md:L191–194`**):

- **`bowlers_end` strict precision combined >40% → ship**
- **35–40% → marginal** → tie-break on net frame accuracy and **operational-severity FP** count (explicitly watch **f941-style** regressions — **same doc:L102–107, L202–211**).
- **&lt;35% or recall regresses → do not ship**; investigate **[V6a/V6b](narrative placeholders in corpus doc** — **`scout_v6c_shadow_run_corpus_v1_2026-04-25.md:L31`; no `PROMPT_V6a`/`V6b` in `variants.py` today** (**Stop-and-route S2 / S5** resolved: roadmap language only).

No staged rollout or A/B **Scout prompt** infra is documented in backlog for this repo; promotion is presented as **binary swap** in **`vision.py`** after shadow sign-off (**`scout_v6c_shadow_run_corpus_v1_2026-04-25.md:L196–198`**). Post-ship telemetry is qualitative (pipeline logs); **explicit percent-split A/B is out of scope** unless added as new work.

---

## §2 V6c hypothesis

### What changed vs V5 (and note on “V6” naming)

There is **no distinct `PROMPT_V6` object** checked into **`files/shadow_eval/variants.py`**. **`VARIANTS`** keys stop at **`V5`** and **`V6c`** (`variants.py:469–478`). Narrative **`V6` / “V6 work”** in **`backlog.md`** (~**L5427–5438**) describes **prompt + architectural follow-ups** broadly; **`V6c`** is one **enumerated prompt delta** atop **V5**.

**V6c vs V5 (code-diff truth):**

- **`PROMPT_V6C`** = **`PROMPT_V5.replace(_V5_CLOSEUP_EXAMPLE, _V6C_CLOSEUP_EXAMPLE)`** (**`variants.py:439–454`**).
- V5 STEP-1 **closeup** bullet (**production-mirrored narrative**): *“During a player closeup (face/body fills frame): … `camera_view: closeup`, `frame_phase: between_play`”* (**`_V5_CLOSEUP_EXAMPLE`**, **`variants.py:439–443`** — production template analogous lines **`vision.py:96–98`**).
- V6c rewrites scenario text to clarify **boundary geometry**:

```445:452:files/shadow_eval/variants.py
_V6C_CLOSEUP_EXAMPLE = (
    "- During a closeup of a player (face/upper body fills frame, "
    "no full pitch receding away even if camera angle is from "
    "bowler's end direction): "
    "{{\"has_strip\": true, \"has_overlay_stats\": false, "
    "\"drs_review\": false, \"camera_view\": \"closeup\", "
    "\"frame_phase\": \"between_play\", \"ball_position\": null}}"
)
```

Comments **`variants.py:416–436`** cite **production eval (DC vs PBKS, ~23 stratified BE frames)** — **34.8% strict precision**, **40%** of FP mass from **“bowlers_end-direction but pitch does NOT recede”** closeups; V5 closeup exemplar anchored only obvious face-fill cases.

### Which outputs V6c targets vs leaves unchanged

**Targets (primary):**

- **`camera_view`** taxonomy — shifting **ambiguous bowler-direction / non-receding-pitch** mass from **`bowlers_end` false positives** toward **`closeup`** (and **truth-aligning `side_on`** human labels where previously misclassified as BE).

**Inherited / not intentionally changed by text diff:**

- **JSON shape** (`has_strip`, `has_overlay_stats`, `drs_review`, `ball_position`) — untouched.
- **`frame_phase` STEP-1 example** still emits **`between_play`** for closeup (**`variants.py:451`**). Corpus doc confirms **phase precision on BE TPs is 0/5 V5=V6c** due to **STEP-1 example attractor**, and **explicitly excludes phase as V6c ship criterion** (**`scout_v6c_shadow_run_corpus_v1_2026-04-25.md:L127–168`**).
- **Strip / overlay text (STEP 2–4)** unchanged between variants → **character-level OCR regression is not hypothesized**, but residual **confidence / flip-rate** jitter may still correlate with tag-line confusion (watch **flip rate**, corpus doc:L212–214).

### Expected improvements vs non-regression

**Expected improvement:**

- Reduced **production-severe `bowlers_end` FPs** on **Pattern 1** frames (boundary closeups incorrectly called BE).

**Explicit non-regressions asserted in corpus_v1 regression filter** (combined run still expects these as **gates before trusting ship bands**):

1. **`bowlers_end` strict precision ≥ corpus_v1 V5 baseline (31.2%)**.
2. **100% recall** on human-labeled **BE** positives (N=5 in corpus doc narrative).
3. **`closeup` recall** unchanged floor.
4. **Closeup-share shift** bounded (>**15 pp swing** flagged fail on corpus filter — **combined run should revisit tolerance** adapted to denominator change).

Additionally **human operational constraints** from corpus doc:

- **`f941-pattern`** — any **`other`/`graphic`/non-cricket** migration into **`bowlers_end`** counts as severe regression (**corpus doc:L96–107, L202–204**).

**Evidence basis:**

- corpus_v1 per-frame deltas (**four frames changed V5→V6c**, **two aligns design intent**) — **`scout_v6c_shadow_run_corpus_v1_2026-04-25.md:L78–93**.
- Live **BE phase attractor observations** aligning with shadow (**`backlog.md` ~L5395–5401** referencing live DC vs PBKS).

---

## §3 Combined corpus definition

### Reference corpus_v1 snapshot (frozen today in repo)

| Property | Ground truth |
|----------|----------------|
| JSON path | `files/docs/scout_corpus_v1.json` (`run_shadow.py:38`; metadata `labeling_rubric` points **`files/docs/scout_labeling_rubric_v1.md`**) |
| Frame records | **41** objects (python `len(frames)`); header `"total_frames": 40` is **internally stale** versus array length (**metadata inconsistency – document, do not “fix” in this session**) |
| Source log recorded | **`logs/runs/rcb_gt_rc9_commentary_203904.log`** (RCB-vs-GT style naming in JSON **`source_log`**) |
| Selection | `"stratified grep-based"` + subsets target map **`batter_closeup_with_background`** 18 • **`disambiguation`** 12 • **`active_play_recall`** (**JSON says 11 rows vs target 10** — another bookkeeping drift worth cleaning at corpus extension time) |

**Empirical human label histogram (computed 2026-04-30 from JSON):**

- `human_camera_view`: **closeup 12**, **other 10**, **graphic 7**, **side_on 7**, **`bowlers_end` 5**

This is **not** the **“25 stratified prod-eval frames”** from the corpus plan; those frames were lost operationally (**`scout_v6c_shadow_run_corpus_v1_2026-04-25.md:L10–17`**) and must be re-captured before the canonical combined run.

### Planned combined composition (from corpus narrative)

Concrete **target** articulated in corpus doc (**L183–190**):

1. **Durably archive** prod-eval snaps for **match 2** (post archival fix narrative).
2. **Stratified ~25 `bowlers_end` emission samples** spanning **powerplay / middle / death** with **`M-2` bucket coverage check** (**L186–187**).
3. **Label `v1.2` rubric** (string in plan doc).
4. **Merge mentally** corpus_v1 (41) + new prod-eval (~24–25, prior plan 23 + fudge) ⇒ **≈66** frames (**L188–189** mentions **65-ish**; original plan **+F976** superseded).

### Sampling methodology (frozen where documented)

Corpus metadata: **`selection_method`** + subset rationale captured per-frame JSON fields (`selection_rationale`, `scout_cam_original`). Active_play_recall entries bias toward **`bowlers_end` scout-tagged deliveries** (**example `f169` rationale** **`scout_corpus_v1.json` ~lines 73–76**).

### Corpus gaps affecting scoping honesty

The combined corpus described in **`scout_v6c_shadow_run_corpus_v1_2026-04-25.md` is logically complete as a narrative but physically incomplete**: **lost prod-eval set** (**doc:L10–14**).

**Not represented (negative findings vs user query):**

| Question | Answer from repository |
|---------|-------------------------|
| **MI vs SRH or PBKS vs RR frames in corpus_v1**? | Corpus source **`rcb_gt_rc9`** naming — **does not imply** MI–SRH or PBKS–RR; those matches are backlog / monitoring narratives elsewhere, **not baked into scout_corpus_v1**. |
| **BATTERS-INVARIANT / WS-SLOT-INVARIANT / ball-by-ball gap fixtures** explicitly in scout corpus | **No** curated linkage in `scout_corpus_v1.json`; those investigations target **pipeline** behavior, **orthogonal** framing except where poor **strip OCR** overlaps (Thread 7). |

### Scoping implication

**Combined corpus assembly is prerequisite work Phase 1** (§7). Stop short of execution if **`files/docs/scout_corpus_combined_<date>.json` + matching JPEGs** absent.

**(Stop-and-route S1 clarification):** The **concept exists** AND **baseline artifacts exist**. What was missing (**prod-eval snaps**) blocked the **prior** dated plan but does **not** prove corpus is impossible — it proves **recovery + rebuild** precedes inference.

---

## §4 Shadow run infrastructure

### `run_shadow.py` behavior (truth table)

| Concern | Code fact |
|---------|-----------|
| **Entry** | **`python3 shadow_eval/run_shadow.py`** (`run_shadow.py:14–15`); cwd `files/` assumed for relative paths as used in codebase |
| **`--variants`** | Comma-separated filter; **`--variants V6c`** appended solo results historically (**corpus doc L45–48**) |
| **`--concurrency`** | Default **4** (`run_shadow.py:252`); doc warns Groq TPM at ≥4 concurrency (`run_shadow.py:99–101`) |
| **`--dry-run`** | Plans only (`run_shadow.py:205–207`) |
| **Resume semantics** | If **`OUT`** exists (`files/docs/shadow_run_v1.json`), load `results`; skip tuples `(frame_id, variant, replicate)` matching existing keys (**`run_shadow.py:193–203`**) — **triple-key resume** stable |
| **Corpus loader** | **Hardcoded:** `CORPUS = docs/scout_corpus_v1.json` (**L38**) |
| **Output writer** | **Overwrites OUT** atomically once per full completed run via single `json.dump` after gather (**`run_shadow.py:234–245`**); **risk:** partial failure mid-run retains prior file only if orchestration abort leaves earlier content — practice: treat **backup `shadow_run_v1.json` before exploratory passes** operator-side |
| **Frame path resolution** | `path = FILES / frame["path"]`; if `corpus_frames_v1/<basename>` exists, prefer snapshot (**`run_shadow.py:145–148`**) |

### Parsed tag surface

Harness extracts **JSON line** identical to **`vision.py`_parse_tag** intent but **parses subset** (**`camera_view`**, **`frame_phase`**) (**`run_shadow.py:71–91`**) — **does not persist** **`has_strip`**, **`has_overlay_stats`**, **`drs_review`** in **`results`** row (**structure `run_shadow.py:157–167`** vs stored raw prefix `raw_first_200`). Therefore **combined-corpus analysis for overlay flags requires harness extension OR offline post-pass on raw completions** (**§5 / §11**.

### Operational logistics

**Paths:**

- Corpus **`files/docs/scout_corpus_v1.json`**
- Snapshots **`files/docs/corpus_frames_v1/*.jpg`** (validated present in discovery)
- Output **`files/docs/shadow_run_v1.json`** (sample shows multiple variants coexist — top-level **`variants`** list may reflect last selective run **`["V6c"]`** as in read sample **L7–10** alongside historical `V1` rows **L13+**).

**Limits / infra gaps:**

- **No `--corpus` / `--output` CLI** Today — **`run_shadow.py` constants only** ⇒ combined JSON requires **either duplicated script constants on a worker branch**, **temporary file swap naming**, **or CLI extension** flagged as Phase 2 engineering (**stop-and-route S3 nuanced:** resume works; **multi-corpus support absent**).

### `analyze.py` coupling (`files/shadow_eval/analyze.py`)

- Hardcoded **`CORPUS`** / **`SHADOW`** (**`analyze.py:30–31`**). Any alternate combined paths require **matching edit** or **parameterization**.

---

## §5 Metrics framework

### What existing docs formally track

 **`scout_v6c_shadow_run_corpus_v1_2026-04-25.md` headline table (**L53–62**):

- **`bowlers_end` strict precision** (denominator emitted BE vs truth)
- **`bowlers_end` recall on human BE subset (N=5)**
- **`closeup` strict precision & recall**
- **`graphic` strict precision**
- **coverage-weighted precision** (weights from A3 audit distribution — **`analyze.py:34–45**)
- **net frame accuracy (41-frame)**
- **cam flip rate** across replicates (**doc:L62**) — surfaced by majority vote divergence conceptually (**`analyze.py:56–77`)

### Ground truth availability

Human labels live in corpus JSON (**`human_camera_view`**, **`human_frame_phase`**). Example row **`scout_corpus_v1.json:~72–106** for annotated fields.

Shadow harness stores **canonical** tags post-alias (**`variants.py:50–61`**, **`canon()`** invoked **`run_shadow.py:156`**).

### What is NOT automatically scored today

Harness output row omits **`has_overlay_stats`** / **`has_strip`** fidelity vs human (no overlay ground-truth field in excerpted corpus JSON schema). Corpus ship criteria focus **taxonomy / BE precision**, not OCR.

### Comparison methodology stance

Predominantly **strict label equality** (`canon_camera_view == human_camera_view`) after majority vote (**pattern `analyze.py` docstring:L3–11** referencing strict precision/recall decomposition).

Statistical significance: **existing docs do NOT define p-values or bootstrap CIs.** For **combined run**, adopting **explicit tie-break ordering** enumerated in corpus doc is **specified policy**, not improvised stats — **anything beyond empirical counts is §11 open work**.

### Corpus doc ship bands (combined)

Copied from **`scout_v6c_shadow_run_corpus_v1_2026-04-25.md:L191–193`:

- **Ship if combined precision >40%**
- **35–40% marginal tie-break**: net accuracy + severity-weighted FP
- **&lt;35% or recall regression → block**

**(Scoping clarification):** Bands reference **`bowlers_end` strict precision** in narrative context (section heading anchors). Verify denominator definition before execution aligns with **`analyze.py` implementation** (**§11**).

---

## §6 Adjacent issues — concurrency vs deferral

Decision grid for **combined-corpus execution** sequencing (engineering risk management, grounded in backlog text).

| Adjacent topic | Relation to Scout shadow | Recommendation |
|----------------|--------------------------|----------------|
| **Pass-2 async + retry policy** (**`backlog.md` ~L5512–5568, L5597+**) | Operational pipeline startup / enrichment; referenced as **timing context** losing prod-eval frames during restart (**`scout_v6c_shadow_run_corpus_v1_2026-04-25.md:L11–13**). Scout shadow itself does not call Pass-2. | **Do not block shadow run**, but schedule prod-eval captures on **sessions with stable archival checklist** (`debug_frames`/snapshot pipeline coherent). Confirm Pass-2 timeout staging state per backlog before confusing match logs |
| **`debug_frames` loss incident** (**corpus narrative L10–16**) | **Direct** — invalidated prior combined attempt | **Mandatory**: execution checklist includes **immediate copy-to-`corpus_frames_v1`** hooks before restarts (**already shipped fix claimed** in corpus doc L15–17) |
| **Sampler urgency / M-2 bucket coverage** (**`backlog` ~L5478–5510**, ~L3274–3276) | Determines **credibility** of prod-eval strata (death overs etc.) | **Before labeling / locking combined JSON**: consume **`bucket_coverage` output**, resolve warnings or document explicit waived buckets |
| **`side_on` canary / P1 backlog ~L6384+** (“Scout never emits `side_on`”) | **Orthogonal taxonomy coverage** distinct from closeup-bullet geometry | **Defer as separate prompt experiment** concurrent only if staffing allows — **risk of cross-coupled destabilisation** backlog itself warns fourth example may perturb BE/closeup balance (**backlog:L6407–6411**) |

Explicit deferrals acceptable provided **combined run still exercises** **f941 / closeup-shift / flip-rate watchers** enumerated (**corpus doc “Watch items” L200–214**).

---

## §7 Execution plan (Composer 2 actionable)

### Phase 1 — Corpus verification + extension

**Deliverables**

1. New **labeled JSON** referencing **corp_v1 + prod-eval**, unique `frame_id`s, **`path`** fields resolvable (`debug_frames/` or archival dir) + snaps under **`corpus_frames_v1/`**.
2. **Bucket coverage artefact**: dump from **`select_corpus_candidates.py`** / **`corpus_candidates.json`** aligning **`[BUCKET-COVERAGE]`** expectations (`backlog.md` ~L5478–5504) saved alongside corpus JSON (operator filename choice).
3. **Metadata block**: versioning (`v1.2` labeling note), **`source_match` identifiers**, **`labeling_rubric` revision pointer**.

**Success criteria**

- Every frame opens locally from repo paths (scripted sanity check enumeration).
- **No silent empty strata** flagged by tooling without written waiver.

### Phase 2 — Shadow invocation

Because **`run_shadow.py` hardcodes `CORPUS`**, Composer must **either**:

- **Fork constants** temporarily (execution branch acceptable), OR  
- Implement **`--corpus` / `--out-json`** (**new work**, not authored here**) before large spend.

Recommended safe pattern (zero logic change): symlink or **temporarily rename** authoritative combined corpus to expected filename **only if** reversible & backup retained — risky; **`--corpus` addition is clearer**.

**Variants:** run **`V5` + `V6c`** (**`run_shadow.py:254`** allows filter). Possibly chunk: `,V5,V6c` sequentially reusing resume.

**Success criteria**

- `shadow_run JSON` contains **completed triples**, **minimal `error` fields**.
- Inspect **latency & error tally** akin to corpus doc (**0 errors cited** historically).

### Phase 3 — Analysis

1. Majority vote (**`analyze.py` pattern`).
2. Rebuild tables analogous to corpus doc (**strict precision/recall/net accuracy/flip**).
3. **Manual migration table**: enumerate rows where **`vote_cam`** differs human OR differs V5 vs V6c; tag severity per corpus doc playbook.

### Phase 4 — Review + promotion

1. Compose decision memo bridging **bands** (**§5** gate).
2. If ship: **`vision.py`** prompt parity PR — align **`SCOUT_PROMPT`** STEP-1 closeup bullet lines **`vision.py:96–98`** with **`variants.py:V6c` text**, preserving **`{{`/`}}`** escaping rules (**`variants.py:458–465`).
3. If no-ship: keep production **V5** (**`scout_v6c_shadow_run_corpus_v1_2026-04-25.md:L196–198`**).

---

## §8 Promotion criteria

### Primary quantitative gates (combined)

Reuse **explicit bands** corpus doc:L191–194 with **additive operational veto list**:

**VETO (immediate no-ship even inside band)**

- **`f941-class` escalation** (**other/non-cricket → `bowlers_end`**) flagged in QA table (**corpus:L102–107, L202–204**).

**Supporting**

- Recall floors from regression filter replicated on merged set (numbers may need denominator recalibration — document before comparing raw percentages mechanically).

### Sign-off actors

Documentation references **assistant labeler historically** (**`scout_corpus_v1.json:L9`**). Promotion should include **human sign-off naming** (**execution session picks owner**).

### Production swap mechanics

1. **`GROQ_PRIMARY_MODEL`** unchanged unless separate model uplift (`config.py:L15`).
2. **Prompt-only diff** merges into **`SCOUT_PROMPT`**.

### Rollback

Revert **`vision.py`** `SCOUT_PROMPT` slice to Git-known V5 content; optionally hotfix commit. Maintain **`shadow_eval/variants`** as regression oracle.

---

## §9 Risk assessment

| Risk | Mitigation |
|------|------------|
| **Geometry ambiguity residual** — backlog notes second failure bucket **hero aerial** needing architecture (**`backlog.md` ~L5434–5441**); prompt-only uplift is bounded | Treat gains as marginal-band only |
| **`closeup` precision mechanical drop** via BE→closeup relabel reshaping denominators (**corpus:L115–121**)| Interpret with **severity lens** |
| **`frame_phase` attractor persists** (**corpus:L127–168**)| Exclude from promotion unless separate P1 handled |
| **Flip-rate increase (7.3→9.8% demo)** instability under boundary rewrite (**corpus:L62, L212–214**)| Quantify similarly on merged set |
| **Overlay/strip regressions undocumented** due harness tag subset | Optionally extend logging / storage |
| **Sample coverage holes** resurrect **death innings precision unknown** pathology (**`backlog.md` ~L5493–5496**) | Mandatory bucket auditing |

Prompt-only perturbations risk **unexpected attractor swaps** unseen in 41-frame set — corpus extension mitigates but never eliminates.

---

## §10 Composer 2 readiness matrix

### Per-phase autonomy

| Phase | Autonomous Composer | Needs Anmol |
|-------|---------------------|-------------|
| P1 path validation | Scripted file checks OK | Choosing match & labeling policy |
| P1 stratified sampling acceptance | Parses JSON outputs OK | Sporting judgment on waived buckets |
| P2 `--corpus` param (if coded) | Can implement mechanically | Approval to expose CLI ergonomics vs temp constants |
| P3 tables | Scripted | Severity classification edge cases |

### Dependencies

P2 **blocked** on P1. P3 blocked on **clean shadow JSON**. Promotion blocked on explicit decision record.

### Stop-and-route conditions (task-specific)

**S-R1**: Combined labels absent → corpus build prerequisite (echo **§3**).  

**S-R2**: Divergence between **`vision.py:V5`** text and **`PROMPT_V5` stringified** parity (risk after manual edits). → Run normalisation script / diff tooling before merge.  

**S-R3**: Groq outages / persistent `error` field → stall & retry with backoff (**already implemented** — `run_shadow.py:128–139`).  

**S-R4**: Analytic script reads wrong corpus path → forbid manual silent edits (**parameterise**).

### Validation against briefing stop flags

| ID | Finding |
|----|---------|
| **S2** Variant differs from bullet-only rewrite? | Confirmed **`PROMPT_V6` absent** — **matches discovery** (**`grep` PROMPT_V6** empty). |
| **S5** Larger multi-variant (`V6d`)? | **none** (**search `V6d`/`V6e`** empty repo-wide). |

---

## §11 Open questions (execution session must resolve)

Operational uncertainties called out in `scout_codebase_discovery.md` (Section 8, gaps ~lines 179–202) plus:

1. **Filename & schema** authoritative for combined corpus — pick stable naming (`scout_corpus_combined_YYYY-MM-DD.json`) & **version bump policy** (**fix `total_frames` drift first** §3).
2. **Denominator semantics** behind **combined >40%** precision — numerator/denominator spec locked with analyst before numeric comparison (**§5 ambiguity flag** labeled **Scoping Proposal** awaiting execution alignment).
3. **Whether to widen harness output** capturing **`has_overlay_stats`**, **`drs_review`** for regression guard given Thread 7 reliance — **proposal**, not precedent.
4. **Which backlog match becomes “match 2”** after narrative date slips — corpus doc anchored **2026-04-25**.
5. **Git handling of gigantic `shadow_run_v1.json` append patterns** versus fresh per-run file naming for clarity (artifact hygiene).

---

## §12 Cross-references

| Artefact | Role |
|---------|------|
| `files/docs/investigations/scout_codebase_discovery.md` | Locality + infra inventory |
| `files/docs/scout_v6c_shadow_run_corpus_v1_2026-04-25.md` | Narrative thresholds, regressions/failure modes |
| `files/docs/backlog.md` | V6c summary ~L5402+, Infrastructure sampler ~L5478+, Pass-2 ~L5512+, side_on P1 ~L6384 |
| `files/shadow_eval/variants.py` | **Authoritative textual diff vs V5** |
| `files/shadow_eval/run_shadow.py` | Harness contract |
| `files/eyes/vision.py` (`SCOUT_PROMPT`, **`Vision.describe` ~294+**) | Production parity target |
| `files/eyes/config.py` (**L15** `GROQ_PRIMARY_MODEL`) | Model pinning |
| `files/docs/scout_shadow_run_v1_analysis.md` | Publication template for regenerated stats |
| `files/docs/scout_labeling_rubric_v1.md` | Referenced corpus rubric lineage |
| Sample `files/docs/shadow_run_v1.json` | Row schema (`frame_id`, `variant`, `replicate`, `canon_*`, `error`, ...) |

---

## Appendix A — Verification checklist (“READ ALL” attestation)

- [x] `scout_codebase_discovery.md` scanned end-to-end
- [x] `scout_v6c_shadow_run_corpus_v1_2026-04-25.md` read fully
- [x] `variants.py` traced through **V5 block + `PROMPT_V6C`** — **confirmed no `V6a/b`/`PROMPT_V6` artifact**
- [x] `run_shadow.py` read fully (**CLI + resume**)
- [x] `vision.py` through **`SCOUT_PROMPT` opener + Vision class entry / describe side effects**
- [x] `config.py` **`GROQ_PRIMARY_MODEL`**
- [x] `backlog.md` selective reads on V6c / sampler / Pass-2 / side_on pillar
- [x] `shadow_run_v1.json` inspected for **`results`** object layout

Grounding rule honored: ambiguous zones labeled **proposal** or deferred to **`§11`**.

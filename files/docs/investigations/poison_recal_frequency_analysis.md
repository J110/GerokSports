# POISON-RECAL trip threshold — frequency & impact analysis

**Phase:** Forensic analysis (~production tee corpus). **No code changes.** **No threshold edits.**

**Purpose:** Quantify **`[POISON-RECAL]`** incidence across three sealed pipeline tees, characterize triggers vs documented logic, summarize downstream integrity impact, and evidence whether **`_POISON_RECAL_THRESHOLD = 5`** combined with **`abs(score_delta) > 7`** is appropriately calibrated.

**Root narrative anchor:** [`state_integrity_f3293_f3346.md`](state_integrity_f3293_f3346.md) — hinge **`[POISON-RECAL]`** at **`F3296`** (`logs/pipeline-2026-04-30-gt-rcb-live.log` **33734–33736**) precipitates tracker **`None`**, cold-start, then **`MULTI_BALL`** **`Δballs=7`** at **`F3346`** (**§1–§2** of that memo).

---

## §1 Executive summary

### Frequency (three tees)

**Superseded headline (Apr 30 corpus drift):** Raw tee totals below (**GT-RCB 24**) mix **live-ball chase** with **hours of post-match broadcast ingestion** (carousel / interviews / replay). [`state_integrity_f5054_f5240.md`](state_integrity_f5054_f5240.md) shows **`F5054` at `23:14:42`** with **`ACTION` … post-game interview** while strips still resemble chase-phase scorecards — evidence the pipeline never gated shutdown at match end. **Wall-clock–filtered live-match counts** are authoritative for threshold urgency; see **§11**.

| Match tee | **`[POISON-RECAL]`** fires |
|-----------|---------------------------:|
| `logs/pipeline-2026-04-28-pbks-rr-live.log` | **7** |
| `logs/pipeline-2026-04-29-194416-mi-srh-live.log` | **4** |
| `logs/pipeline-2026-04-30-gt-rcb-live.log` | **24** |
| **Combined** | **35** |

**Cross-match (raw):** GT vs RCB (**Apr 30**) exhibits **~3.4×** the PBKS–RR count and **6×** MI–SRH on these captures alone — **not** explained solely by tee truncation without normalizing by session duration (**§9**).

**Cross-match (live-window filtered — §11):** GT–RCB drops to **2** live-window fires vs **7** PBKS–RR and **3** MI–SRH (**~0.29×** PBKS–RR live rate by count). Normalized by wall-clock live-window span, GT–RCB is **not** the hot spot — PBKS–RR shows the highest live **`[POISON-RECAL]`** intensity on this slice.

### Trigger correctness vs shorthand

The operational trigger is **not** accurately summarized as “delta = 8 only”:

1. **Poison classification:** **`abs(extracted_score − tracker_score) > 7`** (`files/test_pipeline.py` **7894–7897**).
2. **Streak:** **`_POISON_RECAL_THRESHOLD = 5`** consecutive qualifying poison reads with **monotonic non-decreasing** extracted scores (`files/test_pipeline.py` **7930–7947**, **`5291`**).
3. **Negative deltas:** Large negative gaps (strip **below** tracker, e.g. **99 vs 154**) still poison because **`abs(delta) > 7`** — RECAL messages still reference “**tracker baseline … stale**.”

### Downstream impact (high signal)

Across **35** fires:

| Severity heuristic | Count | Notes |
|-------------------|------:|-------|
| **Clean / fast recovery** | **majority** | Within scanned windows, many fires pair with eventual DETAIL rows showing populated **`AFTER_score`** without nearby **`Δballs≥7`** **`MULTI_BALL`. |
| **Problematic (`MULTI_BALL` `Δballs≥7`)** | **≥2** on GT-RCB | **`F3296`→`F3346`** (**`Δballs=7`**) — **live-window** ([`state_integrity_f3293_f3346.md`](state_integrity_f3293_f3346.md)); **`F5054`→`F5240`** (**`Δballs=25`**, commentary line **56057**) — **post-match tail** per wall-clock filter (**§11**), [`state_integrity_f5054_f5240.md`](state_integrity_f5054_f5240.md). |
| **Oscillation / churn** | **many late GT-RCB** | Repeated fires alternate direction (**tracker 155 vs strip 126**, etc.) suggesting **broadcast graphic / tracker fights** rather than single-direction stale tracker (**§3** inventory). |

### Threshold stance (evidence-led)

**Verdict:** **`MIXED — leaning globally TOO AGGRESSIVE for mid/late chase stability`, while STILL NECESSARY for template / innings-edge rescue.**

For **cross-match frequency→threshold urgency**, treat **`§11` live-window counts** as controlling (**§6.5**): raw GT–RCB **24** largely reflected **post-match ingest**, not elevated **in-play** trip hazard vs MI–SRH.

| Evidence bucket | Points toward |
|-----------------|---------------|
| Rare but severe **`MULTI_BALL`** collapses tied to RECAL recovery | **Aggressive / costly** |
| Many fires recover without huge **`Δballs`** | **Benign typical case** (**stop-condition S6**) |
| Older tees show **tracker 222 vs strip 0** pattern | **Lenient threshold would stall** on wrong innings / `"0-0"` templates |
| GT-RCB raw **24** vs **7+4** | **Contaminated by post-match tail** (**§11**) — **live** GT count **2** vs **7** PBKS–RR / **3** MI–SRH inverts the “GT hot” reading |

**Confidence:** **Medium** — **three** logs only; no authoritative ball-by-ball ground truth wired per frame.

**Recommended next lane:** **Direction L (lifecycle / ingest gating)** as **P1** when interpreting tee corpus totals; **Direction B** remains core for **`F3296`-class live `MULTI_BALL`**. **Direction A2** — **secondary** pending gating (**§8**, **§11.5**).

---

## §2 POISON-RECAL emission mechanics

### §2.1 Code sites

| Signal | Location |
|--------|----------|
| **`[POISON-RECAL]`** WARN | `files/test_pipeline.py` **7950–7957** |
| **`[POISON-STREAK]`** INFO | `files/test_pipeline.py` **7942–7947** |
| **`[POISONED] Extracted score …`** | `files/test_pipeline.py` **7901–7906** |
| **`scoreboard._inn[score|wickets|overs] = None`** | `files/test_pipeline.py` **7958–7960** |
| **`score_mgr.full_reset(reason=poison_recal_consensus …)`** | `files/test_pipeline.py` **7962–7966** |
| **`full_reset` semantics** | `files/score_manager.py` **780–798** (`[SM-FULL-RESET]` → **`force_cold_start_recalibration`** + **`_clear_per_innings_sm_surface`** per docstring **788–790**) |

**`rg POISON-RECAL`** across `files/eyes/*.py`: **no** secondary emitter — poisoning orchestration is **`test_pipeline`** + **`score_mgr`**.

### §2.2 Trip condition (precise)

```5278:5291:files/test_pipeline.py
    # reaching ScoreManager when delta > 7.  ...
    _poison_streak_new_score: int | None = None
    _poison_streak_count: int = 0
    _POISON_RECAL_THRESHOLD = 5
```

```7894:7966:files/test_pipeline.py
                        _delta_check = (
                            _ext_score_int - _cur_score_int_check)
                        if abs(_delta_check) > 7:
                            _frame_poisoned = True
                            ...
                            if (_poison_streak_new_score is None
                                    or _ext_score_int
                                    >= _poison_streak_new_score):
                                _poison_streak_count += 1
                                _poison_streak_new_score = max(...)
                            else:
                                _poison_streak_new_score = _ext_score_int
                                _poison_streak_count = 1
                            log.info(
                                f"  [POISON-STREAK] high="
                                ...
                            if (_poison_streak_count
                                    >= _POISON_RECAL_THRESHOLD):
                                log.warn(
                                    f"  [POISON-RECAL] {_poison_streak_count} "
                                    f"consecutive POISON'd reads "
                                    ...
                                scoreboard._inn["score"] = None
                                scoreboard._inn["wickets"] = None
                                scoreboard._inn["overs"] = None
                                try:
                                    score_mgr.full_reset(
```

**Design rationale:** Inline comments **5278–5288**, **7907–7929** — stale tracker escape when SM rejection path never sees frames because pipeline poison guard drops them first.

### §2.3 Reset scope

| Layer | Cleared / forced |
|-------|------------------|
| **`scoreboard._inn`** | **`score`, `wickets`, `overs` → `None`** (**7958–7960**) |
| **`ScoreManager`** | **`full_reset`** → cold-start + **Fix-16 per-innings scalar wipe** (**780–798** `score_manager.py`) keeping **`innings`, `target`, `batting_team`, `venue`, `match_info`, `innings_history`** (**788–790**) |
| **Streak counters** | **`_poison_streak_*` cleared** (**7971–7972**) |

### §2.4 Log format drift (**stop-condition S5**)

Apr **28–29** tees sometimes emit **`5 consecutive POISON'd reads of score=0 — tracker baseline 243`** (numeric shorthand). Apr **30** GT-RCB emits **`(high=57, latest=57)`** brackets. **Same emission site** (**7951**) — template string evolved between captures; interpret fires equivalently.

---

## §3 Per-match POISON-RECAL inventory

### §3.1 PBKS–RR (**7** fires)

| Tee line | Clock | Frame | Tracker (“baseline”) | Strip-side score parsed | Δ (live−tracker) | \|Δ\| |
|---------:|-------|------:|-----------------------:|------------------------:|-----------------:|------:|
| 27266 | 21:10:24 | F2354 | 222 | 0 | −222 | 222 |
| 29425 | 21:23:13 | F2807 | 222 | 0 | −222 | 222 |
| 32154 | 21:34:26 | F3074 | 0 | 37 | 37 | 37 |
| 34634 | 21:45:24 | F3358 | 0 | 66 | 66 | 66 |
| 35938 | 21:50:51 | F3474 | 0 | 80 | 80 | 80 |
| 36420 | 21:54:02 | F3547 | 0 | 84 | 84 | 84 |
| 37244 | 21:57:54 | F3604 | 0 | 92 | 92 | 92 |

**Pattern:** First pair — **massive negative Δ** (**strip/template reads `0`** vs tracker **222**). Subsequent cluster — **`tracker 0`** climbing toward plausible live totals (**37→92**) — consistent **cold-start / innings-edge / overlay** choreography.

### §3.2 MI–SRH (**4** fires)

| Tee line | Clock | Frame | Tracker | Strip-side | Δ | \|Δ\| |
|---------:|-------|------:|--------:|-----------:|--:|------:|
| 27340 | 21:39:07 | F2483 | 243 | 0 | −243 | 243 |
| 29941 | 21:51:41 | F2855 | 0 | 8 | 8 | 8 |
| 30935 | 21:55:27 | F2954 | 0 | 12 | 12 | 12 |
| 37630 | 22:20:20 | F3573 | 74 | 85 | 11 | 11 |

**Pattern:** Mirrors PBKS–RR (**243→0** spike then low-score ladder).

### §3.3 GT vs RCB (**24** fires) — condensed

Full numeric parse from WARN lines (Apr **30** format):

| Tee line | Clock | Frame | Tracker | Strip-side (`latest`) | Δ |
|---------:|-------|------:|--------:|----------------------:|--:|
| 28677 | 21:43:18 | F2827 | 12 | 20 | +8 |
| 33734 | 22:00:59 | F3296 | 49 | 57 | +8 |
| 54501 | 23:14:42 | F5054 | 154 | 99 | −55 |
| 57700 | 23:29:56 | F5455 | 147 | 159 | +12 |
| 59844 | 23:43:53 | F5967 | 0 | 35 | +35 |
| 60364 | 23:45:52 | F6011 | 0 | 79 | +79 |
| 61757 | 23:51:15 | F6147 | 16 | 42 | +26 |
| 63192 | 23:56:05 | F6279 | 111 | 145 | +34 |
| 64965 | 00:03:41 | F6481 | 101 | 126 | +25 |
| 65616 | 00:06:00 | F6542 | 155 | 26 | −129 |
| 67436 | 00:13:33 | F6746 | 145 | 34 | −111 |
| 68423 | 00:17:13 | F6846 | 82 | 92 | +10 |
| 68804 | 00:18:48 | F6887 | 101 | 126 | +25 |
| 68999 | 00:19:26 | F6895 | 126 | 155 | +29 |
| 69431 | 00:21:07 | F6947 | 155 | 20 | −135 |
| 70768 | 00:26:14 | F7072 | 111 | 141 | +30 |
| 71652 | 00:29:41 | F7171 | 145 | 35 | −110 |
| 73008 | 00:34:40 | F7284 | 126 | 155 | +29 |
| 73405 | 00:36:21 | F7335 | 155 | 26 | −129 |
| 75075 | 00:43:54 | F7550 | 6 | 27 | +21 |
| 75562 | 00:45:36 | F7586 | 35 | 59 | +24 |
| 76285 | 00:47:43 | F7639 | 82 | 96 | +14 |
| 76693 | 00:49:02 | F7671 | 101 | 126 | +25 |
| 76941 | 00:49:53 | F7688 | 126 | 155 | +29 |

**Observations:**

1. **`|Δ|=8`** appears exactly **twice** (**F2827**, **`F3296`**) — **minimum-margin poison band** adjacent to **`unsupported-score-spike`** territory (**7976+**, deltas **2–7**).
2. **`Δ` magnitude spans −243 … +92** across three tees — **`>7` gate is wide**.
3. Late GT-RCB cluster (**23:xx–00:xx**) alternates **sign** — inconsistent notion of “strip always ahead of tracker.”

### §3.4 Cross-match comparison snapshot

| Metric | PBKS–RR | MI–SRH | GT-RCB |
|--------|--------:|-------:|-------:|
| Fires | 7 | 4 | **24** |
| **`streak=5/5`** hits (telemetry) | **11** | **5** | **31** |
| **`MULTI_BALL` with `Δballs≥7`** linked post-fire | **0** detected in heuristic scan | **0** | **≥2** (**`F3296`**, **`F5054`**) |

**Telemetry mismatch note:** **`streak=5/5`** counts **do not equal** **`[POISON-RECAL]`** counts (GT **31 vs 24**). Possible explanations include logging cadence, intervening streak resets (**7940–7941**), or duplicate streak logs — **not reconciled** in this forensic pass (**§9**).

---

## §4 Trigger condition analysis (Phase B)

### §4.1 Pattern taxonomy

| Pattern | Operational signature | Examples |
|---------|----------------------|----------|
| **Stable poisoning** | Strip-side numeric plateaus (`high == latest` across WARN); tracker flat | **`F3296`** (**high=57** plateau — [`state_integrity_f3293_f3346.md`](state_integrity_f3293_f3346.md)); late GT **`126↔155`** oscillation pockets |
| **Template / innings spike** | **`tracker ≫ strip`** with **`strip≈0`** | PBKS **222→0**, MI **243→0** |
| **Ascending rescue ladder** | **`tracker=0`** climbing **`37→92`** | PBKS **F3074–F3604** sequence |
| **Bidirectional chase churn** | Alternating **`Δ` sign**, large \|Δ\| | GT **23:xx–00:xx** cluster |

### §4.2 Scout / broadcast proxy

Without vision replay, **`[SCOUT] … cam= … phase=`** lines preceding fires serve as coarse proxies (**graphic**, **closeup**, **`digits=False`** spikes — cf. **`F3313`** **`GT 0-0`** narrative in [`state_integrity_f3293_f3346.md`](state_integrity_f3293_f3346.md)).

### §4.3 Trip justification (heuristic **B4**)

| Classification | Operational definition used here | Approx. share |
|----------------|----------------------------------|---------------|
| **Justified** | Template **`0`** vs non-zero tracker OR **`tracker 0`** ladder suggesting stalled cold-start | **PBKS/MI-heavy** |
| **Ambiguous / chase oscillation** | Large \|Δ\| both directions late innings — unclear which side truth without scorecard | **GT late cluster** |
| **Likely harmful** | RECAL shortly precedes **`MULTI_BALL`** with **`Δballs≥7`** | **2** GT sequences (**§5**) |

---

## §5 Downstream impact analysis (Phase C)

### §5.1 Worst-case characterizations

**Case W1 — [`state_integrity_f3293_f3346.md`](state_integrity_f3293_f3346.md)**

| Milestone | Tee evidence |
|-----------|--------------|
| RECAL | **33734–33736** (`F3296`) |
| Tracker **`AFTER_score=None`** DETAIL streak | **`33751`–`33893`** region |
| **`MULTI_BALL`** | Commentary **`Δballs=7`** **33996**; DETAIL **`34017`** |
| Resume normal **`ball_event`** | **`34111`** **`1_RUNS`** |

**Classification:** **Problematic** — **`Δballs=7`** + **`wkts 0→2`** telemetry shock (**33992**) documented upstream memo.

**Case W2 — `F5054` → `F5240`**

| Milestone | Tee evidence |
|-----------|--------------|
| RECAL | **54501** (`F5054`) — tracker **154**, strip-side **99** |
| Delay | **`F5240 − F5054 = 186`** frames |
| **`MULTI_BALL`** | **`Δballs=25`** **56057** |

**Classification:** **Problematic → catastrophic collapse** by **`MULTI_BALL`** absorption metric alone — independent sporting verification still absent (**§9**).

### §5.2 Aggregate impact metrics (approximate)

| Metric | Value |
|--------|------:|
| Total fires | **35** |
| Fires with nearby **`Δballs≥7`** **`MULTI_BALL`** | **≥2** (**GT-RCB only** on scanned windows) |
| Fires with **`Δballs≥20`** | **1** confirmed (**25**) |

Heuristic bulk classification across automated scan (narrow downstream window — **§9** caveat): **most fires resemble stop-condition **S6** — recovery without extreme **`MULTI_BALL`**.

---

## §6 Threshold appropriateness (Phase D)

### §6.1 Decomposition (**D1**)

| Knob | Value | Role |
|------|------:|------|
| **`abs(delta) > 7`** | Runs-only poison gate (`test_pipeline.py` **7896**) | **Not wickets/composite** — overs movement handled elsewhere (**unsupported spike** branch **7976+**) |
| **`_POISON_RECAL_THRESHOLD`** | **5** frames (`5291`) | Documented watchdog commentary **5278–5288** |
| **Monotonic streak rule** | Non-decreasing extracted scores (**7930–7941**) | Prevents plateau oscillations from resetting prematurely |

### §6.2 Sensitivity (**D2**) — qualitative

| Hypothetical shift | Expected directional effect | Quantification status |
|--------------------|----------------------------|-----------------------|
| **`N = 7`** frames | Fewer RECAL triggers; prolonged stale-tracker risk during innings-template failures | **Not counted** — requires replaying poison streak lengths |
| **`N = 3`** | More RECAL; higher churn / **`MULTI_BALL`** hazard surface | Same |

**Empirical anchor:** GT-RCB logs **`31`** **`streak=5/5`** vs **`24`** RECAL — suggests tightening threshold isn't the sole throttle (**telemetry coupling unexplained**).

### §6.3 Trip-vs-no-trip cost matrix (**D3**)

| Outcome | Interpretation | Evidence sketch |
|---------|----------------|-----------------|
| **TP trip** | Tracker genuinely stale vs sustained strip truth | PBKS/MI **`222/243 vs 0`** |
| **FP trip** | Strip noisy but numerically stable — tracker nuked anyway | **`F3296`** ambiguity (**[`state_integrity_f3293_f3346.md`](state_integrity_f3293_f3346.md)**) |
| **TN no-trip** | Tracker healthy — occasional **`FRAME_POISONED`** without RECAL | [`match_postmortem_data_gt_rcb_20260430.md`](match_postmortem_data_gt_rcb_20260430.md) (**444** poison mentions ≫ **24** RECAL) |
| **FN no-trip** | Stuck tracker never clears | Would manifest as frozen **`AFTER_score`** — **not** enumerated here |

### §6.4 Recommendation synthesis (**D4**)

| Statement | Confidence |
|-----------|------------|
| Global threshold is **NOT plainly appropriate** for **all innings phases** — GT chase demonstrates **high-frequency RECAL + rare catastrophic `MULTI_BALL`** coupling | **Medium** |
| Global loosening (**↑N** or **↑delta**) risks **PBKS/MI-style template stalls** | **Medium** |
| **`eyes/scoreboard.py`** does **not** centralize **`FRAME_POISONED`** emission — poisoning begins **`test_pipeline`** / extractor divergence (**investigation correction vs brief §Primary context**) | **High** |

### §6.5 Live-window reassessment (**§11 addendum**)

After wall-clock filtering (**§11**), the **cross-match RECAL frequency headline no longer supports “GT–RCB as uniquely threshold-stressed vs MI–SRH.”** Raw **24** on GT–RCB was dominated by **post-match** fires (**22** of **24**) while PBKS–RR and MI–SRH captures were largely live-bound (**§11.4**).

**Threshold stance revision:** The prior **§1** **mixed / leaning aggressive** verdict blended **live** phenomena (e.g. **`F3296`** **`MULTI_BALL`**) with **post-tail churn** unrelated to mid-match calibration. **Numeric threshold tuning (Direction A2) loses urgency as a cross-match explanation** until lifecycle gating caps post-match ingestion noise — **§11.5**, **§8**.

---


## §7 Implications

| Area | Implication |
|------|-------------|
| **State integrity backlog** | Prioritize **`MULTI_BALL` causal decomposition** after RECAL (**Direction B**) ahead of Scout **`V6c/V6e`** churn (**still deferred** per GT postmortem posture). |
| **Lever / roster telemetry** | RECAL + cold-start interacts with **`[WS-SCRUB]`** / slot hygiene observed near **`F3293`** — separate lane from numeric threshold tuning. |
| **Monitoring** | Add rollup dashboards (**outside this doc**) counting **`[POISON-RECAL]` / `[SM-FULL-RESET]` / `Δballs`** jointly — frequency alone insufficient (**S6** lesson). |

---

## §8 Next-step recommendations

| Condition | Recommended lane |
|-----------|------------------|
| Org prioritizes eliminating **`Δballs≥7` collapses** | **Direction B** — **`MULTI_BALL` instrumentation + scorer/SM parity** ([`state_integrity_f3293_f3346.md`](state_integrity_f3293_f3346.md) tee **34005** `[SHADOW] SM=None BED=MULTI_BALL MISSED`) remains primary for **live** collapse causal chains (**§11** shows **`F3296`** is live-window). |
| Large GT–RCB raw RECAL counts driven analysts toward threshold knobs | **Direction L (lifecycle / ingest gating)** — **P1:** stop or downgrade pipeline processing once match telemetry passes **match-end + confirmation buffer**, per **§11** — **before** interpreting tee totals as threshold stress. |
| Org still wants numeric poison-trip experiments after gating | **Direction A2** — scoped replay (**innings phase**, **`digits=False` spikes**, **`tracker None`**) — **secondary** to **Direction L** given **§11** live-frequency inversion vs PBKS–RR. |
| Org accepts RECAL rarity/cost trade | Balanced investment across **B** + **L**; extend corpus (**≥10 tees**) with **live-window tagging** standard practice (**§11.6**). |
| Evidence remains ambiguous | Extend corpus (**≥10 tees**) before numeric threshold edits |

---


## §9 Limitations

1. **Three** tees — insufficient for statistical significance on rare tails (**≥2** severe **`MULTI_BALL`** cases).
2. **No frame-ground-truth alignment** — broadcast reconstruction heuristic-only (**§4.2**).
3. Downstream scans **truncate** — delayed **`MULTI_BALL`** (**186** frames post RECAL) invisible to shallow parsers (**§5.1 Case W2** methodology).
4. **Poison vs RECAL cardinality mismatch** ([`match_postmortem_data_gt_rcb_20260430.md`](match_postmortem_data_gt_rcb_20260430.md) **444 FRAME_POISONED** mentions vs **24** RECAL) — healthy separation but **not modeled** quantitatively here.
5. **`eyes/scoreboard.py`** cited in charter brief — **FRAME_POISONED orchestration lives in `test_pipeline.py`** for this mechanism (**§6.4**).

---

## §10 Cross-references

| Doc / artifact | Role |
|----------------|------|
| [`state_integrity_f3293_f3346.md`](state_integrity_f3293_f3346.md) | Canonical **`F3296`** RECAL → **`MULTI_BALL Δballs=7`** trace |
| [`match_postmortem_data_gt_rcb_20260430.md`](match_postmortem_data_gt_rcb_20260430.md) | Aggregate FRAME_POISONED churn (**§6**, JSON companion); note tee continues **past** ~22:17 — **§11** clock span vs postmortem “truncation” framing |
| [`state_integrity_f5054_f5240.md`](state_integrity_f5054_f5240.md) | Post-match **`F5054`** strip vs tracker / carousel-adjacent **`MULTI_BALL`** (**§11**) |
| `files/test_pipeline.py` **5278–5292**, **7874–7975**, **`5291`** | Threshold constants + poison / streak / RECAL |
| `files/score_manager.py` **780–798**, **1623–1651** | **`full_reset`**, **`force_cold_start_recalibration`** |
| `logs/pipeline-2026-04-30-gt-rcb-live.log` **33734**, **56057** | RECAL anchors + **`Δballs=25`** commentary |

---

### Stop-condition ledger

| ID | Outcome |
|----|---------|
| **S1** | Mechanism located **`test_pipeline.py:7950`** — matches expectation. |
| **S2** | **35** combined fires → analysis meaningful. |
| **S3** | GT **24 < 50** — detailed inventory retained (**§3**). |
| **S4** | Actual logic **`abs(delta)>7` + streak 5 + monotonic rule** — revised vs shorthand (**§2**). |
| **S5** | Message template drift PBKS/MI vs GT logged (**§2.4**). |
| **S6** | Majority fires lack extreme downstream **`MULTI_BALL`** in heuristic passes — informs **mixed** verdict (**§1**, **§5.2**). |

---

## §11 Live-match filtered re-derivation (addendum)

### §11.1 Scope and motivation

[`state_integrity_f5054_f5240.md`](state_integrity_f5054_f5240.md) establishes that **`[POISON-RECAL]` at `F5054`** (**`logs/pipeline-2026-04-30-gt-rcb-live.log` line `54501`**, bracket **`23:14:42`**) sits on **`ACTION` … post-game interview** while **`scout=STRIP`** still prints **`GT 99-6 (13.5)`** against a stale tracker — i.e. **post-match broadcast content** continued to drive **`FRAME_POISONED` → streak → RECAL**. Without separating **live-ball windows** from **post-match tails**, cross-match **`[POISON-RECAL]`** totals confound **threshold appropriateness** with **pipeline longevity past match end**.

**Method:** For each tee, infer **match-end clock** (below). Define **ambiguous band** **`[ME − 5:00, ME + 5:00]`** (minute precision). Classify each WARN:

| Bucket | Rule |
|--------|------|
| **LIVE** | Clock **strictly before** **`ME − 5:00`** |
| **AMBIGUOUS** | Clock **within** **`[ME − 5:00, ME + 5:00]`** |
| **POST_MATCH** | Clock **strictly after** **`ME + 5:00`** |

**Live-match pipeline window** for rates: **[first `[DELIVERY ENQUEUED]` timestamp, `ME + 5:00`]** inclusive intent (wall-clock span reported below).

Clocks are taken from bracket timestamps on **`TEST`** lines as printed in each tee.

### §11.2 Match-end timestamps per log

#### PBKS–RR (`logs/pipeline-2026-04-28-pbks-rr-live.log`) — **medium**

| Field | Value |
|-------|-------|
| **ME (proxy)** | **`22:17:40`** — last **`[DELIVERY ENQUEUED]`** in file (**line `43151`**, **`F4052`**, `dnum=142`, `evt=EXTRA`). |
| **Evidence** | Chase still **RR 132–3 (12.1)** with **target 223** in the same tail — log **ends mid-chase**, not on a completion marker. ME is therefore **“last ball event recorded”**, not verified **winning runs**. |
| **Ambiguous band** | **`22:12:40`–`22:22:40`** |
| **Window end (`ME+5`)** | **`22:22:40`** |
| **First delivery** | **`19:32:13`** (`dnum=1`, **`F168`**, line **`511`**) |

#### MI–SRH (`logs/pipeline-2026-04-29-194416-mi-srh-live.log`) — **medium–high**

| Field | Value |
|-------|-------|
| **ME (proxy)** | **`22:14:37`** — last **`[DELIVERY ENQUEUED]`** (**`F3428`**, `dnum=120`). |
| **Evidence** | No later `DELIVERY ENQUEUED` lines; tee contains **`STRIP: SRH 91-0 (5.5)`** at **line `37914`** (**`22:21:37`**, **`F3594`**) — capture **ends shortly after**, consistent with **end-of-log ≈ late session**. |
| **Ambiguous band** | **`22:09:37`–`22:19:37`** |
| **Window end (`ME+5`)** | **`22:19:37`** |
| **First delivery** | **`19:45:47`** (`dnum=1`) |

#### GT vs RCB (`logs/pipeline-2026-04-30-gt-rcb-live.log`) — **medium** (dual anchors)

| Field | Value |
|-------|-------|
| **ME_A (broadcast-aligned)** | **`22:30`** — external **winning-runs ~22:30 IST** per investigation charter (**ESPNcricinfo ~23:27 IST signoff recorded separately**). Used for primary classification below. |
| **Evidence A** | **`[DELIVERY ENQUEUED]` continues to `22:58:04`** (`dnum=163`, **`F4658`**) — **pipeline clock ≠ broadcast narrative** if chase truly ended ~22:30; [**`match_postmortem_data_gt_rcb_20260430.md`**](match_postmortem_data_gt_rcb_20260430.md) §1 “truncation ~22:17” describes **analysis scope**, **not** last byte of this tee (**tail runs to `00:49:53` next calendar day**). |
| **ME_B (log-last-evening-ball)** | **`22:58:04`** — last evening **`DELIVERY ENQUEUED`** before **`00:`** timestamps resume (**sensitivity anchor**). |
| **Ambiguous band (ME_A)** | **`22:25`–`22:35`** |
| **Window end (`ME_A+5`)** | **`22:35`** |
| **Ambiguous band (ME_B)** | **`22:53:04`–`23:03:04`** |
| **First delivery** | **`19:51:45`** (`dnum=1`, **`F11`**) |

**Classification sensitivity:** Every **`[POISON-RECAL]`** on this tee falls **either** before **`21:25`** **or** after **`23:14`** — **no WARN lands in either ambiguous band**. **`ME_A` vs `ME_B` therefore yields identical LIVE / POST_MATCH buckets** for POISON-RECAL rows.

### §11.3 Per-fire classification (35 rows)

Phase notes: **`scout=STRIP`** text below is quoted from nearest **`DETAIL|…|SCOREBOARD`** / **`STRIP:`** lines around each WARN where sampled; **`AFTER_innings`** from same **`DETAIL`** row after **`full_reset`** commonly **`None`** — innings inferred from **`STATE`** / **`BEFORE_score`** context in tee.

#### PBKS–RR — **7 LIVE**, **0 POST_MATCH**, **0 AMBIGUOUS**

| # | Tee line | Clock | Frame | Bucket | Phase | Tracker → strip (`WARN`) | Strip / context |
|--:|---------:|-------|------:|--------|-------|---------------------------|-----------------|
| 1 | 27266 | 21:10:24 | F2354 | LIVE | **INNINGS_BREAK / inn2 onset** | 222 → 0 | Innings-edge **`0`** template vs latched **`222`** (**§3.1**) |
| 2 | 29425 | 21:23:13 | F2807 | LIVE | **INNINGS_2** | 222 → 0 | Same pattern |
| 3 | 32154 | 21:34:26 | F3074 | LIVE | **INNINGS_2** | 0 → 37 | Cold-start ladder |
| 4 | 34634 | 21:45:24 | F3358 | LIVE | **INNINGS_2** | 0 → 66 | Ladder |
| 5 | 35938 | 21:50:51 | F3474 | LIVE | **INNINGS_2** | 0 → 80 | Ladder |
| 6 | 36420 | 21:54:02 | F3547 | LIVE | **INNINGS_2** | 0 → 84 | Ladder |
| 7 | 37244 | 21:57:54 | F3604 | LIVE | **INNINGS_2** | 0 → 92 | Ladder |

#### MI–SRH — **3 LIVE**, **1 POST_MATCH**, **0 AMBIGUOUS**

| # | Tee line | Clock | Frame | Bucket | Phase | Tracker → strip (`WARN`) | Strip / context |
|--:|---------:|-------|------:|--------|-------|---------------------------|-----------------|
| 8 | 27340 | 21:39:07 | F2483 | LIVE | **INNINGS_2** | 243 → 0 | Template spike (**§3.2**) |
| 9 | 29941 | 21:51:41 | F2855 | LIVE | **INNINGS_2** | 0 → 8 | Ladder |
| 10 | 30935 | 21:55:27 | F2954 | LIVE | **INNINGS_2** | 0 → 12 | Ladder |
| 11 | 37630 | **22:20:20** | F3573 | **POST_MATCH** | — (**clock**) | 74 → 85 | **Strip reads live chase (`SRH 85-0 (5.4)`**) but timestamp **`> ME+5`** (**22:19:37**) — **stop-condition S5**: likely **slow-motion / replay / graphics persistence**, not carousel **`0-0`**, yet **not** inside operational live window under this memo |

#### GT vs RCB — **2 LIVE**, **22 POST_MATCH**, **0 AMBIGUOUS**

| # | Tee line | Clock | Frame | Bucket | Phase | Tracker → strip (`WARN`) | Strip / context |
|--:|---------:|-------|------:|--------|-------|---------------------------|-----------------|
| 12 | 28677 | 21:43:18 | F2827 | LIVE | **INNINGS_2** | 12 → 20 | **`GT 20-0 (1.2)`** chase strip (**[`state_integrity_f3293_f3346.md`](state_integrity_f3293_f3346.md)** precursor family) |
| 13 | 33734 | 22:00:59 | F3296 | LIVE | **INNINGS_2** | 49 → 57 | **`GT 57-2 (5)`** — canonical **`MULTI_BALL Δballs=7`** antecedent (**live**) |
| 14 | 54501 | **23:14:42** | F5054 | **POST_MATCH** | — | 154 → 99 | **`ACTION` … post-game interview**; **`GT 99-6 (13.5)`** vs stale **`154-6`** — [`state_integrity_f5054_f5240.md`](state_integrity_f5054_f5240.md) |
| 15 | 57700 | 23:29:56 | F5455 | POST_MATCH | — | 147 → 159 | Late **`GT …`-family** oscillation (**§3.3**) |
| 16 | 59844 | 23:43:53 | F5967 | POST_MATCH | — | 0 → 35 | Tracker **`0`** ladder resumes post-tail |
| 17 | 60364 | 23:45:52 | F6011 | POST_MATCH | — | 0 → 79 | Same cluster |
| 18 | 61757 | 23:51:15 | F6147 | POST_MATCH | — | 16 → 42 | Bidirectional churn |
| 19 | 63192 | 23:56:05 | F6279 | POST_MATCH | — | 111 → 145 | **`126 ↔ 155`** family (**§4**) |
| 20 | 64965 | **00:03:41** | F6481 | POST_MATCH | — | 101 → 126 | Next-calendar-day tail |
| 21 | 65616 | 00:06:00 | F6542 | POST_MATCH | — | 155 → 26 | Sign flip |
| 22 | 67436 | 00:13:33 | F6746 | POST_MATCH | — | 145 → 34 | Sign flip |
| 23 | 68423 | 00:17:13 | F6846 | POST_MATCH | — | 82 → 92 | Mixed strip/stadium shots |
| 24 | 68804 | 00:18:48 | F6887 | POST_MATCH | — | 101 → 126 | Repeat plateau |
| 25 | 68999 | 00:19:26 | F6895 | POST_MATCH | — | 126 → 155 | Repeat plateau |
| 26 | 69431 | 00:21:07 | F6947 | POST_MATCH | — | 155 → 20 | Large negative Δ |
| 27 | 70768 | 00:26:14 | F7072 | POST_MATCH | — | 111 → 141 | Plateau climb |
| 28 | 71652 | 00:29:41 | F7171 | POST_MATCH | — | 145 → 35 | Negative Δ |
| 29 | 73008 | 00:34:40 | F7284 | POST_MATCH | — | 126 → 155 | Plateau |
| 30 | 73405 | 00:36:21 | F7335 | POST_MATCH | — | 155 → 26 | Negative Δ |
| 31 | 75075 | 00:43:54 | F7550 | POST_MATCH | — | 6 → 27 | Low-score tug |
| 32 | 75562 | 00:45:36 | F7586 | POST_MATCH | — | 35 → 59 | Low-score tug |
| 33 | 76285 | 00:47:43 | F7639 | POST_MATCH | — | 82 → 96 | Mid-score tug |
| 34 | 76693 | 00:49:02 | F7671 | POST_MATCH | — | 101 → 126 | Plateau |
| 35 | 76941 | 00:49:53 | F7688 | POST_MATCH | — | 126 → 155 | Last WARN before tee ends |

**POST_MATCH strip typography:** GT tail alternates plausible-looking totals (**`126`/`155`/`20`**) consistent with **`§3.3`** **“graphic / tracker fights”** — carousel **`GT 309-0`** class artifacts called out in **`F5054`** memo appear **nearby frames**; **many WARN rows were not exhaustively paired with **`DETAIL`** replays** in this pass. **`F5054`** remains the clearest **interview + inconsistent chase-phase strip** exemplar.

### §11.4 Updated frequency table

| Match tee | Total fires | **Live** | **Post-match** | **Ambiguous** |
|-----------|------------:|---------:|---------------:|--------------:|
| `logs/pipeline-2026-04-28-pbks-rr-live.log` | 7 | **7** | **0** | **0** |
| `logs/pipeline-2026-04-29-194416-mi-srh-live.log` | 4 | **3** | **1** | **0** |
| `logs/pipeline-2026-04-30-gt-rcb-live.log` | 24 | **2** | **22** | **0** |
| **Combined** | **35** | **12** | **23** | **0** |

**Intensity (fires ÷ live-window wall hours):**

| Tee | First `DELIVERY ENQUEUED` | **`ME+5`** window end | Approx. span | Live fires | **Fires / hour** |
|-----|---------------------------|----------------------|-------------:|-----------:|-----------------:|
| PBKS–RR | 19:32:13 | 22:22:40 | **~2.84 h** | 7 | **~2.46** |
| MI–SRH | 19:45:47 | 22:19:37 | **~2.56 h** | 3 | **~1.17** |
| GT–RCB | 19:51:45 | 22:35 | **~2.72 h** | 2 | **~0.74** |

**Revised headline:** Raw **“GT–RCB **6×** MI–SRH **`[POISON-RECAL]`**”** collapses to live-window **`2 ÷ 3 ≈ 0.67×`** — GT–RCB is **lower**, not higher, than MI–SRH on filtered counts (**inverse ratio** vs raw totals).

### §11.5 Reframed verdict (executive summary & thresholds)

| Topic | Revision |
|-------|----------|
| **§1 frequency narrative** | Raw totals remain logged for reproducibility but **must not** drive urgency conclusions alone — **§11** header supersede note. |
| **§6 threshold urgency** | Cross-match elevation attributed to GT–RCB **does not reproduce** after live-window tagging — aligns with charter outcome **(b):** **threshold knob urgency drops for explaining tee-vs-tee spread**; **`F3296`** proves **`MULTI_BALL`** tail risk **still exists inside live windows** → **Direction B** stays central for integrity. |
| **`F5054 → F5240` (`Δballs=25`)** | Classified **POST_MATCH** — mitigates using that chain as proof of **in-play** threshold miscalibration; underscores **Direction L** (**lifecycle gating**). |
| **§8 directions** | **Direction L** elevated **P1**; **Direction A2** explicitly **secondary** pending gating discipline. |

### §11.6 Limitations

1. **`±5:00`** bands are **heuristic** — trophy presentation / rain **could** shift true sport end without shifting log quality.
2. **PBKS–RR ME** is **last logged ball**, not verified **match result** — chase incomplete in file (**S1** variant).
3. **MI POST row (`F3573`)** displays **plausible chase digits** yet clears **`POST_MATCH`** on clock alone (**S5**).
4. **GT dual-clock skew** (**DELIVERY** lines **`22:58`** vs external **`22:30`**) implies either **capture timezone**, **replay feed**, or **scoreboard latency** — **`ME_A`** trusts charter externalism (**S3**).
5. **Operational significance:** Some **POST_MATCH** RECAL rows may still stress downstream clients if ingest continues — threshold tuning **does not substitute** for **kill-switch policy**.

---

*Investigation-only memo — thresholds untouched.*

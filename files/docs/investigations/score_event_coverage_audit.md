# Score-event coverage audit — Path 1 ceiling + `save_dir` status

**Date:** 2026-05-01  
**Scope:** Investigation only (no code changes).

**Reads:** IPL **2026** box scores cited from public scorecard pages (**ESPNcricinfo** / **ipl.com**) for denominator sanity checks; corpus files are **`logs/pipeline-2026-04-30-gt-rcb-live.log`** (primary), **`logs/pipeline-2026-04-29-194416-mi-srh-live.log`** (secondary).

---

## 1. Executive summary

| Item | Finding |
|------|---------|
| **Phase A (`save_dir`)** | **`ENABLED`** for production-style runs — not a CLI flag but **`BallAnalyzer._delivery_folder()`** under **`files/logs/deliveries/<session_id>/dNNN/`**. The Apr **30** bulk session **`20260430_195352`** has **215** delivery folders each containing **`window_debug.json`**, **`layer2.json`**, **`delivery_window.mp4`**. |
| **Score-event ceiling (steady GT-RCB session)** | **BED → enqueue parity is tight:** **`DELIVERY ENQUEUED` = eligible `DETAIL` ball events − `MULTI_BALL` − `DRS_NOT_OUT` = 215** (Δ **0**) for **`line_no ≥ 1223`** restart session. Ceiling is dominated by **`MULTI_BALL` aggregation** (no per-ball enqueue until decomposed downstream) rather than stray drops inside this gate pattern. |
| **Coverage vs public scorecard (GT-RCB full match)** | Approx. **official ~211 balls bowled** (GT **95** + RCB **116** from fractional overs notation) vs **215** enqueues ⇒ **≤ ~2.2% surplus** ⇒ **inverse ceiling / phantom-ish mass** (`≈215−211`), **below 5%** threshold · **Uncertainty:** extras / rebowl accounting on card vs pipeline `EXTRA` events. |
| **Phantom verdict** | **`(215−211)/215 ≈ 1.9%`** if denominators assumed exact — classify **below 5%** (noise / accounting). |
| **Ceiling verdict (C1)** | **>** **95%** on **steady-session/internal BED parity**; **ambiguous** vs **MULTI-ball hidden balls** (dominant shrink of true ceiling toward scorecard-perfect extraction). |
| **MI-SRH segmentation (cross-match denominator)** | **Verdict 1 rejected** (not MI-innings-only). **Verdict 2 framing** applies if the denominator is nominal **combined card balls (~232)**: **`120/232 ≈ 51.7%`**. Segment detail (**Verdict 3**): enqueue split **`~104`** before first **`DETAIL`** with **`batting_team=Sunrisers Hyderabad`** (log **~31498**) vs **`~16`** after — chase largely absent; internal **eligible `DETAIL`→enqueue parity stays `120=120`** (§3.4). |
| **PBKS-RR chase spot-check** | **`Verdict T1`**: chase enqueues **`24`** vs card **`116`** RR balls (**`≈21%`**); pre‑chase **`118`** vs innings‑1 **`120`** (**`≈98%`**). Second cross‑match confirming chase starvation (**§3.4 PBKS-RR**). |

**Recommendation (D):** `(1)` Proceed to **Path 1b window-content audit** — artifacts exist; align tee line windows to **`files/logs/deliveries/<session>/dNNN/`** by delivery index. **`(2)` Parallel:** treat **`MULTI_BALL Δballs`** backlog as explicit **coverage hole** (`multi_ball_decomposition_*` design already flags consumer split).

---

## 2. `save_dir` configuration audit

### 2.1 Definition sites (grep results)

**`grep -rn save_dir files/test_pipeline.py files/eyes/`** → **no hits** (`None`).  
Saving is wired through **`BallAnalyzer`** + **`delivery_window_recorder`**, not the main pipeline orchestrator kwargs.

Primary contract:

```1652:1662:files/ball_analyzer.py
    def _delivery_folder(self) -> str:
        """Return the session-scoped folder for the current delivery.

        Folder name: ``logs/deliveries/<session>/d<NNN>``.  Session prefix
        prevents pipeline restarts from clobbering prior runs' frames.
        """
        base = os.path.join(os.path.dirname(__file__), "logs", "deliveries",
                            self._session_id)
        fdir = os.path.join(base, f"d{self._delivery_count:03d}")
        os.makedirs(fdir, exist_ok=True)
        return fdir
```

- **Default:** every enqueue gets a filesystem path (**never `None`**) under **`files/logs/deliveries/`** resolved from **`__file__`** (typically **`…/SportsComm/files/logs/deliveries/...`**).

### 2.2 Consumers (who receives `save_dir`)

| callee | Role |
|--------|------|
| **`enqueue_delivery_analysis`** | `delivery_dir = self._delivery_folder()` ```806:806:files/ball_analyzer.py``` → threaded worker → **`_run_gemini_delivery_analysis(..., delivery_dir)`** ```836:841:files/ball_analyzer.py``` |
| **`DeliveryWindowRecorder.classify_for_score_event`** | `save_dir` passed through to **`_classify_frames_for_event`** → **`_write_window_debug(...)`** ⇒ **`window_debug.json`** ```521:557:files/delivery_window_recorder.py``` |
| **`Layer2Classifier.classify_*`** | optional **`layer2.json`** beside mp4 ```579:603:files/layer2_classifier.py``` |
| **`_save_delivery_frames`** (legacy / VLM) | **`meta.json`** + jpgs ```1664:1706:files/ball_analyzer.py``` |

### 2.3 Live-disk evidence (`find` corpus)

Representative **`20260430_195352`** (215 subdirs):

- **`d001`:** `delivery_window.mp4`, `layer2.json`, **`window_debug.json`**, `replay/`, **`predictions.json`**
- **`d180`:** **`layer2.json`** present (spot-check)

Warmup-only sessions same day (**short capture / restarts**) also exist:  
`20260430_193952/` (**1** delivery), **`20260430_195036/`** (**3**), **`20260430_194341/`** (**6**).

### 2.4 Tee vs artifacts

Sampled **`pipeline-2026-04-30-gt-rcb-live.log`** contained **no** string hits for **`window_debug`** literal path or **`layer2.json`** pathname — unsurprising (**paths not echoed** at INFO in tee grep). Artifact presence confirms **ENABLED**, not **`DISABLED`**.

**Phase A verdict:** **ENABLED.**

---

## 3. Score-event coverage measurement

### 3.1 Event inventory method (STOP **S2** — heterogeneous tags)

|Tee signal|Meaning|
|----------|-------|
|`[DELIVERY ENQUEUED]`|Async path accepted & worker scheduled ```9784:9791:files/test_pipeline.py```|
|`DETAIL \| … \| ball_event=…`|Ball detector surfaced an event row on frame log|
|`ball_event=MULTI_BALL`, `DRS_NOT_OUT`|Present in **`DETAIL`** · excluded from enqueue eligibility parity below|

**Eligible-for-enqueue approximation** ≡ **non-placeholder `DETAIL` ball_event rows − `MULTI_BALL` − `DRS_NOT_OUT`** — aligns with enqueue gate taxonomy (MULTI aggregates; DRS bookkeeping).

### 3.2 GT-RCB: analyzer restart ⇒ two populations

|`line_no` range|`[DELIVERY ENQUEUED]`|Notes|
|--:|--:|-----|
|`1 .. 1222`|**3**|Warm start / abbreviated capture preceding second boot|
|`1223 .. EOF`|**215**|Second session **restarts delivery counter (`dnum=1`)** at **19:55:19** (~line **1223**)|

**Totals:** **`218`** `DELIVERY ENQUEUED` tee lines (**matches** naive grep count).

Observed **`DETAIL` populations:**

|Population|`DETAIL` ball rows|Eligible (`−MULTI −DRS_NO`)|Δ vs enqueue|
|-----------|--:|--:|--:|
| Full file | 228 | **218** | **0** |
|**Steady `≥1223`**|225|**215**|**215** vs **215** ✅|

### 3.3 Per-over DETAIL-vs-expected table caveat

Grouping enqueues by **`int(AFTER overs)` from same-frame `DETAIL`** only matched **`173`** of **`215`** enqueues (**42** lacks same-`Fx` **`DETAIL` overs** linkage — AdaptiveSleep drift / alternating `VISION` vs `TEST` cadence STOP **telemetry gap**).

**Because integer over buckets mingle innings once batting side flips**, a literal **"| Over.x | Expected 6 | … |"** table without innings segmentation would mis-attribute (histogram showed impossible counts like **`10–15`** enqueues/`int_ov` slice — duplication across innings mapped into same **`int`** bucket).

**Actionable aggregation instead:** steady-session **global parity row**

| Segment | Descriptor | Deliveries (enqueue) |
|--------|-------------|---------------------|
| A | preamble (`line<1223`) | **3** |
| B | steady (`line≥1223`) | **215** |

### 3.4 Cross-match: MI-SRH (Apr 29) tee — innings segmentation verification

Whole-file tally (same as prior audit row):

| Metric | Count |
|--------|-------|
| `DETAIL` ball_event rows | **127** |
| Eligible (−MULTI −`DRS_NOT_OUT`) | **120** |
| `[DELIVERY ENQUEUED]` | **120** |
| Δ (eligible − enqueue) | **0** |

Public scorecard ([ESPNcricinfo, MI vs SRH, Apr 29 2026](https://www.espncricinfo.com/series/ipl-2026-1510719/mumbai-indians-vs-sunrisers-hyderabad-41st-match-1529284/full-scorecard)): MI **243/5 (20.0 ov)** → **120** legal balls (fractional-over tally); SRH chase **249/4 (18.4 ov)** → **112** balls; combined **232** balls if both innings counted.

#### Appendix — evidence from `logs/pipeline-2026-04-29-194416-mi-srh-live.log`

**A. Innings boundary / chase context in tee**

- Exploratory `grep` over **`INNINGS` / `innings_change` / “second innings”**-style literals → **no dedicated transition log token** surfaced (empty hits in this corpus pass).
- **Chase-facing state appears before SRH takeover:** First **`DETAIL`** with **`AFTER_innings=2`** observed at **`line ≈28645`** (`F2695`), already with **`AFTER_target=244`** but **`batting_team=Mumbai Indians`** and scorer still reflecting **MI batters** (innings-index flip **ahead** of stable strip resolution — treat as **ambiguous transition window**).
- **Clear chase strip + SRH batting identity:** First **`DETAIL`** with **`batting_team=Sunrisers Hyderabad`** at **`line ≈31498`** (`F2998`, ~21:57:40), scout strip **`SRH 14-0 (1.3)`**, **`AFTER_target=244`**, **`AFTER_innings=2`**.

**B. Score progression**

- **`AFTER_score=243-5(20.0)`** is reached repeatedly in **`DETAIL`** rows in the **`line ≈26677–27320`** band — matches **card MI total** (**243/5**).
- Tee **does not** evolve to SRH **249/4**; chronologically later **`DETAIL`** tail (e.g. ~**22:19**, `F3547` region) remains on **SRH batting** but **`AFTER_score` stays “frozen” (~`74–0` class)** while overlays show **`FRAME_POISONED`** / contradictory strips — consistent with **mid-chase truncation + graphics confusion**, **not** a completed chase scorecard replica.

**C. Batting team resolution**

- Unique **`batting_team=`** values on **`DETAIL`** lines: **`Mumbai Indians`** and **`Sunrisers Hyderabad`** only (sorted-unique parse over file).
- **Enqueue split (operational segmentation):** **`[DELIVERY ENQUEUED]`** lines **`104`** with **`line_no < 31498`** vs **`16`** with **`line_no ≥ 31498`** (boundary = first **`batting_team=Sunrisers Hyderabad`** **`DETAIL`** above). Total enqueues **`120`**.

#### Verdict (replaces prior if/else speculation)

| User label | Applies? | Reasoning |
|------------|----------|-----------|
| **Verdict 1** (tee = MI innings only; **120 ≈ ~100%** vs **~120-ball** denominator) | **No** | **Both** **`batting_team`** values occur; **`AFTER_target=244`** and SRH-positive strips appear; **16/120** enqueues fall after SRH **`batting_team`** onset. |
| **Verdict 2** (interpret **120** vs **full-match card ~232**) | **Yes (headline cross-match)** | **`120 / 232 ≈ 51.7%`** — the **~50-point** swing vs a **MI-only ~100%** reading is **not** “MI-only tee”; it reflects **under-coverage vs combined innings** on the **card denominator**. |
| **Verdict 3** (partial / quantify segment) | **Yes (refinement)** | Inside the tee, **MI phase dominates enqueues** (**~104**) but **SRH chase is only lightly touched** (**~16**); vs nominal **112** chase balls that is **`≈14%`**, and the log **ends without** SRH’s **249/4** terminal state. |

**Net:** Internal **BED→enqueue** parity **`120 = 120`** remains **exact** for **whatever** this run’s **eligible `DETAIL`** population is. **Cross-match:** do **not** interpret **120** as evidence of **~100%** coverage of **both** innings; use **`≈52%`** vs **232** unless a **narrower** tee segment denominator is justified.

#### PBKS-RR cross-match verification

**Evidence source:** **`logs/pipeline-2026-04-28-pbks-rr-live.log`**.  
Broadcast setup (tee): **`=== TEAMS SET: Punjab Kings batting (inn 1) vs Rajasthan Royals bowling ===`** (**RR chase second**).

**A. Innings transition (`batting_team` authoritative, per MI-SRH precedent)**

| Signal | Approx. log line | Notes |
|--------|-----------------|-------|
| First **`DETAIL`** with **`AFTER_innings=2`** | **`≈28658`** (`F2599`) | Already **`AFTER_target=223`**, **`AFTER_score=222-5`**, **`batting_team=Punjab Kings`** — innings index flips **before** stable **`batting_team`** handoff (**same ambiguity class** as MI-SRH). |
| First **`DETAIL`** with **`batting_team=Rajasthan Royals`** (**`CHASE_BOUNDARY`**) | **`≈37378`** (`F3608`) | Scout **`RR 93-1 (7.3)`**, **`AFTER_target=223`**, **`AFTER_innings=2`** — authoritative **RR-chase onset** for pre/post enqueue split. |

**B. Enqueue totals + split (@ `CHASE_BOUNDARY` = **37378**)**

| Bucket | **`[DELIVERY ENQUEUED]`** count |
|--------|--------------------------------:|
| **Pre-chase** (`line_no` **<** `CHASE_BOUNDARY`) | **118** |
| **Chase-from-boundary onward** (`line_no` **≥** `CHASE_BOUNDARY`) | **24** |
| **Whole tee** | **142** |

**C. Scorecard reference** ([ESPNcricinfo, PBKS vs RR, Apr 28 2026](https://www.espncricinfo.com/series/ipl-2026-1510719/punjab-kings-vs-rajasthan-royals-40th-match-1529283/full-scorecard))

| Innings | Batting side | Overs (card) | Legal balls proxy (fractional tally) |
|---------|---------------|--------------|--------------------------------------|
| 1 | **Punjab Kings** | **20.0** | **120** |
| 2 (**chase**) | **Rajasthan Royals** | **19.2** | **116** (**`19 × 6 + 2`**) |
| Combined | — | — | **`236`** |

**Alignment:** **`118`** pre-chase enqueues vs **`120`** inning-1 card balls ⇒ **`≈98%`** (**innings‑1‑heavy**, small shortfall vs MI-SRH-perfect first block). **`24`** chase enqueues vs **`116`** ⇒ **`24/116 ≈ 20.7%`** (same **severe under-density** magnitude class as MI-SRH **`16/112 ≈ 14.3%`**).

**D. Score progression sanity (tee tail)**

- Last enqueues (**`dnum=140–142`**) arrive ~**22:15–22:17**; final sampled **`DETAIL`** tail shows **`batting_team=Rajasthan Royals`**, scout strip around **`RR 131–132/132-3`**, **`AFTER_score` ~`131–132-3`** — **does not reach** official chase line **228/4 (19.2 ov)** (**tee ends mid‑chase**).
- **`FRAME_POISONED`** markers appear on late **`DETAIL`** rows (**e.g.** `scorer_changes=['FRAME_POISONED:0']` adjacent to contradictory strips), matching **graphic-breakdown / confusion** pathology seen on MI‑SRH tail.

**Verdict classification**

| Label | Applies? | Reason |
|-------|----------|--------|
| **T1 — Truncation pattern confirmed** | **Yes** | Chase enqueue rate **`≈21%`** of **`116`** expected (**`< 30%` threshold**); first-innings enqueue density **much higher** ⇒ **dual-match confirmation** alongside MI-SRH. |
| **T2 — Healthy chase** | **No** | Far below **`>70%`** chase parity. |
| **T3 — Mild partial** | **No** | Rate is **below 30%**, not **`30–70%`**. |

**Implication:** Treat **chase-side Path‑1 starvation** as a **repeatable cross-match phenomenon** (**not an MI‑SRH singleton**); **Cause 5** (or equivalent chase-segment remediation) retains **high leverage** pending causal drill-down.

---

## 4. Failure-class breakdown (missed-Path-1-trigger lens)

Against **steady GT-RCB** session where **enqueue/eligible DETAIL parity = 100%**:

| Class | Operational meaning | Approx count (steady session) | Evidence (frame / line) |
|-------|---------------------|------------------------------|---------------------------|
| **M1** | Dot / incremental miss (**no `ball_event`** where card advances) | **0** Δ between eligible **`DETAIL` and enqueue — no silent gap surfaced in parity pass | — |
| **M2** | Aggregated **`MULTI_BALL`** skips per-ball enqueue | **6** post-restart `DETAIL` rows | **`F273`** (~log line **3777**), **`F986`** (~**11597**); commentary prelude shows **`Δballs=2`** / **`3`** |
| **M3** | Wicket surfaced but enqueue skipped | **0** observed | `WICKET` / **`WICKET_LATE`** both appear ineligible-adjusted numerator and match gates |
| **M4** | Other / bookkeeping · **`DRS_NOT_OUT`** | **4** | By design **`DRS_NOT_OUT`** excluded from eligible-enqueue equality |

**Dominant latent gap vs true scorecard-perfect Path 1 ceiling:** **`M2` / `MULTI_BALL`** (aggregated skips) matches architecture notes in **`multi_ball_decomposition_design.md`**.

Warm **preamble** (**3 vs 218 eligible**) is **cold-start / truncated capture** (**not** scorer steady-state pathology).

---

## 5. Phantom-event analysis

| Definition | Computation (GT-RCB steady) |
|------------|-----------------------------|
|**Official ball proxy**|GT **`15.5` ov ⇒ `95` balls** · RCB **`19.2` ov ⇒ `116` balls** · **Σ `≈211`** ([ESPNcricinfo GT vs RCB Match 42, Apr 30 2026](https://www.espncricinfo.com/series/ipl-2026-1510719/gujarat-titans-vs-royal-challengers-bengaluru-42nd-match-1529285/full-scorecard))|
|Pipeline enqueue (steady)|**215**|
|Surplus rate|**`(215−211)/215 ≈ 1.9%`** assuming card balls = strict legal total without rebowl granularity|

**Verdict:** **below 5%** — investigate only if corroborated with umpire-ball-count export; attribution may invert once **`MULTI` hidden balls** added to denominator.

---

## 6. Recommendations

1. **Path 1b window audit next** — use **`files/logs/deliveries/20260430_195352/`** as canonical artifact tree paired with **`[DELIVERY ENQUEUED]` dnum**.
2. **MULTI-ball ceiling program** — parse **`Δballs`** adjacent commentary rows against ESPNC **ball-by-ball where available**.
3. **Tee ergonomics** — optional **one-line `[ARTIFACT]`** log at enqueue with **`d`, `delivery_dir`** to kill manual **`dnum ↔ folder`** joins (explicitly outside this investigation scope).

**`save_dir` change:** none required — already materialises disk.

---

## 7. Limitations

1. STOP **S1 partial:** IPL **extras / free-hit / rebowled wides** distort naive **`overs fractional → balls`** heuristic; denominators cite **publisher overs** — not ball-by-ball umpire ledger.
2. STOP **S2:** **`DETAIL` vs `DELIVERY`** row timing alignment incomplete (**42**/215 unmatched overs).
3. **Innings tagging not carried on `DELIVERY ENQUEUED`** line alone — segmentation required external **`STATE`/scoreboard cues`.
4. **Artifact corpora gitignored/noisy paths** (`logs/` root vs `files/logs/deliveries/`) — reproducibility depends on preserving **`files/logs/deliveries/**`** tree from the capture host.
5. **Public web metadata** (**2026** season) harvested **2026**-**05**-**01** browsing — match detail may revise.

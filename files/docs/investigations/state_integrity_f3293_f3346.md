# State integrity — forensic investigation (F3293→F3346, GT vs RCB chase)

**Phase:** Depth 2 — log reading, code tracing, hypothesis ranking. **No fix proposals.**

**Artifacts:** IPL 2026 Match 42 (GT vs RCB), evening tee `logs/pipeline-2026-04-30-gt-rcb-live.log`. Primary narrative anchor: [`match_postmortem_data_gt_rcb_20260430.md`](match_postmortem_data_gt_rcb_20260430.md) §3.D (lines **33709** → **34017**).

---

## §1 Executive summary

**Window:** Bracket timestamps **22:00:50** (`F3293`) through **22:02:41** (`F3346`) — **111 s**, **53** frame IDs (`3346 − 3293`).

**Observed pipeline arc (corrected vs §3.D headline):**

1. **Strip vs tracker mismatch:** Scout/extractor repeatedly reported **GT 57-1 / 57-2 (≈5 ov)** while `scoreboard._inn` held **49-1 (3.5)** — triggering **`[POISONED]`** (`delta=8`) and **`FRAME_POISONED`** on DETAIL (`scorer_changes=['FRAME_POISONED:57']`). This begins **before** `F3293` (e.g. **`F3292`** line **33672–33673**, **`F3291`** line **33653**).

2. **POISON-STREAK → POISON-RECAL:** After **five** consecutive poison-class reads (threshold **`_POISON_RECAL_THRESHOLD = 5`**, `test_pipeline.py:5291`), **`[POISON-RECAL]`** fires at **`F3296`** — pipeline line **33734** — declaring tracker **49** “stale”, **clearing** `scoreboard._inn["score"|"wickets"|"overs"]` to **`None`**, and calling **`score_mgr.full_reset`** → **`FORCE_COLD_START_RECALIBRATION`** (lines **33734–33736**).

3. **DETAIL `AFTER_score=None-None(None)`:** From **`F3296`** onward through **`F3315`**, DETAIL rows show **empty scoreboard innings snapshot** — consistent with tracker reset + poisoned intermediate frames **not** repopulating `_inn` score via normal scorer apply path.

4. **Recovery at `F3346`:** Clean-enough strip **`GT 57-2 (5)`** with **`scorer_changes=['score→57', 'overs→5', 'wickets→2', …]`** (line **34017**). **`ScoreManager`** seeds cold-start candidate **`57/2 (5.0)`** (line **34004**) and emits **`MULTI_BALL`** — commentary **`Δballs=7`** (line **33996**) matching **3.5 → 5.0** overs (**9** balls − **2** fractional balls already bowled in 3rd over → **7** legal-ball gap in SM’s base-6 accounting).

5. **Individual ball events:** **No** non-em-dash `ball_event` on DETAIL rows **between** **`F3293`** and **`F3346`** in this tee slice — **only** **`MULTI_BALL`** at **`F3346`**. Normal per-ball **`1_RUNS`** resumes at **`F3348`** (line **34111**).

**Pattern disposition (preview):** **Pattern Y (multiple interacting subsystems)** — **HIGH** plausibility: poison delta guard, POISON-RECAL, SM cold-start, strip row misalignment, graphic/no-strip skips, and roster scrubbing all appear in logs. **Pattern X** alone (strip OCR hallucination → trust collapse) is **insufficient** — logs show **deliberate tracker wipe** (`POISON-RECAL`), not only “reject strip until trust returns”. **Pattern Z** (instrumentation-only) — **LOW**: intermediate machinery is logged (`POISON-RECAL`, `AFTER_score=None`, `[SM] cold-start candidate`).

**Next investigation focus:** Whether **POISON-RECAL** was **appropriate** here (broadcast truly at ~57 while tracker stuck at 49) vs **harmful** (numerically stable strip wrong-footed a correct tracker). Replay needs ball-by-ball broadcast truth for **3.5→5.0** and wicket identity (**Sudharsan** vs roster noise).

---

## §2 Window timeline (Phase A)

### A1–A2 Extraction sanity

| Step | Result |
|------|--------|
| `awk 'NR>=33700 && NR<=34050' logs/pipeline-2026-04-30-gt-rcb-live.log` | **351** lines — **covers** brackets **22:00:xx–22:02:41** including **`F3346`** (**stop-condition S1 cleared**). |
| `grep -E "F329[3-9]|F33…|F3346" files/logs/machine-1-2026-04-30.log` | **No matches** in this environment (**stop-condition S2** — DWR correlation **absent**; proceed without machine-1 frame bridge). |

### A3 Per-frame table (DETAIL rows + milestones)

DETAIL lines are **sparse** (~**1 per ~6–25** frames in this stretch). Rows below cite **`logs/pipeline-2026-04-30-gt-rcb-live.log`** line numbers.

| Frame | Tee line | Wall clock | `[SCOUT]` cam / phase (when present) | scout STRIP headline | FRAME_POISONED / scorer | AFTER_score | ball_event | Notes |
|------:|---------:|------------|--------------------------------------|----------------------|-------------------------|-------------|------------|-------|
| F3291 | 33653 | 22:00:45 | (see SCOUT block ~33655 region) | GT **57-1 (4.5)** … Bhuvneshwar | `FRAME_POISONED:57` | **49-1(3.5)** | — | Strip already **+8** vs tracker; **`POISONED`** path active before F3293. |
| F3292 | 33681 | 22:00:48 | closeup / between_play | GT **57-1 (4.5)** | `FRAME_POISONED:57` | **49-1(3.5)** | — | **`[STRIP-ROWS-MISALIGNED]`** **33669** Gill **43 vs 6**; **`[POISON-STREAK]`** **33673** `3/5`. |
| F3293 | 33709 | 22:00:50 | closeup / between_play (**33682**) | GT **57-1** — **Gill 6(4)** vs earlier **43** | `FRAME_POISONED:57` | **49-1(3.5)** | — | Postmortem §3.D anchor; **intra-strip Gill inconsistency** across adjacent frames. |
| F3294 | — | 22:00:53 | — | — | — | — | — | **No DETAIL**; **No-strip skip** (**33711**). |
| F3295 | — | 22:00:54 | **graphic** / graphic (**33713**) | — | — | — | — | **`CAM-GRAPHIC-FAST-PATH-REJECT` G6_score_window**; **dead-time skip** (**33714–33715**). |
| F3296 | 33751 | 22:01:00 | closeup / between_play (**33718**) | GT **57-2 (5)** | `FRAME_POISONED:57` | **`None`** | — | **`[POISON-STREAK] 5/5`** **33733** → **`[POISON-RECAL]`** **33734** → SM **`full_reset`** **33736**. |
| F3297 | 33778 | 22:01:04 | cam=None / between_play | GT **57-2 (5)** … Bhuvneshwar **2-20** | `FRAME_POISONED:57` | **`None`** | — | **`[STRIP-ROWS-MISALIGNED]`** **33760**. |
| F3298 | 33804 | 22:01:09 | closeup / between_play | GT **57-2 (5)** … Bhuvneshwar | `FRAME_POISONED:57` | **`None`** | — | **`[STRIP-ROWS-MISALIGNED]`** **33787**. |
| F3299 | — | 22:01:12 | **graphic** (**33806**) | — | — | — | — | Graphic reject + dead-time (**33807–33808**). |
| F3313 | 33864 | 22:01:26 | closeup / between_play **`digits=False`** (**33836–33837**) | **`GT 0-0 (0.0)`** | *(none)* | **`None`** | — | **`scorer_changes=[]`** — extractor/template spike; mid-innings guard context lines **6828–6841** (`test_pipeline.py`). |
| F3315 | 33893 | 22:01:43 | closeup / between_play | GT **57-2 (5)** … Gill **43** … Tewatia **3** | `FRAME_POISONED:57` | **`None`** | — | **`[STRIP-ROWS-MISALIGNED]`** **33881**. |
| … | … | … | *(many frames: ads, pixskip, no-strip — see §8)* | … | … | … | … | No DETAIL rows **33751→34017** gap except **`F3346`**. |
| **F3346** | **34017** | **22:02:41** | **bowlers_end** / between_play (**33964**) | **GT 57-2 (5)** … **Washington** … Hazlewood **0-37** | **Clean apply** `score→57…` | **57-2(5.0)** | **`MULTI_BALL`** | **`[WICKET-TRACK]`** **33992** `wkts 0→2`; commentary **`Δballs=7`** **33996**; **`[SM] cold-start candidate seeded`** **34004**. |
| F3347 | 34061 | 22:02:48 | bowlers_end / **release** | GT **57-2 (5)** — new strip drift | scorer deltas | **57-2(5.0)** | — | Outside **`NR<=34050`** excerpt — listed for continuity. |
| F3348 | 34111 | 22:02:54 | closeup | GT **58-2 (5.1)** | normal updates | **58-2(5.1)** | **`1_RUNS`** | **`[DELIVERY ENQUEUED]`** **34096** `dnum=105`; normal cadence resumes. |

**State transitions (Phase A5 answers):**

| Question | Answer |
|----------|--------|
| When did **`AFTER_score` first change** off **49-1(3.5)**? | **`F3346`** (line **34017**) → **57-2(5.0)** — **no** intermediate numeric `AFTER_score` on DETAIL between **49** and **57**. |
| When did **`ball_event=MULTI_BALL`** fire? | **`F3346`** — line **34017**; echoed **`[BALL ?] MULTI_BALL`** **33996**. |
| **`scout=STRIP` at `MULTI_BALL`?** | **`GT 57-2 (5)`** — line **34017**. |
| **`FRAME_POISONED` at `MULTI_BALL`?** | **No** — scorer_changes show substantive **`score→57`**, **`wickets→2`**, etc. |
| Other **`ball_event`** types inside **33700–34050** DETAIL slice? | **None** except **`MULTI_BALL`** at **`F3346`**. (**stop-condition S5** — postmortem claim holds on DETAIL grep.) |
| **`[STRIPS-ROW-MISALIGNED]` / `[STRIP-ROWS-MISALIGNED]`** | **33729, 33760, 33787, 33881** — all **`popped=batters`**, **`preserved=score,match_overs,bowler`**, Gill **`strip_runs=43`** vs **`card_runs=6`**. |
| **`[TEAM-ATTRIBUTION-POISON-RATE]`** | **None** in **33700–34050** grep window (telemetry fires on **`inn_break_pending`** cadence elsewhere — **`test_pipeline.py:8918–8929`**). |

### A4 Frame artifact cross-reference (`files/debug_frames_archive/2026-04-30_193643/`)

**Scope:** User-supplied suffix histogram (**23** frames **F3300–F3349**) matches filesystem listing — **`f3314_ad.jpg`**, **`f3346_pixskip.jpg`**, **`f3347_graphic.jpg`**, etc.

**Log vs suffix divergences (examples):**

| Archive file | Pipeline processing (approx.) |
|--------------|--------------------------------|
| **`f3346_pixskip.jpg`** | **`F3346`** processed as **`SCOREBOARD`** DETAIL (`tag=SCOREBOARD`) — suffix **`pixskip`** names sampler/policy; **not** always equal to **`tag=`**. |
| **`f3347_graphic.jpg`** | **`F3347`** **`SCOREBOARD`** DETAIL (**34061**) while scout strip lists live batters — **`graphic`** may reflect upstream **`cam=graphic`** epochs elsewhere; correlation requires frame-index join beyond this doc. |
| **`f3313_scoreboard.jpg`** | Aligns with **`F3313`** scoreboard row (**33864**) — trivial **`GT 0-0 (0.0)`** strip contradiction vs chase. |

**Visual sampling:** JPGs exist on disk (**~186–232 KB** samples **`stat`**); **no vision re-read** performed in this phase — cite filenames only (**§8 limitation**).

### A5 Subsystem contribution sketch

| Subsystem | Evidence |
|-----------|----------|
| **Poison delta guard + streak + POISON-RECAL** | **`[POISONED]`**, **`[POISON-STREAK]`**, **`[POISON-RECAL]`** **33734**; tracker cleared **`7958–7966`** (`test_pipeline.py`). |
| **Strip row alignment guard** | **`[STRIP-ROWS-MISALIGNED]`** — preserves headline score while destroying batter fidelity — fuels **`WS-SCRUB`** / roster contradiction (**3293** shows **`AFTER_non=Sai Sudharsan`** vs strip batters **Buttler**/**Gill** variance). |
| **Graphic fast-path / dead-time** | **`CAM-GRAPHIC-FAST-PATH-REJECT`**, **`dead-time skip`** (**33714–33715**, **33807–33808**). |
| **ScoreManager cold-start + MULTI_BALL** | **`FORCE_COLD_START_RECALIBRATION`** **33736**; **`cold-start candidate seeded`** **34004**; **`MULTI_BALL`** **`score_manager.py:2291–2298`**. |
| **Vision / Scout** | **`[SCOUT]`** latency + **`cam=`**/`phase=`**33836–33964** — **`eyes/vision.py`** emits **`[SCOUT]`** (**371–378**). |

---

## §3 Code path traces (Phase B)

### B1 `MULTI_BALL` emission

**Site:** `files/score_manager.py` **`_infer_event`**:

```2291:2298:files/score_manager.py
        # MULTI_BALL: skipped deliveries (use ball count, not decimal overs)
        new_overs = card.get("overs") or self.overs or 0
        old_overs = prev.get("overs") or 0
        d_balls = self._overs_to_balls(new_overs) - self._overs_to_balls(old_overs)
        if d_balls > 1:
            return {"type": "MULTI_BALL", "runs": d_score,
                    "overs_skipped": d_overs, "wickets_in_gap": d_wickets,
                    "balls_skipped": d_balls, "striker": striker}
```

**Conditions:** **`d_balls > 1`** after **`validate_diff`** passes (**1529–1548**) — i.e. **legal-ball gap > 1** between **`prev`** snapshot and incoming **`card`**.

**Inputs:** **`prev`** captured **before** **`_accept_update`** (**1589–1606**); **`card`** carries overs/score/wickets from extractor/scorer-fed pipeline.

**Relation to strip trust / FRAME_POISONED:** **`MULTI_BALL` classification lives entirely in `ScoreManager`** — **not** gated by **`_FRAME_POISONED_STRIP_TRUST_THRESHOLD`**. That constant (**`test_pipeline.py:4827`**) is **`telemetry-only (does not gate behaviour)`** per adjacent comment (**4823–4827**).

**Telemetry:** Commentary **`[BALL ?] MULTI_BALL | 5.0 +8 runs (Δballs=7)`** — tee line **33996**.

### B2 `FRAME_POISONED` → strip handling

**Pipeline emission:** When **`_frame_poisoned`** is true, scorer branch **replaces** changes:

```8931:8948:files/test_pipeline.py
            if _frame_poisoned:
                # Fix 4: gate consensus on `_frame_poisoned`. Poisoned
                # readings ARE NOT evidence — they're discarded data
                # from a frame our guards have judged untrustworthy.
                ...
                changes = [f"FRAME_POISONED:{_ext_score_raw}"]
                ...
                if _correction_pending is not None:
                    _correction_pending = None
                    _correction_count = 0
```

**Poison delta threshold:** **`abs(ext − tracker) > 7`** triggers **`_frame_poisoned`** (**7896–7906**) — **`delta=8`** case (**33672**, **33732**) clearly qualifies.

**Does poison “reject strip entirely”?** **For scorer-driven mutations this frame — yes** (`FRAME_POISONED` token replaces **`apply_scorer_decision`** output). Separately, **`STRIP-ROWS-MISALIGNED`** may **strip batters** while **preserving score/match_overs/bowler** (**3020–3026** `test_pipeline.py`) — partial ingestion **before** scorer.

**Threshold `0.56`:** Rolling deque **`_poisoned_in_window`** feeds **`[TEAM-ATTRIBUTION-POISON-RATE]`** logs (**8918–8929**) — **does not alter** **`FRAME_POISONED`** branching (**confirmed §B1**).

### B3 Score reconciliation (strip ahead of tracker)

**Mechanisms observed in-window:**

1. **Consensus / correction loops** (`_CORRECTION_CONFIRM`, **`apply_scorer_decision`** **`test_pipeline.py:3111+`**) — **not** exercised while **`FRAME_POISONED`** short-circuits changes (**8942**).

2. **POISON-RECAL escape:** Interprets **monotonic poison streak** as **stuck tracker**, **clears** `_inn` score axes (**7958–7960**) + **`score_mgr.full_reset`** (**7962–7966**).

3. **Cold-start seeding:** **`[SM] cold-start candidate seeded 57/2 (5.0) — streak 1/3`** — line **34004** — SM accepts strip-aligned card after prolonged **`None`** tracker state.

**`scorer_decision_schema.py`:** No **`MULTI_BALL`** symbol hits — schema feeds **`process_scorer_decision_schema`** inside **`apply_scorer_decision`** (**3055–3056**) for LLM-shaped fields; **`MULTI_BALL`** remains **`ScoreManager`** event taxonomy (**§B1**).

### B4 Wicket attribution vs `MULTI_BALL`

**`MULTI_BALL` path wins when `d_balls > 1`** — **`_infer_wicket`** is **not** called for that frame’s primary classification (**2295 vs 2305–2307** ordering).

**Bundle:** Event dict carries **`wickets_in_gap`** (**2297**) — wicket physics folded into **multi-ball gap** semantics rather than discrete **`WICKET`** event type.

**`[WICKET-TRACK]`:** **`33992`** reports **`wkts 0→2`** — reflects **`scoreboard._inn`** wicket field jumping when scorer commits **`wickets→2`** alongside cleared baseline (**cold-start`), **not** proof of **two simultaneous dismissals**.

**Named dismissal (“Sudharsan”):** Not asserted by **`MULTI_BALL`** line — roster telemetry shows **`[WS-SCRUB]`** rejecting **`Sai Sudharsan`** as **`status_out`** near **`F3293`** (**33707**) while **`AFTER_non`** still surfaces **`Sai Sudharsan`** on DETAIL (**33709**) — **human attribution remains ambiguous** without replay.

---

## §4 Pattern evaluation (Phase C)

### Pattern X — Single root cause (strip OCR poisoning)

| FOR | AGAINST |
|-----|---------|
| Repeated **`FRAME_POISONED:57`** while tracker **49** (**33709**, **33751**…). | **`POISON-RECAL`** **explicitly prefers repeated strip “57” over tracker “49”** (**33734**) — if strip were purely hallucinated, mechanism **amplifies** wrong baseline. |
| **`MULTI_BALL`** bundles skipped balls — documented SM behaviour (**§B1**). | **`STRIP-ROWS-MISALIGNED`** shows **structural strip/card mismatch**, not only OCR numeric noise (**33729**). |
| Filler-heavy window (**graphic/ad/no-strip**) per suffix histogram — aligns with **`CAM-GRAPHIC…`** / skips (**§A3**). | Graphic rejects explain **cadence**, **not** the numeric **49 vs 57** staleness story **alone**. |

**Ranking:** **MEDIUM** — necessary **component** but **not sufficient** as lone root cause.

### Pattern Y — Multiple independent / interacting failures

| FOR | AGAINST |
|-----|---------|
| **`POISON-RECAL`** + **SM cold-start** + **`MULTI_BALL`** + row misalignment + **0-0 strip** spike (**F3313**) co-occur with timestamps — **parsimony is worse**, **explanatory power is higher**. | More moving parts → harder replay confirmation. |
| Postmortem §9 **correlation hypothesis** stays **non-final** — matches observed **multi-tag** stew (**[`match_postmortem_data_gt_rcb_20260430.md`](match_postmortem_data_gt_rcb_20260430.md#L218-L220)**). | Doesn’t pinpoint **single code owner** for remediation (investigation-only phase). |

**Ranking:** **HIGH** — best fit to **logged mechanisms**.

### Pattern Z — Instrumentation-only divergence

| FOR | AGAINST |
|-----|---------|
| **`AFTER_score=None`** might **look** like “logging gap” — actually encodes **real `None` tracker fields post-POISON-RECAL**. | Explicit **`[POISON-RECAL]`**, **`FORCE_COLD_START`**, **`MULTI_BALL`** lines (**33734–33736**, **33996**) — hard to dismiss as grep miss. |

**Ranking:** **LOW** (**stop-condition S5** reinforces).

---

## §5 Pipeline vs broadcast comparison (Phase D2)

**User-provided broadcast priors (not re-derived):** Powerplay scoring; **Sudharsan** dismissal in Hazlewood/Bhuvneshwar spell window; **Gill** explosive strike rate.

**Pipeline at `F3346`:** **57-2 (5.0)** — net **+8 runs**, **+1 wicket**, **+7** scored legal-ball equivalents vs prior tracker **49-1 (3.5)** **if** those endpoints bracket truth.

**Gap assessment:**

| Dimension | Assessment |
|-----------|------------|
| **Runs (+8)** | **Plausible** for **~7** missed legal-ball edges + boundary stacking in powerplay — **needs sealed ball chart**. |
| **Wickets (+1 net)** | **Plausible** if **second wicket is Sudharsan** — pipeline **does not name** wicket event inside **`MULTI_BALL`** DETAIL row. |
| **Simultaneous `wkts 0→2` telemetry** | **Likely artefact** of **cold-start reset** clearing wicket axis — **not** proof broadcast saw **two wickets** in one stroke. |

**Phantom signals:** **`GT 0-0 (0.0)`** strip at **`F3313`** (**33864**) — classic **graphic/template intrusion** shape; **`MULTI_BALL`** itself is **real telemetry**, not phantom — question is **sporting correctness**.

---

## §6 Hypothesis disposition + confidence

| Candidate | Verdict | Confidence |
|-----------|---------|------------|
| **Pattern Y** | **Primary** — poison streak/recal **+** SM cold-start **+** strip structural misalignment **+** ingestion skips explain timeline **without** invoking silent per-ball logging. | **Medium–high** (bounded by absent sealed scorecard slice). |
| **Pattern X** | Contributing lens (**strip vs tracker**) but **incomplete**. | **Medium** |
| **Pattern Z** | **Rejected** for this window given **`POISON-RECAL`** / **`MULTI_BALL`** trails. | **Low** |

**To confirm definitively:**

1. Official ball-by-ball for **GT innings overs ~3.5–5.0** — validate **49→57** trajectory and **single** wicket vs **two**.
2. Replay **`F3283–F3350`** frames through analyzer harness — measure **`FRAME_POISONED`** rate **before** streak hits **5**.
3. Inspect **`score_mgr.full_reset`** + **`cold-start candidate`** streak (**`streak 1/3`** at **34004**) against archived extractor JSON — confirm **`57/2/5.0`** alignment **every** seed frame.

---

## §7 Recommendations for next investigation

| Priority | Focus | Estimate |
|---------|-------|----------|
| **P1** | **POISON-RECAL correctness**: When repeated strip **`57`** disagrees with tracker **`49`**, is tracker **always** “stale”? Edge cases: strip numeric stable but **rows misaligned** (**43 vs 6**). | **4–6 h** |
| **P2** | **Cold-start wicket axis**: Prevent **`wkts 0→2`** telemetry shock vs phased wicket ledger — separate investigation (**state**, not commentary-only). | **3–4 h** |
| **P3** | **`STRIP-ROWS-MISALIGNED` interaction**: Does popping batters while preserving score **inflate** poison streak false positives? | **3–5 h** |

**Lever disposition:** **`V6c/V6e`** Scout tuning stays **secondary** until **`P1`** resolves whether **`cam=` / phase** instability is causal vs downstream guards (**per backlog posture** [`match_postmortem_data_gt_rcb_20260430.md`](match_postmortem_data_gt_rcb_20260430.md#L223-L227)).

---

## §8 Limitations

- **23** archived JPGs vs **53** frames — non-uniform sampling (**pixskip/ad/graphic** skew).
- **Single-window** narrative — may not generalize to other **`MULTI_BALL`** bridges.
- **No mechanical replay** of frames through extraction/scorer (**investigation charter**).
- **`eyes/scoreboard.py`:** **`FRAME_POISONED`** string **not** emitted there — poisoning orchestrated in **`test_pipeline.py`** + **`eyes/vision.py`** Scout path (**§A5**).

---

## §9 Cross-references (file:line)

| Topic | Citation |
|-------|----------|
| Poison delta / streak / POISON-RECAL | `files/test_pipeline.py` **7874–7976**, **`_POISON_RECAL_THRESHOLD`** **5291** |
| FRAME_POISONED scorer short-circuit | `files/test_pipeline.py` **8931–8948** |
| P0-C threshold telemetry-only | `files/test_pipeline.py` **4823–4828**, **8918–8929** |
| MULTI_BALL inference | `files/score_manager.py` **2291–2298**, **2511–2515** (`_apply_event` branch) |
| Strip row misalignment guard | `files/test_pipeline.py` **3017–3026** |
| SM forced cold-start API doc | `files/score_manager.py` **1623–1651** |
| Scout emission | `files/eyes/vision.py` **371–378** |
| Pipeline anchors | `logs/pipeline-2026-04-30-gt-rcb-live.log` **33709**, **33734–33736**, **33992**, **33996**, **34004**, **34017**, **34111** |
| Postmortem anchors | [`match_postmortem_data_gt_rcb_20260430.md`](match_postmortem_data_gt_rcb_20260430.md) **§3.D**, **§9 correlation**, **§10 lines 33709→34017** |

---

### Stop-condition ledger (investigation-specific)

| ID | Resolution |
|----|------------|
| **S1** | Slice **33700–34050** **contains** documented anchors — extend to **34115** optionally for **`F3348`** continuity. |
| **S2** | **`machine-1`** frame grep **empty** — **no DWR join**. |
| **S3** | Archive **`2026-04-30_193643/`** matches investigation expectations. |
| **S4** | Actual dominant bridge mechanism includes **`POISON-RECAL`** — hypotheses updated (**§1**, **§4**). |
| **S5** | **No** intervening DETAIL **`ball_event`** types — aligns with postmortem; normal **`1_RUNS`** resumes **`F3348`**. |
| **S6** | **`POISON-RECAL` @ F3296** — flag as **high-signal finding** absent from §3.D two-line précis. |

---

*Authored as Phase 1 Depth-2 forensic memo — **no production edits**.*

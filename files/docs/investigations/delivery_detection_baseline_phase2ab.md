# Delivery detection baseline — Phase 2A + 2B (RCB vs GT)

**Date:** 2026-04-30  
**Architecture reference:** `files/docs/investigations/delivery_extraction_audit.md` (#1a ball detector → #1b span assembly → #1c Layer 2 Qwen).

---

## 1. Executive summary

| Item | Value |
|------|--------|
| **Match** | Royal Challengers Bengaluru vs Gujarat Titans, **IPL 2025**, **Match 14**, **M. Chinnaswamy Stadium, Bengaluru**, **2 April 2025** (night; nominal **19:30 IST** start per scorecard). |
| **Run label `rc9`** | **Internal pipeline/run identifier** in filename `rcb_gt_rc9_commentary_203904.log`; **filename alone does not guarantee** alignment with Match 14 §3 (see §4.1). |
| **Ground-truth window** | **RCB innings**, **overs 5–10** inclusive (powerplay exit → middle-over rebuild). **§3 (Phase 2A) remains authoritative** — not revised here. |
| **Expected deliveries (scorecard)** | **36** (six overs × six balls each; **no wides/no-balls** in this window; **one leg bye** on ball **5.3** — still one **legal delivery**). |
| **Primary log artifact** | **Present:** `files/logs/runs/rcb_gt_rc9_commentary_203904.log` (**not** `logs/runs/…` at repo root). |
| **Fixture / innings vs §3** | **Mismatch.** DETAIL strips with `batting_team=Royal Challengers` show **`AFTER_innings=2` only** (no `AFTER_innings=1` RCB batting rows). **`match_info=IPL 2026`** appears on hundreds of DETAIL lines. This capture is **not** the RCB **first-innings** overs **5–10** ball list in §3. |
| **Pipeline emissions (§4.2 recipe)** | **127** lines matching the §4.2 `grep` pattern; **`60`** **`[DELIVERY ENQUEUED]`** globally in file. **`[DWR]`** literal lines: **0** (instrumentation or tag differs on this run). **`[THIS-OVER]`**: **67** lines. |
| **#1a vs §3 (overs 5–10)** | **Not measurable.** No log-derived pairing to §3 deliveries; apples-to-oranges if counts were forced. |
| **Log-local sanity (RCB chase, `ball_event_over` 5.0–10.6)** | **16** frames where same-frame DETAIL supplies `ball_event_over` in **[5.0, 10.6]** and **`[DELIVERY ENQUEUED]`** exists (**16/16** pairing on those frames). Coverage stops after **7.4** in this window (**no** 8.x–10.x RCB bat DETAIL balls in capture). **Gap:** **7.1** absent between **7.0** (F1485) and **7.2** (F1571). |
| **Outcome (A/B/C/D)** | **Unclassified for the Phase 2 hypothesis** (#1a vs §3). Evidence supports a separate concern: **wrong innings / wrong season metadata** for the labeled “Match 14 §3” experiment. |
| **Recommendation** | Seal a commentary log whose DETAIL/`match_info` **and** batter roster match **IPL 2025 Match 14 RCB innings 1** for overs **5–10**, or attach **explicit `match_id` + innings** in run metadata. Then re-run §4.2–§4.3 against §3. Until then: **do not** cite this `rc9` file as validating #1a on §3; **defer** Scout paste decisions that assume that linkage. |

---

## 2. Match identification

- **Competition:** Indian Premier League 2025.  
- **Fixture:** 14th Match (N), Bengaluru, April 02, 2025 — **RCB 169/8 (20.0 ov)** vs **GT 170/2 (17.5 ov)** — **GT won by 8 wickets**.  
- **Public scorecards:** [ESPNcricinfo full scorecard](https://www.espncricinfo.com/series/ipl-2025-1449924/royal-challengers-bengaluru-vs-gujarat-titans-14th-match-1473451/full-scorecard), [ESPNcricinfo ball-by-ball](https://www.espncricinfo.com/series/ipl-2025-1449924/royal-challengers-bengaluru-vs-gujarat-titans-14th-match-1473451/ball-by-ball-commentary).  
- **Innings for Phase 2A:** **RCB first innings** (GT elected to **field first** — scorecard Match Details).  
- **Log path (canonical in repo):** `files/logs/runs/rcb_gt_rc9_commentary_203904.log`. Verified: `ls files/logs/runs/rcb_gt*.log` lists this file. (**Incorrect path:** `logs/runs/…` at repo root — that directory is not the storage location used here.)

**Stop-and-route-back S3 (`rc9`):** `rc9` is treated as **operator run shorthand**, not ESPN match id (ESPN uses numeric match id **1473451**). Correspondence is **by teams + IPL 2025 Match 14 date/venue**, consistent with Scout docs referencing **`rcb_gt_f1455`**.

---

## 3. Ground truth (Phase 2A)

### 3.1 Window choice

**Overs 5–10** (RCB batting): crosses **end of mandatory powerplay** (scorecard notes powerplay **0.1–6.0**); includes **Rajat Patidar’s dismissal (6.2 ov)** and **Jitesh Sharma / Liam Livingstone** rebuild **without** spanning the later **Over 11.1 DRS** event (outside window). **Over 4.5 review** (Livingstone vs Siraj) is **before** ball **5.1** — does not distort the selected six-over slice (**S2 avoided**).

### 3.2 Primary sources for ball-by-ball

Ball-level narrative for **5.1–10.6** was reconstructed from **India Today** IPL 2025 live blog text (exported snapshot used for analysis; timestamps **IST** on each ball). Fall-of-wicket and match metadata cross-checked against **ESPNcricinfo** full scorecard (Patidar **lbw b Ishant** at **42/4**, **6.2 ov**).

### 3.3 Per-ball reference (RCB innings)

Notation: each row is **one delivery** for pipeline counting purposes (including leg bye).

**Over 5** (Prasidh Krishna; score **35/3 → 38/3**)

| Ball | Outcome |
|------|---------|
| 5.1 | 1 run (Patidar) |
| 5.2 | 0 — dot (Livingstone; beaten) |
| 5.3 | **Leg bye** — 1 bye off pads, batters cross **(1 delivery, extras: leg bye)** |
| 5.4 | 0 — dot (Patidar) |
| 5.5 | 0 — dot (Patidar) |
| 5.6 | 1 run (Patidar); **end powerplay 38/3** |

**Over 6** (Ishant Sharma; **38/3 → 48/4**)

| Ball | Outcome |
|------|---------|
| 6.1 | 4 runs (Patidar) |
| 6.2 | **Wicket** — Patidar **lbw** **42/4** |
| 6.3 | 0 — dot (Jitesh) |
| 6.4 | 0 — dot (Jitesh) |
| 6.5 | 4 runs (Jitesh) |
| 6.6 | 2 runs (Jitesh) |

**Over 7** (Prasidh Krishna; **48/4 → 49/4**)

| Ball | Outcome |
|------|---------|
| 7.1 | 1 run (Livingstone) |
| 7.2 | 0 — dot (Jitesh; beaten) |
| 7.3 | 0 — dot (Jitesh) |
| 7.4 | 0 — dot (Jitesh) |
| 7.5 | 0 — dot (Jitesh) |
| 7.6 | 0 — dot (Jitesh) |

**Over 8** (Ishant Sharma; **49/4 → 66/4**)

| Ball | Outcome |
|------|---------|
| 8.1 | 1 run (Livingstone) |
| 8.2 | **6 runs** (Jitesh) |
| 8.3 | 2 runs (Jitesh) |
| 8.4 | **4 runs** (Jitesh) |
| 8.5 | 0 — dot (Jitesh) |
| 8.6 | **4 runs** (Jitesh); **17 runs off over** |

**Over 9** (Prasidh Krishna; **66/4 → 75/4**; strategic timeout before over)

| Ball | Outcome |
|------|---------|
| 9.1 | 0 — dot (Livingstone) |
| 9.2 | **4 runs** (Livingstone) |
| 9.3 | 1 run (Livingstone; risky single) |
| 9.4 | 1 run (Jitesh) |
| 9.5 | 1 run (Livingstone) |
| 9.6 | 0 — dot (Jitesh) |

**Over 10** (Sai Kishore; **75/4 → 88/4**)

| Ball | Outcome |
|------|---------|
| 10.1 | 1 run (Livingstone) |
| 10.2 | 1 run (Jitesh) |
| 10.3 | 0 — dot (Livingstone) |
| 10.4 | 0 — dot (Livingstone) |
| 10.5 | 1 run (Livingstone; dropped catch noted in commentary) |
| 10.6 | **4 runs** (Jitesh) |

### 3.4 Totals

| Over | Deliveries | Notable |
|------|------------|---------|
| 5 | 6 | 1 leg bye (still 6 deliveries) |
| 6 | 6 | 1 wicket |
| 7 | 6 | All dots except first ball |
| 8 | 6 | Boundaries heavy |
| 9 | 6 | Strategic break precedes over |
| 10 | 6 | Spin (Sai Kishore) |
| **Σ** | **36** | **1 wicket**, **1 leg bye** in window |

### 3.5 Approximate clock alignment

India Today stamps show **5.1** near **20:01 IST** and **6.x** near **20:07–20:10 IST**, progressing through **~20:19 IST** into overs **8–10** region — consistent with **~19:30** scheduled start + ~30 min to mid-innings. Use log wall-clock header when the artifact exists for tighter alignment.

---

## 4. Pipeline emission baseline (Phase 2B)

### 4.1 Stop-and-route-back — log present; **§3 alignment blocked (fixture / innings)**

**Canonical path:**

`files/logs/runs/rcb_gt_rc9_commentary_203904.log`

**Verification (2026-04-30):**

```bash
ls files/logs/runs/rcb_gt*.log
# rcb_gt_rc9_commentary_203904.log
```

**Why Phase 2B cannot attribute `[DELIVERY ENQUEUED]` to §3:**

- **`DETAIL|`** rows with **`batting_team=Royal Challengers`** show **`AFTER_innings=2` only** when **`Royal Challengers`** appears in the same line as **`AFTER_innings=`** token sampling (**571** lines — **0** with **`AFTER_innings=1`**). §3 is **RCB first innings**; this capture does not expose that batting phase on DETAIL.
- **`match_info=IPL 2026`** appears **240** times (plus **491** `match_info=—`). Treating the file as IPL **2025** Match **14** innings **1** without corroboration is therefore unsafe.

Therefore:

- **`[DELIVERY ENQUEUED]`** lines **are** citeable for this run (§4.2).  
- **Per-over counts vs §3** are **not meaningful** as “#1a accuracy”; §4.3 uses **N/A** for §3 pairing plus an **appendix** log-local slice only.  
- **`grep '\[DWR\]'`** on this file → **0** lines — do not infer **#1b** health from the §4.2 recipe here (production may emit **`[DWR] window #…`** when that path runs; see ```451:454:files/delivery_window_recorder.py```).

### 4.2 Recipe (executed)

From repo root:

```bash
grep -E '\[DELIVERY ENQUEUED\]|\[DWR\]|Ball .* appended to over|\[THIS-OVER\]' \
  files/logs/runs/rcb_gt_rc9_commentary_203904.log
```

**Result:** **127** matching lines (**2026-04-30**).

**Counts (same file):** **`[DELIVERY ENQUEUED]`** → **60**; **`[THIS-OVER]`** → **67**; **`[DWR]`** → **0**.

**Interpretation:**

- **`[DELIVERY ENQUEUED]`** — one row per **`ball_analyzer.enqueue_delivery_analysis`** invocation tied to a real ball-event type (see ```9577:9585:files/test_pipeline.py```); proxy for **#1a** firing into async delivery analysis for `_evt_is_real`.  
- **`[THIS-OVER] Ball … appended`** — scoreboard **`over_mgr`** token append (```9405:9406:files/test_pipeline.py```); should align **in count** with accepted ball events over the match (MULTI_BALL edges documented in prior audits may diverge **enqueue** vs **append**).  
- **`[DWR] window`** — **#1b** span assembly + classifier dispatch — **no literal `[DWR]` substring** in this artifact via the recipe above.

### 4.3 Comparison vs §3 (overs 5–10) — **not comparable**

**§3 scorecard column:** IPL **2025** Match **14**, **RCB innings 1**, overs **5–10** (**36** legal deliveries). **`[DELIVERY ENQUEUED]` column:** no defensible per-over mapping from this log to those balls — **N/A**.

| Over | §3 scorecard deliveries | `[DELIVERY ENQUEUED]` attributable to §3 | Δ | Notes |
|------|-------------------------|------------------------------------------|---|--------|
| 5 | 6 | **N/A** | — | Log has **no** RCB **innings 1** DETAIL window for §3 pairing. |
| 6 | 6 | **N/A** | — | Includes wicket (Patidar **6.2**) in §3 only. |
| 7 | 6 | **N/A** | — | |
| 8 | 6 | **N/A** | — | |
| 9 | 6 | **N/A** | — | |
| 10 | 6 | **N/A** | — | |
| **Σ** | **36** | **N/A** | — | **Do not** pool metrics vs **36** using this file. |

#### Appendix — log-local slice (**RCB `AFTER_innings=2`**, `ball_event_over` ∈ **[5.0, 10.6]**)

Pairing rule: same **`[HH:MM:SS F<id> TEST]`** frame — **`[DELIVERY ENQUEUED]`** exists **and** **`DETAIL|`** has **`batting_team=Royal Challengers`** with numeric **`ball_event_over`** in range (**one row per frame**, deduped).

| Over (int) | Paired emissions | Notes |
|------------|-----------------|--------|
| 5 | 6 | `dnum` **39–44**; DETAIL overs **5.0–5.5**. |
| 6 | 6 | `dnum` **45–50**; **6.0–6.5**. |
| 7 | 4 | **Missing `ball_event_over=7.1`** between **7.0** (F1485) and **7.2** (F1571); **7.5**, **7.6** absent before later gap. |
| 8 | 0 | No paired rows in window. |
| 9 | 0 | No paired rows in window. |
| 10 | 0 | No paired rows in window. |
| **Σ (appendix)** | **16** | Exploratory only — **not** §3 #1a validation. |

**Sequential detail (appendix):** `(ball_event_over, dnum, frame)` → (5.0,39,F1313), (5.1,40,F1331), (5.2,41,F1351), (5.3,42,F1364), (5.4,43,F1381), (5.5,44,F1392), (6.0,45,F1422), (6.1,46,F1455), (6.2,47,F1465), (6.3,48,F1472), (6.4,49,F1475), (6.5,50,F1476), (7.0,51,F1485), (7.2,52,F1571), (7.3,53,F1586), (7.4,54,F1604). Next enqueue: **`dnum=55`** at **F2116** (**~22:37**) — large gap after **F1604** (**~22:08**).

**Metrics (§3 N = 36 — not applied):**

- **Pooled #1a alignment vs §3:** **N/A**.  
- **Appendix-only:** **16** paired frames in **[5.0, 7.4]** vs **18** legal balls if overs **5–7** were complete → **~11%** miss rate **within that truncated chase slice** (missing **7.1** + one further **7.x** delivery vs a nominal six-ball over).  
- **Phantom / FP vs §3:** **N/A**.

---

## 5. Per-failure investigation

Failures are framed **without** re-litigating §3 (Phase 2A authoritative).

### 5.1 Primary blocker — dataset mismatch (not a `#1a` UNDER/OVER verdict on §3)

**Symptom:** Public §3 lists **Patidar / Jitesh / Livingstone** in **RCB innings 1**; DETAIL for **`batting_team=Royal Challengers`** here is **`AFTER_innings=2`** with chase framing (e.g. **target ~196**, **Kohli / Padikkal / Bethell** family in later BOARD traces — narrative incompatible with §3 roster phase).

**Consequence:** No **`evt=`** line can be honestly labeled “§3 ball **x.y**” from this file. **Outcome A/B/C/D** thresholds for **#1a vs §3** are **out of scope** until an innings-matched log exists.

### 5.2 Log-internal emission gap — missing **7.1** (appendix slice)

**Observation:** **`ball_event_over`** jumps **7.0** (F1485, `dnum=51`) → **7.2** (F1571, `dnum=52`) with **~3m38s** wall clock between frames — consistent with **missed detection**, **MULTI_BALL merge**, or **non-ball pipeline stall**, not with a simple scoreboard typo alone.

**Follow-up (when investigating this chase on purpose):** grep **`MULTI_BALL`**, **`ball_detector`**, **`Ball.*detect`**, and BOARD **`[DISMISS]`** around **F1485–F1571**; check whether **`[THIS-OVER]`** advances without **`[DELIVERY ENQUEUED]`** on the missing ball.

### 5.3 Long discontinuity — **F1604** → **F2116** (`dnum` **54** → **55**)

**Observation:** Appendix pairing ends **7.4** / **`dnum=54`**; next **`[DELIVERY ENQUEUED]`** is **`dnum=55`** at **F2116**. Wall-clock gap **~29 minutes** suggests **feed gap**, **session boundary**, **different camera/stack**, or **join mid-chase** — not a single contiguous overs **8–10** RCB strip in this excerpt.

### 5.4 Overlay / extractor noise (secondary)

BOARD logs show **Rajat Patidar** / **Jitesh Sharma** candidates **rejected** (“**2 batters already active**”, dismiss blocked as likely **replay/comparison overlay** hallucination). This corroborates **noisy graphics** but does **not** replace §5.1 — the innings/metadata mismatch stands independently.

---

## 6. Aggregate metrics

| Metric | Value |
|--------|-------|
| **Pooled #1a accuracy vs §3 (N=36)** | **N/A** — wrong innings / fixture linkage for §3. |
| **False positive rate vs §3** | **N/A** |
| **False negative rate vs §3** | **N/A** |
| **Appendix: paired frames (RCB chase `ball_event_over` 5.0–10.6)** | **16** (**16/16** enqueue present when DETAIL supplies over in range on same frame). |
| **Appendix: approximate miss rate (overs 5–7 only, 18 nominal balls)** | **~11%** (**2** missed vs **18**) |

---

## 7. Outcome classification

**No A/B/C/D assignment for the Phase 2 hypothesis** (#1a vs §3 overs **5–10**).

| Axis | Result |
|------|--------|
| **Phase 2A** | **Complete** — §3 authoritative; unchanged by this log. |
| **Phase 2B vs §3** | **Unclassified** — log executed through §4.2 and appendix pairing, but **cannot** score #1a against §3. |
| **Evidence added** | **`rc9` artifact path + content prove run-label risk:** **`match_info=IPL 2026`**, **RCB DETAIL only `AFTER_innings=2`** → seal **`match_id` + innings** or abandon crosswalk from filename alone. |

Do **not** conclude Outcome **C** (“binding ball_detector”) **for §3** from this file — that would be **speculative** and **misleading**.

---

## 8. Phase 2C / 2D recommendation

| Gate | Action |
|------|--------|
| **Innings-matched log obtained** | Repeat §4.2–§4.3 with DETAIL **`AFTER_innings=1`** RCB bat **and** batter/roster consistent with §3; then classify **A/B/C/D** per charter; if **A or B**, proceed **2C** + **2D** (V6d/V6e replay). |
| **`rc9`-class mislabels recur** | Require **`match_info`** / ESPN **match id** + **innings** in run metadata; optionally add **`[DELIVERY ENQUEUED]`** + **`[DWR]`** rollups to `analyze_match_telemetry.py` for sealed CI captures under **`files/logs/runs/`**. |
| **This file only** | Treat appendix metrics as **chase-only exploratory**; **do not** gate Scout paste on §3 using **`rcb_gt_rc9_commentary_203904.log`**. |

---

## 9. V6d / V6e disposition update

| Decision | **Defer production paste / Scout iteration tied to “#1a healthy on §3” — unchanged in spirit; rationale updated** |
|----------|---------------------------------------------------------------------------------------------------------------------|
| **Reason** | Phase 2B **ran** (§4.2 grep + appendix pairing) but **did not** validate #1a vs §3 because the log is **innings/fixture-mismatched** (**§5.1**). **`[DELIVERY ENQUEUED]` exists** (**60** globally) — so **instrumentation absence** is **not** the blocker anymore; **dataset alignment** is. Scout variants (**V6d** corpus PRIMARY; **V6e** **`f1455`** / **503** — `scout_v6e_first_shadow_run_results.md`) gain **no** new §3-grounded #1a confirmation from this artifact. |
| **Concrete next step** | **(1)** Capture or locate a log whose DETAIL matches **IPL 2025 Match 14 RCB innings 1** for overs **5–10** (or relocate §3 to a window this file actually covers — **explicit charter change**, not silent drift). **(2)** If appendix chase slice is the intentional target, score **#1a** only against **that** scorecard (including **7.1** gap triage in §5.2). **(3)** Only if **innings-matched** #1a ≥95% → pursue **V6d/V6e** under **#1b** gates; if **<85%** on **that** sealed slice → **pause Scout paste**, prioritize **`ball_detector.detect`** per backlog on BED. |

---

## 10. Limitations

- Single fixture; overs **5–10** omit death overs and chase innings.  
- Run labels (**`rc9`**, filename stem) can diverge from **`match_info`** / innings (**§4.1**); sealed **`match_id` + innings** metadata reduces Phase 2 repeat risk.  
- Public commentary timestamps ≠ pipeline frame indices — alignment needs log.  
- **`MULTI_BALL`** / extras compound events may shift **`[THIS-OVER]`** vs **`[DELIVERY ENQUEUED]`** parity even when #1a is healthy (`delivery_extraction_audit.md` MI–SRH sample).  
- India Today text is **journalistic**; authoritative discrepan­cies should defer to **official IPL ball data** if Evergreen feeds become available.

---

## 11. Cross-references

- `files/docs/investigations/delivery_extraction_audit.md`  
- `files/docs/investigations/scout_v6e_first_shadow_run_results.md`  
- `files/docs/backlog.md` (documentation hygiene + Phase 2AB note)  
- `files/docs/MONITORING_CHARTER.md`  
- Code: ```9369:9564:files/test_pipeline.py``` (`ball_detector.detect`, enqueue path); ```451:454:files/delivery_window_recorder.py``` (`[DWR]` window log).

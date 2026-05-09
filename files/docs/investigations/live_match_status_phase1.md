# Live match status — Phase 1 checkpoint (GT vs RCB, IPL 2026)

**Generated:** 2026-04-30 (checkpoint request: ~15–20 min into match).

**Evidence sources**

- Primary pipeline log: `logs/pipeline-2026-04-30-gt-rcb-live.log` (full artifact on disk at analysis time).
- Structured rollup: regenerated at this checkpoint via  
  `python3 files/scripts/live_match_monitor.py --replay-file logs/pipeline-2026-04-30-gt-rcb-live.log`  
  (no `files/logs/live_observation_*.md` was present under the workspace copy used here).

**Coverage caveat:** Log wall-clock span from first to last stamped pipeline lines is about **19:50:35 → 20:32:31** (same timezone as logger). That is longer than a single 15–20 minute broadcast window; treat early segment as startup/warm-up unless you trimmed to match clock. Delivery and telemetry counts below refer to **this entire captured segment**, not a strict 15-minute slice—appropriate for directionally correct monitoring, weak for strict rate inference.

---

## 1. Status snapshot

| Field | Value |
| --- | --- |
| Approx. log span | ~42 minutes (`19:50:35` → `20:32:31` on stamped lines) |
| Last ball context (tail DETAIL) | RCB **97/6** at **11.0** overs (innings **1**) |
| Max frame index `[Fn]` | **940** |
| Max processed counter `#` seen in rollup | **263** (many frames may not emit the `[F…] … — #n` heartbeat line—do not equate to capture FPS without verifying log format) |
| Approx. rollup frames/sec | ~0.105 (derived from log timestamps vs `#`; **low confidence**) |
| `[SM-INNINGS-2-RESET]` | **0** (expected until innings transition) |
| **Pipeline alive at tail** | **Yes** — DETAIL + ball events still printing through **F940** |

---

## 2. Today’s shipments validation (preliminary)

### Lever 1 (PR1–PR4): `[WS-SLOT-INVARIANT]`

- **Count:** **100** over the analyzed log (replay rollup).
- **Assessment:** Volume is **material** and **bursty** (per-minute rollup shows large spikes, e.g. many WS-SLOT hits around **20:11–20:12** and **20:29–20:30**). The **73–87% reduction vs prior matches** cannot be validated from this artifact alone—you need the **baseline match total / per-over rate** from the same monitor recipe on an earlier IPL 2026 control log (same pipeline version).
- **Recent pattern:** Repeated duplicate-slot repair for **`Krunal Pandya`** with **“cleared non (no alternate active batter)”** in the tail window—worth eyeballing scorecard transitions around that batter.

### Thread 7 Fix 1: `[STRIPS-ROW-MISALIGNED]` (`STRIP-ROWS-*`)

- **Count:** **10**.
- **Recoveries:** Emissions include **`preserved=score,match_overs,bowler`** (narrow pop vs legacy behaviour)—consistent with Fix 1 intent. Example (ANSI stripped):

  `[20:01:55 F187 TEST] WARN:   [STRIP-ROWS-MISALIGNED] frame=F187 row_delta=21 popped=batters preserved=score,match_overs,bowler row_pair=Devdutt Padikkal strip_runs=36 card_runs=15`

### Thread 7 Fix 2: `[CAM-GRAPHIC-FAST-PATH-*]`

- **READ:** **15** · **REJECT:** **9** · **NOOP:** **0**
- **Assessment:** Graphic fast-path is **active**. READ outweighs REJECT in this slice; NOOP absent—fine if graphic frames rarely qualify for noop path.

### PR3 dedup: `[SM-W8-DISMISSED-GUARD]`

- **Count:** **0** vs expectation **≤6/match** — **within bound** (also consistent with “no fires yet”).

### P0-A: `[SM-INNINGS-2-RESET]`

- **Count:** **0** — **normal** while still in innings **1** per tail DETAIL (`AFTER_innings=1`). **Watch at innings change:** expect **exactly one** ping per transition.

### P0-C: cricket-rules attribution / poison-rate

- **`[_FRAME_POISONED_STRIP_TRUST_THRESHOLD]` / `[TEAM-ATTRIBUTION-POISON-RATE]`:** **0** in rollup—**no P0-C poison-rate window fired** in this capture.

### `[BATTERS-INVARIANT]` / rule=A NON-ADMISSION

- **`[BATTERS-INVARIANT]`:** **18**
- **`rule=A NON-ADMISSION` slice:** **0** in rollup counters—either no qualifying admissions in window or messaging differs from the counter regex.

---

## 3. Delivery detection observations

### `[DELIVERY ENQUEUED]` vs `[THIS-OVER]`

- **Global counts:** `[THIS-OVER]` **40**, `[DELIVERY ENQUEUED]` **39** (**off by one**).
- **Per-over:** Replay table shows **over 6:** **5** THIS-OVER vs **4** DELIVERY ENQUEUED — **likely single-ball enqueue gap** (async enqueue skip, classification gate, or ordering vs THIS-OVER attribution).
- **`[DWR]` literal lines:** **0** — **#1b span assembly + dispatch not observable** from substring telemetry on this run (consistent with historical notes that `[DWR]` may be absent depending on path/configuration).

### Pipeline score progression

- Tail DETAIL indicates **97/6 at 11.0 overs**, innings **1** — aligns with mid-innings chase/set phase for RCB **against narrative in DETAIL** (`MATCH 42`). Cross-check vs broadcast score bug-for-digit when you need absolute confirmation.

### Anomalies

- **Missed enqueue vs THIS-OVER:** investigate **over 6** (see counts above).
- **Shadow mismatches (SM vs BED):** multiple **`[SHADOW] SM=DOT BED=… MISMATCH`** lines early—example:

  `[19:52:44 F24 TEST] INFO:   [SHADOW] SM=DOT BED=SIX MISMATCH`

  Tail also shows **`[SHADOW] SM=DOT BED=1_RUNS MISMATCH`** immediately before the final DETAIL excerpt—track whether shadow divergences correlate with extractor/scorer ERROR bursts.

---

## 4. Scout production classification distribution

From rollup (`cam=` classified frames):

| Camera | Share |
| --- | --- |
| `closeup` | ~**47.9%** |
| `bowlers_end` | ~**28.3%** |
| `graphic` | ~**13.0%** |
| Other (`ad`, `other`, rare `side_on`, parse misses) | remainder |

**Assessment:** **bowlers_end ~28%** is **below** the heuristic **30% “over-emission”** flag—**borderline but not tripwired** by the script’s default anomaly rule.

**Scout `[SCOUT] Error:` bucket:** rollup shows **none classified** separately; upstream **`ENRICH` / EXTRACT ERROR** lines dominated infra failures (next section).

---

## 5. Operational health

### Error-rate highlights (specific lines)

| Local timestamp | Frame | Kind | Notes |
| --- | --- | --- | --- |
| **19:52:41** | **F24** | Groq via Cloudflare **524** timeout | Pass-2 verify LLM path (`ENRICH`): origin timeout—**retry/backoff** semantics surfaced in payload (`retry_after`: **120**). |
| **19:59:42** | **F128** | Extract **JSON parse failed** | Model returned conversational preamble (“Here is the JSON…”) instead of pure JSON. |
| **20:16:08** | **F531** | Extract **Connection error** | Transient transport failure to extractor backend. |
| **20:30:59** | **F912** | Extract **JSON parse failed** | Same preamble failure pattern as F128. |

**Verdict:** Pipeline **did not dead-stop**, but **external dependency noise is non-trivial** in this window—especially **Groq timeout** and **extractor JSON hygiene**.

### Frame processing

- Treat rollup **FPS** as **indicative only** until validated against known-good `[F…] … — #processed` cadence on your machine.

---

## 6. Anomalies and recommendations

**Working as expected**

- Innings still **1** with **`[SM-INNINGS-2-RESET]` = 0**.
- **`[SM-W8-DISMISSED-GUARD]`** absent—consistent with dedup idle.
- Thread **7 Fix 2** fast-path READ/REJECT counts prove path live.

**Surprising / concerning**

1. **`[WS-SLOT-INVARIANT]` = 100** with **minute-clustered bursts** — prioritize **baseline comparison** (prior match normalized per over).
2. **Extractor JSON preamble failures** at **F128** and **F912** — operational risk for scoring drift when extract fails soft.
3. **Groq 524** at **F24** — confirms **need backoff / circuit breaker visibility** on enrich path during live.
4. **THIS-OVER vs DELIVERY ENQUEUED** mismatch (**39 vs 40**) — tighten monitoring on **`[DELIVERY SKIPPED]`** and enqueue reasons if Phase **2B** needs strict pairing.

**Suggested monitoring tweaks (remainder of match)**

- Add **`grep '\[DELIVERY SKIPPED]'`** alongside enqueue baseline if not already in rollup v2.
- Track **`[SHADOW]` mismatch rate** per over as a lightweight SM-vs-BED coherence KPI.
- When innings advances: **single-screen `[SM-INNINGS-2-RESET]` assert** (expect **1**).

---

## 7. Decision points for user

**Needs attention now**

- **Extractor JSON failures** — if recurrence exceeds ~**1/min**, consider **lowering extractor temperature**, shorter prompts, or **fail-fast alerting**—investigation-only tonight; no code edits during match per charter.
- **Groq timeout** — if **524** repeats, **pause optional enrichment** or extend timeouts **only if ops playbook allows** (policy decision).

**Watch second innings**

- **`[SM-INNINGS-2-RESET]`** must appear **exactly once** at transition.
- **`[WS-SLOT-INVARIANT]`** spike behaviour **after card churn** at innings break.

**Stop / escalate if**

- **Extractor failures cluster** such that DETAIL lines stop updating for **>60–120 s** while broadcast advances materially.
- **Score/wickets diverge from broadcast** across consecutive DETAIL snapshots **without** corresponding `[GUARD]` / correction telemetry—possible silent degradation.

---

## Flags (Phase 2 stop-and-route summary)

| Gate | Status |
| --- | --- |
| **S2.1** Near-zero telemetry | **Clear** — substantial `[THIS-OVER]`, DETAIL, Scout lines |
| **S2.2** Pipeline crashed | **Clear** — tail activity healthy |
| **S2.3** Fundamental telemetry break | **Watch** — **innings reset not yet testable**; **infra ERRORs present** but pipeline continues (**elevated operational risk**, not automatic halt) |

---

## 8. Addendum — DWR firing verification (investigation only)

### Commands executed

Pipeline log (GT vs RCB live tee):

```bash
grep -iE 'DeliveryWindowRecorder|delivery_window|span_assembled|DWR|window #' \
  logs/pipeline-2026-04-30-gt-rcb-live.log | head -50
```

Result: **no matching lines** (empty).

Source audit (`files/delivery_window_recorder.py`): emission strings remain **`[DWR]`**-prefixed, e.g. `log.info(f"[DWR] window #{win_id} source=..."`, plus **`SKIP phantom`**, **`rejecting stale span`**, **`span … overlaps …`**, warnings for thin windows / classifier crash / debug saves.

### Is DeliveryWindowRecorder “running”?

**Evidence it is wired into the delivery path**

- `BallAnalyzer.enqueue_delivery_analysis()` requires `_recorder` and classifier when **`gemini_async_ok`** is true (see `files/ball_analyzer.py`).
- GT vs RCB pipeline log contains **`[DELIVERY ENQUEUED] … method=gemini_async`** (async stub path)—example:

  `[19:51:45 F11 TEST] INFO:   [DELIVERY ENQUEUED] dnum=1 evt=DOT runs=0 (submit_ms=1, method=gemini_async) — awaiting async classification`

That combination implies **`DeliveryWindowRecorder` + Layer2/Gemini classifier were constructed** and the pipeline is taking the async classification route **by design**.

**Why `[DWR]` does not appear in `pipeline-*-live.log`**

- `delivery_window_recorder` uses **stdlib** `logging.getLogger("delivery_window_recorder")` and attaches **`eyes.cricket_logger._ensure_file_handler()`**.
- That handler writes **`logs/machine-1-{date}.log`** with format **`%(message)s`** only (see `files/eyes/cricket_logger.py`).

The **`pipeline-2026-04-30-gt-rcb-live.log`** tee is driven by **`CricketLogger("TEST")`** (and siblings) in `test_pipeline.py`—**not** the same sink as the stdlib `delivery_window_recorder` logger.

So **absence of `[DWR]` in the pipeline-named log is expected under current wiring**, not proof that `classify_for_score_event()` never ran.

**Workspace cross-check**

- `logs/machine-1-2026-04-30.log` **did not contain** evening timestamps (`19:xx`) matching this GT vs RCB session—likely **different logging session**, **cwd**, or **artifact incompleteness** in this workspace copy.
- **`grep -F '[DWR]'`** on both `pipeline-2026-04-30-gt-rcb-live.log` and `machine-1-2026-04-30.log` here returned **0** hits → **cannot confirm text emission from artifacts on disk**; operator should **`grep '[DWR]'` on the live machine’s `machine-1-{match-date}.log`** during the actual broadcast window.

### Verdict table

| Question | Answer |
| --- | --- |
| **DWR running** | **Likely yes** (async enqueue + code path); **not provable from pipeline tee alone**. |
| **Alternate tag format** | **No** — source still uses **`[DWR]`**; monitor grep was aimed at the **wrong file**. |
| **Monitor regex update** | **Optional**: keep substring **`[DWR]`**; **add second tail/grep target**: **`logs/machine-1-*.log`** (or unify logging later—out of scope during match). |
| **`USE_LAYER2` disabled** | **Default is on** (`USE_LAYER2` env `"1"` in `ball_analyzer.py`). **No evidence** from this grep that Layer2 was forced off—**not** treat as **S1** stop until env snapshot confirms `USE_LAYER2=0`. |

### Implications for #1b span assembly visibility

**Grepping only `pipeline-*-live.log` under-declares #1b.** Treat **`machine-1-{date}.log`** (and optional **`logs/deliveries/<session_id>/`** artifacts when enabled) as **primary evidence** for `[DWR]` window lines until logging is unified.

---

## 9. Addendum — `[WS-SLOT-INVARIANT]` baseline vs MI vs SRH (investigation only)

### MI vs SRH replay (baseline)

Command:

```bash
python3 files/scripts/live_match_monitor.py \
  --replay-file logs/pipeline-2026-04-29-194416-mi-srh-live.log \
  --output /tmp/live_obs_baseline_mi_srh.md \
  --match-title 'MI vs SRH baseline'
```

Rollup extract:

| Metric | Value |
| --- | --- |
| **`[WS-SLOT-INVARIANT]` total** | **122** |
| **Distinct overs with `[THIS-OVER] … appended to over N`** | **18** (overs **2–19** populated) |
| **Max over index seen on those lines** | **19** |

**Per-over rates (baseline)**

- **122 ÷ 18** ≈ **6.78** WS-SLOT events per “active” over (distinct-over denominator).
- **122 ÷ 19** ≈ **6.42** WS-SLOT events per over if normalized by **max over index**.

### GT vs RCB (current, Phase 1 artifact)

| Metric | Value |
| --- | --- |
| **`[WS-SLOT-INVARIANT]` total** | **100** (raw `grep -c`; aligns with Phase 1 rollup) |
| **Distinct overs (`THIS-OVER` lines)** | **9** |
| **Max over index** | **11** |

**Per-over rates (current)**

- **100 ÷ 9** ≈ **11.11** WS-SLOT / distinct active over.
- **100 ÷ 11** ≈ **9.09** WS-SLOT / max-over index.

### Reduction vs Lever 1 prediction (73–87% reduction)

Using **distinct-over** normalization (apples-to-apples on “overs that emitted ball-append telemetry”):

- **(6.778 − 11.111) ÷ 6.778 × 100% ≈ −63.9%**

Using **max-over** normalization:

- **(6.421 − 9.091) ÷ 6.421 × 100% ≈ −41.6%**

**Interpretation**

- **Negative reduction** ⇒ **current per-over WS-SLOT rate is higher than MI vs SRH baseline**, not lower—**does not support** the **73–87% reduction** hypothesis on these two artifacts (**validation: No**).
- **Caveats:** Different innings depth (partial innings vs deeper slice), possible **different pipeline build/version**, and **different scorecard churn** (GT vs RCB showed **burst clusters** and repeated **`Krunal Pandya`** duplicate-slot clears in Phase 1).

### Stop-condition flag (**S3**)

**Raised:** WS-SLOT appears **worse than baseline** on a straightforward per-over normalization—not proof of regression in Lever 1 code without controlling for match situations, but **definitely contradicts** the “large reduction already realized” story until reconciled **post-match** (segment alignment, version pins, batter-specific bursts).

### Recommended follow-up (after match)

- Segment baseline vs current on **same innings phase** (e.g. overs **3–11** only) to reduce innings-shape bias.
- Quantify **`[WS-SLOT-INVARIANT]` per named duplicate slot** (e.g. fraction attributable to **Krunal Pandya** streak vs global rate).

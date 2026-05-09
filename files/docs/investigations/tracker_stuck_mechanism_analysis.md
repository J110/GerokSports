# Tracker-stuck mechanism — Cause 5 (MULTI_BALL chain)

**Date:** 2026-05-01  
**Purpose:** Explain why **`scoreboard._inn["score"]`** (and SM projection) can remain **stale** (**`0`**, **`222`**, **`243`**, …) while **strip OCR repeatedly shows correct live totals**, until **`[POISON-RECAL]`** forces recovery — and why **valid updates never committed earlier**.

**Evidence anchor:** Seven **“genuine live divergence”** trips from [`poison_recal_threshold_analysis.md`](poison_recal_threshold_analysis.md) **§A4** (PBKS **`F2354` `F2807` `F3074` `F3358` `F3474` `F3604`**, MI **`F2855`**).

**Overlap:** Aligns with **Cause 3** (cold-start / recovery exit) where **`ScoreManager`** never reaches **`COLD_START→WARM`** because **feeder inputs are stripped or poison-blocked** — see [`cold_start_recovery_analysis.md`](cold_start_recovery_analysis.md). This memo focuses on **`files/test_pipeline.py` scorer path + `files/eyes/scoreboard.py`** rather than SM consensus internals alone.

---

## Phase A — Stuck-pattern characterization

### A1 — Log inventory (tracker @ ~−50 / −30 / −10 frames)

Telemetry is taken from sealed tees (**shell replay**). **`DETAIL|…|BEFORE_score=`** is the canonical tracker projection on processed frames; many pre-trip frames log **`FRAME_POISONED`** without advancing **`AFTER_score`**.

| Trip | ~F−50 | ~F−30 | ~F−10 | Dominant pre-trip telemetry |
|------|-------|-------|-------|----------------------------|
| **PBKS `F2354`** | *(sparse DETAIL)* | *(sparse)* | **`F2344`** **`BEFORE_score=222-4(20.0)`** | **`[POISONED] 0 vs 222`**; **`[GUARD] 0-0(0.0) PASSED — innings 2`**; scorer **`extractor empty, blocking`** |
| **PBKS `F2807`** | sparse | sparse | sparse | Repeat **`0 vs 222`** POISON ladder; heavy **`[WS-SCRUB]`** / slot churn |
| **PBKS `F3074`** | sparse | sparse | sparse | **`[GUARD] RR is bowling team — comparison strip, ALL data stripped (n/30)`** + **`[POISONED] 37 vs 0`**; **`STATE-RECOVERY-OVERRIDE-CANDIDATE`** |
| **PBKS `F3358`** | **`F3308`** **`BEFORE=0-0(None)`** | — | **`F3348`** **`BEFORE=0-0(None)`** | Same **comparison-strip** guard + **`GRAPHIC`** frame **`F3355`** (career panel); POISON **`66 vs 0`** |
| **PBKS `F3474`** | sparse | **`F3444`** **`BEFORE=0-0`** | **`F3464`** **`BEFORE=0-0`** | **comparison-strip** guard + **`GRAPHIC`** **`F3471`**; **`cam=graphic → dead-time skip`** **`F3473`** |
| **PBKS `F3604`** | sparse | sparse | **`F3594`** **`BEFORE=0-0`** | **comparison-strip** guard POISON **`92 vs 0`** |
| **MI `F2855`** | sparse | sparse | sparse | **comparison-strip** (**SRH “bowling team”**) POISON **`8 vs 0`** |

**Update attempts:** There is **no** sustained stream of **`score→…`** commits in these windows. Instead:

1. **Extractor fields stripped** (`guard … ALL data stripped`), producing **`[GUARD] Scorer proposed … — extractor empty, blocking`** on multiple frames (e.g. **PBKS `F2352`** family).
2. **`FRAME_POISONED`** lines track headline disagreement while **`AFTER_score`** remains **`None`** or stuck until **`POISON-RECAL`**.

**Frame classification:** Pre-trip **`DETAIL`** rows are predominantly **`tag=SCOREBOARD`** with valid **`scout=STRIP: …`** text — i.e. failures are **not** primarily “wrong `frame_type` class” (**§C** rules out **H4** as dominant).

### A2 — Pattern assignment

| Pattern | Definition | Cases |
|---------|------------|-------|
| **P1 — Cold-start latch** | Tracker **`0` / `None`** while chase totals climb; commits never land | **PBKS `F3074`–`F3604`**, **MI `F2855`** |
| **P2 — Innings-edge latch** | Tracker holds **innings‑1 final** (**`222`**) while innings‑2 **`0-0`** strip is correct | **PBKS `F2354`**, **`F2807`** |
| **P3 — Mid-innings stall** | Tracker stuck mid-chase (non-zero) while broadcast progresses | **None** among these seven |

### A3 — Time-to-trip (operational lag)

**Metric A (local poison episode):** frames from **first `DETAIL`** in the **same stuck episode** showing **`PBKS 0-0`** vs **`BEFORE_score=222`** to **`POISON-RECAL`**:

| Trip | First such `DETAIL` | Δ frames → RECAL |
|------|---------------------|------------------|
| **`F2354`** | **`F2327`** | **27** |
| **`F2807`** *(after prior RECAL)* | **`F2796`** | **11** |

**Metric B (RR chase vs cold tracker):** first **`DETAIL`** backward from **`F3074`** with **`scout=RR …`** and **`BEFORE_score`** still cold (**`None-None` / `0-0`**) lands around **`F2809`** → **~265** frames to **`F3074`** RECAL — dominated by **epoch mistake** (roles / commits), not merely **5-frame** poison streak.

**Median / max (poison-only tail):** Once **`[POISONED] score_vs_tracker`** begins monotonic streaking, **`POISON-RECAL`** lands **~5+** poison-class reads later (mechanistic minimum from `files/test_pipeline.py` streak rule). The **large** operational pain is **pre-poison starvation** (**Metric B**), where the tracker never receives legal commits for **hundreds** of SCOREBOARD-class frames.

---

## Phase B — Update-path forensics

### B1 — Where extractor score meets the tracker

| Stage | Location | Role |
|-------|----------|------|
| **Pre-guard snapshot** | **`files/test_pipeline.py`** **`_pre_guard_score = extracted.get("score")`** (**~7035**) | Preserves headline score **before** downstream guards mutate **`extracted`**. |
| **Comparison-strip / squad guards** | **`files/test_pipeline.py`** **~7336–7428** | May **`extracted.pop("score", …)`** — scorer sees **empty** extractor. |
| **Poison delta** | **`files/test_pipeline.py`** **~7994–8067** | Uses **`extracted.get("score")`** or **`_pre_guard_score`** fallback (**~7999–8032**) → **`[POISONED]`** / streak **even when scorer feed was stripped**. |
| **Scorer → `Scoreboard.set`** | **`files/test_pipeline.py`** **`apply_scorer_decision`** (**~3171+**) + **`files/eyes/scoreboard.py`** **`set("score")`** (**1018–1070**) | **`ConsistentReadTracker.update`** requires **`INITIAL_CONSENSUS_FRAMES = 3`** first confirmations (`files/eyes/consistent_tracker.py` **21–27**). **`scoreboard.set`** also **rejects score regressions** (**1054–1058**) without reset authority. |

**Reject telemetry (scoreboard):** `Score rejected: absolute …`, `Score regression rejected`, `Score rejected: jump …`, chase ceiling warns (**1029–1064**).

### B2 — Per-pattern rejecting “guard”

| Cases | Primary blocker observed in tee | Secondary |
|-------|----------------------------------|-----------|
| **P2 (`222→0`)** | **`[POISONED] delta=-222`** → **all updates blocked** this frame; chicken-and-egg with innings‑2 template | Scorer **`extractor empty`** after guards; **`Scoreboard.set`** regression guard would also refuse **`222→0`** without explicit reset |
| **P1 (`0→37…`)** | **`[GUARD] Visible team 'Rajasthan Royals' is bowling team — comparison strip, ALL data stripped`** (**`files/test_pipeline.py` ~7366–7378**) while **`batting_team`** is still **PBKS** in `DETAIL` | **`GRAPHIC`** / **`dead-time skip`** neighbors reduce viable feeds; **`STATE-RECOVERY-OVERRIDE-CANDIDATE`** fires but does not preempt **`POISON-RECAL`** here |

**Interpretation (stop-condition **S2**):** The rejecting machinery is **internally consistent** with its **innings‑1 mental model** (chasing team labeled “bowling team” on broadcast strip during innings‑2 chase). It **correctly rejects** many true comparison strips — but **incorrectly rejects valid chase totals** when **`batting_team` / `bowling_team`** lag the real innings‑2 orientation.

### B3 — Rejection volume

Rough order: **tens to hundreds** of SCOREBOARD **`DETAIL`** lines per RR episode share **`BEFORE_score=0-0(None)`** while strip climbs — commits **starved**, not merely **5** poison frames.

---

## Phase C — Hypothesis ranking

| ID | Hypothesis | Verdict (7-case corpus) |
|----|------------|-------------------------|
| **H1** | **`COLD_START_CONSENSUS_FRAMES`** too strict | **Secondary** — SM cold-start matters **after** **`full_reset`**, but **pre-RECAL** starvation is often **stripped extractor inputs**, not triple disagreement alone |
| **H2** | **`ConfirmedValue` / tracker** too strict post-transition | **Partial** — **`ConsistentReadTracker`** **3-frame** rule applies when commits reach **`set`**, but many frames **never arrive** |
| **H3** | **Innings / team propagation lag** | **Dominant** — comparison-strip guard keyed off **`batting_team` vs visible strip team** |
| **H4** | **Frame-type misclassification** | **Not dominant** — strips processed as **`SCOREBOARD`** (**stop S3** → not Cause‑4-by-proxy) |
| **H5** | **Poison / regression interaction** | **Co-dominant on P2** — large negative Δ poisons frame **before** tracker can legally latch **`0`** |

**Ranked:** **H3 > H5 > H2 > H1 ≫ H4.**

**Cause 3 overlap:** If **`full_reset`** fires but **`observe()`** rarely receives **complete** scorecards because **`extracted`** was stripped, **`_handle_cold_start`** cannot converge (**`files/score_manager.py` ~1113–1116** incomplete-card skip) — same starvation narrative as [`cold_start_recovery_analysis.md`](cold_start_recovery_analysis.md).

---

## Phase D — Fix design & scope

### D1 — Smallest targeted directions

| Priority | Change | Targets |
|----------|--------|---------|
| **1** | **Innings‑2 team-flip correctness** before **`_bowling_team_strip_count`** comparison-strip stripping | **P1** corpus (**RR/SRH** visible while PBKS/MI still “batting” in state) |
| **2** | **Poison / innings-edge exception:** when **`[GUARD] … innings 2 starting fresh`** validates **`0-0`**, **clear innings‑1 headline scores** (or suppress poison comparisons) **before** **`[POISONED]`** compares **`0 vs 222`** | **P2** |
| **3** | **Escalate `STATE-RECOVERY-OVERRIDE-CANDIDATE`** / forced feeder attach when batting-sum consensus matches strip headline **and** team flip pending | Bridges to **Cause 3 Path B** ([`cold_start_recovery_fix_implementation.md`](cold_start_recovery_fix_implementation.md)) — single shipped fix may satisfy **both** if starvation is shared root cause |

### D2 — Scope verdict

**MEDIUM (~100–300 LOC)** minimum for safe **H3** fixes (team assignment + guard ordering + tests). **Not SMALL:** touching **`AUTO-SWAP`**, comparison-strip counters, and poison ordering has **wide blast radius**.

### D3 — Risk

Relaxing comparison-strip stripping **without** reliable innings‑2 detection risks **re-introducing true comparison-strip garbage**. Any fix must **pair** guard relaxation with **stronger orientation signals** (delivery feed, innings counter, target latch, or sustained **`DELIVERY ENQUEUED`** context).

---

## Phase E — Implementation

**Deferred (**`D2`** ≠ SMALL**)** — no **`score_manager.py` / `scoreboard.py` / `test_pipeline.py`** edits in this commit; no **`tracker_stuck_mechanism_fix_implementation.md`**.

Recommended telemetry if implemented later:

- **`[TRACKER-UPDATE-RELEASED]`** — would-have-been-rejected path (guard name, prior tracker, proposed strip headline).
- **`[POISON-RECAL-PRE-EMPTED-VIA-TRACKER]`** — streak reset because headline commit succeeded.

---

## Code anchors

Comparison-strip stripping (feeds empty extractor → scorer blocking):

```7364:7378:files/test_pipeline.py
                    else:
                        _frame_poisoned = True
                        log.info(
                            f"  [GUARD] Visible team '{_ext_vis_team}' "
                            f"is bowling team — comparison strip, "
                            f"ALL data stripped "
                            f"({_bowling_team_strip_count}/"
                            f"{_BOWLING_TEAM_SWAP_THRESHOLD})")
                        extracted.pop("score", None)
                        extracted.pop("wickets", None)
                        extracted.pop("match_overs", None)
                        extracted.pop("batters", None)
                        extracted.pop("bowler", None)
                        extracted.pop("bowler_name", None)
                        extracted.pop("bowler_figures", None)
```

Poison path still sees **pre-strip** score:

```7999:8032:files/test_pipeline.py
            _ext_score_raw = extracted.get("score")
            if _ext_score_raw is None:
                _ext_score_raw = _pre_guard_score
            if _ext_score_raw is not None:
                try:
                    _ext_score_int = int(_ext_score_raw)
                    # Cold-start safety: only run the poison delta check
                    # when we already have a CONFIRMED prior score.
```

Score commit + regression gate + **`ConsistentReadTracker`**:

```1050:1070:files/eyes/scoreboard.py
            cur_score = self._inn.get("score")
            if cur_score is not None:
                try:
                    cur_int = int(cur_score)
                    if v < cur_int:
                        log.warn(
                            f"Score regression rejected: {cur_int}→{v} "
                            f"(normal-play score physics; reset authority "
                            f"required)")
                        return False
...
            confirmed = self._tracker.update("score", v, frame)
            if confirmed != v:
                return False
```

---

## Stop-condition ledger

| ID | Outcome |
|----|---------|
| **S1** | **Shared patterns:** **P1** (**5**) + **P2** (**2**) — not seven unrelated bugs (**single memo bounded**). |
| **S2** | Guards behave **as designed** under **wrong team epoch** — reframe as **valid input rejected**, not “bad OCR”. |
| **S3** | **H4** ruled out as primary (**stop S3**). |
| **S4** | **`D2`** → **MEDIUM** — design-only stop for implementation. |

---

*Investigation memo — no production code change in this commit.*

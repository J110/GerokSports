# POISON-RECAL trip threshold tuning — Cause 2 (MULTI_BALL chain)

**Date:** 2026-05-01  
**Purpose:** Decide whether **`abs(score_delta) > 7` + streak `N = 5`** is correctly tuned, and whether richer gating beats naive threshold moves — **without** ball-by-ball official broadcast CSV in-repo.

**Related:** [`poison_recal_frequency_analysis.md`](poison_recal_frequency_analysis.md) (**§11** live vs post split), [`state_integrity_f3293_f3346.md`](state_integrity_f3293_f3346.md) (**F3296**), [`state_integrity_f5054_f5240.md`](state_integrity_f5054_f5240.md) (**F5054**).

---

## Phase B — Trip mechanism (authoritative)

**Source:** `files/test_pipeline.py` — frame poison block (**≈7994–8257**). *(Historical cites at ~7894 referred to an older DETAIL branch; poison logic sits immediately after.)*

| Question | Answer |
|----------|--------|
| **Compared fields** | **`extracted` team score** (`int`) vs **`scoreboard._inn["score"]`** (`int`). Cold-start guard: if `_inn["score"]` is **`None`**, the **`abs(delta) > 7` branch is skipped** (no streak accumulation from vs-`0`). |
| **Delta definition** | **`_delta_check = _ext_score_int - _cur_score_int_check`** (**signed**). **Poison** when **`abs(_delta_check) > 7`** (strict **>** — so **`|Δ| == 8`** is the smallest poison jump). |
| **“Consecutive”** | **Not** “five arbitrary frames in a row.” Inside the poison branch only: streak **`_poison_streak_count`** increments when **`_ext_score_int >= _poison_streak_new_score`** (monotonic non-decreasing extracted totals while poisoned); if **`_ext_score_int` drops** below the streak high, streak **resets to `1`** from that frame. |
| **Streak cleared** | Whenever **`abs(_delta_check) <= 7`** on a frame that still ran the int-score path, **`_poison_streak_new_score`** and **`_poison_streak_count`** are **zeroed** (**8251–8256**). So **no gaps**: non-poison frames wipe the watchdog. |
| **On `[POISON-RECAL]`** | **`scoreboard._inn["score"|"wickets"|"overs"] → None`**, then **`score_mgr.full_reset(reason=poison_recal_consensus …)`**. Streak state reset; frame stays poisoned for that iteration. |

**Implication:** Operator shorthand **“5 consecutive poison frames”** understates the coupling to **monotonic rising (or flat-high) disagreeing strip totals**. Repeated **`Δ = +8`** on a stuck tracker still advances the streak efficiently (**F3296** family).

---

## Phase A — Inventory (35 trips, three tees)

Telemetry grep across sealed tees:

| Log | `[POISON-RECAL]` count |
|-----|------------------------:|
| `logs/pipeline-2026-04-30-gt-rcb-live.log` | 24 |
| `logs/pipeline-2026-04-29-194416-mi-srh-live.log` | 4 |
| `logs/pipeline-2026-04-28-pbks-rr-live.log` | 7 |
| **Total** | **35** |

**Message template drift:** GT tee prints **`(high=…, latest=…)`**; PBKS/MI tees in this vault show an older **`reads of score=…`** phrasing — logic is the same site (**8070–8077** in current `test_pipeline.py`).

### A1 — Per-trip artifacts (machine-extracted)

For each WARN, the tables below recover:

- **Trigger frame** / wall timestamp from the WARN line.
- **Effective poison deltas** — last up-to-eight **`[POISONED] … delta=`** samples before WARN (same burst).
- **Streak snapshots** — last **`[POISON-STREAK]`** lines (shows monotonic **`high`** ladder).
- **MULTI_BALL** — first commentary **`Δballs=`** within **400 lines** after WARN (*narrow window* — long gaps still exist).

#### GT vs RCB (24 rows)

| F | Clock | Last deltas `(ext−tracker)` | MULTI_BALL in +400 lines |
|---|-------|-----------------------------|---------------------------|
| 2827 | 21:43:18 | −12, −12, −12, **+8, +8, +8** | none |
| 3296 | 22:00:59 | **+8 ×5** | **Δballs=7** @ F3346 |
| 5054 | 23:14:42 | −115, −55, −55, −55 | none |
| 5455 | 23:29:56 | −147, −100, **+12** | none |
| 5967 | 23:43:53 | +34×2, +35×3 | none |
| 6011 | 23:45:52 | +79×5 | none |
| 6147 | 23:51:15 | +10×2, +14, +26×2 | none |
| 6279 | 23:56:05 | +16×3, +30, +34 | none |
| 6481 | 00:03:41 | +25×5 | none |
| 6542 | 00:06:00 | −154, −150, −135, −129×2 | none |
| 6746 | 00:13:33 | −139, −127, −118, −111 | none |
| 6846 | 00:17:13 | +9×2, +10×3 | none |
| 6887 | 00:18:48 | +12, +25×4 | none |
| 6895 | 00:19:26 | +17, +24×2, +29×2 | none |
| 6947 | 00:21:07 | −154, −150×2, −139, −135 | none |
| 7072 | 00:26:14 | +12×2, +16×2, +30 | none |
| 7171 | 00:29:41 | −111, −110×3 | none |
| 7284 | 00:34:40 | +24×2, +29×3 | none |
| 7335 | 00:36:21 | −154, −150×2, −139, −129×2 | none |
| 7550 | 00:43:54 | +8, +12×2, +16, +21 | none |
| 7586 | 00:45:36 | +14×3, +18, +24 | none |
| 7639 | 00:47:43 | +9×2, +10×2, +14 | none |
| 7671 | 00:49:02 | −101, +25×4 | none |
| 7688 | 00:49:53 | +17, +24, +29×3 | none |

**Long-gap MULTI_BALL:** **`F5054 → F5240`** yields **`Δballs=25`** (~1556 frames later in log — outside **400-line** heuristic).

#### MI vs SRH (4 rows)

| F | Clock | Notes |
|---|-------|-------|
| 2483 | 21:39:07 | **243 → 0** poison ladder |
| 2855 | 21:51:41 | **0 → 8** ladder |
| 2954 | 21:55:27 | **0 → 12** ladder |
| 3573 | 22:20:20 | **74 → 85** (+11); **POST_MATCH** by [**frequency §11** clock rule |

#### PBKS vs RR (7 rows)

| F | Clock | Notes |
|---|-------|-------|
| 2354 | 21:10:24 | **222 → 0** |
| 2807 | 21:23:13 | **222 → 0** repeat |
| 3074 | 21:34:26 | **0 → 37** ladder |
| 3358 | 21:45:24 | **0 → 66** ladder |
| 3474 | 21:50:51 | **0 → 80** ladder |
| 3547 | 21:54:02 | **0 → 84** ladder |
| 3604 | 21:57:54 | **0 → 92** ladder |

### A2 — TP / FP / ambiguous (evidence-bound)

Without authoritative ball-by-ball overlays, classifications below use **investigation memos + structural log evidence**.

| Class | Criteria used here | Examples |
|-------|-------------------|----------|
| **TP** | Strip progression coherent with **live chase** or **innings-2 cold-start ladder**; tracker stuck at wrong baseline | PBKS/MI **`0→37…92`** ladders; MI **`243→0`** innings-edge; **F3296** if broadcast truly **57** while tracker **49** ([`state_integrity_f3293_f3346.md`](state_integrity_f3293_f3346.md)) |
| **FP** | Tracker carried **plausible live/post score**; strip reflected **wrong genre** (interview / carousel / replay) | **F5054** (**154 vs 99** interview strip) — [`state_integrity_f5054_f5240.md`](state_integrity_f5054_f5240.md) |
| **Ambiguous** | Cannot assign without replay | **F2827** (**0 vs 12** then **20 vs 12**); **F5455** (mixed **0/47/159** vs **147**); **F7671** (**0** frame next to **126** plateau); **MI F3573** (post-clock but plausible chase digits) |

**MULTI_BALL after RECAL (commentary, extracted):**

| Trip | Next notable MULTI_BALL |
|------|-------------------------|
| **F3296** | **Δballs=7** @ F3346 |
| **F5054** | **Δballs=25** @ F5240 (late; carousel recovery) |
| *(others)* | No **`Δballs>0`** found in **±400-line** quick scan — does **not** prove absence downstream |

### A3 — Rates by bucket ([**frequency §11.4**](poison_recal_frequency_analysis.md))

| Bucket | Count |
|--------|------:|
| **Live-window** | **12** |
| **Post-match-window** | **23** |

**Definitive FP count with memo-grade evidence:** **1** (**F5054**) among **35** ≈ **2.9%** strict.

If **post-match** trips are treated as **operationally harmful** when lifecycle policy should have stopped scoring (**Direction L**), the dominant failure mode is **not** “**Δ>7** too tight” but **“pipeline still interpreting recap/interview STRIP as live truth.”**

**Stop-condition S1 (FP <10% on live-critical classification):** On **live-only** **12** fires, documented single-incident **hard FP** is **0** (**F5054** is POST). Residual ambiguity (**F2827**, **F3296**) keeps honest uncertainty **below** a **10% proven-FP** bar only if we confine the denominator to **live** — **threshold-only urgency stays low** (consistent with [`poison_recal_frequency_analysis.md`](poison_recal_frequency_analysis.md) **§11.5**).

### A4 — Cause 4 leverage on corrected denominator (live-only)

**Denominator:** **`12`** live-window **`[POISON-RECAL]`** rows ([**frequency §11.3–§11.4**](poison_recal_frequency_analysis.md)). Post-match **`23`** rows are **Direction L** scope, excluded here.

**Numerator (Cause 4):** trips where **graphic / overlay / wrong-genre template** plausibly **corrupts the headline score OCR** (not merely “a GRAPHIC frame exists nearby” while the STRIP score stays coherent).

**Operational verdict bands (vs live denominator):**

| Band | Rule |
|------|------|
| **>50%** | Cause 4 **dominant** → ship Cause 4 fix |
| **20–50%** | **Significant** → ship if **SMALL** |
| **<20%** | Cause 4 **minor** for live → prioritize **Causes 2/3** or **Direction L** |

#### Per-trip classification (12 rows)

Evidence = **`DETAIL|…|`** / **`STRIP:`** / WARN telemetry on the RECAL frame and immediate predecessors (shell replay **2026-05-01**).

| # | Tee | `F` | Classification | Evidence snapshot |
|---|-----|-----|----------------|---------------------|
| 1 | PBKS–RR | 2354 | **Genuine live divergence** | **`PBKS 0-0 (0.0)`** vs tracker **`222-4`**, **`action=… interviewed`** — innings/template vs latched **innings‑1** total ([`poison_recal_frequency_analysis.md`](poison_recal_frequency_analysis.md) §3.1 family). |
| 2 | PBKS–RR | 2807 | **Genuine** | Repeat **`0-0`** template vs **`222`** latch; close-up / break. |
| 3 | PBKS–RR | 3074 | **Genuine** | Coherent **`RR 37-0 (2.2)`** chase strip vs **`tracker 0`** cold-start ladder. |
| 4 | PBKS–RR | 3358 | **Genuine** | **`F3355`** **`tag=GRAPHIC`** carries **career INFO_PANEL**, but **team score OCR matches** **`RR 66-1`** on GRAPHIC and SCOREBOARD frames — divergence is **tracker `0`**, not misread total. |
| 5 | PBKS–RR | 3474 | **Genuine** | **`RR 80-1 (5.5)`** + normal **`INFO_PANEL`** chrome (**speed**); headline score coherent vs **`tracker 0`**. |
| 6 | PBKS–RR | 3547 | **Other (strip OCR/layout)** | Scout **`RR 84- 6.1`** — malformed wicket/overs segment vs sibling frames’ **`84-1 (6)`** shape; poison driver still **`tracker 0`**. |
| 7 | PBKS–RR | 3604 | **Genuine** | **`RR 92-1 (7.2)`** coherent vs **`tracker 0`**. |
| 8 | MI–SRH | 2483 | **GRAPHIC pollution attributed** | Composite **`MI 0-0 (0.0)`** alongside **`Rickelton … 123*(55)`** in-strip contradiction (`DETAIL|F2481|` trace) — wrong-genre / polluted header (**Cause 4-class**). |
| 9 | MI–SRH | 2855 | **Genuine** | **`SRH 8-0 (0.2)`** coherent vs **`tracker 0`**. |
| 10 | MI–SRH | 2954 | **Other** | Heavy **`INFO_PANEL`** (**HEAD v BUMRAH…**) + **`TO WIN`** line; headline **`SRH 12-0`** still internally consistent — not scored as corrupting **team total** under strict Cause 4 rule. |
| 11 | GT–RCB | 2827 | **Other** | Consecutive STRIPs disagree on **Gill/Sudharsan** rows while total **`GT 20-0`** stable — strip-row / pairing instability ([`strip_row_pairing_analysis.md`](strip_row_pairing_analysis.md) family), not cam-graphic score substitution. |
| 12 | GT–RCB | 3296 | **Other** | **`[STRIP-ROWS-MISALIGNED]`** on WARN (**Gill strip vs card**) — row pairing / strip hygiene ([`state_integrity_f3293_f3346.md`](state_integrity_f3293_f3346.md)); score **`57`** vs **`49`** is tracker divergence with **documented row skew**. |

#### Cause‑4 leverage score

| Metric | Value |
|--------|------:|
| **GRAPHIC pollution attributed** | **1** (**MI `F2483`**) |
| **Leverage (strict)** **`1 ÷ 12`** | **≈8.3%** |
| **Genuine divergence** | **7** |
| **Other (strip-row / layout OCR)** | **4** |

**Verdict:** **<20%** → under the memo rubric, **Cause 4 is not dominant for live POISON‑RECAL trips** on these tees; redirect priority to **Cause 2/3 mechanisms**, **strip-row pairing (Direction M2)**, and **Direction L** for post-match volume. Re-run **A4** after any Cause 4 ship candidate lands.

---

## Phase B2 — Counter-factual thresholds

| Alternative | Effect on canonical cases |
|-------------|---------------------------|
| **`abs(Δ) > 10`** | **Suppresses** **`|Δ| ∈ {8,9,10}`** poison. **F3296** uses **`Δ=+8`** — would **stop poisoning** → **likely misses a live TP** if tracker truly stale. **Rejected** for blanket use. |
| **Streak 7 (keep Δ>7)** | Delays **`full_reset`** by ~2 poison frames on monotonic ladders — trades slower escape vs slightly fewer trips; **no proof** it trims **F5054-class** (already sustained −55). |
| **`Δ>7` on 5 frames strict consecutive** | **Not implemented** — current design **already differs** (monotonic streak + reset on **`|Δ|≤7`**). |

**Stop-condition S2:** No alternative in **`{Δ threshold, streak length}`** is **strictly better** on documented anchors (**F3296** needs **|Δ|>7**; **F5054** survives large sustained deltas anyway).

---

## Phase C — FP anatomy & gating options

### C1 — FP / noise patterns

| Pattern | Seen where | Notes |
|---------|-----------|-------|
| **Genre mismatch strip** | **F5054** | Interview **`GT 99-6 (13.5)`** vs tracker **`154-6`** |
| **Post-match numeric carousel** | GT **`23:`–`00:`** majority | Tracker vs strip **plateaus** (**126/155/20** families per [**frequency §11**]) |
| **Innings-edge template zeros** | PBKS/MI early RR/MI rows | Real **`0`** template vs latched **220+** — trips are often **useful** (cold-start), not OCR noise |
| **Single-field score disagreement** | **F3296** | **`+8`** score-only divergence — candidate for **multi-axis corroboration** if wickets/overs stable |

### C2 — Smoothing / gating options

| Option | Merit | Risk / scope |
|--------|-------|----------------|
| **A — median-of-7 pre-trip** | Absorbs single-frame OCR spikes | Needs rolling buffer; interacts poorly with **real** monotonic climbs |
| **B — paired delta (score + wickets + overs)** | Targets **score-only** hallucination | **MEDIUM**: false negatives when strip score wrong but wickets/overs accidentally agree |
| **C — confidence weighting** | Theoretically attractive | **MEDIUM**: plumbing **`frame_type` confidence** into poison watchdog |
| **L — lifecycle / phase gate** (from freq memo) | Addresses **most POST_MATCH rows** | **MEDIUM** — orthogonal to **Cause 4** overlap fixes; **re-measure after Cause 4** per charter |

### C3 — Recommendation

**Verdict:** **`SMALL` implementation of net-new trip logic is not justified here.**

1. **S1 + S2:** Live-window **FP pressure is thin** at memo-grade certainty; naive threshold moves **hurt** at least one anchor (**F3296** vs **`Δ>10`**).
2. **Dominant pain:** **POST_MATCH / carousel** trips (**23/35**) — fix class is **lifecycle gating (Direction L)** (**§A4:** live trips show **low strict Cause‑4 leverage**).
3. **If Cause 4 lands first:** Re-run **A3** on fresh tees — FP mix may shift; avoid locking **`Δ`** knobs until then (**interaction note**).

**Best incremental engineering (when permitted MEDIUM scope):** Phase veto / strip-trust policy **before** mutating poison arithmetic; optional **investigation-only** paired-field analysis on **`F3296` DETAIL** wickets/overs rows next replay pass.

---

## Phase D — Implementation status

**Deferred:** No **`test_pipeline.py`** edit in this pass (**D1–D3**).

**Rationale:** **C3** scope → **MEDIUM** (lifecycle / paired-field / confidence). Ship gate **`SMALL`** not met.

If a future **`SMALL`** patch is approved, minimal bundle would be:

- **D1** poison block (**≈7994+**).
- **D2** **`[POISON-RECAL-GATED]`** INFO with would-be streak snapshot.
- **D3** pytest mirrors (**`test_recent_fixes.py`**) for TP preserve / FP suppress / ambiguous conservative.

---

## References (code)

Poison / streak / RECAL emission:

```8068:8092:files/test_pipeline.py
                            if (_poison_streak_count
                                    >= _POISON_RECAL_THRESHOLD):
                                log.warn(
                                    f"  [POISON-RECAL] {_poison_streak_count} "
                                    f"consecutive POISON'd reads "
                                    f"(high={_poison_streak_new_score}, "
                                    f"latest={_ext_score_int}) — tracker "
                                    f"baseline {_cur_score_int_check} is "
                                    f"stale. Clearing tracker innings + "
                                    f"forcing ScoreManager cold-start.")
                                scoreboard._inn["score"] = None
                                scoreboard._inn["wickets"] = None
                                scoreboard._inn["overs"] = None
                                try:
                                    score_mgr.full_reset(
                                        reason=(
                                            "poison_recal_consensus "
                                            f"stuck_tracker={_cur_score_int_check}"
                                            f"→live={_ext_score_int}"))
                                except Exception as e:  # noqa: BLE001
                                    log.debug(
                                        f"[POISON-RECAL] SM recal "
                                        f"swallowed: {e}")
                                _poison_streak_new_score = None
                                _poison_streak_count = 0
```

Streak clearing when divergence drops:

```8251:8257:files/test_pipeline.py
                        # No poison spike on this frame → clear the
                        # stuck-tracker watchdog streak (only the
                        # abs(delta)>7 branch above accumulates it).
                        if abs(_delta_check) <= 7:
                            _poison_streak_new_score = None
                            _poison_streak_count = 0
```

---

*Investigation memo — no production code change in this commit.*

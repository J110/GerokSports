# Direction M — Batter slot churn, stats coupling, and Lever 1 disposition

**Phase:** Forensic log + code analysis (**investigation only**). **No code changes.** **No fix proposals** beyond mechanism characterization and a concrete **Direction M2** follow-up.

**Purpose:** Explain why **`[WS-SLOT-INVARIANT]`** remained dense on GT–RCB (**345** fires in the postmortem live slice) despite Lever 1 PR1–PR4 shipping and charter-style **73–87%** reduction **targets** ([`MONITORING_CHARTER.md`](../MONITORING_CHARTER.md)). Trace representative incidents, separate **duplicate-slot** telemetry from **strip row / stats mis-association**, and rank Patterns **P/Q/R/S**.

**Primary anchors:** [`match_postmortem_data_gt_rcb_20260430.md`](match_postmortem_data_gt_rcb_20260430.md) §3.C / §4; [`poison_recal_frequency_analysis.md`](poison_recal_frequency_analysis.md) §11 (live vs post-match boundaries).

---

## §1 Executive summary

### §1.1 Per-match **`[WS-SLOT-INVARIANT]`** inventory (tee files on disk)

| Tee | Total file | GT **postmortem window** `[≥19:50, ≤22:17:45]` | Notes |
|-----|-----------:|--------------------------------------------------:|-------|
| `logs/pipeline-2026-04-30-gt-rcb-live.log` | **485** | **345** | Reproduces postmortem §3.C headline count exactly on bracket filter. |
| `logs/pipeline-2026-04-29-194416-mi-srh-live.log` | **122** | **122** | Entire capture lies inside poison§11 live span (**19:45:47→22:19:37**). |
| `logs/pipeline-2026-04-28-pbks-rr-live.log` | **387** | **387** | Same span **19:32:13→22:22:40** covers full file. |

**Approximate live intensity:** GT postmortem slice **≈2.35 fires/min** (**345 / 147 min**); PBKS live **≈2.28/min** (**387 / 170 min**); MI live **≈0.79/min** (**122 / 154 min**). Naïve **GT/MI = 2.83×** raw counts (**§4** caution from postmortem still applies); **rate-normalized**, GT lines up with **PBKS**, not MI — indicating **match graphic / innings-phase pathology**, not a universal regression multiplier.

### §1.2 Distribution discovery (GT — dominant phases)

Bracketing **`[WS-SLOT-INVARIANT]`** by tee-line proxies aligned to [`match_postmortem_data_gt_rcb_20260430.md`](match_postmortem_data_gt_rcb_20260430.md) milestones:

| Phase proxy | Tee-line heuristic | Count within **345** postmortem fires |
|-------------|-------------------|--------------------------------------:|
| **RCB innings 1** | Lines **before ~23683** (`[INNINGS-BREAK]` region) | **279** (**81%**) |
| **Innings gap / transition** | **23683–25341** (break → first chase enqueue) | **58** (**17%**) |
| **GT chase core clock `21:28–22:17`** | Wall-clock filter | **8** (**2%** of postmortem fires) |

**Chase-core desert:** Between **`21:28:00`** and **`22:17:45`**, only **eight** **`[WS-SLOT-INVARIANT]`** lines appear — clustered at **`~22:17`** (**Washington Sundar** tail). The heavy POISON / **`MULTI_BALL`** / **`STRIP-ROWS-MISALIGNED`** chase narrative (**[`state_integrity_f3293_f3346.md`](state_integrity_f3293_f3346.md)**) largely **does not** coincide with **`[WS-SLOT-INVARIANT]`** density.

### §1.3 Pattern classification (evidence-ranked)

| Pattern | Summary | Rank |
|---------|---------|------|
| **P** — Lever 1 **detect-and-repair loop** vs **unchanging upstream drift** | **`enforce_ws_slot_invariant`** fires whenever WS projection yields **`striker == non`** after **`[WS-SCRUB]`** swaps dismissed names onto slots; dedup clears/rebuilds **names**, while **`[WS-SCRUB]`** re-introduces bad striker on subsequent frames (`§3`, `§6`). | **HIGH** |
| **R** — **Different symptom class** (stats ↔ rows) | **`[STRIP-ROWS-MISALIGNED]`** demonstrates **runs paired to wrong batter row** while separate layers still emit coherent **`STATE`** lines (`§4`). **`[WS-SLOT-INVARIANT]`** does **not** observe runs — only duplicate **canonical slot names**. | **HIGH** |
| **S** — **External resets** | **[POISON-RECAL]** live windows documented in [`poison_recal_frequency_analysis.md`](poison_recal_frequency_analysis.md) §11 show **no** neighboring **`[WS-SLOT-INVARIANT]`** burst at **`F2827`** / **`F3296`** (`§3.4`). Innings transition **does** concentrate **`[WS-SLOT-INVARIANT]`**, but mechanism remains **Cause-P scrub loops**, not SM `full_reset` alone. | **MEDIUM** |
| **Q** — **Lever 1 regression** | **`_set_slot_pair`** / **`[SM-SLOT-INVARIANT]`** semantics match design (`§5`). **`reason=batter-arrival`** **`[STRIKER-SM-CUTOVER]`** barely fires on MI (**0**) and once on GT (**outside** postmortem window) — suggesting **telemetry vacuum**, not proven inverse causality from a defective helper (`§7`). | **LOW** |

### §1.4 Lever 1 disposition (unflinching)

Lever 1 PR1–PR4 **code is present and behaves as documented** for SM atomic writes and PR3 arrival cutover (**§5**). The GT–RCB **`[WS-SLOT-INVARIANT]`** surge is **not** credible evidence that **`_set_slot_pair` “created”** duplicate slots at SM.

Instead:

1. **`[WS-SLOT-INVARIANT]` is overwhelmingly a WS-boundary backstop** (`enforce_ws_slot_invariant`) reacting to **`[WS-SCRUB]`**-amplified striker/non collisions while **`batting_card`** still lists exactly **one** active batter (**§3 incidents 1 & 5**).
2. The **73–87% reduction prediction** assumed comparability to **MI innings-1 Cause-(C)** baselines and meaningful **`batter-arrival`** cutover volume (**§7**) — **neither holds** on these captures (GT dominated by innings **1**, PBKS dominated by **Marcus Stoinis** duplicates with **zero** “rebuilt non” repairs vs GT’s split).

### §1.5 Direction recommendation (**Direction M2**)

**Primary:** **Scoreboard strip ingestion audit** — pairing of OCR batter **rows** to **`batting_card` entries** (`[STRIPS-ROW-MISALIGNED]` family + **`eyes/scoreboard.py`** parsing), **before** further Lever 1 knob-turning.

**Secondary:** **`[WS-SCRUB]` admission policy review** — repeated **`status_out`** striker fallback onto sole survivor yields tight **`[WS-SLOT-INVARIANT]`** loops (**§3.1**) — orthogonal to duplicate-slot atomicity.

---

## §2 Per-match inventory (Phase A)

### §2.1 Method — live windows

| Tee | Live span used here | Seconds |
|-----|---------------------|--------:|
| GT–RCB | **Postmortem parity:** **`HH:MM:SS ∈ [19:50:00, 22:17:45]`** | matches §3.C **345**. Also report **full-file** **485** (tee continues past postmortem “truncation” narrative per extended capture). |
| MI–SRH | Poison §11: **19:45:47 → 22:19:37** (`ME+5` from last **`[DELIVERY ENQUEUED]`**) | equals whole file (**122**). |
| PBKS–RR | Poison §11: **19:32:13 → 22:22:40** | equals whole file (**387**). |

### §2.2 **`rebuilt non=` vs `cleared non`** split

| Tee | **`rebuilt non=`** | **`cleared non`** |
|-----|------------------:|------------------:|
| GT postmortem **345** | **160** | **185** |
| MI **122** | **0** | **122** |
| PBKS **387** | **0** | **387** |

GT diverges sharply: **`batting_card`** frequently exposes **two distinct active batters**, permitting **`enforce_ws_slot_invariant`** to **repair non** rather than clearing it.

### §2.3 Top duplicate names

**GT postmortem 345:** **Bhuvneshwar Kumar** **114**, **Josh Hazlewood** **58**, **Rajat Patidar** **53**, **Romario Shepherd** **45**, **Krunal Pandya** **25**, **Venkatesh Iyer** **20**, …  
**MI 122:** **Will Jacks** **62**, **Naman Dhir** **29**, **Ryan Rickelton** **29**, …  
**PBKS 387:** **Marcus Stoinis** **370**, **Prabhsimran Singh** **17**.

**Stop-condition S2:** GT/PBKS show **bowler / tail batter names** dominating duplicates — consistent with **strip layout mis-reads** or **both slots populated from bowler-adjacent rows**, not only classical “two openers swapped.”

### §2.4 Supporting telemetry (GT postmortem window)

From [`match_postmortem_data_gt_rcb_20260430.md`](match_postmortem_data_gt_rcb_20260430.md) §4 — **`[STRIKER-SM-CUTOVER]`** reasons:

| Reason | Count |
|--------|------:|
| `over-end` | **40** |
| `broadcast-indicator` | **3** |
| `broadcast-indicator-swap` | **2** |
| `active-slot-dedup` | **3** |

**`[BATTERS-INVARIANT]`:** **79×**, **`rule=C`** only (**0× `rule=A`**) — aligns with **admission-window / striker_non_collision** churn rather than swap-admit Pattern A fires (**§3.C** narrative drift).

**`[SM-W8-DISMISSED-GUARD]`:** **0** on GT tee (**[`match_postmortem_data_gt_rcb_20260430.md`](match_postmortem_data_gt_rcb_20260430.md)** §4).

---

## §3 Sample incident traces (Phase B)

### §3.1 Incident I1 — Early innings **1**, **Rajat Patidar** cluster (**`F383–F395`**)

**Representative tee lines:** **`5369–5396`** (`logs/pipeline-2026-04-30-gt-rcb-live.log`).

**Sequence (condensed):**

1. **`[20:11:12 F383]`** wicket choreography accepts **`Devdutt Padikkal`** dismissal while **`batting_card`** / DETAIL strip still surfaces **`Padikkal`** as active (`DETAIL|F383|… AFTER_bat1=Rajat Patidar 19(15)|AFTER_bat2=—|AFTER_striker=Devdutt Padikkal`).
2. **`[WS-SCRUB] striker='Devdutt Padikkal' rejected reason=status_out`** → fallback **`Rajat Patidar`** (#1).
3. **`[WS-SLOT-INVARIANT] duplicate slots 'Rajat Patidar'; cleared non (no alternate active batter)`** — **`batting_card` active list** only **`Patidar`**.
4. Subsequent frames (**`F384`–`F392`**) repeat **`[WS-SCRUB]`** on **`Padikkal`** (#2–#6) → duplicate **`Patidar`** invariant clears until **`[STATE-RECOVERY-OVERRIDE-CANDIDATE]`** fires (**`F390`**).

**Assessment**

| Lens | Finding |
|------|---------|
| Trigger | **`[WS-SCRUB]`** repeatedly assigns **`striker`** from stale **`score_mgr`/projection path** to dismissed **`Padikkal`**, fallback collapses both slots onto survivor **`Patidar`**. |
| Lever 1 PR1 dedup | **`enforce_ws_slot_invariant`** clears **`non`** — **does not** stop next-frame **`[WS-SCRUB]`** from re-colliding slots. |
| Stats correctness | DETAIL **`AFTER_bat*`** rows lag wicket strip (`Padikkal` still enumerated as crease batter). User-visible **random numbers** plausibly originate **upstream** of invariant (`§4`). |

### §3.2 Incident I2 — Innings transition (**`F2121–F2125`**)

**Tee lines:** **`23640–23685`** region.

**Sequence:**

1. **`[WS-SCRUB] striker='Venkatesh Iyer' rejected reason=status_out`** (#253+) → fallback **`Bhuvneshwar Kumar`** while **`active=['Bhuvneshwar Kumar', 'Josh Hazlewood']`** (tailenders).
2. **`[WS-SLOT-INVARIANT] duplicate slots 'Bhuvneshwar Kumar'; rebuilt non='Josh Hazlewood'`** — repairs duplicate because **two active batters exist**.
3. **`[CAM-GRAPHIC-FAST-PATH-READ]`**, **`[INNINGS-BREAK]`**, wickets latch oscillations (**`10→6` regression rejected**) interleave — graphic / latch ambiguity persists alongside scrub loop.

**Assessment:** Demonstrates **`rebuilt non=`** path tied to **two living batting_card entries**, contrasting **I1** cleared-non behavior.

### §3.3 Incident I3 — **“Early innings 2” expectation vs telemetry desert**

**Sampling outcome (stop-condition S6 nuance):** There is **no dense `[WS-SLOT-INVARIANT]` cluster** during **`21:28–22:17`** chase core (**only eight** fires total in postmortem window).

**Substitute trace — chase instability without duplicate-slot telemetry:**

- **`[21:43:18 F2827]`** **`[POISON-RECAL]`** (**tee line `28677`**) — immediate **`DETAIL|F2827`** shows strip **`GILL/SUDHARSAN`** totals inconsistent with **`BEFORE_bat*`** (**[`poison_recal_frequency_analysis.md`](poison_recal_frequency_analysis.md)** companion narrative).
- **`[STRIP-ROWS-MISALIGNED]`** bursts (**e.g.** tee lines **`28864+`**, **`29642+`**) cite **`Shubman Gill`** **`strip_runs ≫ card_runs`**.

**Assessment:** Chase-phase user pain aligns with **strip-row decoding**, **`FRAME_POISONED`**, **SM resets**, **not** **`[WS-SLOT-INVARIANT]`** density.

### §3.4 Incident I4 — Late chase tail (**`~22:17`**, **Washington Sundar**)

**Representative tee lines:** **`37105–37134`** excerpt (`**F3657–F3718**` neighborhood).

Observed **`[22:15:22 F3657 BOARD] [STRIKER-COLLISION] Refusing non=Washington Sundar — already striker`** — SM refuses symmetric assignment before downstream WS assembly.

Shortly after (**postmortem tail **`22:17`** cluster), **`[WS-SLOT-INVARIANT] duplicate slots 'Washington Sundar'`** repeats (**cleared non**) — same structural pattern as **I1**: surviving singleton active batter after collisions.

### §3.5 Incident I5 — **Josh Hazlewood** duplicate burst (**`F2260–F2271`**)

**Tee lines:** **`24348–24414`** (`logs/pipeline-2026-04-30-gt-rcb-live.log`).

Repeated **`duplicate slots 'Josh Hazlewood'; cleared non (no alternate active batter)`** — bowler-as-card-holder pattern consistent with **`§2.3`** bowler-heavy histogram (**stop-condition S7 subtype**: OCR / layout coupling).

---

## §4 Stats-swap mechanism (Phase B3)

### §4.1 What **`[WS-SLOT-INVARIANT]`** does **not** observe

```2296:2319:files/test_pipeline.py
def enforce_ws_slot_invariant(state: dict,
                              scoreboard,
                              canon_fn) -> bool:
    """Ensure WS striker/non never name the same active player."""
    striker = state.get("striker")
    non = state.get("non")
    if not striker or not non or striker != non:
        return False
    bc = getattr(scoreboard, "batting_card", None) or {}
    active = [name for name, card in bc.items()
              if card and card.get("status") == "batting"]
    duplicate = striker
    alternate = next((name for name in active if name != duplicate), None)
    if alternate:
        state["non"] = canon_fn(alternate)
        log.warn(
            f"  [WS-SLOT-INVARIANT] duplicate slots {duplicate!r}; "
            f"rebuilt non={alternate!r} from active card")
    else:
        state["non"] = None
        log.warn(
            f"  [WS-SLOT-INVARIANT] duplicate slots {duplicate!r}; "
            f"cleared non (no alternate active batter)")
    return True
```

Runs (`bat*_runs`) live under **`scoreboard.batting_card`** entries — **not** in **`state["striker"]` / `state["non"]`**. Duplicate-name repair **cannot** flip which numeric tuple attaches to which batter unless **`batting_card`** itself is corrected elsewhere.

### §4.2 Pipeline-side evidence for **flipped / drifting stats**

| Signal | Illustration |
|--------|--------------|
| **`[STRIP-ROWS-MISALIGNED]`** | Tee **`28864`** — **`frame=F2832`** **`row_delta=21`** **`Shubman Gill strip_runs=28 card_runs=7`** (`logs/pipeline-2026-04-30-gt-rcb-live.log`). Similar **`row_delta=99`** bursts at **`29642`** (**`F2880`**). |
| **Guard rail vs tracker** | **`[22:00:59 F3296]`** **`[STRIP-ROWS-MISALIGNED]`** / **`Gill strip_runs=43 card_runs=6`** immediately precedes **`[POISON-RECAL]`** (**[`poison_recal_frequency_analysis.md`](poison_recal_frequency_analysis.md)** §3.3). |

**Interpretation:** User observation (“random numbers … settled flipped”) maps cleanly to **`strip ↔ card row pairing instability`** plus tracker reconciliation — **Pattern R HIGH**. **`[WS-SLOT-INVARIANT]`** telemetry **misleadingly counts “slot hygiene work”** unrelated to numeric correctness.

---

## §5 Code path analysis (Phase C)

### §5.1 **`[WS-SLOT-INVARIANT]` emission**

**Site:** `files/test_pipeline.py` **`enforce_ws_slot_invariant`** (**2296–2319**) — invoked from **`build_full_payload`** immediately after **`[WS-SCRUB]`** admissions (**4024–4038**).

```4024:4038:files/test_pipeline.py
                log.warn(
                    f"  [WS-SCRUB] {_slot}='{_nm}' rejected "
                    f"reason={_reason} "
                    f"(#{_scrub_counts[_key]}) "
                    f"→ fallback={_fallback!r} "
                    f"active={_active}")
                ...
                state[_slot] = _fallback
            if enforce_ws_slot_invariant(
                    state, scoreboard, canon_player_name):
                record_state_recovery_guard(
                    "slot_collision_rejected",
                    proposed_reset=["slot:striker", "slot:non"])
```

**Trigger:** **`striker` and `non` canon-equal** post-scrub.

### §5.2 Lever 1 **`_set_slot_pair`** (PR2)

```993:1017:files/score_manager.py
    def _set_slot_pair(self, striker: str | None, non: str | None,
                       *, source: str) -> None:
        ...
        if _s is not None and _ns is not None and _s == _ns:
            log.warn(
                f"[SM-SLOT-INVARIANT] duplicate slots {_s!r} "
                f"(source={source}); clearing non")
            _ns = None
        self.striker, self.non = _s, _ns
```

SM clears **`non`** when canonical collision occurs — mirrored philosophy to WS backstop.

### §5.3 PR3 **`batter-arrival` cutover**

```2488:2514:files/test_pipeline.py
def _pr3_batter_arrival_slot_cutover(
        score_mgr, scoreboard, admitted_batter_key: str) -> None:
    ...
    if _is_card_out(score_mgr.non):
        _set_legacy_active_slot(
            score_mgr, scoreboard, "non",
            admitted_batter_key, "batter-arrival")
    elif _is_card_out(score_mgr.striker):
        _set_legacy_active_slot(
            score_mgr, scoreboard, "striker",
            admitted_batter_key, "batter-arrival")
```

**Observation:** Requires **`REPLACE`** admission path AND **`score_mgr.{slot}` still referencing card-marked `out`**. **`grep reason=batter-arrival`** yields **MI `0`**, **GT `1`** (**tee line `41617`**, **`22:31:59 F4040`** — **outside** postmortem **`22:17:45`** window). PR3 telemetry **did not materially animate** during MI comparison tee nor within GT sealed “live observation” cutoff.

### §5.4 Slot vs stats coupling — takeaway

Projection chooses **who** is striker/non; **`eyes/scoreboard.py`** extraction + scorer merges decide **numeric tuples** stored per **`batting_card[key]`**. **`enforce_ws_slot_invariant`** cannot swap stats — aligning **Pattern R**.

---

## §6 Pattern evaluation (Phase D)

| Pattern | Evidence FOR | Evidence AGAINST | Confidence |
|---------|--------------|-------------------|------------|
| **P** | Repeating **`[WS-SCRUB]`→duplicate→repair** loops (**§3.1**); **`STATE-RECOVERY-OVERRIDE-CANDIDATE`** coupling (**§3.1**) | Would need replay proving **`batting_card`** perfectly stable while duplicates persist — not shown | **HIGH** |
| **Q** | — | Helpers + telemetry behave per **`§5`**; MI regression would imply elevated **`[SM-SLOT-INVARIANT]`** — not investigated as spike here | **LOW** |
| **R** | Dense **`[STRIP-ROWS-MISALIGNED]`** during chase absent **`[WS-SLOT-INVARIANT]`** companion (**§4**) | UI-only flip not ruled out without WS payload captures | **HIGH** |
| **S** | Innings transition concentration (**§2**) | **[POISON-RECAL]** windows lack **`[WS-SLOT-INVARIANT]`** bursts (**§3.3–§3.4**) | **MEDIUM** |

**Stop-condition S3:** Five samples span **distinct mechanisms** (scrub-loop singleton vs dual-active rebuild vs chase desert vs collision guard vs bowler duplication) — unified root still **`strip/scorer coherence`**, not SM rotation atomicity alone.

---

## §7 Implications for prior shipments

1. **Lever 1 PR1–PR4 shipped** — **`score_manager.py`** contains **`_set_slot_pair`** with **`source=`** telemetry contract (**993–1017**); **`test_pipeline.py`** wires **`_pr3_batter_arrival_slot_cutover`** (**2488–2514**).
2. **73–87% reduction prediction** ([`MONITORING_CHARTER.md`](../MONITORING_CHARTER.md)) assumed meaningful **`batter-arrival`** firing rate and comparable innings-phase baselines — **this corpus violates both** (**§2.4**, **`§5.3`**).
3. **`[WS-SLOT-INVARIANT]` must never serve alone as stats correctness KPI** — chase-phase instability expresses primarily via **`[STRIP-ROWS-MISALIGNED]`**, **`FRAME_POISONED`**, **`MULTI_BALL`** (**[`state_integrity_f3293_f3346.md`](state_integrity_f3293_f3346.md)**).

---

## §8 Direction recommendation (Phase E)

### §8.1 Direction **M2 — Scoreboard row / stats pairing audit**

| Scope | Actions |
|-------|---------|
| **Deep** | Thread **`[STRIPS-ROW-MISALIGNED]`** counters through **`eyes/scoreboard.py`** parsing → scorer assignment (`files/scorer_decision_schema.py` bat merge sites). Build **pairing invariant tests** using **`F2832`**, **`F2880`**, **`F3296`** frames as fixtures (**investigation harness**, separate ticket). |
| **Medium** | **`[WS-SCRUB]`** policy — damp oscillation when **`status_out`** striker repeats across consecutive frames (**§3.1**). |
| **Lever 1-specific** | Instrument **`_pr3_batter_arrival_slot_cutover` callsites vs `[REPLACE]` admissions** — verify PR3 triggers on GT/MI captures where **`rule=C`** dominates (**§2.4**). |

### §8.2 What would flip recommendation

| Observation | Revised priority |
|-------------|------------------|
| Replayed frames show **`batting_card`** numerically correct while **`state.striker/non`** oscillate | Escalate **Lever 1 SM feeder / `_canonical_active_slot`** investigation |
| Analyzer proves **`[SM-SLOT-INVARIANT]`** spikes precede **`[WS-SLOT-INVARIANT]`** causally | Re-open **Pattern Q** with regression bisect |

---

## §9 Limitations

1. **Five traced incidents** vs **345** postmortem fires — qualitative, not exhaustive (**stop-condition S3** documented).
2. **No interactive replay** — conclusions tied to tee text only.
3. **Ground truth** — no authoritative scorecard keyed per frame.
4. **PBKS/MI baselines** share **`§2` methodology**, but PBKS **`Marcus Stoinis`** dominance suggests **graphic pathology unrelated** to GT specifics (**S2**).
5. **Log extension** — GT file now registers **`485`** total **`[WS-SLOT-INVARIANT]`** vs postmortem **345** — comparisons must always cite window predicate (**§2.1**).

---

## §10 Cross-references

| Artifact | Role |
|----------|------|
| [`match_postmortem_data_gt_rcb_20260430.md`](match_postmortem_data_gt_rcb_20260430.md) | §3.C counts, §4 telemetry table, innings milestones |
| [`poison_recal_frequency_analysis.md`](poison_recal_frequency_analysis.md) §11 | Live/post boundaries; **[POISON-RECAL]** frame cites |
| [`state_integrity_f3293_f3346.md`](state_integrity_f3293_f3346.md) | Chase **`MULTI_BALL`** + strip misalignment companion |
| [`lever1_pr3_redesign.md`](lever1_pr3_redesign.md) | PR3 narrative vs **`reason=batter-arrival`** scarcity |
| [`thread7_rediagnosis_multi_ball_gap.md`](thread7_rediagnosis_multi_ball_gap.md) | Strip transpose hypothesis adjacent to **`STRIP-ROWS-MISALIGNED`** |
| `files/test_pipeline.py` **2296–2319**, **4024–4038**, **2488–2514** | WS invariant + scrub + PR3 cutover |
| `files/score_manager.py` **993–1017** | **`_set_slot_pair`** |

---

*Investigation memo — closing Direction M characterization.*

# Direction M2 — Strip-row OCR ↔ `batting_card` pairing (forensic memo)

**Phase:** Investigation only. **No production code changes.** **No shipped fix proposals** beyond mechanism characterization and **fix-scope / risk estimates**.

**Purpose:** Characterize how strip OCR batter rows join `scoreboard.batting_card`, explain what triggers **`[STRIP-ROWS-MISALIGNED]`**, relate that telemetry to user-visible **“flipped stats”** (wrong runs on wrong batter slot), and bound remediation complexity. This memo responds to Direction **M** Pattern **R** (orthogonal to Lever 1 **`[WS-SLOT-INVARIANT]`** name-only repair) per [`batter_stat_swapping_analysis.md`](batter_stat_swapping_analysis.md).

**Primary anchors:** [`match_postmortem_data_gt_rcb_20260430.md`](match_postmortem_data_gt_rcb_20260430.md) §4 / §10; [`state_integrity_f3293_f3346.md`](state_integrity_f3293_f3346.md); [`logs/pipeline-2026-04-30-gt-rcb-live.log`](../../../logs/pipeline-2026-04-30-gt-rcb-live.log); [`test_pipeline.py`](../../test_pipeline.py); [`eyes/scoreboard.py`](../../eyes/scoreboard.py); [`score_manager.py`](../../score_manager.py); [`scorer_decision_schema.py`](../../scorer_decision_schema.py).

---

## §1 Executive summary

### §1.1 Per-match **`[STRIP-ROWS-MISALIGNED]`** counts

Counts use **`grep -cE 'STRIP-ROWS-MISALIGNED|STRIPS-ROW-MISALIGNED'`** on pipeline tees:

| Tee file | Count |
|---------|------:|
| `logs/pipeline-2026-04-30-gt-rcb-live.log` | **221** |
| `logs/pipeline-2026-04-29-194416-mi-srh-live.log` | **0** |
| `logs/pipeline-2026-04-28-pbks-rr-live.log` | **0** |

GT–RCB is **massively elevated** versus the two baseline tees on disk for this telemetry tag.

Within GT–RCB, bracketing Wallace timestamps **`HH:MM:SS ∈ [19:50:00, 22:17:45]`** (postmortem live parity per Direction **M**) yields **119** parsed events — matching [`match_postmortem_data_gt_rcb_20260430.md`](match_postmortem_data_gt_rcb_20260430.md) §4 headline.

### §1.2 Hypothesis ranking (evidence-backed)

| ID | Hypothesis | Plausibility | Confidence |
|----|------------|--------------|------------|
| **H1** | Strip OCR sometimes associates **runs/balls with the wrong batter label** within the strip row pair (transpose / column slip). | **HIGH** | **Strong** — consecutive frames [`logs/pipeline-2026-04-30-gt-rcb-live.log`](../../../logs/pipeline-2026-04-30-gt-rcb-live.log) tee **2971** vs **3010**: Padikkal/Patidar pair swaps plausible digit attachment while headline score unchanged. |
| **H6** | Strip strings sometimes describe **wrong match slice / wrong innings graphic** (comparison / replay / latch), so **named rows disagree with tracker-backed `batting_card`** by large deltas while **`STATE`** stays coherent. | **HIGH** | **Strong** — [`logs/pipeline-2026-04-30-gt-rcb-live.log`](../../../logs/pipeline-2026-04-30-gt-rcb-live.log) tee **33659–33681** (`F3292`): headline **`GT 57-1`** vs **`STATE`** **`RCB 49-1`**; tee **37316–37342** (`F3666`): **`GT 44-6`** strip vs **`STATE`** **`RCB 90-2`**. |
| **H4** | **Broadcast striker indicator / slot semantics** drift relative to OCR row ordering (`[STRIKER-COLLISION]`, slot churn in **`STATE`** vs **`DETAIL`** striker lines). | **MEDIUM** | **Moderate** — tee **28895** (`F2835`): `[STRIKER-COLLISION]`; **`STATE`** vs **`DETAIL`** striker disagreement examples at tee **4451** (`F300`) vs **4445**. |
| **H2** | **`resolve_name`** fuzzy routing sends strip tokens to **wrong canonical batting_card key**, so comparisons touch the wrong row. | **MEDIUM–LOW** | **Moderate** — fuzzy bowler mismatch visible tee **37341** (`F3666`) (**Mohammed Shami** → **Mohammed Siraj**); batters fuzzy-match logs often show **high similarity**, reducing but not eliminating mis-key risk. |
| **H3** | **`extracted.pop('batters')`** frames leave downstream layers applying **partial / stale scorer projections** before consensus catches up. | **LOW–MEDIUM** | **Limited direct proof** in five traces; poisoning + **`FRAME_POISONED`** streaks correlate with stalled updates rather than sustained wrong-card inversion in the sampled **`DETAIL`** snapshots. |
| **H5** | **`score_manager`** applies **wrong mapping** independent of scoreboard truth. | **LOW** as root cause | **Strong negative** — getters read **`batting_card[self.bat{N}_name]`** ([`score_manager.py`](../../score_manager.py) lines **283–357**); errors propagate from **wrong slot names or wrong card cells**, not an alternate indexing scheme inside SM. |

**Stop-condition S1:** **`[STRIP-ROWS-MISALIGNED]` is not emitted from `eyes/scoreboard.py`.** Emission lives in **`apply_comparison_strip_batter_row_delta_guard`** ([`test_pipeline.py`](../../test_pipeline.py) lines **2976–3028**), invoked from the extraction guard rail ([`test_pipeline.py`](../../test_pipeline.py) lines **7231–7245**). Upstream pairing still flows vision strip → extractor JSON **`batters[]`** → scoreboard merges — but **telemetry naming in ops traces refers to this pipeline guard**, not a scoreboard logger.

### §1.3 Recommended fix-shape (scope class)

**MULTI-HIGH concurrent mechanisms (stop-condition S4):** **H1 row/stat mis-association** and **H6 wrong-graphic / wrong-match headline** both fit substantial log evidence; **H4** contributes episodic churn around striker collisions.

⇒ Overall remediation shape class: **LARGE → phased**, beginning with **strip fidelity / headline–team coherence gates** and **pair-consistency checks before trusting `batters[]`**, rather than a single-line flip.

### §1.4 Confidence in §1.3

**Medium.** Five deep traces anchor narratives, but **119** GT window fires imply diversity beyond the sampled frames; **`debug_frames_archive`** was not readable in this workspace (**§9**), limiting OCR-ground-truth confirmation.

---

## §2 Per-match inventory (Phase A)

### §2.1 Methods

- **Counts:** shell **`grep -c`** as above (telemetry token spelled **`STRIP-ROWS-MISALIGNED`** consistently on GT tee).
- **Parsed distributions:** Python regex on stripped ANSI (`\x1b[[0-9;]*m`) with capture:

  `\[STRIP-ROWS-MISALIGNED\] frame=F(?P<f>\d+) row_delta=(?P<rd>\d+) .* row_pair=(?P<rp>.+?) strip_runs=(?P<sr>\d+) card_runs=(?P<cr>\d+)`

### §2.2 GT full file vs postmortem window

| Slice | Events |
|-------|-------:|
| Full `pipeline-2026-04-30-gt-rcb-live.log` | **221** |
| Wallace **`∈ [19:50:00, 22:17:45]`** | **119** |

### §2.3 **`row_pair` concentration (119-window)**

Top canonical names resolved at guard time:

| `row_pair` | Count |
|------------|------:|
| Shubman Gill | 80 |
| Sai Sudharsan | 27 |
| Devdutt Padikkal | 8 |
| Rajat Patidar | 2 |
| Krunal Pandya | 1 |
| Jos Buttler | 1 |

### §2.4 Magnitude distributions (119-window)

**`row_delta`** buckets (matches **`abs(strip_runs − card_runs)`** because emission sets `row_delta` that way — [`test_pipeline.py`](../../test_pipeline.py) lines **3016–3025**):

| Bucket | Count |
|--------|------:|
| 21–25 | 6 |
| 26–35 | 45 |
| 36–45 | 63 |
| 46+ | 5 |

Dominant mismatches are **large** (≥26 runs), not marginal OCR jitter.

### §2.5 Phase concentration (tee-line heuristic)

Using Direction **M** style breakpoints (**innings-break region ≈ tee line `23683`**, first chase enqueue proxy **`25341`** per [`batter_stat_swapping_analysis.md`](batter_stat_swapping_analysis.md)):

| Phase proxy | STRIP-ROWS events (119-window) |
|-------------|-------------------------------:|
| Tee lines **before** `23683` | **11** |
| Tee lines **`23683–25341`** (gap / transition band) | **0** |
| Tee lines **`≥ 25341`** (chase-heavy) | **108** |

Chase-heavy concentration aligns Pattern **R** with **chase telemetry pain** distinct from innings-1-heavy **`[WS-SLOT-INVARIANT]`** ([`batter_stat_swapping_analysis.md`](batter_stat_swapping_analysis.md) §1.2).

### §2.6 Cluster identification (frame proximity)

Grouping fires where successive frames differ by ≤ **30** frames:

| Approx span (`F_first–F_last`) | Width (frames) |
|-------------------------------|----------------:|
| **3076–3315** | 240 |
| **2832–3036** | 205 |
| **5219–5351** | 133 |
| **6122–6190** | 69 |

The **`3076–3315`** cluster overlaps **Direction M** citations around Gill (**tee lines ~28864, ~29642** neighborhoods when mapped through grep). **`2832–3036`** backs early-chase sustained mismatch episodes.

---

## §3 Code path analysis (Phase B)

### §3.1 Vision strip → extractor `batters[]` → pipeline guards

End-to-end (conceptually):

1. **Vision** logs human-readable **`STRIP:`** lines (scout latency block — examples throughout GT tee).
2. **Extractor** emits structured **`extracted["batters"]`** rows `{name, runs, balls, …}` consumed later by **`apply_scorer_decision`** ([`test_pipeline.py`](../../test_pipeline.py) **`apply_scorer_decision`** entry ~**3031**).
3. **Before** scorer merges, **`apply_comparison_strip_batter_row_delta_guard`** walks **each extractor batter row**, resolves `name` via **`scoreboard.resolve_name`**, and compares **`runs`** against **`batting_card[resolved]['runs']`** when **`balls > 0`** on card ([`test_pipeline.py`](../../test_pipeline.py) lines **2994–3027**).

Mismatch **`> 20` runs** ⇒ WARN **`[STRIP-ROWS-MISALIGNED]`**, **`extracted.pop('batters')`**, **`return True`** ⇒ caller sets **`_frame_poisoned = True`** ([`test_pipeline.py`](../../test_pipeline.py) lines **7241–7245**).

**Recovery semantics (“popped=batters”)** — removes **only** the extractor’s batter list for that frame so **`score` / `match_overs` / `bowler`** paths remain eligible per Thread 7 commentary ([`test_pipeline.py`](../../test_pipeline.py) lines **2984–2989**, **7231–7240**). It does **not** erase **`scoreboard.batting_card`** wholesale.

### §3.2 `resolve_name` — pairing-by-label

[`Scoreboard.resolve_name`](../../eyes/scoreboard.py) (**lines 923–982**) maps broadcast tokens to canonical roster keys via lookup tables, roster membership, initials, then fuzzy similarity threshold **≥ 0.75**.

**Implication:** Guard compares **each OCR-labelled row against that label’s batting_card bucket**. There is **no positional striker/non-striker parameter** inside **`apply_comparison_strip_batter_row_delta_guard`** itself — positional coupling enters earlier when extractor assigns **`batters[]` ordering** or when **`Scoreboard.update_batter`** merges validated decisions.

Thus the operative pairing model at the guard is **pairing-by-OCR-row-label → batting_card[name]** (with fuzzy canonicalisation). **Pure positional pairing without labels is not what this guard implements.**

### §3.3 `Scoreboard.update_batter` — tracker-gated merges

[`Scoreboard.update_batter`](../../eyes/scoreboard.py) (**from ~1695 onward**, rejection paths near **2037–2056**) coordinates **`LiveMatchTracker`** ceilings and **balls regression** rejection (`log.warn` **whole-row invalidation**, **`_last_row_rejected_frame`**).

This layer explains why some malformed rows fail to mutate **`batting_card`**, isolating strip anomalies **before** state surfaces to **`STATE`** lines — visible in **`F2835`** trace (**§4.4**).

### §3.4 `score_manager` consumption — keyed by slot names

Read-only feeders resolve runs/balls via **`batting_card[self.bat1_name]`** / **`bat2_name`** ([`score_manager.py`](../../score_manager.py) lines **283–357**). Wrong **`batN_name`** assignment (WS scrub / invariant repairs) couples statistically with wrong numeric readouts — **orthogonal Lever 1 concern** — but **does not substitute** for strip-row OCR attaching stats to an incorrectly keyed **`batting_card`** entry.

### §3.5 `scorer_decision_schema.py`

[`scorer_decision_schema.py`](../../scorer_decision_schema.py) validates **`batter_updates`** rows (`_validate_batter_row`, `_normalize_batter_updates`, lines **266–427**, **729+**) — schema coercion **drops malformed numeric projections**, but **does not decide strip-vs-card arbitration** or detect swapped striker stats. Pairing remains upstream of schema normalization.

---

## §4 Sample incident traces (Phase C)

**Windowing:** Each incident lists **canonical log lines** (ANSI stripped in citations for readability). Frame-adjacent context is summarized; full ±15/+30 expansions are reachable by searching `F####` in the tee.

### §4.1 Incident I1 — **RCB innings 1 — Padikkal / Patidar swap-like reads** (`F186–F187`)

| Ref | Tee | Excerpt |
|-----|-----|--------|
| Prior strip swap pattern | **2971** | `STRIP: RCB 59-2 (6) \| Padikkal 2(6) \| Patidar 18(10) \| Rabada…` |
| DETAIL confirms tracker retained prior card | **3004** | `BEFORE_bat1=Devdutt Padikkal 15(9)|BEFORE_bat2=Rajat Patidar 9(9)` while strip digits disagree widely |
| Guard trigger | **3012–3013** | `[GUARD] Devdutt Padikkal diff 15→36` → `[STRIP-ROWS-MISALIGNED] frame=F187 row_delta=21 … strip_runs=36 card_runs=15` |
| Poison marker | **3024** | `scorer_changes=['FRAME_POISONED:59']` |

**Stats correctness**

| Phase | Assessment |
|-------|------------|
| Before cluster (`F186` strip digits) | **Visibly wrong vs tracker** (`2971` vs `3004 BEFORE_*`). |
| Card state immediately around guard (`F187`) | **`DETAIL`** shows **`AFTER_bat*` unchanged vs BEFORE — correct rejection pathway for batters once poison blocks commits (`3024`). |
| User-visible flip risk | Episodic acceptance paths **outside** sampled frames could still flash incorrect UI pairing; within **`F186–187`**, **`batting_card`** cells remained **`15 / 9`**. |

**Hypothesis attribution:** **H1 PRIMARY**, **H6 LOW** (headline score matched — graphic slice looks live).

---

### §4.2 Incident I2 — **Innings-transition gap + substitute burst — Rajat Patidar (`F300–F301`)**

**Stop-condition S2:** **`grep STRIP-ROWS-MISALIGNED` across tee lines `22800–23800` returned zero rows** — no telemetry-backed **`[STRIP-ROWS-MISALIGNED]`** directly overlapping the innings-break band on this tee slice.

Substituted trace — **dense Patidar mismatch burst mid innings 1**:

| Ref | Tee | Excerpt |
|-----|-----|---------|
| Strip | **4427** | `STRIP: RCB 70-2 (6.5) \| Padikkal *18(14) \| Patidar 46(36)` |
| Guard | **4437–4438** | `[GUARD] Rajat Patidar diff 10→46` → `row_delta=36 strip_runs=46 card_runs=10` |
| STATE striker ordering | **4445** | `Bat: Devdutt Padikkal(25) Rajat Patidar*(10)` |
| DETAIL striker ordering | **4451** | `AFTER_striker=Devdutt Padikkal|AFTER_non=Rajat Patidar` (**`*` differs between STATE vs DETAIL**) |

**Stats correctness**

| Phase | Assessment |
|-------|------------|
| Card baseline (`4451 BEFORE_*`) | **Patidar `10(10)`**, Padikkal **`25(13)` — coherent.** |
| Strip row Patidar | **Inflated `46(36)` vs card — triggers guard.** |
| After guard | **`FRAME_POISONED`** pattern (`4451 scorer_changes`), **`AFTER_*`** preserves **`10`** runs — **correct.** |

**Hypothesis attribution:** **H1 / OCR exaggeration**, **H4 MEDIUM** (striker asterisk disagreement STATE vs DETAIL).

---

### §4.3 Incident I3 — **Chase integrity pocket — Gill cluster (`F3292`, `F3296`)**

| Ref | Tee | Excerpt |
|-----|-----|---------|
| Wrong-team headline vs tracker | **33659–33681** | Strip **`GT 57-1`** vs **`STATE` `RCB 49-1`** (`33679`) |
| Guard | **33669–33670** | Gill **`strip_runs=43 card_runs=6 row_delta=37`** |
| Poison coupling | **33672–33676** | `[POISONED] Extracted score 57 vs tracker 49 (delta=8)` |
| Repeated mismatch + POISON-RECAL | **33724–33734** | Gill mismatch repeats **`frame=F3296`** → **`[POISON-RECAL]` streak=5/5** (`33734`) |
| Score manager degradation | **33742** | `STATE: RCB None-None (None)` immediately post-recal (`33742`) |

**DETAIL anomaly:** **`33781`** embeds **`AFTER_non=Sai Sudharsan`** while **`33679`** **`STATE`** lists **`Rahul Tewatia`** — indicates **parallel stale/non-striker projections** during chaotic strip interval.

**Hypothesis attribution:** **H6 PRIMARY** (wrong headline / mismatched chase graphic). **H1 accessory** on Gill digits.

Cross-reference [`state_integrity_f3293_f3346.md`](state_integrity_f3293_f3346.md).

---

### §4.4 Incident I4 — **Early chase Sudharsan / Gill neighborhood (`F2832`, `F2835`)**

| Ref | Tee | Excerpt |
|-----|-----|---------|
| Wrong headline magnitude | **28861–28864** | Strip **`GT 47-0 (5.4)`** vs **`STATE` `RCB 20-0 (1.3)`** (`28875`) |
| Guard | **28863–28864** | Gill **`strip_runs=28 card_runs=7 row_delta=21`** |
| Recovery strip sane headline | **28886** | Later **`GT 20-0 (1.3)`** aligns with **`STATE`** chase score |
| Slot / striker coupling | **28895** | `[STRIKER-COLLISION] Refusing non=Shubman Gill — already striker` |
| Score gate | **28903** | `[SCORE-INF-GATE] proposed=20 < min_score_from_batters…` |

**Stats correctness**

| Phase | Assessment |
|-------|------------|
| Around **`F2832`** guard | **`DETAIL`** preserves **`Gill 7(2)`, Sudharsan `11(7)` — correct card under poison.** |
| **`F2835`** attempt | **`AFTER`** moves Gill **`→11(5)`**, Sudharsan **`→11(7)`** (`28917`) — plausible progression vs **`BEFORE`** but **`STATE`** exposes **`Gill*(11) Sai Sudharsan(11)` equal runs artifact (`28911`). |

**Hypothesis attribution:** **H6**, **H4**, partial **H1**.

---

### §4.5 Incident I5 — **Late chase — Jos Buttler (`F3666`)**

| Ref | Tee | Excerpt |
|-----|-----|---------|
| Strip headline nonsense vs chase | **37316–37342** | `STRIP: GT 44-6 (6) \| … J Butler 4(4) \| …` vs **`STATE` `RCB 90-2`** (`37358`) |
| Guard | **37341–37342** | Butler **`strip_runs=4 card_runs=37 row_delta=33`** |
| Poison | **37343–37344** | `[POISONED] Extracted score 44 vs tracker 90 (delta=-46)` |

**Stats correctness**

| Phase | Assessment |
|-------|------------|
| Card retained (`37358` **`DETAIL`** AFTER batters) | **`Buttler 37(17)`**, **`Sundar 3(3)` — aligns with coherent chase.** |

**Hypothesis attribution:** **H6 PRIMARY**, **H5 LOW**.

### §4.6 Frame artifact cross-reference

Workspace rules blocked reading `files/debug_frames_archive/2026-04-30_*` via ignore filters (**§9**). No `_scoreboard` / `_nostrip` suffix correlation table is claimed here.

---

## §5 Failure mechanism (Phase D)

### §5.1 Hypothesis evaluation matrix

| ID | Evidence FOR | Evidence AGAINST | Rank |
|----|----------------|------------------|------|
| **H1** | Pairwise digit swaps **`F186`** (`2971`) vs **`F187`** (`3010`). | Does not explain solo **`GT 44-6`** headline mismatch **`F3666`. | **HIGH** |
| **H6** | Recurring **`GT`** headline strips during **`RCB`** chase **`STATE`** (`28861`, `33659`, `37316`). | Less explanatory when headline score matches **`RCB`** yet digits transpose (**`F186`**). | **HIGH** |
| **H4** | **`[STRIKER-COLLISION]`** (`28895`), **`STATE`** vs **`DETAIL`** striker disagreement (`4451`). | Not every STRIP fire couples to collision logs. | **MEDIUM** |
| **H2** | Demonstrates fuzzy hazards (**`37341`** bowler mismatch). | Batter fuzzy matches frequently **`≥90%`** on same frames — batters less noisy than bowler substring collisions in sampled traces. | **MEDIUM** |
| **H3** | Poison streaks flatten updates (`33742`). | **`DETAIL`** snapshots mostly show stable **`AFTER_*`** bat lines post-guard in sampled incidents. | **LOW–MEDIUM** |
| **H5** | Amplifies symptoms if **`batN_name`** wrong. | Getter logic explicitly keyed — wrong stats trace back to wrong **`batting_card`** cells or wrong names, not alternate numeric indexing ([`score_manager.py`](../../score_manager.py) lines **283–357**). | **LOW** root |

### §5.2 Per-incident attribution summary

| Incident | Drivers |
|---------|---------|
| I1 `F186–187` | **H1** dominant |
| I2 `F300` | **H1**, **H4** |
| I3 `F3292/3296` | **H6**, **H1** |
| I4 `F2832/2835` | **H6**, **H4**, **H1** |
| I5 `F3666` | **H6** |

### §5.3 Multi-hypothesis concurrency

**YES — stop-condition S4.** **`F3292`** couples **`H6`** headline divergence with **`H1`** Gill digit inflation and **`POISON`** escalation (**`33734`**).

### §5.4 Relation to stop-condition S7

Recovery **`extracted.pop('batters')`** is **not** demonstrated here as the *primary* producer of sustained flipped **`batting_card`** cells — sampled **`DETAIL`** lines retain coherent **`BEFORE/AFTER`** batter numbers while stripping OCR digits disagree.

Persistent user-visible flipping likely requires **epochs where malformed strip rows slip past guards** or **alternate merge paths** (not exhaustively proven in five traces) — flagged **honestly** as residual risk.

---

## §6 Fix scope estimate (Phase E)

Assuming phased remediation targeting ranked hypotheses:

| Hypothesis | Fix sketch | Scope | Regression anxiety |
|------------|------------|-------|---------------------|
| **H1** | Row-wise consistency checks (*two batters jointly plausible vs team score / partnership trajectory*); transpose detector across adjacent strip cells. | **MEDIUM–LARGE** single subsystem (extractor + validation hooks) | Might stall legitimate accelerate bursts if thresholds naive. |
| **H6** | Strengthen **`visible_team` / headline coherence** vs tracker inning latch **before** batter delta guard; reuse bowling-team sustained graphic thresholds ([`test_pipeline.py`](../../test_pipeline.py) lines **7195–7228**) pattern for additional headline mismatches. | **MEDIUM multi-file** (`test_pipeline.py` + vision descriptors) | Risk blocking rare legitimate rapid inning-change snapshots — requires staged rollout telemetry. |
| **H4** | Unify striker/non derived from **`STATE`** consensus before merging contradictory OCR asterisk lanes; tighten `[STRIKER-COLLISION]` aftermath policies. | **MEDIUM** | Could interfere with dismissal choreography windows — monitor **`[WS-SLOT-INVARIANT]`** coupling ([`batter_stat_swapping_analysis.md`](batter_stat_swapping_analysis.md)). |
| **H2** | Narrow fuzzy acceptance when multiple roster candidates collide; escalate to abstain rather than mis-key. | **SMALL–MEDIUM** (`scoreboard.resolve_name`) | Name abstention ⇒ more **`FRAME_POISONED`** / sparse batters — acceptable if gated. |
| **H3** | Ensure scorer/UI hydration clears ephemeral projections when **`extracted`** loses batters while **`FRAME_POISONED`**. | **SMALL localized** | Mostly UX/state-display facing — verify Path B feeders ([`dual_broadcaster_path_b_migration_contract.md`](dual_broadcaster_path_b_migration_contract.md)). |
| **H5** | Only if traces prove divergence — **not supported as primary**. | **N/A** | — |

### §6.1 Recommended fix-shape rollup

**Phased LARGE campaign:**

1. **Detection layer upgrades for `H6`-class headline mismatches** (cheap wins reducing false batter deltas).
2. **Structural pairing validation for `H1`** (multi-row joint feasibility).
3. **Targeted collision refinement `H4`** once instrumentation proves coupling frequency.

### §6.2 Validation approaches

| Layer | Proposal |
|-------|----------|
| Unit | Synthetic extractor payloads covering transpose permutations & tracker divergence. |
| Integration | Replay harness fragments (`F186`, `F2832`, `F3292`, `F3666`) asserting **`[STRIP-ROWS-MISALIGNED]`** fires / abstentions without mutating **`batting_card`**. |
| Live ops | Monitor **`STRIP-ROWS` rate**, **`FRAME_POISONED` streak**, **`POISON-RECAL` neighbors**, **`[SM-FEEDER-SYNC]`** divergence ([`dual_broadcaster_path_b_migration_contract.md`](dual_broadcaster_path_b_migration_contract.md)). |
| Regression suites | **`test_recent_fixes.py`** — run selectively whenever comparator thresholds move (exact cases TBD outside memo scope). |

### §6.3 Risk assessment (aggregate)

**If fixes are overly aggressive:** legitimate rapid scoring updates during powerplay surge sequences could be suppressed → upward pressure on **`MULTI_BALL`**/`delivery` divergence classes documented elsewhere.

**Detection:** Rising **`FRAME_POISONED`** density without drop in **`STRIP-ROWS`** implies guards firing earlier — tune via histogram of rejected strips vs ESPN reconciliation backlog ([`match_postmortem_data_gt_rcb_20260430.md`](match_postmortem_data_gt_rcb_20260430.md)).

---

## §7 Implications

### §7.1 **F3296 / state integrity cluster**

Not a distinct pairing subroutine bug isolated from **`STRIP-ROWS`**. Same **`apply_comparison_strip_batter_row_delta_guard`** compares **`Gill`** digits (**§4.3**) — **`POISON-RECAL`** (**`33734`**) is **downstream amplification** of **`H6/H1`** strip unreliability interacting with poison streak thresholds documented in [`state_integrity_f3293_f3346.md`](state_integrity_f3293_f3346.md). **Bundled root class:** unreliable strip inning graphic / OCR rows ⇒ guard ⇒ poison ⇒ SM reset narrative.

**Stop-condition S5** (**entirely separate**) — **NOT triggered**: telemetry overlaps strongly.

### §7.2 **Direction M Issue α (`WS-SCRUB` oscillation)**

Orthogonal mechanism family ([`batter_stat_swapping_analysis.md`](batter_stat_swapping_analysis.md)). **`[WS-SLOT-INVARIANT]`** repairs **names**, not **`bat:{Name}:runs`**. Strip pairing fires dominate **chase** tee bands (**§2.5**) whereas **`WS-SLOT`** concentrates innings **1** — reinforcing operational separation.

Residual coupling risk: **name churn after poison frames** could confuse operators interpreting flipped digits — monitor jointly but fix pipelines remain distinct.

### §7.3 Prior shipments / docs needing revision?

[`thread7_rediagnosis_multi_ball_gap.md`](thread7_rediagnosis_multi_ball_gap.md) (**row transpose H1+H2**) aligns with **`§5`** rankings — recommend cross-tagging Direction **M2** conclusions into future Thread 7 iteration notes **without** rewriting shipped fix narratives inside this memo.

---

## §8 Direction recommendation

Given **S4 multi-hypothesis HIGH**:

| Milestone | Action |
|-----------|--------|
| Near-term | Instrument **`STRIP`** headline vs **`tracker.score`** divergence density **before** batter delta guard — prioritize **`H6`** mitigation prototypes offline. |
| Next | Build pairwise batter feasibility validator (**`H1`**) behind shadow flag on GT replay snippets (`F2832` cluster). |
| Gate before prod toggle | Demonstrate **`STRIP-ROWS`** rate drop **without** **`POISON-RECAL`** surge regressions ([`poison_recal_frequency_analysis.md`](poison_recal_frequency_analysis.md)). |

This is **not** a **`SMALL`** single-file tweak recommendation — staged **`MEDIUM/LARGE`** design loop required.

---

## §9 Limitations

1. **Sample bias:** Five incidents vs **119**/**221** fires.
2. **Frame artifact blackout:** `debug_frames_archive/**` unreadable here — no pixel-level OCR audits.
3. **Ground truth:** No authoritative ESPN ball-by-ball overlay embedded in memo — reliance on internal **`STATE`** / **`DETAIL`** coherence markers only.
4. **Residual acceptance paths:** Memo cannot certify absence of epochs where malformed strips mutate **`batting_card`** prior to tracker rejection without broader symbolic replay.

---

## §10 Cross-references

| Document | Relevance |
|----------|-----------|
| [`batter_stat_swapping_analysis.md`](batter_stat_swapping_analysis.md) | Direction **M** Patterns **P/R**, **`WS-SLOT`** vs **`STRIP-ROWS`** orthogonality |
| [`match_postmortem_data_gt_rcb_20260430.md`](match_postmortem_data_gt_rcb_20260430.md) | §4 telemetry tallies / §10 exemplar **`Padikkal`** mismatch narrative |
| [`state_integrity_f3293_f3346.md`](state_integrity_f3293_f3346.md) | **`F3293→F3346`** poison timeline overlaps **`§4.3`** |
| [`thread7_rediagnosis_multi_ball_gap.md`](thread7_rediagnosis_multi_ball_gap.md) | Earlier transpose hypotheses (**`H1`**) |
| [`dual_broadcaster_path_b_migration_contract.md`](dual_broadcaster_path_b_migration_contract.md) | **`SM-FEEDER`** interaction surfaces |

**Code hotspots**

| File | Lines | Role |
|------|-------|------|
| [`test_pipeline.py`](../../test_pipeline.py) | **2976–3028**, **7231–7245** | **`[STRIP-ROWS-MISALIGNED]` emission & invocation** |
| [`eyes/scoreboard.py`](../../eyes/scoreboard.py) | **923–982**, **`update_batter` ~1695–2071** | **`resolve_name`**, tracker merges |
| [`score_manager.py`](../../score_manager.py) | **283–357** | Read-through getters keyed by **`batN_name`** |
| [`scorer_decision_schema.py`](../../scorer_decision_schema.py) | **266–427**, **729+** | Batter row validation only |

---

### Appendix — Commands reproduced

```bash
grep -cE 'STRIP-ROWS-MISALIGNED|STRIPS-ROW-MISALIGNED' logs/pipeline-2026-04-30-gt-rcb-live.log
grep -cE 'STRIP-ROWS-MISALIGNED|STRIPS-ROW-MISALIGNED' logs/pipeline-2026-04-29-194416-mi-srh-live.log
grep -cE 'STRIP-ROWS-MISALIGNED|STRIPS-ROW-MISALIGNED' logs/pipeline-2026-04-28-pbks-rr-live.log
```

ANSI stripping applied mentally via `\x1b[[0-9;]*m` removal for parsers cited in §2.

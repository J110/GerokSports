# Task B live monitoring — striker-aligned extractor rows (Issue 2)

Operator sheet for the match **after** landing `fix(scoring): align extractor batter rows to striker/non for ScoreManager FrameInput` on `main`.

---

## Phase A — Pre-ship validation record (authoring workspace)

| Step | Result |
|------|--------|
| **A1** | `python3 -m pytest files/test_recent_fixes.py -k align_extractor_batters_fixture -v` → **6 passed** (fixture run on 2026-05-01). |
| **A2** | **Not executed:** No checked-in harness replays `logs/pipeline-2026-04-30-gt-rcb-live.log` through `test_pipeline` with WS capture. `files/scripts/live_match_monitor.py --replay-file` produces observation markdown only — not a pipeline re-exec. **Shadow parity vs symptom match is unverified pre-ship** until someone runs video/log replay on a machine with full pipeline deps. |
| **A3** | **Forensic baseline only** (original artifact log). See **§4** for frame-level before/after fields; no post-fix replay log `logs/replay-gt-rcb-task-b-validation.log` or `logs/ws-payload-task-b.jsonl` exists from this workspace. |

**Stop-condition notes:** S-A3 applies — ship with **elevated live monitoring** (this runbook). If post-match replay reproduces legacy flipped slots with zero `[STRIKER-ALIGN-FALLBACK]` in that window, treat as **S-A1** signal and re-open mechanism work.

---

## §1 Identity

| Field | Value |
|-------|--------|
| **Commit SHA** | **`REPLACE_ME_AFTER_PUSH`** — paste `git rev-parse HEAD` after merge to `main`. |
| **Revert** | `git revert REPLACE_ME_AFTER_PUSH` |
| **Implementation refs** | `files/docs/investigations/batter_stats_flipping_fix_implementation.md`, `batter_stats_flipping_mechanism.md` |
| **Match log pattern (today)** | `logs/pipeline-2026-05-01-*-live.log` (adjust date and slug to actual tee, e.g. `*-mi-dc-live.log`). |
| **Symptom reference match** | GT vs RCB — `logs/pipeline-2026-04-30-gt-rcb-live.log` |

**ROLLBACK COMMAND (copy-paste ready)**

```bash
cd /path/to/SportsComm && git revert REPLACE_ME_AFTER_PUSH --no-edit && git push origin main && sudo systemctl restart cricketmind-pipeline
```

Replace `/path/to/SportsComm` with the deployment repo path; replace **`REPLACE_ME_AFTER_PUSH`** with the real SHA; replace **`sudo systemctl restart cricketmind-pipeline`** with your unit name (`systemctl list-units '*pipeline*'` / internal runbook).

**Revert dry-run (once SHA is known, on a git clone)**

```bash
git revert --no-edit -n REPLACE_ME_AFTER_PUSH && git revert --abort
```

Confirms Git accepts the revert payload without committing.

---

## §2 Healthy baseline (first ~30 DETAIL frames)

**Live tail**

```bash
tail -f logs/<match>.log | grep -E 'STRIKER-ALIGN-FALLBACK|BATTER-ALIGN|WS-SCRUB'
```

**Expect**

- **`[BATTER-ALIGN]`** (INFO): Occasional only — typically when extractor returns **3+** batter rows during info-panel / layout churn. Low, bursty.
- **`[STRIKER-ALIGN-FALLBACK]`** (WARN): **Rare** — operator mental model **&lt; ~5%** of DETAIL lines in settled play (not a hard tool threshold here). Bursts around bad OCR are OK if they clear.
- **`[WS-SCRUB]`**: Tied to dismissal / slot repair events — not every ball.

---

## §3 Alert conditions (rollback triggers)

### Tier 1 — Immediate rollback

| Signal | Meaning |
|--------|---------|
| **`[STRIKER-ALIGN-FALLBACK]`** on **&gt;50%** of DETAIL frames in any **5-minute** wall-clock window during settled play | Resolver/OCR systematically failing — helper falling back to strip order almost always. |
| **Identical `ext_bat1_name` and `ext_bat2_name`** on **multiple consecutive** ScoreManager frames (check DETAIL / FrameInput projection if mirrored in log) | Possible helper or upstream duplication bug. |
| Python traceback referencing **`_align_extractor_batters_for_sm`** | Logic or input contract violation. |

**Action:** Run §1 rollback command; preserve failing log slice + SHA for post-mortem.

### Tier 2 — Watch, do not rollback

| Signal | Action |
|--------|--------|
| Fallback rate **5–50%** in a stretch | Likely OCR / `resolve_name` / feed quality. Log timestamps + strip screenshots if possible; review post-match. |
| **`[BATTER-ALIGN]`** never appears | May simply lack `len(batters)>2` spells — note end-of-match grep counts (§5). |

---

## §4 Symptom-class spot checks (every ~15 minutes)

Pause and reconcile **broadcast striker/non** vs payload batting slots:

1. **First over — innings 1**
2. **First over — innings 2** (original Issue 2 window on GT–RCB was frames ~**2308–2700** with Gill / Sudharsan)
3. **Within ~20 s after each wicket** (WS-SCRUB coupling)

**Verify**

- **bat1** runs/balls track the **striker** name shown on broadcast (strip / graphic).
- **bat2** tracks the **non-striker**.
- After single / end-of-over rotation, the **same player’s** cumulative stats move with **their** slot.

Record mismatches with **frame id** (`DETAIL|F…`), wall time, and payload excerpt.

### §4.1 Original-log forensic baseline (GT–RCB, pre–Task B code)

These fields come from **`logs/pipeline-2026-04-30-gt-rcb-live.log`** — used to reason about the bug class; **not** a replay of the new binary.

| Frame | Notes | `ext_bat` (extractor) | `AFTER_bat1` | `AFTER_bat2` | Striker-axis fields (if present) |
|-------|-------|-------------------------|--------------|--------------|----------------------------------|
| **F2347** | First ball innings 2; strip shows both with 1 ball | `Gill 0(1) \| Sudharsan 0(1)` | Shubman Gill `0(1)` | Sai Sudharsan `0(0)` | Commentary/wire describes Gill facing; **bat2 balls lag strip** |
| **F2352** | Next legal line; strip both `0(1)` | `Gill 0(1) \| Sudharsan 0(1)` | Gill `0(1)` | Sudharsan `0(0)` | Same pattern — extractor vs slot skew |

**Post–Task B expectation (qualitative)**

- Where `score_mgr.striker` / `non` match strip names, **FrameInput** should map extractor rows so **bat1** receives the **striker’s** row stats and **bat2** the **non’s**, reducing “stats on wrong name” vs strip order inversions **(`batter_stats_flipping_mechanism.md`)**.
- Where names cannot match, **`[STRIKER-ALIGN-FALLBACK]`** should appear on those frames — operator should correlate with OCR garbage or wrong squad context.

---

## §5 Post-match validation

After the match, from the tee log:

```bash
grep -c 'STRIKER-ALIGN-FALLBACK' logs/<match>.log
grep -c 'BATTER-ALIGN' logs/<match>.log
grep -c 'WS-SCRUB' logs/<match>.log
```

Optionally estimate **fallback rate**:

```bash
detail=$(grep -c 'DETAIL|' logs/<match>.log || true)
fallback=$(grep -c 'STRIKER-ALIGN-FALLBACK' logs/<match>.log || true)
# rate ≈ fallback / detail  (interpret only when detail >> 0)
```

**Append to this document (below) or ops channel**

- Match id, log path  
- `detail`, `fallback`, `batter_align`, `ws_scrub` counts  
- One-line verdict: okay / elevated fallback / rollback was used  

If **sustained fallback &gt; ~10%** of DETAIL lines over long stable phases, queue follow-up: **`resolve_name`** / squad / extractor row quality vs **`_align_extractor_batters_for_sm`**.

---

## §6 Rollback artifact (templated)

Same as §1 — duplicated for visibility under pressure.

```bash
cd /path/to/SportsComm && git revert REPLACE_ME_AFTER_PUSH --no-edit && git push origin main && sudo systemctl restart cricketmind-pipeline
```

---

## Appendix — Git / push (maintainer)

This documentation was generated in a **partial workspace without `.git`**. Maintainer must:

1. Paste the real **commit SHA** into §1 and §6 (`REPLACE_ME_AFTER_PUSH`).
2. Run **A1** locally before merge.
3. If a **replay harness** exists internally (video + `run_test` / CI), produce `logs/replay-gt-rcb-task-b-validation.log` and WS JSONL; then tighten §3 thresholds using measured fallback rates.

---

_Post-match append area_

```
(match, log path, counts, notes)
```

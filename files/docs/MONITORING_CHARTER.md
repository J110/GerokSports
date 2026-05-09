# Match-day monitoring charter

Canonical discipline for live match telemetry review, escalation, and backlog hygiene.

---

## 1. Purpose and scope

- **When to use:** live match-day monitoring while the pipeline is running against broadcast.
- **Who uses:** Composer 2 routine runs; escalate pattern recognition and innings-break synthesis to Sonnet (medium thinking) or architecture / multi-thread decisions to Opus (high thinking).
- **What this covers:** which log to analyze, analyzer command surfaces, PRIMARY vs PENDING validation tags, escalation thresholds, standard report shape, innings-transition handoff, and model-selection guidance.

---

## 2. Standard monitoring command

**Critical:** Pipeline logs land under **`logs/` at the repository root**, not under `files/logs/`. Wrong path **`files/logs/pipeline-*.log`** does not exist for this tee.

### Resolve latest log (working directory **`files/`**)

```bash
ls -t ../logs/pipeline-*.log | head -1
```

### Full analyzer invocation (working directory **`files/`**)

```bash
cd files && python analyze_match_telemetry.py \
  --log "$(ls -t ../logs/pipeline-*.log | head -1)" \
  --report-all-fixes \
  --report-bundle-bc \
  --report-pending-validation
```

Equivalent from repo root: `--log "$(ls -t logs/pipeline-*.log | head -1)"`.

### Run intervals

| Context | Interval |
|---------|----------|
| Normal play | 15–20 min wall |
| High-activity windows (powerplay, end of innings, wicket clusters) | 10–15 min wall |
| Innings break | Final Composer 2 pass for innings 1; then Sonnet/Opus handoff (see Section 7) |
| Post-match | One comprehensive retrospective pass |

---

## 3. PRIMARY validation surface tags

Treat these as the main quantitative health rails. Expected baselines are single-match-relative; escalate on sustained deviation or nonzero where target is zero.

| Tag | Role | Baseline / target | Escalation notes |
|-----|------|-------------------|------------------|
| `[SM-SLOT-INVARIANT]` | Lever 1 helper repairs via `_set_slot_pair` | Context-dependent when W-path exercises helper | Spike vs recent match when tied to regressions |
| `[WS-SLOT-INVARIANT]` | Defense-in-depth WS repair (`enforce_ws_slot_invariant`) | PBKS archive **~2.4/min**; post–Lever-1-PR3 **target `<0.30/min`** (**~73–87%** reduction vs MI–SRH innings-1 baseline) | Rate **>** **3.0/min** sustained **>** **10 min**; or **>** **20% increase** vs PBKS-style baseline (**regression**) |
| `[SCORER-SCHEMA-WOULD-DROP]` / `[SCORER-SCHEMA-WOULD-COERCE]` | Item 2 PR 1 shadow schema | Expected nonzero in shadow; track first-fire frames | Structural change in coerce/drop ratios without shipped prompt/schema change |
| `[BATTERS-INVARIANT]` | Step 5 SCORER backstop (Phase 1 noop default) | **Rule distribution:** predominantly **rule=C** in admission windows; **12+/13 rule=C**, **0 rule=B** in clean innings windows; **rule=A NON-ADMISSION:** **max 1 per match** expected in observed data | **rule=B any**; **rule=A `>` 1 per 10 min** outside admission windows (**Δ `>` 25 frames** from wicket); **NON-ADMISSION total `>` 2** in first **60 min** |
| `[SM-FEEDER-SYNC]` | Item 3 Path B feeder writes | Healthy volume with score progression | Abrupt collapse vs prior windows |
| `[SM-FEEDER-DIVERGENCE]` | Item 3 Path B parity | Dominated by `bowler_name` drift at low rate acceptable | **`>` 5/min** on **any field other than `bowler_name`** |
| `[WS-PROJECTION-GAP]` | Path A projection sentinel | Transient cold-start class possible | **Non-zero sustained** unexpected pattern = Path A regression triage |
| `sb_accepted=false` count | SB reject storm | **Target 0** | **Any sustained storm** |

---

## 4. PENDING validation tags watch list

Awaiting first-fire or post-ship production validation tied to fixes shipped **2026-04-30** (and adjacent MI–SRH work):

| Tag | Notes |
|-----|-------|
| `[SM-W8-DISMISSED-GUARD]` | Lever 1 PR3; expect **`≤ 6`** fires per match **per dedup** design |
| `[STRIKER-SM-CUTOVER]` with `reason="batter-arrival"` | Lever 1 PR3 Part 2 (intra-over admission) |
| `[STRIP-ROWS-MISALIGNED]` | Thread 7 Fix 1 row-misalignment guard |
| `[CAM-GRAPHIC-FAST-PATH-READ]` / `-REJECT` / `-NOOP` | Thread 7 Fix 2 dead-time fast path |
| `[SM-INNINGS-2-RESET]` with `source="overs_complete_20"` or `"poison_recal_cold_start"` | P0-A |
| `[OVERS-TRACKER-RESET]` | P0-B |
| `[TEAM-ATTRIBUTION-CRICKET-RULES]` / `[TEAM-ATTRIBUTION-STRIP-FALLBACK]` | P0-C |

---

## 5. Stop-and-route-back conditions

Composer 2 **escalates immediately** on:

- Crash / uncaught exception
- Pipeline disconnect or unintended restart
- Score, wicket, or batter state **visibly wrong** in WS payload vs broadcast
- New bug class not mapped to any existing backlog pattern

Composer 2 **escalates when thresholds trip**:

- `[BATTERS-INVARIANT]` **rule=B** (any count)
- `[BATTERS-INVARIANT]` **rule=A `>` 1** in **10 min** outside admission windows (**Δ `>` 25** frames from wicket)
- `[BATTERS-INVARIANT]` NON-ADMISSION **total `>` 2** in first **60 min**
- `[WS-SLOT-INVARIANT]` **>` **3.0/min** sustained **>** **10 min**
- `[WS-SLOT-INVARIANT]` rate **up `>` ~20%** vs PBKS **~2.4/min** archive baseline (**regression**)
- `[SM-FEEDER-DIVERGENCE]` **`>` 5/min** on field **other than** `bowler_name`
- **`[SM-INNINGS-2-RESET]` did not fire** when innings 2 should bootstrap (e.g. SRH over 3 chasing without SM reset equivalent — innings 2 bootstrap failure class)
- `sb_accepted=false` storm (**any** pattern worth triage)
- `[WS-PROJECTION-GAP]` unexpected non-zero persistence (Path A)
- `[SM-W8-DISMISSED-GUARD]` **`>` 6** per match (dedup broken)

---

## 6. Per-run output template

```
===== Match monitoring run [timestamp] =====
Log: <path>
Window: F<start> -> F<end> (<minutes> min)
State: <innings> <score>/<wickets> (<overs>) <batter1>/<batter2> bowling: <bowler>

PRIMARY validation:
  [tag]: N fires (rate: X/min vs baseline Y/min)
  ...

PENDING fires this run:
  [TAG-NAME]: first fire at F<frame>
  ...

Notable observations:
  - <anything unexpected, gaps, patterns>

Backlog updates needed:
  - <fixes whose tags fired for first time>

Escalation status: none / [trigger fired]
```

---

## 7. Innings transition special handling

Innings break is **high complexity**: cold-start relabels, carousel graphics, DETAIL vs strip poison, overs latch, team swap logic.

1. Composer 2 produces the **final innings 1 monitoring run**.
2. **Hand off** to Sonnet/Opus for innings-break synthesis (baseline reference: investigation handoff packs for MI–SRH).
3. Lever 1 PR3 design refinements (dismissed-batter latency, CUTTOVER semantics) explicitly inform expected telemetries across the seam.
4. **Phase 2** (`BATTERS_INVARIANT_AUTOCORRECT` / schema enforce) stays a **defer** decision pending clean data + logic gates (see backlog + `files/docs/investigations/mi_srh_innings_break_analysis.md`).
5. Composer 2 resumes **routine** monitoring at innings 2 start **using this charter** (same log path rules).

---

## 8. Model selection criteria

| Depth | Model | Use for |
|-------|-------|---------|
| Routine | Composer 2 | Mechanical log resolution, tag counts, backlog tick updates |
| Diagnostic | Sonnet (medium thinking) | Fire clusters, wicket-admission attribution, comparisons to predicted rates |
| Architectural | Opus (high thinking) | Novel coupling, overlapping bugs, mid-match remediation strategy |

Escalate to Sonnet/Opus when:

- Multiple stop-and-route-back conditions align
- Visual UI anomaly on broadcast contradicts telemetry narrative
- **End of innings 1** comprehensive snapshot analysis
- **End of match** retrospective

---

## 9. Path correction reference

| Resolving cwd | Correct log glob | Wrong glob (common mistake) |
|---------------|------------------|----------------------------|
| `files/` | `../logs/pipeline-*.log` | `files/logs/` (does not exist for pipeline tee) |
| repo root | `logs/pipeline-*.log` | `files/logs/pipeline-*.log` |

---

## 10. Cross-references

- **Investigations index:** `files/docs/investigations/INDEX.md`
- **Backlog:** `files/docs/backlog.md`
- **Path A WS regression artifact:** `files/path_a_ws_payload_baseline.txt`
- **Representative escalation / thresholds narrative:** `files/docs/investigations/mi_srh_innings_break_analysis.md`
- **`[BATTERS-INVARIANT]` mechanism taxonomy:** `files/docs/investigations/batters_invariant_cluster_innings1.md`

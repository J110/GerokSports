# Trace-and-Detect monitoring system — design memo

**Status:** Design-only. No production code. Implementation deferred to a separate session after operator review.
**Author session date:** 2026-05-02
**Trigger:** RR-vs-DC (43rd match, IPL 2026) post-mortem — multiple visible-on-UI defects that the existing tee log + tag emissions could describe but not *root-cause* without manual replay.
**Companion artefacts:** `logs/pipeline-2026-05-01-1935-rr-vs-dc-43rd-match-indian-premier-league-2026.log` (50,856 lines, 0.5 fps capture-throttled).

---

## §1 Executive summary

The pipeline already emits a dense per-scoreboard-frame `DETAIL|F<n>|...` line (`files/test_pipeline.py:L10568-L10650`) containing BEFORE/AFTER snapshots of score, batters, bowler, this_over, partnership, FOW count, and ball_event. It **also** emits ~30 distinct guard tags (`[POISON-RECAL]`, `[GRAPHIC-FILTER]`, `[STRIKER-ALIGN-FALLBACK]`, `[GUARD] Batter ... rejected`, `[WICKET-AUTO]`, `[SM] dropping bat1_name=...`, `[SCORER-INVARIANT-FILTER]`, etc.) but as separate human-readable lines that must be hand-correlated to the DETAIL frame they apply to.

**Architecture:** convert the DETAIL line + the surrounding guard emissions into a **single structured JSONL trace record per scoreboard frame**, written to `logs/trace/<session>.jsonl` alongside the existing tee. Each record captures (a) the inputs each layer saw, (b) every guard/decision that fired with its reason, (c) the ui-payload diff that resulted. A **detection module** runs nine internal-consistency rules (P1–P9) over a sliding window of trace records, emits a real-time `[ANOMALY-Pn]` tag when one fires, and produces a post-match Markdown report from the JSONL.

**Key design decisions:**

1. **Same emission cadence as DETAIL** (~0.5–2 fps adaptive, not 61 fps capture rate) — trace volume stays under 50 MB/match without sampling logic.
2. **Internal-consistency only** — no external scorecard fetch. All nine v1 rules detect contradictions inside the pipeline's own state (score regression, partnership math, this-over arithmetic, wicket↔batter swap coupling).
3. **Guard catalog promotion** — every existing tag (`[POISON-RECAL]`, `[GUARD] Batter ... rejected`, `[INVARIANT] Refusing to un-dismiss ...`, etc.) becomes a typed `decision` entry inside the trace record so the analyzer can attribute a UI symptom back to the specific guard that suppressed the corrective read.
4. **Post-match analyzer is the primary surface; real-time tags are a v1.1 add-on** — the operator workflow during a live match is already saturated by the existing tee tail; the analyzer is what makes a forensic report repeatable.

**Total scope estimate:** **MEDIUM, ~700–950 LOC.** ~250 LOC for trace emission (replaces the f-string DETAIL block at `files/test_pipeline.py:L10568-L10650` with a structured builder), ~150 LOC of guard-emission instrumentation (typed decision entries), ~200 LOC for the nine detection rules, ~150 LOC for the analyzer CLI + Markdown report, ~100 LOC of pytest fixtures replaying captured RR-DC frames against each rule. Two implementation sessions.

---

## §2 Phase A — Current telemetry forensics

### §2.1 DETAIL line — schema and emission

**Location:** `files/test_pipeline.py:L10460-L10650` (assembly), `files/test_pipeline.py:L10650` (single `log.info(_detail_line)` emission).
**Cadence:** emitted once per *processed scoreboard frame* — not per capture frame. Capture is gated by `frame_changed()` (`files/test_pipeline.py:L832-L839`), `_strip_has_text_band()` (`L857-L891`), `_ws_cold_start_gate_check()` (`L713-L778`), and `AdaptiveSleep` (`L894-…`). On the 2026-05-01 RR-DC log this resolved to ~5,524 DETAIL lines over a 3-hour match (~0.5 fps capture-throttled; capture-card migration today is expected to lift this to ~1–2 fps without changing emission cadence).

**Field inventory (exhaustive — single line, pipe-delimited):**

| Group | Fields | Provenance |
|-------|--------|------------|
| header | `F<n>`, `frame_type`, `tag` | frame counter / scout classifier |
| inputs | `scout=<120 chars>`, `action=<100 chars>`, `ext_score`, `ext_bat`, `ext_bowl` | Scout/extractor raw |
| scorer | `scorer_changes=[…]`, `yolo=<n>` | Scorer commit list |
| BEFORE | `BEFORE_score`, `BEFORE_bat1`, `BEFORE_bat2`, `BEFORE_bowl`, `BEFORE_this_over` | Snapshot taken at `L9942`-region (top of frame) |
| AFTER | `AFTER_score`, `AFTER_bat1/2`, `AFTER_bowl`, `AFTER_this_over` (+ `_src` cell-tags), `AFTER_striker`, `AFTER_non`, `AFTER_run_rate`, `AFTER_target`, `AFTER_innings`, `AFTER_partnership`, `AFTER_fow_count`, `AFTER_field` | Read from `state` / `score_mgr` / `partnership_tracker` / `cricket_field` after commit |
| ball event | `ball_event`, `ball_event_runs`, `ball_event_over`, `ball_event_extra`, `ball_event_free_hit`, `broadcast_extra`, `dismissal_mode`, `striker_this_ball` | `ball_event` dict produced by ball-detector layer |
| delivery (Layer 1+2) | 18 fields: `delivery_length / line / angle / shot / direction / elevation / bounce / dets / det_rate / method / dir_zone / dir_conf / shot_action / shot_intent / swing / speed_vlm / vlm_conf / vlm_ms` | VLM + Qwen + Gemini routed |
| latency | `lat_vision`, `lat_extract`, `lat_scorer`, `lat_field`, `lat_comm`, `lat_code`, `lat_total` | Per-stage timers |
| commentary | `comm_bowler`, `comm_wire`, `comm_storyteller`, `comm_analyst`, `comm_colour` (+ `_ms` for each) | Four commentary tracks |
| meta | `speed_kph`, `venue`, `batting_team`, `match_info`, `completed_over`, `completed_over_runs`, `drs_state`, `corrections` | Mixed |

**Crucially captured already:** `BEFORE_*` vs `AFTER_*` — i.e. the DETAIL line *is* a one-frame state-diff trace today. The gap is that it's pipe-delimited text, not JSON, and it lacks the *decision-level* layer (which guard fired, which extractor row was rejected and why).

### §2.2 Guard / decision tag inventory

Grep over `files/test_pipeline.py` (and one cross-ref into `files/eyes/scoreboard.py`) yields the live decision-tag catalog. Each row below is an existing emission site; the trace system promotes each to a structured `decision` entry inside the trace record.

| Tag | Site | Rejects / mutates | Reason recorded |
|-----|------|-------------------|-----------------|
| `[POISON-RECAL]` | `files/test_pipeline.py:L8140-L8159` | SM recal trigger | streak count + Δ |
| `[POISON-RECAL-PRE-EMPTED]` | `L8108-L8113` | Recal suppressed | `_gfx_phase_recal_skip` |
| `[GRAPHIC-FILTER] info_panel_keyword=…` | `L2208`, `L7031` | Reject extractor commit | matched keyword |
| `[GRAPHIC-FILTER] SCOREBOARD+…` | `L8114` | Strip-class mismatch | strip class delta |
| `[CAM-GRAPHIC-FAST-PATH-{REJECT,READ,NOOP}]` | `files/eyes/vision.py:L184`, `files/test_pipeline.py:L6834-L6841` | 8-clause fast-path verdict | clause flags |
| `[STRIKER-ALIGN-FALLBACK]` | `L1206` | Striker/non aligned by strip order | striker_ref / non_ref / ext_batter_names |
| `[BATTER-ALIGN]` | `L1149` | Diagnostic scan | extractor batters + canonical match attempts |
| `[BOWLER-BATTER-GATE]` | `L2097` | Strip line stripped from bowler row | which line / which batter |
| `[BOWLER] Lock auto-released after …` | `L7780` | Bowler lock released | n-frames since last frame |
| `[BOWLER] New bowler confirmed: …` | `L7833` | Bowler lock acquired | name + consecutive frames |
| `[BOWLER-LEAD] {name} runs …` | `L7878` | Bowler-lead arbitration | runs counts |
| `[WS-SLOT-INVARIANT]` (×2) | `L2442`, `L2447` | Duplicate slot scrub | which slot, which name |
| `[WS-SCRUB]` | `L4166` | Slot scrubbed | reason |
| `[BATTERS-INVARIANT] rule={A,C} violation=…` | `L2665-L2734` | Shadow / backstop demote | rule + viol class |
| `[STRIP-ROWS-MISALIGNED]` | `L3162` | Strip-row pairing rejected | frame row |
| `[NEW-BATTER-BALLS-GATE]` | `L3663`-region (`[EXTRAS-INF-GATE]`) | Fresh-admission ceiling | wkts / balls |
| `[WICKET-AUTO] Dismissed striker …` | `L3468-L3479` | Auto-dismiss on wkts↑ | striker name + wkts delta |
| `[WICKET-AUTO] Skipping auto-dismiss …` | `L3474-L3479` | Auto-dismiss skipped | reason (ambiguous, etc.) |
| `[WICKET-TRACK] Wicket at F{n}` | `L9210` | Wicket logged | over / score |
| `[WICKET-ATTRIB] Dismissed batter set` | `L9617` | Dismissed batter attributed | candidate set |
| `[EXTRAS]` / `[EXTRAS-INF]` / `[EXTRAS-INF-GATE]` | `L6385`, `L6442`, `L3663` | Extras reconciler | inferred totals |
| `[GUARD] Scorer proposed dismissal but wickets unchanged …` | (stdout, observed in RR-DC log F716/F720) | Block scorer dismissal | wkts unchanged |
| `[GUARD] Batter '<name>' not in extractor output — scorer inferred, rejecting` | (stdout, RR-DC F716/F720) | Block scorer batter row | not in extractor names |
| `[SCORER-INVARIANT-FILTER] skipping batter_updates row for witnessed-out '…'` | (stdout, RR-DC F716/F720) | Block stale undismiss | witnessed FOW exists |
| `[SM] dropping bat1_name='…' from card — scoreboard shows status=out` | `files/score_manager.py` (witnessed-out filter) | SM rejects extractor row | scoreboard status=out |
| `[INVARIANT] Refusing to un-dismiss '…' — witnessed FOW entry exists` | `files/eyes/scoreboard.py` (BOARD logger) | Scoreboard refuses revival | witnessed FOW exists |
| `[FIELD-MONITOR] Field unchanged for N frames` | `L10508-L10516` | Stale field warning | n-frames |
| `[WS-COLD-START-GATE] OPEN …` | `L764-L776` | Gate opens | team + score |
| `[SM-FEEDER-SYNC] field=… note=read_only_now` | `files/score_manager.py` (feeder) | Path-B mirror parity | sb_value |

**Common pattern across all of these:** the tag tells you *what* was rejected, but you must scroll backwards through the tee to find the corresponding `DETAIL` line that gave the rejected reading its context (BEFORE/AFTER state, what the extractor said, what the scorer proposed). The trace system collapses this scroll into one record.

### §2.3 UI WebSocket payload — what reaches the browser

**Publisher:** `broadcast_state(payload)` (`files/test_pipeline.py:L809-L827`). Called from at least 8 sites: `L5828`, `L6748`, `L6838`, `L7906`, `L10197` plus a few cold-start fallbacks. Payload built by `_build_full_payload_from_state(...)` (`L4058`, returned from `L5799-L5828` region).

**Cold-start gate:** `_ws_cold_start_gate_check()` (`L713-L778`) suppresses emission until `batting_team` is committed *or* 90s timeout. Once open, never re-closes (`L735-L736`). This is significant for trace design: any "ui_state" snapshot during cold-start is effectively NULL on the client side even though the pipeline's internal state may be fully populated.

**Payload shape:** the consumer-side TypeScript schema in `scorecard-ui/app/lib/types.ts:L1-L214` is the canonical schema for ui_state. Key components mirrored on UI:

- `scorecard` (`Scorecard` interface, `L30-L40`): score, wickets, overs, run_rate, batting_team, bowling_team, striker, non_striker, current_bowler.
- `batting_card` (`BatterEntry[]`, `L1-L16`): per-batter name, status, runs, balls, fours, sixes, sr, dismissal, is_striker, position, batting_style/bowling_style.
- `bowling_card` (`BowlerEntry[]`, `L18-L28`): name, overs, maidens, runs, wickets, economy, is_current.
- `match` (`MatchInfo`, `L42-L53`): team_a/b, innings, target, toss, phase, match_phase.
- `this_over` (`string[]`, `L200`).
- `match_situation` (`L78-L87`): runs_needed, balls_remaining, required_rate, run_rate, balls_bowled, wickets_in_hand, target.
- `extras` (`L89-L97`): wides, no_balls, byes, leg_byes, penalties, total, this_over.
- `partnerships.current` (`Partnership`, `L55-L60`): batters[], runs, balls.
- `over_history` (`Record<string, OverEntry|string[]>`, `L204`).
- `field` (`FieldData`, `L107-L114`).
- `delivery_info` (`DeliveryInfo`, `L143-L189`).
- `fall_of_wickets` (`FallOfWicket[]`, `L116-L124`).
- `innings_history` (`InningsHistoryEntry[]`, `L62-L76`) — archived prior innings, replaced wholesale.

**Consumer-side merging:** `useMatchSocket` (`scorecard-ui/app/hooks/useMatchSocket.ts:L5-L36`) does a `deepMerge` rather than wholesale replace: arrays are replaced if non-empty, nested objects deep-merged, scalar nulls/empty strings preserve previous value. Three implications for the trace:

1. **A NULL field on the wire does NOT clear the UI** (`L29-L33`) — any "wrong batter" symptom can be either a wrong write *or* a missing scrub on a previously-stale value.
2. **`innings_history` is replaced wholesale** (`L11-L15`) — innings transition is observable as a full-array swap, not a merge.
3. **Empty arrays are not preferred over previous non-empty** (`L18-L21`) — clearing the batting_card requires sending an explicit non-empty replacement.

**ui_state_after** in the trace must therefore reflect what the *client* sees post-merge, not just what the server emits. The minimal way to capture this is to maintain a server-side mirror of the merged payload (apply the same deepMerge after each emission) — see §3.1.

### §2.4 Identified gaps — why current telemetry can't root-cause RR-DC

Three classes of state change happen inside the pipeline without ending up in the DETAIL line:

**Gap 1 — Guard-rejection attribution.** When `[GUARD] Batter 'Yashasvi Jaiswal' not in extractor output — scorer inferred, rejecting` fires (RR-DC F716/F720), the DETAIL line on the same frame still says `scorer_changes=['score→35', 'overs→4.3', 'wickets→2', 'bowl:Axar Patel']` — i.e. the *committed* changes after the guard ran. There is no field that says "the scorer ALSO proposed a batter row that was rejected by guard X." Without this, you cannot tell whether stale UI batters are from a missed detection (extractor never read the new pair) or a wrong rejection (extractor read the new pair, guard rejected it).

**Gap 2 — Comparison-strip filter decisions.** The `_apply_comparison_strip_batter_row_delta_guard` family (`files/test_pipeline.py` near `L3162`) decides which extractor batter rows to keep per frame; the only emission today is `[STRIP-ROWS-MISALIGNED]` on rejection, with no record of *which* row was kept and *why*. When the live RR-DC log shows `[INVARIANT] Refusing to un-dismiss 'Dhruv Jurel' — witnessed FOW entry exists`, the trace needs the matching "extractor row Jurel 18(13)" entry alongside the rejection so an analyzer can see the strip is reading from a stale graphic.

**Gap 3 — Stale-state retention reasons.** When SM holds `striker=Yashasvi Jaiswal` for 50+ frames against an extractor consistently saying `Jurel/Parag`, the only existing emission is the per-frame `[STRIKER-ALIGN-FALLBACK]` warning. There is no "held striker because: (a) FOW witnessed for proposed name, (b) cohort mismatch >N, (c) cold-start protection, (d) feeder parity etc." breakdown. The scorer's *reason for inaction* is invisible.

These three gaps are precisely what a structured trace closes.

---

## §3 Phase B — Trace schema design

### §3.1 Per-frame trace record

**Format:** JSON Lines (one JSON object per processed scoreboard frame), gzip on rotation. One file per pipeline session: `logs/trace/<SESSION_ID>.jsonl(.gz)` where `SESSION_ID` is the existing 8-char hex from `files/test_pipeline.py:L829`.

**Top-level schema (one record = one processed scoreboard frame):**

```jsonc
{
  "frame": 712,                          // frame_count
  "ts_wall": 1745524427.184,             // time.time()
  "ts_match": "RR 35-2 (4.3) inn=1",     // human, for grep
  "session": "8a3c1d92",
  "frame_type": "SCOREBOARD",            // tag from scout
  "cadence_ms": 1083,                    // ms since last trace record (wall)

  "capture": {                           // CAPTURE LAYER
    "cap_idx": 712,
    "cap_source": "obs-virtual-cam",     // post-migration
    "cap_resolution": [1920, 1080],
    "pix_skip": 4,                       // n pixel-skips before this commit
    "force_processed": true              // came from "Force-processing after N pixel skips"
  },

  "pipeline": {                          // PIPELINE STATE (top of frame, before processing)
    "innings": 1,
    "mode": "WARM",                      // WARM | COLD_START | TEAM_LATCH | INNINGS_HANDOFF
    "cold_start_gate": "OPEN",
    "ws_clients": 2,
    "batting_team": "Rajasthan Royals",
    "bowling_team": "Delhi Capitals",
    "striker": "Yashasvi Jaiswal",
    "non_striker": "Vaibhav Sooryavanshi",
    "current_bowler": "Axar Patel",
    "fow_count": 2
  },

  "scout": {                             // SCOUT LAYER (raw)
    "ms": 918,
    "tag": "SCOREBOARD",
    "strip": true, "overlay": false, "drs": false,
    "cam": "closeup", "phase": "between_play",
    "digits": true, "chars": 282,
    "raw_text_120": "STRIP: RR 35-2 (4.3) | Jurel 18(13) | Parag 7(9) | Axar 0-6 (0.3)",
    "action_100":   "A player, likely Dhruv Jurel, appears dejected ..."
  },

  "extractor": {                         // EXTRACTOR LAYER (raw, pre-guard)
    "ms": 1084,
    "model": "llama-4-scout-17b-16e-instruct",
    "score": 35, "wickets": 2, "match_overs": "4.3",
    "visible_team": "Rajasthan Royals",
    "target": null, "rr": null,
    "batters": [
      {"name": "Dhruv Jurel",  "runs": 18, "balls": 13, "row": 1},
      {"name": "Riyan Parag",  "runs": 7,  "balls": 9,  "row": 2}
    ],
    "bowler": {"name": "Axar", "wickets": 0, "runs": 6, "overs": "0.3"}
  },

  "scorer": {                            // SCORER LAYER (decisions)
    "ms": 1500,
    "model": "llama-4-scout-17b-16e-instruct",
    "proposed": {                        // what scorer would have committed before guards
      "score": 35, "wickets": 2, "overs": "4.3",
      "batter_updates": [
        {"name": "Dhruv Jurel",  "runs": 18, "balls": 13},
        {"name": "Riyan Parag",  "runs": 7,  "balls": 9}
      ],
      "dismissals": [{"name": "Dhruv Jurel", "mode": null}]
    },
    "decisions": [                       // GUARD/INVARIANT TRAIL — every tag emission, typed
      {"tag": "GUARD-DISMISS-WKTS-UNCHANGED",    "verdict": "block",  "reason": "wkts unchanged at 2"},
      {"tag": "GUARD-BATTER-NOT-IN-EXTRACTOR",   "verdict": "reject", "name": "Yashasvi Jaiswal"},
      {"tag": "GUARD-BATTER-NOT-IN-EXTRACTOR",   "verdict": "reject", "name": "Vaibhav Sooryavanshi"},
      {"tag": "SCORER-INVARIANT-FILTER",         "verdict": "skip",   "name": "Dhruv Jurel", "reason": "witnessed FOW exists"},
      {"tag": "SM-DROP-WITNESSED-OUT",           "verdict": "drop",   "slot": "bat1", "name": "Dhruv Jurel"},
      {"tag": "STRIKER-ALIGN-FALLBACK",          "verdict": "fallback", "striker_ref": "Yashasvi Jaiswal", "non_ref": "Vaibhav Sooryavanshi", "ext_names": ["Dhruv Jurel", "Riyan Parag"]},
      {"tag": "BOARD-INVARIANT-NO-UNDISMISS",    "verdict": "refuse", "name": "Dhruv Jurel"},
      {"tag": "GRAPHIC-FILTER",                  "verdict": "pass",   "info_panel_keyword": null}
      // … all guards that fired this frame
    ],
    "committed_changes": ["score→35", "overs→4.3", "wickets→2", "bowl:Axar Patel"]
  },

  "ball_event": {                        // BALL DETECTOR LAYER
    "type": null,                        // null | LEGAL | WICKET | WIDE | NO_BALL | BYE | LEG_BYE | ABSORBED_LEGAL
    "runs": null, "over": null,
    "extra_type": null, "free_hit": false,
    "absorbed_count": 0,
    "broadcast_extra": null,
    "dismissal_mode": null,
    "striker_this_ball": "Yashasvi Jaiswal"
  },

  "ui_before": {                         // CLIENT-MIRROR SNAPSHOT (post deepMerge)
    "scorecard": {"score": 35, "wickets": 2, "overs": "4.3", "run_rate": 7.78,
                  "striker": "Yashasvi Jaiswal", "non_striker": "Vaibhav Sooryavanshi",
                  "current_bowler": "Axar Patel"},
    "batting_card_at_crease": [
      {"name": "Yashasvi Jaiswal",     "runs": 6, "balls": 9, "is_striker": true},
      {"name": "Vaibhav Sooryavanshi", "runs": 0, "balls": 2, "is_striker": false}
    ],
    "bowling_current": {"name": "Axar Patel", "wickets": 0, "runs": 6, "overs": "0.3"},
    "this_over": ["1", "4", "1"],
    "extras_total": 1,
    "partnership_current": {"batters": ["Yashasvi Jaiswal", "Vaibhav Sooryavanshi"], "runs": 6, "balls": 11},
    "fow_count": 2,
    "innings": 1
  },

  "ui_after": { /* same shape as ui_before */ },

  "ui_diff": [                           // ONLY changed scalar paths; collapses to [] for no-op frames
    // {"path": "scorecard.score", "from": 34, "to": 35},
    // {"path": "this_over",       "from": ["1", "4"], "to": ["1", "4", "1"]}
  ],

  "anomalies": [                         // populated by detection module — see §4
    // {"id": "P1", "severity": "warn", "since_frame": 712, "evidence": {...}}
  ],

  "lat_ms": {"vision": 918, "extract": 1084, "scorer": 1500,
             "field": 40, "comm": 0, "code": 0, "total": 3509}
}
```

**Why this shape:**

- **`scorer.proposed` vs `scorer.committed_changes` closes Gap 1.** The proposed batter rows for Jurel/Parag are recorded *as proposed* even though they were rejected — the analyzer can now distinguish "extractor never saw the new batters" from "scorer proposed them, guard rejected them."
- **`scorer.decisions[]` is the typed promotion of every guard tag** — `[GUARD]`, `[SCORER-INVARIANT-FILTER]`, `[SM] dropping ...`, `[INVARIANT]`, `[POISON-RECAL]`, `[GRAPHIC-FILTER]`, etc. all become entries with a `tag` enum and a structured payload. Closes Gap 2 and Gap 3.
- **`ui_before` / `ui_after` are mirror snapshots** — built by maintaining a server-side `dict` that applies the same deepMerge logic as `useMatchSocket` to every emitted payload. This is the only way to capture what the *user* saw vs what the pipeline emitted (a NULL on the wire is invisible on the UI per `useMatchSocket.ts:L29-L33`).
- **`ui_diff[]` is the audit-friendly summary** — for grep/dashboard use; contains only changed scalar paths. Empty array on no-op frames so most lines are short.
- **`pipeline.mode`** distinguishes COLD_START / WARM / TEAM_LATCH / INNINGS_HANDOFF — anomalies must not fire during transitions when many fields legitimately churn (see §4.2).

**Decision-tag enum** (initial set, mirrors §2.2):

`GUARD-DISMISS-WKTS-UNCHANGED`, `GUARD-BATTER-NOT-IN-EXTRACTOR`, `GUARD-EXT-BATTER-REJECTED-BOARD-FULL`, `SCORER-INVARIANT-FILTER`, `SM-DROP-WITNESSED-OUT`, `BOARD-INVARIANT-NO-UNDISMISS`, `BOARD-DISMISS-AMBIGUOUS-SKIP`, `STRIKER-ALIGN-FALLBACK`, `BATTER-ALIGN`, `BOWLER-LOCK-RELEASED`, `BOWLER-LOCK-ACQUIRED`, `BOWLER-LEAD`, `WS-SLOT-INVARIANT`, `WS-SCRUB`, `BATTERS-INVARIANT`, `STRIP-ROWS-MISALIGNED`, `NEW-BATTER-BALLS-GATE`, `WICKET-AUTO`, `WICKET-AUTO-SKIP`, `WICKET-TRACK`, `WICKET-ATTRIB`, `EXTRAS`, `EXTRAS-INF`, `EXTRAS-INF-GATE`, `POISON-RECAL`, `POISON-RECAL-PRE-EMPTED`, `GRAPHIC-FILTER`, `CAM-GRAPHIC-FAST-PATH`, `FIELD-MONITOR`, `WS-COLD-START-GATE`, `SM-FEEDER-SYNC`, `BOWLER-BATTER-GATE`.

### §3.2 Volume estimate

Using the sample DETAIL line from RR-DC F712 (~2,700 chars, ~3 KB pretty / ~2 KB JSON-compact) as a baseline, with the new fields added:

| Component | Bytes/record |
|-----------|-------------|
| Existing DETAIL fields → JSON | ~2,000 |
| `scout.raw_text_120` + `action_100` | ~250 |
| `extractor.batters[]` + `bowler{}` | ~500 |
| `scorer.proposed{}` | ~400 |
| `scorer.decisions[]` (median 4–6 entries × ~120 B) | ~600 |
| `ui_before` + `ui_after` (mostly small) | ~1,200 |
| `ui_diff[]` (median 1–3 entries) | ~150 |
| Frame on quiet frames (no event, mostly empty diff) | ~3,500 |
| Frame on event frames (wicket / over change) | ~6,500 |
| **Mean (mixed)** | **~4.5 KB / record** |

Per-match totals (3-hour match):

| Cadence | Frames / match | Raw size | Gzip (~6×) |
|---------|---------------|----------|-----------|
| 0.5 fps (RR-DC actual, throttled) | 5,400 | 24 MB | 4 MB |
| **1 fps (post-capture-card-fix expected)** | **10,800** | **49 MB** | **8 MB** |
| 2 fps (worst-case adaptive in busy bursts) | 21,600 | 97 MB | 16 MB |
| 10 fps (sampled subset) | 108,000 | 486 MB | 80 MB |
| 61 fps (full capture) | 658,800 | 2.9 GB | 480 MB |

**Recommendation: emit one record per *processed scoreboard frame*** — the same cadence as the existing DETAIL line, no separate sampling logic. This bounds a typical match to 24–97 MB raw / 4–16 MB gzipped, which fits comfortably alongside the existing `pipeline-*.log` (the RR-DC tee was 50,856 lines / ~12 MB). Stop-condition S1 is **not** triggered; sampling logic is unnecessary.

### §3.3 Storage location and rotation

**Location:** `logs/trace/<SESSION_ID>.jsonl` — sibling to `logs/pipeline-*.log`. One file per pipeline process; on restart, a new SESSION_ID is generated (existing behavior at `files/test_pipeline.py:L829`).

**Rotation:** none during the match — the file is append-only and small enough (≤ 100 MB) that no in-process rotation is justified. After the match a `gzip` step (run by the analyzer or by ops cron) compresses to `<SESSION_ID>.jsonl.gz`. Retention: keep last 30 days uncompressed under `logs/trace/`, archive older to `logs/trace/archive/` (out of scope for this memo — operator decides).

**Schema versioning:** record schema version in the *first line* of the file as `{"_schema_version": 1, "session": "...", "started_ts_wall": ...}` so the analyzer can detect schema drift. Bump on any breaking change to `decisions[]` enum or top-level shape.

---

## §4 Phase C — Anomaly catalog

### §4.1 Patterns

Each pattern is computable from the trace alone; none requires external ground truth (S2 limit honored — see §8).

#### P1 — Batter persistence after wicket
**Definition:** a `WICKET` ball_event fires (or `wkts_left` decreases — see P5), but `ui_after.batting_card_at_crease` contains the same batter names as `ui_before.batting_card_at_crease` for ≥ N frames after the event.
**Detection rule:** sliding window over trace; flag when `ball_event.type == "WICKET"` is present in any record within the last 8 trace frames AND the union of names in `ui_after.batting_card_at_crease[*].name` is unchanged across all 8.
**Threshold:** 8 trace frames (~8 seconds at 1 fps; ~4 seconds at 2 fps).
**Severity:** **error** if persists ≥ 30 frames; **warn** if 8–29 frames.
**Root-cause guidance:** scan `scorer.proposed.batter_updates` and `scorer.decisions[]` in the post-wicket window:
- Proposed names match new pair → cause is a guard rejection (cite the `tag`).
- Proposed names match old pair / are empty → cause is upstream (extractor still reading old strip OR scout pre-Scout gate suppressing new strip frames).
- No `WICKET-AUTO` decision present and `ball_event.type=="WICKET"` → cause is the auto-dismiss path missing this transition (`files/test_pipeline.py:L3468-L3479`).

#### P2 — Score regression
**Definition:** `ui_after.scorecard.score < ui_before.scorecard.score` in the same record OR across consecutive records, without an `INNINGS-RESET` / `set_innings_2` marker between them.
**Detection rule:** for each consecutive pair of trace records `r[i-1]`, `r[i]`: flag if `r[i].ui_after.scorecard.score < r[i-1].ui_after.scorecard.score AND r[i].pipeline.innings == r[i-1].pipeline.innings`.
**Threshold:** any single regression — no debounce.
**Severity:** **error** (always — score must monotonically increase within an innings).
**Root-cause guidance:**
- `r[i].scorer.committed_changes` contains `score→<smaller>` → scorer accepted a regressing extractor read; cite `r[i].extractor.score` and any guard that did NOT fire (`POISON-RECAL` should have fired with `|Δ| > 7`).
- `r[i].scorer.committed_changes` empty but ui_after lower → mutation came from a non-scorer path (FULL_RESET / innings clear). Cite `r[i].pipeline.mode`.

#### P3 — Stale bowler
**Definition:** `ui_after.bowling_current.name` unchanged across N consecutive trace records that span ≥ 2 distinct overs of apparent bowling activity (i.e., `pipeline.current_bowler` and `committed_changes` reflect the same name across >= 2 over-boundary crossings).
**Detection rule:** maintain a per-bowler "last over change" cursor; flag when `(current_over - bowler_last_changed_over) >= 2` AND any `BOWLER-LOCK-RELEASED` decision did NOT subsequently lead to a `BOWLER-LOCK-ACQUIRED` within 12 trace frames.
**Threshold:** 2 overs of apparent bowling activity — single-over runs are normal (a bowler can bowl two consecutive overs only after a third bowler in between, but UI showing same bowler for ≥ 12 deliveries always indicates a problem).
**Severity:** **warn** at 2 overs, **error** at 3+ overs.
**Root-cause guidance:**
- Scan `scorer.decisions[]` for `BOWLER-LEAD` arbitrations across the window — if scorer kept rejecting a new bowler proposal, cite the rejection reason.
- If `BOWLER-LOCK-RELEASED` fires but no `BOWLER-LOCK-ACQUIRED` follows → the bowler-confirmation logic isn't seeing enough consecutive frames; cite the consecutive-frame counts in those decisions.

#### P4 — Partnership math error
**Definition:** `ui_after.partnership_current.runs ≠ Σ(runs of current at-crease batters since last wicket)`.
**Detection rule:** find the most recent `r_w` where `WICKET-TRACK` decision fired. Sum `ui_after.batting_card_at_crease[*].runs` for the *current* striker/non in `r[i]` minus their `r_w.ui_before` runs (extras attributed correctly). Flag when the absolute delta vs `ui_after.partnership_current.runs` exceeds 2 (allows for in-flight extras).
**Threshold:** delta > 2 runs sustained for ≥ 3 trace records (single-frame races are common during a delivery commit).
**Severity:** **warn**.
**Root-cause guidance:** the partnership tracker is fed independently of SM; cite which writes occurred (look for `partnership_tracker.current(...)` calls in the BEFORE/AFTER snapshots) and whether `SM-FEEDER-SYNC` decisions show divergence.

#### P5 — Wickets-left decreased without WICKET event
**Definition:** `ui_after.scorecard.wickets > ui_before.scorecard.wickets` in record `r[i]`, but no `ball_event.type=="WICKET"` and no `WICKET-TRACK` / `WICKET-AUTO` decision in `r[i-2..i+2]`.
**Detection rule:** straightforward delta + decision-log scan.
**Threshold:** any single occurrence (debounce only on `pipeline.mode == "COLD_START"`).
**Severity:** **error**.
**Root-cause guidance:** the wickets number was committed by the extractor without ball-detector or scorer-side wicket attribution. Cite `r[i].extractor.wickets` vs `r[i-1].extractor.wickets` (extractor jumped) vs the absent `WICKET-AUTO` decision (auto-dismiss path missed it). This is the **phantom wicket** pattern from RR-DC.

#### P6 — Extras inconsistency
**Definition:** `ui_after.extras_total ≠ wides + no_balls + byes + leg_byes + penalties` (sum of components).
**Detection rule:** simple arithmetic on `ui_after.extras` from the WS payload mirror (Extras schema at `scorecard-ui/app/lib/types.ts:L89-L97`). Flag any record where the field-sum disagrees with `total` by ≥ 1.
**Threshold:** any single occurrence (this is an internal-consistency check, not a temporal one).
**Severity:** **warn**.
**Root-cause guidance:** scan `scorer.decisions[]` for `EXTRAS-INF` and `EXTRAS-INF-GATE` entries in the same record — these are the reconciliation sites; if they are absent, the extras map was written by extractor pass-through and the reconciler missed it.

#### P7 — Innings score reset while broadcast showed continuity
**Definition:** `ui_after.scorecard.score` drops to 0 OR `ui_after.scorecard.wickets` resets to 0 in record `r[i]`, but `r[i].pipeline.innings == r[i-1].pipeline.innings` (innings counter not advanced).
**Detection rule:** detect drop-to-zero with same innings counter.
**Threshold:** any single occurrence.
**Severity:** **error**.
**Root-cause guidance:** a `full_reset(...)` was called (see `files/score_manager.py:L816` — `full_reset` method) without an accompanying `set_innings_2` marker. Cite the `committed_changes` and any `pipeline.mode == "INNINGS_HANDOFF"` transition that should have surrounded it.

#### P8 — This-over ball-count mismatch
**Definition:** `len(ui_after.this_over) ≠ ball_within_over(ui_after.scorecard.overs)` where `ball_within_over("4.3") == 3`. (Allows `>=` for legal-extra over-extension.)
**Detection rule:** parse `overs` field, derive expected ball count, compare with `len(this_over)`.
**Threshold:** absolute delta > 1, sustained ≥ 2 records (single-frame races during commit are normal).
**Severity:** **warn** at delta=2; **error** at delta≥3.
**Root-cause guidance:** scan the over_history transitions and `completed_over_runs` field — if `completed_over` fired in `r[i-1]` but `this_over` in `r[i]` still contains old balls, the over-rollover handler missed a write. Cite the `over_mgr` source-cell tags from `AFTER_this_over_src` (existing in DETAIL).

#### P9 — Stuck UI field during apparent active play
**Definition:** any of {score, wickets, this_over, striker, non_striker, current_bowler} unchanged for ≥ T trace records during which `pipeline.mode == "WARM"` AND `frame_type` is in `{SCOREBOARD}` (i.e., not all ad / replay / closeup frames).
**Detection rule:** per-field "last changed at" cursor. Flag when stale duration exceeds field-specific T (see thresholds below).
**Thresholds (calibration in §4.2):**
- score: T = 12 trace records (~12 s at 1 fps; ~6 s at 2 fps) — covers any over with no scoring + the gap between overs.
- wickets: T = uncalibrated (changes rarely; covered by P5).
- this_over: T = 30 records (~30 s) — covers any dot-ball cluster.
- striker / non_striker: T = 30 records.
- current_bowler: T = 36 records (~ 6 deliveries) — pair with P3.

**Severity:** **info** (this is the high-noise rule and should be triaged manually).
**Root-cause guidance:** the operator workflow is to look at the `decisions[]` entries in the stuck window — most stuck-state cases have either repeated `[GUARD]` rejections or repeated `[GRAPHIC-FILTER]` filters that are blocking the corrective read.

**Additional patterns deferred to v1.1 (or out of scope):**
- P10 — Striker-stat regression (runs/balls of an at-crease batter decreasing without a new arrival).
- P11 — Bowler-figures regression (wickets/runs of `current` bowler decreasing).
- P12 — `scorecard.wickets` ≠ `len(fall_of_wickets where !_unwitnessed)`.
- P13 — RRR / required_rate sanity (chase math contradicts target).

These are valuable but each requires more thresholding work; ship the nine v1 rules first.

### §4.2 Severity calibration

Calibration source: the 50,856-line RR-DC tee + the prior MI-SRH and PBKS-RR tees referenced in `files/docs/investigations/match_monitoring_plan_pre_live.md`. Specific noise sources:

- **COLD_START windows** (`pipeline.mode == "COLD_START"`): suppress P1, P2, P3, P5, P7 entirely; many fields legitimately go from null/zero to the live value.
- **INNINGS_HANDOFF** (`pipeline.mode` transitions): suppress P2, P3, P5, P7 for a 60-trace-record window after the transition. P1 continues but its threshold doubles.
- **Pixel-skip force-processing windows** (`capture.force_processed == true`): a force-processed frame after 4 pixel skips often carries a stale strip; relax P1/P3/P9 by 50% in these records.
- **Ad / replay windows** (`scout.cam == "ad"` or `phase != "active_play"` for ≥ 5 consecutive records): P9 is paused entirely — the UI not changing during 30s of ads is correct behavior.
- **DRS pause** (`drs_state != "NONE"`): P3, P9 paused.

**Why these specific numbers:** the RR-DC log shows DETAIL emission ~every 4 seconds on average (~0.5 fps), so a 12-record stale window is ~50 wall-seconds — long enough to span a slow over but short enough to catch the 4+over freeze observed in innings 2. With the post-capture-card emission at 1–2 fps, the same 12-record window is 6–12 seconds — also reasonable for a per-over check. Operator should re-tune after the first 3–5 post-fix matches.

### §4.3 Anomaly explanation logic

For each fired anomaly, the analyzer attaches an `evidence` block to the trace record and to the report. The explanation logic is rule-specific but follows a common template:

```jsonc
{
  "id": "P1",
  "severity": "error",
  "fired_at_frame": 1247,
  "first_evidence_frame": 1239,
  "duration_frames": 8,
  "evidence": {
    "wicket_event": {"frame": 1239, "type": "WICKET", "over": "8.4", "dismissed": "Dhruv Jurel"},
    "ui_at_crease_unchanged": ["Yashasvi Jaiswal", "Vaibhav Sooryavanshi"],
    "scorer_proposals_in_window": [
      {"frame": 1240, "names": ["Yashasvi Jaiswal", "Riyan Parag"]},
      {"frame": 1242, "names": ["Yashasvi Jaiswal", "Riyan Parag"]}
    ],
    "decisions_blocking": [
      {"frame": 1240, "tag": "SCORER-INVARIANT-FILTER", "name": "Riyan Parag", "reason": "..."},
      {"frame": 1242, "tag": "GUARD-BATTER-NOT-IN-EXTRACTOR", "name": "Riyan Parag"}
    ],
    "verdict": "Scorer correctly proposed Riyan Parag as new batter; GUARD-BATTER-NOT-IN-EXTRACTOR rejected it because the extractor row read 'Parag' as the *non-striker* row alongside the dismissed 'Jurel' still in row 1. Likely cause: stale strip graphic showing the dismissed Jurel — confirm via scout.raw_text_120 in F1240–F1247."
  }
}
```

The `verdict` string is template-driven, not free-text — each rule has a small set of sub-causes that map to template strings (3–6 templates per rule), parameterized by the cited evidence fields. This keeps the analyzer deterministic and reproducible across runs.

**For the RR-DC observed bugs**, this maps to:

- **Wrong batters showing on UI** → P1 fires, evidence will show repeated `SCORER-INVARIANT-FILTER` + `GUARD-BATTER-NOT-IN-EXTRACTOR` rejections of the new pair (per the actual F716/F720 sequence captured in §2.1). Verdict template: "Stale strip graphic; corrective scorer reads consistently rejected as 'extractor saw dismissed batter.'"
- **Phantom wicket persisted** → P5 fires immediately on the wickets jump; verdict cites whether the extractor jumped vs SM accepted vs no auto-dismiss path fired.
- **Score frozen at 10.3 for 4+ overs** → P9 fires for `score` field at T=12 records; evidence cites the decision pattern in the stuck window (likely repeated `GRAPHIC-FILTER` rejections of all extractor commits because the strip pattern looked graphic-like).
- **Bowler regression** → P3 fires; cite `BOWLER-LEAD` arbitrations.
- **Extras tracking broken** → P6 fires on the first reconciliation gap; cite absent `EXTRAS-INF` decisions.

---

## §5 Phase D — Surfacing & operator workflow

### §5.1 Real-time tagging (v1.1)

The detection module runs incrementally over each new trace record as it's appended. When an anomaly fires for the first time, it emits `[ANOMALY-Pn] <severity> <one-line-summary> trace_idx=<n>` to the existing tee log via `log.warn`/`log.error` (severity-mapped). The trace record itself gets the `anomalies[]` entry attached.

**Hard-stop integration (operator decision — see §7):** for `severity=="error"` rules sustained beyond a threshold (e.g., P5 phantom wicket fires once), the recommendation is to add this to the existing hard-stop checklist in `files/docs/MONITORING_CHARTER.md` rather than auto-killing the pipeline. The operator runs the kill — the system surfaces the trigger.

**Defer to v1.1 if scope pressure:** ship the trace + analyzer first, add real-time tagging once the rules have been calibrated against ≥ 3 post-fix matches. This avoids tag-spam during a critical match while we're still tuning thresholds.

### §5.2 Post-match analyzer

**Tool:** `files/analyze_trace.py` (sibling to existing `files/analyze_match_telemetry.py`).
**Invocation:** `python files/analyze_trace.py logs/trace/<SESSION>.jsonl --report files/docs/match_reports/<DATE>_<MATCH>.md`.

**Steps:**
1. Stream-read the JSONL, validating against the v1 schema; reject if `_schema_version != 1`.
2. Build per-frame-windowed state for each rule's threshold logic.
3. Apply the suppression rules (COLD_START, INNINGS_HANDOFF, ad windows, DRS) per §4.2.
4. Emit a Markdown report with the structure below.

**Report structure:**

```markdown
# Match trace report — <session>
**Match:** RR vs DC, 43rd match, IPL 2026, 2026-05-01
**Trace:** logs/trace/8a3c1d92.jsonl(.gz) — 10,847 records, 2026-05-01 19:30:14 → 2026-05-01 22:34:51

## Summary
- Records: 10,847 (1.0 fps mean; 2.1 fps peak)
- Decisions emitted: 47,221
- Anomalies fired: P1×3 (1 error, 2 warn), P3×1 (warn), P5×1 (error), P6×7 (warn), P9×4 (info)
- Mode windows: COLD_START 124 records, INNINGS_HANDOFF 1 (frame 5247), WARM 10,540, suppressed by mode 183

## Errors (operator action required)
### P5 — Phantom wicket at frame 4128 (over 12.2)
- ui_before.wickets=4, ui_after.wickets=5; no WICKET ball_event in F4126–F4130
- extractor jumped: F4127 wkts=4, F4128 wkts=5
- no [WICKET-AUTO] decision in window
- **Verdict template:** "Extractor wickets jump committed without ball-detector or auto-dismiss path firing. Cause likely: extractor mis-read or graphic transition not filtered."
- Trace: F4126–F4135. Tee context: pipeline-2026-05-01-1935-...:L31204-L31298

### P1 — Batter persistence after wicket at frame 1239 (over 8.4)
- ... (full evidence block)

## Warnings
... (P1×2, P3×1, P6×7)

## Info
... (P9×4 stuck-state)

## Decision-tag histogram
| Tag | Count | Median frames between |
|-----|-------|----------------------|
| GUARD-BATTER-NOT-IN-EXTRACTOR | 412 | 14 |
| GRAPHIC-FILTER | 287 | 31 |
| POISON-RECAL | 8 | — |
| ... |

## Mode timeline
F1–F124: COLD_START → WARM (124 frames)
F5247: INNINGS_HANDOFF → WARM
... (compact)

## Latency p50/p95/p99
vision: 821 / 1402 / 2103 ms
extract: 1093 / 1612 / 2487 ms
scorer: 1187 / 1802 / 3012 ms
total: 3402 / 4711 / 6298 ms

## Trace pointer index
Each anomaly above links to a frame range in the JSONL by `frame` field; `jq -c 'select(.frame >= 4126 and .frame <= 4135)' logs/trace/8a3c1d92.jsonl` returns the supporting records.
```

### §5.3 Operator workflow

**During match:** unchanged from current. Operator tails `logs/pipeline-*.log` and watches for hard-stop tags per `match_monitoring_plan_pre_live.md`. If real-time anomaly tags ship in v1.1, they appear in the same tail.

**Post-match (the new step):**
1. Run analyzer: `python files/analyze_trace.py logs/trace/<SESSION>.jsonl --report .../<MATCH>.md`.
2. Review report's **Errors** section first. Each error must be triaged: real bug vs known suppression-window edge vs detection false positive.
3. For each real-bug error, cross-reference the cited frame range in the trace JSONL using `jq -c 'select(.frame >= X and .frame <= Y)'` to inspect the full decision trail.
4. Open an investigation memo if the root cause is unclear. The trace record is the new artifact — paste the relevant frame slice into the memo.

**File shape, naming, count update:** the report goes under `files/docs/match_reports/<YYYY-MM-DD>_<match-slug>.md` (new directory; not under `investigations/`, keeping it separate from one-off design artifacts).

---

## §6 Implementation scope

| Component | LOC est. | Files touched |
|-----------|----------|---------------|
| Trace record builder (replaces DETAIL f-string) | ~200 | `files/test_pipeline.py` (single section L10460–L10650 → ~250 lines new) |
| Decision-tag promotion (typed entries on every emission site) | ~150 | `files/test_pipeline.py` (~30 sites), `files/score_manager.py` (~6 sites), `files/eyes/scoreboard.py` (~3 sites) |
| Server-side UI mirror (deepMerge replica) | ~50 | `files/test_pipeline.py` near `broadcast_state` (`L809-L827`) |
| Trace writer + rotation | ~60 | new `files/trace_emitter.py` |
| Detection rules (P1–P9) | ~250 | new `files/anomaly_rules.py` |
| Analyzer CLI + Markdown report | ~150 | new `files/analyze_trace.py` |
| pytest fixtures: replay 6–8 captured RR-DC frames per rule | ~150 | new `files/tests/test_anomaly_rules.py` |
| Real-time emission (v1.1) | ~80 | hooks in `files/test_pipeline.py` after each trace record append |
| **Total v1 (post-match analyzer only)** | **~860** | |
| **Total v1.1 (with real-time tagging)** | **~940** | |

**Phasing:** v1 (post-match) is one session; v1.1 (real-time) is a follow-up after threshold calibration on 3–5 post-fix matches.

**Risk hot-spots:**
- The decision-tag promotion touches ~40 emission sites — high surface area, low per-site complexity. Each site needs a small structured payload alongside the existing `log.info(...)` call.
- The server-side UI mirror must exactly match `useMatchSocket.deepMerge` (`scorecard-ui/app/hooks/useMatchSocket.ts:L5-L36`) — a divergence here means `ui_before` / `ui_after` lie. Add a parity test: send a known sequence of payloads through both implementations, assert identical post-merge state.

---

## §7 Open questions for operator decision

**Q1 — Default trace cadence: same as DETAIL line, or higher?**
Recommendation: same as DETAIL (per processed scoreboard frame). Volume: 4–16 MB gzipped/match. Higher cadence (e.g., one record per *capture* frame, including pixel-skipped) would let P9 stuck-state detection see broadcast continuity through skipped frames, but would 4–8× the volume. **Need operator yes/no.**

**Q2 — Storage location and rotation policy.**
Recommendation: `logs/trace/<SESSION>.jsonl` uncompressed during match; gzip post-match; retain uncompressed 30 days, archive older. Alternative: write directly gzipped (saves disk in flight, but breaks `tail -f` during match). **Need operator yes/no on retention window and gzip-during-match.**

**Q3 — Real-time vs post-match — ship which first?**
Recommendation: **post-match analyzer first (v1)**, real-time tags as v1.1 once thresholds are calibrated. Real-time risks tag-spam during a critical match before tuning; post-match is a strictly forensic add. **Need operator concurrence or override.**

**Q4 — Which anomaly patterns ship in v1?**
Recommendation: **P1, P2, P3, P5, P6, P7, P8, P9 — eight rules**. Defer P4 (partnership math) to v1.1: it depends on accurate extras attribution which the v1 analyzer has not yet validated against truth. Defer P10–P13 entirely until the v1 nine settle. **Operator: confirm cut, or expand?**

**Q5 — Severity thresholds for P1, P3, P9 (the high-noise rules).**
Recommendation per §4.2 (P1: 8 frames warn / 30 frames error; P3: 2 overs warn / 3+ error; P9 score: 12 records info). These are first-cut numbers; expect re-tuning after match #1 post-fix. **Operator: accept first-cut, or adjust now based on intuition from RR-DC?**

**Q6 — Should real-time anomaly emission ever auto-hard-stop the pipeline?**
Recommendation: **no**, surface to operator only. Rationale: every existing hard-stop tag (`POISON-STREAK`, `WS-COLD-START-GATE` timeout, etc.) is operator-triggered, not auto-kill. Adding the first auto-kill changes operator workflow. **Operator: confirm or override.**

**Q7 — How to handle schema evolution.**
Recommendation: bump `_schema_version` on the file's first line on any breaking change to `decisions[]` enum or top-level shape. Analyzer must reject mismatched versions rather than silently mis-parse. **Operator: agree on version-fail behavior, or prefer best-effort + warning?**

---

## §8 Limitations and risks

**L1 — No external ground truth.** Stop-condition S2 honored: every v1 rule is internal-consistency only. The system **cannot** detect:
- A scoreboard reading the *wrong* score (e.g., shows 87 when actual is 89) when nothing inside the trace contradicts that.
- A bowler swap that actually happened on the broadcast but the pipeline missed entirely (no extractor read of the new bowler ever arrives, so there's nothing for P3 to flag against).
- An innings transition that the broadcast announced but the pipeline failed to detect.
These require either (a) live scorecard fetch (deferred per scope), or (b) a second-channel observer (the parallel-Scout open-prose narration in `parallel_scout_delivery_window_design.md` could grow into this — out of scope here).

**L2 — UI mirror parity.** The server-side `ui_before` / `ui_after` snapshots depend on a faithful replica of the client `deepMerge`. If this mirror drifts from `scorecard-ui/app/hooks/useMatchSocket.ts:L5-L36`, every UI-visible anomaly is computed against a wrong snapshot. Mitigation: parity test (above). Risk remains MEDIUM if the UI client ever changes its merge semantics without the mirror being updated.

**L3 — Cadence-throttled traces lose between-frame signal.** RR-DC was 0.5 fps capture-throttled (5,524 frames in 3 hours per the user prompt) — many of the visible bugs span tens of seconds, so the 1–2 fps post-fix cadence is sufficient to catch them. But: a 200ms phantom-wicket flicker (extractor jumps to wkts=5 for one frame, then back to 4) is invisible at 1 fps. P5 will not catch sub-emission-cadence transients. Acceptable — those don't reach the UI either at the current emission cadence.

**L4 — Decision-tag promotion is high surface area.** 40 sites, each with their own ad-hoc log format, get a structured payload added. Risk of partial implementation (some sites still text-only) is real. Mitigation: pytest fixture per tag asserts the trace record contains the typed entry when the tag's trigger condition is replayed. CI fails if a site falls back to text-only.

**L5 — Anomaly thresholds are guesses.** §4.2 calibration is based on one tee + retro of three earlier tees. The first 3–5 post-fix matches will inevitably surface threshold-tuning needs; expect a v1.0.1 round of constant tweaks. Operator workflow during this calibration period: expect ~5–15 per-match warnings to triage, settling to ~1–3/match once tuned.

**L6 — `pipeline.mode` taxonomy (COLD_START / WARM / TEAM_LATCH / INNINGS_HANDOFF) is partially derived, not directly emitted today.** Some of these states are implicit in flag combinations (e.g., `_ws_cold_start_gate_open == False` → COLD_START). The trace builder must compute and explicitly stamp `pipeline.mode` per record; getting this wrong corrupts the suppression rules in §4.2. Mitigation: a dedicated ~30 LOC `pipeline_mode.py` helper with unit tests for each transition.

**L7 — None of this fixes the bugs.** The trace + analyzer make root-causing reproducible, not the bugs themselves disappear. Each Markdown report should be followed by an investigation memo + fix when an error pattern recurs across two matches.

# Handoff — Session continuation document

**Last update**: 2026-05-14 (chat is slow; new session needed)
**Branch**: `derive-not-detect`
**Status**: Phase A1 + A2 derivation-only refactor complete (30+ commits today). Validation surfaced 4 issues mid-flight; investigation prompt is in chat history and ready to send to CC.

Entry point for next Cowork session. Read this first, then `CLAUDE.md`, then the design spec at `files/docs/investigations/derivation_only_stats_design.md`.

## TL;DR — Where we are

End-to-end cricket broadcast analysis pipeline. The detection architecture has been rebuilt around two principles:
1. **Detection vs Derivation**: vision detects identity (names) only; all numerical stats derive from event accumulation.
2. **ScoreManager (SM) is the sole authority**: no parallel writers, no strip-driven stats updates. Pipeline tracker → SM event → derivation hook → bowling_card / batting_card.

Phase A1 (bowler) and A2 (batter) are landed. Strip-driven `update_bowler` and `update_batter` writes are neutralized; event-driven `_apply_bowler_delta` / `_apply_batter_delta` are sole writers. Cross-cutting fixes for cold-start propagation, gap-token inference, anti-hallucination veto, joint-pop unblocking, and striker rotation symmetry have all shipped.

**Validation pass surfaced 4 remaining issues** (see Pending below). Investigation prompt is drafted and was the last action in the previous chat — paste into CC to continue.

## Architecture: design principles

### Detection vs Derivation
- **Detection** (vision-only): batting_team, striker/non-striker/bowler names, dismissal events, run events, over-rollover events, boundary classification.
- **Derivation** (event-driven, no vision for stats): bowling_card[name].balls/runs/wickets/overs/maidens, batting_card[name].runs/balls_faced/fours/sixes/status.
- Strip values flow through `update_*` methods but the stat-write code paths are neutralized (kwargs coerced to None); only NAME observations feed the trackers.
- Divergence between derived state and observed strip is logged as `DERIVATION-STRIP-DIVERGENCE-*` trace tags for audit. Never overrides derived state.

### SM as sole authority
- BED (`files/eyes/commentary.py`) emits events as advisory shadows (`SHADOW SM=X BED=Y MISMATCH`). SM's own event inference (`_infer_event` → `_accumulate_stats_from_event`) drives derivation.
- `_event_baseline_score` is a persistent baseline anchored at successful event commits. d_score is computed against this baseline, not `self.score` (which can be clobbered by DIRECT/BOARD writers before `_infer_event` runs).
- Seeded at COLD_START → WARM exit and at hot_resume_from_cache; reset to 0 at innings-2 transition.

### ConfidenceTracker (`files/eyes/confidence_tracker.py`)
- Unified state machine: TENTATIVE → PUBLISHABLE → FIRM → LOCKED → IMMUTABLE (innings-2 only).
- Per-entity trackers: batting_team, striker, non_striker, bowler.
- Bowler tracker: FIRM threshold 3.0, half-life 30s, LOCKED on FIRM. Unlocks on over-end.
- Striker/non-striker: FIRM 3.0, half-life 60s post-cefc595 tuning.
- Batting team: FIRM 5.0 → IMMUTABLE on innings-2 detection.

### Hard cricket invariants
- `at_the_crease` max 2 batters with `status="batting"` (def2c0f).
- Score, overs, wickets monotonically non-decreasing.
- Wickets capped at 10.
- Bowler cannot bowl two consecutive overs (CONSECUTIVE-OVER-BOWLER-REJECTED).
- `sum(batting_card[*].balls_faced) <= team_legal_balls` (BATTER-BALLS-INVARIANT-FREEZE).
- `single_ball_max_score = 7` (six + nb); `multi_ball_max_runs = 7*balls + 5`; `MULTI_BALL_MAX_BALLS = 12` for WARM, `3` for cold-start.

### GRAPHIC-FILTER scope
- Cam ∈ {graphic, ad, replay, other} → dead-time-skip, no state derivation.
- Exception: cam=graphic AND has_strip=true → routes through hybrid extractor path (downstream gates handle overlay hallucinations).
- Mode-C inset detection poisons score AND this_over_broadcast (extended in afe6dfd-area).

### Cold-start handling
- Consensus floor: 2 frames (tightened from 3 in 7689d90). Cold-start MULTI_BALL_MAX_BALLS = 3 (vs WARM=12). Tighter because no anchored state.
- COLD_START → WARM exit synthesizes the gap from cold-start-entry state. `_synthesize_cold_start_ball_events` produces tokens via `infer_gap_tokens(n_balls, runs, wkts)`.
- Skeleton-strip rejection (d935966): drops frames where score+overs present but batters+bowler all null.
- Pre-match cue regex rejects frames containing "won the toss / chosen to / walking onto / warmup".
- COLD-START-PHYSICS-PROMOTE (635a485 / Option E): on flip-and-reset, if candidate-to-card transition is forward-legal physics (Δballs ≤ 3, validate_diff.ok), promote candidate as anchor and commit new card as MULTI_BALL with gap synthesis.
- Synth credit walk (8cb9465 / af7d32d): credits bowler.balls + bowler.runs + batter.balls_faced + batter.runs + boundaries per token, with fallback to scoreboard accessors if SM-side slots not yet populated.

### Off-roster gate
- When extracted batters resolve to off-roster names, frame is non-live and all state-derivation signals suppressed (c5c4792).

## Pipeline tracks

### Track 1 — State derivation (production pipeline)
Live state for UI: score, overs, wickets, this_over, recent_overs, batting_card, bowling_card, partnership, FOW, batting_team, current_bowler, striker.

Entry: `files/test_pipeline.py` main loop. Frame source: `files/eyes/capture/udp_frame_source.py` (UDP MPEG-TS via ffmpeg subprocess).

Status: **A1+A2 landed**. 4 validation issues pending (see below). Single full-stack validation ongoing.

### Track 2 — Clip extraction (OpenScout)
Parallel Scout system for ball-event clip detection. Writes clips for delivery verification UI.

Entry: `files/eyes/open_scout.py` + `files/eyes/openscout_loop.py`. Sidecar persistence: `files/eyes/openscout_persistence.py`.

Status: **Disabled** (`USE_OPEN_SCOUT=0`). Will not enable until Track 1 fully validated.

429 retry buffer for Track 2 shipped in 3a0a4f8 (`_ScoutRetryBuffer`, capacity 3, 5s staleness). Track 1 has its own in-call retry (5e4ff8a).

## File paths

```
files/test_pipeline.py             # Main pipeline (~13K lines)
files/score_manager.py             # State machine (~3.5K lines)
files/eyes/scoreboard.py           # batting_card / bowling_card / squad resolution
files/eyes/confidence_tracker.py   # ConfidenceTracker class + unit tests
files/eyes/vision.py               # SCOUT_PROMPT_SHORT (default), SCOUT_PROMPT (verbose)
files/eyes/agent.py                # Vision agent (LLM-based) + digits-veto + Track 1 429 retry
files/eyes/commentary.py           # BED (advisory shadow event detector)
files/eyes/this_over.py            # over_mgr (this_over tokens, archival, MULTI_BALL handler)
files/eyes/extract_regex.py        # Regex-primary parse_strip + hyphen-guard for bowler rows
files/eyes/open_scout.py           # OpenScout VLM prompt (Track 2)
files/eyes/openscout_loop.py       # OpenScout orchestration + 429 retry buffer
files/eyes/udp_frame_source.py     # UDP MPEG-TS frame source w/ watchdog + frozen-frame telemetry
files/eyes/match_state.py          # Scorer LLM (response_format=json_object)
files/cricket_rules.py             # validate_diff invariants + infer_gap_tokens helper
files/trace_emitter.py             # Structured trace tag emitter (KNOWN_TAGS registry)
files/scripts/extract_live_clips_chunk.sh  # Track 2 clip extractor (60s loop)
files/scripts/stream_to_server.sh         # Mac UGREEN dual-UDP sender (live)
files/scripts/stream_to_server_test.sh    # Mac file replay dual-UDP sender

scorecard-ui/app/page.tsx          # Main UI (live, scorecard, field, comm, clips, logs)
scorecard-ui/app/deliveries/page.tsx # Clip verification UI
scorecard-ui/app/logs/page.tsx     # Log tail viewer
scorecard-ui/app/components/BattingCard.tsx # at-the-crease, green dot

files/docs/investigations/derivation_only_stats_design.md  # Phase A1+A2 spec
files/docs/investigations/thread7_fix2_cam_graphic_fast_path_design.md
files/docs/investigations/trace_and_detect_system_design.md

deploy/systemd/*.service           # pipeline, recorder, live-clips, ui
deploy/Caddyfile                   # reverse proxy
.github/workflows/deploy.yml       # CI deploy
```

## Today's session commits (chronological, ~30 commits)

```
4c58a82 fix(udp-stream): keyframe re-injection + cfr pacing + frozen-frame telemetry
d935966 fix(cold-start): skeleton-strip + pre-match-cue rejection
6d6719e fix(strip-head): joint-pop atomic on overs reject
8140867 fix(graphic-filter): plausibility gate replaces unconditional poison
afe6dfd fix(strip-head): team-match veto at broadcast override + joint-pop on overs regression
6d3bf2a fix(#63 root cause): chase-signature gate on detected_target
cd4f36a fix(wicket-attrib): SM.striker authoritative, scorer dismissal advisory
2a7aac0 fix(wicket-double-write): apply_known_wicket_increment idempotency
33a8574 fix: dismiss_batter parallel idempotency
7689d90 tune(cold-start): consensus floor 3→2 frames
8941e7e feat(cold-start): synthesize ball events from state delta at WARM entry
7332d83 fix(strip-ingestion): overs fast-confirm + physics-aware graphic-filter + GRAPHIC+strip routing
adb587d fix(bowler-override): 2-frame consensus + freeze attribution during transition
8c1b33a fix(attribution): bowler-row junk + wicket-event-required + batter-balls sum invariant
2640a11 docs(investigations): derivation-only stats architecture spec
96b2cce feat(bowler): neutralize strip-driven bowling_card writes (A1 part 1)
5e02a1c feat(bowler): MULTI_BALL decomp + F381 backfill + dismissal filter + maidens + divergence + consecutive-over trace (A1 part 2)
4dbd0e3 fix(sm-event-delta): persistent baseline (option 2)
caedd4c fix(sm-event-delta): reset _event_baseline_score on innings-2
44f2510 fix(sm-event-delta): seed _event_baseline_score at WARM-entry paths
efb0139 feat(batter): neutralize strip-driven batting_card writes; delete f043c5d (A2 part 1)
32a2207 feat(batter): MULTI_BALL + ABSORBED_LEGAL decomp + extras + maiden gap fix + divergence (A2 part 2)
86e9aa4 fix(gap-tokens): unified infer_gap_tokens helper + 5 call sites
635a485 fix(cold-start): physics-linked promotion on forward-legal transitions (Option E)
7d1ddbf fix(pre-a2): joint-pop unblocked + ABSORBED_LEGAL bowler credit + extractor regex + extras positive witness
8cb9465 fix(cold-start + strip-head): synth credits on LOCKED + team-token prefix gate + forward-balls-no-score pop
625e397 fix(scout): veto STRIP block when classifier reports digits=false (anti-hallucination)
af7d32d fix(cold-start): synth credit fallback + tighten digits-veto to score>=10
b858dd5 fix: partnership balls increment in synth credit walk (PART 1)
cfd4b8c fix(striker-rotation): apply odd-run swap before end-of-over swap (option 1)
```

Run `git log --oneline derive-not-detect | head -50` for full list.

## Pending — 4 issues from latest validation pass

Investigation prompt was drafted at the end of the previous chat. Paste into CC to start.

### Issue 1 (major) — overlay/ad window starves event detection
At over 5 start (4.0-4.5 ov), "BE UNSTOPPABLE" promotional overlay obscured the strip for ~5 balls. Pipeline missed per-ball events. Recovery via MULTI_BALL decomp distributed runs as `. . 5` instead of broadcast `4 . 1` (heuristic put boundary at end; reality had it at start). Bowler stayed Roy throughout instead of Tyagi (new bowler for over 5).

### Issue 2 (major) — bowler-debut latency + no retroactive credit
Narine took over for over 4 (3.0 ov). Pipeline didn't detect his name until 3.4. Events 3.1/3.2/3.3 fired with bowler=None and never retroactively credited when Narine locked. Live bowling card showed Narine 0.1/4/0 at 3.5 ov instead of 0.5/10/0.

F381 backfill mechanism (5e02a1c) handles this exact pattern for WICKET events. Needs extension to all ball events (runs/dots) — buffer during bowler-unknown window, drain on LOCK.

### Issue 3 (minor) — this_over UI display stale at over-end
At over-end boundary (n.0 ov), this_over circles show an older over's tokens instead of either blank or the just-completed over. Likely over_mgr.this_over not clearing at rollover, or UI reading from stale cached field.

### Issue 4 (minor) — partnership balls still -1
b858dd5 added partnership increment to synth credit walk but it's not firing. Likely `self.partnership` is None at synth invocation time, guarded check skips silently. Investigation needed on initialization order.

## Groq TPM / rate-limit work

### Current state
- **Short prompt default**: SCOUT_PROMPT_SHORT is default since 2026-05-12. Verbose requires `SCOUT_PROMPT_MODE=verbose`.
- **Track 1 in-call retry** (5e4ff8a): single retry on 429 with parsed reset duration. Trace tags SCOUT-RETRY-IN-CALL-{QUEUED,SUCCESS,EXHAUSTED}.
- **Track 2 retry buffer** (3a0a4f8): ring capacity 3, 5s staleness. SCOUT-RETRY-{QUEUED,SUCCESS,EXHAUSTED,BUFFER-OVERFLOW}.
- **Shadow-mode dedup** (a5487c2): env-gated `SCOUT_DEDUP_SHADOW=1`. phash on score-block ROI, threshold T=6, 10s TTL. Observability only — no skipping. SCOUT-DEDUP-SHADOW trace tag with `would_skip` flag.
- **Anti-hallucination digits-veto** (625e397, tightened in af7d32d): vetoes STRIP block when scout classifier reports digits=false AND score >= 10. Single-digit cold-start strips bypass.

### Multi-provider exploration (all failed for primary route)
- **Kimi K2.6 (Fireworks)**: median 2442ms latency (2.4× Groq), failed cam classification 3/5. Defer.
- **Cerebras Llama 4 Scout**: 404 on multimodal IDs. Account doesn't have access. Not viable for this account.
- **Gemini 2.5 Flash**: median 5164ms latency (5.1× Groq). Defer.

Conclusion: no hosted multimodal provider clears 2× Groq latency at current SCOUT_PROMPT_SHORT size. Multi-provider router not pursued for tonight.

### Frame source robustness
- **H.264 decoder fix** (4c58a82): added `-bsf:v dump_extra` + `-force_key_frames` on sender; `-vsync cfr` on receiver; promoted ffmpeg stderr to WARN; UDP-STREAM-FROZEN telemetry. Fixed the 376 fps frozen-composite-frame anomaly that was making Scout receive corrupted frames.
- **Frame age instrumentation**: env-gated `UDP_FRAME_AGE_DEBUG=1`. Logs `[FRAME-AGE] frame_id age_ms producer_qsize consumer_lag_ms`.

### Crop / dedup prototypes (validated, decided against)
- **Bottom-50% crop**: hit rate < 5%, classifier accuracy drops on shot/bowlers_end frames. Defer.
- **Tight ROI dedup (score block phash)**: hit rate 23.3% at threshold 6, FP rate 0%. Below 30% target but bimodal distribution. Shipped in shadow mode (a5487c2). Decision pending audit data.

### Architectural follow-ups (post-validation)
- BED consolidation: BED should be subsumed into SM as internal helper or removed entirely. Currently emits parallel events.
- Multi-key Groq rotation: deferred. 5 client sites would need shared key-pool abstraction.
- Local VLM (Qwen2.5-VL on MLX): post-match exploration.
- Queueing mechanism with priority lanes: deferred until trace data justifies (SCOUT-RETRY-IN-CALL-EXHAUSTED count is the trigger).

## Replay files

Recordings live at `~/Projects/SportsComm/files/logs/deliveries/<session_id>/match_<session_id>.{mp4,ts}`.

Validation baseline:
- `20260508_191946/match_4621b9f8.mp4` (9.3G) — DC vs KKR (match 152064). Streamed from 10:40 mark (pre-match starts before that). Used for all today's validation cycles.
- Cricbuzz IDs: `CRICBUZZ_MATCH_ID=152064`, `CRICBUZZ_MATCH_SLUG=dc-vs-kkr-51st-match-indian-premier-league-2026`.

Other available:
- `20260510_201650/match_9f4f588c.mp4` (5.8G)
- `20260510_191741/match_80bbdfa5.mp4` (4.4G)
- `8df9ceb8/match_8df9ceb8.mp4` (3.5G)
- `6ff41b76/match_6ff41b76.mp4` (1.0G) — prior MI-RCB baseline (replaced by 4621b9f8)

## Launch sequence

```bash
cd ~/Projects/SportsComm

# Clear stale state
rm -f files/match_state_cache.json logs/openscout-local_*.jsonl
rm -f /tmp/pipeline.log /tmp/stage_trace.jsonl

# UI (terminal A)
cd scorecard-ui && npm run dev    # localhost:3000

# Pipeline (terminal B)
cd ~/Projects/SportsComm
export FRAME_SOURCE=udp
export FRAME_SOURCE_UDP_URL='udp://0.0.0.0:9999?fifo_size=10000000&buffer_size=2097152&overrun_nonfatal=1'
export FRAME_SOURCE_UDP_ALLOWED_DIMENSIONS='1920x1080,1280x720'
export CRICBUZZ_MATCH_ID=152064
export CRICBUZZ_MATCH_SLUG=dc-vs-kkr-51st-match-indian-premier-league-2026
export BMF_SESSION_ID="validate_$(date +%Y%m%d_%H%M%S)"
export USE_OPEN_SCOUT=0    # Track 2 disabled
export SCOUT_PROMPT_MODE=verbose
export SCOUT_RAW_DUMP=1
export PYTHONUNBUFFERED=1
export SCOUT_DEDUP_SHADOW=1    # observability only
export SKIP_PREMATCH_S=0
/Users/anmolmohan/opt/anaconda3/bin/python files/test_pipeline.py 2>&1 | tee /tmp/pipeline.log
# venv: anaconda, NOT .venv/

# Stream (terminal C, after pipeline reports ready)
ffmpeg -re -ss 00:10:40 \
  -i ~/Projects/SportsComm/files/logs/deliveries/20260508_191946/match_4621b9f8.mp4 \
  -c copy \
  -map 0 -f mpegts "udp://127.0.0.1:9999?pkt_size=1316"
```

UI: http://localhost:3000

## Validation acceptance criteria

Bowler stats:
- bowling_card[name].runs/balls/wickets match broadcast at over-end
- Returning bowler resumes existing card (RESUMED trace fires)
- No two consecutive overs by same bowler (CONSECUTIVE-OVER-BOWLER-REJECTED)
- Wicket in between-overs gap credits to next bowler within 10 frames

Batter stats:
- batting_card[name].runs/balls_faced/4s/6s match broadcast
- No phantom 4s/6s on wrong batter
- Striker green dot tracks broadcast `>` indicator
- New batter at wicket creates fresh card (CREATED), not RESUMED

This_over and recent_overs:
- All 6 ball tokens reflect what was bowled (no `?` placeholders during normal play)
- MULTI_BALL gaps distribute realistically (boundary at end, not even-split)
- Cold-start over 1 first ball shows `.` not `?`
- Recent overs archive correct tokens at all positions

Score progression:
- Score/overs/wickets advance with broadcast (no freezes, no jumps)
- Innings transition: state resets cleanly
- batting_team LOCKED within 30s of first live strip
- 0 false `[BATTING_TEAM-FLIP]` after LOCKED
- 0 false `[INNINGS-2-TRANSITION]`
- Mean lat_total < 4s
- Scorer JSON parse failures < 5%

## Key trace tags introduced today (audit signals)

| Tag | What it indicates |
|---|---|
| EVENT-BASELINE-SEEDED-WARM-INITIAL | SM event baseline seeded at COLD→WARM exit |
| EVENT-BASELINE-RESET-INNINGS-2 | Baseline reset at innings transition |
| SM-EVENT-DELTA-FROM-PREV | Persistent baseline computed d_score differently from naive self.score |
| COLD-START-SYNTHESIZE | Cold-start gap synth fired with N implied balls |
| COLD-START-SYNTH-CREDITED | Synth credit walk applied to bowler/batter cards |
| COLD-START-PHYSICS-PROMOTE | Forward-legal cold-start transition promoted to WARM |
| GAP-TOKEN-INFERENCE | infer_gap_tokens called with N balls / M runs |
| MULTI-BALL-DERIVATION-EXPANDED | Bowler credit per ball via gap-token decomposition |
| MULTI-BALL-BATTER-DERIVATION-EXPANDED | Batter credit per ball via gap-token decomposition |
| ABSORBED-LEGAL-BOWLER-CREDITED | WARM MULTI_BALL ABSORBED_LEGAL credit (7d1ddbf) |
| BOWLING-CARD-CREATED / RESUMED | Tracker LOCK; new vs returning bowler |
| BATTING-CARD-CREATED / RESUMED | Striker/non-striker tracker LOCK |
| BOWLER-OVERRIDE-PENDING / FIRED | Bowler change consensus accumulation |
| BOWLER-ATTRIBUTION-FROZEN | Credits frozen during override-pending |
| BOWLER-ROW-JUNK-REJECT | Bowler row violates physics (wickets > 1 per ball) |
| WICKET-PENDING-BOWLER-ATTRIBUTION | F381 wicket queued for next bowler |
| WICKET-BACKFILLED-TO-BOWLER | F381 wicket credited on next bowler LOCK |
| CONSECUTIVE-OVER-BOWLER-REJECTED | Same bowler attempted on consecutive overs |
| BOWLER-MAIDEN-CREDITED | Over closed with 0 bowler-runs |
| EXTRA-FABRICATION-REJECTED-NO-WITNESS | extras-witness required for multi-run wide |
| STRIP-HEAD-JOINT-POP | Atomic strip-head reject (score/overs/wkts together) |
| STRIP-HEAD-TEAM-TOKEN-MISMATCH | Strip prefix doesn't match batting team |
| STRIP-HEAD-FORWARD-BALLS-NO-SCORE-POP | Implausible forward overs jump without score corroboration |
| GRAPHIC-FILTER-PASS / POISON | Plausibility gate verdict on GRAPHIC→SCOREBOARD transition |
| GRAPHIC-HAS-STRIP-ROUTED-HYBRID | GRAPHIC frame with visible strip routed through hybrid path |
| BROADCAST-OVERRIDE-VETOED-TEAM-MISMATCH | this_over_broadcast override vetoed on cross-team |
| SCORER-DISMISSAL-VETOED-* | Wrong-batter dismissal vetoed (SM authoritative) |
| APPLY-KNOWN-WICKET-IDEMPOTENT-NO-OP | Duplicate wicket write skipped |
| TRACKER-SWAP-MIRRORED | Striker swap synced to _inn |
| STRIKER-TRACKER-UNLOCK-ON-DISMISSAL | Dismissed batter's tracker unlocked |
| STRIKER-OVER-END-DOUBLE-ROTATION-APPLIED | rotation_net=cancel when last ball odd-run + over-end |
| STRIKER-BROADCAST-CORRECTION | Broadcast `>` overrode pipeline rotation (Option 2 trigger) |
| SCOUT-DIGITS-FALSE-STRIP-VETOED | Anti-hallucination guard fired |
| DIGITS-VETO-SKIPPED-LOW-SCORE | Veto suppressed for score<10 cold-start |
| SCOUT-RETRY-IN-CALL-* | Track 1 429 retry (queued/success/exhausted) |
| SCOUT-RETRY-* | Track 2 (openscout) retry buffer |
| SCOUT-DEDUP-SHADOW | Shadow-mode dedup observation |
| UDP-STREAM-FROZEN | Frozen-frame anomaly detected |
| DERIVATION-STRIP-DIVERGENCE-BOWLER / BATTER | Audit signal for derived vs observed |

## What NOT to touch

- `files/eyes/confidence_tracker.py` — battle-tested, foundational
- `files/score_manager.py:_synthesize_cold_start_ball_events` — heavily-iterated, fragile
- `files/cricket_rules.py:infer_gap_tokens` — used at 5+ call sites
- `files/test_pipeline.py:_handle_warm` event-delta order-of-ops — option 2 fix lives here
- Any of today's commit chain without reading the full design spec first

## Style notes for next session

- See `CLAUDE.md` for response style (no preamble, decisive, diff-only code, max 5 tool calls per task)
- User pushes back hard when conservative or wrong. Listen, verify, push forward.
- Architecture principles user repeatedly enforces:
  - "Detection establishes identity, derivation maintains state"
  - "SM is the final authority on the UI; everything else should not have a say"
  - "Once high confidence reached, LOCKED — only explicit events unlock"
  - "Real-time first, no offline-only solutions"
  - "Consolidate and validate together" — minimize ping-pong validation cycles

## Next session's first action

1. Read CLAUDE.md
2. Read this HANDOFF.md (you're reading it)
3. Read `files/docs/investigations/derivation_only_stats_design.md`
4. `git log --oneline derive-not-detect | head -40` for today's commit chain
5. Paste the 4-issue investigation prompt (from previous chat tail) into CC
6. Once CC reports, batch fixes into one consolidated commit
7. Validate again on 4621b9f8 from 10:40

If the chat history isn't available, the 4 pending issues are documented above — paste the relevant section as the CC investigation prompt directly.

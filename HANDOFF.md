# Handoff — Session continuation document

**Last update**: 2026-05-13 (current session in progress)
**Match tonight**: yes, run LOCALLY on Mac (no server deploy until Track 1 + Track 2 validated end-to-end on local)
**Branch**: `derive-not-detect`

This document is the entry point for the next Cowork session. Read this first, then `CLAUDE.md`.

## TL;DR — Where we are

End-to-end cricket broadcast analysis pipeline. Today we rebuilt the detection architecture from "every-frame re-read with hard locks" to "ConfidenceTracker accumulating evidence, LOCKED state prevents flips until explicit unlock event." 30+ commits today. Track 1 (state derivation) close to ready. Track 2 (clip extraction) not yet re-enabled. Server deploy deferred.

The pipeline now reliably:
- Detects batting team correctly (LOCKED on MI, doesn't false-flip during recap/timeout)
- Identifies striker/non-striker/bowler from broadcast strip
- Derives score progression cleanly (40+ commits/run on 10-min replay)
- Mean per-frame latency ~2.7s
- 0% Scorer JSON failures (was 89%)
- 0 false innings-2 transitions

Still broken or in-progress:
- **Bug 6 root cause**: bowler tracker doesn't unlock cleanly at strategic timeouts — stale bowler stays committed, runs/overs from new bowler attributed to old one. **In progress.**
- **Bug 5**: wide fabrication — `WD` tokens appear in this_over even when broadcast didn't have a wide. Cumulative extras count leaks into per-ball events. **In progress.**
- **Bug 4**: this_over `?` placeholders during score-delta-without-strip-token frame. Cosmetic. **In progress.**
- **Bug 8**: striker green-dot inverts occasionally. Deferred — needs live frame trace.

## Core design methodologies

### 1. ConfidenceTracker (file: `files/eyes/confidence_tracker.py`)

Unified evidence-accumulation pattern across all detection layers. Replaces ad-hoc N-frame consensus + hard-lock machinery.

```
TENTATIVE → PUBLISHABLE → FIRM → LOCKED (one-way) → IMMUTABLE (one-way, innings-2 only)
```

Per-entity tracker. Each frame's observation feeds `tracker.update(value, weight)`. Confidence accumulates with exponential decay. Tier transitions happen when thresholds crossed. LOCKED is one-way — only explicit `unlock_and_reset()` releases it. IMMUTABLE is for innings-2 batting team (truly never flips).

Thresholds (current):
- `batting_team`: PUBLISH=2.0, FIRM=5.0 → auto LOCKED. Half-life 60s.
- `striker/non_striker`: PUBLISH=1.5, FIRM=3.0. Half-life 20s (CURRENTLY OBSERVATION-STARVED — see below).
- `bowler`: PUBLISH=1.5, FIRM=3.0, half-life 30s. LOCKED on FIRM. Unlocks on over-end.

Unlock triggers (each in score_manager.execute_innings_change or the dismissal/over-end hook):
- `batting_team`: innings-2 detected → `unlock_and_reset()` + `set_immutable(other_team)`.
- `striker`: dismissed batter == striker → `unlock_and_reset()`.
- `non_striker`: dismissed batter == non_striker → `unlock_and_reset()`.
- `bowler`: over-end event → `unlock_and_reset()`. **BUG: this doesn't fire reliably during strategic timeouts.**
- striker/non-striker swap on odd runs: NOT an unlock — `swap_with()` exchanges leader values, both stay LOCKED.

### 2. Detection vs Derivation

The architectural principle pushed by user repeatedly:
- **Detection**: establishes high-confidence identity (team name, batter name, bowler name)
- **Derivation**: maintains stateful values (runs accumulated, balls faced, partnership) from ball events

Once a value has been established with high confidence, only DERIVATION can change it. Strip detection is input to ball-event detection, not source of truth for derived stats. This protects against stats graphics / recap frames showing different numbers from real state.

Currently enforced (see commit `f043c5d` derivation invariants):
- `partnership.runs / .balls`: only ball events update
- `this_over.tokens`: only ball events append
- `batting_card[name].4s / .6s`: only ball events increment
- `batter.runs / .balls_faced`: strip wins ONLY if monotonically >= derived
- `bowler.overs`: should be strip-authoritative (in progress — Bug 6 root cause)

### 3. Hard cricket invariants

Enforced regardless of detection signal:
- `at_the_crease` array max 2 batters with `status="batting"` (commit `def2c0f`)
- Score monotonically non-decreasing
- Overs monotonically non-decreasing
- Wickets monotonically non-decreasing (max 10)
- batting_team LOCKED can only flip via innings-2 explicit trigger

### 4. GRAPHIC-FILTER scope

Frames classified as graphic / ad / replay / strategic-timeout suppress ALL state-derivation signals from that frame, not just score (commit `6d6492e`). Includes tracker observations, batter/bowler stat updates, this_over appends. Only SCOREBOARD-tagged frames contribute to state.

### 5. Recap/off-roster gate

When extracted batters resolve to off-roster names (e.g. Faf du Plessis from a recap of past match), the frame is non-live and ALL state-derivation signals from it are suppressed (commits `c5c4792`, `cf80dd8`-area code). Implementation: `cold_start_off_roster_batters` filter at the strip-commit boundary.

## File paths (the ones you'll actually open)

```
files/test_pipeline.py             # Main pipeline (~12K lines). entry point.
files/score_manager.py             # State machine (~3K lines)
files/scoreboard.py                # batting_card / bowling_card / squad resolution
files/eyes/confidence_tracker.py   # ConfidenceTracker class + 31 unit tests
files/eyes/vision.py               # SCOUT_PROMPT (verbose) and SCOUT_PROMPT_SHORT
files/eyes/agent.py                # Extractor (LLM-based)
files/eyes/match_state.py          # Scorer (LLM-based, response_format=json)
files/eyes/extract_regex.py        # Regex-primary Extractor + alternate-format fallback
files/eyes/open_scout.py           # OpenScout VLM prompt (clip detection)
files/eyes/open_scout_classify.py  # Rule-based classifier for OpenScout output
files/eyes/udp_frame_source.py     # UDP MPEG-TS frame source w/ watchdog
files/eyes/openscout_persistence.py # logs/openscout-<sid>.jsonl sidecar writer
files/eyes/capture/                # frame source implementations
files/scripts/extract_live_clips_chunk.sh  # Track 2 clip extractor (60s loop)
files/scripts/stream_to_server.sh         # Mac UGREEN dual-UDP sender (live capture)
files/scripts/stream_to_server_test.sh    # Mac file replay dual-UDP sender
scorecard-ui/app/page.tsx          # Main UI (live, scorecard, field, comm, clips, logs)
scorecard-ui/app/deliveries/page.tsx # Clip verification UI
scorecard-ui/app/logs/page.tsx     # Log tail viewer
scorecard-ui/app/api/deliveries/route.ts # Clips listing endpoint
scorecard-ui/app/api/logs/route.ts # Log tail endpoint
scorecard-ui/app/components/BattingCard.tsx # at-the-crease table (green dot logic)
files/tests/test_confidence_tracker.py # 31 unit tests for ConfidenceTracker
deploy/systemd/*.service           # pipeline, recorder, live-clips, ui services
deploy/Caddyfile                   # reverse proxy + /clips /server-logs /scout static
deploy/deploy.sh                   # Server deploy script
.github/workflows/deploy.yml       # CI: WIF auth → IAP SSH → git reset --hard → deploy.sh
```

## Today's commit chain (`derive-not-detect`)

Read with `git log --oneline derive-not-detect` for full list. Key commits in order:

```
42a75c7  Scorer response_format=json_object        # killed 89% JSON parse failures
77f3f7b  drop batting_team-None gate               # observations flow every frame (#64)
c5c4792  cold-start off-roster gate (DEFERRED)     # recap frames don't commit team
d60ed55  three per-entity trackers + WS-PROMOTE comment-out
f810cf8  defer team_abbr cache until committed
ae2b5d7  broadcast_abbr corroboration-only
cbeaeeb  LOCKED state + auto_lock_on_firm (batting_team)
544e70d  LOCKED for all four trackers + swap_with + unlock_and_reset
30ef80f  PROMOTE allowlist includes LOCKED
9094492  #66 extractor alternate-format VISIBLE_TEXT fallback
7557fb3  #63 innings-2 tracker reset + 5 IMMUTABLE unit tests
395b537  #4 over-transition recent_overs migration fix
060e963  #3 batter stats propagation
0babccc  #3 batter stats follow-up
7a3ec26  #7 top-strip non_striker field-name fix
def2c0f  hard cap on at-the-crease max 2
6d6492e  GRAPHIC-FILTER extends to all state signals
f043c5d  derivation-only invariants (monotonic stats)
83df630  bug 6 regex fix (bowler runs)
397a07c  bug 6 tracker-unlock-gate (partial — still failing at timeouts)
cefc595  #66 tuning
```

In-progress now: Bugs 6 root cause, 5, 4.

## Pending bugs ranked by impact

| # | Description | Status | Impact |
|---|---|---|---|
| 6 root | Bowler tracker doesn't unlock at strategic timeouts | In progress | Stale bowler stays committed |
| 5 | Wide fabrication in this_over | In progress | Visible wrong tokens |
| 4 | this_over `?` placeholder | In progress | Cosmetic |
| 8 | Striker green-dot inversion | Deferred (needs live trace) | Cosmetic |
| 7 (resolved) | Batter balls drift | Fixed via `f043c5d` | — |
| N/A | striker/non_striker tracker observation starvation | Not blocking (manual env-var anchor used) | Striker/non don't reach LOCKED in some recordings |

## How to run locally for tonight's match

```bash
cd ~/Projects/SportsComm

# Clear stale state
rm -f files/match_state_cache.json logs/openscout-local_*.jsonl
rm -f /tmp/pipeline.log /tmp/stage_trace.jsonl

# UI (terminal A)
cd scorecard-ui && npm run dev    # localhost:3000

# Local recorder (terminal B)
ffmpeg -y -hide_banner -loglevel warning -fflags +genpts -err_detect ignore_err \
  -i "udp://0.0.0.0:9998?fifo_size=10000000&overrun_nonfatal=1" \
  -c copy -f mpegts ~/local-recordings/match_local_$(date +%H%M%S).ts

# Local pipeline (terminal C)
export FRAME_SOURCE=udp
export FRAME_SOURCE_UDP_URL='udp://0.0.0.0:9999?fifo_size=10000000&buffer_size=2097152&overrun_nonfatal=1'
export FRAME_SOURCE_UDP_ALLOWED_DIMENSIONS='1920x1080,1280x720'
export CRICBUZZ_MATCH_ID=<tonight_match_id>
export CRICBUZZ_MATCH_SLUG=<tonight_match_slug>
export BMF_SESSION_ID="local_$(date +%Y%m%d_%H%M%S)"
export USE_OPEN_SCOUT=0    # Track 2 disabled — only enable AFTER Track 1 validated
export SCOUT_PROMPT_MODE=verbose
export SCOUT_RAW_DUMP=1
export PYTHONUNBUFFERED=1
export SKIP_PREMATCH_S=0
/Users/anmolmohan/opt/anaconda3/bin/python files/test_pipeline.py
# venv path: anaconda, NOT .venv/

# Mac sender (terminal D — when broadcast begins, point at capture device or screen)
# For recording replay:
ffplay -autoexit -fflags +nobuffer -flags low_delay <recording.mp4> &
sleep 0.5
ffmpeg -re -i <recording.mp4> \
  -c:v libx264 -preset veryfast -tune zerolatency -b:v 6M \
  -c:a aac -b:a 128k \
  -map 0 -f mpegts "udp://127.0.0.1:9999?pkt_size=1316" \
  -map 0 -f mpegts "udp://127.0.0.1:9998?pkt_size=1316"

# For live UGREEN capture: scripts/stream_to_server.sh (modify SERVER_IP to 127.0.0.1)
```

Browser tabs:
- http://localhost:3000/ (main UI)
- http://localhost:3000/deliveries (clips — only useful when Track 2 enabled)
- http://localhost:3000/logs (log tail)

## How to validate

10-min replay test recording: `~/Projects/SportsComm/files/logs/deliveries/6ff41b76/match_6ff41b76.mp4` (37 min MI-RCB recording, starts mid-innings at MI 74-3 8.5)

Match ID/slug for this recording:
- `CRICBUZZ_MATCH_ID=152097`
- `CRICBUZZ_MATCH_SLUG=rcb-vs-mi-54th-match-indian-premier-league-2026`

Validation acceptance criteria (current baseline):
- `batting_team` reaches FIRM/LOCKED on MI within ~30s of first live strip
- 0 false `[BATTING_TEAM-FLIP]` after LOCKED
- 0 false `[INNINGS-2-TRANSITION]` (pre-existing bug `pending_target` from stats graphics)
- Mean `lat_total` < 4s
- Scorer JSON parse failures < 5%
- 429 cascade count < 5
- Score progression: ≥ 14 distinct tuples in 10 min
- bowler tracker unlocks on over-end (~2-3 unlocks per 10-min replay)

## Session data lookup

This session's chat history is the source of truth for context. If next session needs to look up:

- **Exact diagnostic outputs**: search Cowork session history for "T+", "T+1", "T+5", "T+10" — those are the validation checkpoint reports
- **Commit messages**: `git log --all --oneline derive-not-detect` shows full history; each commit message documents the fix shipped
- **Bug numbering**: bugs #1-#8 are session-internal references (not in tracker), refer to them by description not number
- **Task tracker IDs**: see #59-#69 for the ConfidenceTracker work, #45-#51 for the phase-1-6 work, #11/#14/#37/#42/#43/#44/#52/#53/#54 are still-pending older items
- **Diagnostic methodology**: when a bug is reported, the playbook is (a) frame trace (extract specific frames at moment of failure), (b) grep pipeline.log around that timestamp, (c) identify whether bug is upstream signal or downstream state-machine, (d) propose targeted fix, (e) validate same recording before commit

## Operations cheat sheet (when something breaks during live match)

1. **UI shows stale data** — check `match_state_cache.json` mtime; if recent, pipeline is committing wrong values (state-derivation bug). If old, WS connection problem (UI cache).
2. **Pipeline crash-loops** — `tail /tmp/pipeline.log`, look for traceback.
3. **No state at all** — verify Mac sender is streaming (`lsof -i :9999`), pipeline is reading frames (grep "F[0-9]" in log).
4. **Stats wrong but identity correct** — derivation issue (not detection). Check whether strip detection is overriding derived values; should be derivation-authoritative for stateful fields.
5. **Strategic timeout corruption** — verify GRAPHIC-FILTER firing for timeout frames. If not, frame classifier missed them — diagnose with raw scout response.
6. **Track 2 clip generation** — `USE_OPEN_SCOUT=1` env var required. live-clips.sh polls every 60s. Recorder ffmpeg writes the `.ts` archive.

## Style notes

- See `CLAUDE.md` for response style rules. Decisive, no preamble, diff-only code.
- User pushes back hard when conservative or wrong. Listen, verify, then push forward.
- Architecture principles user repeatedly enforces:
  - "Make cricbuzz obsolete" — pipeline detects everything from broadcast, only squad+team names come from cricbuzz
  - "Detection establishes identity, derivation maintains state"
  - "Once high confidence reached, LOCKED — only explicit events unlock"
  - "Real-time first, no offline-only solutions"

## Files to NOT touch tonight

- `files/eyes/confidence_tracker.py` (battle-tested, 31 unit tests, foundational)
- `files/test_pipeline.py` line 11765 area `set_innings_2()` (pending_target gate is fragile — needs the chase-signature precondition the prior session designed but didn't ship; if Bug "false innings-2" reappears, that's the fix to land)

## Next session's first action

Pull these into context:
1. Read CLAUDE.md
2. Read this HANDOFF.md (you're reading it)
3. `git log --oneline derive-not-detect -30` to see today's commits
4. Check `/tmp/pipeline.log` if a run is in progress
5. Ask user what state they want to resume from

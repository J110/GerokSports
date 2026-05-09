# P12 — Innings transition hardening diagnosis

Match: CSK vs MI 44th, IPL 2026 (innings 2), 2026-05-02
Log: `logs/pipeline-2026-05-02-2049-csk-vs-mi-44th-match-ipl-2026-innings2.log`
Reset marker: `[SM-INNINGS-2-RESET]` at line 10814, F647 21:31:42 (overs_complete_20, target=160).
First real CSK score commit (innings-2 score moves >0): F864 21:45:56 (`[SM] cold-start candidate seeded 9/0 (7.0)` line 13638). Wall-clock gap = 14 min 14 s, 217 frames.

(All line numbers reference the log above unless stated otherwise.)

---

## §1 — 14-minute window timeline (F647 → F864)

Scout tag distribution between F647 and F864 inclusive (76 processed frames; gaps are NON_LIVE/AD frames that Scout suppressed before the TEST handler — F647→F864 spans 217 raw frames so ~141 were silently filtered as commercials/replays):

| Tag | Count | Frames |
|---|---|---|
| SCOREBOARD | 65 | F647, F651–F657, F662, F668–F669, F672, F716, F736, F742–F748, F765–F768, F772, F776, F781–F782, F786–F799, F803–F806, F808–F810, F812–F814, F816–F818, F826–F828, F839–F845, F848–F853, F857–F861, F863–F864 |
| GRAPHIC | 11 | F648, F649, F650, F658, F707, F755, F756, F769, F770, F807, F815, F856, F858 (lines 10834, 10861, 10885, 11023, 11275, 11550, 11557, 11685, 11711, 12504, 12689, 13396, 13446 — 13/76) |

(Counts above are tag-of-record after re-reads; Scout's first-pass tag matches.) Phase distribution skews `between_play` and `closeup` — only 8 SCOREBOARDs land on `bowlers_end/release` (typical live-action ball-in-flight), the rest are `closeup/between_play` (replays, batter close-ups, presenter shots).

Sub-windows (grouped by behaviour):

- **F647–F657 (21:31:39–21:32:31, ~52 s) — innings-1 strip residue + GRAPHIC overlays.**
  - F647 STRIP `null 49-3 (8.1) | *BOULT 21(19) | BHAGAT 25(20) | PATEL 2-20 (3.1)` (line 10801) — that's an innings-1 mid-state replay (Boult 21, Bhagat 25, Patel bowling), not innings-2 live.
  - F648, F649, F650 GRAPHIC `null null-null (null)` (lines 10838, 10865, plus F650 implicit) — full-screen end-of-innings or transition graphic; GUARD prints `GRAPHIC frame — player stats stripped, score mismatch → poisoned (score fields cleared)` (lines 10849, 10874).
  - F651 STRIP `null 89-3 (6.4) | Ruturaj Gaikwad 38(29) | Sanju Samson 15(21) | Will Jacks 1-37 (3.4)` (line 10892) — phantom **CSK 89/3 at 6.4 with Will Jacks bowling**, i.e. a Mumbai-Indians-vs-CSK *projection/scenario graphic* (Will Jacks isn't even MI XI in this match).
  - F652–F657 STRIP all `null null-null (null)` — between-overs analytics frames.

- **F662 (21:33:07) — PBKS phantom recap.**
  - STRIP `null 96-3 (5.4) | *K.L.Rahul 29(21) | A.Garg 17(13) | A.Kishore 1-14 (3)` (line 11036). 27 squad-mismatch warnings fire at lines 11045–11115 for `K.L.RAHUL / A.GARG / A.KISHORE` — those are **Punjab Kings players** (a different match recap inset / PBKS–MI head-to-head card). This is unambiguously not live CSK action.

- **F668–F669, F672 (21:33:40–21:34:08) — more analytics + PBKS-style residue.**
  - F668/F669 strip `null null-null (null)` (lines 11136, 11159).
  - F672 STRIP `null 96-4 (7.5) | *Rahul 29(21) | Karun 19(23) | Bumrah 2-29 (4)` (line 11185); GUARD blocks score correction `0→96 delta=96` (line 11221). "Karun" no-match warnings (line 11193+) — this is a *projected target / pressure graphic* that mixes player names.

- **F716 (21:35:17) — Chahar phantom.** STRIP `null 47-3 (null) | *Chahar 20(18) | Karun 5(7) | Bumrah 1-15 (3.2)` (line 11289). "47-3 (3.2)" is the canonical phantom seen across this whole window (innings-1 final-projection graphic that Sony/Star is showing).

- **F736–F748 (21:36:27–21:37:37, ~70 s) — sustained "47-3 (3.2) Chahar/Bumrah" phantom.**
  - F742 STRIP `null 49-3 (null) | *Rahul Chahar 20(18) | NonStriker 5(7) | Jasprit Bumrah 1-15 (3.2)` (line 11386).
  - F745 same numbers, bowler again Bumrah (line 11471).
  - F748 same canonical 47-3 / Chahar / Bumrah phantom (line 11511). Score-correction GUARD rejects each: lines 11434, 11495, 11531.
  - F743 ACTION (line 11463) `"player is celebrating with their raised arms"` — i.e. innings-1 highlight reel.
  - F748 ACTION (line 11538) `"A cricketer is walking off the field while another person is talking to him."` — interview/post-innings analysis.

- **F765–F799 (21:38:20–21:40:33, ~2 min 13 s) — toggling between phantom recap and the very first CSK live frames.**
  - F765–F770 mix of `null null-null` and `47-3 / 49-3` recap residue (lines 11569, 11593, 11632, 11663–11715).
  - **F781 (21:39:18, line 11796): first STRIP whose payload looks like real CSK innings 2: `null 9-0 (3.1) | extras=null | this_over=◉◉◉◉. | Ruturaj Gaikwad* 0(0) | Rahul Chahar 1(1) | Jasprit Bumrah 0-9 (3.1)`.** But it has wrong over (3.1), wrong non-striker (Chahar isn't opening for CSK), and wrong dot pattern. Score-correction GUARD blocks `0→9` (line 11826).
  - F782 reverts to phantom 47-3/Bumrah (line 11839).
  - **F787 (21:39:38, line 11912): first STRIP with team='CSK' and team-code populated: `CSK 0-0 (0) | >Samson Gaikwad 0(0) | Rahul Chahar null(null) | Boult 0-0 (0)`** — combo of correct opening pair (Samson, Gaikwad) plus phantom Chahar.
  - F790–F791 first stable `CSK 1-0 (0.1) | Samson 1(1) | Gaikwad 0(0) | Boult 0-1 (0.1)` (lines 12039, 12075).
  - F798–F799 still oscillates back to `null 47-3 (null) | GAIKWAD 14(9) | RAHUL 15(13) | BOULT 3-37 (4)` (line 12268) — projection graphic again. F799 commits a phantom `score: None -> 47` cold-start (line 12328) but it gets reverted later.

- **F803–F818 (21:40:49–21:42:08, ~80 s) — live action stabilising but still interleaved with overlays.**
  - Real live frames: F803–F806, F809–F810, F816–F817 all show `CSK 1-0 (0.2)` to `CSK 2-0 (0.4)` (lines 12355, 12391, 12438, 12475, 12524, 12565, 12698, 12724).
  - Overlay frames: F808 GRAPHIC `[CAM-GRAPHIC-FAST-PATH-REJECT] reason=G6_score_window` (line 12512); F812–F814 `null 101-0 / Sanju Samson 101*(54)` projection graphic (lines 12599, 12632); F818 `null null-null (null)` (line 12779).

- **F826–F853 (21:42:28–21:44:54, ~2 min 26 s) — same back-and-forth; phantom 47-3 still surfacing at F826 (line 12813), F853 STRIP `null 77-5 (9.5) | SAMSON 38(29) | GAIKWAD 21(20) | BUMRAH 1-16 (4)` (line 13367) — another forward-projection graphic of CSK score.

- **F856–F863 (21:45:10–21:45:50, ~40 s) — last residual GRAPHIC + phantoms before the lock.**
  - F856 GRAPHIC strip+overlay (line 13396).
  - F860, F861 `null 74-5 (5.5)` and `null 77-3 (7.5)` (lines 13487, 13516) — projection graphics.
  - F863 STRIP `CSK 9-0 (1.3) | Samson 7(6) | Gaikwad 2(3) | null null-null` (line 13550).

- **F864 (21:45:54) — LOCK.** STRIP `CSK 9-0 (7) | Samson 7(6) | Gaikwad 2(3) | null null-null` (line 13606); `[SM] cold-start candidate seeded 9/0 (7.0) — streak 1/3` at line 13638. CSK 9/0 (1.4) becomes the steady locked state from F876 onward (lines 13696, 13748, 13787, 13832, all `score=9-0 (1.4)`).

---

## §2 — Broadcast content analysis (deduced)

Mapping the strip/overlay content to broadcast type:

1. **Innings 1 highlights / boundary recap (F647–F662, F716, F736–F748).** Strip text shows MI players in batting positions (Boult 21(19), Bhagat 25(20), Patel/Bumrah bowling) — innings-1 facts (line 10801 names match MI XI). The "47-3 (3.2) Chahar/Karun" pattern (F716, F742, F745, F748, F767, F782, F799, F826) is the **canonical innings-1 fall-of-wickets recap** (MI lost 3 wickets at 47/3 around the 3.2-over mark; Chahar bowled that spell). This pattern recurs because the recap reel cycles for ~10 min.

2. **Cross-match / projection graphics (F662, F672, F812–F813, F853, F860–F861).** F662 strip names PBKS players (`K.L.Rahul, A.Garg, A.Kishore`, line 11036, 27 no-match warnings) — clearly a **head-to-head / season-stats inset card**. F812 `null 101-0 | Sanju Samson 101*(54)` (line 12599) is a *projected milestone* graphic (Samson is on 0 at this point — "if Samson scores 101…"). F853 `null 77-5 (9.5)` and F860/861 `null 74-5 (5.5) / 77-3 (7.5)` (lines 13367, 13487, 13516) are similar **forecast / required-rate** graphics.

3. **Full-screen analytics / sponsor overlays (F648–F650, F658, F707, F755–F756, F769–F770, F807, F815, F856).** Tagged GRAPHIC by Scout, `has_overlay_stats=true`, strip mostly `null` (lines 10834, 10861, 11023, 11275, 11550, 11557, 11685, 11711, 12504, 12689, 13396). These are presentation/analytics packages.

4. **Pre-toss-style / between-overs filler (F652–F657, F668–F669, F736, F743, F765, F768, F772, F776, F786, F814, F818, F850–F852).** Strip `null null-null (null)` repeated — broadcast on close-ups of dugout, fans, presenter; strip box not rendered or rendered empty.

5. **First true live action.** F781 (21:39:18, ~7 m 36 s after reset) is the first frame whose strip naming pair matches CSK openers; F787/F790 are the first frames where strip team-code = "CSK" with sensible runs/balls; F864 (21:45:54, 14 m 12 s after reset) is the first frame where extractor + tracker agree enough to seed a cold-start commit. ACTION text confirms: F791 `"close-up of a player, likely during a break in play"` (line 12106), F803 `"the Chennai Super Kings batting and the Mumbai Ind…"` (line 12379) — i.e. live action narration only emerges around 21:40:49 (~9 min after reset).

Bottom line: between 21:31:42 and ~21:39:18 the broadcast is **pure post-innings package** (recap reel, head-to-head inset, projection graphics, analytics overlays). Between 21:39:18 and 21:45:54 it's **interleaved live-action + projection/recap graphics** that keep popping the strip back to phantom values.

---

## §3 — Detectable transition signals

Signals available at each frame after `[SM-INNINGS-2-RESET]`:

1. **Frames since reset.** `frame_count - inn2_reset_frame`. F647→F864 = 217 raw frames (Scout-processed = 76). Today the cold-start short-circuit `cold_start_inn2_by_frame = (frame_count <= 20)` (test_pipeline.py:4698) only protects the first 20 frames after match start — not the inn2 reset.

2. **Wall-clock seconds since reset.** `wall_now - inn2_reset_wall`. Window = 854 s. Useful because Scout-frame cadence varies wildly (F662 to F716 jumps 64 s of wall but only ~5 frames; lines 11000→11288 show the gap).

3. **Strip team field.** Team starts as `null` for F647–F786 (every line up to 11883 has `STRIP: null …`). The very first non-null team in window is F787 `CSK …` (line 11912), at +7 m 56 s. **Team-not-null is a necessary (not sufficient) signal**: 11 of 18 post-F787 STRIPs in window still have phantom payloads from projection graphics with team filled in or null.

4. **Consecutive null-team strip reads.** A run of 3+ consecutive `STRIP: null …-… (…)` reads is a strong "still in transition" signal. F647–F657 hits 7 in a row; F668–F786 has multiple 3+ runs.

5. **Score field absent or > sane innings-2 ceiling.** During the window the strip reports scores of 49/3, 89/3, 96/3, 96/4, 47/3, 77/5, 74/5, 77/3, 101/0 — none are plausible early-innings-2 values. A "score ≤ 30 AND wickets ≤ 2 AND overs ≤ 5" gate would have rejected every single one of the recap/projection reads.

6. **Bowler ∉ batting-side opposition XI.** F651 names "Will Jacks" (not in MI XI), F662 names "A.Kishore" (PBKS), F672 names "Karun" (CSK batter, not bowler), F716/F742/F745/F748 name "Chahar" (CSK player, not MI). All would fail an XI-membership check against the latched bowling team's XI (loaded F0, lines 7 + 32).

7. **Striker/non-striker ∈ batting-side XI** — same logic. F662 batters K.L.Rahul + A.Garg are PBKS; would fail CSK XI membership.

8. **Score regression vs locked innings-1 final.** Strip scores 89/3, 96/4, 101/0, 77/5 etc. are *innings-1 territory* (innings-1 final 159/7). They never exceed the innings-1 final, so they look superficially plausible — only context (inn=2, batting team should be CSK with score≈0) reveals them as phantom.

9. **Scout's own frame_phase + camera_view.** 65 of 76 SCOREBOARDs in window are `closeup / between_play` (Preview lines: 10915, 10982, 11001, 11131, 11154, 11348, 11444, 11562, 11658, 11739, 11769, 11790, 11877, 11904, 11953, 12033, 12069, 12109, 12151, 12350, 12385, 12432, 12517, 12665, 12773, 12856, 12891, 12949, 12981, 13069, 13108, 13223, 13274, 13303, 13335, 13447). Only 8 are `bowlers_end/release/post_shot`. A "phase != release/post_shot AND <X min since reset" signal would catch ~85 % of phantom frames.

10. **GUARD-tag fire rate.** During the window, score-correction GUARD blocks fire at F672, F742, F745, F748, F766, F767, F781, F782, F798, F799 (10 frames in 8 minutes). A spike of `CORRECTION_BLOCKED` after an innings reset is itself diagnostic.

The most deterministic combination: **(frames_since_inn2_reset > 0) AND (wall_seconds_since_inn2_reset < THRESHOLD_SEC) AND (no live-action lock yet)** is the gating condition; the *content* gates (score≤30, overs≤5, wickets≤2, players ∈ XI) are the per-frame filters.

---

## §4 — Recommended threshold values

Three options for "in transition window":

- **(a) Pure wall-clock.** `wall_seconds_since_inn2_reset < 600` (10 min). Today's window needed 854 s — even 10 min would have missed the F864 lock by 4 min. **300 s (5 min) is too short** (live action started ~F781 = +7 m 36 s but didn't commit until +14 m 12 s).

- **(b) Pure frame count.** `frames_since_inn2_reset < 200` would catch F647–F846 (~199 raw frames). Trades wall-clock fairness for frame-rate fairness.

- **(c) Hybrid (recommended).** `in_inn2_transition = (frames_since_inn2_reset < 250 AND wall_seconds < 900) OR (no_live_score_committed_yet AND wall_seconds < 1200)`. The second clause is the safety net: stay suspicious until the score actually commits or 20 min elapses, whichever first.

Recommended primary threshold: **`INNINGS_2_TRANSITION_FRAMES = 250` and `INNINGS_2_TRANSITION_SECONDS = 900` (15 min)**, expire-on-first-commit. Make both **configurable env vars** (`INN2_TRANSITION_FRAMES`, `INN2_TRANSITION_SECONDS`) with the defaults above, in the spirit of `USE_OPEN_SCOUT` flags in CLAUDE.md.

Justification for 15 min ceiling: today's window was 14 m 14 s; mi_srh_innings_break_analysis.md (referenced in §A8) reports similar 12+ min windows; we want headroom for pathological breaks (rain, presentation ceremonies). Auto-clear on first commit caps the false-positive cost.

"Early innings 2" content thresholds (apply during the window):
- score ≤ 30
- overs ≤ 5.0
- wickets ≤ 2
- striker AND non-striker ∈ batting-team XI (latched_bat from line 10813)
- bowler ∈ bowling-team XI

These bounds catch all 17 phantom-strip frames in the window evidenced above (49/3, 89/3, 96/3, 96/4, 47/3, 77/5, 77/3, 74/5, 101/0 all fail score≤30; Will Jacks, K.L.Rahul, A.Garg, A.Kishore, "Karun" as bowler all fail XI-membership).

---

## §5 — Recommended hardening rules

When `in_inn2_transition == True`, run all of the following on every SCOREBOARD frame *before* extractor output reaches the tracker / score_manager:

1. **Numeric-bounds gate.** If `score > 30` or `wickets > 2` or `overs > 5.0`, reject the entire row (zero out score/wickets/overs from extractor result and tag `[INN2-TRANSITION-BOUNDS-REJECT]`). Evidence: every phantom strip in §1 fails this.

2. **Bowler XI gate.** If extracted bowler ∉ latched bowling team XI (using the same player_match logic that fires "No match for" warnings, lines 11045+), drop bowler row. Evidence: F716 Chahar, F662 A.Kishore, F651 Will Jacks.

3. **Batter XI gate.** If either batter ∉ latched batting team XI, drop both batter rows. Evidence: F662 K.L.Rahul + A.Garg.

4. **Null-team flush.** During transition, treat `STRIP team=null` AND `score>0` as automatically suspicious — require 2 consecutive corroborating frames before promoting any field. Evidence: every projection-graphic strip in window has `team=null` with score populated.

5. **GRAPHIC tag forced poison.** Already exists (lines 10849, 10874 show `[GUARD] GRAPHIC frame … poisoned`). Confirm rule still fires during transition and extend it to `[CAM-GRAPHIC-FAST-PATH-REJECT]` (line 12512).

6. **Cold-start commit lockout.** Block `[SM] cold-start candidate seeded` when score>0 unless **all** of (numeric-bounds, bowler XI, batter XI, team-not-null) pass for ≥3 consecutive frames. F799 line 12328 shows today's behaviour (commit `score: None -> 47` then back-out) — that round-trip would never start.

7. **Promote `[CORRECTION_BLOCKED]` to a transition-window counter.** When ≥5 `CORRECTION_BLOCKED` events fire within 60 s of an innings reset, log `[INN2-TRANSITION-PHANTOM-STORM]` (advisory) and extend the transition window by 60 s. Evidence: 10 such events between F672 and F799 in this match (165 s window).

These rules are *additive* — they only fire while `in_inn2_transition`, so steady-state behaviour is unchanged.

---

## §6 — Fix proposal & effort estimate

**Files to touch (4):**

1. `files/score_manager.py` (~50 lines).
   - In the `[SM-INNINGS-2-RESET]` block (lines 1998 / 2008), record `self._inn2_reset_frame = frame_idx` and `self._inn2_reset_wall = time.time()`.
   - Expose `score_manager.in_inn2_transition(frame_idx, wall_now) -> bool` using the §4 hybrid rule.
   - In `seed_cold_start_candidate` (the line that emits `[SM] cold-start candidate seeded`, e.g. line 13638), early-return when `in_inn2_transition() and not transition_gates_passed(extractor_row)`.

2. `files/test_pipeline.py` (~80 lines).
   - Replace the existing `cold_start_inn2_by_frame = (frame_count <= 20)` (line 4698) — keep that for match-start, add an analogous `cold_start_inn2_after_reset` driven by `score_manager._inn2_reset_frame`.
   - Add a `_apply_inn2_transition_gates(extractor_row, scorer_output)` helper that runs the 5 content checks (numeric-bounds, bowler XI, batter XI, null-team, GRAPHIC) and returns a poisoned/zeroed copy when in transition.
   - Wire it into the existing GUARD pipeline next to the `[GUARD] GRAPHIC frame …` and `[GUARD] Score correction in Scorer output: …` sites (e.g. lines 11221, 11434, 11495, 11531, 11619, 11648, 11826) — same shape, new tag `[INN2-TRANSITION-…-REJECT]`.
   - Emit `[INN2-TRANSITION-PHANTOM-STORM]` advisory and extend window when ≥5 rejects in 60 s.

3. `files/trace_emitter.py` and `files/analyze_trace.py` (~20 lines each).
   - Add a new decision tag class `INN2-TRANSITION-*` so the analyzer rolls them up under a P10/P11 sibling rule (e.g. P12-A "transition gate fired", P12-B "phantom storm extended window").

4. `files/docs/operations/parallel_scout_setup.md` and/or a small new ops note (~30 lines).
   - Document the env vars `INN2_TRANSITION_FRAMES`, `INN2_TRANSITION_SECONDS`, plus the rollback path (set both to 0 to disable).

**Tests:**
- `files/tests/test_anomaly_rules.py`: add 3–4 fixture cases derived from this match (F647 strip, F716 phantom, F864 lock).
- Replay this match's frames F640–F870 against the new gate and confirm: zero phantom commits, F864 still locks at the right state.

**Effort estimate:** **~1 dev-day** for code + tests, **~½ day** for replay validation across 2–3 prior matches in `logs/` (mi_srh_innings_break, gt_rcb_20260430). Total: **1.5 dev-days.** Aligns with the post-mortem's "P12 ~half day" estimate plus the additional XI-gate plumbing (P11 overlap).

**Risk:** Low. All changes are additive guards behind an env-var gated boolean; auto-clears on first commit so cannot strand the pipeline if thresholds are wrong. Falls back to today's behaviour with `INN2_TRANSITION_FRAMES=0`.

---

## §7 Warm-restart blindness (2026-05-03 SRH-KKR live diagnostic)

Match: SRH vs KKR 45th, IPL 2026, 2026-05-03. Pipeline restarted at 18:02 mid-innings-2 (KKR 79/1 at 7.0, target 166).
Logs: `logs/pipeline-2026-05-03-1802-srh-vs-kkr-RESTART.log` (primary), `pipeline-2026-05-03-1758-…-RESTART.log`, `pipeline-2026-05-03-1808-…-RESTART2.log`.

### §7.1 Symptom

Every post-restart frame got `[INN2-TRANSITION-REJECT] reason=score>30:NN` — the strip read showed legitimate live KKR scores (79, 80, 81, … 90+) which all exceeded the P12 numeric-bounds gate. ScoreManager cached `BEFORE_score=79-1` from the warm-restart relabel but every cold-start seed attempt was blocked by `[INN2-COLD-START-LOCKOUT] reason=score>30`. DETAIL line stayed pinned at `score=79-1 (7.0)` while STRIP advanced through 87/1 (7.4) and beyond. Pipeline could not commit any inn-2 update for the full 1200 s safety-net window.

Concrete log evidence (pipeline-…1802-RESTART.log):
- L210 `F3 [INIT] First-frame initialization complete: 79-1(7.0)` — warm-restart innings-2 detection fires (`test_pipeline.py:9426-9470`, target=166 → `current_innings=2`).
- L383 `F8 [SM-INNINGS-2-RESET] reason=to_win_N_off_M:cold_start_relabel … target=166 new_batting_team=Kolkata Knight Riders` — `score_manager.set_innings_2()` called from `test_pipeline.py:5022-5027` (cold-start relabel path).
- L393 `F8 [INN2-COLD-START-LOCKOUT] proposed seed 79/1 (7.0) rejected — reason=score>30:79`.
- L393–L1541 (and onward): identical lockout repeats every frame (F8, F9, F10, … F108 +) for every score the strip emits (79, 80, 81, 82, 86, 87, 88, 89, 90, 91 …). `[INN2-TRANSITION-REJECT]` from `test_pipeline.py:7613-7625` mirrors the rejection upstream of the scorer.

### §7.2 Root cause analysis

The P12 transition window assumes a **true** innings-1→innings-2 transition: post-innings package, recap reels, projection graphics — a 14-min phantom-storm period documented in §1–§2. The numeric-bounds gate (score ≤ 30, wickets ≤ 2, overs ≤ 5.0) is correct *only* for that scenario, where the real inn-2 score is genuinely ~0/0 (~0.0) and any strip read above those thresholds is by construction phantom.

On a warm restart mid-innings-2 the conditions are reversed:
- The broadcast is in **live action**, not post-innings package (no phantom-graphic storm).
- The strip read is the **ground truth** we want to commit (KKR 79/1 (7.0) is the actual game state).
- Score > 30 is **expected**, not anomalous.

The P12 wire-in (`score_manager.set_innings_2`, `score_manager.py:2058-2070`) does not differentiate between the two callers. It unconditionally records `_inn2_reset_frame = self._current_frame`, `_inn2_reset_wall = time.time()`, `_inn2_first_commit_seen = False`, and sets `mode = "COLD_START"`. From that moment `in_inn2_transition()` (`score_manager.py:2072-2092`) returns `True` via the safety-net branch (`wall_since < INN2_TRANSITION_CEILING_SECONDS = 1200`) for the next 20 minutes — regardless of whether the call was a real transition or a relabel.

Two warm-restart callsites both fall into the trap:
1. `test_pipeline.py:9444-9452` — first-frame init `[INIT] Detected innings=2`, `reason="poison_recal_cold_start"`.
2. `test_pipeline.py:5022-5030` — `[INNINGS-CHANGE] cold-start path: relabelled inn1→inn2`, `reason="{source}:cold_start_relabel"`. **Today's failure went through this path.**

In both cases, the calling code already understands that this is a warm-restart relabel — the scoreboard side carefully *preserves* the existing `_inn` state via `_carry` (test_pipeline.py:5031-5039). Only `score_manager` re-inits to a fresh COLD_START, and once it does, every subsequent seed candidate (which has the legitimate >30 score the relabel was supposed to preserve) is killed by its own bounds gate. The `mark_inn2_first_commit()` lever exists (`score_manager.py:2094-2095`) but only fires *inside* a successful seed (line 1188), so it never fires under lockout. Self-perpetuating.

The 1200 s safety-net branch additionally guarantees the lockout cannot self-clear: even if frames-since-reset and wall-seconds both exceed the primary thresholds (250 frames / 900 s), `safety_net = wall_since < 1200` keeps `in_inn2_transition()` True until 20 min after restart. Today's symptom persisted from F8 through at least F108+ (~6 min in the log excerpt).

### §7.3 Candidate fixes

(a) **Skip transition window on warm-restart callsites.** Add an explicit `warm_restart: bool = False` parameter to `score_manager.set_innings_2`. When `True`, immediately call `mark_inn2_first_commit()` inside the method (or skip `_inn2_reset_frame` capture entirely). Both warm-restart callers (test_pipeline.py:9444, test_pipeline.py:5024) pass `warm_restart=True`; the legitimate transition caller (`_handle_innings_change` → set_innings_2 at score_manager.py:2007) leaves it `False`.
  - **Scope:** ~10 LOC: add param + branch in `set_innings_2`; flip two callsites.
  - **Risk to genuine cold-start lockout:** None. Genuine inn1→inn2 transition routes through `_handle_innings_change` which does *not* set the flag. The 14-min phantom-storm hardening from §5 stays intact for every legitimate transition.
  - **Tests:** add `test_set_innings_2_warm_restart_skips_transition` and `test_set_innings_2_default_keeps_transition`; extend `test_inn2_transition_hardening.py` with a fixture that simulates the warm-restart relabel sequence (init detect → relabel → first frame should commit).

(b) **Detect first-frame innings=2 at startup and short-circuit.** Track whether the pipeline ever observed `current_innings == 1` with progress; if not (i.e., the very first frame already shows inn 2), skip the cold-start lockout entirely.
  - **Scope:** ~30 LOC. Requires a startup-state flag plumbed into `score_manager`.
  - **Risk:** Misses the second warm-restart shape — pipeline that started in inn-1 territory (target undetected) and only later got the `to_win_N_off_M` relabel. Today's bug actually travels via this second shape (relabel fired at F8, not F1), so (b) alone wouldn't fix it without (a) also.
  - Strictly weaker than (a).

(c) **Persist `_inn2_first_commit_seen` across restarts.** Disk-backed state cache.
  - **Scope:** large; introduces a new persistence surface and recovery semantics.
  - **Risk:** stale cache after match-day restarts, schema migration burden. Overkill — the diagnostic signal is already present in the relabel reason.

(d) **Time-based heuristic: if first frame post-`set_innings_2` shows score>30 and `mode=COLD_START`, treat as warm restart and auto-mark first commit.**
  - **Scope:** ~15 LOC inside `_handle_cold_start`.
  - **Risk:** A genuine transition where the broadcast strip flips to a phantom recap with score 47 *immediately* (e.g., F647 in the CSK-MI case) would be incorrectly absorbed as a warm-restart commit. We've documented exactly this pathology in §1 — phantom strips in the first 0–60 s are routine. Heuristic conflates two scenarios with the same surface signal but opposite ground truth.

### §7.4 Recommendation

**Fix (a).** Decisive factor: it consumes the signal the calling code already has (the caller knows it is a relabel — that's why the reason string says so) and leaves the §5 phantom-storm hardening fully intact for the genuine transition path. No new env var, no heuristic, no persistence. Two-line behavioural change in `score_manager.py`, two-line wire-in change in `test_pipeline.py`.

Implementation sketch:

```python
# score_manager.py:2014
def set_innings_2(self, target: int | None = None,
                  batting_team: str | None = None,
                  reason: str = "set_innings_2",
                  archive: bool = True,
                  warm_restart: bool = False) -> None:
    ...
    self._inn2_reset_frame = reset_frame
    self._inn2_reset_wall = time.time()
    self._inn2_first_commit_seen = warm_restart  # ← skip transition window on warm restart
```

```python
# test_pipeline.py:5024  (cold_start_relabel path)
score_mgr.set_innings_2(
    target=derived_target,
    batting_team=batting_team,
    reason=f"{source}:cold_start_relabel",
    warm_restart=True)

# test_pipeline.py:9444  (poison_recal_cold_start path)
score_mgr.set_innings_2(
    target=int(_init_target) if _init_target else None,
    batting_team=batting_team,
    reason="poison_recal_cold_start",
    warm_restart=True)
```

### §7.5 Test coverage plan

Add to `files/tests/test_inn2_transition_hardening.py`:

1. `test_set_innings_2_warm_restart_skips_transition` — call `set_innings_2(warm_restart=True)`, assert `in_inn2_transition()` returns `False` immediately.
2. `test_set_innings_2_default_keeps_transition` — current behaviour must be unchanged: `warm_restart=False` (default) still records `_inn2_reset_frame` and returns `True` from `in_inn2_transition()` within thresholds.
3. `test_warm_restart_score_above_30_seeds_immediately` — fixture: warm-restart `set_innings_2(target=166, warm_restart=True)`, then feed a card `{score:79, wickets:1, overs:7.0}`; assert cold-start consensus advances (no `INN2-COLD-START-LOCKOUT`) and seed commits within `COLD_START_CONSENSUS_FRAMES` matching reads.
4. Replay smoke test (manual or scripted): replay frames F1–F120 of `pipeline-2026-05-03-1802-srh-vs-kkr-RESTART.log` against the patched pipeline; assert ≥1 successful `[SM] cold-start candidate seeded` within the first 30 frames and zero `[INN2-COLD-START-LOCKOUT]` events.
5. Negative regression: replay frames F640–F870 of the CSK-MI inn-2 break log (§1 fixture); assert behaviour unchanged — phantom storm still triggers `INN2-COLD-START-LOCKOUT`, F864 still locks correctly. Confirms (a) does not weaken the genuine-transition guard.

**Effort estimate:** ~½ dev-day total. ~30 min code, ~2 h tests, ~1 h replay validation across both fixtures.

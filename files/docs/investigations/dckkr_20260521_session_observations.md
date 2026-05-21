# DC vs KKR validation session — observed issues (live notes)

**Session.** `validate_dckkr_20260521_070545`
**Trace.** `logs/trace/validate_dckkr_20260521_070545.jsonl`
**Scout dump.** `files/logs/deliveries/validate_dckkr_20260521_070545/scout_raw.jsonl` (expected; verify post-run)
**Status.** Replay still running. Issues noted live for post-replay investigation sweep with Claude Code. No fixes applied; no design memo opened yet.

---

## Issue 1 — Bowler stats over-credited at over crossings (candidate label: B-θ)

**Symptom.** UI bowling card at ov=2.1 showed `Roy 1.2-8-0` while broadcast strip showed `ANUKUL 0-7 1.1`. UI is one ball + one run over broadcast.

**Trace evidence.**
- f97  ov=1.0 s=7  EVT=1_RUNS  bowler=ANUKUL   (end of over 1, correct)
- f118 ov=1.1 s=7  EVT=DOT     bowler=None     (ball 1 of over 2)
- f127 ov=1.2 s=8  EVT=1_RUNS  bowler=VAIBHAV  (ball 2 of over 2)
- ...
- f176 ov=2.0 s=17 EVT=1_RUNS  bowler=ANUKUL  ← **suspect: end-of-over-2 commit credits incoming over-3 bowler, not Vaibhav who actually bowled the ball**
- f177 ov=2.1 s=17 EVT=DOT     bowler=ANUKUL  (over 3 start, Anukul confirmed)

**Hypothesis.** End-of-over commit reads the bowler observed on the over-crossing frame (which already shows the next over's bowler) and credits the final ball of the previous over to the new bowler. Need to inspect `_apply_event` + bowler-tracker on_lock ordering at over-boundary frames.

**Gate 6 anchor frames.** 97, 118, 127, 176, 177.

---

## Issue 2 — Phantom score + missed wicket via stream-gap absorption (candidate label: B-η)

**Symptom.** Broadcast strip at over 6.x showed `DC 49-1` with KL Rahul out `c Green b Tyagi` 23(14). UI showed `DC 54/0` — +5 phantom runs, missed wicket.

**Trace evidence.**
```
f302  ov=4.5  s=49/0  EVT=FOUR              ← broadcast DC 49/0 reached, correct
f303  POISONED                              ← frame guard rejected
f304  ov=6.3  s=54/0  EVT=ABSORBED_LEGAL    ← gap of ~1.8 overs collapsed into ONE event
f308  ov=6.3              bowler=TYAGI
f318  POISONED            proposed: KL Rahul 23(14) striker=false  ← wicket evidence present in Scout but frame poisoned
f356  ov=6.3  s=54/1                        ← wicket finally dispatched, score never reconciled to 49
```

**Mechanism.**
1. Stream lost ~1.8 overs of scoreboard captures (covered ball 4.6, all of over 5/6, balls 6.1, 6.2). `UDP-STREAM-FROZEN` fires 113× this session — most common decision tag.
2. On freeze-end at f304, pipeline observed a delta from ov=4.5 → ov=6.3 (10+ balls) and absorbed the entire range as a single `ABSORBED_LEGAL` with +5 runs, no decomposition, no wicket.
3. KL Rahul's dismissal evidence appeared in Scout at f318 but the frame was poisoned (likely a name/parse guard rejecting the post-wicket frame).
4. Wicket eventually dispatched at f356 (s=54/1) but the +5 phantom was never reverted.

**Hypothesis.** Recovery path on freeze-end with large over-delta has neither multi-ball decomposition nor wicket-claim reconciliation. Distinct from B-β (clean-event wicket dispatch) and from B-α (multi-ball-gap bowler credit) — both assumed contiguous-frame coverage.

**Gate 6 anchor frames.** 302, 303, 304, 308, 318, 356.

**Predicted-flip relevance.**
- `trace_beta_sm_wicket_dispatch`: handoff predicted PASS via F1 cascade. **Falsified on this fixture** — the wicket here failed to dispatch at the right ball (deferred from logical 5.x to f356 absorbed as 6.3 attribution) and the +5 phantom is fresh.
- `trace_alpha_bowler_runs_sum`: expected gap reduction; will likely show this fixture's bowler stats over-attributed (Issue 1 contributes).
- `trace_extras_total`: may stay FAIL per UI-render scope.

---

## Issue 3 — Pipeline stalls after stream-gap absorption (candidate label: B-η-stall, related to B-η)

**Symptom.** After the f302→f304 absorption event (Issue 2), UI froze at `DC 54/1, ov=6.3, Arora 0.5-9-0, Nissanka 27(16), Rana 0(0)` while broadcast moved on to `DC 56-1, ov=6.2, Varun 0.2 / 0-1, Pathum 31(19), N Rana 2(5)`. UI is not catching up.

**Notes.**
- FOW recorded as `54/1 (Rahul, 6.3)` — wrong over (actual dismissal at ov 4.5 per broadcast at the time, DC 49). The wicket got attached to the absorption-target frame, not the originating ball.
- Bowler stuck on `Arora` from over 5 absorption; broadcast has progressed to `Varun` over 7. SM is not accepting new bowler observations post-absorption.
- Batter card stuck on `Nissanka 27(16)`; broadcast shows `Pathum 31(19)` — Pathum scored at least 4 runs post-absorption that never landed on the card.
- `Rana 0(0)` in UI vs `2(5)` on broadcast — incoming-batter resolution worked but no subsequent ball events landed.

**Hypothesis.** Post-absorption, SM is in a state where its `score`/`overs` are ahead of where Scout's per-frame derivation thinks the game is, so subsequent legitimate Δ-frames either (a) fail the score-monotonic guard, (b) get classified as `ABSORBED_LEGAL` again with zero-delta, or (c) get poisoned. The deterministic-rotation override (`STRIKER-SM-BROADCAST-DISAGREES-DETERMINISTIC`) combined with frozen SM state prevents recovery.

**Gate 6 anchor frames.** post-f356 records (especially any frame where broadcast strip shows ov>6.3 or score>54). To enumerate post-replay.

**Severity.** This is the most operationally damaging symptom — single absorption event poisons the entire downstream session. Even if Issue 2's absorption logic gets fixed at the source, a recovery / re-sync path is needed for sessions where the absorption already happened.

---

## Issue 4 — `this_over` widget overflow / token-accumulation bug

**Symptom.** UI `This Over` row showed 12 token dots at the post-absorption state: `4, 1, ., 1, 4, 2, 1, 6, 1, 4, ., .`. A single over has 6 legal balls + possibly extras; 12 tokens is structurally impossible.

**Trace expectation.** `over_history` archives per integer over crossing; the current-over panel should reset on each over rollover. Cross-over accumulation indicates either (a) the rollover trigger isn't firing because SM `overs` value isn't crossing integer boundaries cleanly post-absorption, or (b) the WS payload's `this_over` projection isn't slicing to the current over only.

**Hypothesis.** Same root as B-η-stall — SM state stuck at the absorption-target over, so subsequent ball events keep appending to the same `this_over` bucket instead of rolling over. Pure UI projection bug is also possible; need to inspect `build_full_payload`'s `this_over` source field and compare against `over_history` archived overs.

**Gate 6 anchor frames.** to enumerate post-replay — frames where `this_over` token count exceeds 6.

---

## Issue 5 — Second FOW at ov=8.0 with mis-attributed bowler / score

**Symptom.** UI shows `74/2 (Nissanka, 8.0)` FOW entry while bowler card displays `Green 0.5-11-0`. Over 8.0 boundary should attribute the dismissal to the over-8 bowler with 1.0 in their card; Green showing 0.5 means he started over 9 with 5 balls and is being credited with the wicket from over 8's last ball.

**Notes.**
- Same misattribution mechanism as Issue 1 (B-θ over-boundary bowler credit), now compounded onto a wicket.
- Suggests wicket dispatch path also reads bowler from the post-rollover frame rather than the ball-of-dismissal frame.

**Hypothesis.** `_apply_wicket_fall_only` records dismissal-time bowler by reading current `self.bowler_name` instead of the bowler associated with the legal ball whose runs were committed. If a frame in the over-crossing window updates `self.bowler_name` to the next over's bowler before the wicket dispatch executes, the wrong bowler gets credited.

**Gate 6 anchor frames.** to enumerate post-replay — the frame where `74/2` FOW gets emitted plus the immediately-prior bowler-name transition.

---

## Issue 6 — FOW lists wrong dismissed batter

**Symptom.** At `DC 75/2 (8.3 ov)`, UI FOW shows `74/2 (Nissanka, 8.0)` but per broadcast, Pathum Nissanka was still batting through the over-7/8 window (last seen on broadcast strip as `PATHUM 31(19)` during the post-absorption stall). The batter actually dismissed at 74/2 was not Nissanka. New batter `Rizvi` came in at non-striker, with `Rana` (existing striker) unchanged on `7(3)` — confirms the dismissed end was Nissanka's position only if Nissanka was actually at the crease, which the deterministic-override-suppressed striker state likely got wrong.

**Notes.**
- FOW `54/1 (Rahul, 6.3)` was at least correct on the dismissed-batter identity (KL Rahul matches broadcast), even though the score (54 vs actual 49) and over (6.3 vs actual ~4.5) were mis-attached.
- FOW `74/2 (Nissanka, 8.0)` is suspected to have the wrong identity.

**Hypothesis.** Wicket-commit path reads dismissed-batter identity from SM's `self.striker` / `self.bat1_name` / `self.bat2_name` at commit time. Post-absorption SM state is stale (deterministic-override rejecting fresh broadcast names), so the resolver picks the wrong name. The squad-canonical resolver (`9856fd6`) protects against OCR garbage but cannot detect when a stale-but-valid squad name is asserted.

**Severity.** FOW is a permanent record — wrong identity here corrupts scorecard / partnership / batter-card history.

**Gate 6 anchor frames.** to enumerate post-replay — the f-id where `wickets→2` commits, plus the prior 5 frames to capture the striker/non-striker name state at dismissal time.

---

## Issue 7 — Striker rotation/identification root failure post-absorption (likely root of Issues 5 + 6)

**Symptom.** At broadcast `DC 87-4 10.2` with `AXAR 1(1)` and `> STUBBS 0(1)` (Stubbs on strike), UI shows `DC 86/4 10.1`, `At The Crease: Rizvi 1(2)` (only one batter populated), and FOW chain `54/1 Rahul → 74/2 Nissanka → 80/3 Rana → 85/4 Stubbs`. Stubbs is actively batting per broadcast — the `85/4 Stubbs 10.1` FOW entry dismissed a batter who is still on the field.

**Cascade chain.**
1. B-η absorption (Issue 2) leaves SM `striker` / `bat1_name` / `bat2_name` stale relative to actual game.
2. Deterministic-rotation override (commit `2105463`, `score_manager.py:4295-4325`) rejects all broadcast striker writes once `self.striker is not None` — so SM never accepts the corrected striker identity from fresh broadcast frames.
3. Every subsequent wicket dispatch resolves "dismissed batter" by reading SM's stale `striker` (or non-striker) value.
4. The actual dismissed batter's correct identity is in the broadcast strip but cannot enter SM state because override is blocking.
5. Each FOW entry ratchets the corruption forward — the dismissed name gets removed from SM's batting card while the broadcast's actual dismissed batter stays in the broadcast strip, so the next frame's broadcast looks "wrong" to SM and gets rejected again.

**Root identification.** The deterministic-rotation override was designed for the case where SM is correct and broadcast indicators are noisy. When SM is **wrong** (post-absorption, post-poisoned-frames), the override becomes the corruption-preserver. It needs an unlock condition tied to score/wicket/over divergence beyond a threshold.

**Connection to F1 cascade.** F1 fixed the cold-start initial-striker bug, which prevented one well-known corruption path. It did NOT fix the in-play resync path. The "Once high confidence reached, LOCKED — only explicit events unlock" principle from CLAUDE.md needs a corollary: **what counts as an explicit unlock event when SM and broadcast diverge by >N runs / >M overs?**

**Gate 6 anchor frames.** Each `wickets→N` commit frame post-f302, plus the prior 10 frames showing the SM striker state and any `STRIKER-SM-BROADCAST-DISAGREES-DETERMINISTIC` rejections.

**Severity.** This is the cascade-root for Issues 5 + 6 and arguably Issue 3 (B-η-stall): the override never lets SM resync to ground truth once it's off. Fixing B-η absorption alone won't help — without a resync path, any future absorption will produce the same downstream corruption.

**Candidate label.** B-ι — locked-SM-state-prevents-resync.

---

## Issue 8 — `this_over` token UI shows `?` placeholders for unresolved tokens

**Symptom.** At `DC 89/5 (10.5 ov)`, UI `This Over` panel: `W, Wd, 1, 2, ?, ?` — 4 resolved tokens + 2 `?` placeholders. Broadcast tail strip shows over composition `4, W+WD, WD, 1, 2, ..., W` for the same window (Anukul's spell over 10.5 timestamp). UI is missing the compound `W+WD` token entirely and is rendering `?` for tokens that the system either dropped or never resolved.

**Notes.**
- This is a different failure shape than Issue 4 (12-token overflow). Now the panel is under-populated with explicit unknown markers.
- Compound `W+WD` (wicket-on-wide) is a real cricket event distinct from F1-cascade-closed phantom compounds (`Wd+3`, `Wd+5` from B-α). Real compounds need first-class encoding.
- `?` placeholders indicate the UI projection layer is now exposing unresolved tokens rather than dropping them — possibly intentional from a prior commit, possibly a regression.

**Hypothesis.** Two contributing causes:
1. `_synthesize_cold_start_ball_events` or `_decompose_multi_ball` does not have a token shape for "wicket-on-wide" — the legitimate compound gets either split (losing the wicket) or absorbed.
2. The `?` placeholder rendering is a fallback when `this_over_tokens` contains a `None` / unresolved entry.

**Connection to Issue 7.** When SM is post-absorption-stuck, every subsequent ball whose Δ doesn't match SM's expected commit shape will resolve to `?` or absorbed-null. The same `STRIKER-LOCK-MID-OVER-SUPPRESSED` pattern that blocks striker writes likely blocks the token archival flag updates too.

**Gate 6 anchor frames.** to enumerate post-replay — frames where `this_over_tokens` contains `None` or `?` sentinels.

---

## Issue 9 — Every wicket delivery is the trigger for state corruption

**User-stated diagnosis (validated).** "Wicket deliveries are constantly causing issues." Concrete pattern across the session's FOW chain:

| FOW | UI says | Broadcast truth | Defect |
|---|---|---|---|
| 1st | 54/1 Rahul 6.3 | 49/1 Rahul ~4.5 | score +5 phantom, wrong over (B-η) |
| 2nd | 74/2 Nissanka 8.0 | Nissanka still batting on broadcast at this point | wrong dismissed batter (B-ι) |
| 3rd | 80/3 Rana 9.5 | unverified | likely wrong batter (B-ι cascade) |
| 4th | 85/4 Stubbs 10.1 | Stubbs actively batting per broadcast 10.2 | wrong dismissed batter (B-ι cascade) |
| 5th | 89/5 (Rizvi only at crease) | — | confirmation Rizvi state is stale |

**Consolidated root.** B-η + B-ι together: the absorption event creates the SM/broadcast divergence; the locked override prevents resync; every subsequent wicket commit reads the stale SM striker/non-striker; the FOW chain accumulates wrong identities and corrupts batting-card history permanently.

**Fix sequencing implication.** Single-point fixes in `_apply_wicket_fall_only` will not work — the dismissed-batter resolver itself reads from corrupted state. The fix must address the resync condition first (B-ι unlock threshold), then the wicket dispatcher.

---

## Issue 10 — `over_history` row for over 11 missing both `W` tokens (archived-over corruption)

**Symptom.** At `DC 89/5 (11.0 ov)`, FOW chain records two wickets in over 11: `85/4 Stubbs 10.1` and `89/5 Rizvi 10.5` (using `N.M` notation where 10.1 = ball 1 of over 11, 10.5 = ball 5 of over 11). UI `Recent Overs` row `Ov 11: 4, Wd, 1, 2, ., .` shows zero `W` tokens. UI `This Over` panel for same over also shows `4, Wd, 1, 2, ., .` — both views agree, both omit the wickets.

**Notes.**
- This is the **archived** over_history representation, not just the live panel. The corruption is persisted, not transient.
- Token count is structurally underweight: a 6-ball over with 1 wide and 2 wickets should produce 7+ tokens (Wd extends the over by 1 legal ball; W tokens occupy ball slots). Row shows only 6.
- At-the-crease names now show `Patel` and `Sharma` while broadcast says `AXAR 1(2)` and `> ASHUTOSH 0(1)` — name-resolver continues to drift further from broadcast truth (B-ι cascade compounding).

**Hypothesis.** `_archive_over` reads `this_over_tokens` at over-rollover. If the wicket dispatch (Issue 9) added FOW entries asynchronously without also appending `W` to `this_over_tokens`, the archived row is missing W tokens. This is the data-loss confirmation that the wicket-commit path and the over-token archival path are not transactionally coupled.

**Severity.** This produces a permanently corrupted `over_history` — UI cannot reconstruct correct over composition even after the live-state bug is fixed. Any post-replay analysis using `over_history` as ground truth will inherit the corruption.

**Gate 6 anchor frames.** to enumerate post-replay — the frames where `wickets→4` and `wickets→5` commit, and the immediately-following over-rollover frame. Compare `this_over_tokens` snapshots before and after each commit.

---

## Issue 11 — Per-ball speed indicator stops updating mid-session

**Symptom.** UI top-strip speed reading (e.g., `140.3 kph`, `89.8 kph`) updated ball-by-ball during the early portion of the replay. Past the post-absorption window (post-f304), the speed value stops refreshing on each delivery and persists across multiple balls. User confirmed live: "speed was working well initially when the replay started. but now it is not updating ball by ball."

**Hypothesis.** The speed value is attached to ball-event commit records (likely via Scout's `last_delivery` block → ball_event payload → UI `last_delivery.length/line/etc.`). When ball events are absorbed into `ABSORBED_LEGAL` no-op commits (Issues 2/3) or when commits get poisoned (Issue 2 frame poison pattern), the speed value isn't being refreshed on the UI payload. The previous frame's value persists.

**Connection to existing issues.** Tied to the broader pattern in Issues 3 (B-η-stall) and 7 (B-ι locked state): when SM commits stop firing cleanly, every per-ball-attached signal (speed, length, line, angle, bounce, shot, contact, type — all shown as `—` in `LAST DELIVERY` panel since post-absorption) stops refreshing. The `LAST DELIVERY` row in most recent screenshots shows all fields as `—` / `awaiting first delivery` despite the game being deep into over 11 — confirms the entire delivery-metadata channel is broken.

**Severity.** Lower than B-η/B-ι (no permanent corruption), but symptomatic — useful as a fast-feedback indicator that ball-event commits have stalled. Could be promoted to a real-time anomaly tag (`DELIVERY-METADATA-STALE`) in v1.1 per `trace_and_detect_system_design.md` §3.

**Gate 6 anchor frames.** to enumerate post-replay — last frame where speed value changed vs current frame, frame delta gives stall onset.

---

## C15 predicted-flip claim (2026-05-21, post-C14 fix)

C14 (`ad151fd`) shipped Shape B cross-field pairing gate at `apply_scorer_decision` (`test_pipeline.py:4517`). The gate's empirical evidence chain is documented at `files/docs/investigations/c13_fc5_audit_memo.md` and `temporal_coupling_investigation_brief.md` §11-§13.

**On the next natural production session** (no scheduled re-run; validation gate fires at the next live match capture), the predicted assertion-library deltas are:

| Assertion | Pre-C14 (current trace) | Predicted post-C14 (next session) | Cascade pathway |
|---|---|---|---|
| `trace_epsilon_initial_striker` | PASS | PASS (unchanged) | F1 path, not affected by C14 |
| `trace_compound_tokens` | PASS | PASS (unchanged) | F1 cascade closure |
| `trace_extras_total` | PASS | PASS (unchanged) | unrelated to F304 |
| `trace_alpha_bowler_runs_sum` | FAIL gap=4 | **predicted: gap reduces or PASS** | B-θ over-boundary contribution inherited from B-η-corrupted state collapses when F304 anchor is rejected |
| `trace_beta_sm_wicket_dispatch` | FAIL — 3 misses (f371, f521, f636) | **predicted: PASS** | F304 anchor blocked → SM stays consistent post-f300 → wickets at f371/f521/f636 dispatch at the right frames with the right dismissed-batter identity |

**Issue-level predicted improvements (from the 11-issue observations list above):**

| Issue | Pre-C14 symptom | Predicted post-C14 |
|---|---|---|
| 2 (B-η stream-gap absorption) | DC 54-0 (6.3) phantom + missed wicket | Cascade root closed at f304 — phantom blocked at apply_scorer_decision |
| 3 (B-η-stall) | UI freezes at 54/1 post-absorption | Cascade closed → no absorption → no stall |
| 5 (FOW mis-attribution at 8.0) | Stuck SM striker propagating to wicket commit | SM stays consistent → correct dismissed-batter identity |
| 6 (FOW lists wrong batter) | Nissanka recorded when Pathum still batting | Identity stays correct |
| 7 (B-ι resync-prevention root) | Locked override prevents resync | If B-η truly closes B-ι as cascade symptom: closed too. If not: B-ι remains as standalone investigation |
| 9 (every wicket triggers corruption) | Chain of mis-attribution across FOW 1-5 | All FOW commits land on correct frame with correct identity |
| 10 (`over_history` archived corruption) | Missing W tokens in over 11 | Token archive untainted post-fix |
| 11 (delivery-metadata frozen) | All `LAST DELIVERY` fields stuck at `—` | Per-ball signals refresh normally |

**Falsification trigger.** If `trace_beta_sm_wicket_dispatch` does NOT flip to PASS on the next natural production session, that is the **sixth empirical falsification of the chain**. Per `temporal_coupling_investigation_brief.md` §1.2 + C9 §11, the methodology retires at that point. **The most likely cause of non-flip:** Shape B covers `apply_scorer_decision`'s DIRECT-path sb.set sequence only; the catch-up branch (`test_pipeline.py:8986+`) and end-of-over hook (`:11750`) are uncovered. The C16 follow-up (deferred) would extend Shape B's coverage to those paths with the empirical justification on disk.

**Validation gate.** The next natural production session is the canonical validation step. No fresh-session-now authorization required — the workstream's standing pattern is "ship with predicted-flip claim, validate on next natural session." Per C16's HANDOFF rewrite (next deliverable), this becomes the operational gate for the C14 fix.

---

## Trace-session assertion results (empirical predicted-flip closure)

Run command (post-replay):

```
python3 files/scripts/run_trace_session_assertions.py \
    logs/trace/validate_dckkr_20260521_070545.jsonl
```

Result against 341 records:

| Assertion | Predicted (prior handoff §8.2) | Actual on DC vs KKR | Verdict |
|---|---|---|---|
| `trace_epsilon_initial_striker` | PASS (F1 direct fix) | **PASS** | confirmed |
| `trace_compound_tokens` | PASS (F1 cascade) | **PASS** | confirmed |
| `trace_extras_total` | stays FAIL (UI workstream) | **PASS** | better than predicted |
| `trace_alpha_bowler_runs_sum` | significant gap reduction | **FAIL gap=4** (pre-F1 was 24) | major improvement, not closure |
| `trace_beta_sm_wicket_dispatch` | PASS (F1 cascade closure) | **FAIL — 3 misses** | **predicted-flip violation** |

**B-β misses with concrete anchor frames (the gate-6 frame numbers Issues 5/6/7 were waiting on):**

| Frame | Match state | Dismissal mode | Striker recorded |
|---|---|---|---|
| 371 | DC 54-1 (6.3) | None | Pathum Nissanka |
| 521 | DC 74-2 (8.0) | bowled | Pathum Nissanka |
| 636 | DC 80-3 (9.5) | None | Nitish Rana |

Each row is a `ball_event.type=WICKET` Scout emitted that SM did not dispatch into a `wickets→N` commit at the same frame. Combined with Issues 5/6/7 (FOWs that DID eventually commit at later frames with wrong identity and over), this confirms two failure modes coexist:

1. **Wicket-dispatch deferral** — Scout's WICKET event at frame 371/521/636 not committed; the wicket later commits at a different (later) frame with stale state.
2. **Dismissed-batter mis-attribution** — when the deferred dispatch eventually fires, it reads SM's stale striker/non-striker, producing wrong-name FOW entries.

**B-β cascade-closure falsified.** F1's cascade reach on GTRR captured-dump replay did not generalize to this fresh fixture. The hypothesis "F1 collapses B-β" survives on captured GTRR data but fails the gate-7 cross-fixture check on DC vs KKR. Per §7.2 discipline, B-β returns to the engineering queue with its own design memo target.

**Cascade-root narrowing.** The 3 missed-dispatch frames (371/521/636) all precede the absorption event at f304 (4.5→6.3 jump) — wait, 371 is AFTER 304. So the f304 absorption is the trigger for the entire downstream chain. Pre-f304 the pipeline was healthy (epsilon + compound + extras all PASS). Post-f304 every wicket dispatch defers.

**B-α improvement.** Gap shrunk from 24 runs (GTRR baseline) to 4 runs (DC vs KKR). F-α-queue is doing real work. The remaining 4-run gap is likely Issue 1 (B-θ over-boundary bowler credit) — bowler stats off by 1 run at each over crossing, accumulating.

---

## Cross-fixture verification target (§7.2 gate 7)

After replay ends, replay this trace against the assertion library and **also** replay `validate_gtrr_20260520_180715` to check whether the stream-gap pattern existed there and was previously mis-classified as B-β.

Specifically:
- Search GTRR trace for `ABSORBED_LEGAL` commits with over-delta > 0.6 (i.e., spanning more than one legal ball)
- Cross-reference frame numbers against POISONED frames immediately prior
- If the pattern reproduces in GTRR, B-η is the cascade root and B-β classification needs revision

---

## Next-step queue (do not act until replay complete)

1. Save artifacts per launch instructions §5 (trace, scout dump, pipeline.log, sha256 checksums).
2. Add session stem to `SESSION_CONTEXT` in `files/scripts/run_trace_session_assertions.py`:
   ```python
   "validate_dckkr_20260521_070545": {
       "expected_initial_striker": "Pathum Nissanka",
       "max_acceptable_extras": None,
   },
   ```
3. Run trace-session assertions; record actual vs predicted flips.
4. Open formal design memos for B-η (stream-gap reconciliation) and B-θ (bowler over-boundary credit) under `files/docs/investigations/` with full §7.2 7-gate audit before any code change.
5. Cross-fixture replay against GTRR per §7.2 gate 7.

---

## Pipeline health observations (informational)

- `UDP-STREAM-FROZEN`: 113 fires — investigate whether stream stability is degraded relative to GTRR session.
- `SCORER-SCHEMA-WOULD-DROP`: 112 fires — frames the schema validator would reject; check whether tolerated drops mask real signal loss.
- `STRIKER-LOCK-MID-OVER-SUPPRESSED`: 76 fires — mid-over broadcast striker writes correctly suppressed by deterministic override.
- `STRIKER-SM-BROADCAST-DISAGREES-DETERMINISTIC`: 14 fires — override actively rejecting bad broadcast indicators.
- `NAME-REJECTED-NOT-IN-SQUAD`: 14 fires — squad-canonical resolver working.

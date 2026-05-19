# Deterministic Striker Rotation — Design Memo

**Status:** Draft — awaiting approval before C1 implementation.
**Date:** 2026-05-19
**Owner:** derive-not-detect branch.
**Related:** `striker_write_thrashing.md`, `striker_path_b_read_audit.md`, `sm_rotation_atomicity_design.md`, `trace_and_detect_system_design.md` (tag glossary).

---

## §1. Motivation

Two failure classes converge on the same root cause: **`striker_tracker.lock()` mid-over is fundamentally unreliable.**

- **Issue 3 — 2.2 ov (current trace `watch_20260519_082523.jsonl`):** Rahul was on strike per deterministic rotation from over 1.0 (Nissanka faced ball 6 of over 0 for a single → Rahul on strike at 1.1). At 2.2 ov, Nissanka was wrongly credited for a four. The only mid-over LOCK that could explain this is a `striker_tracker.lock(Nissanka)` triggered by a broadcast `>` symbol read.
- **F344–F372 oscillation precedent (innings1, prior post-mortems):** striker_tracker oscillated between two batters across ~30 frames mid-over, driven by Scout `>` symbol misreads and broadcast strip flicker. The frame-by-frame churn corrupted batter balls-faced and partnership credit.

The shared mechanism: a broadcast or strip-OCR signal (`>` arrow, `*` marker, batter-row ordering) is treated as authoritative mid-over, overriding what the rotation math already knows. Vision is noisier than the rules of cricket. **Cricket's rotation rules are deterministic given an initial pair, per-ball off-bat runs, and over boundaries — vision is not needed to track strike mid-over.**

---

## §2. Architecture — Deterministic Rotation

**Invariant:** From the moment the opening pair (or post-wicket pair) is committed, the striker is a pure function of:
- The initial striker / non-striker at the start of the current at-crease pair.
- The sequence of per-ball events since that initialization.

**Per-ball rotation rules (applied in `_apply_event` after stat accumulation, BEFORE any other striker write):**

| Event | Rotation |
|---|---|
| Legal ball, off-bat runs odd (1, 3, 5) | swap striker ↔ non-striker |
| Legal ball, off-bat runs even (0, 2, 4, 6) | no swap |
| WICKET (caught/bowled/lbw/run-out non-cross) | no rotation; new batter replaces dismissed batter at the dismissed batter's end (§4) |
| WIDE | no rotation (ball re-bowled, no legal-ball boundary) |
| NO_BALL | swap per total off-bat runs parity from the re-bowled legal-ball outcome; the NO_BALL itself is +1 penalty extra, not off-bat |
| BYE / LEG_BYE | swap per total runs parity (these ARE legal-ball completions; batsmen ran) |
| End-of-over boundary | always swap (additional to any per-ball swap on the 6th ball) |

**Net rotation at over boundary:** if last legal ball was odd-runs → per-ball swap cancels end-of-over swap (striker stays on strike for new over). If last ball was even/dot → only end-of-over swap fires (striker rotates).

This matches the existing `STRIKER-OVER-END-DOUBLE-ROTATION-APPLIED` trace evidence in `watch_20260519_082523.jsonl` frame 44 (last ball=1 run, net=cancel, striker stays Nissanka). The deterministic path keeps the same math — it just removes the mid-over vision-driven overrides that contradict it.

---

## §3. Suppressed Paths

Every `striker_tracker.lock(...)` invocation that fires **mid-over** becomes a no-op.

**LOCK paths retained (active):**
- `STRIKER-TRACKER-INNINGS-START-INIT` — fires once at innings start with the opening pair from squad/toss data. Establishes the initial striker.
- `STRIKER-TRACKER-POST-WICKET-NEW-BATTER` — fires once per wicket after the wicket event commits, when the incoming batter is identified by vision (batting card transition or broadcast new-batter graphic). Establishes the post-wicket pair at the dismissed batter's end (§4).

**LOCK paths suppressed:**
- Every mid-over `striker_tracker.lock()` triggered by Scout `>` arrow reads, batter-row ordering, broadcast `*` markers, or any other in-over vision signal. These become observation-only.
- `STRIKER-BROADCAST-CORRECTION` triggers — currently this tag fires when broadcast contradicts the locked striker. Under the new architecture, this trigger emits `STRIKER-BROADCAST-DISAGREES-DETERMINISTIC` (audit-only) and does NOT override the deterministic striker.

**Audit emission:** every suppressed mid-over LOCK call records to trace under one of:
- `STRIKER-LOCK-MID-OVER-SUPPRESSED` — what would have locked, payload `{candidate, source, deterministic_striker, over, ball}`.
- `STRIKER-BROADCAST-DISAGREES-DETERMINISTIC` — broadcast contradicts deterministic striker, payload `{broadcast_striker, deterministic_striker, over, ball, source}`.

These let the analyzer surface the rate and pattern of vision-deterministic disagreements without changing behavior.

---

## §4. Run-out-with-Cross

**Out of scope this round.** Per user directive, assume non-cross — the new batter takes the dismissed batter's end. This is correct for the dominant case (~95%+ of run-outs in T20).

**Cross detection deferred to v2.** When batsmen cross before the run-out completes, the new batter goes to the non-dismissed end, and the surviving batter is now on strike. Detecting cross requires either broadcast signal (the `*` migrates) or replay-frame analysis of the dismissal sequence. Both are higher-complexity and risk re-introducing the vision-trust failure mode.

**Hook in place for future enablement:** `STRIKER-POST-WICKET-RESYNC` — emitted post-wicket if a configured signal (TBD: broadcast `*` migration, replay analysis) suggests cross. Audit-only in v1; activating it in v2 is a single guard flip in `_apply_wicket_fall_only`.

---

## §5. Drift Mitigation

Deterministic rotation assumes:
- The initial striker is correct.
- Every per-ball event is correctly typed (runs count + extras classification).
- The pending-ball queue eventually resolves every `?` with the correct token.

Where any assumption breaks, deterministic striker drifts from ground truth. Drift accumulates across overs because there is no mid-over re-anchor.

**Optional drift detector — `STRIKER-DRIFT-DETECTED`:**
- Fires at over-end only (bounded blast radius).
- Compares deterministic batter totals (runs, balls) to strip-observed totals.
- If `|deterministic_runs - strip_runs| > N` OR `|deterministic_balls - strip_balls| > M`, emit `STRIKER-DRIFT-DETECTED` with both totals and the disagreement direction.
- v1: audit-only — does NOT correct.
- v2 candidate: at over-end, if drift detected AND the deterministic-vs-strip disagreement is consistent with a swapped striker, re-LOCK at over-boundary (lowest-risk re-anchor point — no in-flight ball events).

**Bounded by time-to-next-wicket:** every wicket re-initializes the at-crease pair via `STRIKER-TRACKER-POST-WICKET-NEW-BATTER`, which zeros out any accumulated drift. In a T20 with ~5–7 wickets per innings, drift windows are bounded to ~3–4 overs typical, ~10 overs worst case.

Initial proposed thresholds: `N=3`, `M=2`. Tune after C2 trace analysis.

---

## §6. Deletion / Migration Scope

**Phase C1 — Suppress mid-over LOCKs.**
- Enumerate every `striker_tracker.lock(...)` call site via grep (`def lock`, `\.lock\(`).
- For each call site, classify as:
  - INNINGS-START (retain — innings-start init path)
  - POST-WICKET (retain — post-wicket new-batter init path)
  - MID-OVER (suppress — wrap in `if not _DETERMINISTIC_STRIKER_ROTATION_ENABLED:` and add `STRIKER-LOCK-MID-OVER-SUPPRESSED` trace emission)
- Enumerate every `STRIKER-BROADCAST-CORRECTION` trigger site (grep `STRIKER-BROADCAST-CORRECTION`).
- Rewrite each to emit `STRIKER-BROADCAST-DISAGREES-DETERMINISTIC` instead and skip the lock side-effect.
- Land as a feature-flagged change behind `DETERMINISTIC_STRIKER_ROTATION` (default off in C1, on in C2).

**Phase C2 — Verify rotation math.**
- Enable flag in test environment.
- Replay through over 5 on the current trace (covers F344–F372 oscillation window AND 2.2 ov Issue 3).
- Validate: `STRIKER-LOCK-MID-OVER-SUPPRESSED` count > 0 (proves suppression fired); `STRIKER-BROADCAST-DISAGREES-DETERMINISTIC` count reflects vision-noise rate; Pathum balls_faced at 5.4 ≤ 18 (not 32 as in pre-fix oscillation); 2.2 ov four credited to Rahul.

**Phase C3 — Post-wicket re-init verification.**
- Find a trace with multiple innings-wickets (any post-mortem from prior matches).
- Confirm `STRIKER-TRACKER-POST-WICKET-NEW-BATTER` fires after every wicket, and that the new pair's initial striker matches the dismissed batter's end (§4).

**Phase C4 — Drift detection (optional, deferred).**
- Implement `STRIKER-DRIFT-DETECTED` at over-end only.
- Audit-only; analyze drift rate across 10+ matches.
- If drift rate < 1 per match, ship as-is. If higher, design v2 over-end re-LOCK.

**Default-on flip: at end of C2 if validation passes.** Single-commit revert if regressions appear.

---

## §7. Validation Criteria

**Replay corpus:** the current 2.4-over trace `watch_20260519_082523.jsonl` (covers 2.2 ov Issue 3) PLUS a prior match trace covering F344–F372 oscillation (TBD — pick from `files/docs/investigations/*post_mortem*.md` references).

**Trace tag assertions (per replay):**
- `STRIKER-LOCK-MID-OVER-SUPPRESSED` count >= 1 (proves suppression path fired).
- `STRIKER-BROADCAST-DISAGREES-DETERMINISTIC` count is recorded for baseline; no assertion on magnitude.
- `STRIKER-TRACKER-INNINGS-START-INIT` count == 1 per innings.
- `STRIKER-TRACKER-POST-WICKET-NEW-BATTER` count == wicket count per innings.

**Behavioral assertions:**
- Pathum Nissanka balls_faced at 5.4 ≤ 18 (not 32 — proves F344–F372 class fixed).
- 2.2 ov four credited to Rahul (deterministic striker at that point), not Nissanka.
- Partnership balls match deterministic ball count, not the oscillation-inflated count.
- No new `BATTERS-INVARIANT` violations introduced.

**Regression guard:** existing batter/bowler stats tests in `files/tests/` should pass without modification. If any test depends on mid-over LOCK behavior, the test reflects the bug and needs updating — flag for review.

---

## §8. Risks & Mitigations

### R1 — Cold-start mid-innings join

**Risk:** Pipeline starts mid-innings (operator joins late, post-restart, etc.). `STRIKER-TRACKER-INNINGS-START-INIT` either doesn't fire or fires with stale opening-pair data. Initial deterministic striker is wrong, and every subsequent ball compounds the error.

**Mitigation:** Use the existing cold-start synth path (`COLD-START-SYNTHESIZED-EVENT`, fired this run at frame 7) as the deterministic-striker init signal. At cold-start exit, derive initial striker from `scoreboard.striker` (broadcast read at that moment — one-shot trust event, not a recurring lock). Tag this event as `STRIKER-TRACKER-COLD-START-INIT` for trace audit. Document that cold-start join carries a non-zero initial-mismatch risk; user accepts this for now.

### R2 — Run-out with cross

**Risk:** §4 deferred this case. New batter goes to wrong end; subsequent over has wrong striker. Drift compounds until next wicket re-init.

**Mitigation:** §4 hook `STRIKER-POST-WICKET-RESYNC` is in place. v1 ships with audit-only; v2 implements broadcast `*` migration detection. Estimated impact: ~5% of run-outs → ~1–2 instances per match worst case. Drift is bounded to within-innings.

### R3 — Drift accumulation without vision correction

**Risk:** A misclassified ball event (e.g. a 1-run mis-typed as a dot, or a wide mis-typed as a legal) silently flips striker for the rest of the innings. No vision correction means no recovery until next wicket.

**Mitigation:** §5 drift detector at over-end. Audit-only in v1 (measure rate). v2 over-end re-LOCK provides bounded re-anchor every 6 balls without re-introducing mid-over vision trust. Combined with §3 audit tags, the rate is observable from trace and tunable.

### R4 — Strip-OCR signal sometimes IS right

**Risk:** Some genuine corrections exist (broadcast `>` migration is sometimes accurate, e.g. when our pending-ball queue mis-classified an extra). Suppressing all mid-over LOCKs loses these corrections.

**Mitigation:** §3 `STRIKER-BROADCAST-DISAGREES-DETERMINISTIC` audit tag captures every disagreement. If post-C2 analysis shows broadcast was right more often than the deterministic path, that's a signal to fix the underlying event classification bug (the real root cause), not to re-enable mid-over LOCKs.

---

## §9. Rollback Plan

**Single-commit revert.** The change ships as one commit (or one feature-flag flip if we land C1 and C2 separately):
- C1 commit lands `_DETERMINISTIC_STRIKER_ROTATION_ENABLED` flag default-off + suppression infrastructure. No behavior change. Trivially reversible.
- C2 commit flips the flag to default-on. Single-commit revert restores prior behavior.

**Revert criteria:** if validation §7 fails OR if post-deploy any of the following regress:
- Batter balls_faced/runs accuracy vs. ground truth.
- Partnership balls/runs accuracy.
- `BATTERS-INVARIANT` violation rate.

**Detection:** trace analyzer's batter-stat divergence rule (P5 or P6, check `files/analyze_trace.py`) surfaces regressions automatically; manual eyeball of the first live match post-deploy.

---

## Open Questions (for review before C1)

1. **Cold-start init source:** §8 R1 proposes `scoreboard.striker` at cold-start exit. Confirm this is the right read-once source vs. derived from squad XI ordering.
2. **F344–F372 corpus location:** §7 references it — need the actual trace file path or replay clip to run C2 validation against.
3. **Drift thresholds:** §5 proposes `N=3` runs, `M=2` balls. These are first-pass guesses; happy to set after C2 trace analysis if no strong prior.
4. **Cross detection v2 timeline:** §4 defers run-out-with-cross. Acceptable for v1 ship; want to confirm it's not blocking C2 sign-off.

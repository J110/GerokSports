# P3 Diagnosis — bowler unchanged 4 overs, zero BOWLER decisions captured

Trace: `logs/trace/866ce150.jsonl` (WI-vs-RSA 2nd T20I, 2026-05-02 12:25)
Pipeline log: `logs/pipeline-2026-05-02-1225-wi-vs-rsa-2nd-t20i-south-africa-tour-of-west-indies-2024.log`

## §1 Symptom

P3 fires at **F182** with `overs_unchanged=4`, `bowler="Akeal Hosein"`,
`bowler_decisions_in_window=[]`. The trace contains zero `BOWLER*`-prefixed
decisions across F127–F186 even though that period spans an over-change at F157
(0.5→1.0), F179 (1.0→2.4), and (somewhere ≤F181) (2.4→4.0).

User hypothesis: bowler-change detection didn't fire. **That hypothesis is
wrong.** Detection fires repeatedly; the trace is blind to it.

## §2 Trace evidence vs pipeline log

Trace (`current_bowler` projected from `pipeline.current_bowler`):

| F | overs | ext_bowler | current_bowler | decision tags |
|---|------|-----------|----------------|---------------|
| 157 | 1.0 | Hosein | — (cleared) | (none) |
| 158 | 1.0 | Hosein | Akeal Hosein | (none) |
| 170–178 | 1.0 | S Joseph / Hosein (oscillating) | Akeal Hosein | (none) |
| 179 | 2.4 | Joseph | — | (none) |
| 181 | 4.0 | null | — | (none) |
| 182 | 4.0 | Akeal Hosein | Akeal Hosein | (none) |

Pipeline log for the **same frames** (`grep -E '\[BOWLER\]|\[GUARD\]|\[BOWLER OVERRIDE\]|\[BOWLER-CONSENSUS-INCONSISTENT\]|\[OVER CHANGE\]'`):

```
F157 [OVER CHANGE] → 1.0
F158 [GUARD] Same bowler Akeal Hosein after over change … (stuck 1f)
F159 [GUARD] Same bowler Akeal Hosein … (stuck 2f)
F159 [BOWLER OVERRIDE] None → Akeal Hosein (reads=1, must_change=True)
F178 [BOWLER-CONSENSUS-INCONSISTENT] refusing flip to 'Shamar Joseph'
F179 [BOWLER-CONSENSUS-INCONSISTENT-OVERRIDE] accepting 'Shamar Joseph'
F179 [BOWLER OVERRIDE] Akeal Hosein → Shamar Joseph
F179 [OVER CHANGE] → 2.4
F180 [GUARD] Same bowler Shamar Joseph … (stuck 1f)
F182 [BOWLER] New bowler confirmed: Akeal Hosein (was Shamar Joseph)
```

Eleven distinct bowler decisions fired in the pipeline; **zero** appear in
the trace. The detection path fires, the trace doesn't see it.

`anomaly_rules.rule_p3` checks
`_decisions_with_tag(rec, "BOWLER-LEAD", "BOWLER", "BOWLER-LOCK-RELEASED",
"BOWLER-LOCK-ACQUIRED")` on the firing frame's record only. At F182 the
record's `scorer.decisions[]` is empty (the only tags ever auto-captured in
this trace are `ASYNC-DA, DWR, L2, L2-DENSIFY, OPEN-SCOUT-SELECT,
PHASE-REJECT, TAGS` — none of the `BOWLER*` family).

## §3 Bowler-change flow vs trace promotion path

```
test_pipeline.py main loop
  ├─ scoreboard ext read
  ├─ over rollover detection (~L9961)
  │     scoreboard._bowler_must_change = True
  │     scoreboard._inn["current_bowler"] = None        ← clears
  │     log.info("  [OVER CHANGE] → …")                 (CricketLogger)
  ├─ bowler update path (~L7836)
  │     branch A:  [GUARD] Bowler locked …             (CricketLogger)
  │     branch B:  [GUARD] Same bowler … waiting       (CricketLogger)
  │     branch B':  [GUARD-RELEASE] _bowler_must_change…(CricketLogger)
  │     branch C:  [BOWLER] New bowler confirmed: …    (CricketLogger)
  │     scoreboard.update_bowler(name)
  │           ├─ bootstrap when current_bowler is None ← (note §4 bug 2)
  │           │     [BOWLER OVERRIDE] None → name      (CricketLogger)
  │           ├─ must_change accept-on-1st             (CricketLogger)
  │           ├─ N-frame consensus
  │           │     [BOWLER OVERRIDE] X → Y            (CricketLogger)
  │           └─ overs-mismatch consensus reject
  │                 [BOWLER-CONSENSUS-INCONSISTENT]    (CricketLogger)
  │                 [BOWLER-CONSENSUS-INCONSISTENT-OVERRIDE]
  └─ trace_emitter writes frame record
        scorer.decisions ← _TRACE_RECORDER.drain()

trace_emitter.DecisionLogHandler
  attached to logging.getLogger() (root) at process start
  logging.LogRecord →  [\[TAG\]] regex → recorder.record(tag=…)
```

The detection sites all log via `log = CricketLogger("TEST")`
(test_pipeline.py:88) or `log` in `eyes/scoreboard.py`. `CricketLogger._log`
(`files/eyes/cricket_logger.py:137-156`) **bypasses the Python logging
hierarchy entirely**: it `print()`s to stdout, then constructs a `LogRecord`
manually and calls `_file_handler.emit(record)` directly. No `Logger.handle`,
no propagation. `DecisionLogHandler`, attached to root, never sees the
record.

The handful of tags that *do* appear in trace decisions
(`ASYNC-DA`, `OPEN-SCOUT-SELECT`, `L2-DENSIFY`, `PHASE-REJECT`, …) come from
modules that use stdlib `logging.getLogger(__name__).info(...)` — those
propagate to root and get auto-promoted. Anything routed through
CricketLogger (i.e., the entire bowler-, guard-, wicket-, batter-decision
surface) is invisible to the trace.

## §4 Root cause

**Primary (P3 anomaly cause): trace-emitter blindness to CricketLogger
output.** `DecisionLogHandler` is attached to the root logger;
`CricketLogger` does not propagate through the logging tree, so every
`[BOWLER] / [BOWLER OVERRIDE] / [BOWLER-CONSENSUS-*] / [GUARD] / [GUARD-RELEASE]`
log line bypasses the auto-promote regex. The `bowler_decisions_in_window=[]`
evidence is not "the path didn't fire" — it is "the path fired but we have
no record of it." This is a **trace instrumentation bug**, not a detection
bug.

**Secondary (real bowler-attribution bug, separately visible in the log):**
the over-rollover handler at `test_pipeline.py:9993` clears
`scoreboard._inn["current_bowler"] = None`, then the bootstrap branch in
`scoreboard.update_bowler` at `scoreboard.py:2814-2820` accepts *any* name
on the very next read — including the just-finished bowler — without
checking `_bowler_must_change` or `_prev_over_bowler`. F159 shows
`[BOWLER OVERRIDE] None → Akeal Hosein (reads=1, must_change=True)` even
though Hosein was the previous-over bowler and must_change was set
specifically to require a different name. The `must_change` accept-on-1st
guard at L2765-2768 checks `name != _prev_over_bowler`; the bootstrap path
below does not. This is why the pipeline kept Hosein installed for ~22
frames until F178 when Joseph's overs reading finally drifted enough to
trigger `BOWLER-CONSENSUS-INCONSISTENT-OVERRIDE` at F179.

The secondary bug delays bowler updates but does not, on its own, cause P3:
even with the override at F179, the trace still shows
`bowler_decisions_in_window=[]` because of the primary bug.

**Tertiary (minor, contributing to the user's confusion):** the `BOWLER-LEAD`
tag is enumerated in `KNOWN_TAGS` (`trace_emitter.py:51`) and named in P3's
verdict text and rule scan, but its only emission site (`test_pipeline.py:7949`)
fires on a different condition — bowler runs incremented while team score
unchanged. It is a divergence flag, not the bowler-change signal. The P3
verdict text *"Inspect BOWLER-LEAD arbitrations …"* sends investigators
looking at the wrong tag.

## §5 Hypotheses ranked

1. **CricketLogger-bypass (≈ 95%).** Confirmed by direct comparison of
   pipeline log vs trace decision tags: 11 bowler events in log, 0 in trace,
   *and* every absent tag is a CricketLogger emission while every present
   tag is a stdlib-logger emission.
2. **Per-site `recorder.record(tag=…)` calls missing** (≈ 5%, partial). The
   design memo (CLAUDE.md → trace-and-detect §) explicitly notes auto-promote
   is meant to "close Phase C surface area without touching ~30 sites." The
   bowler sites have no explicit `_TRACE_RECORDER.record(...)` call, so the
   only mechanism is auto-promote — which fails per (1). Not strictly an
   independent hypothesis, but a fix vector.
3. **Frame-bucket lifecycle race** (≈ <1%). `begin_frame(n)` opens a bucket;
   `drain()` closes it. If a `[BOWLER]` log fired *outside* the
   `begin_frame…drain` window for that frame it would be lost. Eliminated:
   if this were the cause, *some* CricketLogger tag would survive in *some*
   frame's `decisions[]`. None do.

## §6 Proposed fix scope

Two-part fix.

**Part A — close the trace blindspot (primary).** In
`files/eyes/cricket_logger.py:137-156`, additionally publish each emission
to the standard logging tree so `DecisionLogHandler` can promote it. ~6 LOC:

- Lazily fetch `logging.getLogger(self.component)` once.
- After the existing `print` + `_file_handler.emit`, also call
  `self._stdlib_logger.log(level, line)` with `propagate=True` (default).
- Or: factor the `_TAG_RE`-extraction and call `_TRACE_RECORDER.record(...)`
  directly inside `_log` when `record.levelname` is INFO/WARN. This is more
  invasive but avoids any chance of double-printing if some other root
  handler is added later.

Either variant is ≤ 15 LOC including imports and a guarded
`get_recorder()` import to avoid a circular-import risk.

**Part B — fix the bootstrap bypass (secondary).** In
`files/eyes/scoreboard.py:2814-2820`, gate the bootstrap on `not
self._bowler_must_change or name != self._prev_over_bowler`. ~3 LOC. This
prevents the just-finished bowler from being re-installed within the
must-change window when `current_bowler` was deliberately cleared.

**Part C — accuracy nit.** Update `anomaly_rules.py:386,402-403` to drop
`BOWLER-LEAD` from the P3 evidence scan (it's the wrong tag — the runs/score
divergence flag — and its inclusion misled this investigation). Replace
verdict text to point at `BOWLER`, `BOWLER OVERRIDE`,
`BOWLER-CONSENSUS-INCONSISTENT`. ~4 LOC. Note: `[BOWLER OVERRIDE]` contains a
space, so the existing `_TAG_RE = r"\[([A-Z][A-Z0-9_-]*)\]"` will not match
it as a tag — Part A will need to either rename the log to `[BOWLER-OVERRIDE]`
or update the regex to allow spaces. Renaming is safer (~2 LOC additional in
scoreboard.py:2804).

**Total: ~25-30 LOC across 3 files.**

## §7 Test plan

1. **Unit (Part A):** add a test in `files/tests/test_anomaly_rules.py` (or
   a new `test_trace_emitter.py`) that emits via `CricketLogger("TEST")`
   inside a `recorder.begin_frame(n) … drain()` window and asserts the
   `[TAG]` shows up in the drained bucket with `_auto: True`.
2. **Unit (Part B):** add to `tests/test_anomaly_rules.py:test_p3_*` (or the
   scoreboard tests if present) a case that simulates over-change with the
   strip still reading the previous bowler for 1-3 frames and asserts
   `current_bowler` does NOT flip back via the bootstrap.
3. **Replay (combined):** rerun the trace analyzer
   `python files/analyze_trace.py logs/trace/866ce150.jsonl` after Part A
   and verify the F182 P3 fires with a populated
   `bowler_decisions_in_window` list (override + guard + confirm tags
   present). If P3 still fires after Part A+B, that is the *real* P3
   surface to triage — the current evidence cannot distinguish it.
4. **Smoke:** run a 5-minute live capture and `jq '[.scorer.decisions[].tag] |
   unique'` the trace; expect to see at least `BOWLER`, `BOWLER-OVERRIDE`,
   `GUARD`, `GUARD-RELEASE`, `STRIKER-ALIGN-FALLBACK` populated.

## §8 Regression risk

**Part A:** medium-low. Adding stdlib propagation may double-emit log lines
if some downstream code has *also* installed a console `StreamHandler` on
root (e.g. `logging.basicConfig` somewhere). Audit for that before merging.
The variant that calls `_TRACE_RECORDER.record(...)` directly avoids this
risk entirely but couples CricketLogger to trace_emitter.

**Part B:** low. The bootstrap path exists for cold-start (frame 1, no
bowler ever read). The proposed gate only suppresses bootstrap when
`_bowler_must_change` is True AND the candidate equals the just-finished
bowler — a state that only occurs immediately after an over rollover. Cold
start has `_bowler_must_change=False` and `_prev_over_bowler=None`, so the
gate does not fire there.

**Part C:** trivial. Verdict text and tag-list change only; if the regex
update is done correctly (or the log is renamed), no behavior change for
existing well-formed trace records.

A combined re-run of `files/tests/test_anomaly_rules.py` (32 cases) should
pass unchanged after Part C; if any P3 case relied on `BOWLER-LEAD` being in
the scan list, that case was already testing the wrong tag and should be
updated.

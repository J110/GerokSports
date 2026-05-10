# Full-pipeline replay validation — RR vs GT 2026-05-09 (52nd match)

D1+D2+D3+D4+D5+D7 derivation fixes replayed end-to-end against last
night's mp4. Two iterations:

- **v1** (`pipeline-replay-rr-gt-derived.log`): crashed at F1513 on
  D8 bug; squad URL was wrong (DC vs CSK 48th).
- **v2** (`pipeline-replay-rr-gt-derived-v2.log`): D8 fixed + correct
  squad URL + cached Scout for first 569 frames; reached F3702 in
  inn2 before SIGINT for unrelated reason.

Validation focuses on v2.

## Run parameters (v2)

- session_id: `8a0c6c14`
- Source: `files/logs/deliveries/20260509_184511/match_05aeca25.mp4`
  (4h12m, ~378k decoded frames @ 25 fps)
- Pipeline log: `files/logs/pipeline-replay-rr-gt-derived-v2.log`
  (34,530 lines)
- Scout cache hits: 569 (from prior run's
  `files/logs/deliveries/8df9ceb8/scout_raw.jsonl`)
- New Scout calls dumped: 1,328 (to
  `files/logs/deliveries/8a0c6c14/scout_raw.jsonl`, gitignored)
- Frames analyzed: F1 → F3702
- Innings reached: **inn1 complete + inn2 first over**
- Wall clock: ~3h15m (SIGINT'd manually for context switch)
- Cost: ~$1.50 Groq vision (1,328 fresh Scout calls)

## D-series marker firings (v2)

| Marker (substring)                 | Count | Status      |
| ---------------------------------- | ----: | :---------- |
| `inn1_impossible_wickets_overs`    |    21 | **D2 ✅ FIRED** |
| `inn1_severe_collapse_implausible` |     0 | not reached |
| `inn1_score_too_low_for_wickets`   |     0 | not reached |
| `Overs LARGE regression`           |     1 | **D5 ✅ FIRED** |
| `Regression streak ... force`      |     0 | not reached |
| `team-change candidate` (defer)    |     0 | not exercised (team stable) |
| `team-change consensus committed`  |     0 | not exercised |
| `NOT preserving (score never...)`  |     0 | inn1 ended cleanly (preserve correctly bypassed) |
| `cold-start reject` (legacy)       |    24 | down from 91 in tonight's broken |
| `Overs regression` (legacy)        |     3 | down from 14 in tonight's broken |
| `BALL EVENT ✓`                     |   129 | up from 3 in tonight's broken |
| `FORCE_COLD_START_RECALIBRATION`   |     1 | (D5-driven full reset) |

### D2 evidence (tonight's bug class confirmed blocked)

```
F1093 [SM] cold-start reject (inn1_impossible_wickets_overs: 5/3 (0.1))
F1095 [SM] cold-start reject (inn1_impossible_wickets_overs: 5/3 (0.1))
F1096 [SM] cold-start reject (inn1_impossible_wickets_overs: 5/3 (0.1))
... (21 total)
```

The `5/3 (0.1)` class — same family as tonight's `5/4 (0.1)` commit
that anchored the 67-min lockup — is now blocked at the SM cold-start
gate before it can poison `_last_warm_state`.

### D5 evidence (large-gap fast-track caught inn-transition graphic)

```
F3600 [SM] Overs LARGE regression (20.0→0.1, gap 19.9)
        — force re-COLD_START (stuck-tracker recovery)
F3600 [SM-FULL-RESET] reason=stuck_tracker_large_overs_regression
F3600 [SM] FORCE_COLD_START_RECALIBRATION:
        was 1/0 (20.0) mode=WARM → COLD_START
```

After GT closed inn1 at 20.0 overs, the broadcast briefly graphic-flashed
RR's 0.1-over chase. Large-gap fast-track recognized this as a stuck
tracker and forced cold-start re-entry — preventing the 20.0 → 0.1
"regression" from getting stuck.

## End-of-inn1 vs cricbuzz scorecard

| Field            | Cricbuzz         | Replay (v2)      | Match |
| ---------------- | ---------------- | ---------------- | :---: |
| Inn1 batting team| Gujarat Titans   | Gujarat Titans   | ✅    |
| Inn1 final score | 229/4            | **229/4**        | ✅    |
| Inn1 final overs | 20.0             | **20.0**         | ✅    |
| Inn2 target      | 230              | **230**          | ✅    |
| Innings transition | F~3279 detected | F3279 transitioned | ✅ |

Team-level scoreboard for inn1 is **exact match to cricbuzz**.

## NEW bugs surfaced (D9 candidate)

### D9 — Per-batter run accumulator under-counts

Per-batter `runs` field appears stuck at 0 throughout inn1 even though
ball counts increment correctly. Examples sampled mid-innings:

```
AFTER_bat1=Shubman Gill 0(31)         — cricbuzz: 84(44)
BEFORE_bat1=Washington Sundar 0(9)    — cricbuzz: 37*(20)
BEFORE_bowl=Tushar Deshpande 0-6 (2.0) — cricbuzz final: 4-0-52-0
```

Team total tracked correctly (229/4) but per-player breakdown does not.
Almost certainly fallout from the recent single-writer refactor
(d94893e / cef68b6 / 4b972e5) — score-event accumulators feeding
`update_batter` / `update_bowler` deltas may not be wired through to
the per-player counters in `scoreboard.batting_card` /
`scoreboard.bowling_card` for all event types. Cataloged here; not
in scope for D1-D8 derivation work.

### D10 — Scout cache + new run share frame_id namespace, but new dump uses new session_id

When SCOUT_REPLAY_LOG points at a prior session's JSONL and SCOUT_RAW_DUMP=1
appends to the new session's JSONL, the cache hits don't get re-dumped
(intentional — saves disk). But this means future replays that point at
the new session's JSONL will only have records past the cache's coverage,
not the full set. Operational note: when chaining replays, point
SCOUT_REPLAY_LOG at the original full cache, not at intermediate dumps.
Cataloged for documentation; no code change needed.

## Tonight's broken vs replay (head-to-head)

| Metric                       | Tonight (broken) | Replay (v2)   |
| ---------------------------- | ---------------: | ------------: |
| Inn1 final state             | wrong (frozen 14/4 (8.4)) | **229/4 (20.0) ✓** |
| Inn1 reached transition?     | No (locked 67 min) | **Yes**     |
| Inn2 reached?                | No               | **Yes (first over)** |
| BALL EVENTS                  | 3                | **129**       |
| 5/4 (0.1) class commits      | committed (D2 absent) | **blocked 21x (D2 active)** |
| Overs-regression lockups     | 67-min lockup    | **0 (D5 caught the one big-gap event)** |

## Replay limitations

1. **SIGINT'd at F3702** for an unrelated context switch — only first
   over of inn2 covered. Cannot validate inn2 final state vs cricbuzz.
2. **Per-batter / per-bowler stats unreliable (D9)** — team totals are
   accurate but individual cards aren't. Cricbuzz batter-level diff
   not produced.
3. **Squad URL still hardcoded** — fixed to RR vs GT for this run, but
   the underlying parametrization issue (backlog item) remains.

## Conclusion

**D2 and D5 empirically validated end-to-end against real Scout signal
on the actual problematic match.** Tonight's broken-state bug
(5/4 (0.1) cold-start lockup) is blocked by D2 with 21 reject events
on the same input class. D5's large-gap fast-track caught the
inn1→inn2 transition graphic (20.0 → 0.1) and forced re-cold-start
cleanly.

D1, D3, D4, D7 unit-tested but not exercised in this run (input
patterns didn't recur). D8 fix (`bowler_wickets` setter migration)
held — pipeline went 2.4× further than v1 before manual SIGINT.

Inn1 ended **exactly correctly**: GT 229/4 (20.0), target 230 — full
match to cricbuzz. The derivation work (D1-D8) measurably moved the
needle from a 67-min lockup with 3 ball events to a clean inn1 close
with 129 ball events.

## Artifacts

- `files/logs/pipeline-replay-rr-gt-derived-v2.log` (34,530 lines, ~12 MB)
- `files/logs/deliveries/8a0c6c14/scout_raw.jsonl` (1,328 fresh records)
- `files/logs/deliveries/8df9ceb8/scout_raw.jsonl` (569 prior records;
  combined: 1,897 cache-able responses for future replays)
- `files/scripts/cricbuzz_rr_gt_2026-05-09.json` (truth source)

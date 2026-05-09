# Trace-and-Detect — operations runbook (v1)

Design memo: `files/docs/investigations/trace_and_detect_system_design.md`.
Implementation date: 2026-05-02. Status: v1 shipped (post-match analyzer).
Real-time anomaly tagging deferred to v1.1 per operator decision Q3.

## What it does

Per processed scoreboard frame, the pipeline writes a structured JSONL
record to `logs/trace/<SESSION_ID>.jsonl` capturing:

- inputs each layer saw (Scout text, extractor batters/bowler, ball
  event)
- guard / decision tags that fired (auto-captured from any
  `[TAG] ...` log line via `DecisionLogHandler`)
- a UI mirror snapshot before / after the WS publish (matches the
  client `useMatchSocket.deepMerge` semantics)
- `ui_diff[]` of changed scalar paths
- per-stage latency

After the match, the analyzer CLI (`files/analyze_trace.py`) reads the
JSONL, fires nine internal-consistency rules (P1, P2, P3, P5, P6, P7,
P8, P9 + P4 in advisory mode), and writes a Markdown report.

## Where files live

| Artifact | Path |
|---|---|
| Live trace JSONL | `logs/trace/<SESSION_ID>.jsonl` |
| Post-match gzipped | `logs/trace/<SESSION_ID>.jsonl.gz` |
| Match report | `files/docs/match_reports/<YYYY-MM-DD>_<slug>.md` |
| Annotated trace (anomalies inlined) | `logs/trace/<SESSION_ID>.annotated.jsonl` |

`SESSION_ID` is the same 8-char hex used by `pipeline-*.log`
(`files/test_pipeline.py:L829`).

`TRACE_DIR` env var overrides the default trace directory.

## During the match

The trace runs alongside the existing pipeline. The DETAIL line in
`pipeline-*.log` is unchanged — operator workflow during the match does
not change. Real-time `[ANOMALY-Pn]` tags are deferred to v1.1 (per
Q3); the live tee continues to be your primary signal.

## After the match

```sh
python files/analyze_trace.py \
  logs/trace/<SESSION_ID>.jsonl \
  --report files/docs/match_reports/$(date +%F)_<match-slug>.md \
  --annotate logs/trace/<SESSION_ID>.annotated.jsonl \
  --match-name "RR vs DC, 43rd Match, IPL 2026"
```

The exit code is `0` on no-error, `1` if any `severity=error` anomaly
fired (CI-friendly).

Triage order: **Errors → Warnings → Info → Advisory**. Each anomaly
block carries a `jq` pointer for inspecting the full record window.

## Inspecting a frame range

```sh
jq -c 'select(.frame >= 4126 and .frame <= 4135)' \
  logs/trace/<SESSION_ID>.jsonl
```

To pull just the decisions in a frame:

```sh
jq -c '.scorer.decisions' logs/trace/<SESSION_ID>.jsonl | head -20
```

To group decisions by tag:

```sh
jq -r '.scorer.decisions[]?.tag' logs/trace/<SESSION_ID>.jsonl \
  | sort | uniq -c | sort -rn | head -30
```

## Retention (operator decision Q2 — first-cut)

- **In-flight (during match):** uncompressed `.jsonl`, `tail -f`-able.
- **Post-match:** `gzip` after the analyzer run; archive to
  `logs/trace/archive/` after 30 days.
- A typical 3-hour match at 1 fps emits ~50 MB raw / ~8 MB gzipped.

## Tuning thresholds

`files/anomaly_rules.py` exposes `THRESHOLDS` near the top of the
module. First-cut values per design memo §4.2:

| Rule | Threshold | Default |
|---|---|---|
| P1 | warn / error frames since wicket | 8 / 30 |
| P3 | warn / error overs unchanged | 2 / 3 |
| P4 | runs tolerance / sustain records | 2 / 3 |
| P5 | wicket lookaround frames | 2 |
| P6 | extras component-vs-total tolerance | 1 |
| P8 | delta warn / error / sustain | 2 / 3 / 2 |
| P9 | stale records: score / this_over / striker / non / bowler | 12 / 30 / 30 / 30 / 36 |

Re-tune after the first 3-5 post-fix matches. Calibration source: the
captured trace itself — count false positives / false negatives in the
report and adjust.

## Schema versioning

The first line of every trace file is:

```json
{"_schema_version": 1, "session": "<id>", "started_ts_wall": <epoch>}
```

`files/trace_emitter.py:TRACE_SCHEMA_VERSION` is the writer's version;
the analyzer rejects mismatched files with `ValueError`. Bump on any
breaking change to the `decisions[]` enum or top-level shape.

## Decision-tag coverage

The `DecisionLogHandler` auto-captures any `[TAG] ...` log line emitted
by ANY Python logger that propagates to the root logger. This covers
all ~30 sites listed in the design memo §2.2 with no per-site changes.

For richer typed payloads on a specific site, that site can call
`trace_emitter.get_recorder().record(tag="X", **payload)` directly;
both auto-captured and direct entries appear in the same `decisions[]`
list. The auto entries carry `_auto: true` for differentiation.

To add a new tag to the known set, append to `KNOWN_TAGS` in
`files/trace_emitter.py`. Unknown tags are still captured but flagged
`known: false` so the analyzer can surface them for catalog updates.

## Hard-stop policy

Per operator decision Q6: **no auto-hard-stop on anomaly fire**. The
real-time emission (v1.1) will surface to the operator only; the
existing `MONITORING_CHARTER.md` hard-stop checklist remains the
authority.

## Known limitations (memo §8)

1. No external scorecard fetch — internal-consistency only.
2. Server-side UI mirror parity must be kept in sync with
   `scorecard-ui/app/hooks/useMatchSocket.ts` deepMerge — covered by
   `files/tests/test_anomaly_rules.py::test_uimirror_*` parity tests.
3. Sub-emission-cadence transients (single-frame flickers between
   processed frames) are not visible to the trace.
4. Threshold calibration is first-cut; expect a v1.0.1 tuning round
   after match #1.

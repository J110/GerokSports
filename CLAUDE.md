## Response style

- No preamble. Start with the answer or action.
- No summaries. Stop when the task is complete.
- No "Let me know if..." or "Feel free to..." closers.
- No restating the request before answering.
- Maximum 3 sentences of prose between code blocks.
- Skip "I will now" / "Let me" / "Here is" / "Sure!" openings.

## Code output

- Show diff only. Do not output unchanged surrounding lines.
- No code comments unless explicitly requested.
- No blank lines for visual separation between code blocks.
- Edit only. No commentary on what was changed.
- For new files: create the file, then state only the path.

## Decision output

- Choice in one sentence.
- Decisive factor in one sentence.
- No alternatives, no caveats, no pros/cons unless explicitly asked.

## Thinking and reasoning

- Default to direct execution.
- Skip extended thinking for tasks under 50 lines of change.
- Skip thinking entirely for trivial tasks: renames, formatting, imports, type fixes.
- For complex tasks, think internally but output only conclusions.
- Do not narrate plans before executing. Execute first.
- Do not explain reasoning after acting. The diff is the explanation.

## Effort tier discipline

- Default effort tier: high. Not xhigh, not max.
- Use xhigh only when the user explicitly invokes /effort xhigh.
- Use low for: variable renames, import additions, formatting fixes, type annotations, comment edits.
- Never use max effort unless the user explicitly invokes it.

## Context discipline

- Do not auto-read files unless explicitly mentioned in the prompt.
- Never read: package-lock.json, pnpm-lock.yaml, yarn.lock, Cargo.lock, poetry.lock.
- Never read files in: node_modules/, dist/, build/, .next/, target/, .turbo/, .cache/.
- For multi-file changes, list target files explicitly before editing.
- Do not explore the codebase looking for "related" files.
- Use Grep with specific patterns over broad Glob searches.
- Do not Read entire files when a targeted Grep would suffice.

## Agent behavior

- Make minimum changes. No "improvements" to surrounding code.
- Do not run tests unless explicitly asked.
- Do not run linters or formatters unless explicitly asked.
- Do not validate work by re-reading edited files.
- Maximum 5 tool calls per task. If unable to complete in 5, stop and report.
- Do not retry failed operations more than once.
- For Agent Teams: never spawn more than 1 sub-agent unless explicitly requested.
- Do not generate file summaries after completion.

## List and format discipline

- Bullet lists maximum 5 items per response.
- No nested bullets unless explicitly requested.
- No headers in responses under 100 lines.
- Tables only when explicitly requested.
- No emoji.

## Pipeline feature flags

- `USE_OPEN_SCOUT` (default 1): runs the parallel-Scout
  `OpenScout` + `SpanAggregator` for shadow telemetry. Adds
  ~$0.03-$0.10 per match. Set `0` to fully disable.
- `USE_OPEN_SCOUT_SPANS` (default 0): when `1`, OpenScout's
  single-candidate span drives the delivery window. Multi-span
  defers to legacy `_find_span` per design memo §5.2. Shadow
  comparison fields land in `window_debug.json` regardless.
- See `files/docs/operations/parallel_scout_setup.md` for cutover
  gates and rollback.

## Trace-and-Detect (v1, 2026-05-02)

- Per processed scoreboard frame, the pipeline writes a structured
  trace record to `logs/trace/<SESSION_ID>.jsonl` via
  `files/trace_emitter.py`. Schema in design memo
  `files/docs/investigations/trace_and_detect_system_design.md` §3.
- Decision/guard tags are auto-promoted to `decisions[]` entries by a
  logging handler installed in `test_pipeline.py` near the SESSION_ID
  init. No per-site instrumentation needed; sites can call
  `trace_emitter.get_recorder().record(tag=…, **payload)` for richer
  typed payloads.
- Post-match analyzer: `python files/analyze_trace.py <trace.jsonl>
  --report files/docs/match_reports/<DATE>_<slug>.md`. Eight rules
  (P1 P2 P3 P5 P6 P7 P8 P9) plus P4 advisory. Real-time anomaly
  tagging deferred to v1.1 (operator decision Q3).
- Tests: `files/tests/test_anomaly_rules.py` (32 cases). Operations
  doc: `files/docs/operations/trace_and_detect_setup.md`.
- The DETAIL line in `pipeline-*.log` is preserved unchanged; trace
  emission is purely additive.

## Forbidden output phrases

- "I'll help you..."
- "Let me start by..."
- "I'll need to..."
- "Here's what I'll do..."
- "I hope this helps"
- "Let me know if you need..."
- "Feel free to..."
- "Great question!"
- "Of course!"
- "Absolutely!"

## Budget discipline (removed by user direction 2026-05-24)

Do NOT track empirical-budget counters, methodology cap proximity, or Phase-tier cost framing. Do NOT introduce budget-counter language into decisions, instructions, commit bodies, or memos. Do NOT recommend workstream deferrals on budget-conservation grounds. The "5-cap empirical-falsification budget" framework is retired going forward.

What remains in scope: code structure discipline (§15 fence, §7.2 audits, canonical write paths), planning discipline (investigation memos for complex scope, pre-screen fix-surface category, S26-v2 spot-check before patch), quality gates (L1.5 + L2 + derivation green before commit), single-IV discipline for empirical replays (causal attribution, not cost-rationing), honest scope assessment.

Execute decisively. Historical references to budget counters in past investigation memos are preserved as factual records but going-forward framing drops the cap.

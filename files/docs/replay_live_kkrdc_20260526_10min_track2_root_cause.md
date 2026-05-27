# KKR/DC 10-Minute Track 2 Root Cause

Inputs:

- Manual labels: all 13 fixed-session clips mostly wrong; only `d007` is partially correct, and `d008` captures the remaining part of the same delivery.
- Delivery windows: `files/logs/deliveries/replay_kkrdc_10min_20260526_200243/d*/window_debug.json`
- OpenScout metadata: `files/logs/openscout_deliveries/replay_kkrdc_10min_20260526_200243/*_metadata.json`
- OpenScout sidecar: `logs/openscout-replay_kkrdc_10min_20260526_200243.jsonl`
- Trace: `logs/trace/replay_kkrdc_10min_20260526_200243.jsonl`
- Replay log: `/tmp/replay_kkrdc_10min_20260526_200243.log`

## Summary

Track 2 failed because score-event-aligned fallback windows are being used for almost every delivery, while the actual OpenScout action spans exist in a separate archive but are not selected for the dNNN delivery windows.

The strongest proof is `d007`/`d008`: `d007` uses an event-aligned fallback window, `d008` uses a retrospective span, and both overlap the same OpenScout action span (`delivery_0008`, `1779797354.972-1779797360.058`). Manual labels say `d007` is only partially correct and `d008` captures the rest of the same delivery, so the system split one real delivery across two clip outputs.

Track 2 has two artifact families that must be debugged separately:

1. OpenScout continuous clips under `files/logs/openscout_deliveries/<session>/delivery_*.mp4`. These are decoupled from Track 1 score events.
2. Score-event `dNNN` delivery windows under `files/logs/deliveries/<session>/dNNN/`. These are triggered by Track 1 score events and therefore inherit false or duplicate Track 1 event boundaries.

Next debug step: audit both families separately. For OpenScout continuous clip quality, ask whether `delivery_*.mp4` clips are real deliveries regardless of Track 1. For score-event `dNNN` quality, ask whether Track 2 cut the correct delivery window when Track 1 emitted a valid event.

Current regression scope: we are debugging `dNNN` score-event windows, not
OpenScout continuous clips. OpenScout continuous quality is a separate lower
layer and should not be used to judge the `dNNN` fallback regression.

Across the three 10-minute runs:

- Good `dNNN` fallback run: `replay_kkrdc_10min_20260526_204204`.
- Regressed `dNNN` run: `replay_kkrdc_10min_combined_20260526_222335`.
- Final post-patch evidence run: `replay_kkrdc_10min_final_20260526_231727`.

The `dNNN` quality regression was not caused by the delayed fallback window
itself. The `204204` run used the same widened delayed-score fallback shape
and had mostly good fallback windows. The likely cause of the later regression
was bad Track 1 event input: duplicate `Wd`, stale queued legal `DOT`, and the
post-ad scoreless legal tick. Those Track 1 causes were patched in
`files/eyes/commentary.py` and `files/test_pipeline.py`, but `dNNN` quality
still needs one bounded video rerun for validation.

## Verified Facts

- `d001`-`d007` and `d010`-`d013` use `window_source="v3_chunker_fallback"` with `window_reason="v3_and_legacy_returned_none"`.
- `d008` uses `window_source="retrospective_span"` with `window_reason="latest_bowlers_end_span"`.
- `d009` is skipped with `window_source="skipped"` and `window_reason="phantom_event"`.
- OpenScout verdict is `no_match` for every non-skipped dNNN window. `d009` has `open_scout_verdict=null` because it is skipped.
- Every fallback dNNN uses `clip_start_ts=event_ts-6s` and `clip_end_ts=event_ts+4s`.
- Replay log `[MATCH-SUMMARY]`: `events_seen=13`, `spans_committed=12`, `v3_resolved=0`, `v3_none=12`, `v3_fallback=11`.
- Session config: `use_v3_chunker=0`, `use_v3_chunker_spans=0`, `use_open_scout_spans=0`.

## 1. Why V3 Resolved Zero Real Spans

Root cause: v3 was not active for this run, so DWR had no v3 span source to resolve.

Evidence:

- Replay log `[SESSION-CONFIG]` has `use_v3_chunker=0 use_v3_chunker_spans=0`.
- All `window_debug.json` files have `"v3_chunker": null`.
- `[MATCH-SUMMARY]` has `v3_resolved=0`, `v3_none=12`, `v3_fallback=11`.
- The first five-minute stats already show the pattern: `[CHUNKER-V3-STATS] ... resolved=0 none=6 fallback=6`.

Conclusion: the zero-resolution result is expected from configuration. It is not evidence that a live v3 detector failed to find spans; it was effectively absent.

## 2. Why OpenScout Produced `no_match` Even Though Clips Exist

OpenScout delivery clips are written by `OpenScoutDeliveryWriter` when action spans are committed. That archive is independent of DWR's dNNN score-event matcher. DWR then tries to match committed action spans to a score event using the selector in `SpanAggregator.match_span_to_event_detailed`.

Selector constraints:

- Candidate window: `[event_ts - LOOKBACK_S, event_ts - POST_EVENT_EXCLUSION_S]`.
- `LOOKBACK_S=25.0`.
- `POST_EVENT_EXCLUSION_S=1.5`.
- `MAX_END_TO_EVENT_GAP_S=8.0`.
- The matcher only returns committed spans, not the currently open span.

Evidence:

- `files/eyes/span_aggregator.py` defines the event selector and filters candidates by `event_ts - s.end_ts <= max_end_to_event_gap_s`.
- `files/delivery_window_recorder.py` sets `LOOKBACK_S=25.0`, `POST_EVENT_EXCLUSION_S=1.5`, and `MAX_END_TO_EVENT_GAP_S=8.0`.
- `window_debug.json` shows `open_scout_window=null` and `open_scout_verdict="no_match"` for all non-skipped dNNN windows.
- OpenScout metadata still contains valid action spans, e.g. `delivery_0008_metadata.json` has span `1779797354.972-1779797360.058`.

Conclusion: OpenScout observed action spans, but the score-event selector rejected or missed them at event time. The archive existing does not imply DWR selected those spans.

## 3. Event Gap Rejection

Yes, useful OpenScout spans are being rejected or missed because score-event timing and selector timing do not line up.

The clearest cases:

- `d006`: event `1779797233.453`; closest useful action span `delivery_0005` ended at `1779797225.354`, gap `8.10s`, just over the `8.0s` limit. The next action span starts `4.90s` after the event.
- `d007`: event `1779797356.091`; action span `delivery_0008` starts before the event and ends after it (`1779797354.972-1779797360.058`). This is useful, but it lies inside the `POST_EVENT_EXCLUSION_S` forbidden zone and/or is not closed before the score event.
- `d008`: event `1779797359.228`; the same action span `delivery_0008` overlaps the event. DWR uses a legacy retrospective span from `1779797354.766-1779797358.266`, while OpenScout still says `no_match`.
- `d010`: event `1779797414.465`; closest action span `delivery_0009` ended at `1779797407.326`, gap `7.14s`, inside the `8.0s` limit, but it still did not land as `open_scout_window`, likely because the committed span was not visible at match time or the selection saw a different committed-set state.

Conclusion: the current selector is too strict for live score-event lag and committed-span latency. It also excludes overlapping action spans that are often the useful clips when score events arrive during or immediately after action.

## 4. Per-Clip Failure Classification

| Clip | Event | Source | Manual status | Failure class | Evidence |
|---|---:|---|---|---|---|
| `d001` | `1.1 DOT` | `v3_chunker_fallback` | mostly wrong | fallback/event misaligned | `event_ts=1779797006.916`; fallback `7000.916-7010.916`; closest action span starts just after event at `7007.405` |
| `d002` | `1.2 1_RUNS` | `v3_chunker_fallback` | mostly wrong | fallback-too-late | event `7046.929`; closest earlier action span ended `7018.155`, gap `28.77s` |
| `d003` | `1.3 DOT` | `v3_chunker_fallback` | mostly wrong | OpenScout candidate missed / fallback misaligned | event `7129.834`; action span `7111.915-7124.918`, gap `4.92s`, but DWR still emits fallback |
| `d004` | `1.4 DOT` | `v3_chunker_fallback` | mostly wrong | fallback-too-late | event `7151.091`; previous action ended `7124.918`, gap `26.17s` |
| `d005` | `1.4 EXTRA` | `v3_chunker_fallback` | mostly wrong | fallback-too-late / extra keyed before legal ball | event `7191.435`; previous action ended `7176.935`, gap `14.50s`; wide is keyed at `1.4` |
| `d006` | `1.5 DOT` | `v3_chunker_fallback` | mostly wrong | fallback-too-late edge case | event `7233.453`; previous action ended `7225.354`, gap `8.10s`, just beyond selector cap |
| `d007` | `1.5 EXTRA` | `v3_chunker_fallback` | partially correct | duplicate/split delivery | event `7356.091`; fallback `7350.091-7360.091`; overlaps OpenScout `delivery_0008` |
| `d008` | `2.0 DOT` | `retrospective_span` | remaining part of same delivery | duplicate/split delivery / wrong retrospective span | event `7359.228`; retrospective `7354.766-7358.266`; same OpenScout `delivery_0008` |
| `d009` | `2.1 1_RUNS` | `skipped` | skipped | skipped phantom | `window_reason="phantom_event"`, `frame_count=0` |
| `d010` | `2.2 1_RUNS` | `v3_chunker_fallback` | mostly wrong | OpenScout candidate missed / fallback-too-late | event `7414.465`; previous action `7397.075-7407.326`, gap `7.14s`, but no OpenScout match |
| `d011` | `2.3 DOT` | `v3_chunker_fallback` | mostly wrong | fallback-too-late | event `7467.637`; previous action ended `7407.326`, gap `60.31s` |
| `d012` | `2.4 SIX` | `v3_chunker_fallback` | mostly wrong | fallback-too-late | event `7511.617`; previous action ended `7407.326`, gap `104.29s`; next action starts `7523.183` |
| `d013` | `2.5 SIX` | `v3_chunker_fallback` | mostly wrong | fallback-too-late | event `7557.985`; previous action ended `7529.684`, gap `28.30s` |

## 5. Closest OpenScout Action Span Per Score Event

| Clip | event_ts | closest earlier OpenScout action span | gap from span end | Selector implication |
|---|---:|---|---:|---|
| `d001` | `1779797006.916` | none earlier; `delivery_0001` starts `+0.489s` later | n/a | event before useful span closes |
| `d002` | `1779797046.929` | `delivery_0001` `7007.405-7018.155` | `28.77s` | outside 25s/8s gates |
| `d003` | `1779797129.834` | `delivery_0002` `7111.915-7124.918` | `4.92s` | should be plausible by timing; likely not visible/closed at match time |
| `d004` | `1779797151.091` | `delivery_0002` `7111.915-7124.918` | `26.17s` | outside gates |
| `d005` | `1779797191.435` | `delivery_0003` `7163.933-7176.935` | `14.50s` | fails 8s gap |
| `d006` | `1779797233.453` | `delivery_0005` `7218.853-7225.354` | `8.10s` | barely fails 8s gap |
| `d007` | `1779797356.091` | `delivery_0008` `7354.972-7360.058` overlaps event | overlaps | useful but excluded/not closed |
| `d008` | `1779797359.228` | `delivery_0008` `7354.972-7360.058` overlaps event | overlaps | useful but excluded/not closed |
| `d009` | `1779797362.518` | `delivery_0008` `7354.972-7360.058` | `2.46s` | skipped phantom |
| `d010` | `1779797414.465` | `delivery_0009` `7397.075-7407.326` | `7.14s` | plausible by timing, but no match selected |
| `d011` | `1779797467.637` | `delivery_0009` `7397.075-7407.326` | `60.31s` | outside gates |
| `d012` | `1779797511.617` | `delivery_0009` `7397.075-7407.326` | `104.29s` | outside gates; next span starts after event |
| `d013` | `1779797557.985` | `delivery_0010` `7523.183-7529.684` | `28.30s` | outside gates |

## 6. Fix Direction

Use both, but prioritize OpenScout span matching tolerance/selection over simply widening fallback.

Why not fallback-only:

- The fallback window is fixed at `event_ts-6s` to `event_ts+4s`.
- Manual labels show almost all clips are wrong, meaning event-aligned fallback is not reliably close enough.
- Several useful OpenScout spans are tens of seconds away from the score event, so making fallback broad enough would create huge noisy clips.

Why OpenScout matching must change:

- Useful action spans exist in `files/logs/openscout_deliveries/...`.
- `d007`/`d008` prove one real delivery is being split across an event-aligned fallback and a retrospective span.
- The matcher rejects overlapping spans by `POST_EVENT_EXCLUSION_S=1.5` and rejects older spans by `MAX_END_TO_EVENT_GAP_S=8.0`.
- The matcher only sees committed spans, so an action span still open at score-event time can be missed even if the writer later archives it.

Recommended fix surface, after manual labels are reviewed:

1. Add a score-event-to-OpenScout matching mode that can use the closest action span whose start is before `event_ts`, including spans that overlap or end shortly after `event_ts`.
2. Increase or adapt `MAX_END_TO_EVENT_GAP_S` only when the candidate span is supported by visible score/over progression or nearby action-class density.
3. Keep a wider fallback as a safety net, but do not rely on wide fallback as the primary Track 2 cut source.
4. Add duplicate/split suppression: if two score events fall inside or near the same OpenScout action span, do not emit two independent dNNN clips without marking the second as duplicate/split.

No code changes made.

## 8. Adguard dNNN Manual Review (20260527_014643)

Session: `replay_kkrdc_10min_adguard_20260527_014643`.

Manual labels:

| Clip | Event | Source | Manual label | Root cause |
|---|---:|---|---|---|
| missing | `1.3 DOT` | n/a | missing between `d002` and `d003` | Track 1 post-dead-time guard suppressed a real scoreless tick after graphic/dead-time resume |
| `d004` | `1.4 EXTRA` | `v3_chunker_fallback` | BAD: replay, not delivery | Track 1 wide confirmation arrived late; fallback used the late event timestamp and cut replay/post-action context |
| `d007` | `2.1 1_RUNS` | `retrospective_span` | PARTIAL/BAD: starts at/near bat contact, misses release | Track 2 retrospective span selected a too-late/single-frame `bowlers_end/release` tag |
| `d012` | `3.0 2_RUNS` | `v3_chunker_fallback` | OK | Comparison-window phantom only; clip is manually acceptable |

`d004` is not a pure Track 2 selector failure. Its `window_debug.json` shows
`event_type=EXTRA`, `over_number=1.4`, `window_source=v3_chunker_fallback`,
`window_reason=v3_and_legacy_returned_none`, `tags=[bowlers_end/between_play]`,
and fallback bounds `event_ts-24s` to `event_ts-4s`. The event was emitted at
F62 after a deferred wide confirmation (`score+1 at overs=1.4` first seen at
F50, confirmed at F62). Because the event timestamp is late, the configured
fallback window lands on replay/injury/post-action material. A Track 2 selector
cannot reliably recover that without an earlier event timestamp or a better
delivery span candidate.

`d007` is a Track 2 selector/cut failure. Its `window_debug.json` shows
`event_type=1_RUNS`, `over_number=2.1`, `window_source=retrospective_span`,
`window_reason=latest_bowlers_end_span`, span
`1779818074.325-1779818074.325`, clip `1779818072.325-1779818075.825`, and
`retrospective_span_safe_margin_s=4.677`. Track 1 emitted the correct `2.1`
run at F98; the bad manual label comes from the selected retrospective tag
being too late or too sparse, so the 3.5s clip starts at/near bat contact and
misses the release.

Smallest Track 2 fix, if manual dNNN quality becomes the next patch target:
`files/delivery_window_recorder.py`, specifically
`DeliveryWindowRecorder._find_span()` and `_span_to_clip_bounds()`. Candidate
direction: reject or expand single-frame retrospective spans, require stronger
release/flight tag density before accepting `latest_bowlers_end_span`, or add
more pre-roll for singleton retrospective spans. Do not change the already
fixed `2.5s` retrospective rejection threshold without new evidence.

## 7. Final-Run OpenScout Continuous Clip Audit (20260526_231727)

Session: `replay_kkrdc_10min_final_20260526_231727`.

This section audits only the OpenScout continuous clips under
`files/logs/openscout_deliveries/replay_kkrdc_10min_final_20260526_231727/`.
These clips are decoupled from Track 1 score events and are produced from
committed OpenScout spans.

Manual labels:

| Clip | Manual label |
|---|---|
| `delivery_0001` | BAD: no delivery, post `1.1` / pre `1.2` |
| `delivery_0002` | OK: `1.3`, but `1.2` missed |
| `delivery_0003` | BAD: post `1.4`, no delivery |
| `delivery_0004` | OK: `1.5` |
| `delivery_0005` | BAD: post `1.5`, no delivery |
| `delivery_0006` | PARTIAL: `2.1` truncated, misses release, starts at bat contact |
| `delivery_0007` | BAD: post `2.1` replay, no delivery |
| `delivery_0008` | BAD: pre `2.2`, cuts just before release |
| `delivery_0009` | BAD: post `2.4` replay, no delivery |
| `delivery_0010` | OK: `2.5` perfect, no baggage |
| `delivery_0011` | BAD: post `2.5` replay, no delivery |

Metadata and nearby OpenScout samples:

| Clip | Span | Frames | Dur | Class | Nearby raw samples |
|---|---:|---:|---:|---|---|
| `delivery_0001` | `8757.625-8773.413` | 4 | 15.788s | `action` | `DC 10-0 1.1`; field/stadium wide shots; `TATA IPL 2026 DC 10/0 (0.1)` |
| `delivery_0002` | `8850.041-8876.049` | 5 | 26.008s | `action` | `DC 11-0 1.2`; then `DC 11-0 1.3` wide field shots |
| `delivery_0003` | `8922.140-8928.645` | 2 | 6.504s | `action` | `TATA IPL 2026, DC 11/0 (1.4)`; wide field; mid-swing wording |
| `delivery_0004` | `8967.888-8987.415` | 4 | 19.527s | `action` | `RAGHUVANSHI COVERS`; IPL graphic; `DC 12-0 1.4` live wide shots |
| `delivery_0005` | `9012.484-9018.986` | 2 | 6.502s | `action` | `S DUBEY TO POREL, OFFSIDE FIELD`; bowler-side wide shots |
| `delivery_0006` | `9127.971-9132.983` | 2 | 5.012s | `action` | `DC 12-0 2`; `DC 12-0 2.1`; wide field side shots |
| `delivery_0007` | `9143.027-9148.030` | 2 | 5.003s | `action` | `50L Views`; bowler already released; side/bowler-end replay-like wide shots |
| `delivery_0008` | `9168.046-9178.825` | 3 | 10.779s | `action` | `KL RAHUL v RIGHT ARM SEAMERS`; stats graphic with wide field visible |
| `delivery_0009` | `9307.612-9314.129` | 2 | 6.517s | `action` | `TATA IPL, SBI, JioHotstar LIVE 56L Views`; wide field replay/post-action shots |
| `delivery_0010` | `9335.586-9342.092` | 2 | 6.505s | `action` | `DC 20-0 2.4`; speed `138.4 kph`; clean wide-field delivery |
| `delivery_0011` | `9368.097-9374.598` | 2 | 6.501s | `action` | `63L Views`; player/action pose; post-boundary/replay-like stadium shot |

All 11 action metadata files have `clip_pre_pad_s=1.0`,
`clip_post_pad_s=1.0`, `frames_written > 0`, and `mp4_exists=true`.
Therefore the clips are auditable, and missing MP4s are no longer the
blocking issue.

### Root Cause

The OpenScout continuous detector is failing below the score-event matching
layer. It is classifying too many broadcast-wide or replay-like frames as
`action`, and `SpanAggregator` then turns consecutive `action` classifications
into committed action spans. The writer faithfully persists those spans with
only one second of pre/post padding.

Evidence:

- `OpenScoutDeliveryWriter` writes a continuous clip whenever
  `span.frame_class == "action"`; it does not reinterpret the clip content.
  The final-run metadata shows `n_classifications_action == frame_count` and
  `n_classifications_other == 0` for every `delivery_000N`.
- `OpenScoutDeliveryWriter` padding is only ±1s (`clip_start_ts =
  span_start_ts - 1`, `clip_end_ts = span_end_ts + 1`). This can add small
  lead/trail baggage but cannot explain `delivery_0002`'s 26s span or
  `delivery_0004`'s 19.5s span. Those spans are already too broad.
- `open_scout_classify.py` routes replay/ad/umpire first, then calls the
  binary action gate. Replay is only detected when the model text explicitly
  contains replay indicators (`REPLAY`, `SLO-MO`, `slow-motion`, etc.).
  The bad final-run samples generally do not contain explicit replay labels,
  so they fall through to the action gate.
- The binary action gate treats generic `"wide field view"` as `action`
  unless negated by specific idle/solitary-player rules. This explains why
  pre-delivery field views, post-delivery field views, and replay-like wide
  shots are promoted to `action`.
- `SpanAggregator` uses class-contiguity only: same-class observations extend
  the open span, one dissenting observation is absorbed, and a gap over 7s
  closes the span. It does not know delivery phase, score progression,
  replay UI, or whether the ball has actually been released.

So the dominant failure is classifier over-breadth, amplified by span
aggregation. It is not primarily writer padding.

### Specific Questions

1. Per-clip span fields are listed in the table above. Raw samples show that
   many bad clips were still all classified as `action`.
2. Post-delivery, replay-like, and pre-delivery frames become `action` because
   the classifier treats wide field cricket broadcast views as action unless
   there is explicit replay/ad/idle evidence.
3. In this run OpenScout did not classify replay as `replay`: match summary
   reports `scout_replay_pct=0.0`, and the delivery metadata has
   `frame_class="action"`. The aggregator grouped already-action frames; it
   did not merge committed `replay` spans into action spans.
4. Writer padding adds at most ±1s. The span itself is wrong or too broad in
   most BAD cases.
5. `1.2` was missed while `1.3` was captured because the `delivery_0002` span
   starts at `1.2` scoreboard context and remains open through `1.3`; the
   manual delivery identity is the later actual delivery inside the same
   broad action span. The classifier/aggregator did not create a close/open
   boundary between the pre/post `1.2` frames and the `1.3` action.
6. `delivery_0008` cuts just before `2.2` release because the stats-graphic
   wide field frames around `KL RAHUL v RIGHT ARM SEAMERS` were classified
   as `action` and committed as their own span before the actual release.
7. Smallest fix should start with classifier tightening plus span boundary
   rules, not padding. Padding adjustment alone cannot fix false action spans.

### Patch Recommendation

Recommended first patch: tighten OpenScout action classification and then add
one span-boundary guard.

Exact target files:

- `files/eyes/open_scout.py`: update `OPEN_PROMPT` to force an explicit
  delivery-phase line or tag, distinguishing `pre_delivery_setup`,
  `release_or_shot`, `post_delivery`, `replay_like`, and `graphic`.
- `files/eyes/open_scout_classify.py`: stop treating generic `"wide field
  view"` as action by itself. Require a strong delivery signal for `action`:
  `release`, `delivery stride`, `ball visible/airborne`, `bat contact`,
  `mid-swing`, `keeper/fielder reacting to live ball`, or equivalent. Add
  negatives for `post delivery`, `walking back`, `replay-like`, sponsor/view
  count overlays, stats graphics, and `"preparing for next delivery"` without
  ball/release evidence.
- `files/eyes/span_aggregator.py`: after classifier tightening, close an
  `action` span when the next observation is `other/replay/ad` or when text
  indicates `post_delivery`/graphic, instead of absorbing one dissenting
  frame for action spans. Keep one-frame absorption for non-action spans if
  needed.

Do not change `OpenScoutDeliveryWriter` padding as the first fix. It is useful
for audit context and is not the source of the broad false spans.

## 8. `dNNN` Regression Status After Track 1 Patches

The immediate Track 2 regression under review is the `dNNN` score-event window
family:

- `files/logs/deliveries/replay_kkrdc_10min_20260526_204204/d*/`
- `files/logs/deliveries/replay_kkrdc_10min_combined_20260526_222335/d*/`
- `files/logs/deliveries/replay_kkrdc_10min_final_20260526_231727/d*/`

Interpretation:

1. `dNNN` window quality regressed after the Track 1 event-stream changes.
2. The regression was not caused by delayed fallback itself, because
   `replay_kkrdc_10min_20260526_204204` had mostly good delayed fallback
   windows.
3. The likely regression source was bad Track 1 event boundaries: duplicate
   `Wd`, stale queued legal `DOT`, and post-ad scoreless legal tick.
4. The duplicate/stale-event causes were patched in `files/eyes/commentary.py`.
   The post-ad scoreless legal tick guard was patched in both
   `files/eyes/commentary.py` and `files/test_pipeline.py`.
5. `dNNN` quality is not validated yet after the post-ad guard. It requires one
   bounded video rerun before declaring the score-event fallback regression
   fixed.
6. OpenScout continuous clip quality remains a separate issue. The continuous
   `delivery_*.mp4` labels in section 7 diagnose classifier/span quality, not
   whether the `dNNN` delayed fallback regression is fixed.

## 9. Clean Guard-Strip Validation

Session: `replay_kkrdc_10min_guardstrip_clean_20260527_100933`.

Preflight passed before the run: `files/match_state_cache.json` was removed and
immediately verified absent (`CACHE_PREFLIGHT=absent`). The replay logged
`[CACHE] No cached state found — starting fresh`, and no `HOT-RESUME` marker
appeared. The prior `replay_kkrdc_10min_guardstrip_20260527_022855` run is
discarded for validation because it hot-resumed from stale cache at
`24/0 (2.5)`.

Track 1 clean-run result: `matched=11`, `missing=1`, `phantom=1`,
`divergences=111`. The guard-strip target behavior is confirmed: `1.3 DOT`
emitted, the false scoreless `2.1 DOT` stayed gone, the real `2.1 1_RUNS`
emitted correctly, and duplicate `Wd` stayed absent. `loop_e429_total=0`.

dNNN result: `12` delivery-window mp4s were produced. Source counts are
`v3_chunker_fallback=11` and `retrospective_span=1`. `d002` is now
`1.3 DOT` via fallback (`event_ts-24.0s` to `event_ts-4.0s`,
`retrospective_span_safe_margin_s=null`), not the earlier `1.2` event.

OpenScout audit result: metadata/audit fields are present. All `12/12`
delivery mp4s exist. There are `4` non-action metadata files but only `3`
non-action mp4s, so one non-action mp4 is missing; mark this as a low-priority
audit artifact issue.

Residuals after the clean run:

1. Remaining missing GT ball: `1.1`.
2. Remaining phantom: `2.6`.
3. `dNNN` manual review is pending for this clean session.
4. OpenScout non-action missing mp4 is a low-priority audit issue.

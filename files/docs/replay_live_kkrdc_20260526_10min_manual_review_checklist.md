# KKR/DC 10-Minute Manual Review Checklist

Session: `replay_kkrdc_10min_combined_20260526_222335`

Use this review in two passes. Checklist A judges OpenScout continuous clips independently of Track 1. Checklist B judges score-event `dNNN` delivery windows, where false or duplicate Track 1 score events can create false Track 2 windows.

Source context: `files/docs/replay_live_kkrdc_20260526_10min_track2_root_cause.md`

## Checklist A: OpenScout Continuous Clips

Artifact root: `files/logs/openscout_deliveries/replay_kkrdc_10min_combined_20260526_222335/`

Note: this directory currently exposes `delivery_000N_metadata.json` files for eight action spans. `delivery_*.mp4` files were not found by the workspace glob, so each row lists the expected clip filename from metadata for manual filesystem verification.

- [ ] `delivery_0001.mp4` metadata `delivery_0001_metadata.json`
  - Span: `1779805525.878-1779805541.645`, duration `15.767s`, band `long`, frames `4`
  - Review label: OK / PARTIAL / BAD
  - Delivery identity if obvious: TBD
  - Duplicate/split with adjacent OpenScout clip? TBD

- [ ] `delivery_0002.mp4` metadata `delivery_0002_metadata.json`
  - Span: `1779805575.585-1779805582.084`, duration `6.499s`, band `normal`, frames `2`
  - Review label: OK / PARTIAL / BAD
  - Delivery identity if obvious: TBD
  - Duplicate/split with adjacent OpenScout clip? TBD

- [ ] `delivery_0003.mp4` metadata `delivery_0003_metadata.json`
  - Span: `1779805608.236-1779805660.327`, duration `52.091s`, band `long`, frames `9`
  - Review label: OK / PARTIAL / BAD
  - Delivery identity if obvious: TBD
  - Duplicate/split with adjacent OpenScout clip? TBD

- [ ] `delivery_0004.mp4` metadata `delivery_0004_metadata.json`
  - Span: `1779805711.847-1779805725.267`, duration `13.421s`, band `normal`, frames `3`
  - Review label: OK / PARTIAL / BAD
  - Delivery identity if obvious: TBD
  - Duplicate/split with adjacent OpenScout clip? TBD

- [ ] `delivery_0005.mp4` metadata `delivery_0005_metadata.json`
  - Span: `1779805766.390-1779805772.891`, duration `6.501s`, band `normal`, frames `2`
  - Review label: OK / PARTIAL / BAD
  - Delivery identity if obvious: TBD
  - Duplicate/split with adjacent OpenScout clip? TBD

- [ ] `delivery_0006.mp4` metadata `delivery_0006_metadata.json`
  - Span: `1779805915.970-1779805926.739`, duration `10.769s`, band `normal`, frames `3`
  - Review label: OK / PARTIAL / BAD
  - Delivery identity if obvious: TBD
  - Duplicate/split with adjacent OpenScout clip? TBD

- [ ] `delivery_0007.mp4` metadata `delivery_0007_metadata.json`
  - Span: `1779806041.691-1779806048.192`, duration `6.501s`, band `normal`, frames `2`
  - Review label: OK / PARTIAL / BAD
  - Delivery identity if obvious: TBD
  - Duplicate/split with adjacent OpenScout clip? TBD

- [ ] `delivery_0008.mp4` metadata `delivery_0008_metadata.json`
  - Span: `1779806064.918-1779806071.523`, duration `6.605s`, band `normal`, frames `2`
  - Review label: OK / PARTIAL / BAD
  - Delivery identity if obvious: TBD
  - Duplicate/split with adjacent OpenScout clip? TBD

## Checklist B: Score-Event `dNNN` Windows

Artifact root: `files/logs/deliveries/replay_kkrdc_10min_combined_20260526_222335/dNNN/`

- [ ] `d001`
  - Event: `1.1 DOT`
  - Window source: `v3_chunker_fallback`, reason `retrospective_span_rejected_too_close_to_event`
  - Clip: `1779805522.137-1779805542.137`
  - Current manual label: TBD
  - Likely failure source: Track 2 window selection / duplicate-split candidate with `d002`; Track 1 event itself is valid.

- [ ] `d002`
  - Event: `1.2 1_RUNS`
  - Window source: `v3_chunker_fallback`, reason `v3_and_legacy_returned_none`
  - Clip: `1779805541.788-1779805561.788`
  - Current manual label: TBD
  - Likely failure source: Track 2 window selection / duplicate-split candidate with `d001`; Track 1 event itself is valid.

- [ ] `d003`
  - Event: `1.3 DOT`
  - Window source: `v3_chunker_fallback`, reason `v3_and_legacy_returned_none`
  - Clip: `1779805624.702-1779805644.702`
  - Current manual label: TBD
  - Likely failure source: Track 2 window selection / adjacent-gap candidate with `d004`; Track 1 event itself is valid.

- [ ] `d004`
  - Event: `1.4 DOT`
  - Window source: `v3_chunker_fallback`, reason `v3_and_legacy_returned_none`
  - Clip: `1779805648.836-1779805668.836`
  - Current manual label: TBD
  - Likely failure source: Track 2 window selection / adjacent-gap candidate with `d003`; Track 1 event itself is valid.

- [ ] `d005`
  - Event: `1.4 EXTRA`
  - Window source: `v3_chunker_fallback`, reason `v3_and_legacy_returned_none`
  - Clip: `1779805692.322-1779805712.322`
  - Current manual label: TBD
  - Likely failure source: score-event timing convention; Track 1 exports this wide as GT slot `1.5`, but the runtime event is still keyed internally as `1.4`.

- [ ] `d006`
  - Event: `1.5 DOT`
  - Window source: `v3_chunker_fallback`, reason `retrospective_span_rejected_too_close_to_event`
  - Clip: `1779805753.823-1779805773.823`
  - Current manual label: TBD
  - Likely failure source: Track 2 window selection / duplicate-split candidate with `d007`; Track 1 event itself is the legal dot after the wide.

- [ ] `d007`
  - Event: `1.5 EXTRA`
  - Window source: `v3_chunker_fallback`, reason `v3_and_legacy_returned_none`
  - Clip: `1779805771.638-1779805791.638`
  - Current manual label: TBD
  - Likely failure source: Track 1 duplicate/false extra boundary; this is the second `Wd` artifact that drives extras divergence.

- [ ] `d008`
  - Event: `2.0 DOT`
  - Window source: `v3_chunker_fallback`, reason `retrospective_span_rejected_too_close_to_event`
  - Clip: `1779805850.192-1779805870.192`
  - Current manual label: TBD
  - Likely failure source: Track 1 duplicate/rollover boundary; candidate adjacent-gap issue with `d009`.

- [ ] `d009`
  - Event: `2.1 1_RUNS`
  - Window source: `retrospective_span`, reason `latest_bowlers_end_span`
  - Clip: `1779805873.734-1779805877.234`
  - Selected span bounds: `1779805875.734-1779805875.734`
  - Current manual label: TBD
  - Likely failure source: Track 2 retrospective window selection / adjacent-gap candidate with `d008`; Track 1 event is a real `2.1` run but appeared as `2.1#1` in the diff because of the prior phantom `2.1` snapshot.

- [ ] `d010`
  - Event: `2.2 1_RUNS`
  - Window source: `v3_chunker_fallback`, reason `v3_and_legacy_returned_none`
  - Clip: `1779805907.797-1779805927.797`
  - Current manual label: TBD
  - Likely failure source: Track 2 window selection if bad; Track 1 event itself is valid.

- [ ] `d011`
  - Event: `2.3 DOT`
  - Window source: `v3_chunker_fallback`, reason `v3_and_legacy_returned_none`
  - Clip: `1779805962.117-1779805982.117`
  - Current manual label: TBD
  - Likely failure source: Track 2 window selection if bad; Track 1 event itself is valid.

- [ ] `d012`
  - Event: `2.4 SIX`
  - Window source: `v3_chunker_fallback`, reason `v3_and_legacy_returned_none`
  - Clip: `1779806005.346-1779806025.346`
  - Current manual label: TBD
  - Likely failure source: Track 2 window selection if bad; Track 1 event itself is valid, though striker attribution remains cold-start polluted.

- [ ] `d013`
  - Event: `2.5 SIX`
  - Window source: `v3_chunker_fallback`, reason `v3_and_legacy_returned_none`
  - Clip: `1779806052.910-1779806072.910`
  - Current manual label: TBD
  - Likely failure source: Track 1 score/token mismatch or source-clip alignment if the clip shows GT `4`; Track 2 window selection if the delivery footage is wrong.

## Adjacent dNNN Pairs To Check First

- [ ] `d001/d002`: clip ranges touch/overlap by `0.35s`; verify whether the same real delivery is split.
- [ ] `d003/d004`: next starts `4.13s` after previous end; verify whether the same real delivery is duplicated across adjacent windows.
- [ ] `d006/d007`: ranges overlap by `2.19s`; also crosses the legal-dot / duplicate-wide area.
- [ ] `d008/d009`: next starts `3.54s` after previous end; verify whether `2.0 DOT` false rollover and real `2.1` run are split or duplicated.

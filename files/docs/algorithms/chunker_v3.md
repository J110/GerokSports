# Chunker v3 — cricket-broadcast delivery-window detection

Status: shadow-only on first deploy (`USE_V3_CHUNKER=1`,
`USE_V3_CHUNKER_SPANS=0`).  Cutover gates in
`files/docs/operations/chunker_v3_setup.md`.

v3 is a **rule-based**, **time-based** per-frame labeller and chunker.
It ingests the same per-frame Scout payloads that the OpenScout
result-sink already publishes (cam, phase, v2_broadcast_tag, v2_class,
open_desc) and emits a single consequential delivery window per score
event.

The v3.1 confidence-scored variant was rejected (10/4/4/0 vs the v3
rule-based baseline of 10/7/1/0).  The constants below are reused
verbatim from `v3_1_simulation.py`; the *algorithm logic* is rule-based
per Section A and B.

## A. Per-frame label rules

### Priority order (highest → lowest)

```
AD > DRS > REPLAY > UMPIRE_SIGNAL > DELIVERY_ACTION > NON_DELIVERY_ACTION
```

The first rule whose predicate fires wins.  `NON_DELIVERY_ACTION` is
the residual.

### Cricket invariants (drive the predicates)

- **Live delivery never shows crowd as foreground.**  Any frame whose
  `open_desc` has *crowd-as-subject* terms together with action verbs
  → REPLAY (regardless of `prod_cam`).
- **Bowlers_end view of a real delivery always names batter, stumps,
  or wicket.**  Bowler running/throwing without a batter mention is
  practice/warmup, not a delivery.
- **Umpire signals only matter post-delivery.**  Pre-delivery umpire
  frames are non-consequential and never anchor a window.
- **"Umpire" must be the SUBJECT of `open_desc`, not hypothetical.**
  "or the umpire", "possibly the umpire", "to a teammate or the
  umpire" → reject.
- **Replay segments are contiguous.**  A confirmed REPLAY anchor
  propagates through ambiguous neighbors in **both** directions.
- **Career-stats and dismissal-figures overlay = REPLAY**, regardless
  of `v2_broadcast_tag`.  The graphic itself is the replay marker.
- **Slow-mo / "moments earlier" / "moments ago" / "previous" = REPLAY.**
- **Celebration with crowd-as-subject = REPLAY.**  Celebration with a
  player-only subject (raised arm, follow-through) is *delivery-tail*
  and stays in the delivery window — see Fix #2.

### Predicates (computed from `open_desc.lower()`)

Boolean predicates evaluated once per frame:

| Predicate | Source |
|---|---|
| `has_action_verb` | `ACTION_VERBS` substring match |
| `has_drs` | `DRS_KEYWORDS` substring match |
| `has_brand` | `BRAND_KEYWORDS` substring match |
| `has_live_ctx` | `LIVE_CONTEXT_TERMS` substring match (batter / stumps / wicket / crease) |
| `has_celeb_player` | `CELEBRATION_TERMS_PLAYER` substring match |
| `has_celeb_crowd` | `CELEBRATION_TERMS_CROWD` substring match |
| `has_crowd_subj` | `CROWD_AS_SUBJECT_TERMS` substring match |
| `has_slowmo` | `SLOWMO_TERMS` substring match |
| `has_no_players` | `NO_PLAYERS_TERMS` substring match |
| `has_career_stats` | `CAREER_STATS_REGEX` OR `MATCH_OVERLAY_REGEX` (case-sensitive on raw text) |
| `has_dismissal` | `DISMISSAL_REGEX` (case-sensitive on raw text) |
| `has_explicit_umpire` | `EXPLICIT_UMPIRE` substring match |
| `has_hypothetical_umpire` | `HYPOTHETICAL_UMPIRE` substring match |
| `has_signaling_verb` | `SIGNALING_VERBS` substring match |
| `is_replay_tag` | `v2_broadcast_tag.upper() in {REPLAY, SLO-MO, TELESTRATOR, SPLIT-SCREEN}` |
| `is_delivery_phase` | `prod_phase in {release, flight, shot, post_shot, runup}` |

Keyword tables are imported from `files/eyes/chunker_v3.py` —
copied verbatim from the v3.1 simulation constants.

### Label decision (priority order)

```
AD if:
    prod_cam == "ad"  OR
    prod_phase == "advertisement"  OR
    (prod_cam == "graphic" AND has_brand AND has_no_players)  OR
    (ts <= 3.0s AND prod_cam == "graphic" AND has_no_players)

DRS if:
    has_drs

REPLAY if:
    is_replay_tag  OR
    has_career_stats  OR
    has_dismissal  OR
    has_slowmo  OR
    (has_crowd_subj AND has_action_verb)  OR  # crowd-as-subject + action
    has_celeb_crowd                            # explicit crowd celebration
    # NOTE: has_celeb_player alone does NOT trigger REPLAY (Fix #2)

UMPIRE_SIGNAL if:
    has_explicit_umpire AND
    NOT has_hypothetical_umpire AND
    has_signaling_verb AND
    prod_cam != "bowlers_end"

DELIVERY_ACTION if any of:
    (a) is_delivery_phase AND has_live_ctx AND NOT has_crowd_subj AND NOT is_replay_tag
    (b) has_action_verb AND prod_cam in {bowlers_end, side_on} AND has_live_ctx
    (c) v2_class == "action" AND prod_cam in {bowlers_end, side_on}
        AND is_delivery_phase AND has_live_ctx
        # path (c) is the strict bowlers_end live-delivery anchor

else:
    NON_DELIVERY_ACTION
```

### Solo prod_phase rejection (post-label demotion)

A frame labeled `DELIVERY_ACTION` whose **only** support is rule (a)
(`is_delivery_phase` plus `has_live_ctx`) — i.e. no `has_action_verb`,
no `v2_class == "action"` — is demoted to `NON_DELIVERY_ACTION` unless:

- another `DELIVERY_ACTION` frame exists within ±1.5 s, OR
- another supporting frame (action-verb OR `v2_class == "action"`)
  exists within ±2.0 s.

Rationale: a single `prod_phase=release` tag with no corroborating
prose or v2 class is almost always a Scout false positive.

## B. Chunking rules (TIME-BASED)

All thresholds are seconds, not frame counts.  At post-decoupled
OpenScout cadence (~1.0–1.3 s median) frame-count thresholds drift
unpredictably; time thresholds are stable across cadence regimes.

### B.1 Anchor confirmation

A `DELIVERY_ACTION` chunk is **confirmed** if either:

(i) ≥2 supporting `DELIVERY_ACTION` frames within a **4 s** window, OR

(ii) 1 `is_delivery_phase` frame + ≥1 `has_action_verb` frame within
     ±2 s of each other.

Unconfirmed chunks survive but are not eligible to seed a delivery
window.

### B.2 Replay forward + backward propagation (Fix #1)

From any confirmed `REPLAY` frame, walk **forward** and then
**backward** through ambiguous frames.  An ambiguous frame is one
where:

- `v2_class == "action"` AND `is_delivery_phase`, OR
- `open_desc` has crowd / celebration / career-stats / slow-mo terms.

The walk stops on each side when the **first** of these conditions
is met:

- 3 consecutive *live-anchor* frames, OR
- 4 s of accumulated live-anchor time.

A *live-anchor* frame has all of:

- `prod_cam in {bowlers_end, side_on}`,
- `has_live_ctx` (batter / stumps / wicket mention),
- NOT `has_crowd_subj`,
- NOT `has_career_stats`.

### B.3 Cluster-merge (Fix #3)

Two confirmed chunks of the **same label** within 10 s of each other
are merged if and only if the inter-chunk gap contains only:

- `NON_DELIVERY_ACTION`, or
- `pre_post` frames (start-of-clip / end-of-clip residual).

The merge is rejected if the gap contains any of:

- AD, REPLAY, DRS, OR
- a graphic-block lasting > 2 s (≥2 contiguous frames with
  `prod_cam == "graphic"`).

### B.4 Celebration tightening (Fix #2)

`has_celeb_player` ALONE never triggers REPLAY.  A single batter
raising their bat / arm in a delivery-tail frame stays in the
delivery window.  Crowd-as-subject (`has_crowd_subj` OR
`has_celeb_crowd`) is required for a celebration → REPLAY promotion.

### B.5 Window construction

Given the merged confirmed `DELIVERY_ACTION` cluster
`(cluster_start, cluster_end)`:

1. **Lookback up to 4 s** from `cluster_start` through
   `NON_DELIVERY_ACTION` frames.  Halt at any AD / REPLAY / DRS /
   graphic-block (≥2 frames `prod_cam == "graphic"`) boundary.
2. **Forward up to 4 s** from `cluster_end` through
   `NON_DELIVERY_ACTION` frames.  Same halt conditions.
3. **Append post-delivery UMPIRE_SIGNAL chunks** that start within
   3 s after `cluster_end` (extends `cluster_end` to that chunk's
   end).
4. **Append DRS chunks** that start within 5 s after `cluster_end`
   (extends `cluster_end` to that chunk's end).

If no confirmed `DELIVERY_ACTION` cluster exists, return `None`.

## C. The three fixes (recap)

1. **Bidirectional REPLAY propagation** — confirmed REPLAY frame
   walks both forward and backward.  Each side stops at 3 consecutive
   live-anchor frames OR 4 s of live anchor (whichever comes first —
   keeps it time-based for slow cadences).  See B.2.
2. **Celebration rule tightened** — REPLAY only fires on celebration
   if open_desc has crowd-as-subject AND celebration verb.  Single
   player raising arm without crowd subject stays in the delivery
   window.  See B.4.
3. **Cluster-merge** — same-label chunks within 10 s merge if the
   gap contains no replay/ad/drs/graphic-block.  See B.3.

## D. Outputs

`find_consequential_window(frames, event_ts) → (start_ts, end_ts) |
None`.

`event_ts` is optional — when supplied, the chunker prefers the
cluster whose end is closest to (and not after) `event_ts` if multiple
confirmed clusters exist.  When omitted, the largest cluster wins
(matches the v3 simulation's `consequential_windows` selection).

## E. Cost

Pure CPU.  No new API calls.  Reuses cached Scout outputs from the
OpenScout sidecar / `result_sink` payloads.

## F. References

- `/Users/anmolmohan/Projects/SportsComm/v3_1_simulation.py` —
  canonical keyword constants (constants only; algorithm logic
  diverges per this spec).
- `/Users/anmolmohan/Projects/SportsComm/v3_simulation_results.txt` —
  v3 rule-based baseline (10 MATCH / 7 PARTIAL / 1 WRONG / 0 FP /18).
- `files/scripts/broadcast_mode_tuning/chunk_v1_combined_data.csv` —
  test-fixture source (3204 rows; 18 cached clips).
- `files/docs/operations/chunker_v3_setup.md` — cutover gates.
- `files/eyes/chunker_v3.py` — pure-function implementation.
- `files/eyes/chunker_v3_aggregator.py` — production wiring
  (`V3SpanAggregator`, mirrors `SpanAggregator` interface).

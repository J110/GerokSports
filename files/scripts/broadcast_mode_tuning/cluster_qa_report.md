# Cluster QA report

Model: `llama-3.3-70b-versatile` · 7 blocks · wall time 4.7s.

Detection verdict for every block is DELIVERY (these are the blocks emitted by `detect_delivery_zones.detect_blocks`).

## Summary table

| Block | Range | Reasoner | Conf | Evidence t | Splits | Gate |
|---|---|---|---|---|---|---|
| 1 | 101-110s (9s) | `UNCERTAIN` | 0.2 | null | - | DROP (label=UNCERTAIN) |
| 2 | 122-147s (25s) | `DELIVERY` | 0.8 | 143.0 | - | KEEP |
| 3 | 161-164s (3s) | `UNCERTAIN` | 0.4 | null | - | DROP (label=UNCERTAIN) |
| 4 | 176-179s (3s) | `NON_LIVE` | 0.8 | null | - | DROP (label=NON_LIVE) |
| 5 | 182-197s (15s) | `NON_LIVE` | 0.8 | null | - | DROP (label=NON_LIVE) |
| 6 | 234-244s (10s) | `UNCERTAIN` | 0.2 | null | - | DROP (label=UNCERTAIN) |
| 7 | 272-278s (6s) | `UNCERTAIN` | 0.4 | null | - | DROP (label=UNCERTAIN) |

**Evidence-in-range sanity**: 1/1 DELIVERY-labeled clusters have `evidence_frame_t` inside their window (100%). Should be 100%; deviations indicate hallucinated timestamps.

## Block 1: t=101-110s (9s, 10 frames)

- **Reasoner**: `UNCERTAIN` (confidence 0.2)
- Evidence frame: null
- Aggregate signals: `{'V': 2, 'S': 5, 'M': 9, 'W': 7, 'K': 10}`
- Path attribution: `{'A': 1, 'B': 0, 'C': 4, 'none': 5}`
- Gate: **DROP** (label=UNCERTAIN)
- Reason: No frame shows clear bowler's-end framing with a live delivery, and the action level appears to be between deliveries or pre-match activities.

## Block 2: t=122-147s (25s, 26 frames)

- **Reasoner**: `DELIVERY` (confidence 0.8)
- Evidence frame: t=143.0s
- Aggregate signals: `{'V': 11, 'S': 11, 'M': 23, 'W': 14, 'K': 21}`
- Path attribution: `{'A': 4, 'B': 4, 'C': 2, 'none': 16}`
- Gate: **KEEP** (kept)
- Reason: The frame at 143.0s shows the clearest bowler's-end framing with the bowler having just released the ball and the batter standing ready, along with a score graphic at the bottom displaying the current score.

## Block 3: t=161-164s (3s, 4 frames)

- **Reasoner**: `UNCERTAIN` (confidence 0.4)
- Evidence frame: null
- Aggregate signals: `{'V': 3, 'S': 2, 'M': 4, 'W': 4, 'K': 2}`
- Path attribution: `{'A': 2, 'B': 1, 'C': 0, 'none': 1}`
- Gate: **DROP** (label=UNCERTAIN)
- Reason: No frame shows clear bowler's-end framing, follow-through, or ball release, but frame t=163.0 shows a bowler in follow-through position, suggesting potential live play.

## Block 4: t=176-179s (3s, 4 frames)

- **Reasoner**: `NON_LIVE` (confidence 0.8)
- Evidence frame: null
- Aggregate signals: `{'V': 1, 'S': 3, 'M': 3, 'W': 4, 'K': 3}`
- Path attribution: `{'A': 0, 'B': 0, 'C': 2, 'none': 2}`
- Gate: **DROP** (label=NON_LIVE)
- Reason: No frame in the cluster shows a clear bowler's-end framing, ball release, or follow-through, and the score graphics do not display over count and batter runs, indicating this is not a live delivery.

## Block 5: t=182-197s (15s, 16 frames)

- **Reasoner**: `NON_LIVE` (confidence 0.8)
- Evidence frame: null
- Aggregate signals: `{'V': 8, 'S': 12, 'M': 13, 'W': 6, 'K': 13}`
- Path attribution: `{'A': 4, 'B': 1, 'C': 3, 'none': 8}`
- Gate: **DROP** (label=NON_LIVE)
- Reason: No frame shows live delivery framing with bowler's-end camera angle, and the action level appears to be between deliveries or post-action moments.

## Block 6: t=234-244s (10s, 11 frames)

- **Reasoner**: `UNCERTAIN` (confidence 0.2)
- Evidence frame: null
- Aggregate signals: `{'V': 6, 'S': 7, 'M': 10, 'W': 10, 'K': 7}`
- Path attribution: `{'A': 4, 'B': 0, 'C': 2, 'none': 5}`
- Gate: **DROP** (label=UNCERTAIN)
- Reason: No frame shows clear bowler's-end framing with a ball release or follow-through, and the action level appears to be between deliveries or pre-delivery moments.

## Block 7: t=272-278s (6s, 7 frames)

- **Reasoner**: `UNCERTAIN` (confidence 0.4)
- Evidence frame: null
- Aggregate signals: `{'V': 2, 'S': 5, 'M': 7, 'W': 6, 'K': 7}`
- Path attribution: `{'A': 1, 'B': 1, 'C': 3, 'none': 2}`
- Gate: **DROP** (label=UNCERTAIN)
- Reason: No frame shows clear live-delivery framing with bowler's-end view, ball release, or follow-through, despite a bowler being in motion at t=276.0s, the action level appears to be just before the delivery of the ball.

## Disagreement highlights

- **Block 2 (25 s)** classified `DELIVERY` — model did NOT detect the bridged-deliveries case despite duration > 12 s.

- **Block 3 (3 s)** classified `UNCERTAIN`.
- **Block 4 (3 s)** classified `NON_LIVE`.

## Truth check

- **1st delivery** (100-115s) covered by Block 1 (101-110s) → reasoner `UNCERTAIN` splits=[]
- **2nd delivery** (122-128s) covered by Block 2 (122-147s) → reasoner `DELIVERY` splits=[]

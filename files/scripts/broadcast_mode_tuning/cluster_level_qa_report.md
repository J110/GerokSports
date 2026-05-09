# Cluster-level QA report

Model: `llama-3.3-70b-versatile` · 15 clusters built · 15 called · wall 14.0s.
Cluster builder: gap_max=2, min_run=1, signal=V|S|M|W|K.

## Cluster table

| ID | Window | Frames | Signals | Paths | #Live | #Replay | Live moments | Conf | Gate |
|---|---|---|---|---|---|---|---|---|---|
| 2 | 101.0-103.0s (2.0s) | 3 | 0/3/3/3/3 | 0/0/3/0 | 0 | 0 | — | 1.0 | DROP (no-live-moments) |
| 3 | 109.0-110.0s (1.0s) | 2 | 1/2/2/2/2 | 1/0/1/0 | 1 | 0 | t=109.0: The camera shows a wide field view of the cricket pitch, capturing several playe | 0.8 | KEEP |
| 1 | 63.0-65.0s (2.0s) | 3 | 2/2/2/3/2 | 2/0/0/1 | 0 | 0 | — | 1.0 | DROP (no-live-moments) |
| 4 | 122.0-128.0s (6.0s) | 7 | 5/0/7/7/6 | 0/4/0/3 | 2 | 0 | t=122.0: The camera shows a wide field view of a cricket match with six players on the fi; t=126.0: The camera shows a wide field view of a cricket pitch with players positioned ar | 0.8 | KEEP |
| 5 | 134.0-134.0s (0.0s) | 1 | 1/1/0/0/1 | 1/0/0/0 | 0 | 0 | — | 1.0 | DROP (no-live-moments) |
| 6 | 141.0-147.0s (6.0s) | 7 | 3/6/6/5/5 | 3/0/2/2 | 1 | 0 | t=143.0: The bowler appears to have just released the ball, and the batter is standing re | 0.8 | KEEP |
| 7 | 161.0-164.0s (3.0s) | 4 | 3/2/4/4/2 | 2/1/0/1 | 1 | 0 | t=163.0: The players are positioned around the pitch, with two batters standing at the wi | 0.8 | KEEP |
| 8 | 172.0-173.0s (1.0s) | 2 | 1/2/2/2/2 | 1/0/1/0 | 0 | 0 | — | 1.0 | DROP (no-live-moments) |
| 9 | 176.0-179.0s (3.0s) | 4 | 1/3/3/4/3 | 0/0/2/2 | 0 | 0 | — | 1.0 | DROP (no-live-moments) |
| 10 | 182.0-185.0s (3.0s) | 4 | 3/4/3/1/3 | 3/0/1/0 | 0 | 0 | — | 1.0 | DROP (no-live-moments) |
| 11 | 192.0-197.0s (5.0s) | 6 | 4/3/6/5/5 | 1/1/2/2 | 1 | 0 | t=195.0: The bowler, wearing a teal uniform, appears to have just released the ball, whic | 0.8 | KEEP |
| 12 | 224.0-224.0s (0.0s) | 1 | 1/0/1/1/1 | 0/1/0/0 | 0 | 0 | — | 1.0 | DROP (no-live-moments) |
| 13 | 234.0-244.0s (10.0s) | 11 | 6/7/10/10/7 | 4/0/2/5 | 0 | 0 | — | 0.8 | DROP (no-live-moments) |
| 14 | 259.0-261.0s (2.0s) | 3 | 3/0/3/3/3 | 0/3/0/0 | 0 | 0 | — | 1.0 | DROP (no-live-moments) |
| 15 | 272.0-278.0s (6.0s) | 7 | 2/5/7/6/7 | 1/1/3/2 | 1 | 0 | t=276.0: The camera shows a wide field view of a cricket pitch with six people on it. The | 0.8 | KEEP |

## Anchor groups (merge gap <= 8s, no min-duration filter — singletons retained)

| ID | #Anchors | Earliest | Latest | Source clusters | Anchors (t @ cluster) | Evidence |
|---|---|---|---|---|---|---|
| 1 | 1 | 109.0s | 109.0s | 3 | 109.0@c3 | The camera shows a wide field view of the cricket pitch, capturing several players and the umpire. The bowler in a light blue uniform is in mid-action, with his right arm extended upward as if he has just released the ball, while the batter in an orange uniform stands ready with his bat. |
| 2 | 2 | 122.0s | 126.0s | 4 | 122.0@c4, 126.0@c4 | The camera shows a wide field view of a cricket match with six players on the field. The bowler is in the process of delivering the ball, with their arm raised and about to release it, while the batter stands ready with their bat and the wicketkeeper crouches behind them. // The camera shows a wide field view of a cricket pitch with players positioned around it. A bowler in a light blue uniform appears to be in the process of bowling, with their arm extended, while two batters in orange and purple uniforms stand at the wickets, one holding a bat and the other walking behind. |
| 3 | 1 | 143.0s | 143.0s | 6 | 143.0@c6 | The bowler appears to have just released the ball, and the batter is standing ready. |
| 4 | 1 | 163.0s | 163.0s | 7 | 163.0@c7 | The players are positioned around the pitch, with two batters standing at the wickets, a bowler in a follow-through position with their right arm raised, a wicketkeeper crouched behind the wickets, and three fielders standing in various positions. |
| 5 | 1 | 195.0s | 195.0s | 11 | 195.0@c11 | The bowler, wearing a teal uniform, appears to have just released the ball, which is visible in mid-air, while the batter in an orange uniform stands ready. |
| 6 | 1 | 276.0s | 276.0s | 15 | 276.0@c15 | The camera shows a wide field view of a cricket pitch with six people on it. The bowler, wearing a teal uniform, is bending over and appears to be about to deliver the ball, while the batter, wearing an orange uniform, is standing with their back to the camera and holding a bat. |

## Truth check

- **1st delivery** (100-115s): 2 cluster(s) overlap [2,3], 1 with live moments [3], 1 moments inside truth window [3@109.0s].
- **2nd delivery** (122-128s): 1 cluster(s) overlap [4], 1 with live moments [4], 2 moments inside truth window [4@122.0s,4@126.0s].

## Gate metrics

- Clusters tested: 15
- Clusters with ≥1 live moment: 6
- Total live moments: 7
- Clusters kept (≥1 moment ∧ all moments in-range ∧ conf ≥ 0.6): 6
- Total anchors across kept clusters: 7
- Final anchor groups emitted: 6
- Moment-in-window sanity: 7/7 (100%; should be 100%)

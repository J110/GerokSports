# Stage 1 70b validation report

Window: 0-3600s · Pipeline clusters: 78 · Dropped candidates: 98 · 70b deliveries: 114 · Regions: 86 (86 ok, 0 errors)

## Drop categories
- FIX5_DROPPED: 3
- HARD_REJECT: 57
- MIN_RUN: 24
- PHANTOM_NOT_RESCUED: 14

## Summary
- agreed: **78**
- 70b-rejected: **0**
- 70b-reclassified: **0**
- 70b-rescued (drop-reversal): **7**
- 70b-found (no pipeline candidate): **29**

## 70b-rescued (drop-reversals, ranked by drop reason)
| drop_id | reason | start | end | conf | outcome | evidence |
|---|---|---|---|---|---|---|
| d20 | MIN_RUN | 1807.0 | 1807.0 | 0.6 | UNKNOWN | Frame 1807 shows a batter preparing to bat, and frame 1808 shows a player walking towards the wickets, suggesting a potential delivery. |
| d23 | MIN_RUN | 2358.0 | 2358.0 | 0.6 | UNKNOWN | Frame t=2358.0 shows a player in motion, possibly having just bowled a ball. |
| d27 | PHANTOM_NOT_RESCUED | 2867.0 | 2869.0 | 0.8 | UNKNOWN | Frames t=2869.0 and t=2871.0 show a batter in motion and a fielder reacting to a play, indicating a live delivery. |
| d39 | FIX5_DROPPED | 1275.0 | 1278.0 | 0.7 | WICKET | Frames t=1277.0 and t=1278.0 show a bowler in a follow-through position and a player celebrating, respectively. |
| d86 | HARD_REJECT | 3071.0 | 3071.0 | 0.8 | WICKET | Frames t=3070.0 to t=3076.0 show a post-action moment with a wicket ball speed graphic and players celebrating. |
| d69 | HARD_REJECT | 1865.0 | 1868.0 | 0.7 | UNKNOWN | Frames t=1865.0-1868.0 show a bowler preparing to bowl and then running, indicating a live delivery. |
| d68 | HARD_REJECT | 1861.0 | 1863.0 | 0.6 | UNKNOWN | Frames t=1861.0-1863.0 show a bowler in motion, indicating a live delivery. |

## 70b-rejected
(none)

## 70b-reclassified
(none)

## 70b-found (pipeline never considered)
| start | end | outcome | conf | evidence |
|---|---|---|---|---|
| 0.0 | 1.0 | UNKNOWN | 0.8 | Frame t=0.0 shows the bowler mid-action, having just released the ball, and t=1.0 shows the batter focused on the bowler. |
| 122.0 | 123.0 | FOUR | 0.9 | Frames t=122.0 and t=123.0 show a bowler delivering the ball and a batter hitting it, with a 'FOUR' graphic displayed on the screen. |
| 125.0 | 126.0 | UNKNOWN | 0.7 | Frames t=125.0 and t=126.0 show a bowler delivering the ball, but the outcome is not clear. |
| 183.0 | 185.0 | UNKNOWN | 0.8 | Frames t=183.0 to t=185.0 show a bowler preparing to bowl or having just finished bowling. |
| 401.0 | 404.0 | RUNS | 0.8 | Frames t=401.0 to t=404.0 show a bowler about to deliver the ball, a batter preparing to hit, and subsequent fielder reactions. |
| 431.0 | 434.0 | UNKNOWN | 0.7 | Frames t=431.0 to t=434.0 show a bowler preparing to bowl and a batter standing at the wicket, indicating a potential delivery. |
| 576.0 | 578.0 | UNKNOWN | 0.7 | Frames t=576.0 to t=578.0 show a batter preparing to hit and the fielders positioned. |
| 594.0 | 597.0 | UNKNOWN | 0.7 | Frames t=594.0 to t=597.0 show a bowler celebrating and a player preparing to bowl. |
| 634.0 | 637.0 | WICKET | 0.9 | Frames t=634.0 to t=637.0 show a bowler throwing the ball, a batter swinging, and the wickets being knocked over. |
| 850.0 | 854.0 | UNKNOWN | 0.7 | Frames t=850.0, t=851.0, t=853.0, and t=854.0 show a batter swinging and a wicketkeeper crouched, indicating active play. |
| 923.0 | 924.0 | UNKNOWN | 0.9 | Frames t=923.0 to t=924.0 show a bowler running towards the wicket, indicating an active play moment. |
| 1012.0 | 1016.0 | UNKNOWN | 0.8 | Frames t=1012.0 to t=1016.0 show a bowler releasing the ball and a batter preparing to hit it. |
| 1028.0 | 1030.0 | UNKNOWN | 0.7 | Frames t=1028.0 to t=1030.0 show a batter swinging and a fielder crouched behind them. |
| 1157.0 | 1160.0 | UNKNOWN | 0.7 | Frames t=1157.0 to t=1160.0 show a bowler releasing the ball and a batter standing at the wicket. |
| 1164.0 | 1166.0 | RUNS | 0.9 | Frames t=1164.0 to t=1166.0 show a batter hitting the ball and running. |
| 1172.0 | 1183.0 | WICKET | 0.8 | Frames t=1172.0 to t=1183.0 show post-action moments with players celebrating, high-fiving, and a dismissed batter walking off the field. |
| 1281.0 | 1283.0 | FOUR | 0.9 | Frames t=1282.0 and t=1283.0 show a batter hitting the ball and a fielder trying to catch it, respectively. |
| 1285.0 | 1286.0 | UNKNOWN | 0.5 | Frame t=1285.0 shows a batter swinging at the ball, but the outcome is unclear. |
| 1447.0 | 1452.0 | WICKET | 0.8 | Frames t=1447.0 to t=1452.0 show a cricket ball in mid-air, a player's leg and foot, and graphical overlays indicating a wicket has fallen. |
| 1810.0 | 1811.0 | UNKNOWN | 0.9 | Frames 1810-1811 show a cricket ball in mid-air, indicating a live delivery. |
| 2247.0 | 2248.0 | UNKNOWN | 0.8 | Player reaction and diving catch in frames t=2247.0 and t=2248.0 |
| 2248.0 | 2257.0 | UNKNOWN | 0.8 | Frames t=2248.0 to t=2257.0 show a bowler releasing the ball and the batter reacting to the delivery. |
| 2259.0 | 2263.0 | UNKNOWN | 0.7 | Frames t=2259.0 to t=2263.0 show two players running and a fielder throwing the ball, indicating a possible delivery. |
| 2268.0 | 2269.0 | UNKNOWN | 0.9 | Frames t=2268.0 to t=2269.0 show a bowler about to throw the ball and a batter reacting to the delivery. |
| 2672.0 | 2673.0 | UNKNOWN | 0.8 | Frames t=2672.0 and t=2673.0 show a player swinging a bat and a wide field view of the cricket field, respectively. |
| 2698.0 | 2699.0 | UNKNOWN | 0.9 | Frame t=2698.0 shows a bowler in mid-stride and a batter poised to hit the ball. |
| 2726.0 | 2726.0 | UNKNOWN | 0.9 | Frame t=2726.0 shows a batter mid-swing with the ball visible in mid-air. |
| 2979.0 | 2981.0 | UNKNOWN | 0.7 | Frames t=2979.0 to t=2981.0 show a bowler releasing the ball and the fielders reacting. |
| 3545.0 | 3546.0 | UNKNOWN | 0.8 | The batter is in motion and the wicketkeeper is positioned to catch the ball at t=3545.0. |

## Per-cluster verdict
| cluster | anchor | path | verdict | 70b note |
|---|---|---|---|---|
| c1 | t=109.0s | A | agreed | Frames t=109.0 and t=110.0 show a bowler releasing the ball and a batter preparing to hit it. |
| c2 | t=143.0s | A | agreed | The bowler appears to have just released the ball at t=143.0s and the batter is standing ready, indicating a live delive |
| c3 | t=163.0s | B | agreed | Frames t=163.0 and t=164.0 show a bowler in a follow-through position and players reacting to the play, indicating a liv |
| c4 | t=195.0s | B | agreed | Frames t=194.0 to t=197.0 show a bowler preparing to deliver the ball and the subsequent reaction of the players. |
| c5 | t=239.0s | B | agreed | Frames t=237.0-240.0 show a bowler preparing to deliver and a batter hitting the ball, followed by a celebration and a ' |
| c6 | t=276.0s | B | agreed | Frames t=276.0 to t=281.0 show a bowler about to deliver the ball and players reacting to the play. |
| c7 | t=355.0s | B | agreed | Frames t=354.0 to t=356.0 show a bowler releasing the ball and a batter swinging. |
| c8 | t=388.0s | B | agreed | Frames t=388.0 to t=402.0 show a bowler delivering the ball, a batter hitting the ball, and subsequent fielder reactions |
| c9 | t=428.0s | B | agreed | Frames t=427.0 to t=429.0 show a bowler in mid-action and a batter standing ready, indicating a live delivery. |
| c10 | t=459.0s | B | agreed | Frames t=459.0 and t=460.0 show a bowler in follow-through and a batter hitting the ball. |
| c11 | t=511.0s | B | agreed | Frames t=511.0 and t=512.0 show a bowler delivering the ball and a batter preparing to hit. |
| c12 | t=545.0s | B | agreed | Frames t=539.0 to t=545.0 show a batter swinging and the fielders reacting. |
| c13 | t=617.0s | B | agreed | Frames t=626.0 to t=628.0 show a bowler releasing the ball and a batter preparing to hit it. |
| c14 | t=671.0s | B | agreed | Frames t=668.0 to t=675.0 show a bowler preparing to bowl, a batter hitting the ball, and the ball in mid-air, indicatin |
| c15 | t=712.0s | A | agreed | Frames t=711.0 and t=712.0 show a bowler releasing the ball and a batter preparing to hit it. |
| c16 | t=737.0s | D | agreed | Frames t=735.0 to t=738.0 show a batter playing a shot and fielders reacting. |
| c17 | t=763.0s | A | agreed | Frames t=763.0-767.0 show a wide field view of a cricket field with players positioned around it, indicating a live deli |
| c18 | t=788.0s | B | agreed | Frames t=788.0-790.0 show a bowler releasing the ball and a batter hitting a four, as indicated by the scoreboard and cr |
| c19 | t=840.0s | B | agreed | Frames t=841.0, t=847.0, and t=848.0 show a batter in motion, a 'FOUR' graphic, and a ball on the ground, respectively. |
| c20 | t=869.0s | D | agreed | Frames t=869.0 to t=872.0 show a player in a post-delivery moment, suggesting a recent ball was bowled. |
| c21 | t=909.0s | B | agreed | Frames t=909.0 to t=912.0 capture a bowler in mid-action, indicating an active play moment. |
| c22 | t=946.0s | B | agreed | The frame at t=958.0 shows a close-up shot of a cricket player celebrating after hitting a shot, as indicated by the wor |
| c23 | t=988.0s | B | agreed | The bowler is captured mid-run towards the wicket, having just released the ball, at t=988.0s. |
| c24 | t=1029.0s | B | agreed | Frames t=1029.0 to t=1031.0 show a bowler about to deliver the ball and subsequent celebration by the players. |
| c25 | t=1150.0s | B | agreed | Frames t=1148.0 to t=1150.0 show a bowler releasing the ball and a batter preparing to react. |
| c26 | t=1198.0s | D | agreed | The batter is seen hitting the ball and preparing to run at t=1198.0, and a player is running towards a white ball on th |
| c27 | t=1239.0s | A | agreed | Frames t=1238.0 to t=1242.0 show a bowler delivering the ball and fielders reacting to the play. |
| c28 | t=1269.0s | B | agreed | Frames t=1269.0 and t=1270.0 show a bowler delivering the ball and a batter swinging, respectively. |
| c29 | t=1307.0s | B | agreed | Frames t=1307.0 to t=1310.0 show a bowler in a follow-through position and a batter preparing to play a shot, followed b |
| c30 | t=1348.0s | B | agreed | Frames t=1348.0 to t=1353.0 show a bowler releasing the ball and the batter reacting to the delivery. |
| c31 | t=1418.0s | B | agreed | Frames t=1417.0-1429.0 show a delivery and subsequent wicket, with a 'WICKET' banner appearing in later frames (e.g., t= |
| c32 | t=1526.0s | A | agreed | Frames t=1525.0 to t=1536.0 show a bowler throwing the ball, a batter preparing to hit, and a wicket falling. |
| c33 | t=1551.0s | B | agreed | Frames t=1551.0 to t=1559.0 show a bowler releasing the ball, a batter swinging, and the ball being hit. |
| c34 | t=1575.0s | C | agreed | Frames t=1576.0-1579.0 show a player in mid-air throwing the ball and a batter preparing to hit, indicating a live deliv |
| c35 | t=1600.0s | A | agreed | Frames t=1600.0 to t=1606.0 show a bowler delivering the ball, a batter attempting to play a shot, and a wicketkeeper re |
| c36 | t=1658.0s | B | agreed | Frames t=1657.0 to t=1661.0 show a bowler releasing the ball and a batter preparing to hit it. |
| c37 | t=1727.0s | A | agreed | Frames t=1724.0 to t=1727.0 show a bowler in motion and a batter preparing to hit the ball. |
| c38 | t=1757.0s | B | agreed | The bowler is captured in mid-action, having just released the ball, at t=1757.0, and the batter is seen preparing to hi |
| c39 | t=1796.0s | C | agreed | Frames 1796-1802 show a bowler approaching the pitch and a batter preparing, indicating a live delivery. |
| c40 | t=1833.0s | B | agreed | Frames t=1830.0 to t=1833.0 show a bowler preparing to bowl and a batter preparing to play a shot, indicating a live del |
| c41 | t=1872.0s | B | agreed | Frames t=1870.0-1872.0 show a bowler and batters in position, indicating a live delivery. |
| c42 | t=1911.0s | B | agreed | Frames t=1911.0 to t=1913.0 show a batter preparing to hit and the crowd reacting, indicating a four was hit. |
| c43 | t=1980.0s | B | agreed | Frames t=1980.0-1992.0 show a bowler delivering the ball and the batter reacting to it. |
| c44 | t=2013.0s | B | agreed | Frames t=2022.0 and t=2023.0 show a player celebrating a successful shot with a 'FOUR' label on the screen. |
| c45 | t=2047.0s | B | agreed | Frames t=2046.0 to t=2047.0 show a batter preparing and a bowler having just delivered the ball, indicating a live deliv |
| c46 | t=2069.0s | A | agreed | Frames 2067.0-2079.0 show a bowler preparing to bowl and a batter preparing to hit, indicating a live delivery. |
| c47 | t=2122.0s | B | agreed | Frames 2122.0-2123.0 show a bowler in the middle of the frame having just bowled the ball and a batsman reacting to the  |
| c48 | t=2144.0s | B | agreed | The frame at t=2144.0 shows the bowler releasing the ball, and subsequent frames show the batter walking back to the pav |
| c49 | t=2347.0s | A | agreed | Frames t=2347.0 to t=2361.0 show a bowler preparing to bowl and a batter preparing to face the delivery. |
| c50 | t=2365.0s | B | agreed | Frames t=2365.0 to t=2377.0 show a bowler preparing to bowl and a batter preparing to face the delivery. |
| c51 | t=2400.0s | B | agreed | Frames t=2397.0 to t=2401.0 show a bowler preparing to bowl and a batter hitting the ball. |
| c52 | t=2427.0s | A | agreed | Frames t=2427.0 to t=2438.0 show a bowler preparing to bowl and a batter hitting the ball, with fielders reacting and sc |
| c53 | t=2462.0s | B | agreed | Frames t=2462.0 and t=2465.0 show a bowler releasing the ball and players reacting, indicating a live delivery. |
| c54 | t=2493.0s | A | agreed | Frames t=2493.0 and t=2494.0 show a bowler releasing the ball and a batter preparing to hit, indicating a live delivery. |
| c55 | t=2527.0s | B | agreed | Frames t=2525.0 to t=2532.0 show a cricket player in action, with the bowler preparing to bowl and the batter standing a |
| c56 | t=2594.0s | B | agreed | Frames t=2594.0 to t=2598.0 show a batter in a red uniform swinging their bat, with the wicket-keeper crouching behind t |
| c57 | t=2616.0s | A | agreed | Frames t=2615.0 to t=2617.0 show a bowler running towards the pitch and a batter playing a shot, followed by fielders re |
| c58 | t=2647.0s | B | agreed | Frames t=2649.0 to t=2659.0 show a batter preparing to hit the ball, followed by a celebration and a 'WICKET' text overl |
| c59 | t=2745.0s | B | agreed | Frames t=2745.0 to t=2750.0 show a bowler preparing to bowl and a batter reacting to the delivery. |
| c60 | t=2779.0s | B | agreed | Frames t=2775.0 and t=2778.0 show a live moment during the match with players engaged in active play, and t=2779.0 shows |
| c61 | t=2808.0s | A | agreed | Frames t=2807.0 and t=2808.0 show a batter preparing to hit the ball and then swinging the bat. |
| c62 | t=2869.0s | C | agreed | Frames t=2869.0 and t=2871.0 show a batter in motion and a fielder reacting to a play, indicating a live delivery. |
| c63 | t=2902.0s | B | agreed | Frames t=2902.0 to t=2905.0 show a batter preparing to hit and then hitting the ball, with subsequent frames showing cel |
| c64 | t=2943.0s | B | agreed | Frames t=2943.0 and t=2945.0 show a batter preparing to play the ball and walking off the field, respectively. |
| c65 | t=2975.0s | B | agreed | Frames t=2975.0 to t=2983.0 show a bowler releasing the ball and the batter reacting. |
| c66 | t=3011.0s | B | agreed | Frames t=3011.0 to t=3019.0 show a bowler releasing the ball and the batters reacting. |
| c67 | t=3032.0s | B | agreed | The batter is seen swinging at the ball at t=3043.0 and then walking off the field at t=3052.0, indicating a wicket was  |
| c68 | t=3164.0s | B | agreed | Frames from 3164.0s to 3170.0s show a batter preparing to play a shot and a fielder reacting, indicating a live delivery |
| c69 | t=3206.0s | A | agreed | Frames t=3200.0 to t=3210.0 show a bowler throwing the ball and a batter preparing to play, indicating a live delivery. |
| c70 | t=3232.0s | B | agreed | Frames t=3232.0 and t=3235.0 show a batter mid-swing and a post-action moment with a 'DISMISSED BATTER' notification, in |
| c71 | t=3254.0s | B | agreed | Frames t=3253.0 to t=3256.0 show a bowler in motion and a batter preparing to hit the ball, indicating a live delivery. |
| c72 | t=3279.0s | C | agreed | Frames t=3278.0 and t=3279.0 show a batter swinging at the ball and fielders reacting, indicating a live delivery. |
| c73 | t=3304.0s | A | agreed | Frames t=3304.0 and t=3308.0 show a bowler preparing to deliver the ball and a batter preparing to play, indicating a li |
| c74 | t=3370.0s | D | agreed | Frames t=3368.0 to t=3375.0 show a bowler preparing to deliver the ball and the batter preparing to hit it, followed by  |
| c75 | t=3413.0s | B | agreed | Frames t=3413.0 to t=3419.0 show a bowler in motion and a batter preparing to hit the ball, indicating a live delivery. |
| c76 | t=3439.0s | B | agreed | Frame t=3436.0 shows a batter swinging at a delivery. |
| c77 | t=3470.0s | A | agreed | Frames t=3478.0 to t=3482.0 show a batter preparing to hit and fielders reacting. |
| c78 | t=3512.0s | D | agreed | Frames t=3512.0 and t=3514.0 show a batter swinging and running, indicating a live delivery. |

# Commentary Benchmark Dataset

Scraped from ESPNcricinfo via ESPN playbyplay API.
Training/benchmark dataset for Machine 2.

## Matches

| # | Match | ID | Deliveries | File |
|---|-------|----|------------|------|
| 1 | IND vs NZ — T20 WC 2026 Final | 1512773 | 250 | commentary_1512773.md |
| 2 | IND vs ENG — T20 WC 2026 Semi-Final | 1512772 | 260 | commentary_1512772.md |
| 3 | IND vs PAK — T20 WC 2024 New York | 1415719 | 244 | commentary_1415719.md |
| 4 | IND vs SA — T20 WC 2024 Final | 1415755 | 252 | commentary_1415755.md |
| 5 | WI vs ENG — T20 WC 2016 Final | 951373 | 246 | commentary_951373.md |
| 6 | IND vs PAK — T20 WC 2022 Melbourne | 1298150 | 252 | commentary_1298150.md |
| 7 | SA vs AFG — T20 WC 2026 Super Over | 1512731 | 249 | commentary_1512731.md |
| 8 | ZIM vs AUS — T20 WC 2026 | 1512737 | 245 | commentary_1512737.md |
| 9 | RCB vs CSK — IPL 2024 | 1426306 | 254 | commentary_1426306.md |
| 10 | CSK vs GT — IPL 2023 Final | 1370353 | 217 | commentary_1370353.md |

**Total: 2,469 deliveries** across 10 matches, 20 innings.

## Per-Delivery Fields

Each delivery (in both `.md` and `.json`) contains:

- **over_ball** — e.g. `14.3`
- **bowler** — full name
- **batter** — full name
- **event** — DOT, SINGLE, TWO, THREE, FOUR, SIX, WICKET, WIDE, NO_BALL, LEG_BYE, BYE
- **runs** — score value of the delivery
- **short_text** — one-line summary (e.g. "no run", "FOUR", "OUT, caught")
- **commentary** — full narrative text (the rich human-written description)
- **score** — running innings total (e.g. `147/3`)
- **bat_runs / bat_balls / bat_fours / bat_sixes** — batter's running stats
- **bowl_overs / bowl_runs / bowl_wickets / bowl_maidens** — bowler's running figures
- **dismissal** — dismissal description if wicket fell
- **dismissal_type** — caught, bowled, lbw, run out, stumped, etc.

## Match Mix

- **6 ICC T20 World Cup** matches (2016, 2022, 2024, 2026)
- **2 IPL** matches (2023 final, 2024)
- **8 countries** represented (IND, NZ, ENG, PAK, SA, WI, AFG, ZIM, AUS)
- Includes: finals, semi-finals, super overs, upsets, DLS, chases
- Range of eras: 2016–2026

## Source

ESPN playbyplay API: `https://site.web.api.espn.com/apis/site/v2/sports/cricket/8676/playbyplay?event={match_id}`

Scraper: `files/scrape_commentary.py` (single match) / `files/scrape_batch_commentary.py` (batch)

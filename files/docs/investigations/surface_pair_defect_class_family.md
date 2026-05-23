# Surface-pair defect-class family — catalogue

> Skeleton memo opened 2026-05-21 per C20. Instance rows enumerate the 9
> confirmed §12.3 surface pairs from the DCKKR replay observation log.
> Per-row (a)-(e) populate deferred to C20b next session. See §0 for source
> anchors; §4 for open questions (including the forcing-function finding).

## §0 Provenance

- Empirical source: `validate_dckkr_replay_observations.md` (21 observation
  frames over ~12 overs of broadcast, DCKKR 2026-05-21 replay).
- Trace artifact: `files/logs/deliveries/validate_dckkr_20260521_155356/`
  (4.3 MB trace JSONL, 3.4 MB pipeline.log, 458 KB scout dump,
  3.3 GB recorded mp4, sha256 checksums).
- Structural theory: `files/docs/investigations/sm_as_orchestrator_design.md`
  §12 — dual-state-write defect-class catalogue (pattern definition,
  family-defining instances F-α-shadow / F1-B-ε / B-η-FC5, structural
  signature §12.3, detection methodology §12.4, remediation patterns
  §12.5, audit obligation §12.6).
- Audit obligation: §12.6 (mandatory gate-3 cross-reference for any
  candidate fix touching these surfaces).

## §1 Framing

The §12.3 dual-state-write structural signature was established at C17 with
three family-defining instances spanning two prior sessions (F1, B-η). The
DCKKR 2026-05-21 replay produced **9 additional instance candidates within
a single match**, tripling the confirmed instance count and validating the
structural pattern as a recurring defect-class family rather than three
coincidental cases.

Family-level taxonomy is the natural next move: §12 retains the structural
theory; per-instance accretion moves here. This memo enumerates the family.
Per-row (a)-(e) populate from trace evidence is deferred to C20b — the
skeleton intentionally surfaces which Obs entries lack sufficient detail to
populate all five axes (the §4 forcing function).

## §2 Instance catalogue

Each instance row uses the §12.2 5-axis template:

| Axis | Meaning |
|---|---|
| (a) Two parallel surfaces | Surface A (weaker) vs Surface B (stronger) — code paths |
| (b) Weaker invariant | What Surface A admits |
| (c) Stronger invariant | What Surface B requires |
| (d) Detection signal | Where the divergence is observable |
| (e) Remediation | Narrow (Shape A/B) vs architectural (Shape C) per §12.5 |

Rows below carry the surface-pair label extracted from the observation log,
the Obs N anchor set, the surface-A/surface-B labels as observed at the UI
level, and a one-line defect summary. All five axes are placeholders for
C20b populate.

### §2.1 — W → · revert on This Over symbol post-wicket

- **Obs anchors:** Obs 4 (Rahul, end of over 5), Obs 11 (Rana, over 8.0),
  Obs 17b (Nissanka misattribution, over 10).
- **Surface A:** This Over panel ball-symbol slot at the wicket-ball
  coordinate.
- **Surface B:** Fall of Wickets ledger + At-the-Crease batter removal.
- **One-line defect:** Wicket symbol "W" commits to This Over panel, then
  reverts to "·" within ~1-3 frames; FOW row and batter removal hold under
  the flip. Reproduced 3/3 live-era wickets.
- (a)-(e): **POPULATE-NEXT-SESSION (C20b).**

### §2.2 — Striker-label vs ball-credit attribution

- **Obs anchors:** Obs 12 (over 8.2), Obs 13 (over 8.4).
- **Surface A:** Striker-name label on At-the-Crease panel (green-dot
  pointer state).
- **Surface B:** Ball-credit increment on batter stats (R, B columns).
- **One-line defect:** Striker label and ball-credit increment route
  through independent paths; pipeline can show Nissanka as striker while
  crediting balls/runs to Rizvi (Obs 12), or flip the pointer between
  frames without any rotation event firing (Obs 13).
- (a)-(e): **POPULATE-NEXT-SESSION (C20b).**

### §2.3 — Score-commit vs symbol-commit confidence threshold

- **Obs anchors:** Obs 5 (balls 2.3/2.4 unresolved permanent), Obs 13
  (ball 8.1 `?` persists while score advances).
- **Surface A:** Symbol-commit confidence gate — writes `?` if below
  threshold; no retry mechanism.
- **Surface B:** Score-commit confidence gate — treats same ball as `·`,
  increments ball counter, advances team score.
- **One-line defect:** A read confident enough to advance score but not
  symbol produces persistent `?` in This Over and Recent Overs panels
  while team-score, ball-counter, partnership, and CRR advance correctly.
- (a)-(e): **POPULATE-NEXT-SESSION (C20b).**

### §2.4 — Score-state vs per-ball-state two-rate commit (with catch-up double-credit)

- **Obs anchors:** Obs 14 (end of over 9, per-ball UI 2 balls stale),
  Obs 15 (over 9.2, catch-up duplicates +1/+2 to Rizvi).
- **Surface A:** Per-ball UI state — slower commit rate, lags 0-2 balls
  behind score.
- **Surface B:** Score-state commit — faster rate, advances independently.
- **One-line defect:** Two commit paths with different rates produce a
  persistent 0-2 ball gap; when per-ball UI catches up, balls credited
  earlier on the fast path are re-credited on the slow path. Observed
  catch-up double-credit: +1 run / +2 balls to Rizvi at Obs 15.
- (a)-(e): **POPULATE-NEXT-SESSION (C20b).**

### §2.5 — Striker-pointer state vs FOW-name commit at wicket

- **Obs anchors:** Obs 16 (Rizvi out at 9.5, pipeline credits Nissanka),
  Obs 18 (Nissanka out at 10.2, pipeline credits Rizvi), Obs 19 (Patel
  10.5 attribution TBD), Obs 21 (5th wicket new-batter never resolved).
- **Surface A:** Striker-pointer state at wicket-ball frame — stale per
  rotation-lock starvation; resolution_src=P3 SM.self.striker fallback
  (per A3 trace_beta_sm_wicket_dispatch payload, restored in C19A3).
- **Surface B:** FOW-row name commit — reads striker pointer at dispatch
  moment.
- **One-line defect:** Wrong batter credited to FOW because striker
  pointer was stale at the wicket-ball frame (rotation never fired or
  fired in wrong direction). 3/3 live-era DCKKR wickets misattributed.
- (a)-(e): **POPULATE-NEXT-SESSION (C20b).**

### §2.6 — FOW-wicket-count vs bowler-card-W increment

- **Obs anchors:** Obs 17 (Narine W=0 at 10.0 after Nissanka wicket),
  Obs 19 (Roy W=0 at 10.5 with 2 missed credits), Obs 21 (Narine W=0
  still at replay-end).
- **Surface A:** Bowler-card W field — no increment fires on dismissal.
- **Surface B:** FOW row append — commits canonically on every wicket.
- **One-line defect:** Wickets accumulate in FOW but bowler-card W stays
  0; per-bowler dismissal credit never lands. 3/3 wickets, 2 bowlers,
  100% reproducibility.
- (a)-(e): **POPULATE-NEXT-SESSION (C20b).**

### §2.7 — Symbol-commit ball-coordinate overwrite (wides / no-balls)

- **Obs anchors:** Obs 18 (10.2 wide+wicket overwrites 10.1's "1"),
  Obs 19 (over 11 partial auto-correct splits W and Wd into separate
  slots).
- **Surface A:** Symbol-commit slot keyed on `(over, ball_within_over)`
  with single-value semantics; new event at same coordinate overwrites.
- **Surface B:** Subsequent symbol-commit re-evaluation path — partial
  retry under unknown trigger that inserts the missing extras slot.
- **One-line defect:** Wide+wicket compound event overwrites the previous
  legal-ball symbol because both share the same `ball_within_over`
  coordinate; symbol-commit lacks ordered-list semantics for extras.
  Partial auto-correct observed at Obs 19 but trigger unclear.
- (a)-(e): **POPULATE-NEXT-SESSION (C20b).**

### §2.8 — Live-state vs Recent-Overs-promote: write-and-revert

- **Obs anchors:** Obs 19 (Recent Overs Ov 10 position 2 regressed from
  `·` to `?`), Obs 20 (Ov 11 W symbols replaced with "4" and "·" at
  promote).
- **Surface A:** Recent-Overs-promote commit path — re-evaluates symbols
  at promote time with stale/lower-confidence inputs; inserts
  confidence-driven guesses (the "4" at Obs 20 has no obvious source).
- **Surface B:** Live-state This Over commit — already finalized at end
  of over.
- **One-line defect:** Recent Overs promote re-evaluates symbols and can
  downgrade committed values (`·` → `?`) or insert arbitrary values
  ("4" replacing "1" at Obs 20). Two W symbols obliterated from Ov 11
  promote.
- (a)-(e): **POPULATE-NEXT-SESSION (C20b).**

### §2.9 — Over-promote-eligibility vs over-completed commit

- **Obs anchors:** Obs 20 (Ov 9 entirely missing from Recent Overs panel
  through replay-end; pattern: 11, 10, 8, 7, 6 — no Ov 9).
- **Surface A:** Promote-eligibility predicate — rejects promotion when
  too many balls unresolved at promote time.
- **Surface B:** Over-completed predicate — fires on legal-ball-count
  reaching 6 regardless of resolution state.
- **One-line defect:** Over 9 completed via Surface B but Surface A
  rejected promotion due to unresolved 8.1 `?` + per-ball UI stall;
  over never appears in Recent Overs. Permanent skip — even after
  the `?` was resolved upstream, the over was not retroactively
  promoted.
- (a)-(e): **POPULATE-NEXT-SESSION (C20b).**

### §2.10 — Phantom-wicket detection (architectural-known-defect)

- **Obs anchors:** F1017 on `validate_dckkr_20260521_155356` —
  POST-WICKET-ROTATION emitted on Axar against cricket truth
  (Obs 21 confirms Axar at-the-crease at replay-end). Scout OCR
  oscillation F1015 wkts=6 / F1016 wkts=4 / F1017 wkts=5 / F1018-F1019
  wkts=5 (3-frame persistent jump) fires `ball_detector.check()` strict-
  increase predicate at `files/eyes/state/ball_detector.py:69`.
- **Surface A:** `ball_detector.check()` wicket-fell predicate —
  single-frame strict-increase on wickets-counter; no consensus or
  cross-field debouncer.
- **Surface B:** `apply_wicket_event` downstream commit — accepts
  upstream wicket-events unconditionally per §15 fence (canonical
  dispatch path).
- **One-line defect:** Phantom-wicket emitted at strip OCR-instability
  boundary; downstream cascade (WICKET-ATTRIB + striker rotation +
  FoW append) commits unrecoverable false-positive wicket event.
- **Fix-surface status:** No fix landed. WS-Surface-E HA' (N=3 consensus
  + overs-advance gate) statically falsified — admits phantom at F1019
  per `workstream_surface_e_phantom_wicket_investigation.md` §14.
  Cricket-physics-gate (Option Y) statically falsified — OCR-noise
  envelope uniform across phantom + genuine cohort per memo §15.
  Detection-layer discriminators built on wickets-counter dynamics
  are structurally incapable of separating phantom from genuine within
  the current Scout primitive set.
- **Re-investigation prerequisites:** (1) new Scout primitive providing
  discriminating signal (e.g., FoW-graphic overlay parsing); OR
  (2) ML classifier trained on labeled phantom-vs-genuine cohort;
  OR (3) operator-side post-hoc retraction workflow.
- (a)-(e): see `workstream_surface_e_phantom_wicket_investigation.md`
  §13-§18 for full retirement context + architectural-known-defect
  framing.

## §3 Cross-instance methodology

**Placeholder for C20b+.** Populate as additional matches add instance
data. Initial hypotheses worth investigating at scale:

- Do §2.3 / §2.7 / §2.8 share a single **confidence-threshold root** on
  the symbol-commit path, or are they architecturally independent?
- Does the **rotation-lock-starvation root** behind §2.5 also drive §2.2
  (both involve striker-pointer staleness)?
- Are §2.1 and §2.6 expressions of a single "wicket-event commit fan-out
  is partial across surfaces" pattern, or independent surface pairs?
- Is the 4-rate commit taxonomy observed at Obs 15 (fast / medium / slow
  / slowest) a useful framing axis for the family, or a derivative of
  per-surface confidence-threshold differences?

## §4 Open questions

- **Forcing function — which Obs entries lack sufficient detail to
  populate all 5 axes?** Populate during C20b per-row work. Expected
  output: a list of Obs N values that need re-observation with targeted
  trace instrumentation at the suspected weaker-surface emission sites.
- Independence vs shared-root analysis for §2.3 / §2.7 / §2.8
  (confidence-threshold hypothesis).
- Independence vs shared-root analysis for §2.2 / §2.5 (rotation-lock
  hypothesis).
- Independence vs shared-root analysis for §2.1 / §2.6 (wicket-event
  commit fan-out hypothesis).
- Three non-§12.3 findings observed in the same replay but not
  catalogued here (single-surface defects, not dual-state-writes):
  bowler-card "Awaiting bowling data..." at every over boundary (6/6
  deterministic — Obs 2b/4/8/10/11/20); `?` marks permanent at 2.3,
  2.4, 8.1 (write-once symbol-commit with no retry path); new-batter
  resolution silent at 5th wicket (Obs 21, blocks downstream
  At-the-Crease state). Track in a separate workstream or add a §6
  here once the non-family instance count justifies.

## §5 Cross-reference

Structural theory remains in
`files/docs/investigations/sm_as_orchestrator_design.md` §12:

- §12.1 — pattern definition
- §12.2 — three family-defining instances (column-by-column template)
- §12.3 — structural signature (what readers should see at a glance)
- §12.4 — detection methodology (static-analysis + cross-fixture
  empirical instrumentation)
- §12.5 — remediation patterns (Shape A / Shape B narrow; Shape C
  architectural)
- §12.6 — audit obligation (§7.2 gate-3 extension; mandatory cross-
  reference for any candidate fix)
- §12.7 — cross-instance methodology lessons (this memo cross-
  referenced from there)
- §12.8 — candidate sites for future instances

This memo extends §12.2 with 9 additional instance rows specific to the
DCKKR 2026-05-21 replay. The §12.2 family-defining instances remain the
canonical examples for the structural pattern; the rows in §2 here are
accretion-class evidence that the pattern recurs at scale, plus the
substrate for forcing-function-driven observation-discipline refinement
during C20b populate.

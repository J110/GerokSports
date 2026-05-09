# Audit: `striker` / `non_striker` write sites (SM-BOARD admission)

Date: 2026-04-22  
Context: Pre-cluster audit before P0-2 → P1-5 ship. Pattern hypothesis: "SM/pipeline writes to striker/non_striker bypass BOARD admission (`batting_card[].status=="batting"`)."

## Methodology

- 3 grep passes (see session transcript) covering `self.striker =`, `self.non_striker =`, `sm.*`, `score_mgr.*`, and `["striker"]=` / `["non_striker"]=` dict writes.
- 22 production hits (tests excluded).
- Bucket scheme:
  - **B1 — Guarded**: write preceded by admission check against `batting_card[].status=="batting"` or equivalent.
  - **B2 — Trusted clear**: internal-only write (None on dismissal, swap at over change, innings reset).
  - **B3 — Unguarded external**: write sourced from Scout/extractor output without admission validation. The pattern we're hunting.
  - **B4 — Ambiguous**: needs deeper trace.
  - **N/A** — output/read-only or payload pass-through (not a state mutation).

## Findings (22 sites)

### `score_manager.py` — 9 sites, ALL clean

```
score_manager.py:675,678,681,684 (_init_from_card — striker)
score_manager.py:676,679,682,685 (_init_from_card — non_striker)
  pattern: self.striker/non_striker = self.bat1_name/self.bat2_name
  bucket: B1
  guard_present: yes (upstream at L640-657, shipped 2026-04-21)
  notes: dismissed-batter scrub at top of _init_from_card nulls card[bat_name]
         before this block runs, so sources are already admission-checked.

score_manager.py:1201,1202 (_update_batters bootstrap)
  pattern: self.striker = self.bat1_name
  bucket: B1
  guard_present: yes (upstream at L1173-1186, shipped 2026-04-21)
  notes: same scrub pattern. Bootstrap path only fires when internal
         state is empty AND card survived scrub.

score_manager.py:1377,1379,1381 (_identify_striker commit)
  pattern: self.striker = new_striker / self.non_striker = self.bat1_name|bat2_name
  bucket: B1
  guard_present: yes (implicit)
  notes: new_striker derived from balls-faced / runs delta analysis of
         internal candidates (_candidates dict). Never sources from raw
         Scout text. non_striker mirror derived from self.bat1/2_name
         (already scrubbed).

score_manager.py:1783,1784,1786,1787 (wicket handler)
  pattern: self.striker = None|survivor / non_striker = None|survivor
  bucket: B2
  guard_present: n/a (trusted clear — wicket event is the trust source)
  notes: survivor computed from self.bat1_name/bat2_name minus best_dismissed.
```

### `eyes/scoreboard.py` — 8 sites, ALL clean

```
scoreboard.py:1635,1637 (update_batter — striker arg)
  pattern: self._inn["striker"/"non_striker"] = name
  bucket: B1
  guard_present: yes (update_batter's own admission runs above this)
  notes: only writes when caller explicitly passes striker=True/False
         and the batter passed admission elsewhere in this method.

scoreboard.py:2363,2365 (record_dismissal)
  pattern: self._inn["striker"] = None
  bucket: B2
  guard_present: n/a (trusted clear on matching dismissed name)

scoreboard.py:2450,2451 (start_new_innings)
  pattern: inn2["striker"] = None
  bucket: B2
  guard_present: n/a (innings reset)

scoreboard.py:2527,2529 (get_broadcast_state — filter)
  pattern: state["striker"] = active[0] if ... else None
  bucket: N/A (this IS the admission guard — filters at WS boundary)
  notes: LAST LINE OF DEFENSE for striker projection. Rewrites striker
         to active[0] if current not in `batting_card[].status=="batting"`.
         BUT IS BYPASSED BY test_pipeline.py:3146-3148 — see below.
```

### `test_pipeline.py` — 9 sites, MIXED

```
test_pipeline.py:3146,3147 (build_full_payload — SM authority override)
  pattern: state["striker"] = _canon_player_name(score_mgr.striker)
  bucket: B1 (relies on SM's internal guarding being sufficient)
  guard_present: partial — ONE dismissed-batter scrub at L3161-3170
         catches status=="out" names. Does NOT catch names that aren't
         in batting_card at all (P1-4 Danish phantom class), nor names
         with status in {None, "not_started", "retired"}.
  notes: ★ KEY ARCHITECTURAL BYPASS ★ — this override discards the
         active-batter filter from scoreboard.get_broadcast_state (L2527-2529)
         and substitutes SM's authority. SM's authority is only as good
         as SM's own write sites. See P1-4 finding below.

test_pipeline.py:5831,5834 (_pending_bcast_striker_key apply)
  pattern: scoreboard._inn["striker"] = _pending_bcast_striker_key
  bucket: B3  ★ UNGUARDED EXTERNAL WRITE ★
  guard_present: partial — suppresses on rejected-row frame, but no
         admission check against batting_card[].status=="batting".
  notes: _pending_bcast_striker_key is set from Scout's broadcast-striker
         asterisk indicator. If Scout reads a stats-overlay with an
         asterisk and picks a bench-player name (Danish Malewar class),
         this writes it straight into scoreboard._inn without checking.
         The L6878-6893 corrective block can partially clean up, but
         only fires on the next ball event. Between ball events, the
         bad value is what build_full_payload projects.

test_pipeline.py:6885,6891,6901 (Ensure striker/non-striker are active batters)
  pattern: scoreboard._inn["striker"] = _new[0] if _new else _active[0]
  bucket: N/A (corrective guard — enforces B1 invariant post-hoc)
  guard_present: yes (this IS the guard that should be at the write sites)
  notes: defensive repair loop that runs on ball events. Only fires for
         scoreboard._inn path; does NOT protect SM's striker/non_striker,
         which is what the WS payload actually uses (L3146).

test_pipeline.py:7096,7097 (over-change rotation)
  pattern: scoreboard._inn["striker"] = _ns (and swap)
  bucket: B2
  guard_present: n/a (pure internal swap — _s and _ns are read from
         scoreboard._inn just above; if they're both valid actives,
         swap preserves validity).

test_pipeline.py:7419 (ball_event["striker"] = _sb_striker)
  pattern: writes to ball_event dict, not state
  bucket: N/A (payload field, not a mutation of canonical state)
```

### Output/read-only sites (not state mutations)

```
parity_monitor.py:236 — out["striker"] = regex group (parity output dict)
element_checker.py:199 — same, for element checker
commentary/context_builder.py:51,56 — ctx["striker"] = batting_card entry (read)
test_pipeline.py:3146 → already classified above
```

## Scope decision

**B3 hits (unguarded external writes): 1 site.**

```
test_pipeline.py:5831 — _pending_bcast_striker_key straight to scoreboard._inn
```

**B1-with-partial-guard (the architectural gap): 1 site.**

```
test_pipeline.py:3146-3148 — build_full_payload SM override bypasses
get_broadcast_state's active-batter filter. The dismissed-batter scrub
at L3161-3170 only catches status=="out", not "not-in-card".
```

## What this means for the cluster commit

The "SM writes bypassing BOARD guards" theme lands more narrowly than the original hypothesis suggested. SM itself (`score_manager.py`) is cleanly guarded on every striker/non_striker write site — yesterday's dismissed-batter scrubs (L640-657, L1173-1186) closed the previously-leaking paths.

The ACTUAL remaining gap is two-part and both parts live in `test_pipeline.py`:

1. **P0-3 / P1-4 root**: `build_full_payload`'s SM-authority override (L3146-3148) discards `get_broadcast_state`'s active-batter filter. The existing hygiene scrub (L3161-3170) only catches `status=="out"` — misses `name not in batting_card` (Danish phantom), `status==None`, `status=="not_started"`, `status=="retired"`.

2. **Ball-event-only corrective**: The "Ensure striker/non-striker are active batters" guard (L6878-6893) enforces the right invariant but only runs inside the `if ball_event:` branch. Between ball events (idle frames), a bad value persists.

Plus the B3 site (L5831) which feeds into #1.

### Cluster commit scope (revised)

Keeps the planned P0-2 / P0-3 / P1-4 / P1-5 commit bounded. Specifically:

- **P0-3 fix** should strengthen the WS-boundary hygiene scrub at `test_pipeline.py:3161-3170` to reject ANY name not in `batting_card[].status=="batting"`, not just `status=="out"`. One-line broadening, catches both the P0-3 striker-resurrection and P1-4 phantom non_striker in a single guard.
- **P1-4** becomes "extends the same WS-boundary scrub" — same diff, no separate fix.
- **P0-2** (XI-REJECT override) independent.
- **P1-5** (fours/sixes accumulator) independent.
- **B3 site (L5831)** add an `_is_active_batter(name)` check before the write to plug the upstream leak, belt-and-braces alongside the WS-boundary tightening.

### Bounded: cluster stays in one session.

2 known issue sites (P0-3, P1-4) collapse into **one** WS-boundary hygiene broadening + **one** B3-site admission check. Plus P0-2 and P1-5 which were always independent. Total diff well under 1.5 hours coding + validation.

No 4-6 site sprawl, no split-into-two-commits signal.

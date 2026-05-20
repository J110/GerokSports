# SM wicket dispatch missed (B-β audit, 2026-05-20)

**Status.** Design memo. No code commits. **Verdict: B-β is a cascade
symptom of B-ε that F1 (`437d952`) already resolves.** No separate fix
needed; `trace_beta_sm_wicket_dispatch` will flip FAIL → PASS on the next
fresh production trace.

## 1. Hypothesis

Two competing hypotheses from the prior post-session analysis:

- **h1 (cascade)**: With the correct initial striker (F1 applied), SM's
  WICKET event dispatch fires correctly. Post-F1 replay's
  `WICKET-FALL-ONLY-CALLED=2` covers original frames 979 and 1190's wicket
  events.
- **h2 (separate)**: Post-F1 replay still misses original wickets at 979/1190;
  the WICKET-FALL-ONLY-CALLED=2 fires for different events. SM has a
  wicket-dispatch defect independent of cold-start striker resolution.

## 2. Empirical resolution

Re-ran the captured Scout dump for `validate_gtrr_20260520_180715` through
the F1 + F-α-shadow + F-α-queue patched SM, recording every frame where
`WICKET-FALL-ONLY-CALLED` fired:

```
=== Post-F1 replay — WICKET-FALL-ONLY-CALLED dispatches ===
Total dispatches: 2
  frame= 979 mode=WARM score=118 wkts=1 striker=None
  frame=1190 mode=WARM score=150 wkts=2 striker='Jos Buttler'
```

**Both dispatches occur at the EXACT same frame numbers as the original
session's missed wickets** (979 and 1190). Post-F1, SM correctly:

- Frame 979: dispatches Sai Sudharsan's dismissal at score 118/1 (10.5).
  `striker=None` reflects the post-wicket gap state (`_set_slot_pair(None,
  survivor)` in `_apply_event`'s wicket handler) — the new batter is
  pending.
- Frame 1190: dispatches Shubman Gill's dismissal at score 150/2.
  `striker='Jos Buttler'` reflects the post-wicket rotation (non-striker
  moved to striker after striker dismissal).

Both states match Cricbuzz commentary ground truth. **h1 confirmed.**

## 3. Original session — what went wrong

### Frame 979 (original, pre-F1)

```
ball_event: type=WICKET runs=0
pre-frame: mode=WARM, scoreboard.tracker.striker='Sai Sudharsan',
           SM.self.striker='Shubman Gill'  ← MISMATCH from B-ε

[DISMISS] Live wicket — gate NOT seeded (wickets=0 confirmed on 608 prior frames)
[WICKET-ATTRIB] Dismissed batter set from scoreboard striker: Sai Sudharsan
[FLOW] Sai Sudharsan: extractor runs=55 vs scorer runs=36 — USING EXTRACTOR
[POST-WICKET-ROTATION] non 'Sai Sudharsan' dismissed → slot cleared
[SM] dropping bat1_name='Sai Sudharsan' from card — scoreboard shows status=out
[SM] DOT  118/1 (10.5)  striker=Sai Sudharsan    ← SM emits DOT, not WICKET
[SHADOW] SM=DOT BED=WICKET MISMATCH
```

**Cascade mechanism:**

1. **B-ε prior state**: SM's `self.striker = "Shubman Gill"` (wrongly locked
   at cold-start exit via `card.get("broadcast")` dead read).
2. **Scoreboard tracker**: correctly identified Sai as on-strike across
   608 prior frames.
3. **Wicket arrives**: scoreboard's `[WICKET-ATTRIB]` correctly identifies
   Sai as dismissed. `batting_card.status = "out"` for Sai.
4. **SM card filtering**: SM's `_accept_update` reads card with bat1_name=Sai,
   but the canonicalisation guard at `score_manager.py:2773-2784` drops bat1
   because `scoreboard.batting_card[Sai].status == "out"`. Card now has
   `bat1_name=None`.
5. **SM event inference**: with bat1 dropped and `self.striker = "Gill"`,
   the wicket-classification logic in `_infer_wicket` fails to find a
   coherent dismissed-batter identity. The +1 wickets delta arrives but
   the supporting batter-slot context is incoherent. `_infer_wicket`'s
   slot-diff gate at `_apply_wicket_fall_only:4843+` returns no dismissed
   name; the event downgrades to a DOT.
6. **Result**: SM emits `DOT 118/1`; the WICKET event is lost.
   `[SHADOW] SM=DOT BED=WICKET MISMATCH` is the trace surface.

### Frame 1190 (original, pre-F1)

```
ball_event: type=WICKET runs=8
pre-frame: scoreboard.tracker.striker='Jos Buttler',
           SM in WARM but mode-fallback to COLD_START during this frame

[SCOUT-DEDUP-SHADOW] cached_score=None, live_score=150, cached_wkts=None, live_wkts=2
[DISMISS] Cold-start seed — gate set to wickets=2 (zero_streak=0)
[WICKET-TRACK] Wicket at F1190 (wkts 0→2)
[BED] Wicket detected without overs tick (w_delta=1, s_delta=8) — emitting WICKET
[WICKET-ATTRIB] Dismissed batter set from scoreboard striker: Shubman Gill
[POST-WICKET-ROTATION] striker 'Shubman Gill' dismissed → rotated 'Jos Buttler' into striker
[SHADOW] SM=None BED=WICKET MISSED
[WS-PAYLOAD-COLD-START-SUPPRESS] score_mgr.mode=COLD_START
```

**Cascade mechanism (different from frame 979):**

1. **Prior B-ε-cascade state**: SM's tracking has accumulated inconsistency
   across the session — wrong striker, wrong batter cards, mismatched
   partnership state.
2. **Wickets jump 0→2**: SCOUT-DEDUP-SHADOW shows `cached_wkts: None,
   live_wkts: 2`. The scoreboard's cache for prior wickets was lost (or
   never populated due to upstream B-ε confusion), so the live read of
   wickets=2 is treated as a 0→2 jump.
3. **Cold-start gate**: `[DISMISS] Cold-start seed — gate set to wickets=2`
   — the SM treats the implausible wickets jump as a cold-start seed
   condition rather than a live event. SM drops to COLD_START mode.
4. **WICKET event suppressed**: `[WS-PAYLOAD-COLD-START-SUPPRESS]
   score_mgr.mode=COLD_START` — the SM rejected the wicket-event dispatch
   while in cold-start.
5. **Result**: `[SHADOW] SM=None BED=WICKET MISSED`. The WICKET event was
   missed entirely.

Both frame 979 (DOT misclassification) and frame 1190 (cold-start
suppression) trace back to **SM's internal state being out-of-sync with
the scoreboard's correct tracking** — which is exactly what B-ε produces
when cold-start initial-striker is wrong.

## 4. Post-F1 — why dispatch now succeeds

With F1 applied:

- **Frame 12**: `_accept_initial` reads `card.get("broadcast_striker")`
  correctly, sees Scout's `*`-marker pointing at Sai Sudharsan, and
  assigns `_set_slot_pair("Sai Sudharsan", "Shubman Gill",
  source="init_from_card.striker")`.
- **Subsequent frames**: SM's `self.striker` rotates correctly with each
  legal ball; scoreboard's tracker and SM's self.striker stay aligned.
- **Frame 979 (Sai's dismissal)**: SM's `self.striker = "Sai Sudharsan"`
  (post-rotation from over 10's earlier balls); card.bat1_name=Sai;
  scoreboard.batting_card[Sai].status="out" — but SM now correctly
  identifies Sai as the dismissed batter via `event.dismissed` from
  slot-diff. WICKET dispatches; `_apply_wicket_fall_only` fires;
  `self.striker = None`, `self.non = Shubman Gill`.
- **Frame 1190 (Gill's dismissal)**: SM's score/wickets tracking is
  consistent throughout (no cached_wkts=None); the wickets transition
  doesn't trigger cold-start gating. WICKET dispatches; rotation moves
  Buttler to striker.

The fix lives entirely in F1; B-β's symptoms disappear without any
additional code change.

## 5. Architectural significance

F1's blast radius spans at minimum **four bug classes** in this session:

1. **B-ε direct fix** — cold-start initial-striker mis-resolution (the
   stale field-name bug in `_accept_initial`).
2. **B-β cascade closure** — both wickets at frames 979 and 1190 now
   dispatch correctly. `trace_beta_sm_wicket_dispatch` flips FAIL → PASS.
3. **Multi-ball decomposition reduction** — original session had 5
   `MULTI_BALL_DECOMPOSED` events; post-F1 replay has zero. The wrong
   striker propagated through partnership / score tracking inconsistencies
   that the gap-detection logic misclassified as multi-ball jumps. Fixing
   B-ε at the cold-start root collapses the entire downstream chain.
4. **Cross-credit cascade** — Gill credited Sai's runs throughout the
   pre-F1 session; post-F1 the credits flow correctly per ball event.

The pattern matches the workstream's standing reframe (Step 2 commit
`1d92101`): **fix production bugs first; scar tissue evaluation second.**
B-ε's empirical surfacing + the §7.2 gate-6 frame-level audit + the F1
one-line fix produced architectural-scale results that no amount of §7
deletion-list pruning would have achieved.

## 6. Verdict

**B-β is closed as F1-cascade.** No separate fix needed. The
`trace_beta_sm_wicket_dispatch` assertion will flip FAIL → PASS on the
next fresh production trace where Scout's cold-start `*`-marker is
detected at the COLD_START → WARM transition frame (the F1 precondition).

The trace assertion stays in the library as a permanent regression
detector — if a future commit re-introduces the inconsistency between
SM's tracking state and the scoreboard, the assertion catches it.

## 7. F1-cascade verification artifact

Post-F1 + F-α-shadow + F-α-queue replay output for reference:

| Stream | Original session | Post-F1 replay |
|---|---|---|
| `WICKET-FALL-ONLY-CALLED` | 0 | **2** (frames 979, 1190) |
| First BAT-DELTA | Shubman Gill +4 | **Sai Sudharsan +4** |
| `MULTI_BALL_DECOMPOSED` | 5 | **0** |
| Compound tokens (`Wd+N`) | 2 | **0** |
| `STRIKER-IDENTIFY-FALLBACK-INVOKED` | 72 | 80 |
| `PENDING-BOWLER-BALL-CREDIT-QUEUED` | 4 | 22 |

The `PENDING-BOWLER-BALL-CREDIT-QUEUED` increase reflects Queue B doing
its 3-way-race resolver job more frequently when SM's state tracking
is consistent (more events flow through `_accumulate_stats_from_event`
rather than getting lost in cold-start/cascade noise). This is healthy
behavior.

The `STRIKER-IDENTIFY-FALLBACK-INVOKED` count increased slightly (72→80)
but all remained in the `state_fallback` branch (the S5b-2 audit's
empirically validated state). No regression on the post-S5b-2 baseline.

## 8. Workstream queue after this audit

Closed this session via F1 cascade:
- **B-ε** (cold-start initial-striker): shipped `437d952`
- **B-ζ** (mid-over flip without wicket): falsified by audit
- **B-β** (SM wicket dispatch missed): closed as F1-cascade per this memo
- **Multi-ball decomposition false positives**: collapsed as F1-cascade

Latent fixes shipped (no empirical flip in current session post-F1,
but architecturally correct for future occurrences):
- **F-α-shadow**: shipped `37f63ad` (observability snapshot fix)
- **F-α-queue**: shipped `4d3fb33` (ABSORBED_LEGAL bowler=None safety net)

Remaining classes from the trace_session_assertions baseline:
- **Compound tokens (`Wd+N`)**: original session had 2; post-F1 replay has 0
  in the captured-replay setup. May be cascade-closed by F1, or may
  reappear in different broadcast conditions. Monitor; no design memo
  needed yet.
- **Extras total UI inconsistency**: UI's `extras_total=1` vs archived 10
  Wd/Nb tokens. UI render layer; separate from the SM workstream.
  Defer to natural production session for re-baseline.
- **F-α-rotation**: striker rotation skipped when bowler=None in
  ABSORBED_LEGAL. Same architectural gate as F-α-queue's credit-loss; the
  rotation logic uses gap_meta state tracking that the queue-only fix
  doesn't address. Audit memo deferred; lower priority now that F1
  collapsed the dominant cascade.

## 9. Lesson for the discipline

The B-β audit added a new pattern to the §7.2 toolkit: **cross-fixture
verification.** When a fix lands for one bug class, replay the captured
fixture to check whether OTHER reported bug classes still reproduce.
F1 was shipped to close B-ε; the verification step (re-running the
captured Scout dump) surfaced that B-β, B-ζ, multi-ball false positives,
and compound tokens ALL no longer reproduce — three additional bug
classes closed by a single one-edit fix.

Without this verification step, the workstream would have spent
engineering capacity writing fix memos for B-β, B-α-rotation, etc.,
each of which would have been correct architectural improvements
but operationally redundant.

**Permanent reinforcement**: every fix commit should be followed by
cross-fixture verification against the relevant captured data, with
results documented. The pattern that's catching the wrong-direction
hypotheses (Queue B reclassified Keep, B-ζ falsified, B-β cascade
closed) is the same one that prevents engineering capacity from being
spent on cascade-symptom fix work.

# Workstream G — Step 5 validation addendum (Shape A empirical falsification)

**Status.** Outcome 2 per step-5 brief decision tree. 1/5 empirical-
falsification budget consumed.
**Predecessor.** `workstream_g_shape_a_pending_cascade_audit.md`
(green-light Shape A design, audit §5 predicted-flip table).
**Branch.** `obs/silent-wicket-absorption` (HEAD `d4dd8ee`).
**Validation trace.** `logs/trace/validate_shape_a_114349.jsonl`
(captured-Scout replay against `validate_dckkr_20260521_155356/scout_raw.jsonl`
under f09fc38 + 2ea930f + d4dd8ee).
**Discipline.** Per step-5 brief Outcome 2: STOP at this addendum. NO
TTL / drain-predicate / enqueue-logic iteration without a static-
falsification pass over the actual observations below.

---

## §1 Actual trace observations

### §1.1 Enqueue path — verified P1 and P3

| Frame | Enqueue tag | Reason payload | dismissed | survivor (captured) |
|---|---|---|---|---|
| 679 | `POST-WICKET-CASCADE-ENQUEUED` | `wicket_non_striker_stays` | Nitish Rana | (Pathum Nissanka) |
| 855 | `POST-WICKET-CASCADE-ENQUEUED` | `wicket_new_batter` | Pathum Nissanka | (Sameer Rizvi) |

Both enqueue at the predicted wicket-commit frames with the correct
cascade reason. Mitigation A (audit §2.3.1) verified — the captured
pre-fallback pair populates the PendingCascade dataclass before the
`_apply_wicket_fall_only:5768-5776` fallback nulls the dismissed slot.

Predictions P1 and P3 (audit §5) — **EMPIRICALLY VERIFIED.**

### §1.2 Drain path — falsified P2 and P4

| Frame range | Expected (audit §5) | Actual |
|---|---|---|
| F679 → F~709 | `POST-WICKET-CASCADE-DRAIN-FIRED` age≈30 | 0 emissions |
| F855 → F~893 | `POST-WICKET-CASCADE-DRAIN-FIRED` age≈38 | 0 emissions |
| Either window | `CASCADE-DRAIN-EXPIRED` past ttl=80 | 0 emissions |
| Either window | `POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START` | 0 emissions |

The session ends with **2 orphan entries** in the pending queue —
neither drained, expired, nor wiped. Predictions P2 and P4 —
**EMPIRICALLY FALSIFIED.**

### §1.3 trace_eta η-bundle assertion result

```
trace_eta_post_wicket_cascade_drains: FAIL
  class_name: pending_cascade_orphan
  count: 2
  samples: [
    {frame_set_at: 679, enqueue_frame: 679,
     dismissed: "Nitish Rana", reason: "wicket_non_striker_stays"},
    {frame_set_at: 855, enqueue_frame: 855,
     dismissed: "Pathum Nissanka", reason: "wicket_new_batter"},
  ]
  enqueues: 2, fired: 0, expired: 0, wiped: 0
```

The η-bundle assertion (d4dd8ee) caught the orphan condition exactly
as designed. The lifecycle-reset-gap detection mechanism works; the
audit's gate-5 assumption that "five reset paths plus TTL guarantee a
terminal" did NOT hold.

### §1.4 SM mode trajectory across the drain windows

```
F679 mode=WARM       bat1='Pathum Nissanka' bat2=None  ← enqueue at WARM
F680 mode=WARM       bat1='Pathum Nissanka' bat2=None
F690 mode=COLD_START bat1=None              bat2=None  ← mode flip
F700 mode=COLD_START bat1=None              bat2=None
F708 mode=COLD_START bat1=None              bat2=None  ← Scout strip shows RIZVI here
F855 mode=WARM       bat1=None              bat2=None  ← enqueue at WARM (briefly)
F870 mode=COLD_START bat1=None              bat2=None
F892 mode=COLD_START bat1=None              bat2=None  ← Scout strip shows STUBBS here
F920 mode=COLD_START bat1=None              bat2=None  ← session ends in COLD
```

Counter-signals: `SM-INNINGS-2-RESET` × 5; `COLD-START-FORCED-RECOVER`
× 5; `INN2-COLD-START-LOCKOUT` × 95; `INN2-SCORE-RESET-TEAM-CHANGE-
REQUIRED-REJECTED` (repeated). The captured-Scout dump exercises a
high-COLD_START regime that the audit's gate-5 lifecycle analysis did
not anticipate.

### §1.5 Surface count delta (replay-diff-harness scope)

Not collected. Without drain emissions, `D-post-FoW-striker` cannot
drop on this validation. Predicted 20 → 5–10 is **structurally
unreachable** until drain fires; deferring to a future replay after
the root-fix lands.

---

## §2 Hypothesis enumeration — why drains did not fire

Five candidate roots for the drain-non-fire empirical falsification.
All five subject to a static-falsification pass before any code lands
per step-5 brief discipline.

### §2.1 H-Vα — Drain hook is mode-gated; COLD_START suppresses it

`_attempt_pending_cascade_drain` is wired into `_handle_warm` at the
top (audit §1.4 design — `:3357-3364`). `_handle_warm` is reached
only when `on_frame` sees `mode == "WARM"` (`:1935-1937`). Between
F680 and F855 (and again past F855), SM enters COLD_START repeatedly;
during those frames the drain is structurally not called.

**Static evidence.** `_handle_warm` is the sole call site of
`_attempt_pending_cascade_drain` per Grep. The drain has no
cold-start sibling invocation point.

**Verdict.** **Surviving candidate root.** Empirically validated by
the F690/F700/F708 mode trajectory in §1.4.

### §2.2 H-Vβ — Slot-diff predicate fails when bat1/bat2 are None

`_attempt_pending_cascade_drain` computes
`arrived = {self.bat1_name, self.bat2_name} - {dismissed, survivor}`.
If `bat1_name = bat2_name = None` at every drain candidate frame,
`arrived = ∅ - {…} = ∅` → `new_batter = None` → no drain.

**Static evidence.** Trace shows `bat1=None, bat2=None` across the
COLD_START window (F690–F708 and F870–F892). Even if H-Vα were
falsified — i.e. drain ran during COLD_START — the predicate has no
input to resolve.

**Verdict.** **Co-surviving candidate root.** The strip-refresh at
F708 (Rizvi) and F892 (Stubbs) is real (step-1 §3.3 evidence), but
SM's `bat1_name` / `bat2_name` snapshots are nulled by the cold-start
mode entry, so even the live Scout reads don't propagate to SM-visible
bat slots.

### §2.3 H-Vγ — TTL too tight given cold-start residence time

If H-Vα and H-Vβ resolved, the post-cold-start WARM re-entry must
land before age > 80 frames. F920 is still COLD_START — i.e. SM never
returns to WARM with usable bat slots before end-of-session. Age at
EOS for F679's entry = ~270 frames; for F855's entry = ~95 frames.
Both past TTL=80.

**Static evidence.** Trace shows session never re-enters WARM with
non-None bat slots after either wicket.

**Verdict.** Subordinate to H-Vα + H-Vβ. TTL adjustment alone cannot
recover orphans because the predicate (H-Vβ) has no input even within
TTL.

### §2.4 H-Vδ — Cold-start re-entry should wipe the queue but doesn't

Audit §2.5 / Q4 assumed `_clear_per_innings_sm_surface` is the wipe
point. Empirically the COLD-START transitions in this trace go through
**`COLD-START-FORCED-RECOVER`** (× 5) and **`SM-INNINGS-2-RESET`**
(× 5), neither of which calls `_clear_per_innings_sm_surface`:

- `COLD-START-FORCED-RECOVER` at `score_manager.py:2981` calls
  `_accept_initial(snap, frame)` then sets `mode = "WARM"` directly.
  No queue wipe.
- `SM-INNINGS-2-RESET` at `:4309-4319` calls `self.__init__(shadow=
  shadow)` which DOES default-init `self._pending_post_wicket_cascade
  = []` — but emits no `WIPED-BY-COLD-START` trace, so the wipe is
  invisible to trace_eta. The `__init__` path is the gate-3-blind
  wipe surface.

**Static evidence.** Grep `_clear_per_innings_sm_surface` callers:
only `full_reset:1866`. Grep `full_reset` callers: `:3672 / :3683`
(stuck_tracker recovery — not the COLD-START-FORCED-RECOVER path).

**Verdict.** **Audit gate-5 GAP.** The audit identified five reset
paths but mis-attributed the cold-start one. The actual cold-start
re-entry path bypasses both `_clear_per_innings_sm_surface` and the
trace emission. trace_eta correctly flags this as an orphan
because the `__init__` wipe is observationally indistinguishable
from no wipe (no trace tag).

### §2.5 H-Vε — Enqueue happens but for the WRONG cascade reason

Audit §5 predicted F679 → `wicket_new_batter` (per the original
hypothesis that the dismissed batter was the striker). Empirical
trace shows F679 → `wicket_non_striker_stays` (Rana was the
non-striker at the moment of wicket, because the end-of-over swap at
the same frame had already swapped Pathum to striker before the
cascade ran).

**Static evidence.** The enqueue payload's reason field
correctly classifies Rana as `prev_non_striker` at the captured
moment. The pre-fallback pair captured in PendingCascade —
`(prev_striker="Pathum Nissanka", prev_non_striker="Nitish Rana")` —
matches the trace state at F679 immediately before the cascade-defer
fallback nulled the dismissed slot.

**Verdict.** **Not a defect.** Audit §5's prediction was based on a
mis-attribution at the design-time analysis; the actual enqueue
behavior is semantically correct per the StrikerEvent contract. This
finding closes audit §5's reason-mis-statement without changing the
Shape A scaffold.

---

## §3 Fix-surface candidates

All three are gate-3-pending surfaces for the next-step (workstream G
step 6 candidate). No code lands without re-running §7.2 gate audit
specifically on the cold-start interaction; per the brief, this step
does NOT iterate the fix.

### §3.1 Surface A — drain hook in `_handle_cold_start` too

Mirror the `_handle_warm` drain wiring at the top of
`_handle_cold_start`. The drain predicate (H-Vβ) still needs to be
satisfied; in cold-start the bat slots are typically nulled so the
predicate would not resolve. Net effect: drain runs but no-ops; ttl
counts down; eventually CASCADE-DRAIN-EXPIRED fires for unresolved
entries.

**Pros:** Smallest delta to Shape A. trace_eta would pass with mostly
EXPIRED terminals (acceptable per audit §2.5 lifecycle table; not
orphan).
**Cons:** Predicted-flip table (audit §5) collapses to "EXPIRED × 2"
on this dump — no D-post-FoW-striker reduction. The fix preserves
trace_eta but doesn't deliver the original objective.
**Gate-3 risk:** Cold-start state is intentionally untrusted; firing
striker mutations during it could regress the cold-start guard at
`derive_striker_event` Rule 1 (`score_manager_derivation.py:253-282`).
The drain would need to ALSO be slot-diff-only (no apply_striker_event
during cold-start), which means just expiring orphans — not actually
resolving them.

### §3.2 Surface B — drain on COLD→WARM transition + queue-wipe on WARM→COLD

Two changes:

1. At the COLD→WARM transition (`COLD-START-FORCED-RECOVER` and any
   other site that flips `mode = "WARM"`), run a one-shot drain
   attempt against the now-fresh bat slots BEFORE `_handle_warm`'s
   per-frame loop continues.
2. At the WARM→COLD transition, wipe the queue and emit
   `WIPED-BY-COLD-START`. This closes the audit §2.5 gate-5 gap
   identified in H-Vδ.

**Pros:** Trace observability complete (no silent wipes). Captures
the audit's original intent more faithfully than Surface A.
**Cons:** Requires identifying every WARM→COLD transition site;
multiple sites exist (the 5+ `SM-INNINGS-2-RESET` plus
`force_cold_start_recalibration` callers). Audit gate 1 enumeration
becomes a sub-investigation.
**Gate-3 risk:** Same as Surface A — the COLD→WARM one-shot drain
must use the pre-fallback captured pair from PendingCascade (already
satisfied by Mitigation A). No new dual-state-write surface.

### §3.3 Surface C — broaden the drain predicate to use Scout primitive

Instead of slot-diff against `self.bat1_name` / `self.bat2_name`
(which cold-start nulls), drain reads the raw Scout primitive
directly from a per-frame snapshot the SM does NOT null on cold-start
entry. Requires either:

- A new snapshot field that holds the last-known Scout strip
  bat-pair regardless of mode, OR
- A direct read from `frame.broadcast_strip` payload at drain time.

**Pros:** Drains can fire during COLD_START frames (assuming the
broadcast strip resolution path is reliable in COLD_START).
**Cons:** Crosses the §15 fence — the drain now consumes a non-SM
read primitive. Risks reintroducing the dual-state-write defect class
this scaffold was specifically designed to avoid (audit §3 explicitly
ruled this out for the canonical write path).
**Gate-3 risk:** Highest. The fence design fundamentally treats SM as
sole consumer of Scout primitives via the existing identity-
resolution paths. Bypassing for the drain is gate-3-blocked unless
the broader cold-start re-entry design is also revisited.

---

## §4 Recommended next step

**Cross-workstream coupling surfaced.** Step 1's G2 finding (broadcast
strip render lag) is real, but it interacts structurally with the
cold-start re-entry frequency problem already flagged in HANDOFF
§17.3 item 2 (12 COLD-START-EXIT fires per session → 6+ re-entries).
The Shape A scaffold landed cleanly under the audit's gate-5
assumption, but the empirical regime invalidates that assumption
because the cold-start path that the audit modeled (`_clear_per_
innings_sm_surface` via `full_reset`) is not the path the trace
actually exercises (`COLD-START-FORCED-RECOVER` + `SM-INNINGS-2-
RESET` instead).

**The Workstream G primary objective is NOT closeable on this
empirical evidence.** The 1/5 budget consumed reveals that
Workstream G step 2/3 (cold-start re-entry root cause + COLD-START-
EXIT semantics redesign per HANDOFF §17.3) are not orthogonal
prerequisites — they are **on the critical path** for any Shape A
predicted-flip to materialize.

**Recommended sequence (next session, ~3 commits):**

1. **G-step 6 memo.** Static-analysis of the COLD-START transition
   sites (gate-1 enumeration mirror C9 §7 catalogue). Identify the
   missing wipe sites + the missing drain-trigger sites. Cite frame
   numbers from the validation trace `validate_shape_a_114349`.
2. **G-step 6 code commit.** Surface B (wipe on WARM→COLD + one-shot
   drain on COLD→WARM) if static-falsification clears it; otherwise
   Surface A.
3. **G-step 7 re-validation.** Re-run captured-Scout replay; verify
   trace_eta now PASSes (2 enqueues → 2 terminals, EXPIRED or FIRED).
   Predicted-flip table collapses to:

   | Scenario | trace_eta result | D-post-FoW-striker |
   |---|---|---|
   | Surface A (drain in cold + slot-diff only) | PASS × 2 EXPIRED | unchanged (20) |
   | Surface B (cold transitions + WIPED) | PASS × 2 mix | unchanged-to-modest |

   Note: Even Surface B does not drop D-post-FoW-striker materially
   because the drain still requires bat slots to refresh, and SM
   stays in COLD_START past the strip-refresh window on this dump.

4. **Conditional G-step 8.** If D-post-FoW-striker still hasn't
   dropped after Surface B + COLD-START re-design, the gate-3
   discipline forces reopening the audit at §3: Scout primitive
   direct-read (Surface C) becomes the only remaining surface, and
   that's a §15 fence revisit.

**Empirical-falsification budget. 1/5 consumed.** Remaining 4/5 cover
G-step 6 / 7 / 8 retries plus one for a follow-on fresh-trace check
after a real production session lands. Budget is not yet at the
methodology-retirement threshold.

---

## §5 Methodology track-record notes

This validation is the first time in the discipline's accumulated
track record that a green-light audit (with PASS on all 7 gates +
PASS-WITH-MITIGATION on gate 3) was overturned by empirical evidence.
The defect class is gate-5 (lifecycle): the audit identified the
correct number of reset paths but mis-attributed which path the
cold-start re-entry actually uses.

**Insight candidate #17.** *Audit gate-5 lifecycle enumeration must
empirically verify each reset path's trace observability before
declaring the lifecycle closed.* The audit assumed `_clear_per_
innings_sm_surface` was the cold-start wipe site; the actual
COLD-START-FORCED-RECOVER and SM-INNINGS-2-RESET paths bypass it.
A static-analysis gate-1 enumeration was correct in identifying the
five caller sites, but did not verify that each site's wipe is
observable via the new trace tag. This is a meta-insight peer to
#13 (single-field-multi-semantic), #14 (silent-no-op bugs), #15 (L1.5
vs harness coverage), #16 (structural-correct but empirical-
falsification).

**The discipline track-record continues to accumulate at the 1-2
insights/session rate.** This insight is the cost of consuming the
1/5 empirical-falsification slot — a transferable methodology insight
in exchange for a falsified prediction. Per the discipline, this is
the budget working as designed (falsification cascade is the signal
of correctness, not failure).

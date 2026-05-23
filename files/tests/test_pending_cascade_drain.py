"""Workstream G Shape A — pending-cascade drain behavioral cases.

Persistent gate-6 verification for the post-wicket cascade scaffold
shipped in commit f09fc38 (`feat(workstream-g): Shape A pending-
cascade scaffold`). Three cases cover the audit memo §6 test plan:

- G-1 happy-path drain: cascade enqueues at wicket-commit because
  Scout new_batter is None; subsequent frame with new_batter on the
  strip drains via apply_striker_event (single canonical ROTATION
  writer per §15 fence).
- G-2 TTL expiry: queue entry ages past ttl_frames; CASCADE-DRAIN-
  EXPIRED fires; queue empties; self.striker / self.non unchanged.
- G-3 cold-start wipe: _clear_per_innings_sm_surface clears a
  non-empty queue and emits POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-
  START with the cleared entry list.

Predicted-flip claim per workstream_g_shape_a_pending_cascade_audit
.md §5: F679 → F709 drain (Rana out → Rizvi resolves, age=30,
reason=wicket_non_striker_stays); F855 → F893 drain (Pathum Nissanka
out → Stubbs resolves, age=38, reason=wicket_new_batter). Net
replay-diff-harness 14 → 9-11.

Wired into pre-commit Layer 1.5 via test_sm_derivation_ledger.main()
after the C31 WICKET-ATTRIB broadcast-override gate, mirroring the
C15 pattern.
"""
from __future__ import annotations

import sys
from pathlib import Path

FILES_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FILES_DIR))
sys.path.insert(0, str(FILES_DIR / "tests"))

import trace_emitter  # noqa: E402
from score_manager_derivation import WicketEvent  # noqa: E402
from test_sm_derivation_ledger import build_sm  # noqa: E402


def _reset_recorder(frame: int) -> None:
    rec = trace_emitter.get_recorder()
    rec.begin_frame(frame)


def _drained_records() -> list[dict]:
    return trace_emitter.get_recorder().drain()


def _records_with_tag(records: list[dict], tag: str) -> list[dict]:
    return [r for r in records if r.get("tag") == tag]


def _build_pre_wicket_sm(striker: str, non: str,
                         dismissed_is_striker: bool):
    sm, sb = build_sm()
    sm.bat1_name = striker
    sm.bat2_name = non
    sm.striker = striker
    sm.non = non
    sm.score = 80
    sm.wickets = 3
    sm.overs = 9.5
    return sm, sb


def _wicket_event_no_new_batter(dismissed: str,
                                bowler: str = "Sunil Narine") -> WicketEvent:
    return WicketEvent(
        delta_wickets=1,
        over_ball="9.5",
        bowler_name=bowler,
        dismissed_batter=dismissed,
        delta_score=0,
        delta_extras=0,
        this_over_token="W",
        is_extras_dismissal=False,
        is_runout_speculative=False,
        wicket_type="caught",
        wicket_number=3,
        new_batter=None,
    )


def _run_g1_happy_path() -> tuple[bool, str]:
    """G-1 — wicket commit with new_batter=None enqueues; subsequent
    frame with new batter on bat slots drains via apply_striker_event.
    """
    sm, _sb = _build_pre_wicket_sm(
        striker="Pathum Nissanka", non="Sameer Rizvi",
        dismissed_is_striker=True)
    sm._current_frame = 855
    event = _wicket_event_no_new_batter(dismissed="Pathum Nissanka")
    _reset_recorder(855)
    sm.apply_wicket_event(event)
    commit_records = _drained_records()

    if len(sm._pending_post_wicket_cascade) != 1:
        return False, (
            f"enqueue: expected queue.len==1, got "
            f"{len(sm._pending_post_wicket_cascade)}")
    entry = sm._pending_post_wicket_cascade[0]
    if entry.reason != "wicket_new_batter":
        return False, (
            f"enqueue: expected reason=wicket_new_batter, got "
            f"{entry.reason!r}")
    if entry.prev_striker != "Pathum Nissanka":
        return False, (
            f"enqueue: prev_striker captured wrong, got "
            f"{entry.prev_striker!r}")
    if entry.prev_non_striker != "Sameer Rizvi":
        return False, (
            f"enqueue: prev_non_striker captured wrong, got "
            f"{entry.prev_non_striker!r}")
    enq = _records_with_tag(commit_records, "POST-WICKET-CASCADE-ENQUEUED")
    if len(enq) != 1:
        return False, (
            f"enqueue: expected 1 POST-WICKET-CASCADE-ENQUEUED, got "
            f"{len(enq)}")

    # Frame +5 — no new batter yet; drain should keep queue intact.
    sm._current_frame = 860
    _reset_recorder(860)
    sm._attempt_pending_cascade_drain()
    if len(sm._pending_post_wicket_cascade) != 1:
        return False, (
            f"mid-window drain: expected queue.len==1, got "
            f"{len(sm._pending_post_wicket_cascade)}")

    # Frame +38 — Scout strip refreshes with new batter. Simulate by
    # writing bat slots directly (live pipeline does this via
    # _accept_update); slot-diff resolves new_batter via the captured
    # pre-fallback pair, not via these slots, so the dismissed name
    # may still be visible.
    sm._current_frame = 893
    sm.bat1_name = "Pathum Nissanka"  # broadcast lag — dismissed still here
    sm.bat2_name = "Tristan Stubbs"
    _reset_recorder(893)
    sm._attempt_pending_cascade_drain()
    drain_records = _drained_records()

    if len(sm._pending_post_wicket_cascade) != 0:
        return False, (
            f"drain: expected queue empty, got len="
            f"{len(sm._pending_post_wicket_cascade)}")
    fired = _records_with_tag(drain_records, "POST-WICKET-CASCADE-DRAIN-FIRED")
    if len(fired) != 1:
        return False, (
            f"drain: expected 1 POST-WICKET-CASCADE-DRAIN-FIRED, got "
            f"{len(fired)}")
    if fired[0].get("age_frames") != 38:
        return False, (
            f"drain: expected age_frames=38, got "
            f"{fired[0].get('age_frames')}")
    # §15 fence: drain dispatched via apply_striker_event canonical path.
    dispatched = _records_with_tag(drain_records, "STRIKER-EVENT-DISPATCHED")
    if len(dispatched) != 1:
        return False, (
            f"drain: expected STRIKER-EVENT-DISPATCHED, got "
            f"{len(dispatched)} (canonical path not exercised)")
    if dispatched[0].get("next_striker") != "Tristan Stubbs":
        return False, (
            f"drain: expected next_striker='Tristan Stubbs', got "
            f"{dispatched[0].get('next_striker')!r}")
    if dispatched[0].get("next_non_striker") != "Sameer Rizvi":
        return False, (
            f"drain: expected next_non_striker='Sameer Rizvi', got "
            f"{dispatched[0].get('next_non_striker')!r}")
    if sm.striker != "Tristan Stubbs":
        return False, (
            f"drain: expected self.striker='Tristan Stubbs', got "
            f"{sm.striker!r}")
    if sm.non != "Sameer Rizvi":
        return False, (
            f"drain: expected self.non='Sameer Rizvi', got {sm.non!r}")
    return True, (
        f"enqueue at F855 (reason=wicket_new_batter), drain at F893 "
        f"(age=38) → striker=Stubbs non=Rizvi via apply_striker_event")


def _run_g2_ttl_expiry() -> tuple[bool, str]:
    """G-2 — entry ages past ttl_frames (default 80) without
    new_batter; CASCADE-DRAIN-EXPIRED fires; queue empties.
    """
    sm, _sb = _build_pre_wicket_sm(
        striker="Pathum Nissanka", non="Sameer Rizvi",
        dismissed_is_striker=True)
    sm._current_frame = 855
    event = _wicket_event_no_new_batter(dismissed="Pathum Nissanka")
    _reset_recorder(855)
    sm.apply_wicket_event(event)

    if len(sm._pending_post_wicket_cascade) != 1:
        return False, (
            f"enqueue: expected queue.len==1, got "
            f"{len(sm._pending_post_wicket_cascade)}")

    striker_before = sm.striker
    non_before = sm.non
    # Frame +81 — past TTL=80; no Scout new_batter. Bat slots show
    # only the dismissed batter (broadcast never resolved).
    sm._current_frame = 936
    sm.bat1_name = "Pathum Nissanka"
    sm.bat2_name = None
    _reset_recorder(936)
    sm._attempt_pending_cascade_drain()
    drain_records = _drained_records()

    if len(sm._pending_post_wicket_cascade) != 0:
        return False, (
            f"ttl: expected queue empty, got len="
            f"{len(sm._pending_post_wicket_cascade)}")
    expired = _records_with_tag(drain_records, "CASCADE-DRAIN-EXPIRED")
    if len(expired) != 1:
        return False, (
            f"ttl: expected 1 CASCADE-DRAIN-EXPIRED, got {len(expired)}")
    if expired[0].get("age_frames") != 81:
        return False, (
            f"ttl: expected age_frames=81, got "
            f"{expired[0].get('age_frames')}")
    if expired[0].get("ttl_frames") != 80:
        return False, (
            f"ttl: expected ttl_frames=80, got "
            f"{expired[0].get('ttl_frames')}")
    fired = _records_with_tag(drain_records, "POST-WICKET-CASCADE-DRAIN-FIRED")
    if fired:
        return False, (
            f"ttl: unexpected DRAIN-FIRED on expiry path; count="
            f"{len(fired)}")
    if sm.striker != striker_before or sm.non != non_before:
        return False, (
            f"ttl: striker/non mutated on expiry — was "
            f"({striker_before!r}, {non_before!r}), now "
            f"({sm.striker!r}, {sm.non!r})")
    return True, (
        f"enqueue at F855, no new_batter through F936; "
        f"CASCADE-DRAIN-EXPIRED (age=81, ttl=80); striker unchanged")


def _run_g3_cold_start_wipe() -> tuple[bool, str]:
    """G-3 — _clear_per_innings_sm_surface clears a non-empty queue
    and emits POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START.
    """
    sm, _sb = _build_pre_wicket_sm(
        striker="Pathum Nissanka", non="Sameer Rizvi",
        dismissed_is_striker=True)
    sm._current_frame = 855
    event = _wicket_event_no_new_batter(dismissed="Pathum Nissanka")
    _reset_recorder(855)
    sm.apply_wicket_event(event)

    if len(sm._pending_post_wicket_cascade) != 1:
        return False, (
            f"enqueue: expected queue.len==1, got "
            f"{len(sm._pending_post_wicket_cascade)}")

    # Frame +10 — innings reset path fires _clear_per_innings_sm_surface.
    sm._current_frame = 865
    _reset_recorder(865)
    sm._clear_per_innings_sm_surface()
    wipe_records = _drained_records()

    if len(sm._pending_post_wicket_cascade) != 0:
        return False, (
            f"wipe: expected queue empty, got len="
            f"{len(sm._pending_post_wicket_cascade)}")
    wiped = _records_with_tag(
        wipe_records, "POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START")
    if len(wiped) != 1:
        return False, (
            f"wipe: expected 1 WIPED-BY-COLD-START trace, got "
            f"{len(wiped)}")
    entries = wiped[0].get("wiped_entries") or []
    if len(entries) != 1:
        return False, (
            f"wipe: expected 1 entry in wiped_entries, got "
            f"{len(entries)}")
    if entries[0].get("frame_set_at") != 855:
        return False, (
            f"wipe: expected frame_set_at=855 in payload, got "
            f"{entries[0].get('frame_set_at')}")
    if entries[0].get("age") != 10:
        return False, (
            f"wipe: expected age=10 in payload, got "
            f"{entries[0].get('age')}")
    return True, (
        f"enqueue at F855, _clear_per_innings_sm_surface at F865; "
        f"WIPED-BY-COLD-START emitted with age=10")


def _run_g4_set_innings_2_wipe() -> tuple[bool, str]:
    """G-4 — Surface B W4 (audit 4f14dee §3.3 ordering site).
    set_innings_2 must emit WIPED-BY-COLD-START BEFORE __init__
    body re-runs, else the queue is silently emptied by the
    default-init and insight #17 fails.

    Mirrors audit §5 predicted-flip frame numbers (F855 enqueue,
    F859 wipe with age=4 — matching the step-5 trace's second
    SM-INNINGS-2-RESET fire).
    """
    sm, _sb = _build_pre_wicket_sm(
        striker="Pathum Nissanka", non="Sameer Rizvi",
        dismissed_is_striker=True)
    sm._current_frame = 855
    event = _wicket_event_no_new_batter(dismissed="Pathum Nissanka")
    _reset_recorder(855)
    sm.apply_wicket_event(event)

    if len(sm._pending_post_wicket_cascade) != 1:
        return False, (
            f"enqueue: expected queue.len==1, got "
            f"{len(sm._pending_post_wicket_cascade)}")

    sm._current_frame = 859
    _reset_recorder(859)
    sm.set_innings_2(target=200, batting_team="KKR",
                     reason="wickets_regressed")
    wipe_records = _drained_records()

    if len(sm._pending_post_wicket_cascade) != 0:
        return False, (
            f"wipe: expected queue empty, got len="
            f"{len(sm._pending_post_wicket_cascade)}")
    wiped = _records_with_tag(
        wipe_records, "POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START")
    if len(wiped) != 1:
        return False, (
            f"wipe: expected 1 WIPED-BY-COLD-START trace, got "
            f"{len(wiped)}")
    if wiped[0].get("transition_site") != "set_innings_2:wickets_regressed":
        return False, (
            f"wipe: expected transition_site="
            f"'set_innings_2:wickets_regressed', got "
            f"{wiped[0].get('transition_site')!r}")
    entries = wiped[0].get("wiped_entries") or []
    if len(entries) != 1:
        return False, (
            f"wipe: expected 1 entry, got {len(entries)}")
    if entries[0].get("frame_set_at") != 855:
        return False, (
            f"wipe: expected frame_set_at=855, got "
            f"{entries[0].get('frame_set_at')}")
    if entries[0].get("age") != 4:
        return False, (
            f"wipe: expected age=4 (audit §5 prediction), got "
            f"{entries[0].get('age')}")
    return True, (
        f"enqueue at F855, set_innings_2(reason=wickets_regressed) "
        f"at F859; WIPED emitted PRE-__init__ with age=4")


def _run_g5_force_cold_start_wipe() -> tuple[bool, str]:
    """G-5 — Surface B W3 (force_cold_start_recalibration). Closes
    the wipe-coverage gap at the external escape-hatch site.
    """
    sm, _sb = _build_pre_wicket_sm(
        striker="Pathum Nissanka", non="Sameer Rizvi",
        dismissed_is_striker=True)
    sm._current_frame = 855
    _reset_recorder(855)
    sm.apply_wicket_event(_wicket_event_no_new_batter(
        dismissed="Pathum Nissanka"))

    if len(sm._pending_post_wicket_cascade) != 1:
        return False, "enqueue failed"

    sm._current_frame = 862
    _reset_recorder(862)
    sm.force_cold_start_recalibration(reason="stuck_warm_consensus")
    wipe_records = _drained_records()

    if len(sm._pending_post_wicket_cascade) != 0:
        return False, (
            f"wipe: expected queue empty, got len="
            f"{len(sm._pending_post_wicket_cascade)}")
    wiped = _records_with_tag(
        wipe_records, "POST-WICKET-CASCADE-DRAIN-WIPED-BY-COLD-START")
    if len(wiped) != 1:
        return False, (
            f"wipe: expected 1 WIPED-BY-COLD-START, got {len(wiped)}")
    site = wiped[0].get("transition_site") or ""
    if not site.startswith("force_cold_start_recalibration:"):
        return False, (
            f"wipe: expected transition_site startswith "
            f"'force_cold_start_recalibration:', got {site!r}")
    entries = wiped[0].get("wiped_entries") or []
    if not entries or entries[0].get("age") != 7:
        return False, (
            f"wipe: expected age=7, got {entries[0].get('age') if entries else 'no-entries'}")
    if sm.mode != "COLD_START":
        return False, f"mode: expected COLD_START, got {sm.mode!r}"
    return True, (
        f"enqueue at F855, force_cold_start_recalibration at F862; "
        f"WIPED with age=7, mode=COLD_START")


def _run_g6_drain_trigger_noop_on_empty_queue() -> tuple[bool, str]:
    """G-6 — defense-in-depth (audit 4f14dee §3.6). COLD→WARM drain
    trigger fires _attempt_pending_cascade_drain unconditionally;
    when queue is empty the call must be a clean no-op (no
    DRAIN-FIRED, no DRAIN-EXPIRED).
    """
    sm, _sb = _build_pre_wicket_sm(
        striker="Pathum Nissanka", non="Sameer Rizvi",
        dismissed_is_striker=True)
    sm._current_frame = 870
    sm.bat1_name = "Pathum Nissanka"
    sm.bat2_name = "Tristan Stubbs"
    _reset_recorder(870)
    sm._attempt_pending_cascade_drain()
    recs = _drained_records()
    fired = _records_with_tag(recs, "POST-WICKET-CASCADE-DRAIN-FIRED")
    expired = _records_with_tag(recs, "CASCADE-DRAIN-EXPIRED")
    if fired or expired:
        return False, (
            f"empty-queue drain: expected no tags, got fired="
            f"{len(fired)} expired={len(expired)}")
    if sm._pending_post_wicket_cascade:
        return False, "queue: expected empty, got non-empty"
    return True, (
        "empty-queue drain at F870 emits no tags; queue unchanged")


CASES: list[tuple[str, callable]] = [
    ("G-1 happy-path drain (F855 → F893 Stubbs resolves)",
     _run_g1_happy_path),
    ("G-2 TTL expiry (no new_batter through ttl_frames=80)",
     _run_g2_ttl_expiry),
    ("G-3 cold-start wipe (_clear_per_innings_sm_surface clears queue)",
     _run_g3_cold_start_wipe),
    ("G-4 Surface B W4 (set_innings_2 pre-__init__ wipe — insight #17)",
     _run_g4_set_innings_2_wipe),
    ("G-5 Surface B W3 (force_cold_start_recalibration wipe)",
     _run_g5_force_cold_start_wipe),
    ("G-6 Surface B drain-trigger no-op on empty queue (defense-in-depth)",
     _run_g6_drain_trigger_noop_on_empty_queue),
]


def run_all() -> int:
    """Run all pending-cascade drain cases. Return 0 on PASS."""
    print(f"\n=== PENDING-CASCADE-DRAIN gate (Workstream G Shape A) "
          f"— {len(CASES)} cases ===")
    fails = 0
    for name, fn in CASES:
        ok, detail = fn()
        verdict = "PASS" if ok else "FAIL"
        print(f"  {verdict} {name}: {detail}")
        if not ok:
            fails += 1
    if fails:
        print(f"\nFAIL — {fails}/{len(CASES)} pending-cascade drain "
              f"cases regressed")
        return 1
    print(f"\nPASS — all {len(CASES)} pending-cascade drain cases hold")
    return 0


def test_pending_cascade_drain_holds() -> None:
    """pytest entry — Shape A scaffold must hold on all 3 cases."""
    rc = run_all()
    assert rc == 0, (
        "Pending-cascade drain regressed; see stdout for the first "
        "failing case.")


if __name__ == "__main__":
    sys.exit(run_all())

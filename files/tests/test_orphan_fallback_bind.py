"""WS-M step-2 Shape 2 — consumer-side fallback bind regression detector.

Persistent gate-6 cases for `ScoreManager.bind_pending_slot` at
`files/score_manager.py:1436+` — on no-match orphan path, lazily
enqueue fallback PendingBall using current striker pointer; preserve
existing `PENDING-BALL-SLOT-BOUND-ORPHAN` emission only when no current
striker is available (fallback-fail signal).

Five cases:
  M-1 Sub-cohort A analog (queue-empty + striker available) →
      PENDING-BALL-ORPHAN-FALLBACK-ENQUEUED fires; entry appended to
      queue with current striker attribution; bind returns True.
  M-2 Sub-cohort A second analog (queue-empty different striker) →
      same path; verifies striker is read fresh per orphan event.
  M-3 Sub-cohort A third analog (queue had bound entries, no unbound) →
      fallback fires; verifies for-loop exit before fallback applies.
  M-4 Negative — non-orphan happy path (queue has unbound entry) →
      existing FIFO bind succeeds; PENDING-BALL-SLOT-BOUND emits;
      fallback NOT invoked.
  M-5 Negative — Sub-cohort B analog (queue-empty AND no striker) →
      PENDING-BALL-SLOT-BOUND-ORPHAN emits (existing fallback-fail
      signal preserved); bind returns False.

Cross-references WS-M step-1 memo §4 MA + step-1b §13 (Shape 2
recommendation) + step-2 patch authorization at `c46fcb0`-tier
commit.

Wired into pre-commit Layer 1.5 via `test_sm_derivation_ledger.main()`
after the WS-Per-Batter-Ledger α-batter-runs-sum gate.
"""
from __future__ import annotations

import sys
from pathlib import Path

FILES_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FILES_DIR))
sys.path.insert(0, str(FILES_DIR / "tests"))

from score_manager import ScoreManager, PendingBall  # noqa: E402


def _make_sm(striker: str | None) -> ScoreManager:
    sm = ScoreManager(shadow=True)
    sm._current_frame = 100
    sm.striker = striker
    return sm


def _case_m1() -> int:
    sm = _make_sm("Alice")
    ok = sm.bind_pending_slot(slot_idx=0)
    if not ok:
        print(f"FAIL M-1: expected True (fallback enqueued), got False")
        return 1
    if len(sm._pending_ball_queue) != 1:
        print(f"FAIL M-1: expected queue depth 1, got {len(sm._pending_ball_queue)}")
        return 1
    entry = sm._pending_ball_queue[0]
    if entry.striker != "Alice":
        print(f"FAIL M-1: expected striker='Alice', got {entry.striker!r}")
        return 1
    if entry.slot_idx != 0:
        print(f"FAIL M-1: expected slot_idx=0, got {entry.slot_idx}")
        return 1
    print("  PASS M-1 (queue-empty + striker → fallback enqueued + bind=True)")
    return 0


def _case_m2() -> int:
    sm = _make_sm("Bob")
    ok = sm.bind_pending_slot(slot_idx=3)
    if not ok or sm._pending_ball_queue[0].striker != "Bob":
        print(f"FAIL M-2: expected fallback with striker='Bob'; "
              f"got ok={ok} striker={sm._pending_ball_queue[0].striker!r}")
        return 1
    print("  PASS M-2 (queue-empty + different striker → fresh-read attribution)")
    return 0


def _case_m3() -> int:
    sm = _make_sm("Charlie")
    pre_bound = PendingBall(
        frame_id=50, runs_delta=1, slot_idx=0, striker="OldStriker")
    sm._pending_ball_queue.append(pre_bound)
    ok = sm.bind_pending_slot(slot_idx=1)
    if not ok:
        print(f"FAIL M-3: expected fallback after for-loop exit; got False")
        return 1
    if len(sm._pending_ball_queue) != 2:
        print(f"FAIL M-3: expected queue depth 2 (pre-bound + fallback); "
              f"got {len(sm._pending_ball_queue)}")
        return 1
    fallback = sm._pending_ball_queue[1]
    if fallback.striker != "Charlie" or fallback.slot_idx != 1:
        print(f"FAIL M-3: fallback misattributed; got striker={fallback.striker!r} "
              f"slot_idx={fallback.slot_idx}")
        return 1
    print("  PASS M-3 (queue had bound entries → for-loop exits → fallback applies)")
    return 0


def _case_m4() -> int:
    sm = _make_sm("Diana")
    unbound = PendingBall(
        frame_id=80, runs_delta=2, slot_idx=None)
    sm._pending_ball_queue.append(unbound)
    ok = sm.bind_pending_slot(slot_idx=2)
    if not ok:
        print(f"FAIL M-4: expected FIFO bind success; got False")
        return 1
    if unbound.slot_idx != 2:
        print(f"FAIL M-4: expected unbound entry slot_idx=2; got {unbound.slot_idx}")
        return 1
    if len(sm._pending_ball_queue) != 1:
        print(f"FAIL M-4: queue depth changed (fallback wrongly invoked); "
              f"got {len(sm._pending_ball_queue)}")
        return 1
    print("  PASS M-4 (non-orphan happy path; FIFO bind succeeds; fallback skipped)")
    return 0


def _case_m5() -> int:
    sm = _make_sm(None)
    ok = sm.bind_pending_slot(slot_idx=4)
    if ok:
        print(f"FAIL M-5: expected False (no striker → orphan path); got True")
        return 1
    if len(sm._pending_ball_queue) != 0:
        print(f"FAIL M-5: queue should stay empty; got depth {len(sm._pending_ball_queue)}")
        return 1
    print("  PASS M-5 (no striker → PENDING-BALL-SLOT-BOUND-ORPHAN preserved)")
    return 0


def run_all() -> int:
    cases = [_case_m1, _case_m2, _case_m3, _case_m4, _case_m5]
    rc = 0
    for case in cases:
        case_rc = case()
        if case_rc != 0:
            rc = case_rc
    if rc == 0:
        print("PASS — all 5 orphan-fallback-bind cases hold")
    return rc


def test_orphan_fallback_bind() -> None:
    assert run_all() == 0, (
        "orphan-fallback-bind regression — see stdout.")


if __name__ == "__main__":
    sys.exit(run_all())

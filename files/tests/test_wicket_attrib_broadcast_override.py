"""C31 H-D2-Layer-1a — broadcast-vs-deterministic override at WICKET-ATTRIB.

Persistent gate-6 verification for the H-D2-Layer-1a fix shipped in C31.
Three cases cover the override-trigger boundary at the WICKET-ATTRIB
event-builder site:

- broadcast agrees with SM-derived striker → no override (canonical wins).
- broadcast disagrees with SM-derived striker AND broadcast populated →
  override fires, broadcast value is the dismissed name (F855 + F983
  cascade closure shape; predicted-flip per
  workstream_d_rotation_root_investigation.md §6).
- broadcast None / empty → fall through to SM-derived striker
  (regression protection — don't override based on absent broadcast).

Wired into pre-commit Layer 1.5 via test_sm_derivation_ledger.main()
after the C28 D1 bowler-dispatch-fallback test, mirroring the C15
pattern.
"""
from __future__ import annotations

import sys
from pathlib import Path

FILES_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FILES_DIR))

from test_pipeline import (  # noqa: E402
    _attribute_dismissed_with_broadcast_override,
)


class _RecordingTrace:
    def __init__(self):
        self.records: list[dict] = []

    def record(self, **kwargs):
        self.records.append(kwargs)


def _override_fired(records: list[dict]) -> bool:
    return any(
        r.get("tag") == "WICKET-ATTRIB-BROADCAST-OVERRIDE-APPLIED"
        for r in records)


def _run_case(name: str, striker: str | None, broadcast: str | None,
              expect_return: str | None,
              expect_override_fired: bool) -> tuple[bool, str]:
    tr = _RecordingTrace()
    result = _attribute_dismissed_with_broadcast_override(
        striker, broadcast, tr, 400)
    fired = _override_fired(tr.records)
    ok = (result == expect_return) and (fired == expect_override_fired)
    detail = (f"striker={striker!r} broadcast={broadcast!r} "
              f"result={result!r} expect={expect_return!r} "
              f"fired={fired} expect_fired={expect_override_fired}")
    return ok, detail


CASES: list[tuple] = [
    # (name, striker_canonical, pending_bcast_striker_key,
    #  expect_return, expect_override_fired)
    ("broadcast agrees → no override (canonical wins)",
     "Sameer Rizvi", "Sameer Rizvi", "Sameer Rizvi", False),
    ("broadcast disagrees AND populated → override fires (F855 shape)",
     "Pathum Nissanka", "Sameer Rizvi", "Sameer Rizvi", True),
    ("broadcast None → fall through (regression protection)",
     "Pathum Nissanka", None, "Pathum Nissanka", False),
]


def run_all() -> int:
    """Run all WICKET-ATTRIB broadcast-override cases. Return 0 on PASS."""
    print(f"\n=== WICKET-ATTRIB-BROADCAST-OVERRIDE gate (C31 / H-D2-Layer-1a) "
          f"— {len(CASES)} cases ===")
    fails = 0
    for case in CASES:
        name = case[0]
        ok, detail = _run_case(*case)
        verdict = "PASS" if ok else "FAIL"
        print(f"  {verdict} {name}: {detail}")
        if not ok:
            fails += 1
    if fails:
        print(f"\nFAIL — {fails}/{len(CASES)} WICKET-ATTRIB broadcast-"
              f"override cases regressed")
        return 1
    print(f"\nPASS — all {len(CASES)} WICKET-ATTRIB broadcast-override "
          f"cases hold")
    return 0


def test_wicket_attrib_broadcast_override_holds() -> None:
    """pytest entry — H-D2-Layer-1a override must hold on all 3 cases."""
    rc = run_all()
    assert rc == 0, (
        "WICKET-ATTRIB broadcast-override regressed; see stdout for "
        "the first failing case.")


if __name__ == "__main__":
    sys.exit(run_all())

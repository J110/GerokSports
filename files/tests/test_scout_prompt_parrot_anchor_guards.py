"""Workstream U step-2 — SCOUT_PROMPT_SHORT parrot-anchor guard gate.

Persistent contract-test for the UD-prime-A prompt-text extensions at
``files/eyes/vision.py:316-410`` SCOUT_PROMPT_SHORT body:

  U-1 Strengthened VISIBLE_TEXT (none) exit clause must explicitly
      authorize all-null demotion on unreadable frames (sponsor card /
      replay graphic / mid-cut / decoder-corrupted). Without this
      clause Scout mode-collapses onto canned structured fields rather
      than emitting the safe (none) + STRIP all-null shape, re-arming
      the cold-start parrot-anchor cascade roots enumerated in WS-U
      step-1 §1.

  U-2 Extended anti-priming bullets must forbid (a) generic round-
      score priors (100-3 / 150-4 / 200-5 / 250-6) and (b) graphic-
      overlay digit parrot (side-panel / OTS-panel / sponsor digits
      being parrot-anchored onto strip score / wickets / overs). These
      are the WS-O.c bogus-63 cohort + WS-Surface-E F1017 wickets-
      oscillation cohort source-frame guards.

Both cases are TEXT-CONTRACT tests: they assert the SCOUT_PROMPT_SHORT
constant contains the specific guard clauses. Dynamic VLM-output
parity verification (S33 phase 3) requires fresh Groq inference on
the DCKKR .mp4 frames and is documented in the WS-U step-2 commit
body — the parity argument for this commit rests on the static
gate-4 PASS at WS-U step-1 §7.2 (schema-preserving text-only
extension; reuses existing STRIP all-null + VT-(none) shape; zero
new output shapes; zero parser-touch).

Cross-references WS-U step-1 memo
``workstream_u_scout_prompt_parrot_anchor_rewrite_investigation.md``
§10.1 patch surface + §10.4 hypothesis enumeration (UD-prime-A
leading candidate) + §7 gate-by-gate audit.

Wired into pre-commit Layer 1.5 via
``test_sm_derivation_ledger.main()`` after the WS-O.b striker-anchor-
deferred gate (last gate prior to WS-U).
"""
from __future__ import annotations

import sys
from pathlib import Path

FILES_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FILES_DIR))

from eyes.vision import SCOUT_PROMPT_SHORT  # noqa: E402


_U1_REQUIRED_PHRASES = (
    "missing OR fully unreadable",
    "blank",
    "decoder-",
    "ad-occluded",
    "mid-cut",
    "sponsor-card only",
    "VISIBLE_TEXT: (none)",
    "Do NOT fabricate structured fields when the strip is unreadable",
)


_U2_REQUIRED_PHRASES = (
    "Forbidden score-shape priors",
    "100-3",
    "150-4",
    "200-5",
    "250-6",
    "Forbidden graphic-overlay digit parrot",
    "side-panel",
    "OTS-panel",
    "Strip values come from the strip alone",
)


def _run_case(label: str, required: tuple[str, ...]) -> int:
    missing = [p for p in required if p not in SCOUT_PROMPT_SHORT]
    if missing:
        print(
            f"FAIL {label}: SCOUT_PROMPT_SHORT missing required guard "
            f"clauses: {missing!r}"
        )
        return 1
    print(f"  PASS {label} ({len(required)} required phrases present)")
    return 0


def run_all() -> int:
    rc = 0
    rc |= _run_case(
        "U-1 strengthened VISIBLE_TEXT (none) unreadable-frame exit",
        _U1_REQUIRED_PHRASES,
    )
    rc |= _run_case(
        "U-2 extended anti-priming bullets (score-shape + OTS-digit)",
        _U2_REQUIRED_PHRASES,
    )
    if rc == 0:
        print(
            "PASS — all 2 SCOUT_PROMPT_SHORT parrot-anchor guard "
            "contracts hold"
        )
    return rc


def test_scout_prompt_parrot_anchor_guards() -> None:
    assert run_all() == 0, (
        "SCOUT_PROMPT_SHORT parrot-anchor guard regression — "
        "see stdout for missing clauses."
    )


if __name__ == "__main__":
    sys.exit(run_all())

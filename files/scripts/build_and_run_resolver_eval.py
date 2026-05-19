#!/usr/bin/env python3
"""Stage 2b eval-corpus assembly + accuracy gate runner.

For each known [GAP-DETECTED] event in the captured DC-vs-KKR Tier 1
and GT-vs-RR corpora, builds a SecondaryResolveRequest from real
Scout text and compares the LLM's resolved events against
hand-labeled ground truth (DC-vs-KKR ledger or GT-vs-RR commentary).

Outputs:
  - corpus JSONL at files/tests/fixtures/secondary_resolver_eval_corpus.jsonl
  - per-case eval output at /tmp/resolver_eval_results.jsonl
  - stdout: case-level accuracy + consistency-check rate
"""
from __future__ import annotations

import collections
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("SM_ORCHESTRATOR_RESOLVER", "1")
os.environ.setdefault("SM_ORCHESTRATOR_RESOLVER_LLM", "1")

from eyes.secondary_resolver import (  # noqa: E402
    SecondaryResolveRequest, ExpectedBallContext, ScoutContext,
    MatchState, DeltaObserved, get_resolver, reset_resolver,
)

DELIVERIES = ROOT / "logs" / "deliveries"
LEDGER_PATH = ROOT / "tests" / "fixtures" / "dc_vs_kkr_2026_152064_ledger.json"
CORPUS_OUT = ROOT / "tests" / "fixtures" / "secondary_resolver_eval_corpus.jsonl"
RESULTS_OUT = pathlib.Path("/tmp/resolver_eval_results.jsonl")


def event_canon(s: str) -> str:
    """Normalize event_type for cross-source comparison."""
    s = (s or "").upper().strip()
    return {
        "DOT": "ZERO", "0": "ZERO",
        "RUNS_1": "ONE", "1": "ONE", "SINGLE": "ONE",
        "RUNS_2": "TWO", "2": "TWO",
        "RUNS_3": "THREE", "3": "THREE",
        "RUNS_4": "FOUR", "BOUNDARY": "FOUR",
        "RUNS_5": "FIVE",
        "RUNS_6": "SIX",
        "OUT": "WICKET",
        "WD": "WIDE",
        "NB": "NO_BALL", "NOBALL": "NO_BALL",
    }.get(s, s)


def load_ledger() -> dict[str, dict]:
    j = json.loads(LEDGER_PATH.read_text())
    return {b["ball_id"]: b for b in j["balls"]}


def fetch_raw_frame(fixture: str, frame_id: int) -> dict | None:
    p = DELIVERIES / fixture / "scout_raw.jsonl"
    if not p.exists():
        return None
    with p.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if int(rec.get("frame_id", -1)) == frame_id:
                return rec
    return None


def fetch_prior_raw_texts(
    fixture: str, frame_id: int, n: int = 3
) -> list[str]:
    p = DELIVERIES / fixture / "scout_raw.jsonl"
    if not p.exists():
        return []
    prior: list[str] = []
    with p.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            fid = int(rec.get("frame_id", -1))
            if fid >= frame_id:
                break
            prior.append(rec.get("raw_response", "") or "")
    return prior[-n:]


def ledger_events_for_range(
    ledger: dict, prev_overs: str, new_overs: str
) -> list[dict]:
    """Return list of expected events for legal balls in (prev_overs, new_overs]."""
    def to_legal(o):
        w, b = str(o).split(".")
        return int(w) * 6 + int(b)
    prev_legal = to_legal(prev_overs)
    new_legal = to_legal(new_overs)
    out = []
    for legal in range(prev_legal + 1, new_legal + 1):
        over_n, ball_in_over = divmod(legal, 6)
        if ball_in_over == 0:
            ball_id = f"{over_n - 1}.6"
        else:
            ball_id = f"{over_n}.{ball_in_over}"
        b = ledger.get(ball_id)
        if b is None:
            continue
        out.append({
            "ball_id": ball_id,
            "event_type": event_canon(b.get("event_type")),
            "runs_off_bat": int(b.get("runs_off_bat", 0)),
        })
    return out


# -----------------------------------------------------------------
# Hand-labeled corpus: GAP-DETECTED events with expected events
# -----------------------------------------------------------------
# DC-vs-KKR cases — labels derived programmatically from ledger.
DC_KKR_GAP_CASES = [
    {
        "case_id": "dc_kkr_161246_F272",
        "fixture": "watch_20260514_161246",
        "frame_id": 272,
        "prev_overs": "3.2",
        "new_overs": "3.4",
        "prev_score_hint": 33,
        "new_score_hint": 34,
        "source_kind": "GAP-DETECTED",
    },
    {
        "case_id": "dc_kkr_161437_F254",
        "fixture": "watch_20260515_161437",
        "frame_id": 254,
        "prev_overs": "3.1",
        "new_overs": "3.4",
        "prev_score_hint": 29,
        "new_score_hint": 34,
        "source_kind": "GAP-DETECTED",
    },
    {
        "case_id": "dc_kkr_161437_F318",
        "fixture": "watch_20260515_161437",
        "frame_id": 318,
        "prev_overs": "4.0",
        "new_overs": "5.0",
        "prev_score_hint": 35,
        "new_score_hint": 45,
        "source_kind": "GAP-DETECTED",
    },
    {
        "case_id": "dc_kkr_175143_F253",
        "fixture": "watch_20260519_175143",
        "frame_id": 253,
        "prev_overs": "3.2",
        "new_overs": "3.4",
        "prev_score_hint": 33,
        "new_score_hint": 34,
        "source_kind": "GAP-DETECTED",
    },
    {
        "case_id": "dc_kkr_082523_F5",
        "fixture": "watch_20260519_082523",
        "frame_id": 5,
        "prev_overs": "0.2",
        "new_overs": "0.5",
        "prev_score_hint": 4,
        "new_score_hint": 6,
        "source_kind": "GAP-DETECTED",
    },
]

# GT-vs-RR — labels hand-extracted from commentary per-over table.
# Reference: files/tests/fixtures/gt_vs_rr_2026_commentary_first_innings.md
GT_RR_GAP_CASES = [
    {
        "case_id": "gt_rr_8a0c_F1527",
        "fixture": "8a0c6c14",
        "frame_id": 1527,
        "prev_overs": "3.3",
        "new_overs": "4.2",
        "prev_score_hint": 38,
        "new_score_hint": 52,
        "source_kind": "GAP-DETECTED",
        "expected_events_manual": [
            # 3.4: over 4 ball 4 → "0 0 6 4" sequence in over 4 (Archer); ball 4 = 0
            {"ball_id": "3.4", "event_type": "ZERO", "runs_off_bat": 0},
            # 3.5: Jofra Archer over → SIX (slow length, Sai hits over deep mid-wicket)
            {"ball_id": "3.5", "event_type": "SIX", "runs_off_bat": 6},
            # 3.6: FOUR (over-end of Archer; "4 1 0 0 6 4")
            {"ball_id": "3.6", "event_type": "FOUR", "runs_off_bat": 4},
            # 4.1: Brijesh Sharma over 5 starts "4 0 6 0 4 1" — ball 1 = FOUR
            {"ball_id": "4.1", "event_type": "FOUR", "runs_off_bat": 4},
            # 4.2: 0 (dot)
            {"ball_id": "4.2", "event_type": "ZERO", "runs_off_bat": 0},
        ],
    },
]


def build_corpus_entry(case: dict, ledger: dict) -> dict | None:
    raw_rec = fetch_raw_frame(case["fixture"], case["frame_id"])
    if raw_rec is None:
        return None
    prior_texts = fetch_prior_raw_texts(
        case["fixture"], case["frame_id"], n=3)

    if "expected_events_manual" in case:
        expected = case["expected_events_manual"]
    else:
        expected = ledger_events_for_range(
            ledger, case["prev_overs"], case["new_overs"])
    if not expected:
        return None

    delta_balls = len(expected)
    delta_score = sum(int(e["runs_off_bat"]) for e in expected)

    # Reconcile prev/new score hints with derived delta where possible.
    new_score = case.get("new_score_hint")
    prev_score = (
        new_score - delta_score
        if new_score is not None else case.get("prev_score_hint"))
    if prev_score is None:
        prev_score = 0

    over_str, ball_str = case["prev_overs"].split(".")
    prev_legal = int(over_str) * 6 + int(ball_str)
    first_missing = prev_legal + 1

    entry = {
        "case_id": case["case_id"],
        "source_kind": case["source_kind"],
        "fixture": case["fixture"],
        "frame_id": case["frame_id"],
        "request": {
            "frame_id": case["frame_id"],
            "expected_ball": {
                "over": first_missing // 6,
                "ball": (first_missing % 6) + 1,
                "legal_ball_count": first_missing,
            },
            "scout_context": {
                "strip": raw_rec.get("raw_response", ""),
            },
            "match_state": {
                "innings": 1,
                "score_before": prev_score,
                "overs_before": float(case["prev_overs"]),
                "overs_after": float(case["new_overs"]),
                "score_after": new_score,
                "wickets_after": 0,
            },
            "delta_observed": {"balls": delta_balls},
            "delta_score": delta_score,
            "prior_scout_texts": prior_texts,
        },
        "expected_events": expected,
    }
    return entry


def request_from_entry(entry: dict) -> SecondaryResolveRequest:
    r = entry["request"]
    eb = r["expected_ball"]
    ms = r["match_state"]
    sc = r["scout_context"]
    do = r["delta_observed"]
    return SecondaryResolveRequest(
        frame_id=int(r["frame_id"]),
        expected_ball=ExpectedBallContext(
            over=eb["over"], ball=eb["ball"],
            legal_ball_count=eb["legal_ball_count"]),
        scout_context=ScoutContext(strip=sc.get("strip")),
        match_state=MatchState(
            innings=ms.get("innings"),
            score_before=ms.get("score_before"),
            overs_before=ms.get("overs_before"),
            overs_after=ms.get("overs_after"),
            score_after=ms.get("score_after"),
            wickets_after=ms.get("wickets_after"),
        ),
        delta_observed=DeltaObserved(balls=int(do["balls"])),
        delta_score=int(r["delta_score"]),
        prior_scout_texts=r.get("prior_scout_texts") or [],
    )


def grade_response(
    expected: list[dict], resp_events: list, resp_source: str
) -> dict:
    if resp_source not in ("llm", "replay"):
        return {
            "case_pass": False, "consistency_pass": False,
            "reason": f"source={resp_source} (no events returned)",
            "per_ball_matches": 0, "per_ball_total": len(expected),
        }
    consistency_pass = len(resp_events) == len(expected)
    if not consistency_pass:
        return {
            "case_pass": False, "consistency_pass": False,
            "reason": f"len mismatch {len(resp_events)} vs {len(expected)}",
            "per_ball_matches": 0, "per_ball_total": len(expected),
        }
    matches = 0
    details = []
    for exp, got in zip(expected, resp_events):
        exp_runs = int(exp["runs_off_bat"])
        got_runs = int(got.runs_off_bat)
        exp_event = event_canon(exp["event_type"])
        got_event = event_canon(got.event_type)
        ok = (exp_runs == got_runs) and (
            exp_event == got_event or
            (exp_event in {"ZERO", "ONE", "TWO", "THREE", "FOUR",
                           "FIVE", "SIX"} and got_runs == exp_runs))
        details.append({
            "exp": exp, "got_event": got_event, "got_runs": got_runs,
            "match": ok,
        })
        if ok:
            matches += 1
    case_pass = matches == len(expected)
    return {
        "case_pass": case_pass, "consistency_pass": consistency_pass,
        "reason": "ok" if case_pass else "per-ball mismatch",
        "per_ball_matches": matches,
        "per_ball_total": len(expected),
        "ball_details": details,
    }


def main():
    ledger = load_ledger()

    cases = DC_KKR_GAP_CASES + GT_RR_GAP_CASES
    print(f"Building corpus from {len(cases)} hand-labeled cases...")

    corpus = []
    for case in cases:
        entry = build_corpus_entry(case, ledger)
        if entry is None:
            print(f"  SKIP {case['case_id']} — could not build")
            continue
        corpus.append(entry)
        evs = ", ".join(
            f"{e['event_type']}({e['runs_off_bat']})"
            for e in entry["expected_events"])
        print(f"  {entry['case_id']:<25} expected: [{evs}]")

    CORPUS_OUT.parent.mkdir(parents=True, exist_ok=True)
    with CORPUS_OUT.open("w") as fh:
        for e in corpus:
            fh.write(json.dumps(e) + "\n")
    print(f"\nCorpus written to {CORPUS_OUT}  ({len(corpus)} cases)")
    print()

    if not os.environ.get("GROQ_API_KEY"):
        print("GROQ_API_KEY not set — skipping LLM eval. Corpus built only.")
        return

    reset_resolver()
    resolver = get_resolver()

    print("Running LLM eval...")
    results = []
    case_passes = 0
    consistency_passes = 0
    total_per_ball_matches = 0
    total_per_ball = 0
    api_errors = 0
    inconsistent_responses = 0

    for entry in corpus:
        req = request_from_entry(entry)
        resp = resolver.resolve(req)
        grade = grade_response(
            entry["expected_events"], resp.events, resp.source)
        results.append({
            "case_id": entry["case_id"],
            "source_kind": entry["source_kind"],
            "resp_source": resp.source,
            "resp_event_type": resp.event_type,
            "resp_confidence": resp.confidence,
            "expected": entry["expected_events"],
            "grade": grade,
            "resp_reasoning": resp.reasoning,
        })
        case_passes += int(grade["case_pass"])
        consistency_passes += int(grade["consistency_pass"])
        total_per_ball_matches += grade["per_ball_matches"]
        total_per_ball += grade["per_ball_total"]
        if resp.source == "llm-error":
            api_errors += 1
        if resp.source == "llm-inconsistent":
            inconsistent_responses += 1
        ev_summary = " ".join(
            f"{e['event_type']}({e['runs_off_bat']})"
            for e in entry["expected_events"])
        got_summary = " ".join(
            f"{event_canon(e.event_type)}({e.runs_off_bat})"
            for e in resp.events) if resp.events else "(none)"
        verdict = (
            "PASS" if grade["case_pass"]
            else ("INCONSISTENT" if not grade["consistency_pass"]
                  else "MISMATCH"))
        print(f"  [{verdict:<12}] {entry['case_id']:<25} "
              f"src={resp.source:<18} conf={resp.confidence:.2f}")
        print(f"      expected: {ev_summary}")
        print(f"      got:      {got_summary}")

    with RESULTS_OUT.open("w") as fh:
        for r in results:
            fh.write(json.dumps(r, default=str) + "\n")

    print()
    print("=" * 72)
    print("ACCURACY GATE")
    print("=" * 72)
    n = len(corpus)
    case_pct = 100.0 * case_passes / n if n else 0.0
    cons_pct = 100.0 * consistency_passes / n if n else 0.0
    ball_pct = (
        100.0 * total_per_ball_matches / total_per_ball
        if total_per_ball else 0.0)
    print(f"Corpus size:                  {n} cases")
    print(f"Case-level accuracy:          "
          f"{case_passes}/{n}  ({case_pct:.1f}%)  "
          f"[gate: ≥80%]")
    print(f"Consistency-check rate:       "
          f"{consistency_passes}/{n}  ({cons_pct:.1f}%)  "
          f"[gate: ≥90%]")
    print(f"Per-ball derivation accuracy: "
          f"{total_per_ball_matches}/{total_per_ball}  ({ball_pct:.1f}%)")
    print(f"API errors:                   {api_errors}")
    print(f"Inconsistent responses:       {inconsistent_responses}")
    gate_pass = case_pct >= 80 and cons_pct >= 90
    print()
    print(f"GATE: {'PASS — production-enable approved' if gate_pass else 'FAIL — escalate model or iterate prompt'}")
    print()
    print(f"per-case results at {RESULTS_OUT}")


if __name__ == "__main__":
    main()

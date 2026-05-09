"""Replay BALL EVENT lines from a pipeline log through the new
event-driven stat accumulator and diff against ground truth.

Validates ScoreManager._accumulate_stats_from_event end-to-end:
- pulls (type, over, runs) from each [BALL EVENT] line,
- cross-walks the same-frame DETAIL line for striker / bowler,
- filters to 1st innings,
- calls sm._accumulate_stats_from_event for each event,
- dumps scoreboard.batting_card / bowling_card,
- diffs vs ground truth, writes markdown report.

Usage:
    python files/scripts/replay_validate_stats.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eyes"))

from eyes.scoreboard import Scoreboard  # noqa: E402
from score_manager import ScoreManager  # noqa: E402

LOG_PATH = ROOT / "logs" / "pipeline-20260508-dc-vs-csk-1stinns.log"
GT_PATH = ROOT / "scripts" / "ground_truth_20260508_dc_csk_inn1.json"
REPORT_PATH = ROOT / "scripts" / "replay_validate_stats_report.md"

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
FRAME_RE = re.compile(r"F(\d+)")
BALL_EVENT_RE = re.compile(
    r"\[BALL EVENT [✓X?]\]\s+(?P<type>[A-Z0-9_]+)\s+\|\s+"
    r"(?P<over>[\d.]+|None)\s+\|\s+\+?(?P<runs>-?\d+)\s+runs"
)
DETAIL_FIELDS = (
    "AFTER_innings", "AFTER_striker", "AFTER_non", "AFTER_bowl",
    "AFTER_bat1", "AFTER_bat2", "batting_team",
    "ball_event", "ball_event_runs", "striker_this_ball",
    "dismissal_mode", "broadcast_extra",
)
BOWLER_NAME_RE = re.compile(r"^\s*(?P<name>.+?)\s+\d+-\d+\s*\(.*\)\s*$")


def strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s)


def parse_detail_line(line: str) -> dict | None:
    if "DETAIL|" not in line:
        return None
    out: dict = {}
    parts = line.split("|")
    for p in parts:
        if "=" not in p:
            continue
        k, _, v = p.partition("=")
        k = k.strip()
        v = v.strip()
        if k in DETAIL_FIELDS:
            out[k] = v
    return out


def parse_bowler_name(after_bowl: str) -> str | None:
    """Parse 'Akeal Hosein 1-19 (4.0)' → 'Akeal Hosein'. '— ?-? (?)' → None."""
    if not after_bowl or after_bowl.startswith(("—", "?")):
        return None
    m = BOWLER_NAME_RE.match(after_bowl)
    return m.group("name").strip() if m else None


def load_events(log_path: Path) -> list[dict]:
    """Stream the log, collecting (frame -> {detail, ball_events})."""
    frames: dict[int, dict] = {}
    with log_path.open("r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = strip_ansi(raw)
            fm = FRAME_RE.search(line)
            if not fm:
                continue
            frame = int(fm.group(1))
            entry = frames.setdefault(frame, {"detail": None, "events": []})

            d = parse_detail_line(line)
            if d:
                entry["detail"] = d
                continue

            be = BALL_EVENT_RE.search(line)
            if be and "TEST]" in line:
                entry["events"].append({
                    "type": be.group("type"),
                    "over": be.group("over"),
                    "runs": int(be.group("runs")),
                })

    flat: list[dict] = []
    for frame in sorted(frames.keys()):
        entry = frames[frame]
        if not entry["events"]:
            continue
        d = entry["detail"] or {}
        for ev in entry["events"]:
            ev["frame"] = frame
            ev["batting_team"] = d.get("batting_team", "—")
            ev["after_innings"] = d.get("AFTER_innings", "1")
            ev["striker"] = (
                d.get("striker_this_ball", "—") if d.get("striker_this_ball", "—") not in ("—", "")
                else d.get("AFTER_striker", "—"))
            ev["bowler"] = parse_bowler_name(d.get("AFTER_bowl", "—"))
            ev["dismissal_mode"] = d.get("dismissal_mode", "—")
            flat.append(ev)
    return flat


def normalize_name(s: str | None) -> str | None:
    if not s or s in ("—", "", "None"):
        return None
    return s.strip()


def map_event_to_accumulator(ev: dict) -> dict | None:
    """Translate a parsed log event to the dict shape that
    ScoreManager._accumulate_stats_from_event consumes."""
    log_type = ev["type"]
    runs = ev["runs"]
    if log_type == "DOT":
        return {"type": "DOT", "runs": 0, "striker": ev["striker"]}
    if log_type == "FOUR":
        return {"type": "FOUR", "runs": 4, "striker": ev["striker"]}
    if log_type == "SIX":
        return {"type": "SIX", "runs": 6, "striker": ev["striker"]}
    if log_type.endswith("_RUNS"):
        n = int(log_type.split("_")[0])
        return {"type": "RUNS", "runs": n, "batter_runs": n,
                "striker": ev["striker"]}
    if log_type == "EXTRA":
        return {"type": "EXTRA", "runs": runs, "striker": ev["striker"]}
    if log_type == "WICKET":
        d_mode = (ev.get("dismissal_mode") or "").lower()
        wkt_kind = ("run_out" if "run" in d_mode and "out" in d_mode
                    else (d_mode.replace(" ", "_") if d_mode and d_mode != "—"
                          else "bowler_wicket"))
        return {"type": "WICKET", "runs": runs, "legal": True,
                "wicket_type": wkt_kind, "striker": ev["striker"]}
    if log_type == "WICKET_LATE":
        # Treat as a bowler-attributable wicket retroactively committed.
        return {"type": "WICKET", "runs": runs, "legal": True,
                "wicket_type": "bowler_wicket", "striker": ev["striker"]}
    # MULTI_BALL / DRS_NOT_OUT / unknown — skip; accumulator returns
    # early for MULTI_BALL anyway, DRS_NOT_OUT credits nothing.
    return None


def setup_state(gt: dict) -> tuple[Scoreboard, ScoreManager]:
    bat_xi = [b["name"] for b in gt["batters"]] + gt.get("did_not_bat", [])
    bowl_xi = [b["name"] for b in gt["bowlers"]]
    bat_squad = bat_xi + gt.get("dc_bench_not_in_xi", [])
    bowl_squad = bowl_xi + gt.get("kkr_bench_not_in_xi", [])
    sb = Scoreboard()
    sb.setup_innings(
        batting_team=gt["batting_team"],
        bowling_team=gt["bowling_team"],
        batting_squad=bat_squad,
        bowling_squad=bowl_squad,
        batting_xi=bat_xi,
        bowling_xi=bowl_xi,
    )
    sm = ScoreManager(shadow=False)
    sm.scoreboard = sb
    return sb, sm


def replay(events: list[dict], sm: ScoreManager) -> dict:
    """Drive sm._accumulate_stats_from_event for each event. Decouples
    batter-side and bowler-side credit so events with an unresolvable
    bowler still credit the batter (the log's AFTER_bowl was broken
    throughout this match — see report)."""
    counts = {
        "total_events": 0, "applied": 0,
        "applied_bat_only": 0, "applied_both": 0,
        "skipped_multiball": 0, "skipped_drs": 0, "skipped_other": 0,
        "skipped_no_striker": 0, "no_bowler_in_log": 0,
        "bowler_unresolvable": 0,
    }
    for ev in events:
        counts["total_events"] += 1
        if ev["after_innings"] not in ("1", "—") or ev["batting_team"] not in ("Delhi Capitals", "—"):
            counts["skipped_other"] += 1
            continue
        log_type = ev["type"]
        if log_type == "MULTI_BALL":
            counts["skipped_multiball"] += 1
            continue
        if log_type == "DRS_NOT_OUT":
            counts["skipped_drs"] += 1
            continue
        mapped = map_event_to_accumulator(ev)
        if mapped is None:
            counts["skipped_other"] += 1
            continue
        striker = normalize_name(mapped.get("striker"))
        bowler = normalize_name(ev.get("bowler"))
        if not striker:
            counts["skipped_no_striker"] += 1
            continue
        sm.striker = striker
        sm._current_frame = ev["frame"]
        if bowler:
            # Probe whether bowler is even in the squad we built. If
            # not (log shows wrong bowler — e.g. opp-team player or
            # bench), credit only the batter side.
            sm.bowler_name = bowler
            resolved = sm.scoreboard.resolve_name(bowler)
            card_key = (sm.scoreboard._find_card_key(
                resolved, sm.scoreboard.bowling_card)
                if resolved else None)
            if card_key is None:
                counts["bowler_unresolvable"] += 1
                sm.bowler_name = None
                sm._accumulate_stats_from_event(mapped)
                counts["applied_bat_only"] += 1
            else:
                sm._accumulate_stats_from_event(mapped)
                counts["applied_both"] += 1
        else:
            counts["no_bowler_in_log"] += 1
            sm.bowler_name = None
            sm._accumulate_stats_from_event(mapped)
            counts["applied_bat_only"] += 1
        counts["applied"] += 1
    return counts


def diff_against_ground_truth(sb: Scoreboard, gt: dict) -> dict:
    bat_diff = []
    for gt_b in gt["batters"]:
        name = gt_b["name"]
        # fuzzy match: pipeline may store full or short name
        sb_entry = None
        for k, v in sb.batting_card.items():
            if name.lower() in k.lower() or k.lower() in name.lower():
                sb_entry = v
                sb_name = k
                break
        if sb_entry is None:
            bat_diff.append({
                "name": name, "found": False,
                "gt": gt_b, "sb": None, "delta": None})
            continue
        bat_diff.append({
            "name": name, "found": True, "sb_name": sb_name,
            "gt": gt_b,
            "sb": {
                "runs": sb_entry.get("runs"),
                "balls": sb_entry.get("balls"),
                "fours": sb_entry.get("fours"),
                "sixes": sb_entry.get("sixes"),
                "status": sb_entry.get("status"),
            },
            "delta": {
                "runs": (sb_entry.get("runs") or 0) - gt_b["runs"],
                "balls": (sb_entry.get("balls") or 0) - gt_b["balls"],
                "fours": (sb_entry.get("fours") or 0) - gt_b["fours"],
                "sixes": (sb_entry.get("sixes") or 0) - gt_b["sixes"],
            },
        })

    bowl_diff = []
    for gt_b in gt["bowlers"]:
        name = gt_b["name"]
        sb_entry = None
        sb_name = None
        for k, v in sb.bowling_card.items():
            if name.lower() in k.lower() or k.lower() in name.lower():
                sb_entry = v
                sb_name = k
                break
        if sb_entry is None:
            bowl_diff.append({
                "name": name, "found": False,
                "gt": gt_b, "sb": None, "delta": None})
            continue
        # parse overs strings into balls for delta math
        def _ov_to_balls(ov):
            if ov is None:
                return 0
            s = str(ov)
            if "." in s:
                w, b = s.split(".", 1)
                return int(w) * 6 + int(b[:1] or 0)
            return int(float(s)) * 6
        bowl_diff.append({
            "name": name, "found": True, "sb_name": sb_name,
            "gt": gt_b,
            "sb": {
                "overs": sb_entry.get("overs"),
                "runs": sb_entry.get("runs"),
                "wickets": sb_entry.get("wickets"),
            },
            "delta": {
                "balls": _ov_to_balls(sb_entry.get("overs"))
                         - _ov_to_balls(gt_b["overs"]),
                "runs": (sb_entry.get("runs") or 0) - gt_b["runs"],
                "wickets": (sb_entry.get("wickets") or 0) - gt_b["wickets"],
            },
        })
    return {"batters": bat_diff, "bowlers": bowl_diff}


def write_report(counts: dict, diff: dict, gt: dict,
                 sb: Scoreboard, report_path: Path) -> None:
    lines: list[str] = []
    lines.append("# Replay validation: derive-not-detect vs ground truth")
    lines.append("")
    lines.append(f"- Match: {gt['match']}")
    lines.append(f"- Innings: {gt['innings']}  ground truth = "
                 f"{gt['total']['runs']}/{gt['total']['wickets']} "
                 f"({gt['total']['overs']})")
    lines.append("")
    lines.append("## Replay coverage")
    lines.append("")
    lines.append("| Bucket | Count |")
    lines.append("|---|---|")
    for k in ("total_events", "applied", "applied_both",
              "applied_bat_only", "bowler_unresolvable",
              "no_bowler_in_log",
              "skipped_multiball", "skipped_drs",
              "skipped_no_striker", "skipped_other"):
        lines.append(f"| {k} | {counts[k]} |")
    lines.append("")
    lines.append("**Notes:**")
    lines.append("- **MULTI_BALL** events are intentionally skipped — they "
                 "represent absorbed-ball gaps with unknown distribution; "
                 "the production accumulator also returns early.")
    lines.append("- **bowler_unresolvable** = log's `AFTER_bowl` field named a "
                 "player not in the bowling squad (e.g. opp-team player, "
                 "bench player). Batter side still credited; bowler side "
                 "skipped.")
    lines.append("- **no_bowler_in_log** = `AFTER_bowl` was placeholder "
                 "(`— ?-? (?)`); same handling.")
    lines.append("- The 20-over innings has ~120 legal balls; the log "
                 "captured 111 BALL EVENT lines, so detection-side loss "
                 "bounds the upper achievable totals.")
    lines.append("")

    lines.append("## Batters")
    lines.append("")
    lines.append("| Batter | GT runs(b) 4s/6s out? | Replay runs(b) 4s/6s status | Δrun/Δb/Δ4/Δ6 | Verdict |")
    lines.append("|---|---|---|---|---|")
    for d in diff["batters"]:
        gt_b = d["gt"]
        gt_str = (f"{gt_b['runs']}({gt_b['balls']}) "
                  f"{gt_b['fours']}/{gt_b['sixes']} "
                  f"{'out' if gt_b['out'] else 'no'}")
        if not d["found"]:
            lines.append(f"| {d['name']} | {gt_str} | NOT FOUND | — | (c) name resolution miss |")
            continue
        sb = d["sb"]; dl = d["delta"]
        sb_str = (f"{sb['runs']}({sb['balls']}) "
                  f"{sb['fours']}/{sb['sixes']} {sb['status']}")
        dlt = f"{dl['runs']:+d}/{dl['balls']:+d}/{dl['fours']:+d}/{dl['sixes']:+d}"
        if all(v == 0 for v in dl.values()):
            verdict = "✓ exact"
        elif all(v <= 0 for v in dl.values()):
            verdict = "(d) detection-loss undershoot"
        elif any(v > 0 for v in dl.values()):
            verdict = "?? overshoot — investigate"
        else:
            verdict = "mixed delta"
        lines.append(f"| {d['name']} | {gt_str} | {sb_str} | {dlt} | {verdict} |")
    lines.append("")

    lines.append("## Bowlers")
    lines.append("")
    lines.append("| Bowler | GT O R W | Replay O R W | Δballs/Δr/Δw | Verdict |")
    lines.append("|---|---|---|---|---|")
    for d in diff["bowlers"]:
        gt_b = d["gt"]
        gt_str = f"{gt_b['overs']} {gt_b['runs']}-{gt_b['wickets']}"
        if not d["found"]:
            lines.append(f"| {d['name']} | {gt_str} | NOT FOUND | — | (c) name resolution miss |")
            continue
        sb_e = d["sb"]; dl = d["delta"]
        sb_str = f"{sb_e['overs']} {sb_e['runs']}-{sb_e['wickets']}"
        dlt = f"{dl['balls']:+d}/{dl['runs']:+d}/{dl['wickets']:+d}"
        if all(v == 0 for v in dl.values()):
            verdict = "✓ exact"
        elif all(v <= 0 for v in dl.values()):
            verdict = "(d) detection-loss undershoot"
        elif any(v > 0 for v in dl.values()):
            verdict = "?? overshoot — investigate"
        else:
            verdict = "mixed delta"
        lines.append(f"| {d['name']} | {gt_str} | {sb_str} | {dlt} | {verdict} |")
    lines.append("")

    # Totals
    sb_runs = sum((b["sb"]["runs"] or 0) for b in diff["batters"] if b["found"])
    sb_balls = sum((b["sb"]["balls"] or 0) for b in diff["batters"] if b["found"])
    sb_fours = sum((b["sb"]["fours"] or 0) for b in diff["batters"] if b["found"])
    sb_sixes = sum((b["sb"]["sixes"] or 0) for b in diff["batters"] if b["found"])
    lines.append("## Totals")
    lines.append("")
    lines.append(f"- GT batter-runs total: {sum(b['runs'] for b in gt['batters'])}")
    lines.append(f"- Replay batter-runs total: {sb_runs}")
    lines.append(f"- GT balls faced total: {sum(b['balls'] for b in gt['batters'])}")
    lines.append(f"- Replay balls faced total: {sb_balls}")
    lines.append(f"- GT 4s/6s: {sum(b['fours'] for b in gt['batters'])}/"
                 f"{sum(b['sixes'] for b in gt['batters'])}")
    lines.append(f"- Replay 4s/6s: {sb_fours}/{sb_sixes}")
    lines.append("")
    lines.append("## Verdict legend")
    lines.append("")
    lines.append("- (a) event inference bug — wrong runs/wicket attribution at "
                 "a known frame (would need event-by-event audit).")
    lines.append("- (b) accumulator bug — delta math wrong (would show as "
                 "non-zero deltas with full-coverage events).")
    lines.append("- (c) name resolution gate dropped a legitimate write.")
    lines.append("- (d) detection error from atoms — out of scope; the upstream "
                 "log lost the event entirely.")
    lines.append("")
    lines.append(f"Report generated by `files/scripts/replay_validate_stats.py`")
    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    gt = json.loads(GT_PATH.read_text())
    events = load_events(LOG_PATH)
    sb, sm = setup_state(gt)
    counts = replay(events, sm)
    diff = diff_against_ground_truth(sb, gt)
    write_report(counts, diff, gt, sb, REPORT_PATH)
    print(f"Replayed {counts['applied']} of {counts['total_events']} events "
          f"(both bat+bowl: {counts['applied_both']}, "
          f"bat only: {counts['applied_bat_only']}; "
          f"bowler unresolvable: {counts['bowler_unresolvable']}, "
          f"no bowler in log: {counts['no_bowler_in_log']}; "
          f"multi-ball: {counts['skipped_multiball']}, "
          f"DRS: {counts['skipped_drs']}).")
    print(f"Report: {REPORT_PATH.relative_to(ROOT.parent)}")


if __name__ == "__main__":
    main()

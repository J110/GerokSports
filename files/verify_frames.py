"""Frame-level UI verification: compare every DETAIL log field against ground truth.

Usage:
    python verify_frames.py <log_file> [--out report.md] [--start-frame N] [--end-frame M] [--verbose]
"""
from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ANSI = re.compile(r'\x1b\[[0-9;]*m')

KNOWN_FIELDS = [
    'tag=', 'qwen=', 'scout=', 'action=',
    'ext_score=', 'ext_bat=', 'ext_bowl=',
    'scorer_changes=', 'yolo=',
    'BEFORE_score=', 'BEFORE_bat1=', 'BEFORE_bat2=',
    'BEFORE_bowl=', 'BEFORE_this_over=',
    'AFTER_score=', 'AFTER_bat1=', 'AFTER_bat2=',
    'AFTER_bowl=', 'AFTER_this_over=', 'AFTER_this_over_src=',
    'AFTER_striker=', 'AFTER_non=', 'AFTER_run_rate=',
    'AFTER_target=', 'AFTER_innings=', 'AFTER_partnership=',
    'AFTER_fow_count=',
    'AFTER_field=',
    'ball_event=',
    'ball_event_runs=', 'ball_event_over=',
    'ball_event_extra=', 'ball_event_free_hit=',
    'broadcast_extra=',
    'dismissal_mode=',
    'striker_this_ball=',
    'delivery_length=', 'delivery_line=', 'delivery_angle=',
    'delivery_shot=', 'delivery_direction=', 'delivery_elevation=',
    'delivery_bounce=',
    'delivery_dets=', 'delivery_det_rate=',
    'delivery_dir_zone=', 'delivery_dir_conf=',
    'speed_kph=',
    'venue=', 'batting_team=', 'match_info=',
    'completed_over=', 'completed_over_runs=',
    'drs_state=',
    'corrections=',
    'lat_vision=', 'lat_extract=', 'lat_scorer=', 'lat_field=',
    'lat_comm=', 'lat_code=', 'lat_total=',
    'comm_bowler=',
    'comm_wire=', 'comm_storyteller=', 'comm_analyst=', 'comm_colour=',
    'comm_wire_ms=', 'comm_story_ms=', 'comm_analyst_ms=', 'comm_colour_ms=',
]

FIELDING_POSITIONS = {
    'point', 'cover', 'covers', 'mid-on', 'mid on', 'midon', 'mid-off',
    'mid off', 'midoff', 'mid-wicket', 'midwicket', 'mid wicket',
    'square leg', 'square-leg', 'fine leg', 'fine-leg', 'third man',
    'third-man', 'slip', 'slips', 'gully', 'long-on', 'long on',
    'long-off', 'long off', 'deep midwicket', 'deep mid-wicket',
    'deep square', 'deep fine', 'backward point', 'forward short',
    'silly point', 'silly mid', 'short leg', 'leg slip', 'backward square',
    'cow corner', 'extra cover', 'deep cover', 'deep point',
    'long leg', 'sweeper', 'deep extra',
}

FIELDING_RE = re.compile(
    r'\b(?:' + '|'.join(re.escape(p) for p in sorted(FIELDING_POSITIONS, key=len, reverse=True)) + r')\b',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Verdict:
    field: str
    expected: str
    actual: str
    verdict: str  # CORRECT / MISMATCH / MISSING / DELAYED / FABRICATED / SKIP
    detail: str = ""


@dataclass
class FrameAudit:
    frame_id: str
    frame_type: str
    verdicts: list[Verdict] = field(default_factory=list)

    @property
    def issues(self) -> list[Verdict]:
        return [v for v in self.verdicts if v.verdict not in ("CORRECT", "SKIP")]


# ---------------------------------------------------------------------------
# Parsing helpers (aligned with parse_detail_log.py)
# ---------------------------------------------------------------------------

def strip_ansi(s: str) -> str:
    return ANSI.sub('', s)


def extract_fields(detail_str: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    text = detail_str
    for key in KNOWN_FIELDS:
        idx = text.find(key)
        if idx < 0:
            continue
        end = len(text)
        for other in KNOWN_FIELDS:
            if other == key:
                continue
            oidx = text.find(other, idx + len(key))
            if 0 < oidx < end:
                end = oidx
        raw = text[idx + len(key):end].strip()
        if raw.endswith('|'):
            raw = raw[:-1]
        raw = raw.split('\n')[0].strip()
        fields[key.rstrip('=')] = raw
    return fields


def parse_detail_blocks(log_text: str) -> list[tuple[str, str, dict]]:
    """Return list of (frame_id, frame_type, fields_dict)."""
    lines = log_text.split('\n')
    blocks: list[str] = []
    i = 0
    while i < len(lines):
        if 'DETAIL|F' in lines[i]:
            block = lines[i]
            j = i + 1
            while j < len(lines):
                if re.match(r'\[\d{2}:\d{2}:\d{2}', lines[j]):
                    break
                block += '\n' + lines[j]
                j += 1
            blocks.append(block)
            i = j
        else:
            i += 1

    results: list[tuple[str, str, dict]] = []
    for block in blocks:
        idx = block.find('DETAIL|')
        if idx < 0:
            continue
        detail = block[idx:]
        parts = detail.split('|', 3)
        frame_id = parts[1] if len(parts) > 1 else "?"
        frame_type = parts[2] if len(parts) > 2 else "?"
        rest = parts[3] if len(parts) > 3 else ""
        results.append((frame_id, frame_type, extract_fields(rest)))
    return results


# ---------------------------------------------------------------------------
# Ground truth extraction from scout text
# ---------------------------------------------------------------------------

_RE_SCORE = re.compile(r'([A-Za-z]+)\s+(\d+)-(\d+)\s*\(?([\d.]+)\)?')
_RE_SPEED = re.compile(r'SPEED:\s*([\d.]+)', re.IGNORECASE)
_RE_TARGET = re.compile(r'TARGET\s+(\d{2,3})', re.IGNORECASE)
_RE_TO_WIN = re.compile(r'(?:TO\s+WIN|NEED|REQUIRED)\s+(\d+)\s+(?:OFF|FROM)\s+(\d+)', re.IGNORECASE)
_RE_STRIKER = re.compile(r'[*>]\s*([A-Za-z]+)\s+\d+\s*\(\s*\d+\s*\)')
_RE_EXTRAS = re.compile(r'EXTRA:\s*(.+?)(?:\||$)', re.IGNORECASE)
_RE_BATTER = re.compile(r'([A-Za-z][A-Za-z .]+?)\s+(\d+)\s*\(\s*(\d+)\s*\)')


def extract_ground_truth(scout_text: str) -> dict:
    """Parse broadcast data from Scout's raw text."""
    gt: dict = {}

    m = _RE_SCORE.search(scout_text)
    if m:
        gt['team'] = m.group(1)
        try:
            gt['score'] = int(m.group(2))
            gt['wickets'] = int(m.group(3))
        except ValueError:
            pass
        gt['overs'] = m.group(4)

    m = _RE_SPEED.search(scout_text)
    if m:
        try:
            gt['speed'] = float(m.group(1))
        except ValueError:
            pass

    m = _RE_TARGET.search(scout_text)
    if m:
        gt['target'] = int(m.group(1))

    m = _RE_TO_WIN.search(scout_text)
    if m:
        gt['to_win'] = int(m.group(1))
        gt['balls_remaining'] = int(m.group(2))

    m = _RE_STRIKER.search(scout_text)
    if m:
        gt['striker_indicator'] = m.group(1)

    m = _RE_EXTRAS.search(scout_text)
    if m and m.group(1).strip():
        gt['extras_text'] = m.group(1).strip()

    batters = _RE_BATTER.findall(scout_text)
    if batters:
        gt['batters'] = [(n.strip(), int(r), int(b)) for n, r, b in batters]

    return gt


# ---------------------------------------------------------------------------
# Score/batter/bowler field parsers
# ---------------------------------------------------------------------------

_RE_AFTER_SCORE = re.compile(r'(\d+)-(\d+)\(([\d.]+)\)')


def parse_score_field(val: str) -> tuple[int | None, int | None, str | None]:
    """Parse '55-5(7.3)' → (55, 5, '7.3')."""
    m = _RE_AFTER_SCORE.search(val)
    if m:
        return int(m.group(1)), int(m.group(2)), m.group(3)
    return None, None, None


def parse_batter_field(val: str) -> tuple[str, int | None, int | None]:
    """Parse 'Donovan Ferreira 24(15)' → ('Donovan Ferreira', 24, 15).
    Also handles 'Jadeja None(None)' → ('Jadeja', None, None)."""
    v = val.strip()
    # Standard format: Name runs(balls)
    m = re.match(r'(.+?)\s+(\d+)\((\d+)\)$', v)
    if m:
        return m.group(1).strip(), int(m.group(2)), int(m.group(3))
    # Extractor sometimes returns 'Name None(None)' or 'Name runs(None)'
    m = re.match(r'(.+?)\s+(?:None|\d+)\((?:None|\d+)\)$', v)
    if m:
        return m.group(1).strip(), None, None
    return v, None, None


def parse_bowler_field(val: str) -> tuple[str, int | None, int | None, str | None]:
    """Parse 'Nitish Kumar Reddy 0-7 (1)' → ('Nitish Kumar Reddy', 0, 7, '1')."""
    m = re.match(r'(.+?)\s+(\d+)-(\d+)\s*\(([\d.]+)\)$', val.strip())
    if m:
        return m.group(1).strip(), int(m.group(2)), int(m.group(3)), m.group(4)
    return val.strip(), None, None, None


def parse_this_over(val: str) -> list[str]:
    """Parse \"['?', '.', '1']\" → ['?', '.', '1']."""
    val = val.strip()
    if val in ('—', '', '[]'):
        return []
    try:
        parsed = ast.literal_eval(val)
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
    except (ValueError, SyntaxError):
        pass
    return []


def safe_float(s: str) -> float | None:
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def name_matches(full_name: str, short_name: str) -> bool:
    """Fuzzy name match: 'Ravindra Jadeja' matches 'Jadeja', 'JADEJA', etc."""
    if not full_name or not short_name:
        return False
    fn = full_name.strip().lower()
    sn = short_name.strip().lower()
    if fn == sn:
        return True
    if sn in fn or fn in sn:
        return True
    fn_parts = fn.split()
    sn_parts = sn.split()
    if fn_parts and sn_parts and fn_parts[-1] == sn_parts[-1]:
        return True
    return False


# ---------------------------------------------------------------------------
# Comparison engine: 7 groups of checks
# ---------------------------------------------------------------------------

def check_group1_scorecard(f: dict, gt: dict) -> list[Verdict]:
    """Core scorecard: score, wickets, overs, run rate."""
    verdicts: list[Verdict] = []
    ui_score, ui_wkts, ui_overs = parse_score_field(f.get('AFTER_score', '—'))
    ext_str = f.get('ext_score', '—')
    ext_score, ext_wkts, ext_overs = parse_score_field(ext_str)

    if ext_str in ('—', '', 'None-None(None)') or ext_score is None:
        verdicts.append(Verdict("score", "N/A (no extract)", str(ui_score), "SKIP",
                                "Extractor returned no score this frame"))
        verdicts.append(Verdict("wickets", "N/A", str(ui_wkts), "SKIP"))
        verdicts.append(Verdict("overs", "N/A", str(ui_overs), "SKIP"))
    else:
        if ui_score == ext_score:
            verdicts.append(Verdict("score", str(ext_score), str(ui_score), "CORRECT"))
        elif ui_score is None:
            verdicts.append(Verdict("score", str(ext_score), "—", "MISSING"))
        else:
            verdicts.append(Verdict("score", str(ext_score), str(ui_score), "MISMATCH",
                                    f"UI={ui_score} vs extracted={ext_score}"))

        if ui_wkts == ext_wkts:
            verdicts.append(Verdict("wickets", str(ext_wkts), str(ui_wkts), "CORRECT"))
        elif ui_wkts is None:
            verdicts.append(Verdict("wickets", str(ext_wkts), "—", "MISSING"))
        else:
            verdicts.append(Verdict("wickets", str(ext_wkts), str(ui_wkts), "MISMATCH",
                                    f"UI={ui_wkts} vs extracted={ext_wkts}"))

        ui_ov_f = safe_float(ui_overs) if ui_overs else None
        ext_ov_f = safe_float(ext_overs) if ext_overs else None
        if ui_ov_f is not None and ext_ov_f is not None and abs(ui_ov_f - ext_ov_f) < 0.01:
            verdicts.append(Verdict("overs", str(ext_overs), str(ui_overs), "CORRECT"))
        elif ui_overs is None:
            verdicts.append(Verdict("overs", str(ext_overs), "—", "MISSING"))
        elif ui_ov_f is not None and ext_ov_f is not None:
            verdicts.append(Verdict("overs", str(ext_overs), str(ui_overs), "MISMATCH",
                                    f"UI={ui_overs} vs extracted={ext_overs}"))
        else:
            verdicts.append(Verdict("overs", str(ext_overs), str(ui_overs), "MISMATCH",
                                    f"UI={ui_overs} vs extracted={ext_overs}"))

    # Run rate: verify internal consistency (computed from pipeline's own score/overs)
    rr_str = f.get('AFTER_run_rate', '—')
    rr_ui = safe_float(rr_str)
    if ui_score is not None and ui_overs is not None:
        ov_f = safe_float(ui_overs)
        if ov_f and ov_f > 0:
            # Cricket-correct: convert overs to balls, then to actual overs
            whole = int(ov_f)
            frac = round((ov_f - whole) * 10)
            total_balls = whole * 6 + frac
            if total_balls > 0:
                expected_rr = round((ui_score / total_balls) * 6, 2)
            else:
                expected_rr = 0.0
            if rr_ui is not None and abs(rr_ui - expected_rr) < 0.5:
                verdicts.append(Verdict("run_rate", f"{expected_rr:.2f}", f"{rr_ui:.2f}", "CORRECT"))
            elif rr_ui is not None:
                verdicts.append(Verdict("run_rate", f"{expected_rr:.2f}", f"{rr_ui:.2f}", "MISMATCH",
                                        f"Expected {expected_rr:.2f}, got {rr_ui:.2f}"))
            else:
                verdicts.append(Verdict("run_rate", f"{expected_rr:.2f}", "—", "MISSING"))
    return verdicts


def check_group2_batters(f: dict, gt: dict) -> list[Verdict]:
    """Batter names, stats, and striker attribution."""
    verdicts: list[Verdict] = []
    ext_bat = f.get('ext_bat', '—')
    if not ext_bat or ext_bat in ('—', ''):
        verdicts.append(Verdict("bat1", "N/A", f.get('AFTER_bat1', '—'), "SKIP", "No batter data extracted"))
        verdicts.append(Verdict("bat2", "N/A", f.get('AFTER_bat2', '—'), "SKIP"))
    else:
        ext_parts = [p.strip() for p in ext_bat.split('|')]
        ui_bat1 = f.get('AFTER_bat1', '—')
        ui_bat2 = f.get('AFTER_bat2', '—')

        # Check each extracted batter appears in ui_bat1 or ui_bat2
        for i, ep in enumerate(ext_parts[:2]):
            ext_name, ext_runs, ext_balls = parse_batter_field(ep)
            ui_name1, ui_r1, ui_b1 = parse_batter_field(ui_bat1)
            ui_name2, ui_r2, ui_b2 = parse_batter_field(ui_bat2)

            field_label = f"bat{i+1}"
            matched = False

            if name_matches(ui_name1, ext_name):
                matched = True
                if ext_runs is not None and ui_r1 is not None:
                    if ui_r1 == ext_runs and ui_b1 == ext_balls:
                        verdicts.append(Verdict(f"{field_label}_stats", f"{ext_name} {ext_runs}({ext_balls})",
                                                f"{ui_name1} {ui_r1}({ui_b1})", "CORRECT"))
                    else:
                        verdicts.append(Verdict(f"{field_label}_stats", f"{ext_name} {ext_runs}({ext_balls})",
                                                f"{ui_name1} {ui_r1}({ui_b1})", "MISMATCH",
                                                f"Stats differ: ext={ext_runs}({ext_balls}) ui={ui_r1}({ui_b1})"))
                else:
                    verdicts.append(Verdict(f"{field_label}_name", ext_name, ui_name1, "CORRECT"))
            elif name_matches(ui_name2, ext_name):
                matched = True
                if ext_runs is not None and ui_r2 is not None:
                    if ui_r2 == ext_runs and ui_b2 == ext_balls:
                        verdicts.append(Verdict(f"{field_label}_stats", f"{ext_name} {ext_runs}({ext_balls})",
                                                f"{ui_name2} {ui_r2}({ui_b2})", "CORRECT"))
                    else:
                        verdicts.append(Verdict(f"{field_label}_stats", f"{ext_name} {ext_runs}({ext_balls})",
                                                f"{ui_name2} {ui_r2}({ui_b2})", "MISMATCH",
                                                f"Stats differ: ext={ext_runs}({ext_balls}) ui={ui_r2}({ui_b2})"))
                else:
                    verdicts.append(Verdict(f"{field_label}_name", ext_name, ui_name2, "CORRECT"))

            if not matched:
                verdicts.append(Verdict(f"{field_label}_name", ext_name,
                                        f"{ui_name1} / {ui_name2}", "MISMATCH",
                                        f"Extracted batter '{ext_name}' not found in UI batters"))

    # Striker from broadcast indicator
    striker_ui = f.get('AFTER_striker', '—')
    if gt.get('striker_indicator'):
        bcast_striker = gt['striker_indicator']
        if name_matches(striker_ui, bcast_striker):
            verdicts.append(Verdict("striker_broadcast", bcast_striker, striker_ui, "CORRECT"))
        else:
            verdicts.append(Verdict("striker_broadcast", bcast_striker, striker_ui, "MISMATCH",
                                    f"Broadcast shows *{bcast_striker}, UI says {striker_ui}"))
    return verdicts


def check_group3_bowler(f: dict, gt: dict) -> list[Verdict]:
    """Bowler name and figures."""
    verdicts: list[Verdict] = []
    ext_bowl = f.get('ext_bowl', '—')
    if not ext_bowl or ext_bowl in ('—', ''):
        verdicts.append(Verdict("bowler", "N/A", f.get('AFTER_bowl', '—'), "SKIP",
                                "No bowler data extracted"))
        return verdicts

    ext_name, ext_w, ext_r, ext_o = parse_bowler_field(ext_bowl)
    ui_bowl = f.get('AFTER_bowl', '—')
    ui_name, ui_w, ui_r, ui_o = parse_bowler_field(ui_bowl)

    if name_matches(ui_name, ext_name):
        verdicts.append(Verdict("bowler_name", ext_name, ui_name, "CORRECT"))
    else:
        verdicts.append(Verdict("bowler_name", ext_name, ui_name, "MISMATCH",
                                f"ext={ext_name} ui={ui_name}"))

    if ext_w is not None and ui_w is not None:
        if ext_w == ui_w and ext_r == ui_r:
            verdicts.append(Verdict("bowler_figures", f"{ext_w}-{ext_r}", f"{ui_w}-{ui_r}", "CORRECT"))
        else:
            verdicts.append(Verdict("bowler_figures", f"{ext_w}-{ext_r}", f"{ui_w}-{ui_r}", "MISMATCH"))

    if ext_o is not None and ui_o is not None:
        if ext_o == ui_o:
            verdicts.append(Verdict("bowler_overs", ext_o, ui_o, "CORRECT"))
        else:
            verdicts.append(Verdict("bowler_overs", ext_o, ui_o, "MISMATCH",
                                    f"ext overs={ext_o} ui overs={ui_o}"))
    return verdicts


def check_group4_this_over(f: dict, prev_f: dict | None) -> list[Verdict]:
    """This over ball tokens: count, content, wide/nb notation."""
    verdicts: list[Verdict] = []
    raw = f.get('AFTER_this_over', '[]')
    tokens = parse_this_over(raw)
    src_raw = f.get('AFTER_this_over_src', '')

    _, _, overs_str = parse_score_field(f.get('AFTER_score', '—'))
    if overs_str:
        ov_f = safe_float(overs_str)
        if ov_f is not None:
            frac = round((ov_f % 1) * 10)
            if frac == 0 and not tokens:
                verdicts.append(Verdict("this_over_count", "0 (over boundary)", "0", "CORRECT"))
            elif frac > 0 and len(tokens) < frac:
                verdicts.append(Verdict("this_over_count", f">={frac} (from overs .{frac})",
                                        str(len(tokens)), "MISMATCH",
                                        f"Overs={overs_str} implies at least {frac} balls, got {len(tokens)}"))
            else:
                verdicts.append(Verdict("this_over_count", f">={frac}", str(len(tokens)), "CORRECT"))

    # Check for unresolved '?' tokens
    q_count = tokens.count('?')
    if q_count > 0:
        verdicts.append(Verdict("this_over_unresolved", "0 question marks",
                                f"{q_count} '?' tokens", "MISMATCH",
                                f"Positions {[i for i, t in enumerate(tokens) if t == '?']} are unresolved"))

    # Check that extras use proper notation (wd/nb), not numeric
    ball_event = f.get('ball_event', '—')
    if ball_event == 'EXTRA':
        if tokens:
            last_token = tokens[-1]
            if last_token.isdigit():
                verdicts.append(Verdict("this_over_extra_notation", "wd or nb",
                                        last_token, "MISMATCH",
                                        f"EXTRA event recorded as '{last_token}' instead of 'wd'/'nb'"))
            elif last_token.lower() in ('wd', 'nb', 'w'):
                verdicts.append(Verdict("this_over_extra_notation", "wd/nb", last_token, "CORRECT"))

    return verdicts


def check_group5_context(f: dict, gt: dict, target_ever_seen: bool) -> list[Verdict]:
    """Target, innings, FOW count, partnership, speed."""
    verdicts: list[Verdict] = []

    # Target
    target_ui = f.get('AFTER_target', '—')
    has_target_gt = 'target' in gt or 'to_win' in gt
    if has_target_gt:
        if target_ui in ('—', '', 'None'):
            gt_val = gt.get('target') or f"TO WIN {gt.get('to_win')}"
            verdicts.append(Verdict("target", str(gt_val), "—", "MISSING",
                                    "Broadcast shows target/chase info, UI shows nothing"))
        else:
            t_ui = safe_float(target_ui)
            t_gt = gt.get('target')
            if t_gt and t_ui and abs(t_ui - t_gt) < 1:
                verdicts.append(Verdict("target", str(t_gt), str(target_ui), "CORRECT"))
            elif t_gt:
                verdicts.append(Verdict("target", str(t_gt), str(target_ui), "MISMATCH"))
            else:
                verdicts.append(Verdict("target", "chase info present", str(target_ui), "CORRECT",
                                        "TO WIN format — exact target depends on computation"))
    else:
        if target_ui not in ('—', '', 'None'):
            if target_ever_seen:
                verdicts.append(Verdict("target", "cached", target_ui, "SKIP",
                                        "Cached from earlier broadcast frame"))
            else:
                verdicts.append(Verdict("target", "none in broadcast", target_ui, "FABRICATED",
                                        "UI shows target but never seen in any broadcast frame"))
        else:
            verdicts.append(Verdict("target", "—", "—", "SKIP", "No target data either side"))

    # FOW count vs wickets
    fow_raw = f.get('AFTER_fow_count', '0')
    _, ui_wkts, _ = parse_score_field(f.get('AFTER_score', '—'))
    try:
        fow = int(fow_raw)
    except (ValueError, TypeError):
        fow = 0
    if ui_wkts is not None:
        if fow == ui_wkts:
            verdicts.append(Verdict("fow_count", str(ui_wkts), str(fow), "CORRECT"))
        else:
            verdicts.append(Verdict("fow_count", str(ui_wkts), str(fow), "MISMATCH",
                                    f"Wickets={ui_wkts} but fow_count={fow}"))

    # Speed
    speed_ui = f.get('speed_kph', '—')
    if gt.get('speed'):
        gt_speed = gt['speed']
        if speed_ui in ('—', '', 'None'):
            verdicts.append(Verdict("speed_kph", str(gt_speed), "—", "MISSING",
                                    f"Scout shows SPEED:{gt_speed} but pipeline didn't extract"))
        else:
            s_ui = safe_float(speed_ui)
            if s_ui is not None and abs(s_ui - gt_speed) < 0.5:
                verdicts.append(Verdict("speed_kph", str(gt_speed), str(speed_ui), "CORRECT"))
            else:
                verdicts.append(Verdict("speed_kph", str(gt_speed), str(speed_ui), "MISMATCH"))
    else:
        if speed_ui not in ('—', '', 'None'):
            verdicts.append(Verdict("speed_kph", "not in broadcast", str(speed_ui), "SKIP",
                                    "Speed in UI but not visible this frame (may be cached)"))
        else:
            verdicts.append(Verdict("speed_kph", "—", "—", "SKIP"))

    # Innings
    innings_ui = f.get('AFTER_innings', '1')
    if gt.get('to_win') or gt.get('target'):
        if innings_ui == '1':
            verdicts.append(Verdict("innings", "2 (chase data present)", innings_ui, "MISMATCH",
                                    "Broadcast shows chase info implying innings 2, pipeline says 1"))
        else:
            verdicts.append(Verdict("innings", "2", innings_ui, "CORRECT"))

    # Partnership
    part_raw = f.get('AFTER_partnership', '—')
    if part_raw not in ('—', '', 'None'):
        m = re.match(r'(\d+)\((\d+)\)', part_raw)
        if m:
            p_runs, p_balls = int(m.group(1)), int(m.group(2))
            if p_runs == 0 and p_balls == 0:
                verdicts.append(Verdict("partnership", "should track", f"{p_runs}({p_balls})",
                                        "SKIP", "Partnership at 0(0) — may be reset"))
            else:
                verdicts.append(Verdict("partnership", "tracked", f"{p_runs}({p_balls})", "CORRECT"))

    return verdicts


_VALID_LENGTHS = {'bouncer', 'short', 'back_of_length', 'good_length',
                  'full', 'overpitched', 'yorker', 'full_toss', 'unknown'}
_VALID_LINES = {'wide_outside_off', 'outside_off', 'off_stump', 'on_stumps',
                'leg_stump', 'on_pads', 'down_leg', 'unknown',
                'middle', 'leg_side'}
_VALID_ANGLES = {'over', 'round', 'unknown'}
_VALID_SHOTS = {'defended', 'along_ground', 'in_the_air', 'missed',
                'left_alone', 'unknown'}
_VALID_DIRECTIONS = {'offside', 'legside', 'straight', 'behind_wicket',
                     'no_shot', 'unknown'}
_VALID_ELEVATIONS = {'in_the_air', 'along_ground', 'unknown'}
_VALID_BOUNCES = {'bouncer', 'sharp_bounce', 'good_bounce', 'normal',
                  'stayed_low', 'skidded_through', 'unknown',
                  'low_bounce', 'normal_bounce', 'extra_bounce'}
_VALID_BALL_EVENTS = {'DOT', '1_RUNS', '2_RUNS', '3_RUNS', 'FOUR', 'SIX',
                      'WICKET', 'EXTRA', 'MULTI_BALL'}
_VALID_EXTRAS = {'wide', 'no_ball', 'no-ball', 'bye', 'leg_bye', 'leg-bye', 'penalty'}


def check_group6_delivery(f: dict) -> list[Verdict]:
    """Delivery classification: length, line, angle, shot type, speed."""
    verdicts: list[Verdict] = []
    dets_raw = f.get('delivery_dets', '0')
    try:
        dets = int(dets_raw)
    except (ValueError, TypeError):
        dets = 0

    ball_event = f.get('ball_event', '—')
    length = f.get('delivery_length', '—')
    line = f.get('delivery_line', '—')
    angle = f.get('delivery_angle', '—')
    shot = f.get('delivery_shot', '—')
    direction = f.get('delivery_direction', '—')
    elevation = f.get('delivery_elevation', '—')
    speed = f.get('speed_kph', '—')

    _absent = ('—', '', 'None')

    if ball_event in _absent:
        verdicts.append(Verdict("delivery", "N/A", "N/A", "SKIP", "No ball event"))
        return verdicts

    # --- Classification presence ---
    if dets > 0:
        if length in _absent and line in _absent:
            verdicts.append(Verdict("delivery_classification", "present (dets>0)",
                                    "missing", "MISMATCH",
                                    f"{dets} detections but no length/line"))
        else:
            verdicts.append(Verdict("delivery_classification", "present",
                                    f"{length}, {line}", "CORRECT"))
    else:
        if length not in _absent:
            verdicts.append(Verdict("delivery_classification", "none (0 dets)",
                                    f"{length}, {line}", "FABRICATED",
                                    "Classification without detections"))
        else:
            verdicts.append(Verdict("delivery_no_data", "0 dets → no classification",
                                    "—", "CORRECT"))

    # --- Length validity ---
    if length not in _absent:
        if length in _VALID_LENGTHS:
            verdicts.append(Verdict("delivery_length", "valid value", length, "CORRECT"))
        else:
            verdicts.append(Verdict("delivery_length", f"one of {_VALID_LENGTHS}", length,
                                    "MISMATCH", f"Unrecognised length '{length}'"))

    # --- Line validity ---
    if line not in _absent:
        if line in _VALID_LINES:
            verdicts.append(Verdict("delivery_line", "valid value", line, "CORRECT"))
        else:
            verdicts.append(Verdict("delivery_line", f"one of {_VALID_LINES}", line,
                                    "MISMATCH", f"Unrecognised line '{line}'"))

    # --- Bowling angle ---
    if angle not in _absent:
        if angle in _VALID_ANGLES:
            verdicts.append(Verdict("delivery_angle", "valid value", angle, "CORRECT"))
        else:
            verdicts.append(Verdict("delivery_angle", f"one of {_VALID_ANGLES}", angle,
                                    "MISMATCH", f"Unrecognised angle '{angle}'"))
    elif dets > 0:
        verdicts.append(Verdict("delivery_angle", "present (dets>0)", "—", "MISSING",
                                f"{dets} detections but no bowling angle"))

    # --- Shot type validity + semantic check ---
    if shot not in _absent:
        if shot not in _VALID_SHOTS:
            verdicts.append(Verdict("delivery_shot", f"one of {_VALID_SHOTS}", shot,
                                    "MISMATCH", f"Unrecognised shot type '{shot}'"))
        else:
            verdicts.append(Verdict("delivery_shot_valid", "valid value", shot, "CORRECT"))

        # Semantic: 4 runs should NOT be along_ground (ambiguous in T20)
        if ball_event == 'FOUR' and shot == 'along_ground':
            verdicts.append(Verdict("delivery_shot_four", "unknown (4 runs ambiguous)",
                                    "along_ground", "MISMATCH",
                                    "FOUR classified as along_ground — could be aerial"))
        # 6 runs must be aerial
        if ball_event == 'SIX' and shot != 'aerial':
            verdicts.append(Verdict("delivery_shot_six", "aerial", shot, "MISMATCH",
                                    f"SIX classified as '{shot}' instead of 'aerial'"))
    elif ball_event not in ('MULTI_BALL', 'EXTRA'):
        verdicts.append(Verdict("delivery_shot", "present on ball event", "—", "MISSING"))

    # --- Shot direction validity ---
    if direction not in _absent:
        if direction in _VALID_DIRECTIONS:
            verdicts.append(Verdict("delivery_direction", "valid value", direction, "CORRECT"))
        else:
            verdicts.append(Verdict("delivery_direction", f"one of {_VALID_DIRECTIONS}",
                                    direction, "MISMATCH",
                                    f"Unrecognised direction '{direction}'"))
    elif dets >= 2 and ball_event not in ('MULTI_BALL', 'EXTRA'):
        verdicts.append(Verdict("delivery_direction", "present (dets>=2)", "—", "MISSING",
                                f"{dets} detections but no shot direction"))

    # --- Shot elevation validity ---
    if elevation not in _absent:
        if elevation in _VALID_ELEVATIONS:
            verdicts.append(Verdict("delivery_elevation", "valid value", elevation, "CORRECT"))
        else:
            verdicts.append(Verdict("delivery_elevation", f"one of {_VALID_ELEVATIONS}",
                                    elevation, "MISMATCH",
                                    f"Unrecognised elevation '{elevation}'"))
        if ball_event == 'SIX' and elevation == 'along_ground':
            verdicts.append(Verdict("delivery_elevation_six", "in_the_air", elevation,
                                    "MISMATCH", "SIX classified as along_ground"))
    elif dets >= 2 and ball_event not in ('MULTI_BALL', 'EXTRA'):
        verdicts.append(Verdict("delivery_elevation", "present (dets>=2)", "—", "MISSING",
                                f"{dets} detections but no shot elevation"))

    # --- Bounce validity ---
    bounce = f.get('delivery_bounce', '—')
    if bounce not in _absent:
        if bounce in _VALID_BOUNCES:
            verdicts.append(Verdict("delivery_bounce", "valid value", bounce, "CORRECT"))
        else:
            verdicts.append(Verdict("delivery_bounce", f"one of {_VALID_BOUNCES}",
                                    bounce, "MISMATCH",
                                    f"Unrecognised bounce '{bounce}'"))

    # --- Detection rate quality ---
    det_rate_raw = f.get('delivery_det_rate', '—')
    if det_rate_raw not in _absent:
        det_rate = safe_float(det_rate_raw)
        if det_rate is not None:
            if det_rate < 0.10 and dets > 0:
                verdicts.append(Verdict("delivery_det_rate", ">0.10", str(det_rate),
                                        "MISMATCH", "Very low detection rate — classification unreliable"))
            elif det_rate >= 0.10:
                verdicts.append(Verdict("delivery_det_rate", "reasonable", str(det_rate), "CORRECT"))

    # --- Direction confidence ---
    dir_conf_raw = f.get('delivery_dir_conf', '0')
    dir_conf = safe_float(dir_conf_raw)
    if direction not in _absent and direction != 'unknown' and dir_conf is not None:
        if dir_conf < 0.33:
            verdicts.append(Verdict("delivery_dir_confidence", ">0.33",
                                    str(dir_conf), "MISMATCH",
                                    "Low confidence direction — may be unreliable"))

    # --- Speed on ball event ---
    if speed not in _absent:
        spd = safe_float(speed)
        if spd is not None:
            if 40 <= spd <= 165:
                verdicts.append(Verdict("delivery_speed", "40-165 kph range", str(spd), "CORRECT"))
            else:
                verdicts.append(Verdict("delivery_speed", "40-165 kph range", str(spd), "MISMATCH",
                                        f"Speed {spd} kph is outside realistic range"))
    else:
        verdicts.append(Verdict("delivery_speed", "present on ball event", "—", "MISSING",
                                "No speed for this delivery"))

    return verdicts


# ---------------------------------------------------------------------------
# Group 6B: DRS state machine
# ---------------------------------------------------------------------------

_VALID_DRS_STATES = {'NONE', 'DETECTING', 'IN_PROGRESS', 'RESOLVED'}
_DRS_TRANSITIONS = {
    'NONE': {'NONE', 'DETECTING'},
    'DETECTING': {'DETECTING', 'IN_PROGRESS', 'NONE'},
    'IN_PROGRESS': {'IN_PROGRESS', 'RESOLVED'},
    'RESOLVED': {'RESOLVED', 'NONE'},
}


def check_drs(f: dict, prev_drs: str) -> list[Verdict]:
    """DRS state machine: valid state, valid transitions."""
    verdicts: list[Verdict] = []
    drs = f.get('drs_state', '')
    if not drs or drs in ('—', '', 'None'):
        return verdicts

    drs_upper = drs.strip().upper()
    if drs_upper not in _VALID_DRS_STATES:
        verdicts.append(Verdict("drs_state", f"one of {_VALID_DRS_STATES}", drs,
                                "MISMATCH", f"Invalid DRS state '{drs}'"))
        return verdicts

    verdicts.append(Verdict("drs_state_valid", "valid state", drs_upper, "CORRECT"))

    if prev_drs and prev_drs in _VALID_DRS_STATES:
        allowed = _DRS_TRANSITIONS.get(prev_drs, set())
        if drs_upper in allowed:
            verdicts.append(Verdict("drs_transition", f"from {prev_drs}", drs_upper, "CORRECT"))
        else:
            verdicts.append(Verdict("drs_transition", f"from {prev_drs} → {allowed}",
                                    drs_upper, "MISMATCH",
                                    f"Invalid DRS transition {prev_drs} → {drs_upper}"))

    return verdicts


def check_group6c_ball_event(f: dict) -> list[Verdict]:
    """Ball event sub-fields: runs, over, extra type, free hit."""
    verdicts: list[Verdict] = []
    _absent = ('—', '', 'None')
    ball_event = f.get('ball_event', '—')

    if ball_event in _absent:
        return verdicts

    # --- Runs consistency ---
    runs_raw = f.get('ball_event_runs', '—')
    if runs_raw not in _absent:
        runs = safe_float(runs_raw)
        if runs is not None:
            expected_runs = {
                'DOT': 0, 'SIX': 6, 'FOUR': 4,
                '1_RUNS': 1, '2_RUNS': 2, '3_RUNS': 3,
            }
            exp = expected_runs.get(ball_event)
            if exp is not None and int(runs) != exp:
                verdicts.append(Verdict("ball_event_runs", str(exp), str(int(runs)),
                                        "MISMATCH",
                                        f"{ball_event} should have {exp} runs, got {int(runs)}"))
            elif exp is not None:
                verdicts.append(Verdict("ball_event_runs", str(exp), str(int(runs)), "CORRECT"))

    # --- Over field present ---
    over_raw = f.get('ball_event_over', '—')
    if over_raw in _absent and ball_event not in ('MULTI_BALL',):
        verdicts.append(Verdict("ball_event_over", "present on ball event", "—", "MISSING",
                                "Ball event has no over number"))
    elif over_raw not in _absent:
        verdicts.append(Verdict("ball_event_over", "present", over_raw, "CORRECT"))

    # --- Extra type on EXTRA event ---
    extra_raw = f.get('ball_event_extra', '—')
    if ball_event == 'EXTRA':
        if extra_raw in _absent:
            verdicts.append(Verdict("ball_event_extra", "present on EXTRA", "—", "MISSING",
                                    "EXTRA event without extra_type"))
        elif extra_raw.lower() not in _VALID_EXTRAS:
            verdicts.append(Verdict("ball_event_extra", f"one of {_VALID_EXTRAS}",
                                    extra_raw, "MISMATCH",
                                    f"Unrecognised extra type '{extra_raw}'"))
        else:
            verdicts.append(Verdict("ball_event_extra", "valid", extra_raw, "CORRECT"))

    # --- Broadcast extra signal cross-check ---
    bcast_extra = f.get('broadcast_extra', '—')
    if bcast_extra not in _absent:
        if ball_event == 'EXTRA':
            verdicts.append(Verdict("broadcast_extra", "consistent with EXTRA event",
                                    bcast_extra, "CORRECT"))
        elif ball_event not in _absent:
            verdicts.append(Verdict("broadcast_extra", "EXTRA event",
                                    f"{bcast_extra} but event={ball_event}", "MISMATCH",
                                    f"Broadcast says {bcast_extra} but ball event is {ball_event}"))
    elif ball_event == 'EXTRA':
        verdicts.append(Verdict("broadcast_extra", "present on EXTRA",
                                "—", "MISSING",
                                "EXTRA event fired without broadcast signal"))

    # --- Free hit flag ---
    free_hit = f.get('ball_event_free_hit', '—')
    if free_hit == 'yes':
        verdicts.append(Verdict("ball_event_free_hit", "flagged", "yes", "CORRECT"))

    return verdicts


def check_group6d_striker_attribution(f: dict) -> list[Verdict]:
    """Striker attribution: striker_this_ball vs AFTER_striker consistency."""
    verdicts: list[Verdict] = []
    _absent = ('—', '', 'None')
    ball_event = f.get('ball_event', '—')
    if ball_event in _absent:
        return verdicts

    striker_tb = f.get('striker_this_ball', '—')
    striker_after = f.get('AFTER_striker', '—')

    if striker_tb in _absent:
        verdicts.append(Verdict("striker_this_ball", "present on ball event", "—", "MISSING",
                                "No striker snapshot for this delivery"))
    elif striker_after not in _absent:
        stb_last = striker_tb.split()[-1].lower() if striker_tb.split() else ''
        sa_last = striker_after.split()[-1].lower() if striker_after.split() else ''
        if stb_last and sa_last and stb_last == sa_last:
            verdicts.append(Verdict("striker_this_ball", striker_after, striker_tb, "CORRECT"))
        elif stb_last and sa_last:
            runs_raw = f.get('ball_event_runs', '0')
            try:
                runs = int(runs_raw)
            except (ValueError, TypeError):
                runs = 0
            if runs in (1, 3):
                verdicts.append(Verdict("striker_this_ball", f"{striker_after} (rotated)",
                                        striker_tb, "CORRECT",
                                        f"Striker rotated after {runs} run(s)"))
            else:
                verdicts.append(Verdict("striker_this_ball", striker_after, striker_tb,
                                        "MISMATCH",
                                        f"Striker mismatch: faced={striker_tb}, shown={striker_after}"))

    return verdicts


def check_group6e_context(f: dict) -> list[Verdict]:
    """Session-level context: venue, batting_team, match_info, completed_over."""
    verdicts: list[Verdict] = []
    _absent = ('—', '', 'None')

    venue = f.get('venue', '—')
    batting_team = f.get('batting_team', '—')
    match_info = f.get('match_info', '—')

    if venue not in _absent:
        verdicts.append(Verdict("venue", "present", venue, "CORRECT"))

    if batting_team not in _absent:
        verdicts.append(Verdict("batting_team", "present", batting_team, "CORRECT"))
    else:
        ball_event = f.get('ball_event', '—')
        if ball_event not in _absent:
            verdicts.append(Verdict("batting_team", "present on ball event", "—", "MISSING",
                                    "Ball event fired but batting team not set"))

    if match_info not in _absent:
        verdicts.append(Verdict("match_info", "present", match_info, "CORRECT"))

    completed_over = f.get('completed_over', '—')
    completed_over_runs = f.get('completed_over_runs', '—')
    if completed_over not in _absent:
        verdicts.append(Verdict("completed_over", "present", completed_over, "CORRECT"))
        if completed_over_runs not in _absent:
            verdicts.append(Verdict("completed_over_runs", "present",
                                    str(completed_over_runs), "CORRECT"))

    return verdicts


def check_group7_commentary(f: dict) -> list[Verdict]:
    """Commentary accuracy: striker name, fielding positions, delivery match."""
    verdicts: list[Verdict] = []
    striker = f.get('striker_this_ball', f.get('AFTER_striker', '—'))
    comm_wire = f.get('comm_wire', '—')
    comm_story = f.get('comm_storyteller', '—')
    comm_analyst = f.get('comm_analyst', '—')

    for label, text in [("wire", comm_wire), ("storyteller", comm_story)]:
        if not text or text == '—':
            continue

        text_lower = text.lower()
        ball_event = f.get('ball_event', '—')

        # Striker name check — compare against striker_this_ball (who
        # actually faced the delivery), not AFTER_striker (post-rotation).
        if striker and striker != '—':
            after_striker = f.get('AFTER_striker', '—')
            non = f.get('AFTER_non', '—')
            stb_non = after_striker if striker != after_striker else non
            parts_striker = striker.split()
            parts_stb_non = stb_non.split() if stb_non != '—' else []
            last_striker = parts_striker[-1].lower() if parts_striker else ''
            last_non = parts_stb_non[-1].lower() if parts_stb_non else ''

            mentions_striker = last_striker and last_striker in text_lower
            mentions_non = last_non and last_non in text_lower

            if ball_event in ('DOT', '1_RUNS', '2_RUNS', '3_RUNS', 'FOUR', 'SIX'):
                if mentions_striker:
                    verdicts.append(Verdict(f"comm_{label}_striker", striker,
                                            "mentioned", "CORRECT"))
                elif mentions_non and not mentions_striker:
                    verdicts.append(Verdict(f"comm_{label}_striker", striker,
                                            f"names {stb_non} instead", "MISMATCH",
                                            f"Commentary attributes to non-striker"))

        # Bowler name check
        comm_bowler = f.get('comm_bowler', '—')
        if comm_bowler and comm_bowler != '—':
            bowl_parts = comm_bowler.split()
            bowl_last = bowl_parts[-1].lower() if bowl_parts else ''
            if bowl_last and len(bowl_last) >= 3:
                mentions_bowler = bowl_last in text_lower
                if ball_event and ball_event != '—':
                    after_bowl = f.get('AFTER_bowl', '—')
                    after_bowl_name = after_bowl.split()[0] if after_bowl != '—' else ''
                    wrong_names = [w.lower() for w in
                                   (after_bowl_name,) if w and w.lower() != bowl_last]
                    names_wrong = any(w in text_lower for w in wrong_names if len(w) >= 4)
                    if not mentions_bowler and names_wrong:
                        verdicts.append(Verdict(f"comm_{label}_bowler",
                                                comm_bowler, "names wrong bowler",
                                                "MISMATCH",
                                                "Commentary attributes to wrong bowler"))

        # Fielding position fabrication
        matches = FIELDING_RE.findall(text)
        if matches:
            verdicts.append(Verdict(f"comm_{label}_fielding", "no positions (banned)",
                                    ', '.join(matches), "FABRICATED",
                                    f"Fielding positions fabricated: {matches}"))

        # Delivery description consistency
        length = f.get('delivery_length', '—')
        line = f.get('delivery_line', '—')
        angle = f.get('delivery_angle', '—')
        _absent = ('—', '', 'None', 'unknown')

        if length not in _absent:
            length_synonyms = {
                'bouncer': ['bouncer', 'short', 'bounce'],
                'short': ['short'],
                'good_length': ['good length', 'good-length'],
                'full': ['full', 'fuller'],
                'yorker': ['yorker'],
                'full_toss': ['full toss', 'full-toss'],
            }
            syns = length_synonyms.get(length, [length.replace('_', ' ')])
            if not any(s in text_lower for s in syns):
                # Wire has delivery data but didn't mention it — not necessarily wrong
                # but flag when no length descriptor at all
                has_any_length_word = any(
                    w in text_lower for w in
                    ['short', 'full', 'good length', 'bouncer', 'yorker', 'length'])
                if not has_any_length_word:
                    verdicts.append(Verdict(f"comm_{label}_delivery_length",
                                            f"mention {length}", "no length description",
                                            "MISSING", "Delivery data available but commentary omits length"))

        if line not in _absent:
            # Check for contradictory line descriptions
            off_terms = ['outside off', 'off stump', 'off-stump', 'wide outside off']
            leg_terms = ['down leg', 'leg stump', 'leg-stump', 'leg side']
            is_off_line = line in ('outside_off', 'off_stump', 'wide_outside_off')
            is_leg_line = line in ('leg_stump', 'down_leg')

            mentions_off = any(t in text_lower for t in off_terms)
            mentions_leg = any(t in text_lower for t in leg_terms)

            if is_off_line and mentions_leg and not mentions_off:
                verdicts.append(Verdict(f"comm_{label}_delivery_line",
                                        f"{line} (off side)", "describes leg side",
                                        "MISMATCH", "Commentary contradicts delivery line data"))
            elif is_leg_line and mentions_off and not mentions_leg:
                verdicts.append(Verdict(f"comm_{label}_delivery_line",
                                        f"{line} (leg side)", "describes off side",
                                        "MISMATCH", "Commentary contradicts delivery line data"))

        # Speed mention when available
        speed = f.get('speed_kph', '—')
        if speed not in ('—', '', 'None'):
            speed_in_comm = bool(re.search(r'\d{2,3}\.?\d?\s*(?:kph|km/?h|clicks)', text_lower))
            if speed_in_comm:
                verdicts.append(Verdict(f"comm_{label}_speed", "speed mentioned", "yes", "CORRECT"))

        # Direction consistency: commentary vs delivery_direction
        direction = f.get('delivery_direction', '—')
        if direction not in ('—', '', 'None', 'unknown'):
            dir_terms = {
                'offside': ['off side', 'offside', 'off-side', 'through the off'],
                'legside': ['leg side', 'legside', 'leg-side', 'into the leg',
                            'through the leg'],
                'straight': ['straight', 'down the ground', 'back past'],
            }
            expected_terms = dir_terms.get(direction, [])
            if expected_terms and any(t in text_lower for t in expected_terms):
                verdicts.append(Verdict(f"comm_{label}_direction",
                                        direction, "mentioned", "CORRECT"))

        # Elevation consistency: commentary vs delivery_elevation
        elevation = f.get('delivery_elevation', '—')
        if elevation not in ('—', '', 'None', 'unknown'):
            if elevation == 'in_the_air':
                air_terms = ['in the air', 'lofted', 'aerial', 'over the',
                             'skied', 'lifted']
                if any(t in text_lower for t in air_terms):
                    verdicts.append(Verdict(f"comm_{label}_elevation",
                                            "in the air", "mentioned", "CORRECT"))
                elif 'along the ground' in text_lower or 'along ground' in text_lower:
                    verdicts.append(Verdict(f"comm_{label}_elevation",
                                            "in the air", "says along ground",
                                            "MISMATCH",
                                            "Elevation data says aerial but commentary says along ground"))
            elif elevation == 'along_ground':
                if 'in the air' in text_lower or 'lofted' in text_lower:
                    verdicts.append(Verdict(f"comm_{label}_elevation",
                                            "along ground", "says aerial",
                                            "MISMATCH",
                                            "Elevation data says along ground but commentary says aerial"))

        # Striker_this_ball vs commentary attribution
        striker_tb = f.get('striker_this_ball', '—')
        if striker_tb not in ('—', '', 'None'):
            stb_parts = striker_tb.split()
            stb_last = stb_parts[-1].lower() if stb_parts else ''
            if stb_last and stb_last not in text_lower:
                sa_last = (striker.split()[-1].lower()
                           if striker and striker != '—' else '')
                if sa_last and sa_last in text_lower and sa_last != stb_last:
                    verdicts.append(Verdict(f"comm_{label}_striker_attribution",
                                            f"{striker_tb} (faced)", f"names {striker}",
                                            "MISMATCH",
                                            "Commentary names AFTER_striker but striker_this_ball was different"))

        # Venue fabrication: commentary mentions a venue not in data
        venue = f.get('venue', '—')
        if venue in ('—', '', 'None'):
            venue_words = ['stadium', 'wankhede', 'eden', 'chinnaswamy',
                           'chepauk', 'kotla', 'rajiv gandhi', 'narendra modi',
                           'brabourne', 'dharamsala', 'mohali', 'uppal',
                           'sawai mansingh', 'green park']
            if any(v in text_lower for v in venue_words):
                verdicts.append(Verdict(f"comm_{label}_venue", "no venue data",
                                        "mentions venue", "FABRICATED",
                                        "Commentary names a venue with no venue data available"))

    # Analyst over summary check
    if comm_analyst and comm_analyst != '—':
        m = re.search(r'conceding\s+(\d+)\s+run', comm_analyst, re.IGNORECASE)
        if m:
            claimed_runs = int(m.group(1))
            this_over = parse_this_over(f.get('AFTER_this_over', '[]'))
            # On over-end, AFTER_this_over is [] — use BEFORE
            if not this_over:
                this_over = parse_this_over(f.get('BEFORE_this_over', '[]'))
            actual_runs = sum(int(t) for t in this_over if t.isdigit())
            if claimed_runs == actual_runs:
                verdicts.append(Verdict("comm_analyst_runs", str(actual_runs),
                                        str(claimed_runs), "CORRECT"))
            else:
                verdicts.append(Verdict("comm_analyst_runs", str(actual_runs),
                                        str(claimed_runs), "MISMATCH",
                                        f"Analyst says {claimed_runs} runs, over data shows {actual_runs}"))

    return verdicts


# ---------------------------------------------------------------------------
# Delayed detection pass
# ---------------------------------------------------------------------------

_DELAY_SKIP_FIELDS = {'run_rate', 'partnership'}


def detect_delays(audits: list[FrameAudit]) -> None:
    """Retroactively mark MISSING/MISMATCH verdicts as DELAYED if a later
    frame corrects the value.  Skips continuously-changing computed fields."""
    field_tracker: dict[str, list[tuple[int, Verdict]]] = {}
    for i, audit in enumerate(audits):
        for v in audit.verdicts:
            if v.field in _DELAY_SKIP_FIELDS:
                continue
            if v.verdict in ("MISMATCH", "MISSING"):
                field_tracker.setdefault(v.field, []).append((i, v))
            elif v.verdict == "CORRECT" and v.field in field_tracker:
                for prev_idx, prev_v in field_tracker[v.field]:
                    delay = i - prev_idx
                    if delay > 0:
                        prev_v.verdict = "DELAYED"
                        prev_v.detail = f"Corrected {delay} frames later at {audits[i].frame_id}. " + prev_v.detail
                del field_tracker[v.field]


# ---------------------------------------------------------------------------
# Root cause knowledge base
# ---------------------------------------------------------------------------

# For each issue field: (status, root_cause_or_monitoring)
# status: "KNOWN" = root cause identified, "MONITOR" = needs more data
ROOT_CAUSE_DB: dict[str, tuple[str, str]] = {
    # --- Core Scorecard ---
    "score": ("KNOWN",
              "Consensus delay: ConsistentReadTracker requires 2-3 matching frames before "
              "accepting a new score value. During transitions (replays, graphics), the "
              "extractor returns stale or missing data, keeping the old score until consensus "
              "is re-established."),
    "wickets": ("KNOWN",
                "Same consensus delay as score. Additionally, wickets consensus is decoupled "
                "from score — when score jumps via consensus, wickets and overs can lag by "
                "1-2 frames. Fix: atomic (score, wickets, overs) updates in ConsistentReadTracker."),
    "overs": ("KNOWN",
              "Consensus delay, plus string format mismatch: extractor returns '18' while "
              "tracker stores '18.0'. Both represent the same value but string comparison "
              "fails. The audit script normalises this; the pipeline should too."),
    "run_rate": ("KNOWN",
                 "MISSING = AFTER_run_rate field not present in DETAIL log (added mid-development). "
                 "MISMATCH = pipeline uses simple score/overs division instead of cricket-correct "
                 "balls conversion (0.1 overs = 1 ball, not 0.1 of an over). "
                 "Fix in pipeline: run_rate = (score / total_balls) * 6."),

    # --- Batters ---
    "bat1_name": ("KNOWN",
                  "Two causes: (1) Batter replacement delay after wicket — dismissed batter "
                  "stays in tracker for up to 34 frames until 2-frame consensus sees the new "
                  "batter. (2) Extractor returns surname only ('Jaiswal') while tracker has "
                  "full name ('Yashasvi Jaiswal') — fuzzy match handles this in audit but "
                  "pipeline name resolution can lag."),
    "bat2_name": ("KNOWN", "Same as bat1_name — batter replacement delay and name resolution."),
    "bat1_stats": ("KNOWN",
                   "Consensus delay: batter stats update via 2-frame consensus. Also, "
                   "frame_poisoned blocks stat updates on corrupted frames, which is correct "
                   "behaviour but causes DELAYED verdicts. Additionally, balls_faced can "
                   "mismatch when extractor reads a different frame than the tracker expects."),
    "bat2_stats": ("KNOWN", "Same as bat1_stats."),
    "striker_broadcast": ("KNOWN",
                          "Broadcast * / > indicator is extracted but not always used to "
                          "override the pipeline's striker inference. When the pipeline's "
                          "balls-faced rotation disagrees with broadcast, broadcast should win. "
                          "Fix: in test_pipeline.py, after extract_info_panel, if "
                          "striker_from_broadcast differs from AFTER_striker for 2 consecutive "
                          "frames, force-set striker."),

    # --- Bowler ---
    "bowler_name": ("KNOWN",
                    "Consensus delay: bowler name changes when a new over starts but the "
                    "extractor may read the previous bowler from a replay/transition frame. "
                    "Also, extractor returns surname while tracker has full name."),
    "bowler_figures": ("KNOWN",
                       "Consensus delay: bowler figures (W-R) lag by 1-2 frames after a ball "
                       "event. The pipeline updates bowler figures after ball_event detection, "
                       "but the extractor reads the scoreboard which may not have refreshed yet."),
    "bowler_overs": ("KNOWN",
                     "Consensus delay. Also, career stats detected: extractor sometimes reads "
                     "a bowler's career overs (e.g. 47) instead of match overs (e.g. 4). "
                     "The >4.0 overs guard catches this but doesn't fix the underlying "
                     "extraction ambiguity."),

    # --- This Over ---
    "this_over_count": ("KNOWN",
                        "Rare — usually correct. DELAYED when a ball event fires but "
                        "this_over token hasn't been appended yet (processing order)."),
    "this_over_unresolved": ("KNOWN",
                             "Pipeline joins mid-over and fills unknown past balls with '?'. "
                             "These persist until broadcast THIS OVER data overwrites them. "
                             "Fix: when broadcast this_over is parsed, replace '?' tokens "
                             "positionally. Currently only a full broadcast override happens, "
                             "which may arrive late or not at all."),
    "this_over_extra_notation": ("KNOWN",
                                 "ThisOverManager.on_ball_event appends the run count (e.g. '1') "
                                 "for EXTRA events instead of 'wd'/'nb'. "
                                 "Fix: in ThisOverManager.on_ball_event, check event type — "
                                 "if EXTRA with sub_type wide, append 'wd'; if no-ball, 'nb'."),

    # --- Match Context ---
    "fow_count": ("KNOWN",
                  "fow_count only increments when the pipeline observes a WICKET ball_event. "
                  "It never syncs to the absolute wickets count from the scoreboard. When "
                  "pipeline starts mid-innings, fow_count starts at 0 regardless of actual "
                  "wickets (e.g. 4). Fix: initialise fow_count = scoreboard.wickets on first "
                  "successful score extraction, and re-sync whenever fow_count < wickets."),
    "target": ("KNOWN",
               "Two problems: (1) TARGET regex requires exact 'TARGET NNN' format — the "
               "'TO WIN X OFF Y' format computes target as current_score + runs_remaining, "
               "which drifts as current_score updates, resetting the 3-frame consensus "
               "counter each time. (2) Once computed target changes, consensus never settles. "
               "Fix: prioritise absolute TARGET extraction; for TO WIN, compute target once "
               "and cache it, don't recompute as score changes."),
    "innings": ("KNOWN",
                "Pipeline has no innings detection logic. scoreboard.current_innings defaults "
                "to 1 and is never updated. Fix: if broadcast shows TARGET or TO WIN or "
                "REQUIRED, set innings = 2. Alternatively, detect team change (different "
                "batting_team from innings 1)."),
    "speed_kph": ("KNOWN",
                  "MISSING in older runs = extract_info_panel not implemented yet. "
                  "In Run 7, speed regex requires 'kph' suffix but broadcast sometimes "
                  "shows 'SPEED: 137.7' without 'kph'. "
                  "Fix: make 'kph' optional in _RE_SPEED: r'SPEED:\\s*([\\d.]+)\\s*(?:kph)?'"),
    "partnership": ("KNOWN",
                    "Partnership tracking resets on wicket events. Generally correct but "
                    "may show 0(0) immediately after a wicket before the next ball."),

    # --- Delivery ---
    "delivery_classification": ("KNOWN",
                                "MISMATCH when detections > 0 but no length/line — happens "
                                "when BallAnalyzer has too few detections to find a bounce "
                                "point (< 5 detections). Delivery analysis returns 'unknown' "
                                "which the audit reports as missing classification."),
    "delivery_length": ("KNOWN", "Valid when present. Checked for correct value set."),
    "delivery_line": ("KNOWN", "Valid when present. Checked for correct value set."),
    "delivery_angle": ("KNOWN",
                       "MISSING when detections > 0 but angle wasn't computed — this happens "
                       "when ball entry point x-coordinate is ambiguous (ball detected mid-flight, "
                       "not at release). Generally reliable with sufficient detections (>10)."),
    "delivery_shot": ("KNOWN",
                      "MISSING = shot_type not populated on some ball events. Happens when "
                      "ball_event fires from score change detection (MULTI_BALL, EXTRA) rather "
                      "than from actual ball tracking. Fix: ensure _shot_type_from_runs is "
                      "called for every ball_event that has a runs value."),
    "delivery_shot_four": ("KNOWN",
                           "4 runs hardcoded as 'along_ground' in _shot_type_from_runs(). "
                           "When post-shot detections >= 2, classify_shot_elevation replaces "
                           "this with actual trajectory data. Fallback only fires with 0-1 "
                           "post-shot detections."),
    "delivery_shot_six": ("KNOWN", "6 runs should always be 'aerial'. Currently correct."),
    "delivery_direction": ("KNOWN",
                           "MISSING = post-shot phase had < 2 detections (camera cut, ball too "
                           "small). classify_shot_direction needs 2+ post-contact points to "
                           "determine offside/legside/straight. Currently hardcoded for "
                           "bowler's-end camera + right-handed batter."),
    "delivery_elevation": ("KNOWN",
                           "MISSING = post-shot phase had < 2 detections. "
                           "classify_shot_elevation uses ball area trend to detect aerial "
                           "shots. Replaces runs-based _shot_type_from_runs when available."),
    "delivery_elevation_six": ("KNOWN",
                               "SIX classified as along_ground by elevation classifier. "
                               "Possible if ball area doesn't shrink enough post-contact "
                               "(e.g. flat six). Rare but valid classification error."),
    "delivery_bounce": ("KNOWN",
                        "Valid when present. Requires bounce point + 3 flight detections. "
                        "Measures rise-after-bounce vs pre-descent ratio."),
    "delivery_det_rate": ("KNOWN",
                          "MISMATCH when < 0.10 — very low detection rate means the ball "
                          "diff pipeline barely tracked the ball. Classification from such "
                          "frames is unreliable. Common cause: dark/night match, fast camera "
                          "cut, or ball too small in wide shot."),
    "delivery_dir_confidence": ("KNOWN",
                                "Low confidence (< 0.33) means only 1-2 post-shot detections. "
                                "Direction classification may be unreliable with few data points."),
    "delivery_speed": ("KNOWN",
                       "MISSING = speed not available on the broadcast frame when ball event "
                       "fires. Speed graphic shows for 3-5 seconds after delivery; if the "
                       "pipeline captures a frame during replay or close-up, speed is absent. "
                       "DELAYED = speed was captured on a later frame and retroactively "
                       "associated. This is expected behaviour for per-frame speed."),

    # --- Ball Event Sub-fields ---
    "ball_event_runs": ("KNOWN",
                        "MISMATCH = ball event type disagrees with run count. E.g. DOT with "
                        "runs > 0, or FOUR with runs != 4. Usually indicates a ball_event "
                        "detection error."),
    "ball_event_over": ("KNOWN",
                        "MISSING = ball event fired without an over number. Happens on "
                        "MULTI_BALL events where overs can't be determined. For normal events, "
                        "this indicates a score extraction issue."),
    "ball_event_extra": ("KNOWN",
                         "MISSING = EXTRA event without extra_type. The pipeline should set "
                         "'wide' or 'no_ball' from the action text or scoreboard extras."),
    "ball_event_free_hit": ("KNOWN",
                            "Set to 'yes' when action text contains 'free hit' OR when the "
                            "detector tags the delivery after a confirmed no-ball."),
    "broadcast_extra": ("KNOWN",
                        "CORRECT = broadcast 'EXTRA: WD/NB' signal matches the EXTRA ball "
                        "event. MISMATCH = broadcast says WD/NB but ball event is a different "
                        "type — usually a timing issue where the broadcast signal arrives on a "
                        "different frame than the score change. MISSING on EXTRA = EXTRA event "
                        "fired without broadcast confirmation, detected via heuristic only."),

    # --- Striker Attribution ---
    "striker_this_ball": ("KNOWN",
                          "MISSING = striker snapshot not captured before ball event. "
                          "MISMATCH = striker who faced the ball differs from AFTER_striker "
                          "without a rotation (odd runs). Common after wickets when new batter "
                          "hasn't been confirmed yet."),

    # --- Context Fields ---
    "venue": ("KNOWN",
              "Extracted once from Scout text via venue regex patterns. If MISSING, "
              "broadcast didn't show a recognisable venue string in any captured frame."),
    "batting_team": ("KNOWN",
                     "MISSING on ball event = team assignment hasn't happened yet. "
                     "Teams are set from extractor/squad matching which requires seeing "
                     "a batter name that maps to a known squad."),
    "match_info": ("KNOWN",
                   "Extracted once from Scout text (e.g. 'MATCH 15', '#MIvRCB'). "
                   "If absent, broadcast didn't show match context in any frame."),
    "completed_over": ("KNOWN",
                       "Only populated on the frame where an over change is detected. "
                       "Contains the ball-by-ball tokens of the just-completed over."),
    "completed_over_runs": ("KNOWN",
                            "Sum of numeric tokens in completed_over. Used by analyst "
                            "commentary for over summary."),

    # --- DRS ---
    "drs_state_valid": ("KNOWN", "DRS state machine values are always valid."),
    "drs_transition": ("MONITOR",
                       "Invalid DRS transition detected. Need to log: (1) the Scout text "
                       "on transition frames to see if DRS keywords appear, (2) the exact "
                       "frame where state changed, (3) whether the state machine reset "
                       "prematurely. Add DETAIL field: drs_prev_state= to track transitions."),

    # --- Commentary ---
    "comm_wire_fielding": ("KNOWN",
                           "Wire LLM fabricates fielding positions (point, cover, mid-on, etc.) "
                           "despite ABSOLUTE RULE in prompt banning them. This is an LLM "
                           "compliance failure. Fix options: (1) post-processing regex to strip "
                           "fielding positions from Wire output, (2) add few-shot examples to "
                           "prompt, (3) switch to a more instruction-following model."),
    "comm_storyteller_fielding": ("KNOWN", "Same as comm_wire_fielding — LLM prompt non-compliance."),
    "comm_wire_striker": ("KNOWN",
                          "Wire names the non-striker instead of the striker. Root cause: "
                          "AFTER_striker is wrong due to incorrect strike rotation on EXTRA "
                          "events (fixed in Run 7) or stale striker after batter replacement "
                          "delay. The commentary uses whatever AFTER_striker says, so the "
                          "fix is upstream in striker tracking, not in the prompt."),
    "comm_storyteller_striker": ("KNOWN", "Same as comm_wire_striker — upstream striker tracking."),
    "comm_analyst_runs": ("KNOWN",
                          "Analyst LLM claims '0 runs conceded' despite prompt context showing "
                          "'JUST-COMPLETED OVER: [...] = 4 runs'. This is an LLM hallucination. "
                          "Fix: (1) strengthen Analyst prompt to say 'cite the exact number from "
                          "COMPLETED OVER data', (2) post-process to verify claimed runs match "
                          "completed_over_runs, (3) retry on mismatch."),
    "comm_wire_delivery_length": ("MONITOR",
                                  "Wire has delivery data (length, line) but doesn't mention it. "
                                  "Need to check: (1) is the DELIVERY DATA line actually in the "
                                  "prompt sent to Groq? Log the full prompt. (2) Is the LLM "
                                  "ignoring it or was the data not passed? Add DETAIL field: "
                                  "comm_prompt_has_delivery=True/False."),
    "comm_storyteller_delivery_length": ("MONITOR",
                                        "Same as comm_wire_delivery_length — need to verify "
                                        "delivery data reaches the LLM prompt. Add logging of "
                                        "whether build_ball_context included DELIVERY DATA line."),
    "comm_wire_delivery_line": ("MONITOR",
                                "Wire describes off-side shot when delivery data says leg side "
                                "(or vice versa). Need to check: (1) is the line data correct in "
                                "the first place (pitch crop calibration), (2) does the LLM "
                                "misinterpret the line label? Log the exact DELIVERY DATA line "
                                "sent to the prompt."),
    "comm_storyteller_delivery_line": ("MONITOR",
                                      "Same as comm_wire_delivery_line."),
    "comm_wire_direction": ("KNOWN",
                            "Direction data provided and Wire used it correctly."),
    "comm_storyteller_direction": ("KNOWN",
                                  "Direction data provided and Storyteller used it correctly."),
    "comm_wire_elevation": ("KNOWN",
                            "MISMATCH = commentary says along ground when elevation data says "
                            "in the air (or vice versa). LLM not following DELIVERY DATA."),
    "comm_storyteller_elevation": ("KNOWN",
                                  "Same as comm_wire_elevation."),
    "comm_wire_bowler": ("MONITOR",
                        "Wire names a different bowler than comm_bowler. "
                        "Root cause may be stale bowler in tracker after over change, "
                        "or LLM hallucinating a bowler name."),
    "comm_storyteller_bowler": ("MONITOR",
                                "Same as comm_wire_bowler."),
    "comm_wire_venue": ("KNOWN",
                        "Wire fabricated a venue name with no venue data available. "
                        "LLM is guessing the stadium instead of omitting it."),
    "comm_storyteller_venue": ("KNOWN",
                               "Same as comm_wire_venue."),
    "comm_wire_striker_attribution": ("KNOWN",
                                      "Wire attributes the shot to AFTER_striker but "
                                      "striker_this_ball was different. Common after rotations "
                                      "where AFTER_striker has already swapped."),
    "comm_storyteller_striker_attribution": ("KNOWN",
                                            "Same as comm_wire_striker_attribution."),
    "comm_storyteller_speed": ("KNOWN",
                               "Speed correctly mentioned in commentary when available. No issue."),
    "comm_wire_speed": ("KNOWN",
                        "Speed correctly mentioned in commentary when available. No issue."),
}

# Fields where MONITOR status requires additional logging
MONITORING_RECOMMENDATIONS: dict[str, str] = {
    "drs_transition": (
        "Add to DETAIL log: `drs_prev_state=` showing previous DRS state. "
        "Add to DETAIL log: `drs_trigger=` showing what Scout text triggered the transition. "
        "Log the raw Scout text on every frame where drs_state != NONE."
    ),
    "comm_wire_delivery_length": (
        "Add to DETAIL log: `comm_prompt_has_delivery=True/False` indicating whether "
        "the DELIVERY DATA line was included in the LLM prompt. "
        "Add to DETAIL log: `comm_prompt_delivery_text=` with the exact delivery line sent. "
        "This disambiguates 'LLM ignored data' from 'data never reached LLM'."
    ),
    "comm_storyteller_delivery_length": (
        "Same as comm_wire_delivery_length — add `comm_prompt_has_delivery=` to DETAIL log."
    ),
    "comm_wire_delivery_line": (
        "Add to DETAIL log: `comm_prompt_delivery_text=` with the DELIVERY DATA line. "
        "Also log the raw pitch crop coordinates used for line classification to verify "
        "calibration: `pitch_crop_x=`, `pitch_crop_width=`."
    ),
    "comm_storyteller_delivery_line": (
        "Same as comm_wire_delivery_line."
    ),
}




def render_report(audits: list[FrameAudit], verbose: bool = False) -> str:
    lines: list[str] = []
    lines.append("# Frame Verification Audit\n")
    lines.append(f"**Frames analyzed**: {len(audits)}\n")

    if not audits:
        lines.append("\nNo DETAIL frames found in the log.\n")
        return '\n'.join(lines)

    lines.append(f"**Range**: {audits[0].frame_id} — {audits[-1].frame_id}\n\n")

    # Section 1: Summary table
    field_counts: dict[str, dict[str, int]] = {}
    for audit in audits:
        for v in audit.verdicts:
            if v.field not in field_counts:
                field_counts[v.field] = {"CORRECT": 0, "MISMATCH": 0, "MISSING": 0,
                                         "DELAYED": 0, "FABRICATED": 0, "SKIP": 0}
            field_counts[v.field][v.verdict] = field_counts[v.field].get(v.verdict, 0) + 1

    lines.append("## 1. Summary\n\n")
    lines.append("| Field | CORRECT | MISMATCH | MISSING | DELAYED | FABRICATED | SKIP |\n")
    lines.append("|-------|---------|----------|---------|---------|------------|------|\n")

    sorted_fields = sorted(field_counts.keys(), key=lambda k: (
        -(field_counts[k].get("MISMATCH", 0) + field_counts[k].get("MISSING", 0)
          + field_counts[k].get("FABRICATED", 0)),
        k))

    for fld in sorted_fields:
        c = field_counts[fld]
        total_issues = c.get("MISMATCH", 0) + c.get("MISSING", 0) + c.get("FABRICATED", 0)
        prefix = "**" if total_issues > 0 else ""
        suffix = "**" if total_issues > 0 else ""
        lines.append(f"| {prefix}{fld}{suffix} | {c.get('CORRECT', 0)} | "
                     f"{c.get('MISMATCH', 0)} | {c.get('MISSING', 0)} | "
                     f"{c.get('DELAYED', 0)} | {c.get('FABRICATED', 0)} | "
                     f"{c.get('SKIP', 0)} |\n")
    lines.append("\n")

    # Section 2: Issues grouped by field
    lines.append("## 2. Issues by Field\n\n")
    issue_fields = [fld for fld in sorted_fields
                    if (field_counts[fld].get("MISMATCH", 0)
                        + field_counts[fld].get("MISSING", 0)
                        + field_counts[fld].get("FABRICATED", 0)
                        + field_counts[fld].get("DELAYED", 0)) > 0]

    if not issue_fields:
        lines.append("No issues found across all frames.\n\n")
    else:
        for fld in issue_fields:
            c = field_counts[fld]
            total = sum(v for k, v in c.items() if k != "SKIP")
            issue_total = c.get("MISMATCH", 0) + c.get("MISSING", 0) + c.get("FABRICATED", 0) + c.get("DELAYED", 0)
            pct = int(issue_total / total * 100) if total > 0 else 0
            parts: list[str] = []
            for k in ("MISMATCH", "MISSING", "DELAYED", "FABRICATED"):
                if c.get(k, 0) > 0:
                    parts.append(f"{c[k]} {k}")
            lines.append(f"### {fld} — {', '.join(parts)} ({pct}% of non-SKIP frames)\n\n")

            shown = 0
            for audit in audits:
                for v in audit.verdicts:
                    if v.field == fld and v.verdict not in ("CORRECT", "SKIP"):
                        lines.append(f"- **{audit.frame_id}** [{v.verdict}]: "
                                     f"expected=`{v.expected}` actual=`{v.actual}`")
                        if v.detail:
                            lines.append(f" — {v.detail}")
                        lines.append("\n")
                        shown += 1
                        if shown >= 10:
                            break
                if shown >= 10:
                    remaining = issue_total - shown
                    if remaining > 0:
                        lines.append(f"- ... and {remaining} more\n")
                    break
            lines.append("\n")

    # Section 3: Root Cause & Monitoring
    lines.append("## 3. Root Cause & Monitoring\n\n")
    if not issue_fields:
        lines.append("No issues — no root cause analysis needed.\n\n")
    else:
        known_count = 0
        monitor_count = 0
        for fld in issue_fields:
            entry = ROOT_CAUSE_DB.get(fld)
            c = field_counts[fld]
            issue_total = (c.get("MISMATCH", 0) + c.get("MISSING", 0)
                           + c.get("FABRICATED", 0) + c.get("DELAYED", 0))
            if entry:
                status, explanation = entry
                icon = "ROOT CAUSE KNOWN" if status == "KNOWN" else "MONITORING NEEDED"
                if status == "KNOWN":
                    known_count += 1
                else:
                    monitor_count += 1
                lines.append(f"### {fld} ({issue_total} issues) — {icon}\n\n")
                lines.append(f"{explanation}\n\n")
                if status == "MONITOR" and fld in MONITORING_RECOMMENDATIONS:
                    lines.append(f"**Action**: {MONITORING_RECOMMENDATIONS[fld]}\n\n")
            else:
                monitor_count += 1
                lines.append(f"### {fld} ({issue_total} issues) — MONITORING NEEDED\n\n")
                lines.append("No known root cause. Investigate by examining the specific "
                             "frames listed in Section 2 and correlating with Scout text, "
                             "extractor output, and ball events.\n\n")
                lines.append("**Action**: Add targeted DETAIL log fields for this data path "
                             "to capture the pipeline state when the issue occurs.\n\n")
        lines.append(f"**Summary**: {known_count} issues with known root cause, "
                     f"{monitor_count} issues needing additional monitoring.\n\n")

    # Section 4: Per-frame detail (verbose)
    if verbose:
        lines.append("## 4. Per-Frame Detail\n\n")
        for audit in audits:
            issues = audit.issues
            marker = f" — {len(issues)} issues" if issues else ""
            lines.append(f"### {audit.frame_id} — {audit.frame_type}{marker}\n\n")
            if not audit.verdicts:
                lines.append("No checks performed.\n\n")
                continue
            lines.append("| Field | Expected | Actual | Verdict | Detail |\n")
            lines.append("|-------|----------|--------|---------|--------|\n")
            for v in audit.verdicts:
                exp = v.expected[:50] if len(v.expected) > 50 else v.expected
                act = v.actual[:50] if len(v.actual) > 50 else v.actual
                det = v.detail[:60] if len(v.detail) > 60 else v.detail
                lines.append(f"| {v.field} | `{exp}` | `{act}` | {v.verdict} | {det} |\n")
            lines.append("\n")

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Frame-level UI verification audit")
    parser.add_argument("log_file", help="Path to pipeline log file")
    parser.add_argument("--out", default=None, help="Output markdown file path")
    parser.add_argument("--start-frame", type=int, default=None, help="Start from frame N")
    parser.add_argument("--end-frame", type=int, default=None, help="End at frame M")
    parser.add_argument("--verbose", action="store_true", help="Include per-frame detail tables")
    args = parser.parse_args()

    if args.out is None:
        base = os.path.splitext(os.path.basename(args.log_file))[0]
        args.out = os.path.join(os.path.dirname(args.log_file) or '.', f"audit-{base}.md")

    with open(args.log_file, 'r', errors='replace') as fh:
        raw = strip_ansi(fh.read())

    all_frames = parse_detail_blocks(raw)

    # Filter by frame range
    frames = []
    for fid, ftype, fields in all_frames:
        m = re.match(r'F(\d+)', fid)
        if m:
            n = int(m.group(1))
            if args.start_frame is not None and n < args.start_frame:
                continue
            if args.end_frame is not None and n > args.end_frame:
                continue
        frames.append((fid, ftype, fields))

    print(f"Parsed {len(all_frames)} total DETAIL frames, analyzing {len(frames)}")

    audits: list[FrameAudit] = []
    prev_fields: dict | None = None
    prev_drs: str = 'NONE'
    target_ever_seen = False

    for fid, ftype, fields in frames:
        audit = FrameAudit(frame_id=fid, frame_type=ftype)
        scout_text = fields.get('scout', '')
        gt = extract_ground_truth(scout_text)

        if 'target' in gt or 'to_win' in gt:
            target_ever_seen = True

        audit.verdicts.extend(check_group1_scorecard(fields, gt))
        audit.verdicts.extend(check_group2_batters(fields, gt))
        audit.verdicts.extend(check_group3_bowler(fields, gt))
        audit.verdicts.extend(check_group4_this_over(fields, prev_fields))
        audit.verdicts.extend(check_group5_context(fields, gt, target_ever_seen))
        audit.verdicts.extend(check_group6_delivery(fields))
        audit.verdicts.extend(check_group6c_ball_event(fields))
        audit.verdicts.extend(check_group6d_striker_attribution(fields))
        audit.verdicts.extend(check_group6e_context(fields))
        audit.verdicts.extend(check_drs(fields, prev_drs))
        audit.verdicts.extend(check_group7_commentary(fields))

        # Track DRS state for transition validation
        drs_raw = fields.get('drs_state', '')
        if drs_raw and drs_raw not in ('—', '', 'None'):
            prev_drs = drs_raw.strip().upper()

        audits.append(audit)
        prev_fields = fields

    detect_delays(audits)

    report = render_report(audits, verbose=args.verbose)

    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    with open(args.out, 'w') as fh:
        fh.write(report)

    # Print summary to stdout
    total_verdicts = sum(len(a.verdicts) for a in audits)
    total_issues = sum(len(a.issues) for a in audits)
    print(f"Written audit to {args.out}")
    print(f"Total checks: {total_verdicts}, Issues: {total_issues}")

    # Quick field summary
    field_issues: dict[str, int] = {}
    for a in audits:
        for v in a.issues:
            field_issues[v.field] = field_issues.get(v.field, 0) + 1
    if field_issues:
        print("\nTop issues:")
        for fld, count in sorted(field_issues.items(), key=lambda x: -x[1])[:10]:
            print(f"  {fld}: {count}")


if __name__ == '__main__':
    main()

"""Parse DETAIL|F... lines from pipeline log into a comprehensive frame-by-frame markdown report."""
import re
import sys

LOG_FILE = sys.argv[1] if len(sys.argv) > 1 else "/tmp/pipeline_detail.log"
OUT_FILE = sys.argv[2] if len(sys.argv) > 2 else "/Users/anmolmohan/Projects/SportsComm/files/logs/frame_by_frame_log.md"

ANSI = re.compile(r'\x1b\[[0-9;]*m')

def strip_ansi(s):
    return ANSI.sub('', s)

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
    'delivery_length=', 'delivery_line=', 'delivery_angle=',
    'delivery_shot=', 'delivery_dets=',
    'speed_kph=',
    'drs_state=',
    'corrections=',
    'lat_vision=', 'lat_extract=', 'lat_scorer=', 'lat_field=',
    'lat_comm=', 'lat_code=', 'lat_total=',
    'comm_wire=', 'comm_storyteller=', 'comm_analyst=', 'comm_colour=',
    'comm_wire_ms=', 'comm_story_ms=', 'comm_analyst_ms=', 'comm_colour_ms=',
]


def extract_fields(detail_str):
    """Extract key=value fields from a DETAIL line."""
    fields = {}
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


def main():
    with open(LOG_FILE, 'r', errors='replace') as f:
        raw = f.read()

    raw = strip_ansi(raw)
    lines = raw.split('\n')

    detail_blocks = []
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
            detail_blocks.append(block)
            i = j
        else:
            i += 1

    out = []
    out.append("# Frame-by-Frame Pipeline Analysis\n")
    out.append(f"**Total frames logged**: {len(detail_blocks)}\n")
    out.append("**Pipeline**: ConsistentReadTracker + CricketChecker + BallEventDetector + ThisOverManager + Commentary\n")
    out.append("**Test duration**: ~5 minutes\n\n")
    out.append("## Column Definitions\n\n")
    out.append("### Input / Processing Columns\n")
    out.append("| Column | Description |\n")
    out.append("|--------|-------------|\n")
    out.append("| **Tag** | Frame type from Scout 17B classification (SCOREBOARD, GRAPHIC, ADVERTISEMENT, etc.) |\n")
    out.append("| **Scout** | Raw text from Scout 17B — strip data, overlay info, and action description |\n")
    out.append("| **Action** | Cricket action description — what's happening on screen (delivery bowled, shot played, etc.) |\n")
    out.append("| **Extractor** | Structured data parsed from Scout output: `ext_score` (score-wickets(overs)), `ext_bat` (batter names + runs(balls)), `ext_bowl` (bowler name + wickets-runs(overs)) |\n")
    out.append("| **Scorer changes** | What fields the Scorer LLM decided to update this frame (e.g. score, overs, batter runs) |\n")
    out.append("| **YOLO** | Number of persons detected by local YOLO model for field tracking |\n\n")
    out.append("### UI State Columns (Before vs After)\n")
    out.append("| Column | Description |\n")
    out.append("|--------|-------------|\n")
    out.append("| **BEFORE_score** | Team score-wickets(overs) *before* this frame was processed by the pipeline |\n")
    out.append("| **BEFORE_bat1 / bat2** | Active batter stats (name runs(balls)) *before* processing |\n")
    out.append("| **BEFORE_bowl** | Current bowler stats (name wickets-runs(overs)) *before* processing |\n")
    out.append("| **BEFORE_this_over** | Ball-by-ball display for current over *before* processing |\n")
    out.append("| **AFTER_score** | Team score-wickets(overs) *after* all pipeline processing (tracker + invariant checks) |\n")
    out.append("| **AFTER_bat1 / bat2** | Active batter stats *after* processing |\n")
    out.append("| **AFTER_bowl** | Current bowler stats *after* processing |\n")
    out.append("| **AFTER_this_over** | Ball-by-ball display for current over *after* processing |\n")
    out.append("| **AFTER_field** | Cricket field template name, frozen state, and fielder positions *after* processing |\n\n")
    out.append("### Event Columns\n")
    out.append("| Column | Description |\n")
    out.append("|--------|-------------|\n")
    out.append("| **Ball Event** | Detected ball event type: DOT, FOUR, SIX, WICKET, EXTRA, MULTI_BALL, or — (none) |\n")
    out.append("| **Corrections** | Cricket invariant corrections applied by CricketChecker (e.g. wicket reverts, bowler caps) |\n\n")
    out.append("### Delivery Analysis Columns\n")
    out.append("| Column | Description |\n")
    out.append("|--------|-------------|\n")
    out.append("| **delivery_length** | Ball length from bounce-point y-position: full_toss, full, good_length, short, bouncer, or unknown |\n")
    out.append("| **delivery_line** | Ball line at crease: outside_off, off_stump, middle, leg_stump, down_leg, wide_outside_off, or unknown |\n")
    out.append("| **delivery_angle** | Bowling angle from ball entry x-position: over (the wicket) or round (the wicket) |\n")
    out.append("| **delivery_shot** | Shot type derived from scoreboard runs: defended (0), along_ground (1-5), aerial (6) |\n")
    out.append("| **delivery_dets** | Number of ball detections in the delivery window (higher = more confident; <5 is low confidence) |\n\n")
    out.append("### Latency Columns (all in milliseconds)\n")
    out.append("| Column | Description |\n")
    out.append("|--------|-------------|\n")
    out.append("| **lat_vision** | Time for single Scout 17B call (tag + read in one call) |\n")
    out.append("| **lat_extract** | Time for Extractor LLM call (structured data parsing from Scout text) |\n")
    out.append("| **lat_scorer** | Time for Scorer LLM call (deciding which fields to update) |\n")
    out.append("| **lat_field** | Time for local YOLO field detection (person detection + zone classification) |\n")
    out.append("| **lat_code** | Time for non-API code: tracker updates, invariant checks, over management, field merge, WS broadcast |\n")
    out.append("| **lat_comm** | Time for commentary generation (all triggered narrators in parallel via Groq) |\n")
    out.append("| **lat_total** | Wall-clock time for the entire frame (from before-snapshot to log line) |\n\n")
    out.append("### Commentary Columns\n")
    out.append("| Column | Description |\n")
    out.append("|--------|-------------|\n")
    out.append("| **comm_wire** | Wire narrator output — factual ball-by-ball, 2-3 sentences (fires every ball event) |\n")
    out.append("| **comm_storyteller** | Storyteller narrator output — radio-style narrative, 3-5 sentences (fires every ball event) |\n")
    out.append("| **comm_analyst** | Analyst narrator output — tactical/statistical insight (fires on over-end, wickets, milestones) |\n")
    out.append("| **comm_colour** | Colour narrator output — big-moment drama (fires on milestones, set-batter dismissals, last-over, RRR thresholds) |\n")
    out.append("| **comm_wire_ms / comm_story_ms / comm_analyst_ms / comm_colour_ms** | Individual Groq latency per narrator (0 if narrator didn't fire) |\n\n")
    out.append("---\n\n")

    all_ui_scores = []
    all_bowlers = []
    all_batters = []
    latency_vision = []
    latency_extract = []
    latency_scorer = []
    latency_field = []
    latency_comm = []
    latency_code = []
    latency_total = []
    comm_wire_latencies = []
    comm_story_latencies = []
    comm_analyst_latencies = []
    comm_colour_latencies = []
    comm_fire_count = {"wire": 0, "storyteller": 0, "analyst": 0, "colour": 0}

    prev_ui_score = None
    prev_ui_bat1 = None
    prev_ui_bat2 = None
    prev_ui_bowl = None

    for block in detail_blocks:
        idx = block.find('DETAIL|')
        if idx < 0:
            continue
        detail = block[idx:]
        parts = detail.split('|', 3)
        frame_id = parts[1] if len(parts) > 1 else "?"
        frame_type = parts[2] if len(parts) > 2 else "?"
        rest = parts[3] if len(parts) > 3 else ""

        fields = extract_fields(rest)

        tag_val = fields.get('tag', fields.get('qwen', '—'))
        scout_raw = fields.get('scout', '—')
        scout_lines_list = scout_raw.split('\n')[:4]
        scout = '\n'.join(scout_lines_list)
        if len(scout) > 250:
            scout = scout[:250] + '...'
        action_text = fields.get('action', '—')

        ext_score = fields.get('ext_score', '—')
        ext_bat = fields.get('ext_bat', '—') or '—'
        ext_bowl = fields.get('ext_bowl', '—') or '—'
        scorer = fields.get('scorer_changes', '—')
        yolo = fields.get('yolo', '0')

        # Before state
        before_score = fields.get('BEFORE_score', '—')
        before_bat1 = fields.get('BEFORE_bat1', '—')
        before_bat2 = fields.get('BEFORE_bat2', '—')
        before_bowl = fields.get('BEFORE_bowl', '—')
        before_this_over = fields.get('BEFORE_this_over', '—')

        # After state
        ui_score = fields.get('AFTER_score', '—')
        ui_bat1 = fields.get('AFTER_bat1', '—')
        ui_bat2 = fields.get('AFTER_bat2', '—')
        ui_bowl = fields.get('AFTER_bowl', '—')
        ui_this_over = fields.get('AFTER_this_over', '—')
        ui_field_raw = fields.get('AFTER_field', '—')
        ball_event = fields.get('ball_event', '—')

        del_length = fields.get('delivery_length', '—')
        del_line = fields.get('delivery_line', '—')
        del_angle = fields.get('delivery_angle', '—')
        del_shot = fields.get('delivery_shot', '—')
        del_dets = fields.get('delivery_dets', '0')

        corrections_raw = fields.get('corrections', 'none').split('\n')[0].strip()
        if corrections_raw in ('none', '0', ''):
            corrections_list = []
        else:
            corrections_list = [c.strip() for c in corrections_raw.split(';') if c.strip()]

        # Latency
        lv = fields.get('lat_vision', '0')
        le = fields.get('lat_extract', '0')
        ls = fields.get('lat_scorer', '0')
        lf = fields.get('lat_field', '0')
        lc = fields.get('lat_comm', '0')
        lcode = fields.get('lat_code', '0')
        lt = fields.get('lat_total', '0')

        def safe_int(s):
            try:
                return int(float(s))
            except (ValueError, TypeError):
                return 0

        lv_i, le_i, ls_i, lf_i, lc_i, lcode_i, lt_i = (
            safe_int(lv), safe_int(le), safe_int(ls),
            safe_int(lf), safe_int(lc), safe_int(lcode), safe_int(lt))

        latency_vision.append(lv_i)
        latency_extract.append(le_i)
        latency_scorer.append(ls_i)
        latency_field.append(lf_i)
        latency_comm.append(lc_i)
        latency_code.append(lcode_i)
        latency_total.append(lt_i)

        # Commentary
        cw = fields.get('comm_wire', '—')
        cs = fields.get('comm_storyteller', '—')
        ca = fields.get('comm_analyst', '—')
        cc = fields.get('comm_colour', '—')

        cw_ms = safe_int(fields.get('comm_wire_ms', '0'))
        cs_ms = safe_int(fields.get('comm_story_ms', '0'))
        ca_ms = safe_int(fields.get('comm_analyst_ms', '0'))
        cc_ms = safe_int(fields.get('comm_colour_ms', '0'))

        if cw != '—' and cw:
            comm_wire_latencies.append(cw_ms)
            comm_fire_count["wire"] += 1
        if cs != '—' and cs:
            comm_story_latencies.append(cs_ms)
            comm_fire_count["storyteller"] += 1
        if ca != '—' and ca:
            comm_analyst_latencies.append(ca_ms)
            comm_fire_count["analyst"] += 1
        if cc != '—' and cc:
            comm_colour_latencies.append(cc_ms)
            comm_fire_count["colour"] += 1

        all_ui_scores.append(ui_score)
        all_bowlers.append(ui_bowl)
        all_batters.append((ui_bat1, ui_bat2))

        field_frozen = 'frozen=True' in ui_field_raw
        field_template = ui_field_raw.split(' frozen=')[0] if ' frozen=' in ui_field_raw else ui_field_raw

        score_changed = ui_score != prev_ui_score and prev_ui_score is not None
        bat_changed = (ui_bat1 != prev_ui_bat1 or ui_bat2 != prev_ui_bat2) and prev_ui_bat1 is not None
        bowl_changed = ui_bowl != prev_ui_bowl and prev_ui_bowl is not None

        # Detect what changed between before and after
        score_diff = before_score != ui_score
        bat1_diff = before_bat1 != ui_bat1
        bat2_diff = before_bat2 != ui_bat2
        bowl_diff = before_bowl != ui_bowl
        over_diff = before_this_over != ui_this_over

        out.append(f"\n## {frame_id} — {frame_type}\n")

        # Latency bar
        out.append(f"**Latency**: V:`{lv_i}ms` E:`{le_i}ms` S:`{ls_i}ms` "
                    f"Field:`{lf_i}ms` Code:`{lcode_i}ms` Comm:`{lc_i}ms` "
                    f"**Total:`{lt_i}ms`**\n\n")

        out.append(f"**Tag**: `{tag_val}`\n\n")

        out.append(f"**Scout**:\n```\n{scout}\n```\n\n")

        if action_text and action_text != '—':
            out.append(f"**Action**: {action_text}\n\n")

        out.append(f"**Extractor**: score=`{ext_score}` bat=`{ext_bat}` bowl=`{ext_bowl}`\n\n")

        out.append(f"**Scorer changes**: `{scorer}`\n\n")

        out.append(f"**YOLO**: `{yolo}` persons\n\n")

        # Before / After comparison
        out.append(f"**UI State — Before vs After**:\n")
        out.append(f"| Element | Before | After | Changed? |\n")
        out.append(f"|---------|--------|-------|----------|\n")
        out.append(f"| Score | `{before_score}` | `{ui_score}` | {'**YES**' if score_diff else ''} |\n")
        out.append(f"| Batter 1 | `{before_bat1}` | `{ui_bat1}` | {'**YES**' if bat1_diff else ''} |\n")
        out.append(f"| Batter 2 | `{before_bat2}` | `{ui_bat2}` | {'**YES**' if bat2_diff else ''} |\n")
        out.append(f"| Bowler | `{before_bowl}` | `{ui_bowl}` | {'**YES**' if bowl_diff else ''} |\n")
        out.append(f"| This Over | `{before_this_over}` | `{ui_this_over}` | {'**YES**' if over_diff else ''} |\n")
        out.append(f"| Field | | `{field_template}` frozen=`{field_frozen}` | |\n\n")

        # Ball event & delivery analysis & corrections
        out.append(f"**Ball Event**: `{ball_event}`\n\n")

        has_delivery = del_dets not in ('0', '—') and safe_int(del_dets) > 0
        if has_delivery or ball_event not in ('—', 'None', ''):
            out.append(f"**Delivery Analysis** ({del_dets} detections):\n")
            out.append(f"| Aspect | Value |\n")
            out.append(f"|--------|-------|\n")
            out.append(f"| Length | `{del_length}` |\n")
            out.append(f"| Line | `{del_line}` |\n")
            out.append(f"| Angle | `{del_angle}` |\n")
            out.append(f"| Shot type | `{del_shot}` |\n")
            dets_i = safe_int(del_dets)
            if dets_i == 0:
                out.append(f"| Confidence | ❌ No detections — classification unavailable |\n")
            elif dets_i < 5:
                out.append(f"| Confidence | ⚠️ Low ({dets_i} detections) |\n")
            elif dets_i < 15:
                out.append(f"| Confidence | 🟡 Medium ({dets_i} detections) |\n")
            else:
                out.append(f"| Confidence | ✅ High ({dets_i} detections) |\n")
            out.append("\n")

        if corrections_list:
            out.append(f"**Corrections** ({len(corrections_list)}):\n")
            for c in corrections_list:
                out.append(f"- `{c}`\n")
            out.append("\n")
        else:
            out.append(f"**Corrections**: none\n\n")

        # Commentary
        has_comm = any(x not in ('—', '') for x in [cw, cs, ca, cc])
        if has_comm:
            out.append(f"**Commentary**:\n")
            if cw and cw != '—':
                out.append(f"| Persona | Latency | Text |\n")
                out.append(f"|---------|---------|------|\n")
                if cw and cw != '—':
                    out.append(f"| Wire | `{cw_ms}ms` | {cw[:150]} |\n")
                if cs and cs != '—':
                    out.append(f"| Storyteller | `{cs_ms}ms` | {cs[:200]} |\n")
                if ca and ca != '—':
                    out.append(f"| Analyst | `{ca_ms}ms` | {ca[:200]} |\n")
                if cc and cc != '—':
                    out.append(f"| Colour | `{cc_ms}ms` | {cc[:200]} |\n")
            out.append("\n")
        else:
            out.append(f"**Commentary**: —\n\n")

        # Analysis
        frame_issues = []
        if ext_score and ext_score != '—':
            ext_parts = ext_score.split('-')
            ui_parts = ui_score.split('-') if ui_score != '—' else []
            if len(ext_parts) >= 2 and len(ui_parts) >= 2:
                try:
                    e_s = ext_parts[0].strip()
                    u_s = ui_parts[0].strip()
                    if e_s != 'None' and u_s != 'None':
                        if abs(int(e_s) - int(u_s)) > 5:
                            frame_issues.append(
                                f"Score mismatch: extractor={e_s} vs UI={u_s}")
                except (ValueError, IndexError):
                    pass

        if ext_bowl and ext_bowl != '—':
            try:
                ov_match = re.search(r'\(([0-9.]+)\)', ext_bowl)
                if ov_match and float(ov_match.group(1)) > 4.0:
                    frame_issues.append(f"Career stat detected: {ext_bowl}")
            except (ValueError, IndexError):
                pass

        any_state_change = score_diff or bat1_diff or bat2_diff or bowl_diff or over_diff
        if any_state_change:
            diffs = []
            if score_diff:
                diffs.append(f"score {before_score}→{ui_score}")
            if bat1_diff:
                diffs.append(f"bat1 {before_bat1}→{ui_bat1}")
            if bat2_diff:
                diffs.append(f"bat2 {before_bat2}→{ui_bat2}")
            if bowl_diff:
                diffs.append(f"bowl {before_bowl}→{ui_bowl}")
            if over_diff:
                diffs.append(f"this_over {before_this_over}→{ui_this_over}")
            frame_issues.append(f"State changed: {', '.join(diffs)}")

        if ball_event not in ('—', 'None', ''):
            frame_issues.append(f"Ball event: {ball_event}")
            dets_i = safe_int(del_dets)
            if dets_i > 0 and del_length not in ('—', 'unknown'):
                frame_issues.append(
                    f"Delivery: {del_angle} wicket, {del_length}, {del_line}, {del_shot} "
                    f"({dets_i} dets)")
            elif dets_i > 0:
                frame_issues.append(
                    f"Delivery: partial — {del_shot} only ({dets_i} dets, "
                    f"length/line unknown)")
            elif ball_event not in ('MULTI_BALL',):
                frame_issues.append("Delivery: ❌ no classification")
        if corrections_list:
            for c in corrections_list:
                frame_issues.append(f"Correction: {c}")
        if not field_frozen and yolo and safe_int(yolo) > 0:
            frame_issues.append(f"Field NOT frozen — {yolo} YOLO detections")
        if lt_i > 3000:
            frame_issues.append(f"Slow frame: {lt_i}ms total")
        if lcode_i > 200:
            frame_issues.append(f"Slow code: {lcode_i}ms (non-API processing)")

        if not frame_issues:
            frame_issues.append("Clean frame — no state change")

        out.append(f"**Analysis**:\n")
        for issue in frame_issues:
            out.append(f"- {issue}\n")
        out.append(f"\n---\n")

        prev_ui_score = ui_score
        prev_ui_bat1 = ui_bat1
        prev_ui_bat2 = ui_bat2
        prev_ui_bowl = ui_bowl

    # ── Executive Summary ──
    unique_scores = list(dict.fromkeys(all_ui_scores))
    unique_bowlers = list(dict.fromkeys(all_bowlers))

    def avg(lst):
        return int(sum(lst) / len(lst)) if lst else 0

    def p95(lst):
        if not lst:
            return 0
        s = sorted(lst)
        return s[int(len(s) * 0.95)]

    summary = []
    summary.append("\n## Executive Summary\n")

    summary.append(f"### Score Progression\n")
    summary.append(f"`{'` → `'.join(s for s in unique_scores if s != '—')}`\n\n")

    summary.append(f"### Bowler Progression\n")
    summary.append(f"`{'` → `'.join(b for b in unique_bowlers if b != '—' and '?' not in b)}`\n\n")

    seen_bat1 = []
    for b1, b2 in all_batters:
        if b1 not in ('—', '') and b1 not in seen_bat1:
            seen_bat1.append(b1)
    summary.append(f"### Batter 1 Progression\n")
    summary.append(f"`{'` → `'.join(seen_bat1[:10])}`\n\n")

    seen_bat2 = []
    for b1, b2 in all_batters:
        if b2 not in ('—', '') and b2 not in seen_bat2:
            seen_bat2.append(b2)
    summary.append(f"### Batter 2 Progression\n")
    summary.append(f"`{'` → `'.join(seen_bat2[:10])}`\n\n")

    # Latency summary
    summary.append(f"### Latency Summary (ms)\n")
    summary.append(f"| Step | Avg | P95 | Max |\n")
    summary.append(f"|------|-----|-----|-----|\n")
    for name, data in [
        ("Vision", latency_vision), ("Extractor", latency_extract),
        ("Scorer", latency_scorer), ("Field/YOLO", latency_field),
        ("Code", latency_code), ("Commentary", latency_comm),
        ("**Total**", latency_total)]:
        if data:
            summary.append(f"| {name} | {avg(data)} | {p95(data)} | {max(data)} |\n")
    summary.append("\n")

    # Commentary summary
    summary.append(f"### Commentary Summary\n")
    summary.append(f"| Persona | Fires | Avg Latency | P95 Latency |\n")
    summary.append(f"|---------|-------|-------------|-------------|\n")
    for name, data, count in [
        ("Wire", comm_wire_latencies, comm_fire_count["wire"]),
        ("Storyteller", comm_story_latencies, comm_fire_count["storyteller"]),
        ("Analyst", comm_analyst_latencies, comm_fire_count["analyst"]),
        ("Colour", comm_colour_latencies, comm_fire_count["colour"])]:
        summary.append(f"| {name} | {count} | {avg(data)}ms | {p95(data)}ms |\n")
    summary.append("\n")

    for i, line in enumerate(summary):
        out.insert(4 + i, line)

    import os
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, 'w') as f:
        f.write('\n'.join(out))

    print(f"Written {len(detail_blocks)} frames to {OUT_FILE}")
    print(f"Latency: avg={avg(latency_total)}ms p95={p95(latency_total)}ms max={max(latency_total) if latency_total else 0}ms")
    print(f"Commentary: wire={comm_fire_count['wire']} story={comm_fire_count['storyteller']} "
          f"analyst={comm_fire_count['analyst']} colour={comm_fire_count['colour']}")


if __name__ == '__main__':
    main()

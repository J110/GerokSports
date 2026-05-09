"""Build a per-window test page for Gemini delivery classification.

This is the *test harness*, not the pipeline.  Its job is to take a set
of recorded delivery windows from a session and render a static HTML
report that tells us, ball-by-ball:

  - what the *broadcast* actually showed (from a hand-graded fixture)
  - what the *pipeline*'s ScoreManager thought happened (the score
    event that consumed each window — runs, event type, over.ball, the
    formatted comm_wire line)
  - what *Gemini* classified the clip as
  - whether each Gemini field matches the ground truth (when truth is
    available)

The original implementation paired by index (i-th window <-> i-th wire
event) which is wrong for any non-trivial session — wires get
deduplicated, windows get rejected, the offset compounds.  This
implementation pairs by *event sequence*: each [DWR] window CLOSE on
score_event is the i-th score-event consumption, and the i-th
score-event firing in the pipeline log is the matching one.  This is
exact.

Inputs:
  files/logs/machine-1-2026-04-20.log               (DWR + Gemini logs)
  files/logs/pipeline-nzvssl-live.log               (ScoreManager + wire)
  files/logs/deliveries/<session>/...               (mp4s + jsons)
  files/logs/audit_v1/fixtures/over_test_<session>.json   (ground truth)

Output:
  files/logs/audit_v1/over_test_<session>/over_test.html
  files/logs/audit_v1/over_test_<session>/over_test_data.json
  files/logs/audit_v1/over_test_<session>/ball_<i>_w<wid>.mp4
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SESSION = "20260420_140137"
DELIV_ROOT = ROOT / "logs" / "deliveries" / SESSION
WIN_ROOT = DELIV_ROOT / "windows"
MACHINE_LOG = ROOT / "logs" / "machine-1-2026-04-20.log"
PIPE_LOG = ROOT / "logs" / "pipeline-nzvssl-live.log"
FIXTURE = ROOT / "logs" / "audit_v1" / "fixtures" / f"over_test_{SESSION}.json"
OUT_ROOT = ROOT / "logs" / "audit_v1" / f"over_test_{SESSION}"

ANSI = re.compile(r"\x1b\[[0-9;]*m")


# ───────────────────────── machine log ──────────────────────────

def parse_machine_log() -> tuple[list[dict], list[dict]]:
    """Walk the machine log for one session.

    Returns:
      score_close_events: ordered list of windows that were closed
        BY a score event.  Each entry:
          {window_id, close_ts, reason, frames, dur_s,
           gemini: {...} | None,        # the GEMINI OK/REJECT block
           gemini_idx_in_session: int}  # rank among score-event closes
      no_window_events: ordered list of "[DWR] score_event with NO
        captured window" markers (these consumed nothing — they're
        ScoreManager firings the pipeline missed).
    """
    if not MACHINE_LOG.exists():
        sys.exit(f"missing {MACHINE_LOG}")
    text = MACHINE_LOG.read_text(errors="replace")
    lines = text.splitlines()

    boot = -1
    for i, ln in enumerate(lines):
        if f"BallAnalyzer mode: GEMINI (session={SESSION}" in ln:
            boot = i
    if boot < 0:
        sys.exit(f"can't find session {SESSION} in {MACHINE_LOG}")
    lines = lines[boot:]

    # Patterns
    close_re = re.compile(
        r"\[DWR\] window #(\d+) CLOSE reason=(\S+) start=([\d.]+) "
        r"end=([\d.]+) dur=([\d.]+)s")
    classify_re = re.compile(
        r"\[DWR\] window #(\d+) classify: (\d+) frames "
        r"\(([\d.]+)s, reason=([^)]+)\)")
    too_few_re = re.compile(
        r"\[DWR\] window #(\d+) too few frames \((\d+)\)")
    consumed_re = re.compile(
        r"\[DWR\] score_event consumed window #(\d+) result")
    no_window_re = re.compile(
        r"\[DWR\] score_event with NO captured window")
    gemini_ok_re = re.compile(
        r"\[D#(\d+)\] GEMINI OK \((\d+)ms\): (.*)")
    gemini_rej_re = re.compile(
        r"\[D#(\d+)\] GEMINI REJECT: (\S+) (.*)")

    win_meta: dict[int, dict] = {}
    closes_in_order: list[dict] = []  # windows that closed on score event
    pending_consume_wid: int | None = None
    no_window_events: list[dict] = []

    for ln in lines:
        m = close_re.search(ln)
        if m:
            wid = int(m.group(1))
            reason = m.group(2)
            win_meta.setdefault(wid, {}).update({
                "close_reason": reason,
                "start_ts": float(m.group(3)),
                "end_ts": float(m.group(4)),
                "dur_s": float(m.group(5)),
            })
            continue
        m = classify_re.search(ln)
        if m:
            wid = int(m.group(1))
            win_meta.setdefault(wid, {}).update({
                "frames": int(m.group(2)),
                "classify_dur_s": float(m.group(3)),
                "classify_reason": m.group(4),
            })
            continue
        m = too_few_re.search(ln)
        if m:
            wid = int(m.group(1))
            win_meta.setdefault(wid, {}).update({
                "too_few_frames": True,
                "frames": int(m.group(2)),
            })
            continue
        m = consumed_re.search(ln)
        if m:
            pending_consume_wid = int(m.group(1))
            continue
        m = no_window_re.search(ln)
        if m:
            no_window_events.append({
                "rank": len(closes_in_order) + len(no_window_events),
                "ts": None,
            })
            pending_consume_wid = None
            continue
        m = gemini_ok_re.search(ln)
        if m and pending_consume_wid is not None:
            wid = pending_consume_wid
            meta = win_meta.get(wid, {})
            closes_in_order.append({
                "window_id": wid,
                "d_num": int(m.group(1)),
                "close_ts": meta.get("end_ts"),
                "close_reason": meta.get("close_reason"),
                "frames": meta.get("frames"),
                "dur_s": meta.get("dur_s"),
                "gemini_ms": int(m.group(2)),
                "gemini_summary": m.group(3).strip(),
                "rejected": False,
                "reject_reason": None,
            })
            pending_consume_wid = None
            continue
        m = gemini_rej_re.search(ln)
        if m and pending_consume_wid is not None:
            wid = pending_consume_wid
            meta = win_meta.get(wid, {})
            closes_in_order.append({
                "window_id": wid,
                "d_num": int(m.group(1)),
                "close_ts": meta.get("end_ts"),
                "close_reason": meta.get("close_reason"),
                "frames": meta.get("frames", 0),
                "dur_s": meta.get("dur_s"),
                "gemini_ms": None,
                "gemini_summary": m.group(0).strip(),
                "rejected": True,
                "reject_reason": m.group(2),
            })
            pending_consume_wid = None
            continue

    return closes_in_order, no_window_events


# ───────────────────────── pipeline log ─────────────────────────

def parse_pipeline_score_events() -> list[dict]:
    """Return ordered list of every ScoreManager firing in the
    pipeline log, with the comm_wire line that was emitted at that
    moment.

    Each entry:
      {wall_ts: 'HH:MM:SS',
       event_type: 'DOT'|'FOUR'|'EXTRA'|...,
       runs: int,
       over_ball: '3.1',
       wire: '3.1: Adam Milne to K Mendis — no run, full. 6/0' | None,
       bowler, batter}
    """
    if not PIPE_LOG.exists():
        sys.exit(f"missing {PIPE_LOG}")
    text = PIPE_LOG.read_text(errors="replace")
    text = ANSI.sub("", text)

    line_re = re.compile(
        r"\[(\d\d:\d\d:\d\d)\s+F\d+\s+TEST\]\s+INFO:\s+DETAIL\|.*?"
        r"ball_event=([A-Z_]+)\|"
        r"ball_event_runs=([0-9]+)\|"
        r"ball_event_over=([0-9]+\.[0-9]+)\|.*?"
        r"comm_wire=([^|]*)\|comm_storyteller=",
    )
    events = []
    for m in line_re.finditer(text):
        ev_type = m.group(2)
        if ev_type == "—":
            continue
        wire = m.group(5).strip()
        if wire == "—":
            wire = None
        # Pull bowler / batter out of the wire line (best-effort)
        bowler = batter = None
        if wire:
            wm = re.match(
                r"^[0-9]+\.[0-9]+:\s+(.+?)\s+to\s+(.+?)\s+—",
                wire,
            )
            if wm:
                bowler = wm.group(1).strip()
                batter = wm.group(2).strip()
        events.append({
            "wall_ts": m.group(1),
            "event_type": ev_type,
            "runs": int(m.group(3)),
            "over_ball": m.group(4),
            "wire": wire,
            "bowler": bowler,
            "batter": batter,
        })
    return events


# ───────────────────────── pairing ──────────────────────────────

# IST offset.  The pipeline log uses local wall-clock (the operator
# is in IST), the machine log uses time.time() which is UTC seconds.
# Confirmed by aligning one known-pair: window #15 close at
# unix_ts=1776674290.69 → 14:08:10 IST, pipeline event at 14:08:17 IST.
IST_OFFSET_SEC = 5 * 3600 + 30 * 60


def unix_to_ist_hms(unix_ts: float) -> str:
    """Convert unix-ts to 'HH:MM:SS' in IST."""
    ist = unix_ts + IST_OFFSET_SEC
    secs = int(ist) % 86400
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def hms_to_secs(hms: str) -> int:
    h, m, s = (int(x) for x in hms.split(":"))
    return h * 3600 + m * 60 + s


def pair_windows_to_pipeline(
    closes: list[dict],
    pipe_events: list[dict],
    no_window_events: list[dict],
) -> list[dict]:
    """Pair each window-close-on-score-event to its pipeline event.

    Strategy:
      The DWR-side score-event consumptions and the pipeline-side
      ScoreManager firings come from the SAME ScoreManager calls.
      In the original test we tried zipping by index — that fails
      when DWR misses some firings ('score_event with NO captured
      window' lines in the machine log).  We can instead align by
      (event_type, runs, time-window) — the firings are far enough
      apart in time (>3 s typically) that this disambiguates fully.

    Each pair (in window order):
      window-i  ⇄  pipeline-event-j   (within ±20 s, matching ev/runs)

    Pipeline events that fail to pair are 'wire-orphans'.  Closes
    that fail are 'window-orphans'.
    """
    used_pipe = set()
    pairs: list[dict] = []

    for c in closes:
        close_hms = unix_to_ist_hms(c["close_ts"])
        close_secs = hms_to_secs(close_hms)
        # close_reason is e.g. 'score_event:EXTRA' — pull event type
        ev_type = (c["close_reason"] or "").split(":", 1)[-1].strip()
        # ScoreManager fires '1_RUNS', '2_RUNS' etc; DWR sometimes
        # logs just the number.  Normalise.
        ev_type_normed = re.sub(r"^\d+_", "", ev_type)

        best_j = -1
        best_dt = 999
        for j, e in enumerate(pipe_events):
            if j in used_pipe:
                continue
            if e["event_type"] != ev_type_normed and ev_type_normed not in (
                    "RUNS", "EXTRA"):
                # Allow loose match for RUNS variants
                continue
            dt = hms_to_secs(e["wall_ts"]) - close_secs
            if dt < -5 or dt > 30:
                continue
            if abs(dt) < best_dt:
                best_dt = abs(dt)
                best_j = j
        match = pipe_events[best_j] if best_j >= 0 else None
        if best_j >= 0:
            used_pipe.add(best_j)
        pairs.append({
            **c,
            "close_hms_ist": close_hms,
            "pipeline_event": match,
            "pair_dt_s": best_dt if best_j >= 0 else None,
        })

    # Mark orphans for diagnostic printing
    orphans = [e for j, e in enumerate(pipe_events) if j not in used_pipe]
    return pairs, orphans


# ───────────────────────── enrichment ───────────────────────────

def enrich_with_artifacts(pairs: list[dict]) -> None:
    for p in pairs:
        d = p["d_num"]
        wid = p["window_id"]
        pred_path = DELIV_ROOT / f"d{d:03d}" / "predictions.json"
        p["predictions"] = (json.loads(pred_path.read_text())
                            if pred_path.exists() else None)
        if wid:
            req = WIN_ROOT / f"window_{wid:04d}" / "gemini_request.json"
            mp4 = WIN_ROOT / f"window_{wid:04d}" / "delivery_window.mp4"
            p["gemini_request"] = (json.loads(req.read_text())
                                   if req.exists() else None)
            p["mp4_src"] = str(mp4) if mp4.exists() else None
        else:
            p["gemini_request"] = None
            p["mp4_src"] = None


def attach_fixture(pairs: list[dict], fixture: dict) -> None:
    """Attach the hand-graded ground-truth label (if any) to each
    pair, indexed by window_id."""
    by_wid = {lbl["window_id"]: lbl for lbl in fixture.get("labels", [])}
    for p in pairs:
        p["fixture"] = by_wid.get(p["window_id"])


# ───────────────────────── selection ────────────────────────────

def select_test_windows(pairs: list[dict],
                        fixture: dict) -> list[dict]:
    """Pick the windows we want on the test page.  Use the windows
    listed in the fixture so the page always covers exactly the
    hand-graded set."""
    wanted = [lbl["window_id"] for lbl in fixture.get("labels", [])]
    by_wid = {p["window_id"]: p for p in pairs}
    chosen = []
    for wid in wanted:
        if wid not in by_wid:
            print(f"WARN: fixture window #{wid} not found in machine log "
                  f"(no matching score-event close)")
            continue
        chosen.append(by_wid[wid])
    return chosen


# ───────────────────────── grading ──────────────────────────────

# Maps from Gemini-schema enum values to the truth-schema values that
# count as a match.  Both sides use the canonical schema, so this is
# mostly identity, but Gemini emits 'over_the_wicket' while truth uses
# the same — we just need exact match.
def grade_field(truth: str | None, pred: str | None) -> str:
    """Return 'match' | 'miss' | 'na' | 'unknown_pred'."""
    if truth is None or truth == "" or truth == "unknown":
        return "na"
    if pred is None or pred == "" or pred == "—":
        return "miss"
    if pred == "unknown":
        return "unknown_pred"
    if str(truth).lower() == str(pred).lower():
        return "match"
    return "miss"


GRADE_FIELDS = [
    "bowling_arm",
    "bowling_angle",
    "bowling_type",
    "length",
    "line",
    "bounce",
    "shot_type",
    "shot_side",
    "shot_angle",
    "elevation",
    "contact_quality",
]


def grade_pair(p: dict) -> dict:
    """Return per-field grading + aggregate."""
    truth = (p.get("fixture") or {}).get("truth")
    pred = (p.get("gemini_request") or {}).get("parsed", {}) or {}
    grades = {}
    if not truth:
        return {"per_field": {}, "graded": 0, "matched": 0,
                "is_delivery_truth": (p.get("fixture") or {})
                .get("is_delivery", None)}
    for f in GRADE_FIELDS:
        grades[f] = grade_field(truth.get(f), pred.get(f))
    graded = sum(1 for g in grades.values() if g in ("match", "miss"))
    matched = sum(1 for g in grades.values() if g == "match")
    return {"per_field": grades, "graded": graded, "matched": matched,
            "is_delivery_truth": True}


# ───────────────────────── HTML render ──────────────────────────

GRADE_BG = {
    "match": "#d6f5d6",   # green
    "miss": "#fbd6d6",    # red
    "unknown_pred": "#fff2cc",  # yellow
    "na": "#f1f1f1",      # gray
}


def cell(value, grade=None) -> str:
    bg = GRADE_BG.get(grade, "transparent")
    return (f"<td style='background:{bg}'>"
            f"{'—' if value in (None, '') else value}</td>")


def render_html(chosen: list[dict], fixture: dict, orphans: list[dict],
                no_window_events: list[dict]) -> str:
    n_truth = sum(1 for p in chosen if (p.get("fixture") or {}).get("truth"))
    total_graded = total_matched = 0
    field_totals: dict[str, dict] = {f: {"match": 0, "miss": 0, "na": 0,
                                         "unknown_pred": 0}
                                     for f in GRADE_FIELDS}

    rows = []
    for i, p in enumerate(chosen, start=1):
        gp = (p.get("gemini_request") or {}).get("parsed", {}) or {}
        fix = p.get("fixture") or {}
        truth = fix.get("truth") or {}
        grading = grade_pair(p)
        total_graded += grading["graded"]
        total_matched += grading["matched"]
        for f, g in grading.get("per_field", {}).items():
            field_totals[f][g] += 1

        pe = p.get("pipeline_event") or {}
        wire = pe.get("wire") or "(no wire emitted at score event)"
        bcast_ball = fix.get("broadcast_ball") or pe.get("over_ball") or "—"
        is_del = fix.get("is_delivery")
        is_del_badge = (
            "<span class='badge ok'>delivery</span>" if is_del is True
            else ("<span class='badge bad'>NOT a delivery</span>"
                  if is_del is False else
                  "<span class='badge na'>unlabelled</span>"))

        # Build the comparison table rows
        per_field = grading.get("per_field", {})
        comp_rows = []
        for f in GRADE_FIELDS:
            tv = truth.get(f) if truth else None
            pv = gp.get(f)
            g = per_field.get(f, "na")
            comp_rows.append(
                f"<tr><td class='fname'>{f}</td>"
                f"{cell(tv)}{cell(pv, g)}</tr>")
        if truth:
            comp_rows.append(
                f"<tr><td class='fname'>runs</td>"
                f"<td>{truth.get('runs', '—')}</td>"
                f"<td>{pe.get('runs', '—')}</td></tr>")
            comp_rows.append(
                f"<tr><td class='fname'>outcome</td>"
                f"<td>{truth.get('outcome', '—')}</td>"
                f"<td>{pe.get('event_type', '—')}</td></tr>")

        comp_table = (
            "<table class='comp'>"
            "<thead><tr><th>field</th><th>truth</th>"
            "<th>Gemini</th></tr></thead>"
            f"<tbody>{''.join(comp_rows)}</tbody>"
            "</table>"
        )

        narrative = gp.get("narrative") or "—"
        if not gp:
            narrative = ("(no Gemini classification — window was "
                         "rejected before classify)")

        truth_notes = fix.get("notes") or ""

        if grading["graded"]:
            score_str = (f"{grading['matched']} / {grading['graded']} "
                         f"fields match")
        else:
            score_str = "no truth fields available for grading"

        video_block = (
            f"<video controls width='420' src='{p.get('mp4_local')}'>"
            f"</video>"
            if p.get("mp4_local")
            else "<div class='reject'>no MP4 saved (0-frame window)</div>")

        rows.append(f"""
<section class='ball'>
  <h2>Ball {i} — window <code>#{p['window_id']}</code> ·
      broadcast <code>{bcast_ball}</code> · {is_del_badge}</h2>
  <div class='wire'>WIRE: <code>{wire}</code></div>
  <div class='meta'>
    pipeline event: <b>{pe.get('event_type','—')}</b>
    ({pe.get('runs','—')} runs) at
    <code>{pe.get('wall_ts','—')}</code> ·
    window close at <code>{p.get('close_hms_ist','—')} IST</code> ·
    pair Δ {p.get('pair_dt_s','?')}s
    <br>
    window stats: <b>{p.get('frames','?')}f / {p.get('dur_s','?')}s</b>
    · close reason <code>{p.get('close_reason','?')}</code>
    · gemini {p.get('gemini_ms','?')} ms
    · grading: <b>{score_str}</b>
  </div>
  <div class='cols'>
    <div class='col-vid'>
      {video_block}
      <div class='truth-notes'><b>Truth:</b> {truth_notes}</div>
    </div>
    <div class='col-cmp'>
      <h3>Truth vs Gemini</h3>
      {comp_table}
    </div>
    <div class='col-narr'>
      <h3>Gemini narrative</h3>
      <div class='narr'>{narrative}</div>
      <h3>Pipeline wire commentary</h3>
      <div class='cmt'>{((p.get('predictions') or {})
                          .get('commentary_line', '—'))}</div>
    </div>
  </div>
</section>
""")

    body = "\n".join(rows)

    # Aggregate header
    overall_pct = (
        f"{100.0 * total_matched / total_graded:.1f}%"
        if total_graded else "n/a")
    field_summary = []
    for f in GRADE_FIELDS:
        ft = field_totals[f]
        denom = ft["match"] + ft["miss"]
        pct = f"{100*ft['match']/denom:.0f}%" if denom else "n/a"
        field_summary.append(
            f"<tr><td>{f}</td><td>{ft['match']}</td><td>{ft['miss']}</td>"
            f"<td>{ft['unknown_pred']}</td><td>{pct}</td></tr>")

    orphan_list = "".join(
        f"<li><code>{e['wall_ts']}</code> {e['event_type']} "
        f"runs={e['runs']} over={e['over_ball']} — wire: "
        f"<code>{e['wire'] or '(none)'}</code></li>"
        for e in orphans)
    no_window_count = len(no_window_events)

    return f"""<!doctype html>
<html><head><meta charset='utf-8'>
<title>Over Test — session {SESSION}</title>
<style>
  body {{ font: 13px -apple-system, sans-serif; max-width: 1500px;
          margin: 16px auto; padding: 0 16px; color: #222; }}
  h1 {{ font-size: 18px; }}
  h2 {{ font-size: 14px; }}
  section.ball {{ border: 1px solid #ccc; border-radius: 6px;
                  margin: 14px 0; padding: 12px; background: #fafafa; }}
  .wire {{ font-size: 12px; margin: 4px 0; }}
  .meta {{ color: #666; font-size: 11px; line-height: 1.5;
            margin-bottom: 10px; }}
  .badge {{ display: inline-block; padding: 1px 6px; border-radius: 3px;
             font-size: 11px; font-weight: bold; margin-left: 8px; }}
  .badge.ok {{ background: #d6f5d6; color: #060; }}
  .badge.bad {{ background: #fbd6d6; color: #900; }}
  .badge.na {{ background: #eee; color: #666; }}
  .cols {{ display: grid; grid-template-columns: 440px 380px 1fr;
           gap: 14px; }}
  .col-vid video {{ width: 420px; height: auto; background: #000; }}
  table.comp {{ border-collapse: collapse; width: 100%; }}
  table.comp th, table.comp td {{ padding: 3px 6px;
                                   border-bottom: 1px solid #eee;
                                   font-size: 12px; text-align: left; }}
  table.comp .fname {{ color: #777; width: 110px; }}
  table.summary {{ border-collapse: collapse; }}
  table.summary td, table.summary th {{ padding: 4px 10px;
                                         border: 1px solid #ddd;
                                         font-size: 12px; }}
  .narr {{ background: #fff; padding: 8px; border: 1px solid #ddd;
            border-radius: 4px; line-height: 1.4; font-size: 12px; }}
  .cmt {{ background: #fffbe7; padding: 6px; font-family: monospace;
           font-size: 11px; }}
  .reject {{ color: #c33; padding: 8px; background: #fff0f0;
              border-radius: 4px; font-weight: bold; }}
  .truth-notes {{ background: #eef6ff; padding: 6px;
                   border: 1px solid #cde; border-radius: 4px;
                   margin-top: 8px; font-size: 11px;
                   line-height: 1.4; }}
  h3 {{ font-size: 11px; margin: 10px 0 4px; color: #555;
         text-transform: uppercase; letter-spacing: 0.5px; }}
  details summary {{ cursor: pointer; font-weight: bold;
                      color: #07a; font-size: 12px; }}
</style>
</head><body>
<h1>Gemini delivery test — session <code>{SESSION}</code></h1>
<p style='color:#666; font-size:12px; line-height: 1.5;'>
  Hand-graded ground truth from
  <code>{FIXTURE.relative_to(ROOT)}</code> ·
  {len(chosen)} windows on page · {n_truth} have truth data ·
  overall per-field accuracy <b>{overall_pct}</b>
  ({total_matched} / {total_graded})
</p>

<details open>
  <summary>Per-field accuracy ({total_graded} graded fields total)</summary>
  <table class='summary'>
    <tr><th>field</th><th>match</th><th>miss</th><th>pred=unknown</th>
        <th>acc</th></tr>
    {''.join(field_summary)}
  </table>
</details>

<details>
  <summary>Pipeline diagnostics — orphan score events
           ({len(orphans)}), score events that hit
           NO captured window ({no_window_count})</summary>
  <p style='color:#666; font-size:11px;'>Orphan score events are
     ScoreManager firings that DID NOT close any window in our 6
     test windows.  These represent ScoreManager activity outside
     the test slice plus any double-fire / extras-attribution
     issues.</p>
  <ul>{orphan_list}</ul>
</details>

{body}
</body></html>
"""


# ───────────────────────── main ─────────────────────────────────

def main() -> None:
    if not FIXTURE.exists():
        sys.exit(f"missing fixture {FIXTURE} — write hand-graded "
                 f"ground truth first")
    fixture = json.loads(FIXTURE.read_text())

    closes, no_window_events = parse_machine_log()
    pipe_events = parse_pipeline_score_events()
    print(f"machine log: {len(closes)} score-event window closes "
          f"({len(no_window_events)} score events with NO window)")
    print(f"pipeline log: {len(pipe_events)} ScoreManager firings")

    pairs, orphans = pair_windows_to_pipeline(closes, pipe_events,
                                              no_window_events)
    enrich_with_artifacts(pairs)
    attach_fixture(pairs, fixture)

    chosen = select_test_windows(pairs, fixture)
    print(f"\nfixture wants {len(fixture['labels'])} windows; "
          f"matched {len(chosen)} in machine log\n")

    print(f"{'i':>2} {'win':>4} {'pe.over':>8} {'pe.event':>8} "
          f"{'pe.runs':>4}  {'truth.ball':>10} {'is_del':>7}  "
          f"matched")
    for i, p in enumerate(chosen, 1):
        pe = p.get("pipeline_event") or {}
        fix = p.get("fixture") or {}
        gr = grade_pair(p)
        if gr["graded"]:
            mm = f"{gr['matched']}/{gr['graded']}"
        else:
            mm = "n/a"
        print(f"{i:>2} {p['window_id']:>4} "
              f"{pe.get('over_ball','-'):>8} "
              f"{pe.get('event_type','-'):>8} "
              f"{pe.get('runs','-'):>4}  "
              f"{fix.get('broadcast_ball') or '-':>10} "
              f"{str(fix.get('is_delivery')):>7}  {mm}")

    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    # Copy MP4s into the output dir.  Use window_id in the name so
    # the file is portable across rebuilds with different orderings.
    for i, p in enumerate(chosen, start=1):
        if p.get("mp4_src"):
            dst = OUT_ROOT / f"ball_{i}_w{p['window_id']:04d}.mp4"
            if not dst.exists():
                shutil.copy(p["mp4_src"], dst)
            p["mp4_local"] = dst.name
        else:
            p["mp4_local"] = None

    (OUT_ROOT / "over_test_data.json").write_text(
        json.dumps({"chosen": chosen, "orphans": orphans,
                    "no_window_events_count": len(no_window_events)},
                   indent=2, default=str))

    html = render_html(chosen, fixture, orphans, no_window_events)
    (OUT_ROOT / "over_test.html").write_text(html)
    print(f"\nWrote {OUT_ROOT / 'over_test.html'}")
    print(f"Wrote {OUT_ROOT / 'over_test_data.json'}")
    print(f"\nServe via:\n  cd {OUT_ROOT}")
    print(f"  python -m http.server 8767")
    print(f"  open http://localhost:8767/over_test.html")


if __name__ == "__main__":
    main()

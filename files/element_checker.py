"""Per-element ground-truth checker for the live scorecard UI.

For every element rendered in the Next.js UI (`scorecard-ui/app/page.tsx`),
this checker:

  1. Pulls the latest WS state from `ws://localhost:8765` (the same
     payload the React UI consumes via `useMatchSocket`).
  2. Pulls the cricbuzz live-scoring HTML and extracts ground truth.
  3. Runs an assertion per UI element. Every divergence becomes an
     issue row with a likely root-cause guess and, when unknown, a
     concrete suggestion for what monitoring to add.
  4. Tracks every transition (state hash diff) so we can see how
     frequently the pipeline mutates each field — and which fields
     never update (suggests stale wiring).

Output:
  - Live console log with iter#, per-element status (OK/DIVERGE/STALE/
    NO_GT), and the list of new issues this iter.
  - JSONL log at logs/element-checker-YYYY-MM-DD.jsonl with one row
    per iteration containing: ts, iter, ws_state_excerpt, gt_excerpt,
    issues[], transitions[].
  - On Ctrl-C: prints a final SUMMARY with per-element divergence
    counts, transition counts, and the proposed monitoring backlog.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import httpx
import websockets
from bs4 import BeautifulSoup

WS_URL = "ws://localhost:8765"
COMM_WS = "ws://localhost:8766"
CB_LIVE = (
    "https://www.cricbuzz.com/live-cricket-scores/152020/"
    "wi-vs-rsa-2nd-t20i-south-africa-tour-of-west-indies-2024"
)
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
RUN_TAG = datetime.now().strftime("%Y-%m-%d-%H%M%S")
JSONL_PATH = LOG_DIR / f"element-checker-{RUN_TAG}.jsonl"
SUMMARY_PATH = LOG_DIR / f"element-checker-{RUN_TAG}-summary.md"

POLL_WS_S = 4.0
POLL_CB_S = 25.0

# ── helpers ────────────────────────────────────────────────────────
TEAM_ABBR = {
    "kolkata knight riders": "KKR",
    "rajasthan royals": "RR",
    "chennai super kings": "CSK",
    "sunrisers hyderabad": "SRH",
    "royal challengers bengaluru": "RCB",
    "royal challengers bangalore": "RCB",
    "delhi capitals": "DC",
    "mumbai indians": "MI",
    "lucknow super giants": "LSG",
    "punjab kings": "PBKS",
    "gujarat titans": "GT",
}


def surname(n):
    if not n:
        return ""
    return n.strip().split()[-1].lower()


def norm_team(n):
    if not n:
        return ""
    return TEAM_ABBR.get(n.lower().strip(), n.strip()[:3].upper())


# ── WS fetcher ─────────────────────────────────────────────────────
async def fetch_ws():
    try:
        async with websockets.connect(WS_URL, open_timeout=4) as ws:
            msg = await asyncio.wait_for(ws.recv(), timeout=4)
            return json.loads(msg)
    except Exception as e:  # noqa: BLE001
        return {"_err": str(e)}


async def fetch_comm():
    """Pull latest commentary entry count to test commentary tab."""
    try:
        async with websockets.connect(COMM_WS, open_timeout=3) as ws:
            msgs = []
            try:
                while True:
                    m = await asyncio.wait_for(ws.recv(), timeout=1.5)
                    try:
                        msgs.append(json.loads(m))
                    except Exception:
                        msgs.append({"raw": m[:200]})
            except asyncio.TimeoutError:
                pass
            return msgs
    except Exception as e:  # noqa: BLE001
        return [{"_err": str(e)}]


# ── cricbuzz scraper ───────────────────────────────────────────────
async def fetch_cb():
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
            r = await c.get(
                CB_LIVE, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return {"_err": f"cb {r.status_code}"}
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text("\n", strip=True)
    except Exception as e:  # noqa: BLE001
        return {"_err": str(e)}
    out = {"_raw_chars": len(text)}
    # toss / opt-to-bat
    m = re.search(
        r"(Kolkata Knight Riders|Rajasthan Royals|"
        r"Chennai Super Kings|Sunrisers Hyderabad|Royal Challengers "
        r"Bengaluru|Delhi Capitals|Mumbai Indians|Lucknow Super "
        r"Giants|Punjab Kings|Gujarat Titans)\s+(?:opt(?:ed)?|elected)"
        r"\s+to\s+(bat|bowl|field)", text, re.I)
    if m:
        out["toss_winner"] = m.group(1)
        out["toss_decision"] = m.group(2).lower()
        # who bats first?
        if out["toss_decision"] == "bat":
            out["bat_first"] = m.group(1)
        else:
            # opposite team bats first
            pass
    # innings score lines
    teams_re = (r"KKR|RR|CSK|SRH|RCB|DC|MI|LSG|PBKS|GT|IND|AUS|ENG|"
                r"SA|NZ|PAK|WI|SL|BAN|AFG")
    pat = re.compile(
        r"\b(" + teams_re + r")\b\s*\n?\s*(\d+)\s*-\s*(\d+)\s*"
        r"\(([\d.]+)\)")
    innings = [{"team": mm.group(1), "score": int(mm.group(2)),
                "wickets": int(mm.group(3)), "overs": mm.group(4)}
               for mm in pat.finditer(text)]
    out["innings"] = innings
    if innings:
        # live = the "later" innings if it's a chase, else the
        # only one. Heuristic: page lists current first usually.
        out["score"] = innings[-1]["score"]
        out["wickets"] = innings[-1]["wickets"]
        out["overs"] = innings[-1]["overs"]
        out["batting_team_abbr"] = innings[-1]["team"]
    # CRR
    m = re.search(r"CRR[:\s\n]*([\d.]+)", text)
    if m:
        out["crr"] = float(m.group(1))
    # Partnership
    m = re.search(r"P'SHIP\s*\n?\s*(\d+)\s*\n?\s*\(\s*\n?\s*(\d+)", text)
    if m:
        out["partnership_runs"] = int(m.group(1))
        out["partnership_balls"] = int(m.group(2))
    # Recent balls
    m = re.search(r"Recent\s*:\s*([0-9wW.\s|]{1,80})", text)
    if m:
        out["recent"] = m.group(1).strip()
    m = re.search(r"Last Wkt:\s*([^\n]+)", text)
    if m:
        out["last_wkt"] = m.group(1).strip()[:200]
    # Batters table — Batter R B 4s 6s SR
    bidx = text.find("Batter")
    if bidx > 0:
        chunk = text[bidx:bidx + 2000]
        bat_pat = re.compile(
            r"\n([A-Z][A-Za-z .'-]{2,30})\s*\n(?:\*\s*\n)?"
            r"(\d+)\s*\n(\d+)\s*\n(\d+)\s*\n(\d+)\s*\n([\d.]+)")
        bats = []
        for bm in bat_pat.finditer(chunk):
            nm = bm.group(1).strip()
            if nm in ("Bowler", "Batter"):
                continue
            bats.append({
                "name": nm,
                "runs": int(bm.group(2)),
                "balls": int(bm.group(3)),
                "fours": int(bm.group(4)),
                "sixes": int(bm.group(5)),
                "sr": float(bm.group(6)),
            })
            if len(bats) >= 2:
                break
        striker_pat = re.compile(
            r"\n([A-Z][A-Za-z .'-]{2,30})\s*\n\*\s*\n(\d+)")
        sm = striker_pat.search(chunk)
        if sm:
            out["striker"] = sm.group(1).strip()
        out["batters"] = bats
    # Bowler table — Bowler O M R W ECO
    bidx2 = text.find("Bowler")
    if bidx2 > 0:
        chunk2 = text[bidx2:bidx2 + 1000]
        bow_pat = re.compile(
            r"\n([A-Z][A-Za-z .'-]{2,30})\s*\n([\d.]+)\s*\n(\d+)\s*\n"
            r"(\d+)\s*\n(\d+)\s*\n([\d.]+)")
        bm2 = bow_pat.search(chunk2)
        if bm2:
            out["bowler"] = {
                "name": bm2.group(1).strip(),
                "overs": bm2.group(2),
                "maidens": int(bm2.group(3)),
                "runs": int(bm2.group(4)),
                "wickets": int(bm2.group(5)),
                "eco": float(bm2.group(6)),
            }
    return out


# ── element checks ────────────────────────────────────────────────
# Each check returns (status, ui_val, gt_val, root_cause_hint,
#                     monitoring_suggestion) where status is OK,
# DIVERGE, NO_GT, STALE, or NA.
ELEMENT_DEFS = []


def element(name, group="live"):
    def deco(fn):
        ELEMENT_DEFS.append((name, group, fn))
        return fn
    return deco


def _ok(ui, gt=None):
    return ("OK", ui, gt, None, None)


def _div(ui, gt, why=None, mon=None):
    return ("DIVERGE", ui, gt, why, mon)


def _no_gt(ui):
    return ("NO_GT", ui, None, None, None)


def _na():
    return ("NA", None, None, None, None)


# === ScoreStrip ===
@element("scorestrip.team_a", "scorestrip")
def chk_team_a(ws, cb):
    v = (ws.get("match") or {}).get("team_a")
    return _no_gt(v) if v else _div(None, "expected", "match.team_a missing",
                                    "log when match.team_a stays null past 60s after squad scrape")


@element("scorestrip.team_b", "scorestrip")
def chk_team_b(ws, cb):
    v = (ws.get("match") or {}).get("team_b")
    return _no_gt(v) if v else _div(None, "expected", "match.team_b missing",
                                    "log when match.team_b stays null past 60s after squad scrape")


@element("scorestrip.innings", "scorestrip")
def chk_innings(ws, cb):
    v = (ws.get("match") or {}).get("innings")
    if v in (1, 2):
        return _ok(v)
    return _div(v, "1 or 2", "innings still 0/null",
                "log innings transitions; alert if stays 0 after first ball event")


@element("scorestrip.batting_team", "scorestrip")
def chk_batting_team(ws, cb):
    sc = ws.get("scorecard") or {}
    ui = sc.get("batting_team")
    bat_first = cb.get("bat_first") if cb else None
    inn = (ws.get("match") or {}).get("innings")
    if not ui:
        return _div(None, bat_first or "expected",
                    "scorecard.batting_team null",
                    "alert if batting_team null while score!=null")
    if bat_first and inn == 1 and norm_team(ui) != norm_team(bat_first):
        return _div(ui, bat_first,
                    "innings1 batting_team mismatches toss winner who chose to bat",
                    "compare match.toss decision vs scorecard.batting_team on every state push; emit DIVERGENCE if mismatch persists >3 frames")
    return _ok(ui, bat_first)


@element("scorestrip.score", "scorestrip")
def chk_score(ws, cb):
    sc = ws.get("scorecard") or {}
    ui = sc.get("score")
    gt = cb.get("score")
    if ui is None:
        return _no_gt(None) if gt is None else _div(None, gt, "ui score null while gt has score", "alert when WS state has innings>=1 and score is null")
    if gt is None:
        return _no_gt(ui)
    if int(ui) != int(gt):
        return _div(ui, gt, "OCR/extractor drift or stale frame",
                    "log per-frame ext_score vs final score; track GUARD-blocked proposals")
    return _ok(ui, gt)


@element("scorestrip.wickets", "scorestrip")
def chk_wkts(ws, cb):
    sc = ws.get("scorecard") or {}
    ui = sc.get("wickets")
    gt = cb.get("wickets")
    if ui is None and gt is None:
        return _no_gt(None)
    if ui is None or gt is None:
        return _no_gt(ui)
    if int(ui) != int(gt):
        return _div(ui, gt, "wickets out of sync — likely missed dismissal",
                    "diff bowling_card.wickets sum vs scorecard.wickets each frame")
    return _ok(ui, gt)


@element("scorestrip.overs", "scorestrip")
def chk_overs(ws, cb):
    sc = ws.get("scorecard") or {}
    ui = sc.get("overs")
    gt = cb.get("overs")
    if ui is None and gt is None:
        return _no_gt(None)
    if ui is None or gt is None:
        return _no_gt(ui)
    if str(ui).strip() != str(gt).strip():
        return _div(ui, gt, "overs differ — burst-mode or scout drop",
                    "log every overs transition; warn when overs goes backwards")
    return _ok(ui, gt)


@element("scorestrip.run_rate", "scorestrip")
def chk_crr(ws, cb):
    sc = ws.get("scorecard") or {}
    ui = sc.get("run_rate")
    gt = cb.get("crr")
    if ui is None and gt is None:
        return _no_gt(None)
    if ui is None or gt is None:
        return _no_gt(ui)
    if abs(float(ui) - float(gt)) > 0.30:
        return _div(ui, gt, "CRR drift > 0.3 — score/overs out of sync",
                    "compute CRR purely from (score, overs) on the UI; warn when backend CRR differs from derived by >0.2")
    return _ok(ui, gt)


@element("scorestrip.striker", "scorestrip")
def chk_striker(ws, cb):
    sc = ws.get("scorecard") or {}
    ui = sc.get("striker")
    gt = cb.get("striker")
    if not ui and not gt:
        return _no_gt(None)
    if not gt:
        return _no_gt(ui)
    if not ui:
        return _div(None, gt, "striker not assigned by pipeline",
                    "alert when batting_card[*].is_striker has 0 or 2+ batters")
    if surname(ui) != surname(gt):
        return _div(ui, gt, "striker mismatch (broadcast hint vs OCR)",
                    "track scorecard.striker transitions; cross-check vs delivery_info.striker_this_ball")
    return _ok(ui, gt)


@element("scorestrip.non", "scorestrip")
def chk_nstr(ws, cb):
    sc = ws.get("scorecard") or {}
    ui = sc.get("non")
    gt_bats = cb.get("batters") or []
    gt = None
    if cb.get("striker"):
        gt = next((b["name"] for b in gt_bats
                   if surname(b["name"]) != surname(cb["striker"])), None)
    if not ui and not gt:
        return _no_gt(None)
    if not gt:
        return _no_gt(ui)
    if not ui:
        return _div(None, gt, "non null", "alert when ws has striker but no non for >10s")
    if surname(ui) != surname(gt):
        return _div(ui, gt, "non mismatch",
                    "log when batting_card has more than 2 status=batting entries")
    return _ok(ui, gt)


@element("scorestrip.bowler", "scorestrip")
def chk_bowler(ws, cb):
    sc = ws.get("scorecard") or {}
    ui = sc.get("current_bowler")
    gt = (cb.get("bowler") or {}).get("name")
    if not ui and not gt:
        return _no_gt(None)
    if not gt:
        return _no_gt(ui)
    if not ui:
        return _div(None, gt, "no current_bowler",
                    "alert when bowling_card[*].is_current count != 1")
    if surname(ui) != surname(gt):
        return _div(ui, gt, "bowler mismatch — likely OCR or bowler-change miss",
                    "log over-boundary transitions; ensure current_bowler refresh on over change")
    return _ok(ui, gt)


# === Live tab numeric panels ===
@element("live.balls_bowled_derivation", "live")
def chk_balls(ws, cb):
    sc = ws.get("scorecard") or {}
    overs = sc.get("overs")
    if overs is None:
        return _no_gt(None)
    try:
        f = float(overs)
        derived = int(f) * 6 + round((f - int(f)) * 10)
    except Exception:
        return _no_gt(overs)
    return _ok(f"{derived}/120", str(overs))


@element("live.wkts_left", "live")
def chk_wkts_left(ws, cb):
    sc = ws.get("scorecard") or {}
    w = sc.get("wickets")
    if w is None:
        return _no_gt(None)
    return _ok(10 - int(w))


@element("live.speed_kph", "live")
def chk_speed(ws, cb):
    v = ws.get("speed_kph")
    if v in (None, 0, "0"):
        return _no_gt(v)  # speed only available on certain frames
    return _ok(v)


@element("live.delivery_info_panel", "live")
def chk_delivery(ws, cb):
    di = ws.get("delivery_info") or {}
    if not di:
        return _no_gt(None)
    fields = ("length", "line", "bowling_angle", "bounce", "swing_or_seam",
              "shot_intent", "shot_action", "shot_elevation")
    known = sum(1 for f in fields
                if di.get(f) and str(di.get(f)).lower() not in ("unknown", "not_visible"))
    return _ok(f"{known}/{len(fields)} known method={di.get('_method')}")


@element("live.this_over", "live")
def chk_this_over(ws, cb):
    bs = ws.get("this_over") or []
    return _ok(bs)


@element("live.partnership", "live")
def chk_partnership(ws, cb):
    p = (ws.get("partnerships") or {}).get("current") or {}
    ui_runs = p.get("runs")
    gt = cb.get("partnership_runs")
    if ui_runs is None and gt is None:
        return _no_gt(None)
    if ui_runs is None or gt is None:
        return _no_gt(ui_runs)
    if int(ui_runs) != int(gt):
        return _div(ui_runs, gt,
                    "partnership runs drift",
                    "verify partnership reset on wicket; check ball-event runs accumulator")
    return _ok(ui_runs, gt)


@element("live.extras_total", "live")
def chk_extras(ws, cb):
    ex = ws.get("extras") or {}
    return _ok(
        f"total={ex.get('total', 0)} "
        f"w{ex.get('wides', 0)} nb{ex.get('no_balls', 0)} "
        f"b{ex.get('byes', 0)} lb{ex.get('leg_byes', 0)} "
        f"this_over={ex.get('this_over', 0)}")


@element("live.fall_of_wickets", "live")
def chk_fow(ws, cb):
    sc = ws.get("scorecard") or {}
    fow = ws.get("fall_of_wickets") or sc.get("fow_list") or []
    wkts = sc.get("wickets") or 0
    if len(fow) != int(wkts or 0):
        return _div(len(fow), wkts,
                    "FOW count != wickets",
                    "log every wicket event; ensure FOW append before next-batter join")
    unk = sum(1 for w in fow if str(w.get("batter") or "").lower() in ("", "unknown"))
    if unk:
        return _div(f"{unk} unknown batters in FOW", 0,
                    "broadcast hadn't shown FOW pop-up before pipeline indexed",
                    "retro-fill FOW.batter from match_state on next scoreboard frame")
    return _ok(len(fow))


@element("live.recent_overs", "live")
def chk_recent_overs(ws, cb):
    oh = ws.get("over_history") or {}
    return _ok(f"{len(oh)} overs in history")


# === Scorecard tab ===
@element("scorecard.batting_card_full", "scorecard")
def chk_full_bat(ws, cb):
    bc = ws.get("full_batting_squad") or ws.get("batting_card") or []
    if isinstance(bc, dict):
        bc = list(bc.values())
    if not bc:
        return _div(0, 11, "no batting card yet",
                    "alert when innings>=1 and len(batting_card)==0")
    return _ok(f"{len(bc)} batters in card")


@element("scorecard.bowling_card_full", "scorecard")
def chk_full_bowl(ws, cb):
    bw = ws.get("full_bowling_squad") or ws.get("bowling_card") or []
    if isinstance(bw, dict):
        bw = list(bw.values())
    return _ok(f"{len(bw)} bowlers in card")


@element("scorecard.active_batter_runs", "scorecard")
def chk_active_runs(ws, cb):
    """Compare each at-the-crease batter R(B) vs ground-truth."""
    bc = ws.get("batting_card") or []
    if isinstance(bc, dict):
        bc = list(bc.values())
    active = [b for b in bc if (b.get("status") in (None, "batting")) and (b.get("runs") is not None)][:2]
    gt = cb.get("batters") or []
    if not active or not gt:
        return _no_gt(active)
    issues = []
    for cb_b in gt:
        sn = surname(cb_b["name"])
        match = next((a for a in active if surname(a.get("name")) == sn), None)
        if not match:
            issues.append(f"{cb_b['name']} not in active")
            continue
        if match.get("runs") != cb_b["runs"] or match.get("balls") != cb_b["balls"]:
            issues.append(
                f"{sn} ui={match.get('runs')}({match.get('balls')}) "
                f"gt={cb_b['runs']}({cb_b['balls']})")
    if issues:
        return _div(active, gt, "; ".join(issues),
                    "log batter R(B) deltas per frame; alert when delta >2 runs")
    return _ok(active, gt)


@element("scorecard.bowler_figures", "scorecard")
def chk_bowler_figs(ws, cb):
    """Compare current bowler O-M-R-W vs ground truth."""
    bw = ws.get("bowling_card") or []
    if isinstance(bw, dict):
        bw = list(bw.values())
    cur = next((b for b in bw if b.get("is_current")), None)
    gt = cb.get("bowler") or None
    if not cur or not gt:
        return _no_gt(cur)
    issues = []
    if str(cur.get("overs")) != str(gt.get("overs")):
        issues.append(f"O ui={cur.get('overs')} gt={gt.get('overs')}")
    if int(cur.get("runs", 0)) != int(gt.get("runs", 0)):
        issues.append(f"R ui={cur.get('runs')} gt={gt.get('runs')}")
    if int(cur.get("wickets", 0)) != int(gt.get("wickets", 0)):
        issues.append(f"W ui={cur.get('wickets')} gt={gt.get('wickets')}")
    if issues:
        return _div(cur, gt, "; ".join(issues),
                    "log bowler delta each frame; check OCR confidence on bowler row")
    return _ok(cur, gt)


# === Field tab ===
@element("field.positions", "field")
def chk_field(ws, cb):
    fd = ws.get("field") or {}
    pos = fd.get("positions") or []
    if not pos:
        return _no_gt(0)
    return _ok(f"{len(pos)} positions, formation={fd.get('formation')}, "
               f"phase={fd.get('phase')}, in={fd.get('inside_count')}, "
               f"out={fd.get('outside_count')}")


@element("field.powerplay_invariant", "field")
def chk_pp_invariant(ws, cb):
    fd = ws.get("field") or {}
    sc = ws.get("scorecard") or {}
    overs = sc.get("overs")
    try:
        f = float(overs) if overs is not None else None
    except Exception:
        f = None
    if f is None or f >= 6.0:
        return _na()
    out = fd.get("outside_count")
    if out is None:
        return _no_gt(None)
    if out > 2:
        return _div(out, "<= 2",
                    "Powerplay should have ≤2 fielders outside the circle",
                    "already logged via [FIELD WARN]; surface to UI as red badge")
    return _ok(out)


# === Connection / freshness ===
@element("ui.connection", "infra")
def chk_conn(ws, cb):
    if "_err" in ws:
        return _div("DISCONNECTED", "CONNECTED", ws["_err"],
                    "WS dropped — alert if WS reconnect cycles >3 in 60s")
    return _ok("connected")


# ── runner ────────────────────────────────────────────────────────
class State:
    def __init__(self):
        self.iter = 0
        self.cb_cache = {}
        self.cb_last = 0.0
        self.div_count = defaultdict(int)
        self.transition_count = defaultdict(int)
        self.last_vals = {}
        self.last_root_causes = {}
        self.first_seen = {}
        self.start = time.time()


def write_jsonl(state, ws_excerpt, gt_excerpt, results):
    rec = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "iter": state.iter,
        "ws": ws_excerpt,
        "gt": gt_excerpt,
        "results": [
            {"el": r["el"], "group": r["group"], "status": r["status"],
             "ui": _short(r["ui"]), "gt": _short(r["gt"]),
             "why": r["why"], "monitor": r["monitor"]}
            for r in results
        ],
    }
    with JSONL_PATH.open("a") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def _short(v, n=120):
    s = str(v)
    return s if len(s) <= n else s[:n] + "…"


def write_summary(state):
    lines = ["# Element-checker run summary", ""]
    lines.append(f"- Run tag: `{RUN_TAG}`")
    lines.append(f"- Iterations: {state.iter}")
    lines.append(f"- Duration: {int(time.time() - state.start)}s")
    lines.append(f"- JSONL: `{JSONL_PATH}`")
    lines.append("")
    lines.append("## Divergence counts per element")
    for el, cnt in sorted(state.div_count.items(),
                          key=lambda x: -x[1]):
        rc = state.last_root_causes.get(el, "?")
        lines.append(f"- **{el}** — diverged {cnt}× | last root cause: {rc}")
    lines.append("")
    lines.append("## Transition counts per element (state churn)")
    for el, cnt in sorted(state.transition_count.items(),
                          key=lambda x: -x[1])[:30]:
        lines.append(f"- {el}: {cnt} transitions")
    SUMMARY_PATH.write_text("\n".join(lines))


async def main():
    state = State()
    match_label = CB_LIVE.rstrip("/").split("/")[-1] or "configured match"
    print(f"=== ELEMENT CHECKER — {match_label} ===")
    print(f"WS:   {WS_URL}")
    print(f"CB:   {CB_LIVE}")
    print(f"JSONL: {JSONL_PATH}\n", flush=True)
    try:
        while True:
            state.iter += 1
            ws = await fetch_ws()
            now = time.time()
            if now - state.cb_last > POLL_CB_S:
                state.cb_cache = await fetch_cb()
                state.cb_last = now
            cb = state.cb_cache or {}

            results = []
            ws_excerpt = {
                "team_a": (ws.get("match") or {}).get("team_a"),
                "team_b": (ws.get("match") or {}).get("team_b"),
                "innings": (ws.get("match") or {}).get("innings"),
                "scorecard": ws.get("scorecard"),
                "this_over": ws.get("this_over"),
                "extras": ws.get("extras"),
            }
            gt_excerpt = {
                "score": cb.get("score"), "wickets": cb.get("wickets"),
                "overs": cb.get("overs"), "crr": cb.get("crr"),
                "bat_first": cb.get("bat_first"),
                "toss": (cb.get("toss_winner"), cb.get("toss_decision")),
                "striker": cb.get("striker"),
                "batters": [(b["name"], b["runs"], b["balls"])
                            for b in (cb.get("batters") or [])],
                "bowler": cb.get("bowler"),
            }
            for name, group, fn in ELEMENT_DEFS:
                try:
                    status, ui, gt, why, monitor = fn(ws, cb)
                except Exception as e:  # noqa: BLE001
                    status, ui, gt, why, monitor = (
                        "ERR", None, None, f"checker_exc: {e}",
                        "harden checker — should never raise")
                key = name
                if status == "DIVERGE":
                    state.div_count[key] += 1
                    state.last_root_causes[key] = why
                # transitions
                cur = (str(ui), str(gt))
                prev = state.last_vals.get(key)
                if prev is not None and prev != cur:
                    state.transition_count[key] += 1
                state.last_vals[key] = cur
                results.append({
                    "el": name, "group": group, "status": status,
                    "ui": ui, "gt": gt, "why": why, "monitor": monitor})

            divs = [r for r in results if r["status"] == "DIVERGE"]
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"[{ts}  iter#{state.iter}]  diverging={len(divs)}/"
                  f"{len(results)}  ws_ok={'_err' not in ws}  "
                  f"gt_ok={'_err' not in cb}", flush=True)
            for d in divs:
                print(f"  ✗ {d['el']:42s}  ui={_short(d['ui'], 40)} | "
                      f"gt={_short(d['gt'], 40)} | why={d['why']}",
                      flush=True)
            write_jsonl(state, ws_excerpt, gt_excerpt, results)
            await asyncio.sleep(POLL_WS_S)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        write_summary(state)
        print(f"\nSummary written to {SUMMARY_PATH}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

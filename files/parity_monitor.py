"""Live parity monitor: pipeline UI WS state vs Cricbuzz ground truth.

Run alongside the pipeline. Polls every ~20s, prints divergences.
Usage: .venv/bin/python parity_monitor.py
"""
from __future__ import annotations

import asyncio
import json
import re
import time

import httpx
import websockets
from bs4 import BeautifulSoup

WS_URL = "ws://localhost:8765"
CB_URL = (
    "https://www.cricbuzz.com/api/cricket-match/commentary/152031"
)
CB_FALLBACK = (
    "https://www.cricbuzz.com/live-cricket-scores/152031/"
    "dc-vs-csk-48th-match-indian-premier-league-2026"
)


async def fetch_ws_state() -> dict | None:
    try:
        async with websockets.connect(WS_URL, open_timeout=4) as ws:
            msg = await asyncio.wait_for(ws.recv(), timeout=4)
            return json.loads(msg)
    except Exception as e:  # noqa: BLE001
        return {"_err": str(e)}


def parse_ws(d: dict) -> dict:
    sc = d.get("scorecard", {}) or {}
    bc = d.get("batting_card", []) or []
    bw = d.get("bowling_card", []) or []
    if isinstance(bc, dict):
        bc = [{"name": n, **(c or {})} for n, c in bc.items()]
    if isinstance(bw, dict):
        bw = [{"name": n, **(c or {})} for n, c in bw.items()]
    fow = d.get("fall_of_wickets") or sc.get("fow_list") or []
    extras = d.get("extras") or {}
    bowler = None
    cur_bowler = sc.get("current_bowler")
    if cur_bowler:
        for b in bw:
            if b.get("name") == cur_bowler:
                bowler = b
                break
    if bowler is None:
        for b in bw:
            if b.get("is_current"):
                bowler = b
                break
    if bowler is None and bw:
        bowler = bw[-1]
    active = [
        b for b in bc
        if b.get("status") in (None, "active", "not_out", "batting")
        and (b.get("balls") is not None or b.get("runs") is not None
             or b.get("name") == sc.get("striker")
             or b.get("name") == sc.get("non"))
    ][:2]
    di = d.get("delivery_info") or {}
    return {
        "team": sc.get("batting_team"),
        "score": sc.get("score"),
        "wickets": sc.get("wickets"),
        "overs": sc.get("overs"),
        "striker": sc.get("striker"),
        "non": sc.get("non"),
        "this_over": d.get("this_over"),
        "fow_count": len(fow),
        "fow_all": fow,
        "fow_last": fow[-1] if fow else None,
        "fow_unknown": sum(
            1 for w in fow if str(w.get("batter") or "").lower()
            in ("", "unknown")),
        "delivery_info": ({
            "length": di.get("length"),
            "line": di.get("line"),
            "shot_type": di.get("shot_type"),
            "method": di.get("_method"),
        } if di else None),
        "bowler": (bowler or {}).get("name") if bowler else None,
        "bowler_w": (bowler or {}).get("wickets") if bowler else None,
        "bowler_r": (bowler or {}).get("runs") if bowler else None,
        "bowler_o": (bowler or {}).get("overs") if bowler else None,
        "active_batters": [
            {"name": b.get("name"), "runs": b.get("runs"),
             "balls": b.get("balls"), "status": b.get("status")}
            for b in active
        ],
        # `extras` shape (from scoreboard.extras):
        #   {wides, no_balls, byes, leg_byes, penalties, total,
        #    this_over, log: [...]}
        "extras_innings": extras.get("total"),
        "extras_this_over": extras.get("this_over"),
        "extras_breakdown": (
            f"w{extras.get('wides',0)}/"
            f"nb{extras.get('no_balls',0)}/"
            f"b{extras.get('byes',0)}/"
            f"lb{extras.get('leg_byes',0)}"
            if extras else None
        ),
        "extras_log_tail": (extras.get("log") or [])[-3:],
    }


async def fetch_cb(prefer_team: str | None = None) -> dict | None:
    # Mirror the error convention used by fetch_ws_state: ALL failures
    # (HTTP errors, network/DNS errors, parse crashes) return
    # {"_err": ...} so the monitor loop in main() logs-and-continues
    # instead of dying. Prior version only caught status != 200; a
    # transient httpx.ConnectError escaped all the way up and killed
    # the process (observed during the MI-vs-CSK run — see
    # logs/runs/parity_mi_csk_195111.log, exited at iter~N with
    # `httpx.ConnectError: All connection attempts failed`).
    try:
        async with httpx.AsyncClient(
                timeout=8, follow_redirects=True) as c:
            r = await c.get(CB_FALLBACK,
                            headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                return {"_err": f"cb {r.status_code}"}
            soup = BeautifulSoup(r.text, "html.parser")
            text = soup.get_text("\n", strip=True)
    except Exception as e:  # noqa: BLE001
        return {"_err": f"cb fetch: {type(e).__name__}: {e}"}
    out: dict = {}
    # Match: TEAM (newline) SCORE-WKTS(OVERS) — cricbuzz can split on
    # newlines or keep all on one line. Find ALL matches across both
    # innings and pick the LIVE one.
    _TEAMS = (
        r"KKR|GT|RCB|DC|MI|CSK|SRH|RR|LSG|PBKS|"
        r"IND|AUS|ENG|SA|NZ|PAK|WI|SL|BAN|AFG|ZIM|IRE|NED")
    pat_split = re.compile(
        r"\b(" + _TEAMS + r")\b\s*\n\s*(\d+)\s*\n?\s*-\s*\n?\s*(\d+)\s*"
        r"\n?\s*\(\s*\n?\s*([\d.]+)\s*\n?\s*\)")
    pat_inline = re.compile(
        r"\b(" + _TEAMS + r")\b\s*\n?\s*(\d+)\s*-\s*(\d+)\s*"
        r"\(([\d.]+)\)")
    matches = list(pat_split.finditer(text))
    if not matches:
        matches = list(pat_inline.finditer(text))
    # Pick the LIVE innings. Heuristics in priority:
    #   1. If `prefer_team` (the team our pipeline says is batting)
    #      matches a candidate, use that one.
    #   2. Else if "REQ:" / "need X runs" / "Required" appears in
    #      the page text, the LATER team-score block in the doc is
    #      the chasing/live innings — use the last match.
    #   3. Else use the first match (single-innings page).
    chosen = None
    # Map WS-format team names ("Chennai Super Kings") to the
    # cricbuzz abbreviations used in the page ("CSK"). Add new
    # entries here if a future broadcast surfaces a team not below.
    _ABBR_MAP = {
        "chennai super kings": "CSK",
        "sunrisers hyderabad": "SRH",
        "royal challengers bengaluru": "RCB",
        "royal challengers bangalore": "RCB",
        "delhi capitals": "DC",
        "mumbai indians": "MI",
        "kolkata knight riders": "KKR",
        "rajasthan royals": "RR",
        "lucknow super giants": "LSG",
        "punjab kings": "PBKS",
        "gujarat titans": "GT",
    }
    if matches and prefer_team:
        _key = prefer_team.lower().strip()
        _abbr = _ABBR_MAP.get(_key, prefer_team.upper()[:3])
        for m in matches:
            if m.group(1).upper() == _abbr.upper():
                chosen = m
                break
    if chosen is None and matches:
        is_chase = bool(re.search(
            r"\bREQ\b|\bRequired\b|need[s]?\s+\d+\s+run",
            text, flags=re.I))
        chosen = matches[-1] if is_chase else matches[0]
    if chosen:
        out["team"] = chosen.group(1)
        out["score"] = int(chosen.group(2))
        out["wickets"] = int(chosen.group(3))
        out["overs"] = chosen.group(4)
        out["all_innings"] = [
            {"team": m.group(1), "score": int(m.group(2)),
             "wickets": int(m.group(3)), "overs": m.group(4)}
            for m in matches
        ]
    m2 = re.search(r"CRR[:\s\n]*([\d.]+)", text)
    if m2:
        out["crr"] = float(m2.group(1))
    m3 = re.search(r"P'SHIP\s*\n?\s*(\d+)\s*\n?\s*\(\s*\n?\s*(\d+)", text)
    if m3:
        out["partnership"] = f"{m3.group(1)}({m3.group(2)})"
    m4 = re.search(r"Recent\s*:\s*([0-9wW.\s]{1,40})", text)
    if m4:
        out["recent"] = m4.group(1).strip()
    m5 = re.search(r"Last Wkt:\s*([^\n]+)", text)
    if m5:
        out["last_wkt"] = m5.group(1).strip()[:200]
    # Active batters: parse the table rows under "Batter R B 4s 6s SR"
    bidx = text.find("Batter")
    if bidx > 0:
        chunk = text[bidx:bidx + 1500]
        # Each batter line: NAME [*] R B 4s 6s SR (each on its own line)
        # Pattern: NAME\n[*\n]?R\nB\n4s\n6s\nSR (where R/B/4s/6s/SR are ints/floats)
        b_pat = re.compile(
            r"\n([A-Z][A-Za-z .'-]{2,30})\s*\n(?:\*\s*\n)?"
            r"(\d+)\s*\n(\d+)\s*\n(\d+)\s*\n(\d+)\s*\n([\d.]+)")
        bats = []
        for bm in b_pat.finditer(chunk):
            name = bm.group(1).strip()
            if name in ("Bowler", "Batter"):
                continue
            bats.append({
                "name": name,
                "runs": int(bm.group(2)),
                "balls": int(bm.group(3)),
                "fours": int(bm.group(4)),
                "sixes": int(bm.group(5)),
            })
            if len(bats) >= 2:
                break
        # Detect striker via the lone "*" line right after the name
        # (already handled implicitly in pattern? — re-scan strict)
        striker_pat = re.compile(
            r"\n([A-Z][A-Za-z .'-]{2,30})\s*\n\*\s*\n(\d+)")
        sm = striker_pat.search(chunk)
        if sm:
            out["striker"] = sm.group(1).strip()
        out["batters"] = bats
    # Bowler: under "Bowler O M R W ECO"
    bidx2 = text.find("Bowler")
    if bidx2 > 0:
        chunk2 = text[bidx2:bidx2 + 800]
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


def _surname(n: str | None) -> str:
    if not n:
        return ""
    return n.strip().split()[-1].lower()


def diff(ws: dict, cb: dict) -> list[str]:
    issues = []
    if ws.get("score") is not None and cb.get("score") is not None:
        if ws["score"] != cb["score"]:
            issues.append(
                f"SCORE: ui={ws['score']} cb={cb['score']}")
    if ws.get("wickets") is not None and cb.get("wickets") is not None:
        if ws["wickets"] != cb["wickets"]:
            issues.append(
                f"WICKETS: ui={ws['wickets']} cb={cb['wickets']}")
    if ws.get("overs") is not None and cb.get("overs") is not None:
        if str(ws["overs"]).strip() != str(cb["overs"]).strip():
            issues.append(
                f"OVERS: ui={ws['overs']} cb={cb['overs']}")
    # Striker (compare surname)
    if cb.get("striker"):
        ui_str = _surname(ws.get("striker"))
        cb_str = _surname(cb.get("striker"))
        if ui_str and cb_str and ui_str != cb_str:
            issues.append(
                f"STRIKER: ui={ws.get('striker')} cb={cb.get('striker')}")
    # Both batters present?
    if cb.get("batters"):
        cb_names = {_surname(b["name"]) for b in cb["batters"]}
        ui_names = {_surname(ws.get("striker")),
                    _surname(ws.get("non"))} - {""}
        missing = cb_names - ui_names
        if missing:
            issues.append(
                f"BATTERS_MISSING_IN_UI: {missing} "
                f"(ui={ui_names}, cb={cb_names})")
        # Compare runs/balls per batter
        for cb_b in cb["batters"]:
            sn = _surname(cb_b["name"])
            for ab in (ws.get("active_batters") or []):
                if _surname(ab.get("name")) == sn:
                    if ab.get("runs") != cb_b["runs"] or \
                       ab.get("balls") != cb_b["balls"]:
                        issues.append(
                            f"BAT_{sn}: ui={ab.get('runs')}({ab.get('balls')}) "
                            f"cb={cb_b['runs']}({cb_b['balls']})")
    # FOW: count must match wickets, warn if any "unknown" persists
    if ws.get("fow_count") is not None and ws.get("wickets") is not None:
        if ws["fow_count"] != int(ws["wickets"] or 0):
            issues.append(
                f"FOW_COUNT: ui={ws['fow_count']} "
                f"vs wickets={ws['wickets']}")
    if (ws.get("fow_unknown") or 0) > 0:
        issues.append(
            f"FOW_UNKNOWN: {ws['fow_unknown']} placeholder(s) "
            f"awaiting broadcast upgrade")
    # Bowler
    if cb.get("bowler"):
        cbb = cb["bowler"]
        if _surname(ws.get("bowler")) != _surname(cbb["name"]):
            issues.append(
                f"BOWLER: ui={ws.get('bowler')} cb={cbb['name']}")
        else:
            if ws.get("bowler_w") is not None and \
               int(ws.get("bowler_w") or 0) != cbb["wickets"]:
                issues.append(
                    f"BOWL_W: ui={ws.get('bowler_w')} cb={cbb['wickets']}")
            if ws.get("bowler_r") is not None and \
               int(ws.get("bowler_r") or 0) != cbb["runs"]:
                issues.append(
                    f"BOWL_R: ui={ws.get('bowler_r')} cb={cbb['runs']}")
            if ws.get("bowler_o") is not None and \
               str(ws.get("bowler_o")) != cbb["overs"]:
                issues.append(
                    f"BOWL_O: ui={ws.get('bowler_o')} cb={cbb['overs']}")
    return issues


async def main():
    print("=== PARITY MONITOR — pipeline UI vs cricbuzz ===")
    print(f"WS:  {WS_URL}")
    print(f"CB:  {CB_FALLBACK}")
    last_print = ""
    iteration = 0
    iter_err_count = 0
    while True:
        iteration += 1
        # Belt-and-braces: wrap the entire iter body so any unexpected
        # exception (parse crash, format error, etc.) logs-and-
        # continues instead of killing the monitor. The fetchers
        # already return {"_err": ...} on failure; this guard catches
        # anything downstream of them.
        try:
            # Fetch WS first so we can pass the live batting team name
            # to the CB scraper — that lets it pick the LIVE innings
            # on the cricbuzz page when both innings are visible
            # (e.g. during a chase the page shows "SRH 194-9(20)" AND
            # "CSK 154-6(16.4)"; without the team hint we always grab
            # the first one which is the wrong/finished innings).
            ws_raw = await fetch_ws_state()
            ws = (parse_ws(ws_raw) if ws_raw and "_err" not in ws_raw
                  else {})
            cb = await fetch_cb(prefer_team=ws.get("team"))
            ts = time.strftime("%H:%M:%S")
            block = []
            block.append(f"\n[{ts}  iter#{iteration}]")
            if "_err" in (ws_raw or {}):
                block.append(f"  WS ERR: {ws_raw['_err']!r}")
            else:
                block.append(
                    f"  UI: {ws.get('team')} {ws.get('score')}-"
                    f"{ws.get('wickets')} ({ws.get('overs')})  "
                    f"str={ws.get('striker')} "
                    f"nstr={ws.get('non')}  "
                    f"bowl={ws.get('bowler')} {ws.get('bowler_w')}-"
                    f"{ws.get('bowler_r')} ({ws.get('bowler_o')})")
                block.append(
                    f"  this_over={ws.get('this_over')}  "
                    f"fow={ws.get('fow_count')} "
                    f"(unk={ws.get('fow_unknown')})  "
                    f"last_fow={ws.get('fow_last')}")
                if ws.get('delivery_info'):
                    _di = ws['delivery_info']
                    block.append(
                        f"  delivery: len={_di.get('length')} "
                        f"line={_di.get('line')} "
                        f"shot={_di.get('shot_type')} "
                        f"[{_di.get('method')}]")
                else:
                    block.append("  delivery: (none yet on UI)")
                block.append(
                    f"  extras: this_over={ws.get('extras_this_over')} "
                    f"innings={ws.get('extras_innings')} "
                    f"[{ws.get('extras_breakdown')}]")
                if ws.get('extras_log_tail'):
                    block.append(
                        f"  extras_log: {ws.get('extras_log_tail')}")
            if "_err" in (cb or {}):
                block.append(f"  CB ERR: {cb['_err']!r}")
            else:
                block.append(
                    f"  CB: {cb.get('team')} {cb.get('score')}-"
                    f"{cb.get('wickets')} ({cb.get('overs')})  "
                    f"crr={cb.get('crr')}  ps={cb.get('partnership')}  "
                    f"recent={cb.get('recent')}")
                if cb.get("batters"):
                    bsum = ", ".join(
                        f"{b['name']}"
                        f"{'*' if cb.get('striker') == b['name'] else ''} "
                        f"{b['runs']}({b['balls']})"
                        for b in cb["batters"])
                    block.append(f"  CB BAT: {bsum}")
                if cb.get("bowler"):
                    bw = cb["bowler"]
                    block.append(
                        f"  CB BOWL: {bw['name']} "
                        f"{bw['wickets']}-{bw['runs']} ({bw['overs']})")
                if cb.get("last_wkt"):
                    block.append(f"  LAST WKT: {cb['last_wkt']}")
            issues = diff(ws or {}, cb or {})
            if issues:
                block.append("  ⚠ DIVERGENCE: " + " | ".join(issues))
            else:
                block.append("  ✓ score/wickets/overs match")
            out = "\n".join(block)
            if out != last_print:
                print(out, flush=True)
                last_print = out
        except Exception as e:  # noqa: BLE001
            # Log-and-continue. Any exception here is a monitor bug
            # (not a downstream system failure), so surface it with a
            # counter so repeated failures are visible.
            iter_err_count += 1
            ts = time.strftime("%H:%M:%S")
            print(
                f"\n[{ts}  iter#{iteration}] "
                f"ITER ERR #{iter_err_count}: "
                f"{type(e).__name__}: {e}",
                flush=True)
        await asyncio.sleep(20)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

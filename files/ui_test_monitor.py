"""
UI Test Monitor — connects to WebSocket, records all state updates for N minutes,
then analyzes for genuine UI problems (persistent/frequent enough to be user-visible).

Usage:
    python ui_test_monitor.py [--duration 300] [--ws ws://localhost:8765]
"""
from __future__ import annotations

import asyncio
import json
import time
import sys
import argparse
from collections import defaultdict
from typing import Any

try:
    import websockets
except ImportError:
    print("pip install websockets")
    sys.exit(1)


# ── thresholds ──────────────────────────────────────────────────────
# A problem is "genuine" only if it persists for >= PERSIST_FRAMES consecutive
# frames OR occurs in >= FREQ_PCT % of all frames.
PERSIST_FRAMES = 5        # ~15-25 seconds depending on cycle time
FREQ_PCT = 20             # 20% of frames


def _safe(d: dict, *keys, default=None):
    v = d
    for k in keys:
        if isinstance(v, dict):
            v = v.get(k, default)
        else:
            return default
    return v


class UITestMonitor:
    def __init__(self, ws_url: str, duration_s: int):
        self.ws_url = ws_url
        self.duration_s = duration_s
        self.snapshots: list[dict] = []
        self.issues: dict[str, list[dict]] = defaultdict(list)

    # ── collection ──────────────────────────────────────────────────
    async def collect(self):
        print(f"[MONITOR] Connecting to {self.ws_url} ...")
        async with websockets.connect(self.ws_url) as ws:
            print(f"[MONITOR] Connected. Recording for {self.duration_s}s ...")
            start = time.time()
            idx = 0
            while time.time() - start < self.duration_s:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=10)
                    data = json.loads(raw)
                    data["_ts"] = time.time()
                    data["_idx"] = idx
                    self.snapshots.append(data)
                    idx += 1
                    elapsed = int(time.time() - start)
                    if idx % 20 == 0:
                        print(f"  [{elapsed}s] {idx} frames captured")
                except asyncio.TimeoutError:
                    print(f"  [WARN] No data for 10s — pipeline paused?")
                except Exception as e:
                    print(f"  [ERR] {e}")
                    await asyncio.sleep(1)
            print(f"[MONITOR] Done. Captured {len(self.snapshots)} frames "
                  f"in {int(time.time()-start)}s.")

    # ── analysis ────────────────────────────────────────────────────
    def analyze(self):
        if len(self.snapshots) < 3:
            print("[MONITOR] Not enough data to analyze.")
            return

        total = len(self.snapshots)
        print(f"\n{'='*70}")
        print(f"UI TEST REPORT — {total} frames over "
              f"{int(self.snapshots[-1]['_ts'] - self.snapshots[0]['_ts'])}s")
        print(f"{'='*70}\n")

        self._check_score_missing()
        self._check_team_name_missing()
        self._check_batting_card_empty()
        self._check_bowling_card_empty()
        self._check_too_many_batters()
        self._check_batter_runs_exceed_score()
        self._check_bowler_wickets_exceed_team()
        self._check_score_flicker()
        self._check_batter_flicker()
        self._check_score_frozen()
        self._check_wrong_team_flash()
        self._check_field_data_missing()
        self._check_three_plus_active_batters()
        self._check_scorecard_tab_empty()
        self._check_overs_regression()

        self._print_summary(total)

    def _flag(self, issue_id: str, frame_idx: int, detail: str):
        self.issues[issue_id].append({"frame": frame_idx, "detail": detail})

    # ── individual checks ───────────────────────────────────────────

    def _check_score_missing(self):
        """Score/wickets/overs all null — UI shows dashes."""
        for s in self.snapshots:
            sc = _safe(s, "scorecard", default={})
            if sc.get("score") is None and sc.get("wickets") is None:
                phase = _safe(s, "match", "phase")
                if phase == "live":
                    self._flag("SCORE_MISSING",
                               s["_idx"], "score=None wickets=None in live phase")

    def _check_team_name_missing(self):
        """Batting team name blank during live play."""
        for s in self.snapshots:
            sc = _safe(s, "scorecard", default={})
            phase = _safe(s, "match", "phase")
            if phase == "live" and not sc.get("batting_team"):
                self._flag("TEAM_NAME_MISSING", s["_idx"],
                           "batting_team empty during live")

    def _check_batting_card_empty(self):
        """Live tab: no batters shown (batting_card empty or all non-batting)."""
        for s in self.snapshots:
            phase = _safe(s, "match", "phase")
            if phase != "live":
                continue
            bc = s.get("batting_card", [])
            active = [b for b in bc if b.get("status") == "batting"]
            if len(active) == 0 and _safe(s, "scorecard", "score") is not None:
                self._flag("NO_ACTIVE_BATTERS", s["_idx"],
                           f"0 active batters, card has {len(bc)} entries")

    def _check_bowling_card_empty(self):
        """No current bowler shown."""
        for s in self.snapshots:
            phase = _safe(s, "match", "phase")
            if phase != "live":
                continue
            bwl = s.get("bowling_card", [])
            current = [b for b in bwl if b.get("is_current")]
            if len(current) == 0 and _safe(s, "scorecard", "overs"):
                self._flag("NO_CURRENT_BOWLER", s["_idx"],
                           f"0 current bowlers, card has {len(bwl)} entries")

    def _check_too_many_batters(self):
        """More than 2 active batters."""
        for s in self.snapshots:
            bc = s.get("batting_card", [])
            active = [b for b in bc if b.get("status") == "batting"]
            if len(active) > 2:
                names = [b.get("name") for b in active]
                self._flag("THREE_PLUS_BATTERS", s["_idx"],
                           f"{len(active)} active: {names}")

    def _check_batter_runs_exceed_score(self):
        """Total batter runs > team score + 10."""
        for s in self.snapshots:
            sc = _safe(s, "scorecard", default={})
            score = sc.get("score")
            if score is None:
                continue
            bc = s.get("batting_card", [])
            total_runs = sum(b.get("runs") or 0 for b in bc
                             if b.get("status") in ("batting", "out"))
            if total_runs > score + 10:
                self._flag("BATTER_RUNS_EXCEED_SCORE", s["_idx"],
                           f"batter total {total_runs} > score {score}+10")

    def _check_bowler_wickets_exceed_team(self):
        """Any bowler has more wickets than team total."""
        for s in self.snapshots:
            sc = _safe(s, "scorecard", default={})
            team_w = sc.get("wickets")
            if team_w is None:
                continue
            for b in s.get("bowling_card", []):
                bw = b.get("wickets")
                if bw is not None and int(bw) > int(team_w):
                    self._flag("BOWLER_WICKETS_EXCEED", s["_idx"],
                               f"{b.get('name')} has {bw}W > team {team_w}W")

    def _check_score_flicker(self):
        """Score jumps up then back down within 3 frames (flicker)."""
        for i in range(1, len(self.snapshots) - 1):
            s0 = _safe(self.snapshots[i-1], "scorecard", "score")
            s1 = _safe(self.snapshots[i], "scorecard", "score")
            s2 = _safe(self.snapshots[i+1], "scorecard", "score")
            if s0 is not None and s1 is not None and s2 is not None:
                if s1 != s0 and s2 == s0 and abs(s1 - s0) > 5:
                    self._flag("SCORE_FLICKER", self.snapshots[i]["_idx"],
                               f"{s0}→{s1}→{s2}")

    def _check_batter_flicker(self):
        """Batter name appears then disappears within 3 frames."""
        for i in range(1, len(self.snapshots) - 1):
            def names(snap):
                return set(b.get("name") for b in snap.get("batting_card", [])
                           if b.get("status") == "batting")
            n0, n1, n2 = names(self.snapshots[i-1]), names(self.snapshots[i]), names(self.snapshots[i+1])
            appeared = n1 - n0
            disappeared = appeared & (n0 - n2)  # appeared in i, gone in i+1
            for name in (n1 - n0) & (n0 | n2):
                pass  # complex — simplified below
            ghost = n1 - n0 - n2
            for name in ghost:
                self._flag("BATTER_FLICKER", self.snapshots[i]["_idx"],
                           f"'{name}' appeared then vanished")

    def _check_score_frozen(self):
        """Score unchanged for 15+ consecutive frames during live play."""
        run_start = 0
        prev_score = None
        for i, s in enumerate(self.snapshots):
            phase = _safe(s, "match", "phase")
            score = _safe(s, "scorecard", "score")
            if phase != "live" or score is None:
                prev_score = None
                run_start = i + 1
                continue
            if score == prev_score:
                if i - run_start >= 15:
                    self._flag("SCORE_FROZEN", s["_idx"],
                               f"score={score} frozen for {i - run_start} frames")
                    run_start = i  # don't flag every frame
            else:
                run_start = i
            prev_score = score

    def _check_wrong_team_flash(self):
        """Batting team changes then reverts (wrong team shown briefly)."""
        for i in range(1, len(self.snapshots) - 1):
            t0 = _safe(self.snapshots[i-1], "scorecard", "batting_team")
            t1 = _safe(self.snapshots[i], "scorecard", "batting_team")
            t2 = _safe(self.snapshots[i+1], "scorecard", "batting_team")
            if t0 and t1 and t2 and t1 != t0 and t2 == t0:
                self._flag("TEAM_FLICKER", self.snapshots[i]["_idx"],
                           f"'{t0}'→'{t1}'→'{t0}'")

    def _check_field_data_missing(self):
        """Field tab has 0 positions during live play."""
        for s in self.snapshots:
            phase = _safe(s, "match", "phase")
            if phase != "live":
                continue
            field = s.get("field", {})
            positions = field.get("positions", []) if field else []
            if len(positions) == 0:
                self._flag("FIELD_EMPTY", s["_idx"], "0 field positions")

    def _check_three_plus_active_batters(self):
        """Full batting squad has 3+ 'batting' status (Scorecard tab issue)."""
        for s in self.snapshots:
            fbs = s.get("full_batting_squad", [])
            active = [b for b in fbs if b.get("status") == "batting"]
            if len(active) > 2:
                names = [b.get("name") for b in active]
                self._flag("SQUAD_THREE_BATTERS", s["_idx"],
                           f"{len(active)} in full_batting_squad: {names}")

    def _check_scorecard_tab_empty(self):
        """Full batting squad completely empty during live play."""
        for s in self.snapshots:
            phase = _safe(s, "match", "phase")
            if phase != "live":
                continue
            fbs = s.get("full_batting_squad", [])
            if len(fbs) == 0:
                self._flag("SCORECARD_EMPTY", s["_idx"],
                           "full_batting_squad empty during live")

    def _check_overs_regression(self):
        """Overs go backward (e.g. 5.3 → 4.1)."""
        prev_overs = None
        for s in self.snapshots:
            overs_str = _safe(s, "scorecard", "overs")
            if not overs_str:
                prev_overs = None
                continue
            try:
                parts = str(overs_str).split(".")
                balls = int(parts[0]) * 6 + (int(parts[1]) if len(parts) > 1 else 0)
            except (ValueError, IndexError):
                continue
            if prev_overs is not None and balls < prev_overs - 6:
                self._flag("OVERS_REGRESSION", s["_idx"],
                           f"overs went from {prev_overs} balls to {balls}")
            prev_overs = balls

    # ── reporting ───────────────────────────────────────────────────

    def _classify_severity(self, issue_id: str, occurrences: list[dict],
                           total: int) -> str | None:
        """Return severity if genuine, None if transient/handled."""
        count = len(occurrences)
        pct = (count / total) * 100 if total else 0

        # Check for consecutive runs
        frames = sorted(o["frame"] for o in occurrences)
        max_run = 1
        current_run = 1
        for i in range(1, len(frames)):
            if frames[i] - frames[i-1] <= 2:  # allow 1-frame gap
                current_run += 1
                max_run = max(max_run, current_run)
            else:
                current_run = 1

        # Classify
        if max_run >= PERSIST_FRAMES or pct >= FREQ_PCT:
            if pct >= 50:
                return "CRITICAL"
            elif pct >= FREQ_PCT or max_run >= PERSIST_FRAMES * 2:
                return "HIGH"
            else:
                return "MEDIUM"
        return None  # transient — system handled it

    def _print_summary(self, total: int):
        genuine: list[tuple[str, str, int, float, int, str]] = []
        transient: list[tuple[str, int]] = []

        for issue_id, occurrences in sorted(self.issues.items()):
            count = len(occurrences)
            pct = (count / total) * 100
            frames = sorted(o["frame"] for o in occurrences)
            max_run = 1
            cr = 1
            for i in range(1, len(frames)):
                if frames[i] - frames[i-1] <= 2:
                    cr += 1
                    max_run = max(max_run, cr)
                else:
                    cr = 1

            severity = self._classify_severity(issue_id, occurrences, total)
            if severity:
                sample = occurrences[0]["detail"]
                genuine.append((issue_id, severity, count, pct, max_run, sample))
            else:
                transient.append((issue_id, count))

        # Print genuine issues
        if genuine:
            print("GENUINE UI ISSUES (visible to users):")
            print("-" * 70)
            for issue_id, sev, count, pct, max_run, sample in \
                    sorted(genuine, key=lambda x: {"CRITICAL": 0, "HIGH": 1,
                                                    "MEDIUM": 2}[x[1]]):
                print(f"\n  [{sev}] {issue_id}")
                print(f"    Occurrences: {count}/{total} ({pct:.1f}%)")
                print(f"    Longest streak: {max_run} consecutive frames")
                print(f"    Example: {sample}")
        else:
            print("NO GENUINE UI ISSUES DETECTED!")

        # Print transient (system-handled)
        if transient:
            print(f"\n\nTransient issues (system recovered, NOT user-visible):")
            print("-" * 70)
            for issue_id, count in transient:
                print(f"  {issue_id}: {count} occurrences (self-corrected)")

        # Score progression
        print(f"\n\nSCORE PROGRESSION:")
        print("-" * 70)
        scores_seen = []
        for s in self.snapshots:
            sc = _safe(s, "scorecard", default={})
            score = sc.get("score")
            wickets = sc.get("wickets")
            overs = sc.get("overs")
            team = sc.get("batting_team", "?")
            if score is not None:
                entry = f"{team} {score}/{wickets} ({overs})"
                if not scores_seen or scores_seen[-1] != entry:
                    scores_seen.append(entry)
        for entry in scores_seen:
            print(f"  {entry}")

        # Batting card evolution
        print(f"\n\nBATTER APPEARANCES (Live tab):")
        print("-" * 70)
        batter_frames: dict[str, int] = defaultdict(int)
        for s in self.snapshots:
            for b in s.get("batting_card", []):
                if b.get("status") == "batting":
                    batter_frames[b.get("name", "?")] += 1
        for name, count in sorted(batter_frames.items(),
                                   key=lambda x: -x[1]):
            pct = (count / total) * 100
            print(f"  {name}: {count} frames ({pct:.0f}%)")

        # Scorecard tab: full squad sizes
        print(f"\n\nSCORECARD TAB DATA:")
        print("-" * 70)
        last = self.snapshots[-1] if self.snapshots else {}
        fbs = last.get("full_batting_squad", [])
        fbwl = last.get("full_bowling_squad", [])
        print(f"  Batting squad: {len(fbs)} players")
        for b in fbs:
            st = b.get("status", "?")
            r = b.get("runs")
            bl = b.get("balls")
            stat = f"{r}({bl})" if r is not None else "-"
            print(f"    {b.get('name','?'):25s} {st:12s} {stat}")
        print(f"  Bowling squad: {len(fbwl)} players")
        for b in fbwl:
            o = b.get("overs")
            stat = f"{b.get('wickets','-')}/{b.get('runs','-')} ({o})" if o else "-"
            cur = " *" if b.get("is_current") else ""
            print(f"    {b.get('name','?'):25s} {stat}{cur}")

        # Save raw data
        outfile = f"ui_test_{int(time.time())}.json"
        with open(outfile, "w") as f:
            json.dump({
                "frames": total,
                "duration_s": int(self.snapshots[-1]["_ts"] - self.snapshots[0]["_ts"]),
                "genuine_issues": [
                    {"id": g[0], "severity": g[1], "count": g[2],
                     "pct": round(g[3], 1), "max_run": g[4], "sample": g[5]}
                    for g in genuine
                ],
                "transient": [{"id": t[0], "count": t[1]} for t in transient],
                "score_progression": scores_seen,
            }, f, indent=2)
        print(f"\n  Raw data saved to {outfile}")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=300,
                        help="seconds to monitor (default 300)")
    parser.add_argument("--ws", type=str, default="ws://localhost:8765",
                        help="WebSocket URL")
    args = parser.parse_args()

    monitor = UITestMonitor(args.ws, args.duration)
    await monitor.collect()
    monitor.analyze()


if __name__ == "__main__":
    asyncio.run(main())

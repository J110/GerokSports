#!/usr/bin/env python3
"""Groq quota go/no-go check for OpenScout decoupling target cadence.

Reads existing OpenScout sidecar JSONL files to compute observed
cadence + project headroom for 1.5s and 1.0s target intervals.
Compares against published Groq tier limits for the configured
model (llama-4-scout-17b-16e-instruct).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import median, mean
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
LOG_DIRS = [
    ROOT / "files" / "logs",
    ROOT / "logs",
    ROOT / "files" / "openscout_shadow",
]

MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

GROQ_TIERS = {
    "free":           {"rpm": 30,  "tpm": 30_000,    "rpd": 1_000},
    "dev_tier_1":     {"rpm": 60,  "tpm": 60_000,    "rpd": 14_400},
    "dev_tier_2":     {"rpm": 600, "tpm": 600_000,   "rpd": 144_000},
    "dev_tier_3":     {"rpm": 1200,"tpm": 1_200_000, "rpd": 288_000},
    "production":     {"rpm": None,"tpm": None,      "rpd": None},
}

MATCH_HOURS = 3.5


def parse_record(line: str) -> dict[str, Any] | None:
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def get_ts(rec: dict[str, Any]) -> float | None:
    for key in ("ts", "timestamp", "t", "frame_ts", "captured_at"):
        v = rec.get(key)
        if isinstance(v, (int, float)):
            return float(v)
    return None


def analyze_sidecar(path: Path) -> dict[str, Any] | None:
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return None
    records = [r for r in (parse_record(l) for l in lines if l.strip())
               if r is not None]
    if len(records) < 2:
        return None
    ts_list = sorted([t for t in (get_ts(r) for r in records) if t is not None])
    if len(ts_list) < 2:
        return None
    gaps = [ts_list[i] - ts_list[i - 1] for i in range(1, len(ts_list))
            if 0 < ts_list[i] - ts_list[i - 1] < 600]
    if not gaps:
        return None
    duration_s = ts_list[-1] - ts_list[0]
    return {
        "path": str(path),
        "name": path.name,
        "n_calls": len(records),
        "duration_s": duration_s,
        "duration_min": duration_s / 60.0,
        "median_gap_s": median(gaps),
        "mean_gap_s": mean(gaps),
        "p90_gap_s": sorted(gaps)[int(0.9 * len(gaps))],
        "observed_rpm": 60.0 * len(ts_list) / duration_s if duration_s > 0 else 0,
    }


def project(target_s: float) -> dict[str, float]:
    rpm = 60.0 / target_s
    rpd = rpm * 60 * MATCH_HOURS
    return {
        "target_s": target_s,
        "projected_rpm": rpm,
        "calls_per_match": rpm * 60 * MATCH_HOURS,
        "projected_rpd": rpd,
    }


def headroom(projected_rpm: float, tier_rpm: int | None) -> str:
    if tier_rpm is None:
        return "unbounded (production tier)"
    pct = 100.0 * projected_rpm / tier_rpm
    if pct < 60:
        return f"OK ({pct:.0f}% of {tier_rpm} RPM)"
    if pct < 80:
        return f"TIGHT ({pct:.0f}% of {tier_rpm} RPM)"
    return f"NO-GO ({pct:.0f}% of {tier_rpm} RPM)"


def main() -> int:
    print("=" * 70)
    print("GROQ QUOTA CHECK — OpenScout decoupling target cadence")
    print(f"Model: {MODEL}")
    print("=" * 70)

    sidecars: list[dict[str, Any]] = []
    for d in LOG_DIRS:
        if not d.is_dir():
            continue
        for p in sorted(d.glob("openscout-*.jsonl")):
            r = analyze_sidecar(p)
            if r:
                sidecars.append(r)

    if not sidecars:
        print("\nNo sidecar data found.")
        return 1

    print(f"\nObserved cadence ({len(sidecars)} sidecar files):")
    print(f"  {'name':<45} {'calls':>6} {'dur_min':>8} "
          f"{'med_gap':>8} {'p90_gap':>8} {'rpm':>6}")
    for s in sidecars:
        print(f"  {s['name']:<45} {s['n_calls']:>6} "
              f"{s['duration_min']:>8.1f} "
              f"{s['median_gap_s']:>8.2f} "
              f"{s['p90_gap_s']:>8.2f} "
              f"{s['observed_rpm']:>6.1f}")

    longest = max(sidecars, key=lambda s: s["duration_s"])
    print(f"\nReference run: {longest['name']}")
    print(f"  duration: {longest['duration_min']:.1f} min, "
          f"calls: {longest['n_calls']}")
    print(f"  median inter-call gap: {longest['median_gap_s']:.2f}s")
    print(f"  p90 inter-call gap:    {longest['p90_gap_s']:.2f}s")
    print(f"  observed RPM:          {longest['observed_rpm']:.1f}")

    print("\nProjections (per match @ {:.1f}h):".format(MATCH_HOURS))
    print(f"  {'target':<10} {'rpm':>6} {'calls/match':>12} {'rpd':>8}")
    for target_s in (1.5, 1.0, 0.75):
        p = project(target_s)
        print(f"  {target_s:>4.2f}s    "
              f"{p['projected_rpm']:>6.0f} "
              f"{p['calls_per_match']:>12.0f} "
              f"{p['projected_rpd']:>8.0f}")

    print("\nHeadroom vs Groq tier limits:")
    print(f"  {'tier':<14} {'tier_rpm':>9} {'1.5s':>16} {'1.0s':>16} {'0.75s':>16}")
    for tier, lim in GROQ_TIERS.items():
        rpm = lim["rpm"]
        rpm_s = str(rpm) if rpm else "∞"
        h15 = headroom(60 / 1.5, rpm)
        h10 = headroom(60 / 1.0, rpm)
        h075 = headroom(60 / 0.75, rpm)
        print(f"  {tier:<14} {rpm_s:>9} {h15:>16} {h10:>16} {h075:>16}")

    print("\nVerdict matrix (assuming match length {:.1f}h):".format(MATCH_HOURS))
    for target_s in (1.5, 1.0):
        p = project(target_s)
        print(f"\n  Target {target_s}s — {p['projected_rpm']:.0f} RPM, "
              f"{p['calls_per_match']:.0f} calls/match")
        for tier, lim in GROQ_TIERS.items():
            rpm = lim["rpm"]
            rpd = lim["rpd"]
            ok_rpm = rpm is None or p["projected_rpm"] <= 0.8 * rpm
            ok_rpd = rpd is None or p["calls_per_match"] <= 0.8 * rpd
            verdict = "GO" if (ok_rpm and ok_rpd) else "NO-GO"
            why = []
            if rpm and not ok_rpm:
                why.append(f"RPM {p['projected_rpm']:.0f}>{0.8*rpm:.0f}")
            if rpd and not ok_rpd:
                why.append(f"RPD {p['calls_per_match']:.0f}>{0.8*rpd:.0f}")
            tag = f" ({', '.join(why)})" if why else ""
            print(f"    {tier:<14} → {verdict}{tag}")

    print("\n" + "=" * 70)
    print("CRITICAL UNKNOWN: which Groq tier is this account on?")
    print("Verify at: https://console.groq.com/settings/billing")
    print("Token-per-minute (TPM) is the OTHER ceiling — vision calls are")
    print("token-heavy (~2-5K tokens/call). At 1.0s × 60 RPM × 3K tokens =")
    print("180K TPM. Free/dev_tier_1 caps at 30-60K TPM → likely NO-GO on TPM.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())

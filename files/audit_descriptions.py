"""Test the action_description-augmented Scout prompt over a real
sequence of consecutive deliveries.

Goal: judge whether the per-frame descriptions, when stitched in
temporal order per delivery, give us a coherent picture of what
happened.

Design choice: action_description is added to the STEP 1 JSON tag line
(structured, always emitted), constrained to ~40 words.  The
existing STEP 4 free-form action sentence is removed to avoid
duplicate output cost.  Everything else (camera_view, frame_phase,
ball_position, scoreboard parsing) is unchanged so we measure the
incremental cost of just the new field.

Outputs:
  audit_descriptions/results.json
        per-frame Scout response (raw + parsed JSON + ms)
  audit_descriptions/by_delivery.txt
        human-readable per-delivery story:
        ground-truth scoreboard before/after, then ordered list of
        frame descriptions
  stdout: latency mean/p50/p95
"""
from __future__ import annotations
import asyncio
import base64
import json
import time
from pathlib import Path

import cv2
from groq import AsyncGroq

from eyes.config import GROQ_API_KEY, GROQ_PRIMARY_MODEL
from eyes.vision import SCOUT_PROMPT as SCOUT_PROMPT_BASE, Vision

ROOT = Path(__file__).parent
SESSION = ROOT / "logs/deliveries/20260419_223221"
OUT = ROOT / "audit_descriptions"


# Construct the description-augmented prompt by:
#   (1) adding `action_description` to the JSON example
#   (2) inserting an instruction block after the ball_position
#       definition, before STEP 2
#   (3) removing the trailing STEP 4 free-form action so we're not
#       asking for the same thing twice and paying for both
def make_prompt() -> str:
    p = SCOUT_PROMPT_BASE

    # (1) extend the JSON example
    p = p.replace(
        '"ball_position": null}}',
        '"ball_position": null, "action_description": '
        '"bowler mid-stride, ball not yet released, batter at far '
        'crease in stance"}}',
    )

    # (2) add the instruction.  Splice right before STEP 2.
    INSTR = """\
action_description: ONE sentence, ~40 words max, plain English, \
describing exactly what is visible in THIS frame.  Be concrete: name \
what you see — bowler position/action, ball if visible and where, \
batter stance/shot, fielders' actions, what fills the frame.  Do NOT \
speculate about what happened before or after.  Do NOT repeat \
scoreboard data.  If the frame is a closeup, replay, graphic, or ad, \
describe the content (who/what is shown).

"""
    p = p.replace("STEP 2 — READ THE STRIP", INSTR + "STEP 2 — READ THE STRIP")

    # (3) drop STEP 4 — already covered by action_description
    p = p.replace(
        "STEP 4 — ACTION (1 sentence):\n"
        "What is happening? (delivery bowled, shot played, "
        "celebration, etc.)\n\n",
        "",
    )
    p = p.replace(
        "- JSON tag line MUST be first. Then strip. Then overlays. "
        "Then action.",
        "- JSON tag line MUST be first. Then strip. Then overlays.",
    )
    return p


def encode(p: Path) -> str:
    bgr = cv2.imread(str(p))
    h, w = bgr.shape[:2]
    if w > 1280:
        bgr = cv2.resize(bgr, (1280, int(h * 1280 / w)),
                         interpolation=cv2.INTER_AREA)
    _, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return base64.b64encode(buf.tobytes()).decode("ascii")


async def call_one(client: AsyncGroq, b64: str, prompt: str) -> dict:
    t0 = time.perf_counter()
    last_err = None
    for attempt in range(6):
        try:
            resp = await client.chat.completions.create(
                model=GROQ_PRIMARY_MODEL,
                temperature=0,
                max_tokens=700,
                messages=[{"role": "user", "content": [
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text": prompt},
                ]}],
            )
            raw = resp.choices[0].message.content.strip()
            ms = int((time.perf_counter() - t0) * 1000)
            tag, ftype = Vision._parse_tag(raw)
            return {
                "raw": raw,
                "tag": tag,
                "frame_type": ftype,
                "ms": ms,
            }
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            if "rate limit" in msg or "429" in msg:
                wait = min(20, 4 * (2 ** attempt))
                await asyncio.sleep(wait)
                continue
            return {"error": repr(e),
                    "ms": int((time.perf_counter() - t0) * 1000)}
    return {"error": repr(last_err),
            "ms": int((time.perf_counter() - t0) * 1000)}


async def main():
    OUT.mkdir(exist_ok=True)
    prompt = make_prompt().format(vision_hint="None.")
    print(f"prompt length: {len(prompt)} chars")

    deliveries = []
    for d in sorted(SESSION.iterdir()):
        if not d.is_dir() or not d.name.startswith("d"):
            continue
        frames = sorted(d.glob("frame_*.jpg"))
        if not frames:
            continue
        meta_path = d / "predictions.json"
        meta = (json.loads(meta_path.read_text())
                if meta_path.exists() else {})
        deliveries.append({"id": d.name, "frames": frames, "meta": meta})

    n_frames = sum(len(d["frames"]) for d in deliveries)
    print(f"deliveries: {len(deliveries)}  frames: {n_frames}")

    client = AsyncGroq(api_key=GROQ_API_KEY, timeout=60)

    results: list[dict] = []
    t_run = time.perf_counter()
    for d in deliveries:
        for fi, fp in enumerate(d["frames"]):
            b64 = encode(fp)
            r = await call_one(client, b64, prompt)
            r["delivery"] = d["id"]
            r["frame_idx"] = fi
            r["frame_path"] = str(fp.relative_to(ROOT))
            results.append(r)
            print(f"  {d['id']}/frame_{fi:02d}  {r.get('ms', '?')}ms"
                  f"  {('error: ' + r['error'][:60]) if 'error' in r else ''}")
    total_s = time.perf_counter() - t_run

    # write raw results
    (OUT / "results.json").write_text(json.dumps(results, indent=2))

    # latency stats
    ok = [r for r in results if "error" not in r]
    if ok:
        ms = sorted(r["ms"] for r in ok)
        mean = sum(ms) / len(ms)
        p50 = ms[len(ms) // 2]
        p95 = ms[int(len(ms) * 0.95)]
        n_err = len(results) - len(ok)
        print()
        print(f"=== Latency over {len(ok)} successful calls "
              f"({n_err} errors) ===")
        print(f"  mean:  {mean:.0f} ms")
        print(f"  p50:   {p50} ms")
        print(f"  p95:   {p95} ms")
        print(f"  total wall time: {total_s:.1f}s")
        print(f"  TARGET: <1500 ms mean   "
              f"{'PASS' if mean < 1500 else 'FAIL'}")

    # write by-delivery story for human evaluation
    lines: list[str] = []
    for d in deliveries:
        meta = d["meta"]
        comp = meta.get("components", {})
        lines.append("=" * 72)
        lines.append(f"{d['id']}  runs={meta.get('runs', '?')}  "
                     f"vlm_conf={meta.get('vlm_confidence', '?')}")
        lines.append(f"  cricbuzz/strip:  {meta.get('commentary_line', '—')}")
        lines.append(f"  pipeline says:   length={comp.get('2_length', '?')}, "
                     f"line={comp.get('3_line', '?')}, "
                     f"shot={comp.get('5_shot', '?')}, "
                     f"speed_kph={meta.get('broadcast_speed_kph', '?')}")
        lines.append("")
        for r in results:
            if r["delivery"] != d["id"]:
                continue
            if "error" in r:
                lines.append(f"  frame_{r['frame_idx']:02d}  ERROR  "
                             f"{r['error'][:60]}")
                continue
            tag = r.get("tag") or {}
            cv = tag.get("camera_view")
            ph = tag.get("frame_phase")
            desc = tag.get("action_description") or "(no description)"
            lines.append(f"  frame_{r['frame_idx']:02d}  "
                         f"cv={cv}  phase={ph}  ({r['ms']}ms)")
            lines.append(f"    \"{desc}\"")
        lines.append("")
    (OUT / "by_delivery.txt").write_text("\n".join(lines))
    print(f"\nwrote {OUT}/by_delivery.txt")


if __name__ == "__main__":
    asyncio.run(main())

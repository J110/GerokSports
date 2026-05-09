"""
DashScope Qwen-VL Tagger Migration Test
Tests: model availability, classification accuracy, latency, strip reading
"""

import asyncio
import base64
import json
import time
import os
import sys
from pathlib import Path

# ── Config ──
sys.path.insert(0, os.path.dirname(__file__))
from eyes.config import DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL

API_KEY = DASHSCOPE_API_KEY
BASE_URL = DASHSCOPE_BASE_URL

MODELS_TO_TEST = [
    "qwen-vl-max",          # Best quality, ~$0.008/image
    "qwen-vl-max-latest",   # Latest version
    "qwen-vl-plus",         # Mid-tier
    "qwen2.5-vl-72b-instruct",  # Large open model
    "qwen2.5-vl-7b-instruct",   # Small open model
]

# Our actual tagger prompt
TAGGER_PROMPT = """Classify this cricket broadcast frame. Reply with ONLY a JSON object, no other text.

{
  "frame_type": "SCOREBOARD" | "CLOSEUP" | "GRAPHIC" | "INFO_PANEL" | "ADVERTISEMENT" | "REPLAY",
  "strip_visible": true | false,
  "info_panel_visible": true | false,
  "drs_review": true | false
}

FRAME TYPES:
- SCOREBOARD: Live match action with scoreboard strip at bottom
- CLOSEUP: Player closeup, crowd shot, or between-delivery shot (strip may be visible)
- GRAPHIC: Full-screen stats graphic (batting card, bowling figures, partnership)
- INFO_PANEL: Career stats or head-to-head overlay on top of live feed
- ADVERTISEMENT: Pure commercial break, no cricket content
- REPLAY: Slow-motion replay of previous delivery

IMPORTANT: The scoreboard strip at the BOTTOM of the screen may be visible in ANY frame type except ADVERTISEMENT."""

# Auto-discover test frames from debug_frames/
DEBUG_DIR = Path(__file__).parent / "debug_frames"


def discover_frames() -> list:
    """Pick a diverse sample of debug frames by type."""
    if not DEBUG_DIR.exists():
        print(f"No debug_frames/ directory. Run the pipeline first.")
        return []

    # Skip pixskip duplicates
    all_frames = sorted(
        [p for p in DEBUG_DIR.glob("*.jpg") if "pixskip" not in p.stem],
        key=lambda p: p.stat().st_mtime,
    )

    by_type: dict[str, list] = {}
    for p in all_frames:
        name = p.stem.lower()
        if "_ad" in name:
            ft = "ADVERTISEMENT"
        elif "_graphic" in name:
            ft = "GRAPHIC"
        elif "_closeup" in name:
            ft = "CLOSEUP"
        elif "_scoreboard" in name:
            ft = "SCOREBOARD"
        else:
            ft = "SCOREBOARD"
        by_type.setdefault(ft, []).append(p)

    frames = []
    quota = {"SCOREBOARD": 3, "GRAPHIC": 2, "ADVERTISEMENT": 2, "CLOSEUP": 1}
    for ft, limit in quota.items():
        for p in by_type.get(ft, [])[:limit]:
            frames.append({
                "path": str(p),
                "expected_type": ft,
                "expected_strip": ft not in ("ADVERTISEMENT",),
                "expected_drs": False,
                "desc": p.name,
            })

    return frames


TEST_FRAMES = discover_frames()


def encode_image(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


async def test_model(model_name: str, frames: list) -> dict:
    """Test a single model against all frames."""
    try:
        import httpx
    except ImportError:
        os.system("pip install httpx --break-system-packages -q")
        import httpx
    
    results = {
        "model": model_name,
        "available": False,
        "frames": [],
        "avg_latency_ms": 0,
        "accuracy": {"type": 0, "strip": 0, "drs": 0, "total": 0},
    }
    
    latencies = []
    
    async with httpx.AsyncClient(timeout=30) as client:
        for frame in frames:
            if not Path(frame["path"]).exists():
                results["frames"].append({"desc": frame["desc"], "error": "file not found"})
                continue
            
            b64 = encode_image(frame["path"])
            
            payload = {
                "model": model_name,
                "temperature": 0,
                "max_tokens": 150,
                "messages": [{
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"}
                        },
                        {"type": "text", "text": TAGGER_PROMPT}
                    ]
                }]
            }
            
            t0 = time.time()
            try:
                resp = await client.post(
                    f"{BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json=payload
                )
                latency_ms = int((time.time() - t0) * 1000)
                latencies.append(latency_ms)
                
                if resp.status_code != 200:
                    results["frames"].append({
                        "desc": frame["desc"],
                        "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
                        "latency_ms": latency_ms
                    })
                    continue
                
                results["available"] = True
                data = resp.json()
                raw = data["choices"][0]["message"]["content"].strip()
                
                # Parse JSON from response
                try:
                    # Strip markdown fences if present
                    clean = raw.replace("```json", "").replace("```", "").strip()
                    parsed = json.loads(clean)
                except json.JSONDecodeError:
                    parsed = {"frame_type": "PARSE_ERROR", "raw": raw[:100]}
                
                # Score accuracy
                type_match = parsed.get("frame_type", "").upper() == frame["expected_type"]
                strip_match = parsed.get("strip_visible") == frame["expected_strip"]
                drs_match = parsed.get("drs_review") == frame["expected_drs"]
                
                results["accuracy"]["total"] += 1
                if type_match: results["accuracy"]["type"] += 1
                if strip_match: results["accuracy"]["strip"] += 1
                if drs_match: results["accuracy"]["drs"] += 1
                
                # Token usage
                usage = data.get("usage", {})
                
                results["frames"].append({
                    "desc": frame["desc"],
                    "expected": frame["expected_type"],
                    "got": parsed.get("frame_type", "?"),
                    "strip": parsed.get("strip_visible"),
                    "drs": parsed.get("drs_review"),
                    "type_ok": "✓" if type_match else "✗",
                    "strip_ok": "✓" if strip_match else "✗",
                    "drs_ok": "✓" if drs_match else "✗",
                    "latency_ms": latency_ms,
                    "tokens": usage,
                    "raw": raw[:150] if not type_match else None
                })
                
            except Exception as e:
                latency_ms = int((time.time() - t0) * 1000)
                results["frames"].append({
                    "desc": frame["desc"],
                    "error": str(e)[:200],
                    "latency_ms": latency_ms
                })
    
    if latencies:
        results["avg_latency_ms"] = int(sum(latencies) / len(latencies))
    
    return results


async def main():
    if not API_KEY:
        print("ERROR: Set DASHSCOPE_API_KEY environment variable")
        print("  export DASHSCOPE_API_KEY='sk-...'")
        sys.exit(1)
    
    print("=" * 70)
    print("DashScope Qwen-VL Tagger Migration Test")
    print("=" * 70)
    print(f"\nAPI Key: {API_KEY[:8]}...{API_KEY[-4:]}")
    print(f"Test frames: {len(TEST_FRAMES)}")
    print(f"Models to test: {len(MODELS_TO_TEST)}")
    print()
    
    all_results = []
    
    for model in MODELS_TO_TEST:
        print(f"\n{'─' * 50}")
        print(f"Testing: {model}")
        print(f"{'─' * 50}")
        
        result = await test_model(model, TEST_FRAMES)
        all_results.append(result)
        
        if not result["available"]:
            print(f"  ✗ NOT AVAILABLE")
            if result["frames"]:
                print(f"    Error: {result['frames'][0].get('error', '?')[:100]}")
            continue
        
        print(f"  ✓ Available | Avg latency: {result['avg_latency_ms']}ms")
        print()
        
        for f in result["frames"]:
            if "error" in f:
                print(f"  ✗ {f['desc']}")
                print(f"    Error: {f['error'][:80]}")
            else:
                print(f"  {f['type_ok']} Type: {f['expected']:12s} → {f['got']:12s} "
                      f"| Strip:{f['strip_ok']} DRS:{f['drs_ok']} "
                      f"| {f['latency_ms']}ms")
                if f.get("raw"):
                    print(f"    Raw: {f['raw'][:100]}")
        
        total = result["accuracy"]["total"]
        if total > 0:
            print(f"\n  Accuracy: type={result['accuracy']['type']}/{total} "
                  f"strip={result['accuracy']['strip']}/{total} "
                  f"drs={result['accuracy']['drs']}/{total}")
    
    # ── Summary ──
    print(f"\n\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    print(f"\n{'Model':<30s} {'Avail':>6s} {'Latency':>8s} {'Type':>6s} {'Strip':>6s} {'DRS':>6s}")
    print(f"{'─' * 30} {'─' * 6} {'─' * 8} {'─' * 6} {'─' * 6} {'─' * 6}")
    
    for r in all_results:
        total = r["accuracy"]["total"] or 1
        print(f"{r['model']:<30s} "
              f"{'✓' if r['available'] else '✗':>6s} "
              f"{r['avg_latency_ms']:>6d}ms "
              f"{r['accuracy']['type']:>2d}/{total:<2d}  "
              f"{r['accuracy']['strip']:>2d}/{total:<2d}  "
              f"{r['accuracy']['drs']:>2d}/{total:<2d}")


if __name__ == "__main__":
    asyncio.run(main())

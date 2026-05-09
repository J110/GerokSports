"""Part B shadow-run driver — offline frames × variants × replicates.

Default corpus: ``docs/scout_corpus_v1.json``. Override with ``--corpus``.
Default output: ``docs/shadow_run_v1.json``. Override with ``--output``
(e.g. ``docs/shadow_run_v6c_<timestamp>.json``).

Reads corpus JSON, runs each frame against selected variant(s) through
Groq's Scout-equivalent call (meta-llama/llama-4-scout-17b-16e-instruct),
parses the JSON tag, and writes canonicalised rows to one JSON envelope.

Each row includes additive ``groq_*`` telemetry when the Groq call returns
(``groq_response_id``, ``groq_model``, ``groq_finish_reason``,
``groq_created``, ``groq_attempt_count``, ``groq_latency_ms``). Legacy
runs without these keys remain valid for downstream tools.
``groq_attempt_count`` is the 1-based number of attempted Groq calls for
that row—including retries for **429** rate limits **or** elapsed-time
timeouts (``asyncio.wait_for``)—so analysts can correlate with backoff.

Resume: unless ``--no-resume`` is passed, if the output file already
exists, existing (frame, variant, replicate) triples are skipped.

Concurrency: asyncio with a semaphore. Default 4 concurrent calls.
Per-attempt request ceiling: ``--timeout-s`` (default 15), applied via
``asyncio.wait_for`` around each ``chat.completions.create``. (Some
successful calls still show wall times above the per-attempt cap in
telemetry when 429 backoff accumulates; tails can exceed 15s.)

Usage:
    python3 shadow_eval/run_shadow.py [--corpus PATH] [--output PATH] \\
        [--dry-run] [--concurrency 4] [--timeout-s 15] [--no-resume] \\
        [--variants V6c]
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import re
import sys
import time
from pathlib import Path

# Project-local imports.  This file lives in files/shadow_eval/.
_HERE = Path(__file__).resolve().parent
_FILES = _HERE.parent
sys.path.insert(0, str(_FILES))

from shadow_eval.variants import VARIANTS, canon  # noqa: E402

from groq import AsyncGroq  # noqa: E402

DEFAULT_CORPUS = _FILES / "docs" / "scout_corpus_v1.json"
DEFAULT_OUT = _FILES / "docs" / "shadow_run_v1.json"
DEFAULT_FRAMES_DIR = _FILES / "docs" / "corpus_frames_v1"

MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
TEMPERATURE = 0.0
MAX_TOKENS = 600
REPLICATES = 3
MAX_ATTEMPTS = 5
DEFAULT_TIMEOUT_S = 15.0
TIMEOUT_S = DEFAULT_TIMEOUT_S
TIMEOUT_RETRY_BACKOFF_S = 1.5


def resolve_under_files(rel_or_abs: str | Path, files_root: Path = _FILES) -> Path:
    """Resolve a path relative to ``files_root`` unless already absolute."""
    p = Path(rel_or_abs)
    return p if p.is_absolute() else (files_root / p)


def _groq_api_key() -> str | None:
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        try:
            from eyes.config import GROQ_API_KEY as _cfg_key
            key = _cfg_key
        except Exception:
            pass
    return key if key else None


def load_corpus(corpus_path: Path) -> list[dict]:
    with corpus_path.open() as f:
        c = json.load(f)
    return c["frames"]


def _encode(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def groq_completion_metadata(resp: object | None, *,
                             attempt_count: int,
                             latency_ms: int) -> dict[str, object | None]:
    """Extract provider fields for shadow JSON rows. Groq may rename fields;
    absent attributes become ``None`` without raising."""

    meta: dict[str, object | None] = {
        "groq_response_id": None,
        "groq_model": None,
        "groq_finish_reason": None,
        "groq_created": None,
        "groq_attempt_count": attempt_count,
        "groq_latency_ms": latency_ms,
    }
    if resp is None:
        return meta
    try:
        meta["groq_response_id"] = getattr(resp, "id", None)
        meta["groq_model"] = getattr(resp, "model", None)
        meta["groq_created"] = getattr(resp, "created", None)
        choices = getattr(resp, "choices", None) or []
        if choices:
            ch0 = choices[0]
            meta["groq_finish_reason"] = getattr(ch0, "finish_reason",
                                                 None)
    except Exception as e:
        print(f"[run_shadow.py] WARN: groq metadata extract failed: "
              f"{type(e).__name__}: {str(e)[:120]}",
              file=sys.stderr)
    return meta


def _parse_tag(raw: str) -> dict | None:
    """Pull the first JSON object containing 'has_strip' from Scout's
    output.  Mirrors vision.py:_parse_tag but without the frame_type
    derivation (we only need camera_view + frame_phase here).
    """
    if not raw:
        return None
    for line in raw.split("\n")[:5]:
        s = line.strip()
        if not (s.startswith("{") and "has_strip" in s):
            continue
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            end = s.rfind("}") + 1
            if end > 0:
                try:
                    return json.loads(s[:end])
                except json.JSONDecodeError:
                    pass
    return None


async def _call(client: AsyncGroq, image_b64: str, prompt: str,
                sem: asyncio.Semaphore, *, timeout_s: float,
                ) -> tuple[str, int, str, dict[str, object | None]]:
    """Return (raw_content, latency_ms, error_str_or_empty,
    groq_* metadata dict — see groq_completion_metadata).

    Retries up to ``MAX_ATTEMPTS`` times: on **429** (rate limit) with
    exponential backoff (+ optional ``retry_after`` hint), and on
    ``asyncio.wait_for`` **TimeoutError** with a short fixed backoff.
    Groq's llama-4-scout TPM ceiling (300k) bites at concurrency≥4 with
    full image payloads (~3.8k tokens/call), so we pace patiently.
    """
    async with sem:
        t0 = time.time()
        for attempt in range(MAX_ATTEMPTS):
            try:
                resp = await asyncio.wait_for(
                    client.chat.completions.create(
                        model=MODEL,
                        temperature=TEMPERATURE,
                        max_tokens=MAX_TOKENS,
                        messages=[{
                            "role": "user",
                            "content": [
                                {"type": "image_url",
                                 "image_url": {
                                     "url": f"data:image/jpeg;base64,{image_b64}"}},
                                {"type": "text", "text": prompt},
                            ],
                        }],
                    ),
                    timeout=timeout_s,
                )
                ms = int((time.time() - t0) * 1000)
                gmeta = groq_completion_metadata(
                    resp, attempt_count=attempt + 1, latency_ms=ms)
                txt = ""
                try:
                    txt = resp.choices[0].message.content or ""
                    txt = txt.strip()
                except Exception as e_txt:
                    print(f"[run_shadow.py] WARN: response body read "
                          f"{type(e_txt).__name__}: "
                          f"{str(e_txt)[:120]}",
                          file=sys.stderr)
                return txt, ms, "", gmeta
            except (asyncio.TimeoutError, TimeoutError):
                # asyncio.wait_for expiry (per-attempt timeout_s ceiling).
                # On some Python versions asyncio uses ``asyncio.TimeoutError``,
                # which is not always ``builtins.TimeoutError``.
                if attempt < MAX_ATTEMPTS - 1:
                    await asyncio.sleep(TIMEOUT_RETRY_BACKOFF_S)
                    continue
                ms = int((time.time() - t0) * 1000)
                terr = asyncio.TimeoutError()
                gfail = groq_completion_metadata(
                    None, attempt_count=attempt + 1, latency_ms=ms)
                return "", ms, (
                    f"{type(terr).__name__}: {str(terr)[:200]}"), gfail
            except Exception as e:
                msg = str(e)
                is_429 = "429" in msg or "rate_limit" in msg.lower()
                if is_429 and attempt < MAX_ATTEMPTS - 1:
                    delay = 2.0 * (2 ** attempt)  # 2, 4, 8, 16s
                    m = re.search(r"try again in ([\d.]+)s", msg)
                    if m:
                        delay = max(delay, float(m.group(1)) + 0.5)
                    await asyncio.sleep(delay)
                    continue
                ms = int((time.time() - t0) * 1000)
                gfail = groq_completion_metadata(
                    None, attempt_count=attempt + 1, latency_ms=ms)
                return "", ms, f"{type(e).__name__}: {msg[:200]}", gfail
        ms = int((time.time() - t0) * 1000)
        gex = groq_completion_metadata(
            None, attempt_count=MAX_ATTEMPTS, latency_ms=ms)
        return "", ms, "retry_exhausted", gex


async def _run_one(client: AsyncGroq, sem: asyncio.Semaphore,
                   frame: dict, variant_name: str, replicate: int,
                   frames_dir: Path, *,
                   timeout_s: float,
                   ) -> dict:
    path = _FILES / frame["path"]
    # Prefer the snapshotted copy (survives debug_frames/ clearing).
    snap = frames_dir / path.name
    if snap.exists():
        path = snap
    image_b64 = _encode(path)
    variant = VARIANTS[variant_name]
    raw, ms, err, gmeta = await _call(
        client, image_b64, variant["prompt"], sem, timeout_s=timeout_s)
    tag = _parse_tag(raw) if raw else None
    raw_cam = tag.get("camera_view") if tag else None
    raw_phase = tag.get("frame_phase") if tag else None
    cam, phase = canon(raw_cam, raw_phase, variant["alias"])
    row = {
        "frame_id": frame["frame_id"],
        "variant": variant_name,
        "replicate": replicate,
        "raw_camera_view": raw_cam,
        "raw_frame_phase": raw_phase,
        "canon_camera_view": cam,
        "canon_frame_phase": phase,
        "latency_ms": ms,
        "error": err,
        "raw_first_200": (raw or "")[:200],
    }
    row.update(gmeta)
    return row


async def main(
        concurrency: int,
        dry_run: bool,
        variant_filter: list[str] | None,
        corpus_path: Path,
        out_path: Path,
        frames_dir: Path,
        resume: bool,
        *,
        timeout_s: float,
        ) -> None:
    groq_key = _groq_api_key()
    if not groq_key and not dry_run:
        print("ERROR: GROQ_API_KEY not set and eyes.config fallback missing",
              file=sys.stderr)
        sys.exit(1)

    frames = load_corpus(corpus_path)
    if variant_filter:
        unknown = [v for v in variant_filter if v not in VARIANTS]
        if unknown:
            print(f"ERROR: unknown variants: {unknown}; "
                  f"known: {sorted(VARIANTS.keys())}", file=sys.stderr)
            sys.exit(2)
        variants = variant_filter
    else:
        variants = list(VARIANTS.keys())
    planned = [
        (f, v, r)
        for f in frames
        for v in variants
        for r in range(1, REPLICATES + 1)
    ]
    print(f"Planned calls: {len(planned)} "
          f"({len(frames)} frames × {len(variants)} variants × {REPLICATES} reps)")
    print(f"Variants to run: {variants}")

    existing: dict[tuple[str, str, int], dict] = {}
    if resume and out_path.exists():
        with out_path.open() as f:
            prev = json.load(f)
        for r in prev.get("results", []):
            existing[(r["frame_id"], r["variant"], r["replicate"])] = r
        print(f"Resuming: {len(existing)} prior results on disk")

    todo = [t for t in planned
            if (t[0]["frame_id"], t[1], t[2]) not in existing]
    print(f"To run:         {len(todo)}")

    if dry_run:
        print("Dry run, exiting.")
        return

    sem = asyncio.Semaphore(concurrency)
    # HTTP client ceiling must exceed per-attempt asyncio.wait_for timeout.
    http_timeout_s = max(timeout_s + 12.0, 25.0)
    client = AsyncGroq(api_key=groq_key or "", timeout=http_timeout_s)

    results: list[dict] = list(existing.values())
    done = 0
    t_start = time.time()

    async def _wrap(item):
        nonlocal done
        f, v, r = item
        res = await _run_one(
            client, sem, f, v, r, frames_dir, timeout_s=timeout_s)
        results.append(res)
        done += 1
        if done % 10 == 0 or done == len(todo):
            elapsed = time.time() - t_start
            rate = done / max(elapsed, 0.01)
            eta = (len(todo) - done) / max(rate, 0.01)
            errs = sum(1 for x in results if x.get("error"))
            print(f"  [{done:3d}/{len(todo):3d}] "
                  f"{rate:.1f} calls/s, ETA {eta:.0f}s, errors={errs}")

    tasks = [asyncio.create_task(_wrap(item)) for item in todo]
    await asyncio.gather(*tasks)
    await client.close()

    try:
        corpus_rel = str(corpus_path.relative_to(_FILES))
    except ValueError:
        corpus_rel = str(corpus_path)
    payload = {
        "model": MODEL,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "replicates_per_pair": REPLICATES,
        "corpus": corpus_rel,
        "variants": list(variants),
        "total_calls": len(results),
        "results": results,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump(payload, f, indent=2)
    try:
        out_rel = out_path.relative_to(_FILES)
    except ValueError:
        out_rel = out_path
    print(f"\nWrote {out_rel} "
          f"({len(results)} results)")


def build_run_shadow_arg_parser() -> argparse.ArgumentParser:
    """CLI used by ``__main__`` and tests (``--timeout-s``, etc.)."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--concurrency", type=int, default=4,
                    help="Max concurrent Groq tasks (default: 4).")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--corpus",
        type=str,
        default=str(DEFAULT_CORPUS.relative_to(_FILES)),
        help="Corpus JSON under files/ or absolute path (default: docs/scout_corpus_v1.json)",
    )
    ap.add_argument(
        "--output", "-o",
        type=str,
        default=str(DEFAULT_OUT.relative_to(_FILES)),
        help="Shadow output JSON path (default: docs/shadow_run_v1.json)",
    )
    ap.add_argument(
        "--frames-dir",
        type=str,
        default=str(DEFAULT_FRAMES_DIR.relative_to(_FILES)),
        help="Directory of snapshot JPEGs (default: docs/corpus_frames_v1)",
    )
    ap.add_argument(
        "--resume",
        dest="resume",
        action="store_true",
        default=True,
        help="Reuse existing triples from output JSON (default: on)",
    )
    ap.add_argument(
        "--no-resume",
        dest="resume",
        action="store_false",
        help="Ignore prior output file; all planned calls run fresh",
    )
    ap.add_argument("--variants", type=str, default=None,
                    help="Comma-separated variant names to run "
                         "(default: all). Resume still skips triples "
                         "already present in the output unless "
                         "--no-resume.")
    ap.add_argument(
        "--timeout-s", type=float, default=TIMEOUT_S,
        help=(
            "Per-attempt asyncio timeout for each Groq "
            "chat.completions.create (default: %(default)s)."
        ))
    return ap


if __name__ == "__main__":
    args = build_run_shadow_arg_parser().parse_args()
    vf = ([v.strip() for v in args.variants.split(",") if v.strip()]
          if args.variants else None)
    corp = resolve_under_files(args.corpus)
    outp = resolve_under_files(args.output)
    fdir = resolve_under_files(args.frames_dir)
    asyncio.run(main(
        args.concurrency,
        args.dry_run,
        vf,
        corp,
        outp,
        fdir,
        args.resume,
        timeout_s=args.timeout_s,
    ))

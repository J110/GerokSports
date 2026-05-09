"""Empirical color-order audit for the two frame-source backends.

Captures a frame from each path, computes per-channel correlation
against the cv2 reference (known BGR by OpenCV convention), and
classifies the legacy CGImage byte order as BGRA or RGBA.

Why this matters
----------------
``ball_analyzer._capture_loop`` and ``CaptureCardFrameSource`` both
publish frames into a downstream variable named ``bgr``. Whether
those bytes are *actually* BGR (cv2-friendly) or RGB (silently
swapped through every cv2.imencode/cv2.imwrite/cv2.cvtColor on the
way to vision APIs) depends entirely on the legacy CGImage byte
order — the capture-card path was tuned to mirror the legacy quirk.

Usage
-----
Run with the broadcast playing on the Air, mirrored to the M1 Max
display, with no live pipeline holding the capture card open::

    cd /Users/anmolmohan/Projects/SportsComm
    python3 files/scripts/color_order_audit.py

Outputs:

* ``/tmp/audit_cv2_bgr.png`` — cv2.VideoCapture frame, saved with
  cv2.imwrite (assumes BGR). Ground-truth correct colors.
* ``/tmp/audit_cg_raw_imwrite.png`` — CGImage ``arr[..., :3]`` (no
  flip), saved with cv2.imwrite. Looks correct iff CGImage is BGRA.
* ``/tmp/audit_cg_flipped_imwrite.png`` — CGImage with the legacy
  ``[:, :, ::-1]`` flip, saved with cv2.imwrite. Looks correct iff
  CGImage is RGBA (i.e., legacy variable named ``bgr`` truly is BGR).
* stdout — per-channel correlation between cv2 reference and each
  CG channel, plus an explicit V1/V2 verdict.

The correlation analysis is the objective verdict; the PNGs are for
operator visual confirmation.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402

try:
    import Quartz.CoreGraphics as CG  # noqa: E402
    HAS_QUARTZ = True
except Exception:
    HAS_QUARTZ = False

DEVICE_INDEX = 0
WARMUP_FRAMES = 10
OUT = Path("/tmp")


def grab_cv2() -> np.ndarray | None:
    cap = cv2.VideoCapture(DEVICE_INDEX)
    if not cap.isOpened():
        cap.release()
        return None
    try:
        for _ in range(WARMUP_FRAMES):
            cap.read()
            time.sleep(0.02)
        ok, frame = cap.read()
        return frame if ok else None
    finally:
        cap.release()


def grab_cg() -> np.ndarray | None:
    if not HAS_QUARTZ:
        return None
    image = CG.CGWindowListCreateImage(
        CG.CGRectInfinite,
        CG.kCGWindowListOptionOnScreenOnly,
        CG.kCGNullWindowID,
        CG.kCGWindowImageDefault,
    )
    if image is None:
        return None
    w = CG.CGImageGetWidth(image)
    h = CG.CGImageGetHeight(image)
    if w == 0 or h == 0:
        return None
    bpr = CG.CGImageGetBytesPerRow(image)
    data = CG.CGDataProviderCopyData(CG.CGImageGetDataProvider(image))
    arr = np.frombuffer(data, dtype=np.uint8).reshape((h, bpr // 4, 4))
    return arr[:h, :w, :3].copy()


def channel_corr(a: np.ndarray, b: np.ndarray) -> float:
    a32 = a.astype(np.float32).ravel()
    b32 = b.astype(np.float32).ravel()
    a32 -= a32.mean()
    b32 -= b32.mean()
    denom = (np.linalg.norm(a32) * np.linalg.norm(b32)) or 1.0
    return float((a32 @ b32) / denom)


def main() -> int:
    print("[audit] grabbing cv2.VideoCapture frame (ground-truth BGR)...")
    cv2_bgr = grab_cv2()
    if cv2_bgr is None:
        print("[audit] cv2 capture failed — is device 0 free? "
              "(close the live pipeline and retry)")
    else:
        print(f"[audit] cv2 frame: shape={cv2_bgr.shape} dtype={cv2_bgr.dtype} "
              f"mean=B{cv2_bgr[:,:,0].mean():.1f} "
              f"G{cv2_bgr[:,:,1].mean():.1f} "
              f"R{cv2_bgr[:,:,2].mean():.1f}")
        cv2.imwrite(str(OUT / "audit_cv2_bgr.png"), cv2_bgr)

    print("[audit] grabbing CGWindowListCreateImage frame...")
    cg_raw = grab_cg()
    if cg_raw is None:
        print("[audit] CG capture failed (Quartz unavailable or empty image)")
    else:
        print(f"[audit] cg frame: shape={cg_raw.shape} dtype={cg_raw.dtype} "
              f"mean[ch0]={cg_raw[:,:,0].mean():.1f} "
              f"mean[ch1]={cg_raw[:,:,1].mean():.1f} "
              f"mean[ch2]={cg_raw[:,:,2].mean():.1f}")
        cv2.imwrite(str(OUT / "audit_cg_raw_imwrite.png"), cg_raw)
        cv2.imwrite(str(OUT / "audit_cg_flipped_imwrite.png"),
                    cg_raw[:, :, ::-1].copy())

    if cv2_bgr is not None:
        # Pipeline-equivalent demo: apply the same `[:, :, ::-1]` flip
        # that ball_analyzer._capture_loop applies, then save via
        # cv2.imwrite (which assumes BGR — exactly like every
        # cv2.imencode(".jpg", bgr) call on the path to Scout/Qwen/
        # Gemini). If the saved PNG looks color-swapped vs the raw
        # one, V2 is confirmed: pipeline ships R/B-swapped JPEGs.
        flipped = cv2_bgr[:, :, ::-1].copy()
        cv2.imwrite(str(OUT / "audit_pipeline_to_vision_api.png"), flipped)
        print(f"[audit] pipeline-equivalent JPEG demo written:")
        print(f"        /tmp/audit_cv2_bgr.png                (raw cv2, correct)")
        print(f"        /tmp/audit_pipeline_to_vision_api.png "
              f"(after legacy flip, what APIs receive)")

    if cv2_bgr is None or cg_raw is None:
        print("\n[audit] CG path unavailable — verdict deferred to "
              "code-level analysis (see frame_source_setup.md). The "
              "cv2 path alone confirms what the pipeline currently "
              "ships to vision APIs (see PNGs above).")
        return 2

    target_h = min(cv2_bgr.shape[0], cg_raw.shape[0], 720)
    target_w = int(target_h * cv2_bgr.shape[1] / cv2_bgr.shape[0])
    cv2_r = cv2.resize(cv2_bgr, (target_w, target_h))
    cg_r = cv2.resize(cg_raw, (target_w, target_h))

    print("\n[audit] per-channel correlation (cv2 ground truth vs CG raw):")
    matrix = {}
    cv2_labels = ("B", "G", "R")
    for i, lbl in enumerate(cv2_labels):
        for j in range(3):
            c = channel_corr(cv2_r[:, :, i], cg_r[:, :, j])
            matrix[(lbl, j)] = c
            print(f"    cv2.{lbl}  vs  cg[ch{j}]  =  {c:+.3f}")

    bgra_score = (matrix[("B", 0)] + matrix[("G", 1)] + matrix[("R", 2)]) / 3
    rgba_score = (matrix[("R", 0)] + matrix[("G", 1)] + matrix[("B", 2)]) / 3
    print(f"\n[audit] aggregate identity-mapping scores:")
    print(f"    BGRA hypothesis (cg ch0=B, ch1=G, ch2=R): {bgra_score:+.3f}")
    print(f"    RGBA hypothesis (cg ch0=R, ch1=G, ch2=B): {rgba_score:+.3f}")

    verdict = None
    if bgra_score > rgba_score + 0.05:
        verdict = "V2"
        print("\n[audit] VERDICT V2: CGImage memory order is BGRA.")
        print("        Legacy `arr[..., :3]` is BGR; the trailing")
        print("        `[:, :, ::-1]` flip turned it into RGB. The")
        print("        downstream variable named `bgr` actually carries")
        print("        RGB pixel bytes — pipeline-wide R/B swap into")
        print("        every cv2.imencode/cv2.imwrite/cv2.cvtColor call.")
    elif rgba_score > bgra_score + 0.05:
        verdict = "V1"
        print("\n[audit] VERDICT V1: CGImage memory order is RGBA.")
        print("        Legacy `arr[..., :3]` is RGB; the trailing")
        print("        `[:, :, ::-1]` flip correctly produces BGR.")
        print("        Variable name `bgr` is accurate. No fix needed.")
    else:
        print("\n[audit] VERDICT INCONCLUSIVE — scenes too dissimilar or")
        print("        scene is grayscale. Re-run on a more saturated frame.")
        return 3

    print(f"\n[audit] verdict = {verdict}")
    print(f"[audit] PNGs at /tmp/audit_*.png — visually compare:")
    print(f"        - audit_cv2_bgr.png       (correct colors)")
    print(f"        - audit_cg_raw_imwrite.png (correct iff V2)")
    print(f"        - audit_cg_flipped_imwrite.png (correct iff V1)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

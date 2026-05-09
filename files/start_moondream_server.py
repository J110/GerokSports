"""Minimal Moondream REST server using the MLX backend directly.

Exposes the same /v1/detect endpoint that the moondream Python SDK expects,
backed by the MLX backend from moondream-station (no REPL needed).

Usage:
    .venv/bin/python3 start_moondream_server.py [--port 2020]

Requires: mlx, tokenizers, Pillow, huggingface_hub, uvicorn, fastapi
"""
import os
import sys
import signal
import argparse
import logging

os.environ.setdefault("HF_TOKEN", "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")
os.environ.setdefault("HUGGING_FACE_HUB_TOKEN", os.environ["HF_TOKEN"])

BACKEND_DIR = os.path.expanduser(
    "~/.moondream-station/models/backends/mlx_backend_v2"
)
sys.path.insert(0, BACKEND_DIR)

import backend as mlx_backend  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("moondream-server")


def build_app():
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse

    app = FastAPI(title="Moondream MLX Server")

    @app.get("/health")
    async def health():
        return {"status": "ok", "server": "moondream-mlx"}

    @app.get("/")
    async def root():
        return {"status": "ok", "server": "moondream-mlx"}

    @app.post("/v1/detect")
    async def detect(request: Request):
        body = await request.json()
        result = mlx_backend.detect(**body)
        return JSONResponse(result)

    @app.post("/v1/caption")
    async def caption(request: Request):
        body = await request.json()
        result = mlx_backend.caption(**body)
        return JSONResponse(result)

    @app.post("/v1/query")
    async def query(request: Request):
        body = await request.json()
        result = mlx_backend.query(**body)
        return JSONResponse(result)

    @app.post("/v1/point")
    async def point(request: Request):
        body = await request.json()
        result = mlx_backend.point(**body)
        return JSONResponse(result)

    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=2020)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--quantize", default="int4",
                        help="Quantization mode: int4, int8, or none")
    args = parser.parse_args()

    log.info("Initializing MLX backend (quantize=%s)...", args.quantize)
    q = args.quantize if args.quantize != "none" else None
    mlx_backend.init_backend(quantize=q)

    log.info("Warming up model (first load downloads weights ~2GB)...")
    mlx_backend._get_model()
    log.info("Model loaded and ready.")

    app = build_app()

    import uvicorn

    def handle_signal(sig, frame):
        log.info("Shutting down...")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    log.info("Starting server on http://%s:%d", args.host, args.port)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()

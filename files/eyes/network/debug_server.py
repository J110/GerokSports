"""Debug UI server — serves the war room dashboard + SSE event stream."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

import cv2
import numpy as np
from aiohttp import web

from eyes.config import DEBUG_PORT

logger = logging.getLogger(__name__)

UI_DIR = Path(__file__).parent.parent / "ui"


class DebugUI:
    """Serves debug dashboard on localhost:8001 with SSE real-time updates.

    Endpoints:
        GET /              → debug HTML page
        GET /stream        → SSE event stream
        GET /state         → full match state JSON
        GET /scorecard     → LiveScorecard JSON
        GET /field         → FieldMemory JSON
        GET /micro         → MicroAnalysis JSON
        GET /validation    → AutoValidator report JSON
        GET /preview       → current frame JPEG
        GET /llm-output    → last LLM extraction JSON
        POST /select-window → set capture window
        GET /windows       → list browser windows
    """

    def __init__(self):
        self._app = web.Application()
        self._runner: web.AppRunner | None = None
        self._subscribers: list[asyncio.Queue] = []
        self._preview_jpeg: bytes | None = None
        self._last_llm_output: dict | None = None
        self._state_getters: dict = {}
        self._window_selector = None
        self._setup_routes()

    def _setup_routes(self):
        self._app.router.add_get("/", self._handle_index)
        self._app.router.add_get("/stream", self._handle_sse)
        self._app.router.add_get("/state", self._handle_state)
        self._app.router.add_get("/scorecard", self._handle_scorecard)
        self._app.router.add_get("/field", self._handle_field)
        self._app.router.add_get("/micro", self._handle_micro)
        self._app.router.add_get("/validation", self._handle_validation)
        self._app.router.add_get("/preview", self._handle_preview)
        self._app.router.add_get("/llm-output", self._handle_llm_output)
        self._app.router.add_post("/select-window", self._handle_select_window)
        self._app.router.add_get("/windows", self._handle_list_windows)

    def set_state_getters(
        self,
        scorecard=None,
        field=None,
        micro=None,
        validation=None,
        full_state=None,
        list_windows=None,
        select_window=None,
    ):
        """Register callbacks for fetching current state."""
        if scorecard:
            self._state_getters["scorecard"] = scorecard
        if field:
            self._state_getters["field"] = field
        if micro:
            self._state_getters["micro"] = micro
        if validation:
            self._state_getters["validation"] = validation
        if full_state:
            self._state_getters["full_state"] = full_state
        if list_windows:
            self._state_getters["list_windows"] = list_windows
        if select_window:
            self._window_selector = select_window

    async def start(self, port: int | None = None):
        port = port or DEBUG_PORT
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", port)
        await site.start()
        logger.info("Debug UI running at http://localhost:%d", port)

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()

    async def emit(self, event_type: str, data: dict):
        """Push an SSE event to all connected clients."""
        if event_type == "llm_output":
            self._last_llm_output = data

        msg = f"event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"
        dead = []
        for q in self._subscribers:
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self._subscribers.remove(q)

    async def update_preview(self, frame: np.ndarray):
        """Update the preview JPEG from the current frame."""
        try:
            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            self._preview_jpeg = buf.tobytes()
        except Exception as e:
            logger.debug("Preview encode failed: %s", e)

    # --- Route handlers ---

    async def _handle_index(self, request: web.Request) -> web.Response:
        html_path = UI_DIR / "debug.html"
        if html_path.exists():
            return web.FileResponse(html_path)
        return web.Response(text="Debug UI not found", status=404)

    async def _handle_sse(self, request: web.Request) -> web.StreamResponse:
        response = web.StreamResponse(
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
            }
        )
        await response.prepare(request)

        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subscribers.append(q)

        try:
            while True:
                msg = await q.get()
                await response.write(msg.encode("utf-8"))
        except (asyncio.CancelledError, ConnectionResetError):
            pass
        finally:
            if q in self._subscribers:
                self._subscribers.remove(q)
        return response

    async def _handle_state(self, request: web.Request) -> web.Response:
        getter = self._state_getters.get("full_state")
        data = getter() if getter else {}
        return web.json_response(data, dumps=lambda x: json.dumps(x, default=str))

    async def _handle_scorecard(self, request: web.Request) -> web.Response:
        getter = self._state_getters.get("scorecard")
        data = getter() if getter else {}
        return web.json_response(data, dumps=lambda x: json.dumps(x, default=str))

    async def _handle_field(self, request: web.Request) -> web.Response:
        getter = self._state_getters.get("field")
        data = getter() if getter else {}
        return web.json_response(data, dumps=lambda x: json.dumps(x, default=str))

    async def _handle_micro(self, request: web.Request) -> web.Response:
        getter = self._state_getters.get("micro")
        data = getter() if getter else {}
        return web.json_response(data, dumps=lambda x: json.dumps(x, default=str))

    async def _handle_validation(self, request: web.Request) -> web.Response:
        getter = self._state_getters.get("validation")
        data = getter() if getter else {}
        return web.json_response(data, dumps=lambda x: json.dumps(x, default=str))

    async def _handle_preview(self, request: web.Request) -> web.Response:
        if self._preview_jpeg:
            return web.Response(body=self._preview_jpeg, content_type="image/jpeg")
        return web.Response(text="No preview available", status=404)

    async def _handle_llm_output(self, request: web.Request) -> web.Response:
        if self._last_llm_output:
            return web.json_response(
                self._last_llm_output, dumps=lambda x: json.dumps(x, default=str)
            )
        return web.json_response({})

    async def _handle_select_window(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
            window_id = body.get("window_id")
            if window_id is not None and self._window_selector:
                self._window_selector(int(window_id))
                return web.json_response({"status": "ok", "window_id": window_id})
            return web.json_response({"error": "window_id required"}, status=400)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def _handle_list_windows(self, request: web.Request) -> web.Response:
        getter = self._state_getters.get("list_windows")
        windows = getter() if getter else []
        return web.json_response(windows)

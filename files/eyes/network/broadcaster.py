"""HTTP broadcaster — sends extracted data to the cloud server."""
from __future__ import annotations

import asyncio
import json
import time
from collections import deque

import aiohttp

from eyes.config import SERVER_URL
from eyes.cricket_logger import CricketLogger

log = CricketLogger("NET")


class Broadcaster:
    """Sends match data to Machine 2 (cloud server) via HTTP POST.

    Endpoints:
        POST /ingest/ball     — immediate on ball event
        POST /ingest/state    — periodic full state
        POST /ingest/graphic  — on broadcast graphic detection
        POST /ingest/event    — on state changes (ads, timeouts, etc.)
    """

    def __init__(self, server_url: str | None = None):
        self._url = server_url or SERVER_URL
        self._session: aiohttp.ClientSession | None = None
        self._connected = False
        self._total_sent = 0
        self._total_errors = 0
        self._send_times: deque[float] = deque(maxlen=30)
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=100)

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=5)
            )

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def send_ball(self, ball: dict):
        await self._post("/ingest/ball", ball)

    async def send_state(self, state: dict):
        await self._post("/ingest/state", state)

    async def send_graphic(self, graphic: dict):
        await self._post("/ingest/graphic", graphic)

    async def send_event(self, event: dict):
        await self._post("/ingest/event", event)

    async def _post(self, path: str, data: dict):
        await self._ensure_session()
        url = f"{self._url}{path}"
        start = time.monotonic()

        try:
            async with self._session.post(url, json=data) as resp:
                elapsed = time.monotonic() - start
                elapsed_ms = int(elapsed * 1000)
                self._send_times.append(elapsed)
                self._total_sent += 1

                if resp.status == 200:
                    self._connected = True
                    event_desc = path.split("/")[-1]
                    log.info(f"Sent {event_desc} to server → 200 OK ({elapsed_ms}ms)")
                    if elapsed_ms > 500:
                        log.warn(f"Server response slow: {elapsed_ms}ms (>500ms threshold)")
                else:
                    text = await resp.text()
                    log.warn(f"Server returned {resp.status} — will retry in 5s")

        except aiohttp.ClientConnectorError:
            self._total_errors += 1
            self._connected = False
            log.error(f"Server unreachable at {self._url} — connection refused")
        except asyncio.TimeoutError:
            self._total_errors += 1
            log.error(f"Timeout sending {path.split('/')[-1]} event after 10s — dropping")
        except Exception as e:
            self._total_errors += 1
            log.error(f"Broadcast error ({path}): {e}")

    def is_connected(self) -> bool:
        return self._connected

    def get_stats(self) -> dict:
        avg_latency = (
            sum(self._send_times) / len(self._send_times)
            if self._send_times
            else 0
        )
        return {
            "server_url": self._url,
            "connected": self._connected,
            "total_sent": self._total_sent,
            "total_errors": self._total_errors,
            "avg_latency_ms": int(avg_latency * 1000),
        }

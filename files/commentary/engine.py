"""Machine 2: Commentary Engine.

Subscribes to Machine 1's WebSocket, detects ball events,
generates commentary from 4 personalities, broadcasts to UI.
"""
from __future__ import annotations

import asyncio
import json
import time

import websockets
from groq import AsyncGroq

from eyes.config import GROQ_API_KEY
from commentary.personalities import PERSONALITIES
from commentary.context_builder import ContextBuilder
from commentary.moment_detector import MomentDetector

MACHINE1_WS = "ws://localhost:8765"
COMMENTARY_PORT = 8766


class CommentaryEngine:
    def __init__(self):
        self.groq = AsyncGroq(api_key=GROQ_API_KEY)
        self.context = ContextBuilder()
        self.detector = MomentDetector()
        self.commentary_log: list[dict] = []
        self.clients: set = set()
        self._prev_state: dict | None = None

    async def on_state_update(self, state: dict):
        ball_event = self._detect_ball_from_state(state)
        over_change = self._detect_over_change(state)

        if not ball_event and not over_change:
            self._prev_state = state
            return

        triggers = self.detector.classify(state, ball_event, over_change)
        if not triggers:
            self._prev_state = state
            return

        if ball_event:
            ctx = self.context.build_ball_context(state, ball_event)
        elif over_change:
            ctx = self.context.build_over_context(state, over_change)
        else:
            ctx = self.context.build_ball_context(state, {"type": "UPDATE"})

        prompt_text = self.context.format_for_prompt(ctx)
        tag = ball_event.get("type", "?") if ball_event else "OVER_END"
        over_str = state.get("scorecard", {}).get("overs", "?")
        print(f"[COMM] {over_str} {tag} → generating: {triggers}")

        tasks = [
            self._generate(name, PERSONALITIES[name], prompt_text, state)
            for name in triggers
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, dict):
                self.commentary_log.append(result)
                self.context.recent_commentary.append(
                    result.get("text", "")[:100])
                await self._broadcast(result)
                print(f"  [{result['persona'].upper()}] "
                      f"{result['text'][:80]}...")

        self._prev_state = state

    async def _generate(self, name: str, persona: dict,
                        prompt_text: str, state: dict) -> dict | None:
        config = persona["config"]
        t0 = time.time()
        try:
            response = await self.groq.chat.completions.create(
                model=config["model"],
                temperature=config["temperature"],
                max_tokens=config["max_tokens"],
                messages=[
                    {"role": "system", "content": persona["system"]},
                    {"role": "user", "content": prompt_text},
                ],
            )
            text = response.choices[0].message.content.strip()
            ms = int((time.time() - t0) * 1000)
            sc = state.get("scorecard", {})
            return {
                "persona": name,
                "text": text,
                "timestamp": time.time(),
                "over": sc.get("overs", "?"),
                "score": f"{sc.get('score', 0)}/{sc.get('wickets', 0)}",
                "latency_ms": ms,
            }
        except Exception as e:
            print(f"[COMM] {name} error: {e}")
            return None

    def _detect_ball_from_state(self, state: dict) -> dict | None:
        if not self._prev_state:
            return None
        prev_sc = self._prev_state.get("scorecard", {})
        curr_sc = state.get("scorecard", {})
        prev_ov = prev_sc.get("overs")
        curr_ov = curr_sc.get("overs")
        if not prev_ov or not curr_ov or prev_ov == curr_ov:
            return None
        prev_b = self._to_balls(prev_ov)
        curr_b = self._to_balls(curr_ov)
        if curr_b - prev_b != 1:
            return None
        s_delta = (curr_sc.get("score") or 0) - (prev_sc.get("score") or 0)
        w_delta = (curr_sc.get("wickets") or 0) - (prev_sc.get("wickets") or 0)
        if w_delta > 0:
            return {"type": "WICKET", "runs": s_delta,
                    "over": curr_ov, "certain": True}
        if s_delta == 0:
            return {"type": "DOT", "runs": 0,
                    "over": curr_ov, "certain": True}
        if s_delta == 4:
            return {"type": "FOUR", "runs": 4,
                    "over": curr_ov, "certain": True}
        if s_delta == 6:
            return {"type": "SIX", "runs": 6,
                    "over": curr_ov, "certain": True}
        return {"type": f"{s_delta}_RUNS", "runs": s_delta,
                "over": curr_ov, "certain": True}

    def _detect_over_change(self, state: dict) -> dict | None:
        if not self._prev_state:
            return None
        curr = state.get("scorecard", {}).get("overs")
        prev = self._prev_state.get("scorecard", {}).get("overs")
        if not curr or not prev:
            return None
        if int(float(curr)) > int(float(prev)):
            return state.get("over_history", {}).get(
                str(int(float(prev))), {})
        return None

    @staticmethod
    def _to_balls(overs) -> int:
        o = float(overs or "0")
        return int(o) * 6 + round((o % 1) * 10)

    async def _broadcast(self, entry: dict):
        payload = json.dumps({"type": "commentary", "entry": entry})
        dead: list = []
        for client in self.clients:
            try:
                await client.send(payload)
            except Exception:
                dead.append(client)
        for c in dead:
            self.clients.discard(c)


async def main():
    engine = CommentaryEngine()

    async def ws_handler(websocket):
        engine.clients.add(websocket)
        print(f"[COMM] UI client connected ({len(engine.clients)} total)")
        for entry in engine.commentary_log[-20:]:
            await websocket.send(
                json.dumps({"type": "commentary", "entry": entry}))
        try:
            async for _ in websocket:
                pass
        finally:
            engine.clients.discard(websocket)
            print(f"[COMM] UI client disconnected ({len(engine.clients)} total)")

    ws_server = await websockets.serve(ws_handler, "0.0.0.0", COMMENTARY_PORT)
    print(f"[COMM] Commentary server on ws://0.0.0.0:{COMMENTARY_PORT}")

    while True:
        try:
            async with websockets.connect(MACHINE1_WS) as ws:
                print("[COMM] Connected to Machine 1")
                async for message in ws:
                    try:
                        state = json.loads(message)
                        if state.get("type") == "state_update":
                            await engine.on_state_update(state)
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            print(f"[COMM] Machine 1 disconnected: {e}")
            await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import json

from fastapi import WebSocket


class ConnectionManager:
    """Broadcasts real-time events to all connected clients.

    `broadcast` is safe to call from FastAPI's sync route handlers (which run in a
    threadpool) — it schedules the coroutine onto the captured event loop.
    Each message is `{"event": <name>, "data": <payload>}`; clients filter by event.
    """

    def __init__(self) -> None:
        self.active: list[WebSocket] = []
        self.loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active:
            self.active.remove(websocket)

    async def _broadcast(self, message: str) -> None:
        dead: list[WebSocket] = []
        for ws in list(self.active):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    def broadcast(self, event: str, data: dict) -> None:
        message = json.dumps({"event": event, "data": data}, default=str)
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self._broadcast(message), self.loop)


manager = ConnectionManager()

"""
websocket_bridge.py — WebSocket-мост Аргоса (клиент и сервер).
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Callable

try:
    import websockets
    import websockets.asyncio.client
    import websockets.asyncio.server
except ImportError:  # pragma: no cover
    websockets = None  # type: ignore[assignment]


class WebSocketBridge:
    """WebSocket клиент + сервер для двунаправленной связи."""

    def __init__(
        self,
        server_host: str | None = None,
        server_port: int | None = None,
        timeout: float = 10.0,
    ):
        self.server_host = server_host or os.getenv("WS_HOST", "0.0.0.0")
        self.server_port = int(server_port or os.getenv("WS_PORT", "8765"))
        self.timeout = timeout
        self._server: Any = None

    @staticmethod
    def available() -> bool:
        """True если библиотека websockets установлена."""
        return websockets is not None

    # ── клиент ────────────────────────────────────────────────────────
    async def send_message(self, url: str, data: str | dict) -> dict[str, Any]:
        """Подключиться к WS-серверу и отправить сообщение."""
        if websockets is None:
            return {"ok": False, "provider": "websocket", "error": "websockets package is not installed"}

        payload = json.dumps(data) if isinstance(data, dict) else data
        try:
            async with websockets.asyncio.client.connect(url, close_timeout=self.timeout) as ws:
                await ws.send(payload)
                reply = await asyncio.wait_for(ws.recv(), timeout=self.timeout)
            return {"ok": True, "provider": "websocket", "data": reply}
        except Exception as exc:
            return {"ok": False, "provider": "websocket", "error": str(exc)}

    def send_message_sync(self, url: str, data: str | dict) -> dict[str, Any]:
        """Синхронная обёртка над send_message."""
        return asyncio.get_event_loop().run_until_complete(self.send_message(url, data))

    # ── сервер ────────────────────────────────────────────────────────
    async def start_server(self, handler: Callable | None = None) -> dict[str, Any]:
        """Запустить WebSocket-сервер."""
        if websockets is None:
            return {"ok": False, "provider": "websocket", "error": "websockets package is not installed"}

        async def _default_handler(ws: Any) -> None:
            async for message in ws:
                await ws.send(f"echo: {message}")

        cb = handler or _default_handler
        try:
            self._server = await websockets.asyncio.server.serve(
                cb, self.server_host, self.server_port,
            )
            return {
                "ok": True,
                "provider": "websocket",
                "data": f"ws://{self.server_host}:{self.server_port}",
            }
        except Exception as exc:
            return {"ok": False, "provider": "websocket", "error": str(exc)}

    async def stop_server(self) -> None:
        """Остановить WebSocket-сервер."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

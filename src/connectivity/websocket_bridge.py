"""
src/connectivity/websocket_bridge.py — WebSocket мост ARGOS
Сервер: asyncio + websockets
Клиент: синхронная обёртка через websockets.sync
"""
from __future__ import annotations

import asyncio
import json
import threading
from typing import Callable, Any

try:
    import websockets
    import websockets.sync.client as _ws_sync_client
    _WS_AVAILABLE = True
except ImportError:
    _WS_AVAILABLE = False


class WebSocketBridge:
    """
    WebSocket сервер и клиент для ARGOS.

    Использование (сервер):
        bridge = WebSocketBridge(server_host="0.0.0.0", server_port=8765)
        bridge.start_server(on_message=lambda ws, msg: ws.send("pong"))

    Использование (клиент):
        bridge = WebSocketBridge()
        result = bridge.send_message("ws://localhost:8765", "hello")
    """

    def __init__(
        self,
        server_host: str = "0.0.0.0",
        server_port: int = 8765,
    ):
        self.server_host = server_host
        self.server_port = server_port
        self._server_thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._on_message: Callable | None = None

    def available(self) -> bool:
        return _WS_AVAILABLE

    # ── Сервер ────────────────────────────────────────────────────────────────

    def start_server(self, on_message: Callable | None = None) -> dict:
        """Запустить WebSocket сервер в фоновом потоке."""
        if not _WS_AVAILABLE:
            return {"ok": False, "error": "pip install websockets"}

        self._on_message = on_message

        def _run():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            async def _handler(ws):
                async for msg in ws:
                    if self._on_message:
                        try:
                            self._on_message(ws, msg)
                        except Exception:
                            pass
                    else:
                        # echo
                        await ws.send(msg)

            async def _serve():
                async with websockets.serve(_handler, self.server_host, self.server_port):
                    await asyncio.Future()  # run forever

            self._loop.run_until_complete(_serve())

        self._server_thread = threading.Thread(target=_run, daemon=True)
        self._server_thread.start()
        return {"ok": True, "host": self.server_host, "port": self.server_port}

    # ── Клиент ────────────────────────────────────────────────────────────────

    def send_message(self, url: str, message: str, timeout: float = 5.0) -> dict:
        """Отправить сообщение на WebSocket сервер и получить ответ."""
        if not _WS_AVAILABLE:
            return {"ok": False, "provider": "websocket", "error": "pip install websockets"}
        try:
            with _ws_sync_client.connect(url, open_timeout=timeout) as ws:
                ws.send(message)
                response = ws.recv(timeout)
            return {"ok": True, "provider": "websocket", "data": response}
        except Exception as exc:
            return {"ok": False, "provider": "websocket", "error": str(exc)}

    def status(self) -> str:
        if not _WS_AVAILABLE:
            return "🔌 WebSocket: не установлен (pip install websockets)"
        running = self._server_thread and self._server_thread.is_alive()
        srv = f"сервер ✅ ws://{self.server_host}:{self.server_port}" if running else "сервер ⛔"
        return f"🔌 WebSocket: {srv}"

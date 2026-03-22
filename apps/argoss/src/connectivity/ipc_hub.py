"""
src/connectivity/ipc_hub.py
━━━━━━━━━━━━━━━━━━━━━━━━━━
Хаб межпроцессного взаимодействия (IPC) Аргоса.

Реализованные каналы IPC:
  1. HTTP Webhook  (FastAPI) — /webhook/command  [проще всего]
  2. WebSocket     (asyncio websockets)           [двусторонний real-time]
  3. Redis Pub/Sub (aioredis / redis-py)          [брокер между нодами]
  4. TCP Socket    (SocketTransport)              [низкий уровень]

Выбор канала зависит от задачи:
  - HTTP webhook → интеграции сторонних сервисов (n8n, Make, Zapier)
  - WebSocket    → real-time UI / мобильное приложение
  - Redis Pub/Sub→ несколько процессов Аргоса на одной машине
  - TCP Socket   → embedded / IoT узлы без HTTP стека

pip install fastapi uvicorn[standard] redis websockets
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
from typing import Any, Callable

# ── FastAPI / Uvicorn ─────────────────────────────────────────────────────────
try:
    from fastapi import FastAPI, Request, HTTPException  # type: ignore
    from fastapi.responses import JSONResponse  # type: ignore
    import uvicorn  # type: ignore
    _FASTAPI_OK = True
except ImportError:
    _FASTAPI_OK = False

# ── Redis ────────────────────────────────────────────────────────────────────
try:
    import redis  # type: ignore
    _REDIS_OK = True
except ImportError:
    _REDIS_OK = False

# ── WebSocket ─────────────────────────────────────────────────────────────────
try:
    import websockets  # type: ignore
    _WS_OK = True
except ImportError:
    _WS_OK = False


class IPCHub:
    """
    Центральный хаб IPC для Аргоса.
    on_command(text) → str — общий обработчик команд из любого канала.
    """

    def __init__(
        self,
        on_command: Callable[[str], str] | None = None,
        http_port: int = 8089,
        ws_port: int = 8090,
        redis_url: str = "",
        redis_channel: str = "argos:commands",
        token: str = "",
    ):
        self.on_command = on_command or (lambda x: f"[Аргос] {x}")
        self.http_port = http_port
        self.ws_port = ws_port
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.redis_channel = redis_channel
        self.token = token or os.getenv("ARGOS_IPC_TOKEN", "")
        self._threads: list[threading.Thread] = []

    # ═════════════════════════════════════════════════════════════════════════
    # 1. HTTP Webhook (FastAPI)
    # ═════════════════════════════════════════════════════════════════════════

    def start_http_webhook(self) -> str:
        """
        POST /webhook/command  {"cmd": "...", "token": "..."}
        → {"ok": true, "reply": "..."}
        """
        if not _FASTAPI_OK:
            return "❌ FastAPI не установлен: pip install fastapi uvicorn"

        app = FastAPI(title="Argos IPC Webhook", version="2.1")

        @app.post("/webhook/command")
        async def handle_command(request: Request):
            data = await request.json()
            if self.token and data.get("token") != self.token:
                raise HTTPException(status_code=401, detail="Unauthorized")
            cmd = data.get("cmd", "")
            if not cmd:
                raise HTTPException(status_code=400, detail="cmd is required")
            reply = self.on_command(cmd)
            return JSONResponse({"ok": True, "reply": reply})

        @app.get("/webhook/health")
        async def health():
            return {"ok": True, "service": "argos-ipc"}

        def _run():
            uvicorn.run(app, host="0.0.0.0", port=self.http_port, log_level="warning")

        t = threading.Thread(target=_run, daemon=True, name="ArgosIPCHttp")
        t.start()
        self._threads.append(t)
        return f"✅ HTTP Webhook: http://0.0.0.0:{self.http_port}/webhook/command"

    # ═════════════════════════════════════════════════════════════════════════
    # 2. WebSocket IPC
    # ═════════════════════════════════════════════════════════════════════════

    def start_websocket(self) -> str:
        """Запустить WS-сервер для real-time двустороннего IPC."""
        if not _WS_OK:
            return "❌ websockets не установлен: pip install websockets"

        async def _handler(ws, path=""):
            async for msg in ws:
                try:
                    data = json.loads(msg) if msg.startswith("{") else {"cmd": msg}
                    if self.token and data.get("token") != self.token:
                        await ws.send(json.dumps({"ok": False, "error": "Unauthorized"}))
                        continue
                    reply = self.on_command(data.get("cmd", msg))
                    await ws.send(json.dumps({"ok": True, "reply": reply}))
                except Exception as exc:
                    await ws.send(json.dumps({"ok": False, "error": str(exc)}))

        async def _serve():
            async with websockets.serve(_handler, "0.0.0.0", self.ws_port):
                await asyncio.Future()

        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_serve())

        t = threading.Thread(target=_run, daemon=True, name="ArgosIPCWS")
        t.start()
        self._threads.append(t)
        return f"✅ WebSocket IPC: ws://0.0.0.0:{self.ws_port}"

    # ═════════════════════════════════════════════════════════════════════════
    # 3. Redis Pub/Sub
    # ═════════════════════════════════════════════════════════════════════════

    def start_redis_subscriber(self) -> str:
        """
        Подписаться на Redis канал и выполнять команды.
        Публикация: redis-cli PUBLISH argos:commands "статус"
        """
        if not _REDIS_OK:
            return "❌ redis не установлен: pip install redis"

        def _run():
            try:
                r = redis.from_url(self.redis_url)
                pubsub = r.pubsub()
                pubsub.subscribe(self.redis_channel)
                for message in pubsub.listen():
                    if message["type"] == "message":
                        cmd = message["data"]
                        if isinstance(cmd, bytes):
                            cmd = cmd.decode("utf-8")
                        reply = self.on_command(cmd)
                        # Публикуем ответ в reply-канал
                        r.publish(f"{self.redis_channel}:reply", json.dumps({
                            "cmd": cmd, "reply": reply
                        }))
            except Exception as exc:
                print(f"[IPCHub Redis] ошибка: {exc}")

        t = threading.Thread(target=_run, daemon=True, name="ArgosIPCRedis")
        t.start()
        self._threads.append(t)
        return f"✅ Redis Pub/Sub: {self.redis_url} → {self.redis_channel}"

    def publish_redis(self, message: str) -> bool:
        """Опубликовать сообщение в Redis канал (для broadcast между нодами)."""
        if not _REDIS_OK:
            return False
        try:
            r = redis.from_url(self.redis_url)
            r.publish(self.redis_channel, message)
            return True
        except Exception:
            return False

    # ═════════════════════════════════════════════════════════════════════════
    # 4. Запуск всех каналов
    # ═════════════════════════════════════════════════════════════════════════

    def start_all(self, channels: list[str] | None = None) -> str:
        """
        Запустить все доступные IPC-каналы.
        channels=["http", "ws", "redis"] или None → все.
        """
        targets = channels or ["http", "ws", "redis"]
        results = []

        if "http" in targets:
            results.append(self.start_http_webhook())
        if "ws" in targets:
            results.append(self.start_websocket())
        if "redis" in targets:
            results.append(self.start_redis_subscriber())

        return "\n".join(results)

    def status(self) -> str:
        lines = ["🔌 IPC HUB"]
        lines.append(f"  HTTP Webhook : {'✅' if _FASTAPI_OK else '❌ нет fastapi'} → port {self.http_port}")
        lines.append(f"  WebSocket    : {'✅' if _WS_OK else '❌ нет websockets'} → port {self.ws_port}")
        lines.append(f"  Redis Pub/Sub: {'✅' if _REDIS_OK else '❌ нет redis'} → {self.redis_url}")
        lines.append(f"  Потоков активно: {len(self._threads)}")
        return "\n".join(lines)

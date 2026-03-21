"""
socket_transport.py — Низкоуровневый TCP/UDP транспорт Аргоса (модуль socket).
"""
from __future__ import annotations

import json
import os
import socket
import threading
from typing import Any, Callable


class SocketTransport:
    """TCP/UDP транспорт на базе стандартного модуля socket."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        protocol: str = "tcp",
        timeout: float = 10.0,
        buffer_size: int = 4096,
    ):
        self.host = host or os.getenv("SOCKET_HOST", "0.0.0.0")
        self.port = int(port or os.getenv("SOCKET_PORT", "9999"))
        self.protocol = protocol.lower()
        self.timeout = timeout
        self.buffer_size = buffer_size
        self._server_sock: socket.socket | None = None
        self._running = False
        self._thread: threading.Thread | None = None

    # ── клиент ────────────────────────────────────────────────────────
    def send_message(self, host: str, port: int, data: str | dict) -> dict[str, Any]:
        """Отправить данные на указанный хост/порт."""
        payload = json.dumps(data).encode("utf-8") if isinstance(data, dict) else data.encode("utf-8")

        try:
            if self.protocol == "udp":
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    sock.settimeout(self.timeout)
                    sock.sendto(payload, (host, port))
                return {"ok": True, "provider": "socket_udp", "data": {"host": host, "port": port}}

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout)
                sock.connect((host, port))
                sock.sendall(payload)
                reply = sock.recv(self.buffer_size)
            return {
                "ok": True,
                "provider": "socket_tcp",
                "data": reply.decode("utf-8", errors="replace"),
            }
        except Exception as exc:
            return {"ok": False, "provider": f"socket_{self.protocol}", "error": str(exc)}

    # ── сервер ────────────────────────────────────────────────────────
    def start_server(self, handler: Callable[[bytes, Any], bytes] | None = None) -> dict[str, Any]:
        """Запустить TCP/UDP-сервер в фоновом потоке."""
        if self._running:
            return {"ok": False, "provider": f"socket_{self.protocol}", "error": "Server already running"}

        def _default_handler(data: bytes, addr: Any) -> bytes:
            return b"echo:" + data

        cb = handler or _default_handler

        if self.protocol == "udp":
            return self._start_udp_server(cb)
        return self._start_tcp_server(cb)

    def _start_tcp_server(self, handler: Callable) -> dict[str, Any]:
        try:
            self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_sock.settimeout(1.0)
            self._server_sock.bind((self.host, self.port))
            self._server_sock.listen(5)
        except Exception as exc:
            return {"ok": False, "provider": "socket_tcp", "error": str(exc)}

        self._running = True

        def _loop() -> None:
            while self._running and self._server_sock:
                try:
                    conn, addr = self._server_sock.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                try:
                    data = conn.recv(self.buffer_size)
                    reply = handler(data, addr)
                    if reply:
                        conn.sendall(reply)
                finally:
                    conn.close()

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()
        return {"ok": True, "provider": "socket_tcp", "data": f"{self.host}:{self.port}"}

    def _start_udp_server(self, handler: Callable) -> dict[str, Any]:
        try:
            self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_sock.settimeout(1.0)
            self._server_sock.bind((self.host, self.port))
        except Exception as exc:
            return {"ok": False, "provider": "socket_udp", "error": str(exc)}

        self._running = True

        def _loop() -> None:
            while self._running and self._server_sock:
                try:
                    data, addr = self._server_sock.recvfrom(self.buffer_size)
                except socket.timeout:
                    continue
                except OSError:
                    break
                reply = handler(data, addr)
                if reply:
                    self._server_sock.sendto(reply, addr)

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()
        return {"ok": True, "provider": "socket_udp", "data": f"{self.host}:{self.port}"}

    def stop_server(self) -> None:
        """Остановить сервер."""
        self._running = False
        if self._server_sock:
            self._server_sock.close()
            self._server_sock = None
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

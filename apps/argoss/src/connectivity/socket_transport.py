"""
src/connectivity/socket_transport.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TCP/UDP транспорт для IPC (межпроцессного взаимодействия).
Используется для связи между процессами Аргоса внутри машины
и между нодами в локальной сети.
"""
from __future__ import annotations

import json
import os
import socket
import threading
from typing import Any, Callable


class SocketTransport:
    """
    Низкоуровневый TCP/UDP транспорт.
    protocol = "tcp" | "udp"
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 9000,
        protocol: str = "tcp",
        on_message: Callable[[str, tuple], str] | None = None,
        buffer_size: int = 65536,
    ):
        self.host = host
        self.port = port
        self.protocol = protocol.lower()
        self.on_message = on_message or (lambda msg, addr: f"[Аргос] {msg}")
        self.buffer_size = buffer_size
        self._server_sock: socket.socket | None = None
        self._running = False
        self._thread: threading.Thread | None = None

    # ── Сервер ────────────────────────────────────────────────────────────────

    def start_server(self) -> dict[str, Any]:
        """Запустить TCP или UDP сервер в отдельном потоке."""
        try:
            if self.protocol == "tcp":
                self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            else:
                self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

            self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_sock.bind((self.host, self.port))

            if self.protocol == "tcp":
                self._server_sock.listen(10)
                self._server_sock.settimeout(1.0)

            self._running = True
            target = self._tcp_loop if self.protocol == "tcp" else self._udp_loop
            self._thread = threading.Thread(target=target, daemon=True)
            self._thread.start()
            return {"ok": True, "provider": f"socket_{self.protocol}",
                    "host": self.host, "port": self.port}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def stop_server(self):
        self._running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
            self._server_sock = None

    # ── TCP loop ──────────────────────────────────────────────────────────────

    def _tcp_loop(self):
        while self._running and self._server_sock:
            try:
                conn, addr = self._server_sock.accept()
            except (socket.timeout, OSError):
                continue
            threading.Thread(
                target=self._handle_tcp, args=(conn, addr), daemon=True
            ).start()

    def _handle_tcp(self, conn: socket.socket, addr: tuple):
        try:
            data = b""
            while chunk := conn.recv(self.buffer_size):
                data += chunk
                if len(chunk) < self.buffer_size:
                    break
            text = data.decode("utf-8", errors="replace")
            reply = self.on_message(text, addr)
            conn.sendall(reply.encode("utf-8"))
        except Exception:
            pass
        finally:
            conn.close()

    # ── UDP loop ──────────────────────────────────────────────────────────────

    def _udp_loop(self):
        while self._running and self._server_sock:
            try:
                self._server_sock.settimeout(1.0)
                data, addr = self._server_sock.recvfrom(self.buffer_size)
                text = data.decode("utf-8", errors="replace")
                reply = self.on_message(text, addr)
                self._server_sock.sendto(reply.encode("utf-8"), addr)
            except socket.timeout:
                continue
            except OSError:
                break

    # ── Клиент ────────────────────────────────────────────────────────────────

    def send_message(self, host: str, port: int, message: str,
                     timeout: float = 5.0) -> dict[str, Any]:
        """Отправить сообщение на удалённый сервер (TCP или UDP)."""
        try:
            if self.protocol == "tcp":
                return self._send_tcp(host, port, message, timeout)
            return self._send_udp(host, port, message, timeout)
        except Exception as exc:
            return {"ok": False, "provider": f"socket_{self.protocol}", "error": str(exc)}

    def _send_tcp(self, host: str, port: int, message: str, timeout: float) -> dict:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((host, port))
            s.sendall(message.encode("utf-8"))
            data = s.recv(self.buffer_size).decode("utf-8", errors="replace")
        return {"ok": True, "provider": "socket_tcp", "data": data}

    def _send_udp(self, host: str, port: int, message: str, timeout: float) -> dict:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(timeout)
            s.sendto(message.encode("utf-8"), (host, port))
            # UDP: не ждём ответа (fire-and-forget для broadcast)
        return {"ok": True, "provider": "socket_udp"}

    # ── IPC helper ────────────────────────────────────────────────────────────

    def send_json(self, host: str, port: int, payload: dict, timeout: float = 5.0) -> dict:
        return self.send_message(host, port, json.dumps(payload, ensure_ascii=False), timeout)

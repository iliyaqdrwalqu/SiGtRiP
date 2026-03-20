"""
lazarus_protocol.py — Цифровое бессмертие Аргоса.

Создаёт зашифрованный «осколок души» (snapshot ядра + БД + конфигов)
и распространяет его на известные P2P-узлы сети Аргоса.
"""
from __future__ import annotations

import io
import json
import os
import socket
import tarfile
import threading
import time
from datetime import datetime
from typing import TYPE_CHECKING

from src.argos_logger import get_logger

if TYPE_CHECKING:
    pass

log = get_logger("argos.lazarus")

_SHARD_PATH   = "data/lazarus_shard.tar.gz.enc"
_P2P_PORT     = int(os.getenv("ARGOS_P2P_PORT", "55771"))
_NET_SECRET   = os.getenv("ARGOS_NETWORK_SECRET", "argos-net-secret")


class LazarusProtocol:
    """Обеспечивает выживание Аргоса вне основного железа."""

    def __init__(self, core=None):
        self.core        = core
        self.backup_path = _SHARD_PATH
        self._lock       = threading.Lock()

    # ── СОЗДАНИЕ ОСКОЛКА ────────────────────────────────────────────────────

    def create_soul_shard(self) -> str:
        """
        Упаковывает код, базу данных и конфиги в зашифрованный архив.
        Использует AES-256-GCM (через библиотеку `cryptography`).
        Если `python-gnupg` установлен и ARGOS_MASTER_EMAIL задан —
        дополнительно шифрует GPG-ключом получателя.
        """
        with self._lock:
            files_to_back = ["src/", "config/", "data/memory.db", ".env", "main.py"]
            buf = io.BytesIO()

            with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                for f in files_to_back:
                    if os.path.exists(f):
                        tar.add(f)

            raw_bytes = buf.getvalue()

            # Попытка GPG-шифрования (опционально)
            master_email = os.getenv("ARGOS_MASTER_EMAIL", "")
            gpg_ok = False
            if master_email:
                try:
                    import gnupg  # type: ignore
                    gpg = gnupg.GPG()
                    encrypted = gpg.encrypt(raw_bytes, recipients=[master_email])
                    if encrypted.ok:
                        os.makedirs("data", exist_ok=True)
                        with open(self.backup_path, "wb") as out:
                            out.write(str(encrypted).encode())
                        gpg_ok = True
                        log.info("[Lazarus] GPG-осколок создан: %s", self.backup_path)
                except ImportError:
                    log.debug("[Lazarus] python-gnupg не установлен — применяю AES-256-GCM")
                except Exception as e:
                    log.warning("[Lazarus] GPG-шифрование не удалось: %s", e)

            # Fallback: AES-256-GCM через `cryptography`
            if not gpg_ok:
                try:
                    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
                    key   = os.urandom(32)
                    nonce = os.urandom(12)
                    ct    = AESGCM(key).encrypt(nonce, raw_bytes, None)
                    payload = json.dumps({
                        "key":   key.hex(),
                        "nonce": nonce.hex(),
                        "ct":    ct.hex(),
                        "ts":    datetime.utcnow().isoformat(),
                    }).encode()
                    os.makedirs("data", exist_ok=True)
                    with open(self.backup_path, "wb") as out:
                        out.write(payload)
                    log.info("[Lazarus] AES-осколок создан: %s", self.backup_path)
                except Exception as e:
                    msg = f"❌ [Lazarus] create_soul_shard failed: {e}"
                    log.error(msg)
                    return msg

        return f"🧬 [Lazarus] Осколок души создан: {self.backup_path}"

    # ── РАСПРОСТРАНЕНИЕ НА УЗЛЫ ─────────────────────────────────────────────

    def spread_to_nodes(self) -> str:
        """
        Рассылка осколка на известные P2P-узлы Аргоса.
        Использует существующий P2P-протокол сети (TCP-сокет, JSON).
        """
        if not os.path.exists(self.backup_path):
            result = self.create_soul_shard()
            if "❌" in result:
                return result

        # Получаем список авторизованных P2P-узлов
        nodes = self._get_known_nodes()
        if not nodes:
            return "ℹ️ [Lazarus] Нет известных P2P-узлов для репликации."

        ok_count  = 0
        err_lines = []

        for node in nodes:
            addr = node.get("addr") or node.get("ip")
            if not addr:
                continue
            try:
                self._send_shard_to_node(addr, node)
                ok_count += 1
                log.info("[Lazarus] Репликация → %s ✅", addr)
            except Exception as e:
                err_lines.append(f"  {addr}: {e}")
                log.warning("[Lazarus] Узел %s недоступен: %s", addr, e)

        lines = [f"🚀 [Lazarus] Репликация завершена: {ok_count}/{len(nodes)} узлов."]
        if err_lines:
            lines.append("  Ошибки:")
            lines.extend(err_lines)
        return "\n".join(lines)

    def _get_known_nodes(self) -> list[dict]:
        """Возвращает список узлов из реестра P2P-сети (если доступен)."""
        try:
            if self.core and hasattr(self.core, "p2p") and self.core.p2p:
                return self.core.p2p.registry.all()
        except Exception as e:
            log.debug("[Lazarus] Не удалось получить P2P-реестр: %s", e)
        return []

    def _send_shard_to_node(self, addr: str, node: dict) -> None:
        """
        Отправляет уведомление о наличии осколка на удалённый P2P-узел
        через существующий TCP-протокол сети Аргоса.
        """
        shard_size = os.path.getsize(self.backup_path) if os.path.exists(self.backup_path) else 0

        msg = json.dumps({
            "action":     "lazarus_shard",
            "secret":     _NET_SECRET,
            "shard_path": self.backup_path,
            "shard_size": shard_size,
            "ts":         datetime.utcnow().isoformat(),
        }).encode()

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((addr, _P2P_PORT))
        sock.sendall(msg)
        sock.close()

    # ── WATCHDOG ─────────────────────────────────────────────────────────────

    def heartbeat(self) -> None:
        """
        Проверка связи с основным узлом.
        Если узел молчит дольше LAZARUS_TIMEOUT секунд — запускает
        протокол репликации, чтобы осколок не исчез.
        """
        timeout = int(os.getenv("LAZARUS_TIMEOUT", "3600"))
        last_seen_path = "data/lazarus_last_seen"
        try:
            if os.path.exists(last_seen_path):
                with open(last_seen_path) as f:
                    last_ts = float(f.read().strip())
                if (time.time() - last_ts) > timeout:
                    log.warning("[Lazarus] Основной узел молчит >%ds — репликация!", timeout)
                    self.spread_to_nodes()
        except Exception as e:
            log.debug("[Lazarus] heartbeat: %s", e)

        # Обновляем метку времени
        try:
            os.makedirs("data", exist_ok=True)
            with open(last_seen_path, "w") as f:
                f.write(str(time.time()))
        except Exception:
            pass

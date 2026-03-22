"""
src/connectivity/protocols/nfc_bridge.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NFC мост для ARGOS. Чтение/запись NDEF, MIFARE, NTAG.

Поддерживаемые ридеры:
  • ACR122U (USB, CCID)
  • PN532 (UART / I2C / SPI)
  • RC522 (SPI для RPi)
  • Sonoff NFC / смартфон Android с NFC

Подключение RC522 к RPi (SPI):
  RC522 SDA  → GPIO8  (SPI0 CE0)
  RC522 SCK  → GPIO11 (SPI0 SCLK)
  RC522 MOSI → GPIO10 (SPI0 MOSI)
  RC522 MISO → GPIO9  (SPI0 MISO)
  RC522 RST  → GPIO25
  RC522 3.3V → 3.3V
  RC522 GND  → GND

pip install nfcpy mfrc522
"""
from __future__ import annotations

import os
import time
import threading
import logging
from typing import Any, Callable

log = logging.getLogger("argos.nfc")

try:
    import nfc  # type: ignore
    _NFCPY_OK = True
except ImportError:
    _NFCPY_OK = False

try:
    from mfrc522 import SimpleMFRC522  # type: ignore
    _MFRC_OK = True
except ImportError:
    _MFRC_OK = False


class NFCBridge:
    """
    Мост NFC — чтение меток, запись NDEF, регистрация тегов.
    Поддерживает nfcpy (ACR122U, PN532) и mfrc522 (RC522 RPi).
    """

    def __init__(
        self,
        device: str = "",               # "usb:054c:06c3" для ACR122U или "" для авто
        on_tag: Callable[[dict], None] | None = None,
        mode: str = "auto",             # "nfcpy" | "rc522" | "auto"
    ):
        self.device = device or os.getenv("NFC_DEVICE", "")
        self.on_tag = on_tag
        self.mode = mode
        self._tags: dict[str, dict] = {}   # uid → info
        self._running = False
        self._thread: threading.Thread | None = None
        self._reader = None

        if mode == "rc522" or (mode == "auto" and _MFRC_OK):
            try:
                self._reader = SimpleMFRC522()
                self._mode = "rc522"
            except Exception:
                self._mode = "none"
        elif _NFCPY_OK:
            self._mode = "nfcpy"
        else:
            self._mode = "none"

    def available(self) -> bool:
        return self._mode != "none"

    # ── Однократное чтение ────────────────────────────────────────────────────

    def read_tag(self, timeout: float = 5.0) -> dict[str, Any]:
        """Ждать и прочитать один NFC тег."""
        if self._mode == "rc522":
            return self._read_rc522(timeout)
        if self._mode == "nfcpy":
            return self._read_nfcpy(timeout)
        return {"ok": False, "error": "NFC не доступен"}

    def _read_rc522(self, timeout: float) -> dict[str, Any]:
        if not self._reader:
            return {"ok": False, "error": "RC522 не инициализирован"}
        try:
            import signal
            def _timeout_handler(signum, frame):
                raise TimeoutError()
            signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(int(timeout) + 1)
            uid, text = self._reader.read()
            signal.alarm(0)
            uid_hex = hex(uid)
            tag = {"ok": True, "uid": uid_hex, "text": text.strip(), "type": "MIFARE"}
            self._register_tag(uid_hex, tag)
            return tag
        except TimeoutError:
            return {"ok": False, "error": "timeout"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _read_nfcpy(self, timeout: float) -> dict[str, Any]:
        try:
            result: dict = {"ok": False}

            def _connected(tag):
                uid = tag.identifier.hex()
                info: dict[str, Any] = {
                    "ok": True,
                    "uid": uid,
                    "type": type(tag).__name__,
                }
                # NDEF
                if hasattr(tag, "ndef") and tag.ndef:
                    records = []
                    for r in tag.ndef.records:
                        records.append({
                            "type": r.type.decode("utf-8", errors="replace"),
                            "data": r.data.decode("utf-8", errors="replace") if r.data else "",
                        })
                    info["ndef"] = records
                result.update(info)
                self._register_tag(uid, info)
                return False  # не держать соединение

            kwargs = {"on-connect": _connected, "iterations": 1, "interval": 0.1}
            if self.device:
                with nfc.ContactlessFrontend(self.device) as clf:
                    clf.connect(rdwr=kwargs)
            else:
                with nfc.ContactlessFrontend() as clf:
                    clf.connect(rdwr=kwargs)
            return result
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ── Запись ────────────────────────────────────────────────────────────────

    def write_tag(self, text: str, timeout: float = 10.0) -> dict[str, Any]:
        """Записать текст на NFC метку."""
        if self._mode == "rc522":
            return self._write_rc522(text)
        return {"ok": False, "error": "Запись поддерживается только RC522"}

    def _write_rc522(self, text: str) -> dict[str, Any]:
        if not self._reader:
            return {"ok": False, "error": "RC522 не инициализирован"}
        try:
            uid, _ = self._reader.write(text[:16].ljust(16))  # MIFARE 16 байт
            return {"ok": True, "uid": hex(uid), "text": text}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ── Реестр тегов ─────────────────────────────────────────────────────────

    def _register_tag(self, uid: str, info: dict):
        """Зарегистрировать тег в реестре."""
        now = time.time()
        if uid not in self._tags:
            log.info("Новый NFC тег: %s", uid)
        self._tags[uid] = {**info, "last_seen": now}
        if self.on_tag:
            self.on_tag({**info, "uid": uid})

    def get_tags(self) -> dict[str, dict]:
        return dict(self._tags)

    def tag_info(self, uid: str) -> dict | None:
        return self._tags.get(uid)

    # ── Фоновое сканирование ──────────────────────────────────────────────────

    def start_scan(self, core=None) -> str:
        """Непрерывное сканирование в фоне."""
        if self._running:
            return "⚠️ NFC уже сканирует"
        if not self.available():
            return "❌ NFC не доступен (нет nfcpy или mfrc522)"
        self._running = True

        def _loop():
            while self._running:
                tag = self.read_tag(timeout=2.0)
                if tag.get("ok") and core:
                    cmd = tag.get("text", "")
                    if cmd:
                        try:
                            core.process(cmd)
                        except Exception:
                            pass
                time.sleep(0.5)

        self._thread = threading.Thread(target=_loop, daemon=True, name="NFCScan")
        self._thread.start()
        return "✅ NFC сканирование запущено"

    def stop_scan(self):
        self._running = False

    # ── Статус ────────────────────────────────────────────────────────────────

    def status(self) -> str:
        lib_info = {
            "nfcpy": "✅" if _NFCPY_OK else "❌",
            "mfrc522": "✅" if _MFRC_OK else "❌",
        }
        return (
            f"📱 NFC\n"
            f"  Режим   : {self._mode}\n"
            f"  nfcpy   : {lib_info['nfcpy']}\n"
            f"  mfrc522 : {lib_info['mfrc522']}\n"
            f"  Тегов   : {len(self._tags)}\n"
            f"  Скан    : {'активен' if self._running else 'остановлен'}"
        )

    def handle_command(self, cmd: str) -> str | None:
        c = cmd.lower().strip()
        if c in ("nfc", "nfc статус"):
            return self.status()
        if c in ("nfc читать", "nfc read", "nfc скан"):
            r = self.read_tag(timeout=5.0)
            if r.get("ok"):
                return f"📱 NFC тег:\n  UID: {r['uid']}\n  Текст: {r.get('text', r.get('ndef', ''))}"
            return f"📱 NFC: {r.get('error', 'нет тегов')}"
        if c.startswith("nfc записать "):
            text = cmd[13:].strip()
            r = self.write_tag(text)
            return f"✅ NFC записано: {text}" if r["ok"] else f"❌ NFC: {r.get('error')}"
        if c == "nfc метки":
            tags = self.get_tags()
            if not tags:
                return "📱 NFC: меток нет"
            return "📱 NFC метки:\n" + "\n".join(f"  • {uid}: {v.get('text','')}" for uid, v in tags.items())
        return None

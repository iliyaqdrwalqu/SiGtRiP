"""
src/connectivity/protocols/lora_bridge.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LoRa мост для ARGOS.

Поддерживаемые модули:
  • EBYTE E32 (SX1276/SX1278) — UART AT команды
  • EBYTE E22 (SX1262) — UART AT команды
  • SX1276 breakout (SPI, via pyLoRa)
  • RAK811 / RAK3172 — AT команды

Схема подключения E32/E22 к RPi:
  E32 M0  → GPIO22 (управление режимом)
  E32 M1  → GPIO27 (управление режимом)
  E32 TXD → GPIO15/RX (RPi UART RX)
  E32 RXD → GPIO14/TX (RPi UART TX)
  E32 AUX → GPIO17 (состояние модуля)
  E32 VCC → 3.3V
  E32 GND → GND

  Частоты: 433MHz (E32-433T20D) / 868MHz / 915MHz

pip install pyserial
"""
from __future__ import annotations

import os
import struct
import threading
import time
import logging
from typing import Any, Callable

try:
    import serial  # type: ignore
    _SERIAL_OK = True
except ImportError:
    _SERIAL_OK = False

try:
    import RPi.GPIO as GPIO  # type: ignore
    _GPIO_OK = True
except ImportError:
    _GPIO_OK = False

log = logging.getLogger("argos.lora")

# Режимы E32
_MODE_NORMAL = (0, 0)   # M0=0 M1=0
_MODE_WAKEUP = (1, 0)   # M0=1 M1=0
_MODE_POWER  = (0, 1)   # M0=0 M1=1
_MODE_SLEEP  = (1, 1)   # M0=1 M1=1  (конфигурация)


class LoRaBridge:
    """
    LoRa мост через UART (E32 / E22 / RAK811).
    Поддерживает отправку, приём и конфигурацию.
    """

    def __init__(
        self,
        port: str = "",
        baudrate: int = 9600,
        pin_m0: int | None = None,
        pin_m1: int | None = None,
        pin_aux: int | None = None,
        address: int = 0x0000,
        channel: int = 0x17,   # канал 23 = 433MHz для E32-433
        on_receive: Callable[[bytes, dict], None] | None = None,
    ):
        self.port = port or os.getenv("LORA_PORT", "/dev/ttyAMA0")
        self.baudrate = baudrate or int(os.getenv("LORA_BAUD", "9600"))
        self.pin_m0 = pin_m0 or int(os.getenv("LORA_M0_PIN", "22"))
        self.pin_m1 = pin_m1 or int(os.getenv("LORA_M1_PIN", "27"))
        self.pin_aux = pin_aux or int(os.getenv("LORA_AUX_PIN", "17"))
        self.address = address
        self.channel = channel
        self.on_receive = on_receive
        self._ser: Any = None
        self._rx_thread: threading.Thread | None = None
        self._running = False

    # ── Подключение ───────────────────────────────────────────────────────────

    def connect(self) -> str:
        if not _SERIAL_OK:
            return "❌ pyserial не установлен: pip install pyserial"
        try:
            self._setup_gpio()
            self._ser = serial.Serial(self.port, self.baudrate, timeout=1)
            self._set_mode(*_MODE_NORMAL)
            time.sleep(0.1)
            return f"✅ LoRa подключён: {self.port} @ {self.baudrate}"
        except Exception as exc:
            return f"❌ LoRa: {exc}"

    def disconnect(self):
        self._running = False
        if self._ser and self._ser.is_open:
            self._ser.close()

    # ── GPIO режимы ───────────────────────────────────────────────────────────

    def _setup_gpio(self):
        if not _GPIO_OK:
            return
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        for pin in (self.pin_m0, self.pin_m1):
            GPIO.setup(pin, GPIO.OUT)
        GPIO.setup(self.pin_aux, GPIO.IN)

    def _set_mode(self, m0: int, m1: int):
        if not _GPIO_OK:
            return
        GPIO.output(self.pin_m0, m0)
        GPIO.output(self.pin_m1, m1)
        time.sleep(0.05)
        # Ждём пока AUX станет HIGH (модуль готов)
        deadline = time.time() + 2.0
        while time.time() < deadline:
            if GPIO.input(self.pin_aux):
                break
            time.sleep(0.01)

    # ── Отправка ──────────────────────────────────────────────────────────────

    def send(
        self,
        data: bytes | str,
        target_addr: int = 0xFFFF,  # broadcast
        target_channel: int | None = None,
    ) -> dict[str, Any]:
        """
        Отправить данные.
        target_addr=0xFFFF — широковещательная рассылка всем.
        """
        if not self._ser or not self._ser.is_open:
            return {"ok": False, "error": "LoRa не подключён"}

        if isinstance(data, str):
            data = data.encode("utf-8")

        # Адресная передача: 3 байта заголовка + данные
        ch = target_channel if target_channel is not None else self.channel
        header = bytes([
            (target_addr >> 8) & 0xFF,
            target_addr & 0xFF,
            ch & 0xFF,
        ])
        payload = header + data

        try:
            self._ser.write(payload)
            self._ser.flush()
            return {"ok": True, "bytes_sent": len(payload), "target": hex(target_addr)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def send_json(self, obj: dict, target_addr: int = 0xFFFF) -> dict[str, Any]:
        import json
        return self.send(json.dumps(obj, ensure_ascii=False).encode("utf-8"), target_addr)

    # ── Получение ─────────────────────────────────────────────────────────────

    def start_receive(self) -> str:
        """Запустить фоновый приём пакетов."""
        if not self._ser:
            return "❌ LoRa не подключён"
        self._running = True
        self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True, name="LoRaRX")
        self._rx_thread.start()
        return "✅ LoRa приёмник запущен"

    def _rx_loop(self):
        while self._running and self._ser and self._ser.is_open:
            try:
                if self._ser.in_waiting >= 1:
                    raw = self._ser.read(self._ser.in_waiting)
                    meta = self._parse_packet(raw)
                    if self.on_receive:
                        self.on_receive(raw, meta)
                    log.debug("LoRa RX: %s", raw.hex())
            except Exception as exc:
                log.warning("LoRa RX: %s", exc)
            time.sleep(0.05)

    def _parse_packet(self, raw: bytes) -> dict:
        """Базовый парсинг пакета E32."""
        if len(raw) < 3:
            return {"raw": raw}
        return {
            "addr": (raw[0] << 8) | raw[1],
            "channel": raw[2],
            "data": raw[3:],
            "text": raw[3:].decode("utf-8", errors="replace"),
        }

    def read_once(self, timeout: float = 2.0) -> dict[str, Any]:
        """Прочитать один пакет синхронно."""
        if not self._ser:
            return {"ok": False}
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._ser.in_waiting:
                raw = self._ser.read(self._ser.in_waiting)
                return {"ok": True, **self._parse_packet(raw)}
            time.sleep(0.05)
        return {"ok": False, "error": "timeout"}

    # ── Конфигурация E32 ──────────────────────────────────────────────────────

    def configure_e32(
        self,
        address: int | None = None,
        channel: int | None = None,
        baud: int = 9600,
        air_rate: int = 2400,
    ) -> str:
        """Записать конфигурацию в E32 (режим сна)."""
        if not self._ser:
            return "❌ не подключён"
        addr = address if address is not None else self.address
        ch = channel if channel is not None else self.channel

        # Переключаем в режим конфигурации
        self._set_mode(*_MODE_SLEEP)
        time.sleep(0.1)

        # Формируем пакет конфигурации E32 (6 байт)
        baud_map = {1200: 0, 2400: 1, 4800: 2, 9600: 3, 19200: 4, 38400: 5, 57600: 6, 115200: 7}
        air_map  = {250: 0, 1200: 1, 2400: 2, 4800: 3, 9600: 4, 19200: 5}
        b_code = baud_map.get(baud, 3)
        a_code = air_map.get(air_rate, 2)
        sped = (b_code << 3) | a_code

        config = bytes([
            0xC0,                    # HEAD — сохранить в flash
            (addr >> 8) & 0xFF,      # ADDH
            addr & 0xFF,             # ADDL
            sped,                    # SPED
            ch & 0x1F,               # CHAN
            0x44,                    # OPTION (TXD pull-up, push-pull, 250ms wake)
        ])
        try:
            self._ser.write(config)
            self._ser.flush()
            time.sleep(0.5)
            resp = self._ser.read(self._ser.in_waiting)
            self._set_mode(*_MODE_NORMAL)
            return f"✅ E32 сконфигурирован: addr={hex(addr)}, ch={ch}"
        except Exception as exc:
            self._set_mode(*_MODE_NORMAL)
            return f"❌ E32 конфигурация: {exc}"

    # ── Статус ────────────────────────────────────────────────────────────────

    def status(self) -> str:
        connected = bool(self._ser and self._ser.is_open)
        return (
            f"📻 LORA\n"
            f"  Порт   : {self.port} @ {self.baudrate}\n"
            f"  Статус : {'✅ подключён' if connected else '❌ не подключён'}\n"
            f"  Адрес  : {hex(self.address)}\n"
            f"  Канал  : {self.channel} ({433 + self.channel}MHz approx)\n"
            f"  Приём  : {'активен' if self._running else 'остановлен'}"
        )

    def handle_command(self, cmd: str) -> str | None:
        c = cmd.lower().strip()
        if c in ("lora", "lora статус"):
            return self.status()
        if c.startswith("lora отправить "):
            msg = cmd[15:].strip()
            r = self.send(msg)
            return f"✅ LoRa отправлено ({r.get('bytes_sent',0)} байт)" if r["ok"] else f"❌ {r.get('error')}"
        if c == "lora получить":
            r = self.read_once()
            return f"📻 LoRa: {r.get('text', r)}"
        return None

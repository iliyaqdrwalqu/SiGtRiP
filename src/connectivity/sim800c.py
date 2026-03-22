"""
src/connectivity/sim800c.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Полный драйвер SIM800C для ARGOS Universal OS

Поддерживает:
  ✅ Raspberry Pi (Малинка) — /dev/ttyAMA0 или /dev/ttyS0
  ✅ ESP (через pyserial по USB-UART) — /dev/ttyUSB0, COM3...
  ✅ Linux/Windows/macOS desktop

Возможности:
  • SMS: отправка, получение, парсинг команд из входящих
  • Голосовые звонки: набор, ответ, сброс
  • GPRS: подключение к интернету
  • USSD: запросы баланса и услуг
  • Гомеостаз: автоперезапуск при потере сети
  • Интеграция с ArgosCore: SMS = команда Аргосу

Схема подключения:
  Raspberry Pi:
    GPIO14 (TX) → SIM800C RXD
    GPIO15 (RX) → SIM800C TXD
    GPIO17       → SIM800C RST   (опционально)
    GPIO18       → SIM800C PWRKEY (опционально)
    4.0–4.2V / 2A → SIM800C VCC
    GND          → SIM800C GND

  ESP32:
    GPIO17 (TX2) → SIM800C RXD
    GPIO16 (RX2) → SIM800C TXD
    GPIO4        → SIM800C RST
    GPIO5        → SIM800C PWRKEY
    4.0–4.2V / 2A → SIM800C VCC
    GND          → SIM800C GND

  ⚠️ ВАЖНО: SIM800C требует 4.0–4.2V, пик тока 2A.
     НЕ подключайте к 3.3V или 5V GPIO напрямую!
     Используйте Li-Ion аккумулятор или DC-DC конвертер.

pip install pyserial
"""
from __future__ import annotations

import os
import re
import sys
import time
import threading
import logging
from typing import Any, Callable, Optional

try:
    import serial  # type: ignore
    _SERIAL_OK = True
except ImportError:
    _SERIAL_OK = False

log = logging.getLogger("argos.sim800c")


# ── Настройки платформ по умолчанию ──────────────────────────────────────────

_PLATFORM_DEFAULTS = {
    "rpi": {
        "port": "/dev/ttyAMA0",
        "baudrate": 9600,
        "rst_pin": 17,
        "pwr_pin": 18,
        "description": "Raspberry Pi (GPIO UART)",
    },
    "rpi5": {
        "port": "/dev/ttyAMA10",
        "baudrate": 9600,
        "rst_pin": 17,
        "pwr_pin": 18,
        "description": "Raspberry Pi 5 (UART0)",
    },
    "esp": {
        "port": "/dev/ttyUSB0",
        "baudrate": 9600,
        "rst_pin": 4,
        "pwr_pin": 5,
        "description": "ESP32 / Arduino (USB-UART)",
    },
    "windows": {
        "port": "COM3",
        "baudrate": 9600,
        "rst_pin": None,
        "pwr_pin": None,
        "description": "Windows COM-порт",
    },
    "auto": {
        "port": os.getenv("SIM800C_PORT", "/dev/ttyAMA0"),
        "baudrate": int(os.getenv("SIM800C_BAUD", "9600")),
        "rst_pin": None,
        "pwr_pin": None,
        "description": "Авто (из SIM800C_PORT env)",
    },
}


class SIM800CError(Exception):
    """Базовое исключение SIM800C."""


class SIM800C:
    """
    Полный драйвер SIM800C для ARGOS.
    Поддерживает SMS, звонки, GPRS, USSD.
    """

    AT_TIMEOUT = float(os.getenv("SIM800C_TIMEOUT", "5"))
    SMS_POLL_INTERVAL = int(os.getenv("SIM800C_POLL", "30"))

    def __init__(
        self,
        port: str = "",
        baudrate: int = 9600,
        platform: str = "auto",
        on_sms: Callable[[str, str, str], None] | None = None,
        on_call: Callable[[str], None] | None = None,
        rst_pin: int | None = None,
        pwr_pin: int | None = None,
    ):
        """
        port     — serial порт (если пустой — берётся из platform)
        platform — "rpi" | "rpi5" | "esp" | "windows" | "auto"
        on_sms(sender, text, timestamp) — callback на входящее SMS
        on_call(number) — callback на входящий звонок
        """
        cfg = _PLATFORM_DEFAULTS.get(platform, _PLATFORM_DEFAULTS["auto"])
        self.port = port or cfg["port"]
        self.baudrate = baudrate or cfg["baudrate"]
        self.rst_pin = rst_pin if rst_pin is not None else cfg.get("rst_pin")
        self.pwr_pin = pwr_pin if pwr_pin is not None else cfg.get("pwr_pin")
        self.on_sms = on_sms
        self.on_call = on_call
        self._ser: serial.Serial | None = None
        self._lock = threading.RLock()
        self._poll_thread: threading.Thread | None = None
        self._running = False
        self._signal = 0
        self._operator = ""
        self._phone_number = os.getenv("SIM800C_PHONE", "")

    # ── Подключение ───────────────────────────────────────────────────────────

    def connect(self) -> str:
        """Открыть serial-соединение и инициализировать модем."""
        if not _SERIAL_OK:
            return "❌ pyserial не установлен: pip install pyserial"
        try:
            self._ser = serial.Serial(
                self.port,
                self.baudrate,
                timeout=self.AT_TIMEOUT,
                write_timeout=self.AT_TIMEOUT,
            )
            time.sleep(0.5)
            # Сброс по GPIO если доступен (RPi)
            self._gpio_power_on()
            # Инициализация модема
            self._init_modem()
            log.info("SIM800C подключён: %s", self.port)
            return f"✅ SIM800C подключён ({self.port}), оператор: {self._operator}"
        except Exception as exc:
            log.error("SIM800C ошибка подключения: %s", exc)
            return f"❌ SIM800C: {exc}"

    def disconnect(self):
        self._running = False
        if self._ser and self._ser.is_open:
            try:
                self._ser.close()
            except Exception:
                pass
        self._ser = None

    def is_connected(self) -> bool:
        return bool(self._ser and self._ser.is_open)

    # ── GPIO управление (RPi) ─────────────────────────────────────────────────

    def _gpio_power_on(self):
        """Включить SIM800C через PWRKEY если настроен GPIO."""
        if self.pwr_pin is None:
            return
        try:
            import RPi.GPIO as GPIO  # type: ignore
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            GPIO.setup(self.pwr_pin, GPIO.OUT)
            GPIO.output(self.pwr_pin, GPIO.HIGH)
            time.sleep(0.1)
            GPIO.output(self.pwr_pin, GPIO.LOW)
            time.sleep(1.0)
            GPIO.output(self.pwr_pin, GPIO.HIGH)
            time.sleep(2.0)
        except ImportError:
            pass  # не RPi — игнорируем

    def _gpio_reset(self):
        """Аппаратный сброс через RST пин."""
        if self.rst_pin is None:
            return
        try:
            import RPi.GPIO as GPIO  # type: ignore
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.rst_pin, GPIO.OUT)
            GPIO.output(self.rst_pin, GPIO.LOW)
            time.sleep(0.5)
            GPIO.output(self.rst_pin, GPIO.HIGH)
            time.sleep(1.0)
        except ImportError:
            pass

    # ── AT-команды ────────────────────────────────────────────────────────────

    def _send_at(self, cmd: str, wait_ok: bool = True, timeout: float | None = None) -> str:
        """Отправить AT-команду и получить ответ."""
        if not self._ser or not self._ser.is_open:
            raise SIM800CError("Порт не открыт")
        with self._lock:
            self._ser.reset_input_buffer()
            self._ser.write((cmd + "\r\n").encode("utf-8"))
            self._ser.flush()
            t = timeout or self.AT_TIMEOUT
            deadline = time.time() + t
            lines = []
            while time.time() < deadline:
                if self._ser.in_waiting:
                    raw = self._ser.readline()
                    line = raw.decode("utf-8", errors="replace").strip()
                    if line:
                        lines.append(line)
                    if wait_ok and line in ("OK", "ERROR", "NO CARRIER", "BUSY"):
                        break
                    if not wait_ok and lines:
                        break
                else:
                    time.sleep(0.05)
            return "\n".join(lines)

    def _init_modem(self):
        """Базовая инициализация SIM800C."""
        cmds = [
            ("AT", 2),            # проверка связи
            ("ATE0", 2),          # эхо выкл
            ("AT+CMGF=1", 2),     # SMS в текстовом режиме
            ("AT+CNMI=2,2,0,0,0", 2),  # уведомления о новых SMS
            ("AT+CLIP=1", 2),     # определитель номера при звонке
            ("AT+CSCS=\"UTF-8\"", 2),  # кодировка
        ]
        for cmd, to in cmds:
            try:
                self._send_at(cmd, timeout=to)
            except Exception:
                pass
        # Читаем оператора
        try:
            resp = self._send_at("AT+COPS?", timeout=3)
            m = re.search(r'"([^"]+)"', resp)
            if m:
                self._operator = m.group(1)
        except Exception:
            pass
        # Уровень сигнала
        self._update_signal()

    def _update_signal(self):
        try:
            resp = self._send_at("AT+CSQ", timeout=3)
            m = re.search(r"\+CSQ:\s*(\d+)", resp)
            if m:
                rssi = int(m.group(1))
                # Перевод в dBm: -113 + rssi*2
                self._signal = rssi
        except Exception:
            pass

    # ── SMS ──────────────────────────────────────────────────────────────────

    def send_sms(self, number: str, text: str) -> dict[str, Any]:
        """Отправить SMS."""
        if not self.is_connected():
            return {"ok": False, "error": "SIM800C не подключён"}
        try:
            self._send_at(f"AT+CMGS=\"{number}\"", wait_ok=False, timeout=3)
            time.sleep(0.3)
            # Отправляем текст + Ctrl+Z (0x1A)
            with self._lock:
                self._ser.write((text + "\x1a").encode("utf-8"))
                self._ser.flush()
            time.sleep(3)
            raw = b""
            if self._ser.in_waiting:
                raw = self._ser.read(self._ser.in_waiting)
            resp = raw.decode("utf-8", errors="replace")
            ok = "+CMGS:" in resp or "OK" in resp
            return {"ok": ok, "provider": "sim800c", "to": number, "response": resp}
        except Exception as exc:
            return {"ok": False, "provider": "sim800c", "error": str(exc)}

    def read_sms(self, status: str = "ALL") -> list[dict[str, Any]]:
        """
        Прочитать SMS.
        status: ALL | REC UNREAD | REC READ | STO UNSENT | STO SENT
        """
        if not self.is_connected():
            return []
        try:
            resp = self._send_at(f'AT+CMGL="{status}"', timeout=10)
            return self._parse_sms_list(resp)
        except Exception as exc:
            log.error("read_sms: %s", exc)
            return []

    def _parse_sms_list(self, raw: str) -> list[dict[str, Any]]:
        """Парсинг ответа AT+CMGL."""
        messages = []
        lines = raw.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.startswith("+CMGL:"):
                # +CMGL: index,status,sender,,"timestamp"
                parts = line.split(",")
                try:
                    idx = parts[0].split(":")[1].strip()
                    sender = parts[2].strip().strip('"')
                    timestamp = parts[4].strip().strip('"') if len(parts) > 4 else ""
                    body = lines[i + 1] if i + 1 < len(lines) else ""
                    messages.append({
                        "index": idx,
                        "sender": sender,
                        "timestamp": timestamp,
                        "text": body.strip(),
                        "command": body.strip(),  # text = команда для Аргоса
                    })
                    i += 2
                    continue
                except Exception:
                    pass
            i += 1
        return messages

    def delete_sms(self, index: str = "1", flag: int = 4) -> bool:
        """
        Удалить SMS.
        flag: 0=по индексу, 1=прочитанные, 4=все
        """
        try:
            resp = self._send_at(f"AT+CMGD={index},{flag}", timeout=5)
            return "OK" in resp
        except Exception:
            return False

    def poll_commands(self) -> list[str]:
        """Опрос входящих SMS как команд для ArgosCore."""
        msgs = self.read_sms("REC UNREAD")
        commands = []
        for msg in msgs:
            cmd = msg.get("command", "").strip()
            if cmd:
                commands.append(cmd)
                self.delete_sms(msg["index"], flag=0)
        return commands

    # ── Звонки ────────────────────────────────────────────────────────────────

    def call(self, number: str) -> dict[str, Any]:
        """Набрать номер."""
        if not self.is_connected():
            return {"ok": False, "error": "SIM800C не подключён"}
        try:
            resp = self._send_at(f"ATD{number};", timeout=10)
            return {"ok": True, "provider": "sim800c", "number": number, "response": resp}
        except Exception as exc:
            return {"ok": False, "provider": "sim800c", "error": str(exc)}

    def answer(self) -> str:
        """Ответить на входящий звонок."""
        try:
            return self._send_at("ATA", timeout=5)
        except Exception as exc:
            return str(exc)

    def hangup(self) -> str:
        """Сбросить звонок."""
        try:
            return self._send_at("ATH", timeout=5)
        except Exception as exc:
            return str(exc)

    # ── USSD ─────────────────────────────────────────────────────────────────

    def ussd(self, code: str) -> str:
        """
        Отправить USSD запрос (например баланс).
        Пример: ussd("*100#")
        """
        if not self.is_connected():
            return "❌ SIM800C не подключён"
        try:
            resp = self._send_at(f'AT+CUSD=1,"{code}",15', timeout=10)
            m = re.search(r'\+CUSD:\s*\d+,"([^"]+)"', resp)
            return m.group(1) if m else resp
        except Exception as exc:
            return str(exc)

    def balance(self) -> str:
        """Запрос баланса через USSD (МТС, Билайн, Мегафон и т.д.)."""
        codes = os.getenv("SIM800C_BALANCE_USSD", "*100#")
        return self.ussd(codes)

    # ── GPRS ─────────────────────────────────────────────────────────────────

    def gprs_connect(self, apn: str = "", user: str = "", pwd: str = "") -> str:
        """Подключить GPRS/данные."""
        apn = apn or os.getenv("SIM_APN", "internet")
        user = user or os.getenv("SIM_USER", "")
        pwd = pwd or os.getenv("SIM_PWD", "")
        cmds = [
            f'AT+SAPBR=3,1,"Contype","GPRS"',
            f'AT+SAPBR=3,1,"APN","{apn}"',
            f'AT+SAPBR=3,1,"USER","{user}"',
            f'AT+SAPBR=3,1,"PWD","{pwd}"',
            "AT+SAPBR=1,1",
            "AT+SAPBR=2,1",
        ]
        results = []
        for cmd in cmds:
            try:
                r = self._send_at(cmd, timeout=8)
                results.append(r)
            except Exception as exc:
                return f"❌ GPRS ошибка: {exc}"
        # Получаем IP
        m = re.search(r'"(\d+\.\d+\.\d+\.\d+)"', " ".join(results))
        ip = m.group(1) if m else "?"
        return f"✅ GPRS подключён, IP: {ip}"

    def gprs_disconnect(self) -> str:
        try:
            return self._send_at("AT+SAPBR=0,1", timeout=5)
        except Exception as exc:
            return str(exc)

    # ── Статус / диагностика ──────────────────────────────────────────────────

    def status(self) -> str:
        """Статус модема для ArgosCore."""
        if not self.is_connected():
            return "📵 SIM800C: не подключён"
        self._update_signal()
        bars = "▁▃▅█"[min(self._signal // 8, 3)]
        lines = [
            "📡 SIM800C GSM",
            f"  Порт     : {self.port} @ {self.baudrate}",
            f"  Оператор : {self._operator or '?'}",
            f"  Сигнал   : {bars} (CSQ={self._signal})",
            f"  Номер    : {self._phone_number or 'не задан'}",
        ]
        try:
            bat = self._send_at("AT+CBC", timeout=3)
            m = re.search(r"\+CBC:\s*\d+,(\d+),(\d+)", bat)
            if m:
                pct = m.group(1)
                mv = m.group(2)
                lines.append(f"  Питание  : {pct}% ({mv} мВ)")
        except Exception:
            pass
        return "\n".join(lines)

    def raw_at(self, cmd: str, timeout: float = 5.0) -> str:
        """Отправить произвольную AT-команду (для отладки)."""
        try:
            return self._send_at(cmd, timeout=timeout)
        except Exception as exc:
            return f"❌ {exc}"

    # ── Фоновый опрос SMS ─────────────────────────────────────────────────────

    def start_polling(self, core=None) -> str:
        """
        Запустить фоновый опрос входящих SMS.
        Если передан core — команды из SMS передаются в ArgosCore.
        """
        if self._running:
            return "⚠️ Опрос уже запущен"
        if not self.is_connected():
            result = self.connect()
            if "❌" in result:
                return result

        self._running = True

        def _loop():
            while self._running:
                try:
                    msgs = self.read_sms("REC UNREAD")
                    for msg in msgs:
                        sender = msg["sender"]
                        text = msg["text"]
                        ts = msg["timestamp"]
                        log.info("SMS от %s: %s", sender, text)
                        # Callback пользователя
                        if self.on_sms:
                            self.on_sms(sender, text, ts)
                        # Передача команды в ArgosCore
                        if core and text:
                            try:
                                result = core.process(text)
                                answer = result.get("answer", "") if isinstance(result, dict) else str(result)
                                if answer and sender:
                                    self.send_sms(sender, answer[:160])
                            except Exception as exc:
                                log.error("Core error: %s", exc)
                        # Удаляем обработанные
                        self.delete_sms(msg["index"], flag=0)
                    # Проверяем входящие звонки
                    self._check_incoming_call()
                except Exception as exc:
                    log.warning("poll error: %s", exc)
                time.sleep(self.SMS_POLL_INTERVAL)

        self._poll_thread = threading.Thread(target=_loop, daemon=True, name="SIM800C_Poll")
        self._poll_thread.start()
        return f"✅ Фоновый опрос SMS запущен (интервал {self.SMS_POLL_INTERVAL}с)"

    def stop_polling(self):
        self._running = False

    def _check_incoming_call(self):
        """Проверить наличие входящего звонка."""
        if not self._ser or not self._ser.in_waiting:
            return
        try:
            raw = self._ser.read(self._ser.in_waiting).decode("utf-8", errors="replace")
            if "RING" in raw:
                m = re.search(r"\+CLIP:\s*\"([^\"]+)\"", raw)
                number = m.group(1) if m else "unknown"
                log.info("Входящий звонок от %s", number)
                if self.on_call:
                    self.on_call(number)
        except Exception:
            pass


# ── Фасад для ArgosCore ───────────────────────────────────────────────────────

class SIM800CBridge:
    """
    Обёртка SIM800C для MessengerRouter и ArgosCore.
    Реализует тот же интерфейс что WhatsAppBridge / SlackBridge.
    """

    def __init__(self, port: str = "", platform: str = "auto"):
        self._modem = SIM800C(port=port, platform=platform)
        self._connected = False

    def _ensure_connected(self) -> bool:
        if not self._connected or not self._modem.is_connected():
            result = self._modem.connect()
            self._connected = "✅" in result
        return self._connected

    def _configured(self) -> bool:
        return _SERIAL_OK

    def send_message(self, to: str, text: str, **kwargs) -> dict[str, Any]:
        """Отправить SMS (интерфейс MessengerRouter)."""
        if not self._ensure_connected():
            return {"ok": False, "provider": "sim800c", "error": "Нет подключения"}
        return self._modem.send_sms(to, text[:160])

    def receive_messages(self) -> dict[str, Any]:
        """Получить входящие SMS."""
        if not self._ensure_connected():
            return {"ok": False, "provider": "sim800c", "error": "Нет подключения"}
        msgs = self._modem.read_sms("ALL")
        return {"ok": True, "provider": "sim800c", "data": msgs}

    def poll_commands(self) -> list[str]:
        """Команды из непрочитанных SMS для ArgosCore."""
        if not self._ensure_connected():
            return []
        return self._modem.poll_commands()

    def status(self) -> str:
        if not self._ensure_connected():
            return "📵 SIM800C: не подключён"
        return self._modem.status()

    def ussd(self, code: str) -> str:
        self._ensure_connected()
        return self._modem.ussd(code)

    def balance(self) -> str:
        self._ensure_connected()
        return self._modem.balance()

    def call(self, number: str) -> dict[str, Any]:
        self._ensure_connected()
        return self._modem.call(number)

    def hangup(self) -> str:
        self._ensure_connected()
        return self._modem.hangup()

    def raw_at(self, cmd: str) -> str:
        self._ensure_connected()
        return self._modem.raw_at(cmd)

    def start_polling(self, core=None) -> str:
        self._ensure_connected()
        return self._modem.start_polling(core=core)

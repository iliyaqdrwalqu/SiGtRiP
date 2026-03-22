"""
src/connectivity/protocols/sensor_bridges.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Мосты для датчиков:
  • OnewireBridge  — 1-Wire (DS18B20, DS2438) через /sys/bus/w1
  • I2CBridge      — I2C (BME280, SHT30, ADS1115, BMP180...)
  • RS485Bridge    — RS-485 raw serial (без Modbus)
  • MQTTBridge     — MQTT клиент/публикатор

Схема 1-Wire (DS18B20):
  DS18B20 VCC → 3.3V
  DS18B20 GND → GND
  DS18B20 DATA → GPIO4 + 4.7kΩ резистор к 3.3V
  /boot/config.txt: dtoverlay=w1-gpio,gpiopin=4

Схема I2C (BME280):
  BME280 VCC → 3.3V
  BME280 GND → GND
  BME280 SDA → GPIO2 (SDA)
  BME280 SCL → GPIO3 (SCL)
  i2cdetect -y 1  →  должен показать 0x76 или 0x77

pip install w1thermsensor smbus2 paho-mqtt
"""
from __future__ import annotations

import os
import time
import logging
import threading
from typing import Any, Callable

log = logging.getLogger("argos.sensors")


# ══════════════════════════════════════════════════════════════════════════════
# 1-Wire (DS18B20)
# ══════════════════════════════════════════════════════════════════════════════

class OnewireBridge:
    """Чтение 1-Wire датчиков температуры через Linux /sys/bus/w1."""

    W1_ROOT = "/sys/bus/w1/devices"

    def __init__(self, gpio_pin: int = 4):
        self.gpio_pin = gpio_pin

    def _is_available(self) -> bool:
        return os.path.isdir(self.W1_ROOT)

    def scan(self) -> list[str]:
        """Список ID обнаруженных 1-Wire датчиков."""
        if not self._is_available():
            return []
        try:
            return [
                d for d in os.listdir(self.W1_ROOT)
                if d.startswith("28-")  # DS18B20 family code = 0x28
            ]
        except Exception:
            return []

    def read_temperature(self, sensor_id: str) -> float | None:
        """Прочитать температуру одного датчика (°C)."""
        path = os.path.join(self.W1_ROOT, sensor_id, "w1_slave")
        try:
            with open(path) as f:
                content = f.read()
            if "YES" not in content:
                return None
            t_pos = content.find("t=")
            if t_pos == -1:
                return None
            t_raw = int(content[t_pos + 2:].strip())
            return t_raw / 1000.0
        except Exception:
            return None

    def read_all(self) -> dict[str, float | None]:
        """Прочитать все найденные датчики."""
        sensors = self.scan()
        return {s: self.read_temperature(s) for s in sensors}

    def status(self) -> str:
        if not self._is_available():
            return (
                "🌡️ 1-Wire: не доступен\n"
                "  Добавьте в /boot/config.txt:\n"
                "    dtoverlay=w1-gpio,gpiopin=4"
            )
        sensors = self.read_all()
        lines = [f"🌡️ 1-Wire датчики ({len(sensors)}):"]
        for sid, temp in sensors.items():
            lines.append(f"  • {sid}: {temp:.2f}°C" if temp is not None else f"  • {sid}: ошибка")
        return "\n".join(lines)

    def handle_command(self, cmd: str) -> str | None:
        c = cmd.lower().strip()
        if c in ("1wire", "ds18b20", "температура"):
            return self.status()
        return None


# ══════════════════════════════════════════════════════════════════════════════
# I2C / SMBus
# ══════════════════════════════════════════════════════════════════════════════

class I2CBridge:
    """I2C шина — BME280, SHT30, ADS1115, SSD1306, BH1750 и другие."""

    def __init__(self, bus: int = 1):
        self.bus_num = bus
        self._bus = None
        self._init_bus()

    def _init_bus(self):
        try:
            import smbus2  # type: ignore
            self._bus = smbus2.SMBus(self.bus_num)
        except ImportError:
            try:
                import smbus  # type: ignore
                self._bus = smbus.SMBus(self.bus_num)
            except ImportError:
                self._bus = None

    def scan(self) -> list[int]:
        """Сканировать I2C шину (адреса 0x03..0x77)."""
        found = []
        if not self._bus:
            return found
        for addr in range(3, 0x78):
            try:
                self._bus.read_byte(addr)
                found.append(addr)
            except OSError:
                pass
        return found

    def read_byte(self, addr: int, reg: int) -> int | None:
        if not self._bus:
            return None
        try:
            return self._bus.read_byte_data(addr, reg)
        except Exception:
            return None

    def read_word(self, addr: int, reg: int, big_endian: bool = False) -> int | None:
        if not self._bus:
            return None
        try:
            raw = self._bus.read_word_data(addr, reg)
            if big_endian:
                return ((raw & 0xFF) << 8) | ((raw >> 8) & 0xFF)
            return raw
        except Exception:
            return None

    def write_byte(self, addr: int, reg: int, value: int) -> bool:
        if not self._bus:
            return False
        try:
            self._bus.write_byte_data(addr, reg, value)
            return True
        except Exception:
            return False

    def read_block(self, addr: int, reg: int, length: int) -> bytes:
        if not self._bus:
            return b""
        try:
            return bytes(self._bus.read_i2c_block_data(addr, reg, length))
        except Exception:
            return b""

    # ── BME280 (0x76 / 0x77) ─────────────────────────────────────────────────

    def read_bme280(self, addr: int = 0x76) -> dict[str, float]:
        """
        Упрощённое чтение BME280.
        Для точности используйте adafruit-circuitpython-bme280.
        """
        try:
            import struct
            # Сброс + режим нормальный
            self.write_byte(addr, 0xF2, 0x01)  # ctrl_hum: oversample×1
            self.write_byte(addr, 0xF4, 0x27)  # ctrl_meas: temp×1 press×1 normal
            time.sleep(0.1)
            # Читаем raw данные
            raw = self.read_block(addr, 0xF7, 8)
            if len(raw) < 8:
                return {}
            press_raw = ((raw[0] << 16) | (raw[1] << 8) | raw[2]) >> 4
            temp_raw  = ((raw[3] << 16) | (raw[4] << 8) | raw[5]) >> 4
            hum_raw   = (raw[6] << 8)  |  raw[7]
            # Читаем калибровочные данные (упрощённо)
            cal = self.read_block(addr, 0x88, 24)
            if len(cal) < 24:
                return {"raw_temp": temp_raw, "raw_press": press_raw}
            T1 = struct.unpack_from("<H", cal, 0)[0]
            T2 = struct.unpack_from("<h", cal, 2)[0]
            T3 = struct.unpack_from("<h", cal, 4)[0]
            var1 = (temp_raw / 16384.0 - T1 / 1024.0) * T2
            var2 = (temp_raw / 131072.0 - T1 / 8192.0) ** 2 * T3
            t_fine = var1 + var2
            temp = t_fine / 5120.0
            return {"temperature": round(temp, 2)}
        except Exception as exc:
            return {"error": str(exc)}

    # ── BH1750 (0x23 / 0x5C) ─────────────────────────────────────────────────

    def read_bh1750(self, addr: int = 0x23) -> float | None:
        """Освещённость в люксах."""
        try:
            self.write_byte(addr, 0x10, 0x00)  # непрерывное измерение H-res
            time.sleep(0.18)
            raw = self.read_block(addr, 0x00, 2)
            if len(raw) >= 2:
                return ((raw[0] << 8) | raw[1]) / 1.2
        except Exception:
            pass
        return None

    # ── ADS1115 (0x48) ADC ───────────────────────────────────────────────────

    def read_ads1115(self, addr: int = 0x48, channel: int = 0) -> float | None:
        """АЦП ADS1115 — напряжение в вольтах (0..3.3V)."""
        try:
            mux = 0x4000 | ((4 + channel) << 12)
            config = mux | 0x0200 | 0x0100 | 0x8000
            hi = (config >> 8) & 0xFF
            lo = config & 0xFF
            self.write_byte(addr, 0x01, hi)
            self.write_byte(addr, 0x01, lo)
            time.sleep(0.01)
            raw = self.read_block(addr, 0x00, 2)
            if len(raw) >= 2:
                val = (raw[0] << 8) | raw[1]
                if val > 32767:
                    val -= 65536
                return val * 4.096 / 32768.0
        except Exception:
            pass
        return None

    def status(self) -> str:
        if not self._bus:
            return "🔌 I2C: smbus2 не установлен (pip install smbus2)"
        devices = self.scan()
        lines = [f"🔌 I2C шина {self.bus_num} — найдено {len(devices)} устройств:"]
        known = {
            0x20: "PCF8574 (GPIO expander)",
            0x23: "BH1750 (освещённость)",
            0x27: "LCD PCF8574",
            0x3C: "SSD1306 OLED",
            0x48: "ADS1115 (АЦП)",
            0x68: "MPU-6050 / DS3231 RTC",
            0x76: "BME280 (T+P+H)",
            0x77: "BME280 / BMP180",
        }
        for addr in devices:
            name = known.get(addr, "неизвестное")
            lines.append(f"  • 0x{addr:02X} — {name}")
        return "\n".join(lines)

    def handle_command(self, cmd: str) -> str | None:
        c = cmd.lower().strip()
        if c in ("i2c", "i2c скан", "i2c статус"):
            return self.status()
        if c == "bme280":
            r = self.read_bme280()
            return f"BME280: {r}"
        return None


# ══════════════════════════════════════════════════════════════════════════════
# RS-485 (raw serial, без Modbus)
# ══════════════════════════════════════════════════════════════════════════════

class RS485Bridge:
    """
    Прямой RS-485 мост без Modbus.
    Для проприетарных протоколов (DALI, DMX-512 и т.д.)
    """

    def __init__(
        self,
        port: str = "",
        baudrate: int = 9600,
        rts_pin: int | None = None,
        on_receive: Callable[[bytes], None] | None = None,
    ):
        self.port = port or os.getenv("RS485_PORT", "/dev/ttyUSB0")
        self.baudrate = baudrate
        self.rts_pin = rts_pin
        self.on_receive = on_receive
        self._ser = None
        self._running = False

    def connect(self) -> str:
        try:
            import serial  # type: ignore
            kwargs: dict = {"port": self.port, "baudrate": self.baudrate, "timeout": 0.5}
            if self.rts_pin:
                kwargs["rtscts"] = True
            self._ser = serial.Serial(**kwargs)
            return f"✅ RS-485: {self.port} @ {self.baudrate}"
        except ImportError:
            return "❌ pyserial не установлен"
        except Exception as exc:
            return f"❌ RS-485: {exc}"

    def send(self, data: bytes) -> bool:
        if not self._ser or not self._ser.is_open:
            return False
        try:
            self._ser.write(data)
            self._ser.flush()
            return True
        except Exception:
            return False

    def receive(self, timeout: float = 1.0) -> bytes:
        if not self._ser:
            return b""
        deadline = time.time() + timeout
        buf = b""
        while time.time() < deadline:
            if self._ser.in_waiting:
                buf += self._ser.read(self._ser.in_waiting)
            time.sleep(0.01)
        return buf

    def status(self) -> str:
        conn = bool(self._ser and self._ser.is_open)
        return f"📡 RS-485: {self.port} {'✅' if conn else '❌'}"


# ══════════════════════════════════════════════════════════════════════════════
# MQTT клиент
# ══════════════════════════════════════════════════════════════════════════════

class MQTTBridge:
    """
    MQTT клиент для ARGOS.
    Подписка на топики, публикация сообщений.
    """

    def __init__(
        self,
        host: str = "",
        port: int = 1883,
        user: str = "",
        pwd: str = "",
        client_id: str = "argos-mqtt",
        on_message: Callable[[str, str], None] | None = None,
    ):
        self.host = host or os.getenv("MQTT_HOST", "localhost")
        self.port = port or int(os.getenv("MQTT_PORT", "1883"))
        self.user = user or os.getenv("MQTT_USER", "")
        self.pwd  = pwd  or os.getenv("MQTT_PWD", "")
        self.client_id = client_id
        self.on_message = on_message
        self._client = None
        self._connected = False
        self._subscriptions: set[str] = set()

    def connect(self) -> str:
        try:
            import paho.mqtt.client as mqtt  # type: ignore
        except ImportError:
            return "❌ paho-mqtt не установлен: pip install paho-mqtt"
        self._client = mqtt.Client(client_id=self.client_id)
        if self.user:
            self._client.username_pw_set(self.user, self.pwd)
        self._client.on_connect    = self._on_connect
        self._client.on_message    = self._on_message
        self._client.on_disconnect = lambda c, u, rc: setattr(self, "_connected", False)
        try:
            self._client.connect(self.host, self.port, keepalive=60)
            self._client.loop_start()
            time.sleep(0.8)
            return f"✅ MQTT: {self.host}:{self.port}"
        except Exception as exc:
            return f"❌ MQTT: {exc}"

    def _on_connect(self, client, userdata, flags, rc):
        self._connected = (rc == 0)
        for topic in self._subscriptions:
            client.subscribe(topic)

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        try:
            payload = msg.payload.decode("utf-8")
        except Exception:
            payload = msg.payload.hex()
        if self.on_message:
            self.on_message(topic, payload)

    def subscribe(self, topic: str, qos: int = 0) -> bool:
        self._subscriptions.add(topic)
        if self._client and self._connected:
            self._client.subscribe(topic, qos)
            return True
        return False

    def publish(self, topic: str, payload: str | bytes | dict, qos: int = 0, retain: bool = False) -> bool:
        if not self._client or not self._connected:
            return False
        import json as _json
        if isinstance(payload, dict):
            payload = _json.dumps(payload)
        self._client.publish(topic, payload, qos=qos, retain=retain)
        return True

    def disconnect(self):
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
        self._connected = False

    def status(self) -> str:
        subs = ", ".join(list(self._subscriptions)[:5]) or "нет"
        return (
            f"📡 MQTT\n"
            f"  Брокер : {self.host}:{self.port}\n"
            f"  Статус : {'✅ подключён' if self._connected else '❌ не подключён'}\n"
            f"  Топики : {subs}"
        )

    def handle_command(self, cmd: str) -> str | None:
        c = cmd.lower().strip()
        if c in ("mqtt", "mqtt статус"):
            return self.status()
        if c.startswith("mqtt публикация "):
            # mqtt публикация <topic> <payload>
            parts = cmd.split(None, 3)
            if len(parts) >= 4:
                ok = self.publish(parts[2], parts[3])
                return f"✅ MQTT → {parts[2]}" if ok else "❌ MQTT не подключён"
        return None

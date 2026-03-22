"""
src/connectivity/iot_hub.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Единый IoT-хаб ARGOS.

Объединяет все протоколы под одним интерфейсом:
  Беспроводные : Zigbee, LoRa, BLE, Z-Wave, WiFi/MQTT
  Проводные    : Modbus RTU/TCP, RS-485, 1-Wire, I2C/SPI
  GSM          : SIM800C (SMS, GPRS)
  NFC          : NDEF, MIFARE, NTAG
  Промышленные : KNX, M-Bus, OPC UA, BACnet, LonWorks
  Платформы    : Home Assistant, Tasmota

Все протоколы подключаются лениво — только при первом использовании.
"""
from __future__ import annotations

import os
import time
import logging
import threading
from typing import Any

log = logging.getLogger("argos.iot_hub")


class ArgosIoTHub:
    """
    Центральный IoT-хаб ARGOS.
    Роутер команд → протокол → устройство.
    """

    def __init__(self, core=None):
        self.core = core
        # Ленивая инициализация — создаём только при обращении
        self._zigbee = None
        self._lora = None
        self._ble = None
        self._modbus = None
        self._zwave = None
        self._ha = None
        self._tasmota = None
        self._nfc = None
        self._onewire = None
        self._i2c = None
        self._rs485 = None
        self._mqtt = None
        self._gsm = None
        self._lon = None
        self._lock = threading.RLock()

    # ── Фабричные методы (ленивая загрузка) ──────────────────────────────────

    @property
    def zigbee(self):
        with self._lock:
            if self._zigbee is None:
                from .protocols.zigbee_bridge import ZigbeeBridge
                self._zigbee = ZigbeeBridge(
                    on_device_update=self._on_device_update
                )
            return self._zigbee

    @property
    def lora(self):
        with self._lock:
            if self._lora is None:
                from .protocols.lora_bridge import LoRaBridge
                self._lora = LoRaBridge(
                    on_receive=self._on_lora_receive
                )
            return self._lora

    @property
    def ble(self):
        with self._lock:
            if self._ble is None:
                from .protocols.ble_bridge import BLEBridge
                self._ble = BLEBridge()
            return self._ble

    @property
    def modbus(self):
        with self._lock:
            if self._modbus is None:
                from .protocols.modbus_bridge import ModbusBridge
                mode = os.getenv("MODBUS_MODE", "rtu")
                self._modbus = ModbusBridge(mode=mode)
            return self._modbus

    @property
    def zwave(self):
        with self._lock:
            if self._zwave is None:
                from .protocols.platform_bridges import ZWaveBridge
                self._zwave = ZWaveBridge()
            return self._zwave

    @property
    def ha(self):
        with self._lock:
            if self._ha is None:
                from .protocols.platform_bridges import HomeAssistantBridge
                self._ha = HomeAssistantBridge()
            return self._ha

    @property
    def tasmota(self):
        with self._lock:
            if self._tasmota is None:
                from .protocols.platform_bridges import TasmotaBridge
                self._tasmota = TasmotaBridge()
            return self._tasmota

    @property
    def nfc(self):
        with self._lock:
            if self._nfc is None:
                from .protocols.nfc_bridge import NFCBridge
                self._nfc = NFCBridge(on_tag=self._on_nfc_tag)
            return self._nfc

    @property
    def onewire(self):
        with self._lock:
            if self._onewire is None:
                from .protocols.sensor_bridges import OnewireBridge
                self._onewire = OnewireBridge()
            return self._onewire

    @property
    def i2c(self):
        with self._lock:
            if self._i2c is None:
                from .protocols.sensor_bridges import I2CBridge
                self._i2c = I2CBridge()
            return self._i2c

    @property
    def mqtt(self):
        with self._lock:
            if self._mqtt is None:
                from .protocols.sensor_bridges import MQTTBridge
                self._mqtt = MQTTBridge(
                    on_message=self._on_mqtt_message
                )
            return self._mqtt

    @property
    def gsm(self):
        with self._lock:
            if self._gsm is None:
                from .sim800c import SIM800CBridge
                self._gsm = SIM800CBridge()
            return self._gsm

    @property
    def lon(self):
        with self._lock:
            if self._lon is None:
                from .protocols.platform_bridges import LonWorksBridge
                self._lon = LonWorksBridge()
            return self._lon

    # ── Callbacks ────────────────────────────────────────────────────────────

    def _on_device_update(self, device: str, state: dict):
        log.debug("Zigbee %s: %s", device, state)

    def _on_lora_receive(self, raw: bytes, meta: dict):
        log.info("LoRa: %s", meta.get("text", raw.hex()))
        if self.core and meta.get("text"):
            try:
                self.core.process(meta["text"])
            except Exception:
                pass

    def _on_nfc_tag(self, tag: dict):
        log.info("NFC тег: %s", tag.get("uid"))
        if self.core and tag.get("text"):
            try:
                self.core.process(tag["text"])
            except Exception:
                pass

    def _on_mqtt_message(self, topic: str, payload: str):
        log.debug("MQTT %s: %s", topic, payload)
        # Топик argos/command → выполнить команду
        if topic == "argos/command" and self.core:
            try:
                result = self.core.process(payload)
                answer = result.get("answer", "") if isinstance(result, dict) else str(result)
                self.mqtt.publish("argos/response", answer)
            except Exception as exc:
                log.error("MQTT command: %s", exc)

    # ── Универсальный роутер ──────────────────────────────────────────────────

    def route(self, protocol: str, device: str, action: str, **kwargs) -> dict[str, Any]:
        """
        Универсальная команда устройству.
        route("zigbee", "living_room_light", "turn_on", brightness=200)
        route("modbus", "pump_1", "write", address=100, value=1)
        route("ha", "light.kitchen", "turn_on")
        route("gsm", "+79001234567", "sms", text="статус")
        """
        proto = protocol.lower()
        act = action.lower()

        if proto == "zigbee":
            if act == "turn_on":
                return {"ok": self.zigbee.turn_on(device, brightness=kwargs.get("brightness"))}
            if act == "turn_off":
                return {"ok": self.zigbee.turn_off(device)}
            if act == "set":
                return {"ok": self.zigbee.set_state(device, kwargs)}

        if proto in ("ha", "homeassistant"):
            if act == "turn_on":
                return {"ok": bool(self.ha.turn_on(device, **kwargs))}
            if act == "turn_off":
                return {"ok": bool(self.ha.turn_off(device))}
            if act == "service":
                return {"ok": bool(self.ha.call_service(kwargs.get("domain",""), device, kwargs))}

        if proto == "modbus":
            if act == "read":
                return self.modbus.read_holding(kwargs.get("address", 0), unit=kwargs.get("unit", 1))
            if act == "write":
                return self.modbus.write_register(kwargs.get("address", 0), kwargs.get("value", 0))

        if proto == "tasmota":
            if act == "turn_on":
                return {"ok": self.tasmota.turn_on(device)}
            if act == "turn_off":
                return {"ok": self.tasmota.turn_off(device)}

        if proto == "gsm":
            if act == "sms":
                return self.gsm.send_message(device, kwargs.get("text", ""))
            if act == "call":
                return self.gsm.call(device)

        if proto in ("zwave", "z-wave"):
            if act == "turn_on":
                return self.zwave.turn_on(int(device))
            if act == "turn_off":
                return self.zwave.turn_off(int(device))

        if proto == "mqtt":
            ok = self.mqtt.publish(device, kwargs.get("payload", action))
            return {"ok": ok}

        if proto == "lora":
            return self.lora.send(kwargs.get("data", action), kwargs.get("addr", 0xFFFF))

        return {"ok": False, "error": f"Неизвестный протокол: {protocol}"}

    # ── Запуск всех фоновых служб ─────────────────────────────────────────────

    def start_all(self) -> str:
        """Запустить все настроенные IoT протоколы."""
        results = []

        if os.getenv("ZIGBEE_MQTT_HOST"):
            results.append(self.zigbee.connect())
        if os.getenv("LORA_PORT"):
            results.append(self.lora.connect())
            results.append(self.lora.start_receive())
        if os.getenv("MQTT_HOST"):
            results.append(self.mqtt.connect())
            self.mqtt.subscribe("argos/#")
        if os.getenv("HA_TOKEN"):
            pass  # HA — без постоянного подключения, по запросу
        if os.getenv("TASMOTA_MQTT_HOST"):
            results.append(self.tasmota.connect())
        if os.getenv("SIM800C_PORT") or os.getenv("SIM800C_PLATFORM"):
            results.append(self.gsm.start_polling(core=self.core))

        if not results:
            return "⚠️ IoT: нет настроенных протоколов. Добавьте переменные в .env"
        return "🌐 IoT Hub запущен:\n" + "\n".join(f"  {r}" for r in results)

    # ── Сбор телеметрии ───────────────────────────────────────────────────────

    def collect_telemetry(self) -> dict[str, Any]:
        """Собрать данные со всех доступных датчиков."""
        data: dict[str, Any] = {}

        # 1-Wire температура
        try:
            temps = self.onewire.read_all()
            if temps:
                data["temperatures_1wire"] = temps
        except Exception:
            pass

        # I2C датчики
        try:
            bme = self.i2c.read_bme280()
            if bme:
                data["bme280"] = bme
        except Exception:
            pass

        # Zigbee устройства
        if self._zigbee:
            data["zigbee_devices"] = len(self.zigbee.get_devices())

        # GSM
        if self._gsm:
            data["gsm_status"] = "connected" if self.gsm._modem.is_connected() else "disconnected"

        return data

    # ── Статус ────────────────────────────────────────────────────────────────

    def status(self) -> str:
        lines = ["🌐 ARGOS IoT HUB\n"]

        checks = [
            ("📡 Zigbee",         self._zigbee,  "ZIGBEE_MQTT_HOST"),
            ("📻 LoRa",           self._lora,    "LORA_PORT"),
            ("🔵 BLE",            self._ble,     None),
            ("🔵 Z-Wave",         self._zwave,   "ZWAVE_API_URL"),
            ("📡 MQTT",           self._mqtt,    "MQTT_HOST"),
            ("🏠 Home Assistant", self._ha,      "HA_TOKEN"),
            ("💡 Tasmota",        self._tasmota, "TASMOTA_MQTT_HOST"),
            ("📱 NFC",            self._nfc,     None),
            ("🌡️ 1-Wire",         self._onewire, None),
            ("🔌 I2C",            self._i2c,     None),
            ("⚙️ Modbus",         self._modbus,  "MODBUS_PORT"),
            ("📵 GSM/SIM800C",    self._gsm,     "SIM800C_PORT"),
            ("🔗 LonWorks",       self._lon,     "LONWORKS_ADAPTER"),
        ]

        for label, instance, env_key in checks:
            if instance is not None:
                icon = "✅"
            elif env_key and os.getenv(env_key):
                icon = "⚙️ "
            else:
                icon = "○ "
            lines.append(f"  {icon} {label}")

        tele = self.collect_telemetry()
        if tele:
            lines.append("\n📊 Телеметрия:")
            for k, v in tele.items():
                lines.append(f"  {k}: {v}")

        return "\n".join(lines)

    # ── Обработчик команд ArgosCore ───────────────────────────────────────────

    def handle_command(self, cmd: str) -> str | None:
        c = cmd.lower().strip()

        # Глобальный статус
        if c in ("iot", "iot статус", "умные устройства"):
            return self.status()
        if c == "iot запуск":
            return self.start_all()
        if c == "iot телеметрия":
            tele = self.collect_telemetry()
            return f"📊 IoT телеметрия:\n" + "\n".join(f"  {k}: {v}" for k, v in tele.items())

        # Делегирование к протоколам
        handlers = [
            self.zigbee.handle_command,
            self.lora.handle_command,
            self.ble.handle_command,
            self.modbus.handle_command,
            self.zwave.handle_command,
            self.ha.handle_command,
            self.tasmota.handle_command,
            self.nfc.handle_command,
            self.onewire.handle_command,
            self.i2c.handle_command,
            self.mqtt.handle_command,
        ]
        for handler in handlers:
            try:
                result = handler(cmd)
                if result is not None:
                    return result
            except Exception as exc:
                log.debug("handler %s: %s", handler, exc)

        return None

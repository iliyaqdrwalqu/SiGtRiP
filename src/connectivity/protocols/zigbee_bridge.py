"""
src/connectivity/protocols/zigbee_bridge.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Zigbee мост для ARGOS.

Режимы работы:
  1. MQTT (через zigbee2mqtt) — рекомендуется
     Zigbee координатор → zigbee2mqtt → Mosquitto MQTT → ARGOS
  2. Serial (zigpy) — прямое управление координатором
     Zigbee координатор USB → /dev/ttyACM0 → ARGOS

Поддерживаемые координаторы:
  • CC2531 (USB донгл, прошивка Z-Stack)
  • CC2652R/P (лучший выбор, Sonoff Zigbee 3.0)
  • ConBee II / RaspBee II (Dresden Elektronik)
  • HUSBZB-1 (Silicon Labs EM358)

Схема подключения (CC2531 USB):
  CC2531 USB → RPi / PC USB порт → /dev/ttyACM0
  (питание и данные через USB — доп. проводов не нужно)

pip install paho-mqtt zigpy zigpy-cc (опционально)
"""
from __future__ import annotations

import json
import os
import threading
import time
import logging
from typing import Any, Callable

try:
    import paho.mqtt.client as mqtt  # type: ignore
    _MQTT_OK = True
except ImportError:
    _MQTT_OK = False

log = logging.getLogger("argos.zigbee")


class ZigbeeBridge:
    """
    Zigbee мост через zigbee2mqtt (MQTT).
    Управляет устройствами, подписывается на события.
    """

    TOPIC_BASE = "zigbee2mqtt"

    def __init__(
        self,
        mqtt_host: str = "",
        mqtt_port: int = 1883,
        mqtt_user: str = "",
        mqtt_pwd: str = "",
        on_device_update: Callable[[str, dict], None] | None = None,
    ):
        self.mqtt_host = mqtt_host or os.getenv("ZIGBEE_MQTT_HOST", "localhost")
        self.mqtt_port = mqtt_port or int(os.getenv("ZIGBEE_MQTT_PORT", "1883"))
        self.mqtt_user = mqtt_user or os.getenv("ZIGBEE_MQTT_USER", "")
        self.mqtt_pwd  = mqtt_pwd  or os.getenv("ZIGBEE_MQTT_PWD", "")
        self.on_device_update = on_device_update
        self._client: Any = None
        self._devices: dict[str, dict] = {}
        self._connected = False

    # ── Подключение ───────────────────────────────────────────────────────────

    def connect(self) -> str:
        if not _MQTT_OK:
            return "❌ paho-mqtt не установлен: pip install paho-mqtt"
        self._client = mqtt.Client(client_id="argos-zigbee")
        if self.mqtt_user:
            self._client.username_pw_set(self.mqtt_user, self.mqtt_pwd)
        self._client.on_connect    = self._on_connect
        self._client.on_message    = self._on_message
        self._client.on_disconnect = self._on_disconnect
        try:
            self._client.connect(self.mqtt_host, self.mqtt_port, keepalive=60)
            self._client.loop_start()
            time.sleep(1.0)
            return f"✅ Zigbee MQTT: {self.mqtt_host}:{self.mqtt_port}"
        except Exception as exc:
            return f"❌ Zigbee MQTT: {exc}"

    def disconnect(self):
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
        self._connected = False

    # ── MQTT callbacks ────────────────────────────────────────────────────────

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._connected = True
            # Подписываемся на все устройства и бридж
            client.subscribe(f"{self.TOPIC_BASE}/#")
            log.info("Zigbee MQTT подключён")
        else:
            log.error("Zigbee MQTT rc=%s", rc)

    def _on_disconnect(self, client, userdata, rc):
        self._connected = False

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            return

        # zigbee2mqtt/<device_name>
        parts = topic.split("/")
        if len(parts) == 2:
            device_name = parts[1]
            if device_name not in ("bridge",):
                self._devices[device_name] = {**self._devices.get(device_name, {}), **payload}
                if self.on_device_update:
                    self.on_device_update(device_name, payload)

        # Список устройств
        if topic == f"{self.TOPIC_BASE}/bridge/devices":
            if isinstance(payload, list):
                for dev in payload:
                    name = dev.get("friendly_name", dev.get("ieee_address", ""))
                    self._devices.setdefault(name, {})["info"] = dev

    # ── Управление устройствами ───────────────────────────────────────────────

    def set_state(self, device: str, state: dict) -> bool:
        """
        Установить состояние устройства.
        Примеры:
          set_state("living_room_light", {"state": "ON"})
          set_state("thermostat", {"occupied_heating_setpoint": 22})
          set_state("dimmer", {"brightness": 128, "state": "ON"})
        """
        if not self._connected or not self._client:
            return False
        topic = f"{self.TOPIC_BASE}/{device}/set"
        self._client.publish(topic, json.dumps(state))
        return True

    def get_state(self, device: str) -> dict:
        """Запросить текущее состояние устройства."""
        return self._devices.get(device, {})

    def get_devices(self) -> dict[str, dict]:
        """Список всех известных устройств."""
        return dict(self._devices)

    def permit_join(self, duration: int = 60) -> bool:
        """Разрешить сопряжение новых устройств на N секунд."""
        if not self._connected:
            return False
        payload = json.dumps({"value": True, "time": duration})
        self._client.publish(f"{self.TOPIC_BASE}/bridge/request/permit_join", payload)
        return True

    def rename_device(self, old_name: str, new_name: str) -> bool:
        if not self._connected:
            return False
        payload = json.dumps({"from": old_name, "to": new_name})
        self._client.publish(f"{self.TOPIC_BASE}/bridge/request/device/rename", payload)
        return True

    # ── Быстрые команды ───────────────────────────────────────────────────────

    def turn_on(self, device: str, brightness: int | None = None) -> bool:
        state: dict = {"state": "ON"}
        if brightness is not None:
            state["brightness"] = max(0, min(254, brightness))
        return self.set_state(device, state)

    def turn_off(self, device: str) -> bool:
        return self.set_state(device, {"state": "OFF"})

    def toggle(self, device: str) -> bool:
        return self.set_state(device, {"state": "TOGGLE"})

    def set_color_temp(self, device: str, temp_k: int) -> bool:
        """Цветовая температура 2700K–6500K → mireds."""
        mireds = int(1_000_000 / temp_k)
        return self.set_state(device, {"color_temp": mireds})

    def set_color_rgb(self, device: str, r: int, g: int, b: int) -> bool:
        return self.set_state(device, {"color": {"r": r, "g": g, "b": b}})

    # ── Статус ────────────────────────────────────────────────────────────────

    def status(self) -> str:
        lines = [
            "📡 ZIGBEE",
            f"  MQTT : {self.mqtt_host}:{self.mqtt_port}",
            f"  Статус: {'✅ подключён' if self._connected else '❌ не подключён'}",
            f"  Устройств: {len(self._devices)}",
        ]
        for name, data in list(self._devices.items())[:10]:
            state = data.get("state", data.get("contact", "?"))
            lines.append(f"    • {name}: {state}")
        return "\n".join(lines)

    def handle_command(self, cmd: str) -> str | None:
        """Обработчик команд ArgosCore."""
        c = cmd.lower().strip()
        if c in ("zigbee", "zigbee статус", "zigbee status"):
            return self.status()
        if c == "zigbee устройства":
            devs = self.get_devices()
            if not devs:
                return "📡 Zigbee: устройств не найдено"
            return "📡 Zigbee устройства:\n" + "\n".join(f"  • {k}" for k in devs)
        if c.startswith("zigbee вкл "):
            dev = cmd[11:].strip()
            return f"✅ {dev}: ON" if self.turn_on(dev) else "❌ не подключён"
        if c.startswith("zigbee выкл "):
            dev = cmd[12:].strip()
            return f"✅ {dev}: OFF" if self.turn_off(dev) else "❌ не подключён"
        if c.startswith("zigbee сопряжение"):
            return "✅ Сопряжение 60с" if self.permit_join(60) else "❌ не подключён"
        return None

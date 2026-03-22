"""
src/connectivity/protocols/platform_bridges.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Мосты для умного дома:
  • ZWaveBridge      — Z-Wave через ZWaveJS / zwavejs2mqtt
  • HomeAssistantBridge — Home Assistant REST/WebSocket API
  • TasmotaBridge    — Tasmota MQTT discovery
  • LonWorksBridge   — LonWorks ISO/IEC 14908

pip install requests websocket-client paho-mqtt
"""
from __future__ import annotations

import json
import os
import time
import threading
import logging
from typing import Any, Callable

try:
    import requests as _requests
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False

try:
    import paho.mqtt.client as _mqtt_cls  # type: ignore
    _MQTT_OK = True
except ImportError:
    _MQTT_OK = False

log = logging.getLogger("argos.platforms")


# ══════════════════════════════════════════════════════════════════════════════
# Z-Wave (через zwavejs2mqtt REST API)
# ══════════════════════════════════════════════════════════════════════════════

class ZWaveBridge:
    """
    Z-Wave мост через zwavejs2mqtt REST API.

    Установка zwavejs2mqtt:
      docker run -d --name zwavejs2mqtt \
        --device=/dev/ttyACM0 \
        -p 8091:8091 \
        -v zwavejs2mqtt:/usr/src/app/store \
        zwavejs2mqtt/zwavejs2mqtt

    Контроллеры:
      • Aeotec Z-Stick 7 (USB)    → /dev/ttyACM0
      • ZWave.me RaZberry2 (UART) → /dev/ttyAMA0
      • Sigma Designs UZB7 (USB)  → /dev/ttyUSB0
    """

    def __init__(
        self,
        api_url: str = "",
        api_key: str = "",
    ):
        self.api_url = (api_url or os.getenv("ZWAVE_API_URL", "http://localhost:8091")).rstrip("/")
        self.api_key = api_key or os.getenv("ZWAVE_API_KEY", "")
        self._nodes: dict[int, dict] = {}

    def _get(self, path: str) -> dict:
        if not _REQUESTS_OK:
            return {"error": "requests не установлен"}
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            r = _requests.get(f"{self.api_url}{path}", headers=headers, timeout=5)
            return r.json()
        except Exception as exc:
            return {"error": str(exc)}

    def _post(self, path: str, data: dict) -> dict:
        if not _REQUESTS_OK:
            return {"error": "requests не установлен"}
        try:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            r = _requests.post(f"{self.api_url}{path}", json=data, headers=headers, timeout=5)
            return r.json()
        except Exception as exc:
            return {"error": str(exc)}

    def get_nodes(self) -> list[dict]:
        result = self._get("/api/nodes")
        if isinstance(result, list):
            self._nodes = {n["nodeId"]: n for n in result if "nodeId" in n}
            return result
        return []

    def set_value(self, node_id: int, command_class: int, property_name: str, value: Any) -> dict:
        """Установить значение ноды."""
        return self._post("/api/setValue", {
            "nodeId": node_id,
            "commandClassName": command_class,
            "property": property_name,
            "value": value,
        })

    def turn_on(self, node_id: int) -> dict:
        return self.set_value(node_id, "Binary Switch", "targetValue", True)

    def turn_off(self, node_id: int) -> dict:
        return self.set_value(node_id, "Binary Switch", "targetValue", False)

    def set_level(self, node_id: int, level: int) -> dict:
        return self.set_value(node_id, "Multilevel Switch", "targetValue", level)

    def status(self) -> str:
        nodes = self.get_nodes()
        return (
            f"🔵 Z-WAVE\n"
            f"  API     : {self.api_url}\n"
            f"  Нод     : {len(nodes)}\n"
            + "\n".join(f"    • Node {n.get('nodeId')}: {n.get('name', n.get('label','?'))}" for n in nodes[:8])
        )

    def handle_command(self, cmd: str) -> str | None:
        c = cmd.lower().strip()
        if c in ("zwave", "z-wave", "zwave статус"):
            return self.status()
        return None


# ══════════════════════════════════════════════════════════════════════════════
# Home Assistant
# ══════════════════════════════════════════════════════════════════════════════

class HomeAssistantBridge:
    """
    Home Assistant REST API мост.
    Полный доступ к сущностям, сервисам, событиям.
    """

    def __init__(
        self,
        url: str = "",
        token: str = "",
    ):
        self.url = (url or os.getenv("HA_URL", "http://localhost:8123")).rstrip("/")
        self.token = token or os.getenv("HA_TOKEN", "")
        self._states: dict[str, dict] = {}

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str) -> Any:
        if not _REQUESTS_OK:
            return None
        try:
            r = _requests.get(f"{self.url}/api{path}", headers=self._headers, timeout=5)
            return r.json()
        except Exception as exc:
            log.error("HA GET %s: %s", path, exc)
            return None

    def _post(self, path: str, data: dict = None) -> Any:
        if not _REQUESTS_OK:
            return None
        try:
            r = _requests.post(
                f"{self.url}/api{path}",
                json=data or {},
                headers=self._headers,
                timeout=5,
            )
            return r.json()
        except Exception as exc:
            log.error("HA POST %s: %s", path, exc)
            return None

    def is_available(self) -> bool:
        r = self._get("/")
        return bool(r and r.get("message") == "API running.")

    def get_states(self) -> list[dict]:
        result = self._get("/states") or []
        self._states = {s["entity_id"]: s for s in result if "entity_id" in s}
        return result

    def get_state(self, entity_id: str) -> dict | None:
        return self._get(f"/states/{entity_id}")

    def call_service(
        self,
        domain: str,
        service: str,
        data: dict | None = None,
    ) -> Any:
        return self._post(f"/services/{domain}/{service}", data or {})

    def turn_on(self, entity_id: str, **kwargs) -> Any:
        return self.call_service("homeassistant", "turn_on",
                                  {"entity_id": entity_id, **kwargs})

    def turn_off(self, entity_id: str) -> Any:
        return self.call_service("homeassistant", "turn_off", {"entity_id": entity_id})

    def toggle(self, entity_id: str) -> Any:
        return self.call_service("homeassistant", "toggle", {"entity_id": entity_id})

    def set_temperature(self, entity_id: str, temp: float) -> Any:
        return self.call_service("climate", "set_temperature",
                                  {"entity_id": entity_id, "temperature": temp})

    def fire_event(self, event_type: str, data: dict | None = None) -> Any:
        return self._post(f"/events/{event_type}", data or {})

    def get_history(self, entity_id: str, hours: int = 24) -> list:
        from datetime import datetime, timedelta
        start = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        return self._get(f"/history/period/{start}?filter_entity_id={entity_id}") or []

    def status(self) -> str:
        avail = self.is_available()
        states = self.get_states() if avail else []
        return (
            f"🏠 HOME ASSISTANT\n"
            f"  URL     : {self.url}\n"
            f"  Статус  : {'✅ доступен' if avail else '❌ недоступен'}\n"
            f"  Сущностей: {len(states)}"
        )

    def handle_command(self, cmd: str) -> str | None:
        c = cmd.lower().strip()
        if c in ("ha", "ha статус", "home assistant"):
            return self.status()
        if c == "ha состояния":
            states = self.get_states()
            lights = [s for s in states if s["entity_id"].startswith("light.")]
            return f"🏠 HA: {len(states)} сущностей, {len(lights)} ламп"
        if c.startswith("ha вкл "):
            eid = cmd[7:].strip()
            self.turn_on(eid)
            return f"✅ HA: {eid} ON"
        if c.startswith("ha выкл "):
            eid = cmd[8:].strip()
            self.turn_off(eid)
            return f"✅ HA: {eid} OFF"
        return None


# ══════════════════════════════════════════════════════════════════════════════
# Tasmota MQTT discovery
# ══════════════════════════════════════════════════════════════════════════════

class TasmotaBridge:
    """
    Tasmota устройства через MQTT discovery.
    Авто-обнаружение, управление, статус.
    """

    DISCOVERY_TOPIC = "tasmota/discovery/#"
    CMD_TOPIC = "cmnd/{device}/Power"

    def __init__(
        self,
        mqtt_host: str = "",
        mqtt_port: int = 1883,
        on_device: Callable[[str, dict], None] | None = None,
    ):
        self.mqtt_host = mqtt_host or os.getenv("TASMOTA_MQTT_HOST", "localhost")
        self.mqtt_port = mqtt_port
        self.on_device = on_device
        self._devices: dict[str, dict] = {}
        self._client = None
        self._connected = False

    def connect(self) -> str:
        if not _MQTT_OK:
            return "❌ paho-mqtt не установлен"
        self._client = _mqtt_cls.Client(client_id="argos-tasmota")
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        try:
            self._client.connect(self.mqtt_host, self.mqtt_port, 60)
            self._client.loop_start()
            time.sleep(0.8)
            return f"✅ Tasmota MQTT: {self.mqtt_host}"
        except Exception as exc:
            return f"❌ Tasmota: {exc}"

    def _on_connect(self, c, u, f, rc):
        if rc == 0:
            self._connected = True
            c.subscribe(self.DISCOVERY_TOPIC)
            c.subscribe("tele/+/STATE")
            c.subscribe("tele/+/SENSOR")
            c.subscribe("stat/+/POWER")

    def _on_message(self, c, u, msg):
        try:
            payload = json.loads(msg.payload.decode())
        except Exception:
            return
        topic = msg.topic
        parts = topic.split("/")

        if "discovery" in topic and len(parts) >= 3:
            device_id = parts[2]
            hostname = payload.get("hn", device_id)
            self._devices[device_id] = {
                "hostname": hostname,
                "ip": payload.get("ip", ""),
                "module": payload.get("md", ""),
                "version": payload.get("sw", ""),
                "topic": payload.get("t", device_id),
                "power": None,
            }
            if self.on_device:
                self.on_device(device_id, self._devices[device_id])

        elif len(parts) >= 2 and parts[0] in ("tele", "stat"):
            device_id = parts[1]
            if parts[0] == "stat" and parts[-1] == "POWER":
                if device_id in self._devices:
                    self._devices[device_id]["power"] = payload
            elif parts[0] == "tele":
                if device_id not in self._devices:
                    self._devices[device_id] = {}
                self._devices[device_id]["telemetry"] = payload

    def send_command(self, device_topic: str, command: str, payload: str = "") -> bool:
        if not self._client or not self._connected:
            return False
        self._client.publish(f"cmnd/{device_topic}/{command}", payload)
        return True

    def turn_on(self, device_topic: str) -> bool:
        return self.send_command(device_topic, "Power", "ON")

    def turn_off(self, device_topic: str) -> bool:
        return self.send_command(device_topic, "Power", "OFF")

    def toggle(self, device_topic: str) -> bool:
        return self.send_command(device_topic, "Power", "TOGGLE")

    def get_devices(self) -> dict[str, dict]:
        return dict(self._devices)

    def status(self) -> str:
        lines = [
            f"💡 TASMOTA",
            f"  MQTT   : {self.mqtt_host}",
            f"  Статус : {'✅' if self._connected else '❌'}",
            f"  Устройств: {len(self._devices)}",
        ]
        for did, info in list(self._devices.items())[:8]:
            pwr = info.get("power", "?")
            lines.append(f"    • {info.get('hostname', did)} [{info.get('ip','')}] pwr={pwr}")
        return "\n".join(lines)

    def handle_command(self, cmd: str) -> str | None:
        c = cmd.lower().strip()
        if c in ("tasmota", "tasmota статус"):
            return self.status()
        if c.startswith("tasmota вкл "):
            dev = cmd[12:].strip()
            return f"✅ Tasmota {dev}: ON" if self.turn_on(dev) else "❌ не подключён"
        if c.startswith("tasmota выкл "):
            dev = cmd[13:].strip()
            return f"✅ Tasmota {dev}: OFF" if self.turn_off(dev) else "❌ не подключён"
        return None


# ══════════════════════════════════════════════════════════════════════════════
# LonWorks (ISO/IEC 14908) — заглушка с протокольной моделью
# ══════════════════════════════════════════════════════════════════════════════

class LonWorksBridge:
    """
    LonWorks мост.
    Реальная работа требует OpenLNS или u60 (USB-FT adapter).
    Без адаптера работает в режиме симуляции.
    """

    def __init__(self, adapter: str = "", network_name: str = "ArgosNet"):
        self.adapter = adapter or os.getenv("LONWORKS_ADAPTER", "")
        self.network_name = network_name
        self._devices: dict[str, dict] = {}
        self._connected = False

    def connect(self) -> str:
        try:
            import openlns  # type: ignore
            self._connected = True
            return f"✅ LonWorks: {self.adapter}"
        except ImportError:
            return "⚠️ LonWorks: openlns не установлен, режим симуляции"

    def discover(self, timeout: float = 5.0) -> list[dict]:
        """Сканировать LonWorks сеть."""
        # Без реального адаптера возвращаем заглушку
        return []

    def read_nv(self, device_id: str, nv_index: int) -> Any:
        """Чтение Network Variable."""
        log.warning("LonWorks: нет адаптера, симуляция")
        return None

    def write_nv(self, device_id: str, nv_index: int, value: Any) -> bool:
        log.warning("LonWorks: нет адаптера, симуляция")
        return False

    def status(self) -> str:
        try:
            import openlns  # type: ignore
            return f"🔗 LONWORKS: {self.adapter} ✅"
        except ImportError:
            return (
                "🔗 LONWORKS\n"
                "  Статус: ⚠️ режим симуляции\n"
                "  Для реальной работы: USB-FT адаптер + openlns\n"
                "  Альтернатива: OpenLNS / U60 / PCC-10"
            )

    def handle_command(self, cmd: str) -> str | None:
        c = cmd.lower().strip()
        if c in ("lonworks", "lon"):
            return self.status()
        return None

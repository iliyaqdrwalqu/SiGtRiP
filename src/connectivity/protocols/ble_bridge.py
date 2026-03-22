"""
src/connectivity/protocols/ble_bridge.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BLE (Bluetooth Low Energy) мост для ARGOS.
Сканирование, подключение, чтение/запись GATT характеристик.

pip install bleak
"""
from __future__ import annotations

import asyncio
import os
import threading
import time
import logging
from typing import Any, Callable

try:
    from bleak import BleakScanner, BleakClient  # type: ignore
    from bleak.backends.device import BLEDevice  # type: ignore
    _BLEAK_OK = True
except ImportError:
    _BLEAK_OK = False

log = logging.getLogger("argos.ble")

# Стандартные GATT UUID
GATT = {
    "battery":        "0000180f-0000-1000-8000-00805f9b34fb",
    "battery_level":  "00002a19-0000-1000-8000-00805f9b34fb",
    "temperature":    "00002a6e-0000-1000-8000-00805f9b34fb",
    "humidity":       "00002a6f-0000-1000-8000-00805f9b34fb",
    "device_name":    "00002a00-0000-1000-8000-00805f9b34fb",
    "firmware_rev":   "00002a26-0000-1000-8000-00805f9b34fb",
    "tx_power":       "00002a07-0000-1000-8000-00805f9b34fb",
}


class BLEBridge:
    """BLE сканер и клиент через bleak."""

    def __init__(
        self,
        on_advertisement: Callable[[str, str, int, dict], None] | None = None,
        scan_duration: float = 5.0,
    ):
        self.on_advertisement = on_advertisement
        self.scan_duration = scan_duration
        self._devices: dict[str, Any] = {}
        self._scan_thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def _available(self) -> bool:
        return _BLEAK_OK

    def _run_async(self, coro):
        """Запустить корутину синхронно."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                future = asyncio.run_coroutine_threadsafe(coro, loop)
                return future.result(timeout=30)
            return loop.run_until_complete(coro)
        except RuntimeError:
            return asyncio.run(coro)

    # ── Сканирование ──────────────────────────────────────────────────────────

    def scan(self, duration: float | None = None) -> list[dict[str, Any]]:
        """Синхронное сканирование BLE устройств."""
        if not _BLEAK_OK:
            return []
        dur = duration or self.scan_duration
        return self._run_async(self._async_scan(dur))

    async def _async_scan(self, duration: float) -> list[dict[str, Any]]:
        devices = await BleakScanner.discover(timeout=duration)
        result = []
        for dev in devices:
            info = {
                "address": dev.address,
                "name": dev.name or "Unknown",
                "rssi": getattr(dev, "rssi", None),
                "metadata": dev.metadata if hasattr(dev, "metadata") else {},
            }
            self._devices[dev.address] = info
            if self.on_advertisement:
                self.on_advertisement(
                    dev.address,
                    dev.name or "Unknown",
                    info.get("rssi", 0),
                    info.get("metadata", {}),
                )
            result.append(info)
        return result

    # ── Чтение GATT ───────────────────────────────────────────────────────────

    def read_characteristic(
        self,
        address: str,
        uuid: str,
    ) -> dict[str, Any]:
        """Прочитать GATT характеристику."""
        if not _BLEAK_OK:
            return {"ok": False, "error": "bleak не установлен"}
        return self._run_async(self._async_read(address, uuid))

    async def _async_read(self, address: str, uuid: str) -> dict[str, Any]:
        try:
            async with BleakClient(address, timeout=10) as client:
                data = await client.read_gatt_char(uuid)
                return {"ok": True, "address": address, "uuid": uuid, "data": bytes(data)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ── Запись GATT ───────────────────────────────────────────────────────────

    def write_characteristic(
        self,
        address: str,
        uuid: str,
        data: bytes,
    ) -> dict[str, Any]:
        if not _BLEAK_OK:
            return {"ok": False, "error": "bleak не установлен"}
        return self._run_async(self._async_write(address, uuid, data))

    async def _async_write(self, address: str, uuid: str, data: bytes) -> dict[str, Any]:
        try:
            async with BleakClient(address, timeout=10) as client:
                await client.write_gatt_char(uuid, data)
                return {"ok": True, "address": address, "uuid": uuid}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ── Специализированные читалки ────────────────────────────────────────────

    def read_battery(self, address: str) -> int | None:
        """Прочитать уровень заряда батареи (%)."""
        r = self.read_characteristic(address, GATT["battery_level"])
        if r.get("ok") and r.get("data"):
            return r["data"][0]
        return None

    def read_temperature(self, address: str) -> float | None:
        """Прочитать температуру (стандарт GATT 0x2A6E = 0.01°C)."""
        r = self.read_characteristic(address, GATT["temperature"])
        if r.get("ok") and len(r.get("data", b"")) >= 2:
            raw = int.from_bytes(r["data"][:2], "little", signed=True)
            return raw / 100.0
        return None

    def read_humidity(self, address: str) -> float | None:
        """Прочитать влажность (стандарт GATT 0x2A6F = 0.01%)."""
        r = self.read_characteristic(address, GATT["humidity"])
        if r.get("ok") and len(r.get("data", b"")) >= 2:
            raw = int.from_bytes(r["data"][:2], "little")
            return raw / 100.0
        return None

    # ── Notifications ─────────────────────────────────────────────────────────

    def start_notify(
        self,
        address: str,
        uuid: str,
        callback: Callable[[bytes], None],
        duration: float = 30.0,
    ) -> str:
        """Подписаться на уведомления от BLE устройства."""
        if not _BLEAK_OK:
            return "❌ bleak не установлен"

        async def _notify():
            async with BleakClient(address, timeout=10) as client:
                await client.start_notify(uuid, lambda h, d: callback(bytes(d)))
                await asyncio.sleep(duration)
                await client.stop_notify(uuid)

        t = threading.Thread(target=lambda: asyncio.run(_notify()), daemon=True)
        t.start()
        return f"✅ BLE уведомления: {address[:8]}... {uuid[:8]}..."

    # ── RSSI трекинг / инвентаризация ────────────────────────────────────────

    def inventory(self) -> list[dict[str, Any]]:
        """Список всех обнаруженных устройств."""
        return list(self._devices.values())

    def find_by_name(self, name: str) -> dict | None:
        for dev in self._devices.values():
            if name.lower() in dev.get("name", "").lower():
                return dev
        return None

    # ── Статус ────────────────────────────────────────────────────────────────

    def status(self) -> str:
        lines = [
            "🔵 BLE",
            f"  Библиотека : {'✅ bleak' if _BLEAK_OK else '❌ нет bleak (pip install bleak)'}",
            f"  Устройств  : {len(self._devices)}",
        ]
        for addr, info in list(self._devices.items())[:8]:
            lines.append(f"    • {info['name']} [{addr}] RSSI={info.get('rssi','?')}")
        return "\n".join(lines)

    def handle_command(self, cmd: str) -> str | None:
        c = cmd.lower().strip()
        if c in ("ble", "ble статус", "bluetooth"):
            return self.status()
        if c in ("ble скан", "ble scan", "bt скан"):
            devs = self.scan()
            if not devs:
                return "🔵 BLE: устройств не найдено"
            return "🔵 BLE:\n" + "\n".join(f"  • {d['name']} [{d['address']}]" for d in devs)
        if c == "ble инвентарь":
            return self.status()
        return None

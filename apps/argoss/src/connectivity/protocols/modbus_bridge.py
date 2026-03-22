"""
src/connectivity/protocols/modbus_bridge.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Modbus RTU / TCP / ASCII мост для ARGOS.

Modbus RTU — RS-485/RS-232 (физический уровень)
Modbus TCP — Ethernet/WiFi (порт 502)
Modbus ASCII — текстовый режим через serial

Схема RS-485 (Modbus RTU):
  RPi GPIO14 TX → MAX485 DI
  RPi GPIO15 RX → MAX485 RO
  RPi GPIO18     → MAX485 DE + RE (управление направлением)
  MAX485 A/B    → шина RS-485 (витая пара)
  MAX485 VCC    → 5V
  MAX485 GND    → GND

pip install pymodbus
"""
from __future__ import annotations

import os
import time
import logging
from typing import Any

try:
    from pymodbus.client import ModbusSerialClient, ModbusTcpClient  # type: ignore
    from pymodbus.exceptions import ModbusException  # type: ignore
    _MODBUS_OK = True
except ImportError:
    try:
        # pymodbus < 3.0 API
        from pymodbus.client.sync import ModbusSerialClient, ModbusTcpClient  # type: ignore
        from pymodbus.exceptions import ModbusException  # type: ignore
        _MODBUS_OK = True
    except ImportError:
        _MODBUS_OK = False

log = logging.getLogger("argos.modbus")


class ModbusBridge:
    """
    Modbus RTU + TCP + ASCII.
    Единый интерфейс для всех режимов.
    """

    def __init__(
        self,
        mode: str = "rtu",          # "rtu" | "tcp" | "ascii"
        port: str = "",              # RTU: /dev/ttyUSB0; TCP: IP
        baudrate: int = 9600,        # RTU only
        tcp_port: int = 502,         # TCP only
        stopbits: int = 1,
        bytesize: int = 8,
        parity: str = "N",
        timeout: float = 1.0,
        rs485_rts_pin: int | None = None,
    ):
        self.mode = mode.lower()
        self.port = port or os.getenv("MODBUS_PORT", "/dev/ttyUSB0")
        self.baudrate = baudrate or int(os.getenv("MODBUS_BAUD", "9600"))
        self.tcp_port = tcp_port
        self.stopbits = stopbits
        self.bytesize = bytesize
        self.parity = parity
        self.timeout = timeout
        self.rs485_rts_pin = rs485_rts_pin
        self._client = None

    # ── Подключение ───────────────────────────────────────────────────────────

    def connect(self) -> str:
        if not _MODBUS_OK:
            return "❌ pymodbus не установлен: pip install pymodbus"
        try:
            if self.mode == "tcp":
                self._client = ModbusTcpClient(
                    self.port, port=self.tcp_port, timeout=self.timeout
                )
            else:
                self._client = ModbusSerialClient(
                    method=self.mode,
                    port=self.port,
                    baudrate=self.baudrate,
                    stopbits=self.stopbits,
                    bytesize=self.bytesize,
                    parity=self.parity,
                    timeout=self.timeout,
                )
            ok = self._client.connect()
            if ok:
                return f"✅ Modbus {self.mode.upper()}: {self.port}"
            return f"❌ Modbus: не удалось подключиться к {self.port}"
        except Exception as exc:
            return f"❌ Modbus: {exc}"

    def disconnect(self):
        if self._client:
            self._client.close()

    def is_connected(self) -> bool:
        return bool(self._client and getattr(self._client, "is_socket_open", lambda: True)())

    # ── Чтение регистров ──────────────────────────────────────────────────────

    def read_holding(self, address: int, count: int = 1, unit: int = 1) -> dict[str, Any]:
        """Чтение Holding Registers (FC 03)."""
        return self._read("holding_registers", address, count, unit)

    def read_input(self, address: int, count: int = 1, unit: int = 1) -> dict[str, Any]:
        """Чтение Input Registers (FC 04) — только чтение."""
        return self._read("input_registers", address, count, unit)

    def read_coils(self, address: int, count: int = 1, unit: int = 1) -> dict[str, Any]:
        """Чтение Coils (FC 01) — дискретные выходы."""
        return self._read("coils", address, count, unit)

    def read_discrete(self, address: int, count: int = 1, unit: int = 1) -> dict[str, Any]:
        """Чтение Discrete Inputs (FC 02) — дискретные входы."""
        return self._read("discrete_inputs", address, count, unit)

    def _read(self, reg_type: str, address: int, count: int, unit: int) -> dict[str, Any]:
        if not self._client:
            return {"ok": False, "error": "не подключён"}
        try:
            methods = {
                "holding_registers": self._client.read_holding_registers,
                "input_registers":   self._client.read_input_registers,
                "coils":             self._client.read_coils,
                "discrete_inputs":   self._client.read_discrete_inputs,
            }
            kwargs = {"address": address, "count": count}
            # pymodbus 3.x: unit → slave; pymodbus 2.x: unit=unit
            try:
                result = methods[reg_type](**kwargs, slave=unit)
            except TypeError:
                result = methods[reg_type](**kwargs, unit=unit)

            if result.isError():
                return {"ok": False, "error": str(result)}

            values = getattr(result, "registers", None) or getattr(result, "bits", None)
            return {"ok": True, "address": address, "unit": unit, "values": values}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ── Запись регистров ──────────────────────────────────────────────────────

    def write_register(self, address: int, value: int, unit: int = 1) -> dict[str, Any]:
        """Запись одного Holding Register (FC 06)."""
        if not self._client:
            return {"ok": False, "error": "не подключён"}
        try:
            try:
                result = self._client.write_register(address=address, value=value, slave=unit)
            except TypeError:
                result = self._client.write_register(address=address, value=value, unit=unit)
            return {"ok": not result.isError(), "address": address, "value": value}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def write_registers(self, address: int, values: list[int], unit: int = 1) -> dict[str, Any]:
        """Запись нескольких Holding Registers (FC 16)."""
        if not self._client:
            return {"ok": False, "error": "не подключён"}
        try:
            try:
                result = self._client.write_registers(address=address, values=values, slave=unit)
            except TypeError:
                result = self._client.write_registers(address=address, values=values, unit=unit)
            return {"ok": not result.isError(), "address": address, "count": len(values)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def write_coil(self, address: int, value: bool, unit: int = 1) -> dict[str, Any]:
        """Запись Coil (FC 05)."""
        if not self._client:
            return {"ok": False, "error": "не подключён"}
        try:
            try:
                result = self._client.write_coil(address=address, value=value, slave=unit)
            except TypeError:
                result = self._client.write_coil(address=address, value=value, unit=unit)
            return {"ok": not result.isError()}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ── Удобные хелперы ───────────────────────────────────────────────────────

    def read_float32(self, address: int, unit: int = 1) -> float | None:
        """Читать IEEE 754 float из двух регистров."""
        import struct
        r = self.read_holding(address, count=2, unit=unit)
        if r.get("ok") and r.get("values") and len(r["values"]) >= 2:
            raw = struct.pack(">HH", r["values"][0], r["values"][1])
            return struct.unpack(">f", raw)[0]
        return None

    def write_float32(self, address: int, value: float, unit: int = 1) -> dict[str, Any]:
        import struct
        raw = struct.pack(">f", value)
        hi, lo = struct.unpack(">HH", raw)
        return self.write_registers(address, [hi, lo], unit)

    # ── Сканирование шины ─────────────────────────────────────────────────────

    def scan_devices(self, start: int = 1, end: int = 247) -> list[int]:
        """Найти все устройства на шине Modbus."""
        found = []
        for uid in range(start, end + 1):
            r = self.read_holding(0, count=1, unit=uid)
            if r.get("ok"):
                found.append(uid)
        return found

    # ── Статус ────────────────────────────────────────────────────────────────

    def status(self) -> str:
        return (
            f"⚙️ MODBUS {self.mode.upper()}\n"
            f"  Порт  : {self.port}\n"
            f"  Статус: {'✅ подключён' if self.is_connected() else '❌ не подключён'}\n"
            f"  Режим : {self.mode.upper()} {'@ '+str(self.baudrate)+' baud' if self.mode != 'tcp' else 'порт '+str(self.tcp_port)}"
        )

    def handle_command(self, cmd: str) -> str | None:
        c = cmd.lower().strip()
        if c in ("modbus", "modbus статус"):
            return self.status()
        # modbus чтение <addr> <count> <unit>
        if c.startswith("modbus чтение "):
            parts = cmd.split()[2:]
            try:
                addr = int(parts[0])
                count = int(parts[1]) if len(parts) > 1 else 1
                unit = int(parts[2]) if len(parts) > 2 else 1
                r = self.read_holding(addr, count, unit)
                return f"Modbus [{addr}]: {r.get('values', r.get('error'))}"
            except Exception as exc:
                return f"❌ {exc}"
        # modbus запись <addr> <value> <unit>
        if c.startswith("modbus запись "):
            parts = cmd.split()[2:]
            try:
                addr = int(parts[0])
                val = int(parts[1])
                unit = int(parts[2]) if len(parts) > 2 else 1
                r = self.write_register(addr, val, unit)
                return f"✅ Modbus [{addr}]={val}" if r["ok"] else f"❌ {r.get('error')}"
            except Exception as exc:
                return f"❌ {exc}"
        if c == "modbus скан":
            devs = self.scan_devices(1, 20)
            return f"Modbus устройства: {devs}" if devs else "Modbus: устройств не найдено"
        return None

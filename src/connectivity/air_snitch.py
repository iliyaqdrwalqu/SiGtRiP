"""
air_snitch.py — AirSnitch (SDR / Sub-GHz Radio Scanner)
Пассивный мониторинг эфира 433/868/915 МГц.
⚠ Только RX. Передача запрещена.

Поддерживает два режима:
  • rtl_433 (subprocess) — перехват пакетов через rtl_433 JSON-вывод
  • RTL-SDR (pyrtlsdr) — низкоуровневый сырой сигнал
  • Serial — чтение с UART-приёмника

Модуль управляется RX 560 (4GB): потоковая задача, не требующая основного мозга.
"""
import os
import subprocess
import time
import json
import threading
from enum import Enum
from typing import List, Optional
from collections import deque
from dataclasses import dataclass, field, asdict
from src.argos_logger import get_logger

log = get_logger("argos.airsnitch")

try:
    from rtlsdr import RtlSdr
    RTLSDR_OK = True
except ImportError:
    RtlSdr = None; RTLSDR_OK = False

try:
    import numpy as np
    NP_OK = True
except ImportError:
    np = None; NP_OK = False

try:
    import serial
    SERIAL_OK = True
except ImportError:
    serial = None; SERIAL_OK = False


class Modulation(Enum):
    OOK = "OOK"; FSK = "FSK"; GFSK = "GFSK"; LORA = "LoRa"; UNKNOWN = "unknown"

class Band(Enum):
    SUB_433 = 433.92e6; SUB_868 = 868.0e6; SUB_915 = 915.0e6


@dataclass
class RFPacket:
    ts: float = field(default_factory=time.time)
    freq_hz: float = 0.0
    modulation: str = "unknown"
    rssi_dbm: float = -120.0
    raw_hex: str = ""
    decoded: str = ""
    protocol: str = ""
    device_id: str = ""
    repeated: int = 1
    summary: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["freq_mhz"] = round(self.freq_hz / 1e6, 3)
        return d


class AirSnitch:
    """Сверхслух Аргоса: SDR/Sub-GHz сканер эфира 433/868/915 МГц (RX only).

    Принимает необязательный ``core`` — ссылку на ArgosCore.
    При наличии ``core`` перехваченные данные сохраняются в быстрой памяти
    и пробрасываются через шину событий AWA.
    """
    MAX_LOG = 500

    def __init__(self, core=None):
        self.core = core
        self._packets: deque = deque(maxlen=self.MAX_LOG)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._serial_port = None
        self.process: Optional[subprocess.Popen] = None

    # ── rtl_433 subprocess mode ──────────────────────────────────────────────

    def start_sniffing(self) -> str:
        """Запуск перехвата через rtl_433 (subprocess JSON-режим).

        Для работы требуется установленный rtl_433:
          Linux/Docker: sudo apt install rtl-433
          Windows:      rtl_433.exe в PATH или папке проекта
        """
        if self._running:
            return "⚠️ AirSnitch: уже запущен"
        self._running = True
        self._thread = threading.Thread(target=self._rtl433_run, daemon=True, name="AirSnitch")
        self._thread.start()
        log.info("AirSnitch: сканирование эфира запущено (rtl_433)")
        print("📡 [AIR-SNITCH] Аргос начал слушать эфир...")
        return "✅ AirSnitch: сканирование запущено"

    def _rtl433_run(self) -> None:
        """Фоновый цикл: читает JSON-пакеты из rtl_433 и обрабатывает."""
        cmd = ["rtl_433", "-F", "json", "-M", "level"]
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            for raw_line in iter(self.process.stdout.readline, b""):
                if not self._running:
                    break
                try:
                    data = json.loads(raw_line.decode("utf-8"))
                    self._process_packet(data)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
        except FileNotFoundError:
            log.warning("AirSnitch: rtl_433 не найден. Установи: sudo apt install rtl-433")
            print("⚠️ [AIR-SNITCH] rtl_433 не найден. Установи: sudo apt install rtl-433")
            self._running = False
        except Exception as e:
            log.error("AirSnitch _rtl433_run: %s", e)
            self._running = False

    def _process_packet(self, packet: dict) -> None:
        """Анализ перехваченного сигнала rtl_433 и интеграция с ядром Аргоса."""
        model = packet.get("model", "Unknown")
        temp = packet.get("temperature_C")
        btn = packet.get("button") or packet.get("event")

        pkt = RFPacket(
            freq_hz=float(packet.get("freq", packet.get("frequency", 433.92)) or 433.92) * 1e6,
            rssi_dbm=float(packet.get("rssi", -100) or -100),
            modulation=packet.get("mod", "OOK"),
            protocol=str(model),
            device_id=str(packet.get("id", "")),
            decoded=json.dumps(packet, ensure_ascii=False)[:200],
            summary=f"{model} rssi={packet.get('rssi','?')}dBm",
        )
        self._packets.append(pkt)

        if temp is not None:
            msg = f"Услышал датчик {model}: Температура {temp}°C"
            log.info("AirSnitch: %s", msg)
            if self.core and hasattr(self.core, "memory"):
                try:
                    self.core.memory.fast_store(f"Radio_Sensor_{model}: {temp}C")
                except Exception as e:
                    log.debug("AirSnitch memory store: %s", e)

        if btn:
            log.info("AirSnitch: перехвачен сигнал пульта %s → %s", model, btn)
            print(f"🔑 [AIR-SNITCH] Перехвачен сигнал пульта: {model} -> {btn}")
            if self.core and hasattr(self.core, "awa"):
                try:
                    self.core.awa.trigger_event("radio_event", packet)
                except Exception as e:
                    log.debug("AirSnitch awa trigger: %s", e)

    # ── RTL-SDR low-level mode ───────────────────────────────────────────────

    def start_rtlsdr(self, band: str = "433", gain: float = 40.0) -> str:
        if not RTLSDR_OK:
            return "❌ AirSnitch: pyrtlsdr не установлен (pip install pyrtlsdr)"
        freq_map = {"433": Band.SUB_433.value, "868": Band.SUB_868.value, "915": Band.SUB_915.value}
        freq = freq_map.get(str(band), Band.SUB_433.value)
        self._running = True
        self._thread = threading.Thread(target=self._rtl_loop, args=(freq, gain), daemon=True)
        self._thread.start()
        return f"✅ AirSnitch RTL-SDR запущен [{band} МГц]"

    def start_serial(self, port: str = "/dev/ttyUSB0", baud: int = 115200) -> str:
        if not SERIAL_OK:
            return "❌ AirSnitch: pyserial не установлен"
        try:
            import serial as pyserial
            self._serial_port = pyserial.Serial(port, baud, timeout=1)
            self._running = True
            self._thread = threading.Thread(target=self._serial_loop, daemon=True)
            self._thread.start()
            return f"✅ AirSnitch serial запущен ({port} @{baud})"
        except Exception as e:
            return f"❌ AirSnitch serial: {e}"

    def stop(self) -> str:
        self._running = False
        if self.process:
            try:
                self.process.terminate()
            except Exception:
                pass
        if self._serial_port:
            try: self._serial_port.close()
            except Exception: pass
        log.info("AirSnitch: остановлен")
        return "✅ AirSnitch остановлен"

    def _rtl_loop(self, freq: float, gain: float):
        try:
            sdr = RtlSdr()
            sdr.sample_rate = 2.048e6
            sdr.center_freq = freq
            sdr.gain = gain
            while self._running:
                if NP_OK:
                    samples = sdr.read_samples(256 * 1024)
                    power = float(np.mean(np.abs(samples) ** 2))
                    rssi = 10 * np.log10(max(power, 1e-12))
                    pkt = RFPacket(freq_hz=freq, rssi_dbm=float(rssi),
                                   modulation="OOK", summary=f"power={rssi:.1f}dBm")
                    self._packets.append(pkt)
                time.sleep(0.5)
            sdr.close()
        except Exception as e:
            log.error("RTL-SDR loop: %s", e)

    def _serial_loop(self):
        while self._running and self._serial_port:
            try:
                line = self._serial_port.readline().decode("ascii", errors="ignore").strip()
                if line.startswith("RF:"):
                    parts = dict(p.split("=") for p in line[3:].split(",") if "=" in p)
                    pkt = RFPacket(
                        freq_hz=float(parts.get("f", 433.92)) * 1e6,
                        rssi_dbm=float(parts.get("rssi", -100)),
                        modulation=parts.get("mod", "OOK"),
                        raw_hex=parts.get("data", ""),
                        protocol=parts.get("proto", ""),
                        summary=line
                    )
                    self._packets.append(pkt)
            except Exception:
                time.sleep(0.1)

    def get_packets(self, limit: int = 50) -> list:
        return [p.to_dict() for p in list(self._packets)[-limit:]]

    def spectrum_summary(self) -> str:
        if not self._packets:
            return "📻 AirSnitch: пакетов нет (запусти сканирование)"
        recent = list(self._packets)[-20:]
        freqs = set(round(p.freq_hz / 1e6, 1) for p in recent)
        avg_rssi = sum(p.rssi_dbm for p in recent) / len(recent)
        return (
            f"📻 AIRSNITCH — {len(self._packets)} пакетов:\n"
            f"  Частоты: {', '.join(str(f)+' МГц' for f in sorted(freqs))}\n"
            f"  Ср. RSSI: {avg_rssi:.1f} dBm\n"
            f"  Активен: {'✅' if self._running else '❌'}"
        )

    def status(self) -> str:
        rtl = "✅" if RTLSDR_OK else "❌"
        serial_ok = "✅" if SERIAL_OK else "❌"
        return (
            f"📻 AIRSNITCH:\n"
            f"  RTL-SDR:  {rtl}\n"
            f"  Serial:   {serial_ok}\n"
            f"  Запущен:  {'✅' if self._running else '❌'}\n"
            f"  Пакетов:  {len(self._packets)}"
        )

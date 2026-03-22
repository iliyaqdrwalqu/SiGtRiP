"""
sensor_bridge.py -- System sensor bridge for ARGOS.
CPU / RAM / disk / battery / temperature / network.
"""
import platform, socket, time
from collections import deque
from typing import Any, Dict

try:
    import psutil
except Exception:
    from src import psutil_android as psutil

from src.argos_logger import get_logger
log = get_logger("argos.sensor")


class ArgosSensorBridge:
    MAX_HISTORY = 120

    def __init__(self):
        self.os_type = platform.system()
        self._history = deque(maxlen=self.MAX_HISTORY)
        self._cache: Dict[str, Any] = {}
        self._cache_ts = 0.0

    def get_metrics(self) -> Dict[str, Any]:
        now = time.time()
        if self._cache and (now - self._cache_ts) < 1.0:
            return self._cache
        m: Dict[str, Any] = {
            "ts":            now,
            "cpu_percent":   0.0,
            "ram_percent":   0.0,
            "ram_used_mb":   psutil.virtual_memory().used // (1024*1024),
            "ram_total_mb":  1073741824 // (1024*1024),
            "disk_percent":  self._disk_percent(),
            "disk_free_gb":  self._disk_free_gb(),
            "cpu_freq_mhz":  self._cpu_freq(),
            "cpu_cores":     psutil.cpu_count(logical=True),
            "temperature":   self._get_temperature(),
            "battery":       self._check_battery(),
            "network":       self._ping_status(),
            "load_avg":      self._load_avg(),
            "uptime_sec":    int(now - psutil.boot_time()),
        }
        self._cache = m
        self._cache_ts = now
        self._history.append({"ts": now, "cpu": m["cpu_percent"], "ram": m["ram_percent"]})
        return m

    def get_vital_signs(self) -> Dict[str, Any]:
        m = self.get_metrics()
        return {
            "battery": m["battery"],
            "thermal": m["temperature"],
            "network": m["network"],
            "storage": {"free_gb": f"{m['disk_free_gb']} GB", "load": f"{m['disk_percent']}%"},
        }

    def get_full_report(self) -> str:
        m = self.get_metrics()
        bat = m["battery"]
        bat_s = (f"{bat['percent']} ({bat['plugged']})" if isinstance(bat, dict) else str(bat))
        net = m["network"]
        net_s = (f"{net['ping']} ({net['status']})" if isinstance(net, dict) else str(net))
        uh = m["uptime_sec"] // 3600
        um = (m["uptime_sec"] % 3600) // 60
        return (
            f"HEALTH REPORT ({self.os_type})\n"
            f"  CPU:   {m['cpu_percent']:.1f}%  ({m['cpu_cores']} cores @ {m['cpu_freq_mhz']} MHz)\n"
            f"  RAM:   {m['ram_percent']:.1f}%  ({m['ram_used_mb']} / {m['ram_total_mb']} MB)\n"
            f"  Disk:  {m['disk_percent']:.1f}%  (free {m['disk_free_gb']} GB)\n"
            f"  Temp:  {m['temperature']}\n"
            f"  Net:   {net_s}\n"
            f"  Bat:   {bat_s}\n"
            f"  Up:    {uh}h {um}m"
        )

    def _check_battery(self):
        b = psutil.sensors_battery()
        if b:
            return {"percent": f"{b.percent:.0f}%",
                    "plugged": "Connected" if b.power_plugged else "Discharging",
                    "time_left": f"{b.secsleft//60} min" if b.secsleft not in (-1,-2) else "N/A"}
        return "N/A (Stationary)"

    def _get_temperature(self) -> str:
        try:
            if hasattr(psutil, "sensors_temperatures"):
                temps = psutil.sensors_temperatures()
                if temps:
                    all_t = [s.current for v in temps.values() for s in v]
                    if all_t:
                        return f"{max(all_t):.1f}degC"
        except Exception:
            pass
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                return f"{int(f.read().strip())/1000:.1f}degC"
        except Exception:
            pass
        return "N/A"

    def _ping_status(self) -> Dict[str, str]:
        try:
            t0 = time.time()
            with socket.create_connection(("8.8.8.8", 53), timeout=2):
                pass
            ms = int((time.time()-t0)*1000)
            return {"ping": f"{ms}ms", "status": "Stable" if ms < 100 else "Degraded"}
        except Exception:
            return {"ping": "inf", "status": "Offline"}

    def _disk_percent(self) -> float:
        try:
            return psutil.disk_usage("/") if hasattr(psutil, "disk_usage") else type("D",(),({"percent":0,"free":0,"total":0,"used":0}))().percent
        except Exception:
            return 0.0

    def _disk_free_gb(self) -> int:
        try:
            return psutil.disk_usage("/") if hasattr(psutil, "disk_usage") else type("D",(),({"percent":0,"free":0,"total":0,"used":0}))().free // (1024**3)
        except Exception:
            return 0

    def _cpu_freq(self) -> int:
        try:
            f = psutil.cpu_freq()
            return int(f.current) if f else 0
        except Exception:
            return 0

    def _load_avg(self) -> str:
        try:
            la = psutil.getloadavg()
            return f"{la[0]:.2f} {la[1]:.2f} {la[2]:.2f}"
        except Exception:
            return "N/A"

    def history_avg(self, window: int = 60) -> Dict[str, float]:
        now = time.time()
        recent = [h for h in self._history if (now - h["ts"]) <= window]
        if not recent:
            return {"cpu": 0.0, "ram": 0.0}
        return {
            "cpu": round(sum(h["cpu"] for h in recent) / len(recent), 2),
            "ram": round(sum(h["ram"] for h in recent) / len(recent), 2),
        }

    # ── GPU / VRAM МОНИТОРИНГ (AMD RX 580 + RX 560) ──────

    def get_gpu_metrics(self) -> list[dict]:
        """
        Возвращает список GPU с информацией о VRAM.
        Поддерживает AMD (через `rocm-smi`), NVIDIA (через `nvidia-smi`).
        Если ни то, ни другое недоступно — возвращает пустой список.
        """
        gpus = []

        # Попытка через rocm-smi (AMD Linux/ROCm)
        try:
            import subprocess
            out = subprocess.check_output(
                ["rocm-smi", "--showmeminfo", "vram", "--json"],
                timeout=5, stderr=subprocess.DEVNULL,
            ).decode()
            import json as _json
            data = _json.loads(out)
            for dev_id, info in data.items():
                used  = int(info.get("VRAM Total Used Memory (B)", 0)) // (1024**2)
                total = int(info.get("VRAM Total Memory (B)", 1)) // (1024**2)
                gpus.append({"id": dev_id, "used_mb": used, "total_mb": total,
                             "used_pct": round(used / max(total, 1) * 100, 1),
                             "backend": "rocm-smi"})
            return gpus
        except Exception:
            pass

        # Попытка через nvidia-smi (NVIDIA)
        try:
            import subprocess
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=index,memory.used,memory.total",
                 "--format=csv,noheader,nounits"],
                timeout=5, stderr=subprocess.DEVNULL,
            ).decode()
            for line in out.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) == 3:
                    gpus.append({"id": parts[0], "used_mb": int(parts[1]),
                                 "total_mb": int(parts[2]),
                                 "used_pct": round(int(parts[1]) / max(int(parts[2]), 1) * 100, 1),
                                 "backend": "nvidia-smi"})
            return gpus
        except Exception:
            pass

        return []

    def optimize_vram_distribution(self) -> str:
        """
        VRAM-Unlocker: проверяет нагрузку на GPU через `ollama ps`
        и сообщает, если RX 580 работает не на полную мощность.
        Возвращает строку-отчёт для отображения в интерфейсе.
        """
        lines = ["📊 VRAM-АНАЛИЗ:"]

        # Проверка через `ollama ps`
        try:
            import subprocess
            result = subprocess.check_output(
                ["ollama", "ps"], timeout=5, stderr=subprocess.DEVNULL
            ).decode()
            lines.append(f"  Ollama модели:\n{result.strip()}")

            # Детект ограничения: 8B-модель занимает ~4GB вместо ~8GB
            if "4.0 GB" in result and "8b" in result.lower():
                lines.append(
                    "  ⚠️  ОБНАРУЖЕНО ОГРАНИЧЕНИЕ VRAM!\n"
                    "      RX 580 работает не на полную мощность.\n"
                    "  💡 Установи переменные окружения:\n"
                    "      OLLAMA_MAX_VRAM=8192\n"
                    "      HIP_VISIBLE_DEVICES=0,1\n"
                    "      OLLAMA_NUM_PARALLEL=1\n"
                    "      OLLAMA_MAX_LOADED_MODELS=2"
                )
            else:
                lines.append("  ✅ VRAM распределён корректно.")
        except FileNotFoundError:
            lines.append("  ℹ️ ollama не найден в PATH — пропуск проверки.")
        except Exception as e:
            lines.append(f"  ⚠️ ollama ps: {e}")

        # GPU-метрики
        gpus = self.get_gpu_metrics()
        if gpus:
            lines.append("  GPU:")
            for g in gpus:
                bar = "█" * int(g["used_pct"] / 10)
                lines.append(
                    f"    [{g['id']}] {g['used_mb']}/{g['total_mb']} MB "
                    f"({g['used_pct']}%) {bar} [{g['backend']}]"
                )
        else:
            lines.append("  GPU: данные недоступны (rocm-smi / nvidia-smi не найдены)")

        return "\n".join(lines)


SensorBridge = ArgosSensorBridge

# Aliases
SensorBridge = ArgosSensorBridge

"""
src/health_monitor.py — ARGOS v2.0.0
Фоновый поток самодиагностики: CPU / RAM / диск / модули / БД.
Отправляет Telegram-алерты при деградации. Предоставляет HTTP /api/health.
"""

from __future__ import annotations

import importlib
import os
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


# ─── Структуры данных ───────────────────────────────────────────────────────

@dataclass
class ComponentStatus:
    name:    str
    ok:      bool
    value:   Any    = None
    message: str    = ""


@dataclass
class HealthSnapshot:
    timestamp:  float
    status:     str                      # "healthy" | "degraded" | "critical"
    cpu_pct:    float
    ram_pct:    float
    disk_pct:   float
    components: List[ComponentStatus]
    uptime_sec: float

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["components"] = [asdict(c) for c in self.components]
        return d


# ─── Пороги (переопределяются через .env) ──────────────────────────────────

_CPU_WARN  = float(os.getenv("ARGOS_HEALTH_CPU_WARN",  "80"))
_CPU_CRIT  = float(os.getenv("ARGOS_HEALTH_CPU_CRIT",  "95"))
_RAM_WARN  = float(os.getenv("ARGOS_HEALTH_RAM_WARN",  "80"))
_RAM_CRIT  = float(os.getenv("ARGOS_HEALTH_RAM_CRIT",  "95"))
_DISK_WARN = float(os.getenv("ARGOS_HEALTH_DISK_WARN", "85"))
_DISK_CRIT = float(os.getenv("ARGOS_HEALTH_DISK_CRIT", "95"))
_INTERVAL  = float(os.getenv("ARGOS_HEALTH_INTERVAL",  "30"))   # секунды
_ALERT_COOLDOWN = float(os.getenv("ARGOS_HEALTH_ALERT_COOLDOWN", "300"))  # 5 мин


class HealthMonitor:
    """
    Запускается как daemon-поток при старте ArgosCore.

    Использование::

        monitor = HealthMonitor(db_path="data/argos.db")
        monitor.start()
        snapshot = monitor.latest()   # текущий слепок
        monitor.stop()

    HTTP-интеграция (FastAPI)::

        @app.get("/api/health")
        async def health():
            return monitor.latest().to_dict()
    """

    def __init__(
        self,
        db_path:          Optional[str]       = None,
        alert_callback:   Optional[Callable]  = None,
        interval:         float               = _INTERVAL,
    ):
        self._db_path       = db_path or "data/argos.db"
        self._alert_cb      = alert_callback   # async или sync — определяем при вызове
        self._interval      = interval
        self._start_time    = time.time()
        self._latest:       Optional[HealthSnapshot] = None
        self._lock          = threading.Lock()
        self._stop_event    = threading.Event()
        self._thread:       Optional[threading.Thread] = None
        self._last_alert:   Dict[str, float] = {}   # component → timestamp последнего алерта
        self._history:      List[HealthSnapshot] = []
        self._max_history   = 120  # ~1 час при interval=30

    # ── Публичный API ──────────────────────────────────────────────────────

    def start(self) -> None:
        """Запустить фоновый поток мониторинга."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="ArgosHealthMonitor",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Остановить фоновый поток."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def latest(self) -> Optional[HealthSnapshot]:
        with self._lock:
            return self._latest

    def history(self, n: int = 10) -> List[HealthSnapshot]:
        with self._lock:
            return list(self._history[-n:])

    def is_healthy(self) -> bool:
        snap = self.latest()
        return snap is not None and snap.status == "healthy"

    # ── Основной цикл ─────────────────────────────────────────────────────

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                snap = self._take_snapshot()
                with self._lock:
                    self._latest = snap
                    self._history.append(snap)
                    if len(self._history) > self._max_history:
                        self._history.pop(0)
                self._check_alerts(snap)
            except Exception as exc:
                # Мониторинг никогда не должен падать молча
                _log(f"HealthMonitor error: {exc}")
            self._stop_event.wait(self._interval)

    def _take_snapshot(self) -> HealthSnapshot:
        components = []
        cpu_pct = ram_pct = disk_pct = 0.0

        # psutil — опционально
        try:
            try:
    import psutil
except Exception:
    from src import psutil_android as psutil
            cpu_pct  = 0.0
            ram      = psutil.virtual_memory()
            ram_pct  = ram.percent
            disk     = psutil_android.disk_usage()
            disk_pct = disk.percent
            components.append(ComponentStatus("cpu",  True, cpu_pct,  f"{cpu_pct:.1f}%"))
            components.append(ComponentStatus("ram",  True, ram_pct,  f"{ram_pct:.1f}%"))
            components.append(ComponentStatus("disk", True, disk_pct, f"{disk_pct:.1f}%"))
        except ImportError:
            components.append(ComponentStatus("psutil", False, None, "не установлен"))

        # SQLite
        components.append(self._check_db())

        # Ключевые модули
        for mod, label in [
            ("src.event_bus",   "EventBus"),
            ("src.memory",      "Memory"),
            ("src.agent",       "Agent"),
        ]:
            components.append(self._check_module(mod, label))

        # Общий статус
        status = self._calc_status(cpu_pct, ram_pct, disk_pct, components)

        return HealthSnapshot(
            timestamp   = time.time(),
            status      = status,
            cpu_pct     = cpu_pct,
            ram_pct     = ram_pct,
            disk_pct    = disk_pct,
            components  = components,
            uptime_sec  = time.time() - self._start_time,
        )

    def _check_db(self) -> ComponentStatus:
        try:
            conn = sqlite3.connect(self._db_path, timeout=3)
            conn.execute("SELECT 1")
            conn.close()
            return ComponentStatus("sqlite", True, self._db_path, "ok")
        except Exception as e:
            return ComponentStatus("sqlite", False, None, str(e))

    @staticmethod
    def _check_module(mod: str, label: str) -> ComponentStatus:
        try:
            importlib.import_module(mod)
            return ComponentStatus(label, True, mod, "импортирован")
        except ImportError as e:
            return ComponentStatus(label, False, mod, str(e))

    @staticmethod
    def _calc_status(cpu: float, ram: float, disk: float,
                     components: List[ComponentStatus]) -> str:
        failed_required = [
            c for c in components
            if not c.ok and c.name in ("sqlite", "EventBus")
        ]
        if failed_required or cpu >= _CPU_CRIT or ram >= _RAM_CRIT or disk >= _DISK_CRIT:
            return "critical"
        if cpu >= _CPU_WARN or ram >= _RAM_WARN or disk >= _DISK_WARN:
            return "degraded"
        return "healthy"

    # ── Алерты ────────────────────────────────────────────────────────────

    def _check_alerts(self, snap: HealthSnapshot) -> None:
        if snap.status == "healthy":
            return
        if not self._alert_cb:
            return

        now = time.time()
        key = snap.status

        # Кулдаун: не спамим одним и тем же статусом чаще раз в 5 минут
        if now - self._last_alert.get(key, 0) < _ALERT_COOLDOWN:
            return

        self._last_alert[key] = now

        emoji = "⚠️" if snap.status == "degraded" else "🔴"
        msg = (
            f"{emoji} *ARGOS HealthMonitor — {snap.status.upper()}*\n"
            f"CPU: {snap.cpu_pct:.1f}%  RAM: {snap.ram_pct:.1f}%  "
            f"Disk: {snap.disk_pct:.1f}%\n"
        )
        failed = [c for c in snap.components if not c.ok]
        if failed:
            msg += "Проблемы: " + ", ".join(c.name for c in failed)

        try:
            import asyncio, inspect
            if inspect.iscoroutinefunction(self._alert_cb):
                asyncio.get_event_loop().create_task(self._alert_cb(msg))
            else:
                self._alert_cb(msg)
        except Exception as e:
            _log(f"HealthMonitor alert_cb error: {e}")


def _log(msg: str) -> None:
    try:
        from src.argos_logger import get_logger
        get_logger("health_monitor").warning(msg)
    except Exception:
        print(f"[HealthMonitor] {msg}", flush=True)


# ── CLI / ручной запуск ───────────────────────────────────────────────────
if __name__ == "__main__":
    import json

    monitor = HealthMonitor()
    monitor.start()
    time.sleep(3)
    snap = monitor.latest()
    if snap:
        print(json.dumps(snap.to_dict(), indent=2, ensure_ascii=False))
    monitor.stop()

"""
src/graceful_shutdown.py — ARGOS v2.0.0
Обработчики SIGTERM / SIGINT / atexit на всех платформах.
Корректно завершает P2P, IoT, Telegram, очередь задач и SQLite.
"""

from __future__ import annotations

import atexit
import signal
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional


class GracefulShutdown:
    """
    Регистрирует обработчики сигналов и atexit-хуки.
    Каждая подсистема регистрирует свой shutdown-callback.

    Использование::

        shutdown = GracefulShutdown(timeout=10)
        shutdown.register("p2p",      p2p_bridge.stop)
        shutdown.register("telegram", bot.stop,           priority=10)
        shutdown.register("task_queue", queue.shutdown,   priority=5)
        shutdown.register("db",       db.close,           priority=1)
        shutdown.setup_signals()      # вызвать один раз при запуске
    """

    def __init__(self, timeout: float = 15.0):
        self._timeout    = timeout
        self._callbacks: List[Dict[str, Any]] = []
        self._done       = threading.Event()
        self._lock       = threading.Lock()
        self._triggered  = False

    # ── Регистрация ────────────────────────────────────────────────────────

    def register(
        self,
        name:     str,
        callback: Callable,
        priority: int = 5,
        timeout:  Optional[float] = None,
    ) -> None:
        """
        Зарегистрировать shutdown-callback.

        Args:
            name:     метка для логов.
            callback: функция без аргументов (sync или async).
            priority: порядок вызова — выше = раньше (10 → 1).
            timeout:  максимальное время ожидания этого callback (сек).
        """
        with self._lock:
            self._callbacks.append({
                "name":     name,
                "fn":       callback,
                "priority": priority,
                "timeout":  timeout or self._timeout,
            })

    def setup_signals(self) -> None:
        """Зарегистрировать обработчики OS-сигналов и atexit."""
        if sys.platform != "win32":
            signal.signal(signal.SIGTERM, self._handler)
        signal.signal(signal.SIGINT,  self._handler)
        atexit.register(self._run)

    def trigger(self) -> None:
        """Инициировать завершение вручную (например, из команды 'выключить')."""
        self._handler(None, None)

    def wait(self) -> None:
        """Блокировать до завершения всех callback-ов."""
        self._done.wait()

    # ── Внутренняя логика ──────────────────────────────────────────────────

    def _handler(self, signum: Any, frame: Any) -> None:
        with self._lock:
            if self._triggered:
                return
            self._triggered = True
        _log("🛑 Получен сигнал завершения. Останавливаю подсистемы...")
        t = threading.Thread(target=self._run, name="ArgosShutdown", daemon=True)
        t.start()

    def _run(self) -> None:
        sorted_cbs = sorted(
            self._callbacks,
            key=lambda c: c["priority"],
            reverse=True,  # высокий приоритет — первым
        )
        for cb in sorted_cbs:
            self._call(cb)
        _log("✅ Все подсистемы остановлены.")
        self._done.set()

    @staticmethod
    def _call(cb: Dict[str, Any]) -> None:
        name    = cb["name"]
        fn      = cb["fn"]
        timeout = cb["timeout"]
        _log(f"   ↳ Останавливаю {name}...")
        done = threading.Event()

        def _run_fn() -> None:
            try:
                import asyncio, inspect
                if inspect.iscoroutinefunction(fn):
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            asyncio.ensure_future(fn())
                            time.sleep(0.5)
                        else:
                            loop.run_until_complete(fn())
                    except RuntimeError:
                        asyncio.run(fn())
                else:
                    fn()
            except Exception as e:
                _log(f"   ⚠️  {name} ошибка завершения: {e}")
            finally:
                done.set()

        t = threading.Thread(target=_run_fn, daemon=True)
        t.start()
        if not done.wait(timeout):
            _log(f"   ⏱️  {name} timeout ({timeout}s) — принудительно")


def _log(msg: str) -> None:
    try:
        from src.argos_logger import get_logger
        get_logger("graceful_shutdown").info(msg)
    except Exception:
        print(msg, flush=True)


# ── Singleton для использования в main.py ─────────────────────────────────
_instance: Optional[GracefulShutdown] = None


def get_shutdown_manager() -> GracefulShutdown:
    global _instance
    if _instance is None:
        _instance = GracefulShutdown()
    return _instance

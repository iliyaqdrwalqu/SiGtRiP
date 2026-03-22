"""
src/awareness.py
━━━━━━━━━━━━━━━
Re-export корневого awareness.py для совместимости тестов:
  from src.awareness import ArgosAwareness, _safe
"""
from __future__ import annotations

import os
import sys

# Добавляем корень проекта в путь, чтобы найти корневой awareness.py
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

try:
    from awareness import ArgosAwareness, _safe, SelfAwareness  # noqa: F401
except ImportError:
    # Если корневой awareness.py не найден — определяем базовый класс
    import time
    import platform

    def _safe(fn):
        try:
            return fn()
        except Exception:
            return ""

    class ArgosAwareness:
        def __init__(self, core=None):
            self.core = core
            self._start_time = time.time()
            self._impact_log: list = []

        def perceive(self) -> dict:
            world = {
                "platform": platform.system(),
                "arch": platform.machine(),
                "hostname": _safe(lambda: __import__("socket").gethostname()),
                "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            try:
                try:
    import psutil
except Exception:
    from src import psutil_android as psutil
                mem = psutil.virtual_memory()
                world["cpu_pct"] = 0.0
                world["ram_pct"] = mem.percent
                world["ram_mb"] = mem.total // 1024 // 1024
            except Exception:
                pass
            if self.core:
                p2p = getattr(self.core, "p2p", None)
                if p2p:
                    world["p2p_nodes"] = getattr(p2p, "node_count", 0)
            return world

        def record_impact(self, action: str, result: str, affected: str = "user") -> dict:
            positive = any(w in result.lower() for w in ["✅", "успешно", "готово", "помог", "решил"])
            negative = any(w in result.lower() for w in ["❌", "ошибка", "не могу", "отказ"])
            impact = {
                "action": action[:100],
                "affected": affected,
                "positive": positive,
                "negative": negative,
                "neutral": not positive and not negative,
                "timestamp": time.time(),
            }
            self._impact_log.append(impact)
            if len(self._impact_log) > 500:
                self._impact_log = self._impact_log[-250:]
            return impact

        def reflect(self) -> str:
            world = self.perceive()
            uptime_h = round((time.time() - self._start_time) / 3600, 2)
            positive = sum(1 for i in self._impact_log if i["positive"])
            total = len(self._impact_log)
            lines = [
                "👁️  ОСОЗНАНИЕ АРГОСА",
                f"  Платформа : {world.get('platform', '?')} / {world.get('arch', '?')}",
                f"  Хост      : {world.get('hostname', '?')}",
                f"  Аптайм    : {uptime_h} ч.",
                f"  CPU       : {world.get('cpu_pct', '?')}%",
                f"  RAM       : {world.get('ram_pct', '?')}%  ({world.get('ram_mb', '?')} МБ)",
                f"  Действий  : {total} (положительных: {positive})",
            ]
            if "p2p_nodes" in world:
                lines.append(f"  P2P узлов : {world['p2p_nodes']}")
            return "\n".join(lines)

    SelfAwareness = None  # type: ignore

__all__ = ["ArgosAwareness", "_safe", "SelfAwareness"]

"""
src/ai_failover.py — ARGOS v2.0.0
Multi-Provider Failover: автоматическое переключение между AI-провайдерами
при ошибке с экспоненциальным backoff и детальным логированием.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


class ProviderStatus(str, Enum):
    OK      = "ok"
    FAILING = "failing"
    DOWN    = "down"


@dataclass
class ProviderStats:
    name:          str
    status:        ProviderStatus = ProviderStatus.OK
    success_count: int = 0
    fail_count:    int = 0
    last_error:    str = ""
    last_used:     float = 0.0
    backoff_until: float = 0.0   # unix timestamp — не использовать до этого момента

    @property
    def available(self) -> bool:
        return time.time() >= self.backoff_until and self.status != ProviderStatus.DOWN


# ─── Конфигурация провайдеров ──────────────────────────────────────────────

_PROVIDER_ORDER = [
    "gemini",
    "openai",
    "grok",
    "watsonx",
    "gigachat",
    "yandexgpt",
    "ollama",
    "lmstudio",
]

# Базовые задержки backoff в секундах: попытка 1, 2, 3...
_BACKOFF_DELAYS = [5, 15, 60, 300, 900]


class AIFailover:
    """
    Обёртка над ai_providers.py с автоматическим failover.

    Использование::

        failover = AIFailover()
        response = await failover.ask("Что такое квантовые вычисления?")
        # → пробует провайдеров по приоритету до первого успешного ответа

        # Принудительно использовать конкретный провайдер:
        response = await failover.ask("...", prefer="ollama")

        # Статус всех провайдеров:
        for name, stats in failover.stats().items():
            print(f"{name}: {stats.status.value}")
    """

    def __init__(self, provider_module: Any = None):
        self._mod   = provider_module       # внедрение зависимости для тестов
        self._stats: Dict[str, ProviderStats] = {
            name: ProviderStats(name=name) for name in _PROVIDER_ORDER
        }
        self._lock  = asyncio.Lock()

    # ── Публичный API ──────────────────────────────────────────────────────

    async def ask(
        self,
        prompt:         str,
        system:         str = "",
        prefer:         Optional[str] = None,
        context:        Optional[List[Dict]] = None,
        max_retries:    int = 3,
        **kwargs,
    ) -> Tuple[str, str]:
        """
        Отправить запрос, используя failover между провайдерами.

        Returns:
            (response_text, provider_name_used)

        Raises:
            RuntimeError: если все провайдеры недоступны.
        """
        order = self._build_order(prefer)
        last_error = ""

        for provider_name in order:
            stats = self._stats[provider_name]
            if not stats.available:
                continue

            for attempt in range(max_retries):
                try:
                    result = await self._call_provider(
                        provider_name, prompt, system, context, **kwargs
                    )
                    self._record_success(provider_name)
                    return result, provider_name
                except Exception as e:
                    last_error = str(e)
                    _log(f"AIFailover: {provider_name} attempt {attempt+1} failed: {e}")
                    if not self._is_retryable(e):
                        break
                    delay = _BACKOFF_DELAYS[min(attempt, len(_BACKOFF_DELAYS) - 1)]
                    await asyncio.sleep(delay)

            self._record_failure(provider_name, last_error)

        raise RuntimeError(
            f"AIFailover: все {len(order)} провайдеров недоступны. "
            f"Последняя ошибка: {last_error}"
        )

    def stats(self) -> Dict[str, ProviderStats]:
        return dict(self._stats)

    def reset(self, provider_name: Optional[str] = None) -> None:
        """Сбросить статус провайдера (или всех)."""
        names = [provider_name] if provider_name else list(self._stats)
        for name in names:
            if name in self._stats:
                self._stats[name] = ProviderStats(name=name)

    def set_order(self, order: List[str]) -> None:
        """Переопределить порядок провайдеров."""
        global _PROVIDER_ORDER
        _PROVIDER_ORDER = [p for p in order if p in self._stats]

    # ── Внутренняя логика ──────────────────────────────────────────────────

    def _build_order(self, prefer: Optional[str]) -> List[str]:
        order = list(_PROVIDER_ORDER)
        # Смотрим на ARGOS_AGENT_BACKEND для дефолтного провайдера
        env_backend = os.getenv("ARGOS_AGENT_BACKEND", "auto").lower()
        if env_backend != "auto" and env_backend in order:
            order.remove(env_backend)
            order.insert(0, env_backend)
        if prefer and prefer in order:
            order.remove(prefer)
            order.insert(0, prefer)
        return order

    async def _call_provider(
        self,
        name:    str,
        prompt:  str,
        system:  str,
        context: Optional[List[Dict]],
        **kwargs,
    ) -> str:
        """Вызвать конкретного провайдера через ai_providers.py."""
        mod = self._mod
        if mod is None:
            try:
                from src import ai_providers as _mod
                mod = _mod
            except ImportError:
                raise RuntimeError(f"src/ai_providers.py не найден")

        # Ищем async-функцию провайдера
        fn_names = [
            f"ask_{name}",
            f"{name}_ask",
            f"ask",
        ]
        fn = None
        for fn_name in fn_names:
            fn = getattr(mod, fn_name, None)
            if fn is not None:
                break

        if fn is None:
            raise RuntimeError(f"Провайдер '{name}' не реализован в ai_providers")

        # Поддерживаем и sync, и async провайдеры
        import inspect
        if inspect.iscoroutinefunction(fn):
            result = await fn(prompt, system=system, context=context, **kwargs)
        else:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, lambda: fn(prompt, system=system, context=context, **kwargs)
            )

        if not result or not isinstance(result, str):
            raise ValueError(f"Провайдер '{name}' вернул пустой ответ")
        return result

    def _record_success(self, name: str) -> None:
        s = self._stats[name]
        s.success_count += 1
        s.last_used = time.time()
        s.status = ProviderStatus.OK
        s.backoff_until = 0.0
        _log(f"AIFailover: ✅ {name} — успех (всего: {s.success_count})")

    def _record_failure(self, name: str, error: str) -> None:
        s = self._stats[name]
        s.fail_count += 1
        s.last_error = error
        # Экспоненциальный backoff на основе количества ошибок подряд
        delay_idx = min(s.fail_count - 1, len(_BACKOFF_DELAYS) - 1)
        delay = _BACKOFF_DELAYS[delay_idx]
        s.backoff_until = time.time() + delay
        s.status = ProviderStatus.DOWN if s.fail_count >= 5 else ProviderStatus.FAILING
        _log(f"AIFailover: ❌ {name} — ошибок: {s.fail_count}, backoff: {delay}s | {error[:80]}")

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        """Определить, стоит ли повторять запрос после этой ошибки."""
        msg = str(exc).lower()
        # Не повторяем при явных ошибках авторизации
        if any(kw in msg for kw in ("api key", "unauthorized", "forbidden", "invalid key")):
            return False
        # Повторяем при сетевых ошибках и rate limit
        if any(kw in msg for kw in ("timeout", "rate limit", "503", "502", "connection")):
            return True
        return True


def _log(msg: str) -> None:
    try:
        from src.argos_logger import get_logger
        get_logger("ai_failover").info(msg)
    except Exception:
        print(f"[AIFailover] {msg}", flush=True)


# ── Singleton ──────────────────────────────────────────────────────────────
_instance: Optional[AIFailover] = None


def get_failover() -> AIFailover:
    global _instance
    if _instance is None:
        _instance = AIFailover()
    return _instance

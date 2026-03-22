"""
src/ollama_three.py — Менеджер трёх моделей Ollama.

Архитектура:
  ┌─────────────────────────────────────────────────┐
  │  ARGOS запрос                                    │
  │       ↓                                          │
  │  Определяем тип задачи                           │
  │       ↓                                          │
  │  fast?  → tinyllama (локальная, 637MB)           │
  │  smart? → llama3.2:3b (локальная, 2GB)           │
  │  hard?  → gpt-oss:120b-cloud (облако Ollama)     │
  │       ↓                                          │
  │  Нет ответа → следующая модель                   │
  └─────────────────────────────────────────────────┘
"""
from __future__ import annotations

import os
import time
import logging
import threading
from typing import Optional

log = logging.getLogger("argos.ollama_three")

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
TIMEOUT_FAST  = int(os.getenv("OLLAMA_TIMEOUT_FAST",  "30"))
TIMEOUT_SMART = int(os.getenv("OLLAMA_TIMEOUT_SMART", "120"))
TIMEOUT_CLOUD = int(os.getenv("OLLAMA_TIMEOUT_CLOUD", "180"))

# Ключевые слова для определения сложности задачи
HARD_KEYWORDS = [
    "разработай архитектуру", "напиши подробный", "создай систему",
    "проанализируй", "сравни детально", "объясни в деталях",
    "написать код для", "реализуй алгоритм", "design", "architecture",
]
FAST_KEYWORDS = [
    "статус", "привет", "помощь", "время", "погода", "кратко",
    "да", "нет", "ok", "ок", "спасибо", "пока",
]


def _classify(prompt: str) -> str:
    p = prompt.lower()
    if any(kw in p for kw in FAST_KEYWORDS) or len(prompt) < 30:
        return "fast"
    if any(kw in p for kw in HARD_KEYWORDS) or len(prompt) > 300:
        return "hard"
    return "smart"


class ThreeModelManager:
    """Менеджер трёх моделей Ollama."""

    def __init__(self):
        self.model_fast  = os.getenv("OLLAMA_FAST_MODEL",  "tinyllama")
        self.model_smart = os.getenv("OLLAMA_MODEL",       "llama3.2:3b")
        self.model_cloud = os.getenv("OLLAMA_CLOUD_MODEL", "gpt-oss:120b-cloud")
        self.host = OLLAMA_HOST
        self._status_cache: dict[str, tuple[bool, float]] = {}

    def _is_model_available(self, model: str) -> bool:
        """Кешируем проверку на 60 секунд."""
        cached = self._status_cache.get(model)
        if cached and (time.time() - cached[1]) < 60:
            return cached[0]
        try:
            import requests
            resp = requests.get(f"{self.host}/api/tags", timeout=3)
            models = [m["name"] for m in resp.json().get("models", [])]
            available = any(model.split(":")[0] in m for m in models)
            self._status_cache[model] = (available, time.time())
            return available
        except Exception:
            self._status_cache[model] = (False, time.time())
            return False

    def _ask_ollama(self, model: str, prompt: str,
                    system: str = "", timeout: int = 120) -> Optional[str]:
        try:
            import requests
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False,
            }
            if system:
                payload["system"] = system
            resp = requests.post(
                f"{self.host}/api/generate",
                json=payload,
                timeout=timeout,
            )
            result = resp.json().get("response", "").strip()
            return result if result else None
        except Exception as e:
            log.warning(f"[{model}] ошибка: {e}")
            return None

    def ask(self, prompt: str, system: str = "",
            force: Optional[str] = None) -> tuple[Optional[str], str]:
        """
        Умный запрос к трём моделям.
        Возвращает (ответ, имя_модели).
        force = "fast" | "smart" | "cloud" — принудительный выбор.
        """
        task = force or _classify(prompt)
        log.info(f"[ThreeModel] задача='{task}' prompt[:50]='{prompt[:50]}'")

        # Порядок попыток по типу задачи
        order = {
            "fast":  [self.model_fast,  self.model_smart, self.model_cloud],
            "smart": [self.model_smart, self.model_cloud, self.model_fast],
            "hard":  [self.model_cloud, self.model_smart, self.model_fast],
        }.get(task, [self.model_smart, self.model_cloud, self.model_fast])

        timeouts = {
            self.model_fast:  TIMEOUT_FAST,
            self.model_smart: TIMEOUT_SMART,
            self.model_cloud: TIMEOUT_CLOUD,
        }

        for model in order:
            if not model:
                continue
            if not self._is_model_available(model):
                log.info(f"[ThreeModel] {model} недоступна — пропускаем")
                continue
            log.info(f"[ThreeModel] пробуем {model}...")
            result = self._ask_ollama(
                model, prompt, system, timeouts.get(model, 120)
            )
            if result:
                log.info(f"[ThreeModel] ответ от {model}")
                return result, model

        return None, "none"

    def ask_parallel(self, prompt: str, system: str = "") -> tuple[Optional[str], str]:
        """
        Параллельный режим: спрашиваем fast и smart одновременно,
        берём первый ответ. cloud используем если оба не ответили.
        """
        results: dict[str, Optional[str]] = {}
        lock = threading.Lock()
        first_result = [None, None]  # [answer, model]
        event = threading.Event()

        def _ask(model, timeout):
            if not self._is_model_available(model):
                return
            r = self._ask_ollama(model, prompt, system, timeout)
            with lock:
                results[model] = r
                if r and not event.is_set():
                    first_result[0] = r
                    first_result[1] = model
                    event.set()

        threads = [
            threading.Thread(target=_ask, args=(self.model_fast, TIMEOUT_FAST)),
            threading.Thread(target=_ask, args=(self.model_smart, TIMEOUT_SMART)),
        ]
        for t in threads:
            t.daemon = True
            t.start()

        # Ждём первого ответа максимум TIMEOUT_SMART секунд
        event.wait(timeout=TIMEOUT_SMART)

        if first_result[0]:
            return first_result[0], first_result[1]

        # Fallback на облако
        if self._is_model_available(self.model_cloud):
            r = self._ask_ollama(self.model_cloud, prompt, system, TIMEOUT_CLOUD)
            if r:
                return r, self.model_cloud

        return None, "none"

    def status(self) -> str:
        models = [
            (self.model_fast,  "Быстрая (локальная)"),
            (self.model_smart, "Умная  (локальная)"),
            (self.model_cloud, "Облако (Ollama Cloud)"),
        ]
        lines = ["🤖 Три модели Ollama:\n"]
        for model, desc in models:
            if not model:
                continue
            ok = self._is_model_available(model)
            icon = "✅" if ok else "❌"
            lines.append(f"  {icon}  {model:<25} — {desc}")

        lines.append("")
        lines.append("  Команды:")
        lines.append("  три модели статус  — этот экран")
        lines.append("  три модели быстро <запрос>  — tinyllama")
        lines.append("  три модели умно <запрос>    — llama3.2:3b")
        lines.append("  три модели облако <запрос>  — gpt-oss:120b")
        lines.append("  три модели авто <запрос>    — автовыбор")
        return "\n".join(lines)

    def pull_all(self) -> str:
        """Скачать все три модели."""
        lines = []
        for model in [self.model_fast, self.model_smart, self.model_cloud]:
            if not model:
                continue
            try:
                import subprocess
                result = subprocess.run(
                    ["ollama", "pull", model],
                    capture_output=True, text=True, timeout=300
                )
                if result.returncode == 0:
                    lines.append(f"✅ {model} скачана")
                else:
                    lines.append(f"❌ {model}: {result.stderr[:100]}")
            except Exception as e:
                lines.append(f"❌ {model}: {e}")
        return "\n".join(lines)


# Глобальный инстанс
_manager: Optional[ThreeModelManager] = None


def get_manager() -> ThreeModelManager:
    global _manager
    if _manager is None:
        _manager = ThreeModelManager()
    return _manager

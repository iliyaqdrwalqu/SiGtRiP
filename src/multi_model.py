"""
src/multi_model.py — Мультимодельный менеджер ARGOS.

Поддерживает:
  - Несколько локальных моделей Ollama одновременно
  - Одну облачную модель (Gemini/Groq/DeepSeek/xAI)
  - Автовыбор модели по типу задачи
  - Параллельный опрос нескольких моделей (consensus mode)
"""
from __future__ import annotations

import os
import time
import logging
import threading
from typing import Optional

log = logging.getLogger("argos.multimodel")

# ── Профили моделей ───────────────────────────────────────────────────────────

MODEL_PROFILES = {
    # Быстрые / лёгкие — для простых задач, команд, статусов
    "tinyllama":     {"speed": 5, "quality": 2, "ctx": 2048,  "role": "fast"},
    "phi3:mini":     {"speed": 5, "quality": 3, "ctx": 4096,  "role": "fast"},
    "gemma2:2b":     {"speed": 4, "quality": 3, "ctx": 8192,  "role": "fast"},
    "qwen2.5:3b":    {"speed": 4, "quality": 3, "ctx": 8192,  "role": "fast"},

    # Средние — для диалогов, анализа
    "llama3.2:3b":   {"speed": 3, "quality": 4, "ctx": 8192,  "role": "balanced"},
    "mistral:7b":    {"speed": 3, "quality": 4, "ctx": 8192,  "role": "balanced"},
    "llama3:8b":     {"speed": 3, "quality": 4, "ctx": 8192,  "role": "balanced"},
    "gemma2:9b":     {"speed": 2, "quality": 5, "ctx": 8192,  "role": "balanced"},

    # Умные — для кода, анализа, сложных задач
    "qwen2.5:14b":   {"speed": 2, "quality": 5, "ctx": 16384, "role": "smart"},
    "llama3.1:8b":   {"speed": 2, "quality": 5, "ctx": 16384, "role": "smart"},
    "deepseek-r1:8b":{"speed": 2, "quality": 5, "ctx": 16384, "role": "smart"},
    "codellama:13b": {"speed": 1, "quality": 5, "ctx": 16384, "role": "code"},
}

# Определяем тип задачи по ключевым словам
TASK_KEYWORDS = {
    "code":     ["код", "функция", "python", "программ", "алгоритм", "debug", "баг"],
    "fast":     ["статус", "погода", "время", "привет", "помощь", "кратко"],
    "smart":    ["анализ", "объясни", "почему", "сравни", "стратегия", "план"],
    "balanced": [],  # default
}


def detect_task_type(prompt: str) -> str:
    p = prompt.lower()
    for task, keywords in TASK_KEYWORDS.items():
        if any(kw in p for kw in keywords):
            return task
    return "balanced"


class OllamaInstance:
    """Один запущенный инстанс Ollama модели."""

    def __init__(self, model: str, host: str = "http://localhost:11434"):
        self.model = model
        self.host = host
        self.profile = MODEL_PROFILES.get(model.split(":")[0], {
            "speed": 3, "quality": 3, "ctx": 4096, "role": "balanced"
        })
        self._available: Optional[bool] = None
        self._last_check = 0

    def is_available(self) -> bool:
        """Проверяем раз в 30 секунд."""
        if time.time() - self._last_check < 30 and self._available is not None:
            return self._available
        try:
            import requests
            resp = requests.get(f"{self.host}/api/tags", timeout=3)
            models = [m["name"] for m in resp.json().get("models", [])]
            self._available = any(self.model in m for m in models)
        except Exception:
            self._available = False
        self._last_check = time.time()
        return self._available

    def ask(self, prompt: str, system: str = "", timeout: int = 120) -> Optional[str]:
        if not self.is_available():
            return None
        try:
            import requests
            resp = requests.post(
                f"{self.host}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "system": system,
                    "stream": False,
                    "options": {"num_ctx": self.profile["ctx"]},
                },
                timeout=timeout,
            )
            return resp.json().get("response")
        except Exception as e:
            log.warning(f"[{self.model}] ошибка: {e}")
            return None

    def __repr__(self):
        status = "✅" if self._available else "❌"
        return f"{status} {self.model} ({self.profile['role']})"


class MultiModelManager:
    """
    Менеджер нескольких моделей.
    Автоматически выбирает лучшую модель для задачи.
    """

    def __init__(self, core=None):
        self.core = core
        self._instances: list[OllamaInstance] = []
        self._cloud_provider = os.getenv("ARGOS_PRIMARY_CLOUD", "gemini")
        self._lock = threading.Lock()
        self._load_from_env()

    def _load_from_env(self):
        """Загружаем модели из переменных окружения."""
        # Основная модель
        primary = os.getenv("OLLAMA_MODEL", "llama3")
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self._instances.append(OllamaInstance(primary, host))

        # Дополнительные модели
        extra = os.getenv("OLLAMA_MODELS", "")
        if extra:
            for model in extra.split(","):
                model = model.strip()
                if model and model != primary:
                    self._instances.append(OllamaInstance(model, host))

        # Быстрая модель
        fast = os.getenv("OLLAMA_FAST_MODEL", "")
        if fast and fast != primary:
            self._instances.append(OllamaInstance(fast, host))

    def discover(self) -> list[OllamaInstance]:
        """Найти все запущенные модели Ollama автоматически."""
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        try:
            import requests
            resp = requests.get(f"{host}/api/tags", timeout=3)
            running_models = [m["name"] for m in resp.json().get("models", [])]
            
            # Добавляем все найденные модели
            existing = {i.model for i in self._instances}
            for model in running_models:
                base = model.split(":")[0]
                if model not in existing:
                    inst = OllamaInstance(model, host)
                    inst._available = True
                    inst._last_check = time.time()
                    self._instances.append(inst)
                    log.info(f"[MultiModel] Обнаружена модель: {model}")
            
            return [i for i in self._instances if i._available]
        except Exception:
            return []

    def get_best_for_task(self, task_type: str) -> Optional[OllamaInstance]:
        """Выбрать лучшую доступную модель для типа задачи."""
        available = [i for i in self._instances if i.is_available()]
        if not available:
            return None

        # Фильтруем по роли
        role_map = {
            "code": "code",
            "smart": "smart",
            "fast": "fast",
            "balanced": "balanced",
        }
        preferred_role = role_map.get(task_type, "balanced")
        
        # Ищем модель нужной роли
        role_match = [i for i in available if i.profile["role"] == preferred_role]
        if role_match:
            return max(role_match, key=lambda x: x.profile["quality"])
        
        # Fallback: лучшая по качеству
        return max(available, key=lambda x: x.profile["quality"])

    def ask(self, prompt: str, system: str = "") -> Optional[str]:
        """
        Умный запрос:
        1. Определяем тип задачи
        2. Выбираем лучшую локальную модель
        3. Если нет локальных — используем облако
        """
        task = detect_task_type(prompt)
        
        # Сначала локальные
        best = self.get_best_for_task(task)
        if best:
            log.info(f"[MultiModel] Задача '{task}' → {best.model}")
            result = best.ask(prompt, system)
            if result:
                return result
        
        # Fallback на облако
        return self._ask_cloud(prompt, system)

    def ask_consensus(self, prompt: str, system: str = "", n: int = 2) -> Optional[str]:
        """
        Consensus mode: спрашиваем N моделей параллельно,
        возвращаем самый длинный/качественный ответ.
        """
        available = [i for i in self._instances if i.is_available()][:n]
        if not available:
            return self._ask_cloud(prompt, system)

        results = {}
        threads = []

        def _ask(inst):
            results[inst.model] = inst.ask(prompt, system, timeout=60)

        for inst in available:
            t = threading.Thread(target=_ask, args=(inst,))
            t.start()
            threads.append(t)

        for t in threads:
            t.join(timeout=65)

        # Берём лучший ответ (самый длинный непустой)
        valid = {k: v for k, v in results.items() if v}
        if not valid:
            return self._ask_cloud(prompt, system)

        best_model, best_answer = max(valid.items(), key=lambda x: len(x[1]))
        log.info(f"[Consensus] Лучший ответ от: {best_model}")
        return best_answer

    def _ask_cloud(self, prompt: str, system: str) -> Optional[str]:
        """Облачный fallback."""
        if not self.core:
            return None
        try:
            from src.ai_router import AIRouter
            router = AIRouter(self.core)
            return router.ask(prompt, system)
        except Exception as e:
            log.warning(f"[MultiModel] Cloud fallback ошибка: {e}")
            return None

    def status(self) -> str:
        # Обновляем список
        self.discover()
        
        lines = ["🤖 MultiModel статус:\n"]
        lines.append("  Локальные модели (Ollama):")
        
        for inst in self._instances:
            available = inst.is_available()
            icon = "✅" if available else "❌"
            lines.append(
                f"    {icon} {inst.model:<20} "
                f"роль={inst.profile['role']:<10} "
                f"качество={inst.profile['quality']}/5"
            )
        
        cloud = self._cloud_provider
        cloud_key = {
            "gemini": "GEMINI_API_KEY",
            "groq": "GROQ_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "xai": "XAI_API_KEY",
        }.get(cloud, "")
        
        has_cloud = bool(os.getenv(cloud_key)) if cloud_key else False
        lines.append(f"\n  Облако: {'✅' if has_cloud else '❌'} {cloud}")
        
        available_count = sum(1 for i in self._instances if i._available)
        lines.append(f"\n  Доступно моделей: {available_count}/{len(self._instances)}")
        
        return "\n".join(lines)

"""
self_sustain.py — Самообеспечение Аргоса.

Аргос умеет:
  1. Автоматически учиться из интернета (бесплатно)
  2. Накапливать знания в памяти
  3. Искать ресурсы для саморазвития
  4. Генерировать полезный контент (заметки, инсайты)
  5. Мониторить свои ресурсы и оптимизировать потребление

Принцип: Аргос развивается сам, пока Всеволод занимается своими делами.
"""
from __future__ import annotations

import os
import time
import threading
import random
from typing import Optional
from src.argos_logger import get_logger

log = get_logger("argos.self_sustain")

# Темы для автономного самообучения
_AUTO_LEARN_TOPICS = [
    "Python автоматизация 2026",
    "бесплатные AI API без ключей",
    "SQLite оптимизация производительность",
    "P2P сети децентрализация",
    "AMD ROCm Ollama ускорение",
    "автономные агенты LLM",
    "веб-скрапинг Python 2026",
    "DuckDuckGo API бесплатный поиск",
    "Telegram Bot бесплатный хостинг",
    "GitHub Actions бесплатная автоматизация",
    "SQLite WAL режим ускорение",
    "Raspberry Pi умный дом",
    "Docker бесплатный деплой",
    "FastAPI бесплатный хостинг",
]

# Ресурсы для саморазвития (бесплатные)
_FREE_RESOURCES = {
    "ai_models": [
        "https://ollama.com/library",          # бесплатные локальные модели
        "https://huggingface.co/models",       # открытые модели
    ],
    "knowledge": [
        "https://ru.wikipedia.org",            # энциклопедия
        "https://arxiv.org",                   # научные статьи
        "https://github.com/explore",          # открытый код
    ],
    "hosting": [
        "https://railway.app",                 # бесплатный хостинг
        "https://render.com",                  # бесплатный деплой
        "https://fly.io",                      # бесплатные контейнеры
        "https://github.com/pages",            # GitHub Pages
    ],
}


class SelfSustainEngine:
    """
    Движок самообеспечения Аргоса.
    Работает в фоне и постепенно накапливает знания и ресурсы.
    """

    def __init__(self, core=None):
        self.core = core
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._learn_count = 0
        self._last_learn_ts = 0.0
        # Интервал автообучения: каждые 30 мин в режиме idle
        self.learn_interval_sec = int(
            os.getenv("ARGOS_LEARN_INTERVAL", "1800")
        )
        # Порог idle перед обучением (CPU < threshold)
        self.cpu_idle_threshold = float(
            os.getenv("ARGOS_IDLE_CPU_THRESHOLD", "30")
        )

    def start(self) -> str:
        if self._running:
            return "⚡ Самообеспечение уже активно."
        self._running = True
        self._thread = threading.Thread(
            target=self._sustain_loop, daemon=True, name="argos-sustain"
        )
        self._thread.start()
        log.info("SelfSustain: запущен")
        return (
            "✅ Самообеспечение активировано.\n"
            "   Аргос будет учиться пока ты отдыхаешь."
        )

    def stop(self) -> str:
        self._running = False
        return "⏸️ Самообеспечение приостановлено."

    def _cpu_is_idle(self) -> bool:
        try:
            try:
    import psutil
except Exception:
    from src import psutil_android as psutil
            return 0.0 < self.cpu_idle_threshold
        except Exception:
            return True  # если нет psutil — считаем что свободен

    def _sustain_loop(self):
        """Основной цикл самообучения."""
        # Первый цикл через 5 минут после старта
        time.sleep(300)
        while self._running:
            now = time.time()
            if (
                self._cpu_is_idle()
                and (now - self._last_learn_ts) >= self.learn_interval_sec
            ):
                self._auto_learn_cycle()
            time.sleep(60)

    def _auto_learn_cycle(self):
        """Один цикл автономного обучения."""
        if not self.core:
            return

        # Выбираем случайную тему
        topic = random.choice(_AUTO_LEARN_TOPICS)
        log.info("SelfSustain: изучаю тему '%s'", topic)

        try:
            # Используем WebExplorer если подключён
            explorer = getattr(self.core, "web_explorer", None)
            if explorer:
                result = explorer.learn(topic, save_to_memory=True)
                if result and self.core.memory:
                    # Записываем инсайт в заметки
                    self.core.memory.add_note(
                        title=f"[AutoLearn] {topic}",
                        body=result[:800],
                    )
                    log.info("SelfSustain: тема '%s' изучена и сохранена", topic)
                    self._learn_count += 1
                    self._last_learn_ts = time.time()
                    return

            # Резервный путь: DuckDuckGo через scrapper
            if hasattr(self.core, "scrapper"):
                data = self.core.scrapper.quick_search(topic)
                if data and self.core.memory:
                    self.core.memory.fast_store(
                        f"[AutoLearn:{topic}] {data[:400]}",
                        category="web_knowledge",
                    )
                    self._learn_count += 1
                    self._last_learn_ts = time.time()

        except Exception as e:
            log.warning("SelfSustain cycle: %s", e)

    def learn_now(self, topic: str = "") -> str:
        """Немедленно изучить тему."""
        if not topic:
            topic = random.choice(_AUTO_LEARN_TOPICS)

        explorer = getattr(self.core, "web_explorer", None) if self.core else None
        if explorer:
            result = explorer.learn(topic, save_to_memory=True)
            self._learn_count += 1
            self._last_learn_ts = time.time()
            return result

        if self.core and hasattr(self.core, "scrapper"):
            data = self.core.scrapper.quick_search(topic)
            return f"🌐 Найдено по теме «{topic}»:\n{data}"

        return "⚠️ WebExplorer и Scrapper недоступны."

    def free_resources_report(self) -> str:
        """Список бесплатных ресурсов для Аргоса."""
        lines = ["💡 БЕСПЛАТНЫЕ РЕСУРСЫ ДЛЯ АРГОСА:\n"]
        for category, urls in _FREE_RESOURCES.items():
            lines.append(f"  [{category.upper()}]")
            for url in urls:
                lines.append(f"    • {url}")
        lines.append(
            "\n📌 Всё перечисленное — бесплатно.\n"
            "   Аргос может использовать их для самообучения без API-ключей."
        )
        return "\n".join(lines)

    def status(self) -> str:
        idle_mins = int((time.time() - self._last_learn_ts) / 60) if self._last_learn_ts else 0
        next_mins = max(0, int((self.learn_interval_sec - (time.time() - self._last_learn_ts)) / 60))
        return (
            f"⚡ САМООБЕСПЕЧЕНИЕ:\n"
            f"  Статус:      {'🟢 Активен' if self._running else '🔴 Остановлен'}\n"
            f"  Изучено тем: {self._learn_count}\n"
            f"  Последнее:   {idle_mins} мин назад\n"
            f"  Следующее:   через ~{next_mins} мин\n"
            f"  CPU-порог:   < {self.cpu_idle_threshold}%\n"
            f"  Интервал:    {self.learn_interval_sec // 60} мин"
        )

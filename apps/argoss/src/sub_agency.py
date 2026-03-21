"""
sub_agency.py — Система суб-агентств Аргоса.

SubAgencyManager управляет набором специализированных SubAgent-ов, каждый из
которых отвечает за определённый домен (сеть, крипто, IoT, файлы, ИИ, …).

Интеграция:
  • ArgosAgent делегирует шаги плана подходящему субагенту вместо того, чтобы
    всегда вызывать core.process_logic напрямую.
  • ArgosCore инициализирует SubAgencyManager через _init_sub_agency().

Команды (core.execute_intent):
  субагенты · список субагентов          — список зарегистрированных агентств
  статус субагентов                      — статус всех субагентств
  запусти субагент [имя] [задача]        — выполнить задачу через субагент
  сбрось субагенты                       — очистить статистику субагентств
"""

from __future__ import annotations

import re
import time
from typing import Any, Callable, Optional

from src.argos_logger import get_logger

log = get_logger("argos.sub_agency")


# ── Базовый класс субагента ────────────────────────────────────────────────

class SubAgent:
    """Специализированный субагент, отвечающий за определённый домен задач."""

    #: Уникальное имя субагента (переопределяется в подклассах)
    name: str = "base"
    #: Короткое человекочитаемое описание
    description: str = "Базовый субагент"
    #: Список ключевых слов, по которым диспетчер направляет задачу сюда
    keywords: list[str] = []

    def __init__(self, core=None) -> None:
        self.core = core
        self._call_count = 0
        self._error_count = 0
        self._last_result: str = ""

    def can_handle(self, task: str) -> bool:
        """Возвращает True, если этот субагент подходит для выполнения задачи."""
        t = task.lower()
        return any(kw in t for kw in self.keywords)

    def execute(self, task: str, context: Any = None) -> str:
        """Выполнить задачу и вернуть строковый результат."""
        self._call_count += 1
        try:
            result = self._run(task, context)
            self._last_result = str(result)[:500]
            return self._last_result
        except Exception as exc:
            self._error_count += 1
            err = f"❌ [{self.name}] Ошибка: {exc}"
            log.error(err)
            self._last_result = err
            return err

    def _run(self, task: str, context: Any = None) -> str:
        """Реализация субагента. Переопределяется в подклассах."""
        raise NotImplementedError

    def status(self) -> str:
        return (
            f"  🔹 {self.name} — {self.description} "
            f"[вызовов: {self._call_count}, ошибок: {self._error_count}]"
        )

    def reset_stats(self) -> None:
        self._call_count = 0
        self._error_count = 0
        self._last_result = ""


# ── Встроенные специализированные субагенты ────────────────────────────────

class _CoreDelegateAgent(SubAgent):
    """Вспомогательный миксин: делегирует задачу core.process_logic."""

    def _run(self, task: str, context: Any = None) -> str:
        if self.core is None:
            return f"[{self.name}] core не подключён, задача: {task}"
        res = self.core.process_logic(task, None, None)
        return res.get("answer", "") if isinstance(res, dict) else str(res)


class NetSubAgent(_CoreDelegateAgent):
    name = "net"
    description = "Сетевой субагент: сканирование, P2P, IoT, mesh"
    keywords = [
        "сеть", "сканируй", "scan", "ip", "порт", "p2p", "mesh", "iot",
        "устройств", "сетевые", "колибри", "подключись", "zigbee", "lora",
    ]


class CryptoSubAgent(_CoreDelegateAgent):
    name = "crypto"
    description = "Крипто-субагент: мониторинг курсов, аналитика"
    keywords = [
        "крипто", "биткоин", "btc", "eth", "ethereum", "курс", "токен",
        "монет", "coin", "binance", "рынок", "crypto",
    ]


class FilesSubAgent(_CoreDelegateAgent):
    name = "files"
    description = "Файловый субагент: чтение, запись, управление файлами"
    keywords = [
        "файл", "папку", "директори", "прочитай", "создай файл",
        "удали файл", "сохрани", "архив", "путь", "каталог",
    ]


class SystemSubAgent(_CoreDelegateAgent):
    name = "system"
    description = "Системный субагент: статус, процессы, мониторинг"
    keywords = [
        "статус", "процесс", "cpu", "ram", "память", "диск", "температур",
        "нагрузк", "system", "репликац", "алерт", "монитор", "чек-ап",
    ]


class AISubAgent(_CoreDelegateAgent):
    name = "ai"
    description = "ИИ-субагент: запросы к языковой модели, анализ"
    keywords = [
        "спроси ии", "запрос ии", "ai query", "ии ответь", "объясни",
        "проанализируй", "суммаризируй", "переведи", "напиши",
    ]


class ScheduleSubAgent(_CoreDelegateAgent):
    name = "schedule"
    description = "Субагент расписания: таймеры, cron, отложенные задачи"
    keywords = [
        "каждые", "расписание", "в 0", "в 1", "через", "запланируй",
        "schedule", "cron", "таймер", "напомни", "автоматически",
    ]


class VisionSubAgent(_CoreDelegateAgent):
    name = "vision"
    description = "Субагент зрения: анализ изображений, экрана, камеры"
    keywords = [
        "посмотри", "камер", "экран", "фото", "изображен", "vision",
        "скриншот", "распознай", "что видишь",
    ]


class ContentSubAgent(_CoreDelegateAgent):
    name = "content"
    description = "Контент-субагент: дайджест, генерация текста, публикация"
    keywords = [
        "дайджест", "новости", "контент", "пост", "статья", "генер",
        "publish", "публикуй", "напиши текст",
    ]


# ── Менеджер субагентств ───────────────────────────────────────────────────

class SubAgencyManager:
    """
    Реестр и диспетчер субагентств.

    Алгоритм маршрутизации:
      1. Перебираем зарегистрированных субагентов по приоритету (порядку регистрации).
      2. Первый, чей can_handle() возвращает True, получает задачу.
      3. Если никто не подходит — возвращает None (задача обрабатывается стандартным путём).
    """

    # Встроенные субагенты в порядке приоритета
    _BUILTIN_CLASSES: list[type[SubAgent]] = [
        VisionSubAgent,
        CryptoSubAgent,
        NetSubAgent,
        FilesSubAgent,
        ScheduleSubAgent,
        ContentSubAgent,
        SystemSubAgent,
        AISubAgent,
    ]

    def __init__(self, core=None) -> None:
        self.core = core
        self._agents: list[SubAgent] = []
        self._custom_agents: dict[str, SubAgent] = {}
        self._init_builtins()
        log.info("SubAgencyManager: %d субагентов зарегистрировано", len(self._agents))

    # ── инициализация ──────────────────────────────────────────────────────

    def _init_builtins(self) -> None:
        for cls in self._BUILTIN_CLASSES:
            agent = cls(self.core)
            self._agents.append(agent)

    # ── регистрация ────────────────────────────────────────────────────────

    def register(self, agent: SubAgent) -> None:
        """Зарегистрировать пользовательский субагент."""
        self._custom_agents[agent.name] = agent
        # Пользовательские агенты имеют наивысший приоритет
        self._agents.insert(0, agent)
        log.info("SubAgencyManager: зарегистрирован %s", agent.name)

    def unregister(self, name: str) -> bool:
        """Удалить пользовательский субагент по имени."""
        if name not in self._custom_agents:
            return False
        agent = self._custom_agents.pop(name)
        self._agents = [a for a in self._agents if a is not agent]
        log.info("SubAgencyManager: удалён %s", name)
        return True

    # ── диспетчеризация ────────────────────────────────────────────────────

    def dispatch(self, task: str, context: Any = None) -> Optional[str]:
        """
        Найти подходящий субагент и выполнить задачу.
        Возвращает строку-результат или None, если никто не взялся.
        """
        for agent in self._agents:
            if agent.can_handle(task):
                log.info("SubAgency: задача → %s: %s", agent.name, task[:60])
                return agent.execute(task, context)
        return None

    def run(self, agent_name: str, task: str, context: Any = None) -> str:
        """Явно запустить субагент по имени."""
        for agent in self._agents:
            if agent.name == agent_name:
                log.info("SubAgency: явный запуск %s: %s", agent_name, task[:60])
                return agent.execute(task, context)
        return f"❌ Субагент '{agent_name}' не найден. Доступные: {self._names_str()}"

    # ── отчёты ────────────────────────────────────────────────────────────

    def list_agents(self) -> str:
        lines = ["🏢 ЗАРЕГИСТРИРОВАННЫЕ СУБАГЕНТСТВА:"]
        for agent in self._agents:
            tag = "🔧" if agent.name in self._custom_agents else "🔹"
            lines.append(f"  {tag} [{agent.name}] {agent.description}")
        return "\n".join(lines)

    def status(self) -> str:
        lines = ["🏢 СТАТУС СУБАГЕНТСТВ:"]
        for agent in self._agents:
            lines.append(agent.status())
        lines.append(f"\nВсего субагентств: {len(self._agents)}")
        return "\n".join(lines)

    def reset_stats(self) -> str:
        for agent in self._agents:
            agent.reset_stats()
        return "♻️ Статистика всех субагентств сброшена."

    def _names_str(self) -> str:
        return ", ".join(a.name for a in self._agents)

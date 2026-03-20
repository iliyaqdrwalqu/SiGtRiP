"""
src/startup_validator.py — ARGOS v2.0.0
Проверяет корректность .env и зависимостей до запуска ядра.
Выводит понятные сообщения об ошибках и предупреждения.
"""

from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional


class Level(str, Enum):
    OK      = "✅"
    WARN    = "⚠️ "
    ERROR   = "❌"
    SKIP    = "⬜"


@dataclass
class CheckResult:
    level:   Level
    message: str
    hint:    Optional[str] = None


@dataclass
class ValidationReport:
    results:  List[CheckResult] = field(default_factory=list)

    @property
    def errors(self) -> List[CheckResult]:
        return [r for r in self.results if r.level == Level.ERROR]

    @property
    def warnings(self) -> List[CheckResult]:
        return [r for r in self.results if r.level == Level.WARN]

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def print(self) -> None:
        print("\n" + "─" * 56)
        print("  🔱 ARGOS v2.0.0 — Проверка окружения")
        print("─" * 56)
        for r in self.results:
            line = f"  {r.level.value}  {r.message}"
            print(line)
            if r.hint:
                print(f"       ↳ {r.hint}")
        print("─" * 56)
        if self.ok:
            w = len(self.warnings)
            print(f"  Готов к запуску{f' (предупреждений: {w})' if w else ''}.\n")
        else:
            print(f"  Критических ошибок: {len(self.errors)}. Запуск невозможен.\n")


# ─── Обязательные переменные окружения ─────────────────────────────────────
_REQUIRED_VARS: list[tuple[str, str]] = [
    # (имя,  подсказка если отсутствует)
]

_OPTIONAL_VARS: list[tuple[str, str, str]] = [
    # (имя, описание, подсказка)
    ("GEMINI_API_KEY",        "Gemini AI",       "ai.google.dev"),
    ("TELEGRAM_BOT_TOKEN",    "Telegram-бот",    "@BotFather"),
    ("USER_ID",               "Telegram User ID","@userinfobot"),
    ("OPENAI_API_KEY",        "OpenAI",          "platform.openai.com"),
    ("WATSONX_API_KEY",       "IBM WatsonX",     "cloud.ibm.com/watsonx"),
    ("ARGOS_REMOTE_TOKEN",    "REST API токен",  "Задай любую строку для защиты API"),
]

_REQUIRED_PYTHON = (3, 11)

_REQUIRED_PACKAGES: list[tuple[str, str]] = [
    ("fastapi",     "pip install fastapi"),
    ("uvicorn",     "pip install uvicorn[standard]"),
    ("psutil",      "pip install psutil"),
    ("dotenv",      "pip install python-dotenv"),
    ("cryptography","pip install cryptography"),
    ("aiohttp",     "pip install aiohttp"),
]

_OPTIONAL_PACKAGES: list[tuple[str, str, str]] = [
    # (import_name, описание, install_hint)
    ("pyttsx3",         "TTS голос",           "pip install pyttsx3"),
    ("speech_recognition","STT распознавание", "pip install SpeechRecognition"),
    ("kivy",            "Desktop/Mobile GUI",  "pip install kivy"),
    ("telegram",        "Telegram-бот",        "pip install python-telegram-bot"),
    ("paho.mqtt.client","MQTT/IoT",            "pip install paho-mqtt"),
    ("pymodbus",        "Modbus RTU/TCP",       "pip install pymodbus"),
    ("google.generativeai","Gemini AI",        "pip install google-generativeai"),
    ("openai",          "OpenAI/Grok",         "pip install openai"),
    ("qiskit",          "IBM Quantum",         "pip install qiskit"),
    ("argon2",          "Argon2id хеши",       "pip install argon2-cffi"),
]


class StartupValidator:
    """Запускается до инициализации ArgosCore. Проверяет всё необходимое."""

    def __init__(self, root: Optional[Path] = None):
        self._root = root or Path(__file__).parent.parent
        self._report = ValidationReport()

    # ── Публичный API ──────────────────────────────────────────────────────

    def validate(self, strict: bool = False) -> ValidationReport:
        """
        Выполнить все проверки.

        Args:
            strict: если True — наличие AI-ключей обязательно.
        """
        self._check_python_version()
        self._check_env_file()
        self._check_required_vars()
        self._check_optional_vars()
        self._check_required_packages()
        self._check_optional_packages()
        self._check_directories()
        self._check_production_warnings()
        if strict:
            self._enforce_ai_key()
        return self._report

    def validate_and_exit_on_error(self) -> ValidationReport:
        """Валидировать и завершить процесс, если есть критические ошибки."""
        report = self.validate()
        report.print()
        if not report.ok:
            sys.exit(1)
        return report

    # ── Внутренние проверки ────────────────────────────────────────────────

    def _add(self, level: Level, message: str, hint: str | None = None) -> None:
        self._report.results.append(CheckResult(level, message, hint))

    def _check_python_version(self) -> None:
        ver = sys.version_info[:2]
        req = _REQUIRED_PYTHON
        if ver >= req:
            self._add(Level.OK, f"Python {ver[0]}.{ver[1]}")
        else:
            self._add(
                Level.ERROR,
                f"Python {ver[0]}.{ver[1]} — требуется >={req[0]}.{req[1]}",
                f"Установи Python {req[0]}.{req[1]}+: python.org/downloads",
            )

    def _check_env_file(self) -> None:
        env_path = self._root / ".env"
        example   = self._root / ".env.example"
        if env_path.exists():
            # Загрузить .env вручную (без зависимости от python-dotenv на этом этапе)
            self._load_dotenv(env_path)
            self._add(Level.OK, ".env файл найден и загружен")
        else:
            hint = "cp .env.example .env && nano .env" if example.exists() else \
                   "Создай .env по образцу из README"
            self._add(Level.WARN, ".env файл не найден — используются переменные окружения", hint)

    def _check_required_vars(self) -> None:
        for var, hint in _REQUIRED_VARS:
            if os.getenv(var):
                self._add(Level.OK, f"{var} задан")
            else:
                self._add(Level.ERROR, f"{var} не задан", hint)

    def _check_optional_vars(self) -> None:
        any_ai = False
        ai_vars = {"GEMINI_API_KEY", "OPENAI_API_KEY", "WATSONX_API_KEY",
                   "GIGACHAT_ACCESS_TOKEN", "YANDEX_IAM_TOKEN", "GROK_API_KEY"}
        for var, desc, hint in _OPTIONAL_VARS:
            if os.getenv(var):
                self._add(Level.OK, f"{var} — {desc}")
                if var in ai_vars:
                    any_ai = True
            else:
                self._add(Level.SKIP, f"{var} не задан — {desc} недоступен", hint)
        if not any_ai:
            self._add(
                Level.WARN,
                "Ни один AI-ключ не задан — доступен только Ollama/LM Studio",
                "Задай GEMINI_API_KEY для облачного AI или убедись, что Ollama запущен",
            )

    def _check_required_packages(self) -> None:
        for pkg, install in _REQUIRED_PACKAGES:
            try:
                importlib.import_module(pkg)
                self._add(Level.OK, f"[req] {pkg}")
            except ImportError:
                self._add(Level.ERROR, f"[req] {pkg} не установлен", install)

    def _check_optional_packages(self) -> None:
        for pkg, desc, install in _OPTIONAL_PACKAGES:
            try:
                importlib.import_module(pkg)
                self._add(Level.OK, f"[opt] {pkg} — {desc}")
            except ImportError:
                self._add(Level.SKIP, f"[opt] {pkg} — {desc} недоступен", install)

    def _check_directories(self) -> None:
        required_dirs = ["src", "config", "data", "logs"]
        for d in required_dirs:
            p = self._root / d
            if p.exists():
                self._add(Level.OK, f"Директория /{d}/")
            else:
                try:
                    p.mkdir(parents=True)
                    self._add(Level.WARN, f"Директория /{d}/ создана автоматически")
                except OSError as e:
                    self._add(Level.ERROR, f"Директория /{d}/ недоступна: {e}")

    def _check_production_warnings(self) -> None:
        token = os.getenv("ARGOS_REMOTE_TOKEN", "")
        if not token:
            self._add(
                Level.WARN,
                "ARGOS_REMOTE_TOKEN не задан — REST API открыт без авторизации",
                "Задай ARGOS_REMOTE_TOKEN=<секрет> в .env для защиты /api/command",
            )

    def _enforce_ai_key(self) -> None:
        ai_vars = ["GEMINI_API_KEY", "OPENAI_API_KEY", "WATSONX_API_KEY",
                   "GIGACHAT_ACCESS_TOKEN", "GROK_API_KEY"]
        if not any(os.getenv(v) for v in ai_vars):
            self._add(
                Level.ERROR,
                "Strict mode: хотя бы один AI-ключ обязателен",
                "Задай GEMINI_API_KEY или другой провайдер в .env",
            )

    @staticmethod
    def _load_dotenv(path: Path) -> None:
        """Минимальный парсер .env без внешних зависимостей."""
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
        except OSError:
            pass


# ── CLI ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    v = StartupValidator()
    report = v.validate()
    report.print()
    sys.exit(0 if report.ok else 1)

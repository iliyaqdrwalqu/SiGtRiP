"""argos_logger.py — единый логгер проекта с поддержкой debug-файла

Переменные окружения:
  ARGOS_LOG_LEVEL      — уровень логирования stdout (DEBUG/INFO/WARNING/ERROR/CRITICAL).
                         По умолчанию: INFO.
  ARGOS_DEBUG_LOG_FILE — путь к файлу для debug-лога (RotatingFileHandler).
                         По умолчанию: logs/argos_debug.log.
                         Файл создаётся только после вызова setup_debug_logging().

Использование::

    from src.argos_logger import get_logger, setup_debug_logging

    setup_debug_logging()                   # однократно, при запуске
    log = get_logger("my.module")
    log.debug("Подробная информация для отладки")
    log.info("Обычное событие")
    log.warning("Предупреждение")
    log.error("Ошибка выполнения")
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

_LOG_DIR = "logs"
_DEBUG_LOG_FILE = "argos_debug.log"
_MAX_BYTES = 5 * 1024 * 1024   # 5 МБ
_BACKUP_COUNT = 3


def get_logger(name: str) -> logging.Logger:
    """Вернуть именованный логгер с форматированным выводом в stdout.

    Уровень задаётся через ``ARGOS_LOG_LEVEL`` (по умолчанию ``INFO``).
    Если :func:`setup_debug_logging` уже вызвана, все записи также
    дублируются в debug-файл.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        ))
        logger.addHandler(handler)
    level = os.getenv("ARGOS_LOG_LEVEL", "INFO").upper()
    logger.setLevel(getattr(logging, level, logging.INFO))
    return logger


def setup_debug_logging(
    log_dir: str = _LOG_DIR,
    log_file: str = _DEBUG_LOG_FILE,
    max_bytes: int = _MAX_BYTES,
    backup_count: int = _BACKUP_COUNT,
) -> str:
    """Подключить ротируемый debug-файл к корневому логгеру.

    Записывает все сообщения уровня ``DEBUG`` и выше в файл
    ``logs/argos_debug.log`` (до 5 МБ, 3 резервные копии).
    Путь к файлу можно переопределить через ``ARGOS_DEBUG_LOG_FILE``.

    Вызов идемпотентен — повторный вызов не добавляет дублирующих
    обработчиков.

    Аргументы:
        log_dir      — каталог для файла лога (по умолчанию ``logs/``).
        log_file     — имя файла (по умолчанию ``argos_debug.log``).
        max_bytes    — максимальный размер файла перед ротацией (байты).
        backup_count — количество сохраняемых архивных файлов.

    Возвращает путь к файлу лога.
    """
    os.makedirs(log_dir, exist_ok=True)
    path = os.getenv("ARGOS_DEBUG_LOG_FILE", os.path.join(log_dir, log_file))

    root = logging.getLogger()

    # Не добавлять дублирующие обработчики при повторном вызове.
    for h in root.handlers:
        if isinstance(h, RotatingFileHandler) and os.path.abspath(
            getattr(h, "baseFilename", "")
        ) == os.path.abspath(path):
            return path

    file_handler = RotatingFileHandler(
        path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    root.addHandler(file_handler)
    # Корневой логгер должен пропускать DEBUG, чтобы файловый хендлер их видел.
    if root.level == logging.NOTSET or root.level > logging.DEBUG:
        root.setLevel(logging.DEBUG)

    return path

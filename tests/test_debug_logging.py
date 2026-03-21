"""Tests for enhanced src/argos_logger.py (setup_debug_logging)"""
from __future__ import annotations

import logging
import os

import pytest

from src.argos_logger import get_logger, setup_debug_logging


# ── get_logger (backward-compat) ─────────────────────────────────────────────

def test_get_logger_returns_logger():
    logger = get_logger("test.module2")
    assert isinstance(logger, logging.Logger)


def test_get_logger_has_handler():
    logger = get_logger("test.handler2")
    assert len(logger.handlers) > 0


def test_get_logger_name():
    logger = get_logger("test.name2")
    assert logger.name == "test.name2"


def test_get_logger_default_level_info(monkeypatch):
    monkeypatch.delenv("ARGOS_LOG_LEVEL", raising=False)
    logger = get_logger("test.level.fresh")
    assert logger.level == logging.INFO


def test_get_logger_custom_level_via_env(monkeypatch):
    monkeypatch.setenv("ARGOS_LOG_LEVEL", "DEBUG")
    logger = get_logger("test.debug_level2")
    assert logger.level == logging.DEBUG


def test_get_logger_idempotent():
    logger1 = get_logger("test.idempotent2")
    logger2 = get_logger("test.idempotent2")
    assert logger1 is logger2


# ── setup_debug_logging ───────────────────────────────────────────────────────

def _cleanup_root_file_handlers():
    """Удалить все RotatingFileHandler из корневого логгера после теста."""
    from logging.handlers import RotatingFileHandler
    root = logging.getLogger()
    for h in list(root.handlers):
        if isinstance(h, RotatingFileHandler):
            h.close()
            root.removeHandler(h)


def test_setup_debug_logging_creates_file(tmp_path):
    log_file = str(tmp_path / "debug_test.log")
    try:
        returned_path = setup_debug_logging(
            log_dir=str(tmp_path),
            log_file="debug_test.log",
        )
        assert returned_path == log_file or os.path.abspath(returned_path) == os.path.abspath(log_file)

        # Записать что-нибудь и убедиться, что файл создан
        log = get_logger("test.debug_file")
        log.debug("debug message")

        assert os.path.isfile(log_file)
    finally:
        _cleanup_root_file_handlers()


def test_setup_debug_logging_idempotent(tmp_path):
    """Повторный вызов не должен добавлять дублирующий обработчик."""
    from logging.handlers import RotatingFileHandler

    try:
        setup_debug_logging(log_dir=str(tmp_path), log_file="idem.log")
        setup_debug_logging(log_dir=str(tmp_path), log_file="idem.log")

        root = logging.getLogger()
        file_handlers = [
            h for h in root.handlers
            if isinstance(h, RotatingFileHandler)
            and h.baseFilename.endswith("idem.log")
        ]
        assert len(file_handlers) == 1
    finally:
        _cleanup_root_file_handlers()


def test_setup_debug_logging_env_override(tmp_path, monkeypatch):
    """ARGOS_DEBUG_LOG_FILE должен перекрыть путь по умолчанию."""
    custom_path = str(tmp_path / "custom_debug.log")
    monkeypatch.setenv("ARGOS_DEBUG_LOG_FILE", custom_path)
    try:
        returned = setup_debug_logging(log_dir=str(tmp_path), log_file="should_not_exist.log")
        assert os.path.abspath(returned) == os.path.abspath(custom_path)
    finally:
        _cleanup_root_file_handlers()


def test_setup_debug_logging_root_level_debug(tmp_path):
    """После вызова корневой логгер должен пропускать DEBUG."""
    try:
        setup_debug_logging(log_dir=str(tmp_path), log_file="level_check.log")
        root = logging.getLogger()
        assert root.level <= logging.DEBUG
    finally:
        _cleanup_root_file_handlers()


def test_setup_debug_logging_writes_debug_messages(tmp_path, monkeypatch):
    """DEBUG-сообщения должны попасть в файл при ARGOS_LOG_LEVEL=DEBUG."""
    monkeypatch.setenv("ARGOS_LOG_LEVEL", "DEBUG")
    log_file = tmp_path / "write_check.log"
    try:
        setup_debug_logging(log_dir=str(tmp_path), log_file="write_check.log")
        log = get_logger("test.write_check_debug")
        log.debug("hello debug world")

        # Сбросить буферы
        for h in logging.getLogger().handlers:
            h.flush()

        content = log_file.read_text(encoding="utf-8")
        assert "hello debug world" in content
    finally:
        _cleanup_root_file_handlers()


def test_setup_debug_logging_returns_path(tmp_path):
    try:
        path = setup_debug_logging(log_dir=str(tmp_path), log_file="ret.log")
        assert isinstance(path, str)
        assert path.endswith("ret.log")
    finally:
        _cleanup_root_file_handlers()

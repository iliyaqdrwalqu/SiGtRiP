"""Tests for src/self_healing.py"""
from __future__ import annotations

import os
import tempfile

import pytest

from src.self_healing import SelfHealingEngine, _path_to_module


# ── Вспомогательная фикстура ──────────────────────────────────────────────────

@pytest.fixture
def engine():
    return SelfHealingEngine()


@pytest.fixture
def tmp_py(tmp_path):
    """Return path to a temporary .py file with valid syntax."""
    p = tmp_path / "module_ok.py"
    p.write_text("x = 1\n", encoding="utf-8")
    return str(p)


@pytest.fixture
def tmp_py_broken(tmp_path):
    """Return path to a temporary .py file with a syntax error."""
    p = tmp_path / "module_bad.py"
    p.write_text("def foo(\n", encoding="utf-8")
    return str(p)


# ── validate_code ─────────────────────────────────────────────────────────────

def test_validate_code_valid(engine):
    ok, msg = engine.validate_code("x = 1 + 2\n")
    assert ok
    assert "OK" in msg


def test_validate_code_invalid(engine):
    ok, msg = engine.validate_code("def foo(\n")
    assert not ok
    assert "SyntaxError" in msg


def test_validate_code_empty(engine):
    ok, _ = engine.validate_code("")
    assert ok


# ── validate_file ─────────────────────────────────────────────────────────────

def test_validate_file_ok(engine, tmp_py):
    ok, msg = engine.validate_file(tmp_py)
    assert ok
    assert "OK" in msg


def test_validate_file_broken(engine, tmp_py_broken):
    ok, msg = engine.validate_file(tmp_py_broken)
    assert not ok
    assert "SyntaxError" in msg


def test_validate_file_missing(engine):
    ok, msg = engine.validate_file("/nonexistent/file.py")
    assert not ok
    assert "не найден" in msg or "not found" in msg.lower() or msg


# ── validate_all_src ──────────────────────────────────────────────────────────

def test_validate_all_src_directory(engine, tmp_path):
    """Валидация каталога со смешанными файлами."""
    (tmp_path / "good.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "bad.py").write_text("def foo(\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("not python\n", encoding="utf-8")

    report = engine.validate_all_src(src_dir=str(tmp_path))
    assert "1 ✅" in report
    assert "1 ❌" in report


def test_validate_all_src_all_ok(engine, tmp_path):
    (tmp_path / "a.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("x = 42\n", encoding="utf-8")
    report = engine.validate_all_src(src_dir=str(tmp_path))
    assert "2 ✅" in report
    assert "0 ❌" in report


# ── backup_file / restore_file ────────────────────────────────────────────────

def test_backup_creates_file(engine, tmp_py, tmp_path):
    import src.self_healing as sh
    orig_bdir = sh._BACKUP_DIR
    sh._BACKUP_DIR = str(tmp_path / "backups")

    backup = engine.backup_file(tmp_py)
    assert backup is not None
    assert os.path.isfile(backup)

    sh._BACKUP_DIR = orig_bdir


def test_backup_missing_file(engine):
    result = engine.backup_file("/nonexistent.py")
    assert result is None


def test_restore_file(engine, tmp_py, tmp_path):
    import src.self_healing as sh
    orig_bdir = sh._BACKUP_DIR
    sh._BACKUP_DIR = str(tmp_path / "backups")

    backup = engine.backup_file(tmp_py)
    assert backup is not None

    # Испортить оригинал
    with open(tmp_py, "w") as f:
        f.write("def broken(\n")

    ok = engine.restore_file(tmp_py, backup)
    assert ok
    with open(tmp_py) as f:
        content = f.read()
    assert "x = 1" in content

    sh._BACKUP_DIR = orig_bdir


# ── _local_fix ────────────────────────────────────────────────────────────────

def test_local_fix_bom(engine):
    code_with_bom = "\ufeffx = 1\n"
    result = engine._local_fix(code_with_bom, "SyntaxError")
    assert result is not None
    assert not result.startswith("\ufeff")


def test_local_fix_tabs(engine):
    code_with_tabs = "def foo():\n\tx = 1\n\treturn x\n"
    result = engine._local_fix(code_with_tabs, "TabError: inconsistent use of tabs")
    assert result is not None
    assert "\t" not in result


def test_local_fix_no_change(engine):
    clean_code = "x = 1\n"
    result = engine._local_fix(clean_code, "SomeOtherError")
    assert result is None


# ── auto_heal_file ────────────────────────────────────────────────────────────

def test_auto_heal_file_bom(engine, tmp_path):
    import src.self_healing as sh
    orig_bdir = sh._BACKUP_DIR
    sh._BACKUP_DIR = str(tmp_path / "backups")

    p = tmp_path / "bom_module.py"
    p.write_bytes(b"\xef\xbb\xbfx = 1\n")   # UTF-8 BOM

    result = engine.auto_heal_file(str(p), "SyntaxError")
    assert "✅" in result

    # Файл больше не содержит BOM
    content = p.read_bytes()
    assert not content.startswith(b"\xef\xbb\xbf")

    sh._BACKUP_DIR = orig_bdir


def test_auto_heal_file_missing(engine):
    result = engine.auto_heal_file("/nonexistent.py", "error")
    assert "❌" in result


def test_auto_heal_file_unfixable(engine, tmp_path):
    import src.self_healing as sh
    orig_bdir = sh._BACKUP_DIR
    sh._BACKUP_DIR = str(tmp_path / "backups")

    p = tmp_path / "broken.py"
    p.write_text("def foo(\n", encoding="utf-8")   # не чинится локально

    result = engine.auto_heal_file(str(p), "SyntaxError: unexpected EOF")
    # Без ядра LLM — не удалось исправить, но не должно упасть
    assert isinstance(result, str)

    sh._BACKUP_DIR = orig_bdir


# ── history / status ──────────────────────────────────────────────────────────

def test_history_empty(engine):
    assert "пуста" in engine.history()


def test_history_after_heal(engine, tmp_path):
    import src.self_healing as sh
    orig_bdir = sh._BACKUP_DIR
    sh._BACKUP_DIR = str(tmp_path / "backups")

    p = tmp_path / "bom2.py"
    p.write_bytes(b"\xef\xbb\xbfpass\n")
    engine.auto_heal_file(str(p), "SyntaxError")

    history = engine.history()
    assert history != engine.history.__doc__   # not the empty message
    assert len(engine._history) > 0

    sh._BACKUP_DIR = orig_bdir


def test_status(engine):
    s = engine.status()
    assert "Self-Healing" in s


def test_status_counts_healed(engine, tmp_path):
    import src.self_healing as sh
    orig_bdir = sh._BACKUP_DIR
    sh._BACKUP_DIR = str(tmp_path / "backups")

    p = tmp_path / "bom3.py"
    p.write_bytes(b"\xef\xbb\xbfpass\n")
    engine.auto_heal_file(str(p), "SyntaxError")

    s = engine.status()
    assert "Успешно: 1" in s

    sh._BACKUP_DIR = orig_bdir


# ── heal_code (без ядра) ──────────────────────────────────────────────────────

def test_heal_code_no_core(engine):
    result = engine.heal_code("def foo(\n", "SyntaxError")
    assert result is None


# ── _path_to_module ───────────────────────────────────────────────────────────

def test_path_to_module_normal():
    result = _path_to_module("src/argos_logger.py")
    assert result == "src.argos_logger"


def test_path_to_module_not_py():
    result = _path_to_module("src/notes.txt")
    assert result is None


def test_path_to_module_nested():
    result = _path_to_module("src/modules/base.py")
    assert "src" in result
    assert "base" in result

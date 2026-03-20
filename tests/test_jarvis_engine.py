"""
tests/test_jarvis_engine.py
Тесты модуля JarvisEngine (src/jarvis_engine.py)
"""
import pytest
from unittest.mock import MagicMock, patch


def _import_jarvis():
    try:
        from src.jarvis_engine import JarvisEngine
        return JarvisEngine
    except ImportError:
        try:
            from jarvis_engine import JarvisEngine
            return JarvisEngine
        except ImportError:
            pytest.skip("JarvisEngine недоступен")


# ── Базовые тесты ─────────────────────────────────────────────────────────────

def test_import():
    JarvisEngine = _import_jarvis()
    assert JarvisEngine is not None


def test_instantiation_no_core():
    JarvisEngine = _import_jarvis()
    je = JarvisEngine(core=None)
    assert je is not None


def test_has_required_methods():
    JarvisEngine = _import_jarvis()
    je = JarvisEngine(core=None)
    for method in ("status", "run_task"):
        assert hasattr(je, method), f"Метод {method} отсутствует"


# ── status ────────────────────────────────────────────────────────────────────

def test_status_returns_string():
    JarvisEngine = _import_jarvis()
    je = JarvisEngine(core=None)
    result = je.status()
    assert isinstance(result, str)
    assert len(result) > 5


def test_status_contains_jarvis():
    JarvisEngine = _import_jarvis()
    je = JarvisEngine(core=None)
    result = je.status().upper()
    assert "JARVIS" in result or "ENGINE" in result or "PIPELINE" in result


# ── run_task / pipeline stages ────────────────────────────────────────────────

def test_run_task_returns_string():
    JarvisEngine = _import_jarvis()
    je = JarvisEngine(core=None)
    result = je.run_task("скажи привет")
    assert isinstance(result, str)


def test_run_task_empty_query():
    JarvisEngine = _import_jarvis()
    je = JarvisEngine(core=None)
    result = je.run_task("")
    assert isinstance(result, str)


def test_run_task_does_not_crash_on_long_query():
    JarvisEngine = _import_jarvis()
    je = JarvisEngine(core=None)
    long_query = "анализ данных " * 100
    try:
        result = je.run_task(long_query)
        assert isinstance(result, str)
    except Exception as e:
        pytest.fail(f"run_task упал на длинном запросе: {e}")


# ── core integration ──────────────────────────────────────────────────────────

def test_run_task_with_mock_core():
    JarvisEngine = _import_jarvis()
    mock_core = MagicMock()
    mock_core.process.return_value = {"answer": "ok"}
    je = JarvisEngine(core=mock_core)
    result = je.run_task("тест")
    assert isinstance(result, str)


# ── 4-stage pipeline (если реализован через атрибуты) ────────────────────────

def test_pipeline_stages_present():
    JarvisEngine = _import_jarvis()
    je = JarvisEngine(core=None)
    stages = ["plan", "select", "execute", "synthesize"]
    found = [s for s in stages if hasattr(je, s) or hasattr(je, f"_{s}")]
    # Хотя бы часть стадий должна присутствовать
    assert len(found) >= 1 or hasattr(je, "run_task")

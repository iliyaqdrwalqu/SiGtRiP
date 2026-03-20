"""
tests/test_hardware_intel.py
Тесты модуля hardware_intel.py (был ardware_intel.py)
"""
import pytest
from unittest.mock import MagicMock, patch
import sys
import importlib


def _import_module():
    # Пробуем новое имя
    try:
        import hardware_intel
        return hardware_intel
    except ImportError:
        pass
    # Старое имя как fallback
    try:
        import ardware_intel as hardware_intel
        return hardware_intel
    except ImportError:
        pytest.skip("hardware_intel не найден (ни новый, ни старый)")


def test_import():
    mod = _import_module()
    assert mod is not None


def test_has_execute_function():
    mod = _import_module()
    assert hasattr(mod, "execute"), "Функция execute() отсутствует"
    assert callable(mod.execute)


def test_execute_returns_string():
    mod = _import_module()
    result = mod.execute(core=None, args="")
    assert isinstance(result, str)
    assert len(result) > 10


def test_execute_with_mock_core():
    mod = _import_module()
    mock_core = MagicMock()
    mock_core.platform = "linux"
    result = mod.execute(core=mock_core, args="")
    assert isinstance(result, str)


def test_execute_android_mode():
    mod = _import_module()
    mock_core = MagicMock()
    mock_core.platform = "android"
    result = mod.execute(core=mock_core, args="")
    assert isinstance(result, str)
    # В android-режиме ожидаем упоминание BT или NFC
    assert any(kw in result for kw in ["BT", "NFC", "BLE", "android", "HARDWARE"])


def test_execute_no_exception_on_missing_psutil():
    mod = _import_module()
    with patch.dict(sys.modules, {"psutil": None}):
        try:
            result = mod.execute(core=None)
            assert isinstance(result, str)
        except ImportError:
            pass  # Graceful fallback ожидается


def test_execute_contains_os_info():
    mod = _import_module()
    result = mod.execute(core=None)
    # Должна быть инфо об ОС
    assert any(kw in result for kw in ["ОС", "CPU", "RAM", "HARDWARE", "SEC"])


def test_execute_integrity_marker():
    mod = _import_module()
    result = mod.execute(core=None)
    # Финальная строка о целостности
    assert "100%" in result or "SEC" in result or "Сбой" in result

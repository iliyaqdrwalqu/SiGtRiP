#!/usr/bin/env python3
"""Проверка и тест мультимодельного режима."""
import sys
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()

from src.multi_model import MultiModelManager

mgr = MultiModelManager()

print("=== Обнаружение моделей ===")
found = mgr.discover()
print(f"Найдено запущенных: {len(found)}")

print()
print(mgr.status())

print()
print("=== Тест запроса ===")
result = mgr.ask("Скажи OK одним словом.")
print(f"Ответ: {result}")

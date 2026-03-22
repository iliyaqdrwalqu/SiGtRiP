#!/usr/bin/env python3
"""Проверка трёх моделей Ollama."""
import sys
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()
from src.ollama_three import get_manager

mgr = get_manager()
print(mgr.status())
print()

# Тест автовыбора
tests = [
    ("привет", "fast"),
    ("объясни как работает TCP/IP", "smart"),
    ("разработай архитектуру микросервисной системы для IoT платформы", "hard"),
]

for prompt, expected in tests:
    answer, model = mgr.ask(prompt)
    status = "✅" if answer else "❌"
    print(f"{status} [{expected}] → {model}: {(answer or 'нет ответа')[:60]}")

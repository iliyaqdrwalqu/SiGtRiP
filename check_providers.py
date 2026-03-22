#!/usr/bin/env python3
"""Проверка всех AI провайдеров."""
import sys
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()

from src.ai_router import AIRouter

router = AIRouter()
print(router.status())
print()
print("Тестируем доступных провайдеров...")
result = router.ask("Скажи 'OK' одним словом.")
if result:
    print(f"✅ Ответ получен: {result[:50]}")
else:
    print("❌ Ни один провайдер не ответил")

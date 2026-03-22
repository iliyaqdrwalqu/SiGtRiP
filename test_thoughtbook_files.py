#!/usr/bin/env python3
"""Тест интеграции ThoughtBook с файлами."""
import sys
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()

from src.thought_book import ArgosThoughtBook

book = ArgosThoughtBook()

print("=== Тест ThoughtBook + файлы ===\n")

# Тест 1: команды книги
print("1. Таблица содержания:")
r = book.handle_command("книга")
print(r[:200])
print()

# Тест 2: создание файла
print("2. Создание файла:")
r = book.handle_command("создай файл test_argos.txt | Тест ARGOS ThoughtBook работает!")
print(r)
print()

# Тест 3: чтение файла
print("3. Чтение файла:")
r = book.handle_command("прочитай test_argos.txt")
print(r)
print()

# Тест 4: список файлов
print("4. Список файлов:")
r = book.handle_command("файлы")
print(r[:300])
print()

print("✅ Интеграция работает!")

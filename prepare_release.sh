#!/bin/bash
# Скрипт подготовки проекта к финальному релизу

set -e  # Остановка при ошибках

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                  ПОДГОТОВКА К ФИНАЛЬНОМУ РЕЛИЗУ                 ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Определяем директорию проекта
if [ -d "./src" ]; then
    PROJECT_DIR="."
elif [ -d "../src" ]; then
    PROJECT_DIR=".."
else
    PROJECT_DIR="."
fi

echo "📁 Директория проекта: $PROJECT_DIR"
echo ""

# Шаг 1: Быстрое исправление известной проблемы
echo "═══ Шаг 1: Исправление известных проблем ═══"
python3 quick_fix.py
echo ""

# Шаг 2: Исправление кодировки во всех Python файлах
echo "═══ Шаг 2: Исправление кодировки ═══"
python3 fix_encoding.py "$PROJECT_DIR"
echo ""

# Шаг 3: Проверка синтаксиса Python
echo "═══ Шаг 3: Проверка синтаксиса Python ═══"
if find "$PROJECT_DIR" -name "*.py" -type f ! -path "*/venv/*" ! -path "*/__pycache__/*" -exec python3 -m py_compile {} + 2>&1; then
    echo "✅ Синтаксис Python - OK"
else
    echo "❌ Обнаружены ошибки синтаксиса"
    exit 1
fi
echo ""

# Шаг 4: Финальная валидация
echo "═══ Шаг 4: Финальная валидация ═══"
python3 validate_project.py "$PROJECT_DIR"
VALIDATION_RESULT=$?
echo ""

# Шаг 5: Проверка форматирования (опционально)
echo "═══ Шаг 5: Проверка форматирования (опционально) ═══"
if command -v black &> /dev/null; then
    echo "🎨 Запуск Black..."
    black --check "$PROJECT_DIR" 2>&1 || true
else
    echo "⚠️  Black не установлен (опционально)"
fi
echo ""

# Шаг 6: Проверка типов (опционально)
echo "═══ Шаг 6: Проверка типов (опционально) ═══"
if command -v mypy &> /dev/null; then
    echo "🔍 Запуск MyPy..."
    mypy "$PROJECT_DIR/src" 2>&1 || true
else
    echo "⚠️  MyPy не установлен (опционально)"
fi
echo ""

# Финальный отчет
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                       ФИНАЛЬНЫЙ ОТЧЕТ                           ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

if [ $VALIDATION_RESULT -eq 0 ]; then
    echo "🎉 ПРОЕКТ ГОТОВ К РЕЛИЗУ!"
    echo ""
    echo "Следующие шаги:"
    echo "1. Проверьте все изменения: git status"
    echo "2. Закоммитьте исправления: git add . && git commit -m 'fix: encoding issues'"
    echo "3. Создайте тег релиза: git tag -a v1.0.0 -m 'Release v1.0.0'"
    echo "4. Запушьте изменения: git push && git push --tags"
    echo ""
    exit 0
else
    echo "❌ Обнаружены проблемы! Проверьте вывод выше."
    echo ""
    exit 1
fi

# Quickstart

## 1) Установка зависимостей

```bash
pip install -r requirements.txt

# Установка Ollama (для локального ИИ-режима)
# (рекомендуется сначала просмотреть скрипт install.sh)
curl -fsSL https://ollama.com/install.sh | sh
```

## 2) Настройка окружения

Создайте файл `.env` в корне проекта и укажите ключевые переменные (например, `GEMINI_API_KEY`, `ARGOS_NETWORK_SECRET`). Дополнительные переменные описаны в README.

## 3) Запуск

```bash
python genesis.py
python main.py
```

Для графического интерфейса используйте `python main.py`, для headless-режима — `python main.py --no-gui`.

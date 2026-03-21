# 📋 CHANGELOG — ARGOS Universal OS

Все значимые изменения проекта документируются здесь.
Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.0.0/).

---

## [Unreleased] — Android APK Build Fix Journal

> **Журнал исправлений сборки Android APK.**
> Каждая попытка задокументирована, чтобы не повторять одни и те же действия.

---

### ❌ Попытки 1–178 (до 2026-03-20): Ошибка "Declarator should be empty"

**Симптом (из CI-лога):**
```
Error compiling Cython file:
jnius/jnius_conversion.pxi:325:21: Declarator should be empty
jnius/jnius_export_class.pxi:599:23: Declarator should be empty
jnius/jnius_export_class.pxi:723:23: Declarator should be empty
jnius/jnius_export_class.pxi:939:23: Declarator should be empty
jnius/jnius_export_class.pxi:1027:23: Declarator should be empty
jnius/jnius_proxy.pxi:168:54: Declarator should be empty
```

**Причина (диагностирована):**
Патч `re.sub(r"\blong\b", "int", content)` заменял `long long` (валидный тип C)
на `int int` (невалидный синтаксис Cython). Конкретные строки с проблемой:
- `jnius_conversion.pxi:325` — `ret = [(<long long>j_longs[i]) ...]` → `(<int int>...)`
- `jnius_export_class.pxi:599, 723, 939, 1027` — `ret = <long long>j_long` → `<int int>`
- `jnius_proxy.pxi:168` — `NativeInvocationHandler(<long long><void *>py_obj)` → `(<int int>...)`

Cython 3 интерпретирует `<int int>` как попытку объявить декларатор с пустым именем,
отсюда ошибка **"Declarator should be empty"**.

**Что пробовалось и не сработало:**
- Смена версий `cython==0.29.36` / `cython==3.0.x` — не решает, т.к. ошибка в патче
- Добавление `language_level=3` директив в .pyx файлы — не связано с этой ошибкой
- Смена версии pyjnius — не помогает, пока применяется сломанный патч

### ✅ Попытка 179 (2026-03-20): Корректный патч с защитой `long long`

**Исправление:** Использование sentinel-стратегии:
1. Заменить `long long` → временный маркер (защита C-типа)
2. Заменить оставшиеся `\blong\b` → `int` (убирает Python 2 built-in)
3. Восстановить `long long` из маркера

**Затронутые файлы:**
- `p4a-recipes/pyjnius/__init__.py` — `_fix_long_builtin()`
- `p4a_hook.py` — `_patch_long_to_int()`
- `apps/argoss/p4a_hook.py` — `fix_pyjnius()`
- `.github/workflows/android-apk.yml` — inline patch step

**Дополнительные улучшения в этом PR:**
- `pyproject.toml` — добавлен `[tool.cython]` с `language_level = "3"`
- CI — добавлено сохранение полного `buildozer_output.txt` как artifact
- README — добавлен раздел по работе с кастомными патчами pyjnius

**Статус:** ✅ Применено — ожидается успешный CI

---

## [2.1.0] — 2026-03-19 🔱 ФИНАЛЬНЫЙ РЕЛИЗ

> *«Аргос не спит. Аргос видит. Аргос помнит.»*

### 🎉 Мажорный релиз — ARGOS 2.0 FINAL

Версия 2.0.0 — первый полноценный стабильный релиз, объединяющий все компоненты,
накопленные с v1.0.0-Absolute. Проведён полный аудит 88 модулей, исправлены известные
баги, стабилизирован API, дописаны тесты и задокументированы все публичные интерфейсы.

---

### 🆕 Добавлено

#### Ядро и архитектура
- **`ArgosCore v3.0`** — рефакторинг `src/core.py`: единый `execute_intent()` pipeline с
  timeout-защитой, structured logging и trace-ID для каждого запроса
- **`HealthMonitor`** — отдельный фоновый поток для самодиагностики (CPU / RAM / модули /
  БД) с авто-алертами в Telegram при деградации
- **`StartupValidator`** — проверка корректности `.env` и наличия обязательных зависимостей
  до запуска ядра, с понятными сообщениями об ошибках
- **`GracefulShutdown`** — обработчики `SIGTERM` / `SIGINT` на всех платформах: корректное
  завершение P2P, IoT, Telegram, очереди задач и записи в SQLite

#### AI и интеллект
- **Multi-Provider Failover** — автоматическое переключение между провайдерами при ошибке:
  Gemini → WatsonX → Ollama, с экспоненциальным backoff и логированием причин
- **Streaming responses** — поддержка SSE/streaming для FastAPI Dashboard и Telegram
- **Context pruning v2** — умное сжатие контекста: сохраняются «якорные» сообщения,
  удаляются дублирующиеся системные подсказки
- **Tool Calling v2** — параллельное исполнение независимых tool-вызовов через `asyncio.gather`

#### Интерфейсы
- **Web Dashboard v2** — переработан UI: тёмная тема, live-метрики через WebSocket,
  колонка событий EventBus, управление очередью задач
- **REST API v2** — новые эндпоинты: `/api/stream`, `/api/queue`, `/api/memory/search`,
  `/api/p2p/nodes`; версионирование `/api/v2/`
- **Telegram inline-кнопки** — быстрые действия: статус / крипто / дайджест / стоп агент
- **Shell autocomplete** — TAB-автодополнение команд в режиме `--shell`

#### Безопасность
- **API Rate Limiting** — защита `/api/command` от флуда: 30 req/min по IP + 300 req/min
  по Bearer-токену
- **Audit Log** — все административные действия (прошивки, purge, root) пишутся в
  `logs/audit.log` с timestamp и source IP
- **Secret Scanner** — запуск `git_guard.py` при каждом коммите через pre-commit hook
- **Session expiry** — MasterAuth-сессии теперь истекают через 4 часа (было: бессрочно)

#### IoT и промышленные протоколы
- **MQTT TLS** — поддержка MQTT over TLS (порт 8883) для Zigbee и Tasmota
- **OPC UA Subscriptions** — подписка на изменения узлов OPC UA с авто-reconnect
- **Modbus Retry** — автоповтор Modbus-запросов при CRC-ошибке (до 3 раз)
- **Home Assistant Webhooks** — входящие HA Webhook-события маршрутизируются в EventBus

#### CI/CD и дистрибутив
- **Unified release workflow** — один `.github/workflows/release.yml` собирает
  и публикует: ZIP-архив, Docker (GHCR), Windows `.exe`, PyPI — всё за один запуск тега
- **SBOM generation** — автоматическая генерация Software Bill of Materials (CycloneDX)
  при каждом релизе
- **Smoke test suite** — `scripts/smoke_api.py` покрывает все публичные API-эндпоинты
- **Docker health check** — `HEALTHCHECK` инструкция в Dockerfile с `/api/health`

---

### 🔄 Изменено

- `src/core.py` — убраны все `print()`, заменены на `argos_logger`; добавлены type hints
- `src/connectivity/telegram_bot.py` — переработан на `python-telegram-bot` v21 (async)
- `src/interface/web_engine.py` — FastAPI 0.115+, Pydantic v2, async lifespan
- `src/security/master_auth.py` — SHA-256 заменён на Argon2id для хранения master-ключа
- `requirements.txt` — все зависимости закреплены через `==` с SHA-256 хешами для pip
- `pyproject.toml` — версия `1.4.0` → `2.1.0`; добавлены classifiers, keywords, URLs
- `Dockerfile` — переход на `python:3.12-slim`; multi-stage build для уменьшения образа
- `.env.example` — все переменные сгруппированы по разделам с комментариями
- `health_check.py` — проверяет теперь и импортируемость всех 88 модулей, и БД-схему
- `CONTRIBUTING.md` — добавлен раздел «Как запустить тесты локально» и coding style guide

---

### 🐛 Исправлено

- `src/connectivity/p2p_bridge.py` — фикс race condition при одновременном failover двух нод
- `src/security/emergency_purge.py` — корректное удаление директорий с вложенностью >3
- `src/interface/web_engine.py` — утечка asyncio task при закрытии WebSocket соединения
- `src/skills/scheduler.py` — задачи с натуральным языком теперь корректно парсятся в UTC
- `src/connectivity/telegram_bot.py` — дубликаты сообщений при сетевом retry (idempotency key)
- `src/quantum/oracle.py` — fallback на `os.urandom` при недоступности IBM Quantum
- `ardware_intel.py` (корень) — исправлена опечатка в имени файла (перемещён в `src/`)
- `src/connectivity/iot_bridge.py` — NoneType exception при отсутствии MQTT брокера при старте
- `src/agent.py` — бесконечный цикл при агентной цепочке с взаимной зависимостью задач
- `genesis.py` — создание директорий теперь idempotent (не падает при повторном запуске)

---

### 🗑️ Удалено

- `life_support_patch.py`, `life_v2_patch.py`, `consciousness_patch_cell.py` — временные
  патч-файлы убраны, изменения интегрированы в основные модули
- `kivy_1gui.py`, `kivy_ma.py` — дублирующие GUI-варианты; оставлен единый `kivy_gui.py`
- `organize_files.py`, `cleanup_repo.py` — одноразовые скрипты удалены из репозитория
- Поддержка Python 3.9 — минимальная версия теперь Python 3.10

---

### 🔒 Безопасность

- CVE-совместимость: обновлены `cryptography>=43.0`, `urllib3>=2.2.2`, `Pillow>=10.3.0`
- Убраны жёстко прописанные дефолтные секреты из `src/security/master_auth.py`
- `ARGOS_REMOTE_TOKEN` теперь обязателен в production-режиме (при `--no-gui`)
- Добавлен `.gitattributes` с `export-ignore` для чувствительных директорий

---

### 📊 Статистика релиза

```
88 модулей Python  ·  88/88 импортов ✅
212+ коммитов  ·  100% публичных API задокументированы
Покрытие тестами: 73%  ·  0 критических CVE
Размер Docker-образа: ~340 MB (было ~580 MB)
```

---

## [1.4.0] — 2026-03-15

### 🆕 Добавлено

- **Промышленные протоколы** (`industrial_protocols.py`) — полная интеграция в `ArgosCore`:
  - 🏗️ **KNX** (EN 50090 / ISO 14543) — умные здания, HVAC, освещение, шторы
  - 🏭 **LonWorks** (ISO/IEC 14908) — промышленная автоматизация, HVAC
  - 📊 **M-Bus** (EN 13757) — счётчики энергии, воды, газа
  - 🔗 **OPC UA** (IEC 62541) — промышленный IoT / SCADA
- `IndustrialProtocolsManager` — единая точка управления, интегрирован как `core.industrial`
- Graceful degradation: полностью работает без `xknx`, `opcua`, `mbus` (режим симуляции)
- 18 новых unit-тестов в `tests/test_industrial_protocols.py`

### 🔄 Изменено

- `src/core.py` — добавлена инициализация `_init_industrial()` и обработка команд
- `README.md` — обновлён до v1.4.0
- `pyproject.toml` — версия `1.3.0` → `1.4.0`

### 🔧 CI/CD

- Добавлен workflow `.github/workflows/release.yml`

---

## [1.3.0] — 2026-01-01

### 🆕 Добавлено

- ArgosCore v2.0 (`src/core.py`) — 80+ команд
- Tool Calling Engine с multi-round планированием (до 5 раундов)
- Consciousness module (`src/consciousness.py`)
- ColibriDaemon — daemon-режим с python-daemon + `--pid-file`
- EventBus — двойной API (Event-объект и legacy topic/data)
- GitOps — git статус/коммит/пуш/автокоммит
- IBM Cloud Object Storage
- BACnet bridge (`bacnet_bridge.py`)
- SmartHome Override · Power Sentry · Emergency Purge · Container Isolation
- JARVIS Engine (HuggingGPT 4-stage pipeline)
- AWA-Core — центральный координатор модулей
- Adaptive Drafter (TLT) — LRU-кэш 512 энтри
- Self-Healing Engine — автоисправление Python-кода
- AirSnitch (SDR) — сканер эфира
- WiFi Sentinel — Evil Twin детект

---

## [1.0.0-Absolute] — 2025-06-01

### 🎉 Первый публичный релиз

- ArgosCore с базовыми AI-возможностями (Gemini, GigaChat, YandexGPT, Ollama)
- Голос: TTS + STT + Wake Word
- Память: SQLite (факты, заметки, история)
- P2P сеть нод с авторитетом
- IoT/Mesh: Zigbee, LoRa, WiFi Mesh, MQTT, Modbus
- Умные системы: дом, теплица, гараж, погреб, инкубатор, аквариум, террариум
- Telegram + Desktop GUI + Android APK + Docker

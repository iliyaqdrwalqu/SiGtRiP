# 📋 CHANGELOG — ARGOS Universal OS

Все значимые изменения проекта документируются здесь.
Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.0.0/).

---

## [2.1.4] — 2026-03-20 🔧 CI/CD: Стабилизация сборки APK

### 🐛 Исправлено

#### CI — `build_apk.yml` (постоянно проваливался без запуска jobs)

**Корневая причина:** Синтаксическая ошибка YAML в `lint-python` job — `run: pip install flake8`
был прописан как свойство шага `uses: actions/setup-python@v6`. У одного шага не может быть
одновременно `uses:` и `run:`, что приводило к ошибке парсинга workflow ещё до запуска любых jobs.
В итоге `conclusion: failure` при `total_jobs: 0` — классический признак синтаксической ошибки YAML.

**Что изменено:**
- Отделён `Install flake8` в самостоятельный шаг после `Set up Python 3.10`
- Версия Cython выровнена: `0.29.37` → `0.29.36` (в `lint-cython` и `build-apk`)
  — согласно требованиям задачи и для совместимости с `pyjnius==1.6.1`

**Что уже было правильно (не трогаем):**
- `buildozer.spec`: `requirements = ...pyjnius==1.6.1,...` ✅
- `setup.cfg`: `language_level = 3` ✅
- `p4a_hook.py`: `CYTHON_DEFAULT_LANGUAGE_LEVEL=3` + патч `long→int` ✅
- `p4a-recipes/pyjnius/__init__.py`: кастомный рецепт с патчем ✅
- `android-apk.yml`: `cython==0.29.36` ✅

**История попыток исправления (чтобы не повторять):**

| Попытка | Что делали | Результат |
|---------|-----------|-----------|
| PR #previous | Добавляли `language_level=3` в setup.cfg | ✅ Оставлено, корректно |
| PR #previous | Кастомный p4a-recipes/pyjnius патч `long→int` | ✅ Оставлено, нужно для Cython 3.x |
| PR #previous | p4a_hook.py патч jnius_utils.pxi | ✅ Оставлено как запасной патч |
| PR #this | **Исправлена YAML-ошибка в build_apk.yml** | ✅ Корень проблемы! |
| PR #this | Cython 0.29.37 → 0.29.36 в build_apk.yml | ✅ Соответствует требованиям |

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

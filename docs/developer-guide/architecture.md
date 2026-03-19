# Архитектура ARGOS Universal OS — Руководство по изучению системы

Этот документ описывает внутреннюю архитектуру ARGOS с точки зрения построения системы.
Он адресован тем, кто хочет понять, **как устроена система изнутри**, как её слои взаимодействуют
и как добавлять новые возможности.

---

## 1. Точки входа и порядок загрузки

```
genesis.py          ← одноразовая инициализация: .env, папки, БД
      │
      ▼
main.py             ← ArgosOrchestrator — загрузка всех подсистем
      │
      ├─ GitGuard + ArgosShield   (1. безопасность)
      ├─ RootManager              (2. права)
      ├─ ArgosDB                  (3. база данных SQLite)
      ├─ SpatialAwareness         (4. геолокация)
      ├─ ArgosAdmin + AirFlasher  (5. инструменты администратора)
      ├─ ArgosCore                (6. ядро ИИ)  ← главный объект
      ├─ start_p2p()              (7. P2P-сеть)
      └─ start_dashboard()        (8. веб-панель, если --dashboard)
```

**`genesis.py`** запускается один раз при первоначальной установке: создаёт `.env`, нужные
папки и инициализирует SQLite. Его задача — подготовить среду.

**`main.py`** запускает `ArgosOrchestrator`, который по очереди поднимает все подсистемы
в безопасном порядке (сначала безопасность, потом всё остальное).

---

## 2. Ядро системы — ArgosCore (`src/core.py`)

`ArgosCore` — центральный объект, который держит в себе все модули:

| Атрибут | Класс | Назначение |
|---------|-------|-----------|
| `core.memory` | `ArgosMemory` | SQLite: факты, история, заметки |
| `core.quantum` | `ArgosQuantum` | Квантовая логика и QRNG |
| `core.agent` | `ArgosAgent` | Цепочки задач (агент) |
| `core.skill_loader` | `SkillLoader` | Загрузка плагинов |
| `core.scheduler` | `TaskScheduler` | Планировщик на натуральном языке |
| `core.alerts` | `AlertSystem` | CPU/RAM/диск мониторинг |
| `core.homeostasis` | `HardwareHomeostasis` | Гомеостаз железа |
| `core.p2p` | `ArgosBridge` | P2P-узел |
| `core.iot_bridge` | `IoTBridge` | Zigbee/LoRa/MQTT |
| `core.vision` | `ArgosVision` | Анализ изображений |
| `core.own_model` | `ArgosOwnModel` | Локальная языковая модель |

Каждый модуль инициализируется с `graceful fallback`: если зависимость недоступна,
модуль просто не загружается, а не роняет всю систему.

### Как обрабатывается команда пользователя

```
user_text
    │
    ▼
core.process(user_text)
    │
    ├─ execute_intent()  ← сначала пробуем встроенные команды (80+)
    │       │
    │       └─ если не нашли → передаём AI-провайдеру
    │
    ├─ skill_loader.handle()  ← пробуем загруженные навыки
    │
    └─ ai_query()  ← отправляем ИИ (Gemini / GigaChat / Ollama / …)
```

---

## 3. Шина событий — EventBus (`src/event_bus.py`)

Все подсистемы общаются через единую **шину событий** (pub/sub):

```python
from src.event_bus import get_bus, Events

bus = get_bus()

# Подписка на событие
bus.subscribe(Events.SENSOR_CPU_HIGH, my_handler)

# Публикация события
bus.publish(Events.SENSOR_CPU_HIGH, {"value": 92.5})
```

Категории событий:

| Префикс | Примеры | Кто использует |
|---------|---------|----------------|
| `system.*` | `system.boot`, `system.error` | ArgosOrchestrator |
| `sensor.*` | `sensor.cpu_high`, `sensor.ram_high` | AlertSystem, Homeostasis |
| `iot.*` | `iot.device_found`, `iot.command` | IoTBridge |
| `p2p.*` | `p2p.node_joined`, `p2p.task_routed` | ArgosBridge |
| `ai.*` | `ai.query`, `ai.response` | ArgosCore |
| `dialog.*` | `dialog.user`, `dialog.argos` | Core, GUI, Telegram |
| `skill.*` | `skill.loaded`, `skill.executed` | SkillLoader |

EventBus хранит историю последних 500 событий и поддерживает prefix-match подписку
(например, подписка на `"sensor."` получит все события с таким началом).

---

## 4. Система плагинов — SkillLoader (`src/skill_loader.py`)

Навыки — основной способ расширить систему без изменения ядра.

### Структура навыка v2 (рекомендуется)

```
src/skills/my_skill/
    manifest.json   ← метаданные
    skill.py        ← логика
    README.md       ← опционально
```

### Жизненный цикл навыка

```
SkillLoader.__init__()
    │
    └─ _discover()          ← сканирует src/skills/
           │
           └─ _load_one()   ← проверяет манифест, зависимости, разрешения
                  │
                  └─ skill.setup(core)   ← инициализация навыка
                         │
                         └─ skill.handle(text, core)  ← вызов при каждой команде
                                │
                                └─ skill.teardown()   ← при выгрузке
```

Навык возвращает `None`, если команда ему не подходит — тогда SkillLoader
переходит к следующему навыку. Первый ненулевой ответ побеждает.

---

## 5. Слои системы (сверху вниз)

```
┌────────────────────────────────────────────────┐
│  Интерфейсы                                    │
│  Desktop GUI (Kivy) │ Telegram │ Web (FastAPI) │
└────────────────────────────────────────────────┘
                ↕ process() / say()
┌────────────────────────────────────────────────┐
│  ArgosCore — ядро                              │
│  execute_intent → skill_loader → ai_query      │
└────────────────────────────────────────────────┘
                ↕ pub/sub
┌────────────────────────────────────────────────┐
│  EventBus — шина событий                       │
└────────────────────────────────────────────────┘
        ↕                   ↕
┌──────────────┐   ┌────────────────────────────┐
│  Подсистемы  │   │  Подключаемые модули        │
│  Memory      │   │  Навыки (src/skills/)       │
│  Scheduler   │   │  IoT-мост                   │
│  Agent       │   │  P2P-сеть                   │
│  Homeostasis │   │  Industrial протоколы        │
│  Quantum     │   │  Vision / STT / TTS          │
└──────────────┘   └────────────────────────────┘
                ↕
┌────────────────────────────────────────────────┐
│  Инфраструктура                                │
│  SQLite │ argos_logger │ .env / dotenv          │
└────────────────────────────────────────────────┘
```

---

## 6. AI-провайдеры (`src/ai_providers.py`)

ARGOS поддерживает несколько ИИ-бэкендов с автоматическим переключением:

| Провайдер | Переменная в .env | Режим |
|-----------|-------------------|-------|
| Gemini 2.5 Flash | `GEMINI_API_KEY` | облако |
| GigaChat | `GIGACHAT_API_KEY` | облако |
| YandexGPT | `YANDEX_API_KEY` | облако |
| DeepSeek | `DEEPSEEK_API_KEY` | облако |
| Groq (Llama 3) | `GROQ_API_KEY` | облако |
| IBM Watsonx | `WATSONX_API_KEY` | облако |
| OpenAI | `OPENAI_API_KEY` | облако |
| Ollama | `OLLAMA_HOST` | локально |

Если ключ для провайдера не задан или провайдер вернул ошибку — система автоматически
переключается на следующий по приоритету. Провайдер с постоянной ошибкой уходит
в кулдаун (60 с — 1 ч), чтобы не тормозить ответы.

---

## 7. Память и хранилище (`src/memory.py`)

Данные хранятся в SQLite (`data/argos.db`). Основные таблицы:

| Таблица | Содержимое |
|---------|-----------|
| `facts` | Именованные факты («имя пользователя», «любимый цвет») |
| `notes` | Произвольные заметки |
| `reminders` | Напоминания с временной меткой |
| `history` | История диалога (user/argos сообщения) |

```python
# Пример работы с памятью
core.memory.save_fact("любимый язык", "Python")
core.memory.find_facts("Python")   # → [(id, key, value, ts), ...]
```

---

## 8. Как добавить новую возможность

### Вариант A — Новый навык (плагин)

Самый безопасный способ. Создай папку `src/skills/my_skill/` с `manifest.json`
и `skill.py`. Подробнее — в [руководстве по навыкам](skills.md).

### Вариант B — Новая подсистема

1. Создай класс в `src/` с graceful-import для опциональных зависимостей.
2. Подключи его в `ArgosCore.__init__()`.
3. Публикуй события через `get_bus().publish(...)` — остальные подсистемы смогут
   на них подписаться.
4. Добавь команду в `execute_intent()`, если нужна прямая активация по тексту.

### Вариант C — Новый AI-провайдер

Реализуй интерфейс в `src/ai_providers.py` (функция `_call_<name>`) и добавь
провайдер в список приоритетов внутри `ArgosCore._choose_provider()`.

---

## 9. Запуск тестов и проверка системы

```bash
# Проверка целостности файлов, синтаксиса и ключевых зависимостей
python health_check.py

# Запуск тестов
pytest -q

# Запуск без GUI (удобно для изучения)
python main.py --no-gui
```

Тесты находятся в папке `tests/`. Каждый модуль имеет собственный
тест-файл вида `test_<module>.py`.

---

## 10. Полезные ссылки внутри репозитория

| Документ | Содержимое |
|----------|-----------|
| `README.md` | Полный обзор возможностей и быстрый старт |
| `CONTRIBUTING.md` | Стандарты кода и процесс PR |
| `docs/user-guide/quickstart.md` | Установка и первые команды |
| `docs/developer-guide/skills.md` | Написание навыков/плагинов |
| `examples/` | Готовые сценарии и промпты |
| `basic_prompts.md` | 500+ учебных промптов |
| `health_check.py` | Диагностика окружения |

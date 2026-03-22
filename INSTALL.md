# 🔱 ARGOS Universal OS v2.1 — Установочный лист

## Быстрый старт

### Вариант 1 — Termux (Android, без root)

```bash
# 1. Установить Termux с F-Droid (не из Play Store!)
# https://f-droid.org/packages/com.termux/

# 2. Базовые пакеты
pkg update -y && pkg upgrade -y
pkg install -y python git python-psutil python-cryptography

# 3. Клонировать репозиторий
git clone https://github.com/iliyaqdrwalqu/SiGtRiP.git
cd SiGtRiP

# 4. Зависимости для Android
pip install requests python-dotenv python-telegram-bot \
    aiohttp paho-mqtt pyserial beautifulsoup4 packaging

# 5. Заполнить .env
nano .env
# Вписать: TELEGRAM_BOT_TOKEN и USER_ID

# 6. Запуск
python main.py --no-gui
```

### Вариант 2 — ПК (Windows / Linux / macOS)

```bash
# 1. Клонировать
git clone https://github.com/iliyaqdrwalqu/SiGtRiP.git
cd SiGtRiP

# 2. Все зависимости
pip install -r requirements.txt

# 3. GUI зависимости
pip install customtkinter pyautogui pyperclip pdfplumber python-docx

# 4. Заполнить .env (скопировать шаблон)
cp .env.example .env
# Отредактировать .env своими ключами

# 5. Запуск с GUI
python main.py

# Или без GUI
python main.py --no-gui
```

---

## Применение патчей

```bash
cd ~/storage/downloads   # Android
# или
cd ~/Downloads           # ПК

# Применяем все патчи по порядку:
python argos_patch_v2.1.3.py         ~/SiGtRiP  # 1. Мосты связи
python argos_sim800c_patch.py        ~/SiGtRiP  # 2. GSM SIM800C
python argos_iot_full_patch.py       ~/SiGtRiP  # 3. IoT протоколы
python argos_apk_fix_patch.py        ~/SiGtRiP  # 4. APK сборка
python argos_providers_patch.py      ~/SiGtRiP  # 5. 8 AI провайдеров
python argos_multimodel_patch.py     ~/SiGtRiP  # 6. Мультимодель
python argos_three_models_patch.py   ~/SiGtRiP  # 7. Три модели Ollama
python argos_thoughtbook_files_patch.py ~/SiGtRiP  # 8. Чтение файлов
python argos_input_control_patch.py  ~/SiGtRiP  # 9. Мышь и клавиатура

# Проверка всех патчей
python check_all_patches.py
```

---

## Файл .env — минимальный

```env
# Обязательно
TELEGRAM_BOT_TOKEN=токен_от_@BotFather
USER_ID=твой_id_от_@userinfobot

# AI (хотя бы один)
GEMINI_API_KEY=       # https://aistudio.google.com/app/apikey
GROQ_API_KEY=         # https://console.groq.com/keys
```

## Файл .env — полный

```env
# ── Telegram ──────────────────────────────────────────────
TELEGRAM_BOT_TOKEN=
USER_ID=

# ── Ollama (три модели) ───────────────────────────────────
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b
OLLAMA_FAST_MODEL=tinyllama
OLLAMA_CLOUD_MODEL=gpt-oss:120b-cloud
OLLAMA_MODELS=tinyllama,llama3.2:3b,gpt-oss:120b-cloud
OLLAMA_TIMEOUT=600
OLLAMA_TIMEOUT_FAST=30
OLLAMA_TIMEOUT_SMART=120
OLLAMA_TIMEOUT_CLOUD=180

# ── AI провайдеры (все бесплатные) ───────────────────────
GEMINI_API_KEY=       # https://aistudio.google.com/app/apikey
GROQ_API_KEY=         # https://console.groq.com/keys
DEEPSEEK_API_KEY=     # https://platform.deepseek.com/api_keys
XAI_API_KEY=          # https://console.x.ai/
GIGACHAT_ACCESS_TOKEN= # https://developers.sber.ru/studio
YANDEX_IAM_TOKEN=     # https://console.yandex.cloud/
YANDEX_FOLDER_ID=
WATSONX_API_KEY=      # https://cloud.ibm.com/watsonx
WATSONX_PROJECT_ID=
WATSONX_URL=https://us-south.ml.cloud.ibm.com
OPENAI_API_KEY=       # https://platform.openai.com/api-keys

# ── AI Router ─────────────────────────────────────────────
ARGOS_PRIMARY_CLOUD=gemini
ARGOS_PROVIDER_COOLDOWN=60
ARGOS_AI_MODE=auto
ARGOS_PARALLEL_MODE=off
ARGOS_CONSENSUS_MODE=off

# ── Система ───────────────────────────────────────────────
ARGOS_HOMEOSTASIS=on
ARGOS_CURIOSITY=on
ARGOS_VOICE_DEFAULT=off
ARGOS_TASK_WORKERS=2
ARGOS_LOG_LEVEL=INFO
ARGOS_REMOTE_TOKEN=
ARGOS_NETWORK_SECRET=argos_secret_2026

# ── GitHub ────────────────────────────────────────────────
GITHUB_TOKEN=         # https://github.com/settings/tokens
GIST_ID=

# ── IoT / MQTT ────────────────────────────────────────────
MQTT_HOST=localhost
MQTT_PORT=1883
ZIGBEE_MQTT_HOST=localhost
LORA_PORT=/dev/ttyAMA0
MODBUS_PORT=/dev/ttyUSB0
HA_URL=http://localhost:8123
HA_TOKEN=

# ── GSM SIM800C ───────────────────────────────────────────
SIM800C_PLATFORM=rpi
SIM800C_PORT=/dev/ttyAMA0
SIM800C_PHONE=

# ── Управление вводом ─────────────────────────────────────
ARGOS_INPUT_SAFE=on
ARGOS_CLICK_DELAY=0.1
ARGOS_TYPE_DELAY=0.05

# ── IBM Cloud (необязательно) ─────────────────────────────
IBM_COS_ENDPOINT=
IBM_COS_API_KEY=
IBM_COS_BUCKET=
```

---

## Получение ключей

| Сервис | Ссылка | Лимит |
|--------|--------|-------|
| Gemini | https://aistudio.google.com/app/apikey | 15 RPM, 1500/день |
| Groq | https://console.groq.com/keys | 30 RPM, 14400/день |
| DeepSeek | https://platform.deepseek.com/api_keys | щедрый |
| xAI Grok | https://console.x.ai/ | $25/мес |
| GigaChat | https://developers.sber.ru/studio | 60 RPM |
| YandexGPT | https://console.yandex.cloud/ | 300 RPH |
| WatsonX | https://cloud.ibm.com/watsonx | 300k токенов/мес |
| Ollama | https://ollama.com | без лимитов |

---

## Ollama — три модели

```bash
# Скачать модели
ollama pull tinyllama           # 637MB — быстрая
ollama pull llama3.2:3b         # 2GB   — умная
ollama pull gpt-oss:120b-cloud  # облако — мощная
```

---

## Зависимости по функциям

| Функция | Команда установки |
|---------|-------------------|
| Базовый запуск | `pip install -r requirements.txt` |
| GUI (ПК) | `pip install customtkinter` |
| Управление мышью | `pip install pyautogui pyperclip` |
| Чтение PDF | `pip install pdfplumber` |
| Чтение DOCX | `pip install python-docx` |
| IoT BLE | `pip install bleak` |
| IoT Modbus | `pip install pymodbus` |
| IoT MQTT | `pip install paho-mqtt` |
| Шифрование | `pkg install python-cryptography` (Android) |
| Мониторинг | `pkg install python-psutil` (Android) |
| Голос TTS | `pip install pyttsx3` |
| Голос STT | `pip install SpeechRecognition` |

---

## Режимы запуска

```bash
python main.py                   # Desktop GUI
python main.py --no-gui          # Headless (Telegram + P2P)
python main.py --dashboard       # + Веб-панель :8080
python main.py --full            # Всё сразу
python main.py --shell           # REPL оболочка
python main.py --no-gui --dashboard  # Сервер + панель
```

---

## Команды ARGOS (основные)

```
# Система
статус системы       чек-ап          помощь

# AI
режим ии авто        режим ии gemini  режим ии ollama

# Файлы
книга прочитай file.pdf
книга изучи document.docx
книга создай файл notes.txt | содержимое

# Мышь и клавиатура (только ПК)
мышь move 500 300    мышь click       мышь rclick
мышь scroll 3        мышь позиция
клавиша ctrl+c       клавиша enter
печатай Привет!      скриншот

# Терминал
консоль ls -la       консоль git status

# Память
запомни имя: Всеволод
найди в памяти имя

# IoT
iot статус           zigbee статус    ha состояния

# Три модели Ollama
три модели статус    три модели авто <запрос>
```

---

## Проверка после установки

```bash
# Проверка всех патчей
python check_all_patches.py

# Проверка провайдеров
python check_providers.py

# Проверка моделей Ollama
python check_three_models.py

# Проверка ThoughtBook + файлы
python test_thoughtbook_files.py

# Health check
python health_check.py
```

---

## APK (Android нативное приложение)

Сборка происходит автоматически на GitHub Actions при каждом пуше.

1. Открой: https://github.com/iliyaqdrwalqu/SiGtRiP/actions
2. Выбери **"Build ARGOS Full APK"**
3. Дождись зелёного ✅ (~30-40 минут)
4. Скачай артефакт `argos-apk-...`
5. Установи на телефон

---

## Структура патчей

| # | Патч | Что добавляет |
|---|------|---------------|
| 1 | argos_patch_v2.1.3 | Email, SMS, WebSocket, Aiogram, Socket IPC |
| 2 | argos_sim800c_patch | GSM модуль SIM800C |
| 3 | argos_iot_full_patch | Zigbee, LoRa, BLE, Modbus, NFC, 1-Wire, I2C |
| 4 | argos_apk_fix_patch | APK workflows, pip --user fix |
| 5 | argos_providers_patch | 8 AI провайдеров с автопереключением |
| 6 | argos_multimodel_patch | Мультимодельный режим Ollama |
| 7 | argos_three_models_patch | Три модели: fast/smart/cloud |
| 8 | argos_thoughtbook_files | Чтение txt/pdf/docx/md |
| 9 | argos_input_control | Мышь, клавиатура, скриншот |

---

*ARGOS Universal OS v2.1 — "Аргос не спит. Аргос видит. Аргос помнит."*

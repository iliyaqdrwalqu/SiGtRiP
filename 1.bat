@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion
title ARGOS Universal OS v1.3 — Windows
color 0A

echo.
echo ======================================================
echo    ARGOS UNIVERSAL OS v1.3 — WINDOWS LAUNCHER
echo ======================================================
echo.

cd /d "%~dp0"

:: ── 1. Python ──────────────────────────────────────────
python --version > nul 2>&1
if errorlevel 1 (
    echo [!] Python не найден. Скачиваю...
    powershell -Command "Invoke-WebRequest -Uri https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe -OutFile python_setup.exe"
    start /wait python_setup.exe /quiet InstallAllUsers=1 PrependPath=1
    del python_setup.exe
    echo [+] Python установлен.
) else (
    echo [+] Python найден.
)

:: ── 2. Git ─────────────────────────────────────────────
git --version > nul 2>&1
if errorlevel 1 (
    echo [!] Git не найден. Скачиваю...
    powershell -Command "Invoke-WebRequest -Uri https://github.com/git-for-windows/git/releases/download/v2.44.0.windows.1/Git-2.44.0-64-bit.exe -OutFile git_setup.exe"
    start /wait git_setup.exe /VERYSILENT
    del git_setup.exe
    echo [+] Git установлен.
) else (
    echo [+] Git найден.
)

:: ── 3. Ollama ──────────────────────────────────────────
if not exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
    echo [!] Ollama не найдена. Скачиваю...
    powershell -Command "Invoke-WebRequest -Uri https://ollama.com/download/OllamaSetup.exe -OutFile ollama_setup.exe"
    start /wait ollama_setup.exe /silent
    del ollama_setup.exe
    timeout /t 5 /nobreak > nul
    echo [+] Ollama установлена.
) else (
    echo [+] Ollama найдена.
)

:: ── 4. Запуск сервера Ollama ───────────────────────────
tasklist /FI "IMAGENAME eq ollama.exe" 2>nul | find /I "ollama.exe" > nul
if errorlevel 1 (
    echo [~] Запуск Ollama сервера...
    if not exist "logs" mkdir logs
    start /B "" ollama serve > logs\ollama.log 2>&1
    timeout /t 5 /nobreak > nul
)
echo [+] Ollama сервер активен.

:: ── 5. Модель llama3 ───────────────────────────────────
ollama list 2>nul | find "llama3" > nul
if errorlevel 1 (
    echo [~] Первый запуск: скачиваю llama3:8b (~5 GB)...
    ollama pull llama3:8b
) else (
    echo [+] Модель llama3 готова.
)

:: ── 6. Python-зависимости ─────────────────────────────
if not exist ".deps_ok" (
    echo [~] Установка зависимостей...
    pip install -r requirements.txt -q
    echo. > .deps_ok
    echo [+] Готово.
) else (
    echo [+] Зависимости уже установлены.
)

:: ── 7. Мастер настройки .env ─────────────────────────
if not exist ".env" (
    echo.
    echo ======================================================
    echo   ПЕРВЫЙ ЗАПУСК — НАСТРОЙКА АРГОСА
    echo   Введи данные. Просто нажми Enter чтобы пропустить.
    echo ======================================================
    echo.

    set /p GEMINI_KEY="  Gemini API Key (ai.google.dev): "
    set /p TG_TOKEN="  Telegram Bot Token (@BotFather): "
    set /p TG_USER="  Твой Telegram ID (@userinfobot): "
    set /p NET_SECRET="  Секрет P2P сети (придумай сам): "

    if "!NET_SECRET!"=="" set NET_SECRET=argos_secret_2026

    echo.
    echo   Сборка APK (Android):
    set /p GH_TOKEN="  GitHub Token (github.com/settings/tokens): "
    set /p GIST_ID="  GitHub Gist ID (если есть): "

    echo.
    echo   ИИ-провайдеры (необязательно):
    set /p OPENAI_KEY="  OpenAI API Key: "
    set /p GROK_KEY="  Grok API Key: "

    :: Записываем .env
    (
        echo GEMINI_API_KEY=!GEMINI_KEY!
        echo TELEGRAM_BOT_TOKEN=!TG_TOKEN!
        echo USER_ID=!TG_USER!
        echo ARGOS_NETWORK_SECRET=!NET_SECRET!
        echo GITHUB_TOKEN=!GH_TOKEN!
        echo GIST_ID=!GIST_ID!
        echo OPENAI_API_KEY=!OPENAI_KEY!
        echo GROK_API_KEY=!GROK_KEY!
        echo ARGOS_HOMEOSTASIS=on
        echo ARGOS_CURIOSITY=on
        echo ARGOS_VOICE_DEFAULT=off
        echo ARGOS_TASK_WORKERS=2
        echo ARGOS_OLLAMA_AUTOSTART=on
    ) > .env

    echo.
    echo [+] .env сохранён!
    echo.

) else (
    echo [+] .env найден.
    echo     Для изменения настроек удали файл .env и перезапусти.
)

:: ── 8. Инициализация структуры ────────────────────────
if not exist "config\identity.json" (
    echo [~] Первый запуск — создаю структуру проекта...
    python genesis.py
)

if not exist "logs" mkdir logs
if not exist "data"  mkdir data

:: ── 9. Самоосознание ─────────────────────────────────
echo.
echo [~] Аргос сканирует свою структуру...
python awareness.py
echo.

:: ── 10. Выбор режима ───────────────────────────────────
echo.
echo ======================================================
echo   Выбери режим:
echo   [1] Desktop GUI           (по умолчанию)
echo   [2] Headless / Терминал
echo   [3] GUI + Dashboard :8080
echo   [4] Headless + Dashboard
echo   [5] GUI + Wake Word "Аргос"
echo ======================================================
echo.
set /p MODE="Введи номер [1-5] или Enter: "

if "%MODE%"=="2" (
    python main.py --no-gui
) else if "%MODE%"=="3" (
    python main.py --dashboard
) else if "%MODE%"=="4" (
    python main.py --no-gui --dashboard
) else if "%MODE%"=="5" (
    python main.py --wake
) else (
    python main.py
)

pause

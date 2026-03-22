#!/usr/bin/env python3
"""
check_all_patches.py — Проверка всех патчей ARGOS.
Запуск: python check_all_patches.py
"""
import sys
import os
sys.path.insert(0, ".")

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "

results = []

def check(name, ok, detail=""):
    icon = PASS if ok else FAIL
    print(f"  {icon}  {name}" + (f"  ({detail})" if detail else ""))
    results.append((name, ok))
    return ok

def section(title):
    print(f"\n{'─'*55}")
    print(f"  {title}")
    print("─"*55)

# ══════════════════════════════════════════════════════
# ПАТЧ 1 — Мосты связи
# ══════════════════════════════════════════════════════
section("1. Мосты связи (argos_patch_v2.1.3)")

try:
    from src.connectivity.email_bridge import EmailBridge
    check("EmailBridge", True)
except Exception as e:
    check("EmailBridge", False, str(e)[:50])

try:
    from src.connectivity.sms_bridge import SMSBridge
    check("SMSBridge", True)
except Exception as e:
    check("SMSBridge", False, str(e)[:50])

try:
    from src.connectivity.websocket_bridge import WebSocketBridge
    check("WebSocketBridge", True)
except Exception as e:
    check("WebSocketBridge", False, str(e)[:50])

try:
    from src.connectivity.web_scraper import WebScraper
    check("WebScraper", True)
except Exception as e:
    check("WebScraper", False, str(e)[:50])

try:
    from src.connectivity.aiogram_bridge import AiogramBridge
    check("AiogramBridge", True)
except Exception as e:
    check("AiogramBridge", False, str(e)[:50])

try:
    from src.connectivity.socket_transport import SocketTransport
    check("SocketTransport", True)
except Exception as e:
    check("SocketTransport", False, str(e)[:50])

try:
    from src.connectivity.messenger_router import MessengerRouter
    r = MessengerRouter()
    check("MessengerRouter (email+sms+tg)", hasattr(r, "email") and hasattr(r, "sms"))
except Exception as e:
    check("MessengerRouter", False, str(e)[:50])

try:
    from src.awareness import ArgosAwareness
    check("ArgosAwareness (src)", True)
except Exception as e:
    check("ArgosAwareness", False, str(e)[:50])

# ══════════════════════════════════════════════════════
# ПАТЧ 2 — SIM800C GSM
# ══════════════════════════════════════════════════════
section("2. GSM SIM800C (argos_sim800c_patch)")

try:
    from src.connectivity.sim800c import SIM800C, SIM800CBridge
    check("SIM800C", True)
    check("SIM800CBridge", True)
except Exception as e:
    check("SIM800C / SIM800CBridge", False, str(e)[:50])

# ══════════════════════════════════════════════════════
# ПАТЧ 3 — IoT протоколы
# ══════════════════════════════════════════════════════
section("3. IoT протоколы (argos_iot_full_patch)")

iot_modules = [
    ("src.connectivity.protocols.zigbee_bridge", "ZigbeeBridge"),
    ("src.connectivity.protocols.lora_bridge", "LoRaBridge"),
    ("src.connectivity.protocols.ble_bridge", "BLEBridge"),
    ("src.connectivity.protocols.modbus_bridge", "ModbusBridge"),
    ("src.connectivity.protocols.nfc_bridge", "NFCBridge"),
    ("src.connectivity.protocols.sensor_bridges", "DS18B20Bridge"),
    ("src.connectivity.protocols.platform_bridges", "HomeAssistantBridge"),
    ("src.connectivity.iot_hub", "ArgosIoTHub"),
]

for mod, cls in iot_modules:
    try:
        m = __import__(mod, fromlist=[cls])
        getattr(m, cls)
        check(cls, True)
    except Exception as e:
        check(cls, False, str(e)[:50])

# ══════════════════════════════════════════════════════
# ПАТЧ 4 — APK fix (workflows проверяем наличие)
# ══════════════════════════════════════════════════════
section("4. APK workflows (argos_apk_fix_patch)")

from pathlib import Path
for wf in ["android-apk.yml", "build_apk_client.yml", "auto_push.yml", "status_report.yml"]:
    p = Path(f".github/workflows/{wf}")
    check(wf, p.exists())

# Проверяем нет ли --user в workflows
user_found = False
for wf in Path(".github/workflows").glob("*.yml"):
    text = wf.read_text(errors="replace")
    if "pip install --user" in text:
        user_found = True
        print(f"  {WARN} --user найден в {wf.name}")
check("Нет pip --user в workflows", not user_found)

# ══════════════════════════════════════════════════════
# ПАТЧ 5 — AI провайдеры
# ══════════════════════════════════════════════════════
section("5. AI провайдеры (argos_providers_patch)")

try:
    from src.ai_router import AIRouter
    r = AIRouter()
    status = r.status()
    check("AIRouter импорт", True)
    check("AIRouter.status()", "AI Router" in status)
    # Проверяем ключи
    providers = {
        "GEMINI_API_KEY": "Gemini",
        "GROQ_API_KEY": "Groq",
        "DEEPSEEK_API_KEY": "DeepSeek",
        "XAI_API_KEY": "xAI Grok",
    }
    for env, name in providers.items():
        has_key = bool(os.getenv(env))
        icon = PASS if has_key else WARN
        print(f"  {icon}  {name} ключ {'настроен' if has_key else 'не задан'}")
except Exception as e:
    check("AIRouter", False, str(e)[:50])

# ══════════════════════════════════════════════════════
# ПАТЧ 6 — Мультимодельный режим
# ══════════════════════════════════════════════════════
section("6. Мультимодель (argos_multimodel_patch)")

try:
    from src.multi_model import MultiModelManager, detect_task_type
    mgr = MultiModelManager()
    check("MultiModelManager", True)
    t = detect_task_type("привет")
    check("detect_task_type('привет')", t == "fast", f"→ {t}")
    t2 = detect_task_type("напиши код на python")
    check("detect_task_type('код')", t2 == "code", f"→ {t2}")
except Exception as e:
    check("MultiModelManager", False, str(e)[:50])

# ══════════════════════════════════════════════════════
# ПАТЧ 7 — Три модели Ollama
# ══════════════════════════════════════════════════════
section("7. Три модели Ollama (argos_three_models_patch)")

try:
    from src.ollama_three import ThreeModelManager, get_manager
    mgr = get_manager()
    check("ThreeModelManager", True)
    status = mgr.status()
    check("status() работает", "tinyllama" in status or "Ollama" in status)
    check("OLLAMA_FAST_MODEL задан", bool(os.getenv("OLLAMA_FAST_MODEL", "")))
    check("OLLAMA_CLOUD_MODEL задан", bool(os.getenv("OLLAMA_CLOUD_MODEL", "")))
except Exception as e:
    check("ThreeModelManager", False, str(e)[:50])

# ══════════════════════════════════════════════════════
# ПАТЧ 8 — ThoughtBook + файлы
# ══════════════════════════════════════════════════════
section("8. ThoughtBook + файлы (argos_thoughtbook_files_patch)")

try:
    from src.thought_book import ArgosThoughtBook
    book = ArgosThoughtBook()
    check("ArgosThoughtBook импорт", True)

    # Проверяем наличие файловых команд
    r = book.handle_command("создай файл _test_check.txt | test")
    check("создай файл", "✅" in r or "создан" in r.lower())

    r2 = book.handle_command("прочитай _test_check.txt")
    check("прочитай файл", "test" in r2 or "📄" in r2)

    # Чистим тест файл
    Path("_test_check.txt").unlink(missing_ok=True)

    # Проверяем что handle_command расширен
    check("файловые команды в handle_command",
          "_patched_handle_command" in str(type(book).handle_command))
except Exception as e:
    check("ThoughtBook+файлы", False, str(e)[:60])

# ══════════════════════════════════════════════════════
# ИТОГ
# ══════════════════════════════════════════════════════
print(f"\n{'═'*55}")
total = len(results)
passed = sum(1 for _, ok in results if ok)
failed = total - passed

if failed == 0:
    print(f"  🔱 ВСЕ ПАТЧИ РАБОТАЮТ: {passed}/{total}")
else:
    print(f"  {FAIL} Результат: {passed}/{total} OK, {failed} проблем")
    print("\n  Проблемы:")
    for name, ok in results:
        if not ok:
            print(f"    ❌ {name}")
print("═"*55)

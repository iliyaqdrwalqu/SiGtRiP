import asyncio
import io
import importlib.util
import logging
import aiosqlite
import sys
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message
from dotenv import load_dotenv
from openai import AsyncOpenAI
import os

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

if not TOKEN:
    logging.critical(
        "TELEGRAM_TOKEN не задан! "
        "Скопируйте .env.example в .env и укажите токен бота от @BotFather."
    )
    sys.exit(1)

bot = Bot(token=TOKEN)
dp = Dispatcher()
openai_client = AsyncOpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

log = logging.getLogger(__name__)

# Telegram hard limit for message text length
TELEGRAM_MAX_MESSAGE_LENGTH = 4096
# Number of most-recent messages passed to the AI as context
GPT_CONTEXT_LIMIT = 80
# Hard cap for persisted messages per chat to avoid unbounded history retention
MAX_STORED_MESSAGES_PER_CHAT = 500
# ISO datetime format "YYYY-MM-DD HH:MM:SS" is 19 characters
DATETIME_DISPLAY_LENGTH = 19
# Maximum file size (bytes) that will be downloaded and read
MAX_FILE_READ_BYTES = 10 * 1024 * 1024  # 10 MB
# Maximum characters shown from a file's text content in the reply
MAX_FILE_DISPLAY_CHARS = 3000

# Set of chat IDs that have voice output enabled
_voice_chats: set[int] = set()

# Cached ArgosAbsolute instance — loaded once to avoid re-importing main.py on every /argos call
_argos_core: object | None = None


def _get_argos_core() -> object:
    """Return a cached ArgosAbsolute instance, loading main.py only the first time."""
    global _argos_core
    if _argos_core is None:
        _spec = importlib.util.spec_from_file_location(
            "argos_main",
            os.path.join(os.path.dirname(__file__), "main.py"),
        )
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _argos_core = _mod.ArgosAbsolute()
    return _argos_core


def _tts_to_bytes(text: str, lang: str = "ru") -> bytes | None:
    """Generate TTS audio for *text* using gTTS and return MP3 bytes.

    Returns ``None`` if gTTS is not installed or synthesis fails.
    """
    try:
        from gtts import gTTS  # type: ignore[import]
        buf = io.BytesIO()
        gTTS(text=text[:500], lang=lang).write_to_fp(buf)
        return buf.getvalue()
    except Exception as exc:
        log.warning("TTS synthesis failed: %s", exc)
        return None

def _read_file_content(raw: bytes, file_name: str) -> str:
    """Decode *raw* bytes as text and return a human-readable string.

    Null bytes are used as a reliable indicator of binary (non-text) content.
    For text files, UTF-8 is attempted first, with latin-1 as a fallback for
    legacy encodings.  Long text is truncated to ``MAX_FILE_DISPLAY_CHARS``
    characters.
    """
    if b"\x00" in raw:
        return f"🔒 Файл содержит бинарные данные ({len(raw)} байт)."
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    if len(text) > MAX_FILE_DISPLAY_CHARS:
        text = (
            text[:MAX_FILE_DISPLAY_CHARS]
            + f"\n\n... (показано {MAX_FILE_DISPLAY_CHARS} из {len(text)} символов)"
        )
    return f"📄 Содержимое файла:\n{text}"


# ====================== SQLite ======================
DB_NAME = "chat_history.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id INTEGER,
                username TEXT,
                full_name TEXT,
                text TEXT,
                date TEXT
            )
        ''')
        await db.commit()

async def save_message(chat_id: int, user_id: int, username: str, full_name: str, text: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            INSERT INTO messages (chat_id, user_id, username, full_name, text, date)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (chat_id, user_id, username, full_name, text, datetime.now().isoformat()))
        await db.execute('''
            DELETE FROM messages
            WHERE chat_id = ?
              AND id NOT IN (
                SELECT id FROM messages
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT ?
              )
        ''', (chat_id, chat_id, MAX_STORED_MESSAGES_PER_CHAT))
        await db.commit()

async def get_recent_history(chat_id: int, limit: int = 100) -> str:
    async with aiosqlite.connect(DB_NAME) as db:
        # Fetch the most recent rows in reverse, then re-order ascending for readability
        async with db.execute('''
            SELECT full_name, text, date FROM (
                SELECT id, full_name, text, date FROM messages
                WHERE chat_id = ? ORDER BY id DESC LIMIT ?
            ) ORDER BY id ASC
        ''', (chat_id, limit)) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        return "История пуста."
    return "\n".join([f"[{date[:DATETIME_DISPLAY_LENGTH]}] {name}: {text}" for name, text, date in rows])

# ====================== AI with bounded recent context ======================
async def get_gpt_response(chat_id: int, user_message: str) -> str:
    if not openai_client:
        return (
            "⚠️ OPENAI_API_KEY не задан в .env\n"
            "Бот работает без GPT. Установите ключ и перезапустите."
        )

    history_text = await get_recent_history(chat_id, limit=GPT_CONTEXT_LIMIT)

    system_prompt = (
        "Ты умный дружелюбный помощник системы ARGOS v1.33. "
        "У тебя есть только недавний контекст чата ниже. "
        "Отвечай максимально полезно, с юмором и учитывая контекст.\n\n"
        f"=== ПОСЛЕДНИЕ {GPT_CONTEXT_LIMIT} СООБЩЕНИЙ ЧАТА ===\n{history_text}\n=== КОНЕЦ КОНТЕКСТА ===\n\n"
        f"Пользователь сейчас написал: {user_message}\n"
        "Отвечай только на русском, коротко и по делу."
    )

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system_prompt}],
            temperature=0.7,
            max_tokens=800,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Ошибка OpenAI: {e}"

# ====================== Handlers ======================
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "🔱 *ARGOS v1.33 ONLINE*\n\n"
        "Команды:\n"
        "/history — последние 50 сообщений\n"
        "/clear — очистить историю\n"
        "/voice\\_on — включить голосовые ответы 🔊\n"
        "/voice\\_off — отключить голосовые ответы 🔇\n"
        "/argos \\<команда\\> — выполнить команду ARGOS\n\n"
        "Команды ARGOS: nfc, bt, wifi, root, gps, status, build apk, "
        "build firmware, model status, model update, 7z pack \\<путь\\>, help\n\n"
        "📎 Отправь любой файл — ARGOS прочитает его содержимое\\.",
        parse_mode="MarkdownV2",
    )

@dp.message(Command("history"))
async def cmd_history(message: Message):
    hist = await get_recent_history(message.chat.id, limit=50)
    preview = hist[:TELEGRAM_MAX_MESSAGE_LENGTH]
    await message.answer("📜 Последние 50 сообщений:\n\n" + preview)

@dp.message(Command("clear"))
async def cmd_clear(message: Message):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM messages WHERE chat_id = ?", (message.chat.id,))
        await db.commit()
    await message.answer("✅ Вся история этого чата удалена из базы.")

@dp.message(Command("voice_on"))
async def cmd_voice_on(message: Message):
    """Включить голосовые ответы для этого чата."""
    _voice_chats.add(message.chat.id)
    await message.answer("🔊 Голосовые ответы включены.")

@dp.message(Command("voice_off"))
async def cmd_voice_off(message: Message):
    """Отключить голосовые ответы для этого чата."""
    _voice_chats.discard(message.chat.id)
    await message.answer("🔇 Голосовые ответы отключены.")

@dp.message(Command("argos"))
async def cmd_argos(message: Message):
    """Выполнить команду ARGOS напрямую через Telegram."""
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "ℹ️ Использование: /argos <команда>\n"
            "Пример: /argos status\n"
            "Пример: /argos build firmware\n"
            "Команда help покажет все доступные команды."
        )
        return
    cmd = parts[1].strip()
    try:
        # Reuse the cached ArgosAbsolute instance — avoids re-loading main.py on every call
        core = _get_argos_core()
        result = core.execute(cmd)
    except Exception as e:
        result = f"❌ Ошибка выполнения: {e}"
    # Разбить длинный ответ на части (все части, без ограничения)
    for i in range(0, len(result), TELEGRAM_MAX_MESSAGE_LENGTH):
        await message.answer(result[i:i + TELEGRAM_MAX_MESSAGE_LENGTH])

@dp.message(F.document)
async def handle_document(message: Message):
    """Принять файл от пользователя, прочитать его содержимое и отправить ответ."""
    doc = message.document
    file_name = doc.file_name or "неизвестный_файл"
    file_size = doc.file_size or 0
    mime_type = doc.mime_type or "application/octet-stream"

    description = f"[ФАЙЛ: {file_name}, {file_size} байт, {mime_type}]"
    await save_message(
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        username=message.from_user.username or "no_username",
        full_name=message.from_user.full_name,
        text=description,
    )

    if file_size > MAX_FILE_READ_BYTES:
        await message.answer(
            f"📎 Файл «{file_name}» получен ({file_size // 1024} КБ).\n"
            f"⚠️ Файл слишком большой для чтения (лимит {MAX_FILE_READ_BYTES // 1024 // 1024} МБ)."
        )
        return

    buf = io.BytesIO()
    await bot.download(doc, destination=buf)
    buf.seek(0)
    raw = buf.read()

    content = _read_file_content(raw, file_name)
    header = f"📎 Файл: {file_name}\n📏 Размер: {file_size} байт\n📂 Тип: {mime_type}\n\n"
    reply = header + content
    for i in range(0, len(reply), TELEGRAM_MAX_MESSAGE_LENGTH):
        await message.answer(reply[i:i + TELEGRAM_MAX_MESSAGE_LENGTH])

@dp.message()
async def all_messages(message: Message):
    text = message.text or f"[НЕ ТЕКСТ: {message.content_type}]"

    # Save message and fetch GPT response concurrently — the current text is passed
    # directly to get_gpt_response, so history context stays accurate either way.
    save_task = asyncio.create_task(save_message(
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        username=message.from_user.username or "no_username",
        full_name=message.from_user.full_name,
        text=text,
    ))

    # In group chats, skip non-text messages
    if message.chat.type in ["group", "supergroup"] and not message.text:
        await save_task
        return

    thinking = await message.answer("🤔 Думаю...")
    gpt_text, _ = await asyncio.gather(
        get_gpt_response(message.chat.id, text),
        save_task,
    )
    await thinking.edit_text(gpt_text)

    # Send voice reply when enabled for this chat
    if message.chat.id in _voice_chats:
        audio_bytes = await asyncio.to_thread(_tts_to_bytes, gpt_text)
        if audio_bytes:
            await message.answer_voice(
                BufferedInputFile(audio_bytes, filename="reply.mp3")
            )

async def main():
    await init_db()
    logging.basicConfig(level=logging.INFO)
    await bot.delete_webhook(drop_pending_updates=True)
    log.info("Bot started. Saving bounded recent history to SQLite and replying via ChatGPT.")
    log.info("For group chats: BotFather → /setprivacy → Disable, then re-add bot to the group.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

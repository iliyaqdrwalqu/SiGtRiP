"""
src/connectivity/aiogram_bridge.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Aiogram 3.x мост Аргоса.
Используется как альтернатива python-telegram-bot там,
где нужна asyncio-native интеграция.

pip install aiogram>=3.0.0
"""
from __future__ import annotations

import asyncio
import os
import threading
from typing import Any, Callable

try:
    from aiogram import Bot, Dispatcher, F  # type: ignore
    from aiogram.filters import Command  # type: ignore
    from aiogram.types import Message  # type: ignore
    _AIOGRAM_AVAILABLE = True
except ImportError:
    _AIOGRAM_AVAILABLE = False
    Bot = Dispatcher = F = Command = Message = None  # type: ignore


class AiogramBridge:
    """
    Aiogram 3.x обёртка.
    Поддерживает polling и webhook.
    on_message(text, user_id) → str: обработчик команд.
    """

    def __init__(
        self,
        token: str = "",
        on_message: Callable[[str, int], str] | None = None,
    ):
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.on_message = on_message
        self._bot: Any = None
        self._dp: Any = None
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

        if self._ready():
            self._bot = Bot(token=self.token)
            self._dp = Dispatcher()
            self._register_handlers()

    def _ready(self) -> bool:
        return bool(self.token and _AIOGRAM_AVAILABLE)

    @property
    def bot(self):
        return self._bot

    @property
    def dispatcher(self):
        return self._dp

    # ── Handlers ─────────────────────────────────────────────────────────────

    def _register_handlers(self):
        if not self._dp:
            return

        @self._dp.message(Command("start"))
        async def _start(msg: Message):
            await msg.answer("🔱 Аргос онлайн. Отправь команду.")

        @self._dp.message(Command("status"))
        async def _status(msg: Message):
            reply = self._dispatch("статус системы", msg.from_user.id)
            await msg.answer(reply)

        @self._dp.message(F.text)
        async def _text(msg: Message):
            reply = self._dispatch(msg.text or "", msg.from_user.id)
            await msg.answer(reply)

    def _dispatch(self, text: str, user_id: int) -> str:
        if self.on_message:
            try:
                return self.on_message(text, user_id)
            except Exception as exc:
                return f"❌ Ошибка: {exc}"
        return f"[Аргос] получено: {text}"

    # ── Polling ───────────────────────────────────────────────────────────────

    def start_polling(self) -> str:
        """Запустить polling в отдельном потоке."""
        if not self._ready():
            return "❌ aiogram не настроен (токен или библиотека отсутствуют)"

        def _run():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._dp.start_polling(self._bot))

        self._thread = threading.Thread(target=_run, daemon=True, name="ArgosAiogram")
        self._thread.start()
        return "✅ Aiogram polling запущен"

    # ── Send ─────────────────────────────────────────────────────────────────

    def send_message_sync(self, chat_id: int | str, text: str) -> dict[str, Any]:
        """Синхронная отправка сообщения."""
        if not self._ready():
            return {"ok": False, "error": "aiogram не настроен"}
        try:
            async def _send():
                await self._bot.send_message(chat_id=chat_id, text=text)
            if self._loop and self._loop.is_running():
                fut = asyncio.run_coroutine_threadsafe(_send(), self._loop)
                fut.result(timeout=10)
            else:
                asyncio.run(_send())
            return {"ok": True, "provider": "aiogram", "chat_id": chat_id}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

"""
aiogram_bridge.py — Telegram-мост Аргоса через aiogram 3.x.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Callable

try:
    from aiogram import Bot, Dispatcher, types as aio_types
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
except ImportError:  # pragma: no cover
    Bot = None  # type: ignore[assignment,misc]
    Dispatcher = None  # type: ignore[assignment,misc]
    aio_types = None  # type: ignore[assignment]
    DefaultBotProperties = None  # type: ignore[assignment,misc]
    ParseMode = None  # type: ignore[assignment,misc]


class AiogramBridge:
    """Telegram-бот на базе aiogram 3 — отправка сообщений, запуск polling."""

    def __init__(
        self,
        token: str | None = None,
        parse_mode: str | None = None,
    ):
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.parse_mode = parse_mode or "HTML"
        self._bot: Any = None
        self._dp: Any = None

        if Bot and self.token:
            self._bot = Bot(
                token=self.token,
                default=DefaultBotProperties(parse_mode=self.parse_mode),
            )
            self._dp = Dispatcher()

    def _ready(self) -> bool:
        return bool(self.token and Bot is not None and self._bot is not None)

    @property
    def dispatcher(self) -> Any:
        """Dispatcher для регистрации хендлеров (dp.message, dp.callback_query и т.д.)."""
        return self._dp

    @property
    def bot(self) -> Any:
        """Экземпляр aiogram.Bot."""
        return self._bot

    # ── отправка ──────────────────────────────────────────────────────
    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Отправить сообщение в чат."""
        if not self._ready():
            return {"ok": False, "provider": "aiogram", "error": "Aiogram bridge is not configured"}

        try:
            msg = await self._bot.send_message(chat_id=chat_id, text=text, **kwargs)
            return {"ok": True, "provider": "aiogram", "data": {"message_id": msg.message_id}}
        except Exception as exc:
            return {"ok": False, "provider": "aiogram", "error": str(exc)}

    def send_message_sync(self, chat_id: int | str, text: str, **kwargs: Any) -> dict[str, Any]:
        """Синхронная обёртка для send_message."""
        return asyncio.get_event_loop().run_until_complete(
            self.send_message(chat_id, text, **kwargs),
        )

    # ── polling ───────────────────────────────────────────────────────
    async def start_polling(self) -> dict[str, Any]:
        """Запустить polling (блокирующий)."""
        if not self._ready():
            return {"ok": False, "provider": "aiogram", "error": "Aiogram bridge is not configured"}

        try:
            await self._dp.start_polling(self._bot)
            return {"ok": True, "provider": "aiogram", "data": "polling stopped"}
        except Exception as exc:
            return {"ok": False, "provider": "aiogram", "error": str(exc)}

    async def stop(self) -> None:
        """Остановить бота и закрыть сессию."""
        if self._bot:
            await self._bot.session.close()

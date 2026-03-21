"""
messenger_router.py — единый маршрутизатор всех мессенджеров.
"""
from __future__ import annotations

from typing import Any

from src.connectivity.aiogram_bridge import AiogramBridge
from src.connectivity.email_bridge import EmailBridge
from src.connectivity.max_bridge import MaxBridge
from src.connectivity.slack_bridge import SlackBridge
from src.connectivity.sms_bridge import SMSBridge
from src.connectivity.whatsapp_bridge import WhatsAppBridge


class MessengerRouter:
    def __init__(
        self,
        whatsapp: WhatsAppBridge | None = None,
        slack: SlackBridge | None = None,
        max_bridge: MaxBridge | None = None,
        email_bridge: EmailBridge | None = None,
        sms_bridge: SMSBridge | None = None,
        aiogram_bridge: AiogramBridge | None = None,
    ):
        self.whatsapp = whatsapp or WhatsAppBridge()
        self.slack = slack or SlackBridge()
        self.max = max_bridge or MaxBridge()
        self.email = email_bridge or EmailBridge()
        self.sms = sms_bridge or SMSBridge()
        self.telegram = aiogram_bridge or AiogramBridge()

    def route_message(self, messenger: str, recipient: str, text: str) -> dict[str, Any]:
        normalized = (messenger or "").strip().lower()
        if normalized in {"whatsapp", "wa"}:
            return self.whatsapp.send_message(to=recipient, text=text)
        if normalized in {"slack"}:
            return self.slack.send_message(channel=recipient, text=text)
        if normalized in {"max", "mailru_max", "mailru-max"}:
            return self.max.send_message(chat_id=recipient, text=text)
        if normalized in {"email", "mail", "smtp"}:
            return self.email.send_message(to=recipient, subject="Argos", body=text)
        if normalized in {"sms"}:
            return self.sms.send_message(to=recipient, text=text)
        if normalized in {"telegram", "tg", "aiogram"}:
            return self.telegram.send_message_sync(chat_id=recipient, text=text)
        return {"ok": False, "provider": normalized or "unknown", "error": f"Unsupported messenger: {messenger}"}

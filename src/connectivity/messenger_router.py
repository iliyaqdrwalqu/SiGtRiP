"""
src/connectivity/messenger_router.py (обновлено — SIM800C)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Единый роутер мессенджеров Аргоса.
Добавлен канал: sms800c / gsm (через SIM800C модем)
"""
from __future__ import annotations

from typing import Any

from .whatsapp_bridge import WhatsAppBridge
from .slack_bridge import SlackBridge
from .max_bridge import MaxBridge
from .email_bridge import EmailBridge
from .sms_bridge import SMSBridge
from .aiogram_bridge import AiogramBridge
from .sim800c import SIM800CBridge


class MessengerRouter:
    """Маршрутизатор сообщений по всем каналам связи."""

    def __init__(self):
        self.whatsapp = WhatsAppBridge()
        self.slack = SlackBridge()
        self.max = MaxBridge()
        self.email = EmailBridge()
        self.sms = SMSBridge()
        self.telegram = AiogramBridge()
        # GSM-модем SIM800C
        self.gsm = SIM800CBridge(
            port=__import__("os").getenv("SIM800C_PORT", ""),
            platform=__import__("os").getenv("SIM800C_PLATFORM", "auto"),
        )

    def route_message(
        self,
        channel: str,
        recipient: str,
        text: str,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Отправить сообщение через указанный канал.
        channel: whatsapp | slack | max | email | sms | telegram | tg | gsm | sim | sms800c
        """
        ch = channel.lower().strip()

        if ch == "whatsapp":
            return self.whatsapp.send_message(to=recipient, text=text)
        if ch == "slack":
            return self.slack.send_message(channel=recipient, text=text)
        if ch == "max":
            return self.max.send_message(chat_id=recipient, text=text)
        if ch == "email":
            return self.email.send_message(to=recipient, subject=kwargs.get("subject", "Argos"), body=text)
        if ch == "sms":
            return self.sms.send_message(to=recipient, text=text)
        if ch in ("telegram", "tg"):
            return self.telegram.send_message_sync(chat_id=recipient, text=text)
        if ch in ("gsm", "sim", "sms800c", "sim800c"):
            return self.gsm.send_message(to=recipient, text=text)

        return {"ok": False, "error": f"Неизвестный канал: {channel}"}

    def broadcast(self, text: str, channels: list[str] | None = None) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for ch in (channels or ["slack"]):
            results[ch] = self.route_message(ch, "", text)
        return {"ok": all(r.get("ok") for r in results.values()), "results": results}

    def status(self) -> str:
        lines = ["📡 МЕССЕНДЖЕР РОУТЕР"]
        for name, bridge in [
            ("WhatsApp", self.whatsapp),
            ("Slack", self.slack),
            ("Max", self.max),
            ("Email", self.email),
            ("SMS (smsmobileapi)", self.sms),
            ("Telegram (aiogram)", self.telegram),
            ("GSM SIM800C", self.gsm),
        ]:
            configured = getattr(bridge, "_configured", lambda: True)()
            lines.append(f"  {'✅' if configured else '⚠️'} {name}")
        return "\n".join(lines)

"""
src/connectivity/sms_bridge.py — SMS мост ARGOS
Использует smsmobileapi (pip install smsmobileapi).
Graceful fallback: если библиотека не установлена — возвращает ошибку.
"""
from __future__ import annotations

import os
from typing import Any

try:
    from smsmobileapi import SMSMobileAPI as _SMSMobileAPI
except ImportError:
    _SMSMobileAPI = None  # type: ignore[assignment]


class SMSBridge:
    """
    Мост для отправки/получения SMS через smsmobileapi.

    Переменные окружения:
        SMSMOBILEAPI_KEY — API ключ сервиса
    """

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.getenv("SMSMOBILEAPI_KEY", "")
        self._client = None
        if self.api_key and _SMSMobileAPI:
            try:
                self._client = _SMSMobileAPI(self.api_key)
            except Exception:
                self._client = None

    def _ready(self) -> bool:
        return bool(self.api_key and self._client)

    def send_message(self, to: str, text: str) -> dict:
        """Отправить SMS. to — номер в международном формате (+7...)"""
        if not self._ready():
            return {
                "ok": False,
                "provider": "sms",
                "error": "SMS не настроен (SMSMOBILEAPI_KEY или pip install smsmobileapi)",
            }
        try:
            result = self._client.send_sms(to, text)
            return {"ok": True, "provider": "sms", "data": result}
        except Exception as exc:
            return {"ok": False, "provider": "sms", "error": str(exc)}

    def receive_messages(self) -> dict:
        """Получить входящие SMS."""
        if not self._ready():
            return {"ok": False, "provider": "sms", "error": "SMS не настроен"}
        try:
            msgs = self._client.get_sms()
            return {"ok": True, "provider": "sms", "data": msgs}
        except Exception as exc:
            return {"ok": False, "provider": "sms", "error": str(exc)}

    def status(self) -> str:
        if not self.api_key:
            return "📱 SMS: не настроен (SMSMOBILEAPI_KEY)"
        if _SMSMobileAPI is None:
            return "📱 SMS: ключ есть, но smsmobileapi не установлен (pip install smsmobileapi)"
        return "📱 SMS: ✅  smsmobileapi подключён"

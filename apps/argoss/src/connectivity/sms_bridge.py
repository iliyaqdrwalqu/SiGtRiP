"""
sms_bridge.py — SMS-мост Аргоса через SMSMobileAPI.
"""
from __future__ import annotations

import os
from typing import Any

try:
    from smsmobileapi import SMSMobileAPI as _SMSMobileAPI
except ImportError:  # pragma: no cover
    _SMSMobileAPI = None


class SMSBridge:
    """Отправка / получение SMS через SMSMobileAPI (smsmobileapi)."""

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 15.0,
    ):
        self.api_key = api_key or os.getenv("SMSMOBILEAPI_KEY", "")
        self.timeout = timeout
        self._client: Any = None
        if _SMSMobileAPI and self.api_key:
            self._client = _SMSMobileAPI(self.api_key)

    def _ready(self) -> bool:
        return bool(self.api_key and _SMSMobileAPI is not None)

    # ── отправка ──────────────────────────────────────────────────────
    def send_message(self, to: str, text: str) -> dict[str, Any]:
        """Отправить SMS через SMSMobileAPI."""
        if _SMSMobileAPI is None:
            return {"ok": False, "provider": "sms", "error": "smsmobileapi package is not installed"}
        if not self._ready():
            return {"ok": False, "provider": "sms", "error": "SMSMOBILEAPI_KEY is not configured"}

        try:
            result = self._client.send_sms(to, text)
            return {"ok": True, "provider": "sms", "data": result}
        except Exception as exc:
            return {"ok": False, "provider": "sms", "error": str(exc)}

    # ── получение ─────────────────────────────────────────────────────
    def receive_messages(self) -> dict[str, Any]:
        """Получить входящие SMS через SMSMobileAPI."""
        if _SMSMobileAPI is None:
            return {"ok": False, "provider": "sms", "error": "smsmobileapi package is not installed"}
        if not self._ready():
            return {"ok": False, "provider": "sms", "error": "SMSMOBILEAPI_KEY is not configured"}

        try:
            result = self._client.get_sms()
            return {"ok": True, "provider": "sms", "data": result}
        except Exception as exc:
            return {"ok": False, "provider": "sms", "error": str(exc)}

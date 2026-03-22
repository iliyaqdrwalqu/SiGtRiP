"""
src/connectivity/email_bridge.py — Email мост ARGOS
Отправка через smtplib, получение через imaplib.
Только встроенные библиотеки Python — нет внешних зависимостей.
"""
from __future__ import annotations

import os
import smtplib
import imaplib
import email
import email.mime.text
import email.mime.multipart
from typing import Any


class EmailBridge:
    """
    Мост для отправки/получения email через SMTP/IMAP.

    Переменные окружения:
        ARGOS_EMAIL_USERNAME  — адрес отправителя
        ARGOS_EMAIL_PASSWORD  — пароль / app-password
        ARGOS_EMAIL_SMTP_HOST — SMTP сервер (default: smtp.gmail.com)
        ARGOS_EMAIL_SMTP_PORT — SMTP порт (default: 465 SSL)
        ARGOS_EMAIL_IMAP_HOST — IMAP сервер (default: imap.gmail.com)
    """

    def __init__(
        self,
        username: str = "",
        password: str = "",
        smtp_host: str = "",
        smtp_port: int = 465,
        imap_host: str = "",
        use_ssl: bool = True,
    ):
        self.username  = username  or os.getenv("ARGOS_EMAIL_USERNAME", "")
        self.password  = password  or os.getenv("ARGOS_EMAIL_PASSWORD", "")
        self.smtp_host = smtp_host or os.getenv("ARGOS_EMAIL_SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = smtp_port
        self.imap_host = imap_host or os.getenv("ARGOS_EMAIL_IMAP_HOST", "imap.gmail.com")
        self.use_ssl   = use_ssl

    def _ready(self) -> bool:
        return bool(self.username and self.password)

    def send_message(
        self,
        to: str,
        subject: str = "Argos",
        body: str = "",
        html: bool = False,
    ) -> dict:
        if not self._ready():
            return {"ok": False, "provider": "email", "error": "Email не настроен"}

        try:
            msg = email.mime.multipart.MIMEMultipart("alternative")
            msg["From"]    = self.username
            msg["To"]      = to
            msg["Subject"] = subject
            part = email.mime.text.MIMEText(body, "html" if html else "plain", "utf-8")
            msg.attach(part)

            if self.use_ssl:
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port) as srv:
                    srv.login(self.username, self.password)
                    srv.sendmail(self.username, to, msg.as_string())
            else:
                with smtplib.SMTP(self.smtp_host, self.smtp_port) as srv:
                    srv.starttls()
                    srv.login(self.username, self.password)
                    srv.sendmail(self.username, to, msg.as_string())

            return {"ok": True, "provider": "email"}
        except Exception as exc:
            return {"ok": False, "provider": "email", "error": str(exc)}

    def fetch_messages(self, folder: str = "INBOX", limit: int = 10) -> dict:
        if not self._ready():
            return {"ok": False, "provider": "email", "error": "Email не настроен"}

        try:
            conn = imaplib.IMAP4_SSL(self.imap_host)
            conn.login(self.username, self.password)
            conn.select(folder)

            _, data = conn.search(None, "ALL")
            ids = data[0].split() if data[0] else []
            ids = ids[-limit:]

            messages = []
            for uid in ids:
                _, raw = conn.fetch(uid, "(RFC822)")
                for part in raw:
                    if isinstance(part, tuple):
                        m = email.message_from_bytes(part[1])
                        messages.append({
                            "from":    m.get("From", ""),
                            "subject": m.get("Subject", ""),
                            "date":    m.get("Date", ""),
                            "body":    self._get_body(m),
                        })

            conn.logout()
            return {"ok": True, "provider": "email", "data": messages}
        except Exception as exc:
            return {"ok": False, "provider": "email", "error": str(exc)}

    def _get_body(self, msg) -> str:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    try:
                        return part.get_payload(decode=True).decode("utf-8", errors="replace")
                    except Exception:
                        pass
        else:
            try:
                return msg.get_payload(decode=True).decode("utf-8", errors="replace")
            except Exception:
                pass
        return ""

    def status(self) -> str:
        if not self._ready():
            return "📧 Email: не настроен (ARGOS_EMAIL_USERNAME / ARGOS_EMAIL_PASSWORD)"
        return f"📧 Email: ✅  {self.username} → {self.smtp_host}"

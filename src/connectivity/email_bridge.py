"""
email_bridge.py — Email-мост Аргоса: отправка через smtplib, получение через imaplib.
"""
from __future__ import annotations

import email
import email.mime.multipart
import email.mime.text
import imaplib
import os
import smtplib
from typing import Any


class EmailBridge:
    """Отправка и получение электронной почты через встроенные smtplib / imaplib."""

    def __init__(
        self,
        smtp_host: str | None = None,
        smtp_port: int | None = None,
        imap_host: str | None = None,
        imap_port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        use_ssl: bool = True,
        timeout: float = 15.0,
    ):
        self.smtp_host = smtp_host or os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(smtp_port or os.getenv("EMAIL_SMTP_PORT", "465" if use_ssl else "587"))
        self.imap_host = imap_host or os.getenv("EMAIL_IMAP_HOST", "imap.gmail.com")
        self.imap_port = int(imap_port or os.getenv("EMAIL_IMAP_PORT", "993"))
        self.username = username or os.getenv("EMAIL_USERNAME", "")
        self.password = password or os.getenv("EMAIL_PASSWORD", "")
        self.use_ssl = use_ssl
        self.timeout = timeout

    # ── готовность ────────────────────────────────────────────────────
    def _ready(self) -> bool:
        return bool(self.username and self.password)

    # ── отправка ──────────────────────────────────────────────────────
    def send_message(
        self,
        to: str,
        subject: str,
        body: str,
        html: bool = False,
    ) -> dict[str, Any]:
        """Отправить письмо через SMTP."""
        if not self._ready():
            return {"ok": False, "provider": "email", "error": "EMAIL_USERNAME / EMAIL_PASSWORD not configured"}

        msg = email.mime.multipart.MIMEMultipart("alternative")
        msg["From"] = self.username
        msg["To"] = to
        msg["Subject"] = subject
        subtype = "html" if html else "plain"
        msg.attach(email.mime.text.MIMEText(body, subtype, "utf-8"))

        try:
            if self.use_ssl:
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=self.timeout) as srv:
                    srv.login(self.username, self.password)
                    srv.sendmail(self.username, [to], msg.as_string())
            else:
                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=self.timeout) as srv:
                    srv.ehlo()
                    srv.starttls()
                    srv.login(self.username, self.password)
                    srv.sendmail(self.username, [to], msg.as_string())
        except Exception as exc:
            return {"ok": False, "provider": "email", "error": str(exc)}

        return {"ok": True, "provider": "email", "data": {"to": to, "subject": subject}}

    # ── получение ─────────────────────────────────────────────────────
    def fetch_messages(
        self,
        folder: str = "INBOX",
        limit: int = 10,
        unseen_only: bool = True,
    ) -> dict[str, Any]:
        """Получить последние письма через IMAP."""
        if not self._ready():
            return {"ok": False, "provider": "email", "error": "EMAIL_USERNAME / EMAIL_PASSWORD not configured"}

        try:
            conn = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
            conn.login(self.username, self.password)
            conn.select(folder)

            criterion = "UNSEEN" if unseen_only else "ALL"
            _status, msg_ids = conn.search(None, criterion)
            id_list = msg_ids[0].split() if msg_ids[0] else []
            id_list = id_list[-limit:]  # последние N

            messages: list[dict[str, Any]] = []
            for mid in id_list:
                _status, raw = conn.fetch(mid, "(RFC822)")
                if raw[0] is None:
                    continue
                msg = email.message_from_bytes(raw[0][1])
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        ct = part.get_content_type()
                        if ct == "text/plain":
                            payload = part.get_payload(decode=True)
                            if payload:
                                body = payload.decode("utf-8", errors="replace")
                            break
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        body = payload.decode("utf-8", errors="replace")

                messages.append({
                    "id": mid.decode(),
                    "from": msg.get("From", ""),
                    "subject": msg.get("Subject", ""),
                    "date": msg.get("Date", ""),
                    "body": body,
                })

            conn.logout()
            return {"ok": True, "provider": "email", "data": messages}

        except Exception as exc:
            return {"ok": False, "provider": "email", "error": str(exc)}

"""
tests/test_communication_bridges.py
Тесты интеграционных модулей связи: Email, SMS, WebSocket, Web Scraper,
Aiogram, Socket Transport и расширенного MessengerRouter.
"""
import os
import sys
import socket
import time
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.connectivity.email_bridge import EmailBridge
from src.connectivity.sms_bridge import SMSBridge
from src.connectivity.websocket_bridge import WebSocketBridge
from src.connectivity.web_scraper import WebScraper
from src.connectivity.aiogram_bridge import AiogramBridge
from src.connectivity.socket_transport import SocketTransport
from src.connectivity.messenger_router import MessengerRouter


# ═══════════════════════════════════════════════════════
# EmailBridge
# ═══════════════════════════════════════════════════════

class TestEmailBridge(unittest.TestCase):
    def test_not_configured(self):
        bridge = EmailBridge(username="", password="")
        result = bridge.send_message("a@b.com", "subj", "body")
        self.assertFalse(result["ok"])
        self.assertEqual(result["provider"], "email")

    def test_fetch_not_configured(self):
        bridge = EmailBridge(username="", password="")
        result = bridge.fetch_messages()
        self.assertFalse(result["ok"])
        self.assertEqual(result["provider"], "email")

    @patch("src.connectivity.email_bridge.smtplib.SMTP_SSL")
    def test_send_ssl_success(self, mock_smtp):
        ctx = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=ctx)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

        bridge = EmailBridge(username="u@test.com", password="pass", use_ssl=True)
        result = bridge.send_message("to@test.com", "subject", "body")

        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "email")
        ctx.login.assert_called_once_with("u@test.com", "pass")
        ctx.sendmail.assert_called_once()

    @patch("src.connectivity.email_bridge.smtplib.SMTP_SSL")
    def test_send_ssl_failure(self, mock_smtp):
        mock_smtp.side_effect = ConnectionRefusedError("refused")
        bridge = EmailBridge(username="u@t.com", password="p", use_ssl=True)
        result = bridge.send_message("to@t.com", "s", "b")
        self.assertFalse(result["ok"])
        self.assertIn("refused", result["error"])

    @patch("src.connectivity.email_bridge.imaplib.IMAP4_SSL")
    def test_fetch_messages_success(self, mock_imap):
        conn = MagicMock()
        mock_imap.return_value = conn
        conn.search.return_value = ("OK", [b"1 2"])
        conn.fetch.return_value = (
            "OK",
            [(b"1", b"From: a@b.com\r\nSubject: hi\r\n\r\nHello")],
        )

        bridge = EmailBridge(username="u@t.com", password="p")
        result = bridge.fetch_messages(limit=2)

        self.assertTrue(result["ok"])
        self.assertIsInstance(result["data"], list)


# ═══════════════════════════════════════════════════════
# SMSBridge
# ═══════════════════════════════════════════════════════

class TestSMSBridge(unittest.TestCase):
    def test_not_configured(self):
        bridge = SMSBridge(api_key="")
        result = bridge.send_message("+70000000000", "hello")
        self.assertFalse(result["ok"])
        self.assertEqual(result["provider"], "sms")

    @patch("src.connectivity.sms_bridge._SMSMobileAPI")
    def test_send_success(self, mock_cls):
        mock_client = MagicMock()
        mock_client.send_sms.return_value = {"status": "sent"}
        mock_cls.return_value = mock_client

        with patch.dict(os.environ, {"SMSMOBILEAPI_KEY": ""}):
            bridge = SMSBridge(api_key="key123")
            bridge._client = mock_client
            result = bridge.send_message("+70000000000", "test")

        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "sms")
        mock_client.send_sms.assert_called_once_with("+70000000000", "test")

    @patch("src.connectivity.sms_bridge._SMSMobileAPI")
    def test_receive_success(self, mock_cls):
        mock_client = MagicMock()
        mock_client.get_sms.return_value = [{"from": "+7111", "text": "hi"}]
        mock_cls.return_value = mock_client

        bridge = SMSBridge(api_key="key123")
        bridge._client = mock_client
        result = bridge.receive_messages()

        self.assertTrue(result["ok"])
        mock_client.get_sms.assert_called_once()


# ═══════════════════════════════════════════════════════
# WebSocketBridge
# ═══════════════════════════════════════════════════════

class TestWebSocketBridge(unittest.TestCase):
    def test_available_returns_bool(self):
        bridge = WebSocketBridge()
        self.assertIsInstance(bridge.available(), bool)

    def test_defaults(self):
        bridge = WebSocketBridge()
        self.assertEqual(bridge.server_host, "0.0.0.0")
        self.assertEqual(bridge.server_port, 8765)


# ═══════════════════════════════════════════════════════
# WebScraper
# ═══════════════════════════════════════════════════════

class TestWebScraper(unittest.TestCase):
    def test_available_returns_bool(self):
        scraper = WebScraper()
        self.assertIsInstance(scraper.available(), bool)

    @patch("src.connectivity.web_scraper.requests.get")
    def test_fetch_success(self, mock_get):
        resp = MagicMock()
        resp.text = "<html><body>hello</body></html>"
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp

        scraper = WebScraper()
        result = scraper.fetch("https://example.com")

        self.assertTrue(result["ok"])
        self.assertIn("hello", result["data"])

    @patch("src.connectivity.web_scraper.requests.get")
    def test_fetch_failure(self, mock_get):
        mock_get.side_effect = ConnectionError("no network")
        scraper = WebScraper()
        result = scraper.fetch("https://example.com")
        self.assertFalse(result["ok"])
        self.assertIn("no network", result["error"])

    @patch("src.connectivity.web_scraper.requests.get")
    def test_scrape_with_selector(self, mock_get):
        resp = MagicMock()
        resp.text = '<html><body><a href="/link1">A</a><a href="/link2">B</a></body></html>'
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp

        scraper = WebScraper()
        result = scraper.scrape("https://example.com", selector="a", attr="href")

        self.assertTrue(result["ok"])
        self.assertEqual(result["data"], ["/link1", "/link2"])

    def test_parse_html(self):
        scraper = WebScraper()
        if scraper.available():
            soup = scraper.parse_html("<p>test</p>")
            self.assertEqual(soup.p.text, "test")


# ═══════════════════════════════════════════════════════
# AiogramBridge
# ═══════════════════════════════════════════════════════

class TestAiogramBridge(unittest.TestCase):
    def test_not_configured(self):
        bridge = AiogramBridge(token="")
        self.assertFalse(bridge._ready())

    def test_dispatcher_and_bot_properties(self):
        bridge = AiogramBridge(token="")
        # Without valid token, bot/dp might be None, but properties shouldn't crash
        _ = bridge.dispatcher
        _ = bridge.bot


# ═══════════════════════════════════════════════════════
# SocketTransport
# ═══════════════════════════════════════════════════════

class TestSocketTransport(unittest.TestCase):
    def test_tcp_server_and_client(self):
        transport = SocketTransport(host="127.0.0.1", port=0, protocol="tcp")
        # Use port 0 to let the OS assign a free port
        transport._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        transport._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        transport._server_sock.settimeout(1.0)
        transport._server_sock.bind(("127.0.0.1", 0))
        transport._server_sock.listen(5)
        actual_port = transport._server_sock.getsockname()[1]
        transport.port = actual_port
        transport._running = True

        import threading

        def _accept_loop():
            while transport._running and transport._server_sock:
                try:
                    conn, addr = transport._server_sock.accept()
                except (socket.timeout, OSError):
                    break
                data = conn.recv(4096)
                conn.sendall(b"echo:" + data)
                conn.close()

        t = threading.Thread(target=_accept_loop, daemon=True)
        t.start()

        result = transport.send_message("127.0.0.1", actual_port, "hello")
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"], "echo:hello")

        transport.stop_server()

    def test_udp_send(self):
        transport = SocketTransport(protocol="udp")
        # Sending UDP to loopback won't fail (fire-and-forget)
        result = transport.send_message("127.0.0.1", 19999, "ping")
        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "socket_udp")

    def test_start_stop_tcp_server(self):
        transport = SocketTransport(host="127.0.0.1", port=0, protocol="tcp")
        result = transport.start_server()
        self.assertTrue(result["ok"])
        transport.stop_server()

    def test_start_stop_udp_server(self):
        transport = SocketTransport(host="127.0.0.1", port=0, protocol="udp")
        result = transport.start_server()
        self.assertTrue(result["ok"])
        transport.stop_server()


# ═══════════════════════════════════════════════════════
# MessengerRouter (расширенный)
# ═══════════════════════════════════════════════════════

class TestMessengerRouterExtended(unittest.TestCase):
    def test_routes_to_email(self):
        router = MessengerRouter()
        with patch.object(router.email, "send_message", return_value={"ok": True}) as sender:
            result = router.route_message("email", "a@b.com", "hello")
        sender.assert_called_once_with(to="a@b.com", subject="Argos", body="hello")
        self.assertTrue(result["ok"])

    def test_routes_to_sms(self):
        router = MessengerRouter()
        with patch.object(router.sms, "send_message", return_value={"ok": True}) as sender:
            result = router.route_message("sms", "+70000000000", "hello")
        sender.assert_called_once_with(to="+70000000000", text="hello")
        self.assertTrue(result["ok"])

    def test_routes_to_telegram(self):
        router = MessengerRouter()
        with patch.object(router.telegram, "send_message_sync", return_value={"ok": True}) as sender:
            result = router.route_message("telegram", "12345", "hello")
        sender.assert_called_once_with(chat_id="12345", text="hello")
        self.assertTrue(result["ok"])

    def test_routes_to_tg_alias(self):
        router = MessengerRouter()
        with patch.object(router.telegram, "send_message_sync", return_value={"ok": True}) as sender:
            result = router.route_message("tg", "12345", "hello")
        sender.assert_called_once()
        self.assertTrue(result["ok"])

    def test_existing_routes_still_work(self):
        router = MessengerRouter()
        with patch.object(router.whatsapp, "send_message", return_value={"ok": True}):
            self.assertTrue(router.route_message("whatsapp", "+7", "hi")["ok"])
        with patch.object(router.slack, "send_message", return_value={"ok": True}):
            self.assertTrue(router.route_message("slack", "#ch", "hi")["ok"])
        with patch.object(router.max, "send_message", return_value={"ok": True}):
            self.assertTrue(router.route_message("max", "42", "hi")["ok"])

    def test_unsupported_still_returns_error(self):
        router = MessengerRouter()
        result = router.route_message("unknown_service", "id", "hi")
        self.assertFalse(result["ok"])

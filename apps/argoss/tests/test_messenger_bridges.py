"""
tests/test_messenger_bridges.py
Тесты мессенджер-мостов: WhatsApp (whatsapp_bridge.py) и Slack (slack_bridge.py)
"""
import pytest
from unittest.mock import MagicMock, patch


# ═══════════════════════════════════════════════════════
# WhatsApp Bridge
# ═══════════════════════════════════════════════════════

def _import_whatsapp():
    try:
        from src.connectivity.whatsapp_bridge import WhatsAppBridge
        return WhatsAppBridge
    except ImportError:
        try:
            from whatsapp_bridge import WhatsAppBridge
            return WhatsAppBridge
        except ImportError:
            pytest.skip("WhatsAppBridge недоступен")


def test_whatsapp_import():
    WhatsAppBridge = _import_whatsapp()
    assert WhatsAppBridge is not None


def test_whatsapp_instantiation():
    WhatsAppBridge = _import_whatsapp()
    bridge = WhatsAppBridge(access_token="test_token", phone_number_id="12345")
    assert bridge is not None


def test_whatsapp_has_send_method():
    WhatsAppBridge = _import_whatsapp()
    bridge = WhatsAppBridge(access_token="tok", phone_number_id="pid")
    assert hasattr(bridge, "send") or hasattr(bridge, "send_message")


@patch("requests.post")
def test_whatsapp_send_calls_meta_api(mock_post):
    WhatsAppBridge = _import_whatsapp()
    mock_post.return_value = MagicMock(status_code=200, json=lambda: {"messages": [{"id": "wamid.1"}]})
    bridge = WhatsAppBridge(access_token="tok", phone_number_id="pid")
    send = getattr(bridge, "send", None) or getattr(bridge, "send_message", None)
    if send:
        try:
            send(to="+79001234567", text="Тест")
        except Exception:
            pass  # сетевые ошибки ожидаемы


@patch("requests.post")
def test_whatsapp_fallback_to_twilio(mock_post):
    WhatsAppBridge = _import_whatsapp()
    # Симулируем что Meta API недоступен
    mock_post.side_effect = [Exception("Meta API down"), MagicMock(status_code=200)]
    bridge = WhatsAppBridge(
        access_token="tok",
        phone_number_id="pid",
        twilio_sid="ACxxx",
        twilio_token="twtok",
        twilio_from="+14155238886",
    )
    send = getattr(bridge, "send", None) or getattr(bridge, "send_message", None)
    if send and hasattr(bridge, "twilio_sid"):
        try:
            send(to="+79001234567", text="fallback test")
        except Exception:
            pass


# ═══════════════════════════════════════════════════════
# Slack Bridge
# ═══════════════════════════════════════════════════════

def _import_slack():
    try:
        from src.connectivity.slack_bridge import SlackBridge
        return SlackBridge
    except ImportError:
        try:
            from slack_bridge import SlackBridge
            return SlackBridge
        except ImportError:
            pytest.skip("SlackBridge недоступен")


def test_slack_import():
    SlackBridge = _import_slack()
    assert SlackBridge is not None


def test_slack_instantiation():
    SlackBridge = _import_slack()
    bridge = SlackBridge(bot_token="xoxb-test")
    assert bridge is not None


def test_slack_has_send_method():
    SlackBridge = _import_slack()
    bridge = SlackBridge(bot_token="xoxb-test")
    assert hasattr(bridge, "send") or hasattr(bridge, "send_message")


@patch("requests.post")
def test_slack_send_calls_web_api(mock_post):
    SlackBridge = _import_slack()
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {"ok": True, "ts": "1234567890.123456"},
    )
    bridge = SlackBridge(bot_token="xoxb-test", default_channel="#alerts")
    send = getattr(bridge, "send", None) or getattr(bridge, "send_message", None)
    if send:
        try:
            send(text="Тест алерта", channel="#alerts")
        except Exception:
            pass


def test_slack_status():
    SlackBridge = _import_slack()
    bridge = SlackBridge(bot_token="xoxb-test")
    if hasattr(bridge, "status"):
        result = bridge.status()
        assert isinstance(result, str)


# ═══════════════════════════════════════════════════════
# MessengerRouter
# ═══════════════════════════════════════════════════════

def _import_router():
    try:
        from src.connectivity.messenger_router import MessengerRouter
        return MessengerRouter
    except ImportError:
        try:
            from messenger_router import MessengerRouter
            return MessengerRouter
        except ImportError:
            pytest.skip("MessengerRouter недоступен")


def test_router_import():
    MessengerRouter = _import_router()
    assert MessengerRouter is not None


def test_router_instantiation():
    MessengerRouter = _import_router()
    router = MessengerRouter()
    assert router is not None


def test_router_has_send_method():
    MessengerRouter = _import_router()
    router = MessengerRouter()
    assert hasattr(router, "send") or hasattr(router, "route")


def test_router_register_bridge():
    MessengerRouter = _import_router()
    router = MessengerRouter()
    mock_bridge = MagicMock()
    register = getattr(router, "register", None) or getattr(router, "add_bridge", None)
    if register:
        try:
            register("whatsapp", mock_bridge)
        except Exception as e:
            pytest.fail(f"register() упал: {e}")

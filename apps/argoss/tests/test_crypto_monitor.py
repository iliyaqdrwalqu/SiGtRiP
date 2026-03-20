"""
tests/test_crypto_monitor.py
Тесты модуля CryptoSentinel (crypto_monitor.py)
"""
import time
import threading
from unittest.mock import MagicMock, patch
from crypto_monitor import CryptoSentinel


# ── Fixtures ──────────────────────────────────────────────────────────────────

FAKE_PRICES = {
    "bitcoin":  {"usd": 65000.0, "usd_24h_change":  6.5},
    "ethereum": {"usd":  3200.0, "usd_24h_change": -2.1},
}

FAKE_PRICES_CALM = {
    "bitcoin":  {"usd": 64000.0, "usd_24h_change":  1.0},
    "ethereum": {"usd":  3100.0, "usd_24h_change": -0.5},
}


def _sentinel(bot=None):
    return CryptoSentinel(telegram_bot=bot)


# ── get_prices ────────────────────────────────────────────────────────────────

@patch("crypto_monitor.requests.get")
def test_get_prices_ok(mock_get):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: FAKE_PRICES,
        raise_for_status=lambda: None,
    )
    s = _sentinel()
    prices = s.get_prices()
    assert "bitcoin" in prices
    assert prices["bitcoin"]["price"] == 65000.0
    assert prices["bitcoin"]["change"] == 6.5


@patch("crypto_monitor.requests.get", side_effect=Exception("timeout"))
def test_get_prices_network_error(mock_get):
    s = _sentinel()
    prices = s.get_prices()
    assert prices == {}


# ── check / alerts ────────────────────────────────────────────────────────────

@patch("crypto_monitor.requests.get")
def test_check_returns_alert_on_big_move(mock_get):
    mock_get.return_value = MagicMock(
        json=lambda: FAKE_PRICES,
        raise_for_status=lambda: None,
    )
    s = _sentinel()
    alerts = s.check()
    # BTC изменился на 6.5% > порог 5% → должен быть алерт
    assert len(alerts) == 1
    assert "BTC" in alerts[0]
    assert "РОСТ" in alerts[0]


@patch("crypto_monitor.requests.get")
def test_check_no_alert_on_small_move(mock_get):
    mock_get.return_value = MagicMock(
        json=lambda: FAKE_PRICES_CALM,
        raise_for_status=lambda: None,
    )
    s = _sentinel()
    alerts = s.check()
    assert alerts == []


# ── report ────────────────────────────────────────────────────────────────────

@patch("crypto_monitor.requests.get")
def test_report_contains_symbols(mock_get):
    mock_get.return_value = MagicMock(
        json=lambda: FAKE_PRICES,
        raise_for_status=lambda: None,
    )
    s = _sentinel()
    rpt = s.report()
    assert "BTC" in rpt
    assert "ETH" in rpt
    assert "$" in rpt


@patch("crypto_monitor.requests.get", side_effect=Exception("err"))
def test_report_on_error(mock_get):
    s = _sentinel()
    rpt = s.report()
    assert "недоступен" in rpt


# ── _send_alert / Telegram integration ───────────────────────────────────────

def test_send_alert_no_bot():
    """Без бота не должно бросать исключение."""
    s = _sentinel(bot=None)
    s._send_alert("тест")  # не должно кидать


def test_send_alert_via_send_message():
    bot = MagicMock(spec=["send_message"])
    s = _sentinel(bot=bot)
    s._send_alert("🪙 BTC АЛЕРТ")
    bot.send_message.assert_called_once_with("🪙 BTC АЛЕРТ")


def test_send_alert_via_send():
    bot = MagicMock(spec=["send"])
    s = _sentinel(bot=bot)
    s._send_alert("🪙 ETH АЛЕРТ")
    bot.send.assert_called_once_with("🪙 ETH АЛЕРТ")


def test_send_alert_via_notify():
    bot = MagicMock(spec=["notify"])
    s = _sentinel(bot=bot)
    s._send_alert("msg")
    bot.notify.assert_called_once_with("msg")


def test_send_alert_telegram_exception_handled():
    """Ошибка отправки не должна крашить процесс."""
    bot = MagicMock()
    bot.send_message.side_effect = Exception("network down")
    s = _sentinel(bot=bot)
    s._send_alert("msg")  # не должно кидать


# ── start_loop / stop ─────────────────────────────────────────────────────────

@patch("crypto_monitor.requests.get")
def test_start_loop_returns_status(mock_get):
    mock_get.return_value = MagicMock(
        json=lambda: FAKE_PRICES_CALM,
        raise_for_status=lambda: None,
    )
    s = _sentinel()
    msg = s.start_loop(interval_sec=9999)
    assert "Крипто-Страж запущен" in msg
    assert "не подключён" in msg
    s.stop()


@patch("crypto_monitor.requests.get")
def test_start_loop_with_bot_shows_connected(mock_get):
    mock_get.return_value = MagicMock(
        json=lambda: FAKE_PRICES_CALM,
        raise_for_status=lambda: None,
    )
    bot = MagicMock(spec=["send_message"])
    s = _sentinel(bot=bot)
    msg = s.start_loop(interval_sec=9999)
    assert "подключён" in msg
    s.stop()


@patch("crypto_monitor.requests.get")
def test_stop_sets_running_false(mock_get):
    mock_get.return_value = MagicMock(
        json=lambda: FAKE_PRICES_CALM,
        raise_for_status=lambda: None,
    )
    s = _sentinel()
    s.start_loop(interval_sec=9999)
    assert s._running is True
    s.stop()
    assert s._running is False


# ── threshold customisation ───────────────────────────────────────────────────

@patch("crypto_monitor.requests.get")
def test_custom_threshold(mock_get):
    mock_get.return_value = MagicMock(
        json=lambda: FAKE_PRICES,   # BTC +6.5%, ETH -2.1%
        raise_for_status=lambda: None,
    )
    s = _sentinel()
    s.threshold = 10.0  # выше чем оба изменения
    alerts = s.check()
    assert alerts == []

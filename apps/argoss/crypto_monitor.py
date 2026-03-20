"""
crypto_monitor.py — Крипто-Страж
  Мониторинг BTC/ETH каждый час, алерт в Telegram при изменении > 5%
"""
import requests
import time
import threading
import logging

logger = logging.getLogger("argos.crypto")


class CryptoSentinel:
    API_URL = "https://api.coingecko.com/api/v3/simple/price"
    COINS   = ["bitcoin", "ethereum"]
    SYMBOLS = {"bitcoin": "BTC", "ethereum": "ETH"}

    def __init__(self, telegram_bot=None):
        self.bot       = telegram_bot   # ArgosTelegram instance
        self.prev      = {}
        self.threshold = 5.0            # % изменения для алерта
        self._running  = False

    def _send_alert(self, msg: str) -> None:
        """Отправляет алерт — в Telegram если бот подключён, иначе в лог."""
        logger.warning("[CRYPTO-SENTINEL] %s", msg)
        if self.bot is None:
            return
        # Поддержка разных интерфейсов ArgosTelegram
        try:
            if hasattr(self.bot, "send_message"):
                self.bot.send_message(msg)
            elif hasattr(self.bot, "send"):
                self.bot.send(msg)
            elif hasattr(self.bot, "notify"):
                self.bot.notify(msg)
            else:
                logger.warning(
                    "[CRYPTO-SENTINEL] telegram_bot не имеет метода send/send_message/notify"
                )
        except Exception as exc:
            logger.error("[CRYPTO-SENTINEL] Ошибка отправки в Telegram: %s", exc)

    def get_prices(self) -> dict:
        try:
            params = {
                "ids": ",".join(self.COINS),
                "vs_currencies": "usd",
                "include_24hr_change": "true",
            }
            r = requests.get(self.API_URL, params=params, timeout=8)
            r.raise_for_status()
            data = r.json()
            return {
                coin: {
                    "price":  data[coin]["usd"],
                    "change": data[coin].get("usd_24h_change", 0.0),
                }
                for coin in self.COINS
                if coin in data
            }
        except Exception as exc:
            logger.error("[CRYPTO-SENTINEL] get_prices error: %s", exc)
            return {}

    def check(self) -> list[str]:
        """Возвращает список алертов (пустой если всё тихо)."""
        current = self.get_prices()
        alerts  = []

        for coin, info in current.items():
            change = info.get("change", 0.0)
            sym    = self.SYMBOLS[coin]
            price  = info["price"]

            if abs(change) >= self.threshold:
                direction = "📈 РОСТ" if change > 0 else "📉 ПАДЕНИЕ"
                alerts.append(
                    f"🪙 {sym} АЛЕРТ\n"
                    f"{direction}: {change:+.2f}%\n"
                    f"Цена: ${price:,.2f}"
                )

        self.prev = current
        return alerts

    def report(self) -> str:
        """Разовый отчёт по текущим ценам."""
        prices = self.get_prices()
        if not prices:
            return "❌ CoinGecko недоступен."
        lines = ["🪙 КРИПТО-РЫНОК:"]
        for coin, info in prices.items():
            sym = self.SYMBOLS[coin]
            lines.append(
                f"  {sym}: ${info['price']:,.2f}  ({info['change']:+.2f}% за 24ч)"
            )
        return "\n".join(lines)

    def start_loop(self, interval_sec: int = 3600):
        """Фоновый мониторинг в отдельном потоке."""
        self._running = True

        def _loop():
            while self._running:
                try:
                    alerts = self.check()
                    for msg in alerts:
                        self._send_alert(msg)
                except Exception as exc:
                    logger.error("[CRYPTO-SENTINEL] loop error: %s", exc)
                time.sleep(interval_sec)

        threading.Thread(target=_loop, daemon=True, name="crypto-sentinel").start()
        return (
            f"Крипто-Страж запущен. "
            f"Интервал: {interval_sec // 60} мин. "
            f"Порог: {self.threshold}%. "
            f"Telegram: {'подключён ✅' if self.bot else 'не подключён ⚠️'}"
        )

    def stop(self):
        self._running = False
        return "Крипто-Страж остановлен."

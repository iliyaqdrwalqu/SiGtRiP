"""
web_scraper.py — Модуль веб-скрапинга Аргоса (Requests + Beautiful Soup).
"""
from __future__ import annotations

import os
from typing import Any

import requests

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    BeautifulSoup = None  # type: ignore[assignment,misc]


class WebScraper:
    """Загружает веб-страницы через requests и парсит их Beautiful Soup."""

    def __init__(
        self,
        default_timeout: float = 15.0,
        user_agent: str | None = None,
    ):
        self.timeout = default_timeout
        self.user_agent = user_agent or os.getenv(
            "ARGOS_USER_AGENT",
            "ArgosBot/2.1 (+https://github.com/ArkMaster-ARGOS)",
        )

    @staticmethod
    def available() -> bool:
        """True если beautifulsoup4 установлен."""
        return BeautifulSoup is not None

    # ── загрузка ──────────────────────────────────────────────────────
    def fetch(self, url: str, **kwargs: Any) -> dict[str, Any]:
        """GET-запрос и возврат HTML."""
        headers = {"User-Agent": self.user_agent}
        headers.update(kwargs.pop("headers", {}))
        try:
            resp = requests.get(url, headers=headers, timeout=self.timeout, **kwargs)
            resp.raise_for_status()
            return {"ok": True, "provider": "web_scraper", "data": resp.text, "status": resp.status_code}
        except Exception as exc:
            return {"ok": False, "provider": "web_scraper", "error": str(exc)}

    # ── парсинг ───────────────────────────────────────────────────────
    def parse_html(self, html: str, parser: str = "html.parser") -> Any:
        """Вернуть BeautifulSoup-объект для дальнейшего разбора."""
        if BeautifulSoup is None:
            raise RuntimeError("beautifulsoup4 is not installed")
        return BeautifulSoup(html, parser)

    # ── универсальный метод ───────────────────────────────────────────
    def scrape(
        self,
        url: str,
        selector: str | None = None,
        attr: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """
        Загрузить страницу и извлечь данные CSS-селектором.

        Параметры:
            url      — целевой URL
            selector — CSS-селектор (если None — вернуть весь текст)
            attr     — атрибут элемента (href, src и т.п.)
            limit    — максимум результатов
        """
        result = self.fetch(url)
        if not result["ok"]:
            return result

        if BeautifulSoup is None:
            return {"ok": False, "provider": "web_scraper", "error": "beautifulsoup4 is not installed"}

        soup = BeautifulSoup(result["data"], "html.parser")

        if selector is None:
            return {"ok": True, "provider": "web_scraper", "data": soup.get_text(separator="\n", strip=True)}

        elements = soup.select(selector, limit=limit)
        if attr:
            items = [el.get(attr, "") for el in elements]
        else:
            items = [el.get_text(strip=True) for el in elements]

        return {"ok": True, "provider": "web_scraper", "data": items}

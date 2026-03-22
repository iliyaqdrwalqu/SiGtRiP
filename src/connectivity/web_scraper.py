"""
src/connectivity/web_scraper.py — Веб-скрапер ARGOS
Requests + Beautiful Soup 4
"""
from __future__ import annotations

import os
from typing import Any

import requests

try:
    from bs4 import BeautifulSoup
    _BS4 = True
except ImportError:
    _BS4 = False


class WebScraper:
    """
    Скрапер на базе Requests + BeautifulSoup4.

    Использование:
        scraper = WebScraper()
        # Получить HTML:
        result = scraper.fetch("https://example.com")
        # Извлечь атрибуты элементов:
        result = scraper.scrape("https://example.com", selector="a", attr="href")
        # Поиск по CSS-селектору, вернуть текст:
        result = scraper.find_text("https://example.com", selector="h1")
    """

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; ArgosBot/2.1; "
            "+https://github.com/iliyaqdrwalqu/SiGtRiP)"
        )
    }

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(self.DEFAULT_HEADERS)

    def available(self) -> bool:
        return _BS4

    def parse_html(self, html: str) -> "BeautifulSoup":
        if not _BS4:
            raise ImportError("pip install beautifulsoup4")
        return BeautifulSoup(html, "html.parser")

    # ── Основные методы ───────────────────────────────────────────────────────

    def fetch(self, url: str) -> dict:
        """Скачать страницу, вернуть {"ok": bool, "data": text}"""
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            # Извлекаем только видимый текст если есть bs4
            if _BS4:
                soup = BeautifulSoup(resp.text, "html.parser")
                # убираем скрипты и стили
                for tag in soup(["script", "style"]):
                    tag.decompose()
                text = soup.get_text(separator=" ", strip=True)
            else:
                text = resp.text
            return {"ok": True, "provider": "web_scraper", "data": text, "url": url}
        except requests.HTTPError as exc:
            return {"ok": False, "provider": "web_scraper", "error": f"HTTP {exc.response.status_code}"}
        except Exception as exc:
            return {"ok": False, "provider": "web_scraper", "error": str(exc)}

    def scrape(self, url: str, selector: str = "a", attr: str | None = None) -> dict:
        """
        Найти элементы по CSS-селектору.
        attr=None → вернуть текст элементов
        attr="href" → вернуть значения атрибута
        """
        if not _BS4:
            return {"ok": False, "provider": "web_scraper", "error": "pip install beautifulsoup4"}
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            elements = soup.select(selector)
            if attr:
                data = [el.get(attr, "") for el in elements if el.get(attr)]
            else:
                data = [el.get_text(strip=True) for el in elements if el.get_text(strip=True)]
            return {"ok": True, "provider": "web_scraper", "data": data}
        except Exception as exc:
            return {"ok": False, "provider": "web_scraper", "error": str(exc)}

    def find_text(self, url: str, selector: str) -> dict:
        """Найти первый элемент и вернуть его текст."""
        if not _BS4:
            return {"ok": False, "error": "pip install beautifulsoup4"}
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            el = soup.select_one(selector)
            return {"ok": True, "data": el.get_text(strip=True) if el else ""}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def status(self) -> str:
        bs4_ok = "✅" if _BS4 else "❌ (pip install beautifulsoup4)"
        return f"🕷️ WebScraper: requests ✅  BeautifulSoup4 {bs4_ok}"

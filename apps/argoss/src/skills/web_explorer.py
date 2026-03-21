"""
web_explorer.py — Бесплатный интернет-разведчик Аргоса.

Использует ТОЛЬКО бесплатные источники без API-ключей:
  • DuckDuckGo HTML — основной поиск
  • Wikipedia API   — энциклопедические знания
  • GitHub Search   — код и проекты (публичные репозитории)
  • arXiv API       — научные статьи
  • Прямой fetch    — любой URL с извлечением текста

Интегрируется с памятью Аргоса: выученные факты сохраняются в SQLite.
"""
from __future__ import annotations

import re
import time
import json
import threading
from typing import Optional
from urllib.parse import quote_plus, urlparse
from src.argos_logger import get_logger

log = get_logger("argos.web_explorer")

try:
    import requests
    _REQUESTS_OK = True
except ImportError:
    requests = None  # type: ignore
    _REQUESTS_OK = False

try:
    from bs4 import BeautifulSoup
    _BS4_OK = True
except ImportError:
    BeautifulSoup = None  # type: ignore
    _BS4_OK = False

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}

_DEFAULT_TIMEOUT = 12


def _get(url: str, params: dict | None = None, timeout: int = _DEFAULT_TIMEOUT) -> Optional[requests.Response]:
    """Безопасный GET-запрос с таймаутом."""
    if not _REQUESTS_OK:
        return None
    try:
        return requests.get(url, params=params, headers=_HEADERS, timeout=timeout)
    except Exception as e:
        log.debug("_get %s: %s", url, e)
        return None


def _extract_text(html: str, max_chars: int = 2000) -> str:
    """Извлекает чистый текст из HTML."""
    if not _BS4_OK or not html:
        return re.sub(r"<[^>]+>", " ", html)[:max_chars]
    soup = BeautifulSoup(html, "html.parser")
    # Удаляем скрипты, стили, навигацию
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    # Убираем лишние пробелы
    text = re.sub(r"\s{2,}", " ", text)
    return text[:max_chars]


class ArgosWebExplorer:
    """
    Бесплатный интернет-разведчик Аргоса.
    Все методы работают без API-ключей и денег.
    """

    def __init__(self, memory=None):
        """
        memory — экземпляр ArgosMemory для сохранения выученных фактов.
        """
        self.memory = memory
        self._lock = threading.Lock()
        self._search_count = 0
        self._last_search_ts = 0.0
        self._rate_limit_sec = 1.5  # минимум между запросами (не спамим)

    def _throttle(self):
        with self._lock:
            elapsed = time.time() - self._last_search_ts
            if elapsed < self._rate_limit_sec:
                time.sleep(self._rate_limit_sec - elapsed)
            self._last_search_ts = time.time()
            self._search_count += 1

    # ── 1. DUCKDUCKGO ПОИСК ───────────────────────────────

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        """
        Бесплатный поиск через DuckDuckGo HTML.
        Возвращает список {'title': ..., 'snippet': ..., 'url': ...}
        """
        if not _REQUESTS_OK or not _BS4_OK:
            return [{"title": "Ошибка", "snippet": "requests/beautifulsoup4 не установлены", "url": ""}]

        self._throttle()
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        resp = _get(url)
        if not resp or resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        results = []

        for block in soup.select(".result")[:max_results * 2]:
            title_el = block.select_one(".result__title")
            snip_el  = block.select_one(".result__snippet") or block.select_one(".result__body")
            link_el  = block.select_one(".result__url") or block.select_one("a.result__a")

            title   = title_el.get_text(strip=True) if title_el else ""
            snippet = snip_el.get_text(separator=" ", strip=True) if snip_el else ""
            href    = ""
            if link_el:
                href = link_el.get("href", "") or link_el.get_text(strip=True)

            if title or snippet:
                results.append({"title": title, "snippet": snippet, "url": href})
            if len(results) >= max_results:
                break

        log.info("DuckDuckGo: '%s' → %d результатов", query[:50], len(results))
        return results

    def quick_search(self, query: str) -> str:
        """Быстрый поиск — возвращает одну строку с результатами."""
        results = self.search(query, max_results=3)
        if not results:
            return "Поиск не дал результатов."
        parts = []
        for r in results:
            snippet = r["snippet"] or r["title"]
            if snippet:
                parts.append(snippet[:300])
        return " | ".join(parts) if parts else "Результатов не найдено."

    # ── 2. WIKIPEDIA (БЕСПЛАТНЫЙ API) ────────────────────

    def wikipedia_search(self, query: str, lang: str = "ru") -> str:
        """
        Ищет статью в Википедии через бесплатный API.
        Возвращает краткое резюме первой найденной статьи.
        """
        self._throttle()

        # Поиск подходящей страницы
        search_url = f"https://{lang}.wikipedia.org/w/api.php"
        resp = _get(search_url, params={
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": 3,
            "format": "json",
            "utf8": 1,
        })
        if not resp or not resp.ok:
            return ""

        data = resp.json()
        hits = (data.get("query") or {}).get("search") or []
        if not hits:
            return ""

        # Берём первый результат
        page_title = hits[0]["title"]
        self._throttle()

        # Получаем экстракт (краткое содержание)
        extract_resp = _get(search_url, params={
            "action": "query",
            "prop": "extracts",
            "exintro": True,
            "explaintext": True,
            "titles": page_title,
            "format": "json",
            "utf8": 1,
        })
        if not extract_resp or not extract_resp.ok:
            return ""

        pages = (extract_resp.json().get("query") or {}).get("pages") or {}
        for page in pages.values():
            extract = (page.get("extract") or "").strip()
            if extract:
                # Отрезаем первые 600 символов
                short = re.sub(r"\s{2,}", " ", extract)[:600]
                log.info("Wikipedia: '%s' → %d симв.", page_title, len(short))
                return f"[Wikipedia: {page_title}] {short}"
        return ""

    # ── 3. GITHUB ПОИСК (ПУБЛИЧНЫЕ РЕПОЗИТОРИИ) ──────────

    def search_github(self, query: str, max_results: int = 3) -> str:
        """
        Ищет публичные репозитории GitHub без API-ключа.
        Лимит: 10 запросов/минуту неавторизованно.
        """
        self._throttle()
        resp = _get("https://api.github.com/search/repositories", params={
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": max_results,
        }, timeout=10)

        if not resp or not resp.ok:
            return ""

        items = resp.json().get("items") or []
        if not items:
            return ""

        lines = [f"[GitHub поиск: {query}]"]
        for item in items[:max_results]:
            name  = item.get("full_name", "")
            desc  = item.get("description", "") or ""
            stars = item.get("stargazers_count", 0)
            url   = item.get("html_url", "")
            lines.append(f"  ★{stars} {name} — {desc[:120]} | {url}")

        result = "\n".join(lines)
        log.info("GitHub: '%s' → %d репо", query[:40], len(items))
        return result

    # ── 4. ARXIV (НАУЧНЫЕ СТАТЬИ БЕСПЛАТНО) ──────────────

    def search_arxiv(self, query: str, max_results: int = 3) -> str:
        """
        Ищет научные статьи на arXiv.org через бесплатный API.
        Идеально для технических тем: ИИ, квантовые вычисления, etc.
        """
        self._throttle()
        resp = _get("https://export.arxiv.org/api/query", params={
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": max_results,
        }, timeout=15)

        if not resp or not resp.ok:
            return ""

        # Простой парсинг Atom XML
        entries = re.findall(
            r"<entry>(.*?)</entry>", resp.text, re.DOTALL
        )
        if not entries:
            return ""

        lines = [f"[arXiv: {query}]"]
        for entry in entries[:max_results]:
            title   = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
            summary = re.search(r"<summary>(.*?)</summary>", entry, re.DOTALL)
            link    = re.search(r'href="(https://arxiv[^"]+)"', entry)

            t = title.group(1).strip().replace("\n", " ") if title else "?"
            s = summary.group(1).strip().replace("\n", " ")[:200] if summary else ""
            l = link.group(1) if link else ""
            lines.append(f"  📄 {t}\n     {s} | {l}")

        result = "\n".join(lines)
        log.info("arXiv: '%s' → %d статей", query[:40], len(entries))
        return result

    # ── 5. ПРЯМОЙ FETCH СТРАНИЦЫ ──────────────────────────

    def fetch_page(self, url: str, max_chars: int = 3000) -> str:
        """
        Загружает произвольную страницу и возвращает её текст.
        Безопасно: только GET, только текст, без JS.
        """
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return "⚠️ Только HTTP/HTTPS ссылки поддерживаются."
        except Exception:
            return "⚠️ Некорректный URL."

        self._throttle()
        resp = _get(url, timeout=15)
        if not resp:
            return "⚠️ Не удалось загрузить страницу."
        if not resp.ok:
            return f"⚠️ HTTP {resp.status_code}"

        content_type = resp.headers.get("content-type", "")
        if "text" not in content_type and "html" not in content_type:
            return f"⚠️ Не текстовый контент: {content_type}"

        text = _extract_text(resp.text, max_chars=max_chars)
        log.info("fetch_page: %s → %d симв.", url[:60], len(text))
        return text or "Страница пуста."

    # ── 6. УМНОЕ ОБУЧЕНИЕ (learn) ─────────────────────────

    def learn(self, query: str, save_to_memory: bool = True) -> str:
        """
        Аргос «учится» по теме: ищет в нескольких источниках,
        объединяет результаты и сохраняет в память.

        Это главный метод для «самообразования» Аргоса.
        """
        log.info("WebExplorer.learn: '%s'", query[:60])
        parts = []

        # 1. Wikipedia — базовые знания
        wiki = self.wikipedia_search(query)
        if wiki:
            parts.append(wiki)

        # 2. DuckDuckGo — свежие данные
        ddg_results = self.search(query, max_results=3)
        if ddg_results:
            ddg_texts = [
                f"  • {r['title']}: {r['snippet'][:200]}"
                for r in ddg_results if r.get("snippet")
            ]
            if ddg_texts:
                parts.append("[Поиск DuckDuckGo]\n" + "\n".join(ddg_texts))

        # 3. arXiv — если тема техническая
        tech_keywords = (
            "ии", "нейросеть", "модель", "алгоритм", "квантов",
            "ai", "neural", "model", "algorithm", "quantum", "llm",
        )
        if any(kw in query.lower() for kw in tech_keywords):
            arxiv = self.search_arxiv(query, max_results=2)
            if arxiv:
                parts.append(arxiv)

        if not parts:
            return f"⚠️ Не удалось найти информацию по теме: «{query}»"

        knowledge = "\n\n".join(parts)

        # Сохраняем в память Аргоса
        if save_to_memory and self.memory:
            try:
                key = f"web_learn:{query[:50].replace(' ', '_')}"
                self.memory.remember(
                    key=key,
                    value=knowledge[:1000],
                    category="web_knowledge",
                )
                log.info("Сохранено в память: %s", key)
            except Exception as e:
                log.warning("learn save_memory: %s", e)

        return f"🌐 Аргос изучил: «{query}»\n\n{knowledge}"

    # ── СТАТИСТИКА ────────────────────────────────────────

    def status(self) -> str:
        return (
            f"🌐 WEB EXPLORER:\n"
            f"  Запросов выполнено: {self._search_count}\n"
            f"  Источники: DuckDuckGo, Wikipedia, GitHub, arXiv\n"
            f"  Ключи API: не нужны (всё бесплатно)\n"
            f"  requests: {'✅' if _REQUESTS_OK else '❌'} | "
            f"bs4: {'✅' if _BS4_OK else '❌'}"
        )

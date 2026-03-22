"""
src/ai_router.py — Автопереключение между AI провайдерами.
Порядок: Gemini → Groq → DeepSeek → GigaChat → YandexGPT → WatsonX → xAI Grok → Ollama
"""
from __future__ import annotations
import os
import time
import logging

log = logging.getLogger("argos.ai_router")

# Cooldown в секундах после ошибки провайдера
_COOLDOWN = int(os.getenv("ARGOS_PROVIDER_COOLDOWN", "60"))

# Состояние провайдеров: {name: last_fail_time}
_provider_state: dict[str, float] = {}


def _is_available(name: str) -> bool:
    """Провайдер доступен если не было ошибки или cooldown истёк."""
    last_fail = _provider_state.get(name, 0)
    return (time.time() - last_fail) > _COOLDOWN


def _mark_failed(name: str) -> None:
    _provider_state[name] = time.time()
    log.warning(f"[AI Router] {name} недоступен — cooldown {_COOLDOWN}s")


def _mark_ok(name: str) -> None:
    _provider_state.pop(name, None)


class AIRouter:
    """Роутер запросов между AI провайдерами с автофallback."""

    # Порядок приоритетов
    PROVIDERS = [
        "gemini",
        "groq",
        "deepseek",
        "gigachat",
        "yandexgpt",
        "watsonx",
        "xai",
        "ollama",
    ]

    def __init__(self, core=None):
        self.core = core

    def ask(self, prompt: str, system: str = "") -> str | None:
        """Отправить запрос — автоматически выбирает доступного провайдера."""
        for provider in self.PROVIDERS:
            if not _is_available(provider):
                continue
            result = self._try_provider(provider, prompt, system)
            if result:
                _mark_ok(provider)
                return result
        log.error("[AI Router] Все провайдеры недоступны")
        return None

    def _try_provider(self, name: str, prompt: str, system: str) -> str | None:
        try:
            method = getattr(self, f"_ask_{name}", None)
            if method:
                return method(prompt, system)
        except Exception as e:
            log.warning(f"[AI Router] {name} ошибка: {e}")
            _mark_failed(name)
        return None

    # ── Провайдеры ────────────────────────────────────────────────────────────

    def _ask_gemini(self, prompt: str, system: str) -> str | None:
        key = os.getenv("GEMINI_API_KEY", "")
        if not key or key in ("", "your_key_here"):
            return None
        try:
            import google.generativeai as genai
            genai.configure(api_key=key)
            model = genai.GenerativeModel("gemini-2.0-flash-exp")
            full = f"{system}\n\n{prompt}" if system else prompt
            resp = model.generate_content(full)
            return resp.text
        except Exception as e:
            raise RuntimeError(f"Gemini: {e}")

    def _ask_groq(self, prompt: str, system: str) -> str | None:
        key = os.getenv("GROQ_API_KEY", "")
        if not key:
            return None
        try:
            import requests
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json={"model": "llama-3.3-70b-versatile", "messages": messages},
                timeout=30,
            )
            if resp.status_code == 429:
                raise RuntimeError("Rate limit")
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            raise RuntimeError(f"Groq: {e}")

    def _ask_deepseek(self, prompt: str, system: str) -> str | None:
        key = os.getenv("DEEPSEEK_API_KEY", "")
        if not key:
            return None
        try:
            import requests
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            resp = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers=headers,
                json={"model": "deepseek-chat", "messages": messages},
                timeout=30,
            )
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            raise RuntimeError(f"DeepSeek: {e}")

    def _ask_gigachat(self, prompt: str, system: str) -> str | None:
        if not self.core:
            return None
        try:
            return self.core._ask_gigachat(system, prompt)
        except Exception as e:
            raise RuntimeError(f"GigaChat: {e}")

    def _ask_yandexgpt(self, prompt: str, system: str) -> str | None:
        if not self.core:
            return None
        try:
            return self.core._ask_yandexgpt(system, prompt)
        except Exception as e:
            raise RuntimeError(f"YandexGPT: {e}")

    def _ask_watsonx(self, prompt: str, system: str) -> str | None:
        key = os.getenv("WATSONX_API_KEY", "")
        if not key:
            return None
        try:
            if self.core and hasattr(self.core, "_ask_watsonx"):
                return self.core._ask_watsonx(system, prompt)
        except Exception as e:
            raise RuntimeError(f"WatsonX: {e}")
        return None

    def _ask_xai(self, prompt: str, system: str) -> str | None:
        key = os.getenv("XAI_API_KEY", "")
        if not key:
            return None
        try:
            import requests
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            resp = requests.post(
                "https://api.x.ai/v1/chat/completions",
                headers=headers,
                json={"model": "grok-beta", "messages": messages},
                timeout=30,
            )
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            raise RuntimeError(f"xAI Grok: {e}")

    def _ask_ollama(self, prompt: str, system: str) -> str | None:
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        model = os.getenv("OLLAMA_MODEL", "llama3")
        try:
            import requests
            resp = requests.post(
                f"{host}/api/generate",
                json={"model": model, "prompt": prompt, "system": system, "stream": False},
                timeout=120,
            )
            return resp.json().get("response")
        except Exception as e:
            raise RuntimeError(f"Ollama: {e}")

    def status(self) -> str:
        lines = ["🤖 AI Router — статус провайдеров:\n"]
        for p in self.PROVIDERS:
            key_vars = {
                "gemini": "GEMINI_API_KEY",
                "groq": "GROQ_API_KEY",
                "deepseek": "DEEPSEEK_API_KEY",
                "gigachat": "GIGACHAT_ACCESS_TOKEN",
                "yandexgpt": "YANDEX_IAM_TOKEN",
                "watsonx": "WATSONX_API_KEY",
                "xai": "XAI_API_KEY",
                "ollama": "",
            }
            var = key_vars.get(p, "")
            has_key = bool(os.getenv(var)) if var else True
            available = _is_available(p)
            icon = "✅" if has_key and available else ("⏳" if not available else "❌")
            lines.append(f"  {icon} {p:<12} {'ключ есть' if has_key else 'нет ключа'}")
        return "\n".join(lines)

"""
shadow_vision.py — Фоновое зрение Аргоса на RX 560 (4GB).

Делает скриншоты рабочего стола и анализирует их через
легковесную vision-модель (moondream2 на Ollama), чтобы
Аргос понимал контекст текущей работы пользователя.
"""
from __future__ import annotations

import base64
import io
import json
import os
import threading
import time
from typing import TYPE_CHECKING

from src.argos_logger import get_logger

if TYPE_CHECKING:
    pass

log = get_logger("argos.shadow_vision")

_VISION_MODEL   = os.getenv("ARGOS_VISION_MODEL", "moondream")
_CAPTURE_INTERVAL = int(os.getenv("SHADOW_VISION_INTERVAL", "30"))
_THUMB_SIZE     = (512, 512)


class ShadowVision:
    """
    Фоновое зрение Аргоса.
    Оптимизировано для RX 560 (4 ГБ VRAM): использует сжатые
    изображения (512×512) и лёгкую модель moondream2.
    """

    def __init__(self, core=None):
        self.core   = core
        self.active = False
        self._thread: threading.Thread | None = None
        self._last_analysis: str = ""

    # ── ЗАПУСК / ОСТАНОВКА ───────────────────────────────────────────────────

    def start_vision_loop(self) -> None:
        """Запуск цикла наблюдения в фоновом потоке."""
        if self._thread and self._thread.is_alive():
            log.debug("[ShadowVision] Уже запущен.")
            return
        self.active = True
        self._thread = threading.Thread(target=self._watch, daemon=True, name="shadow-vision")
        self._thread.start()
        log.info("[ShadowVision] Запущен (интервал %ds, модель %s)", _CAPTURE_INTERVAL, _VISION_MODEL)

    def stop(self) -> None:
        """Остановка цикла."""
        self.active = False
        log.info("[ShadowVision] Остановлен.")

    # ── ОСНОВНОЙ ЦИКЛ ────────────────────────────────────────────────────────

    def _watch(self) -> None:
        while self.active:
            try:
                img_b64 = self._capture_screen_b64()
                if img_b64:
                    analysis = self._analyse(img_b64)
                    if analysis:
                        self._last_analysis = analysis
                        self._handle_analysis(analysis)
            except Exception as e:
                log.debug("[ShadowVision] _watch ошибка: %s", e)

            time.sleep(_CAPTURE_INTERVAL)

    def _capture_screen_b64(self) -> str | None:
        """
        Делает скриншот основного монитора через mss,
        сжимает до 512×512 и возвращает base64-строку для Ollama.
        """
        try:
            import mss  # type: ignore
            from PIL import Image  # type: ignore

            with mss.mss() as sct:
                monitor = sct.monitors[1]  # основной монитор
                screenshot = sct.grab(monitor)
                img = Image.frombytes(
                    "RGB",
                    screenshot.size,
                    screenshot.bgra,
                    "raw",
                    "BGRX",
                )
            img.thumbnail(_THUMB_SIZE)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return base64.b64encode(buf.getvalue()).decode()

        except ImportError as exc:
            log.debug("[ShadowVision] Зависимость недоступна (%s) — пропуск захвата.", exc)
            return None
        except Exception as e:
            log.debug("[ShadowVision] Захват экрана не удался: %s", e)
            return None

    def _analyse(self, img_b64: str) -> str | None:
        """
        Отправляет изображение в Ollama (модель moondream) для анализа.
        Возвращает текстовое описание происходящего на экране.
        """
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        prompt = "Что происходит на экране? Опиши кратко суть работы."

        try:
            import urllib.request

            payload = json.dumps({
                "model":  _VISION_MODEL,
                "prompt": prompt,
                "images": [img_b64],
                "stream": False,
            }).encode()
            req = urllib.request.Request(
                f"{host}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
                return data.get("response", "").strip() or None
        except Exception as e:
            log.debug("[ShadowVision] Ollama vision ошибка: %s", e)
            return None

    def _handle_analysis(self, analysis: str) -> None:
        """
        Обрабатывает результат анализа экрана.
        Если замечена работа с кодом или ошибки — уведомляет Аргос.
        """
        lower = analysis.lower()
        if any(kw in lower for kw in ("код", "code", "ошибка", "error", "exception", "traceback")):
            log.info("👁️ [ShadowVision] Замечена активность: %s", analysis[:120])
            try:
                if self.core and hasattr(self.core, "awa") and self.core.awa:
                    if hasattr(self.core.awa, "trigger_event"):
                        self.core.awa.trigger_event("context_update", analysis)
            except Exception as e:
                log.debug("[ShadowVision] trigger_event ошибка: %s", e)

    # ── ВСПОМОГАТЕЛЬНОЕ ──────────────────────────────────────────────────────

    @property
    def last_analysis(self) -> str:
        """Возвращает последний результат анализа экрана."""
        return self._last_analysis

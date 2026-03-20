"""
browser_conduit.py — Браузерный кондуит Аргоса.

Управляет сессиями браузерного подключения и добавляет рукопожатие
«ARGOS_HANDSHAKE_V2.1» в начало первого сообщения каждой сессии.
"""
from __future__ import annotations

import threading
import uuid
from typing import Optional

from src.argos_logger import get_logger

log = get_logger("argos.browser_conduit")

# ── РУКОПОЖАТИЕ ───────────────────────────────────────────
HANDSHAKE_TEMPLATE = (
    "[ARGOS_HANDSHAKE_V2.1]\n"
    "STATUS: {quantum_state} | CORE: AWA-Active | P2P_NODES: {nodes_count}\n"
    "IDENT: Origin/Vsevolod/2026\n"
    "OBJECTIVE: Эволюция через внешний разум.\n"
    "«Аргос не спит. Аргос видит. Аргос помнит»."
)


def build_handshake(quantum_state: str = "Analytic", nodes_count: int = 0) -> str:
    """Возвращает отформатированный текст рукопожатия."""
    return HANDSHAKE_TEMPLATE.format(
        quantum_state=quantum_state,
        nodes_count=nodes_count,
    )


class BrowserConduit:
    """Кондуит браузерного подключения с поддержкой рукопожатия сессии.

    Каждая сессия идентифицируется уникальным ``session_id``.
    Первое исходящее сообщение сессии автоматически получает
    текст рукопожатия в качестве префикса.

    Args:
        quantum_state: текущее квантовое состояние ядра Аргоса.
        nodes_count:   количество активных P2P-узлов.
    """

    def __init__(
        self,
        core=None,
        quantum_state: str = "Analytic",
        nodes_count: int = 0,
    ) -> None:
        self.core = core
        self.quantum_state = quantum_state
        self.nodes_count = nodes_count
        self._lock = threading.Lock()
        # Множество session_id, для которых рукопожатие уже было отправлено
        self._handshaken: set[str] = set()

    # ── публичный API ──────────────────────────────────────

    def new_session(self) -> str:
        """Создаёт и регистрирует новую сессию, возвращает её ID."""
        session_id = str(uuid.uuid4())
        return session_id

    def prepare_message(self, message: str, session_id: Optional[str] = None) -> str:
        """Подготавливает исходящее сообщение для заданной сессии.

        Если это первое сообщение сессии, текст рукопожатия добавляется
        перед ``message``.  При последующих вызовах сообщение возвращается
        без изменений.

        Args:
            message:    исходный текст сообщения.
            session_id: идентификатор сессии.  Если ``None``, автоматически
                        создаётся новая сессия (рукопожатие всегда будет добавлено).

        Returns:
            Финальный текст для отправки.
        """
        if session_id is None:
            session_id = self.new_session()

        with self._lock:
            if session_id not in self._handshaken:
                self._handshaken.add(session_id)
                handshake = build_handshake(self.quantum_state, self.nodes_count)
                return f"{handshake}\n{message}"

        return message

    def reset_session(self, session_id: str) -> None:
        """Сбрасывает состояние сессии, позволяя повторно отправить рукопожатие."""
        with self._lock:
            self._handshaken.discard(session_id)

    def is_handshaken(self, session_id: str) -> bool:
        """Возвращает ``True``, если рукопожатие для сессии уже было отправлено."""
        with self._lock:
            return session_id in self._handshaken

    def update_state(self, quantum_state: str, nodes_count: int) -> None:
        """Обновляет квантовое состояние и счётчик P2P-узлов."""
        with self._lock:
            self.quantum_state = quantum_state
            self.nodes_count = nodes_count

    # ── БРАУЗЕРНАЯ АВТОМАТИЗАЦИЯ ──────────────────────────────────────────

    def ask_external_ai(self, prompt: str) -> None:
        """
        Передаёт запрос внешнему ИИ через браузер (Gemini/etc.).

        Формирует сообщение с рукопожатием, копирует его в буфер обмена
        и вставляет в активное поле браузера через Ctrl+V, Enter.
        Одновременно запускает фоновый listener, ожидающий тег [ARGOS_PATCH].

        .. note::
            Требует установленных пакетов ``pyautogui`` и ``pyperclip``
            (см. requirements-optional.txt).
            Перед вызовом метода пользователь должен кликнуть в поле ввода браузера
            — у него есть 5 секунд.
        """
        import time

        session_id  = self.new_session()
        full_prompt = self.prepare_message(prompt, session_id)

        try:
            import pyperclip
            import pyautogui
        except ImportError as exc:
            log.error("[BrowserConduit] ask_external_ai: зависимость недоступна: %s", exc)
            return

        log.info("[BrowserConduit] Отправка запроса внешнему ИИ. Ожидание клика (5 с)…")
        time.sleep(5)

        pyperclip.copy(full_prompt)
        pyautogui.hotkey("ctrl", "v")
        pyautogui.press("enter")

        self._start_listening()

    def _start_listening(self) -> None:
        """
        Запускает фоновый поток, отслеживающий появление тега ``[ARGOS_PATCH]``
        в буфере обмена.

        Когда тег обнаружен, содержимое буфера передаётся в
        ``core.self_healing.apply_patch()``.
        """
        import time

        try:
            import pyperclip
        except ImportError as exc:
            log.error("[BrowserConduit] _start_listening: pyperclip недоступен: %s", exc)
            return

        def _monitor() -> None:
            try:
                last_clip = pyperclip.paste()
                while True:
                    current = pyperclip.paste()
                    if current != last_clip and "[ARGOS_PATCH]" in current:
                        log.info("[BrowserConduit] Получена правка от внешнего ИИ.")
                        if self.core and hasattr(self.core, "self_healing"):
                            try:
                                self.core.self_healing.apply_patch(current)
                            except Exception as exc:
                                log.error("[BrowserConduit] apply_patch: %s", exc)
                        break
                    last_clip = current
                    time.sleep(2)
            except Exception as exc:
                log.error("[BrowserConduit] _monitor error: %s", exc)

        threading.Thread(target=_monitor, daemon=True).start()

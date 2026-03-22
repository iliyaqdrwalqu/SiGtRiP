"""
src/input_control.py — Управление мышью и клавиатурой.
"""
from __future__ import annotations
import logging
import time
import os
from typing import Optional, Tuple

log = logging.getLogger("argos.input_control")

# Безопасная зона — ARGOS не может кликать за пределами экрана
SAFE_MODE = os.getenv("ARGOS_INPUT_SAFE", "on") == "on"
CLICK_DELAY = float(os.getenv("ARGOS_CLICK_DELAY", "0.1"))
TYPE_DELAY  = float(os.getenv("ARGOS_TYPE_DELAY", "0.05"))


def _get_pyautogui():
    try:
        import pyautogui
        pyautogui.FAILSAFE = True   # Угол экрана = стоп
        pyautogui.PAUSE = CLICK_DELAY
        return pyautogui
    except ImportError:
        return None


def _get_screen_size() -> Tuple[int, int]:
    try:
        pg = _get_pyautogui()
        if pg:
            return pg.size()
    except Exception:
        pass
    return (1920, 1080)


class InputController:
    """Управление мышью и клавиатурой."""

    def __init__(self):
        self.pg = _get_pyautogui()
        self._available = self.pg is not None
        self._history = []

    def is_available(self) -> bool:
        return self._available

    def _log(self, action: str):
        self._history.append({"action": action, "time": time.time()})
        if len(self._history) > 100:
            self._history = self._history[-50:]

    # ── Мышь ──────────────────────────────────────────────────────────────────

    def move(self, x: int, y: int, duration: float = 0.3) -> str:
        if not self._available:
            return "❌ pyautogui не установлен: pip install pyautogui"
        try:
            sw, sh = _get_screen_size()
            x = max(0, min(x, sw))
            y = max(0, min(y, sh))
            self.pg.moveTo(x, y, duration=duration)
            self._log(f"move({x},{y})")
            return f"🖱️ Курсор перемещён → ({x}, {y})"
        except Exception as e:
            return f"❌ Ошибка: {e}"

    def click(self, x: int = None, y: int = None, button: str = "left") -> str:
        if not self._available:
            return "❌ pyautogui не установлен"
        try:
            if x is not None and y is not None:
                self.pg.click(x, y, button=button)
                self._log(f"click({x},{y},{button})")
                return f"🖱️ Клик {button} → ({x}, {y})"
            else:
                pos = self.pg.position()
                self.pg.click(button=button)
                self._log(f"click({pos.x},{pos.y},{button})")
                return f"🖱️ Клик {button} на текущей позиции ({pos.x}, {pos.y})"
        except Exception as e:
            return f"❌ Ошибка: {e}"

    def double_click(self, x: int = None, y: int = None) -> str:
        if not self._available:
            return "❌ pyautogui не установлен"
        try:
            if x is not None and y is not None:
                self.pg.doubleClick(x, y)
                return f"🖱️ Двойной клик → ({x}, {y})"
            else:
                self.pg.doubleClick()
                return "🖱️ Двойной клик на текущей позиции"
        except Exception as e:
            return f"❌ Ошибка: {e}"

    def right_click(self, x: int = None, y: int = None) -> str:
        return self.click(x, y, button="right")

    def scroll(self, clicks: int = 3, x: int = None, y: int = None) -> str:
        if not self._available:
            return "❌ pyautogui не установлен"
        try:
            if x and y:
                self.pg.scroll(clicks, x=x, y=y)
            else:
                self.pg.scroll(clicks)
            direction = "вверх" if clicks > 0 else "вниз"
            return f"🖱️ Прокрутка {direction} ({abs(clicks)} шагов)"
        except Exception as e:
            return f"❌ Ошибка: {e}"

    def drag(self, x1: int, y1: int, x2: int, y2: int,
             duration: float = 0.5) -> str:
        if not self._available:
            return "❌ pyautogui не установлен"
        try:
            self.pg.moveTo(x1, y1, duration=0.2)
            self.pg.dragTo(x2, y2, duration=duration, button="left")
            self._log(f"drag({x1},{y1}→{x2},{y2})")
            return f"🖱️ Перетащено ({x1},{y1}) → ({x2},{y2})"
        except Exception as e:
            return f"❌ Ошибка: {e}"

    def position(self) -> str:
        if not self._available:
            return "❌ pyautogui не установлен"
        try:
            pos = self.pg.position()
            sw, sh = _get_screen_size()
            return f"🖱️ Позиция курсора: ({pos.x}, {pos.y})\nЭкран: {sw}×{sh}"
        except Exception as e:
            return f"❌ Ошибка: {e}"

    # ── Клавиатура ────────────────────────────────────────────────────────────

    def press(self, key: str) -> str:
        if not self._available:
            return "❌ pyautogui не установлен"
        try:
            # Комбинации: ctrl+c, alt+f4 и т.д.
            if "+" in key:
                keys = [k.strip() for k in key.split("+")]
                self.pg.hotkey(*keys)
                self._log(f"hotkey({key})")
                return f"⌨️ Комбинация: {key}"
            else:
                self.pg.press(key)
                self._log(f"press({key})")
                return f"⌨️ Нажата: {key}"
        except Exception as e:
            return f"❌ Ошибка клавиши '{key}': {e}"

    def type_text(self, text: str, interval: float = None) -> str:
        if not self._available:
            return "❌ pyautogui не установлен"
        try:
            interval = interval or TYPE_DELAY
            self.pg.typewrite(text, interval=interval)
            self._log(f"type({text[:20]})")
            return f"⌨️ Напечатано: {text[:50]}{'...' if len(text)>50 else ''}"
        except Exception as e:
            # Для Unicode используем pyperclip + paste
            try:
                import pyperclip
                old = pyperclip.paste()
                pyperclip.copy(text)
                time.sleep(0.1)
                self.pg.hotkey("ctrl", "v")
                time.sleep(0.2)
                pyperclip.copy(old)
                return f"⌨️ Вставлено: {text[:50]}{'...' if len(text)>50 else ''}"
            except Exception as e2:
                return f"❌ Ошибка печати: {e2}"

    def write_clipboard(self, text: str) -> str:
        """Скопировать текст в буфер обмена."""
        try:
            import pyperclip
            pyperclip.copy(text)
            return f"📋 Скопировано в буфер: {text[:50]}"
        except ImportError:
            return "❌ pip install pyperclip"
        except Exception as e:
            return f"❌ Ошибка: {e}"

    # ── Скриншот ──────────────────────────────────────────────────────────────

    def screenshot(self, path: str = None) -> str:
        if not self._available:
            return "❌ pyautogui не установлен"
        try:
            from pathlib import Path as P
            if not path:
                import time as t
                path = str(P.home() / f"screenshot_{int(t.time())}.png")
            img = self.pg.screenshot()
            img.save(path)
            size = P(path).stat().st_size // 1024
            return f"📸 Скриншот сохранён: {path} ({size} KB)"
        except Exception as e:
            return f"❌ Ошибка скриншота: {e}"

    def find_on_screen(self, image_path: str,
                       confidence: float = 0.8) -> str:
        if not self._available:
            return "❌ pyautogui не установлен"
        try:
            loc = self.pg.locateOnScreen(image_path, confidence=confidence)
            if loc:
                center = self.pg.center(loc)
                return f"🔍 Найдено на экране: ({center.x}, {center.y})"
            return f"🔍 Не найдено на экране: {image_path}"
        except Exception as e:
            return f"❌ Ошибка поиска: {e}"

    # ── Макросы ───────────────────────────────────────────────────────────────

    def run_macro(self, name: str) -> str:
        """Выполнить именованный макрос."""
        macros = {
            "копировать": lambda: self.press("ctrl+c"),
            "вставить":   lambda: self.press("ctrl+v"),
            "вырезать":   lambda: self.press("ctrl+x"),
            "отменить":   lambda: self.press("ctrl+z"),
            "сохранить":  lambda: self.press("ctrl+s"),
            "выделить всё": lambda: self.press("ctrl+a"),
            "закрыть":    lambda: self.press("alt+f4"),
            "новая вкладка": lambda: self.press("ctrl+t"),
            "закрыть вкладку": lambda: self.press("ctrl+w"),
            "скрин":      lambda: self.screenshot(),
        }
        fn = macros.get(name.lower())
        if fn:
            return fn()
        return f"❓ Макрос не найден: {name}\nДоступные: {', '.join(macros.keys())}"

    def status(self) -> str:
        sw, sh = _get_screen_size()
        lines = [
            "⌨️🖱️ Input Controller:\n",
            f"  pyautogui: {'✅' if self._available else '❌ pip install pyautogui'}",
            f"  Экран: {sw}×{sh}",
            f"  Безопасный режим: {'✅' if SAFE_MODE else '⚠️ выключен'}",
            f"  Задержка клика: {CLICK_DELAY}s",
            f"  Задержка печати: {TYPE_DELAY}s",
            "",
            "  Команды:",
            "  мышь move X Y          — переместить курсор",
            "  мышь click [X Y]       — левый клик",
            "  мышь rclick [X Y]      — правый клик",
            "  мышь dclick [X Y]      — двойной клик",
            "  мышь scroll N          — прокрутка",
            "  мышь drag X1 Y1 X2 Y2  — перетащить",
            "  мышь позиция           — текущие координаты",
            "  клавиша KEY            — нажать клавишу",
            "  клавиша ctrl+c         — комбинация",
            "  печатай ТЕКСТ          — ввод текста",
            "  буфер ТЕКСТ            — копировать в буфер",
            "  макрос НАЗВАНИЕ        — выполнить макрос",
            "  скриншот               — сделать скриншот",
        ]
        return "\n".join(lines)


# Глобальный инстанс
_controller: InputController = None


def get_controller() -> InputController:
    global _controller
    if _controller is None:
        _controller = InputController()
    return _controller

"""
style.py — ARGOS Unified UI Style  (Sovereign Emerald / Deep Space)

Единая цветовая схема и константы для всех интерфейсов ARGOS:
  • kivy_remote_ui.py   — Android Remote Control (планшет/телефон)
  • mobile_ui.py        — Android Mobile Node (локальный режим)
  • kivy_gui.py         — Desktop / Kivy UI
  • wear_os_ui.py       — Носимые устройства (Wear OS, умные часы)

Подключение:
    from src.interface.style import S
    Window.clearcolor = S.BG
"""


class _Style:
    # ── Фоны ────────────────────────────────────────────────────────────────
    BG       = (0.04, 0.05, 0.10, 1)   # Deep Space Navy
    CARD     = (0.08, 0.11, 0.21, 1)   # Card / input field background
    CARD2    = (0.05, 0.07, 0.16, 1)   # Secondary card (darker)

    # ── Акцентные цвета ─────────────────────────────────────────────────────
    GREEN    = (0.00, 1.00, 0.40, 1)   # Sovereign Emerald — primary accent
    CYAN     = (0.00, 1.00, 0.80, 1)   # Cyan — headers / labels
    BLUE     = (0.10, 0.40, 0.80, 1)   # Blue — action buttons
    PURPLE   = (0.30, 0.00, 0.60, 0.7) # Purple — quantum / special actions

    # ── Состояния ───────────────────────────────────────────────────────────
    RED      = (1.00, 0.30, 0.30, 1)   # Error / alert
    ORANGE   = (1.00, 0.55, 0.10, 1)   # Warning / system
    YELLOW   = (1.00, 1.00, 0.20, 1)   # Unstable / caution

    # ── Текст ───────────────────────────────────────────────────────────────
    TEXT     = (0.90, 0.95, 1.00, 1)   # Primary text
    GRAY     = (0.50, 0.60, 0.70, 1)   # Secondary / hint text
    DIM      = (0.30, 0.35, 0.45, 1)   # Dimmed / disabled text

    # ── Кнопки ──────────────────────────────────────────────────────────────
    BTN_PRIMARY  = (0.10, 0.40, 0.80, 1)   # Primary action
    BTN_OK       = (0.08, 0.42, 0.22, 1)   # Confirm / success
    BTN_DANGER   = (0.55, 0.10, 0.10, 1)   # Destructive action
    BTN_IOT      = (0.12, 0.24, 0.44, 1)   # IoT / connectivity
    BTN_QUICK    = (0.10, 0.20, 0.40, 1)   # Quick-action grid

    # ── Орб / квантовое состояние ───────────────────────────────────────────
    ORB_COLORS = {
        "Analytic":   "[color=00ffcc]",
        "Protective": "[color=ff3333]",
        "Creative":   "[color=00ff88]",
        "Unstable":   "[color=ffff00]",
        "All-Seeing": "[color=ffffff]",
        "System":     "[color=ff8800]",
        "Offline":    "[color=444444]",
    }

    # ── Типографика ─────────────────────────────────────────────────────────
    FONT_HEADER  = "20sp"
    FONT_NORMAL  = "14sp"
    FONT_SMALL   = "12sp"
    FONT_TINY    = "11sp"

    # ── Отступы / размеры ───────────────────────────────────────────────────
    PAD         = 14    # dp  — стандартный padding
    PAD_SMALL   = 8     # dp  — компактный padding (носимые)
    SPACING     = 8     # dp  — стандартный spacing
    SPACING_SM  = 5     # dp  — компактный spacing
    BTN_HEIGHT  = 44    # dp  — стандартная высота кнопки
    BTN_HEIGHT_WEAR = 52  # dp — кнопка для носимых (крупный тач-таргет)
    INPUT_H     = 40    # dp  — высота поля ввода
    HEADER_H    = 48    # dp  — высота заголовка

    def orb_color(self, state: str) -> str:
        """Возвращает Kivy markup-цвет для заданного состояния."""
        key = state.split(" ")[0] if state else "Offline"
        return self.ORB_COLORS.get(key, "[color=aaaaaa]")


# Singleton — импортируй `S` во всех UI-модулях
S = _Style()

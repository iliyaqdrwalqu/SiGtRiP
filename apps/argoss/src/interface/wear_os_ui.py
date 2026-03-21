"""
wear_os_ui.py — ARGOS v2.1  Wearable / Wear OS UI  (Kivy)

Минималистичный интерфейс для носимых устройств:
  • Умные часы (Wear OS, Samsung Galaxy Watch)
  • Фитнес-браслеты с экраном
  • Компактные Android-гаджеты (экран ≤ 1.5″ или ≤ 320×320 px)

Особенности:
  • Круговой дизайн — учитывает round-screen Wear OS
  • Крупные кнопки (52dp) — удобные тач-таргеты на маленьком экране
  • Минимум текста — только ключевые метрики
  • Режимы: STATUS / CMD / QUANTUM ORB
  • Автоматический опрос ARGOS API каждые 10 секунд
  • Тема: Sovereign Emerald (единый стиль со всеми интерфейсами)

Запуск (локально): python -m src.interface.wear_os_ui  (из корня проекта)
"""
import threading
import time

try:
    import requests as _req_lib
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

try:
    from kivy.app import App
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.label import Label
    from kivy.uix.button import Button
    from kivy.uix.textinput import TextInput
    from kivy.uix.screenmanager import ScreenManager, Screen
    from kivy.uix.scrollview import ScrollView
    from kivy.clock import Clock
    from kivy.storage.jsonstore import JsonStore
    from kivy.core.window import Window
    KIVY_OK = True
except ImportError:
    KIVY_OK = False

try:
    from src.interface.style import S
except ImportError:
    # Fallback: работаем без пакетного импорта
    class _S:
        BG = (0.04, 0.05, 0.10, 1)
        CARD = (0.08, 0.11, 0.21, 1)
        GREEN = (0.00, 1.00, 0.40, 1)
        CYAN = (0.00, 1.00, 0.80, 1)
        RED = (1.00, 0.30, 0.30, 1)
        GRAY = (0.50, 0.60, 0.70, 1)
        TEXT = (0.90, 0.95, 1.00, 1)
        BTN_PRIMARY = (0.10, 0.40, 0.80, 1)
        BTN_OK = (0.08, 0.42, 0.22, 1)
        BTN_HEIGHT_WEAR = 52
        PAD_SMALL = 8
        SPACING_SM = 5
        FONT_HEADER = "17sp"
        FONT_NORMAL = "13sp"
        FONT_SMALL = "11sp"
        ORB_COLORS = {
            "Analytic": "[color=00ffcc]", "Protective": "[color=ff3333]",
            "Creative": "[color=00ff88]", "Unstable": "[color=ffff00]",
            "All-Seeing": "[color=ffffff]", "System": "[color=ff8800]",
            "Offline": "[color=444444]",
        }
        def orb_color(self, state):
            key = state.split(" ")[0] if state else "Offline"
            return self.ORB_COLORS.get(key, "[color=aaaaaa]")
    S = _S()

_DEFAULT_URL = "http://localhost:8080"
_POLL_INTERVAL = 10   # секунды — реже чем на телефоне (экономия батареи)


def _request(method: str, url: str, token: str, **kw):
    """Синхронный HTTP-запрос. Возвращает (data, error_str)."""
    if not REQUESTS_OK:
        return None, "requests not installed"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        r = _req_lib.request(method, url, headers=headers, timeout=6, **kw)
        try:
            return r.json(), None
        except Exception:
            return {"_text": r.text}, None
    except Exception as exc:
        return None, str(exc)


if KIVY_OK:
    # ─────────────────────────────────────────────────────────────────────────
    # Screen 1 — ORB  (главный экран — квантовый орб + статус)
    # ─────────────────────────────────────────────────────────────────────────
    class OrbScreen(Screen):
        def __init__(self, app_ref, **kwargs):
            super().__init__(name="orb", **kwargs)
            self._app = app_ref

            root = BoxLayout(
                orientation="vertical",
                padding=S.PAD_SMALL,
                spacing=S.SPACING_SM,
            )

            # ── Заголовок ─────────────────────────────────
            root.add_widget(Label(
                text="[b]🔱 ARGOS[/b]",
                markup=True,
                font_size=S.FONT_HEADER,
                color=S.CYAN,
                size_hint_y=None,
                height=34,
            ))

            # ── Орб ───────────────────────────────────────
            self.orb = Label(
                text=f"{S.orb_color('Analytic')}●[/color]",
                markup=True,
                font_size="72sp",
                size_hint_y=None,
                height=90,
            )
            root.add_widget(self.orb)

            # ── Состояние / uptime ───────────────────────
            self.state_lbl = Label(
                text="Analytic",
                font_size=S.FONT_NORMAL,
                color=S.GREEN,
                size_hint_y=None,
                height=24,
                bold=True,
            )
            self.uptime_lbl = Label(
                text="Uptime: —",
                font_size=S.FONT_SMALL,
                color=S.GRAY,
                size_hint_y=None,
                height=20,
            )
            root.add_widget(self.state_lbl)
            root.add_widget(self.uptime_lbl)

            # ── Кнопки навигации ──────────────────────────
            nav = BoxLayout(
                size_hint_y=None,
                height=S.BTN_HEIGHT_WEAR,
                spacing=S.SPACING_SM,
            )
            for txt, screen in [("📊", "status"), ("🖥", "cmd"), ("⚙️", "settings")]:
                b = Button(
                    text=txt, font_size="18sp",
                    background_color=S.BTN_PRIMARY,
                )
                b.bind(on_press=lambda _, s=screen: setattr(
                    self._app.sm, "current", s
                ))
                nav.add_widget(b)
            root.add_widget(nav)
            self.add_widget(root)

        def refresh(self, data: dict):
            """Обновляет орб из ответа /api/health."""
            state = data.get("state", data.get("status", "Analytic"))
            uptime = data.get("uptime_seconds", "?")
            color = S.orb_color(state)
            Clock.schedule_once(lambda *_: self._update(color, state, uptime))

        def _update(self, color, state, uptime):
            self.orb.text = f"{color}●[/color]"
            self.state_lbl.text = state
            self.uptime_lbl.text = f"Uptime: {uptime}s"

    # ─────────────────────────────────────────────────────────────────────────
    # Screen 2 — STATUS  (ключевые метрики)
    # ─────────────────────────────────────────────────────────────────────────
    class StatusScreen(Screen):
        def __init__(self, app_ref, **kwargs):
            super().__init__(name="status", **kwargs)
            self._app = app_ref

            root = BoxLayout(
                orientation="vertical",
                padding=S.PAD_SMALL,
                spacing=S.SPACING_SM,
            )
            root.add_widget(Label(
                text="[b]📊 Статус[/b]",
                markup=True,
                font_size=S.FONT_HEADER,
                color=S.CYAN,
                size_hint_y=None, height=34,
            ))

            sv = ScrollView()
            self.info = Label(
                text="Загрузка...",
                font_size=S.FONT_SMALL,
                color=S.GREEN,
                halign="left", valign="top",
                size_hint_y=None,
                markup=True,
            )
            self.info.bind(texture_size=lambda *_: setattr(
                self.info, "height", max(self.info.texture_size[1], 120)
            ))
            sv.add_widget(self.info)
            root.add_widget(sv)

            nav = BoxLayout(size_hint_y=None, height=S.BTN_HEIGHT_WEAR, spacing=S.SPACING_SM)
            back = Button(text="← Орб", background_color=S.BTN_OK)
            back.bind(on_press=lambda *_: setattr(self._app.sm, "current", "orb"))
            refresh = Button(text="🔄", background_color=S.BTN_PRIMARY)
            refresh.bind(on_press=lambda *_: self._app.poll_now())
            nav.add_widget(back)
            nav.add_widget(refresh)
            root.add_widget(nav)
            self.add_widget(root)

        def refresh(self, data: dict):
            lines = []
            for key, val in data.items():
                if key.startswith("_"):
                    continue
                lines.append(f"[b][color=00ffcc]{key}[/color][/b]: {val}")
            text = "\n".join(lines) if lines else "Нет данных"
            Clock.schedule_once(lambda *_: setattr(self.info, "text", text))

    # ─────────────────────────────────────────────────────────────────────────
    # Screen 3 — CMD  (быстрые команды + ввод)
    # ─────────────────────────────────────────────────────────────────────────
    class CmdScreen(Screen):
        def __init__(self, app_ref, **kwargs):
            super().__init__(name="cmd", **kwargs)
            self._app = app_ref

            root = BoxLayout(
                orientation="vertical",
                padding=S.PAD_SMALL,
                spacing=S.SPACING_SM,
            )
            root.add_widget(Label(
                text="[b]🖥 Команды[/b]",
                markup=True,
                font_size=S.FONT_HEADER,
                color=S.CYAN,
                size_hint_y=None, height=34,
            ))

            # Быстрые команды
            quick = BoxLayout(size_hint_y=None, height=S.BTN_HEIGHT_WEAR, spacing=4)
            for emoji, cmd in [("📊", "статус"), ("📡", "сеть"), ("🛡", "root статус")]:
                b = Button(text=emoji, font_size="18sp", background_color=S.BTN_PRIMARY)
                b.bind(on_press=lambda _, c=cmd: self._send_quick(c))
                quick.add_widget(b)
            root.add_widget(quick)

            # Вывод ответа
            sv = ScrollView()
            self.output = Label(
                text="> Готов\n",
                font_size=S.FONT_SMALL,
                color=S.GREEN,
                halign="left", valign="top",
                size_hint_y=None,
                markup=True,
            )
            self.output.bind(texture_size=lambda *_: setattr(
                self.output, "height", max(self.output.texture_size[1], 80)
            ))
            sv.add_widget(self.output)
            root.add_widget(sv)

            # Поле ввода
            inp = BoxLayout(size_hint_y=None, height=S.BTN_HEIGHT_WEAR, spacing=4)
            self.cmd_input = TextInput(
                hint_text="Команда...",
                multiline=False,
                background_color=S.CARD,
                foreground_color=S.TEXT,
                font_size=S.FONT_SMALL,
            )
            self.cmd_input.bind(on_text_validate=self._send)
            send_btn = Button(
                text="▶", size_hint_x=None, width=52,
                background_color=S.BTN_PRIMARY,
            )
            send_btn.bind(on_press=self._send)
            inp.add_widget(self.cmd_input)
            inp.add_widget(send_btn)
            root.add_widget(inp)

            # Навигация назад
            back = Button(
                text="← Орб",
                size_hint_y=None, height=S.BTN_HEIGHT_WEAR,
                background_color=S.BTN_OK,
            )
            back.bind(on_press=lambda *_: setattr(self._app.sm, "current", "orb"))
            root.add_widget(back)
            self.add_widget(root)

        def _send(self, *_):
            cmd = self.cmd_input.text.strip()
            if not cmd:
                return
            self.cmd_input.text = ""
            self._append(f"> {cmd}")
            threading.Thread(target=self._do_send, args=(cmd,), daemon=True).start()

        def _send_quick(self, cmd: str):
            self._append(f"> {cmd}")
            threading.Thread(target=self._do_send, args=(cmd,), daemon=True).start()

        def _do_send(self, cmd: str):
            url, token = self._app.get_connection()
            if not url:
                Clock.schedule_once(lambda *_: self._append("⚠ URL не задан"))
                return
            data, err = _request("POST", f"{url}/api/command", token, json={"cmd": cmd})
            if err:
                Clock.schedule_once(lambda *_: self._append(f"❌ {err}"))
                return
            answer = data.get("answer", str(data)) if data else "—"
            Clock.schedule_once(lambda *_: self._append(f"  {answer[:120]}"))

        def _append(self, line: str):
            self.output.text += f"\n{line}"

    # ─────────────────────────────────────────────────────────────────────────
    # Screen 4 — SETTINGS  (URL + Token)
    # ─────────────────────────────────────────────────────────────────────────
    class SettingsScreen(Screen):
        def __init__(self, app_ref, **kwargs):
            super().__init__(name="settings", **kwargs)
            self._app = app_ref

            root = BoxLayout(
                orientation="vertical",
                padding=S.PAD_SMALL,
                spacing=S.SPACING_SM,
            )
            root.add_widget(Label(
                text="[b]⚙️ Настройки[/b]",
                markup=True,
                font_size=S.FONT_HEADER,
                color=S.CYAN,
                size_hint_y=None, height=34,
            ))

            root.add_widget(Label(
                text="Server URL:", color=S.GRAY,
                font_size=S.FONT_SMALL,
                size_hint_y=None, height=22,
            ))
            self.url_input = TextInput(
                text=_DEFAULT_URL, multiline=False,
                background_color=S.CARD,
                foreground_color=S.TEXT,
                font_size=S.FONT_SMALL,
                size_hint_y=None, height=38,
            )
            root.add_widget(self.url_input)

            root.add_widget(Label(
                text="Token:", color=S.GRAY,
                font_size=S.FONT_SMALL,
                size_hint_y=None, height=22,
            ))
            self.token_input = TextInput(
                text="", multiline=False, password=True,
                background_color=S.CARD,
                foreground_color=S.TEXT,
                font_size=S.FONT_SMALL,
                size_hint_y=None, height=38,
            )
            root.add_widget(self.token_input)

            save_btn = Button(
                text="💾 Сохранить",
                size_hint_y=None, height=S.BTN_HEIGHT_WEAR,
                background_color=S.BTN_OK,
            )
            save_btn.bind(on_press=self._save)
            root.add_widget(save_btn)

            self._status_lbl = Label(
                text="", color=S.GREEN,
                font_size=S.FONT_SMALL,
                size_hint_y=None, height=22,
            )
            root.add_widget(self._status_lbl)

            back = Button(
                text="← Орб",
                size_hint_y=None, height=S.BTN_HEIGHT_WEAR,
                background_color=S.BTN_PRIMARY,
            )
            back.bind(on_press=lambda *_: setattr(self._app.sm, "current", "orb"))
            root.add_widget(back)
            root.add_widget(BoxLayout())  # spacer
            self.add_widget(root)

        def _save(self, *_):
            url = self.url_input.text.strip().rstrip("/")
            token = self.token_input.text.strip()
            self._app.store.put("cfg", url=url, token=token)
            self._app._url = url
            self._app._token = token
            self._status_lbl.text = "✅ Сохранено"
            Clock.schedule_once(
                lambda *_: setattr(self._status_lbl, "text", ""), 2
            )

        def load_saved(self, store):
            if store.exists("cfg"):
                cfg = store.get("cfg")
                self.url_input.text = cfg.get("url", _DEFAULT_URL)
                self.token_input.text = cfg.get("token", "")

    # ─────────────────────────────────────────────────────────────────────────
    # Main App
    # ─────────────────────────────────────────────────────────────────────────
    class ArgosWearApp(App):
        """ARGOS Wear — UI для носимых устройств (Wear OS / умные часы)."""

        def build(self):
            Window.clearcolor = S.BG
            # Для носимых устройств — квадратный экран ~300×300
            # buildozer.spec может задать другой размер через android.window_size

            self.store = JsonStore("argos_wear.json")
            self._url   = _DEFAULT_URL
            self._token = ""
            if self.store.exists("cfg"):
                cfg = self.store.get("cfg")
                self._url   = cfg.get("url", _DEFAULT_URL)
                self._token = cfg.get("token", "")

            self.sm = ScreenManager()

            self._orb_screen      = OrbScreen(self)
            self._status_screen   = StatusScreen(self)
            self._cmd_screen      = CmdScreen(self)
            self._settings_screen = SettingsScreen(self)

            self.sm.add_widget(self._orb_screen)
            self.sm.add_widget(self._status_screen)
            self.sm.add_widget(self._cmd_screen)
            self.sm.add_widget(self._settings_screen)

            self._settings_screen.load_saved(self.store)

            # Автоопрос API
            self._poll_ev = Clock.schedule_interval(
                lambda *_: self._poll(), _POLL_INTERVAL
            )
            self._poll()
            return self.sm

        def get_connection(self):
            return self._url, self._token

        def poll_now(self):
            threading.Thread(target=self._poll, daemon=True).start()

        def _poll(self):
            threading.Thread(target=self._do_poll, daemon=True).start()

        def _do_poll(self):
            url, token = self._url, self._token
            if not url:
                return
            data, err = _request("GET", f"{url}/api/health", token)
            if err or not data:
                data = {"state": "Offline", "status": "error", "uptime_seconds": 0}
            self._orb_screen.refresh(data)
            self._status_screen.refresh(data)

else:
    # ── Заглушка для не-Android / не-Kivy окружений ──────────────────────────
    class ArgosWearApp:
        """Stub when Kivy is not installed."""

        def run(self):
            print("⚠️  wear_os_ui: Kivy не установлен. pip install kivy")


if __name__ == "__main__":
    ArgosWearApp().run()

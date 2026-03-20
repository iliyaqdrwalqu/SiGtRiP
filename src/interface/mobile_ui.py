from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock
from kivy.core.window import Window
import threading

try:
    from src.interface.style import S
except ImportError:
    from style import S

class QuantumOrb(Label):
    """Визуализация квантового состояния Аргоса."""

    def update_orb(self, state):
        color = S.orb_color(state)
        self.text   = f"{color}●[/color]"
        self.markup = True


class ArgosMobileUI(App):
    def __init__(self, core=None, admin=None, flasher=None, **kwargs):
        super().__init__(**kwargs)
        self.core    = core
        self.admin   = admin
        self.flasher = flasher
        self._listening = False

    def build(self):
        Window.clearcolor = S.BG
        root = BoxLayout(orientation='vertical', padding=S.PAD, spacing=S.SPACING)

        # ── Шапка ─────────────────────────────────────────
        root.add_widget(Label(
            text="👁️  ARGOS MOBILE NODE",
            font_size=S.FONT_HEADER, bold=True,
            color=S.CYAN,
            size_hint_y=None, height=S.HEADER_H,
        ))

        # ── Орб + статус ──────────────────────────────────
        top = BoxLayout(size_hint_y=None, height=120, spacing=10)
        self.orb = QuantumOrb(text=f"{S.orb_color('Analytic')}●[/color]",
                              font_size='90sp', markup=True,
                              size_hint_x=None, width=110)
        top.add_widget(self.orb)

        info = BoxLayout(orientation='vertical')
        self.state_lbl  = Label(text="Состояние: Analytic", halign="left",
                                font_size=S.FONT_NORMAL, color=S.GREEN)
        self.health_lbl = Label(text="Shield: Active", halign="left",
                                font_size=S.FONT_TINY, color=S.CYAN)
        info.add_widget(self.state_lbl)
        info.add_widget(self.health_lbl)
        top.add_widget(info)
        root.add_widget(top)

        # ── Быстрые кнопки ────────────────────────────────
        grid = BoxLayout(size_hint_y=None, height=50, spacing=6)
        quick = [
            ("📊 Статус",   "статус системы"),
            ("🪙 Крипто",   "крипто"),
            ("📡 Сеть",     "сканируй сеть"),
            ("📰 Дайджест", "дайджест"),
        ]
        for label, cmd in quick:
            btn = Button(text=label, font_size=S.FONT_SMALL,
                         background_color=S.BTN_QUICK)
            btn.bind(on_press=lambda _, c=cmd: self._send(c))
            grid.add_widget(btn)
        root.add_widget(grid)

        # ── IoT / прошивка быстрые кнопки ────────────────
        iot_grid = BoxLayout(size_hint_y=None, height=50, spacing=6)
        iot_quick = [
            ("📡 IoT",       "iot статус"),
            ("🏭 Протоколы", "iot протоколы"),
            ("🧩 Шаблоны",   "шаблоны шлюзов"),
            ("🛠 Прошивка",  "создай прошивку "),
        ]
        for label, cmd in iot_quick:
            btn = Button(text=label, font_size=S.FONT_SMALL,
                         background_color=S.BTN_IOT)
            if cmd.endswith(" "):
                btn.bind(on_press=lambda _, c=cmd: self._prefill(c))
            else:
                btn.bind(on_press=lambda _, c=cmd: self._send(c))
            iot_grid.add_widget(btn)
        root.add_widget(iot_grid)

        voice_grid = BoxLayout(size_hint_y=None, height=44, spacing=6)
        listen_btn = Button(text="🎙 Слушай меня", font_size=S.FONT_NORMAL,
                            background_color=S.BTN_OK)
        listen_btn.bind(on_press=lambda _: self._start_listen())
        voice_grid.add_widget(listen_btn)
        root.add_widget(voice_grid)

        # ── Чат ───────────────────────────────────────────
        scroll = ScrollView()
        self.chat = Label(
            text="👁️ Аргос активирован. Ожидаю директив...\n",
            font_size='13sp', halign='left', valign='top',
            markup=True, size_hint_y=None,
        )
        self.chat.bind(texture_size=lambda i, v: i.setter('size')(i, v))
        scroll.add_widget(self.chat)
        root.add_widget(scroll)

        # ── Ввод ──────────────────────────────────────────
        inp = BoxLayout(size_hint_y=None, height=48, spacing=6)
        self.entry = TextInput(
            hint_text="Директива...", multiline=False,
            background_color=S.CARD,
            foreground_color=S.TEXT, font_size=S.FONT_NORMAL,
        )
        self.entry.bind(on_text_validate=lambda _: self._send(self.entry.text))
        inp.add_widget(self.entry)

        send_btn = Button(text="▶", size_hint_x=None, width=50,
                          font_size='18sp', background_color=S.BTN_PRIMARY)
        send_btn.bind(on_press=lambda _: self._send(self.entry.text))
        inp.add_widget(send_btn)

        mic_btn = Button(text="🎤", size_hint_x=None, width=50,
                         font_size='16sp', background_color=S.BTN_OK)
        mic_btn.bind(on_press=lambda _: self._start_listen())
        inp.add_widget(mic_btn)
        root.add_widget(inp)

        return root

    # ── ОТПРАВКА ──────────────────────────────────────────
    def _send(self, text: str):
        if not text or not text.strip():
            return
        self.entry.text = ""
        self._append(f"[color=5599ff]▷ ВЫ:[/color] {text}\n")
        threading.Thread(target=self._process, args=(text,), daemon=True).start()

    def _prefill(self, text: str):
        self.entry.text = text
        self.entry.focus = True

    def _process(self, text: str):
        if self.core and self.admin and self.flasher:
            res = self.core.process_logic(text, self.admin, self.flasher)
        else:
            res = {"answer": "Ядро не подключено.", "state": "Offline"}
        Clock.schedule_once(lambda dt: self._on_reply(res))

    def _on_reply(self, res: dict):
        self.orb.update_orb(res['state'])
        self.state_lbl.text = f"Состояние: {res['state']}"
        self._append(f"[color=00d4ff]👁 АРГОС [{res['state']}]:[/color]\n{res['answer']}\n\n")

    # ── ГОЛОСОВОЙ ВВОД ────────────────────────────────────
    def _start_listen(self):
        if self._listening:
            return
        self._listening = True
        self._append("[color=88ff88]🎙 Слушаю тебя...[/color]\n")
        threading.Thread(target=self._listen, daemon=True).start()

    def _listen(self):
        text = ""
        if self.core:
            text = self.core.listen() or ""
        Clock.schedule_once(lambda dt: self._after_listen(text))

    def _after_listen(self, text: str):
        self._listening = False
        if text:
            self._send(text)
        else:
            self._append("[color=ff8800]👂 Не распознано. Попробуй снова.[/color]\n")

    def _append(self, text: str):
        self.chat.text += text

if __name__ == '__main__':
    ArgosMobileUI().run()

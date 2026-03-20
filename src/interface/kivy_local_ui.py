"""
kivy_local_ui.py — ARGOS Standalone Local APK UI.

Табы:
  • WiFi           — скан/мониторинг эфира
  • BT             — состояние Bluetooth
  • Root           — проверка root и запрос повышения прав
  • Files          — проводник (plyer filechooser)
  • Terminal/Колибри — локальный терминал + управление Colibri Daemon
  • OTG/Drivers    — USB OTG мониторинг
  • Flasher        — Smart Flasher подсказки/детект
"""
from __future__ import annotations

import os
import shlex
import subprocess
import threading
from typing import Optional

try:
    from kivy.app import App
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.label import Label
    from kivy.uix.button import Button
    from kivy.uix.textinput import TextInput
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
    from kivy.clock import Clock
    from kivy.core.window import Window

    KIVY_OK = True
except ImportError:  # pragma: no cover - Android only
    KIVY_OK = False

try:
    from src.interface.style import S
except Exception:  # pragma: no cover - fallback
    class _S:
        BG = (0.04, 0.05, 0.10, 1)
        CARD = (0.08, 0.11, 0.21, 1)
        GREEN = (0.00, 1.00, 0.40, 1)
        CYAN = (0.00, 1.00, 0.80, 1)
        GRAY = (0.50, 0.60, 0.70, 1)
        BTN_PRIMARY = (0.10, 0.40, 0.80, 1)
        BTN_OK = (0.08, 0.42, 0.22, 1)
        BTN_DANGER = (0.55, 0.10, 0.10, 1)
        PAD = 14
        SPACING = 8
    S = _S()  # type: ignore

# ── Optional managers ---------------------------------------------------------
try:
    from src.connectivity.wifi_sentinel import WiFiSentinel
except Exception:
    WiFiSentinel = None  # type: ignore

try:
    from src.security.root_manager import RootManager
except Exception:
    RootManager = None  # type: ignore

try:
    from src.connectivity.otg_manager import OTGManager
except Exception:
    OTGManager = None  # type: ignore

try:
    from src.factory.flasher import AirFlasher
except Exception:
    AirFlasher = None  # type: ignore

try:
    from src.connectivity.colibri_daemon import ColibriDaemon
except Exception:
    ColibriDaemon = None  # type: ignore

try:
    from src.interface.voice_manager import VoiceManager
    VOICE_OK = True
except Exception:
    VoiceManager = None  # type: ignore
    VOICE_OK = False

try:
    from plyer import filechooser  # type: ignore
    PLYER_FC_OK = True
except Exception:
    filechooser = None  # type: ignore
    PLYER_FC_OK = False

MAX_CMD_OUTPUT = 1200


if KIVY_OK:
    # ── Общие helpers ───────────────────────────────────────────────────────
    class _Card(BoxLayout):
        def __init__(self, title: str, **kwargs):
            super().__init__(orientation="vertical", padding=S.PAD, spacing=S.SPACING, **kwargs)
            self.size_hint_y = None
            self.height = 280
            self.add_widget(Label(text=title, color=S.CYAN, size_hint_y=None, height=32, bold=True))


    def _async(fn):
        """Декоратор для запуска действий в фоне."""

        def wrapper(self, *args, **kwargs):
            threading.Thread(target=lambda: fn(self, *args, **kwargs), daemon=True).start()

        return wrapper


    class WiFiPanel(BoxLayout):
        def __init__(self, sentinel: Optional[WiFiSentinel], **kwargs):
            super().__init__(orientation="vertical", padding=S.PAD, spacing=S.SPACING, **kwargs)
            self._sentinel = sentinel
            self._monitoring = False
            self._log = Label(text="Готов к сканированию WiFi.", color=S.GREEN, size_hint_y=None, height=28)
            self._list = Label(text="—", color=S.GRAY, halign="left", valign="top", size_hint_y=None)
            self._list.bind(texture_size=lambda *_: setattr(self._list, "height", max(self._list.texture_size[1], 120)))

            row = BoxLayout(size_hint_y=None, height=46, spacing=6)
            btn_scan = Button(text="📡 Скан", background_color=S.BTN_PRIMARY)
            btn_scan.bind(on_press=lambda *_: self.scan())
            btn_mon = Button(text="▶ Монитор", background_color=S.BTN_OK)
            btn_mon.bind(on_press=lambda *_: self.toggle_monitor())
            row.add_widget(btn_scan)
            row.add_widget(btn_mon)

            self.add_widget(Label(text="WiFi Sentinel", color=S.CYAN, size_hint_y=None, height=32))
            self.add_widget(self._log)
            sv = ScrollView()
            sv.add_widget(self._list)
            self.add_widget(sv)
            self.add_widget(row)

        @_async
        def scan(self):
            if not self._sentinel:
                Clock.schedule_once(lambda *_: setattr(self._log, "text", "⚠️ WiFi модуль недоступен."))
                return
            try:
                aps = self._sentinel.scan_aps()
                lines = [f"• {ap.ssid or '<нет SSID>'} [{ap.bssid}] ch{ap.channel} {ap.signal_dbm}dBm" for ap in aps]
                text = "\n".join(lines) if lines else "📭 Сети не найдены."
                Clock.schedule_once(lambda *_: setattr(self._list, "text", text))
                Clock.schedule_once(lambda *_: setattr(self._log, "text", "✅ Скан завершён."))
            except Exception as exc:
                Clock.schedule_once(lambda *_: setattr(self._log, "text", f"❌ Ошибка: {exc}"))

        @_async
        def toggle_monitor(self):
            if not self._sentinel:
                Clock.schedule_once(lambda *_: setattr(self._log, "text", "⚠️ WiFi модуль недоступен."))
                return
            if self._monitoring:
                self._monitoring = False
                Clock.schedule_once(lambda *_: setattr(self._log, "text", "⏹ Мониторинг остановлен."))
                return
            msg = self._sentinel.start_monitor()
            self._monitoring = True
            Clock.schedule_once(lambda *_: setattr(self._log, "text", msg))


    class BluetoothPanel(BoxLayout):
        def __init__(self, **kwargs):
            super().__init__(orientation="vertical", padding=S.PAD, spacing=S.SPACING, **kwargs)
            self.add_widget(Label(text="Bluetooth", color=S.CYAN, size_hint_y=None, height=32))
            info = (
                "⚙️ Управление Bluetooth выполняется системно.\n"
                "Используй шторку или настройки Android для включения/парного режима.\n"
                "Для мониторинга BLE подключи внешние инструменты (nRF Connect)."
            )
            self._status = Label(text=info, color=S.GRAY, halign="left", valign="top", size_hint_y=None)
            self._status.bind(texture_size=lambda *_: setattr(self._status, "height", self._status.texture_size[1]))
            sv = ScrollView()
            sv.add_widget(self._status)
            self.add_widget(sv)


    class RootPanel(BoxLayout):
        def __init__(self, manager: Optional[RootManager], **kwargs):
            super().__init__(orientation="vertical", padding=S.PAD, spacing=S.SPACING, **kwargs)
            self._mgr = manager
            self._info = Label(text=self._status(), color=S.GREEN, halign="left", valign="top", size_hint_y=None)
            self._info.bind(texture_size=lambda *_: setattr(self._info, "height", max(self._info.texture_size[1], 120)))

            row = BoxLayout(size_hint_y=None, height=46, spacing=6)
            btn_refresh = Button(text="🔄 Обновить", background_color=S.BTN_PRIMARY)
            btn_refresh.bind(on_press=lambda *_: self._refresh())
            btn_root = Button(text="🛡️ Запрос ROOT", background_color=S.BTN_OK)
            btn_root.bind(on_press=lambda *_: self._request())
            row.add_widget(btn_refresh)
            row.add_widget(btn_root)

            self.add_widget(Label(text="ROOT доступ", color=S.CYAN, size_hint_y=None, height=32))
            self.add_widget(self._info)
            self.add_widget(row)

        def _status(self) -> str:
            if not self._mgr:
                return "⚠️ root_manager недоступен."
            try:
                return self._mgr.status()
            except Exception as exc:
                return f"❌ {exc}"

        def _refresh(self):
            self._info.text = self._status()

        @_async
        def _request(self):
            if not self._mgr:
                Clock.schedule_once(lambda *_: setattr(self._info, "text", "⚠️ root_manager недоступен."))
                return
            try:
                res = self._mgr.request_elevation()
                Clock.schedule_once(lambda *_: setattr(self._info, "text", res))
            except Exception as exc:
                Clock.schedule_once(lambda *_: setattr(self._info, "text", f"❌ {exc}"))


    class FilesPanel(BoxLayout):
        def __init__(self, **kwargs):
            super().__init__(orientation="vertical", padding=S.PAD, spacing=S.SPACING, **kwargs)
            self._path_lbl = Label(text="Файл не выбран.", color=S.GRAY, size_hint_y=None, height=32)
            btn = Button(text="📂 Выбрать файл", background_color=S.BTN_PRIMARY, size_hint_y=None, height=46)
            btn.bind(on_press=lambda *_: self._choose())

            self.add_widget(Label(text="Файлы", color=S.CYAN, size_hint_y=None, height=32))
            self.add_widget(self._path_lbl)
            self.add_widget(btn)

        def _choose(self):
            if not PLYER_FC_OK:
                self._path_lbl.text = "⚠️ plyer.filechooser недоступен."
                return

            def _cb(selection):
                path = selection[0] if selection else "Не выбрано."
                Clock.schedule_once(lambda *_: setattr(self._path_lbl, "text", str(path)))

            try:
                filechooser.open_file(on_selection=_cb)
            except Exception as exc:
                self._path_lbl.text = f"❌ {exc}"


    class TerminalPanel(BoxLayout):
        def __init__(self, voice: Optional[VoiceManager], **kwargs):
            super().__init__(orientation="vertical", padding=S.PAD, spacing=S.SPACING, **kwargs)
            self._voice = voice
            self._colibri: Optional[ColibriDaemon] = None
            self._log = Label(text="> Терминал готов.\n", color=S.GREEN, halign="left", valign="top", size_hint_y=None)
            self._log.bind(texture_size=lambda *_: setattr(self._log, "height", max(self._log.texture_size[1], 160)))
            sv = ScrollView()
            sv.add_widget(self._log)

            self._inp = TextInput(hint_text="Команда shell...", multiline=False, background_color=S.CARD)
            self._inp.bind(on_text_validate=lambda *_: self._run_cmd())
            btn_run = Button(text="▶ Выполнить", size_hint_y=None, height=46, background_color=S.BTN_PRIMARY)
            btn_run.bind(on_press=lambda *_: self._run_cmd())

            btn_colibri = Button(text="🐦 Запуск Колибри", size_hint_y=None, height=46, background_color=S.BTN_OK)
            btn_colibri.bind(on_press=lambda *_: self._start_colibri())
            btn_colibri_stop = Button(text="⏹ Стоп Колибри", size_hint_y=None, height=46, background_color=S.BTN_DANGER)
            btn_colibri_stop.bind(on_press=lambda *_: self._stop_colibri())

            row = BoxLayout(size_hint_y=None, height=46, spacing=6)
            btn_mic = Button(text="🎙 Голос", size_hint_x=0.25, background_color=S.BTN_OK)
            btn_mic.bind(on_press=lambda *_: self._listen())
            row.add_widget(btn_mic)
            row.add_widget(btn_run)

            self.add_widget(Label(text="Терминал + Колибри", color=S.CYAN, size_hint_y=None, height=32))
            self.add_widget(self._inp)
            self.add_widget(row)
            self.add_widget(sv)
            self.add_widget(btn_colibri)
            self.add_widget(btn_colibri_stop)

        def _append(self, text: str, color=None):
            def _upd(_dt=None):
                if color:
                    self._log.color = color
                self._log.text += text + "\n"

            Clock.schedule_once(_upd)

        @_async
        def _run_cmd(self):
            cmd = self._inp.text.strip()
            if not cmd:
                return
            self._inp.text = ""
            self._append(f"> {cmd}", S.GRAY)
            try:
                args = shlex.split(cmd)
                if not args:
                    return
                out = subprocess.check_output(args, shell=False, text=True, stderr=subprocess.STDOUT, timeout=20)
            except subprocess.CalledProcessError as exc:
                out = exc.output or str(exc)
            except Exception as exc:
                out = str(exc)
            self._append(out.strip()[:MAX_CMD_OUTPUT])

        @_async
        def _start_colibri(self):
            if ColibriDaemon is None:
                self._append("⚠️ Colibri недоступен.", S.GRAY)
                return
            try:
                work_dir = os.path.join(App.get_running_app().user_data_dir, "colibri")  # type: ignore[attr-defined]
            except Exception as exc:
                work_dir = os.path.join(os.getcwd(), "colibri")
                self._append(f"ℹ️ user_data_dir недоступен: {exc}", S.GRAY)
            os.makedirs(work_dir, exist_ok=True)
            if not self._colibri:
                self._colibri = ColibriDaemon(work_dir=work_dir, light_mode=True)
            self._colibri.start()
            self._append("✅ Colibri daemon запущен.")

        @_async
        def _stop_colibri(self):
            if self._colibri:
                try:
                    self._colibri.stop()
                    self._append("⏹ Colibri остановлен.")
                except Exception as exc:
                    self._append(f"❌ {exc}", S.BTN_DANGER)
            else:
                self._append("ℹ️ Colibri не запущен.", S.GRAY)

        @_async
        def _listen(self):
            voice = self._ensure_voice()
            if not voice:
                self._append("⚠️ Голосовой ввод недоступен.", S.GRAY)
                return
            try:
                text = voice.listen()
                if text:
                    self._append(f"🎙 {text}", S.GREEN)
                    self._inp.text = text
                    self._run_cmd()
                else:
                    self._append("👂 Не распознано.", S.GRAY)
            except Exception as exc:
                self._append(f"❌ Голос: {exc}", S.BTN_DANGER)

        def _ensure_voice(self) -> Optional[VoiceManager]:
            if self._voice:
                return self._voice
            if not VOICE_OK:
                return None
            try:
                self._voice = VoiceManager()
                return self._voice
            except Exception as exc:
                self._append(f"⚠️ Голос недоступен: {exc}", S.GRAY)
                self._voice = None
                return None


    class OTGPanel(BoxLayout):
        def __init__(self, manager: Optional[OTGManager], **kwargs):
            super().__init__(orientation="vertical", padding=S.PAD, spacing=S.SPACING, **kwargs)
            self._mgr = manager
            self._info = Label(text="Готов к сканированию OTG.", color=S.GREEN, size_hint_y=None, height=28)
            self._list = Label(text="—", color=S.GRAY, halign="left", valign="top", size_hint_y=None)
            self._list.bind(texture_size=lambda *_: setattr(self._list, "height", max(self._list.texture_size[1], 140)))

            btn_scan = Button(text="🔌 Скан OTG", background_color=S.BTN_PRIMARY, size_hint_y=None, height=46)
            btn_scan.bind(on_press=lambda *_: self._scan())

            self.add_widget(Label(text="OTG / Drivers", color=S.CYAN, size_hint_y=None, height=32))
            self.add_widget(self._info)
            sv = ScrollView()
            sv.add_widget(self._list)
            self.add_widget(sv)
            self.add_widget(btn_scan)

        @_async
        def _scan(self):
            if not self._mgr:
                Clock.schedule_once(lambda *_: setattr(self._info, "text", "⚠️ OTG модуль недоступен."))
                return
            try:
                supported = self._mgr.is_otg_supported()
                devices = self._mgr.scan_devices()
                lines = [d.info() for d in devices] if devices else ["📭 Устройства не найдены."]
                Clock.schedule_once(lambda *_: setattr(self._info, "text", f"OTG поддержка: {'✅' if supported else '❌'}"))
                Clock.schedule_once(lambda *_: setattr(self._list, "text", "\n".join(lines)))
            except Exception as exc:
                Clock.schedule_once(lambda *_: setattr(self._info, "text", f"❌ {exc}"))


    class FlasherPanel(BoxLayout):
        def __init__(self, flasher: Optional[AirFlasher], **kwargs):
            super().__init__(orientation="vertical", padding=S.PAD, spacing=S.SPACING, **kwargs)
            self._flasher = flasher
            self._info = Label(text="Smart Flasher готов.", color=S.GREEN, size_hint_y=None, height=28)
            self._list = Label(text="—", color=S.GRAY, halign="left", valign="top", size_hint_y=None)
            self._list.bind(texture_size=lambda *_: setattr(self._list, "height", max(self._list.texture_size[1], 140)))

            row = BoxLayout(size_hint_y=None, height=46, spacing=6)
            btn_ports = Button(text="🔍 Порты", background_color=S.BTN_PRIMARY)
            btn_ports.bind(on_press=lambda *_: self._scan_ports())
            btn_detect = Button(text="🧠 Детект USB", background_color=S.BTN_OK)
            btn_detect.bind(on_press=lambda *_: self._detect())
            row.add_widget(btn_ports)
            row.add_widget(btn_detect)

            self.add_widget(Label(text="Flasher", color=S.CYAN, size_hint_y=None, height=32))
            self.add_widget(self._info)
            sv = ScrollView()
            sv.add_widget(self._list)
            self.add_widget(sv)
            self.add_widget(row)

        @_async
        def _scan_ports(self):
            if not self._flasher:
                Clock.schedule_once(lambda *_: setattr(self._info, "text", "⚠️ flasher недоступен."))
                return
            try:
                ports = self._flasher.scan_ports()
                Clock.schedule_once(lambda *_: setattr(self._list, "text", "\n".join(ports)))
                Clock.schedule_once(lambda *_: setattr(self._info, "text", "✅ Порты обновлены."))
            except Exception as exc:
                Clock.schedule_once(lambda *_: setattr(self._info, "text", f"❌ {exc}"))

        @_async
        def _detect(self):
            if not self._flasher:
                Clock.schedule_once(lambda *_: setattr(self._info, "text", "⚠️ flasher недоступен."))
                return
            try:
                rep = self._flasher.detect_usb_chips_report()
                Clock.schedule_once(lambda *_: setattr(self._list, "text", rep))
                Clock.schedule_once(lambda *_: setattr(self._info, "text", "✅ Детект выполнен."))
            except Exception as exc:
                Clock.schedule_once(lambda *_: setattr(self._info, "text", f"❌ {exc}"))


    class ArgosLocalApp(App):
        """Полноценный локальный APK интерфейс ARGOS."""

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self._wifi = WiFiSentinel() if WiFiSentinel else None
            self._root = RootManager() if RootManager else None
            self._otg = OTGManager() if OTGManager else None
            self._flasher = AirFlasher() if AirFlasher else None
            self._voice: Optional[VoiceManager] = None

        def build(self):
            Window.clearcolor = S.BG
            root = BoxLayout(orientation="vertical")

            tp = TabbedPanel(do_default_tab=False)

            tab_wifi = TabbedPanelItem(text="📡 WiFi")
            tab_wifi.add_widget(WiFiPanel(self._wifi))
            tp.add_widget(tab_wifi)

            tab_bt = TabbedPanelItem(text="🔵 BT")
            tab_bt.add_widget(BluetoothPanel())
            tp.add_widget(tab_bt)

            tab_root = TabbedPanelItem(text="🛡 Root")
            tab_root.add_widget(RootPanel(self._root))
            tp.add_widget(tab_root)

            tab_files = TabbedPanelItem(text="📂 Files")
            tab_files.add_widget(FilesPanel())
            tp.add_widget(tab_files)

            tab_term = TabbedPanelItem(text="🖥 Term")
            tab_term.add_widget(TerminalPanel(self._voice))
            tp.add_widget(tab_term)

            tab_otg = TabbedPanelItem(text="🔌 OTG")
            tab_otg.add_widget(OTGPanel(self._otg))
            tp.add_widget(tab_otg)

            tab_flash = TabbedPanelItem(text="⚡ Flasher")
            tab_flash.add_widget(FlasherPanel(self._flasher))
            tp.add_widget(tab_flash)

            root.add_widget(tp)
            return root

else:
    class ArgosLocalApp:
        """Stub when Kivy is unavailable."""

        def run(self):
            print("⚠️  Kivy not installed. Install kivy to run ArgosLocalApp.")

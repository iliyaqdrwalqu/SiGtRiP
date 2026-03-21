import re
import unittest
from pathlib import Path


class TestGuiResilience(unittest.TestCase):
    def test_gui_process_handles_core_exceptions(self):
        text = Path("src/interface/gui.py").read_text(encoding="utf-8")
        self.assertIn("except Exception as e:", text)
        self.assertIn("\"state\": \"ERROR\"", text)
        self.assertIn("❌ Ошибка выполнения команды:", text)

    def test_gui_response_handler_uses_safe_dict_access(self):
        text = Path("src/interface/gui.py").read_text(encoding="utf-8")
        self.assertIn("EMPTY_CORE_RESPONSE_TEXT = \"❌ Пустой ответ от ядра.\"", text)
        self.assertIn("payload = res if res is not None else {}", text)
        self.assertIn("state = payload.get(\"state\", \"ERROR\")", text)
        self.assertIn("answer = payload.get(\"answer\", self.EMPTY_CORE_RESPONSE_TEXT)", text)

    def test_update_metrics_runs_psutil_off_ui_thread(self):
        """psutil.cpu_percent(interval=…) в _update_metrics должен вызываться
        внутри вложенной функции _collect, которая запускается в daemon-потоке,
        а не напрямую в теле _update_metrics."""
        text = Path("src/interface/gui.py").read_text(encoding="utf-8")
        # Find _update_metrics method body
        match = re.search(
            r"def _update_metrics\(self\):(.*?)(?=\n    def |\Z)", text, re.DOTALL
        )
        self.assertIsNotNone(match, "_update_metrics не найден в gui.py")
        body = match.group(1)
        # The blocking call must be inside a nested function (not at top level of method)
        self.assertIn("def _collect", body,
                      "_update_metrics должен делегировать сбор метрик функции _collect")
        self.assertIn("threading.Thread", body,
                      "_update_metrics должен запускать _collect в daemon-потоке")
        self.assertIn("cpu_percent(interval=", body,
                      "cpu_percent не найден в _update_metrics")

    def test_refresh_system_tab_runs_psutil_off_ui_thread(self):
        """psutil.cpu_percent(interval=…) в _refresh_system_tab должен вызываться
        внутри вложенной функции _collect, запускаемой в daemon-потоке."""
        text = Path("src/interface/gui.py").read_text(encoding="utf-8")
        match = re.search(
            r"def _refresh_system_tab\(self\):(.*?)(?=\n    def |\Z)", text, re.DOTALL
        )
        self.assertIsNotNone(match, "_refresh_system_tab не найден в gui.py")
        body = match.group(1)
        self.assertIn("def _collect", body,
                      "_refresh_system_tab должен делегировать сбор метрик функции _collect")
        self.assertIn("threading.Thread", body,
                      "_refresh_system_tab должен запускать _collect в daemon-потоке")
        self.assertIn("cpu_percent(interval=", body,
                      "cpu_percent не найден в _refresh_system_tab")

    def test_apply_metrics_method_exists(self):
        """_apply_metrics должен существовать как отдельный метод,
        вызываемый из UI-потока через self.after(0, ...)."""
        text = Path("src/interface/gui.py").read_text(encoding="utf-8")
        self.assertIn("def _apply_metrics(self,", text,
                      "_apply_metrics не найден в gui.py")
        self.assertIn("self.after(0,", text,
                      "self.after(0, ...) не найден — UI-обновление должно планироваться через after()")

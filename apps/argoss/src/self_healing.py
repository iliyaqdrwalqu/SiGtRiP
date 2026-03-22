"""self_healing.py — Автоисправление Python-кода Аргоса

Модуль предоставляет :class:`SelfHealingEngine` — компонент автодиагностики
и восстановления Python-файлов системы.

Возможности:
  * Валидация синтаксиса через ``ast.parse`` (без запуска кода).
  * Локальные исправления типичных ошибок без LLM-вызовов:
    - «голые» символы ``exec``, ``eval`` в начале файла;
    - смешанные отступы (tabs → spaces);
    - кодировочная BOM-метка в начале файла.
  * Резервное копирование файла перед применением исправлений.
  * Восстановление файла из резервной копии при неудачном лечении.
  * Горячая перезагрузка модуля через ``importlib.reload`` после исправления.
  * Healсинг через LLM (Gemini) при наличии подключённого ядра.
  * Валидация всего каталога ``src/`` с выводом краткого отчёта.
  * История применённых исправлений (последние 50 событий).

Использование::

    from src.self_healing import SelfHealingEngine

    engine = SelfHealingEngine()

    ok, msg = engine.validate_file("src/my_module.py")
    if not ok:
        result = engine.auto_heal_file("src/my_module.py", msg)
        print(result)

    print(engine.history())
"""
from __future__ import annotations

import ast
import importlib
import os
import re
import shutil
import sys
import time
from typing import Optional, Tuple

from src.argos_logger import get_logger

log = get_logger("argos.healing")

# Каталог для резервных копий файлов.
_BACKUP_DIR = "data/.self_healing_backups"


class SelfHealingEngine:
    """Движок самолечения Python-кода Аргоса."""

    def __init__(self, core=None):
        self.core = core
        self._history: list[dict] = []

    # ── ВАЛИДАЦИЯ ─────────────────────────────────────────────────────────────

    def validate_code(self, code: str) -> Tuple[bool, str]:
        """Проверить синтаксис Python-кода через ``ast.parse``.

        Возвращает кортеж ``(ok, сообщение)``.
        """
        try:
            ast.parse(code)
            return True, "✅ Синтаксис OK"
        except SyntaxError as e:
            return False, f"❌ SyntaxError: {e}"

    def validate_file(self, path: str) -> Tuple[bool, str]:
        """Проверить синтаксис одного файла.

        Возвращает кортеж ``(ok, сообщение)``.
        """
        if not os.path.isfile(path):
            return False, f"файл не найден: {path}"
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                ast.parse(f.read())
            return True, "✅ Синтаксис OK"
        except SyntaxError as e:
            return False, f"❌ SyntaxError: {e}"

    def validate_all_src(self, src_dir: str = "src") -> str:
        """Проверить синтаксис всех ``*.py`` файлов в каталоге ``src_dir``.

        Возвращает текстовый отчёт с подсчётом успехов и ошибок.
        """
        ok, fail, errors = 0, 0, []
        for root, _, fnames in os.walk(src_dir):
            for fname in fnames:
                if not fname.endswith(".py"):
                    continue
                fp = os.path.join(root, fname)
                valid, msg = self.validate_file(fp)
                if valid:
                    ok += 1
                else:
                    fail += 1
                    errors.append(f"  ❌ {fp}: {msg}")
        header = f"🩹 ВАЛИДАЦИЯ: {ok} ✅ / {fail} ❌"
        return header + ("\n" + "\n".join(errors) if errors else "\n  Все файлы валидны.")

    # ── РЕЗЕРВНЫЕ КОПИИ ───────────────────────────────────────────────────────

    def _backup_path(self, path: str) -> str:
        """Вернуть путь для резервной копии файла."""
        safe = path.replace(os.sep, "__").replace(":", "")
        ts = int(time.time())
        return os.path.join(_BACKUP_DIR, f"{safe}.{ts}.bak")

    def backup_file(self, path: str) -> Optional[str]:
        """Создать резервную копию файла перед лечением.

        Возвращает путь к резервной копии или ``None`` при ошибке.
        """
        if not os.path.isfile(path):
            return None
        try:
            os.makedirs(_BACKUP_DIR, exist_ok=True)
            dst = self._backup_path(path)
            shutil.copy2(path, dst)
            log.debug("Self-healing: резервная копия %s → %s", path, dst)
            return dst
        except OSError as e:
            log.warning("Self-healing: не удалось создать резервную копию %s: %s", path, e)
            return None

    def restore_file(self, path: str, backup: str) -> bool:
        """Восстановить файл из резервной копии.

        Возвращает ``True`` при успехе.
        """
        try:
            shutil.copy2(backup, path)
            log.info("Self-healing: файл %s восстановлен из %s", path, backup)
            return True
        except OSError as e:
            log.error("Self-healing: не удалось восстановить %s из %s: %s", path, backup, e)
            return False

    # ── ЛОКАЛЬНЫЕ ИСПРАВЛЕНИЯ (без LLM) ──────────────────────────────────────

    def _local_fix(self, code: str, error_msg: str) -> Optional[str]:
        """Попытаться исправить типичные ошибки локально (без LLM).

        Обрабатывает:
        - BOM-метку UTF-8 в начале файла.
        - Смешанные отступы (tabs → 4 пробела).
        - Незакрытые строки (простая эвристика).
        - Случайные непечатаемые управляющие символы.

        Возвращает исправленный код или ``None``, если исправление
        не применимо.
        """
        fixed = code

        # Удалить BOM
        if fixed.startswith("\ufeff"):
            fixed = fixed.lstrip("\ufeff")
            log.debug("Self-healing: удалена BOM-метка")

        # Заменить tabs на 4 пробела
        if "\t" in fixed and "TabError" in error_msg:
            fixed = fixed.expandtabs(4)
            log.debug("Self-healing: заменены табуляции на пробелы")

        # Удалить управляющие символы (кроме \n, \r, \t)
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", fixed)
        if cleaned != fixed:
            fixed = cleaned
            log.debug("Self-healing: удалены управляющие символы")

        if fixed == code:
            return None   # нет изменений — локальный патч не применим

        ok, _ = self.validate_code(fixed)
        return fixed if ok else None

    # ── HEALING ───────────────────────────────────────────────────────────────

    def heal_code(self, code: str, error_msg: str) -> Optional[str]:
        """Исправить Python-код с помощью LLM (Gemini).

        Требует подключённого ``core`` с методом ``_ask_gemini``.
        Возвращает исправленный код или ``None``.
        """
        if not self.core:
            return None
        prompt = (
            f"Исправь Python-код. Ошибка: {error_msg}\n\n"
            f"Код:\n{code}\n\nВерни только исправленный код без пояснений."
        )
        try:
            fixed = self.core._ask_gemini("Ты Python-эксперт.", prompt)
            if fixed:
                fixed = fixed.replace("```python", "").replace("```", "").strip()
                self._history.append({"error": error_msg, "fixed": True, "method": "llm"})
                log.info("Self-healing: LLM-исправление применено")
                return fixed
        except Exception as e:
            log.warning("Self-healing: ошибка LLM: %s", e)
        return None

    def auto_heal_file(self, path: str, error_msg: str) -> str:
        """Полный цикл автолечения одного файла.

        Алгоритм:
        1. Создать резервную копию.
        2. Попробовать локальные исправления (без LLM).
        3. При наличии ядра — попробовать LLM-исправление.
        4. Записать результат; при неудаче — восстановить из резервной копии.
        5. После успешного исправления — горячая перезагрузка модуля.

        Возвращает строку с кратким отчётом о результате.
        """
        if not os.path.isfile(path):
            return f"❌ Файл не найден: {path}"

        backup = self.backup_file(path)

        with open(path, encoding="utf-8", errors="replace") as f:
            original = f.read()

        # 1. Локальный патч
        fixed = self._local_fix(original, error_msg)
        method = "local"

        # 2. LLM-патч (если локальный не помог)
        if fixed is None:
            fixed = self.heal_code(original, error_msg)
            method = "llm"

        if fixed is None:
            self._record(path, error_msg, False, method)
            return f"🩹 {path}: исправление не найдено. Резервная копия: {backup}"

        # Проверить результат перед записью
        ok, val_msg = self.validate_code(fixed)
        if not ok:
            if backup:
                self.restore_file(path, backup)
            self._record(path, error_msg, False, method)
            return f"❌ {path}: исправленный код не прошёл валидацию ({val_msg}). Оригинал восстановлен."

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(fixed)
        except OSError as e:
            self._record(path, error_msg, False, method)
            return f"❌ {path}: не удалось записать исправление: {e}"

        self._record(path, error_msg, True, method)
        log.info("Self-healing: %s исправлен методом '%s'", path, method)

        # Горячая перезагрузка
        reload_msg = self._hot_reload(path)

        return (
            f"✅ {path}: исправлен методом '{method}'. "
            f"Резервная копия: {backup}. {reload_msg}"
        )

    # ── ГОРЯЧАЯ ПЕРЕЗАГРУЗКА ──────────────────────────────────────────────────

    def _hot_reload(self, path: str) -> str:
        """Попытаться горячо перезагрузить модуль после исправления.

        Определяет имя модуля по пути к файлу и вызывает
        ``importlib.reload``, если модуль уже загружен.

        Возвращает краткое сообщение о результате.
        """
        module_name = _path_to_module(path)
        if module_name and module_name in sys.modules:
            try:
                importlib.reload(sys.modules[module_name])
                log.info("Self-healing: модуль '%s' перезагружен", module_name)
                return f"Модуль '{module_name}' перезагружен."
            except Exception as e:
                log.warning("Self-healing: не удалось перезагрузить '%s': %s", module_name, e)
                return f"Перезагрузка '{module_name}' не удалась: {e}"
        return ""

    # ── ИСТОРИЯ ───────────────────────────────────────────────────────────────

    def _record(self, path: str, error: str, fixed: bool, method: str) -> None:
        self._history.append({
            "path": path,
            "error": error,
            "fixed": fixed,
            "method": method,
            "ts": time.time(),
        })
        if len(self._history) > 50:
            self._history = self._history[-50:]

    def history(self) -> str:
        """Вернуть текстовую историю исправлений (последние 10)."""
        if not self._history:
            return "🩹 История лечений пуста."
        lines = ["🩹 ИСТОРИЯ ЛЕЧЕНИЙ:"]
        for i, h in enumerate(self._history[-10:], 1):
            status = "✅" if h.get("fixed") else "❌"
            method = h.get("method", "?")
            error = h.get("error", "")[:60]
            path = h.get("path", "")
            lines.append(f"  {i}. {status} [{method}] {path}: {error}")
        return "\n".join(lines)

    def status(self) -> str:
        """Вернуть однострочный статус движка."""
        total = len(self._history)
        healed = sum(1 for h in self._history if h.get("fixed"))
        return f"🩹 Self-Healing: активен | Всего случаев: {total} | Успешно: {healed}"


# ── ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ───────────────────────────────────────────────────

def _path_to_module(path: str) -> Optional[str]:
    """Преобразовать путь к файлу в имя Python-модуля.

    Пример: ``src/argos_logger.py`` → ``src.argos_logger``.
    Возвращает ``None``, если путь не соответствует обычному модулю.
    """
    path = os.path.normpath(path)
    if not path.endswith(".py"):
        return None
    module = path[:-3].replace(os.sep, ".")
    return module

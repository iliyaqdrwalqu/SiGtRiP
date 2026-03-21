"""
Custom pyjnius recipe that patches jnius_utils.pxi to replace the
Python-2-only ``long`` built-in with ``int`` so Cython 3.x / Python 3
can compile it without raising ``undeclared name not builtin: long``.

This recipe extends the built-in p4a pyjnius recipe and overrides
``apply_patches`` to inject the fix BEFORE Cython compilation.

ПАТЧ [FIX-LONG-LONG]:
  ``re.sub(r"\\blong\\b", "int", ...)`` заменяет ОБА слова в ``long long``,
  превращая ``ctypedef long long jlong`` / ``cdef long long x`` в
  ``ctypedef int int jlong`` / ``cdef int int x`` — что вызывает ошибку
  Cython «Declarator should be empty».
  Исправление: сначала защищаем ``long long`` маркером, только потом
  заменяем одиночный ``long`` (Python 2 builtin) на ``int``, затем
  восстанавливаем ``long long``.
  ``ctypedef long long jlong`` — правильный 64-битный тип для JNI.
"""

import re
from pathlib import Path

from pythonforandroid.recipes.pyjnius import PyjniusRecipe as _PyjniusBase

_LONG_LONG_PLACEHOLDER = "__ARGOS_LONG_LONG__"


class PyjniusRecipe(_PyjniusBase):
    """Extends the built-in pyjnius recipe with a Python 3 / Cython 3 fix."""

    def apply_patches(self, arch, build_dir=None):
        if build_dir is None:
            build_dir = self.get_build_dir(arch.arch)
        # Patch source BEFORE upstream patches so the fix is always applied.
        self._fix_long_builtin(build_dir)
        super().apply_patches(arch, build_dir=build_dir)

    @staticmethod
    def _fix_long_builtin(build_dir):
        """Replace the Python-2-only ``long`` builtin with ``int`` in all .pxi files.

        C-level ``long long`` type declarations are preserved intact so Cython
        does not produce "Declarator should be empty" errors.
        """
        build_path = Path(build_dir)
        if not build_path.exists():
            return
        for pxi_file in build_path.rglob('*.pxi'):
            try:
                content = pxi_file.read_text(encoding='utf-8', errors='replace')
                # Step 1: protect C ``long long`` from the broad replacement below.
                protected = content.replace("long long", _LONG_LONG_PLACEHOLDER)
                # Step 2: replace Python 2 ``long`` builtin with ``int``.
                patched = re.sub(r"\blong\b", "int", protected)
                # Step 3: restore ``long long`` (keeps jlong as 64-bit).
                patched = patched.replace(_LONG_LONG_PLACEHOLDER, "long long")
                # Step 4: fix any pre-existing ``ctypedef int int jlong`` artefacts
                # that may have been left by older build-cache runs.
                patched = re.sub(
                    r"ctypedef\s+int\s+int\s+jlong", "ctypedef long long jlong", patched
                )
                if patched != content:
                    pxi_file.write_text(patched, encoding='utf-8')
                    print(f"[custom pyjnius] Patched long/jlong in {pxi_file.name}")
            except OSError as exc:
                print(f"[custom pyjnius] Could not patch {pxi_file}: {exc}")


recipe = PyjniusRecipe()

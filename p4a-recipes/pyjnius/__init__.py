"""
Custom pyjnius recipe that patches pyjnius source files for Python 3 / Cython 3:
  - Replaces the Python-2-only ``long`` built-in with ``int`` in all .pxi files
    so Cython 3.x / Python 3 can compile without "undeclared name not builtin: long".
  - Injects ``# cython: language_level=3`` into jnius.pyx and all .pxi files to
    prevent "Declarator should be empty" errors caused by Cython defaulting to
    Python 2 semantics when the directive is absent.

This recipe extends the built-in p4a pyjnius recipe and overrides
``apply_patches`` to inject both fixes BEFORE Cython compilation.
"""

import re
from pathlib import Path

from pythonforandroid.recipes.pyjnius import PyjniusRecipe as _PyjniusBase

_LANGUAGE_LEVEL_DIRECTIVE = "# cython: language_level=3\n"


class PyjniusRecipe(_PyjniusBase):
    """Extends the built-in pyjnius recipe with a Python 3 / Cython 3 fix."""

    def apply_patches(self, arch, build_dir=None):
        if build_dir is None:
            build_dir = self.get_build_dir(arch.arch)
        # Patch source BEFORE upstream patches so the fix is always applied.
        self._fix_long_builtin(build_dir)
        self._inject_language_level(build_dir)
        super().apply_patches(arch, build_dir=build_dir)

    @staticmethod
    def _fix_long_builtin(build_dir):
        """Replace the Python-2-only ``long`` builtin with ``int`` in all .pxi files."""
        build_path = Path(build_dir)
        if not build_path.exists():
            return
        for pxi_file in build_path.rglob('*.pxi'):
            try:
                content = pxi_file.read_text(encoding='utf-8', errors='replace')
                patched = re.sub(r"\blong\b", "int", content)
                patched_jlong = re.sub(
                    r"ctypedef\s+int\s+int\s+jlong", "ctypedef long jlong", patched
                )
                if patched_jlong != content:
                    pxi_file.write_text(patched_jlong, encoding='utf-8')
                    changes = []
                    if patched != content:
                        changes.append('long→int')
                    if patched_jlong != patched:
                        changes.append('jlong typedef')
                    change_label = ' & '.join(changes)
                    print(f"[custom pyjnius] Fixed {change_label} in {pxi_file.name}")
            except OSError as exc:
                print(f"[custom pyjnius] Could not patch {pxi_file}: {exc}")

    @staticmethod
    def _inject_language_level(build_dir):
        """Inject ``# cython: language_level=3`` into .pyx and .pxi files.

        Without this directive Cython defaults to Python 2 semantics, which
        causes "Declarator should be empty" errors when compiling pyjnius 1.6.1
        under Python 3.10 with Cython 0.29.x.
        """
        build_path = Path(build_dir)
        if not build_path.exists():
            return
        for cython_file in list(build_path.rglob('*.pyx')) + list(build_path.rglob('*.pxi')):
            try:
                content = cython_file.read_text(encoding='utf-8', errors='replace')
                if 'language_level' not in content:
                    cython_file.write_text(_LANGUAGE_LEVEL_DIRECTIVE + content, encoding='utf-8')
                    print(f"[custom pyjnius] Injected language_level=3 into {cython_file.name}")
            except OSError as exc:
                print(f"[custom pyjnius] Could not inject language_level into {cython_file}: {exc}")


recipe = PyjniusRecipe()

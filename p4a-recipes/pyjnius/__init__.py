"""
Custom pyjnius recipe that patches jnius_utils.pxi to replace the
Python-2-only ``long`` built-in with ``int`` so Cython 3.x / Python 3
can compile it without raising ``undeclared name not builtin: long``.

This recipe extends the built-in p4a pyjnius recipe and overrides
``apply_patches`` to inject the fix BEFORE Cython compilation.
"""

import re
from pathlib import Path

from pythonforandroid.recipes.pyjnius import PyjniusRecipe as _PyjniusBase


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
                    change_label = ' & '.join(changes) or 'patch'
                    print(f"[custom pyjnius] Fixed {change_label} in {pxi_file.name}")
            except OSError as exc:
                print(f"[custom pyjnius] Could not patch {pxi_file}: {exc}")


recipe = PyjniusRecipe()


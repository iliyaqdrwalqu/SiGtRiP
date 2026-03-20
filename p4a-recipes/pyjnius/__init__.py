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
        """Replace the Python-2-only ``long`` builtin with ``int`` in all .pxi files.

        Strategy:
          1. Protect ``long long`` (a valid C type used in Cython casts like
             ``<long long>``) by temporarily replacing it with a sentinel so the
             subsequent ``\\blong\\b`` substitution does not turn it into
             ``int int``, which Cython rejects with "Declarator should be empty".
          2. Replace remaining standalone ``long`` occurrences (Python 2 built-in
             ``long`` type / callable) with ``int``.
          3. Restore ``long long`` from the sentinel.
          4. Fix the ``ctypedef long jlong`` definition in jni.pxi which the
             broad replacement in step 2 would otherwise corrupt.
        """
        _SENTINEL = "\x00LONGLONG\x00"
        build_path = Path(build_dir)
        if not build_path.exists():
            return
        for pxi_file in build_path.rglob('*.pxi'):
            try:
                content = pxi_file.read_text(encoding='utf-8', errors='replace')
                # Step 1: protect 'long long' C type
                guarded = content.replace('long long', _SENTINEL)
                # Step 2: replace standalone Python 2 'long' builtin with 'int'
                patched = re.sub(r"\blong\b", "int", guarded)
                # Step 3: restore 'long long'
                patched = patched.replace(_SENTINEL, 'long long')
                # Step 4: fix jlong typedef if corrupted by earlier bad patches
                patched = re.sub(
                    r"ctypedef\s+int\s+int\s+jlong", "ctypedef long jlong", patched
                )
                if patched != content:
                    pxi_file.write_text(patched, encoding='utf-8')
                    print(f"[custom pyjnius] Fixed long→int (safe) in {pxi_file.name}")
            except OSError as exc:
                print(f"[custom pyjnius] Could not patch {pxi_file}: {exc}")


recipe = PyjniusRecipe()

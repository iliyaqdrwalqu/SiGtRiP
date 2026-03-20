"""
python-for-android build hook.

Applies patches required to build pyjnius with modern Cython + Python 3:
  - Injects ``# cython: language_level=3`` into jnius.pyx and all .pxi files
    so Cython does not default to Python 2 semantics (which causes
    "Declarator should be empty" errors in pyjnius 1.6.1 on Python 3.10).
  - Replaces the Python-2-only ``long`` built-in with ``int`` in
    ``jnius_utils.pxi`` so Cython 3.x / Python 3 can compile it.

Also disables Python stdlib C extensions that cannot be built against the
Android NDK (no grp/group, no libuuid, no liblzma in the NDK sysroot):
  - grp
  - _uuid
  - _lzma
"""

from __future__ import annotations

import glob
import os
import re

# Ensure third-party Cython builds default to Python 3 semantics during recipe compilation.
os.environ.setdefault("CYTHON_DEFAULT_LANGUAGE_LEVEL", "3")

_LANGUAGE_LEVEL_DIRECTIVE = "# cython: language_level=3\n"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_long_to_int(path: str) -> None:
    """Replace all word-boundary occurrences of ``long`` with ``int`` in *path*.

    This covers both function-call style (``long(x)``) and type-reference style
    (``isinstance(x, long)``) that pyjnius uses for Python 2 compatibility.
    """
    with open(path, "r", encoding="utf-8") as fh:
        src = fh.read()
    patched = re.sub(r"\blong\b", "int", src)
    if patched == src:
        return
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(patched)
    print(f"[p4a_hook] Patched 'long' -> 'int' in: {path}")


def _inject_language_level(path: str) -> None:
    """Prepend ``# cython: language_level=3`` to *path* if not already present.

    This prevents Cython from defaulting to Python 2 semantics, which causes
    "Declarator should be empty" errors when compiling pyjnius 1.6.1 under
    Python 3.10 with Cython 0.29.x.
    """
    with open(path, "r", encoding="utf-8") as fh:
        src = fh.read()
    if "language_level" in src:
        return
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(_LANGUAGE_LEVEL_DIRECTIVE + src)
    print(f"[p4a_hook] Injected language_level=3 into: {path}")


def _patch_jni_jlong(path: str) -> None:
    """Replace invalid ``ctypedef int int jlong`` definition with ``long``."""
    with open(path, "r", encoding="utf-8") as fh:
        src = fh.read()
    patched = re.sub(r"ctypedef\s+int\s+int\s+jlong", "ctypedef long jlong", src)
    if patched == src:
        return
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(patched)
    print(f"[p4a_hook] Patched jlong typedef in: {path}")


# ---------------------------------------------------------------------------
# p4a hook entry-points
# ---------------------------------------------------------------------------

def before_apk_build(toolchain) -> None:
    """Called by p4a before the APK is assembled (after recipe compilation).

    At this stage recipes are already compiled; we use this hook as an extra
    safety net to patch any pyjnius Python source files that may still reference
    the Python-2-only ``long`` builtin.
    """
    _fix_pyjnius(toolchain)
    _disable_android_incompatible_modules(toolchain)


# ---------------------------------------------------------------------------
# Patch implementations
# ---------------------------------------------------------------------------

def _fix_pyjnius(toolchain) -> None:
    """
    Patch pyjnius source files for Python 3 / Cython 3 compatibility:
      - Inject ``# cython: language_level=3`` into .pyx and .pxi files to
        prevent "Declarator should be empty" errors.
      - Replace ``long`` with ``int`` in jnius_utils.pxi (Python-2-only builtin).
      - Fix ``ctypedef int int jlong`` typedef in jni.pxi.
    """
    storage = getattr(toolchain, "storage_dir", None) or ""
    search_roots = [
        storage,
        os.path.expanduser("~/.buildozer"),
        os.getcwd(),
    ]
    for root in search_roots:
        if not root:
            continue
        for match in glob.glob(
            os.path.join(root, "**", "jnius*.pxi"), recursive=True
        ):
            _inject_language_level(match)
            _patch_long_to_int(match)
        for match in glob.glob(
            os.path.join(root, "**", "jnius*.pyx"), recursive=True
        ):
            _inject_language_level(match)
        for match in glob.glob(os.path.join(root, "**", "jni.pxi"), recursive=True):
            _inject_language_level(match)
            _patch_jni_jlong(match)


def _disable_android_incompatible_modules(toolchain) -> None:
    """
    Prevent Python-for-Android from trying to build stdlib C extensions
    that depend on headers / libraries absent from the Android NDK sysroot:

      * grp   – POSIX group-database functions (setgrent / getgrent …)
      * _uuid – requires libuuid (not bundled with Android NDK)
      * _lzma – requires liblzma / lzma.h (not bundled with Android NDK)
    """
    incompatible = {"grp", "_uuid", "_lzma"}
    try:
        from pythonforandroid.recipes.python3 import Python3Recipe  # type: ignore[import]

        existing = set(getattr(Python3Recipe, "disabled_modules", []))
        new_disabled = sorted(existing | incompatible)
        Python3Recipe.disabled_modules = new_disabled
        added = incompatible - existing
        if added:
            print(
                f"[p4a_hook] Added to Python3Recipe.disabled_modules: "
                f"{', '.join(sorted(added))}"
            )
    except Exception as exc:  # noqa: BLE001
        print(
                f"[p4a_hook] WARNING: Could not patch Python3Recipe.disabled_modules "
                f"({exc}). The build may still succeed if p4a already excludes "
                f"grp/_uuid/_lzma for Android, but watch for NDK linker errors."
            )

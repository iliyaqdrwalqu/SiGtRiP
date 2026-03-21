"""
python-for-android build hook.

Applies patches required to build pyjnius with modern Cython + Python 3:
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LONG_LONG_PLACEHOLDER = "__ARGOS_LONG_LONG__"


def _patch_long_to_int(path: str) -> None:
    """Replace Python-2-only ``long`` builtin with ``int`` in *path*.

    This covers both function-call style (``long(x)``) and type-reference style
    (``isinstance(x, long)``) that pyjnius uses for Python 2 compatibility.

    ПАТЧ [FIX-LONG-LONG]: C-level ``long long`` type declarations are protected
    before the broad substitution so they are never turned into ``int int``,
    which would cause Cython's "Declarator should be empty" error.
    """
    with open(path, "r", encoding="utf-8") as fh:
        src = fh.read()
    # Step 1: protect C ``long long`` declarations from the broad replacement.
    protected = src.replace("long long", _LONG_LONG_PLACEHOLDER)
    # Step 2: replace Python 2 ``long`` builtin → ``int``.
    patched = re.sub(r"\blong\b", "int", protected)
    # Step 3: restore ``long long``.
    patched = patched.replace(_LONG_LONG_PLACEHOLDER, "long long")
    if patched == src:
        return
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(patched)
    print(f"[p4a_hook] Patched 'long' -> 'int' in: {path}")

def _patch_jni_jlong(path: str) -> None:
    """Fix ``ctypedef int int jlong`` artefact left by over-broad long→int patch.

    ``jlong`` is the JNI 64-bit integer type; it must be declared as
    ``ctypedef long long jlong`` so Cython generates the correct C type.
    """
    with open(path, "r", encoding="utf-8") as fh:
        src = fh.read()
    patched = re.sub(r"ctypedef\s+int\s+int\s+jlong", "ctypedef long long jlong", src)
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
    Patch jnius_utils.pxi to remove the Python-2-only ``long`` built-in.

    Cython 3 raises ``undeclared name not builtin: long`` because ``long``
    no longer exists in Python 3.  Replace every occurrence of
    ``isinstance(x, long)`` with ``isinstance(x, int)``.
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
            os.path.join(root, "**", "jnius_utils.pxi"), recursive=True
        ):
            _patch_long_to_int(match)
        for match in glob.glob(os.path.join(root, "**", "jni.pxi"), recursive=True):
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

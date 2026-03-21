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
    """Replace Python-2-only standalone ``long`` with ``int`` in *path*.

    Uses a sentinel to protect ``long long`` (a valid C type used in Cython casts
    like ``<long long>``) so it is never changed to ``int int``, which Cython
    rejects with "Declarator should be empty".

    This covers both function-call style (``long(x)``) and type-reference style
    (``isinstance(x, long)``) that pyjnius uses for Python 2 compatibility.

    ПАТЧ [FIX-LONG-LONG]: C-level ``long long`` type declarations are protected
    before the broad substitution so they are never turned into ``int int``,
    which would cause Cython's "Declarator should be empty" error.
    """
    _SENTINEL = "\x00LONGLONG\x00"

    with open(path, "r", encoding="utf-8") as fh:
        src = fh.read()

    # Step 1: protect C ``long long`` declarations from the broad replacement.
    protected = src.replace("long long", _LONG_LONG_PLACEHOLDER)
    # Step 2: replace Python 2 ``long`` builtin → ``int``.
    patched = re.sub(r"\blong\b", "int", protected)
    # Step 3: restore ``long long``.
    patched = patched.replace(_LONG_LONG_PLACEHOLDER, "long long")

    # (Optional) Also handle any legacy sentinel that may exist in cached files.
    patched = patched.replace(_SENTINEL, "long long")

    if patched == src:
        return

    with open(path, "w", encoding="utf-8") as fh:
        fh.write(patched)

    print(f"[p4a_hook] Patched 'long' -> 'int' (safe) in: {path}")


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


def after_apk_build(toolchain) -> None:
    """Called by p4a after the AndroidManifest.xml is generated but before Gradle runs.

    Injects a ``<provider>`` element for ``androidx.core.content.FileProvider``
    directly inside the ``<application>`` block of the generated manifest.
    This fixes the SAI ``DISPLAY_NAME is null`` error and ensures the
    ``<provider>`` is placed at the correct level in the manifest XML
    (``<manifest><application><provider>``), not at manifest root level.

    The hook runs while the current working directory is the distribution
    directory, so the manifest is found at ``src/main/AndroidManifest.xml``.
    """
    _inject_file_provider()


# ---------------------------------------------------------------------------
# Patch implementations
# ---------------------------------------------------------------------------

def _fix_pyjnius(toolchain) -> None:
    """Patch jnius_utils.pxi to remove the Python-2-only ``long`` built-in.

    Cython 3 raises ``undeclared name not builtin: long`` because ``long``
    no longer exists in Python 3.
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

        for match in glob.glob(os.path.join(root, "**", "jnius_utils.pxi"), recursive=True):
            _patch_long_to_int(match)

        for match in glob.glob(os.path.join(root, "**", "jni.pxi"), recursive=True):
            _patch_jni_jlong(match)


def _disable_android_incompatible_modules(toolchain) -> None:
    """Prevent Python-for-Android from trying to build stdlib C extensions absent from the NDK."""
    incompatible = {"grp", "_uuid", "_lzma"}

    try:
        from pythonforandroid.recipes.python3 import Python3Recipe  # type: ignore[import]

        existing = set(getattr(Python3Recipe, "disabled_modules", []))
        new_disabled = sorted(existing | incompatible)
        Python3Recipe.disabled_modules = new_disabled

        added = incompatible - existing
        if added:
            print(
                f"[p4a_hook] Added to Python3Recipe.disabled_modules: {', '.join(sorted(added))}"
            )
    except Exception as exc:  # noqa: BLE001
        print(
            f"[p4a_hook] WARNING: Could not patch Python3Recipe.disabled_modules ({exc}). "
            f"The build may still succeed if p4a already excludes grp/_uuid/_lzma for Android, "
            f"but watch for NDK linker errors."
        )


def _inject_file_provider() -> None:
    """Patch the generated AndroidManifest.xml to inject a FileProvider inside <application>.

    ``android.extra_manifest_xml`` (buildozer) inserts XML at manifest root level,
    which causes the Gradle error::

        error: unexpected element <provider> found in <manifest>

    Instead we patch the rendered manifest directly, placing ``<provider>``
    immediately before ``</application>`` so it sits at the correct level:
    ``<manifest> → <application> → <provider>``.

    p4a renders the manifest to ``src/main/AndroidManifest.xml`` inside the
    distribution directory, which is the current working directory when this
    hook is invoked (``after_apk_build``).
    """
    manifest_path: str | None = None
    for candidate in ("src/main/AndroidManifest.xml", "AndroidManifest.xml"):
        if os.path.exists(candidate):
            manifest_path = candidate
            break

    if manifest_path is None:
        for found in glob.glob("**/AndroidManifest.xml", recursive=True):
            manifest_path = found
            break

    if manifest_path is None:
        print("[p4a_hook] after_apk_build: AndroidManifest.xml not found, skipping FileProvider injection")
        return

    with open(manifest_path, "r", encoding="utf-8") as fh:
        content = fh.read()

    if "FileProvider" in content:
        print(f"[p4a_hook] FileProvider already present in {manifest_path}, skipping")
        return

    provider_xml = (
        "\n    <provider\n"
        "        android:name=\"androidx.core.content.FileProvider\"\n"
        "        android:authorities=\"${applicationId}.provider\"\n"
        "        android:exported=\"false\"\n"
        "        android:grantUriPermissions=\"true\">\n"
        "        <meta-data\n"
        "            android:name=\"android.support.FILE_PROVIDER_PATHS\"\n"
        "            android:resource=\"@xml/file_paths\" />\n"
        "    </provider>"
    )

    if "</application>" not in content:
        print(f"[p4a_hook] </application> tag not found in {manifest_path}, skipping FileProvider injection")
        return

    content = content.replace("</application>", provider_xml + "\n    </application>", 1)

    with open(manifest_path, "w", encoding="utf-8") as fh:
        fh.write(content)

    print(f"[p4a_hook] FileProvider injected into {manifest_path}")

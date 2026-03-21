"""
p4a_hook.py — Хук Python-for-Android.
Патчит pyjnius для Python 3, отключает несовместимые C-модули,
и добавляет FileProvider в AndroidManifest.xml.
"""
import os
import re
from pathlib import Path

# Ensure third-party Cython builds default to Python 3 semantics during recipe compilation.
os.environ.setdefault("CYTHON_DEFAULT_LANGUAGE_LEVEL", "3")


def fix_pyjnius(arch):
    """Фикс pyjnius для Python 3 (убирает использование 'long' как тип Python 2).

    Использует sentinel для защиты ``long long`` (валидный тип C в Cython-кастах
    вида ``<long long>``), чтобы не получить ``int int``, которое Cython
    отвергает с ошибкой "Declarator should be empty".
    """
    _SENTINEL = "\x00LONGLONG\x00"
    site_packages = arch.get_env_vars().get("PYTHONPATH", "")
    for sp in site_packages.split(":"):
        jnius_src = Path(sp) / "jnius" / "jnius_utils.pxi"
        if jnius_src.exists():
            content = jnius_src.read_text(errors="replace")
            guarded = content.replace("long long", _SENTINEL)
            patched = re.sub(r"\blong\b", "int", guarded)
            patched = patched.replace(_SENTINEL, "long long")
            if patched != content:
                jnius_src.write_text(patched)
                print("[p4a_hook] pyjnius: fixed long → int (safe)")


def fix_jni_typedef(arch):
    """Исправляет некорректный typedef jlong в jni.pxi (ctypedef int int jlong)."""
    site_packages = arch.get_env_vars().get("PYTHONPATH", "")
    for sp in site_packages.split(":"):
        jni_pxi = Path(sp) / "jnius" / "jni.pxi"
        if jni_pxi.exists():
            content = jni_pxi.read_text(errors="replace")
            patched = re.sub(r"ctypedef\s+int\s+int\s+jlong", "ctypedef long jlong", content)
            if patched != content:
                jni_pxi.write_text(patched)
                print("[p4a_hook] pyjnius: fixed jlong typedef in jni.pxi")


def disable_broken_modules(arch):
    """Отключает C-модули несовместимые с Android."""
    broken = ["grp", "_uuid", "_lzma"]
    site_packages = arch.get_env_vars().get("PYTHONPATH", "")
    for sp in site_packages.split(":"):
        for mod in broken:
            path = Path(sp) / f"{mod}.py"
            if not path.exists():
                path.write_text(
                    f'''# {mod} disabled on Android\nraise ImportError("{mod} not available on Android")\n'''
                )


def _disable_android_incompatible_modules(toolchain):
    incompatible = {"grp", "_uuid", "_lzma"}
    try:
        from pythonforandroid.recipes.python3 import Python3Recipe  # type: ignore[import]
        existing = set(getattr(Python3Recipe, "disabled_modules", []))
        Python3Recipe.disabled_modules = sorted(existing | incompatible)
    except Exception as exc:
        print(f"[p4a_hook] WARNING: could not set disabled_modules ({exc})")


def add_file_provider(build_dir):
    """Добавляет FileProvider в AndroidManifest.xml."""
    manifest_path = Path(build_dir) / "AndroidManifest.xml"
    if not manifest_path.exists():
        # Ищем в .buildozer
        for p in Path(".buildozer").rglob("AndroidManifest.xml"):
            manifest_path = p
            break

    if not manifest_path.exists():
        print("[p4a_hook] AndroidManifest.xml не найден — пропускаю FileProvider")
        return

    content = manifest_path.read_text(encoding="utf-8", errors="replace")

    if "FileProvider" in content:
        print("[p4a_hook] FileProvider уже в манифесте")
        return

    provider_xml = '''
    <provider
        android:name="androidx.core.content.FileProvider"
        android:authorities="${applicationId}.provider"
        android:exported="false"
        android:grantUriPermissions="true">
        <meta-data
            android:name="android.support.FILE_PROVIDER_PATHS"
            android:resource="@xml/file_paths" />
    </provider>
'''

    # Вставляем перед </application>
    if "</application>" in content:
        content = content.replace("</application>", provider_xml + "</application>", 1)
        manifest_path.write_text(content, encoding="utf-8")
        print("[p4a_hook] FileProvider добавлен в AndroidManifest.xml")
    else:
        print("[p4a_hook] </application> не найден — FileProvider не добавлен")


def add_file_paths_xml(dist_dir):
    """Создаёт res/xml/file_paths.xml в дистрибутиве."""
    xml_dir = Path(dist_dir) / "res" / "xml"
    xml_dir.mkdir(parents=True, exist_ok=True)
    file_paths = xml_dir / "file_paths.xml"
    if not file_paths.exists():
        file_paths.write_text('''<?xml version="1.0" encoding="utf-8"?>
<paths xmlns:android="http://schemas.android.com/apk/res/android">
    <external-path name="external_files" path="." />
    <files-path name="internal_files" path="." />
    <cache-path name="cache_files" path="." />
    <external-cache-path name="external_cache" path="." />
    <external-files-path name="external_app_files" path="." />
</paths>
''', encoding="utf-8")
        print("[p4a_hook] file_paths.xml создан")


def source_dirs(arch):
    fix_pyjnius(arch)
    fix_jni_typedef(arch)
    disable_broken_modules(arch)


def before_apk_build(toolchain):
    """Called by p4a before APK assembly – extra safety-net to patch pyjnius."""
    try:
        arch_obj = getattr(toolchain, 'archs', [None])[0]
        if arch_obj:
            fix_pyjnius(arch_obj)
            fix_jni_typedef(arch_obj)
            disable_broken_modules(arch_obj)
        _disable_android_incompatible_modules(toolchain)
    except Exception as exc:
        print(f"[p4a_hook] before_apk_build warning: {exc}")


def postbuild_arch(arch, api, **kwargs):
    build_dir = getattr(arch, "build_dir", "")
    dist_dir  = getattr(arch, "dist_dir",  ".buildozer/android/platform/build")
    add_file_provider(build_dir or dist_dir)
    add_file_paths_xml(dist_dir)

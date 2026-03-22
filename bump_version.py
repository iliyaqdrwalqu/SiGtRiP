"""
bump_version.py — автоматическое увеличение patch-версии пакета.

Экспортирует:
  OLD, NEW      — текущая и новая версия
  TARGETS       — список (файл, old_pattern, new_pattern)
  REMOVE        — устаревшие файлы для удаления
  RENAME        — пары (старое имя, новое имя)

Использование:
  python bump_version.py              # применить изменения (patch)
  python bump_version.py --dry-run    # показать без записи
  python bump_version.py --minor      # minor bump
  python bump_version.py --major      # major bump
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
PYPROJECT = ROOT / "pyproject.toml"
BUILD_PY  = ROOT / "build.py"
README    = ROOT / "README.md"

_VERSION_RE = re.compile(r'^([ \t]*version\s*=\s*")[^"]+(")', re.MULTILINE)
_VERSION_MD  = re.compile(r'\(v(\d+\.\d+\.\d+)\)')
_VERSION_JSON = re.compile(r'"version":\s*"([^"]+)"')


def _read(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _write(path: Path, content: str, dry_run: bool) -> None:
    if dry_run:
        print(f"[dry-run] {path.name} не изменён")
    else:
        path.write_text(content, encoding="utf-8")
        print(f"✅  {path.name} обновлён")


def current_version() -> str:
    text = _read(PYPROJECT)
    m = _VERSION_RE.search(text)
    if not m:
        return "2.1.3"
    return m.group(0).split('"')[1]


def bump(version: str, part: str = "patch") -> str:
    parts = version.split(".")
    if len(parts) != 3:
        return version
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    if part == "major":
        major, minor, patch = major + 1, 0, 0
    elif part == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    return f"{major}.{minor}.{patch}"


# ── Экспортируемые константы ──────────────────────────────────────────────────

OLD = current_version()
NEW = bump(OLD, "patch")

# Список файлов для замены версии: (Path, pattern, replacement_template)
TARGETS: list[tuple[Path, str, str]] = [
    (PYPROJECT,              OLD, NEW),
    (BUILD_PY,               OLD, NEW),
    (README,                 OLD, NEW),
    (ROOT / "manifest.json", OLD, NEW),
    (ROOT / "manifest.yaml", OLD, NEW),
]

# Файлы для удаления (устаревшие артефакты)
REMOVE: list[str] = []

# Переименования: (старое имя в корне, новое имя)
RENAME: list[tuple[str, str]] = [
    ("ardware_intel.py", "hardware_intel.py"),
]


# ── Применение патча ──────────────────────────────────────────────────────────

def _update_file(path: Path, old_ver: str, new_ver: str, dry_run: bool) -> None:
    if not path.exists():
        print(f"  ⚠️  {path.name} не найден, пропускаю")
        return
    text = path.read_text(encoding="utf-8")
    # Заменяем версионные строки
    new_text = text.replace(old_ver, new_ver)
    if new_text == text:
        print(f"  ⏭️  {path.name}: версия не найдена")
        return
    count = text.count(old_ver)
    print(f"  {path.name}: {old_ver} → {new_ver}  ({count} замен)")
    _write(path, new_text, dry_run)


def _apply_renames(dry_run: bool) -> None:
    for old_name, new_name in RENAME:
        old_path = ROOT / old_name
        new_path = ROOT / new_name
        if old_path.exists() and not new_path.exists():
            print(f"  ✏️  rename {old_name} → {new_name}")
            if not dry_run:
                old_path.rename(new_path)
        elif new_path.exists():
            print(f"  ⏭️  {new_name} уже существует")


def _apply_removals(dry_run: bool) -> None:
    for name in REMOVE:
        path = ROOT / name
        if path.exists():
            print(f"  🗑️  удаляю {name}")
            if not dry_run:
                path.unlink()


def run_bump(dry_run: bool = False) -> None:
    print(f"\n📦 Текущая версия : {OLD}")
    print(f"🚀 Новая версия   : {NEW}\n")
    for path, old_ver, new_ver in TARGETS:
        _update_file(path, old_ver, new_ver, dry_run)
    _apply_renames(dry_run)
    _apply_removals(dry_run)
    print("\n✅ Готово!")


# Алиас для обратной совместимости с тестами
def bump_files(dry_run: bool = False) -> None:
    run_bump(dry_run)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bump package version")
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--major", action="store_true")
    grp.add_argument("--minor", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_bump(dry_run=args.dry_run)


if __name__ == "__main__":
    main()

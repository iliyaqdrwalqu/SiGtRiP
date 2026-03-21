#!/usr/bin/env python3
"""
bump_version.py — автоматическое увеличение patch-версии пакета.

Обновляет поле version в pyproject.toml и шаблон в build.py.

Использование:
    python bump_version.py              # применить изменения
    python bump_version.py --dry-run    # показать изменения без записи
    python bump_version.py --minor      # увеличить minor-версию (сбросить patch в 0)
    python bump_version.py --major      # увеличить major-версию (сбросить minor и patch в 0)
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
PYPROJECT = ROOT / "pyproject.toml"
BUILD_PY = ROOT / "build.py"

# Regex для строки вида: version = "X.Y.Z"  (допускает ведущие пробелы)
_VERSION_RE = re.compile(r'^([ \t]*version\s*=\s*")[^"]+(")', re.MULTILINE)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, content: str, dry_run: bool) -> None:
    if dry_run:
        print(f"[dry-run] {path} не изменён")
    else:
        path.write_text(content, encoding="utf-8")
        print(f"✅  {path.name} обновлён")


def current_version() -> str:
    text = _read(PYPROJECT)
    m = _VERSION_RE.search(text)
    if not m:
        print(f"❌  Не найдена строка version в {PYPROJECT}", file=sys.stderr)
        sys.exit(1)
    return m.group(0).split('"')[1]


def bump(version: str, part: str) -> str:
    parts = version.split(".")
    if len(parts) != 3:
        print(f"❌  Неожиданный формат версии: {version!r}", file=sys.stderr)
        sys.exit(1)
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    if part == "major":
        major, minor, patch = major + 1, 0, 0
    elif part == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    return f"{major}.{minor}.{patch}"


def update_file(path: Path, old_ver: str, new_ver: str, dry_run: bool) -> None:
    text = _read(path)
    new_text, count = _VERSION_RE.subn(
        lambda m: m.group(1) + new_ver + m.group(2),
        text,
    )
    if count == 0:
        print(f"⚠️   version не найдена в {path.name}, пропускаю")
        return
    print(f"  {path.name}: {old_ver} → {new_ver}  ({count} замен)")
    _write(path, new_text, dry_run)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bump package version")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--major", action="store_true", help="Bump major version")
    group.add_argument("--minor", action="store_true", help="Bump minor version")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    args = parser.parse_args()

    part = "major" if args.major else "minor" if args.minor else "patch"
    old_ver = current_version()
    new_ver = bump(old_ver, part)

    print(f"📦  Текущая версия: {old_ver}")
    print(f"🚀  Новая версия:   {new_ver}\n")

    update_file(PYPROJECT, old_ver, new_ver, args.dry_run)
    update_file(BUILD_PY, old_ver, new_ver, args.dry_run)


if __name__ == "__main__":
    main()

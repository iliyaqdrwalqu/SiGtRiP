#!/usr/bin/env python3
"""
bump_version.py — скрипт обновления версии ARGOS до v2.0.0 финального релиза.

Использование:
    python bump_version.py
    python bump_version.py --dry-run   # только показать изменения без записи
"""
import re
import sys
import argparse
from pathlib import Path

OLD = "1.4.0"
NEW = "2.0.0"

# Файл → (паттерн для поиска, заменяемая строка)
TARGETS = [
    ("pyproject.toml",    r'version = "1\.4\.0"',         f'version = "{NEW}"'),
    ("pyproject.toml",    r"version = '1\.4\.0'",         f"version = '{NEW}'"),
    ("pack_archive.py",   r'version="1\.4\.0"',           f'version="{NEW}"'),
    ("pack_archive.py",   r"version='1\.4\.0'",           f"version='{NEW}'"),
    ("__init__.py",       r'__version__ = "1\.4\.0"',     f'__version__ = "{NEW}"'),
    ("__init__.py",       r"__version__ = '1\.4\.0'",     f"__version__ = '{NEW}'"),
    ("README.md",         r"ARGOS UNIVERSAL OS \(v1\.4\.0\)", f"ARGOS UNIVERSAL OS (v{NEW})"),
    ("README.md",         r"\[1\.4\.0\]",                  f"[{NEW}]"),
    ("manifest.yaml",     r"version: 1\.4\.0",             f"version: {NEW}"),
    ("manifest.json",     r'"version": "1\.4\.0"',         f'"version": "{NEW}"'),
]

# Файлы для удаления (временные патчи)
REMOVE = [
    "life_support_patch.py",
    "life_v2_patch.py",
    "consciousness_patch_cell.py",
    "organize_files.py",
    "cleanup_repo.py",
]

# Файлы для переименования
RENAME = [
    ("ardware_intel.py", "hardware_intel.py"),  # опечатка в оригинале
]


def bump(dry_run: bool = False):
    root = Path(__file__).parent
    changed = []

    print(f"🔱 ARGOS Version Bump: {OLD} → {NEW}")
    print("=" * 50)

    # Обновить версии
    for filename, pattern, replacement in TARGETS:
        fpath = root / filename
        if not fpath.exists():
            continue
        text = fpath.read_text(encoding="utf-8")
        new_text = re.sub(pattern, replacement, text)
        if new_text != text:
            if not dry_run:
                fpath.write_text(new_text, encoding="utf-8")
            changed.append(filename)
            print(f"  ✅ Обновлено: {filename}")

    # Показать файлы для удаления
    print("\n📋 Временные файлы для удаления (выполни git rm вручную):")
    for fname in REMOVE:
        fpath = root / fname
        status = "  ❌ СУЩЕСТВУЕТ" if fpath.exists() else "  ⬜ не найден"
        print(f"{status}: {fname}")

    # Показать файлы для переименования
    print("\n📋 Файлы для переименования:")
    for old_name, new_name in RENAME:
        old_path = root / old_name
        if old_path.exists():
            print(f"  ⚠️  git mv {old_name} src/{new_name}")
        else:
            print(f"  ⬜ не найден: {old_name}")

    print("\n" + "=" * 50)
    if dry_run:
        print(f"  DRY RUN: изменения НЕ записаны. Будет изменено {len(changed)} файлов.")
    else:
        print(f"  ✅ Обновлено {len(changed)} файлов.")
        print(f"\n  Следующий шаг:")
        print(f"  git add -A && git commit -m '🔱 chore: bump version to v{NEW}'")
        print(f"  git tag -a v{NEW} -m 'ARGOS Universal OS v{NEW} — Финальный релиз'")
        print(f"  git push origin main && git push origin v{NEW}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ARGOS version bump script")
    parser.add_argument("--dry-run", action="store_true", help="только показать изменения")
    args = parser.parse_args()
    bump(dry_run=args.dry_run)

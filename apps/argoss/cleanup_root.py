#!/usr/bin/env python3
"""
cleanup_root.py — Очистка корня репозитория Argos
===================================================
Удаляет файлы-дубли из корня (они уже есть в src/).
Перемещает старые GUI-файлы в src/interface/legacy/.
Запускать из корня репозитория: python cleanup_root.py

ВНИМАНИЕ: Сделайте git commit перед запуском!
"""
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).parent

# ── 1. Файлы-дубли из корня (основная копия в src/) ──────────────────────────
ROOT_DUPLICATES = [
    "agent.py",
    "awareness.py",
    "consciousness.py",
    "consciousness_patch_cell.py",
    "content_gen.py",
    "dag_agent.py",
    "evolution.py",
    "core.py",
    "empathy_engine.py",
    "event_bus.py",
    "net_scanner.py",
    "scheduler.py",
    "db_init.py",
    "git_ops.py",
    "git_push.py",
    "auto_integrator.py",
    "budding_manager.py",
    "organize_files.py",
    "pack_archive.py",
]

# ── 2. Patch-файлы (устаревшие) ───────────────────────────────────────────────
PATCH_FILES = [
    "life_support_patch.py",
    "life_v2_patch.py",
    "consciousness_patch_cell.py",
]

# ── 3. Старые GUI-файлы → src/interface/legacy/ ───────────────────────────────
LEGACY_GUI = [
    "kivy_1gui.py",
    "kivy_ma.py",
    "main_kivy.py",
    # kivy_gui.py оставляем как основной
]

LEGACY_DIR = ROOT / "src" / "interface" / "legacy"


def move_to_legacy(filename: str):
    src = ROOT / filename
    if not src.exists():
        print(f"  ПРОПУСК (нет файла): {filename}")
        return
    LEGACY_DIR.mkdir(parents=True, exist_ok=True)
    dst = LEGACY_DIR / filename
    shutil.move(str(src), str(dst))
    print(f"  ПЕРЕМЕЩЁН → legacy/: {filename}")


def delete_file(filename: str, reason: str = "дубль"):
    path = ROOT / filename
    if not path.exists():
        print(f"  ПРОПУСК (нет файла): {filename}")
        return
    # Проверяем что копия есть в src/ перед удалением
    src_copy = ROOT / "src" / filename
    if not src_copy.exists():
        print(f"  ⚠ ПРОПУСК (нет копии в src/): {filename} — удалите вручную")
        return
    path.unlink()
    print(f"  УДАЛЁН ({reason}): {filename}")


def main():
    print("=" * 60)
    print("ARGOS Root Cleanup — v2.1")
    print("=" * 60)

    # Создаём legacy/__init__.py
    LEGACY_DIR.mkdir(parents=True, exist_ok=True)
    init = LEGACY_DIR / "__init__.py"
    if not init.exists():
        init.write_text('"""Legacy GUI files — kept for reference only."""\n')

    print("\n[1/3] Удаление дублей из корня (копии есть в src/)...")
    for f in ROOT_DUPLICATES:
        delete_file(f, reason="дубль")

    print("\n[2/3] Удаление patch-файлов...")
    for f in PATCH_FILES:
        path = ROOT / f
        if path.exists():
            path.unlink()
            print(f"  УДАЛЁН (patch): {f}")
        else:
            print(f"  ПРОПУСК (нет файла): {f}")

    print("\n[3/3] Перемещение старых GUI → src/interface/legacy/...")
    for f in LEGACY_GUI:
        move_to_legacy(f)

    print("\n" + "=" * 60)
    print("Готово! Теперь выполните:")
    print("  git add -A")
    print("  git commit -m 'cleanup: remove root duplicates, move legacy GUI'")
    print("  git push")
    print("=" * 60)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Быстрое исправление для ./src/interface/legacy/__init__.py
"""

import os
from pathlib import Path


def fix_legacy_init():
    """Исправляет файл legacy/__init__.py с проблемой кодировки."""
    
    # Возможные пути к файлу
    possible_paths = [
        './src/interface/legacy/__init__.py',
        'src/interface/legacy/__init__.py',
        Path.cwd() / 'src' / 'interface' / 'legacy' / '__init__.py'
    ]
    
    target_file = None
    for path in possible_paths:
        p = Path(path)
        if p.exists():
            target_file = p
            break
    
    if not target_file:
        print("❌ Файл ./src/interface/legacy/__init__.py не найден")
        print("\nПопытка создать директорию и файл...")
        
        # Создаем директорию если нужно
        legacy_dir = Path('./src/interface/legacy')
        if not legacy_dir.exists():
            legacy_dir.mkdir(parents=True, exist_ok=True)
            print(f"✅ Создана директория: {legacy_dir}")
        
        target_file = legacy_dir / '__init__.py'
    
    # Правильное содержимое файла
    correct_content = '''"""Legacy GUI files — kept for reference only."""
'''
    
    try:
        # Записываем правильное содержимое
        with open(target_file, 'w', encoding='utf-8') as f:
            f.write(correct_content)
        
        print(f"✅ Файл исправлен: {target_file}")
        
        # Проверяем что файл теперь читается
        with open(target_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        print("✅ Файл успешно читается в UTF-8")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при исправлении файла: {e}")
        return False


if __name__ == "__main__":
    print("🔧 Исправление ./src/interface/legacy/__init__.py\n")
    
    if fix_legacy_init():
        print("\n✅ Готово! Теперь можно запустить проверку синтаксиса.")
    else:
        print("\n❌ Не удалось исправить файл автоматически.")
        print("\nРучное исправление:")
        print("1. Откройте ./src/interface/legacy/__init__.py")
        print('2. Замените содержимое на: """Legacy GUI files — kept for reference only."""')
        print("3. Сохраните файл в кодировке UTF-8")

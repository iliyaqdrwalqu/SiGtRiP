#!/usr/bin/env python3
"""
Скрипт для исправления проблем с кодировкой в Python файлах.
Исправляет файлы с неправильной кодировкой и заменяет проблемные символы.
"""

import os
import sys
from pathlib import Path
import chardet


def detect_encoding(file_path):
    """Определяет кодировку файла."""
    try:
        with open(file_path, 'rb') as f:
            raw_data = f.read()
            result = chardet.detect(raw_data)
            return result['encoding']
    except Exception as e:
        print(f"Ошибка при определении кодировки {file_path}: {e}")
        return None


def fix_file_encoding(file_path):
    """Исправляет кодировку файла, конвертируя в UTF-8."""
    try:
        # Пытаемся определить текущую кодировку
        encoding = detect_encoding(file_path)
        
        if encoding is None:
            print(f"⚠️  Не удалось определить кодировку: {file_path}")
            return False
        
        # Читаем файл с определенной кодировкой
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
        except:
            # Пробуем альтернативные кодировки
            for enc in ['cp1251', 'windows-1252', 'latin-1', 'iso-8859-1']:
                try:
                    with open(file_path, 'r', encoding=enc) as f:
                        content = f.read()
                    encoding = enc
                    break
                except:
                    continue
            else:
                print(f"❌ Не удалось прочитать файл: {file_path}")
                return False
        
        # Заменяем проблемные символы
        replacements = {
            '\x97': '—',  # Em dash
            '\x96': '–',  # En dash
            '\x93': '"',  # Left double quote
            '\x94': '"',  # Right double quote
            '\x91': '\u2018',  # Left single quote
            '\x92': '\u2019',  # Right single quote
            '\x85': '…',  # Ellipsis
        }
        
        for old, new in replacements.items():
            content = content.replace(old, new)
        
        # Записываем обратно в UTF-8
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ Исправлено: {file_path} (было: {encoding})")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при обработке {file_path}: {e}")
        return False


def find_and_fix_python_files(root_dir):
    """Находит и исправляет все Python файлы в директории."""
    root_path = Path(root_dir)
    
    if not root_path.exists():
        print(f"❌ Директория не найдена: {root_dir}")
        return
    
    print(f"\n🔍 Поиск Python файлов в: {root_dir}\n")
    
    python_files = list(root_path.rglob('*.py'))
    
    if not python_files:
        print("⚠️  Python файлы не найдены")
        return
    
    print(f"Найдено файлов: {len(python_files)}\n")
    
    fixed_count = 0
    error_count = 0
    
    for py_file in python_files:
        # Пропускаем виртуальные окружения и кэш
        if any(part in py_file.parts for part in ['venv', '.venv', '__pycache__', 'node_modules']):
            continue
        
        # Проверяем, можно ли прочитать файл как UTF-8
        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                f.read()
            # print(f"✓ OK: {py_file}")
        except UnicodeDecodeError:
            print(f"🔧 Исправляю: {py_file}")
            if fix_file_encoding(py_file):
                fixed_count += 1
            else:
                error_count += 1
        except Exception as e:
            print(f"❌ Ошибка при проверке {py_file}: {e}")
            error_count += 1
    
    print(f"\n{'='*60}")
    print(f"📊 Результаты:")
    print(f"   Всего файлов: {len(python_files)}")
    print(f"   Исправлено: {fixed_count}")
    print(f"   Ошибок: {error_count}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    # Определяем корневую директорию проекта
    if len(sys.argv) > 1:
        project_dir = sys.argv[1]
    else:
        # Пытаемся найти src директорию
        current = Path.cwd()
        if (current / 'src').exists():
            project_dir = str(current)
        elif current.name == 'src':
            project_dir = str(current.parent)
        else:
            project_dir = str(current)
    
    print(f"🚀 Исправление кодировки Python файлов")
    print(f"{'='*60}")
    
    # Устанавливаем chardet если нужно
    try:
        import chardet
    except ImportError:
        print("📦 Установка chardet...")
        os.system(f"{sys.executable} -m pip install chardet --quiet")
        import chardet
    
    find_and_fix_python_files(project_dir)

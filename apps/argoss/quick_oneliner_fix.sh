#!/bin/bash
# Быстрое исправление проблемы с кодировкой - one-liner версия
# Использование: bash quick_oneliner_fix.sh

echo "🔧 БЫСТРОЕ ИСПРАВЛЕНИЕ КОДИРОВКИ"
echo "=================================="
echo ""

# One-liner Python скрипт для исправления
python3 << 'EOF'
from pathlib import Path
import sys

# Исправление конкретного файла legacy/__init__.py
target = Path("./src/interface/legacy/__init__.py")
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text('"""Legacy GUI files — kept for reference only."""\n', encoding="utf-8")
print(f"✅ Исправлен: {target}")

# Исправление всех Python файлов с проблемами кодировки
try:
    import chardet
except ImportError:
    print("📦 Установка chardet...")
    import os
    os.system(f"{sys.executable} -m pip install chardet --quiet")
    import chardet

fixed_count = 0
for py_file in Path(".").rglob("*.py"):
    if any(part in py_file.parts for part in ["venv", ".venv", "__pycache__", "node_modules"]):
        continue
    
    try:
        with open(py_file, "r", encoding="utf-8") as f:
            f.read()
    except UnicodeDecodeError:
        try:
            with open(py_file, "rb") as f:
                raw_data = f.read()
            
            result = chardet.detect(raw_data)
            encoding = result["encoding"] or "utf-8"
            
            try:
                content = raw_data.decode(encoding)
            except:
                for enc in ["cp1251", "windows-1252", "latin-1", "iso-8859-1"]:
                    try:
                        content = raw_data.decode(enc)
                        break
                    except:
                        continue
                else:
                    print(f"❌ Не удалось исправить: {py_file}")
                    continue
            
            replacements = {
                "\x97": "—", "\x96": "–", "\x93": """, "\x94": """,
                "\x91": "'", "\x92": "'", "\x85": "…"
            }
            for old, new in replacements.items():
                content = content.replace(old, new)
            
            with open(py_file, "w", encoding="utf-8") as f:
                f.write(content)
            
            print(f"✅ Исправлен: {py_file}")
            fixed_count += 1
        except Exception as e:
            print(f"❌ Ошибка при исправлении {py_file}: {e}")

print(f"\n📊 Исправлено файлов: {fixed_count}")
EOF

echo ""
echo "=================================="
echo "🎉 Готово! Теперь можно запустить:"
echo "   find . -name '*.py' | xargs python3 -m py_compile"
echo ""

"""
Временный скрипт для проверки структуры Excel файла
"""
import pandas as pd
import sys
import os
from pathlib import Path

# Исправление кодировки для Windows
if sys.platform == 'win32':
    import codecs
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    os.environ['PYTHONIOENCODING'] = 'utf-8'

excel_path = Path(__file__).parent.parent / "1c" / "sales25.xlsx"

print("=" * 80)
print("АНАЛИЗ СТРУКТУРЫ EXCEL ФАЙЛА")
print("=" * 80)
print(f"Файл: {excel_path}\n")

# Проверяем размер и тип файла
print(f"Размер файла: {excel_path.stat().st_size} байт")
print(f"Существует: {excel_path.exists()}\n")

# Читаем без заголовков, первые 30 строк
# Пробуем разные движки для .xls файла
df = None
engines = ['xlrd', 'openpyxl', 'calamine']  # calamine для Rust-based чтения

for engine in engines:
    try:
        print(f"Пробую движок: {engine}...")
        df = pd.read_excel(excel_path, engine=engine, header=None, nrows=30)
        print(f"[OK] Успешно прочитано с движком {engine}\n")
        break
    except Exception as e:
        print(f"[FAIL] {engine}: {e}")
        continue

if df is None:
    print("\n[ERROR] Не удалось прочитать файл ни одним движком")
    print("Попробуйте конвертировать файл в .xlsx или установите xlrd:")
    print("  pip install xlrd")
    sys.exit(1)

print(f"Размер: {len(df)} строк, {len(df.columns)} колонок\n")

print("=" * 80)
print("ПЕРВЫЕ 15 СТРОК (все колонки)")
print("=" * 80)
for i in range(min(15, len(df))):
    print(f"\nСтрока {i}:")
    for j in range(min(10, len(df.columns))):  # Показываем первые 10 колонок
        val = df.iloc[i, j]
        if pd.notna(val):
            val_str = str(val)[:50]  # Ограничиваем длину
            print(f"  Колонка {j}: {val_str}")

print("\n" + "=" * 80)
print("АНАЛИЗ КОЛОНОК")
print("=" * 80)

# Ищем строку с заголовками
for i in range(min(20, len(df))):
    row_values = [str(val).lower() if pd.notna(val) else '' for val in df.iloc[i].values]
    row_text = ' '.join(row_values)
    
    if any(keyword in row_text for keyword in ['номенклатура', 'единица', 'артикул', 'количество', 'сумма']):
        print(f"\nНайдена строка заголовков на строке {i}:")
        for j in range(min(15, len(df.columns))):
            val = df.iloc[i, j]
            if pd.notna(val):
                print(f"  Колонка {j}: {val}")

print("\n" + "=" * 80)
print("ПРИМЕРЫ ДАННЫХ (строки после заголовков)")
print("=" * 80)

# Ищем строки с товарами (содержат запятые и артикулы)
for i in range(5, min(20, len(df))):
    for j in range(min(5, len(df.columns))):
        val = df.iloc[i, j]
        if pd.notna(val) and isinstance(val, str) and ',' in val:
            # Проверяем, есть ли артикул (число в конце)
            if any(char.isdigit() for char in val):
                print(f"\nСтрока {i}, Колонка {j}:")
                print(f"  {val}")

print("\n" + "=" * 80)
print("СТАТИСТИКА ПО КОЛОНКАМ")
print("=" * 80)

for j in range(min(10, len(df.columns))):
    non_null = df.iloc[:, j].notna().sum()
    sample_vals = df.iloc[:, j].dropna().head(3).tolist()
    print(f"\nКолонка {j}:")
    print(f"  Непустых значений: {non_null}")
    print(f"  Примеры: {sample_vals}")

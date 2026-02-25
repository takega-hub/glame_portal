"""Проверка структуры очищенного Excel файла"""
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

excel_path = Path(__file__).parent.parent / "1c" / "sales_clean.xlsx"

print("=" * 80)
print("АНАЛИЗ СТРУКТУРЫ ОЧИЩЕННОГО EXCEL ФАЙЛА")
print("=" * 80)
print(f"Файл: {excel_path}\n")

if not excel_path.exists():
    print(f"[ERROR] Файл не найден: {excel_path}")
    sys.exit(1)

# Читаем без заголовков, первые 30 строк
df = pd.read_excel(excel_path, engine='openpyxl', header=None, nrows=30)

print(f"Размер: {len(df)} строк, {len(df.columns)} колонок\n")

print("=" * 80)
print("ПЕРВЫЕ 15 СТРОК")
print("=" * 80)
for i in range(min(15, len(df))):
    print(f"\nСтрока {i}:")
    for j in range(min(10, len(df.columns))):  # Показываем первые 10 колонок
        val = df.iloc[i, j]
        if pd.notna(val):
            val_str = str(val)[:60]  # Ограничиваем длину
            print(f"  Колонка {j}: {val_str}")

print("\n" + "=" * 80)
print("ПОИСК ЗАГОЛОВКОВ")
print("=" * 80)

# Ищем строку с заголовками
for i in range(min(20, len(df))):
    row_values = [str(val).lower() if pd.notna(val) else '' for val in df.iloc[i].values]
    row_text = ' '.join(row_values)
    
    if any(keyword in row_text for keyword in ['номенклатура', 'единица', 'артикул', 'количество', 'сумма', 'янв', 'февр', 'март']):
        print(f"\nНайдена строка заголовков на строке {i}:")
        for j in range(min(15, len(df.columns))):
            val = df.iloc[i, j]
            if pd.notna(val):
                print(f"  Колонка {j}: {val}")

print("\n" + "=" * 80)
print("ПРИМЕРЫ ДАННЫХ (строки с товарами)")
print("=" * 80)

# Ищем строки с товарами
found = 0
for i in range(5, min(25, len(df))):
    for j in range(min(5, len(df.columns))):
        val = df.iloc[i, j]
        if pd.notna(val) and isinstance(val, str) and ',' in val:
            # Проверяем, есть ли артикул (число в конце)
            if any(char.isdigit() for char in val):
                print(f"\nСтрока {i}, Колонка {j}:")
                print(f"  {val}")
                found += 1
                if found >= 10:
                    break
    if found >= 10:
        break

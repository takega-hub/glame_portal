"""Проверка формата файла"""
import os
from pathlib import Path

excel_path = Path(__file__).parent.parent / "1c" / "sales25.xls"

with open(excel_path, 'rb') as f:
    header = f.read(8)
    
print(f"Размер файла: {excel_path.stat().st_size} байт")
print(f"Заголовок (hex): {header.hex()}")
print(f"Это ZIP (xlsx)? {header[:2] == b'PK'}")
print(f"Это OLE2 (xls)? {header[:8] == b'\\xd0\\xcf\\x11\\xe0\\xa1\\xb1\\x1a\\xe1'}")
print(f"Первые байты: {header}")

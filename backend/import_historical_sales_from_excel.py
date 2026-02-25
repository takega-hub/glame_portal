"""
Скрипт для импорта исторических данных о продажах из Excel файла (1c/sales25.xlsx)
Формат данных: дата, товар (например "Каффа Geometry, шт, 82039-G")
Сопоставляет товары по артикулам с каталогом products
"""
import asyncio
import asyncpg
import os
import sys
import re
from datetime import timezone
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from typing import Optional, Dict, Tuple

# Для работы с Excel
try:
    import pandas as pd
    import openpyxl
except ImportError:
    print("[ERROR] Необходимо установить библиотеки: pandas и openpyxl")
    print("   pip install pandas openpyxl")
    sys.exit(1)

# Исправление кодировки для Windows
if sys.platform == 'win32':
    import codecs
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# Добавляем корневую директорию в путь для импорта
sys.path.insert(0, str(Path(__file__).parent))

# Загружаем переменные окружения
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)


def parse_product_string(product_str: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Парсит строку товара вида "Каффа Geometry, шт, 82039-G"
    Возвращает: (название, единица_измерения, артикул)
    """
    if not product_str or not isinstance(product_str, str):
        return None, None, None
    
    # Убираем лишние пробелы
    product_str = product_str.strip()
    
    # Паттерн 1: название, единица, артикул (с запятыми)
    # Примеры: "Каффа Geometry, шт, 82039-G" или "Браслет Geometry, шт, 71112"
    # Разбиваем по запятым и берём последние 3 части
    if ',' in product_str:
        parts = [p.strip() for p in product_str.split(',')]
        if len(parts) >= 3:
            # Последняя часть - артикул
            article = parts[-1].strip()
            # Предпоследняя - единица
            unit = parts[-2].strip()
            # Всё остальное - название
            name = ', '.join(parts[:-2]).strip()
            
            # Проверяем, что артикул выглядит как артикул (число или буквенно-цифровой)
            if re.match(r'^[A-Za-z0-9\-]+$', article) and len(article) >= 2:
                return name, unit, article
    
    # Паттерн 2: название единица артикул (без запятых)
    # "Каффа Geometry шт 82039-G"
    pattern2 = r'^(.+?)\s+([а-яА-Яa-zA-Z]+)\s+(.+)$'
    match2 = re.match(pattern2, product_str)
    if match2:
        name = match2.group(1).strip()
        unit = match2.group(2).strip()
        article = match2.group(3).strip()
        if re.match(r'^[A-Za-z0-9\-]+$', article):
            return name, unit, article
    
    # Паттерн 3: пытаемся найти артикул в конце строки
    # Артикул может быть просто числом (например, 71112) или буквенно-цифровым (82039-G)
    # Ищем последнее слово/группу, которая выглядит как артикул
    article_patterns = [
        r'\b([0-9]{4,})\s*$',  # Просто число (минимум 4 цифры) - часто артикул
        r'\b([A-Z0-9\-]{3,})\s*$',  # Артикул в конце: буквы/цифры/дефисы, минимум 3 символа
        r'\b([0-9]+[A-Z]?[0-9]*\-?[A-Z0-9]*)\s*$',  # Цифры-буквы-цифры
        r'\b([A-Z]+[0-9]+[A-Z0-9\-]*)\s*$',  # Буквы-цифры
    ]
    
    for pattern in article_patterns:
        article_match = re.search(pattern, product_str)
        if article_match:
            article = article_match.group(1).strip()
            # Убираем артикул из строки, остальное - название
            name = product_str[:article_match.start()].strip().rstrip(',').strip()
            # Пытаемся найти единицу измерения перед артикулом
            unit_match = re.search(r'\b(шт|шт\.|ед|ед\.|pcs|pcs\.)\b', name, re.IGNORECASE)
            unit = unit_match.group(1) if unit_match else None
            if unit:
                name = name.replace(unit, '').strip().rstrip(',').strip()
            return name, unit, article
    
    # Паттерн 4: если есть дефис, возможно артикул после последнего дефиса
    if '-' in product_str:
        parts = product_str.split('-')
        if len(parts) >= 2:
            # Последняя часть после дефиса может быть артикулом
            potential_article = parts[-1].strip()
            if re.match(r'^[A-Z0-9]+$', potential_article) and len(potential_article) >= 2:
                # Собираем артикул из последних частей
                article = '-'.join(parts[-2:]) if len(parts) >= 2 else potential_article
                name = '-'.join(parts[:-2]) if len(parts) > 2 else parts[0]
                return name.strip(), None, article
    
    # Если ничего не подошло, возвращаем всю строку как название
    return product_str, None, None


def to_utc_datetime(value: datetime) -> datetime:
    """Ensure datetime is timezone-aware in UTC."""
    if value is None:
        return value
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def get_product_by_article(conn: asyncpg.Connection, article: str) -> Optional[Dict]:
    """Ищет товар в каталоге по артикулу"""
    if not article:
        return None
    
    # Убеждаемся, что артикул - строка
    article_str = str(article).strip()
    
    # Ищем по точному совпадению артикула (как строка)
    product = await conn.fetchrow("""
        SELECT id, name, article, category, brand, external_id, external_code
        FROM products
        WHERE article::text = $1 OR external_code::text = $1
        LIMIT 1
    """, article_str)
    
    if product:
        return dict(product)
    
    # Пробуем найти по частичному совпадению (если артикул содержит дефисы)
    if '-' in article_str:
        # Ищем товары, где артикул содержит основную часть
        parts = article_str.split('-')
        if len(parts) >= 2:
            main_part = parts[0]
            product = await conn.fetchrow("""
                SELECT id, name, article, category, brand, external_id, external_code
                FROM products
                WHERE article::text LIKE $1 OR external_code::text LIKE $1
                LIMIT 1
            """, f"{main_part}%")
            
            if product:
                return dict(product)
    
    # Для числовых артикулов пробуем найти без ведущих нулей
    if article_str.isdigit():
        # Пробуем найти, убирая ведущие нули
        article_no_zeros = str(int(article_str))
        if article_no_zeros != article_str:
            product = await conn.fetchrow("""
                SELECT id, name, article, category, brand, external_id, external_code
                FROM products
                WHERE article::text = $1 OR external_code::text = $1
                LIMIT 1
            """, article_no_zeros)
            
            if product:
                return dict(product)
    
    return None


async def import_historical_sales(excel_path: Path, batch_size: int = 1000):
    """Импортирует исторические данные о продажах из Excel"""
    
    # Параметры подключения
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "5433"))
    DB_USER = os.getenv("DB_USER", "glame_user")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "glame_password")
    DB_NAME = os.getenv("DB_NAME", "glame_db")
    
    print(f"Подключение к БД: {DB_HOST}:{DB_PORT}/{DB_NAME} как {DB_USER}")
    
    # Проверяем существование файла
    if not excel_path.exists():
        print(f"[ERROR] Файл не найден: {excel_path}")
        return False
    
    try:
        conn = await asyncpg.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        
        print("[OK] Подключение установлено")
        print(f"[INFO] Чтение файла: {excel_path}")
        
        # Читаем Excel файл
        # Определяем формат по расширению и используем соответствующий движок
        file_ext = excel_path.suffix.lower()
        df_raw = None
        df = None
        
        if file_ext == '.xlsx':
            # Для .xlsx используем openpyxl
            try:
                df_raw = pd.read_excel(excel_path, engine='openpyxl', header=None)
                df = pd.read_excel(excel_path, engine='openpyxl')
                print("[OK] Файл прочитан с движком openpyxl (.xlsx)")
            except Exception as e:
                print(f"[ERROR] Не удалось прочитать .xlsx файл: {e}")
                print("   Установите: pip install openpyxl")
                await conn.close()
                return False
        elif file_ext == '.xls':
            # Для .xls используем xlrd
            try:
                df_raw = pd.read_excel(excel_path, engine='xlrd', header=None)
                df = pd.read_excel(excel_path, engine='xlrd')
                print("[OK] Файл прочитан с движком xlrd (.xls)")
            except Exception as e:
                print(f"[ERROR] Не удалось прочитать .xls файл: {e}")
                print("   Установите: pip install xlrd")
                await conn.close()
                return False
        else:
            # Пробуем оба движка (для файлов без расширения или других форматов)
            try:
                df_raw = pd.read_excel(excel_path, engine='openpyxl', header=None)
                df = pd.read_excel(excel_path, engine='openpyxl')
                print("[OK] Файл прочитан с движком openpyxl")
            except:
                try:
                    df_raw = pd.read_excel(excel_path, engine='xlrd', header=None)
                    df = pd.read_excel(excel_path, engine='xlrd')
                    print("[OK] Файл прочитан с движком xlrd")
                except Exception as e:
                    print(f"[ERROR] Не удалось прочитать Excel файл: {e}")
                    print("   Установите: pip install openpyxl xlrd")
                    await conn.close()
                    return False
        
        print(f"[OK] Файл прочитан. Строк: {len(df_raw)}")
        print(f"[INFO] Колонки (первые 5): {list(df.columns[:5])}")
        
        # Ищем строку с заголовками колонок
        # Обычно это строка с текстом "Номенклатура", "Единица", "Артикул" и т.д.
        header_row = None
        for idx in range(min(20, len(df_raw))):  # Проверяем первые 20 строк
            row_values = [str(val).lower() if pd.notna(val) else '' for val in df_raw.iloc[idx].values]
            row_text = ' '.join(row_values)
            
            # Ищем ключевые слова заголовков
            if any(keyword in row_text for keyword in ['номенклатура', 'единица', 'артикул', 'товар', 'наименование']):
                header_row = idx
                print(f"[INFO] Найдена строка заголовков на строке {idx + 1}")
                break
        
        # Если нашли заголовки, перечитываем файл с правильным header
        if header_row is not None:
            print(f"[INFO] Перечитываем файл с заголовками со строки {header_row + 1}")
            try:
                df = pd.read_excel(excel_path, engine='openpyxl', header=header_row)
            except:
                try:
                    df = pd.read_excel(excel_path, engine='xlrd', header=header_row)
                except:
                    print("[WARNING] Не удалось перечитать с заголовками, используем исходные данные")
        
        print(f"[INFO] Колонки после обработки: {list(df.columns)}")
        
        # Определяем колонки
        date_col = None
        product_col = None
        quantity_col = None
        revenue_col = None
        
        # Ищем колонки по ключевым словам
        for col in df.columns:
            col_lower = str(col).lower()
            
            # Колонка с датой
            if any(keyword in col_lower for keyword in ['дата', 'date', 'период', 'period']):
                date_col = col
            
            # Колонка с товаром/номенклатурой
            if any(keyword in col_lower for keyword in ['номенклатура', 'товар', 'product', 'наименование', 'название']):
                product_col = col
            
            # Колонка с количеством
            if any(keyword in col_lower for keyword in ['количество', 'quantity', 'кол-во']):
                quantity_col = col
            
            # Колонка с суммой
            if any(keyword in col_lower for keyword in ['сумма', 'sum', 'revenue', 'выручка', 'стоимость']):
                revenue_col = col
        
        # Если не нашли колонки по названиям, определяем по содержимому
        if not product_col:
            # Ищем колонку, которая содержит формат "Название, единица, артикул"
            # Проверяем несколько первых непустых строк
            for col in df.columns:
                found_product_format = False
                for i in range(min(10, len(df))):
                    val = df.iloc[i][col]
                    if pd.notna(val) and isinstance(val, str):
                        val_str = str(val).strip()
                        # Проверяем формат: содержит запятые и похож на "Название, единица, артикул"
                        if ',' in val_str and not any(keyword in val_str.lower() for keyword in ['номенклатура', 'единица', 'артикул', 'итого']):
                            # Пробуем распарсить
                            parts = [p.strip() for p in val_str.split(',')]
                            if len(parts) >= 3:
                                # Третий элемент должен быть артикулом (число или буквы-цифры)
                                potential_article = parts[2].strip()
                                if re.match(r'^[A-Za-z0-9\-]+$', potential_article):
                                    product_col = col
                                    found_product_format = True
                                    break
                if found_product_format:
                    break
        
        # Если всё ещё не нашли, пробуем по позиции
        if not product_col:
            # Пробуем колонки по очереди, ищем ту, где есть формат с запятыми
            for col_idx, col in enumerate(df.columns):
                # Пропускаем первую колонку, если она похожа на дату
                if col_idx == 0:
                    continue
                # Проверяем несколько строк
                for i in range(min(5, len(df))):
                    val = df.iloc[i][col]
                    if pd.notna(val) and isinstance(val, str):
                        val_str = str(val).strip()
                        if ',' in val_str:
                            product_col = col
                            break
                if product_col:
                    break
        
        # Если всё ещё не нашли, используем первую колонку с данными
        if not product_col:
            product_col = df.columns[0]
        
        # Для даты - если не нашли по названию, пробуем определить
        # Но если в первой колонке товары, то дата может быть в другой колонке или отсутствовать
        if not date_col:
            # Если первая колонка - это товары, пробуем другие колонки для даты
            if product_col == df.columns[0] and len(df.columns) > 1:
                # Пробуем найти колонку с датами
                for col in df.columns[1:6]:  # Проверяем первые 5 колонок после товара
                    sample_vals = df[col].dropna().head(10)
                    date_count = 0
                    for val in sample_vals:
                        try:
                            pd.to_datetime(val)
                            date_count += 1
                        except:
                            pass
                    # Если больше половины значений - даты, это колонка с датой
                    if date_count > len(sample_vals) * 0.5:
                        date_col = col
                        break
            
            # Если не нашли, используем первую колонку (может быть дата или что-то другое)
            if not date_col:
                date_col = df.columns[0] if product_col != df.columns[0] else None
        
        print(f"[INFO] Колонка даты: {date_col}")
        print(f"[INFO] Колонка товара: {product_col}")
        if quantity_col:
            print(f"[INFO] Колонка количества: {quantity_col}")
        if revenue_col:
            print(f"[INFO] Колонка суммы: {revenue_col}")
        
        # Показываем примеры данных (пропускаем пустые строки)
        print("\n[INFO] Примеры данных (первые 10 непустых строк):")
        shown = 0
        for i in range(len(df)):
            if shown >= 10:
                break
            date_val = df.iloc[i][date_col] if date_col else None
            product_val = df.iloc[i][product_col] if product_col else None
            
            # Пропускаем строки, где нет данных
            if (date_col and pd.isna(date_val)) and (product_col and pd.isna(product_val)):
                continue
            
            print(f"   {i+1}. Дата: {date_val}, Товар: {product_val}")
            shown += 1
        
        # Статистика
        stats = {
            'total_rows': 0,  # Количество записей (для широкого формата - по одной на месяц)
            'product_rows': 0,  # Количество строк товаров в файле
            'imported': 0,
            'skipped': 0,
            'matched_products': 0,
            'unmatched_products': 0,
            'errors': 0,
            'debug_count': 0  # Счетчик для отладочных сообщений
        }
        
        # Генерируем batch_id для этого импорта
        batch_id = f"historical_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        print(f"\n[INFO] Начало импорта (batch_id: {batch_id})...")
        
        # Обрабатываем данные батчами
        records_to_insert = []
        
        # Определяем формат файла: широкий (даты в заголовках колонок) или обычный (дата в отдельной колонке)
        # Широкий формат: в заголовках колонок есть datetime объекты или даты
        wide_format = False
        if date_col is None:
            # Если не нашли колонку с датой, проверяем, есть ли datetime объекты в заголовках
            datetime_in_headers = False
            for col in df.columns:
                if isinstance(col, (datetime, pd.Timestamp)):
                    datetime_in_headers = True
                    break
            if datetime_in_headers:
                wide_format = True
        elif product_col == date_col:
            # Если продуктная колонка совпадает с датой, это широкий формат
            wide_format = True
        else:
            # Проверяем, есть ли datetime объекты в заголовках колонок (кроме колонки товара)
            datetime_in_headers = False
            for col in df.columns:
                if col != product_col and isinstance(col, (datetime, pd.Timestamp)):
                    datetime_in_headers = True
                    break
            if datetime_in_headers:
                wide_format = True
        
        if wide_format:
            print("[INFO] Обнаружен широкий формат: данные по месяцам в отдельных колонках")
            
            # Ищем строку с датами (datetime объекты или текстовые даты)
            date_row = None
            for idx in range(min(5, len(df_raw))):
                # Проверяем, есть ли в строке datetime объекты или даты в формате "2024-01-01"
                has_dates = False
                for col_idx in range(min(20, len(df_raw.columns))):
                    val = df_raw.iloc[idx, col_idx]
                    if pd.notna(val):
                        # Проверяем, является ли значение datetime объектом
                        if isinstance(val, (datetime, pd.Timestamp)):
                            has_dates = True
                            break
                        # Или датой в текстовом формате
                        val_str = str(val)
                        if re.match(r'^\d{4}-\d{2}-\d{2}', val_str) or re.match(r'^\d{2}\.\d{2}\.\d{4}', val_str):
                            has_dates = True
                            break
                
                if has_dates:
                    date_row = idx
                    break
            
            # Если не нашли datetime, ищем по текстовым ключевым словам (старый формат)
            if date_row is None:
                for idx in range(min(10, len(df_raw))):
                    row_values = [str(val).lower() if pd.notna(val) else '' for val in df_raw.iloc[idx].values]
                    month_keywords = ['янв', 'февр', 'март', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'нояб', 'дек']
                    if any(keyword in ' '.join(row_values) for keyword in month_keywords):
                        date_row = idx
                        break
            
            # Ищем строку с метриками (Количество/Сумма)
            metrics_row = None
            if date_row is not None:
                # Метрики обычно на следующей строке после дат
                for idx in range(date_row + 1, min(date_row + 3, len(df_raw))):
                    row_values = [str(val).lower() if pd.notna(val) else '' for val in df_raw.iloc[idx].values]
                    if row_values.count('количество') >= 1 or row_values.count('сумма') >= 1:
                        metrics_row = idx
                        break
            
            # Данные начинаются после строки метрик (или после строки дат, если метрик нет)
            if metrics_row is not None:
                data_start_row = metrics_row + 1
            elif date_row is not None:
                data_start_row = date_row + 2  # Пропускаем строку дат и следующую (может быть пустая)
            else:
                data_start_row = 2
            
            print(f"[INFO] Строка с датами: {date_row + 1 if date_row is not None else 'N/A'}, строка метрик: {metrics_row + 1 if metrics_row is not None else 'N/A'}, начало данных: {data_start_row + 1}")
            
            # Определяем колонку с товаром (первая непустая колонка с товарами)
            product_col_idx = None
            for col_idx in range(len(df_raw.columns)):
                # Ищем первую колонку, где есть товары в строках данных
                for row_idx in range(data_start_row, min(data_start_row + 10, len(df_raw))):
                    val = df_raw.iloc[row_idx, col_idx]
                    if pd.notna(val) and isinstance(val, str) and ',' in str(val):
                        product_col_idx = col_idx
                        break
                if product_col_idx is not None:
                    break
            
            if product_col_idx is None:
                product_col_idx = 0
            
            print(f"[INFO] Колонка с товарами: {product_col_idx}")
            
            # Собираем колонки метрик по месяцам
            # В упрощённой структуре может быть только количество, без отдельной строки метрик
            month_columns = []
            for col_idx in range(len(df_raw.columns)):
                # Пропускаем колонку с товарами (обычно колонка 0)
                if col_idx == product_col_idx:
                    continue
                
                # Сначала проверяем, что в строке дат нет "Итого"
                if date_row is not None:
                    date_val = df_raw.iloc[date_row, col_idx]
                    if pd.notna(date_val):
                        if isinstance(date_val, str):
                            date_str = str(date_val).strip().lower()
                            # Пропускаем колонки с "Итого" в строке дат
                            if 'итого' in date_str:
                                continue
                
                if metrics_row is not None:
                    metric_label = df_raw.iloc[metrics_row, col_idx]
                    if pd.isna(metric_label):
                        continue
                    metric_label = str(metric_label).strip().lower()
                    if metric_label not in ['количество', 'сумма']:
                        continue
                else:
                    # В упрощённой структуре все колонки с месяцами содержат количество
                    metric_label = 'количество'
                
                # Извлекаем дату/месяц из строки с датами
                # Сохраняем как datetime объект или строку для последующего парсинга
                month_label_raw = None
                if date_row is not None:
                    date_val = df_raw.iloc[date_row, col_idx]
                    if pd.notna(date_val):
                        # Если это datetime объект, сохраняем его напрямую
                        if isinstance(date_val, (datetime, pd.Timestamp)):
                            # Проверяем, что дата в разумных пределах
                            if 2020 <= date_val.year <= 2030:
                                month_label_raw = date_val
                        else:
                            date_str = str(date_val).strip()
                            # Проверяем, что это не "Итого" или другие служебные значения
                            if date_str.lower() not in ['итого', 'nan', 'none', '']:
                                month_label_raw = date_str
                    
                    # Если месяц не указан в этой колонке, пробуем взять из предыдущей (для пар Количество/Сумма)
                    # Для колонки "Сумма" дата всегда берется из предыдущей колонки "Количество"
                    if month_label_raw is None or (isinstance(month_label_raw, str) and month_label_raw.lower() in ['итого', 'nan', 'none', '']):
                        if col_idx > 0:
                            # Если текущая колонка - "Сумма", сразу берем дату из предыдущей колонки
                            if metric_label == 'сумма':
                                prev_col_idx = col_idx - 1
                                if prev_col_idx >= 0:
                                    prev_date = df_raw.iloc[date_row, prev_col_idx]
                                    if pd.notna(prev_date):
                                        if isinstance(prev_date, (datetime, pd.Timestamp)):
                                            if 2020 <= prev_date.year <= 2030:
                                                month_label_raw = prev_date
                                        else:
                                            prev_date_str = str(prev_date).strip()
                                            # Проверяем, что это дата, а не что-то другое
                                            if prev_date_str.lower() not in ['итого', 'nan', 'none', '']:
                                                if re.match(r'^\d{4}-\d{2}-\d{2}', prev_date_str) or re.match(r'^\d{2}\.\d{2}\.\d{4}', prev_date_str) or any(keyword in prev_date_str.lower() for keyword in ['янв', 'февр', 'март', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'нояб', 'дек']):
                                                    month_label_raw = prev_date_str
                            else:
                                # Для других случаев ищем ближайшую предыдущую колонку с датой
                                for prev_col_idx in range(col_idx - 1, max(0, col_idx - 3), -1):
                                    prev_date = df_raw.iloc[date_row, prev_col_idx]
                                    if pd.notna(prev_date):
                                        if isinstance(prev_date, (datetime, pd.Timestamp)):
                                            if 2020 <= prev_date.year <= 2030:
                                                month_label_raw = prev_date
                                        else:
                                            prev_date_str = str(prev_date).strip()
                                            # Проверяем, что это дата, а не что-то другое
                                            if prev_date_str.lower() not in ['итого', 'nan', 'none', '']:
                                                if re.match(r'^\d{4}-\d{2}-\d{2}', prev_date_str) or re.match(r'^\d{2}\.\d{2}\.\d{4}', prev_date_str) or any(keyword in prev_date_str.lower() for keyword in ['янв', 'февр', 'март', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'нояб', 'дек']):
                                                    month_label_raw = prev_date_str
                                        if month_label_raw:
                                            break
                
                # Пропускаем колонки без даты (например, "Итого")
                if month_label_raw is None or (isinstance(month_label_raw, str) and month_label_raw.lower() in ['итого', 'nan', 'none', '']):
                    continue
                
                # Для отображения конвертируем в строку, но сохраняем raw для парсинга
                month_label_display = None
                if month_label_raw is not None:
                    if isinstance(month_label_raw, (datetime, pd.Timestamp)):
                        month_label_display = month_label_raw.strftime('%Y-%m-%d')
                    else:
                        month_label_display = str(month_label_raw)
                
                month_columns.append({
                    'col_idx': col_idx,
                    'metric': metric_label,
                    'month_label': month_label_raw,  # Сохраняем raw (datetime или строка) для парсинга
                    'month_label_display': month_label_display  # Для отображения
                })
            
            print(f"[INFO] Найдено колонок с метриками: {len(month_columns)}")
            print(f"[INFO] Примеры первых 10 колонок:")
            for i, col_info in enumerate(month_columns[:10]):
                display_label = col_info.get('month_label_display', col_info.get('month_label', 'N/A'))
                metric = col_info.get('metric', 'N/A')
                # Показываем, что колонки "Сумма" используют дату из предыдущей колонки "Количество"
                if metric == 'сумма' and i > 0:
                    prev_col = month_columns[i-1] if i > 0 else None
                    if prev_col and prev_col.get('metric') == 'количество':
                        prev_display = prev_col.get('month_label_display', 'N/A')
                        print(f"  Колонка {col_info['col_idx']}: metric='{col_info['metric']}', month_label='{display_label}' (из предыдущей колонки 'Количество': {prev_display})")
                    else:
                        print(f"  Колонка {col_info['col_idx']}: metric='{col_info['metric']}', month_label='{display_label}'")
                else:
                    print(f"  Колонка {col_info['col_idx']}: metric='{col_info['metric']}', month_label='{display_label}'")
            
            # Парсер месяца
            # Поддерживаем разные варианты сокращений
            month_map = {
                'янв': 1, 
                'фев': 2, 'февр': 2,  # "февр. 24"
                'мар': 3, 'март': 3,
                'апр': 4,
                'май': 5,
                'июн': 6, 'июнь': 6,
                'июл': 7, 'июль': 7,
                'авг': 8, 'авгу': 8,
                'сен': 9, 'сент': 9,  # "сент. 24"
                'окт': 10, 'октя': 10,
                'ноя': 11, 'нояб': 11,  # "нояб. 24"
                'дек': 12, 'дека': 12
            }
            
            def parse_month_label(label) -> Optional[datetime]:
                if label is None:
                    return None
                
                # Если это уже datetime объект, извлекаем год и месяц
                if isinstance(label, (datetime, pd.Timestamp)):
                    if 2020 <= label.year <= 2030:
                        return datetime(label.year, label.month, 1)
                    return None
                
                label_str = str(label).strip()
                if not label_str or label_str.lower() in ['nan', 'none', '']:
                    return None
                
                label_lower = label_str.lower()
                if 'итого' in label_lower:
                    return None
                
                # Сначала пробуем распарсить как дату в форматах "2024-01-01" или "01.02.2024"
                try:
                    # Формат ISO: "2024-01-01" (YYYY-MM-DD) или "2024-01-01 00:00:00"
                    if re.match(r'^\d{4}-\d{2}-\d{2}', label_str):
                        # Убираем время, если есть
                        date_part = label_str.split()[0] if ' ' in label_str else label_str
                        date_obj = pd.to_datetime(date_part, format='%Y-%m-%d', errors='coerce')
                        if pd.notna(date_obj) and 2020 <= date_obj.year <= 2030:
                            return datetime(date_obj.year, date_obj.month, 1)
                    
                    # Формат DD.MM.YYYY: "01.02.2024"
                    if re.match(r'^\d{2}\.\d{2}\.\d{4}', label_str):
                        date_obj = pd.to_datetime(label_str, format='%d.%m.%Y', errors='coerce')
                        if pd.notna(date_obj) and 2020 <= date_obj.year <= 2030:
                            return datetime(date_obj.year, date_obj.month, 1)
                    
                    # Формат DD/MM/YYYY: "01/02/2024"
                    if re.match(r'^\d{2}/\d{2}/\d{4}', label_str):
                        date_obj = pd.to_datetime(label_str, format='%d/%m/%Y', errors='coerce')
                        if pd.notna(date_obj) and 2020 <= date_obj.year <= 2030:
                            return datetime(date_obj.year, date_obj.month, 1)
                    
                    # Пробуем автоматический парсинг pandas для других форматов дат
                    date_obj = pd.to_datetime(label_str, errors='coerce')
                    if pd.notna(date_obj):
                        # Строгая проверка года - возвращаем None для дат вне диапазона
                        if 2020 <= date_obj.year <= 2030:
                            return datetime(date_obj.year, date_obj.month, 1)
                        else:
                            # Дата вне допустимого диапазона
                            return None
                except Exception as e:
                    # Если не удалось распарсить как дату, продолжаем с парсингом месяца
                    pass
                
                # Если не удалось распарсить как дату, пробуем как месяц (старый формат)
                # Примеры: "янв. 24", "янв 24", "январь 2024", "янв.24", "февр. 24"
                patterns = [
                    r'([а-я]+)\.?\s*(\d{2,4})',  # "янв. 24" или "янв 24" или "февр. 24"
                    r'([а-я]+)\s+(\d{4})',       # "январь 2024"
                    r'([а-я]+)\.(\d{2,4})',      # "янв.24" (без пробела)
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, label_lower)
                    if match:
                        month_str_full = match.group(1)
                        year_str = match.group(2)
                        
                        # Пробуем разные варианты сокращений месяцев
                        month_num = None
                        # Сначала пробуем первые 4 буквы (для "февр", "сент", "нояб" и т.д.)
                        if len(month_str_full) >= 4:
                            month_num = month_map.get(month_str_full[:4])
                        # Если не нашли, пробуем первые 3 буквы
                        if not month_num:
                            month_num = month_map.get(month_str_full[:3])
                        
                        if month_num:
                            try:
                                year = int(year_str)
                                if year < 100:
                                    year += 2000
                                # Проверяем, что год в разумных пределах
                                if 2020 <= year <= 2030:
                                    result = datetime(year, month_num, 1)
                                    return result
                                else:
                                    # Логируем подозрительные годы
                                    if stats.get('debug_count', 0) < 5:
                                        print(f"[DEBUG] Год вне диапазона: '{label_str}' -> год {year}")
                                        stats['debug_count'] = stats.get('debug_count', 0) + 1
                            except ValueError as e:
                                if stats.get('debug_count', 0) < 5:
                                    print(f"[DEBUG] Ошибка парсинга года: '{label_str}' -> {e}")
                                    stats['debug_count'] = stats.get('debug_count', 0) + 1
                                continue
                        else:
                            # Логируем нераспознанные месяцы
                            if stats.get('debug_count', 0) < 5:
                                print(f"[DEBUG] Месяц не распознан: '{label_str}' -> month_str='{month_str_full}'")
                                stats['debug_count'] = stats.get('debug_count', 0) + 1
                
                return None
            
            # Проходим по строкам данных
            for row_idx in range(data_start_row, len(df_raw)):
                try:
                    product_val = df_raw.iloc[row_idx, product_col_idx]
                    if pd.isna(product_val):
                        continue
                    
                    product_str = str(product_val).strip()
                    if not product_str or product_str.lower() in ['nan', 'none', '']:
                        continue
                    
                    # Пропускаем строки-заголовки
                    if any(keyword in product_str.lower() for keyword in ['номенклатура', 'итого', 'выводимые данные']):
                        continue
                    
                    product_name, unit, article = parse_product_string(product_str)
                    if not article:
                        continue
                    
                    # Увеличиваем счётчик строк товаров
                    stats['product_rows'] += 1
                    
                    # Ищем товар в каталоге
                    product_info = await get_product_by_article(conn, article)
                    if product_info:
                        stats['matched_products'] += 1
                        product_id = str(product_info['id'])
                        category = product_info.get('category')
                        brand = product_info.get('brand')
                    else:
                        stats['unmatched_products'] += 1
                        product_id = None
                        category = None
                        brand = None
                    
                    # Для каждой колонки месяца создаем запись
                    month_data = {}
                    for col_info in month_columns:
                        month_label_raw = col_info['month_label']  # datetime объект или строка
                        month_label_display = col_info.get('month_label_display', str(month_label_raw) if month_label_raw else 'N/A')
                        metric = col_info['metric']
                        col_idx = col_info['col_idx']
                        
                        month_date = parse_month_label(month_label_raw)
                        if month_date is None:
                            # Пропускаем колонки "Итого" и другие без даты
                            # Но логируем для отладки первые несколько случаев
                            if stats['total_rows'] < 5:
                                print(f"[DEBUG] Пропущена колонка: month_label='{month_label_display}', metric='{metric}', col_idx={col_idx}")
                            continue
                        
                        # Проверяем, что дата правильная (не 1970)
                        if month_date.year < 2020:
                            if stats['total_rows'] < 5:
                                print(f"[DEBUG] Подозрительная дата: month_label='{month_label_display}' -> {month_date}")
                            continue
                        
                        val = df_raw.iloc[row_idx, col_idx]
                        if pd.isna(val):
                            continue
                        
                        # Парсим значение
                        try:
                            if isinstance(val, (int, float)):
                                num_val = float(val)
                            else:
                                num_val = float(str(val).replace(' ', '').replace(',', '.'))
                        except:
                            num_val = 0.0
                        
                        # Пропускаем нулевые значения
                        if num_val == 0.0:
                            continue
                        
                        # Используем month_date как ключ, но сохраняем month_label для raw_data
                        if month_date not in month_data:
                            month_data[month_date] = {
                                'quantity': 0.0, 
                                'revenue': 0.0,
                                'month_label': month_label_display  # Сохраняем display label для raw_data
                            }
                        
                        if metric == 'количество':
                            month_data[month_date]['quantity'] = num_val
                        elif metric == 'сумма':
                            month_data[month_date]['revenue'] = num_val
                    
                    # Создаем записи только для месяцев, где есть данные (quantity > 0 или revenue > 0)
                    for month_date, metrics in month_data.items():
                        # Пропускаем записи, где оба значения равны 0
                        if metrics['quantity'] == 0 and metrics['revenue'] == 0:
                            continue
                        
                        # Проверяем, что дата правильная (не 1970)
                        if month_date.year < 2020:
                            print(f"[WARNING] Подозрительная дата для товара {product_name} (артикул {article}): {month_date}, month_label: {metrics.get('month_label')}")
                            continue
                        
                        record = {
                            'sale_date': to_utc_datetime(month_date),
                            'external_id': f"{batch_id}_{row_idx}_{month_date.strftime('%Y%m')}",
                            'product_id': product_id,
                            'product_name': product_name,
                            'product_article': article,
                            'product_category': category,
                            'product_brand': brand,
                            'revenue': metrics['revenue'],
                            'quantity': metrics['quantity'],
                            'channel': 'offline',
                            'raw_data': {
                                'source': 'historical_excel_wide',
                                'original_string': product_str,
                                'unit': unit,
                                'row_index': int(row_idx),
                                'month_label': metrics.get('month_label', 'N/A')  # Используем сохраненный label
                            },
                            'sync_batch_id': batch_id,
                            'synced_at': datetime.now()
                        }
                        
                        records_to_insert.append(record)
                        stats['total_rows'] += 1
                        
                        # Вставляем батчами
                        if len(records_to_insert) >= batch_size:
                            await insert_batch(conn, records_to_insert)
                            stats['imported'] += len(records_to_insert)
                            records_to_insert = []
                            print(f"   Импортировано: {stats['imported']}/{stats['total_rows']}")
                
                except Exception as e:
                    stats['errors'] += 1
                    print(f"[WARNING] Ошибка в строке {row_idx}: {e}")
                    continue
        
        else:
            # Обычный (неширокий) формат
            for idx, row in df.iterrows():
                try:
                    # Парсим дату (может отсутствовать)
                    sale_date = None
                    if date_col:
                        date_val = row[date_col]
                        if pd.notna(date_val):
                            # Пропускаем строки-заголовки
                            if isinstance(date_val, str):
                                date_str_lower = date_val.lower()
                                if any(keyword in date_str_lower for keyword in ['номенклатура', 'единица', 'артикул', 'итого', 'выводимые данные']):
                                    stats['skipped'] += 1
                                    continue
                            
                            # Конвертируем дату
                            try:
                                if isinstance(date_val, datetime):
                                    sale_date = date_val
                                else:
                                    sale_date = pd.to_datetime(date_val)
                                
                                # Проверяем, что дата в разумных пределах
                                if sale_date is not None:
                                    if isinstance(sale_date, pd.Timestamp):
                                        sale_date = sale_date.to_pydatetime()
                                    if sale_date.year < 2020 or sale_date.year > 2030:
                                        # Дата вне допустимого диапазона
                                        sale_date = None
                            except:
                                # Если не удалось распарсить дату, используем None
                                sale_date = None
                    
                    # Если дата не найдена или неправильная, используем дату по умолчанию
                    if sale_date is None:
                        sale_date = datetime(2025, 1, 1)
                    sale_date = to_utc_datetime(sale_date)
                    
                    # Парсим товар
                    product_val = row[product_col]
                    if pd.isna(product_val):
                        stats['skipped'] += 1
                        continue
                    
                    product_str = str(product_val).strip()
                    
                    # Пропускаем строки-заголовки и служебные строки
                    product_str_lower = product_str.lower()
                    if any(keyword in product_str_lower for keyword in ['номенклатура', 'единица', 'артикул', 'итого', 'выводимые данные', 'продажи за', 'товар, шт']):
                        # Но пропускаем только если это точно заголовок (не содержит реального артикула)
                        if not re.search(r'\b[0-9]{4,}\b', product_str):
                            stats['skipped'] += 1
                            continue
                    
                    # Пропускаем пустые строки
                    if not product_str or product_str.lower() in ['nan', 'none', '']:
                        stats['skipped'] += 1
                        continue
                    
                    product_name, unit, article = parse_product_string(product_str)
                    
                    if not article:
                        # Пробуем ещё раз - возможно артикул просто число в конце
                        # Формат может быть: "Название, единица, число"
                        parts = [p.strip() for p in product_str.split(',')]
                        if len(parts) >= 3:
                            potential_article = parts[-1].strip()
                            # Если последняя часть - это число или буквенно-цифровой код
                            if re.match(r'^[A-Za-z0-9\-]+$', potential_article):
                                article = potential_article
                                product_name = ', '.join(parts[:-2]) if len(parts) > 2 else parts[0]
                                unit = parts[-2] if len(parts) > 2 else None
                    
                    if not article:
                        stats['skipped'] += 1
                        continue
                    
                    # Увеличиваем счётчик строк товаров
                    stats['product_rows'] += 1
                    
                    # Парсим количество и сумму, если есть колонки
                    quantity = 1.0
                    if quantity_col and not pd.isna(row[quantity_col]):
                        try:
                            qty_val = row[quantity_col]
                            if isinstance(qty_val, (int, float)):
                                quantity = float(qty_val)
                            else:
                                quantity = float(str(qty_val).replace(',', '.'))
                        except:
                            quantity = 1.0
                    
                    revenue = 0.0
                    if revenue_col and not pd.isna(row[revenue_col]):
                        try:
                            rev_val = row[revenue_col]
                            if isinstance(rev_val, (int, float)):
                                revenue = float(rev_val)
                            else:
                                revenue = float(str(rev_val).replace(',', '.').replace(' ', ''))
                        except:
                            revenue = 0.0
                    
                    # Ищем товар в каталоге
                    product_info = await get_product_by_article(conn, article)
                    
                    if product_info:
                        stats['matched_products'] += 1
                        product_id = str(product_info['id'])
                        category = product_info.get('category')
                        brand = product_info.get('brand')
                    else:
                        stats['unmatched_products'] += 1
                        product_id = None
                        category = None
                        brand = None
                    
                    # Формируем запись для вставки
                    record = {
                        'sale_date': to_utc_datetime(sale_date),
                        'external_id': f"{batch_id}_{idx}",
                        'product_id': product_id,
                        'product_name': product_name,
                        'product_article': article,
                        'product_category': category,
                        'product_brand': brand,
                        'revenue': revenue,
                        'quantity': quantity,
                        'channel': 'offline',  # Исторические данные обычно офлайн
                        'raw_data': {
                            'source': 'historical_excel',
                            'original_string': str(product_val),
                            'unit': unit,
                            'row_index': int(idx),
                            'quantity_from_file': quantity if quantity_col else None,
                            'revenue_from_file': revenue if revenue_col else None
                        },
                        'sync_batch_id': batch_id,
                        'synced_at': datetime.now()
                    }
                    
                    records_to_insert.append(record)
                    stats['total_rows'] += 1
                    
                    # Вставляем батчами
                    if len(records_to_insert) >= batch_size:
                        await insert_batch(conn, records_to_insert)
                        stats['imported'] += len(records_to_insert)
                        records_to_insert = []
                        print(f"   Импортировано: {stats['imported']}/{stats['total_rows']}")
                
                except Exception as e:
                    stats['errors'] += 1
                    print(f"[WARNING] Ошибка в строке {idx}: {e}")
                    continue
        
        # Вставляем оставшиеся записи
        if records_to_insert:
            await insert_batch(conn, records_to_insert)
            stats['imported'] += len(records_to_insert)
        
        # Выводим статистику
        print("\n" + "=" * 60)
        print("[INFO] Статистика импорта:")
        if wide_format:
            print(f"   Строк товаров в файле: {stats['product_rows']}")
            print(f"   Создано записей (по одной на месяц с продажами): {stats['total_rows']}")
        else:
            print(f"   Всего строк в файле: {stats['total_rows']}")
        print(f"   Импортировано: {stats['imported']}")
        print(f"   Пропущено: {stats['skipped']}")
        print(f"   Ошибок: {stats['errors']}")
        print(f"   Товаров найдено в каталоге: {stats['matched_products']}")
        print(f"   Товаров не найдено: {stats['unmatched_products']}")
        print("=" * 60)
        
        await conn.close()
        print("\n[OK] Импорт завершен успешно!")
        return True
        
    except Exception as e:
        print(f"[ERROR] Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False


async def insert_batch(conn: asyncpg.Connection, records: list):
    """Вставляет батч записей в БД"""
    if not records:
        return
    
    import json
    
    # Фильтруем записи с external_id для проверки существования
    records_with_id = [r for r in records if r.get('external_id')]
    records_without_id = [r for r in records if not r.get('external_id')]
    
    # Для записей с external_id проверяем существование
    if records_with_id:
        external_ids = [r['external_id'] for r in records_with_id]
        existing_ids = await conn.fetch("""
            SELECT external_id FROM sales_records 
            WHERE external_id = ANY($1::text[])
        """, external_ids)
        existing_set = {row['external_id'] for row in existing_ids}
        
        # Фильтруем только новые записи
        new_records = [r for r in records_with_id if r['external_id'] not in existing_set]
    else:
        new_records = []
    
    # Объединяем новые записи с записями без external_id
    all_new_records = new_records + records_without_id
    
    if not all_new_records:
        return
    
    # Вставляем только новые записи
    await conn.executemany("""
        INSERT INTO sales_records (
            sale_date, external_id, product_id, product_name, product_article,
            product_category, product_brand, revenue, quantity, channel,
            raw_data, sync_batch_id, synced_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13
        )
    """, [
        (
            r['sale_date'],
            r['external_id'],
            r['product_id'],
            r['product_name'],
            r['product_article'],
            r['product_category'],
            r['product_brand'],
            r['revenue'],
            r['quantity'],
            r['channel'],
            json.dumps(r['raw_data'], ensure_ascii=False) if r['raw_data'] else None,  # Сериализуем dict в JSON
            r['sync_batch_id'],
            r['synced_at']
        )
        for r in all_new_records
    ])


if __name__ == "__main__":
    import argparse
    
    # Настройка для Windows
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # Парсинг аргументов командной строки
    parser = argparse.ArgumentParser(description='Импорт исторических данных о продажах из Excel')
    parser.add_argument(
        '--file',
        type=str,
        default=None,
        help='Путь к Excel файлу (по умолчанию: 1c/sales25.xlsx)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=1000,
        help='Размер батча для вставки (по умолчанию: 1000)'
    )
    
    args = parser.parse_args()
    
    # Определяем путь к файлу
    if args.file:
        excel_path = Path(args.file)
    else:
        excel_path = Path(__file__).parent.parent / "1c" / "sales25.xlsx"
    
    print("=" * 60)
    print("Импорт исторических данных о продажах из Excel")
    print("=" * 60)
    print(f"Файл: {excel_path}")
    print(f"Размер батча: {args.batch_size}")
    print()
    
    if not excel_path.exists():
        print(f"[ERROR] Файл не найден: {excel_path}")
        print("   Убедитесь, что файл существует или укажите путь через --file")
        sys.exit(1)
    
    success = asyncio.run(import_historical_sales(excel_path, batch_size=args.batch_size))
    
    if success:
        print("\n" + "=" * 60)
        print("[OK] Скрипт выполнен успешно!")
        print("=" * 60)
        exit(0)
    else:
        print("\n" + "=" * 60)
        print("[ERROR] Скрипт завершился с ошибками")
        print("=" * 60)
        exit(1)

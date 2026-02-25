"""
Скрипт синхронизации данных счетчиков магазинов с FTP
Загружает данные из файлов счетчиков и сохраняет в БД
"""
import sys
import os
import ftplib
import json
import csv
import xml.etree.ElementTree as ET
from datetime import datetime, date as date_type
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import psycopg2
from dotenv import load_dotenv

# Пути
script_path = Path(__file__).resolve()
root_path = script_path.parent
backend_path = root_path / "backend"
sys.path.insert(0, str(backend_path))

# Загружаем .env
env_path = backend_path / ".env"
load_dotenv(dotenv_path=env_path, override=True)

# FTP настройки
FTP_CONFIG = {
    "host": os.getenv("FTP_HOST", "5.101.179.47"),
    "username": os.getenv("FTP_USERNAME"),
    "password": os.getenv("FTP_PASSWORD"),
    "directory": os.getenv("FTP_DIRECTORY", "/")
}

# Соответствие папок FTP и названий магазинов
STORES = {
    "CENTRUM": "CENTRUM",
    "YALTA": "YALTA"
}

# Цветной вывод
class Colors:
    GREEN = '\033[92m'
    BLUE = '\033[94m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_success(msg: str):
    print(f"{Colors.GREEN}[OK] {msg}{Colors.RESET}")

def print_info(msg: str):
    print(f"{Colors.BLUE}[INFO] {msg}{Colors.RESET}")

def print_warning(msg: str):
    print(f"{Colors.YELLOW}[WARN] {msg}{Colors.RESET}")

def print_error(msg: str):
    print(f"{Colors.RED}[ERROR] {msg}{Colors.RESET}")

def print_separator():
    print(f"{Colors.BOLD}{'='*60}{Colors.RESET}")

class FTPService:
    """Сервис для работы с FTP"""
    
    def __init__(self, host: str, username: str, password: str, directory: str = "/"):
        self.host = host
        self.username = username
        self.password = password
        self.directory = directory
        self.ftp = None
    
    def connect(self):
        """Подключение к FTP"""
        try:
            self.ftp = ftplib.FTP(self.host)
            self.ftp.login(self.username, self.password)
            self.ftp.cwd(self.directory)
            return True
        except Exception as e:
            print_error(f"FTP connection error: {e}")
            return False
    
    def list_files_recursive(self, path: str = "") -> List[Dict[str, str]]:
        """Рекурсивно получает список файлов"""
        full_path = os.path.join(self.directory, path).replace("\\", "/")
        entries = []
        
        try:
            self.ftp.cwd(full_path)
            listing = []
            self.ftp.dir(listing.append)
            
            for line in listing:
                parts = line.split(None, 8)
                if len(parts) < 9:
                    continue
                
                name = parts[8]
                if name in ['.', '..']:
                    continue
                
                is_dir = parts[0].startswith('d')
                entry_path = os.path.join(path, name).replace("\\", "/")
                
                if is_dir:
                    entries.extend(self.list_files_recursive(entry_path))
                else:
                    entries.append({"name": name, "path": entry_path, "is_dir": False})
        except Exception as e:
            print_warning(f"Error listing {full_path}: {e}")
        finally:
            self.ftp.cwd(self.directory)
        
        return entries
    
    def download_file(self, filename: str) -> Optional[bytes]:
        """Скачивание файла"""
        try:
            from io import BytesIO
            buffer = BytesIO()
            self.ftp.retrbinary(f"RETR {filename}", buffer.write)
            return buffer.getvalue()
        except Exception as e:
            print_error(f"Error downloading {filename}: {e}")
            return None
    
    def parse_file(self, content: bytes, filename: str) -> List[Dict[str, Any]]:
        """Парсинг файла"""
        data = []
        ext = filename.lower().split('.')[-1]
        
        try:
            if ext == 'csv':
                text = content.decode('utf-8-sig')
                reader = csv.DictReader(text.splitlines())
                data = list(reader)
            
            elif ext == 'json':
                data = json.loads(content.decode('utf-8'))
                if not isinstance(data, list):
                    data = [data]
            
            elif ext == 'xml':
                root = ET.fromstring(content.decode('utf-8'))
                for record in root.findall('.//record'):
                    item = {}
                    for field in record:
                        item[field.tag] = field.text
                    data.append(item)
            
            elif ext == 'txt':
                text = content.decode('utf-8-sig')
                lines = [l.strip() for l in text.splitlines() if l.strip()]
                if not lines:
                    return []
                
                # Проверяем, не является ли это файлом MEGACOUNT_3D
                if 'device_name: MEGACOUNT_3D' in text or 'total_out:' in text:
                    # Парсим формат MEGACOUNT_3D - считаем по total_out (вышедших)
                    visitors = 0
                    for line in lines:
                        if line.startswith('total_out:'):
                            visitors = int(line.split(':')[1].strip())
                            break
                    data.append({"visitors": visitors})
                else:
                    # Стандартный формат CSV/TSV
                    headers = lines[0].split(',') if ',' in lines[0] else lines[0].split('\t')
                    
                    for line in lines[1:]:
                        values = line.split(',') if ',' in line else line.split('\t')
                        if len(values) == len(headers):
                            data.append(dict(zip(headers, values)))
                        else:
                            # Простая запись без структуры - предполагаем, что это число посетителей
                            try:
                                num = int(line)
                                data.append({"visitors": num})
                            except:
                                data.append({"value": line})
        
        except Exception as e:
            print_error(f"Parse error for {filename}: {e}")
        
        return data
    
    def disconnect(self):
        """Отключение от FTP"""
        if self.ftp:
            try:
                self.ftp.quit()
            except:
                pass


def get_db_connection():
    """Создание подключения к БД"""
    database_url = os.getenv("DATABASE_URL", "")
    # Преобразуем asyncpg в psycopg2 формат
    database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    
    if not database_url:
        raise ValueError("DATABASE_URL не найден в .env")
    
    # Парсим URL
    from urllib.parse import urlparse
    parsed = urlparse(database_url)
    
    return psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        database=parsed.path[1:],
        user=parsed.username,
        password=parsed.password
    )


def ensure_store_exists(cursor, store_name: str) -> str:
    """Проверяет существование магазина или создает новый"""
    cursor.execute("SELECT id FROM stores WHERE name = %s", (store_name,))
    result = cursor.fetchone()
    
    if result:
        return str(result[0])
    
    print_info(f"Создание магазина: {store_name}")
    cursor.execute(
        "INSERT INTO stores (name, city, is_active) VALUES (%s, %s, %s) RETURNING id",
        (store_name, "Севастополь", True)
    )
    store_id = cursor.fetchone()[0]
    print_success(f"Магазин создан: {store_name}")
    return str(store_id)


def sync_store_data(conn, cursor, store_name: str, store_folder: str) -> Tuple[int, int, int]:
    """Синхронизация данных одного магазина"""
    print()
    print_info(f"Синхронизация магазина: {store_name}")
    
    ftp_service = FTPService(**FTP_CONFIG)
    if not ftp_service.connect():
        print_error(f"Не удалось подключиться к FTP для {store_name}")
        return 0, 0, 1
    
    created_count = 0
    updated_count = 0
    error_count = 0
    
    try:
        # Получаем или создаем магазин в БД
        store_id = ensure_store_exists(cursor, store_name)
        
        # Получаем файлы из папки магазина
        all_files = ftp_service.list_files_recursive(store_folder)
        parseable_files = [f for f in all_files if not f['is_dir'] and 
                          f['name'].lower().endswith(('.csv', '.json', '.xml', '.txt'))]
        
        print_info(f"Найдено файлов: {len(parseable_files)}")
        
        for file_info in parseable_files:
            try:
                file_path = file_info['path']
                print_info(f"Обработка: {file_info['name']}")
                
                content = ftp_service.download_file(file_path)
                if not content:
                    error_count += 1
                    continue
                
                data = ftp_service.parse_file(content, file_info['name'])
                
                # Извлекаем дату из имени файла (формат: YYMMDD.txt)
                filename = file_info['name']
                try:
                    date_part = filename.split('.')[0]  # Убираем расширение
                    if len(date_part) == 6 and date_part.isdigit():
                        yy = int(date_part[0:2])
                        mm = int(date_part[2:4])
                        dd = int(date_part[4:6])
                        # Предполагаем 20xx для yy < 50, иначе 19xx
                        year = 2000 + yy if yy < 50 else 1900 + yy
                        visit_date = date_type(year, mm, dd)
                    else:
                        visit_date = datetime.now().date()
                except:
                    visit_date = datetime.now().date()
                
                for record in data:
                    try:
                        # Переопределяем дату, если она указана в записи
                        if record.get('date') or record.get('Дата'):
                            date_str = record.get('date') or record.get('Дата')
                            if isinstance(date_str, str):
                                try:
                                    visit_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                                except:
                                    try:
                                        visit_date = datetime.strptime(date_str, '%d.%m.%Y').date()
                                    except:
                                        pass  # Используем дату из имени файла
                        
                        visitor_count = int(record.get('visitors') or record.get('Посетители') or record.get('value') or 0)
                        sales_count = int(record.get('sales') or record.get('Продажи') or 0)
                        revenue = float(record.get('revenue') or record.get('Выручка') or 0)
                        
                        # Проверяем существующую запись
                        cursor.execute(
                            "SELECT id FROM store_visits WHERE store_id = %s AND date = %s",
                            (store_id, visit_date)
                        )
                        existing = cursor.fetchone()
                        
                        if existing:
                            cursor.execute(
                                """UPDATE store_visits 
                                   SET visitor_count = %s, sales_count = %s, revenue = %s, updated_at = NOW()
                                   WHERE id = %s""",
                                (visitor_count, sales_count, revenue, existing[0])
                            )
                            updated_count += 1
                        else:
                            cursor.execute(
                                """INSERT INTO store_visits (store_id, date, visitor_count, sales_count, revenue)
                                   VALUES (%s, %s, %s, %s, %s)""",
                                (store_id, visit_date, visitor_count, sales_count, revenue)
                            )
                            created_count += 1
                    
                    except Exception as e:
                        print_warning(f"Ошибка записи: {e}")
                        error_count += 1
            
            except Exception as e:
                print_error(f"Ошибка обработки файла {file_info['name']}: {e}")
                error_count += 1
        
        conn.commit()
        ftp_service.disconnect()
        
        print_success(f"Магазин {store_name}: создано {created_count}, обновлено {updated_count}, ошибок {error_count}")
        
    except Exception as e:
        print_error(f"Критическая ошибка для {store_name}: {e}")
        conn.rollback()
        error_count += 1
    
    return created_count, updated_count, error_count


def main():
    """Главная функция"""
    print()
    print_separator()
    print("СИНХРОНИЗАЦИЯ ДАННЫХ СЧЕТЧИКОВ МАГАЗИНОВ")
    print_separator()
    print()
    
    print_info(f"FTP сервер: {FTP_CONFIG['host']}")
    print_info(f"Магазины: {', '.join(STORES.keys())}")
    print()
    
    try:
        # Подключаемся к БД
        conn = get_db_connection()
        cursor = conn.cursor()
        
        total_created = 0
        total_updated = 0
        total_errors = 0
        
        # Синхронизируем каждый магазин
        for store_name, store_folder in STORES.items():
            try:
                created, updated, errors = sync_store_data(conn, cursor, store_name, store_folder)
                total_created += created
                total_updated += updated
                total_errors += errors
            except Exception as e:
                print_error(f"Ошибка синхронизации {store_name}: {e}")
                total_errors += 1
                continue
        
        cursor.close()
        conn.close()
        
        # Итоговая статистика
        print()
        print_separator()
        print_success(f"Синхронизация завершена")
        print_info(f"Всего создано записей: {total_created}")
        print_info(f"Всего обновлено записей: {total_updated}")
        if total_errors > 0:
            print_warning(f"Ошибок: {total_errors}")
        print_separator()
        
        return 0 if total_errors == 0 else 1
    
    except Exception as e:
        print()
        print_error(f"Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print()
        print_warning("Прервано пользователем")
        sys.exit(130)

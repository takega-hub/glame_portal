import ftplib
import os
import csv
import json
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
from datetime import datetime
from io import StringIO, BytesIO
import logging

logger = logging.getLogger(__name__)


class FTPService:
    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        directory: str = "/"
    ):
        self.host = host
        self.username = username
        self.password = password
        self.directory = directory
        self.ftp = None
    
    def connect(self) -> ftplib.FTP:
        """Подключение к FTP серверу"""
        try:
            self.ftp = ftplib.FTP(self.host)
            self.ftp.login(self.username, self.password)
            if self.directory:
                self.ftp.cwd(self.directory)
            logger.info(f"Connected to FTP server: {self.host}")
            return self.ftp
        except Exception as e:
            logger.error(f"Error connecting to FTP: {e}")
            raise
    
    def disconnect(self):
        """Отключение от FTP сервера"""
        if self.ftp:
            try:
                self.ftp.quit()
            except:
                self.ftp.close()
            self.ftp = None
    
    def list_files(self, pattern: Optional[str] = None, recursive: bool = False) -> List[str]:
        """Список файлов в директории
        
        Args:
            pattern: Паттерн для поиска файлов
            recursive: Рекурсивный обход поддиректорий
        """
        if not self.ftp:
            self.connect()
        
        files = []
        try:
            if recursive:
                # Рекурсивный обход директорий
                files = self._list_files_recursive(self.directory, pattern)
            else:
                # Обычный список файлов в текущей директории
                file_list = self.ftp.nlst()
                if pattern:
                    import fnmatch
                    files = [f for f in file_list if fnmatch.fnmatch(f, pattern)]
                else:
                    files = file_list
        except Exception as e:
            logger.error(f"Error listing files: {e}")
            raise
        
        return files
    
    def _list_files_recursive(self, directory: str, pattern: Optional[str] = None) -> List[str]:
        """Рекурсивный обход директорий на FTP"""
        files = []
        try:
            # Сохраняем текущую директорию
            original_dir = self.ftp.pwd()
            
            # Переходим в указанную директорию
            self.ftp.cwd(directory)
            
            # Получаем список элементов
            items = self.ftp.nlst()
            
            for item in items:
                # Пропускаем служебные элементы
                if item in ['.', '..']:
                    continue
                
                try:
                    # Пробуем перейти в элемент (если это директория)
                    self.ftp.cwd(item)
                    # Если успешно - это директория, обходим рекурсивно
                    sub_files = self._list_files_recursive(item, pattern)
                    files.extend([f"{item}/{f}" for f in sub_files])
                    # Возвращаемся назад
                    self.ftp.cwd('..')
                except:
                    # Если не удалось перейти - это файл
                    if pattern:
                        import fnmatch
                        if fnmatch.fnmatch(item, pattern):
                            files.append(item)
                    else:
                        files.append(item)
            
            # Возвращаемся в исходную директорию
            self.ftp.cwd(original_dir)
            
        except Exception as e:
            logger.warning(f"Error in recursive listing for {directory}: {e}")
        
        return files
    
    def download_file(self, filename: str) -> bytes:
        """Скачивание файла с FTP"""
        if not self.ftp:
            self.connect()
        
        try:
            buffer = BytesIO()
            self.ftp.retrbinary(f'RETR {filename}', buffer.write)
            buffer.seek(0)
            return buffer.getvalue()
        except Exception as e:
            logger.error(f"Error downloading file {filename}: {e}")
            raise
    
    def parse_csv(self, content: bytes, encoding: str = 'utf-8') -> List[Dict[str, Any]]:
        """Парсинг CSV файла"""
        try:
            text = content.decode(encoding)
            reader = csv.DictReader(StringIO(text))
            return list(reader)
        except Exception as e:
            logger.error(f"Error parsing CSV: {e}")
            raise
    
    def parse_json(self, content: bytes, encoding: str = 'utf-8') -> Any:
        """Парсинг JSON файла"""
        try:
            text = content.decode(encoding)
            return json.loads(text)
        except Exception as e:
            logger.error(f"Error parsing JSON: {e}")
            raise
    
    def parse_xml(self, content: bytes, encoding: str = 'utf-8') -> ET.Element:
        """Парсинг XML файла"""
        try:
            text = content.decode(encoding)
            return ET.fromstring(text)
        except Exception as e:
            logger.error(f"Error parsing XML: {e}")
            raise
    
    def sync_store_visits_from_csv(
        self,
        filename: str,
        date_format: str = "%Y-%m-%d"
    ) -> List[Dict[str, Any]]:
        """Синхронизация посещений магазинов из CSV файла
        
        Ожидаемый формат CSV:
        store_id,date,visitor_count,sales_count,revenue
        или
        store_name,date,visitor_count,sales_count,revenue
        """
        content = self.download_file(filename)
        rows = self.parse_csv(content)
        
        visits = []
        for row in rows:
            try:
                # Парсим дату
                date_str = row.get('date') or row.get('Date') or row.get('DATE')
                if not date_str:
                    continue
                
                date = datetime.strptime(date_str, date_format)
                
                # Получаем данные
                visitor_count = int(row.get('visitor_count') or row.get('visitors') or 0)
                sales_count = int(row.get('sales_count') or row.get('sales') or 0)
                revenue = float(row.get('revenue') or row.get('revenue_rub') or 0.0)
                
                # Store ID или name
                store_id = row.get('store_id') or row.get('store_name')
                
                visits.append({
                    'store_id': store_id,
                    'date': date,
                    'visitor_count': visitor_count,
                    'sales_count': sales_count,
                    'revenue': revenue
                })
            except Exception as e:
                logger.warning(f"Error parsing row {row}: {e}")
                continue
        
        return visits
    
    def sync_store_sales_from_csv(
        self,
        filename: str,
        date_format: str = "%Y-%m-%d"
    ) -> List[Dict[str, Any]]:
        """Синхронизация продаж из CSV файла
        
        Ожидаемый формат CSV:
        store_id,date,product_id,quantity,price
        """
        content = self.download_file(filename)
        rows = self.parse_csv(content)
        
        sales = []
        for row in rows:
            try:
                date_str = row.get('date') or row.get('Date')
                if not date_str:
                    continue
                
                date = datetime.strptime(date_str, date_format)
                
                sales.append({
                    'store_id': row.get('store_id'),
                    'date': date,
                    'product_id': row.get('product_id'),
                    'quantity': int(row.get('quantity') or 0),
                    'price': float(row.get('price') or 0.0)
                })
            except Exception as e:
                logger.warning(f"Error parsing sales row {row}: {e}")
                continue
        
        return sales
    
    def detect_file_format(self, content: bytes) -> str:
        """
        Автоматическое определение формата файла
        
        Returns:
            'csv', 'json', 'xml', 'text', or 'unknown'
        """
        try:
            # Пытаемся декодировать в текст
            text = content.decode('utf-8')
            text_stripped = text.strip()
            
            # Проверяем JSON
            if text_stripped.startswith('{') or text_stripped.startswith('['):
                try:
                    json.loads(text)
                    return 'json'
                except:
                    pass
            
            # Проверяем XML
            if text_stripped.startswith('<?xml') or text_stripped.startswith('<'):
                try:
                    ET.fromstring(text)
                    return 'xml'
                except:
                    pass
            
            # Проверяем CSV (есть запятые или точки с запятой)
            if ',' in text or ';' in text:
                # Проверяем первую строку
                first_line = text.split('\n')[0]
                if first_line.count(',') > 0 or first_line.count(';') > 0:
                    return 'csv'
            
            # Если ничего не подошло, считаем текстовым файлом
            return 'text'
            
        except UnicodeDecodeError:
            return 'unknown'
    
    def parse_counter_file(
        self,
        content: bytes,
        format_hint: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Универсальный парсер текстовых файлов счетчиков
        
        Args:
            content: Содержимое файла
            format_hint: Подсказка о формате ('csv', 'json', 'xml', 'text')
        
        Returns:
            Список записей о посещениях магазинов
        """
        # Определяем формат, если не указан
        file_format = format_hint or self.detect_file_format(content)
        
        logger.info(f"Обнаружен формат файла: {file_format}")
        
        if file_format == 'csv':
            return self._parse_counter_csv(content)
        elif file_format == 'json':
            return self._parse_counter_json(content)
        elif file_format == 'xml':
            return self._parse_counter_xml(content)
        elif file_format == 'text':
            return self._parse_counter_text(content)
        else:
            raise ValueError(f"Неподдерживаемый формат файла: {file_format}")
    
    def _parse_counter_csv(self, content: bytes) -> List[Dict[str, Any]]:
        """Парсинг CSV файла счетчика"""
        rows = self.parse_csv(content)
        
        visits = []
        for row in rows:
            try:
                # Поддерживаем различные форматы заголовков
                date_str = (row.get('date') or row.get('Date') or 
                           row.get('DATE') or row.get('дата'))
                
                visitor_count = (row.get('visitor_count') or row.get('visitors') or 
                                row.get('посетители') or row.get('количество') or '0')
                
                store_id = (row.get('store_id') or row.get('store_name') or 
                           row.get('магазин') or row.get('id'))
                
                if not date_str or not store_id:
                    continue
                
                # Пытаемся распарсить дату в различных форматах
                date = self._parse_date(date_str)
                if not date:
                    continue
                
                visits.append({
                    'store_id': store_id,
                    'date': date,
                    'visitor_count': int(visitor_count) if str(visitor_count).isdigit() else 0,
                    'sales_count': int(row.get('sales_count') or row.get('sales') or 0),
                    'revenue': float(row.get('revenue') or row.get('выручка') or 0.0)
                })
            except Exception as e:
                logger.warning(f"Ошибка парсинга строки CSV: {e}")
                continue
        
        return visits
    
    def _parse_counter_json(self, content: bytes) -> List[Dict[str, Any]]:
        """Парсинг JSON файла счетчика"""
        data = self.parse_json(content)
        
        # Поддерживаем разные структуры JSON
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            # Ищем массив в ключах visits, data, records, etc.
            records = (data.get('visits') or data.get('data') or 
                      data.get('records') or data.get('items') or [])
        else:
            return []
        
        visits = []
        for record in records:
            try:
                date_str = record.get('date') or record.get('timestamp')
                if not date_str:
                    continue
                
                date = self._parse_date(date_str)
                if not date:
                    continue
                
                visits.append({
                    'store_id': record.get('store_id') or record.get('store_name'),
                    'date': date,
                    'visitor_count': int(record.get('visitor_count') or record.get('visitors') or 0),
                    'sales_count': int(record.get('sales_count') or record.get('sales') or 0),
                    'revenue': float(record.get('revenue') or 0.0)
                })
            except Exception as e:
                logger.warning(f"Ошибка парсинга записи JSON: {e}")
                continue
        
        return visits
    
    def _parse_counter_xml(self, content: bytes) -> List[Dict[str, Any]]:
        """Парсинг XML файла счетчика"""
        root = self.parse_xml(content)
        
        visits = []
        # Ищем записи в различных структурах XML
        for record in root.findall('.//record') or root.findall('.//visit') or root.findall('.//item'):
            try:
                date_str = record.findtext('date') or record.get('date')
                if not date_str:
                    continue
                
                date = self._parse_date(date_str)
                if not date:
                    continue
                
                visits.append({
                    'store_id': record.findtext('store_id') or record.get('store_id'),
                    'date': date,
                    'visitor_count': int(record.findtext('visitors') or record.findtext('visitor_count') or 0),
                    'sales_count': int(record.findtext('sales_count') or record.findtext('sales') or 0),
                    'revenue': float(record.findtext('revenue') or 0.0)
                })
            except Exception as e:
                logger.warning(f"Ошибка парсинга записи XML: {e}")
                continue
        
        return visits
    
    def _parse_counter_text(self, content: bytes) -> List[Dict[str, Any]]:
        """
        Парсинг произвольного текстового файла счетчика
        
        Поддерживает различные форматы:
        - Разделитель: пробел, табуляция, |, ;
        - Формат даты: различные варианты
        """
        text = content.decode('utf-8')
        lines = text.strip().split('\n')
        
        visits = []
        for line_num, line in enumerate(lines):
            # Пропускаем пустые строки и заголовки
            if not line.strip() or line_num == 0:
                continue
            
            try:
                # Пытаемся определить разделитель
                if '\t' in line:
                    parts = line.split('\t')
                elif '|' in line:
                    parts = line.split('|')
                elif ';' in line:
                    parts = line.split(';')
                else:
                    parts = line.split()
                
                # Убираем пробелы
                parts = [p.strip() for p in parts if p.strip()]
                
                if len(parts) < 2:
                    continue
                
                # Первый элемент обычно - дата или ID магазина
                # Пытаемся найти дату
                date = None
                store_id = None
                visitor_count = 0
                
                for i, part in enumerate(parts):
                    if not date:
                        parsed_date = self._parse_date(part)
                        if parsed_date:
                            date = parsed_date
                            continue
                    
                    if part.isdigit():
                        visitor_count = int(part)
                        break
                    elif not store_id:
                        store_id = part
                
                if date and store_id:
                    visits.append({
                        'store_id': store_id,
                        'date': date,
                        'visitor_count': visitor_count,
                        'sales_count': 0,
                        'revenue': 0.0
                    })
            except Exception as e:
                logger.warning(f"Ошибка парсинга строки текста (строка {line_num}): {e}")
                continue
        
        return visits
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """
        Универсальный парсинг даты в различных форматах
        
        Поддерживаемые форматы:
        - 2024-01-15
        - 15.01.2024
        - 15/01/2024
        - 2024-01-15T10:30:00
        - ISO формат с Z
        """
        date_formats = [
            "%Y-%m-%d",
            "%d.%m.%Y",
            "%d/%m/%Y",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S",
            "%d.%m.%Y %H:%M:%S",
        ]
        
        for fmt in date_formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        
        # Пытаемся распарсить ISO формат
        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except:
            pass
        
        return None
    
    def sync_store_visits_from_ftp(
        self,
        filename: Optional[str] = None,
        pattern: Optional[str] = None,
        format_hint: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Автоматическая синхронизация посещений магазинов с FTP
        
        Args:
            filename: Конкретный файл для загрузки
            pattern: Паттерн для поиска файлов (например, "visits_*.csv")
            format_hint: Подсказка о формате файла
        
        Returns:
            Список всех обработанных посещений
        """
        all_visits = []
        
        if filename:
            # Загружаем конкретный файл
            content = self.download_file(filename)
            visits = self.parse_counter_file(content, format_hint)
            all_visits.extend(visits)
        elif pattern:
            # Загружаем файлы по паттерну (с рекурсивным обходом)
            files = self.list_files(pattern, recursive=True)
            logger.info(f"Найдено {len(files)} файлов по паттерну {pattern}")
            
            for file in files:
                try:
                    content = self.download_file(file)
                    visits = self.parse_counter_file(content, format_hint)
                    all_visits.extend(visits)
                except Exception as e:
                    logger.error(f"Ошибка обработки файла {file}: {e}")
                    continue
        else:
            raise ValueError("Необходимо указать filename или pattern")
        
        logger.info(f"Всего обработано {len(all_visits)} записей о посещениях")
        return all_visits
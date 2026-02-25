"""
Тестовый скрипт для проверки скачивания медиаресурсов из 1С.
Использует синхронный requests с правильной авторизацией.
"""
import httpx
import xml.etree.ElementTree as ET
import os
import sys
import codecs
from base64 import b64encode

# Настройка кодировки для Windows
if sys.platform == "win32":
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

# Параметры подключения
ODATA_BASE_URL = os.getenv("ONEC_API_URL", "https://msk1.1cfresh.com/a/sbm/3322419/odata/standard.odata")
ODATA_USER = os.getenv("ONEC_API_USER", "odata.user")
ODATA_PASSWORD = os.getenv("ONEC_API_PASSWORD", "opexoboe")

# Создаем Basic Auth заголовок
auth_string = f"{ODATA_USER}:{ODATA_PASSWORD}"
auth_bytes = auth_string.encode('utf-8')
auth_b64 = b64encode(auth_bytes).decode('utf-8')
BASIC_AUTH = f"Basic {auth_b64}"

def get_file_metadata(file_ref_key, collection="Catalog_ХарактеристикиНоменклатурыПрисоединенныеФайлы"):
    """Получаем полные метаданные файла с ссылкой на медиаресурс"""
    # Проверяем кодировку collection
    print(f"   Collection (repr): {repr(collection)}")
    print(f"   Collection (bytes): {collection.encode('utf-8')}")
    
    # Используем тот же способ, что в test_find_file_collection.py (который работает)
    url = f"{ODATA_BASE_URL}/{collection}(guid'{file_ref_key}')"
    
    headers = {
        'Accept': 'application/atom+xml',
        'X-Requested-With': 'XMLHttpRequest',
        'Authorization': BASIC_AUTH
    }
    
    print(f"\n1. Запрос метаданных: GET {url}")
    
    with httpx.Client(verify=False, timeout=30.0) as client:
        response = client.get(url, headers=headers)
    
    # Проверяем реальный URL, который был отправлен
    if hasattr(response, 'request') and hasattr(response.request, 'url'):
        print(f"   Реальный URL запроса: {response.request.url}")
    
    print(f"   Статус: {response.status_code}")
    print(f"   Content-Type: {response.headers.get('Content-Type')}")
    
    if response.status_code == 200:
        return response.text  # XML с метаданными
    else:
        print(f"   Ошибка получения метаданных: {response.status_code}")
        print(f"   Ответ: {response.text[:500]}")
        return None

def extract_media_link_from_xml(xml_content, api_url):
    """Извлекает ссылку на бинарные данные файла из XML"""
    try:
        root = ET.fromstring(xml_content)
        
        # Получаем xml:base
        xml_base = root.get('{http://www.w3.org/XML/1998/namespace}base')
        if not xml_base:
            xml_base = api_url.rstrip('/')
        
        print(f"\n2. Найденные ссылки в XML:")
        
        # Ищем ссылку на медиаресурс ФайлХранилище
        media_url = None
        for link in root.findall('.//{http://www.w3.org/2005/Atom}link'):
            rel = link.get('rel')
            href = link.get('href')
            print(f"   - rel: {rel}")
            print(f"     href: {href}")
            
            if rel and 'mediaresource/ФайлХранилище' in rel:
                media_url = href
                print(f"   ✓ Найдена медиассылка: {media_url}")
        
        if media_url:
            # Проверяем, полный это URL или относительный
            if media_url.startswith('http'):
                return media_url
            elif media_url.startswith('/'):
                # Абсолютный путь от корня сервера
                if '/odata' in xml_base:
                    base_parts = xml_base.split('/odata')
                    base_url = base_parts[0] + '/odata'
                else:
                    base_url = xml_base.rstrip('/')
                return f"{base_url}{media_url}"
            else:
                # Относительный путь
                return f"{xml_base.rstrip('/')}/{media_url.lstrip('/')}"
        
        return None
    except Exception as e:
        print(f"Ошибка парсинга XML: {e}")
        import traceback
        traceback.print_exc()
        return None

def download_file_via_media_link(media_url, file_ref_key):
    """Скачивает файл по медиассылке"""
    try:
        headers = {
            'Accept': 'application/octet-stream, */*',
            'X-Requested-With': 'XMLHttpRequest',
            'Authorization': BASIC_AUTH
        }
        
        print(f"\n3. Скачивание по медиассылке: {media_url}")
        
        # Пробуем несколько вариантов
        urls_to_try = [media_url]
        if not media_url.endswith('/$value'):
            urls_to_try.append(f"{media_url}/$value")
        if media_url.endswith('/$value'):
            urls_to_try.insert(0, media_url[:-7])  # Без /$value
        
        with httpx.Client(verify=False, timeout=30.0) as client:
            for url in urls_to_try:
                print(f"   Пробуем URL: {url}")
                response = client.get(url, headers=headers)
            
            print(f"   Статус: {response.status_code}")
            print(f"   Content-Type: {response.headers.get('Content-Type')}")
            print(f"   Content-Length: {response.headers.get('Content-Length', 'неизвестно')}")
            print(f"   Размер данных: {len(response.content)} байт")
            
            if response.status_code == 200 and response.content and len(response.content) > 0:
                # Сохраняем для проверки
                filename = f'test_{file_ref_key}.bin'
                with open(filename, 'wb') as f:
                    f.write(response.content)
                print(f"   ✓ Файл сохранен как {filename}")
                
                # Проверяем, что это JPEG
                if response.content[:3] == b'\xff\xd8\xff':
                    print(f"   ✓ Это JPEG файл")
                else:
                    print(f"   ⚠ Не JPEG. Первые байты: {response.content[:20].hex()}")
                
                return response.content
            else:
                print(f"   ✗ Файл пустой или ошибка")
        
        return None
            
    except Exception as e:
        print(f"Исключение при скачивании: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_media_download(file_ref_key='586efdd6-bfd0-11f0-80bc-fa163e4cc04e', 
                       collection="Catalog_ХарактеристикиНоменклатурыПрисоединенныеФайлы"):
    """Тестируем скачивание конкретного файла"""
    print(f"\n{'='*70}")
    print(f"ТЕСТ СКАЧИВАНИЯ ФАЙЛА {file_ref_key}")
    print(f"{'='*70}")
    
    # 1. Получаем метаданные
    xml_metadata = get_file_metadata(file_ref_key, collection)
    if not xml_metadata:
        print("✗ Не удалось получить метаданные")
        return None
    
    # 2. Извлекаем медиассылку
    media_url = extract_media_link_from_xml(xml_metadata, ODATA_BASE_URL)
    if not media_url:
        print("✗ Медиассылка не найдена")
        return None
    
    # 3. Скачиваем файл
    file_data = download_file_via_media_link(media_url, file_ref_key)
    
    if file_data:
        print(f"\n✓ УСПЕХ: Файл скачан ({len(file_data)} байт)")
        return file_data
    else:
        print(f"\n✗ ОШИБКА: Не удалось скачать файл")
        return None

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Тест скачивания медиаресурсов из 1С')
    parser.add_argument('--file-ref', type=str, default='586efdd6-bfd0-11f0-80bc-fa163e4cc04e',
                       help='Ref_Key файла для тестирования')
    parser.add_argument('--collection', type=str, 
                       default='Catalog_ХарактеристикиНоменклатурыПрисоединенныеФайлы',
                       help='Коллекция файлов')
    
    args = parser.parse_args()
    
    # Исправляем кодировку collection, если она неправильная
    # Если collection содержит неправильно закодированные символы, используем правильную строку
    if args.collection and 'РќРѕРјРµРЅРєР»Р°С‚СѓСЂР°' in args.collection:
        # Это неправильно закодированная строка, используем правильную
        args.collection = 'Catalog_НоменклатураПрисоединенныеФайлы'
    elif args.collection and 'Характеристики' in args.collection and 'Р' in args.collection:
        # Это тоже может быть неправильно закодировано
        args.collection = 'Catalog_ХарактеристикиНоменклатурыПрисоединенныеФайлы'
    
    test_media_download(args.file_ref, args.collection)

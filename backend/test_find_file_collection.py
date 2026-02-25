"""
Скрипт для поиска файла по Ref_Key во всех возможных коллекциях.
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

# Список возможных коллекций файлов
FILE_COLLECTIONS = [
    "Catalog_НоменклатураПрисоединенныеФайлы",
    "Catalog_ХарактеристикиНоменклатурыПрисоединенныеФайлы",
]

def find_file_in_collection(file_ref_key, collection):
    """Проверяет, существует ли файл в указанной коллекции"""
    url = f"{ODATA_BASE_URL}/{collection}(guid'{file_ref_key}')"
    
    headers = {
        'Accept': 'application/atom+xml',
        'X-Requested-With': 'XMLHttpRequest',
        'Authorization': BASIC_AUTH
    }
    
    try:
        with httpx.Client(verify=False, timeout=30.0) as client:
            response = client.get(url, headers=headers)
            
            if response.status_code == 200:
                return True, response.text
            elif response.status_code == 404:
                return False, None
            else:
                return False, f"Ошибка {response.status_code}: {response.text[:200]}"
    except Exception as e:
        return False, str(e)

def find_file_collection(file_ref_key):
    """Ищет файл во всех возможных коллекциях"""
    print(f"\n{'='*70}")
    print(f"ПОИСК ФАЙЛА {file_ref_key}")
    print(f"{'='*70}\n")
    
    found = False
    for collection in FILE_COLLECTIONS:
        print(f"Проверяем коллекцию: {collection}")
        exists, result = find_file_in_collection(file_ref_key, collection)
        
        if exists:
            print(f"  ✓ Файл найден в коллекции: {collection}")
            print(f"  Метаданные получены ({len(result)} байт)")
            
            # Парсим XML и выводим основную информацию
            try:
                root = ET.fromstring(result)
                props = root.find(".//{http://schemas.microsoft.com/ado/2007/08/dataservices/metadata}properties")
                if props is not None:
                    print(f"\n  Основные свойства файла:")
                    for prop in props:
                        tag_name = prop.tag.split("}")[-1] if "}" in prop.tag else prop.tag
                        value = prop.text
                        if value and len(str(value)) < 100:
                            print(f"    - {tag_name}: {value}")
            except:
                pass
            
            found = True
            return collection, result
        else:
            if result:
                print(f"  ✗ Файл не найден: {result}")
            else:
                print(f"  ✗ Файл не найден (404)")
    
    if not found:
        print(f"\n✗ Файл не найден ни в одной из проверенных коллекций")
        return None, None
    
    return None, None

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Поиск файла по Ref_Key во всех коллекциях')
    parser.add_argument('--file-ref', type=str, default='ef7f875e-d088-11f0-8e4d-fa163e4cc04e',
                       help='Ref_Key файла для поиска')
    
    args = parser.parse_args()
    
    collection, metadata = find_file_collection(args.file_ref)
    
    if collection:
        print(f"\n✓ УСПЕХ: Файл найден в коллекции {collection}")
    else:
        print(f"\n✗ ФАЙЛ НЕ НАЙДЕН")

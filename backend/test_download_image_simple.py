"""
Простой тест загрузки изображения для товара 71136-S
Укажите base_url вручную или через переменную окружения
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import httpx
from urllib.parse import urljoin

# Загружаем .env
load_dotenv()

# Можно указать base_url здесь или через переменную окружения
BASE_URL = os.getenv("ONEC_XML_BASE_URL", "")
# Или извлечь из ONEC_XML_IMPORT_URL
if not BASE_URL:
    import_url = os.getenv("ONEC_XML_IMPORT_URL", "")
    if import_url:
        from urllib.parse import urlparse
        parsed = urlparse(import_url)
        # Убираем имя файла, оставляем базовый путь
        base_path = '/'.join(parsed.path.split('/')[:-1]) if '/' in parsed.path else ''
        BASE_URL = f"{parsed.scheme}://{parsed.netloc}{base_path}".rstrip('/')

# Если все еще нет, можно указать через аргумент командной строки
if not BASE_URL and len(sys.argv) > 1:
    BASE_URL = sys.argv[1]

# Если все еще нет, выводим инструкцию
if not BASE_URL:
    print("=" * 80)
    print("BASE_URL не установлен!")
    print("=" * 80)
    print()
    print("Использование:")
    print("  python test_download_image_simple.py <BASE_URL>")
    print()
    print("Или установите переменную окружения ONEC_XML_BASE_URL в .env файле")
    print()
    print("Пример:")
    print("  python test_download_image_simple.py http://your-server.com/path/to/xml")
    print()
    sys.exit(1)

print("=" * 80)
print("ТЕСТ ЗАГРУЗКИ ИЗОБРАЖЕНИЙ")
print("=" * 80)
print()
print(f"Base URL: {BASE_URL}")
print()

# Изображения из XML
image_urls = [
    "import_files/ec/ec2f3800bbf311f09138fa163e4cc04e_277b494ad0ed11f08e4dfa163e4cc04e.jpeg",
    "import_files/ec/ec2f3800bbf311f09138fa163e4cc04e_27b1896ad0ed11f08e4dfa163e4cc04e.jpeg"
]

# Путь для сохранения
storage_path = Path("static/product_images")
storage_path.mkdir(parents=True, exist_ok=True)

print(f"Сохранение в: {storage_path.absolute()}")
print()

downloaded = []

for idx, image_url in enumerate(image_urls, 1):
    print(f"{idx}. {image_url}")
    
    # Строим полный URL
    if not image_url.startswith('http'):
        full_url = urljoin(BASE_URL + '/', image_url.lstrip('/'))
    else:
        full_url = image_url
    
    print(f"   Полный URL: {full_url}")
    
    # Определяем имя файла
    if '/' in image_url:
        filename = image_url.split('/')[-1]
    else:
        filename = f"test_{idx}.jpg"
    
    local_path = storage_path / filename
    
    try:
        # Скачиваем
        print(f"   Загрузка...")
        with httpx.Client(timeout=30.0) as client:
            response = client.get(full_url)
            response.raise_for_status()
            
            # Сохраняем
            with open(local_path, 'wb') as f:
                f.write(response.content)
            
            file_size = local_path.stat().st_size
            print(f"   [OK] Сохранено: {local_path} ({file_size} байт)")
            downloaded.append(str(local_path))
            
    except httpx.HTTPStatusError as e:
        print(f"   [ERROR] HTTP ошибка: {e.response.status_code}")
    except httpx.RequestError as e:
        print(f"   [ERROR] Ошибка запроса: {e}")
    except Exception as e:
        print(f"   [ERROR] Ошибка: {e}")
    
    print()

print("=" * 80)
print(f"РЕЗУЛЬТАТ: загружено {len(downloaded)} из {len(image_urls)} изображений")
print("=" * 80)
if downloaded:
    print("Загруженные файлы:")
    for path in downloaded:
        print(f"  - {path}")

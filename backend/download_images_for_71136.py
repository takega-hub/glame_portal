"""
Скрипт для загрузки изображений товара 71136-S
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
import json
import httpx
from urllib.parse import urljoin, urlparse

# Добавляем путь к app
sys.path.insert(0, os.path.dirname(__file__))

# Загружаем .env
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")
ONEC_XML_IMPORT_URL = os.getenv("ONEC_XML_IMPORT_URL", "")
ONEC_XML_BASE_URL = os.getenv("ONEC_XML_BASE_URL", "")

if not DATABASE_URL:
    print("[ERROR] DATABASE_URL not found")
    sys.exit(1)

def get_base_url():
    """Получить base URL для изображений"""
    if ONEC_XML_BASE_URL:
        return ONEC_XML_BASE_URL.rstrip('/')
    
    if ONEC_XML_IMPORT_URL:
        parsed = urlparse(ONEC_XML_IMPORT_URL)
        # Убираем имя файла из пути, оставляем только базовый URL
        base_path = '/'.join(parsed.path.split('/')[:-1]) if '/' in parsed.path else ''
        return f"{parsed.scheme}://{parsed.netloc}{base_path}".rstrip('/')
    
    # Если ничего не найдено, просим пользователя указать
    print("[WARNING] ONEC_XML_BASE_URL и ONEC_XML_IMPORT_URL не установлены")
    print("Пожалуйста, установите ONEC_XML_BASE_URL в .env файле")
    return None

def download_image(image_url, base_url, local_path):
    """Скачать изображение"""
    try:
        # Если URL относительный, добавляем base_url
        if not image_url.startswith('http'):
            if base_url:
                full_url = urljoin(base_url + '/', image_url.lstrip('/'))
            else:
                print(f"[ERROR] Относительный URL без base_url: {image_url}")
                return None
        else:
            full_url = image_url
        
        print(f"  Загрузка: {full_url}")
        
        # Создаем директорию если нужно
        local_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Скачиваем изображение
        with httpx.Client(timeout=30.0) as client:
            response = client.get(full_url)
            response.raise_for_status()
            
            # Сохраняем файл
            with open(local_path, 'wb') as f:
                f.write(response.content)
            
            print(f"  Сохранено: {local_path}")
            return str(local_path)
    except Exception as e:
        print(f"  [ERROR] Ошибка загрузки {image_url}: {e}")
        return None

def download_product_images():
    """Загрузить изображения для товара"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        print("=" * 80)
        print("ЗАГРУЗКА ИЗОБРАЖЕНИЙ ДЛЯ ТОВАРА 71136-S")
        print("=" * 80)
        print()
        
        # Получаем base_url
        base_url = get_base_url()
        print(f"Base URL: {base_url}")
        print()
        
        # Ищем товар
        cursor.execute("""
            SELECT 
                id,
                name,
                article,
                images
            FROM products
            WHERE article = '71136-S';
        """)
        product = cursor.fetchone()
        
        if not product:
            print("Товар с артикулом 71136-S не найден")
            return
        
        print(f"Товар: {product['name']}")
        print(f"Артикул: {product['article']}")
        print()
        
        # Проверяем изображения
        if not product['images']:
            print("У товара нет изображений в поле images")
            return
        
        print(f"Найдено {len(product['images'])} изображений:")
        print()
        
        # Путь для сохранения
        storage_path = Path("static/product_images")
        storage_path.mkdir(parents=True, exist_ok=True)
        
        downloaded_paths = []
        
        for idx, image_url in enumerate(product['images'], 1):
            print(f"{idx}. {image_url}")
            
            # Определяем имя файла
            if '/' in image_url:
                filename = image_url.split('/')[-1]
            else:
                filename = f"product_{product['id']}_{idx}.jpg"
            
            local_path = storage_path / filename
            
            # Проверяем, существует ли файл
            if local_path.exists():
                print(f"  Файл уже существует: {local_path}")
                downloaded_paths.append(str(local_path))
            else:
                # Скачиваем изображение
                downloaded = download_image(image_url, base_url, local_path)
                if downloaded:
                    downloaded_paths.append(downloaded)
            print()
        
        # Обновляем товар в базе с полными путями
        if downloaded_paths:
            # Сохраняем относительные пути для веб-доступа
            relative_paths = [f"/static/product_images/{Path(p).name}" for p in downloaded_paths]
            cursor.execute("""
                UPDATE products
                SET images = %s
                WHERE id = %s;
            """, (json.dumps(relative_paths), product['id']))
            conn.commit()
            print(f"Обновлено {len(downloaded_paths)} изображений в базе данных")
            print("Пути в базе:")
            for path in relative_paths:
                print(f"  - {path}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"[ERROR] Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    download_product_images()

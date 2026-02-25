"""
Поиск изображений в 1С (номенклатура и характеристики).
Приоритет: изображения, привязанные к характеристикам.
"""
import argparse
import asyncio
import codecs
import os
import sys
from typing import Any, Dict, List, Optional

import httpx

if sys.platform == "win32":
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

API_URL = os.getenv("ONEC_API_URL", "https://msk1.1cfresh.com/a/sbm/3322419/odata/standard.odata").rstrip("/")
API_TOKEN = os.getenv("ONEC_API_TOKEN", "b2RhdGEudXNlcjpvcGV4b2JvZQ==")

DEFAULT_COLLECTIONS = [
    "/Catalog_ХарактеристикиНоменклатуры",
    "/Catalog_Номенклатура",
]

ATTACHED_FILES_COLLECTIONS = [
    "/Catalog_НоменклатураПрисоединенныеФайлы",
    "/Catalog_ХарактеристикиНоменклатурыПрисоединенныеФайлы",
]

ATTACHMENTS_HINTS = (
    "ПрисоединенныеФайлы",
    "Хранилище",
    "Файлы",
    "BinaryData",
    "Pictures",
    "Images",
    "Files",
)

IMAGE_KEYS = [
    "Изображение",
    "Фотография",
    "ФайлКартинки",
    "Picture",
    "Image",
    "images",
    "image",
    "image_urls",
]

ATTACHED_FILE_KEYS = [
    "Файл",
    "File",
    "ИмяФайла",
    "FileName",
    "Данные",
    "Data",
    "URL",
    "Url",
    "Ссылка",
    "Link",
    "Содержимое",
    "Content",
    "ДвоичныеДанные",
    "BinaryData",
]


def _build_headers() -> Dict[str, str]:
    headers = {"Accept": "application/json"}
    if API_TOKEN:
        if API_TOKEN.startswith("Basic "):
            headers["Authorization"] = API_TOKEN
        else:
            headers["Authorization"] = f"Basic {API_TOKEN}"
    return headers


async def _get_json(
    client: httpx.AsyncClient,
    url: str,
    params: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    response = await client.get(url, params=params)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


async def _get_service_collections(client: httpx.AsyncClient) -> List[str]:
    url = f"{API_URL}/"
    response = await client.get(url, headers={"Accept": "application/json"})
    response.raise_for_status()
    data = response.json()
    collections = []
    for item in data.get("value", []):
        name = item.get("name")
        if name:
            collections.append(f"/{name}")
    return collections


def _looks_like_image(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, dict):
        return any(k in value for k in ("url", "href", "link"))
    if isinstance(value, list):
        return any(_looks_like_image(v) for v in value)
    if isinstance(value, str):
        return value.startswith("http") or value.startswith("data:image") or len(value) > 200
    return False


def _extract_image_fields(item: Dict[str, Any]) -> Dict[str, Any]:
    images: Dict[str, Any] = {}
    # Стандартные поля изображений
    for key in IMAGE_KEYS:
        if key in item and _looks_like_image(item[key]):
            images[key] = item[key]
    # Поля присоединенных файлов
    for key in ATTACHED_FILE_KEYS:
        if key in item:
            value = item[key]
            if value is not None:
                images[key] = value
    # дополнительно ищем по ключам с подстроками "image/фото/картин/файл"
    for key, value in item.items():
        if value is None:
            continue
        key_lower = str(key).lower()
        if any(word in key_lower for word in ("image", "photo", "foto", "картин", "фото", "изображ", "файл", "file")):
            if _looks_like_image(value) or isinstance(value, (str, dict, list)):
                images[key] = value
    return images


async def search_images(
    client: httpx.AsyncClient,
    endpoint: str,
    search: Optional[str],
    top: int,
    page_size: int,
) -> List[Dict[str, Any]]:
    url = f"{API_URL}{endpoint}"
    results: List[Dict[str, Any]] = []
    skip = 0
    processed = 0
    is_attached_files = "ПрисоединенныеФайлы" in endpoint

    # Без $expand, работаем с ключами напрямую
    params = {"$top": page_size, "$skip": skip}

    while processed < top:
        data = await _get_json(client, url, params=params)
        if not data:
            break
        items = data.get("value", [])
        if not items:
            break
        for item in items:
            if search:
                search_lower = search.lower()
                # Прямые поля
                name = str(item.get("Description", "")).lower()
                article = str(item.get("Артикул", "")).lower()
                code = str(item.get("Code", "")).lower()
                
                # Для присоединенных файлов ищем по имени файла и во всех полях
                if is_attached_files:
                    # Специальные поля для имени файла
                    file_name = str(item.get("ИмяФайла", "")).lower()
                    file_name_en = str(item.get("FileName", "")).lower()
                    file_name_field = str(item.get("Имя", "")).lower()
                    description = str(item.get("Description", "")).lower()
                    
                    # Ищем в полях имени файла
                    found = (
                        search_lower in file_name or
                        search_lower in file_name_en or
                        search_lower in file_name_field or
                        search_lower in description
                    )
                    
                    # Если не найдено в специальных полях, ищем во всех полях
                    if not found:
                        item_str = str(item).lower()
                        found = search_lower in item_str
                    
                    if not found:
                        continue
                else:
                    # Обычная проверка для стандартных коллекций
                    if search_lower not in name and search_lower not in article and search_lower not in code:
                        continue

            images = _extract_image_fields(item)
            if images:
                results.append({
                    "item": item,
                    "images": images,
                })
        processed += len(items)
        skip += len(items)
        params["$skip"] = skip
        if len(items) < page_size:
            break
    return results


async def main() -> None:
    parser = argparse.ArgumentParser(description="Поиск изображений в 1С")
    parser.add_argument("--search", default="", help="Поиск по названию/артикулу/коду")
    parser.add_argument("--top", type=int, default=1000, help="Сколько записей грузить")
    parser.add_argument("--page-size", type=int, default=200, help="Размер страницы")
    parser.add_argument("--all", action="store_true", help="Искать по всем коллекциям из service document")
    parser.add_argument("--only-attachments", action="store_true", help="Искать только в коллекциях с присоединенными файлами")
    args = parser.parse_args()

    headers = _build_headers()
    search = args.search.strip() or None

    async with httpx.AsyncClient(timeout=120.0, headers=headers, verify=True) as client:
        if args.all:
            try:
                collections = await _get_service_collections(client)
            except Exception as e:
                print(f"[ERROR] Не удалось получить список коллекций: {e}")
                collections = DEFAULT_COLLECTIONS + ATTACHED_FILES_COLLECTIONS
        else:
            # По умолчанию ищем в стандартных коллекциях и коллекциях присоединенных файлов
            collections = DEFAULT_COLLECTIONS + ATTACHED_FILES_COLLECTIONS

        if args.only_attachments:
            collections = [
                coll
                for coll in collections
                if any(hint.lower() in coll.lower() for hint in ATTACHMENTS_HINTS)
            ]
            # Если ничего не найдено, используем известные коллекции присоединенных файлов
            if not collections:
                collections = ATTACHED_FILES_COLLECTIONS

        for endpoint in collections:
            try:
                results = await search_images(
                    client,
                    endpoint,
                    search,
                    args.top,
                    args.page_size,
                )
            except Exception as e:
                print(f"[ERROR] {endpoint}: {e}")
                continue

            if not results:
                print(f"[EMPTY] {endpoint}")
                continue

            print("=" * 100)
            print(f"Изображения найдены в {endpoint}: {len(results)}")
            print("=" * 100)
            for entry in results[:10]:
                item = entry["item"]
                images = entry["images"]
                
                # Информация о товаре/характеристике
                owner_info = ""
                file_name_info = ""
                if "ПрисоединенныеФайлы" in endpoint:
                    # Имя файла
                    file_name = item.get("ИмяФайла") or item.get("FileName") or item.get("Имя")
                    if file_name:
                        file_name_info = f"Имя файла: {file_name}"
                    
                    owner = item.get("Owner", {})
                    if isinstance(owner, dict):
                        owner_info = f"Owner: Code={owner.get('Code')} Артикул={owner.get('Артикул')} Description={owner.get('Description')}"
                    else:
                        owner_info = f"Owner={owner}"
                    nom = item.get("Номенклатура", {})
                    if isinstance(nom, dict):
                        owner_info += f" | Номенклатура: Code={nom.get('Code')} Артикул={nom.get('Артикул')}"
                
                print(
                    f"- Ref_Key={item.get('Ref_Key')} "
                    f"Code={item.get('Code')} "
                    f"Артикул={item.get('Артикул')} "
                    f"Description={item.get('Description')}"
                )
                if file_name_info:
                    print(f"  {file_name_info}")
                if owner_info:
                    print(f"  {owner_info}")
                for key, value in images.items():
                    preview = value
                    if isinstance(value, list):
                        preview = value[0] if value else None
                    if preview:
                        preview_str = str(preview)
                        # Для длинных строк (base64) показываем только начало
                        if len(preview_str) > 200:
                            preview_str = preview_str[:200] + "..."
                        print(f"  * {key}: {preview_str}")


if __name__ == "__main__":
    asyncio.run(main())

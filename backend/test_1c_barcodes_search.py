"""
Поиск штрихкодов в 1С по артикулу/наименованию/штрихкоду.
Может искать по всем коллекциям из service document.
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

DEFAULT_ENDPOINTS = [
    "/InformationRegister_ШтрихкодыНоменклатуры",
    "/Catalog_ШтрихкодыНоменклатуры",
    "/InformationRegister_Штрихкоды",
    "/Catalog_Штрихкоды",
]

FALLBACK_COLLECTIONS = [
    "/Catalog_Номенклатура",
    "/Catalog_ХарактеристикиНоменклатуры",
]

BARCODE_HINTS = (
    "Штрихкод",
    "Barcode",
    "Штрихкоды",
    "Barcodes",
    "EAN",
    "GTIN",
    "UPC",
)


def _build_headers() -> Dict[str, str]:
    headers = {"Accept": "application/json"}
    if API_TOKEN:
        if API_TOKEN.startswith("Basic "):
            headers["Authorization"] = API_TOKEN
        else:
            headers["Authorization"] = f"Basic {API_TOKEN}"
    return headers


async def _get_service_collections(client: httpx.AsyncClient) -> List[str]:
    """Получить список всех коллекций из service document."""
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


def _value_contains(value: Any, needle: str) -> bool:
    if value is None:
        return False
    text = str(value).lower()
    return needle.lower() in text


def _extract_hits(item: Dict[str, Any], needle: str) -> List[str]:
    hits: List[str] = []
    for key, value in item.items():
        if isinstance(value, (str, int, float)) and _value_contains(value, needle):
            hits.append(f"{key}={value}")
    return hits


async def search_endpoint(
    client: httpx.AsyncClient,
    endpoint: str,
    barcode: str,
    article: str,
    name: str,
    top: int,
) -> List[Dict[str, Any]]:
    url = f"{API_URL}{endpoint}"
    data = await _get_json(client, url, params={"$top": top})
    if not data:
        print(f"[404] {endpoint}")
        return []

    items = data.get("value", [])
    results: List[Dict[str, Any]] = []
    for item in items:
        if barcode and _value_contains(item, barcode):
            results.append({"reason": "barcode", "item": item, "hits": _extract_hits(item, barcode)})
            continue
        if article and _value_contains(item, article):
            results.append({"reason": "article", "item": item, "hits": _extract_hits(item, article)})
            continue
        if name and _value_contains(item, name):
            results.append({"reason": "name", "item": item, "hits": _extract_hits(item, name)})
            continue
    return results


async def scan_collection(
    client: httpx.AsyncClient,
    endpoint: str,
    needle: str,
    top: int,
    page_size: int,
) -> List[Dict[str, Any]]:
    """Сканировать коллекцию и искать needle во всех полях."""
    url = f"{API_URL}{endpoint}"
    results: List[Dict[str, Any]] = []
    skip = 0
    processed = 0

    while processed < top:
        data = await _get_json(client, url, params={"$top": page_size, "$skip": skip})
        if not data:
            break
        items = data.get("value", [])
        if not items:
            break
        for item in items:
            hits = _extract_hits(item, needle)
            if hits:
                results.append({"item": item, "hits": hits})
        processed += len(items)
        skip += len(items)
        if len(items) < page_size:
            break
    return results


async def main() -> None:
    parser = argparse.ArgumentParser(description="Поиск штрихкодов в 1С")
    parser.add_argument("--barcode", default="", help="Штрихкод для поиска")
    parser.add_argument("--article", default="", help="Артикул (характеристики)")
    parser.add_argument("--name", default="", help="Наименование")
    parser.add_argument("--top", type=int, default=5000, help="Сколько записей грузить")
    parser.add_argument("--page-size", type=int, default=200, help="Размер страницы при поиске")
    parser.add_argument("--all", action="store_true", help="Искать по всем коллекциям из service document")
    parser.add_argument("--only-barcodes", action="store_true", help="Искать только в коллекциях со штрихкодами")
    args = parser.parse_args()

    needle = args.barcode or args.article or args.name
    if not needle:
        print("Укажите хотя бы один параметр: --barcode, --article или --name")
        return

    headers = _build_headers()

    async with httpx.AsyncClient(timeout=120.0, headers=headers, verify=True) as client:
        # Определяем список коллекций для поиска
        if args.all:
            try:
                collections = await _get_service_collections(client)
                print(f"[INFO] Найдено {len(collections)} коллекций в service document")
            except Exception as e:
                print(f"[ERROR] Не удалось получить список коллекций: {e}")
                collections = DEFAULT_ENDPOINTS + FALLBACK_COLLECTIONS
        else:
            collections = DEFAULT_ENDPOINTS

        # Фильтруем по штрихкодам, если нужно
        if args.only_barcodes:
            collections = [
                coll
                for coll in collections
                if any(hint.lower() in coll.lower() for hint in BARCODE_HINTS)
            ]
            print(f"[INFO] Отфильтровано до {len(collections)} коллекций со штрихкодами")

        # Сначала пробуем стандартные регистры штрихкодов
        if not args.all:
            for endpoint in DEFAULT_ENDPOINTS:
                try:
                    results = await search_endpoint(
                        client,
                        endpoint,
                        args.barcode,
                        args.article,
                        args.name,
                        args.top,
                    )
                except Exception as e:
                    print(f"[ERROR] {endpoint}: {e}")
                    continue

                if not results:
                    print(f"[EMPTY] {endpoint}")
                    continue

                print("=" * 100)
                print(f"Совпадения в {endpoint}: {len(results)}")
                print("=" * 100)
                for match in results[:20]:
                    item = match["item"]
                    print(f"- reason={match['reason']} hits={match['hits']}")
                    print(
                        f"  Ref_Key={item.get('Ref_Key')} "
                        f"Owner={item.get('Owner')} "
                        f"Номенклатура={item.get('Номенклатура')} "
                        f"Характеристика={item.get('Характеристика')} "
                        f"Штрихкод={item.get('Штрихкод') or item.get('Barcode')}"
                    )

        # Сканируем все выбранные коллекции
        for endpoint in collections:
            if endpoint in DEFAULT_ENDPOINTS and not args.all:
                continue  # Уже проверили выше
            try:
                results = await scan_collection(
                    client,
                    endpoint,
                    needle,
                    args.top,
                    args.page_size,
                )
            except Exception as e:
                print(f"[ERROR] scan {endpoint}: {e}")
                continue

            if not results:
                print(f"[EMPTY] scan {endpoint}")
                continue

            print("=" * 100)
            print(f"Совпадения (скан) в {endpoint}: {len(results)}")
            print("=" * 100)
            for match in results[:20]:
                item = match["item"]
                print(f"- hits={match['hits']}")
                print(
                    f"  Ref_Key={item.get('Ref_Key')} "
                    f"Code={item.get('Code')} "
                    f"Артикул={item.get('Артикул')} "
                    f"Description={item.get('Description')}"
                )
                # Показываем найденные поля со штрихкодом
                for hit in match['hits']:
                    if any(hint.lower() in hit.lower() for hint in BARCODE_HINTS):
                        print(f"  *** ШТРИХКОД НАЙДЕН: {hit}")


if __name__ == "__main__":
    asyncio.run(main())

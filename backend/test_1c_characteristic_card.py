"""
Тестовый скрипт для получения карточки характеристики из 1С
и вывода свойств/значений как на скриншоте.
"""
import argparse
import asyncio
import codecs
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import httpx


if sys.platform == "win32":
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")


API_URL = os.getenv("ONEC_API_URL", "https://msk1.1cfresh.com/a/sbm/3322419/odata/standard.odata").rstrip("/")
API_TOKEN = os.getenv("ONEC_API_TOKEN", "b2RhdGEudXNlcjpvcGV4b2JvZQ==")


def _build_headers() -> Dict[str, str]:
    headers = {"Accept": "application/json"}
    if API_TOKEN:
        if API_TOKEN.startswith("Basic "):
            headers["Authorization"] = API_TOKEN
        else:
            headers["Authorization"] = f"Basic {API_TOKEN}"
    return headers


def _get_first(item: Dict[str, Any], keys: List[str]) -> Optional[Any]:
    for key in keys:
        if key in item and item[key] not in (None, ""):
            return item[key]
    return None


async def _get_json(client: httpx.AsyncClient, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    response = await client.get(url, params=params)
    response.raise_for_status()
    return response.json()


def _collect_string_matches(value: Any, needle: str, path: str = "") -> List[Tuple[str, str]]:
    matches: List[Tuple[str, str]] = []
    if isinstance(value, dict):
        for key, val in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            matches.extend(_collect_string_matches(val, needle, child_path))
    elif isinstance(value, list):
        for idx, val in enumerate(value):
            child_path = f"{path}[{idx}]"
            matches.extend(_collect_string_matches(val, needle, child_path))
    else:
        if isinstance(value, (str, int, float)):
            text = str(value)
            if needle.lower() in text.lower():
                matches.append((path, text))
    return matches


async def _scan_collection(
    client: httpx.AsyncClient,
    collection_name: str,
    needle: str,
    max_items: int,
    page_size: int,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    skip = 0
    processed = 0
    while processed < max_items:
        url = f"{API_URL}/{collection_name}"
        batch = await _get_json(client, url, params={"$top": page_size, "$skip": skip})
        items = batch.get("value", [])
        if not items:
            break

        for item in items:
            matches = _collect_string_matches(item, needle)
            if matches:
                results.append({
                    "Ref_Key": item.get("Ref_Key"),
                    "Code": item.get("Code"),
                    "Description": item.get("Description"),
                    "Артикул": item.get("Артикул"),
                    "matches": matches,
                })
        processed += len(items)
        skip += len(items)
    return results


async def _find_characteristic(
    client: httpx.AsyncClient,
    search: Optional[str],
    ref_key: Optional[str],
    top: int,
) -> Dict[str, Any]:
    nom_url = f"{API_URL}/Catalog_Номенклатура"
    data = await _get_json(client, nom_url, params={"$top": top})
    items = data.get("value", [])

    characteristics = [
        item for item in items
        if item.get("Parent_Key")
        and item.get("Parent_Key") != "00000000-0000-0000-0000-000000000000"
    ]

    if ref_key:
        exact = next((item for item in characteristics if item.get("Ref_Key") == ref_key), None)
        if exact:
            return exact

    if search:
        search_lower = search.lower()
        # 1) Сначала ищем точное совпадение по артикулу
        exact_article = next(
            (item for item in characteristics if str(item.get("Артикул", "")).lower() == search_lower),
            None,
        )
        if exact_article:
            return exact_article

        # 2) Затем ищем точное совпадение по коду/Ref_Key
        exact_code = next(
            (item for item in characteristics if str(item.get("Code", "")).lower() == search_lower),
            None,
        )
        if exact_code:
            return exact_code

        exact_ref = next(
            (item for item in characteristics if str(item.get("Ref_Key", "")).lower() == search_lower),
            None,
        )
        if exact_ref:
            return exact_ref

        # 3) И только потом — частичное совпадение
        for item in characteristics:
            name = str(item.get("Description", "")).lower()
            article = str(item.get("Артикул", "")).lower()
            code = str(item.get("Code", "")).lower()
            if search_lower in name or search_lower in article or search_lower in code:
                return item

    if characteristics:
        return characteristics[0]
    return {}


async def _load_characteristic_record(
    client: httpx.AsyncClient,
    owner_ref_key: str,
    top: int,
) -> Optional[Dict[str, Any]]:
    url = f"{API_URL}/Catalog_ХарактеристикиНоменклатуры"
    data = await _get_json(client, url, params={"$top": top})
    records = data.get("value", [])
    return next((item for item in records if item.get("Owner") == owner_ref_key), None)


async def _resolve_properties(
    client: httpx.AsyncClient,
    dop_rekv: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    if not dop_rekv:
        return []

    value_keys = {rek.get("Значение") for rek in dop_rekv if rek.get("Значение")}
    prop_keys = {rek.get("Свойство_Key") for rek in dop_rekv if rek.get("Свойство_Key")}

    values_map: Dict[str, str] = {}
    prop_name_map: Dict[str, str] = {}

    if value_keys:
        values_url = f"{API_URL}/Catalog_ЗначенияСвойствОбъектов"
        values_data = await _get_json(client, values_url, params={"$top": 2000})
        for value in values_data.get("value", []):
            ref_key = value.get("Ref_Key")
            if ref_key in value_keys:
                values_map[ref_key] = value.get("Description", "") or value.get("Наименование", "")

    results: List[Dict[str, str]] = []
    for rek in dop_rekv:
        prop_key = rek.get("Свойство_Key")
        value_key = rek.get("Значение")
        if not prop_key or not value_key:
            continue

        value_name = values_map.get(value_key, "")
        if not value_name:
            try:
                val_url = f"{API_URL}/Catalog_ЗначенияСвойствОбъектов(guid'{value_key}')"
                val_data = await _get_json(client, val_url)
                value_name = val_data.get("Description", "") or val_data.get("Наименование", "")
                if value_name:
                    values_map[value_key] = value_name
            except Exception:
                pass

        prop_name = prop_name_map.get(prop_key, "")
        if not prop_name:
            try:
                owner_url = f"{API_URL}/Catalog_ЗначенияСвойствОбъектов(guid'{value_key}')/Owner"
                owner_data = await _get_json(client, owner_url)
                prop_name = owner_data.get("Description") or owner_data.get("Заголовок") or owner_data.get("Наименование", "")
                if prop_name:
                    prop_name_map[prop_key] = prop_name
            except Exception:
                pass

        if not prop_name:
            prop_name = prop_key
        if not value_name:
            value_name = value_key

        if value_name == "00000000-0000-0000-0000-000000000000":
            continue

        results.append({"property": str(prop_name), "value": str(value_name)})

    return results


async def main() -> None:
    parser = argparse.ArgumentParser(description="Получение карточки характеристики из 1С")
    parser.add_argument("--search", default="", help="Поиск по названию/артикулу/коду")
    parser.add_argument("--ref-key", default="", help="Точный Ref_Key характеристики")
    parser.add_argument("--top", type=int, default=1000, help="Сколько записей грузить из 1С")
    parser.add_argument("--scan-limit", type=int, default=2000, help="Лимит сканирования коллекций")
    parser.add_argument("--page-size", type=int, default=200, help="Размер страницы при сканировании")
    parser.add_argument("--save", default="characteristic_card_example.json", help="Файл для сохранения результата")
    args = parser.parse_args()

    headers = _build_headers()

    async with httpx.AsyncClient(timeout=120.0, headers=headers, verify=True) as client:
        characteristic = await _find_characteristic(
            client,
            search=args.search or None,
            ref_key=args.ref_key or None,
            top=args.top,
        )

        if not characteristic:
            print("Характеристика не найдена.")
            return

        ref_key = characteristic.get("Ref_Key")
        name = _get_first(characteristic, ["Description", "Наименование", "НаименованиеПолное"])
        name_print = _get_first(characteristic, ["НаименованиеДляПечати", "DescriptionForPrint"])
        article = characteristic.get("Артикул")

        print("=" * 100)
        print("КАРТОЧКА ХАРАКТЕРИСТИКИ (из Catalog_Номенклатура)")
        print("=" * 100)
        print(f"Ref_Key: {ref_key}")
        print(f"Наименование: {name}")
        print(f"Наименование для печати: {name_print}")
        print(f"Артикул: {article}")
        print()

        char_record = None
        dop_rekv = []
        if ref_key:
            char_record = await _load_characteristic_record(client, ref_key, args.top)
            if char_record:
                dop_rekv = char_record.get("ДополнительныеРеквизиты", [])

        properties = await _resolve_properties(client, dop_rekv)

        print("=" * 100)
        print("СВОЙСТВА И ЗНАЧЕНИЯ")
        print("=" * 100)
        if properties:
            for row in properties:
                print(f"- {row['property']}: {row['value']}")
        else:
            print("Свойства не найдены или не заполнены.")

        payload = {
            "characteristic": characteristic,
            "characteristic_record": char_record,
            "properties": properties,
        }
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

        print()
        print(f"Результат сохранен в {args.save}")

        # Если искали конкретный артикул и не совпало — ищем где он хранится
        if args.search and str(article or "").lower() != args.search.lower():
            print()
            print("=" * 100)
            print("ПОИСК АРТИКУЛА В ДРУГИХ ПОЛЯХ")
            print("=" * 100)
            print(f"Ищем '{args.search}' в Catalog_Номенклатура и Catalog_ХарактеристикиНоменклатуры")

            nom_hits = await _scan_collection(
                client,
                "Catalog_Номенклатура",
                args.search,
                args.scan_limit,
                args.page_size,
            )
            char_hits = await _scan_collection(
                client,
                "Catalog_ХарактеристикиНоменклатуры",
                args.search,
                args.scan_limit,
                args.page_size,
            )

            total_hits = len(nom_hits) + len(char_hits)
            print(f"Совпадений найдено: {total_hits}")

            if nom_hits:
                print("\nСовпадения в Catalog_Номенклатура:")
                for hit in nom_hits[:10]:
                    print(f"- Ref_Key: {hit.get('Ref_Key')} Артикул: {hit.get('Артикул')} Code: {hit.get('Code')}")
                    for path, value in hit.get("matches", [])[:5]:
                        print(f"  * {path}: {value}")

            if char_hits:
                print("\nСовпадения в Catalog_ХарактеристикиНоменклатуры:")
                for hit in char_hits[:10]:
                    print(f"- Ref_Key: {hit.get('Ref_Key')} Артикул: {hit.get('Артикул')} Code: {hit.get('Code')}")
                    for path, value in hit.get("matches", [])[:5]:
                        print(f"  * {path}: {value}")



if __name__ == "__main__":
    asyncio.run(main())

import re
from typing import Optional


_CYRILLIC_LOOKALIKES = str.maketrans({
    "А": "A",
    "В": "B",
    "Е": "E",
    "К": "K",
    "М": "M",
    "Н": "H",
    "О": "O",
    "Р": "P",
    "С": "C",
    "Т": "T",
    "Х": "X",
    "а": "a",
    "е": "e",
    "о": "o",
    "р": "p",
    "с": "c",
    "у": "y",
    "х": "x",
})

_KNOWN_BRANDS = [
    "Claudio Canzian",
    "Raganella Princess",
    "Prism of Elegance",
    "PRISM OF ELEGANCE",
    "Eva Rites",
    "UNOde50",
    "Kalliope",
    "Bicolor",
    "GEOMETRY",
    "Swarovski",
    "Momenti",
    "Antura",
    "AGafi",
    "CRYSTAL",
    "MAGNA",
    "PEARL",
    "GLAME",
]

_NON_BRAND_VALUES = {
    "сопутствующие материалы",
    "подарочная упаковка",
    "sale",
    "прочее",
}
_NON_CATEGORY_VALUES = {
    "sale",
}

_CATEGORY_PATTERNS = [
    (r"\bкольц[оа]\b", "Кольца"),
    (r"\bсерьг[аи]\b|\bсерьги\b", "Серьги"),
    (r"\bклипс[аы]\b", "Серьги"),
    (r"\bбраслет\w*\b", "Браслеты"),
    (r"\bгривн[аы]\b", "Браслеты"),
    (r"\bчокер\w*\b", "Чокеры"),
    (r"\bброш[ьи]\b", "Броши"),
    (r"\bкулон\w*\b", "Кулоны"),
    (r"\bожерель[ея]\b", "Кулоны"),
    (r"\bлариат\w*\b", "Кулоны"),
    (r"\bподвеск[аи]\b", "Подвески"),
    (r"\bколье\b", "Колье"),
    (r"\bцеп[ьи]\b", "Цепи"),
    (r"\bсотуар\w*\b", "Сотуары"),
    (r"\bкафф\w*\b", "Каффы"),
    (r"\bбодичейн\w*\b", "Прочее"),
    (r"\bчас[ыов]\b", "Прочее"),
    (r"\bмешочек\w*\b", "Сопутствующие материалы"),
    (r"\bпакет\w*\b", "Сопутствующие материалы"),
    (r"\bупаковк[аи]\b", "Сопутствующие материалы"),
    (r"\bкоробк[аи]\b", "Сопутствующие материалы"),
    (r"\bсалфетк[аи]\b", "Сопутствующие материалы"),
    (r"\bзаколк[аи]\b", "Прочее"),
]


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", str(value).replace("\u00a0", " ")).strip()
    return cleaned or None


def _norm(value: Optional[str]) -> str:
    return (_clean(value) or "").translate(_CYRILLIC_LOOKALIKES).casefold()


def _norm_ru(value: Optional[str]) -> str:
    return (_clean(value) or "").casefold()


def derive_purchase_brand(
    product_name: Optional[str],
    catalog_brand: Optional[str] = None,
    catalog_category: Optional[str] = None,
) -> Optional[str]:
    source = _norm(product_name)
    for brand in _KNOWN_BRANDS:
        if _norm(brand) in source:
            return brand

    for candidate in (catalog_brand, catalog_category):
        candidate_clean = _clean(candidate)
        if not candidate_clean:
            continue
        candidate_norm = _norm(candidate_clean)
        if candidate_clean.casefold() in _NON_BRAND_VALUES or candidate_norm in _NON_BRAND_VALUES:
            continue
        for brand in _KNOWN_BRANDS:
            if candidate_norm == _norm(brand):
                return brand
        if not derive_purchase_category(candidate_clean):
            return candidate_clean

    return None


def derive_purchase_category(
    product_name: Optional[str],
    catalog_category: Optional[str] = None,
) -> Optional[str]:
    name_norm = _norm_ru(product_name)
    for pattern, category in _CATEGORY_PATTERNS:
        if re.search(pattern, name_norm):
            return category

    catalog_clean = _clean(catalog_category)
    if (
        catalog_clean
        and catalog_clean.casefold() not in _NON_CATEGORY_VALUES
        and _norm(catalog_clean) not in _NON_CATEGORY_VALUES
        and not derive_purchase_brand(None, catalog_category=catalog_clean)
    ):
        return catalog_clean
    return None

# GLAME mobile app — следующий раздел после Home: Catalog + Product

Дата: 2026-05-30
Режим: дизайн/ТЗ перед реализацией, без live API/admin write-операций.

## Проверенный контекст

- Backend health: `/health` → `200 OK`, status `healthy`.
- Каталог API: `/api/products/paged?skip=0&limit=5&has_images=true` → `200 OK`, total `482`.
- Разделы каталога: `/api/catalog-sections/` → `200 OK`.
- В проекте много существующих незакоммиченных изменений; перед кодом нельзя делать широкие refactor/cleanup без отдельной ветки и согласования.
- В контейнере Hermes команда `flutter` недоступна, поэтому локальная проверка `flutter analyze` из этого окружения сейчас невозможна.

## Дизайн-источники

- `docs/mobile_app_ui_spec.md`, разделы `2.2 Каталог`, `3.1 Экран товара`.
- `docs/design/GLAME_updated_document_system_v2_FULL/02_GLAME_NAVIGATION_SAFE_AREA_SYSTEM.md`.
- `docs/design/GLAME_updated_document_system_v2_FULL/12_GLAME_UI_TOKENS_AND_COMPONENTS.md`.
- `docs/design/GLAME_updated_document_system_v2_FULL/14_GLAME_CURSOR_EXECUTION_RULES.md`.
- `docs/design/GLAME_updated_document_system_v2_FULL/15_GLAME_QA_ACCEPTANCE_CHECKLIST.md`.

## Текущая реализация

Файлы:

- `mobile/glame_app/lib/src/features/catalog/catalog_screen.dart`
- `mobile/glame_app/lib/src/features/catalog/catalog_controller.dart`
- `mobile/glame_app/lib/src/features/catalog/catalog_filter_sheet.dart`
- `mobile/glame_app/lib/src/features/product/product_screen.dart`
- `mobile/glame_app/lib/src/features/home/home_api.dart`

Что уже хорошо:

- Каталог грузит `/products/paged` с `has_images=true`, значит товары без фото уже не должны попадать в основной customer catalog.
- `inStockOnly` выключен по умолчанию: можно показывать out-of-stock товары с фото.
- Product detail уже отключает покупку при `stock <= 0` и показывает CTA `Сообщить о поступлении`.
- Product detail уже показывает статус `В наличии` / `Нет в наличии`.
- Карточка товара уже содержит фото, brand badge, wishlist, название и цену.
- Фильтр-sheet существует: цена, материал, покрытие, тип замка, сортировка.

Главные расхождения с design workflow:

1. `catalog_screen.dart` строит категории напрямую из `/catalog-sections/`, поэтому в верхнюю категорийную строку попадают бренды/линии (`AGafi`, `Antura`, `Eva Rites`, `NEW`, `SALE`) рядом с продуктовыми категориями.
2. По design rule верхний ряд должен быть коротким: `Все | Серьги | Кольца | Колье | Браслеты | Каффы`; `NEW`/`SALE` — коллекции/status, бренды — фильтр или Brands page.
3. Header/search/actions требуют визуального упорядочивания: страница должна читаться как curated GLAME catalog, а не raw inventory strip.
4. В данных обнаружен label typo: `WRINKLES OG TIME` вместо `WRINKLES OF TIME`; нужно нормализовать отображение на клиенте или в API, не меняя 1C raw value без отдельного решения.
5. Catalog UI использует местами 16/20 px horizontal padding, а дизайн-система ориентирует mobile pages на 28 px и строгую сетку 390–430W.

## Рекомендуемое решение v1

### Catalog hierarchy

```text
[Top nav]
Каталог украшений
Каталог
────────────────
[Поиск по названию или артикулу] [Фильтры] [2/1]
[В наличии] [Цена] [Бренд] [Материал]
Все | Серьги | Кольца | Колье | Браслеты | Каффы
482 изделия                         Сначала новые
[2-column product grid]
```

### Категории

- Показывать в top category row только customer-safe product categories:
  - `Все`
  - `Серьги`
  - `Кольца`
  - `Колье`
  - `Браслеты`
  - `Каффы`
- `NEW`, `SALE` вынести в отдельные collection chips или filter/action row.
- Бренды/линии (`AGafi`, `Antura`, `Eva Rites`, `Bicolor`, `Geometry`, etc.) оставить в фильтрах/Brands route.
- Скрывать `Подарочная упаковка`, `Подарочные сертификаты`, `Прочее`, `Сопутствующие материалы` из основного product-category row до отдельного UX-решения.

### Product card

- Сохранять фото + brand badge + wishlist + name + price.
- Добавить явный availability label для `stock <= 0`: `Нет в наличии` / `Сообщить о поступлении`.
- Не давать buy/add-to-cart с карточки для out-of-stock.
- Нормализовать display brand typo: `WRINKLES OG TIME` → `WRINKLES OF TIME`.

### Product detail

- Текущий unavailable CTA оставить как baseline.
- Следующий UX-слой: после нажатия `Сообщить о поступлении` открывать contact/auth capture вместо только SnackBar. Это требует отдельного endpoint/CRM-сценария, поэтому не делать без утверждения.

## Acceptance checklist для первой итерации Catalog/Product

- [ ] В catalog category row нет брендов/линий и `NEW`/`SALE` как категорий.
- [ ] Товары без фото не отображаются в customer catalog.
- [ ] Out-of-stock товары с фото отображаются, но имеют явный unavailable state.
- [ ] Product detail при `stock <= 0` не показывает покупку и имеет CTA `Сообщить о поступлении`.
- [ ] Product cards не выглядят как просто галерея: name/price/status видны до перехода.
- [ ] Radius = 0, border = 1 px, без warm accents / rounded marketplace cards.
- [ ] Safe area / bottom nav не перекрывают контент на 390W и 430W.
- [ ] `WRINKLES OG TIME` не показывается клиенту как typo.

## Выполнено в минимальной итерации после approval

1. В `catalog_screen.dart` `_buildCategoryLabels` переведен на whitelist customer-safe product categories.
2. Добавлен helper display normalization для brand/line labels: `WRINKLES OG TIME` → `WRINKLES OF TIME`.
3. Добавлен availability label в `_ProductCardDarkrain`: `В наличии` / `Нет в наличии`.

## Что осталось для следующей итерации

1. Добавить кнопку/чип `Фильтры`, если текущий filter sheet не вызывается из UI.
2. Проверить/подключить count/sort label в header.
3. Спроектировать реальный capture-flow для `Сообщить о поступлении` вместо SnackBar.

## Блокеры/риски

- В текущем Docker окружении нет Flutter CLI, поэтому финальный `flutter analyze` нужен либо на host, либо в образе с Flutter.
- В репозитории много чужих dirty changes; любые правки должны быть минимальными и точечными.
- Endpoint для реальной подписки `Сообщить о поступлении` пока не подтвержден; не внедрять CRM write-flow без API-дизайна и approval.

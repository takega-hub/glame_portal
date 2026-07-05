# GLAME Stitch Output Audit — 2026-06-16

Проверяемый архив:

`/root/.codex/attachments/ef529e9b-db15-48a4-bd5a-6b3e59d07768/stitch_glame_jewelry_app_design.zip`

Распаковка для проверки:

`tmp/stitch_review/stitch_glame_jewelry_app_design/`

## Итог

Статус: **не готово к реализации как полный дизайн-пакет**.

Stitch сделал полезный visual direction и несколько отдельных экранов, но результат не закрывает полное ТЗ приложения. Это набор HTML-макетов/moodboard, а не complete app design system.

Ключевые проблемы:

- часть заявленных экранов отсутствует физически: есть только `screen.png` размером 28 байт с текстом `<FIFE Image failed to fetch>`;
- нет валидной полной Главной с 6 блоками;
- нет валидной страницы каталога как основной витрины;
- нет валидной карточки товара;
- нет полноценного checkout flow 1-4, есть только cart/success/confirmation фрагменты;
- нет профиля и регистрации как валидных HTML-экранов;
- недостаточно состояний: guest/auth, empty/error/loading;
- используются внешние generated `lh3.googleusercontent.com/aida-public/...` изображения вместо approved/local assets;
- логотип GLAME часто набран текстом, а не использован как original asset;
- bottom nav во многих экранах не соответствует утвержденной структуре GLAME;
- есть screen registry с `{{DATA:SCREEN:...}}`, но соответствующих файлов в архиве нет.

## Что есть валидно

В архиве есть 18 экранов с `code.html` и нормальным `screen.png`:

| Папка | Экран | Оценка |
|---|---|---|
| `welcome_glame` | Onboarding | частично годится, но image generated/external |
| `glame_2` | Looks feed | визуально сильный, но nav не наш и внешние картинки |
| `glame_3` | Brands list | покрывает список брендов, но hero generated |
| `geometry_glame` | Brand detail Geometry | частично годится |
| `glame_4` | AI photo upload | годится как направление |
| `glame_5` | My Style | частично годится |
| `glame_6` | Space Simferopol | есть структура, но external/generated images |
| `glame_7` | Space Yalta | есть структура, но external/generated images |
| `glame_8` | Stylist chat | полезно как направление |
| `glame_9` | Cart | есть cart state |
| `glame_10` | Look builder | полезно как направление |
| `glame_11` | Empty favorites | есть empty state |
| `glame_12` | Drawer | частично годится |
| `glame_13` | AI result | полезно как направление |
| `glame_14` | Checkout success | есть success state |
| `glame_16` | Selection method | годится как структура |
| `glame_17` | OTP confirmation | есть auth fragment |
| `glame_18` | Orders history | частично годится |
| `glame_19` | Login | есть login |
| `glame_21` | Cart / catalog-like fragment | неясное назначение, не заменяет каталог |
| `glame_23` | Filters | useful, но brand list неверный |

## Битые или неполные элементы

Эти папки имеют `screen.png` размером 28 байт и не имеют `code.html`:

- `glame_1`
- `glame_15`
- `glame_20`
- `glame_22`
- `minimalist_band_glame`
- `urban_cold_glame`

Содержимое битых PNG:

```text
<FIFE Image failed to fetch>
```

Вероятно именно здесь должны были быть ключевые screens, заявленные в `glame_design_archive_v1.0.md`:

- Главная;
- Каталог;
- Карточка товара;
- Регистрация;
- Профиль;
- Детальный образ;
- Оформление заказа.

## Coverage Matrix

| Обязательный экран/состояние из ТЗ | Статус в Stitch | Что нужно |
|---|---|---|
| Onboarding | Есть частично | заменить generated image на approved/local asset или нейтральный layout |
| Home 6 blocks | Нет валидного экрана | сделать полностью |
| Home hero slide 01 | Нет | сделать с live top/bottom nav |
| Home block 2 New in GLAME | Нет | сделать editorial-commerce block |
| Home block 3 AI photo | Только отдельная page | добавить именно home block |
| Home block 4 Brands | Есть отдельная brands page, нет home block | добавить home block |
| Home block 5 Spaces | Нет home block | добавить home block |
| Home block 6 How choose/buy | Нет home block | добавить home block с фото магазина/pattern logic |
| Drawer | Есть частично | привести пункты к нашей навигации |
| Catalog | Нет валидного экрана | сделать основной catalog grid/search/tabs |
| Filters | Есть | убрать `GLAME Atelier`, привести бренды/категории |
| Product detail | Нет валидного экрана | сделать полностью |
| Brands list | Есть | заменить generated hero и проверить signatures |
| Brand detail | Есть Geometry only | добавить reusable template и states |
| Spaces list | Нет | сделать список пространств |
| Space Yalta | Есть | заменить на реальные assets |
| Space Simferopol | Есть | заменить на реальные assets |
| Looks feed | Есть | привести nav и filters |
| Look detail | Нет валидного экрана | сделать |
| Look builder | Есть | доработать связи с wishlist/AI/stylist/cart |
| My Style authorized | Есть частично | добавить saved products/looks/recent/stylist CTA |
| Wishlist empty | Есть | привести текст/CTA |
| Wishlist filled | Нет отдельного state | сделать |
| AI photo upload | Есть | заменить assets/привести copy |
| AI photo guide sheet | Нет | сделать |
| AI auth gate | Нет | сделать |
| Photo review | Нет | сделать |
| Photo analysis | Нет | сделать |
| AI result | Есть | добавить explanation blocks и product routes |
| Stylist bottom sheet open | Нет | сделать |
| Stylist bottom sheet closed | Нет | сделать |
| Stylist chat authorized | Есть | доработать attachments/products/looks/stores |
| Stylist chat guest auth gate | Нет | сделать |
| Cart filled | Есть | привести товарные данные |
| Cart empty | Частично внутри `glame_9` | сделать отдельное state |
| Checkout steps 1-4 | Нет | сделать полный flow |
| Checkout success | Есть | доработать summary |
| Profile guest | Нет | сделать |
| Profile authorized | Нет валидного экрана | сделать |
| Orders/history | Есть | связать с profile |
| Login | Есть | добавить register/SMS routes |
| Register | Нет валидного экрана | сделать |
| OTP | Есть | проверить route/copy |
| Change password | Нет | сделать |
| Error/loading templates | Нет | сделать component states |

## Design Issues

### 1. Логотип

Во многих HTML файлах logo сделан как текст:

```html
GLAME
```

Нужно использовать original logo assets:

- `glame_logo silver.png`
- `glame_logo graph.png`
- `glame_logo black.png`
- `glame_sign.png`

### 2. Images

Много внешних ссылок:

```text
https://lh3.googleusercontent.com/aida-public/...
```

Это нельзя считать production-ready. Для реальных пространств и brand identity нужны approved assets из нашего пакета.

### 3. Bottom nav

В ряде экранов nav выглядит как:

```text
Каталог / Образы / GLAME / Избранное / Профиль
```

Утвержденная структура:

```text
G / Украшения / Мой стиль / Подбор / Профиль
```

### 4. Витрина

Нет нормального каталога и карточки товара. Это блокирует реализацию витринной части.

### 5. Checkout

Нет последовательного flow:

```text
Корзина → Адрес/доставка → Оплата → Подтверждение → Success
```

### 6. Auth gates

Не хватает обязательных gates:

- AI photo upload guest gate;
- stylist chat guest gate;
- profile guest;
- checkout guest;
- wishlist/save guest.

## Что можно сохранить из Stitch

Использовать как direction:

- dark graphite UI language;
- brands list rhythm;
- selection method panels;
- stylist chat visual mood;
- look builder concept;
- My Style direction;
- spaces detail page composition.

Не использовать как final:

- generated/external images;
- text-based logo;
- incomplete screen registry;
- missing home/catalog/product/checkout/profile screens.

## Вывод

Нужно отправить Stitch на вторую итерацию с обязательным требованием:

1. предоставить физически валидный `code.html + screen.png` для каждого обязательного экрана;
2. собрать Home полностью;
3. закрыть catalog/product/checkout/profile/auth;
4. заменить external/generated images на approved/local assets или четкие placeholders;
5. приложить coverage matrix с соответствием каждому пункту ТЗ.

# GLAME Stitch V2 Output Audit — 2026-06-16

Проверяемый архив:

`/root/.codex/attachments/47f501de-001d-4bd5-ada2-78ebfaed978b/stitch_glame_jewelry_app_design (1).zip`

Распаковка:

`tmp/stitch_review_v2/stitch_glame_jewelry_app_design/`

## Итог

Статус: **лучше первой версии по отдельным экранам, но всё ещё не готово как полный дизайн-пакет приложения**.

Вторая версия содержит только 4 HTML-экрана:

| Папка | Экран | Статус |
|---|---|---|
| `glame_v2_1` | Главная / Home с блоками | есть, но неполная и с placeholder block 4 |
| `glame_v2_2` | Профиль | есть |
| `glame_v2_3` | Каталог | есть |
| `minimalist_band_glame_v2` | Карточка товара | есть, но с критичной ошибкой изображения |

Также есть `architectural_minimalist/DESIGN.md`.

## Улучшения относительно первой версии

- Нет 28-byte `<FIFE Image failed to fetch>` PNG.
- Появились физически валидные HTML+PNG для Home, Catalog, Product, Profile.
- Home пытается собрать несколько блоков в одну страницу.
- Catalog стал ближе к нужной витринной структуре.
- Profile стал отдельным экраном.

## Критичные проблемы

### 1. Это не полный пакет приложения

Во втором архиве всего 4 экрана, тогда как минимальный список из ТЗ — 50+ экранов/состояний.

Не хватает:

- Onboarding;
- Brands list/detail;
- Spaces list/detail;
- Looks feed;
- Look detail;
- Look builder;
- My Style / Wishlist states;
- AI photo guide/auth/review/analysis/result;
- Stylist bottom sheets/chat/auth gate;
- Cart filled/empty;
- Checkout steps 1-4 and success;
- Login/Register/OTP/Change password;
- Orders/history;
- Empty/loading/error states.

### 2. Home неполная

`glame_v2_1` включает:

- Hero;
- New in GLAME;
- AI photo block;
- Spaces block;
- How choose/buy block.

Но:

- Block 4 `Собрано GLAME` — placeholder `[Содержимое блока Собрано GLAME]`;
- нет полноценной brand grid / curated brands logic;
- block 6 не доведен до согласованной сервисной зоны;
- фон/лого/space images всё еще внешние;
- top/bottom nav используют внешние logo/G URLs.

### 3. Product detail содержит неверное изображение

`minimalist_band_glame_v2` показывает автомобиль в hero image.

Это blocker: product screen нельзя использовать как reference для jewelry product detail, пока hero/image gallery не заменены на jewelry assets/placeholders.

### 4. External/generated images

Во всех HTML используются ссылки:

```text
https://lh3.googleusercontent.com/aida-public/...
```

Это нельзя считать production-ready. Нужно заменить на approved/local assets или нейтральные placeholders.

### 5. Logo/G assets не локальные

Логотип и G-знак подключены через external URLs. В production/reference package нужно использовать наши оригинальные файлы:

- `glame_logo silver.png`
- `glame_logo graph.png`
- `glame_logo black.png`
- `glame_sign.png`

### 6. Bottom nav всё еще расходится

Утвержденный nav:

```text
G / Украшения / Мой стиль / Подбор / Профиль
```

В v2 местами:

```text
Главная / Каталог / Корзина / Избранное / Профиль
```

или другие вариации. Нужно унифицировать.

### 7. Design system still mentions Hanken Grotesk

`DESIGN.md` всё еще использует Hanken Grotesk as proxy. Для production handoff нужно явно подключить Clinica Pro Regular asset или пометить fallback только как технический временный fallback.

## Coverage Matrix V2

| Экран/состояние | V2 статус |
|---|---|
| Home full | частично |
| Home block 1 | частично |
| Home block 2 | частично |
| Home block 3 | частично |
| Home block 4 | нет, placeholder |
| Home block 5 | частично |
| Home block 6 | частично |
| Catalog | есть |
| Product detail | есть, но blocker из-за car image |
| Profile authorized | есть |
| Onboarding | нет |
| Drawer | нет |
| Brands | нет |
| Brand detail | нет |
| Spaces | нет |
| Looks | нет |
| Look detail | нет |
| Look builder | нет |
| Wishlist/My style states | нет |
| AI full flow | нет |
| Stylist full flow | нет |
| Cart | нет |
| Checkout full flow | нет |
| Auth screens | нет |
| Empty/loading/error states | нет |

## Что можно взять из V2

- Общий dark graphite визуальный тон.
- Catalog grid direction.
- Profile layout direction.
- Идею Home как длинной страницы с блоками.

## Что нельзя брать без правок

- Product detail из-за автомобиля.
- Home block 4 placeholder.
- Любые external logo/G/image URLs как production references.
- Bottom nav variations.
- Неполный coverage как готовность к реализации.

## Рекомендация

Нужно не заменять первый архив вторым, а объединить полезные v1 + v2 направления и отправить Stitch/дизайнеру на третью итерацию:

1. собрать полный пакет всех экранов из `STITCH_FIX_REQUEST.md`;
2. использовать v2 Home/Catalog/Profile как направление;
3. полностью переделать product detail image/content;
4. заменить external assets на approved/local;
5. закрыть missing flows: AI, stylist, looks, cart, checkout, auth, brands, spaces.

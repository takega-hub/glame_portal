# GLAME Stitch — обязательное задание на доработку

Использовать вместе с исходным полным ТЗ:

`docs/design/stitch_app_design_package/GLAME_APP_STITCH_FULL_DESIGN_TZ.md`

## 1. Проблема текущей выдачи

Текущий архив `stitch_glame_jewelry_app_design.zip` неполный:

- часть screen-файлов битые: `<FIFE Image failed to fetch>`;
- нет физически валидных экранов Главной, Каталога, Карточки товара, Профиля, Регистрации, полного checkout;
- многие изображения внешние/generated (`lh3.googleusercontent.com/aida-public/...`);
- логотип GLAME часто набран текстом, а не оригинальным asset;
- bottom nav местами не соответствует GLAME;
- не покрыты обязательные auth gates и states.

Нужно пересобрать пакет как complete app design, а не moodboard.

## 2. Формат результата

Для каждого экрана предоставить:

```text
screen_id/
  code.html
  screen.png
```

Дополнительно:

```text
SCREEN_COVERAGE_MATRIX.md
COMPONENT_LIBRARY.md
FLOW_MAP.md
IMPLEMENTATION_NOTES.md
```

Все `screen.png` должны быть валидными изображениями, не 28-byte fetch error.

## 3. Обязательные экраны

Сделать минимум эти экраны:

1. Onboarding
2. Home full page with 6 blocks
3. Home hero slide 01
4. Home block 2 New in GLAME
5. Home block 3 AI photo selection
6. Home block 4 Collected GLAME
7. Home block 5 Spaces
8. Home block 6 How choose/buy
9. Drawer
10. Catalog
11. Catalog filters
12. Catalog empty
13. Product detail
14. Product detail loading/error
15. Brands list
16. Brand detail
17. Spaces list
18. Space detail Yalta
19. Space detail Simferopol
20. Looks feed editorial
21. Looks feed grid
22. Look detail
23. Look builder
24. My Style authorized
25. My Style guest auth gate
26. Wishlist filled
27. Wishlist empty
28. Selection method
29. AI photo upload
30. AI photo guide bottom sheet
31. AI auth gate
32. Photo review
33. Photo analysis
34. Photo selection result
35. Stylist bottom sheet open
36. Stylist bottom sheet closed
37. Stylist chat authorized
38. Stylist chat guest auth gate
39. Cart filled
40. Cart empty
41. Checkout step 1 Cart
42. Checkout step 2 Delivery/address
43. Checkout step 3 Payment
44. Checkout step 4 Confirmation
45. Checkout success
46. Profile guest
47. Profile authorized
48. Orders/history
49. Loyalty/profile progress
50. Login
51. Register
52. OTP
53. Change password
54. Generic loading template
55. Generic empty template
56. Generic error template

## 4. Navigation rules

Bottom nav must be:

```text
G / Украшения / Мой стиль / Подбор / Профиль
```

Do not use:

```text
Каталог / Образы / GLAME / Избранное / Профиль
```

Top bar:

- Hero: transparent overlay, centered original logo, right menu/search/cart.
- Internal: centered original logo asset, back left, context actions right.

## 5. Brand rules

Use only original logo/G assets. Do not write GLAME as live text where logo is required.

Use:

- `glame_logo silver.png`
- `glame_logo graph.png`
- `glame_logo black.png`
- `glame_sign.png`

Do not use generated logo or font approximation.

## 6. Image rules

Do not rely on `lh3.googleusercontent.com/aida-public/...` as final production references.

Use approved assets from:

- `docs/design/stitch_app_design_package/assets/brand`
- `docs/design/stitch_app_design_package/assets/home`
- `docs/design/stitch_app_design_package/assets/spaces`
- `docs/design/stitch_app_design_package/assets/looks`

For unavailable product photos, use clearly marked placeholders, but real spaces must use approved real space photos.

## 7. Component rules

All components:

- radius 0;
- border 1 px;
- cold graphite/steel palette;
- no warm beige/gold UI;
- no glow;
- no marketplace shadows;
- no pill buttons.

Component library must include:

- top bar transparent;
- top bar internal;
- bottom nav;
- drawer;
- hero slide;
- primary/secondary CTA;
- action panel;
- service tile;
- product card;
- product mini card;
- drop card;
- brand row/card;
- space card;
- look card;
- look builder selected item;
- auth gate;
- bottom sheet;
- chat bubble;
- chat attachment product;
- filters;
- segmented control;
- checkout stepper;
- empty/loading/error states.

## 8. Functional links to preserve

Use these route/action mappings:

```text
Hero primary → /selection
Hero secondary → /catalog
Block 2 all new → /home?tab=6 or /catalog?category=NEW
Block 3 upload → /selection/ai-photo
Block 4 brands → /brands
Block 5 Yalta → /spaces/yalta
Block 5 Simferopol → /spaces/simferopol
Block 6 самостоятельный → /catalog
Block 6 stylist → showStylistContactSheet(source: home_block_6)
Block 6 AI → /selection/ai-photo
Brand row → /brand/:id
Product card → /product/:id
Look card → /look/:id
Cart checkout → /checkout
Guest protected action → auth gate with next route preserved
```

## 9. Required customer journeys

Show these flows in `FLOW_MAP.md`:

1. Home → Catalog → Product → Cart → Checkout → Success
2. Home → AI photo → Auth gate → Upload → Review → Analysis → Result → Product
3. Home/Product/Wishlist → Stylist sheet → Chat → Product/Look/Space
4. Home → Brands → Brand detail → Catalog filtered → Product
5. Home → Spaces → Space detail → Map/Stylist/Catalog city
6. Looks → Look detail → Save/Add products/Replace with stylist
7. Guest → Login/Register/OTP → return to original action
8. Profile → Orders → Loyalty → Saved looks/products

## 10. Acceptance criteria

The revised Stitch package is acceptable only if:

- every required screen has real `code.html` and real `screen.png`;
- no screen PNG contains `<FIFE Image failed to fetch>`;
- Home has all 6 blocks;
- catalog/product/checkout/profile are complete;
- auth gates are present;
- original logos/G are used as assets;
- real space photos are not generated;
- bottom nav matches GLAME;
- screen coverage matrix explicitly maps every required screen to a file.

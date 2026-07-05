# GLAME Stitch Design Package — asset manifest

Этот пакет предназначен для передачи агенту Stitch вместе с файлом:

`GLAME_APP_STITCH_FULL_DESIGN_TZ.md`

## 1. Главные документы

- `GLAME_APP_STITCH_FULL_DESIGN_TZ.md` — основное полное ТЗ по приложению.
- `ASSET_MANIFEST_FOR_STITCH.md` — этот манифест.

## 2. Brand assets

Папка: `assets/brand/`

Использовать только эти логотипы и G-знак:

- `glame_logo black.png`
- `glame_logo graph.png`
- `glame_logo gray.png`
- `glame_logo silver.png`
- `glame_sign.png`
- `glame_sign_black background.png`
- `glame_sign_graph background.png`
- `glame_sign_gray background.png`
- `glame_sign_silver background.png`

Шрифты:

- `clinica_pro_regular.otf`
- `clinica_pro_regular.ttf`

Правило: логотип и G-знак не перерисовывать и не генерировать.

## 3. Home references

Папка: `assets/home/`

### Block 1 / Hero

- `GLAME_home_block1_button_layout_430x932.png`
- `GLAME_home_block1_button_layout_1290x2796.png`
- `GLAME_home_block1_button_layout_specs.json`

Использовать для safe-area, CTA coordinates и hero button layout.

### Block 2 / New in GLAME

- `block_2.png`

Использовать как visual reference editorial-commerce block.

### Block 3 / AI photo selection

- `home_block_3_photo_selection.png`
- `photo_upload_intro.png`
- `photo_guide_example.png`
- `block3_authorized.png`
- `block3_not_authorized.png`
- `block3_photo_selection.png`
- `block3_photo_checking.png`
- `block3_photo_ok.png`
- `block3_photo_guide_button.png`

Использовать для AI photo flow и auth states.

### Block 4 / Brands

- `glame_home_block4_design.png`
- `glame_home_block4_background_underlay.png`
- `glame_home_block4_visual_image_no_text.png`
- `home_block_4_collected_glame.png`

Использовать для curated brands block.

### Block 5 / Spaces

- `glame_home_block5_design.png`
- `glame_home_block5_background_underlay.png`
- `glame_block5_yalta_card_photo.png`
- `glame_block5_simferopol_card_photo.png`

Использовать для Home spaces block.

### Block 6 / How to choose and buy

- `glame_home_block6_agreed_design.png`
- `glame_home_block6_background_underlay.png`
- `glame_home_block6_current_app_background.png`
- `glame_service_how_to_buy_page_design.png`
- `glame_service_how_to_buy_background_underlay.png`
- `glame_service_how_to_buy_photo_accent_no_text.png`

Важно: в текущей версии команда хочет сохранить атмосферу фото магазина как фон для home block 6. Pattern design использовать как reference для графитовой геометрии, воздуха, линий и сервисной сетки, но не обязательно заменять фото.

## 4. Spaces references

Папка: `assets/spaces/`

Ялта:

- `glame_space_yalta_hero_photo.png`
- `glame_space_yalta_gallery_main.png`
- `glame_space_yalta_gallery_01.png`
- `glame_space_yalta_gallery_02.png`
- `glame_space_yalta_page_design.png`

Симферополь:

- `glame_space_simferopol_hero_photo.png`
- `glame_space_simferopol_gallery_main.png`
- `glame_space_simferopol_gallery_01.png`
- `glame_space_simferopol_gallery_02.png`
- `glame_space_simferopol_page_design.png`

Правило: не смешивать фото городов.

## 5. Looks references

Папка: `assets/looks/`

- `looks_reference.png`

Использовать как общий референс для раздела образов, look-feed и сборки образа. При сборке полного дизайна доработать структуру по ТЗ, не ограничиваться одним референсом.

## 6. Reference docs

Папка: `reference_docs/`

Внутри лежат ключевые дизайн-доки:

- identity and anti-distortion;
- navigation and safe area;
- hero slides;
- home blocks 2-6;
- live stylist;
- AI selection;
- spaces;
- UI tokens;
- photo selection flow;
- block-specific logic docs.

Stitch должен использовать их как source of truth при конфликте с визуальной догадкой.

## 7. Current code references

Папка: `current_code_refs/`

Копии ключевых Flutter-файлов нужны только для понимания структуры экранов, routes и текущего функционала. Stitch не обязан повторять верстку 1:1, но должен сохранить функциональные связи.

## 8. Priority order

Если есть конфликт:

1. `GLAME_APP_STITCH_FULL_DESIGN_TZ.md`
2. Identity / navigation / UI tokens docs
3. Current approved block-specific logic docs
4. Approved visual references
5. Current Flutter code behavior
6. Stitch design judgement

## 9. Что нельзя делать с assets

- Не генерировать новые логотипы.
- Не дорисовывать реальные пространства.
- Не встраивать навигацию в фоновые изображения.
- Не использовать warm/gold marketplace style.
- Не сокращать названия брендов.

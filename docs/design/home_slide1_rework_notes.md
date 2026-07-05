# GLAME Home — Block 1 / Slide 1 rework notes

Дата: 2026-05-28

## Найденный текущий слайд

Live API endpoint:

```text
/api/app/home-slides?block_key=style_inside
```

Первый активный слайд:

- id: `15ed0b86-e2fa-4bc8-9557-501e987dc677`
- sort_order: `1`
- image_url: `/static/app_admin_media/home_slide/8e71909014554ed390fb178da0e68a14.png`
- файл в репозитории: `backend/static/app_admin_media/home_slide/8e71909014554ed390fb178da0e68a14.png`
- title сейчас: `СТИЛЬ ВНУТРИ`
- subtitle сейчас: `Украшения, которые собирают образ под ваш стиль, задачу и повод.\nОнлайн — по всей России.`
- primary CTA сейчас: `Собрать свой стиль` → `/selection`
- secondary CTA сейчас: `Смотреть новинки` → home block 2

## Что не совпадает с правилами блока 1

По документу `03_GLAME_HOME_HERO_SLIDES_LOGIC.md` первый слайд должен вести в две главные ветки:

1. персональный подбор;
2. каталог украшений.

Текущий secondary CTA ведет в новинки, а не в каталог. Это сужает первый экран до блока новинок и не соответствует роли первого hero как входа в GLAME.

Также title лучше хранить не капсом, а нормальным регистром: `Стиль внутри`. Визуальный стиль должен задаваться Flutter-типографикой, а не текстом в uppercase.

## Доработанная версия

Title:

```text
Стиль внутри
```

Subtitle:

```text
Украшения, которые собирают образ
под ваш стиль, повод и настроение.
Онлайн — по всей России.
```

Primary CTA:

```text
Собрать свой стиль
```

Action:

```json
{
  "type": "selection",
  "legacyLink": "/selection"
}
```

Secondary CTA:

```text
Смотреть украшения
```

Action:

```json
{
  "type": "catalog",
  "payload": {},
  "legacyLink": "/catalog"
}
```

## Layout rules

- Фон/фото отдельно: без текста, кнопок, top bar, bottom nav, logo, slide indicator.
- Top bar, bottom nav, CTA, текст и индикатор — live Flutter UI.
- Canvas preview: 430 × 932 px.
- Content margin: 28 px.
- Primary CTA: x=28, y=602, width=300, height=58.
- Secondary CTA: x=28, y=676, width=300, height=58.
- Slide indicator: x=28, y=768.
- Bottom nav reserve: y=802–932.

## Preview output

Generated local preview for discussion:

```text
/home/glameAI/.hermes/media_cache/glame_home_review/glame_home_slide1_reworked_preview.png
```

Current background copied for reference:

```text
/home/glameAI/.hermes/media_cache/glame_home_review/glame_home_slide1_current_background.png
```

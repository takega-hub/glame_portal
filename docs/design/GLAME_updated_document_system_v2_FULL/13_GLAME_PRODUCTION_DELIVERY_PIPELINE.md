# 13. GLAME — Production Delivery Pipeline

## Rule

После согласования экрана/слайда выдавать production-package, а не только картинку.

Файлы создаются только после визуального согласования.

---

## Package structure

1. Product Logic Document
2. Approved Visual
3. Constructor Assets
4. Design System Spec
5. Responsive Rules
6. Safe Area Specification
7. Component Specification
8. State Map
9. Flutter/Dart Package
10. Cursor Execution Prompt
11. QA Checklist
12. Interaction Map

---

## Required formats

```text
.md
.dart
.png
.zip
```

При необходимости:
- `.json` для tokens;
- `.svg` для approved vector assets;
- `.webp` для optimized images.

---

## Naming

```text
glame_[section]_[block]_[type]_[version].ext
```

Example:

```text
glame_home_hero_slide01_logic_v1.md
glame_home_hero_slide01_background_v1.png
glame_home_hero_component_v1.dart
glame_home_hero_cursor_prompt_v1.md
```

---

## Non-negotiable

Production screen нельзя генерировать цельной картинкой, если там есть:
- логотип;
- G-знак;
- реальные магазины;
- navigation;
- точный UI;
- фирменный паттерн.

Такой экран собирается из approved layers.


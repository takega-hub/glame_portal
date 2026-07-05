# GLAME App — модульная система документов v2

## Назначение

Это новая структура документации GLAME App, где общие правила и согласованные сценарии разложены по отдельным модулям.

Цель:
- не терять уже согласованные решения;
- быстрее передавать задачи разработчику/Cursor;
- исключить искажение айдентики, фото, логотипа, G-знака, safe area и логики переходов;
- после каждого согласованного экрана выдавать production-package.

## Состав v2

1. `01_GLAME_IDENTITY_AND_ANTI_DISTORTION.md`
2. `02_GLAME_NAVIGATION_SAFE_AREA_SYSTEM.md`
3. `03_GLAME_HOME_HERO_SLIDES_LOGIC.md`
4. `04_GLAME_HOME_BLOCK2_NEW_IN_GLAME.md`
5. `05_GLAME_HOME_BLOCK3_AI_PHOTO_SELECTION.md`
6. `06_GLAME_HOME_BLOCK4_BRANDS.md`
7. `07_GLAME_HOME_BLOCK5_SPACES.md`
8. `08_GLAME_HOME_BLOCK6_HOW_TO_CHOOSE_BUY.md`
9. `09_GLAME_LIVE_STYLIST_FLOW.md`
10. `10_GLAME_AI_SELECTION_FLOW.md`
11. `11_GLAME_SPACES_YALTA_SIMFEROPOL_RULES.md`
12. `12_GLAME_UI_TOKENS_AND_COMPONENTS.md`
13. `13_GLAME_PRODUCTION_DELIVERY_PIPELINE.md`
14. `14_GLAME_CURSOR_EXECUTION_RULES.md`
15. `15_GLAME_QA_ACCEPTANCE_CHECKLIST.md`

## Главный принцип

Согласованный экран — это не одна картинка. Это пакет:

```text
logic.md
flutter.dart
background/assets.png
approved visual.png
safe-area reference.png
cursor prompt.md
QA checklist.md
```

## Critical rule

Top menu и bottom menu не являются частью hero-фото или фонового изображения.  
Они всегда живые UI-компоненты Flutter.

Hero-фото / фон / подложка передаются отдельно:
- без текста;
- без кнопок;
- без логотипа top bar;
- без bottom nav;
- без slide indicator.


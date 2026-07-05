# GLAME APP — Архитектура server-side pipeline для анализа внешности

**Раздел:** Главная -> Блок 3 -> Подбор по фото  
**Назначение:** целевая архитектура backend/ML-pipeline для production-внедрения анализа внешности без "магической" единственной модели.  
**Статус:** target design

---

## 1. Цель

Перевести сценарий `Подбор по фото` с текущего LLM-only анализа на детерминированный pipeline:

1. quality gate;
2. face landmarks;
3. color analysis;
4. hair / region analysis;
5. rule engine для рекомендаций;
6. user-safe summary.

Пользователю показывается только мягкий результат.  
Внутренние параметры анализа остаются техническими и не выводятся напрямую.

---

## 2. Главный принцип

Используем не одну модель "сделай всё", а конвейер из специализированных компонентов:

- `MediaPipe Face Landmarks` -> геометрия лица и пропорции;
- `OpenCV + LAB/YCrCb` -> тон кожи, контраст, светлота, цветовой характер;
- `hair segmentation / region segmentation` -> волосы, границы зон, дополнительный color sampling;
- `rule engine` -> перевод CV-метрик в рекомендации для подбора;
- `LLM summarizer` -> только финальная мягкая формулировка для UI.

LLM не должен быть первичным источником фактов о лице.

---

## 3. Как встраивается в текущий backend

Текущие точки интеграции:

- `backend/app/api/look_tryon.py`
- `backend/app/services/look_tryon_service.py`
- `backend/app/agents/stylist_agent.py`
- `backend/app/models/look.py`

### Что меняем

- `look_tryon_service.analyze_photo()` перестает напрямую делать vision-LLM анализ.
- Вместо этого он вызывает отдельный pipeline service и получает structured JSON.
- `look_tryon_service.generate_tryon_image()` использует результат анализа повторно, а не пересчитывает его заново.
- `look_tryon.py` расширяет response contract `/look-tryon/analyze`.
- `StylistAgent` использует structured analysis для:
  - выбора категории акцента;
  - передачи style/mood в генерацию образа;
  - будущего placement logic для try-on.

---

## 4. Рекомендуемая deployment-схема

### Основной вариант

Отдельный сервис:

- `backend` -> FastAPI бизнес-логика
- `ml-inference` -> CV / MediaPipe / segmentation pipeline

### Почему так лучше

- не перегружаем основной API нативными ML-зависимостями;
- проще изолировать `opencv`, `mediapipe`, `numpy`, `onnxruntime`;
- проще масштабировать отдельно;
- проще хранить и версионировать модели;
- легче дебажить артефакты анализа.

### Схема вызова

1. mobile/web вызывает backend `/api/look-tryon/analyze` или `/api/look-tryon/generate`;
2. backend нормализует вход и auth;
3. backend передает фото в `ml-inference`;
4. `ml-inference` возвращает structured analysis JSON;
5. backend сохраняет analysis metadata;
6. backend строит user-safe summary и рекомендации;
7. backend возвращает результат клиенту.

---

## 5. Новые backend-модули

### В backend

- `backend/app/services/photo_analysis_orchestrator.py`
  - orchestration-слой;
  - общается с `ml-inference`;
  - валидирует ответ;
  - кэширует / сохраняет structured result.

- `backend/app/services/photo_analysis_summary_service.py`
  - строит UI-safe summary;
  - может использовать шаблоны + LLM fallback;
  - не генерирует сырой анализ, только текст результата.

- `backend/app/services/jewelry_recommendation_mapper.py`
  - переводит structured analysis в фильтры под каталог;
  - pure rule engine;
  - без LLM.

- `backend/app/schemas/photo_analysis.py`
  - Pydantic-модели результата анализа;
  - единый canonical contract между backend и `ml-inference`.

### В отдельном ML сервисе

- `ml-service/app/main.py`
- `ml-service/app/pipeline/quality_gate.py`
- `ml-service/app/pipeline/face_landmarks.py`
- `ml-service/app/pipeline/color_analysis.py`
- `ml-service/app/pipeline/hair_analysis.py`
- `ml-service/app/pipeline/feature_mapper.py`
- `ml-service/app/pipeline/contracts.py`

---

## 6. Новый canonical JSON contract

Это целевой JSON-контракт, который должен соответствовать developer-spec и быть стабильным для backend/mobile.

```json
{
  "version": "1.0",
  "photoQuality": {
    "faceDetected": true,
    "singlePerson": true,
    "faceVisibleLarge": true,
    "sharpness": "good",
    "lightQuality": "good",
    "filterDetected": false,
    "headTiltStrong": false,
    "earVisible": "partial",
    "neckVisible": "visible"
  },
  "faceGeometry": {
    "faceShape": "oval",
    "faceLength": "balanced",
    "faceWidth": "balanced",
    "jawlineType": "soft",
    "cheekboneProminence": "medium",
    "chinType": "soft",
    "foreheadProportion": "balanced",
    "overallVertical": "balanced",
    "overallHorizontal": "balanced"
  },
  "appearanceScale": {
    "overallAppearanceScale": "medium",
    "featureScale": "medium",
    "eyeScale": "medium",
    "lipScale": "medium",
    "noseScale": "medium",
    "featureDensity": "medium",
    "allowedJewelryScale": "medium",
    "riskOfOverload": "medium"
  },
  "lineAnalysis": {
    "lineType": "soft_geometric",
    "dominantLineDirection": "elongated",
    "softnessLevel": "medium",
    "graphicLevel": "medium",
    "visualStrictness": "balanced",
    "visualNaturalness": "medium"
  },
  "colorAnalysis": {
    "eyeColor": "brown",
    "hairColor": "dark_brown",
    "hairDepth": "dark",
    "skinUndertone": "neutral",
    "appearanceLightness": "medium",
    "contrastLevel": "medium",
    "appearanceBrightness": "soft",
    "recommendedMetal": "mixed",
    "recommendedStonePalette": ["soft", "contrast"]
  },
  "textureAnalysis": {
    "skinTextureVisual": "delicate_lively",
    "frecklesVisible": "none",
    "fineLinesVisible": "light",
    "overallTexture": "soft",
    "textureContrast": "medium",
    "recommendedTextures": ["smooth", "mirror", "delicate_hammered"],
    "textureOverloadRisk": "low"
  },
  "earAndLobeAnalysis": {
    "earVisibility": "both",
    "earlobeSize": "medium",
    "earlobeType": "free",
    "earlobeCondition": "not_stretched",
    "piercingCountVisible": 1,
    "currentEarringFit": "unclear",
    "recommendedEarringWeight": "light_medium",
    "recommendedEarringClosure": ["stud", "english_lock"],
    "heavyEarringRisk": "medium"
  },
  "neckAnalysis": {
    "neckLength": "medium",
    "neckVisibility": "visible",
    "neckDelicacy": "medium",
    "recommendedNecklaceLength": ["short", "medium"],
    "shorteningRisk": "medium",
    "verticalAccentNeeded": "optional"
  },
  "accentZones": {
    "primaryAccentZone": "earrings",
    "secondaryAccentZone": "necklace",
    "accentNearFace": "yes",
    "accentOnNeck": "moderate",
    "accentOnHands": "optional"
  },
  "recommendations": {
    "primaryCategory": "earrings",
    "recommendedCategories": ["earrings", "necklace", "rings"],
    "recommendedScale": "medium",
    "recommendedEarringLength": ["short", "medium"],
    "recommendedEarringWeight": "light_medium",
    "recommendedNecklaceLength": ["short", "medium"],
    "recommendedShapes": ["oval", "drop", "soft_geometry", "clean_line"],
    "recommendedTextures": ["smooth", "mirror", "delicate_hammered"],
    "recommendedMetals": ["silver", "mixed"],
    "avoidAsPrimary": ["too_heavy", "too_tiny"],
    "stylistSummaryInternal": "Средний масштаб, мягкая геометрия, легкая посадка серег, деликатный блеск."
  },
  "userFacing": {
    "summary": "Вам подойдут украшения среднего масштаба, мягкой геометрии и деликатного блеска. Они поддержат линию лица и не перегрузят образ.",
    "bullets": [
      "Лучше выбирать серьги средней длины",
      "Мягкая геометрия будет смотреться гармоничнее",
      "Смешанные металлы и деликатный блеск сохранят баланс"
    ]
  },
  "debug": {
    "pipelineVersion": "face-analysis-v1",
    "provider": "ml-inference",
    "timingsMs": {},
    "artifacts": {}
  }
}
```

---

## 7. Что хранить в базе

### Быстрый вариант без миграции

Использовать уже существующее поле:

- `looks.generation_metadata`

Структура:

```json
{
  "photo_analysis": { "...structured json..." },
  "photo_analysis_version": "1.0",
  "photo_analysis_source": "ml-inference",
  "user_facing_summary": { "...summary..." }
}
```

### Правильный вариант

Добавить отдельную таблицу:

- `photo_analysis_results`

Поля:

- `id`
- `user_id`
- `source_photo_url`
- `analysis_json`
- `quality_status`
- `pipeline_version`
- `created_at`
- `updated_at`

И optional linkage:

- `look_id`

### Почему отдельная таблица лучше

- analysis живет отдельно от конкретного generated look;
- можно переиспользовать один analysis для нескольких подборок;
- можно перегенерировать recommendations без повторного CV анализа;
- удобно для аудита и улучшения pipeline.

---

## 8. Новый backend flow для `/look-tryon/analyze`

### Текущий контракт

Сейчас ответ слишком плоский:

- `color_type`
- `style`
- `features`
- `recommendations`

### Целевой контракт

`/api/look-tryon/analyze` должен возвращать:

- полный structured analysis;
- `userFacing.summary`;
- `quality_status`;
- `can_continue`;
- optional `retry_hint`.

Пример:

```json
{
  "success": true,
  "can_continue": true,
  "quality_status": "ok",
  "analysis": { "...canonical json..." },
  "retry_hint": null
}
```

Если фото плохое:

```json
{
  "success": true,
  "can_continue": false,
  "quality_status": "retry_required",
  "analysis": {
    "photoQuality": {
      "faceDetected": true,
      "singlePerson": false
    }
  },
  "retry_hint": "На фото должно быть одно лицо крупным планом и при ровном свете."
}
```

---

## 9. Новый backend flow для `/look-tryon/generate`

### Целевой pipeline

1. принять фото и `user_id`;
2. получить structured analysis из pipeline;
3. если `can_continue=false` -> вернуть controlled response без генерации образа;
4. через `jewelry_recommendation_mapper` получить recommendation filters;
5. передать фильтры и summary в генерацию образа;
6. сохранить `photo_analysis` рядом с образoм;
7. вернуть:
   - `generated_look`
   - `photo_analysis`
   - `user_facing_summary`
   - `try_on_result`

### Ключевой принцип

Генерация образа не должна повторно пересчитывать landmarks и color analysis, если они уже были получены на этом же фото.

---

## 10. Где использовать rule engine, а где LLM

### Rule engine

Rule engine обязателен для:

- `recommendedCategories`
- `recommendedScale`
- `recommendedShapes`
- `recommendedTextures`
- `recommendedMetals`
- `avoidAsPrimary`
- `primaryAccentZone`

### LLM допустим только для:

- генерации мягкого summary;
- стилистической переформулировки результата;
- optional narrative explanation.

LLM не должен определять:

- face shape;
- undertone;
- earlobe condition;
- contrast level;
- jewelry scale.

---

## 11. Mapping CV -> jewelry recommendations

### Примеры правил

- если `overallAppearanceScale=delicate` -> понизить приоритет `large`, `statement`;
- если `heavyEarringRisk=high` -> исключать heavy earrings из primary;
- если `skinUndertone=cool` и `contrastLevel=low` -> повышать `silver`, `soft stones`;
- если `lineType=soft_geometric` -> повышать `oval`, `drop`, `soft_geometry`;
- если `verticalAccentNeeded=yes` -> повышать вытянутые серьги и подвески;
- если `earVisibility=none` -> не делать уверенный вывод по серьгам, понизить confidence;
- если `neckVisibility=hidden` -> не делать жесткие рекомендации по длине колье.

---

## 12. Какие фазы внедрения делать

### Phase 1 — production MVP

- отдельный `ml-inference` сервис;
- quality gate;
- MediaPipe landmarks;
- базовый color analysis;
- rule engine;
- user-facing summary;
- новый response contract `/look-tryon/analyze`;
- сохранение structured analysis.

### Phase 2 — усиление точности

- hair segmentation;
- improved eye color detection;
- neck / ear heuristics;
- confidence score по блокам;
- повторное использование analysis без re-run.

### Phase 3 — связь с try-on

- использовать landmarks и zones для placement logic;
- category-aware compositor:
  - earrings
  - necklace
  - rings
  - bracelets
- подготовка входа для внешнего try-on API на основе CV-артефактов.

---

## 13. Какие файлы менять в текущем репозитории

### Обязательно

- `backend/app/api/look_tryon.py`
  - расширить response model;
  - добавить controlled quality response.

- `backend/app/services/look_tryon_service.py`
  - убрать LLM-only анализ как primary path;
  - перенести orchestration в `photo_analysis_orchestrator`.

- `backend/app/agents/stylist_agent.py`
  - использовать structured analysis и recommendation filters;
  - не вызывать повторный анализ без необходимости.

- `backend/app/models/look.py`
  - временно использовать `generation_metadata.photo_analysis`;
  - позже вынести в отдельную таблицу.

### Новые backend файлы

- `backend/app/schemas/photo_analysis.py`
- `backend/app/services/photo_analysis_orchestrator.py`
- `backend/app/services/photo_analysis_summary_service.py`
- `backend/app/services/jewelry_recommendation_mapper.py`
- `backend/app/services/ml_inference_client.py`

### Infra

- `ml-service/Dockerfile`
- `ml-service/requirements.txt`
- обновление compose/deploy конфигурации

---

## 14. Рекомендуемый API между backend и ml-service

### `POST /analyze-face`

Request:

- multipart file `photo`

Response:

```json
{
  "success": true,
  "analysis": { "...canonical json without userFacing..." },
  "quality_status": "ok",
  "can_continue": true
}
```

### Почему `userFacing` лучше строить на backend

- брендовый tone of voice контролируется backend;
- можно менять тексты без перевыката ML сервиса;
- меньше coupling между CV и продуктовой логикой.

---

## 15. Зависимости и runtime

### Для ml-service

- `opencv-python-headless`
- `numpy`
- `mediapipe`
- `onnxruntime`
- `pydantic`
- `fastapi`
- `uvicorn`
- `python-multipart`
- optional: `scikit-learn`

### Не рекомендуется

Не ставить все эти зависимости в текущий `backend/Dockerfile`, пока нет отдельного ML runtime.

---

## 16. Главные решения

Фиксируем:

1. Анализ внешности строится как server-side pipeline, а не как один LLM-запрос.
2. `MediaPipe` используется для геометрии лица и пропорций.
3. Цветовой анализ строится отдельно на `LAB/YCrCb`.
4. Рекомендации для ювелирного подбора рассчитываются rule-engine, а не LLM.
5. LLM используется только для мягкой формулировки результата.
6. Structured analysis хранится отдельно и может переиспользоваться.
7. Лучший deployment-вариант — отдельный `ml-inference` сервис рядом с backend.


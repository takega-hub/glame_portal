# Раздел "Подбор по фото" для отдельного AI-стилиста

Документ фиксирует текущие наработки GLAME по сценарию "Подбор по фото" и описывает, какие модули, функции и контракты стоит перенести в отдельное приложение AI-стилиста.

Цель раздела: пользователь загружает портретное фото, система проверяет качество снимка, анализирует внешность, формирует понятное описание и подбирает украшения/образы по структурированным правилам.

## 1. Пользовательский сценарий

1. Пользователь открывает раздел "Подбор по фото".
2. Если пользователь не авторизован, приложение предлагает войти/зарегистрироваться и после входа возвращает к загрузке фото.
3. Пользователь выбирает источник фото: камера или галерея.
4. Клиент показывает экран предварительной проверки фото с рамкой лица и краткими требованиями.
5. Клиент отправляет фото на backend endpoint анализа.
6. Backend сохраняет фото, вызывает ML-сервис, нормализует результат, добавляет рекомендации, human-readable описание и товары.
7. Если фото не подходит, пользователь получает retry-hint: что исправить в снимке.
8. Если фото подходит, пользователь видит результат:
   - описание внешности;
   - стиль/типаж;
   - цветовое впечатление;
   - правила подбора;
   - рекомендуемые категории/металлы/формы/фактуры;
   - карточки подходящих товаров.

Текущий mobile flow реализован в:

- `mobile/glame_app/lib/src/features/home/photo_upload_screen.dart`
- `mobile/glame_app/lib/src/features/home/photo_selection_api.dart`

## 2. Архитектура модулей

Рекомендуемая структура для нового проекта:

```text
ai-stylist/
  app/
    api/
      photo_selection.py
    schemas/
      photo_analysis.py
    services/
      ml_inference_client.py
      photo_analysis_orchestrator.py
      photo_analysis_summary_service.py
      jewelry_recommendation_mapper.py
      product_recommendation_service.py
      photo_storage_service.py
    agents/
      photo_analysis_interpreter_agent.py
  ml-service/
    app/
      main.py
      pipeline.py
```

Минимальный MVP можно запускать с двумя сервисами:

- `backend` - авторизация, загрузка фото, хранение результата, подбор товаров, клиентский API;
- `ml-service` - чистый анализ изображения и возврат structured analysis.

## 3. ML Service

Текущие файлы:

- `ml-service/app/main.py`
- `ml-service/app/pipeline.py`
- `ml-service/requirements.txt`

### 3.1 Endpoint

`POST /analyze-face`

Вход: `multipart/form-data`, поле `photo`.

Ограничения:

- пустой файл запрещен;
- размер фото до 10 MB;
- файл проверяется через `PIL.Image.verify()`;
- неподдерживаемые/битые изображения возвращают `400`;
- слишком большой файл возвращает `413`.

Пример верхнего уровня ответа:

```json
{
  "success": true,
  "can_continue": true,
  "quality_status": "ok",
  "retry_hint": null,
  "analysis": {}
}
```

### 3.2 Основные зависимости

- `Pillow` - чтение изображения, basic stats;
- `mediapipe` - Face Mesh landmarks;
- `opencv-python` / `cv2` - LAB/HSV, резкость, контраст, k-means для цвета глаз;
- `numpy` - регионы изображения, статистика пикселей.

Если `mediapipe`, `cv2` или `numpy` недоступны, пайплайн должен переходить в baseline/fallback.

### 3.3 Два режима анализа

`mediapipe-color-v1` - основной режим:

- находит лицо через MediaPipe Face Mesh;
- строит регионы лица, волос, глаз, щек, носа, подбородка;
- считает геометрию лица, цветовые признаки, волосы, кожу, шею, уши, гармонию лица;
- формирует рекомендации для украшений.

`baseline-cpu-v1` - fallback:

- работает без landmarks;
- использует размер изображения, среднюю яркость, контраст и соотношение сторон;
- возвращает менее точный, но совместимый JSON;
- нужен, чтобы UI и backend не ломались при runtime-ошибках ML.

## 4. Quality Gate Фото

Quality gate решает, можно ли продолжать подбор.

Ключевые поля:

```json
{
  "photoQuality": {
    "faceDetected": true,
    "singlePerson": true,
    "faceVisibleLarge": true,
    "sharpness": "good",
    "lightQuality": "good",
    "filterDetected": false,
    "headTiltStrong": false,
    "earVisible": "both",
    "neckVisible": "visible"
  }
}
```

Логика отказа:

- лицо не найдено;
- найдено больше одного лица;
- лицо слишком маленькое;
- плохой свет;
- плохая резкость;
- сильный наклон головы.

Функции из текущего пайплайна:

- `_quality_failure_reasons(photo_quality)`
- `_quality_retry_hint(photo_quality)`
- `_quality_bucket(value, low, medium)`
- `_laplacian_sharpness(region)`

Текущий `can_continue` в основном режиме:

```python
can_continue = (
    single_person
    and face_visible_large
    and light_quality != "poor"
    and sharpness != "poor"
    and not head_tilt_strong
)
```

Retry hint должен быть человеческим, например:

```text
Чтобы подбор был точнее: в кадре должно быть только одно лицо; нужно более ровное освещение без сильных теней.
```

## 5. Structured Analysis Contract

`analysis` должен оставаться стабильным контрактом между ML, backend, LLM-интерпретатором, UI и рекомендациями.

Рекомендуемая структура:

```json
{
  "version": "1.0",
  "photoQuality": {},
  "faceGeometry": {},
  "appearanceScale": {},
  "lineAnalysis": {},
  "colorAnalysis": {},
  "hairAnalysis": {},
  "colorContrastAnalysis": {},
  "skinAnalysis": {},
  "facialHarmonyAnalysis": {},
  "vibeAnalysis": {},
  "earAndLobeAnalysis": {},
  "neckAnalysis": {},
  "decolleteAnalysis": {},
  "accentZones": {},
  "recommendations": {},
  "debug": {}
}
```

### 5.1 Face Geometry

Назначение: понять форму лица и направление линий.

Поля:

- `faceShape`: `oval`, `round`, `elongated`, `square`, `heart`;
- `faceLength`: `short`, `balanced`, `long`;
- `faceWidth`: `narrow`, `balanced`, `wide`;
- `jawlineType`: `soft`, `defined`;
- `cheekboneProminence`: `medium`, `high`;
- `overallVertical`: `compact`, `balanced`, `elongated`;
- `overallHorizontal`: `narrow`, `balanced`, `wide`.

Ключевые функции:

- `_face_shape(face_ratio, jaw_to_cheek)`
- `_recommended_shapes_from_face(face_shape, line_type)`

### 5.2 Appearance Scale

Назначение: определить масштаб украшений.

Поля:

- `overallAppearanceScale`: `delicate`, `medium`, `expressive`;
- `featureScale`: `small`, `medium`, `large`;
- `featureDensity`: `light`, `medium`, `dense`;
- `allowedJewelryScale`: `mini`, `medium`, `large`;
- `riskOfOverload`: `low`, `medium`, `high`.

### 5.3 Line Analysis

Назначение: связать линии лица с формами украшений.

Поля:

- `lineType`: `graphic`, `organic`, `soft_geometric`;
- `dominantLineDirection`: `rounded`, `elongated`;
- `softnessLevel`;
- `graphicLevel`;
- `visualStrictness`;
- `visualNaturalness`.

Правила:

- `graphic` -> clean line, geometry, elongated;
- `soft_geometric` -> oval, drop, soft geometry, clean line;
- `organic` -> organic, soft geometry, drop.

### 5.4 Color Analysis

Назначение: определить металл, цвет камней и контраст.

Поля:

- `eyeColor`: `blue`, `green`, `hazel`, `brown`, `gray`, `unknown`;
- `hairColor`: `black`, `dark_brown`, `brown`, `light_brown`, `blonde`, `red`, `unknown`;
- `hairDepth`: `light`, `medium`, `dark`;
- `skinUndertone`: `warm`, `cool`, `neutral`, `olive`;
- `appearanceLightness`: `light`, `medium`, `deep`;
- `contrastLevel`: `low`, `medium`, `high`;
- `appearanceBrightness`: `soft`, `clear`;
- `recommendedMetal`: `gold`, `silver`, `mixed`;
- `recommendedStonePalette`: список палитр.

Ключевые функции:

- `_lab_color_stats(region)`
- `_determine_metal(brightness, warmth)`
- `_classify_eye_color(region)`
- `_classify_hair_color(region)`
- `_season_from_color_metrics(...)`
- `_recommended_stone_palette(...)`

### 5.5 Hair Analysis

Назначение: понять, закрыты ли уши/лоб, какой объем волос и как это влияет на серьги.

Поля:

- `hairLength`: `short`, `medium`, `long`, `very_long`;
- `hairVolume`: `low`, `medium`, `high`;
- `hairTexture`: `straight`, `wavy`, `curly`;
- `earsCovered`: `none`, `left`, `right`, `both`;
- `foreheadCovered`: `none`, `partially`, `full`;
- `hairColorPrimary`;
- `hairColorSecondary`: `neutral`, `ash`, `copper`, `golden`;
- `hairRootsVisible`;
- `hairGrayPercentage`;
- `coverageRatios`.

Если `earsCovered == both`, текущая логика переносит primary accent с серег на колье.

### 5.6 Skin Analysis

Назначение: подобрать фактуры металла и огранки камней.

Поля:

- `skinToneDepth`;
- `skinUndertone`;
- `skinEvenness`;
- `skinTexturePrimary`: `smooth`, `fine_pores`, `visible_pores`, `textured`;
- `skinShineLevel`: `matte`, `natural`, `dewy`, `oily`;
- `rednessAreas`;
- `fineLines`;
- `wrinklesDepth`;
- `freckles`;
- `moles`;
- `recommendedMetalFinish`: `mirror`, `satin`, `brushed`, `matte`;
- `avoidMetalFinish`;
- `stoneCutPreference`: `brilliant`, `princess`, `rose`, `cabochon`.

Ключевые функции:

- `_skin_evenness(region)`
- `_skin_texture_primary(region)`
- `_skin_shine_level(region)`
- `_redness_areas(...)`
- `_fine_lines(region, sharpness_score)`
- `_freckles_level(region)`
- `_moles_level(region)`
- `_recommended_metal_finish(...)`
- `_stone_cut_preference(...)`

Важно: в пользовательском тексте нельзя звучать медицински или оценочно. Эти поля нужны для стиля и материалов, а не для диагностики.

### 5.7 Facial Harmony и Vibe

Назначение: определить допустимую симметрию, характер форм и mood украшений.

Поля `facialHarmonyAnalysis`:

- `facialThirdRatio`;
- `eyeSpacingDeviation`;
- `noseToMouthRatio`;
- `goldenRatioDeviation`;
- `centerAlignmentDeviation`;
- `harmonyLevel`: `classic`, `character`, `expressive`, `avantgarde`;
- `symmetryImportance`;
- `recommendedSymmetry`: `strict`, `balanced`, `asymmetric_possible`.

Поля `vibeAnalysis`:

- `primaryImpression`: `elegant`, `romantic`, `bold`, `sweet`, `mysterious`;
- `faceExpressionBaseline`;
- `energyLevel`: `calm`, `balanced`, `dynamic`;
- `recommendedJewelryMood`;
- `forbiddenJewelryMood`.

Ключевые функции:

- `_facial_thirds_ratio(...)`
- `_golden_ratio_deviation(...)`
- `_harmony_level(...)`
- `_symmetry_guidance(harmony_level)`
- `_vibe_analysis(...)`

### 5.8 Ear, Lobe, Neck, Decollete

Назначение: правила для серег, застежек, веса, длины и колье.

`earAndLobeAnalysis`:

- видимость каждого уха;
- тип/размер/толщина мочки;
- форма уха;
- `recommendedClosures`;
- `maxEarringWeightGrams`;
- `maxEarringLengthMm`;
- `heavyEarringRisk`.

`neckAnalysis`:

- `neckLengthToWidth`;
- `neckProfile`;
- `neckBaseType`;
- `collarboneVisibility`;
- `rigidChokerRisk`;
- `recommendedNecklaceTypes`;
- `pendulumLengthRecommendationMm`.

`decolleteAnalysis`:

- `visibility`;
- `collarboneShape`;
- `chestWidth`;
- `recommendedPendantDropMm`;
- `recommendedLayeringPossible`.

Ключевые функции:

- `_recommended_ear_closures(...)`
- `_ear_weight_and_length(...)`
- `_necklace_recommendations_from_ratio(...)`
- `_decollete_recommendations(...)`

## 6. Recommendation Rules

`recommendations` - главный слой для каталога и UI.

Пример:

```json
{
  "primaryCategory": "earrings",
  "recommendedCategories": ["earrings", "necklace", "rings"],
  "recommendedScale": "medium",
  "recommendedEarringLength": ["short", "medium"],
  "recommendedEarringWeight": "light_medium",
  "recommendedNecklaceLength": ["short", "medium"],
  "recommendedShapes": ["oval", "drop", "soft_geometry"],
  "recommendedTextures": ["smooth", "mirror"],
  "recommendedMetals": ["silver", "mixed"],
  "metal_colors": ["silver", "mixed"],
  "stone_colors": ["soft", "contrast"],
  "styles": ["элегантный", "спокойный"],
  "avoidAsPrimary": ["too_heavy", "too_tiny"],
  "avoidRules": {}
}
```

Текущие модули:

- `backend/app/services/jewelry_recommendation_mapper.py`
- `ml-service/app/pipeline.py`, функция `_avoid_rules(...)`

`jewelry_recommendation_mapper.enrich(analysis)` должен:

- гарантировать наличие `accentZones`;
- гарантировать наличие `recommendations`;
- добавить legacy aliases `metal_colors`, `stone_colors`, `styles`;
- держать контракт стабильным для старых клиентов.

`avoidRules` должен запрещать неподходящие признаки:

- металлы, конфликтующие с undertone;
- слишком тяжелые серьги;
- oversized при delicate scale;
- короткий choker при высоком риске;
- mirror finish при oily shine;
- хаотичная асимметрия при classic harmony;
- слишком контрастные камни при low contrast.

## 7. Backend Orchestrator

Текущие файлы:

- `backend/app/services/ml_inference_client.py`
- `backend/app/services/photo_analysis_orchestrator.py`
- `backend/app/services/photo_analysis_summary_service.py`
- `backend/app/api/look_tryon.py`
- `backend/app/schemas/photo_analysis.py`

### 7.1 ML Inference Client

Задача:

- знать `ML_INFERENCE_URL`;
- отправить фото в `/analyze-face`;
- иметь timeout;
- при ошибке вернуть `None`, чтобы backend ушел в fallback.

Переменные:

```env
ML_INFERENCE_URL=http://127.0.0.1:8010
ML_INFERENCE_TIMEOUT_SECONDS=45.0
```

### 7.2 PhotoAnalysisOrchestrator

Задача:

1. Вызвать ML-сервис.
2. Если ML недоступен, вызвать legacy provider.
3. Нормализовать payload в canonical `analysis`.
4. Прогнать `jewelry_recommendation_mapper.enrich`.
5. Посчитать итоговый quality.
6. Собрать `user_facing`.
7. Вернуть legacy projection: `color_type`, `style`, `features`, `recommendations`.

Возвращаемый backend envelope:

```json
{
  "success": true,
  "can_continue": true,
  "quality_status": "ok",
  "retry_hint": null,
  "analysis": {},
  "user_facing": {},
  "human_readable": {},
  "recommended_products": [],
  "saved_photo_url": null,
  "saved_analysis_url": null,
  "color_type": "универсальный",
  "style": "классический",
  "features": {},
  "recommendations": {}
}
```

## 8. Human-Readable Interpreter

Текущий файл:

- `backend/app/agents/photo_analysis_interpreter_agent.py`

Назначение: превратить structured analysis в мягкое описание для пользователя.

Правила системного промпта:

- опираться только на входной structured analysis;
- не выдумывать признаки;
- не делать выводов о возрасте, этничности, здоровье, характере, социальном статусе, привлекательности;
- не использовать медицинские формулировки;
- не упоминать внутренние JSON-поля;
- писать как стилист, осторожно: "считывается как", "выглядит более", "лучше поддержать";
- возвращать только JSON.

Response format:

```json
{
  "summary": "2-4 предложения",
  "appearance": "общее визуальное впечатление",
  "face": "форма лица, линии, масштаб, акцентные зоны",
  "style_type": "2-5 слов",
  "color_type": "2-5 слов",
  "bullets": ["мысль 1", "мысль 2", "мысль 3"]
}
```

Если LLM недоступен, нужен deterministic fallback из structured fields.

## 9. Product Recommendation Service

В текущем проекте подбор товаров реализован внутри `backend/app/api/look_tryon.py` функцией `_recommended_products_for_analysis`.

В новом проекте лучше вынести в `product_recommendation_service.py`.

Вход:

- canonical `analysis`;
- `recommendations`;
- `avoidRules`;
- каталог товаров.

Алгоритм:

1. Если `can_continue != true`, не подбирать товары.
2. Взять категории из `recommendedCategories`.
3. По категориям построить exact/like tokens:
   - `earrings` -> `серьг`, `пусет`, `кафф`, `earring`;
   - `necklace` -> `колье`, `цеп`, `подвес`, `кулон`, `necklace`, `pendant`;
   - `rings` -> `кольц`, `ring`;
   - `bracelets` -> `браслет`, `bracelet`.
4. Отфильтровать активные товары с фото.
5. Исключить упаковку, салфетки, сопутствующие товары.
6. Проверить металл:
   - allowed metals: `gold`, `silver`, `mixed`;
   - forbidden metals из `avoidRules.metalForbidden`.
7. Начислить score:
   - совпадение категории;
   - exact category;
   - совпадение металла;
   - совпадение формы;
   - совпадение stone palette;
   - bonus за core assortment / brand concept;
   - penalty за forbidden shapes/stones;
   - penalty за тяжелые серьги.
8. Отсортировать по score, core flags, цене.
9. Убрать дубли по id и signature.

Товарный payload:

```json
{
  "id": "uuid",
  "name": "Название",
  "brand": "GLAME",
  "price": 10000,
  "category": "Серьги",
  "images": [],
  "description": "",
  "article": "",
  "weight": 8.4
}
```

## 10. Storage и Privacy

Текущая логика:

- фото сохраняется через `look_tryon_service.save_user_photo`;
- analysis sidecar сохраняется рядом с фото через `save_photo_analysis_artifacts`;
- URL фото и URL анализа возвращаются в API;
- анализ может сохраняться в metadata сгенерированного look.

Для отдельного приложения рекомендуется:

- хранить оригинальное фото отдельно от публичных assets;
- не публиковать фото без явного действия пользователя;
- хранить structured analysis как JSON sidecar;
- иметь TTL/удаление фото по запросу пользователя;
- в UI писать: "Фото используется только для подбора и не публикуется";
- в логах не писать base64 и бинарные данные.

## 11. Mobile/Web UI

Основные экраны:

1. Intro:
   - заголовок "Подбор по фото";
   - описание;
   - кнопка "Выбрать или сделать фото";
   - кнопка "Какое фото подойдет".
2. Auth gate:
   - если пользователь не вошел.
3. Source picker:
   - camera;
   - gallery;
   - guide.
4. Photo review:
   - превью фото;
   - face frame overlay;
   - chips требований;
   - кнопка "Начать анализ".
5. Analysis progress:
   - статусы: лицо видно, свет подходит, фото четкое, снимок готов;
   - animated reveal по реальным полям `photoQuality`.
6. Retry screen:
   - `retry_hint`;
   - кнопка выбрать другое фото;
   - guide.
7. Result:
   - preview;
   - "Описание внешности";
   - "Что мы увидели";
   - chips style/color type;
   - bullet-рекомендации;
   - рекомендуемые товары.

Mobile endpoint:

```dart
final form = FormData.fromMap({
  'photo': MultipartFile.fromBytes(bytes, filename: fileName),
});
final resp = await dio.post('/look-tryon/analyze', data: form);
```

## 12. API нового приложения

Минимальный набор:

### `POST /photo-selection/analyze`

Вход: `multipart/form-data`, `photo`.

Ответ: `PhotoAnalysisApiResponse`.

Действия:

- авторизовать пользователя;
- сохранить фото;
- вызвать orchestrator;
- добавить `human_readable`;
- добавить `recommended_products`;
- сохранить sidecar JSON;
- вернуть полный результат.

### `GET /photo-selection/history`

Вернуть прошлые подборы пользователя.

### `GET /photo-selection/{id}`

Вернуть один сохраненный анализ.

### `DELETE /photo-selection/{id}`

Удалить фото и analysis.

## 13. Что переносить первым

MVP:

1. `ml-service/app/main.py`
2. `ml-service/app/pipeline.py`
3. `backend/app/services/ml_inference_client.py`
4. `backend/app/services/photo_analysis_orchestrator.py`
5. `backend/app/services/jewelry_recommendation_mapper.py`
6. `backend/app/services/photo_analysis_summary_service.py`
7. `backend/app/schemas/photo_analysis.py`
8. API endpoint `/photo-selection/analyze`
9. UI flow загрузки/проверки/результата

Второй этап:

1. `photo_analysis_interpreter_agent.py`
2. catalog scoring service
3. сохранение истории подборов
4. админка/промпты для interpreter agent
5. A/B тесты текстов summary и retry hints

Третий этап:

1. улучшенная hair segmentation;
2. более точный single-person gate;
3. confidence score по каждому блоку анализа;
4. отдельные rulesets под одежду, макияж, прически, украшения;
5. персональная память пользователя: dislikes, любимые металлы, бюджет, аллергии, поводы.

## 14. Ограничения текущей методики

- Часть выводов эвристическая, не модельная.
- Hair segmentation сейчас основан на регионах и сравнении HSV, не на segmentation mask.
- Ear/lobe анализ приблизительный, зависит от прически и кадра.
- Neck/decollete анализ приблизительный и зависит от crop.
- Цветовой анализ чувствителен к свету, фильтрам, макияжу и балансу белого.
- Нельзя показывать пользователю технические или оценочные формулировки.

## 15. Рекомендации по развитию для AI-стилиста

Для нового продукта стоит развести три слоя:

1. Vision facts - что система видит на фото.
2. Style rules - как эти факты превращаются в рекомендации.
3. Stylist narration - как мягко объяснить результат пользователю.

Это позволит:

- менять правила подбора без переписывания ML;
- добавлять новые категории: одежда, макияж, очки, прически;
- тестировать разные стилистические методики;
- сохранять прозрачность: почему пользователю предложили именно эти вещи.

Главный принцип: structured analysis должен быть сухим и стабильным, а пользовательский текст должен быть деликатным, осторожным и полезным.

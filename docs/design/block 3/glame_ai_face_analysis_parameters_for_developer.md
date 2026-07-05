# GLAME APP — Перечень параметров AI-анализа лица / внешности

**Раздел:** Главная → Блок 3 → Подбор по фото  
**Назначение:** внутренняя спецификация для разработчика / AI-команды.  
**Важно:** эти параметры используются внутри системы и **не выводятся пользователю напрямую**.

---

## 1. Принцип

Сценарий «Подбор по фото» анализирует фото пользователя, чтобы сформировать рекомендации украшений по:

- соразмерности;
- посадке;
- масштабу;
- форме;
- цвету;
- фактуре;
- визуальному впечатлению.

В интерфейсе пользователю показывается **не технический анализ**, а мягкий результат:

> Вам подойдут украшения среднего масштаба, мягкой геометрии и деликатного блеска. Они поддержат линию лица и не перегрузят образ.

---

# 2. Качество фото

Проверяется до основного анализа.

| Параметр | Возможные значения | Зачем нужен |
|---|---|---|
| Лицо найдено | true / false | понять, можно ли запускать анализ |
| Один человек в кадре | true / false | исключить ошибочный анализ |
| Лицо видно крупно | true / false | повысить точность подбора |
| Фото не размыто | good / medium / poor | корректно считать черты и детали |
| Достаточно света | good / medium / poor | видеть форму, цвет, фактуру |
| Сильный фильтр | true / false | не искажать цвет и фактуру |
| Сильный наклон головы | true / false | не искажать пропорции |
| Уши видны | left / right / both / partial / none | важно для подбора серег |
| Шея видна | visible / partial / hidden | важно для колье и длины украшений |

---

# 3. Геометрия лица

| Параметр | Возможные значения | Зачем нужен |
|---|---|---|
| Форма лица | oval / round / elongated / square / heart / diamond / mixed / unknown | подбор формы и длины серег |
| Длина лица | short / balanced / long | понять, нужно ли визуально вытягивать / балансировать лицо |
| Ширина лица | narrow / balanced / wide | определить масштаб и ширину украшений |
| Линия челюсти | soft / defined / angular / narrow / unknown | подобрать смягчающие или графичные формы |
| Скулы | low / medium / high / unknown | определить зону визуального акцента |
| Подбородок | rounded / pointed / square / soft / unknown | подобрать форму серег и подвесок |
| Лоб | narrow / balanced / wide / unknown | оценить баланс верхней части лица |
| Общая вертикаль лица | compact / balanced / elongated | подобрать длину серег |
| Общая горизонталь лица | narrow / balanced / wide | определить ширину и объем украшений |

---

# 4. Масштаб внешности

| Параметр | Возможные значения | Зачем нужен |
|---|---|---|
| Общий масштаб внешности | delicate / medium / expressive / unknown | понять допустимый масштаб украшений |
| Масштаб черт | small / medium / large / mixed / unknown | подобрать соразмерность украшений |
| Масштаб глаз | small / medium / large / unknown | оценить выразительность зоны лица |
| Масштаб губ | small / medium / large / unknown | оценить общий баланс черт |
| Масштаб носа | small / medium / large / unknown | оценить визуальную плотность лица |
| Визуальная плотность черт | light / medium / dense / unknown | понять, не потеряются ли украшения |
| Допустимый масштаб украшений | mini / medium / large / statement | выбрать размер изделий |
| Риск перегруза украшениями | low / medium / high | не рекомендовать слишком тяжелые / крупные формы |

---

# 5. Линии внешности

| Параметр | Возможные значения | Зачем нужен |
|---|---|---|
| Тип линий | soft / graphic / soft_geometric / organic / mixed / unknown | подобрать характер формы украшений |
| Доминирующая пластика | rounded / angular / elongated / mixed / unknown | определить форму: овалы, капли, геометрия, органика |
| Мягкость черт | low / medium / high | подобрать мягкие или более четкие линии |
| Графичность черт | low / medium / high | понять, выдержит ли лицо строгую геометрию |
| Визуальная строгость | soft / balanced / strict | подобрать степень графичности |
| Визуальная естественность | low / medium / high | подобрать органичные / природные формы |

---

# 6. Цветовой блок

| Параметр | Возможные значения | Зачем нужен |
|---|---|---|
| Цвет глаз | blue / green / gray / brown / hazel / dark / unknown | подобрать металл и оттенки вставок |
| Цвет волос | black / dark_brown / brown / light_brown / blonde / red / gray / mixed / unknown | оценить глубину и контрастность |
| Глубина волос | light / medium / dark / unknown | определить контраст украшений |
| Подтон кожи | cool / warm / neutral / olive / unknown | подобрать серебро / золото / mixed |
| Светлота внешности | light / medium / deep / unknown | подобрать яркость металла и вставок |
| Контрастность внешности | low / medium / high / unknown | определить мягкие или контрастные украшения |
| Яркость внешности | soft / clear / deep / unknown | подобрать уровень блеска |
| Рекомендованный металл | silver / gold / mixed / unknown | фильтр для каталога |
| Рекомендованные оттенки вставок | light / deep / contrast / soft / unknown | фильтр по цветовым акцентам |

---

# 7. Фактурность внешности

**Важно:** в интерфейсе пользователю это не показываем напрямую.

| Параметр | Возможные значения | Зачем нужен |
|---|---|---|
| Визуальная фактура кожи | smooth / delicate_lively / textured / unknown | подобрать поверхность украшений |
| Веснушки | none / light / visible / unknown | оценить живость / мягкость фактуры |
| Мимические линии | none / light / visible / unknown | подобрать деликатность блеска |
| Общая фактурность внешности | smooth / soft / lively / expressive / unknown | подобрать гладкие или фактурные изделия |
| Контраст фактуры | soft / medium / strong / unknown | определить уровень фактурности украшений |
| Рекомендованная фактура украшений | smooth / matte / hammered / organic / mirror | фильтр по поверхности |
| Риск перегруза фактурой | low / medium / high | не перегружать образ слишком активной фактурой |

## Не выводить пользователю

- «морщины»;
- «дефекты»;
- «текстура кожи»;
- «возрастные изменения».

## Можно выводить пользователю

- «деликатная фактура»;
- «мягкий блеск»;
- «живая фактура»;
- «гладкая поверхность будет смотреться чище».

---

# 8. Уши и мочка

Это важный блок именно для ювелирного подбора.

| Параметр | Возможные значения | Зачем нужен |
|---|---|---|
| Видимость ушей | left / right / both / partial / none / unknown | понять, можно ли оценить посадку серег |
| Размер мочки | small / medium / large / unknown | подобрать размер и вес серег |
| Тип мочки | attached / free / soft / unknown | подобрать посадку |
| Состояние мочки | not_stretched / slightly_stretched / stretched / unknown | не рекомендовать тяжелые серьги при риске перегруза |
| Количество видимых проколов | 0 / 1 / 2 / 3+ / unknown | учитывать сценарии сетов |
| Посадка текущих серег, если есть | good / low / stretched / unclear | оценить, какие серьги сядут лучше |
| Рекомендованный вес серег | light / light_medium / medium / avoid_heavy / unknown | фильтр по весу |
| Рекомендованный тип посадки | stud / english_lock / light_hook / clip / cuff / unknown | фильтр по замку |
| Риск тяжелых серег | low / medium / high | понижать тяжелые серьги в выдаче |

## Не выводить пользователю

- «у вас растянутая мочка»;
- «мочка слабая»;
- «прокол низкий» в оценочном виде.

## Можно выводить пользователю

- «лучше выбирать легкие серьги»;
- «аккуратная посадка будет смотреться гармоничнее»;
- «серьги среднего масштаба не перегрузят зону уха».

---

# 9. Шея и зона декольте

| Параметр | Возможные значения | Зачем нужен |
|---|---|---|
| Длина шеи | short / medium / long / unknown | подобрать длину колье |
| Видимость шеи | visible / partial / hidden | понять, можно ли анализировать зону колье |
| Визуальная хрупкость шеи | delicate / medium / expressive / unknown | подобрать масштаб колье |
| Рекомендованная длина колье | choker / short / medium / long | фильтр по длине |
| Риск визуально укоротить шею | low / medium / high | избегать неудачной длины |
| Нужен ли вертикальный акцент | yes / no / optional | выбрать подвески / вытянутые формы |

---

# 10. Зона акцента

AI должен определить, куда лучше ставить акцент.

| Параметр | Возможные значения | Зачем нужен |
|---|---|---|
| Главная зона акцента | earrings / necklace / rings / bracelets / mixed | определить первую категорию выдачи |
| Вторичная зона акцента | earrings / necklace / rings / bracelets / mixed | подобрать дополнительные категории |
| Стоит ли делать акцент у лица | yes / no / moderate | приоритет серег |
| Стоит ли делать акцент на шее | yes / no / moderate | приоритет колье |
| Стоит ли уводить акцент в руки | yes / no / moderate | приоритет колец / браслетов |

---

# 11. Итоговые рекомендации для подбора

После анализа система должна выдавать не только параметры, но и рекомендации для фильтрации товаров.

```json
{
  "recommendedCategories": ["earrings", "necklace", "rings"],
  "primaryCategory": "earrings",
  "recommendedScale": "medium",
  "recommendedEarringLength": ["short", "medium"],
  "recommendedEarringWeight": "light_medium",
  "recommendedNecklaceLength": ["short", "medium"],
  "recommendedShapes": ["oval", "drop", "soft_geometry", "clean_line"],
  "recommendedTextures": ["smooth", "delicate_hammered", "mirror"],
  "recommendedMetals": ["silver", "mixed"],
  "avoidAsPrimary": ["too_heavy", "too_tiny", "too_round"],
  "stylistSummaryInternal": "Средний масштаб, мягкая геометрия, легкая посадка серег, деликатный блеск."
}
```

---

# 12. Пример итоговой JSON-структуры для разработчика

```json
{
  "photoQuality": {
    "faceDetected": true,
    "singlePerson": true,
    "faceVisibleLarge": true,
    "earVisible": "partial",
    "neckVisible": true,
    "lightQuality": "good",
    "sharpness": "good",
    "filterDetected": false
  },
  "faceGeometry": {
    "faceShape": "oval",
    "faceLength": "balanced",
    "faceWidth": "balanced",
    "jawlineType": "soft",
    "cheekboneProminence": "medium",
    "chinType": "soft",
    "foreheadProportion": "balanced"
  },
  "appearanceScale": {
    "overallAppearanceScale": "medium",
    "featureScale": "medium",
    "visualWeightCapacity": "medium",
    "riskOfOverload": "medium"
  },
  "lineAnalysis": {
    "lineType": "soft_geometric",
    "dominantLineDirection": "elongated",
    "softnessLevel": "medium",
    "graphicLevel": "medium"
  },
  "colorAnalysis": {
    "eyeColor": "brown",
    "hairColor": "dark_brown",
    "hairDepth": "dark",
    "skinUndertone": "neutral",
    "contrastLevel": "medium",
    "recommendedMetals": ["silver", "mixed"]
  },
  "textureAnalysis": {
    "skinTextureVisual": "delicate_lively",
    "frecklesVisible": "none",
    "fineLinesVisible": "light",
    "recommendedTextures": ["smooth", "mirror", "delicate_hammered"]
  },
  "earAndLobeAnalysis": {
    "earVisibility": "both",
    "earlobeSize": "medium",
    "earlobeType": "free",
    "earlobeCondition": "not_stretched",
    "piercingCountVisible": 1,
    "recommendedEarringWeight": "light_medium",
    "recommendedEarringClosure": ["stud", "english_lock", "light_hook"]
  },
  "neckAnalysis": {
    "neckLength": "medium",
    "recommendedNecklaceLength": ["short", "medium"],
    "verticalAccentNeeded": false
  },
  "recommendations": {
    "primaryCategory": "earrings",
    "recommendedCategories": ["earrings", "necklace", "rings"],
    "recommendedScale": "medium",
    "recommendedShapes": ["oval", "drop", "soft_geometry", "clean_line"],
    "recommendedTextures": ["smooth", "mirror", "delicate_hammered"],
    "recommendedMetals": ["silver", "mixed"],
    "avoidAsPrimary": ["too_heavy", "too_tiny"]
  }
}
```

---

# 13. Важная пометка для разработчика

Все параметры выше — **внутренние**.

В пользовательском интерфейсе показываем не анализ, а результат:

> Вам подойдут украшения среднего масштаба, мягкой геометрии и деликатного блеска. Они поддержат линию лица и не перегрузят образ.

Пользователю нельзя показывать грубые, медицинские или оценочные формулировки.

# Photo Analysis Color Mapping Rules

## Назначение

Этот документ фиксирует rule-based логику, по которой photo-analysis переводит цветовые метрики внешности в палитру камней и стиль контраста.

Цель:
- сделать выбор `recommendedStoneIntensity` и `recommendedStonePalette` прозрачным;
- упростить калибровку пайплайна на реальных фото;
- исключить расхождения между `colorAnalysis`, `colorContrastAnalysis`, `recommendations` и `human_readable`.

## Источники сигналов

Палитра строится на базе нескольких групп признаков:

- `colorAnalysis.skinUndertone`
- `colorAnalysis.hairColor`
- `colorAnalysis.hairTone`
- `colorAnalysis.eyeColor`
- `colorAnalysis.contrastLevel`
- `colorContrastAnalysis.valueContrast`
- `colorContrastAnalysis.valueContrastBand`
- `colorContrastAnalysis.hueContrast`
- `colorContrastAnalysis.colorSeasonType`
- `colorContrastAnalysis.colorSubtype`
- `hairAnalysis.hairColorPrimary`
- `hairAnalysis.hairColorSecondary`

## Базовая логика интенсивности

### `recommendedStoneIntensity`

Интенсивность определяется в первую очередь по `valueContrast`:

- `valueContrast < 0.20` -> `pastel`
- `0.20 <= valueContrast < 0.45` -> `medium`
- `0.45 <= valueContrast < 0.70` -> `saturated`
- `valueContrast >= 0.70` -> `deep`

Дополнительные корректировки:

- `hueContrast = monochromatic` усиливает выбор в сторону более мягкой палитры;
- `hueContrast = complementary` или `triadic` допускает более насыщенные камни;
- тёплый подтон кожи и мягкий цветотип удерживают палитру от слишком тёмных решений;
- высокий контраст волос к коже допускает `saturated` и `deep`.

## Базовая логика палитры камней

### `recommendedStonePalette`

Палитра должна быть согласована с `recommendedStoneIntensity`.

Ожидаемая связка:

- `pastel` -> `["pastel", "soft", "peach"]`
- `medium` -> `["soft", "balanced", "warm"]`
- `saturated` -> `["rich", "saturated", "contrast"]`
- `deep` -> `["deep", "contrast", "dark"]`

Если итоговая палитра не пересекается с ожидаемым набором по интенсивности, это считается inconsistency и должно попадать в `analysis.consistencyChecks`.

## Влияние сезона

### Spring

- Базовое направление: светлее, теплее, чище
- Типичные палитры: `pastel`, `soft`, `peach`
- Неосновной выбор: слишком тёмные, ледяные и жёстко-контрастные камни

### Summer

- Базовое направление: холоднее, мягче, дымчатее
- Типичные палитры: `soft`, `balanced`, `cool`
- Неосновной выбор: слишком тёплые и оранжево-золотые оттенки

### Autumn

- Базовое направление: тёплые, плотные, природные оттенки
- Типичные палитры: `warm`, `rich`, `saturated`
- Неосновной выбор: ледяные бело-голубые и чрезмерно пастельные решения

### Winter

- Базовое направление: холодные, контрастные, глубокие оттенки
- Типичные палитры: `contrast`, `deep`, `dark`
- Неосновной выбор: размытые и слишком припылённые камни

## Влияние волос

Волосы влияют не напрямую, а через perceived contrast и temperature.

### Светлые волосы

Примеры:
- `hairColorPrimary = blond`
- `hairColorSecondary = ash | golden | neutral`

Эффект:
- чаще поддерживают `pastel` или `medium`;
- при `golden` сильнее поддерживают тёплые мягкие камни;
- при `ash` могут сдвигать палитру в более нейтральную или холодную сторону.

Типовой паттерн:
- `blond + golden + warm undertone + low contrast` -> `["pastel", "soft", "peach"]`

### Рыжие или медные волосы

Примеры:
- `hairColorPrimary = red`
- `hairColorSecondary = copper`

Эффект:
- повышают ощущение тепла и цветовой выразительности;
- при среднем и высоком контрасте допускают более плотную палитру;
- не обязаны автоматически вести к `deep`, если общая светлотная разница низкая.

Типовой паттерн:
- `red + copper + warm undertone + medium contrast` -> `["warm", "rich", "saturated"]`
- `red + copper + warm undertone + high contrast` -> `["rich", "contrast", "deep"]`

## Влияние цвета глаз

Цвет глаз работает как уточняющий, а не главный сигнал:

- `hazel` хорошо поддерживает тёплые и мягкие палитры;
- `brown` допускает как мягкие, так и насыщенные тёплые решения;
- `green` усиливает природные и контрастно-комплементарные схемы;
- `blue` и `gray` чаще поддерживают холодные и чистые палитры.

Если `eyeColor = unknown`, палитра не должна ломаться: решение принимается по коже, волосам и контрасту.

## Consistency Checks

После сборки ответа система должна проверять:

- `colorAnalysis.contrastLevel` vs `colorContrastAnalysis.valueContrastBand`
- `recommendedStoneIntensity` vs `recommendedStonePalette`
- `human_readable.color_type` vs `colorSeasonType + skinUndertone`
- `human_readable.style_type` vs `lineAnalysis.lineType + vibeAnalysis.primaryImpression`

Если есть расхождение, оно должно появиться в `analysis.consistencyChecks.notes`.

## Практический пример

Для кейса со светлой кожей, тёплым подтоном, низким контрастом и мягким spring-профилем:

- `skinUndertone = warm`
- `valueContrastBand = low`
- `colorSeasonType = spring`
- `colorSubtype = soft_spring`
- `hairColorPrimary = blond`
- `hairColorSecondary = copper | golden`

Ожидаемый результат:

- `recommendedStoneIntensity = pastel`
- `recommendedStonePalette = ["pastel", "soft", "peach"]`
- `recommendedContrastStyle = low_contrast`

Это предпочтительнее, чем старые `deep/contrast`, если формульный контраст действительно низкий.

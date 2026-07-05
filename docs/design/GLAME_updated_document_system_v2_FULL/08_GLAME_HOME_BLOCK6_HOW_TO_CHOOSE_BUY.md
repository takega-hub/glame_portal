# 08. GLAME — Home Block 6 / «Как выбрать и купить»

## Роль

6-й блок — финальный сервисный блок Главной.  
Он не ведет на отдельную сервисную страницу.  
Он сам закрывает финальный выбор на Главной.

Задачи:
- снять страх онлайн-покупки;
- дать 3 способа действия;
- показать сервисность GLAME;
- завершить Home точкой выбора.

---

## Заголовок

```text
Как выбрать
и купить
```

## Верхний текст

```text
Онлайн-заказ в GLAME не должен быть покупкой вслепую. Мы поможем выбрать украшение спокойно — до оплаты и во время примерки.
```

---

## 3 action-panels

### 01 Самостоятельно

Описание:

```text
Каталог, бренды и подборки.
```

Действие:

```dart
context.push('/catalog');
```

---

### 02 С живым стилистом

Описание:

```text
Онлайн или в пространстве.
```

Действие:

```dart
openStylistContact(source: 'home_block_6');
```

Статус зависит от МСК.

Рабочее время:

```text
10:00–20:00 по МСК
```

В рабочее время:

```text
На связи сейчас · до 20:00 по МСК
```

В нерабочее время:

```text
Сейчас не на связи · с 10:00 по МСК
```

---

### 03 Через AI-подбор

Описание:

```text
По фото, форме, масштабу и стилю.
```

Действие:

```dart
context.push('/selection/ai-photo');
```

Если пользователь не авторизован — authorization gate.

---

## Сервисная зона

Заголовок:

```text
Чтобы онлайн-покупка
была спокойной
```

Сервисная зона не кликабельна.

### 01 Примерка перед покупкой

```text
Курьер привозит изделия для примерки: вы выбираете и оплачиваете только то, что подошло, остальное возвращается с курьером.
```

### 02 Детали до заказа

```text
Уточним размер, длину, застёжку, цвет, фактуру, вес и масштаб изделия.
```

### 03 Гарантия и уход

```text
Расскажем условия по конкретному изделию и подскажем, как за ним ухаживать.
```

### 04 Поддержка и Клуб стильных

```text
Можно обратиться в GLAME после покупки. Покупки участвуют в программе лояльности.
```

---

## Visual direction

Финальный дизайн:
- mobile-first;
- graphite architectural background;
- volumetric GLAME-pattern / approved pattern only;
- no rotated pattern;
- no warm colors;
- no icons;
- radius 0;
- border 1 px;
- action-panels as primary CTA;
- service zone 2×2.

---

## Важные запреты

- Не делать переход на `/service/how-to-buy`.
- Не добавлять общую нижнюю CTA.
- Не дублировать AI внутри stylist bottom sheet.
- Не делать сервисные tiles кликабельными.
- Не превращать в FAQ.
- Не делать “4 шага покупки”.

---

## Payload для стилиста из блока 6

```json
{
  "source": "home_block_6",
  "scenario": "live_stylist",
  "created_at": "ISO_DATE",
  "working_hours_status": "open_or_closed",
  "user": {
    "is_authorized": true,
    "name": "string_or_null",
    "phone": "string_or_null",
    "city": "string_or_null"
  },
  "request": {
    "text": "string",
    "quick_tags": ["for_self", "gift", "look", "set", "try_in_space"],
    "favorite_product_ids": [],
    "source_product_id": null
  },
  "purchase_history": {
    "available": true,
    "last_purchases": [],
    "categories": [],
    "brands_or_lines": [],
    "metals_or_colors": [],
    "sizes": [],
    "average_item_price": null,
    "purchase_frequency": null,
    "gift_scenarios": [],
    "purchase_cities": []
  }
}
```

История покупок — внутренний контекст для стилиста, не публичный UI-блок.


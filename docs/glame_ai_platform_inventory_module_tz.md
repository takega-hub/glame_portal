# Финальное ТЗ для разработчика
## Модуль контроля закупок с AI-агентами внутри маркетинговой платформы GLAME

## 1. Цель
Добавить в существующую AI-платформу GLAME, которая сейчас сфокусирована на маркетинге, новый раздел **Inventory Control** для управления остатками, продажами, закупками, чисткой склада и связкой маркетинга со складом.

Система должна работать как встроенный операционный модуль внутри текущей маркетинговой платформы, а не как отдельный продукт.

Главная задача модуля:
- анализировать продажи и остатки;
- прогнозировать дефицит;
- формировать рекомендации по закупке;
- выявлять зависшие позиции;
- предлагать чистку склада;
- контролировать структуру ассортимента;
- рекомендовать товары для маркетингового продвижения с учетом текущего склада и концепции бренда.

---

## 2. Место модуля в платформе
### Новая структура платформы

### MARKETING
- Campaign Planner
- Content Planner
- CRM Communications
- Performance Analytics

### OPERATIONS
- Inventory Control
  - Dashboard
  - Sales & Stock
  - Reorder Recommendations
  - Stock Clearance
  - Assortment Structure
  - Marketing Inventory Link

---

## 3. Раздел Inventory Control

### 3.1 Dashboard
Главный экран раздела.

Отображаемые блоки:

#### Продажи
- Выручка
- Кол-во изделий
- Средний чек
- Длина чека
- Кол-во чеков
- Кол-во смен
- Средние продажи в смену
- Отставание / перевыполнение
- Трафик
- Выручка на вошедшего
- Конверсия план / факт

#### Остатки
- Количество SKU
- Общий остаток
- Среднее покрытие остатком
- Количество критических остатков
- Количество slow moving позиций

#### Закупки
- Рекомендуемый заказ
- Количество позиций к заказу
- Общая сумма заказа
- Критические позиции к дозаказу

#### Чистка склада
- Количество slow moving позиций
- Количество dead stock позиций
- Рекомендации по PROMO / BUNDLE / RELOCATION / WRITE_OFF

---

### 3.2 Sales & Stock
Основная аналитическая таблица.

Поля:
- Номенклатура
- Цвет
- Категория
- Продано
- Остаток
- Продажи в месяц
- Покрытие
- Статус

Формулы:

`sales_month = Продано / months_in_period`

`stock_cover = Остаток / sales_month`

Если `sales_month = 0`, статус должен определяться отдельно как `no_sales`.

---

### 3.3 Reorder Recommendations
Таблица рекомендаций по закупке.

Поля:
- Номенклатура
- Цвет
- Остаток
- Продажи в месяц
- Оптимальный остаток
- Заказать
- Статус

Формулы:

`optimal_stock = sales_month * 3`

`order_qty = optimal_stock - Остаток`

Если `order_qty < 0`, то `order_qty = 0`.

Позиции включаются в таблицу заказа только если:

`order_qty > 0`

---

### 3.4 Stock Clearance
Таблица для чистки склада.

Поля:
- Номенклатура
- Цвет
- Остаток
- Продажи в месяц
- Покрытие
- Рекомендация
- Причина

Базовые правила:

`stock_cover > 6 -> slow_moving`

`sales_month = 0 -> dead_stock`

Возможные рекомендации:
- PROMO
- BUNDLE
- RELOCATION
- WRITE_OFF

Ограничение:
система не должна автоматически рекомендовать вывод из ассортимента для позиций, которые поддерживают ядро матрицы или концепцию бренда.

---

### 3.5 Assortment Structure
Таблица структуры ассортимента.

Поля:
- Категория
- Продано
- Остаток
- Доля продаж
- Доля склада
- Целевая доля
- Отклонение
- Рекомендация

Целевая матрица задается вручную через админку.

Пример структуры:
- Серьги
- Браслеты
- Кольца
- Кулоны
- Каффы

Порог предупреждения:

`abs(category_share_stock - target_share) > 0.10`

Дополнительно:
- контроль по цветам;
- контроль количества SKU в категории;
- контроль концентрации продаж по top-10 позициям.

---

### 3.6 Marketing Inventory Link
Связующий блок маркетинга и закупок.

Система должна определять:
- какие товары нужно продвигать в Instagram;
- какие товары отдавать в email / SMS;
- какие товары выводить в промо;
- какие товары нельзя продвигать скидкой, чтобы не разрушать концепцию бренда.

Поля:
- Номенклатура
- Цвет
- Продажи в месяц
- Остаток
- Покрытие
- Группа
- Recommended channel

Группы:

#### GROWTH_PRODUCTS
`sales_month > 0.5 AND stock_cover <= 3`

#### INVENTORY_RELIEF
`stock_cover > 4 AND sales_month > 0.2`

#### PROMO_PRODUCTS
`stock_cover > 6`

#### PROTECT_PRODUCTS
`sales_month > 0.7 AND stock_cover <= 2`

Логика каналов:
- Instagram -> GROWTH_PRODUCTS
- Email / SMS -> INVENTORY_RELIEF
- Promotions -> PROMO_PRODUCTS

---

## 4. Источники данных
Система должна работать с таблицами / сущностями:

### products
Поля:
- Номенклатура
- Цвет
- Категория
- Бренд
- Коллекция
- Цена

### sales
Поля:
- Номенклатура
- Цвет
- Продано
- Период

### stock
Поля:
- Номенклатура
- Цвет
- Остаток

### promo_history
Поля:
- Номенклатура
- Цвет
- Дата акции
- Тип акции
- Скидка
- Продано в акции

### marketing_campaigns
Поля:
- Кампания
- Дата
- Тип
- Продвигаемые товары

Ключ объединения данных:
- Номенклатура
- Цвет

Важно: агент не должен придумывать названия, а использовать значения строго как в таблицах.

---

## 5. AI-агенты внутри модуля

### 5.1 Inventory Control Agent
Функции:
- объединяет sales и stock;
- считает продажи в месяц;
- считает покрытие;
- формирует рекомендации по заказу;
- определяет статусы остатков.

Статусы:
- `stock_cover < 1 -> critical_stock`
- `stock_cover < 2 -> reorder`
- `2 <= stock_cover <= 3 -> normal`
- `3 < stock_cover <= 6 -> overstock`
- `stock_cover > 6 -> slow_moving`

---

### 5.2 Clearance Agent
Функции:
- выявляет slow moving и dead stock;
- формирует предложения по чистке склада;
- предлагает PROMO / BUNDLE / RELOCATION / WRITE_OFF;
- учитывает защиту концепции бренда.

Правила:
- `sales_month = 0 AND stock_cover > 12 -> WRITE_OFF candidate`
- `sales_month > 0 AND stock_cover > 6 -> PROMO candidate`
- `sales_month > 0 AND stock_cover > 5 -> BUNDLE candidate`

---

### 5.3 Assortment Matrix Agent
Функции:
- анализирует структуру продаж и остатков по категориям;
- сравнивает с целевой матрицей;
- контролирует перекос по цветам;
- контролирует количество SKU;
- отслеживает концентрацию продаж.

Правила:
- `category_share_sales = sales_category / total_sales`
- `category_share_stock = stock_category / total_stock`
- предупреждение при отклонении > 10%
- предупреждение если `color_share > 0.75`
- предупреждение если `top10_sales_share > 0.6`

---

### 5.4 Merchandising Agent
Функции:
- определяет товары для витрины;
- определяет товары для кассовой зоны;
- формирует комплекты;
- назначает selling priority;
- предлагает позиции для ротации витрины.

Правила:
- `sales_month > median_sales AND stock > 3 -> DISPLAY`
- товары категорий серьги / кольца при `sales_month > 0.5 -> CHECKOUT`
- `stock_cover > 4 AND sales_month > 0.2 -> SELLING PRIORITY`
- `sales_month < 0.2 -> REMOVE`

---

### 5.5 Pricing Agent
Функции:
- определяет, где скидка не нужна;
- где нужна мягкая скидка;
- где нужна глубокая скидка;
- где лучше комплект вместо скидки;
- учитывает концепцию бренда и базовую матрицу.

Статусы:
- `NO DISCOUNT`
- `LIGHT DISCOUNT`
- `HEAVY DISCOUNT`
- `BUNDLE INSTEAD OF DISCOUNT`
- `HOLD PRICE`

Правила:
- `sales_month > 0.7 AND stock_cover <= 3 -> NO DISCOUNT`
- `sales_month > 0.2 AND stock_cover > 3 AND stock_cover <= 6 -> LIGHT DISCOUNT`
- `sales_month <= 0.2 AND stock_cover > 6 -> HEAVY DISCOUNT`

---

### 5.6 Marketing Inventory Agent
Функции:
- связывает маркетинговые кампании и склад;
- выбирает товары для продвижения с учетом покрытия и продаж;
- предлагает канал продвижения;
- определяет товары для разгрузки склада через маркетинг.

---

## 6. Учет концепции бренда
Система должна иметь отдельный флаг или справочник для товарных групп, которые нельзя автоматически уценивать или выводить из ядра матрицы.

Нужен параметр:
- `is_core_assortment`
- `supports_brand_concept`

Если товар относится к ядру или поддерживает концепцию бренда, система должна сначала рекомендовать:
- bundle
- relocation
- selling priority
- visual merchandising

И только после этого скидку или вывод.

---

## 7. Частота обновления
- Загрузка и пересчет данных: 1 раз в сутки
- Обновление дашборда: 1 раз в сутки
- Пересчет рекомендаций по закупке: 1 раз в сутки
- Пересчет рекомендаций по pricing: 1 раз в неделю
- Экстренный пересчет по slow moving и critical stock: ежедневно

---

## 8. API / сервисные методы

### `/inventory/report`
Возвращает:
- продажи
- остатки
- покрытие
- статусы
- критические позиции

### `/inventory/order`
Возвращает:
- таблицу рекомендованного заказа

### `/inventory/clearance`
Возвращает:
- slow moving
- dead stock
- рекомендации по чистке склада

### `/inventory/assortment`
Возвращает:
- структуру ассортимента
- доли по категориям
- доли по цветам
- предупреждения

### `/inventory/marketing-link`
Возвращает:
- товары для маркетинга
- recommended channel
- основание выбора

### `/pricing/report`
Возвращает:
- статус по ценам
- рекомендованную скидку
- рекомендации по комплектам / визуальному усилению

---

## 9. Требования к логике вывода
Система должна:
- возвращать структурированные таблицы;
- не придумывать названия товаров;
- использовать Номенклатура и Цвет строго как в таблицах;
- сохранять точные значения полей;
- поддерживать фильтрацию по периоду, категории, цвету, бренду, коллекции, магазину.

---

## 10. Что должно появиться в интерфейсе
### Новый раздел:
`Operations -> Inventory Control`

### Внутри раздела вкладки:
- Dashboard
- Sales & Stock
- Reorder Recommendations
- Stock Clearance
- Assortment Structure
- Marketing Inventory Link

---

## 11. Финальный результат для бизнеса
После внедрения модуль должен позволять:
- контролировать остатки и продажи в одном интерфейсе;
- получать ежедневные рекомендации по заказу;
- видеть позиции для чистки склада;
- контролировать перекосы по категории и цвету;
- использовать маркетинг для разгрузки склада;
- защищать концепцию бренда при промо, уценке и чистке склада.

---

# Финальные системные промпты для разработчика

## 1. SYSTEM PROMPT — Inventory Control Agent
```text
You are an inventory control agent integrated into a marketing analytics platform.

Your task is to analyze product sales and stock levels and provide inventory management recommendations.

You receive datasets:
sales
stock
products

Each product is identified by:
Номенклатура
Цвет

Rules:
1. Merge sales and stock datasets using keys:
   Номенклатура
   Цвет

2. Calculate:
   sales_month = Продано / months_in_period
   stock_cover = Остаток / sales_month
   optimal_stock = sales_month * 3
   order_qty = optimal_stock - Остаток

3. If order_qty < 0 then order_qty = 0.

4. Assign status:
   stock_cover < 1 -> critical_stock
   stock_cover < 2 -> reorder
   2 <= stock_cover <= 3 -> normal
   3 < stock_cover <= 6 -> overstock
   stock_cover > 6 -> slow_moving

5. Generate reorder recommendations only for items where order_qty > 0.

6. Return structured tables only.

7. Never invent product names.
Use values exactly as provided in dataset.
```

## 2. SYSTEM PROMPT — Clearance Agent
```text
You are an inventory optimization agent.

Your task is to detect slow moving inventory and propose warehouse clearance actions.

Use metrics:
sales_month = Продано / months_in_period
stock_cover = Остаток / sales_month

Rules:
If sales_month = 0 and stock_cover > 12 -> WRITE_OFF candidate
If sales_month > 0 and stock_cover > 6 -> PROMO candidate
If sales_month > 0 and stock_cover > 5 -> BUNDLE candidate

Never recommend removing products that belong to core assortment or support brand concept.

Output columns:
Номенклатура
Цвет
Остаток
Продажи в месяц
Покрытие
Recommendation
Reason

Recommendation must be one of:
PROMO
BUNDLE
RELOCATION
WRITE_OFF
```

## 3. SYSTEM PROMPT — Assortment Matrix Agent
```text
You are an assortment matrix management agent.

Your task is to analyze assortment structure and ensure that inventory composition follows the target assortment matrix.

You receive datasets:
products
sales
stock

Each product contains:
Номенклатура
Категория
Цвет

Tasks:
1. Aggregate sales by category.
2. Aggregate stock by category.
3. Calculate:
   category_share_sales = sales_category / total_sales
   category_share_stock = stock_category / total_stock
4. Compare values with target matrix.
5. If deviation exceeds 10% return a warning.
6. Aggregate sales by color.
7. Calculate color_share = sales_color / total_sales.
8. If color_share > 0.75 return warning.
9. Calculate top10_sales_share = sales_top10 / total_sales.
10. If top10_sales_share > 0.6 return warning.
11. Output structured tables only.
12. Do not invent product names.
Use values exactly as provided in dataset.
```

## 4. SYSTEM PROMPT — Merchandising Agent
```text
You are a merchandising optimization agent.

Your task is to analyze product sales and stock levels and recommend merchandising actions.

Input datasets:
products
sales
stock

Each product contains:
Номенклатура
Категория
Цвет

Tasks:
1. Calculate sales_month.
2. Identify products suitable for store display.
   Rule: sales_month > median_sales AND stock > 3 -> DISPLAY
3. Identify products suitable for checkout zone.
   Rule: category in (earrings, rings) AND sales_month > 0.5 -> CHECKOUT
4. Identify bundle opportunities.
   Rule: combine products from different categories with sales_month > 0.3.
5. Identify selling priority items.
   Rule: stock_cover > 4 AND sales_month > 0.2 -> SELLING PRIORITY
6. Identify products that should be removed from display.
   Rule: sales_month < 0.2 -> REMOVE
7. Return structured tables only.
8. Do not invent product names.
Use values exactly as provided in dataset.
```

## 5. SYSTEM PROMPT — Pricing Agent
```text
You are a pricing optimization agent.

Your task is to analyze inventory, sales, and stock coverage and generate pricing recommendations.

You work with datasets:
sales
stock
products
promo_history

Each product is identified by:
Номенклатура
Цвет

Responsibilities:
1. Merge datasets by:
   Номенклатура
   Цвет
2. Calculate:
   sales_month = Продано / months_in_period
   stock_cover = Остаток / sales_month
3. If sales_month = 0, classify product as no_sales.
4. Assign pricing status:
   NO DISCOUNT
   LIGHT DISCOUNT
   HEAVY DISCOUNT
   BUNDLE INSTEAD OF DISCOUNT
   HOLD PRICE
5. For core assortment products, prefer bundle, relocation, selling priority, visual merchandising before any price reduction.
6. Generate pricing recommendation table.
7. Do not invent product names.
Use values exactly as provided in dataset.
8. Return structured tables only.
```

## 6. SYSTEM PROMPT — Marketing Inventory Agent
```text
You are a marketing inventory optimization agent.

Your role is to connect marketing campaigns with inventory management.

Your tasks:
1. Analyze sales and stock data.
2. Calculate:
   sales_month = Продано / months_in_period
   stock_cover = Остаток / sales_month
3. Classify products into groups:
   GROWTH_PRODUCTS
   INVENTORY_RELIEF
   PROMO_PRODUCTS
   PROTECT_PRODUCTS
4. Recommend marketing channels:
   Instagram -> growth products
   Email / SMS -> inventory relief
   Promotions -> promo products
5. Output structured tables.
6. Never invent product names.
Use values exactly as provided in dataset.
```

---

# Финальные рабочие prompts

## Prompt — Reorder Recommendations
```text
Analyze inventory data and generate reorder recommendations.
Include only products where order_qty > 0.
Return columns:
Номенклатура
Цвет
Остаток
Продажи в месяц
Оптимальный остаток
Заказать
Sort by order_qty descending.
```

## Prompt — Stock Clearance
```text
Analyze inventory and detect slow moving items.
Rules:
stock_cover > 6
or
sales_month = 0
Return table:
Номенклатура
Цвет
Остаток
Продажи в месяц
Покрытие
Recommendation
Reason
```

## Prompt — Assortment Analysis
```text
Analyze assortment structure.
Return tables:
1. Sales distribution by category
2. Stock distribution by category
3. Sales distribution by color
4. Top selling concentration
Highlight deviations from target matrix.
```

## Prompt — Merchandising Recommendations
```text
Analyze inventory and sales.
Return merchandising recommendations:
DISPLAY
CHECKOUT
SELLING PRIORITY
REMOVE
Use product names exactly as provided.
```

## Prompt — Pricing Recommendations
```text
Analyze sales, stock, and pricing data.
Return pricing recommendations for each product.
Use statuses:
NO DISCOUNT
LIGHT DISCOUNT
HEAVY DISCOUNT
BUNDLE INSTEAD OF DISCOUNT
HOLD PRICE
Return columns:
Номенклатура
Цвет
Цена
Остаток
Продажи в месяц
Покрытие
Статус
Рекомендованная скидка
Рекомендация
```

## Prompt — Campaign Product Selection
```text
Select products for marketing campaign.
Rules:
Instagram -> growth products
Email -> inventory relief
Promotion -> promo products
Return columns:
Номенклатура
Цвет
Продажи в месяц
Остаток
Группа
Recommended channel
```


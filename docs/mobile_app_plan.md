# План реализации мобильного приложения GLAME (Flutter)

Этот документ фиксирует текущий прогресс по backend-API и оставшиеся задачи для выпуска Flutter-приложения (iOS/Android) на базе платформы.

## 1) Архитектура и роли

- **Платформа (portal)** — только для сотрудников/админов: администрирование контента приложения, доставки, заказов и т.п.
- **Мобильное приложение (Flutter)** — для покупателей: каталог, контент, профиль/лояльность, заказы, оплата, доставка.

## 2) Что уже готово (backend)

### 2.1 Контент приложения (для Home и разделов контента)

- Баннеры (с плейсментами и типом медиа): `GET /api/app/banners?placement=...`
  - `placement`: `home_hero`, `home_stories`, `splash`, `catalog_top`, `fashion_top`, `product_bottom`, `favorites_empty`
  - `media_type`: `image|video`, поле `video_url`
- Лукбуки: `GET /api/app/lookbooks`
- Акции: `GET /api/app/promotions`
- Новости: `GET /api/app/news`

Администрирование контента:
- `/api/admin/app/*` (баннеры/лукбуки/акции/новости + upload медиа)

### 2.2 Каталог

- Категории/разделы: `GET /api/catalog-sections/`
- Листинг товаров: `GET /api/products/paged`
- Карточка товара: `GET /api/products/{product_id}`
- Варианты товара: `GET /api/products/{product_id}/variants`
- Значения характеристик: `GET /api/products/characteristics/values`

### 2.3 Авторизация и кабинет покупателя

- Auth:
  - `POST /api/auth/login-by-card`
  - `POST /api/auth/refresh`
  - `GET /api/auth/me`
- Customer:
  - `GET/PUT /api/customer/profile`
  - `GET /api/customer/purchase-history`
  - `GET /api/customer/loyalty`
  - `GET/POST/DELETE /api/customer/saved-looks`

### 2.4 E-commerce: корзина, checkout, оплата (YooKassa)

Модели/таблицы:
- `carts`, `cart_items`, `orders`, `order_items`, `payments`

Корзина:
- `GET /api/cart`
- `POST /api/cart/items`
- `DELETE /api/cart/items/{item_id}`

Checkout и оплата:
- `POST /api/checkout`
  - создаёт `order` + `order_items`
  - создаёт платёж YooKassa
  - возвращает `confirmation_url` для открытия в WebView

Webhook YooKassa:
- `POST /api/webhooks/yookassa` — обновляет статусы `payments` и `orders`

Статусы платежа/заказа:
- `GET /api/orders` — список
- `GET /api/orders/{order_id}` — деталка + items + payment
- `GET /api/orders/{order_id}/payment-status` — быстрый polling
- `GET /api/payments/{payment_id}`
- `POST /api/payments/{payment_id}/refresh` — ручной refresh статуса через YooKassa API
- `GET /api/payments/last-active` — восстановление платёжного flow

### 2.5 Доставка (СДЭК)

Flutter endpoints (для выбора доставки):
- Поиск города: `GET /api/shipping/cdek/cities?q=...`
- Список ПВЗ: `GET /api/shipping/cdek/pvz?city_code=...`
- Расчёт доставки: `POST /api/shipping/cdek/calculate`

Создание отправления после оплаты:
- `POST /api/shipping/cdek/shipments` — создаёт отправление в СДЭК (или сохраняет "черновик", если включено `Не отправлять заказы в СДЭК`)

Трекинг доставки для покупателя:
- `GET /api/shipping/cdek/track/{order_id}?refresh=true|false` — получает/обновляет статус в СДЭК и кэширует в `orders.meta.cdek.tracking`

Админка доставки:
- UI: `/admin/shipping`
- API:
  - `GET/PUT /api/admin/shipping/cdek/settings`
  - `GET /api/admin/shipping/cdek/options` (dropdown options)
  - `GET /api/admin/shipping/cdek/search/cities`
  - `GET /api/admin/shipping/cdek/search/offices`

## 3) Что НЕ хватает для полноценного mobile MVP

### 3.1 Wishlist товаров (отдельно от saved looks)

Сейчас есть только `saved looks`. Для wishlist по товарам нужно:
- модели и API: `GET/POST/DELETE /api/wishlist/products`
- (опционально) синхронизация с сайтом

### 3.2 Доставка в checkout (интеграция расчёта/выбора)

Сейчас `checkout` принимает `delivery_amount` и `delivery` как произвольный JSON.
Чтобы сделать flow полностью управляемым:
- добавить серверную валидацию выбранного способа доставки
- добавить расчёт `delivery_amount` на backend (по выбранному тарифу/ПВЗ/адресу) вместо передачи числа с клиента

### 3.3 Сценарии оплаты

- deep link `return_url` для приложения (например `glame://payment-return`)
- обработка отмены/ошибки в WebView
- подтверждение заказа в UI по `/payment-status` или `/refresh`

### 3.4 Создание отправления: данные получателя/адреса

Сейчас для отправления используются `order.contact` и `order.delivery`.
Нужно закрепить контракт в Flutter:
- какие поля обязательны (`fio/phone/email`, `address` или `pvz_code`)
- формат хранения в `order.delivery` и `order.contact`

### 3.5 Оформление заказа (серверный контракт)

Сейчас `checkout` принимает произвольные поля и не фиксирует тип доставки как строгую схему.
Нужно формализовать:
- схема `delivery`: `type` (`pvz|courier`), `to_city_code`, `pvz_code` (для pvz) или `address` (для courier)
- схема `contact`: `name`, `phone`, `email` (email опционально)
- валидация на backend, чтобы приложение не могло сохранить неконсистентный заказ

### 3.6 Расчёт стоимости доставки на backend (единый источник истины)

Сейчас приложение передаёт `delivery_amount` числом.
Чтобы исключить подмену и рассинхрон:
- добавить режим, когда backend сам считает `delivery_amount` по выбранному тарифу/ПВЗ/адресу через СДЭК
- применять настройки из админки: `pricing_mode` (калькулятор/бесплатно/фикс), `markup`, `free_shipping_threshold`, `ship_days`
- вернуть в ответе checkout рассчитанные поля (включая "почему так")

### 3.7 Жизненный цикл заказа и статусы

Сейчас есть базовые статусы `pending/paid/canceled`.
Для мобильного UX обычно нужно минимум:
- `payment_pending` (создан, но ещё не оплачен)
- `paid` (оплата подтверждена)
- `shipping_created` (создано отправление в СДЭК)
- `in_transit` (в пути)
- `delivered` (доставлено)
- `canceled` (отменено)

Также нужны действия:
- отмена заказа пользователем до отправки (и правила отмены/возврата)

### 3.8 Возвраты/рефанды (если требуются)

Если бизнес-процесс предусматривает возврат денег:
- endpoint для инициирования возврата
- хранение статусов refund
- правила: до/после отгрузки, частичный/полный

### 3.9 Резервирование наличия

Сейчас заказ создаётся на основе `products.price`, но резерв по складу не фиксируется.
Для предотвращения оверсейла:
- стратегия резерва: при `checkout` или при `paid`
- проверка доступности перед оплатой и перед созданием отправления

### 3.10 Push/уведомления о заказах

Для конверсии и удержания:
- события: оплата успешна/неуспешна, отправлено, прибыло в ПВЗ, доставлено
- интеграция: Firebase Cloud Messaging
- хранение device token’ов и подписок

### 3.11 Улучшения API под Flutter (качество SDK)

- добавить строгие схемы ответов (Pydantic модели) вместо `Dict[str, Any]` там, где критично
- добавить codebook’и (списки) для справочников доставки
- добавить эндпоинты для "Мои адреса" (если нужен address book)

## 4) План работ по Flutter (высокоуровнево)

1. **Auth + профиль**: login-by-card, /me, профиль/лояльность.
2. **Контент Home**: баннеры по placement + лукбуки/новости/акции.
3. **Каталог**: категории → листинг → карточка товара.
4. **Корзина**: локальный UI + синк с `/api/cart`.
5. **Checkout + оплата YooKassa**: `/api/checkout` → WebView confirmation_url → статус.
6. **Доставка СДЭК**: выбор города/ПВЗ, расчёт, сохранение в заказ, создание отправления после `paid`.
7. **Трекинг доставки**: /track в “Мои заказы”.

## 5) Примечания по конфигурации

- YooKassa ключи хранятся только на backend (env), в приложение не попадают.
- CDEK ключи хранятся только на backend (env), в админке отображаются маской.

## 6) Flutter проект (репозиторий)

В репозитории создан стартовый Flutter-проект:
- `mobile/glame_app`

Быстрый старт (локально):
- `flutter pub get`
- `flutter analyze`

Конфиг API:
- через `--dart-define=API_BASE_URL=...` (например, `http://localhost:8000`)
- `API_PREFIX` по умолчанию `/api`

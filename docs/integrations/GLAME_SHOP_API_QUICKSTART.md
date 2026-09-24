# GLAME Shop API: краткая инструкция

## Подключение

- Production API: `https://portal.glamejewelry.ru/api`
- Резервный same-origin адрес витрины: `https://app.glamejewelry.ru/api`
- Формат данных: JSON, UTF-8.
- Изображения в ответах могут быть абсолютными URL или путями `/static/...` и `/uploads/...`. Относительный путь нужно соединять с `https://portal.glamejewelry.ru`.
- Денежные поля (`price`, `subtotal`, `total`, скидки) передаются целыми числами в копейках. `739000` = `7 390 RUB`.

Публичного Swagger сейчас нет: `/docs` и `/openapi.json` закрыты на внешнем контуре. Источник истины для существующего клиента находится в `mobile/glame_app/lib/src/features/*/*_api.dart`.

## Авторизация клиента

Телефон всегда нормализовать к формату `+7XXXXXXXXXX`.

### Вход по паролю

`POST /auth/login`, тип тела `application/x-www-form-urlencoded`:

```text
username=+79781234567&password=secret
```

Ответ:

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "token_type": "bearer"
}
```

Для защищённых запросов передавать `Authorization: Bearer <access_token>`.

При `401` один раз вызвать:

```http
POST /auth/refresh?refresh_token=<refresh_token>
```

Сохранить новую пару токенов и повторить исходный запрос. Если refresh тоже вернул `401`, очистить сессию.

Дополнительные сценарии:

- `POST /auth/register-phone` — JSON: `phone`, `password`, `full_name`; необязательно `email`, `birth_date`, `referral_code`.
- `POST /auth/request-otp` — `{"phone":"+79781234567"}`.
- `POST /auth/login-otp` — `{"phone":"+79781234567","code":"123456"}`.
- `GET /auth/me` — текущий пользователь.

## Каталог

Основной маршрут:

```http
GET /products/paged?skip=0&limit=24&has_images=true
```

Ответ: `items`, `total`, `skip`, `limit`.

Поддерживаемые фильтры: `category`, `brand`, `search`, `price_min`, `price_max`, `sort`, `in_stock`, `store_id`, `material`, `vstavka`, `pokrytie`, `razmer`, `tip_zamka`, `color`, `specs`.

Другие маршруты:

- `GET /products/{product_id}` — карточка товара.
- `GET /products/{product_id}/variants` — базовый товар и варианты.
- `GET /products/{product_id}/recommendations` — похожие товары.
- `GET /products/characteristics/values` — значения фильтров.
- `GET /catalog-sections` — категории витрины.
- `GET /app/stores`, `/app/home-slides`, `/app/lookbooks`, `/app/news`, `/app/promotions` — публичный контент приложения.
- `GET /looks/feed` — образы.

Не определять наличие только по родительской карточке: API агрегирует варианты и возвращает `stock`. Для выбора цвета/размера использовать конкретный `product_id` из `/products/{id}/variants`.

## Корзина и заказ

Корзина серверная и доступна только авторизованному пользователю:

- `GET /cart` — состав и рассчитанные итоги.
- `POST /cart/items` — `{"product_id":"uuid","quantity":1}`.
- `PUT /cart/items/{item_id}` — `{"quantity":2}`; значение `0` удаляет позицию.
- `DELETE /cart/items/{item_id}` — удалить позицию.

Всегда отображать итог из `GET /cart -> totals`. Не пересчитывать акции на клиенте: сервер учитывает действующие акции, включая механику `3=2`.

Оформление:

```http
POST /checkout
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "return_url": "https://other-app.example/payment-result",
  "payment_method": "card",
  "delivery": {},
  "contact": {
    "name": "Имя клиента",
    "phone": "+79781234567",
    "email": "client@example.com"
  },
  "delivery_amount": 0,
  "use_bonus_points": 0,
  "use_glm_amount": 0,
  "gift_certificate": null,
  "meta": {
    "source": "other_app"
  }
}
```

`payment_method`: `card` или `cod`. Использовать URL оплаты и итоговые суммы только из ответа `/checkout`.

## Правила интеграции

1. Не обращаться из клиентского приложения к `/admin/*`, синхронизации 1С и внутренним маршрутам.
2. Не хранить пароль; хранить access/refresh токены в защищённом хранилище устройства.
3. Обрабатывать `400`, `401`, `404`, `409`, `422`, `429` и `5xx`; текст ошибки обычно находится в поле `detail`.
4. Добавить debounce 400-500 мс для поиска и отменять предыдущий запрос.
5. Пагинацию строить по `skip`, `limit`, `total`; максимальный `limit` каталога — 100.
6. Перед разработкой платёжного сценария согласовать `return_url`, CORS/deep links и идентификатор источника в `meta.source`.


# Подарочные сертификаты GLAME: интеграция с Tilda

## Назначение

Контракт позволяет сайту GLAME на Tilda проверить сертификат, оплатить им заказ полностью или частично, сохранить остаток, отменить резерв и вернуть сумму на сертификат.

Все суммы передаются в копейках: `930000` означает `9 300 ₽`. Production API: `https://portal.glamejewelry.ru/api`.

## Архитектура и безопасность

```text
Корзина Tilda -> public API GLAME -> резерв -> GLAME checkout -> ЮKassa
Webhook ЮKassa -> GLAME -> штатный OData 1С
```

Штатную интеграцию ЮKassa в Tilda не менять. Для сертификата в существующую
корзину добавляется отдельная кнопка `Оплатить с сертификатом`; при частичной
оплате она направляет покупателя в ЮKassa только на остаток. Не создавать в
Tilda «Универсальную платежную систему»: этот экран предназначен для заявки
разработчика отдельной платёжной системы и требует модерации.

Не хранить секреты в JavaScript Tilda. Публичные `validate` и `reserve` доступны только для доменов из `TILDA_GIFT_CERTIFICATE_ALLOWED_ORIGINS`, ограничены rate limit и используют одноразовый короткоживущий `validation_token`. Внутренние методы вызываются только серверным мостом с заголовками:

```http
Authorization: Bearer <TILDA_GIFT_CERTIFICATE_INTERNAL_SECRET>
Idempotency-Key: <UUID>
Content-Type: application/json
```

В заказ Tilda, письма, аналитику и логи нельзя передавать номер сертификата. В ответах после проверки использовать только маску. Для Tilda сертификат проверяется только по номеру; PIN не запрашивается и не передается.

## Правила

1. 1С является источником истины для серий, признака продажи и остатка.
2. Сертификаты бессрочные: `expires_at = null`.
3. Допускается частичная оплата; сдача не выдается.
4. Сертификатом нельзя купить другой подарочный сертификат.
5. Применяемая сумма не превышает доступный остаток, сумму заказа после скидок и запрошенную сумму.
6. Изменение корзины отменяет проверку и резерв.
7. Повторный запрос или webhook не могут создать второе списание.

## API

### Проверка сертификата

```http
POST /public/tilda/gift-certificates/validate
```

```json
{
  "number": "GLM-2026-ABCD-EF12-10000",
  "cart_total": 1250000,
  "cart_fingerprint": "sha256:normalized-cart"
}
```

Ответ `200`:

```json
{
  "valid": true,
  "certificate_mask": "GLM-2026-****-10000",
  "available_amount": 1000000,
  "applicable_amount": 1000000,
  "amount_due": 250000,
  "currency": "RUB",
  "validation_token": "short-lived-single-use-token",
  "validation_expires_at": "2026-09-30T12:05:00Z"
}
```

Запрос не изменяет остаток. Неизвестный номер сначала ищется в 1С и импортируется либо обновляется локально. В ответ нельзя включать полный номер, `Ref_Key` 1С или необработанные ошибки инфраструктуры.

### Резервирование

```http
POST /public/tilda/gift-certificates/reserve
Idempotency-Key: <UUID>
```

```json
{
  "validation_token": "short-lived-single-use-token",
  "amount": 1000000,
  "tilda_order_id": "1234567890",
  "cart_total": 1250000,
  "cart_fingerprint": "sha256:normalized-cart"
}
```

Ответ `200`:

```json
{
  "operation_id": "f4da3fd7-8b72-4dc5-a64b-5b64f2b76bfa",
  "certificate_mask": "GLM-2026-****-10000",
  "applied_amount": 1000000,
  "amount_due": 250000,
  "status": "reserved",
  "reservation_expires_at": "2026-09-30T12:30:00Z"
}
```

Срок резерва без оплаты — 30 минут (`GIFT_CERTIFICATE_RESERVATION_TTL_MINUTES`). Повторный запрос с тем же `tilda_order_id` возвращает существующий резерв. Параллельные резервы блокируются транзакционно. После создания платежа ЮKassa резерв сохраняется до финального статуса: `succeeded` подтверждает списание, `canceled` освобождает сумму, а `pending` продлевает резерв. При изменении `cart_total` или `cart_fingerprint` токен и прежний резерв недействительны. Если в корзине есть подарочный сертификат как товар, его стоимость исключается из применяемой суммы.

### Checkout GLAME для корзины Tilda

Публичный маршрут объединяет резервирование и переход в ЮKassa. Доступен
только с разрешённых доменов Tilda и не принимает номер или PIN: вместо них
используется короткоживущий `validation_token` из предыдущей проверки.

```http
POST /public/tilda/gift-certificates/checkout
Idempotency-Key: <UUID>
```

```json
{
  "validation_token": "short-lived-single-use-token",
  "amount": 1000000,
  "checkout_id": "a3a0420e-56cc-40ce-a955-8fb90c9a9b39",
  "cart_total": 1250000,
  "cart_fingerprint": "sha256:normalized-cart",
  "return_url": "https://glamejewelry.ru/catalog?glame_certificate_checkout=...",
  "items": [{"sku": "GL10050", "quantity": 1, "unit_price": 1250000}]
}
```

Для частичной оплаты ответ содержит `confirmation_url` ЮKassa, созданный на
`amount_due`. Для полной оплаты ответ возвращает `status: paid` без перехода
в ЮKassa. Вебхук ЮKassa читает статус платежа через API ЮKassa, находит резерв
по `payment_id` и вызывает подтверждение списания ровно один раз. Статус после
возврата покупателя проверяется через:

```http
GET /public/tilda/gift-certificates/checkout/{checkout_id}
```

Готовый изолированный блок интерфейса: `docs/integrations/tilda-gift-certificate-cart.js`.
Его добавляют в общий Footer Tilda только после теста на предпросмотре. Он не
заменяет стандартную кнопку оформления и не меняет штатную ЮKassa.

### Подтверждение списания

Вызывается серверным мостом только после webhook `succeeded` от ЮKassa либо после подтвержденного заказа с `amount_due = 0`.

```http
POST /internal/tilda/gift-certificates/confirm
Authorization: Bearer <TILDA_GIFT_CERTIFICATE_INTERNAL_SECRET>
Idempotency-Key: <UUID>
```

```json
{
  "operation_id": "f4da3fd7-8b72-4dc5-a64b-5b64f2b76bfa",
  "tilda_order_id": "1234567890",
  "payment_status": "succeeded",
  "payment_id": "yookassa-or-tilda-payment-id",
  "order_amount": 1250000,
  "payment_amount": 250000,
  "items": [{"sku": "GL10050", "quantity": 1, "unit_price": 1250000}]
}
```

```json
{
  "operation_id": "f4da3fd7-8b72-4dc5-a64b-5b64f2b76bfa",
  "status": "confirmed",
  "certificate_mask": "GLM-2026-****-10000",
  "redeemed_amount": 1000000,
  "balance_amount": 0,
  "sync_status": "synced"
}
```

Backend финализирует резерв ровно один раз, пишет журнал операции и через OData создаёт штатный документ `СписаниеПроданныхПодарочныхСертификатов` в 1С. В документ передаётся остаток после частичного списания, а платформа после проведения сверяет его с регистром 1С. Одного изменения флага `Продан` недостаточно. Если 1С недоступна после подтвержденной оплаты, заказ не отменяется: операция записывается как `pending_sync` и повторяется фоново без повторного списания.

### Освобождение резерва

Используется при отмене заказа, `canceled`/`failed` платеже или ошибке до подтверждения. Просроченные резервы освобождаются фоновым заданием.

```http
POST /internal/tilda/gift-certificates/release
Authorization: Bearer <TILDA_GIFT_CERTIFICATE_INTERNAL_SECRET>
Idempotency-Key: <UUID>
```

```json
{
  "operation_id": "f4da3fd7-8b72-4dc5-a64b-5b64f2b76bfa",
  "tilda_order_id": "1234567890",
  "reason": "payment_canceled"
}
```

Допустимые причины: `checkout_abandoned`, `payment_canceled`, `payment_failed`, `order_canceled`, `reservation_expired`. Движение в 1С при release не создается.

### Возврат на сертификат

Поддерживает полный и частичный возврат, всегда связан с исходным списанием.

```http
POST /internal/tilda/gift-certificates/refund
Authorization: Bearer <TILDA_GIFT_CERTIFICATE_INTERNAL_SECRET>
Idempotency-Key: <UUID>
```

```json
{
  "original_operation_id": "f4da3fd7-8b72-4dc5-a64b-5b64f2b76bfa",
  "tilda_order_id": "1234567890",
  "refund_id": "tilda-refund-123",
  "amount": 200000,
  "reason": "returned_goods"
}
```

Полный возврат отменяет проведение исходного документа списания через OData `Unpost`, а не создаёт второе списание. Частичный возврат пока не поддерживается: он требует отдельного проверенного сценария корректировки исходного документа. `refund_id` и `Idempotency-Key` предотвращают повторную отмену.

### Статус операции

```http
GET /internal/tilda/gift-certificates/operations/{operation_id}
Authorization: Bearer <TILDA_GIFT_CERTIFICATE_INTERNAL_SECRET>
```

```json
{
  "operation_id": "f4da3fd7-8b72-4dc5-a64b-5b64f2b76bfa",
  "type": "redeem",
  "status": "confirmed",
  "sync_status": "synced",
  "tilda_order_id": "1234567890",
  "certificate_mask": "GLM-2026-****-10000",
  "amount": 1000000,
  "last_sync_attempt_at": "2026-09-30T12:05:03Z",
  "error": null
}
```

## Сценарии Tilda

**Полная оплата:** `validate` -> `reserve` -> создать заказ без ЮKassa -> `confirm` -> показать успех.

**Частичная оплата:** `validate` -> `reserve` -> отправить в ЮKassa только `amount_due` -> по webhook `succeeded` вызвать `confirm`; по `canceled`/`failed` вызвать `release`.

Не доверять редиректу покупателя из ЮKassa. Если платёж прошел, но `confirm` не ответил, серверный мост повторяет тот же запрос либо читает статус операции.

В заказ Tilda передавать только `gift_certificate_applied`, маску номера, примененную сумму, `operation_id` и статус.

## Учёт 1С и данные GLAME

Для сертификата хранятся: нормализованный номер, источник (`platform`/`onec`), ссылки на серию и номенклатуру 1С, номинал, доступный/зарезервированный остаток, дата последней синхронизации и `sync_status` (`synced`, `pending_sync`, `sync_error`). PIN, если он используется в нативном приложении, не участвует в Tilda-контуре.

Журнал каждой операции хранит `operation_id`, `idempotency_key`, тип (`reserve`, `redeem`, `release`, `refund`), сумму, номер заказа Tilda, ссылку серии и документа 1С, статус синхронизации и безопасный текст ошибки. На идемпотентный ключ нужен уникальный индекс.

Технические имена документов и регистров списания 1С определяются по актуальному `$metadata` рабочей базы. В текущей базе используется `Document_СписаниеПроданныхПодарочныхСертификатов`; необработанные ответы 1С не отдаются в Tilda.

## Ошибки и проверка

| HTTP | Значение |
| --- | --- |
| `400`, `422` | Неверная сумма, корзина или статус сертификата. |
| `401`, `403` | Нет доступа к внутреннему API. |
| `404` | Не найдены серия, резерв или операция. |
| `409` | Повтор с другим телом; запросить статус операции. |
| `410` | Резерв или токен проверки истек. |
| `429` | Превышен лимит проверок номера сертификата. |
| `502`, `503` | 1С временно недоступна; не создавать новый резерв, проверить статус оплаченной операции. |

Автотесты должны покрывать импорт серии 1С, проверку Tilda только по номеру, полную/частичную оплату, запрет покупки сертификата сертификатом, отмену, истечение резерва, возврат, параллельные резервы, повтор webhook, `pending_sync` и отсутствие номера в открытых данных.

## Конфигурация

```env
ONEC_GIFT_CERTIFICATES_ENABLED=true
ONEC_API_URL=
ONEC_API_TOKEN=
GIFT_CERTIFICATE_SECRET=
GIFT_CERTIFICATE_RESERVATION_TTL_MINUTES=30
GIFT_CERTIFICATE_PIN_REQUIRED_FOR_NEW=true
TILDA_GIFT_CERTIFICATE_ALLOWED_ORIGINS=https://glamejewelry.ru,https://www.glamejewelry.ru
TILDA_GIFT_CERTIFICATE_INTERNAL_SECRET=
ONEC_GIFT_CERTIFICATE_OPERATIONS_URL=
```

`ONEC_GIFT_CERTIFICATE_OPERATIONS_URL` оставляем пустым: тогда платформа использует штатный OData 1С. Переменная нужна только если в будущем появится отдельный 1С HTTP-сервис.

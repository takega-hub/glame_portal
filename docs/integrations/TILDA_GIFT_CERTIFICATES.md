# Подарочные сертификаты GLAME: интеграция с Tilda

## Назначение

Контракт позволяет сайту GLAME на Tilda проверить сертификат, оплатить им заказ полностью или частично, сохранить остаток, отменить резерв и вернуть сумму на сертификат.

Все суммы передаются в копейках: `930000` означает `9 300 ₽`. Production API: `https://portal.glamejewelry.ru/api`.

## Архитектура и безопасность

```text
Форма Tilda -> public API GLAME -> резерв
Webhook Tilda/ЮKassa -> internal API GLAME -> штатный OData 1С
```

Не хранить секреты в JavaScript Tilda. Публичные `validate` и `reserve` доступны только для доменов из `TILDA_GIFT_CERTIFICATE_ALLOWED_ORIGINS`, ограничены rate limit и используют одноразовый короткоживущий `validation_token`. Внутренние методы вызываются только серверным мостом с заголовками:

```http
Authorization: Bearer <TILDA_GIFT_CERTIFICATE_INTERNAL_SECRET>
Idempotency-Key: <UUID>
Content-Type: application/json
```

Номер и PIN нельзя передавать в заказ Tilda, письма, аналитику и логи. В ответах после проверки использовать только маску. PIN передается только по HTTPS и хранится в GLAME лишь как хеш. Для старых серий 1С без PIN проверка возможна только по номеру.

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
  "pin": "123456",
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

Запрос не изменяет остаток. Неизвестный номер сначала ищется в 1С и импортируется либо обновляется локально. В ответ нельзя включать полный номер, PIN, `Ref_Key` 1С или необработанные ошибки инфраструктуры.

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

Срок резерва — 30 минут (`GIFT_CERTIFICATE_RESERVATION_TTL_MINUTES`). Повторный запрос с тем же `tilda_order_id` возвращает существующий резерв. Параллельные резервы блокируются транзакционно. При изменении `cart_total` или `cart_fingerprint` токен и прежний резерв недействительны. Если в корзине есть подарочный сертификат как товар, его стоимость исключается из применяемой суммы.

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

Возврат не включается до отдельной проверки штатного OData-сценария отмены исходного документа списания. Платформа не создаёт для возврата второй документ списания: это могло бы уменьшить баланс повторно. `refund_id` и `Idempotency-Key` сохраняются для будущей безопасной реализации отмены.

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

Для сертификата хранятся: нормализованный номер, хеш PIN, источник (`platform`/`onec`), ссылки на серию и номенклатуру 1С, номинал, доступный/зарезервированный остаток, дата последней синхронизации и `sync_status` (`synced`, `pending_sync`, `sync_error`).

Журнал каждой операции хранит `operation_id`, `idempotency_key`, тип (`reserve`, `redeem`, `release`, `refund`), сумму, номер заказа Tilda, ссылку серии и документа 1С, статус синхронизации и безопасный текст ошибки. На идемпотентный ключ нужен уникальный индекс.

Технические имена документов и регистров списания 1С определяются по актуальному `$metadata` рабочей базы. В текущей базе используется `Document_СписаниеПроданныхПодарочныхСертификатов`; необработанные ответы 1С не отдаются в Tilda.

## Ошибки и проверка

| HTTP | Значение |
| --- | --- |
| `400`, `422` | Неверная сумма, корзина, PIN или статус сертификата. |
| `401`, `403` | Нет доступа к внутреннему API. |
| `404` | Не найдены серия, резерв или операция. |
| `409` | Повтор с другим телом; запросить статус операции. |
| `410` | Резерв или токен проверки истек. |
| `429` | Превышен лимит проверок номера/PIN. |
| `502`, `503` | 1С временно недоступна; не создавать новый резерв, проверить статус оплаченной операции. |

Автотесты должны покрывать импорт серии 1С, старую серию без PIN, неверный PIN нового сертификата, полную/частичную оплату, запрет покупки сертификата сертификатом, отмену, истечение резерва, возврат, параллельные резервы, повтор webhook, `pending_sync` и отсутствие номера/PIN в открытых данных.

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

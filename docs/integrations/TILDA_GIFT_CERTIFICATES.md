# Подарочные сертификаты GLAME: Tilda ↔ портал ↔ 1С

## Контур

```text
Корзина Tilda → public API портала → резерв сертификата
Webhook Tilda/ЮKassa → server-to-server мост → internal API портала → 1С
```

1С остаётся источником истины для серии, продажи и движения по сертификату.
Все суммы в API передаются в копейках.

## Маршруты

| Метод | Назначение |
| --- | --- |
| `POST /api/public/tilda/gift-certificates/validate` | Проверяет номер/PIN и выдаёт одноразовый токен проверки на 5 минут. |
| `POST /api/public/tilda/gift-certificates/reserve` | Резервирует сумму на 30 минут. Нужен `Idempotency-Key`. |
| `POST /api/internal/tilda/gift-certificates/confirm` | Подтверждает списание после `succeeded` в ЮKassa или при полной оплате сертификатом. |
| `POST /api/internal/tilda/gift-certificates/release` | Освобождает резерв при отмене или ошибке платежа. |
| `POST /api/internal/tilda/gift-certificates/refund` | Возвращает полную либо частичную сумму на сертификат. |
| `GET /api/internal/tilda/gift-certificates/operations/{operation_id}` | Возвращает статус операции для повторной доставки webhook. |

Публичные методы разрешены только для `TILDA_GIFT_CERTIFICATE_ALLOWED_ORIGINS` и ограничены по частоте. Внутренние требуют:

```http
Authorization: Bearer <TILDA_GIFT_CERTIFICATE_INTERNAL_SECRET>
Idempotency-Key: <UUID>
```

## Поведение корзины

- Полная оплата: `validate → reserve → создать заказ без ЮKassa → confirm`.
- Частичная оплата: `validate → reserve → передать в ЮKassa только amount_due → confirm` после webhook `succeeded`.
- При `canceled` или `failed` серверный мост вызывает `release`.
- Возврат пользователя с платёжной страницы не является подтверждением: используется только webhook и повторный запрос статуса операции.
- В Tilda разрешено сохранять только маску номера, `operation_id`, применённую сумму и статус. Номер и PIN не попадают в заказ, почту, аналитику или логи.

## Ограничения

- Сертификаты бессрочные.
- Старые серии из 1С без PIN проверяются по номеру; при первом обращении серия импортируется в портал.
- Новый сертификат с PIN требует PIN.
- Сертификат нельзя применять к покупке другого сертификата.
- Любое изменение корзины требует новой проверки и резерва.
- Повторный запрос с тем же `Idempotency-Key` возвращает прежний результат; другой запрос с тем же ключом получает `409`.

## 1С

В портале уже реализованы поиск серии `Catalog_СерииНоменклатуры` и импорт её номинала из номенклатуры.
Для проведения списания/возврата нужен утверждённый endpoint моста 1С, заданный в `ONEC_GIFT_CERTIFICATE_OPERATIONS_URL`. Прямого универсального OData-документа для движений подарочных сертификатов в УНФ нет: его нельзя угадывать по русскому названию. Пока endpoint не задан или 1С временно недоступна, успешное списание сохраняется в статусе `pending_sync` и безопасно повторяется фоновым заданием.

## Конфигурация

```env
ONEC_GIFT_CERTIFICATES_ENABLED=true
ONEC_API_URL=
ONEC_API_TOKEN=
ONEC_GIFT_CERTIFICATE_OPERATIONS_URL=
GIFT_CERTIFICATE_SECRET=
GIFT_CERTIFICATE_RESERVATION_TTL_MINUTES=30
GIFT_CERTIFICATE_PIN_REQUIRED_FOR_NEW=true
TILDA_GIFT_CERTIFICATE_ALLOWED_ORIGINS=https://glamejewelry.ru,https://www.glamejewelry.ru
TILDA_GIFT_CERTIFICATE_INTERNAL_SECRET=
TILDA_GIFT_CERTIFICATE_SCHEDULER_ENABLED=true
TILDA_GIFT_CERTIFICATE_MAINTENANCE_INTERVAL_SECONDS=60
```

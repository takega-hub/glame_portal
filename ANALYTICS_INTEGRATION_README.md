# Интеграция внешних источников аналитики

Этот документ описывает интеграцию различных источников аналитики в GLAME AI platform.

## Обзор

Платформа интегрирована со следующими источниками данных:

1. **Яндекс.Метрика** - веб-аналитика сайта
2. **FTP счетчики** - данные о посещениях физических магазинов
3. **Instagram** - статистика аккаунта и постов
4. **ВКонтакте** - метрики сообщества
5. **Telegram** - статистика канала и бота
6. **1С** - данные о продажах

## Настройка

### 1. Переменные окружения

Скопируйте `.env.example` в `.env` и заполните необходимые переменные:

```bash
cp .env.example .env
```

### 2. Миграция базы данных

Примените миграцию для создания новых таблиц:

```bash
cd backend
alembic upgrade head
```

### 3. Настройка API ключей

#### Яндекс.Метрика

1. Перейдите на https://metrika.yandex.ru
2. Создайте счетчик или используйте существующий
3. Получите OAuth токен: https://oauth.yandex.ru/authorize?response_type=token&client_id=YOUR_CLIENT_ID
4. Добавьте в `.env`:
   ```
   YANDEX_METRIKA_COUNTER_ID=12345678
   YANDEX_METRIKA_OAUTH_TOKEN=your_token
   ```

#### Instagram Graph API

1. Создайте Facebook App на https://developers.facebook.com
2. Подключите Instagram Business Account
3. Получите долгоживущий Access Token
4. Добавьте права: `instagram_basic`, `instagram_manage_insights`
5. Добавьте в `.env`:
   ```
   INSTAGRAM_ACCESS_TOKEN=your_token
   INSTAGRAM_BUSINESS_ACCOUNT_ID=your_account_id
   ```

#### ВКонтакте API

1. Создайте приложение: https://vk.com/apps?act=manage
2. Получите Access Token с правами: `stats`, `groups`, `wall`
3. Добавьте в `.env`:
   ```
   VK_ACCESS_TOKEN=your_token
   VK_GROUP_ID=your_group_id
   ```

#### Telegram Bot API

1. Создайте бота через @BotFather
2. Получите Bot Token
3. Для каналов - сделайте бота администратором
4. Добавьте в `.env`:
   ```
   TELEGRAM_BOT_TOKEN=your_token
   TELEGRAM_CHANNEL_USERNAME=your_channel
   ```

#### 1С УНФ ФРЕШ

Для подключения к 1С УНФ ФРЕШ используется OData сервис.

**Настройка в GLAME:**

Добавьте в `.env` файл:

```env
ONEC_API_URL=https://msk1.1cfresh.com/a/sbm/3322419/odata/standard.odata
ONEC_API_TOKEN=b2RhdGEudXNlcjpvcGV4b2JvZQ==
ONEC_SALES_ENDPOINT=/AccumulationRegister_Продажи_RecordType
ONEC_DISCOUNT_CARDS_ENDPOINT=/Catalog_ДисконтныеКарты
ONEC_CUSTOMERS_ENDPOINT=/Catalog_Контрагенты
```

**Примечание:** Токен должен быть в формате base64 для базовой HTTP-аутентификации (Basic Auth). 
Формат: `base64(логин:пароль)`

**Пример для ваших учетных данных:**
- Логин: `odata.user`
- Пароль: `opexoboe`
- Токен (base64): `b2RhdGEudXNlcjpvcGV4b2JvZQ==`

**Доступные сущности для аналитики:**

1. **Продажи** (`AccumulationRegister_Продажи_RecordType`)
   - Детальные записи о продажах
   - Поля: Period, Сумма, Количество, Номенклатура_Key, Контрагент_Key
   - Фильтрация по покупателю: `$filter=Контрагент_Key eq guid'...'`

2. **Дисконтные карты** (`Catalog_ДисконтныеКарты`)
   - Номер карты (`КодКартыШтрихкод`) = номер телефона = логин
   - Связь с покупателем через `ВладелецКарты_Key`

3. **Документы продаж** (`DocumentJournal_РозничныеПродажи`)
   - Чеки ККМ с суммами и датами
   - Связь с покупателем через `Покупатель_Key`

**Проверка подключения:**

Используйте тестовый скрипт:
```bash
python test_1c_connection.py
```

Подробнее см. `1C_CUSTOMERS_INTEGRATION.md`

## Использование

### Backend API

Все endpoints доступны по адресу `/api/analytics/`:

#### Яндекс.Метрика
- `POST /api/analytics/yandex-metrika/sync` - синхронизация данных
- `GET /api/analytics/yandex-metrika/metrics` - получение метрик

#### Instagram
- `POST /api/analytics/instagram/sync` - синхронизация
- `GET /api/analytics/instagram/metrics` - получение метрик

#### ВКонтакте
- `POST /api/analytics/vk/sync` - синхронизация
- `GET /api/analytics/vk/metrics` - получение метрик

#### Telegram
- `POST /api/analytics/telegram/sync` - синхронизация
- `GET /api/analytics/telegram/metrics` - получение метрик

#### FTP счетчики
- `POST /api/analytics/ftp/sync` - синхронизация файлов
- `GET /api/analytics/ftp/status` - статус синхронизации

#### 1С продажи
- `POST /api/analytics/1c-sales/sync` - синхронизация через API
- `POST /api/analytics/1c-sales/sync/file` - загрузка из файла
- `GET /api/analytics/1c-sales/metrics` - получение метрик

#### 1С покупатели
- `POST /api/analytics/1c-customers/sync` - синхронизация дисконтных карт
- `GET /api/analytics/1c-customers/{customer_id}/purchases` - история покупок покупателя
- `GET /api/analytics/1c-customers/{customer_id}/profile` - профиль покупателя

#### Объединенная аналитика
- `GET /api/analytics/unified` - сводка по всем источникам

### Frontend

Dashboard с аналитикой доступен по адресу `/analytics`.

Включает вкладки:
- **Обзор** - объединенная аналитика из всех источников
- **Яндекс.Метрика** - веб-аналитика
- **Instagram** - статистика соцсети
- **ВКонтакте** - метрики сообщества
- **Telegram** - данные канала
- **Магазины** - посещения физических точек
- **Продажи** - статистика из 1С
- **Покупатели** - профили и история покупок из 1С

## Автоматизация

Для автоматической синхронизации данных рекомендуется настроить периодические задачи (cron/celery):

```python
# Пример: ежедневная синхронизация в 6:00
@scheduler.scheduled_job('cron', hour=6, minute=0)
async def sync_all_analytics():
    # Яндекс.Метрика
    await yandex_metrika_service.sync()
    
    # Instagram
    await instagram_service.sync()
    
    # И так далее...
```

## Структура данных

### SocialMediaMetric
Хранит метрики из социальных сетей (Instagram, VK, Telegram):
- `platform` - название платформы
- `metric_type` - тип метрики (post, story, account, etc.)
- `likes`, `comments`, `shares`, `views`, `reach` - стандартные метрики
- `metadata` - дополнительная информация

### SalesMetric
Хранит данные о продажах из 1С:
- `revenue` - выручка
- `order_count` - количество заказов
- `items_sold` - проданные товары
- `average_order_value` - средний чек
- `channel` - канал продаж (online, offline, instagram, vk)
- `store_id` - ID магазина (для офлайн продаж)

## Troubleshooting

### Ошибка: "YANDEX_METRIKA_OAUTH_TOKEN не настроен"
Убедитесь, что переменная окружения установлена в `.env` файле.

### Ошибка: "VK API Error: invalid access_token"
Проверьте срок действия токена. Access Token VK может истечь - получите новый.

### Instagram API возвращает 403
Убедитесь, что:
1. Используется Business Account
2. Access Token имеет необходимые права
3. Токен не истек (используйте долгоживущий токен)

## Дополнительно

Для получения подробной информации по каждому сервису см.:
- `backend/app/services/yandex_metrika_service.py`
- `backend/app/services/instagram_service.py`
- `backend/app/services/vk_service.py`
- `backend/app/services/telegram_service.py`
- `backend/app/services/ftp_service.py`
- `backend/app/services/onec_sales_service.py`
- `backend/app/services/onec_customers_service.py`
- `1C_CUSTOMERS_INTEGRATION.md` - подробная документация по интеграции покупателей

# Примеры использования Analytics API

## Яндекс.Метрика

### Синхронизация данных за последние 30 дней
```bash
curl -X POST "http://localhost:8000/api/analytics/yandex-metrika/sync?days=30"
```

### Получение метрик посещаемости
```bash
curl "http://localhost:8000/api/analytics/yandex-metrika/metrics?metric_type=visits&days=30"
```

### Получение всех метрик
```bash
curl "http://localhost:8000/api/analytics/yandex-metrika/metrics?days=7"
```

## Instagram

### Синхронизация данных
```bash
curl -X POST "http://localhost:8000/api/analytics/instagram/sync?days=7&include_posts=true&posts_limit=10"
```

### Получение метрик аккаунта
```bash
curl "http://localhost:8000/api/analytics/instagram/metrics?metric_type=account&days=30"
```

### Получение статистики постов
```bash
curl "http://localhost:8000/api/analytics/instagram/metrics?metric_type=post&days=30"
```

## ВКонтакте

### Синхронизация данных
```bash
curl -X POST "http://localhost:8000/api/analytics/vk/sync?days=7"
```

### Получение метрик
```bash
curl "http://localhost:8000/api/analytics/vk/metrics?days=30"
```

## Telegram

### Синхронизация данных канала
```bash
curl -X POST "http://localhost:8000/api/analytics/telegram/sync"
```

### Получение метрик
```bash
curl "http://localhost:8000/api/analytics/telegram/metrics?days=30"
```

## FTP счетчики магазинов

### Синхронизация данных с FTP
```bash
curl -X POST "http://localhost:8000/api/analytics/ftp/sync" \
  -H "Content-Type: application/json" \
  -d '{
    "ftp_host": "ftp.example.com",
    "ftp_username": "user",
    "ftp_password": "password",
    "ftp_directory": "/counters",
    "pattern": "visits_*.csv",
    "format_hint": "csv"
  }'
```

### Получение статуса синхронизации
```bash
curl "http://localhost:8000/api/analytics/ftp/status"
```

## 1С Статистика продаж

### Синхронизация через API
```bash
curl -X POST "http://localhost:8000/api/analytics/1c-sales/sync?days=30"
```

### Загрузка из файла JSON
```bash
curl -X POST "http://localhost:8000/api/analytics/1c-sales/sync/file" \
  -H "Content-Type: application/json" \
  -d '{
    "file_content": "{\"orders\": [{\"id\": \"001\", \"date\": \"2024-01-15\", \"revenue\": 5000, \"channel\": \"online\"}]}",
    "file_format": "json"
  }'
```

### Получение метрик продаж
```bash
curl "http://localhost:8000/api/analytics/1c-sales/metrics?days=30"
```

## Объединенная аналитика

### Получение сводки по всем источникам
```bash
curl "http://localhost:8000/api/analytics/unified?days=30"
```

## Python примеры

### Яндекс.Метрика
```python
import httpx

async def sync_yandex_metrika():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/analytics/yandex-metrika/sync",
            params={"days": 30}
        )
        data = response.json()
        print(f"Синхронизировано: {data}")

# asyncio.run(sync_yandex_metrika())
```

### Instagram
```python
import httpx

async def get_instagram_metrics():
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://localhost:8000/api/analytics/instagram/metrics",
            params={"days": 30, "metric_type": "post"}
        )
        data = response.json()
        print(f"Постов: {data['total']}")
        for post in data['metrics']:
            print(f"  - {post['date']}: ❤️ {post['likes']} 💬 {post['comments']}")

# asyncio.run(get_instagram_metrics())
```

### Объединенная аналитика
```python
import httpx

async def get_unified_analytics():
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://localhost:8000/api/analytics/unified",
            params={"days": 30}
        )
        data = response.json()
        
        print(f"📱 Соцсети: {data['social_media']['total_metrics']} метрик")
        print(f"   Платформы: {', '.join(data['social_media']['platforms'])}")
        
        print(f"💰 Продажи: ₽{data['sales']['total_revenue']:,.2f}")
        print(f"   Заказов: {data['sales']['total_orders']}")
        
        print(f"🏪 Магазины: {data['stores']['total_visitors']:,} посетителей")
        print(f"   Продаж: {data['stores']['total_sales']}")

# asyncio.run(get_unified_analytics())
```

## JavaScript/TypeScript примеры

### Frontend интеграция
```typescript
// Синхронизация Яндекс.Метрики
const syncYandexMetrika = async () => {
  const response = await fetch('/api/analytics/yandex-metrika/sync', {
    method: 'POST'
  });
  const data = await response.json();
  return data;
};

// Получение метрик Instagram
const getInstagramMetrics = async (days = 30) => {
  const response = await fetch(`/api/analytics/instagram/metrics?days=${days}`);
  const data = await response.json();
  return data.metrics;
};

// Объединенная аналитика
const getUnifiedAnalytics = async () => {
  const response = await fetch('/api/analytics/unified?days=30');
  const data = await response.json();
  
  return {
    socialMedia: data.social_media,
    sales: data.sales,
    stores: data.stores
  };
};
```

## Форматы данных для FTP счетчиков

### CSV формат
```csv
store_id,date,visitor_count,sales_count,revenue
store_001,2024-01-15,150,25,12500.50
store_002,2024-01-15,200,30,15000.00
```

### JSON формат
```json
{
  "visits": [
    {
      "store_id": "store_001",
      "date": "2024-01-15",
      "visitor_count": 150,
      "sales_count": 25,
      "revenue": 12500.50
    }
  ]
}
```

### XML формат
```xml
<?xml version="1.0"?>
<visits>
  <record>
    <store_id>store_001</store_id>
    <date>2024-01-15</date>
    <visitors>150</visitors>
    <sales_count>25</sales_count>
    <revenue>12500.50</revenue>
  </record>
</visits>
```

## Формат данных 1С

### JSON формат заказов
```json
{
  "orders": [
    {
      "id": "ORD-001",
      "date": "2024-01-15T10:30:00",
      "store_id": "store_001",
      "channel": "online",
      "revenue": 5000.00,
      "items_count": 3,
      "customer_id": "CUST-123"
    }
  ]
}
```

### JSON формат агрегированных данных
```json
{
  "period": {
    "start": "2024-01-01",
    "end": "2024-01-31"
  },
  "metrics": {
    "total_revenue": 150000.00,
    "order_count": 500,
    "average_order_value": 300.00,
    "items_sold": 1200
  },
  "by_channel": [
    {
      "channel": "online",
      "revenue": 80000.00,
      "order_count": 300
    }
  ]
}
```

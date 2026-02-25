import requests
import json

# Получаем список магазинов
print("=== Список магазинов ===")
stores_response = requests.get("http://localhost:8000/api/analytics/stores")
stores_data = stores_response.json()
print(json.dumps(stores_data, indent=2, ensure_ascii=False))

if stores_data.get('stores') and len(stores_data['stores']) > 0:
    store_id = stores_data['stores'][0]['id']
    store_name = stores_data['stores'][0]['name']
    
    print(f"\n=== Статистика для магазина: {store_name} (ID: {store_id}) ===")
    status_response = requests.get(f"http://localhost:8000/api/analytics/ftp/status?store_id={store_id}")
    status_data = status_response.json()
    print(json.dumps(status_data, indent=2, ensure_ascii=False))
    
    print(f"\n=== Детальная статистика за 30 дней для: {store_name} ===")
    daily_response = requests.get(f"http://localhost:8000/api/analytics/store-visits/daily?days=30&store_id={store_id}")
    daily_data = daily_response.json()
    print(f"Всего посетителей: {daily_data['summary']['current_total']}")
    print(f"Дней с данными: {len(daily_data['daily_data'])}")
    print(f"Магазины: {daily_data.get('stores', [])}")

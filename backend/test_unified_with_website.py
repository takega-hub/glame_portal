import requests
import json

try:
    response = requests.get("http://localhost:8000/api/analytics/unified?days=30")
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"\n=== Unified Analytics ===")
    print(f"Website:")
    print(f"  Visits: {data.get('website', {}).get('visits', 0)}")
    print(f"  Visitors: {data.get('website', {}).get('visitors', 0)}")
    print(f"  Bounce rate: {data.get('website', {}).get('bounce_rate', 0)}%")
    print(f"\nSocial Media:")
    print(f"  Total metrics: {data.get('social_media', {}).get('total_metrics', 0)}")
    print(f"  Platforms: {data.get('social_media', {}).get('platforms', [])}")
    print(f"\nSales:")
    print(f"  Revenue: ₽{data.get('sales', {}).get('total_revenue', 0)}")
    print(f"  Orders: {data.get('sales', {}).get('total_orders', 0)}")
    print(f"\nStores:")
    print(f"  Visitors: {data.get('stores', {}).get('total_visitors', 0)}")
    print(f"  Sales: {data.get('stores', {}).get('total_sales', 0)}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

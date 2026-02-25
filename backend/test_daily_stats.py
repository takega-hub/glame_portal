import requests
import json

try:
    response = requests.get("http://localhost:8000/api/analytics/store-visits/daily?days=30")
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"\nSummary:")
    print(f"  Current: {data['summary']['current_total']}")
    print(f"  Previous: {data['summary']['previous_total']}")
    print(f"  Change: {data['summary']['change_percent']}%")
    print(f"\nDaily data points: {len(data['daily_data'])}")
    print(f"Stores: {', '.join(data['stores'])}")
    print(f"\nFirst 3 days:")
    for day in data['daily_data'][:3]:
        print(f"  {day['date']}: {day['visitors']} visitors")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

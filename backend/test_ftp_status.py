import requests
import json

try:
    response = requests.get("http://localhost:8000/api/analytics/ftp/status")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
except Exception as e:
    print(f"Error: {e}")

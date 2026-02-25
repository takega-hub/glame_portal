"""
Тест эндпоинта загрузки файлов
"""
import requests
import os

API_URL = os.getenv("API_URL", "http://localhost:8000")

def test_health():
    """Проверка доступности API"""
    try:
        response = requests.get(f"{API_URL}/health", timeout=5)
        print(f"Health check: {response.status_code} - {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"Health check failed: {e}")
        return False

def test_knowledge_endpoint():
    """Проверка доступности knowledge endpoint"""
    try:
        response = requests.get(f"{API_URL}/api/knowledge/stats", timeout=5)
        print(f"Knowledge stats: {response.status_code}")
        if response.status_code == 200:
            print(f"Response: {response.json()}")
        else:
            print(f"Error: {response.text}")
        return response.status_code == 200
    except Exception as e:
        print(f"Knowledge endpoint check failed: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Testing upload endpoint availability")
    print("=" * 60)
    
    print("\n1. Testing API health...")
    if not test_health():
        print("[ERROR] API is not available. Make sure backend is running:")
        print("  cd backend")
        print("  python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000")
        exit(1)
    
    print("\n2. Testing knowledge endpoint...")
    if not test_knowledge_endpoint():
        print("[WARNING] Knowledge endpoint may not be working correctly")
    else:
        print("[OK] Knowledge endpoint is accessible")
    
    print("\n" + "=" * 60)
    print("If both tests pass, the backend is ready for file uploads")
    print("=" * 60)

# deep_analysis.py
import requests
from requests.auth import HTTPBasicAuth
import json
import base64

class DeepUNFAnalysis:
    def __init__(self):
        self.base_url = "https://msk1.1cfresh.com"
        self.base_path = "/e1cib/application/sbm/3322419"
        self.username = "odata.user"
        self.password = "your_1c_password_here"
        
    def analyze_403_endpoint(self):
        """Детальный анализ endpoint с 403 ошибкой"""
        print("🔍 Анализ endpoint с кодом 403...")
        
        endpoint = "/api/v1/reports/daily"
        full_url = f"{self.base_url}{self.base_path}{endpoint}"
        
        print(f"📡 Endpoint: {full_url}")
        
        # Пробуем разные методы аутентификации
        auth_methods = [
            ("Basic Auth", {'auth': HTTPBasicAuth(self.username, self.password)}),
            ("Bearer Token", {'headers': {'Authorization': 'Bearer test_token'}}),
            ("API Key", {'headers': {'X-API-Key': 'test_key'}}),
            ("Session Cookie", {'cookies': {'session': 'test'}}),
            ("Без аутентификации", {}),
        ]
        
        for method_name, auth_config in auth_methods:
            print(f"\n🔐 Пробуем: {method_name}")
            
            try:
                if 'auth' in auth_config:
                    response = requests.get(full_url, **auth_config, timeout=10)
                else:
                    response = requests.get(full_url, **auth_config, timeout=10)
                
                print(f"   Статус: {response.status_code}")
                
                if response.status_code != 403:
                    print(f"   ⚠️ Изменился статус!")
                    print(f"   Заголовки: {dict(response.headers)}")
                    
                    if response.status_code == 200:
                        print(f"   ✅ УСПЕХ!")
                        try:
                            data = response.json()
                            print(f"   Данные: {json.dumps(data, ensure_ascii=False)[:200]}...")
                            return True, data
                        except:
                            print(f"   Текст: {response.text[:500]}")
                            return True, response.text
                
                # Анализируем заголовки 403
                if response.status_code == 403:
                    headers = dict(response.headers)
                    print(f"   Заголовки ответа:")
                    for key, value in headers.items():
                        if any(word in key.lower() for word in ['auth', 'token', 'key', 'www']):
                            print(f"     • {key}: {value}")
                    
                    # Сохраняем ответ для анализа
                    with open('403_response.html', 'w', encoding='utf-8') as f:
                        f.write(response.text)
                    
            except Exception as e:
                print(f"   ❌ Ошибка: {e}")
        
        return False, None
    
    def discover_api_structure(self):
        """Обнаружение структуры API"""
        print("\n🗺️  Исследование структуры API...")
        
        # Базовые пути для исследования
        base_endpoints = [
            "/api",
            "/api/v1",
            "/api/v2",
            "/data",
            "/reports",
            "/export",
            "/integration",
            "/webservice",
            "/soap",
            "/rest",
        ]
        
        discovered = []
        
        for endpoint in base_endpoints:
            url = f"{self.base_url}{self.base_path}{endpoint}"
            
            try:
                response = requests.get(
                    url,
                    auth=HTTPBasicAuth(self.username, self.password),
                    timeout=5,
                    allow_redirects=True
                )
                
                print(f"🔍 {url}: {response.status_code}")
                
                if response.status_code in [200, 401, 403]:
                    discovered.append({
                        'endpoint': endpoint,
                        'url': url,
                        'status': response.status_code,
                        'content_type': response.headers.get('Content-Type', ''),
                        'size': len(response.content)
                    })
                    
                    # Сохраняем для анализа
                    if response.status_code == 200:
                        filename = f"api_{endpoint.replace('/', '_')}.txt"
                        with open(filename, 'w', encoding='utf-8') as f:
                            f.write(f"URL: {url}\n")
                            f.write(f"Status: {response.status_code}\n")
                            f.write(f"Content:\n{response.text[:2000]}")
                
            except Exception as e:
                print(f"🔍 {url}: ошибка - {e}")
        
        return discovered
    
    def try_post_requests(self):
        """Пробуем POST запросы к API"""
        print("\n📤 Тестирование POST запросов...")
        
        endpoints = [
            "/api/v1/auth/login",
            "/api/v1/token",
            "/api/v1/query",
            "/data/query",
            "/report/generate",
        ]
        
        for endpoint in endpoints:
            url = f"{self.base_url}{self.base_path}{endpoint}"
            
            # Пробуем разные типы данных
            payloads = [
                {'username': self.username, 'password': self.password},
                {'action': 'getSales', 'dateFrom': '2024-01-01'},
                {'query': 'SELECT TOP 10 * FROM Document_Реализация'},
                {'report': 'daily_sales'},
            ]
            
            for payload in payloads:
                try:
                    print(f"\n📤 POST {endpoint}")
                    print(f"   Данные: {payload}")
                    
                    response = requests.post(
                        url,
                        json=payload,
                        auth=HTTPBasicAuth(self.username, self.password),
                        timeout=10
                    )
                    
                    print(f"   Статус: {response.status_code}")
                    
                    if response.status_code != 404:
                        print(f"   Ответ: {response.text[:200]}")
                        
                        if response.status_code == 200:
                            print(f"   ✅ УСПЕХ!")
                            return endpoint, payload, response.json()
                
                except Exception as e:
                    print(f"   ❌ Ошибка: {e}")
                    continue
        
        return None, None, None
    
    def examine_manifest(self):
        """Анализ manifest.json"""
        print("\n📄 Анализ manifest.json...")
        
        manifest_url = f"{self.base_url}/a/sbm/3322419/manifest.json?sysver=8.5.1.1165"
        
        try:
            response = requests.get(manifest_url, timeout=10)
            
            if response.status_code == 200:
                manifest = response.json()
                
                print(f"✅ Manifest получен")
                print(f"   Версия: {manifest.get('version', 'N/A')}")
                print(f"   Имя: {manifest.get('name', 'N/A')}")
                
                # Ищем информацию об API
                if 'api' in manifest:
                    print(f"   API endpoints: {manifest['api']}")
                
                # Сохраняем manifest
                with open('manifest.json', 'w', encoding='utf-8') as f:
                    json.dump(manifest, f, indent=2, ensure_ascii=False)
                
                return manifest
            else:
                print(f"❌ Не удалось получить manifest: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            return None
    
    def brute_force_api_endpoints(self):
        """Перебор возможных API endpoints"""
        print("\n🔓 Перебор API endpoints...")
        
        # Список возможных endpoints для отчетов о продажах
        possible_endpoints = [
            # Отчеты
            "/api/v1/report/sales",
            "/api/v1/reports/sales",
            "/api/v1/sales/report",
            "/api/v1/sales/daily",
            "/api/v1/sales/today",
            "/api/v1/daily/sales",
            
            # Данные
            "/api/v1/data/sales",
            "/api/v1/sales/data",
            "/api/v1/documents/sales",
            "/api/v1/sales/documents",
            
            # Экспорт
            "/api/v1/export/sales",
            "/api/v1/sales/export",
            "/api/v1/export/json",
            "/api/v1/data/export",
            
            # Запросы
            "/api/v1/query/sales",
            "/api/v1/sales/query",
        ]
        
        working_endpoints = []
        
        for endpoint in possible_endpoints:
            url = f"{self.base_url}{self.base_path}{endpoint}"
            
            try:
                response = requests.get(
                    url,
                    auth=HTTPBasicAuth(self.username, self.password),
                    timeout=5
                )
                
                status_emoji = "✅" if response.status_code == 200 else "⚠️" if response.status_code == 403 else "❌"
                print(f"{status_emoji} {endpoint}: {response.status_code}")
                
                if response.status_code in [200, 403]:
                    working_endpoints.append({
                        'endpoint': endpoint,
                        'status': response.status_code,
                        'url': url
                    })
                    
                    if response.status_code == 200:
                        # Пробуем с параметрами
                        params_response = requests.get(
                            url,
                            params={'dateFrom': '2024-01-01', 'format': 'json'},
                            auth=HTTPBasicAuth(self.username, self.password),
                            timeout=5
                        )
                        
                        if params_response.status_code == 200:
                            print(f"   📊 С параметрами: УСПЕХ!")
                            try:
                                data = params_response.json()
                                print(f"   Данные: {json.dumps(data, ensure_ascii=False)[:100]}...")
                            except:
                                print(f"   Текст: {params_response.text[:200]}")
                
            except Exception as e:
                print(f"❌ {endpoint}: ошибка - {e}")
        
        return working_endpoints

# Запуск анализа
analyzer = DeepUNFAnalysis()

print("=" * 60)
print("🚀 ЗАПУСК ГЛУБОКОГО АНАЛИЗА 1С УНФ ФРЕШ")
print("=" * 60)

# 1. Анализ manifest
manifest = analyzer.examine_manifest()

# 2. Анализ 403 endpoint
success, data = analyzer.analyze_403_endpoint()

# 3. Исследование структуры
discovered = analyzer.discover_api_structure()

# 4. Перебор endpoints
working = analyzer.brute_force_api_endpoints()

# 5. POST запросы
endpoint, payload, result = analyzer.try_post_requests()

print("\n" + "=" * 60)
print("📊 ИТОГИ АНАЛИЗА")
print("=" * 60)

if working:
    print(f"✅ Найдено потенциальных endpoints: {len(working)}")
    for ep in working:
        status = "ДОСТУПЕН" if ep['status'] == 200 else "ТРЕБУЕТ АВТОРИЗАЦИИ"
        print(f"   • {ep['endpoint']} - {status}")

if success:
    print(f"\n🎉 API ДОСТУПЕН! Используйте: {analyzer.base_path}/api/v1/reports/daily")
else:
    print("\n🔒 API требует настройки аутентификации")
    print("   Попробуйте:")
    print("   1. Получить токен через /api/v1/auth/login")
    print("   2. Использовать другой метод аутентификации")
    print("   3. Обратиться к администратору за токеном API")
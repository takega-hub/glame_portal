# quick_workaround.py
import requests
from requests.auth import HTTPBasicAuth
import json
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import re

class UNFWorkaround:
    def __init__(self):
        self.domain = "msk1.1cfresh.com"
        self.base_name = "sbm"
        self.company_code = "3322419"
        self.username = "odata.user"
        self.password = "your_1c_password_here"
        
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(self.username, self.password)
    
    def discover_available_endpoints(self):
        """Автоматическое обнаружение доступных endpoints"""
        print("🔍 Сканирование доступных endpoints...")
        
        base_paths = [
            "/a/{b}/{c}",           # Портал
            "/e1cib/{b}/{c}",       # E1CIB API
            "/{b}/{c}",             # Прямой доступ
            "/api/{b}/{c}",         # API
            "/rest/{b}/{c}",        # REST
            "/v1/{b}/{c}",          # API v1
            "/v2/{b}/{c}",          # API v2
        ]
        
        discovered = []
        
        for path_template in base_paths:
            path = path_template.format(b=self.base_name, c=self.company_code)
            
            # Тестируем разные варианты
            test_urls = [
                f"https://{self.domain}{path}",
                f"https://{self.domain}{path}/",
                f"https://{self.domain}{path}/data",
                f"https://{self.domain}{path}/api",
                f"https://{self.domain}{path}/export",
                f"https://{self.domain}{path}/reports",
            ]
            
            for url in test_urls:
                try:
                    response = self.session.get(url, timeout=5)
                    if response.status_code == 200:
                        print(f"✅ НАЙДЕНО: {url}")
                        discovered.append({
                            'url': url,
                            'status': response.status_code,
                            'content_type': response.headers.get('Content-Type', ''),
                            'size': len(response.content)
                        })
                        
                        # Сохраняем для анализа
                        filename = f"discovered_{url.replace('https://', '').replace('/', '_')}.html"
                        with open(filename, 'w', encoding='utf-8') as f:
                            f.write(response.text[:5000])
                            
                except Exception as e:
                    continue
        
        return discovered
    
    def parse_portal_for_data(self):
        """Парсинг портала для поиска данных"""
        print("\n🧠 Анализ портала...")
        
        portal_url = f"https://{self.domain}/a/{self.base_name}/{self.company_code}"
        
        try:
            response = self.session.get(portal_url, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Ищем JavaScript переменные с данными
                scripts = soup.find_all('script')
                data_patterns = [
                    r'data:\s*({[^}]+})',
                    r'JSON\.parse\(\'([^\']+)\'\)',
                    r'initialState\s*=\s*({[^}]+})',
                    r'window\.__INITIAL_STATE__\s*=\s*({[^}]+})',
                ]
                
                found_data = []
                
                for script in scripts:
                    if script.string:
                        for pattern in data_patterns:
                            matches = re.findall(pattern, script.string, re.DOTALL)
                            for match in matches:
                                try:
                                    if isinstance(match, tuple):
                                        match = match[0]
                                    
                                    # Пробуем распарсить как JSON
                                    data = json.loads(match)
                                    found_data.append(data)
                                    print(f"  ✅ Найдены данные в JavaScript")
                                except:
                                    # Пробуем очистить строку
                                    cleaned = match.replace("\\'", "'").replace('\\"', '"')
                                    try:
                                        data = json.loads(cleaned)
                                        found_data.append(data)
                                        print(f"  ✅ Найдены данные в JavaScript (очищенные)")
                                    except:
                                        continue
                
                # Ищем ссылки на API
                api_links = []
                for tag in soup.find_all(['a', 'link', 'script', 'iframe']):
                    src = tag.get('src') or tag.get('href') or ''
                    if any(api_keyword in src.lower() for api_keyword in ['api', 'data', 'json', 'export', 'report']):
                        api_links.append(src)
                
                print(f"\n🔗 Найдено API ссылок: {len(set(api_links))}")
                for link in list(set(api_links))[:10]:
                    print(f"  • {link}")
                
                return found_data, api_links
                
        except Exception as e:
            print(f"❌ Ошибка анализа портала: {e}")
        
        return [], []
    
    def try_common_unf_patterns(self):
        """Попробовать стандартные паттерны УНФ Фреш"""
        print("\n🎯 Пробуем стандартные паттерны УНФ...")
        
        # Стандартные паттерны для УНФ Фреш
        patterns = [
            # Статистика
            f"https://{self.domain}/e1cib/application/{self.base_name}/{self.company_code}/data/statistics",
            f"https://{self.domain}/e1cib/application/{self.base_name}/{self.company_code}/api/v1/reports/daily",
            
            # Экспорт
            f"https://{self.domain}/e1cib/application/{self.base_name}/{self.company_code}/data/export/json",
            f"https://{self.domain}/e1cib/application/{self.base_name}/{self.company_code}/export/data",
            
            # Стандартные отчеты
            f"https://{self.domain}/e1cib/application/{self.base_name}/{self.company_code}/report/sales",
            f"https://{self.domain}/e1cib/application/{self.base_name}/{self.company_code}/report/daily",
        ]
        
        for url in patterns:
            try:
                response = self.session.get(url, timeout=5)
                print(f"  {url}: статус {response.status_code}")
                
                if response.status_code == 200:
                    content_type = response.headers.get('Content-Type', '')
                    
                    if 'json' in content_type:
                        data = response.json()
                        print(f"    ✅ JSON данные получены!")
                        return data
                    else:
                        # Сохраняем для анализа
                        with open(f'pattern_{url.split("/")[-1]}.txt', 'w', encoding='utf-8') as f:
                            f.write(response.text[:2000])
            except Exception as e:
                print(f"  {url}: ошибка {e}")
        
        return None

# Запуск
workaround = UNFWorkaround()

# 1. Сканирование
discovered = workaround.discover_available_endpoints()

# 2. Анализ портала
data, links = workaround.parse_portal_for_data()

# 3. Стандартные паттерны
common_data = workaround.try_common_unf_patterns()
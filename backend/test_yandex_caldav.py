#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для проверки настроек Яндекс CalDAV
"""
import os
import sys
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

def check_env():
    """Проверка переменных окружения"""
    print("=" * 60)
    print("Проверка настроек Яндекс CalDAV")
    print("=" * 60)
    
    username = os.getenv("YANDEX_CALDAV_USERNAME", "").strip()
    password = os.getenv("YANDEX_CALDAV_PASSWORD", "").strip()
    url = os.getenv("YANDEX_CALDAV_URL", "https://caldav.yandex.ru").strip()
    
    print(f"\n1. YANDEX_CALDAV_URL: {url}")
    print(f"2. YANDEX_CALDAV_USERNAME: {username}")
    print(f"3. YANDEX_CALDAV_PASSWORD: {'*' * len(password) if password else 'НЕ ЗАДАН'}")
    print(f"   Длина пароля: {len(password)} символов")
    
    issues = []
    
    if not username:
        issues.append("❌ YANDEX_CALDAV_USERNAME не задан")
    elif "@" not in username:
        issues.append("⚠️  YANDEX_CALDAV_USERNAME не похож на email")
    else:
        print(f"   ✓ Username выглядит как email: {username}")
    
    if not password:
        issues.append("❌ YANDEX_CALDAV_PASSWORD не задан")
    elif len(password) < 8:
        issues.append("⚠️  Пароль слишком короткий (меньше 8 символов)")
    elif password.startswith(" ") or password.endswith(" "):
        issues.append("⚠️  Пароль содержит пробелы в начале/конце")
    else:
        print(f"   ✓ Пароль задан, длина: {len(password)} символов")
    
    if not url:
        issues.append("❌ YANDEX_CALDAV_URL не задан")
    elif not url.startswith("http"):
        issues.append("⚠️  URL не начинается с http/https")
    else:
        print(f"   ✓ URL выглядит корректно: {url}")
    
    print("\n" + "=" * 60)
    
    if issues:
        print("Обнаружены проблемы:")
        for issue in issues:
            print(f"  {issue}")
        print("\n" + "=" * 60)
        print("\nРекомендации:")
        print("1. Убедитесь, что в .env файле нет пробелов в конце значений")
        print("2. Используйте пароль приложения Яндекса (не обычный пароль)")
        print("3. Создайте пароль приложения: https://id.yandex.ru/security/app-passwords")
        print("4. Перезапустите backend после изменения .env")
        return False
    else:
        print("✓ Все настройки выглядят корректно!")
        print("\nПопробуйте подключиться через API или проверьте логи backend")
        return True

def test_connection():
    """Попытка подключения к CalDAV"""
    print("\n" + "=" * 60)
    print("Попытка подключения к Яндекс CalDAV...")
    print("=" * 60)
    
    try:
        from app.services.yandex_calendar_service import list_calendars, get_config_from_env
        
        cfg = get_config_from_env()
        print(f"\nПодключение к: {cfg.url}")
        print(f"Username: {cfg.username}")
        
        calendars = list_calendars(cfg)
        print(f"\n✓ Успешно подключено!")
        print(f"Найдено календарей: {len(calendars)}")
        
        for i, cal in enumerate(calendars, 1):
            print(f"  {i}. {cal.get('name', 'Без названия')} - {cal.get('url', 'N/A')}")
        
        return True
        
    except ModuleNotFoundError as e:
        print(f"\n❌ Ошибка: {e}")
        print("\nУстановите зависимости:")
        print("  pip install caldav")
        return False
    except ValueError as e:
        print(f"\n❌ Ошибка конфигурации: {e}")
        return False
    except Exception as e:
        error_msg = str(e)
        print(f"\n❌ Ошибка подключения: {error_msg}")
        
        if "Unauthorized" in error_msg or "401" in error_msg:
            print("\nПроблема с авторизацией:")
            print("1. Проверьте правильность username и password")
            print("2. Используйте пароль приложения: https://id.yandex.ru/security/app-passwords")
            print("3. Убедитесь, что нет пробелов в .env файле")
        elif "405" in error_msg or "Method Not Allowed" in error_msg:
            print("\nПроблема с CalDAV endpoint:")
            print("1. Проверьте URL: https://caldav.yandex.ru")
            print("2. Возможно, нужен другой путь или настройки аккаунта")
        
        return False

if __name__ == "__main__":
    print("\n")
    
    # Проверка переменных окружения
    env_ok = check_env()
    
    if not env_ok:
        sys.exit(1)
    
    # Попытка подключения
    print("\n")
    conn_ok = test_connection()
    
    if conn_ok:
        print("\n✓ Все проверки пройдены успешно!")
        sys.exit(0)
    else:
        print("\n❌ Проверка подключения не прошла")
        sys.exit(1)

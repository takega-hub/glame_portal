#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для добавления переменных 1С API в .env файл
"""
import os
import sys

# Устанавливаем кодировку для Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

def add_onec_vars():
    """Добавление переменных 1С в .env файл"""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_file = os.path.join(project_root, ".env")
    
    # Переменные для добавления
    onec_vars = """
# ---------
# 1С УНФ ФРЕШ OData API
# ---------
# URL OData сервиса 1С
ONEC_API_URL=https://msk1.1cfresh.com/a/sbm/3322419/odata/standard.odata
# Токен в формате base64 для Basic Auth (логин:пароль)
ONEC_API_TOKEN=b2RhdGEudXNlcjpvcGV4b2JvZQ==
# Endpoint для получения данных о продажах
ONEC_SALES_ENDPOINT=/AccumulationRegister_Продажи_RecordType
# Endpoint для дисконтных карт
ONEC_DISCOUNT_CARDS_ENDPOINT=/Catalog_ДисконтныеКарты
# Endpoint для контрагентов/покупателей
ONEC_CUSTOMERS_ENDPOINT=/Catalog_Контрагенты
# Таймауты подключения к 1С (в секундах)
# ONEC_CONNECT_TIMEOUT=60.0  # Таймаут установки соединения (по умолчанию 60)
# ONEC_READ_TIMEOUT=300.0    # Таймаут чтения данных (по умолчанию 300)
"""
    
    if not os.path.exists(env_file):
        print(f"ERROR: .env файл не найден: {env_file}")
        return False
    
    # Читаем существующий файл
    with open(env_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Проверяем, есть ли уже переменные 1С
    if 'ONEC_API_URL' in content:
        print("Переменные 1С API уже присутствуют в .env файле")
        return True
    
    # Добавляем переменные
    with open(env_file, 'a', encoding='utf-8') as f:
        f.write(onec_vars)
    
    print("✓ Переменные 1С API добавлены в .env файл")
    return True

if __name__ == "__main__":
    success = add_onec_vars()
    sys.exit(0 if success else 1)

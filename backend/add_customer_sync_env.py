#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для добавления переменных синхронизации покупателей в .env файл
"""
import os
import sys

# Устанавливаем кодировку для Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

def add_customer_sync_vars():
    """Добавление переменных синхронизации покупателей в .env файл"""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_file = os.path.join(project_root, ".env")
    
    # Переменные для добавления
    sync_vars = """
# Настройки синхронизации покупателей
CUSTOMER_SYNC_LOAD_ALL=true      # Загружать всех покупателей (true) или ограниченное количество (false)
CUSTOMER_SYNC_BATCH_SIZE=1000    # Размер батча для пагинации (рекомендуется 1000)
CUSTOMER_SYNC_CARDS_LIMIT=1000   # Максимальное количество карт (если LOAD_ALL=false)
CUSTOMER_SYNC_PURCHASE_DAYS=365  # Количество дней истории покупок для синхронизации
"""
    
    if not os.path.exists(env_file):
        print(f"ERROR: .env файл не найден: {env_file}")
        return False
    
    # Читаем существующий файл
    with open(env_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Проверяем, есть ли уже переменные синхронизации
    if 'CUSTOMER_SYNC_LOAD_ALL' in content:
        print("Переменные синхронизации покупателей уже присутствуют в .env файле")
        return True
    
    # Добавляем переменные
    with open(env_file, 'a', encoding='utf-8') as f:
        f.write(sync_vars)
    
    print("✓ Переменные синхронизации покупателей добавлены в .env файл")
    return True

if __name__ == "__main__":
    success = add_customer_sync_vars()
    sys.exit(0 if success else 1)

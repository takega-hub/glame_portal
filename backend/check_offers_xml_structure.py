"""
Скрипт для проверки структуры offers.xml
Проверяет, есть ли в offers.xml разбивка остатков по складам
"""
import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Исправление кодировки для Windows
if sys.platform == 'win32':
    import codecs
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# Добавляем путь к app
sys.path.insert(0, str(Path(__file__).parent))

from app.services.commerceml_xml_service import CommerceMLXMLService

# Загружаем переменные окружения
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

ONEC_OFFERS_XML_URL = os.getenv("ONEC_OFFERS_XML_URL")

async def check_offers_xml_structure():
    """Проверяет структуру offers.xml"""
    
    if not ONEC_OFFERS_XML_URL:
        print("[ERROR] ONEC_OFFERS_XML_URL не настроен в .env")
        print("Добавьте в .env: ONEC_OFFERS_XML_URL=https://ваш-сервер-1с/offers.xml")
        return
    
    print("=" * 80)
    print("Проверка структуры offers.xml")
    print("=" * 80)
    print(f"URL: {ONEC_OFFERS_XML_URL}")
    print()
    
    try:
        async with CommerceMLXMLService() as xml_service:
            offers_data = await xml_service.load_and_parse_offers(ONEC_OFFERS_XML_URL)
        
        print(f"[OK] Загружено предложений: {len(offers_data)}")
        print()
        
        # Анализируем структуру
        offers_with_store_stocks = 0
        offers_without_store_stocks = 0
        all_stores = set()
        store_stocks_examples = []
        
        for offer_id, offer_info in list(offers_data.items())[:100]:  # Проверяем первые 100
            store_stocks = offer_info.get('store_stocks', {})
            
            if store_stocks:
                offers_with_store_stocks += 1
                all_stores.update(store_stocks.keys())
                
                # Сохраняем примеры для демонстрации
                if len(store_stocks_examples) < 3:
                    store_stocks_examples.append({
                        'offer_id': offer_id,
                        'product_id': offer_info.get('product_id'),
                        'article': offer_info.get('article'),
                        'store_stocks': store_stocks
                    })
            else:
                offers_without_store_stocks += 1
        
        print("Статистика по остаткам:")
        print("-" * 80)
        print(f"Предложений с разбивкой по складам: {offers_with_store_stocks}")
        print(f"Предложений без разбивки по складам: {offers_without_store_stocks}")
        print(f"Всего найдено складов: {len(all_stores)}")
        
        if all_stores:
            print(f"\nНайденные склады (первые 10):")
            for i, store_id in enumerate(sorted(all_stores)[:10], 1):
                print(f"  {i}. {store_id}")
        
        if store_stocks_examples:
            print("\nПримеры предложений с разбивкой по складам:")
            print("-" * 80)
            for example in store_stocks_examples:
                print(f"\nПредложение: {example['offer_id']}")
                print(f"  Товар ID: {example['product_id']}")
                print(f"  Артикул: {example['article']}")
                print(f"  Остатки по складам:")
                for store_id, quantity in example['store_stocks'].items():
                    print(f"    - Склад {store_id}: {quantity} шт.")
        
        print()
        print("=" * 80)
        print("Выводы:")
        print("=" * 80)
        
        if offers_with_store_stocks > 0:
            print(f"[OK] В offers.xml есть разбивка остатков по складам!")
            print(f"     Найдено {len(all_stores)} складов")
            print(f"     Сервис OneCStockService будет использовать эти данные")
        else:
            print("[WARNING] В offers.xml нет разбивки остатков по складам")
            print("     Варианты решения:")
            print("     1. Настроить 1С для экспорта остатков по складам в offers.xml")
            print("     2. Использовать распределение остатков пропорционально продажам")
            print("     3. Использовать склад по умолчанию (текущее поведение)")
        
    except Exception as e:
        print(f"[ERROR] Ошибка при проверке offers.xml: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(check_offers_xml_structure())

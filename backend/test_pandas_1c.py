import os
import asyncio
import pandas as pd
import sys
from dotenv import load_dotenv
from app.services.onec_customers_service import OneCCustomersService

# Исправление кодировки для Windows
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

# Загрузка переменных окружения
load_dotenv()

async def test_load_and_print():
    print("=== Тестовая загрузка дисконтных карт из 1С ===")
    
    # Инициализация сервиса
    service = OneCCustomersService()
    
    if not service.api_url:
        print("ОШИБКА: ONEC_API_URL не задан в .env")
        return

    try:
        # Пытаемся получить данные
        print(f"Запрос к 1С: {service.api_url}...")
        cards = await service.fetch_discount_cards(limit=10)
        
        if not cards:
            print("Предупреждение: Получен пустой список карт.")
            return

        print(f"Успешно получено {len(cards)} записей.")

        # Создаем DataFrame
        df = pd.DataFrame(cards)
        
        # Словарь для переименования колонок (для удобства чтения)
        # 1С часто возвращает названия на русском, но в OData они могут быть в разной кодировке
        # Мы попробуем найти нужные нам поля по смыслу
        
        column_mapping = {
            "Description": "ФИО_и_Телефон",
            "Code": "Код_Карты",
            "Ref_Key": "ID_Карты_1C",
            "ВладелецКарты_Key": "ID_Покупателя_1C"
        }
        
        # Ищем колонку со штрихкодом (телефоном)
        # Она может называться "КодКартыШтрихкод"
        for col in df.columns:
            if "Штрихкод" in col or "Barcode" in col:
                column_mapping[col] = "Телефон_Логин"
            if "Владелец" in col and "Key" in col:
                column_mapping[col] = "ID_Покупателя_1C"

        # Переименовываем только то, что нашли
        df_display = df.rename(columns=column_mapping)
        
        # Выбираем основные колонки для вывода
        cols_to_show = [v for k, v in column_mapping.items() if v in df_display.columns]
        
        print("\nРезультат (Основные данные):")
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 1000)
        print(df_display[cols_to_show].head(10))
        
        print("\nПолный список всех полей из 1С (RAW):")
        print(df.columns.tolist())

    except Exception as e:
        print(f"\nОШИБКА при подключении: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await service.close()

if __name__ == "__main__":
    asyncio.run(test_load_and_print())

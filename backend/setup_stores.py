"""
Скрипт для добавления/обновления магазинов с известными UUID из 1С
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

# Сопоставление UUID -> название магазина
STORE_MAPPING = {
    "6c3a8322-a2ab-11f0-96fc-fa163e4cc04e": "CENTRUM",
    "3daee4e4-a2ab-11f0-96fc-fa163e4cc04e": "YALTA",
    "8cebda58-a2ab-11f0-96fc-fa163e4cc04e": "MEGANOM",
    "e1a2eace-fdc8-11ef-8c0c-fa163e4cc04e": "Основной склад",
}


async def setup_stores():
    """Добавляет или обновляет магазины в базе данных"""
    # Получаем параметры подключения из переменных окружения
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL не установлен в переменных окружения")
    
    conn = await asyncpg.connect(db_url)
    
    try:
        created = 0
        updated = 0
        
        for external_id, name in STORE_MAPPING.items():
            # Проверяем, существует ли магазин с таким external_id
            existing = await conn.fetchrow(
                "SELECT id, name FROM stores WHERE external_id = $1",
                external_id
            )
            
            if existing:
                # Обновляем название, если оно отличается
                if existing['name'] != name:
                    await conn.execute(
                        "UPDATE stores SET name = $1, updated_at = NOW() WHERE external_id = $2",
                        name, external_id
                    )
                    print(f"[OK] Обновлен магазин: {name} ({external_id})")
                    updated += 1
                else:
                    print(f"[SKIP] Магазин уже существует: {name} ({external_id})")
            else:
                # Создаем новый магазин
                await conn.execute(
                    """
                    INSERT INTO stores (name, external_id, is_active, created_at, updated_at)
                    VALUES ($1, $2, $3, NOW(), NOW())
                    """,
                    name, external_id, True
                )
                print(f"[OK] Создан магазин: {name} ({external_id})")
                created += 1
        
        print(f"\nИтого: создано {created}, обновлено {updated}")
        
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(setup_stores())

"""
Скрипт для проверки статуса задачи синхронизации в реальном времени
Использование: python backend/check_sync_status.py <task_id>
"""
import sys
import asyncio
import time
from app.services.sync_progress_service import get_sync_progress_service


async def check_task_status(task_id: str):
    """Проверяет статус задачи и выводит информацию"""
    progress_service = get_sync_progress_service()
    
    print(f"\n{'='*60}")
    print(f"Отслеживание задачи: {task_id}")
    print(f"{'='*60}\n")
    
    last_progress = -1
    last_stage = ""
    
    while True:
        task = await progress_service.get_task(task_id)
        
        if not task:
            print(f"\nERROR: Задача {task_id} не найдена!")
            print("Возможные причины:")
            print("  - Задача была удалена (старше 7 дней)")
            print("  - Неверный task_id")
            print("  - Сервер был перезапущен (задачи хранятся в памяти)")
            break
        
        status = task.get("status", "unknown")
        progress = task.get("progress", 0)
        current = task.get("current", 0)
        total = task.get("total", 0)
        stage = task.get("stage", "")
        stage_desc = task.get("stage_description", "")
        error = task.get("error")
        
        # Выводим только если что-то изменилось
        if progress != last_progress or stage != last_stage:
            print(f"\r[{status.upper():8}] {progress:5.1f}% | {current}/{total} | {stage_desc[:50]:50}", end="", flush=True)
            last_progress = progress
            last_stage = stage
        
        if status == "completed":
            print(f"\n\nOK: Задача завершена успешно!")
            result = task.get("result", {})
            if result:
                groups = result.get("groups", {})
                products = result.get("products", {})
                print(f"\nРезультаты:")
                if groups:
                    print(f"  Группы: создано {groups.get('created', 0)}, обновлено {groups.get('updated', 0)}")
                if products:
                    print(f"  Товары: создано {products.get('created', 0)}, обновлено {products.get('updated', 0)}")
                    print(f"  Варианты: создано {products.get('variants_created', 0)}")
            break
        
        if status == "failed":
            print(f"\n\nERROR: Задача завершена с ошибкой!")
            if error:
                print(f"\nОшибка: {error}")
            break
        
        if status == "cancelled":
            print(f"\n\nWARNING: Задача отменена")
            break
        
        # Ждем перед следующей проверкой
        await asyncio.sleep(2)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python backend/check_sync_status.py <task_id>")
        print("\nПример:")
        print("  python backend/check_sync_status.py 4d60e150-43d2-4c02-8425-aded2a985503")
        sys.exit(1)
    
    task_id = sys.argv[1]
    asyncio.run(check_task_status(task_id))

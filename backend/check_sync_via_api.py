"""
Проверка статуса синхронизации через API
Использование: python backend/check_sync_via_api.py <task_id>
"""
import sys
import requests
import time

def check_status_via_api(task_id: str):
    """Проверяет статус через HTTP API"""
    url = f"http://localhost:8000/api/products/sync-1c/status?task_id={task_id}"
    
    print(f"\n{'='*60}")
    print(f"Проверка статуса через API: {task_id}")
    print(f"{'='*60}\n")
    
    try:
        while True:
            response = requests.get(url, timeout=5)
            
            if response.status_code == 404:
                print(f"ERROR: Задача {task_id} не найдена!")
                print("Возможные причины:")
                print("  - Сервер был перезапущен (задачи хранятся в памяти)")
                print("  - Неверный task_id")
                break
            
            if response.status_code != 200:
                print(f"ERROR: HTTP {response.status_code}: {response.text}")
                break
            
            data = response.json()
            
            status = data.get("status", "unknown")
            progress = data.get("progress", 0)
            current = data.get("current", 0)
            total = data.get("total", 0)
            stage = data.get("stage", "")
            stage_desc = data.get("stage_description", "")
            error = data.get("error")
            
            print(f"\r[{status.upper():8}] {progress:5.1f}% | {current}/{total} | {stage_desc[:60]:60}", end="", flush=True)
            
            if status == "completed":
                print(f"\n\nOK: Задача завершена успешно!")
                result = data.get("result", {})
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
            
            time.sleep(2)
            
    except requests.exceptions.ConnectionError:
        print(f"\nERROR: Не удалось подключиться к серверу!")
        print("Убедитесь, что бэкенд запущен на http://localhost:8000")
    except KeyboardInterrupt:
        print(f"\n\nПрервано пользователем")
    except Exception as e:
        print(f"\nERROR: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python backend/check_sync_via_api.py <task_id>")
        print("\nПример:")
        print("  python backend/check_sync_via_api.py 4d60e150-43d2-4c02-8425-aded2a985503")
        sys.exit(1)
    
    task_id = sys.argv[1]
    check_status_via_api(task_id)

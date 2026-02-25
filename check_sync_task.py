import requests
import json
import sys

task_id = sys.argv[1] if len(sys.argv) > 1 else "e4628773-0eae-4dae-bd9e-2de82327234c"

try:
    r = requests.get(f'http://localhost:8000/api/products/sync-1c/status?task_id={task_id}')
    r.raise_for_status()
    data = r.json()
    
    print("=" * 60)
    print(f"Статус задачи синхронизации: {task_id}")
    print("=" * 60)
    print(f"Статус: {data.get('status')}")
    print(f"Тип задачи: {data.get('task_type')}")
    print(f"Прогресс: {data.get('progress')}%")
    print(f"Текущий: {data.get('current')}/{data.get('total')}")
    print(f"Этап: {data.get('stage')}")
    print(f"Описание этапа: {data.get('stage_description')}")
    print(f"Начато: {data.get('started_at')}")
    print(f"Завершено: {data.get('completed_at') or 'Нет'}")
    if data.get('error'):
        print(f"ОШИБКА: {data.get('error')}")
    if data.get('result'):
        print(f"Результат: {json.dumps(data.get('result'), indent=2, ensure_ascii=False)}")
    print("=" * 60)
    
except Exception as e:
    print(f"Ошибка при проверке статуса: {e}")

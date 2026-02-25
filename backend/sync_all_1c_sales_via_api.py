"""
Скрипт для полной синхронизации всех доступных данных о продажах из 1С через API
Использует HTTP запросы к API вместо прямого доступа к БД
"""
import asyncio
import httpx
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Исправление кодировки для Windows
if sys.platform == 'win32':
    import codecs
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# Загружаем переменные окружения
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)


async def sync_all_1c_sales_via_api(
    api_base_url: str = "http://localhost:8000",
    start_date: datetime = None,
    end_date: datetime = None,
    chunk_days: int = 30,
    incremental: bool = True
):
    """
    Полная синхронизация всех доступных данных из 1С через API
    
    Args:
        api_base_url: Базовый URL API
        start_date: Начальная дата (если None, используется 2025-11-10)
        end_date: Конечная дата (если None, используется текущая дата)
        chunk_days: Количество дней в одном чанке
        incremental: Инкрементальная синхронизация
    """
    # Определяем даты
    if not start_date:
        start_date = datetime(2025, 11, 10, 0, 0, 0)
    
    if not end_date:
        end_date = datetime.now()
    
    print("=" * 80)
    print("ПОЛНАЯ СИНХРОНИЗАЦИЯ ДАННЫХ О ПРОДАЖАХ ИЗ 1С (через API)")
    print("=" * 80)
    print(f"API URL: {api_base_url}")
    print(f"Период: {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}")
    print(f"Режим: {'Инкрементальная' if incremental else 'Полная'} синхронизация")
    print(f"Размер чанка: {chunk_days} дней")
    print()
    
    total_days = (end_date - start_date).days + 1
    print(f"Всего дней для синхронизации: {total_days}")
    
    # Разбиваем период на чанки
    chunks = []
    current_start = start_date
    
    while current_start < end_date:
        current_end = min(current_start + timedelta(days=chunk_days - 1), end_date)
        chunks.append((current_start, current_end))
        current_start = current_end + timedelta(seconds=1)
    
    print(f"Период разбит на {len(chunks)} чанков")
    print()
    
    total_stats = {
        "total_records": 0,
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "chunks_processed": 0,
        "chunks_total": len(chunks)
    }
    
    async with httpx.AsyncClient(timeout=300.0) as client:
        for i, (chunk_start, chunk_end) in enumerate(chunks, 1):
            print("-" * 80)
            print(f"Обработка чанка {i}/{len(chunks)}: {chunk_start.strftime('%Y-%m-%d')} - {chunk_end.strftime('%Y-%m-%d')}")
            print("-" * 80)
            
            try:
                url = f"{api_base_url}/api/analytics/1c-sales/sync"
                params = {
                    "start_date": chunk_start.strftime('%Y-%m-%dT%H:%M:%S'),
                    "end_date": chunk_end.strftime('%Y-%m-%dT%H:%M:%S'),
                    "incremental": "true" if incremental else "false"
                }
                
                response = await client.post(url, params=params)
                response.raise_for_status()
                
                result = response.json()
                
                print(f"Чанк {i} завершен:")
                print(f"  - Всего записей: {result.get('total_records', 0)}")
                print(f"  - Добавлено: {result.get('inserted', 0)}")
                print(f"  - Обновлено: {result.get('updated', 0)}")
                print(f"  - Пропущено: {result.get('skipped', 0)}")
                
                # Суммируем статистику
                total_stats["total_records"] += result.get('total_records', 0)
                total_stats["inserted"] += result.get('inserted', 0)
                total_stats["updated"] += result.get('updated', 0)
                total_stats["skipped"] += result.get('skipped', 0)
                total_stats["chunks_processed"] += 1
                
            except httpx.HTTPStatusError as e:
                print(f"❌ HTTP ошибка при обработке чанка {i}: {e.response.status_code}")
                print(f"   Ответ: {e.response.text[:500]}")
                continue
            except Exception as e:
                print(f"❌ Ошибка при обработке чанка {i}: {e}")
                continue
            
            # Небольшая пауза между чанками
            if i < len(chunks):
                await asyncio.sleep(1)
    
    # Итоговая статистика
    print()
    print("=" * 80)
    print("ИТОГОВАЯ СТАТИСТИКА")
    print("=" * 80)
    print(f"Обработано чанков: {total_stats['chunks_processed']}/{total_stats['chunks_total']}")
    print(f"Всего записей: {total_stats['total_records']:,}")
    print(f"Добавлено: {total_stats['inserted']:,}")
    print(f"Обновлено: {total_stats['updated']:,}")
    print(f"Пропущено: {total_stats['skipped']:,}")
    print("=" * 80)
    
    return total_stats


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Полная синхронизация данных о продажах из 1С через API')
    parser.add_argument(
        '--api-url',
        type=str,
        default='http://localhost:8000',
        help='Базовый URL API (по умолчанию: http://localhost:8000)'
    )
    parser.add_argument(
        '--start-date',
        type=str,
        help='Начальная дата (формат: YYYY-MM-DD, по умолчанию: 2025-11-10)'
    )
    parser.add_argument(
        '--end-date',
        type=str,
        help='Конечная дата (формат: YYYY-MM-DD, по умолчанию: текущая дата)'
    )
    parser.add_argument(
        '--chunk-days',
        type=int,
        default=30,
        help='Количество дней в одном чанке (по умолчанию: 30)'
    )
    parser.add_argument(
        '--full-sync',
        action='store_true',
        help='Полная синхронизация (перезапись существующих данных)'
    )
    
    args = parser.parse_args()
    
    # Парсим даты
    start_date = None
    if args.start_date:
        start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
    
    end_date = None
    if args.end_date:
        end_date = datetime.strptime(args.end_date, '%Y-%m-%d')
        end_date = end_date.replace(hour=23, minute=59, second=59)
    
    incremental = not args.full_sync
    
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    try:
        result = asyncio.run(sync_all_1c_sales_via_api(
            api_base_url=args.api_url,
            start_date=start_date,
            end_date=end_date,
            chunk_days=args.chunk_days,
            incremental=incremental
        ))
        
        print("\n✅ Синхронизация успешно завершена!")
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n❌ Синхронизация прервана пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

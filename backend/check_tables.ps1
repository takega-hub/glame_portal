# Скрипт для проверки существования таблиц
# Использование: .\check_tables.ps1

Write-Host "=== Проверка таблиц Content Agent ===" -ForegroundColor Cyan
Write-Host ""

$checkScript = @"
import asyncio
import asyncpg
import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

async def check_tables():
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = int(os.getenv('DB_PORT', '5433'))
    DB_USER = os.getenv('DB_USER', 'glame_user')
    DB_PASSWORD = os.getenv('DB_PASSWORD', 'glame_password')
    DB_NAME = os.getenv('DB_NAME', 'glame_db')
    
    try:
        conn = await asyncpg.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        
        tables = await conn.fetch('''
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name LIKE 'content_%'
            ORDER BY table_name
        ''')
        
        await conn.close()
        
        if tables:
            print('✅ Найдены таблицы:')
            for t in tables:
                print(f'   - {t[\"table_name\"]}')
            return True
        else:
            print('❌ Таблицы не найдены')
            return False
            
    except Exception as e:
        print(f'❌ Ошибка подключения: {e}')
        return False

if __name__ == '__main__':
    import sys
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    success = asyncio.run(check_tables())
    sys.exit(0 if success else 1)
"@

$checkScript | Out-File -FilePath "check_tables_temp.py" -Encoding UTF8

try {
    python check_tables_temp.py
    $exitCode = $LASTEXITCODE
    
    if ($exitCode -eq 0) {
        Write-Host ""
        Write-Host "✅ Все таблицы существуют!" -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "❌ Таблицы отсутствуют. Запустите:" -ForegroundColor Red
        Write-Host "  .\fix_content_tables.ps1" -ForegroundColor Yellow
    }
} catch {
    Write-Host ""
    Write-Host "❌ Ошибка: $_" -ForegroundColor Red
} finally {
    if (Test-Path "check_tables_temp.py") {
        Remove-Item "check_tables_temp.py"
    }
}

Write-Host ""

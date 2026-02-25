# Скрипт для создания таблиц content_plans, content_items, content_publications
# Использование: .\fix_content_tables.ps1

Write-Host "=== Создание таблиц для Content Agent ===" -ForegroundColor Cyan
Write-Host ""

# Проверка подключения к БД
Write-Host "Проверка подключения к БД..." -ForegroundColor Yellow

try {
    python create_content_tables.py
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "✅ Таблицы успешно созданы!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Теперь перезапустите backend и обновите страницу в браузере." -ForegroundColor Cyan
    } else {
        Write-Host ""
        Write-Host "❌ Ошибка при создании таблиц. Проверьте логи выше." -ForegroundColor Red
        Write-Host ""
        Write-Host "Возможные причины:" -ForegroundColor Yellow
        Write-Host "1. Docker контейнеры не запущены" -ForegroundColor Yellow
        Write-Host "2. Неправильные параметры подключения к БД" -ForegroundColor Yellow
        Write-Host "3. База данных не создана" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Проверьте статус Docker контейнеров:" -ForegroundColor Cyan
        Write-Host "  cd ..\infra" -ForegroundColor White
        Write-Host "  docker-compose ps" -ForegroundColor White
    }
} catch {
    Write-Host ""
    Write-Host "❌ Ошибка выполнения скрипта: $_" -ForegroundColor Red
}

Write-Host ""

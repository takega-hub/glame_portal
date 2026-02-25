# Скрипт для проверки статуса backend
Write-Host "Проверка статуса backend..." -ForegroundColor Cyan

# Проверка порта 8000
$port8000 = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($port8000) {
    Write-Host "✓ Порт 8000 занят (backend может быть запущен)" -ForegroundColor Green
    Write-Host "  PID процесса: $($port8000.OwningProcess)" -ForegroundColor Gray
} else {
    Write-Host "✗ Порт 8000 свободен (backend НЕ запущен)" -ForegroundColor Red
}

# Проверка доступности API
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 2 -ErrorAction Stop
    Write-Host "✓ Backend отвечает на /health" -ForegroundColor Green
    Write-Host "  Статус: $($response.StatusCode)" -ForegroundColor Gray
} catch {
    Write-Host "✗ Backend не отвечает на /health" -ForegroundColor Red
    Write-Host "  Ошибка: $($_.Exception.Message)" -ForegroundColor Gray
}

Write-Host "`nДля запуска backend выполните:" -ForegroundColor Yellow
Write-Host "  cd backend" -ForegroundColor White
Write-Host "  .\start_backend.ps1" -ForegroundColor White

# Скрипт для инициализации базы данных на Windows PowerShell
Write-Host "Инициализация базы данных GLAME AI Platform..." -ForegroundColor Cyan
Write-Host ""

# Активируем виртуальное окружение если оно существует
if (Test-Path "venv\Scripts\Activate.ps1") {
    & "venv\Scripts\Activate.ps1"
}

# Запускаем Python скрипт
python init_database.py

Read-Host "Нажмите Enter для выхода"

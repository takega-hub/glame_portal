@echo off
REM Скрипт для инициализации базы данных на Windows
echo Инициализация базы данных GLAME AI Platform...
echo.

REM Активируем виртуальное окружение если оно существует
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

REM Запускаем Python скрипт
python init_database.py

pause

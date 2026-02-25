@echo off
REM Скрипт для создания таблиц через psql (обходит проблему с psycopg2 на Windows)
REM Требует установленный PostgreSQL client tools

echo Creating tables in PostgreSQL...
docker exec -i glame_postgres psql -U glame_user -d glame_db < create_tables.sql

if %ERRORLEVEL% EQU 0 (
    echo Tables created successfully!
) else (
    echo Error creating tables. Make sure PostgreSQL container is running.
    pause
)

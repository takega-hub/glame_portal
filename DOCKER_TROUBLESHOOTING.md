# Решение проблем с Docker Desktop

## Ошибка: "Docker Desktop is unable to start"

### Причины и решения:

1. **Docker Desktop не запущен**
   - Открой Docker Desktop вручную из меню Пуск
   - Дождись полной загрузки (иконка в трее должна быть зелёной)

2. **Проблемы с виртуализацией**
   - Убедись, что включена виртуализация в BIOS/UEFI
   - Проверь, что Hyper-V или WSL2 включены в Windows Features

3. **Конфликт с другими виртуальными машинами**
   - Закрой VirtualBox, VMware, если они запущены
   - Перезапусти Docker Desktop

4. **Переустановка Docker Desktop**
   - Полностью удали Docker Desktop
   - Скачай последнюю версию: https://www.docker.com/products/docker-desktop
   - Установи заново и перезагрузи компьютер

5. **Проверка через PowerShell (от администратора)**
   ```powershell
   # Проверь статус Docker
   docker version
   
   # Проверь, запущен ли Docker daemon
   docker ps
   ```

## Альтернатива: Запуск без Docker

Если Docker не работает, можно запустить сервисы локально:

### Минимальный вариант (только PostgreSQL)

1. Установи PostgreSQL: https://www.postgresql.org/download/windows/
2. Создай базу через pgAdmin или psql:
   ```sql
   CREATE DATABASE glame_db;
   CREATE USER glame_user WITH PASSWORD 'glame_password';
   GRANT ALL PRIVILEGES ON DATABASE glame_db TO glame_user;
   ```

3. Qdrant и Redis можно пропустить на начальном этапе (код будет работать без них, но с ограничениями)

### Проверка работы Docker

После запуска Docker Desktop выполни:
```cmd
docker ps
```

Если команда работает без ошибок - Docker готов к использованию.

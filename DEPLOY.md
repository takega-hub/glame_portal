# DEPLOY (Production)

Цель: чтобы **данные (контент) точно сохранялись** и переносились между серверами.

## Что “переносится” с контейнером

- **Контейнеры** (образы) — это код. Они легко пересобираются/перезапускаются.
- **Данные** живут в:
  - **Docker volumes** (на диске сервера), или
  - во **внешней БД** (managed Postgres).

Если вы поднимете контейнер Postgres на новом сервере **без restore** — данных не будет.

## Рекомендованный прод-формат (самый простой и надёжный для MVP)

- Один Linux-сервер (Ubuntu) + `docker compose`
- Всё в контейнерах: `nginx` + `frontend` + `backend` + `postgres` + `qdrant` + `redis`
- Данные в volumes + регулярный backup (pg_dump)

## 1) Подготовка сервера (Ubuntu)

- Установить Docker Engine + Docker Compose plugin
- Открыть наружу только:
  - **80/tcp** (и позже 443/tcp, когда добавим TLS)

## 2) Настройка env

Создайте файл `.env` рядом с репозиторием (в корне проекта) по примеру `ENV.example`.

Минимум нужно задать:
- `OPENROUTER_API_KEY`
- `JWT_SECRET_KEY`

## 3) Первый запуск (prod)

Из корня проекта:

```bash
docker compose -f infra/docker-compose.prod.yml up -d --build
```

Проверка:
- `http://<server-ip>/` (frontend)
- `http://<server-ip>/docs` (backend swagger через nginx не проксируется; если нужно — добавим location)

## 4) Миграции БД

В прод-образе backend есть Alembic migrations (см. `backend/Dockerfile.prod`), поэтому миграции запускаем внутри контейнера backend:

```bash
docker exec -it glame_backend alembic upgrade head
```

## 5) Обновления (deploy новой версии)

**Через Git** (если проект клонирован на сервере):

```bash
./scripts/deploy_from_git.sh
```

**Вручную** (или без Git):

```bash
docker compose -f infra/docker-compose.prod.yml pull
docker compose -f infra/docker-compose.prod.yml up -d
docker exec -it glame_backend alembic upgrade head
```

## 6) Backup / Restore (самое важное для переноса контента)

### Backup Postgres (Docker)

Linux/macOS:

```bash
./scripts/backup_postgres_docker.sh
```

Windows PowerShell:

```powershell
.\scripts\backup_postgres_docker.ps1
```

Бэкап будет в `./backups/*.dump`.

### Restore Postgres (Docker)

Linux/macOS:

```bash
./scripts/restore_postgres_docker.sh ./backups/glame_db_YYYYMMDDTHHMMSSZ.dump
```

Windows PowerShell:

```powershell
.\scripts\restore_postgres_docker.ps1 -DumpFile .\backups\glame_db_YYYYMMDDTHHMMSSZ.dump
```

## 7) Как переносим контент на новый сервер (пошагово)

На старом сервере:
- сделать backup Postgres (см. выше)
- скопировать файл `*.dump` на новый сервер (scp/WinSCP)

На новом сервере:
- поднять инфраструктуру `docker compose -f infra/docker-compose.prod.yml up -d`
- выполнить restore `*.dump`
- прогнать миграции `alembic upgrade head`

Для деплоя на конкретный сервер (5.101.179.47), переноса данных с Windows и скриптов обновления см. **[docs/DEPLOY_SERVER.md](docs/DEPLOY_SERVER.md)**.

## 8) Qdrant и Redis (кратко)

- **Redis**: обычно кэш, можно не переносить (если не используем как основное хранилище).
- **Qdrant**:
  - если вы загружаете туда “базу знаний”, то для 100% переноса либо
    - делаем backup его volume (`qdrant_data`), либо
    - повторно импортируем знания из исходных файлов/документов.


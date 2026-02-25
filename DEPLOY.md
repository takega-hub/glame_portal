# Деплой GLAME AI (Production)

Единая инструкция по развёртыванию на portal.glamejewelry.ru: подготовка сервера, Git, первый запуск, обновления, бэкапы и перенос данных.

## Что важно про данные

- **Контейнеры (образы)** — это код, их можно пересобирать и перезапускать.
- **Данные** хранятся в **Docker volumes** (Postgres, Qdrant, Redis, файлы backend) или во внешней БД. Если поднять Postgres на новом сервере без restore — данных не будет. Для переноса контента нужны бэкапы и восстановление (см. разделы 8–11).

**Рекомендуемый формат:** один Linux-сервер (Ubuntu) + Docker Compose; всё в контейнерах (nginx, frontend, backend, postgres, qdrant, redis); данные в volumes + регулярный backup (pg_dump).

---

# Деплой на portal.glamejewelry.ru

Пошаговая инструкция под конкретный сервер и домен.

**Сайт:** [http://portal.glamejewelry.ru/](http://portal.glamejewelry.ru/)  
**Репозиторий:** [https://github.com/takega-hub/glame_portal](https://github.com/takega-hub/glame_portal)

### Доступы к управлению

- **Portainer** — веб-интерфейс для Docker на сервере: `https://5.101.179.47:9443` (логин и пароль храните в менеджере паролей).
- **Панель управления сайтом** — логин и пароль храните в менеджере паролей; не добавляйте их в репозиторий и в файлы конфигурации.
- **FTP** — для загрузки файлов на хостинг (если используется). Для деплоя через Docker нужен **SSH**-доступ к серверу; FTP не заменяет SSH для запуска контейнеров.

## Требования

- **Сервер**: Ubuntu (или аналог) с SSH-доступом (для Docker). Доступы к панели управления и FTP храните в безопасном месте, **не добавляйте пароли в репозиторий**.
- **Домен**: `portal.glamejewelry.ru` — A-запись должна указывать на IP сервера.
- **Порты**: 80 (HTTP), при необходимости 443 (HTTPS).

---

## 1. Подготовка сервера

### 1.1 Установка Docker и Docker Compose

На сервере (Ubuntu):

```bash
# Docker Engine
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Проверка
docker --version
docker compose version
```

### 1.2 Открытие портов

Убедитесь, что открыты порты 80 (и 443 при использовании HTTPS), например через ufw:

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

---

## 2. Развёртывание и обновление через Git

Портал загружается и обновляется через Git: сначала выкладываете локальный проект на GitHub, затем на сервере клонируете репозиторий; дальше обновление — `git push` с локальной машины и `git pull` + перезапуск на сервере.

### 2.0 Загрузка локальной версии на GitHub

Перед первым деплоем на сервер нужно один раз отправить код в репозиторий [https://github.com/takega-hub/glame_portal](https://github.com/takega-hub/glame_portal).

**На локальной машине** в корне проекта (где лежат `backend/`, `frontend/`, `infra/` и т.д.):

1. Инициализировать Git (если ещё не сделано) и привязать удалённый репозиторий:
   ```bash
   git init
   git remote add origin https://github.com/takega-hub/glame_portal.git
   ```
   Если репозиторий уже инициализирован и `origin` другой — замените: `git remote set-url origin https://github.com/takega-hub/glame_portal.git`

2. Убедиться, что в `.gitignore` не попадают лишние каталоги (уже должны быть: `node_modules/`, `backend/venv/`, `.env`, `backups/`, `__pycache__/`, `.next/`). Файл `.env` с секретами в репозиторий не коммитить.

3. Добавить файлы и сделать первый push:
   ```bash
   git add .
   git commit -m "Initial commit: GLAME portal"
   git branch -M main
   git push -u origin main
   ```
   Если основная ветка у вас называется `master`, используйте `git push -u origin master`. При запросе авторизации укажите логин GitHub и пароль (или personal access token для HTTPS).

После этого репозиторий на GitHub будет содержать актуальный код, и на сервере можно выполнить клонирование (раздел 2.1).

### 2.1 Первая загрузка на сервер

По SSH на сервере:

```bash
cd ~
git clone https://github.com/takega-hub/glame_portal.git glame-platform
cd glame-platform
```

Репозиторий: [https://github.com/takega-hub/glame_portal](https://github.com/takega-hub/glame_portal).  
Если репозиторий приватный, настройте SSH-ключ на сервере или используйте токен в URL (например `https://<token>@github.com/takega-hub/glame_portal.git`).

### 2.2 Обновление портала (после git push)

**На сервере** (по SSH) из каталога проекта выполните:

```bash
cd ~/glame-platform
./scripts/deploy_from_git.sh
```

Скрипт сам сделает `git pull`, пересборку контейнеров (`docker compose up -d --build`) и миграции БД (`alembic upgrade head`). **Перед первым запуском** на сервере выдайте права на выполнение:

```bash
chmod +x scripts/deploy_from_git.sh
./scripts/deploy_from_git.sh
```

**С локальной Windows** (после того как вы сделали `git push`): можно не заходить на сервер вручную — скрипт по SSH подтянет код и перезапустит стек:

```powershell
.\scripts\update_server.ps1 -ServerUser glame -ServerHost portal.glamejewelry.ru -ServerPath /home/glame/glame-platform -UseGit
```

Подставьте своего пользователя SSH и путь к проекту. Опция `-UseGit` означает: на сервере выполнить `git pull` и `./scripts/deploy_from_git.sh` (без загрузки архива с Windows).

### 2.3 Альтернатива: загрузка без Git (scp/архив)

Если Git на сервере не используется, можно один раз скопировать проект по SCP или использовать `update_server.ps1` **без** `-UseGit` — тогда скрипт соберёт архив и загрузит его на сервер. Для регулярных обновлений удобнее работать через Git (раздел 2.2).

---

## 3. Настройка окружения (.env)

На сервере в корне проекта:

```bash
cp .env.example .env
nano .env
```

Обязательно задайте:

- `OPENROUTER_API_KEY` — ключ OpenRouter.
- `JWT_SECRET_KEY` — секрет для JWT (уникальная строка для продакшена).

Остальные переменные для prod можно оставить по умолчанию (Postgres, Qdrant, Redis уже заданы в `infra/docker-compose.prod.yml` для работы внутри Docker-сети). При использовании домена переменные `NEXT_PUBLIC_API_URL` и `NEXT_PUBLIC_WS_URL` в prod можно не менять (фронт ходит на тот же хост через nginx).

---

## 4. Первый запуск

Из **корня проекта** на сервере:

```bash
docker compose -f infra/docker-compose.prod.yml up -d --build
```

После поднятия контейнеров — миграции БД:

```bash
docker exec -it glame_backend alembic upgrade head
```

### Проверка

- Фронт: [http://portal.glamejewelry.ru/](http://portal.glamejewelry.ru/)
- API: `http://portal.glamejewelry.ru/api/...`

При первом заходе браузер запросит логин и пароль (HTTP Basic Auth). Пользователь по умолчанию: **admin**, пароль: **changeme**. Рекомендуется сменить пароль после первого входа (см. ниже).

---

## 5. Доступ по паролю (Basic Auth)

Портал закрыт одним пользователем: **admin**. Файл паролей: `infra/.htpasswd`.

**Сменить пароль для admin:**

На сервере из корня проекта (файл `infra/.htpasswd` будет перезаписан на хосте):

```bash
cd infra
docker run --rm -it -v "$(pwd):/data" -w /data httpd:alpine htpasswd -c .htpasswd admin
```

Введите новый пароль при запросе. Затем перезапустите nginx:

```bash
docker restart glame_nginx
```

Добавить второго пользователя (без `-c`, чтобы не затереть admin):

```bash
cd infra
docker run --rm -it -v "$(pwd):/data" -w /data httpd:alpine htpasswd .htpasswd second_user
```

---

## 6. Управление через Portainer

На сервере уже запущен **Portainer** (доступ: `https://5.101.179.47:9443`). Через него можно разворачивать и обновлять стек GLAME без SSH.

### 6.1 Развёртывание стека (первый раз)

1. **Portainer** → выберите окружение **local** (Standalone Docker).
2. **Stacks** → **Add stack**.
3. Имя стека, например: `glame`.
4. **Build method**: выберите **Repository** или **Upload**.
   - **Вариант «Из файла на сервере»**: если проект уже скопирован на сервер (например в `/home/glame/glame-platform`), укажите путь к compose-файлу:  
     `/home/glame/glame-platform/infra/docker-compose.prod.yml`  
     (в Portainer это может быть через «Custom template» / «Load from file» при наличии доступа к путям на хосте).
   - **Вариант «Web editor»**: вставьте содержимое `infra/docker-compose.prod.yml`. Тогда образы backend и frontend нужно будет собрать отдельно (через Images → Build) или заранее загрузить на сервер код и указать контекст сборки.
5. **Environment variables**: добавьте переменные (имена и значения):
   - `OPENROUTER_API_KEY` — ключ OpenRouter.
   - `JWT_SECRET_KEY` — секрет для JWT.
   - При необходимости: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` (по умолчанию в compose уже заданы).
6. Запустите стек (**Deploy the stack**). Дождитесь сборки образов и запуска контейнеров.

Важно: для сборки backend и frontend в compose указаны `context: ..` и `context: ../frontend`. Поэтому при деплое через Portainer **репозиторий должен лежать на сервере**, а стек лучше разворачивать из каталога проекта (путь к `docker-compose.prod.yml`) или предварительно собрать образы по SSH и в compose использовать только `image:`.

### 6.2 Миграции БД после деплоя

1. **Containers** → найдите контейнер **glame_backend**.
2. Откройте контейнер → **Console** (или **Exec**).
3. Выберите оболочку (например `sh`) и выполните:
   ```bash
   alembic upgrade head
   ```
4. Выйдите из консоли.

### 6.3 Перезапуск и обновление

- **Обновление из Git**: на сервере выполните `cd /path/to/glame-platform && ./scripts/deploy_from_git.sh` (по SSH или через задачу). Либо в Portainer: **Stacks** → стек `glame` → **Editor** — после `git pull` на сервере нажмите **Update the stack** (с опцией пересборки образов).
- **Перезапуск стека**: **Stacks** → выберите стек `glame` → **Editor** (при необходимости обновите compose) → **Update the stack**.
- **Перезапуск одного сервиса**: **Containers** → выберите контейнер (например `glame_backend`) → **Restart**.
- **Логи**: **Containers** → контейнер → **Logs**.
- **Тома (volumes)**: **Volumes** — здесь будут `postgres_data`, `qdrant_data`, `redis_data`, `backend_uploads`, `backend_static`, `backend_generated_messages` (имена могут быть с префиксом стека, например `glame_postgres_data`).

### 6.4 Пароль для портала (Basic Auth)

Файл `infra/.htpasswd` монтируется в контейнер nginx. Чтобы изменить пароль:

1. На сервере (по SSH) обновите `infra/.htpasswd` (команды в разделе [5. Доступ по паролю](#5-доступ-по-паролю-basic-auth)).
2. В Portainer: **Containers** → **glame_nginx** → **Restart**.

Либо смонтируйте в стеке свой `.htpasswd` с хоста и после изменения файла перезапустите только nginx.

---

## 7. Домен и nginx

В `infra/nginx.conf` указан домен **portal.glamejewelry.ru**. Убедитесь, что A-запись домена указывает на IP сервера. Перезапуск nginx после изменений:

```bash
docker restart glame_nginx
```

SSL (HTTPS) для portal.glamejewelry.ru можно добавить позже (certbot / Let's Encrypt).

---

## 8. Регулярный бэкап Postgres (опционально)

На сервере можно настроить cron для ежедневного бэкапа:

```bash
crontab -e
```

Добавьте (подставьте путь к проекту):

```cron
0 3 * * * cd /home/user/glame-platform && ./scripts/backup_postgres_docker.sh
```

Бэкапы будут в каталоге `./backups/` в корне проекта. При необходимости настройте копирование в другое хранилище.

---

## 9. Перенос данных с локальной Windows на сервер

Используйте скрипт **`scripts/migrate_to_server.ps1`** — он собирает дамп Postgres, бэкап Qdrant (snapshot), архив файлов backend и копирует всё на сервер. Запуск с Windows (PowerShell):

```powershell
.\scripts\migrate_to_server.ps1 -ServerUser glame -ServerHost portal.glamejewelry.ru -ServerPath /home/glame/glame-platform
```

Подставьте своего пользователя SSH и путь к проекту на сервере. Опционально: `-KeyPath C:\Users\...\.ssh\id_rsa` для SSH-ключа.

После копирования выполните на сервере шаги из раздела [10. Восстановление данных на сервере](#10-восстановление-данных-на-сервере).

---

## 10. Восстановление данных на сервере

После того как скрипт миграции скопировал файлы на сервер:

### 10.1 Восстановление PostgreSQL

Контейнеры должны быть запущены. Укажите путь к скопированному dump:

```bash
./scripts/restore_postgres_docker.sh ./backups/glame_db_YYYYMMDDTHHMMSSZ.dump
```

Переменные `POSTGRES_CONTAINER`, `POSTGRES_USER`, `POSTGRES_DB` по умолчанию соответствуют prod-compose (`glame_postgres`, `glame_user`, `glame_db`).

### 10.2 Восстановление файлов backend (uploads, static, generated_messages)

Архив `data_backend_files.tar.gz` (или `.zip`) скопирован в каталог проекта на сервере. Распакуйте содержимое в тома backend. Данные монтируются в контейнер по путям:

- `uploads` → volume `backend_uploads`
- `static` → volume `backend_static`
- `backend/generated_messages` → volume `backend_generated_messages`

Пример (если архив распакован в `./migration_data/`):

```bash
# Остановить backend, чтобы смонтировать данные
docker compose -f infra/docker-compose.prod.yml stop backend

# Вариант через docker run с volume
docker run --rm -v glame-platform_backend_uploads:/target -v $(pwd)/migration_data/uploads:/src alpine sh -c "cp -a /src/. /target/"
docker run --rm -v glame-platform_backend_static:/target -v $(pwd)/migration_data/static:/src alpine sh -c "cp -a /src/. /target/"
docker run --rm -v glame-platform_backend_generated_messages:/target -v $(pwd)/migration_data/generated_messages:/src alpine sh -c "cp -a /src/. /target/"

# Запустить backend снова
docker compose -f infra/docker-compose.prod.yml start backend
```

Имена томов могут иметь префикс проекта (например `glame-platform_backend_uploads`). Уточните их командой `docker volume ls`.

### 10.3 Восстановление Qdrant

Два варианта.

**Вариант A — восстановление из snapshot (рекомендуется).**

Скрипт миграции создаёт snapshot по каждой коллекции Qdrant и копирует файлы в `backups/` на сервере. Для каждой коллекции выполните (подставьте имя коллекции и имя файла):

```bash
chmod +x scripts/restore_qdrant_from_snapshot.sh
./scripts/restore_qdrant_from_snapshot.sh ./backups/qdrant_<collection>_<name>.snapshot <collection>
```

Подробности в разделе [11. Бэкап и восстановление Qdrant](#11-бэкап-и-восстановление-qdrant).

**Вариант B — копирование volume.**

Если вы скопировали весь volume Qdrant с локальной машины (данные Docker Desktop), остановите контейнер Qdrant, подмените содержимое тома на сервере (или создайте новый том из скопированных данных) и запустите контейнер снова. Структура должна соответствовать тому, что ожидает Qdrant (`/qdrant/storage`).

---

## 11. Бэкап и восстановление Qdrant

### Создание snapshot (локально или на сервере)

Qdrant предоставляет API для создания snapshot по коллекции. Snapshot — tar-архив с данными коллекции.

**Список коллекций:**

```bash
curl -s http://localhost:6333/collections
```

**Создать snapshot для коллекции `knowledge` (подставьте своё имя):**

```bash
curl -X POST "http://localhost:6333/collections/knowledge/snapshots?wait=true"
```

Ответ содержит имя файла snapshot (например `knowledge-2024-02-25-12-00-00.snapshot`). Файл появляется в каталоге snapshot внутри контейнера (или в volume). Скачать его можно через API:

```bash
curl -O "http://localhost:6333/collections/knowledge/snapshots/knowledge-2024-02-25-12-00-00.snapshot"
```

Скрипт `migrate_to_server.ps1` автоматизирует создание snapshot для всех коллекций и копирование на сервер.

### Восстановление из snapshot на сервере

Используйте скрипт (указать путь к файлу snapshot и имя коллекции):

```bash
chmod +x scripts/restore_qdrant_from_snapshot.sh
./scripts/restore_qdrant_from_snapshot.sh ./backups/qdrant_knowledge_knowledge-2024-02-25.snapshot knowledge
```

Имя коллекции должно совпадать с тем, под которым snapshot был создан (например `knowledge`, `brand_philosophy`, `product_knowledge`). Скрипт копирует файл в контейнер Qdrant и вызывает API восстановления. Если коллекция уже есть, она будет перезаписана данными из snapshot.

---

## 12. Обновление деплоя с локальной версии

**Рекомендуемый способ — через Git:**

1. Локально: `git add` → `git commit` → `git push`.
2. На сервере обновить и перезапустить одним из способов:
   - По SSH: `cd ~/glame-platform && ./scripts/deploy_from_git.sh`
   - С Windows одной командой (скрипт по SSH выполнит то же самое):

```powershell
.\scripts\update_server.ps1 -ServerUser glame -ServerHost portal.glamejewelry.ru -ServerPath /home/glame/glame-platform -UseGit
```

Опция **`-UseGit`**: не загружать архив, а на сервере выполнить `git pull` и `./scripts/deploy_from_git.sh`. Путь `ServerPath` должен указывать на клонированный репозиторий.

**Без Git** (загрузка архива): запустите тот же скрипт **без** `-UseGit` — код будет упакован и скопирован по SCP, затем распакован и развёрнут на сервере.

Опционально: **`-BackupBefore`** — перед обновлением выполнить на сервере бэкап Postgres.

---

## Ссылки на скрипты

| Действие | Локально (Windows) | На сервере (Linux) |
|----------|--------------------|--------------------|
| Бэкап Postgres | `scripts/backup_postgres_docker.ps1` | `scripts/backup_postgres_docker.sh` |
| Восстановление Postgres | — | `scripts/restore_postgres_docker.sh ./backups/glame_db_*.dump` |
| Перенос данных на сервер | `scripts/migrate_to_server.ps1` | — |
| Обновление кода на сервере (через Git) | `scripts/update_server.ps1 -UseGit ...` | `./scripts/deploy_from_git.sh` |
| Обновление кода (архив без Git) | `scripts/update_server.ps1 ...` (без -UseGit) | — |
| Деплой/обновление из Git на сервере | — | `./scripts/deploy_from_git.sh` |
| Восстановление Qdrant | — | `scripts/restore_qdrant_from_snapshot.sh <snapshot_file> <collection_name>` |

### Если сборка Docker падает (frontend/backend)

- **Полный лог сборки** (чтобы увидеть реальную ошибку):  
  `docker compose -f infra/docker-compose.prod.yml build --no-cache frontend 2>&1 | tee build.log`  
  В конце `build.log` будет сообщение от Next.js, TypeScript или ESLint.
- **Мало памяти на сервере**: в `frontend/Dockerfile` уже задано `NODE_OPTIONS=--max-old-space-size=4096`. Если RAM меньше 2 GB, сборка может падать — увеличьте swap или соберите образ на другой машине и загрузите в registry.
- Убедитесь, что в репозитории есть `frontend/package-lock.json` (нужен для `npm ci` в Dockerfile).

См. также [README.md](README.md).

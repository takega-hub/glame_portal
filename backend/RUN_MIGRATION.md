# Решение проблемы с миграцией knowledge_documents

## Проблема
Ошибка `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xc2 in position 61` при выполнении миграций через Alembic/psycopg2.

## Решение 1: Выполнить SQL скрипт напрямую (РЕКОМЕНДУЕТСЯ)

Выполните SQL скрипт напрямую через `psql`:

```bash
# Вариант 1: Через psql с параметрами
psql -U glame_user -d glame_db -h localhost -p 5432 -f create_knowledge_documents_table.sql

# Вариант 2: Если пароль задан в переменной окружения PGPASSWORD
set PGPASSWORD=glame_password
psql -U glame_user -d glame_db -h localhost -p 5432 -f create_knowledge_documents_table.sql

# Вариант 3: Интерактивный ввод пароля
psql -U glame_user -d glame_db -h localhost -p 5432 -f create_knowledge_documents_table.sql
```

## Решение 2: Использовать Python с subprocess

Если `psql` доступен в PATH:

```bash
cd backend
python -c "import subprocess; subprocess.run(['psql', '-U', 'glame_user', '-d', 'glame_db', '-h', 'localhost', '-p', '5432', '-f', 'create_knowledge_documents_table.sql'], env={'PGPASSWORD': 'glame_password'})"
```

## Решение 3: Обновить psycopg2

Попробуйте обновить psycopg2 до последней версии:

```bash
pip install --upgrade psycopg2-binary
```

Или установите psycopg (новая версия):

```bash
pip install psycopg[binary]
```

## Решение 4: Использовать Docker для выполнения миграций

Если PostgreSQL запущен в Docker:

```bash
docker exec -i <postgres_container_name> psql -U glame_user -d glame_db < create_knowledge_documents_table.sql
```

## После создания таблицы

После успешного создания таблицы, отметьте миграцию как выполненную в Alembic:

```bash
cd backend
alembic stamp head
```

Или создайте запись в таблице `alembic_version` вручную:

```sql
INSERT INTO alembic_version (version_num) VALUES ('003_add_knowledge_documents') 
ON CONFLICT DO NOTHING;
```

## Проверка

Проверьте, что таблица создана:

```sql
SELECT * FROM information_schema.tables WHERE table_name = 'knowledge_documents';
\d knowledge_documents
```

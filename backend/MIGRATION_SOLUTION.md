# Решение проблемы с миграцией knowledge_documents

## Проблема
Ошибка `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xc2 in position 61` при выполнении миграций через Alembic/psycopg2 в Windows окружении.

## Решение (выполнено)

### 1. Создание таблицы через Docker
Таблица `knowledge_documents` была создана напрямую через Docker exec, обходя проблему с psycopg2:

```bash
python create_table_docker.py
```

### 2. Отметка миграции как выполненной
Миграция была отмечена как выполненная через Docker exec:

```bash
python stamp_migration_docker.py
```

## Альтернативные способы (если Docker недоступен)

### Вариант 1: Через psql (если установлен PostgreSQL клиент)
```bash
psql -U glame_user -d glame_db -h localhost -p 5432 -f create_knowledge_documents_table.sql
```

### Вариант 2: Через pgAdmin или DBeaver
Откройте файл `backend/create_knowledge_documents_table.sql` и выполните его содержимое в GUI клиенте PostgreSQL.

### Вариант 3: Через Python с asyncpg (если PostgreSQL доступен)
```bash
python create_table_asyncpg.py
```

## Проверка

Проверьте, что таблица создана:

```bash
python verify_table.py
```

Или вручную через Docker:

```bash
docker exec glame_postgres psql -U glame_user -d glame_db -c "\d knowledge_documents"
```

## Текущий статус

✅ Таблица `knowledge_documents` создана  
✅ Миграция `003_knowledge_documents` отмечена как выполненная  
✅ Индексы созданы  
✅ Функциональность базы знаний готова к использованию

## Примечание

Проблема с psycopg2 в Windows окружении остается нерешенной. Для будущих миграций рекомендуется:
1. Использовать Docker exec для выполнения SQL напрямую
2. Или использовать альтернативные способы подключения (asyncpg через Python)
3. Или выполнять миграции на Linux/Mac, где проблема не возникает

-- Скрипт для изменения колонки email на nullable в таблице users
-- Позволяет создавать покупателей без email адреса

-- Удаляем уникальный индекс (если существует)
DROP INDEX IF EXISTS ix_users_email;

-- Изменяем колонку email на nullable
ALTER TABLE users ALTER COLUMN email DROP NOT NULL;

-- Создаем частичный уникальный индекс только для не-NULL значений
-- Это позволяет иметь несколько NULL значений, но уникальность для не-NULL
CREATE UNIQUE INDEX ix_users_email ON users(email) WHERE email IS NOT NULL;

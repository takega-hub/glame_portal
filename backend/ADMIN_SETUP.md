# Настройка администратора GLAME

## Быстрое создание администратора

### Вариант 1: Дефолтные данные (рекомендуется для первого запуска)

```bash
cd backend
python create_default_admin.py
```

**Данные для входа:**
- Email: `admin@glame.ru`
- Пароль: `admin123`

⚠️ **ВНИМАНИЕ:** После первого входа рекомендуется изменить пароль!

### Вариант 2: Свои данные через командную строку

```bash
cd backend
python create_admin.py --email your@email.com --password yourpassword
```

### Вариант 3: Интерактивный режим

```bash
cd backend
python create_admin.py
```

Скрипт запросит:
- Email администратора
- Пароль (дважды для подтверждения)

## Проверка структуры базы данных

Если возникают ошибки о недостающих колонках, выполните:

```bash
cd backend
python add_role_column.py
```

Этот скрипт добавит все необходимые колонки в таблицу `users`:
- `password_hash` - для хранения паролей
- `role` - роль пользователя (admin, customer, ai_marketer)
- `phone`, `discount_card_number` - для покупателей
- И другие поля для системы покупателей

## Вход в систему

1. Откройте браузер и перейдите на `/login`
2. Выберите вкладку **"Вход"** (не "Для покупателей")
3. Введите email и пароль
4. Нажмите "Войти"

## Доступные роли

- **admin** - полный доступ ко всем функциям
- **ai_marketer** - доступ к AI маркетологу и аналитике
- **content_manager** - управление контентом
- **customer** - обычный покупатель (по умолчанию)

## Изменение роли существующего пользователя

Если нужно изменить роль существующего пользователя, можно использовать SQL:

```sql
UPDATE users SET role = 'admin' WHERE email = 'user@example.com';
```

Или через скрипт `create_admin.py` - он автоматически обновит роль существующего пользователя на 'admin'.

## Устранение проблем

### Ошибка: "column 'role' does not exist"

Выполните:
```bash
cd backend
python add_role_column.py
```

### Ошибка: "column 'password_hash' does not exist"

Тот же скрипт `add_role_column.py` добавит и эту колонку.

### Пользователь не может войти

1. Проверьте, что пользователь существует:
   ```sql
   SELECT email, role FROM users WHERE email = 'your@email.com';
   ```

2. Проверьте, что пароль установлен:
   ```sql
   SELECT email, password_hash IS NOT NULL as has_password FROM users WHERE email = 'your@email.com';
   ```

3. Если пароля нет, создайте администратора заново через скрипт.

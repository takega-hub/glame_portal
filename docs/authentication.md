# Аутентификация в платформе GLAME

## Обзор системы

Платформа GLAME использует двухфакторную систему аутентификации:

1. **Frontend Basic Auth** — базовая HTTP-аутентификация на уровне фронтенда
2. **Backend JWT Auth** — токенная аутентификация для API запросов

## Переменные окружения

### Frontend (.env.local)

```bash
# Basic Auth для доступа к фронтенду
FRONTEND_BASIC_AUTH_USER=admin
FRONTEND_BASIC_AUTH_PASS=Mw6miQvX3LsMpSg

# Режим отладки авторизации (true — пропускать проверку, использовать fake user)
NEXT_PUBLIC_SKIP_APP_AUTH=false
```

### Backend (.env)

```bash
# JWT настройки
JWT_SECRET_KEY=qoGQQ1oRkSn_bg9oDf6V1YUYEb5YN4QhJPxx68XK13o
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24
JWT_REFRESH_EXPIRATION_DAYS=30
```

## Процесс аутентификации

### 1. Доступ к фронтенду

При обращении к `http://localhost:3001` браузер запрашивает Basic Auth credentials:

- Username: `admin`
- Password: `Mw6miQvX3LsMpSg`

После успешной аутентификации пользователь попадает на главную страницу портала.

## Получение токена

### Запрос

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@glame.ru&password=admin123"
```

### Ответ

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

## Использование токена

### Авторизованный запрос к API

Для доступа к защищённым endpoints необходимо передавать токен в заголовке `Authorization`:

```bash
curl http://localhost:8000/api/admin/customers \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

## Обновление токена

Когда срок действия access_token истекает, можно обновить его с помощью refresh_token:

### Запрос

```bash
curl -X POST "http://localhost:8000/api/auth/refresh?refresh_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

### Ответ

```json
{
  "access_token": "новый_access_token",
  "refresh_token": "новый_refresh_token",
  "token_type": "bearer"
}
```

## Хранение токенов на клиенте

Токены хранятся в localStorage браузера:

- `glame_access_token` — JWT access token
- `glame_refresh_token` — JWT refresh token
- `glame_user` — данные пользователя

## Interceptors

Frontend автоматически добавляет токен к каждому запросу через axios interceptor:

```typescript
// src/lib/api.ts
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('glame_access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});
```

При получении 401 ошибки会自动尝试 обновить токен:

```typescript
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401 && !originalRequest._retry) {
      // Попытка обновить токен
      const refreshToken = localStorage.getItem('glame_refresh_token');
      // ...
    }
  }
);
```

## Структура JWT токена

### Access Token

```json
{
  "sub": "a51c940a-11e1-4e5c-8550-b9fb8a64e66a",
  "exp": 1772296911,
  "type": "access"
}
```

- `sub` — ID пользователя (UUID)
- `exp` — время истечения (Unix timestamp)
- `type` — тип токена

### Refresh Token

```json
{
  "sub": "a51c940a-11e1-4e5c-8550-b9fb8a64e66a",
  "exp": 1774802511,
  "type": "refresh"
}
```

## Роли пользователей

| Роль | Описание |
|------|----------|
| `admin` | Администратор системы |
| `customer` | Клиент (покупатель) |

## Защищённые endpoints

### Admin endpoints

Все endpoints `/api/admin/*` требуют роль `admin`:

- `/api/admin/customers` — список клиентов
- `/api/admin/customers/segments/list` — сегменты клиентов
- `/api/admin/customers/analytics/*` — аналитика

## Создание администратора

Для создания или обновления администратора используется скрипт:

```bash
cd backend
source venv/bin/activate
python create_admin.py --email admin@glame.ru --password ваш_пароль
```

## Устранение неполадок

### 401 Unauthorized

1. Проверьте, что токен не истёк
2. Проверьте, что токен корректно передаётся в заголовке `Authorization`
3. Убедитесь, что пользователь имеет роль `admin`

### Ошибка "Incorrect email or password"

1. Проверьте правильность email и пароля
2. Сбросьте пароль через скрипт `create_admin.py`

### Токен не сохраняется

1. Проверьте настройки localStorage в браузере
2. Убедитесь, что не включён режим инкогнито

## Режим отладки (NEXT_PUBLIC_SKIP_APP_AUTH)

При `NEXT_PUBLIC_SKIP_APP_AUTH=true`:
- Используется fake user `admin@portal`
- Не требуется вход через форму
- Токены не выдаются

При `NEXT_PUBLIC_SKIP_APP_AUTH=false`:
- Обязательная авторизация через форму
- Токены сохраняются в localStorage

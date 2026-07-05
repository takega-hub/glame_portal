# Деплой Flutter Web (GLAME)

Цель: собрать Flutter Web из `mobile/glame_app` и раздать через nginx на сервере.

## 1) Варианты размещения

### Вариант A (рекомендуется): отдельный домен

Например: `https://app.glamejewelry.ru`.

- Плюсы: не конфликтует с Basic Auth портала, проще кеширование, проще правила роутинга.
- Минусы: нужен CORS на backend.

### Вариант B: под-путь на том же домене

Например: `https://portal.glamejewelry.ru/app/`.

- Плюсы: нет CORS (same-origin).
- Минусы: на портале сейчас Basic Auth, он заблокирует доступ покупателям.

## 2) Backend: CORS (если отдельный домен)

Добавьте в окружение backend:

```bash
CORS_ALLOW_ORIGINS=https://app.glamejewelry.ru
```

Backend читает список из `CORS_ALLOW_ORIGINS` (через запятую) и добавляет к localhost.

Перезапустите backend.

## 3) Сборка Flutter Web

На сервере (или в CI) в папке репозитория:

```bash
cd mobile/glame_app
flutter pub get

# для отдельного домена
flutter build web --release --dart-define=API_BASE_URL=https://portal.glamejewelry.ru

# если размещение в под-пути /app/ (нужно base-href)
# flutter build web --release --base-href /app/ --dart-define=API_BASE_URL=https://portal.glamejewelry.ru
```

Артефакты будут в `mobile/glame_app/build/web`.

Важно про обновления:
- По умолчанию Flutter Web использует PWA service worker (`--pwa-strategy=offline-first`), и из-за кэша браузер может не сразу увидеть новую версию.
- Для preview-окружения можно отключить PWA кэш:

```bash
flutter build web --release --pwa-strategy=none --dart-define=API_BASE_URL=https://portal.glamejewelry.ru
```

Если уже была открыта старая версия, очистите service worker для домена (DevTools → Application → Service Workers → Unregister) или “Clear site data”.

## 4) Nginx (пример конфигурации для отдельного домена)

Создайте каталог:

```bash
sudo mkdir -p /var/www/glame_app_web
sudo rsync -a --delete mobile/glame_app/build/web/ /var/www/glame_app_web/
```

Пример server block:

```nginx
server {
  listen 80;
  server_name app.glamejewelry.ru;

  root /var/www/glame_app_web;
  index index.html;

  location / {
    try_files $uri $uri/ /index.html;
  }

  location ~* \.(js|css|png|jpg|jpeg|gif|svg|ico|woff2?)$ {
    expires 7d;
    add_header Cache-Control "public, max-age=604800";
    try_files $uri =404;
  }
}
```

Дальше:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

HTTPS (Let's Encrypt) — как обычно через certbot.

## 5) Проверка

- Откройте `https://app.glamejewelry.ru` — должен появиться экран логина Flutter.
- Проверьте запросы к API в network:
  - `POST /api/auth/login`
  - `GET /api/auth/me`

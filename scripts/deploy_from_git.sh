#!/usr/bin/env bash
# Обновление портала из Git: pull + пересборка контейнеров + миграции.
# Запускать из корня репозитория на сервере: ./scripts/deploy_from_git.sh
# Либо: cd /path/to/glame-platform && ./scripts/deploy_from_git.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "=== Git pull ==="
git pull

echo "=== Docker Compose up (build) ==="
docker compose -f infra/docker-compose.prod.yml up -d --build

echo "=== Migrations ==="
docker exec glame_backend alembic upgrade head

echo "=== Done ==="

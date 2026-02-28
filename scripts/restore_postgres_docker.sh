#!/usr/bin/env bash
set -euo pipefail

# Restore Postgres dump into docker container (default: glame_postgres)
# Format expected: pg_dump -Fc (custom format)
#
# Usage:
#   $0 path/to/glame_db_*.dump           — восстановить в существующую БД (таблицы перезаписываются через --clean)
#   $0 --recreate path/to/glame_db_*.dump — пересоздать БД с нуля, затем восстановить (рекомендуется при конфликте с миграциями)

RECREATE_DB=false
if [[ "${1:-}" == "--recreate" ]]; then
  RECREATE_DB=true
  shift
fi

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 [--recreate] path/to/glame_db_*.dump"
  echo "  --recreate  drop and recreate database before restore (use when tables already exist from migrations)"
  exit 1
fi

DUMP_FILE="$1"
if [[ ! -f "$DUMP_FILE" ]]; then
  echo "Dump file not found: $DUMP_FILE"
  exit 1
fi

CONTAINER_NAME="${POSTGRES_CONTAINER:-glame_postgres}"
DB_USER="${POSTGRES_USER:-glame_user}"
DB_NAME="${POSTGRES_DB:-glame_db}"

echo "Restoring $DUMP_FILE -> $DB_NAME in container $CONTAINER_NAME"

docker cp "$DUMP_FILE" "${CONTAINER_NAME}:/tmp/restore.dump"

if [[ "$RECREATE_DB" == true ]]; then
  echo "Recreating database $DB_NAME (terminating connections, drop, create)..."
  # Use DB_USER (e.g. glame_user): container may have no 'postgres' role when POSTGRES_USER is set
  ADMIN_USER="${POSTGRES_USER:-glame_user}"
  docker exec "$CONTAINER_NAME" psql -U "$ADMIN_USER" -d template1 -v ON_ERROR_STOP=1 -c "
    SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();
  " || true
  docker exec "$CONTAINER_NAME" psql -U "$ADMIN_USER" -d template1 -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS $DB_NAME;"
  docker exec "$CONTAINER_NAME" psql -U "$ADMIN_USER" -d template1 -v ON_ERROR_STOP=1 -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"
  echo "Restoring into empty database..."
  docker exec "$CONTAINER_NAME" pg_restore -U "$DB_USER" -d "$DB_NAME" --no-owner --no-privileges /tmp/restore.dump || true
else
  docker exec "$CONTAINER_NAME" pg_restore -U "$DB_USER" -d "$DB_NAME" --clean --if-exists --no-owner --no-privileges /tmp/restore.dump || true
fi

docker exec "$CONTAINER_NAME" rm -f /tmp/restore.dump

echo "OK: restored (some warnings may appear)"


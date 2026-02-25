#!/usr/bin/env bash
set -euo pipefail

# Restore Postgres dump into docker container (default: glame_postgres)
# Format expected: pg_dump -Fc (custom format)

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 path/to/glame_db_*.dump"
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

# --clean/--if-exists drops objects before recreating them.
# --no-owner avoids ownership issues between environments.
docker exec "$CONTAINER_NAME" sh -lc "pg_restore -U '$DB_USER' -d '$DB_NAME' --clean --if-exists --no-owner --no-privileges /tmp/restore.dump"
docker exec "$CONTAINER_NAME" sh -lc "rm -f /tmp/restore.dump"

echo "OK: restored"


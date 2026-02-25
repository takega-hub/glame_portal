#!/usr/bin/env bash
set -euo pipefail

# Backup Postgres running in docker container (default: glame_postgres)
# Uses pg_dump inside container + docker cp to avoid shell redirection issues.

CONTAINER_NAME="${POSTGRES_CONTAINER:-glame_postgres}"
DB_USER="${POSTGRES_USER:-glame_user}"
DB_NAME="${POSTGRES_DB:-glame_db}"
OUT_DIR="${BACKUP_DIR:-./backups}"

mkdir -p "$OUT_DIR"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_FILE="$OUT_DIR/${DB_NAME}_${TS}.dump"

echo "Backing up $DB_NAME from container $CONTAINER_NAME -> $OUT_FILE"

docker exec "$CONTAINER_NAME" sh -lc "pg_dump -U '$DB_USER' -d '$DB_NAME' -Fc -f /tmp/${DB_NAME}.dump"
docker cp "${CONTAINER_NAME}:/tmp/${DB_NAME}.dump" "$OUT_FILE"
docker exec "$CONTAINER_NAME" sh -lc "rm -f /tmp/${DB_NAME}.dump"

echo "OK: $OUT_FILE"


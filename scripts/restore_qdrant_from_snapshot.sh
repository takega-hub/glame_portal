#!/usr/bin/env bash
# Restore a Qdrant collection from a snapshot file (e.g. created by migrate_to_server.ps1).
# Usage: ./restore_qdrant_from_snapshot.sh <snapshot_file> <collection_name>
# Example: ./restore_qdrant_from_snapshot.sh ./backups/qdrant_knowledge_knowledge-2024-02-25.snapshot knowledge
# On server, snapshot file must be reachable from the host; it is copied into the Qdrant container for recovery.

set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <snapshot_file> <collection_name>"
  echo "  snapshot_file   Path to .snapshot file (e.g. from backups/qdrant_<collection>_<name>.snapshot)"
  echo "  collection_name Qdrant collection name (e.g. knowledge, brand_philosophy)"
  exit 1
fi

SNAPSHOT_FILE="$1"
COLLECTION_NAME="$2"
CONTAINER="${QDRANT_CONTAINER:-glame_qdrant}"

if [[ ! -f "$SNAPSHOT_FILE" ]]; then
  echo "Snapshot file not found: $SNAPSHOT_FILE"
  exit 1
fi

echo "Restoring collection '$COLLECTION_NAME' from $SNAPSHOT_FILE"

docker cp "$SNAPSHOT_FILE" "${CONTAINER}:/tmp/restore.snapshot"
docker run --rm --network "container:${CONTAINER}" curlimages/curl -s -X PUT \
  "http://127.0.0.1:6333/collections/${COLLECTION_NAME}/snapshots/recover" \
  -H "Content-Type: application/json" \
  -d '{"location":"file:///tmp/restore.snapshot"}'
docker exec "$CONTAINER" rm -f /tmp/restore.snapshot

echo "OK: collection '$COLLECTION_NAME' restored"

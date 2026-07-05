#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-https://portal.glamejewelry.ru}"
BASE_HREF="${BASE_HREF:-/}"
PWA_STRATEGY="${PWA_STRATEGY:-none}"
WEB_ROOT="${WEB_ROOT:-/var/www/glame_app_web}"

BUILD_ID="${BUILD_ID:-$(date +%Y%m%d%H%M%S)}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$SCRIPT_DIR/../mobile/glame_app"

flutter pub get

if [[ "$BASE_HREF" == "/" ]]; then
  flutter build web --release --pwa-strategy="$PWA_STRATEGY" --dart-define=API_BASE_URL="$API_BASE_URL"
else
  flutter build web --release --pwa-strategy="$PWA_STRATEGY" --base-href "$BASE_HREF" --dart-define=API_BASE_URL="$API_BASE_URL"
fi

python3 "$SCRIPT_DIR/postprocess_flutter_web.py" "$(pwd)/build/web" "$BUILD_ID"

mkdir -p "$WEB_ROOT"
rsync -a --delete build/web/ "$WEB_ROOT/"

echo "Deployed BUILD_ID=$BUILD_ID to $WEB_ROOT"

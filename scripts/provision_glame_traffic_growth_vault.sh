#!/usr/bin/env bash
set -euo pipefail

# Provisions the Traffic Growth Obsidian vault and attaches a concise pointer
# to its dedicated Hermes profile. Run on the GLAME Hermes host.

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
TEMPLATE_ROOT="$REPO_ROOT/docs/obsidian/traffic-growth-vault"
VAULT_ROOT="${GLAME_TRAFFIC_GROWTH_VAULT:-/home/glameAI/obsidian/GLAME Traffic Growth}"
PROFILE_ROOT="${GLAME_HERMES_PROFILE_ROOT:-/home/glameAI/.hermes/profiles/glame-traffic-growth}"
MEMORY_FILE="$PROFILE_ROOT/memories/MEMORY.md"
MEMORY_TEMPLATE="$REPO_ROOT/docs/obsidian/traffic-growth-profile-memory.md"

if [[ ! -d "$TEMPLATE_ROOT" || ! -d "$PROFILE_ROOT" ]]; then
  echo "Vault template or Hermes profile not found." >&2
  exit 1
fi

install -d -m 0750 "$VAULT_ROOT" \
  "$VAULT_ROOT/00-briefs" \
  "$VAULT_ROOT/01-yandex" \
  "$VAULT_ROOT/02-media" \
  "$VAULT_ROOT/03-reports" \
  "$VAULT_ROOT/04-experiments" \
  "$VAULT_ROOT/99-runbook" \
  "$VAULT_ROOT/.obsidian"

for source in \
  "$TEMPLATE_ROOT/README.md" \
  "$TEMPLATE_ROOT/99-runbook/Базовые инструкции.md" \
  "$TEMPLATE_ROOT/.obsidian/app.json" \
  "$TEMPLATE_ROOT/.obsidian/core-plugins.json"; do
  relative=${source#"$TEMPLATE_ROOT"/}
  target="$VAULT_ROOT/$relative"
  if [[ ! -e "$target" ]]; then
    install -D -m 0640 "$source" "$target"
  fi
done

if ! grep -Fqx "Рабочий vault: \`/home/glameAI/obsidian/GLAME Traffic Growth\`." "$MEMORY_FILE" 2>/dev/null; then
  printf '\n' >> "$MEMORY_FILE"
  sed '1d' "$MEMORY_TEMPLATE" >> "$MEMORY_FILE"
fi

echo "Traffic Growth vault ready: $VAULT_ROOT"
echo "Hermes profile attached: glame-traffic-growth"

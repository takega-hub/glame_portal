#!/usr/bin/env bash
set -euo pipefail

# Host-side helper for preparing Hermes profiles used by GLAME AI agents.
# Dry-run by default. Execute with DRY_RUN=0 on the host where Hermes is installed.

DRY_RUN=${DRY_RUN:-1}
BASE_PROFILE=${BASE_PROFILE:-anatoly}
HERMES_BIN=${HERMES_BIN:-hermes}

PROFILES=(
  glame-agent-worker
  glame-director
  glame-crm
  glame-brand-media
  glame-personal-media
  glame-analytics
  glame-assortment
  glame-pr-partnerships
  glame-traffic-growth
  glame-stylist
)

run() {
  if [[ "$DRY_RUN" == "1" ]]; then
    printf '[dry-run] %q ' "$@"
    printf '\n'
  else
    "$@"
  fi
}

if [[ "$DRY_RUN" != "1" ]] && ! command -v "$HERMES_BIN" >/dev/null 2>&1; then
  echo "Hermes binary not found: $HERMES_BIN" >&2
  echo "Set HERMES_BIN=/path/to/hermes or run this on the Hermes host." >&2
  exit 127
fi

echo "Current Hermes profiles:"
run "$HERMES_BIN" profile list

# Equivalent command shape: hermes profile list
# Equivalent command shape: hermes profile create <profile> --clone-from <base>
for profile in "${PROFILES[@]}"; do
  if [[ "$DRY_RUN" != "1" ]] && "$HERMES_BIN" profile list 2>/dev/null | awk '{print $1}' | grep -Fxq "$profile"; then
    echo "Profile already exists: $profile"
    continue
  fi
  echo "Creating profile: $profile from base profile: $BASE_PROFILE"
  run "$HERMES_BIN" profile create "$profile" --clone-from "$BASE_PROFILE"
done

cat <<'ENV_HELP'

Recommended GLAME backend env after profiles exist:

GLAME_AGENT_RUNTIME=hermes
GLAME_HERMES_BINARY=hermes
GLAME_HERMES_DEFAULT_PROFILE=glame-agent-worker
GLAME_HERMES_TIMEOUT_SECONDS=300
GLAME_HERMES_PROFILE_DIRECTOR_AGENT=glame-director
GLAME_HERMES_PROFILE_CRM_AGENT=glame-crm
GLAME_HERMES_PROFILE_BRAND_MEDIA_AGENT=glame-brand-media
GLAME_HERMES_PROFILE_PERSONAL_MEDIA_AGENT=glame-personal-media
GLAME_HERMES_PROFILE_ANALYTICS_AGENT=glame-analytics
GLAME_HERMES_PROFILE_ASSORTMENT_AGENT=glame-assortment
GLAME_HERMES_PROFILE_PR_PARTNERSHIPS_AGENT=glame-pr-partnerships
GLAME_HERMES_PROFILE_TRAFFIC_GROWTH_AGENT=glame-traffic-growth
GLAME_HERMES_PROFILE_STYLIST_AGENT=glame-stylist

Verify after backend restart:
GET /api/ai-marketer/agents/hermes/readiness
ENV_HELP

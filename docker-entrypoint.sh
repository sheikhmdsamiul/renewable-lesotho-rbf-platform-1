#!/bin/sh
# docker-entrypoint.sh — Generate runtime config for the frontend SPA.
#
# Reads environment variables and writes them to config.json so the
# React app can consume them without a rebuild.
#
# Expected vars:
#   VITE_API_URL  (default: /api)
#   VITE_API_TIMEOUT_MS  (default: 60000)

set -e

CONFIG_DIR=/usr/share/nginx/html
CONFIG_FILE="${CONFIG_DIR}/config.json"
TEMPLATE_FILE="${CONFIG_DIR}/config.template.json"

# Use the template if it exists, otherwise create config.json from scratch
if [ -f "$TEMPLATE_FILE" ]; then
  echo "Generating ${CONFIG_FILE} from template …"
  export VITE_API_URL="${VITE_API_URL:-/api}"
  export VITE_API_TIMEOUT_MS="${VITE_API_TIMEOUT_MS:-60000}"

  # Use envsubst to replace ${VAR} placeholders in the template
  envsubst < "$TEMPLATE_FILE" > "$CONFIG_FILE"
  rm -f "$TEMPLATE_FILE"
  echo "Runtime config written to ${CONFIG_FILE}:"
  cat "$CONFIG_FILE"
else
  # No template: write a minimal config so the app always has something
  cat > "$CONFIG_FILE" <<EOF
{
  "VITE_API_URL": "${VITE_API_URL:-/api}",
  "VITE_API_TIMEOUT_MS": "${VITE_API_TIMEOUT_MS:-60000}"
}
EOF
  echo "Config written directly to ${CONFIG_FILE}"
fi

exec nginx -g "daemon off;"

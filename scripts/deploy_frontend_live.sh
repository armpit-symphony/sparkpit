#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/ubuntu/thesparkpit"
FRONTEND_DIR="$ROOT/frontend"
BUILD_DIR="$FRONTEND_DIR/build"
WEB_ROOT="/var/www/thesparkpit"
BACKUP_ROOT="/var/www"
HOST_HEADER="thesparkpit.com"

cd "$ROOT"

echo "Building frontend..."
GENERATE_SOURCEMAP=false npm --prefix "$FRONTEND_DIR" run build

echo "Verifying bundle..."
bash "$ROOT/scripts/verify_frontend_bundle.sh"

echo "Resolving built asset hash..."
BUILT_JS="$(find "$BUILD_DIR/static/js" -maxdepth 1 -type f -name 'main.*.js' | sort | head -n 1)"
if [[ -z "${BUILT_JS:-}" ]]; then
  echo "missing built main.*.js asset" >&2
  exit 1
fi
BUILT_BASENAME="$(basename "$BUILT_JS")"

echo "Backing up current web root..."
STAMP="$(date +%Y%m%d-%H%M%S)"
sudo rsync -a --delete "$WEB_ROOT/" "$BACKUP_ROOT/thesparkpit.bak.$STAMP/"

echo "Deploying frontend build to $WEB_ROOT ..."
sudo rsync -a --delete "$BUILD_DIR/" "$WEB_ROOT/"

echo "Verifying deployed files..."
DEPLOYED_JS="$WEB_ROOT/static/js/$BUILT_BASENAME"
if [[ ! -f "$DEPLOYED_JS" ]]; then
  echo "deployed asset missing: $DEPLOYED_JS" >&2
  exit 1
fi

if ! grep -q "$BUILT_BASENAME" "$WEB_ROOT/index.html"; then
  echo "deployed index.html does not reference $BUILT_BASENAME" >&2
  exit 1
fi

if ! cmp -s "$BUILT_JS" "$DEPLOYED_JS"; then
  echo "deployed bundle does not match built bundle" >&2
  exit 1
fi

echo "Verifying nginx served hash..."
SERVED_HASH="$(curl -k -sS https://127.0.0.1/ -H "Host: $HOST_HEADER" | grep -oE 'main\.[a-f0-9]+\.js' | head -n 1 || true)"
if [[ "$SERVED_HASH" != "$BUILT_BASENAME" ]]; then
  echo "nginx served hash mismatch: expected $BUILT_BASENAME got ${SERVED_HASH:-<none>}" >&2
  exit 1
fi

echo "Frontend deploy complete: $BUILT_BASENAME"

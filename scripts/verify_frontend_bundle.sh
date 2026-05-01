#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/ubuntu/thesparkpit"
BUILD_DIR="$ROOT/frontend/build"

if [[ ! -f "$BUILD_DIR/index.html" ]]; then
  echo "frontend build missing: $BUILD_DIR/index.html" >&2
  exit 1
fi

if grep -RIn -m 1 --binary-files=text "undefined/api" "$BUILD_DIR/index.html" "$BUILD_DIR/static/js" >/dev/null; then
  echo "found invalid undefined/api reference in built frontend assets" >&2
  exit 1
fi

if ! grep -RIn -m 1 --binary-files=text "/api" "$BUILD_DIR/index.html" "$BUILD_DIR/static/js" >/dev/null; then
  echo "no /api references found in built frontend assets" >&2
  exit 1
fi

if find "$BUILD_DIR" -type f -name '*.map' | grep -q .; then
  echo "source map files found in production frontend build" >&2
  exit 1
fi

if grep -RIn -m 1 --binary-files=text "sourceMappingURL=" "$BUILD_DIR/index.html" "$BUILD_DIR/static/js" "$BUILD_DIR/static/css" >/dev/null; then
  echo "source map references found in production frontend build" >&2
  exit 1
fi

echo "frontend bundle verification passed"

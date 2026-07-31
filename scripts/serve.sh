#!/usr/bin/env bash
# Serve the map locally. It needs HTTP, not file:// -- the textures are fetched.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "http://localhost:${1:-8000}/index.html"
exec python3 -m http.server "${1:-8000}" --directory src

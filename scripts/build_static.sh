#!/usr/bin/env bash
# Vercel build: serve the SPA and its assets from a clean output directory.
# The Python API is not built here; /api/* is proxied by vercel.json.
set -euo pipefail

rm -rf public
mkdir -p public/static
cp static/index.html public/index.html
cp -R static/. public/static/

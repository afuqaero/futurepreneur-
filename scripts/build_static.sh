#!/usr/bin/env bash
# Vercel build: publish the SPA shell and every browser asset.
set -euo pipefail

rm -rf public
mkdir -p public/static
cp static/index.html public/index.html
# Copy files (including dotfiles) without creating an extra static/ directory.
cp -a static/. public/static/
# Keep the asset paths explicit so Vercel's filesystem handler can serve them.
test -s public/static/app.js
test -s public/static/styles.css || true

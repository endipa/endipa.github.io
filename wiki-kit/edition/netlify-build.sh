#!/usr/bin/env bash
# Build used by Netlify (see netlify.toml): download a pinned Quarto release,
# render the book into _book, and remove one script tag current browsers do not need.
set -euo pipefail

QUARTO_VERSION="${QUARTO_VERSION:-1.10.20}"
TOOLS="${TMPDIR:-/tmp}/quarto-tools"
QUARTO="$TOOLS/quarto-${QUARTO_VERSION}/bin/quarto"

if [ ! -x "$QUARTO" ]; then
  mkdir -p "$TOOLS"
  curl -fsSL "https://github.com/quarto-dev/quarto-cli/releases/download/v${QUARTO_VERSION}/quarto-${QUARTO_VERSION}-linux-amd64.tar.gz" \
    | tar -xz -C "$TOOLS"
fi

"$QUARTO" render --to html

# Quarto adds a polyfill script from a CDN; the pages do not need it.
sed -i '/polyfill\.min\.js/d' _book/*.html

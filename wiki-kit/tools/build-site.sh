#!/usr/bin/env bash
# build-site.sh: the provisional website = Quarto edition + static preview of the wiki, one zip for Netlify.
# Part of the wiki kit (2026); drafted by Claude (AI).
#
#   bash build-site.sh <site.xml> <edition-dir> [<preview-dir>] [<out.zip>]
#
#   site.xml     the XML built by wikikit.py (provisional phase) or a Special:Export of the real wiki
#   edition-dir  Quarto project: edition.json, theme.scss, page-links.lua, _headers, robots.txt, netlify.*
#                (generated .qmd files and _quarto.yml are rewritten on every run; never edit them)
#   preview-dir  output of wiki-export.js, copied to _book/wiki-preview/ (omit once the real wiki exists)
#   out.zip      default: <edition-dir>/site.zip; drop it on Netlify (Deploys tab)
#
# Media (kit v2.1): the files of {{Media}} are taken from $MEDIA_DIR, by default the folder media/ next to
# the folder of site.xml (wiki/build/x.xml -> wiki/media), and copied into the edition.
#
# Quarto: uses `quarto` from PATH, else downloads the pinned release 1.10.20 (as netlify-build.sh does).
# MathJax 3.2.2 is self-hosted: fetched once from npm into <edition-dir>/mathjax/.
set -euo pipefail
XML="$(realpath "${1:?site.xml}")"; ED="$(realpath "${2:?edition dir}")"; PV="${3:-}"; ZIP="$(realpath -m "${4:-$ED/site.zip}")"
HERE="$(cd "$(dirname "$0")" && pwd)"
QV=1.10.20
if command -v quarto >/dev/null 2>&1; then Q=quarto; else
  Q=/opt/quarto-tools/quarto-$QV/bin/quarto
  if [ ! -x "$Q" ]; then mkdir -p /opt/quarto-tools
    curl -fsSL "https://github.com/quarto-dev/quarto-cli/releases/download/v$QV/quarto-$QV-linux-amd64.tar.gz" | tar -xz -C /opt/quarto-tools; fi
fi
if [ ! -f "$ED/mathjax/tex-chtml-full.js" ]; then
  tmp="$(mktemp -d)"; (cd "$tmp" && npm pack -s mathjax@3.2.2 >/dev/null && tar xzf mathjax-3.2.2.tgz)
  mkdir -p "$ED/mathjax/output/chtml/fonts"
  cp "$tmp/package/es5/tex-chtml-full.js" "$ED/mathjax/"
  cp -r "$tmp/package/es5/output/chtml/fonts/woff-v2" "$ED/mathjax/output/chtml/fonts/"
  cp "$tmp/package/LICENSE" "$ED/mathjax/LICENSE.txt"; rm -rf "$tmp"
fi
# generated files of the previous run (pages may have been renamed)
find "$ED" -maxdepth 1 -name '*.qmd' -delete; rm -rf "$ED/_statements" "$ED/_book" "$ED/.quarto"
MEDIA="${MEDIA_DIR:-$(dirname "$XML")/../media}"; MARGS=(); [ -d "$MEDIA" ] && MARGS=(--media "$(realpath "$MEDIA")")
# kit v2.1: the TeX source of every page, linked under its title
SITE_NAME="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("title",""))' "$ED/edition.json" 2>/dev/null || true)"
python3 "$HERE/wikitex.py" page2tex "$XML" "$ED/tex" --date "$(date -u +%F)" --site "$SITE_NAME" > "$ED/tex-report.txt" || { cat "$ED/tex-report.txt"; exit 1; }
# the whole wiki in one document, a section per page (opened in Overleaf from the Overview)
python3 "$HERE/wikitex.py" book "$XML" "$ED/tex" "$ED/tex/whole-wiki.tex" --site "$SITE_NAME" --date "$(date -u +%F)" >> "$ED/tex-report.txt"
# the PDF of every page, compiled from its TeX source (skipped when pdflatex is missing); images from the media folder
rm -f "$ED"/tex/*.pdf
if command -v pdflatex >/dev/null 2>&1; then
  T="$(mktemp -d)"; mkdir -p "$T/tex"; cp "$ED"/tex/*.tex "$T/tex/"; [ -d "$MEDIA" ] && cp -r "$MEDIA" "$T/media"
  for f in "$T"/tex/*.tex; do b="$(basename "$f" .tex)"
    (cd "$T/tex" && pdflatex -interaction=nonstopmode -halt-on-error "$b.tex" >/dev/null 2>&1 && pdflatex -interaction=nonstopmode -halt-on-error "$b.tex" >/dev/null 2>&1) \
      && cp "$T/tex/$b.pdf" "$ED/tex/" || echo "pdflatex failed on $b.tex" >> "$ED/tex-report.txt"
  done; rm -rf "$T"
fi
# all the TeX sources in one zip, for "Open in Overleaf" on the Overview: whole-wiki.tex as the main document, every
# page a file of its own, and the images they show
rm -f "$ED/tex/all-pages.zip"; T="$(mktemp -d)"; cp "$ED"/tex/*.tex "$T/"; [ -d "$MEDIA" ] && cp "$MEDIA"/*.png "$MEDIA"/*.jpg "$T/" 2>/dev/null || true
(cd "$T" && zip -q "$ED/tex/all-pages.zip" *); rm -rf "$T"
python3 "$HERE/wiki2qmd.py" "$XML" "$ED" --date "$(date -u +%F)" "${MARGS[@]}" > "$ED/convert-report.json" || { cat "$ED/convert-report.json"; exit 1; }
(cd "$ED" && "$Q" render --to html >/tmp/quarto-render.log 2>&1) || { tail -30 /tmp/quarto-render.log; exit 1; }
sed -i '/polyfill\.min\.js/d' "$ED"/_book/*.html
if [ -n "$PV" ]; then PV="$(realpath "$PV")"; rm -rf "$ED/_book/wiki-preview"; cp -r "$PV" "$ED/_book/wiki-preview"; rm -f "$ED/_book/wiki-preview/_headers"; fi
rm -f "$ZIP"; (cd "$ED/_book" && zip -qr "$ZIP" .)
echo "built $(ls "$ED"/_book/*.html | wc -l) edition pages$( [ -n "$PV" ] && echo " + $(ls "$ED"/_book/wiki-preview/*.html | wc -l) preview pages") -> $ZIP"

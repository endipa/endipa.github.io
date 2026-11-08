#!/usr/bin/env python3
"""Draw the map of the wiki (the diagram on the Overview): wiki/media/wiki-map.svg.

    python3 tools/make_wiki_map.py [wiki/media/wiki-map.svg]

The map shows the parts of the wiki with the same names as the menu, without arrows or numbers:
the parts can be read in any order. A part with one page is a box that opens the page; a part with
several pages lists them, each one a link. The links point to the pages of the edition (file name =
slug of the page title, as in wiki2qmd.py). Change ROWS when a part or a page changes, and run the
script again. Drafted by Claude (AI), 8 November 2026.
"""
import re
import sys
import unicodedata
from xml.sax.saxutils import escape

# rows of boxes; a box is (part name, description or None, pages, width weight); a part whose only page has
# its name is one link; a part with several pages lists them (one column up to two pages, then two columns)
ROWS = [
    [("Motivation and history", "why the problem matters; its history, technique by technique", ["Motivation and history"], 1)],
    [("Techniques through examples", None, ["Couette flow", "Poiseuille flow"], 9),
     ("Techniques and general results", None, ["Spectral methods", "Hypocoercivity", "Stochastic methods", "Hörmander theory"], 11)],
    [("Extensions and recent advances", None, ["State of the art", "Related results", "Open problems", "Raw data"], 1)],
    [("Toolkit", None, ["Notation", "Standard analysis", "Enhanced-dissipation tools"], 1)],
    [("Numerical methods", "the code of the figures", ["Numerical methods"], 1),
     ("Lean formalization", "certificates", ["Lean formalization"], 1)],
]
W, PAD, GAP, ROW_GAP = 600, 16, 12, 12
INK, MUTED, ACCENT, FILL, FILL_LIGHT, LINE, LINE_LIGHT = "#1c222b", "#59616e", "#1f4e79", "#f4f7fb", "#fafbfc", "#1f4e79", "#9aa6b5"


def slug(title):
    title = title.replace("–", "-").replace("—", "-")
    s = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower().replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def href(page):
    return "index.html" if page == "Overview" else slug(page) + ".html"


def box(x, y, w, h, part, desc, pages, light):
    fill, line = (FILL_LIGHT, LINE_LIGHT) if light else (FILL, LINE)
    rect = f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="6" fill="{fill}" stroke="{line}" stroke-width="1.3"/>'
    title = f'<text x="{x + 14:g}" y="{y + 24:g}" font-size="15" font-weight="600" fill="{INK}">{escape(part)}</text>'
    if len(pages) == 1 and pages[0] == part:   # the whole box opens the page
        sub = f'<text x="{x + 14:g}" y="{y + 43:g}" font-size="12" fill="{MUTED}">{escape(desc or "")}</text>'
        return f'<a href="{href(part)}" class="map-box"><title>{escape(part)}</title>{rect}{title}{sub}</a>'
    out, ly, cols = [rect, title], y + 45, 1 if len(pages) <= 2 else (3 if len(pages) == 3 else 2)
    for k in range(0, len(pages), cols):
        lx = x + 14
        for p in pages[k:k + cols]:
            out.append(f'<a href="{href(p)}" class="map-page"><title>{escape(p)}</title>'
                       f'<text x="{lx:g}" y="{ly:g}" font-size="13" fill="{ACCENT}">{escape(p)}</text></a>')
            lx += (w - 28) / cols
        ly += 20
    return "".join(out)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "wiki/media/wiki-map.svg"
    parts, y = [], 10
    for r, row in enumerate(ROWS):
        free = W - 2 * PAD - (len(row) - 1) * GAP
        total = sum(b[3] for b in row)
        lines = max(0 if (len(pages) == 1 and pages[0] == part) else (len(pages) if len(pages) <= 2 else 1 if len(pages) == 3 else (len(pages) + 1) // 2)
                    for part, _, pages, _ in row)
        h = 56 if lines == 0 else 36 + 20 * lines
        light = r >= len(ROWS) - 2
        x = PAD
        for part, desc, pages, weight in row:
            w = free * weight / total
            parts.append(box(x, y, w, h, part, desc, pages, light))
            x += w + GAP
        y += h + ROW_GAP
    height = y - ROW_GAP + 10
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" class="wiki-map" viewBox="0 0 {W} {height:g}" width="{W}" height="{height:g}" '
           f'role="group" aria-label="Map of the wiki" font-family="\'IBM Plex Sans\', system-ui, -apple-system, \'Segoe UI\', sans-serif">'
           '<style>.wiki-map a { text-decoration: none; } .wiki-map a.map-box rect { transition: fill 0.15s; }'
           ' .wiki-map a.map-box:hover rect { fill: #e6edf6; } .wiki-map a.map-page:hover text { text-decoration: underline; }</style>'
           + "".join(parts) + "</svg>\n")
    open(out, "w", encoding="utf-8").write(svg)
    print(f"{out}: {W} x {height:g}")


if __name__ == "__main__":
    main()

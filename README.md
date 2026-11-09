# Enhanced dissipation for passive scalars

A collection of old and new results on enhanced dissipation for passive scalars: the linear advection–diffusion equation
$\partial_t f + u\cdot\nabla f = \nu\Delta f$ with a prescribed incompressible velocity $u$.

- **Website** (built from the wiki, never edited by hand): https://endipa.github.io/
- **Wiki** (where the text is written; for now open to invited members only): https://endipa.miraheze.org
- **How to contribute**: the page [How to contribute](https://endipa.github.io/how-to-contribute.html). Every page can be downloaded as a TeX source
  (a standard LaTeX article that compiles as it is) and as a PDF, or opened in Overleaf with its pictures; printing a page from the browser gives the website's layout with every fold open; mathematical contributions are proposed on Zulip with the TeX of the blocks they change.

The project is a work in progress: most pages are still a skeleton.

## What is in this repository

| Folder | Content |
|---|---|
| `docs/` | the website, as served by GitHub Pages (generated: do not edit) |
| `wiki/pages/` | the wiki's pages as text files (one file per page; a snapshot of the wiki, regenerated from it) |
| `wiki/media/` | pictures, videos and diagrams shown on the website |
| `numerics/` | the code of every computed picture or video, with its checks (each has a record on the page *Numerical methods*) |
| `references/` | the reference catalogue (`catalog.json`) and its BibTeX file |
| `site/` | the settings of the website (Quarto): `edition.json`, theme, link filter |
| `tools/` | project scripts: the Literature page from the catalogue, the map of the wiki |
| `wiki-kit/` | the wiki kit: the tools that check the pages, convert wiki ↔ TeX, apply proposals, and build the website |

## How the website is built

The wiki is the source. The website and the TeX sources are generated from it:

1. Export the wiki's pages (Special:Export) to an XML file.
2. `bash wiki-kit/tools/build-site.sh <export.xml> site` — converts every page to TeX (`wikitex.py page2tex`) and to Quarto
   (`wiki2qmd.py`), renders the website and packs it into `site/site.zip`. Needs Python 3.8+ and Quarto 1.10 (downloaded if missing); with pdflatex installed it also compiles the PDF of every page from its TeX source.
3. Copy the content of `site/_book/` into `docs/` and commit.

Checks before publishing: `python3 wiki-kit/tools/wikikit.py lint wiki/pages` (0 errors), `python3 wiki-kit/tools/wikitex.py roundtrip wiki/pages`
(every page ok), pdflatex on the files of `docs/tex/`.

A mathematical proposal (a TeX file) is turned into a change of the wiki with
`python3 wiki-kit/tools/wikitex.py apply wiki/pages proposal.tex`: it prints exactly which blocks change, the new citations and links,
and the problems; `--write` saves the new page.

## Building it with Claude

The tools were written with Claude (Anthropic's AI model), and Claude can run the whole cycle. With this repository as a folder
connected to Claude (desktop app, Cowork), ask for instance:

- *"Rebuild the website from the wiki"*: Claude exports the pages through your browser (the wiki is private), builds, checks, and writes `docs/`; you review and push.
- *"Here is a proposal for the page Couette flow (TeX attached): show me the report"*: Claude runs `wikitex.py apply` and shows the diff; after acceptance it writes the change into the wiki and rebuilds the website.

The procedures are in `wiki-kit/RUNBOOK.md`. Claude asks before anything visible to others (editing the wiki, publishing); no text drafted by Claude goes into the wiki without the label *demo text* until a person approves it.

## Licence

To be decided by the editorial board (text, code).

# Runbook (for Claude and for editors)

K = `wiki-kit/tools`. The wiki https://endipa.miraheze.org is the source of truth; `wiki/pages/` and `docs/` are generated from it.

## Rebuild the website from the wiki
1. Export: `python3 $K/wikikit.py titles wiki/pages --wiki https://endipa.miraheze.org` prints the Special:Export address (templates included). The wiki is private: export from a logged-in browser, save the XML. Equivalent, when the snapshot is current: compare the SHA-1 of every page of the wiki (API, `prop=revisions&rvprop=sha1`, from the logged-in browser) with the files of `wiki/pages` (text with trailing whitespace removed); if all agree, `python3 $K/wikikit.py build wiki/pages <xml> --sitename "Enhanced dissipation for passive scalars"` gives the same pages.
2. Refresh the snapshot: `python3 $K/wikikit.py split <export.xml> wiki/pages`; then `python3 $K/wikikit.py lint wiki/pages` (0 errors) and `python3 $K/wikitex.py roundtrip wiki/pages` (every page ok).
3. Build: `bash $K/build-site.sh <export.xml> site` (media from `wiki/media`, set `MEDIA_DIR` otherwise). Check `site/convert-report.json` (no problems, no formula mismatches); compile two TeX files of `site/_book/tex/` with pdflatex.
4. Publish: replace the content of `docs/` with `site/_book/` (keep `docs/.nojekyll`; delete the files the new build no longer has, e.g. a renamed page), commit, push (GitHub Desktop). The `.gitignore` keeps the zips of `docs/tex/` (the Overleaf projects).

## The TeX sources (9 November 2026)
- `docs/tex/<page>.tex` is named after the page (`overview.tex`, `couette-flow.tex`), next to `<page>.pdf` and `<page>.zip`: the page and the pictures it shows, the project that "Open in Overleaf" opens (`wikitex.py zips`). `all-pages.zip` is the whole wiki.
- Layout of the preamble: `\begin{note}[Title]` is a dashed box; `\media` is a grey panel with the picture (for a video, its poster image) and the caption, placed as a figure (in place inside a box); `\begin{quote}` is centred and in italics: on the wiki it is `<div class="central-question">`, the central question of the Overview. The preamble needs tcolorbox (TeX Live, Overleaf). An SVG picture is shown from a PDF copy, which build-site.sh makes with rsvg-convert.
- A text written in TeX by an editor goes to the wiki as a proposal: `check`, then `apply --write` on `wiki/pages`, then the new page text into the wiki (API from the logged-in browser, `postWithEditToken` with `basetimestamp`; compare the SHA-1 of the saved page with the local file), then rebuild the website.

## A mathematical proposal (from Zulip)
1. The contributor posts the page's TeX source reduced to the blocks they change (a `\section{...}` with its content, or a statement or proof with its `\label`), keeping the preamble and `\title{Page}`; a new block is preceded by `%% after: <section title or label>`.
2. `python3 $K/wikitex.py check proposal.tex --pages wiki/pages`: macros, preamble changes, numbered equations, `\ref`, footnotes, unknown citation keys, formulas the wiki rejects.
3. `python3 $K/wikitex.py apply wiki/pages proposal.tex`: replaced / inserted / unchanged blocks, problems, new citations (added to the page's reference list), new and removed links, the author named in `\author`, and the diff. Post the report in the Zulip topic. Flag any new citation or link the proposal did not announce.
4. After acceptance: `--write`, then put the new page text into the wiki (edit summary: "Proposal <title> by <name>, accepted by <associate editor>, Zulip: <link>"), credit the author, rebuild the website.
5. A paper not yet in `references/catalog.json` is a separate proposal; then `python3 tools/refs_from_catalog.py literature references/catalog.json wiki/pages` and `... apply ...`.

## Small corrections
Members: talk pages of the wiki; others: Zulip #contributing. Draft the fixes as a list (page, old, new), an editor approves, apply, answer where they were posted.

## Media and numerics
Files in `wiki/media/`. Each computed item has a record on *Numerical methods* and its code in `numerics/<name>/`. The map of the wiki: `python3 tools/make_wiki_map.py wiki/media/wiki-map.svg` (names = menu names).

## Rules for Claude
Ask before anything visible to others: editing the wiki, changing its settings or permissions, inviting, posting, publishing. Never invent participants, reviews or approvals. Text drafted by Claude carries `{{Demo}}` until a person replaces or approves it; a machine check never counts as a human check.

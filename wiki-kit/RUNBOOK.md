# Runbook (for Claude and for editors)

K = `wiki-kit/tools`. The wiki https://endipa.miraheze.org is the source of truth; `wiki/pages/` and `docs/` are generated from it.

## Rebuild the website from the wiki
1. Export: `python3 $K/wikikit.py titles wiki/pages --wiki https://endipa.miraheze.org` prints the Special:Export address (templates included). The wiki is private: export from a logged-in browser, save the XML.
2. Refresh the snapshot: `python3 $K/wikikit.py split <export.xml> wiki/pages`; then `python3 $K/wikikit.py lint wiki/pages` (0 errors) and `python3 $K/wikitex.py roundtrip wiki/pages` (every page ok).
3. Build: `bash $K/build-site.sh <export.xml> site` (media from `wiki/media`, set `MEDIA_DIR` otherwise). Check `site/convert-report.json` (no problems, no formula mismatches); compile two TeX files of `site/_book/tex/` with pdflatex.
4. Publish: replace the content of `docs/` with `site/_book/` (keep `docs/.nojekyll`), commit, push (GitHub Desktop).

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

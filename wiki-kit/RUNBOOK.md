# Runbook (for Claude and for editors)

K = `wiki-kit/tools`. The wiki https://endipa.miraheze.org is the source of truth; `wiki/pages/` and `docs/` are generated from it.

## Rebuild the website from the wiki
1. Export: `python3 $K/wikikit.py titles wiki/pages --wiki https://endipa.miraheze.org` prints the Special:Export address (templates included). The wiki is private: export from a logged-in browser, save the XML. Equivalent, when the snapshot is current: compare the SHA-1 of every page of the wiki (API, `prop=revisions&rvprop=sha1`, from the logged-in browser) with the files of `wiki/pages` (text with trailing whitespace removed); if all agree, `python3 $K/wikikit.py build wiki/pages <xml> --sitename "Enhanced dissipation for passive scalars"` gives the same pages.
2. Refresh the snapshot: `python3 $K/wikikit.py split <export.xml> wiki/pages`; then `python3 $K/wikikit.py lint wiki/pages` (0 errors) and `python3 $K/wikitex.py roundtrip wiki/pages` (every page ok).
3. Build: `bash $K/build-site.sh <export.xml> site` (media from `wiki/media`, set `MEDIA_DIR` otherwise). Check `site/convert-report.json` (no problems, no formula mismatches); compile two TeX files of `site/_book/tex/` with pdflatex.
4. Publish: replace the content of `docs/` with `site/_book/` (keep `docs/.nojekyll`; delete the files the new build no longer has, e.g. a renamed page), commit, push (GitHub Desktop). The `.gitignore` keeps the zips of `docs/tex/` (the Overleaf projects).

## The TeX sources (9 November 2026)
- `docs/tex/<page>.tex` is named after the page (`overview.tex`, `couette-flow.tex`), next to `<page>.pdf`; a page with pictures also has `<page>.zip` (the .tex and its pictures in `figures/`, `wikitex.py zips`), and its "TeX source" link gives the zip. No per-page Overleaf link (each click would open a new Overleaf project).
- `all-pages.zip` is the whole wiki as one LaTeX project, downloaded from the Overview ("TeX of the whole wiki"; no Overleaf button since 10 November 2026; `wikitex.py book`): `main.tex` has the preamble, the title, the contents and the reference list, and reads every page with `\inputpage` from `pages/<page>.tex`; the pictures are in `figures/`. A file of `pages/` starts with `\wikipage{Title}` and is a valid proposal for `apply`. `whole-wiki.pdf` is compiled from `main.tex` (three runs).
- Layout of the preamble: `\begin{note}[Title]` is a dashed box; `\media` is a grey panel with the picture (for a video, its poster image) and the caption, placed as a figure (in place inside a box), found next to the file, in `figures/` or in `../media`; `\begin{quote}` is centred and in italics: on the wiki it is `<div class="central-question">`, the central question of the Overview. The preamble needs tcolorbox (TeX Live, Overleaf). An SVG picture is shown from a PDF copy, which build-site.sh makes with rsvg-convert.
- A text written in TeX by an editor goes to the wiki as a proposal: `check`, then `apply --write` on `wiki/pages`, then the new page text into the wiki (API from the logged-in browser, `postWithEditToken` with `basetimestamp`; compare the SHA-1 of the saved page with the local file), then rebuild the website.

## Zulip
https://endipa.zulipchat.com (set up on 9 November 2026): one channel per part of the wiki, as on *How to contribute* (overview, examples, techniques, advances, toolkit, numerics, lean, contributing), all public inside the organization and joined by new members, plus general; one topic per page (the line under each page's title links to it), for questions, ideas for new results or pages, and announcements; proposals to change a page go to its talk page in the wiki. Messages need a topic; only administrators invite members and create channels. The address is in `Template:Zulip host` (wiki); the channel ids, for the website's links, in `site/edition.json` (`zulip_channels`).

## Proposals (talk pages; 9 November 2026)
Every change to a page is a topic on its talk page, opened with `Template:Proposal/Preload` (the pencil button of a paragraph in the edition: `{{Proposal|status=open|paragraph=<id>}}`, the reason, the proposed and the current TeX) or `Template:Proposal/Preload-block` (link *new proposal* under the title in the wiki, *Propose a change* in the edition: `{{Proposal|status=open}}`, the blocks of TeX in `<pre>`). The box `{{Proposal}}` shows the status (open, accepted, applied, declined) and files the talk page in *Category:Open proposals*, *Accepted proposals*, ... Members reply with the buttons *Support* / *Oppose* / *Comment* of the box (signed replies at the end of the topic; the box counts supports and oppositions). An associate editor accepts or declines with the buttons *Accept* / *Decline* in the box (MediaWiki:Common.js, shown to the groups editor, sysop, bureaucrat: one edit of the topic that sets the status and adds the reason as a signed reply), or by hand. No deadlines.
To apply the accepted proposals (when Michele asks):
1. In the browser pane on the wiki (logged in): `await mw.loader.getScript('/w/index.php?title=MediaWiki:Proposals.js&action=raw&ctype=text/javascript')` (the wiki's copy of `tools/proposals.js`), then `await Proposals.list('accepted')`. For each proposal: `eligible` must be true (the user who changed the status to accepted is in the group editor, sysop or bureaucrat); flag `selfAccepted`.
2. Copy the topic's wikitext (`text`) to `wiki/build/proposals/<talk>--<n>.wiki` on the computer and check its SHA-1 against `sha1`. Refresh the snapshot of the page first (its SHA-1 on the wiki must be that of `wiki/pages`).
3. `python3 $K/wikitex.py apply-proposal wiki/pages "<page>" <topic.wiki>`: a paragraph proposal is refused if the paragraph changed since (then apply by hand, or ask the author to redo it from the edition); a block proposal reports replaced / inserted / unchanged blocks, problems, new citations and links. Then `--write` (refused unless the status is accepted), `wikikit.py lint`.
4. `await Proposals.save(page, newText, sha1OfNewText, Proposals.summary(p))`: the summary links the topic and credits author and acceptor. Then `await Proposals.markApplied(p.talk, p.heading, revid)` and `await Proposals.archive(p.talk, p.heading)` (the topic moves to `<talk>/Archive`; *Decline* does this by itself). Mirror the page file to the root `wiki/pages`, rebuild the website.
Talk pages are not mirrored after each discussion: the wiki is their home (Special:Export or the Miraheze dump for a backup).
5. A paper not yet in `references/catalog.json` is a proposal on *Talk:Literature*; then `python3 tools/refs_from_catalog.py literature references/catalog.json wiki/pages`.
Proposals sent as a TeX file (Zulip, email) still go through `wikitex.py check` and `wikitex.py apply`, as before.

## Credits
`{{Contributed by|Name, Name}}` on the line after a section heading (TeX `\contributors{...}` after `\section{...}`): the contributors of the section, most recent first, chosen by the editors at their discretion.

## Media and numerics
Files in `wiki/media/`. Each computed item has a record on *Numerical methods* and its code in `numerics/<name>/`. The map of the wiki: `python3 tools/make_wiki_map.py wiki/media/wiki-map.svg` (names = menu names).

## Rules for Claude
Ask before anything visible to others: editing the wiki, changing its settings or permissions, inviting, posting, publishing. Never invent participants, reviews or approvals. Text drafted by Claude carries `{{Demo}}` until a person replaces or approves it; a machine check never counts as a human check.

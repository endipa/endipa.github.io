#!/usr/bin/env python3
"""Build the Quarto edition from the wiki.

Usage: python3 wiki2qmd.py <wiki-export.xml> <quarto-project-dir> [--date YYYY-MM-DD] [--config edition.json]
                            [--media DIR]

The XML is a Special:Export of the real wiki (current revisions, "Include templates"), or the file
built by wikikit.py from the page files. The project settings come from edition.json (default:
<quarto-project-dir>/edition.json): title, subtitle, author, wiki_url, zulip_host, footer_left,
footer_right; kit v2.1: contributors, zulip_channels, wiki_note (e.g. "members": shown after the link to the
real wiki). wiki_url is the real wiki ("https://<slug>.miraheze.org/wiki/") or, before it exists,
the relative address of the static preview inside the site ("wiki-preview/").

Kit v2.1 (8 Nov 2026): {{Media}} (pictures, videos, diagrams; files copied from --media into media/,
an SVG diagram is inlined so that its links work), {{Lean}} (formalization banner), {{Discuss}} (Zulip
channel and topic of a page; the Zulip address comes from edition.json or from Template:Zulip host),
labels {{Published}} and {{Raw}}, unnumbered Claim/Remark/Conjecture boxes (Theorem start with a
title "Claim (name)."), <pre> blocks (code; data-lang="python" sets the language).

History: written for the 2D Euler reading group; adapted on 30 Oct 2026 for the wiki "Regularity of the
2D Euler trajectories" ({{Theorem start|id=...|title=Kind (Name).}}, a {{Heuristic}} badge, inline
{{Statement/...}} transclusions, <code>; wiki ids prop-x become Quarto labels prp-x); made
configurable for new projects in the wiki kit (Nov 2026).

Reads a MediaWiki XML export (current revisions) and writes into the Quarto project:
  index.qmd and one <slug>.qmd per article;
  _statements/<name>.md for every Template:Statement/<Name>;
  _quarto.yml, with parts and chapters taken from MediaWiki:Sidebar.
It understands the wiki's own templates (Result, Proof, Level, Fold, Quote, Card, Placeholder,
Proof link, Crumbs, Ref, Anchor, Demo, Claim, Preprint, Statement/...) and the plain wikitext
used on the pages: headings, bold and italics, links, lists, definition lists, simple tables
and <math>. Anything else is reported, not guessed. At the end it checks that every formula of
every page appears unchanged in the output, and prints a summary.

Conventions (see also the recipe):
  * labels: thm-, prp-, lem-, cor-, def- for results; sec- for sections (Template:Anchor in the
    heading). {{Ref|label|text}} becomes @label, so the edition prints "Lemma 4.2";
  * the wiki names results, the edition numbers them;
  * the Quarto output is never edited by hand: edit the wiki and run this script again.
"""
import re, sys, os, json, collections, unicodedata, html, shutil, urllib.parse
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wikitex   # noqa: E402  (the editable paragraphs of a page and their TeX, for the edit buttons)

XML, OUT = sys.argv[1], sys.argv[2]
DATE = sys.argv[sys.argv.index('--date') + 1] if '--date' in sys.argv else None
CONFIG_PATH = sys.argv[sys.argv.index('--config') + 1] if '--config' in sys.argv else os.path.join(OUT, 'edition.json')
MEDIA_DIR = sys.argv[sys.argv.index('--media') + 1] if '--media' in sys.argv else ''
MEDIA_USED = set()   # files of wiki/media used by the pages; copied into <project>/media/
CONFIG = {'title': 'Wiki edition', 'subtitle': 'A modular exposition built from the wiki (format demo)',
          'author': 'Project members, to be listed; first draft by Claude (AI)',
          'wiki_url': 'wiki-preview/', 'zulip_host': '',
          'footer_left': "Built from the wiki by a script, never edited by hand. Text marked 'demo text' was drafted by Claude and is to be replaced by human authors.",
          'footer_right': 'AI-generated arguments appear only as verbatim quotes; see How to contribute.'}
if os.path.exists(CONFIG_PATH):
    CONFIG.update(json.load(open(CONFIG_PATH, encoding='utf-8')))
REF_PREFIXES = ('thm-', 'prp-', 'lem-', 'cor-', 'def-', 'sec-')
THEOREM_PREFIXES = ('thm-', 'prp-', 'lem-', 'cor-', 'def-')   # results that Quarto numbers
QUARTO_TITLED = ('Remark', 'Proof', 'Solution')               # Quarto prints these words itself
# Fallback labels; main() replaces them by the texts of Template:Demo, Template:Claim, Template:Preprint.
BADGES = {'Demo': '[demo text]{.badge-demo}', 'Claim': '[claimed · under study]{.badge-claim}',
          'Preprint': '[recent preprint · to be verified]{.badge-preprint}',
          'Heuristic': '[heuristic]{.badge-heuristic}', 'Numeric': '[numerics · not a proof]{.badge-numeric}',
          'Published': '[published]{.badge-published}', 'Raw': '[raw · unchecked]{.badge-raw}'}
problems = []
ZULIP_HOST = CONFIG['zulip_host']   # e.g. 'myproject.zulipchat.com'; empty: no Zulip links
LABEL_RENAME = {}   # wiki ids -> Quarto labels (prop-x -> prp-x); filled in main()
KIND_PREFIX = {'Theorem': 'thm-', 'Lemma': 'lem-', 'Proposition': 'prp-', 'Corollary': 'cor-', 'Definition': 'def-'}
THEOREM_TITLE = re.compile(r'^(Theorem|Lemma|Proposition|Corollary|Definition)\s*\((.*)\)\.?$', re.S)
UNNUMBERED_TITLE = re.compile(r'^(Claim|Remark|Conjecture|Example)\s*(?:\((.*)\))?\.?$', re.S)   # boxes Quarto does not number
ZULIP_CHANNELS = CONFIG.get('zulip_channels', {})   # short name -> "<id>-<name>" once the Zulip exists (optional)
# Edit buttons (kit, November 2026): with "edit_paragraphs": {"preload": "Template:Proposal/Preload"} in edition.json,
# (and "preload_block": "Template:Proposal/Preload-block": the "Propose a change" link under each title, page-links.lua)
# every paragraph of a page has a button that shows its TeX in a popup; the reader changes it and opens a new topic on
# the page's talk page in the wiki, filled in by the preload page ($1 page, $2 paragraph id, $3 current TeX, $4 proposed
# TeX, $5 reason, $6 the change in a few words). The proposal is saved only when the reader saves it in the wiki;
# wikitex.py apply-proposal applies it.
EDIT = CONFIG.get('edit_paragraphs')
EDIT_SCRIPT = r"""<style>
.edit-unit { position: relative; }
.edit-unit > .edit-btn { position: absolute; top: 0.1rem; right: -2.1rem; width: 1.7rem; height: 1.7rem; padding: 0; border: 1px solid #c9cfd8;
  border-radius: 4px; background: #fff; color: #1f4e79; font-size: 0.85rem; line-height: 1; opacity: 0; transition: opacity .15s; cursor: pointer; }
.edit-unit:hover > .edit-btn, .edit-unit > .edit-btn:focus { opacity: 1; }
.callout .edit-unit > .edit-btn { right: -0.4rem; top: -0.5rem; }
@media (hover: none), (max-width: 767px) { .edit-unit > .edit-btn { right: 0; top: -0.3rem; opacity: 0.55; } }
.edit-overlay { position: fixed; inset: 0; z-index: 3000; background: rgba(20, 28, 40, 0.38); display: flex; align-items: center;
  justify-content: center; padding: 1rem; }
.edit-dialog { background: #fff; width: min(46rem, 100%); max-height: 92vh; overflow: auto; border-radius: 8px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, .25); padding: 1.1rem 1.3rem 1rem; font-size: 0.95rem; }
.edit-dialog h3 { font-size: 1.1rem; margin: 0 0 .3rem; }
.edit-dialog .edit-note { color: #59616e; font-size: 0.85rem; margin: 0 0 .7rem; }
.edit-dialog .edit-todo { display: block; margin: .3rem 0 0; padding: .4rem .7rem; border: 1px dashed #8aa2c0; border-radius: 4px;
  font-style: italic; color: #3f4855; font-size: .9rem; }
.edit-dialog textarea { width: 100%; min-height: 10rem; font-family: SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.82rem;
  line-height: 1.45; padding: .5rem .6rem; border: 1px solid #c9cfd8; border-radius: 4px; }
.edit-dialog input[type=text] { width: 100%; padding: .35rem .6rem; border: 1px solid #c9cfd8; border-radius: 4px; font-size: .9rem; }
.edit-dialog label { display: block; font-size: .8rem; color: #59616e; margin: .6rem 0 .2rem; }
.edit-insert { display: flex; flex-wrap: wrap; gap: .3rem; align-items: center; margin: 0 0 .35rem; font-size: .8rem; color: #59616e; }
.edit-insert button { border: 1px solid #c9cfd8; border-radius: 4px; background: #fff; padding: .1rem .5rem; font-size: .8rem; cursor: pointer; }
.edit-preview .pv-env { border-left: 3px solid #1f4e79; background: #f8f9fb; padding: .2rem .6rem; margin: .4rem 0; }
.edit-preview .pv-proof { border-left: 1px solid #d5dbe3; padding-left: .6rem; margin: .4rem 0; }
.edit-preview .pv-claim { border: 1px dashed #c8cfd9; border-left: 3px solid #1f4e79; }
.edit-preview .pv-note { border: 1px dashed #8a94a3; border-radius: 3px; padding: .3rem .6rem; margin: .4rem 0; }
.edit-preview { border: 1px dashed #c9cfd8; border-radius: 4px; padding: .5rem .8rem; background: #fbfcfd; font-size: .93rem; }
.edit-actions { display: flex; flex-wrap: wrap; gap: .5rem; margin-top: .9rem; align-items: center; }
.edit-actions button { border-radius: 4px; padding: .35rem .8rem; font-size: .88rem; border: 1px solid #c9cfd8; background: #fff; cursor: pointer; }
.edit-actions button.edit-send { background: #1f4e79; border-color: #1f4e79; color: #fff; }
.edit-status { font-size: .82rem; color: #59616e; }
@media print { .edit-btn { display: none !important; } }
</style>
<script>
(function () {
  var el = document.getElementById('edit-units'); if (!el) return;
  var data = JSON.parse(el.textContent);
  function esc(s) { return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
  // a rough preview of the TeX: the formulas with MathJax, a few commands as text
  function preview(tex) {
    var h = esc(tex);
    var ENV = 'theorem|proposition|lemma|corollary|definition|claim|remark|conjecture|example';
    h = h.replace(new RegExp('\\\\begin\\{(' + ENV + ')\\}(?:\\[([^\\]]*)\\])?(?:\\\\label\\{[^}]*\\})?', 'g'), function (m, e, n) {
           return '<div class="pv-env' + (e === 'claim' ? ' pv-claim' : '') + '"><strong>' + e.charAt(0).toUpperCase() + e.slice(1) + (n ? ' (' + n + ')' : '') + '.</strong> '; })
         .replace(new RegExp('\\\\end\\{(' + ENV + ')\\}', 'g'), '</div>')
         .replace(/\\begin\{proof\}(?:\[([^\]]*)\])?(?:\\label\{[^}]*\})?/g, function (m, n) { return '<div class="pv-proof"><em>' + (n || 'Proof') + '.</em> '; })
         .replace(/\\end\{proof\}/g, ' &#9633;</div>')
         .replace(/\\begin\{note\}(?:\[([^\]]*)\])?/g, function (m, n) { return '<div class="pv-note"><em>' + (n || 'Note') + '.</em> '; })
         .replace(/\\end\{note\}/g, '</div>');
    h = h.replace(/\\begin\{(itemize|enumerate|quote)\}|\\end\{(itemize|enumerate|quote)\}/g, '')
         .replace(/\\item\s*/g, '<br>&bull;&nbsp;')
         .replace(/\\(emph|textit)\{([^{}]*)\}/g, '<em>$2</em>').replace(/\\textbf\{([^{}]*)\}/g, '<strong>$1</strong>')
         .replace(/\\wikilink\{([^{}]*)\}\{\}/g, '<u>$1</u>').replace(/\\wikilink\{[^{}]*\}\{([^{}]*)\}/g, '<u>$1</u>')
         .replace(/\\hyperref\[[^\]]*\]\{([^{}]*)\}/g, '<u>$1</u>').replace(/\\cite[tp]?\{([^{}]*)\}/g, '[$1]')
         .replace(/\\(numerics|heuristic|demo|preprint|published|raw)\{\}/g, '[$1]')
         .replace(/---/g, '&mdash;').replace(/--/g, '&ndash;').replace(/\n\s*\n/g, '<br><br>');
    return h.replace(/\$([^$]+)\$/g, '\\($1\\)');
  }
  // the change in a few words, for the talk page: "… such as <del>heat,</del> <ins>temperature,</ins> a dye in …"
  function change(a, b) {
    var x = a.split(/\s+/), y = b.split(/\s+/), p = 0, s = 0;
    while (p < x.length && p < y.length && x[p] === y[p]) p++;
    while (s < x.length - p && s < y.length - p && x[x.length - 1 - s] === y[y.length - 1 - s]) s++;
    function nw(w) { w = w.join(' '); return w ? '<nowiki>' + (w.length > 400 ? w.slice(0, 400) + ' …' : w) + '</nowiki>' : ''; }
    var del = x.slice(p, x.length - s), ins = y.slice(p, y.length - s);
    return (p > 4 ? '… ' : '') + nw(x.slice(Math.max(0, p - 4), p)) + (del.length ? ' <del>' + nw(del) + '</del>' : '')
      + (ins.length ? ' <ins>' + nw(ins) + '</ins>' : '') + ' ' + nw(x.slice(x.length - s, x.length - s + 4)) + (s > 4 ? ' …' : '');
  }
  var PASTE = 'PASTE THE TEXT HERE: it was copied to the clipboard';
  // a placeholder (a part still to be written): its description, and a few words of it for the titles
  function todo(tex) { var m = tex.match(/^\\placeholder\{([\s\S]*)\}\s*$/); return m ? m[1] : null; }
  function words(s, n) {
    return s.replace(/\$[^$]*\$/g, ' ').replace(/\\[a-zA-Z]+|[{}$\\]/g, ' ').replace(/\s+/g, ' ').trim().split(' ').slice(0, n).join(' ');
  }
  function open(id) {
    var old = data.units[id], ph = todo(old);
    var where = ' then open the proposal on the talk page of <em>' + esc(data.page) + '</em> in the wiki (members, logged in): it is saved only'
      + ' when you click <em>Save</em> there, and it is discussed before an editor applies it.</p>';
    var ov = document.createElement('div'); ov.className = 'edit-overlay';
    ov.innerHTML = '<div class="edit-dialog" role="dialog" aria-modal="true" aria-label="' + (ph ? 'Write this part' : 'Propose a change') + '">'
      + '<h3>' + (ph ? 'Write this part' : 'Propose a change') + '</h3>'
      + (ph ? '<p class="edit-note">Still to be written:<span class="edit-todo">' + preview(ph) + '</span></p>'
            + '<p class="edit-note">Write it in TeX, as in the TeX source of the page (<code>$...$</code>, <code>\\[...\\]</code>, <code>align*</code>,'
            + ' <code>\\citet{Key}</code>, <code>\\wikilink{Page}{text}</code>; no macros): it takes the place of this placeholder once the'
            + ' proposal is accepted;' + where
          : '<p class="edit-note">The TeX of this paragraph or figure, as in the TeX source of the page. Change it (the buttons add a note, a'
            + ' folded box as on the Overview, or a claim, a dashed box, after it), or describe below the change you ask for (a shorter video, a clearer picture, ...);' + where)
      + '<div class="edit-insert">Add after the text: <button type="button" data-ins="note">Note (folded box)</button>'
      + '<button type="button" data-ins="claim">Claim (dashed box)</button></div>'
      + '<textarea spellcheck="false"></textarea>'
      + '<label>Preview (formulas and basic formatting)</label><div class="edit-preview"></div>'
      + '<label>' + (ph ? 'Note for the editors (optional, one line)' : 'Reason, or the change you ask for (one line)')
      + '</label><input type="text" maxlength="500">'
      + '<div class="edit-actions"><button type="button" class="edit-send">Open the proposal on the talk page</button>'
      + '<button type="button" class="edit-copy">Copy the TeX</button><button type="button" class="edit-cancel">Cancel</button>'
      + '<span class="edit-status"></span></div></div>';
    document.body.appendChild(ov);
    var ta = ov.querySelector('textarea'), pv = ov.querySelector('.edit-preview'), reason = ov.querySelector('input'),
        status = ov.querySelector('.edit-status'), timer = null;
    ta.value = ph === null ? old : '';
    var todoEl = ov.querySelector('.edit-todo');
    if (todoEl && window.MathJax && MathJax.typesetPromise) { MathJax.typesetPromise([todoEl]).catch(function () {}); }
    function render() {
      pv.innerHTML = preview(ta.value);
      if (window.MathJax && MathJax.typesetPromise) { MathJax.typesetPromise([pv]).catch(function () {}); }
    }
    ta.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(render, 300); });
    // the buttons "Add after the text": a note (a folded box, as on the Overview: its title is selected, to be typed over) or a
    // claim (a dashed box: the cursor in its first line); statements, proofs and formulas are written in TeX as usual
    var SNIP = { note: ['\\begin{note}[', 'Title', ']\n', '\n\\end{note}'], claim: ['\\begin{claim}\n', '', '', '\n\\end{claim}'] };
    ov.querySelectorAll('.edit-insert button').forEach(function (b) {
      b.onclick = function () {
        var s = SNIP[b.getAttribute('data-ins')], v = ta.value, at = ta.selectionStart || v.length;
        if (document.activeElement !== ta && at === 0) at = v.length;
        var before = v.slice(0, at).replace(/\s+$/, ''), after = v.slice(at).replace(/^\s+/, '');
        var pre = before ? before + '\n\n' : '';
        ta.value = pre + s.join('') + (after ? '\n\n' + after : '');
        var a0 = (pre + s[0]).length; ta.focus(); ta.setSelectionRange(a0, a0 + s[1].length); render();
      };
    });
    render();
    function close() { ov.remove(); document.removeEventListener('keydown', onkey); }
    function onkey(e) { if (e.key === 'Escape') close(); }
    document.addEventListener('keydown', onkey);
    ov.addEventListener('click', function (e) { if (e.target === ov) close(); });
    ov.querySelector('.edit-cancel').onclick = close;
    ov.querySelector('.edit-copy').onclick = function () {
      ta.select();
      try { document.execCommand('copy'); status.textContent = 'Copied.'; } catch (e) { status.textContent = 'Select the text and copy it.'; }
    };
    ov.querySelector('.edit-send').onclick = function () {
      var neu = ta.value.replace(/\s+$/, '');
      var same = neu === old.replace(/\s+$/, ''), why = reason.value.trim();
      if (ph !== null && !neu) { status.textContent = 'Write the text first.'; return; }
      if (same && !why) { status.textContent = 'Change the TeX, or describe the change you ask for in the field below.'; return; }
      var fig = old.match(/^\\media(?:\[[^\]]*\])?\{[^}]*\}\{([^}]*)\}/);
      var title = ph !== null ? 'text for “' + words(ph, 6) + '”' : same ? why.split(/\s+/).slice(0, 6).join(' ')
                  : fig ? 'figure ' + fig[1] : words(neu, 6) + '…';
      var params = [data.page, id, old, neu, why || '(none given)',
                    ph !== null ? 'a new text in place of the placeholder “' + words(ph, 10) + '”'
                    : same ? '(no change to the TeX: the change asked for is in the reason)' : change(old, neu)];
      function link(p) {
        return data.edit + encodeURIComponent(data.talk.replace(/ /g, '_')) + '?action=edit&section=new'
          + '&preloadtitle=' + encodeURIComponent('Proposal: ' + title)
          + '&preload=' + encodeURIComponent(data.preload)
          + p.map(function (x) { return '&preloadparams%5B%5D=' + encodeURIComponent(x); }).join('');
      }
      // a link to the wiki holds about 7500 characters: a long text is copied to the clipboard and pasted in the wiki
      var u = link(params), pasted = false;
      if (u.length > 7500) { params[2] = '(not repeated: see the element ' + id + ' of the page)'; u = link(params); }
      if (u.length > 7500) {
        params[3] = PASTE; params[5] = ph !== null ? params[5] : '(see the proposed text)'; u = link(params); pasted = true;
        ta.select();
        try { (navigator.clipboard ? navigator.clipboard.writeText(neu) : Promise.reject()).catch(function () { document.execCommand('copy'); }); }
        catch (e) { try { document.execCommand('copy'); } catch (e2) {} }
      }
      window.open(u, '_blank', 'noopener');
      status.textContent = pasted ? 'The text is too long for a link: it has been copied. In the new tab, replace the line "' + PASTE
        + '" with it (paste), then click Save.' : 'Opened in a new tab: check it there and click Save.';
    };
    ta.focus();
  }
  document.querySelectorAll('.edit-unit').forEach(function (u) {
    var id = u.getAttribute('data-unit'); if (!data.units[id]) return;
    var b = document.createElement('button'); b.type = 'button'; b.className = 'edit-btn';
    var ph = todo(data.units[id]) !== null;
    b.title = ph ? 'Write this part' : 'Propose a change'; b.setAttribute('aria-label', b.title);
    b.innerHTML = '<i class="bi bi-pencil" aria-hidden="true"></i>';
    b.addEventListener('click', function () { open(id); });
    u.appendChild(b);
    // a placeholder: its "Propose a text" link (page-links.lua) opens the same box
    var a = ph && u.querySelector('a.propose');
    if (a) { a.textContent = 'Write this part →'; a.addEventListener('click', function (e) { e.preventDefault(); open(id); }); }
  });
})();
</script>"""


# Contributors of a section: a long list shows the three most recent names and a link that opens the others
CONTRIB_SCRIPT = r"""<script>
document.querySelectorAll('.section-contributors .sc-names').forEach(function (s) {
  var MAX = 3, parts = s.innerHTML.split(/\s*,\s*(?![^<]*>)/).filter(function (x) { return x.trim(); });
  if (parts.length <= MAX + 1) return;
  var more = 'and ' + (parts.length - MAX) + ' more';
  s.innerHTML = parts.slice(0, MAX).join(', ') + '<span class="sc-rest" hidden>, ' + parts.slice(MAX).join(', ')
    + '</span> <a href="#" class="sc-more" role="button">' + more + '</a>';
  var a = s.querySelector('.sc-more'), r = s.querySelector('.sc-rest');
  a.addEventListener('click', function (e) { e.preventDefault(); r.hidden = !r.hidden; a.textContent = r.hidden ? more : 'show fewer'; });
});
</script>"""


def edit_block(title, tex):
    """The TeX of the editable paragraphs of a page and the script of the edit buttons, as raw HTML."""
    data = {'page': title, 'talk': 'Talk:' + title, 'edit': WIKI, 'preload': EDIT.get('preload', ''), 'units': tex}
    js = json.dumps(data, ensure_ascii=False).replace('</', '<\\/')
    return '\n\n```{=html}\n<script type="application/json" id="edit-units">' + js + '</script>\n' + EDIT_SCRIPT + '\n```\n'


def zulip_hash(s):
    """Zulip's encoding of a narrow URL component: encodeURIComponent, then % ( ) . written .XX."""
    enc = urllib.parse.quote(s, safe="!~*'()")
    return re.sub(r'[%().]', lambda m: {'%': '.', '(': '.28', ')': '.29', '.': '.2E'}[m.group(0)], enc)


def no_pre(text):
    """The text without its <pre> blocks (code may contain braces that look like templates)."""
    return re.sub(r'<pre[^>]*>.*?</pre>', '', text, flags=re.S)


def plain_text(s):
    s = re.sub(r'<math[^>]*>(.*?)</math>', r'\1', s, flags=re.S)
    s = re.sub(r'\{\{[^{}]*\}\}', '', s)
    s = re.sub(r'\[\[(?:[^\]|]*\|)?([^\]]*)\]\]', r'\1', s)
    s = re.sub(r"'{2,}|<[^>]+>", '', s)
    return re.sub(r'\s+', ' ', s).strip()


def media_block(page, named):
    """{{Media|kind=image|video|diagram|file=...|caption=...|record=...|poster=...|id=...}} -> a figure."""
    kind = named.get('kind', 'image').strip() or 'image'
    f = named.get('file', '').strip()
    if not f:
        problems.append(f'{page}: Media without file=')
        return []
    MEDIA_USED.add(f)
    poster = named.get('poster', '').strip()
    if poster:
        MEDIA_USED.add(poster)
    mid = named.get('id', '').strip()
    cap = named.get('caption', '').strip()
    alt = html.escape(plain_text(cap) or f, quote=True)
    src = 'media/' + urllib.parse.quote(f)
    out = ['', '::: {' + ('#' + mid + ' ' if mid else '') + '.media-figure .media-' + kind + '}', '']
    if kind == 'video':
        mime = {'.mp4': 'video/mp4', '.m4v': 'video/mp4', '.webm': 'video/webm', '.ogv': 'video/ogg'}.get(os.path.splitext(f)[1].lower(), 'video/mp4')
        attrs = 'controls muted loop playsinline preload="metadata"' + (' poster="media/' + urllib.parse.quote(poster) + '"' if poster else '')
        out += ['```{=html}', f'<video class="media-video" {attrs} aria-label="{alt}"><source src="{src}" type="{mime}">'
                f'Your browser cannot play this video: <a href="{src}">download it</a>.</video>', '```', '']
    elif kind == 'diagram' and f.lower().endswith('.svg'):
        path = os.path.join(MEDIA_DIR, f) if MEDIA_DIR else ''
        if path and os.path.exists(path):
            svg = open(path, encoding='utf-8').read()
            svg = re.sub(r'<!DOCTYPE[^>]*>', '', re.sub(r'^\s*<\?xml[^>]*\?>', '', svg)).strip()
            out += ['```{=html}', svg, '```', '']   # inlined, so that the links of the diagram work
        else:
            problems.append(f'{page}: media file not found (run with --media DIR): {f}')
    else:
        out += ['```{=html}', f'<img class="media-img" src="{src}" alt="{alt}" loading="lazy">', '```', '']
    if cap:
        out += ['::: {.media-caption}', inline(cap), ':::', '']
    if named.get('record', '').strip():
        out += ['::: {.media-record}', link('Numerical methods#' + named['record'].strip(), 'How this was made →'), ':::', '']
    return out + [':::', '']


def slug(title):
    title = title.replace('–', '-').replace('—', '-')   # "Bahouri–Chemin" -> "bahouri-chemin"
    s = unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode().lower().replace("'", '').replace('’', '')
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')


WIKI = CONFIG['wiki_url']           # absolute: the real wiki; relative: the static preview
WIKI_IS_PREVIEW = not re.match(r'^https?://', WIKI)
ARTICLES = set()   # titles of the pages of the edition; filled in main()
IDS = set()        # ids of boxes ({{Theorem start|id=}}, {{Quote start|id=}}, {{Anchor|}}); filled in main()


def anchor_id(a):
    """A wiki anchor -> the id in the edition: box ids are kept (prop-x -> prp-x), sections are slugged
    with the rule used for the heading ids written by convert_page."""
    a = a.strip()
    if not a:
        return ''
    if a in LABEL_RENAME:
        return LABEL_RENAME[a]
    if a in IDS:
        return a
    return slug(a.replace('_', ' '))


def qmd_name(title):
    return 'index.qmd' if title == 'Overview' else slug(title) + '.qmd'


# ---------------------------------------------------------------- reading the export
def read_export(path):
    root = ET.parse(path).getroot()
    ns = {'mw': root.tag.split('}')[0].strip('{')}
    pages = {}
    for p in root.findall('mw:page', ns):
        title = p.find('mw:title', ns).text
        text = p.find('mw:revision/mw:text', ns).text or ''
        pages[title] = text
    return pages


def strip_noinclude(text):
    return re.sub(r'<noinclude>.*?</noinclude>', '', text, flags=re.S).strip()


# ---------------------------------------------------------------- template calls
def find_template(s, start):
    """Return the end index (exclusive) of the template call starting at s[start] == '{{'."""
    depth, i = 0, start
    while i < len(s):
        if s.startswith('<math', i):
            j = s.find('</math>', i)
            i = j + 7
            continue
        if s.startswith('{{', i):
            depth += 1; i += 2; continue
        if s.startswith('}}', i):
            depth -= 1; i += 2
            if depth == 0:
                return i
            continue
        i += 1
    raise ValueError('unbalanced template at: ' + s[start:start + 60])


def split_params(inner):
    """Split 'Name|a|b=c' at top-level pipes (outside {{ }}, [[ ]] and <math>)."""
    parts, depth_t, depth_l, cur, i = [], 0, 0, '', 0
    while i < len(inner):
        if inner.startswith('<math', i):
            j = inner.find('</math>', i) + 7
            cur += inner[i:j]; i = j; continue
        two = inner[i:i + 2]
        if two == '{{': depth_t += 1; cur += two; i += 2; continue
        if two == '}}': depth_t -= 1; cur += two; i += 2; continue
        if two == '[[': depth_l += 1; cur += two; i += 2; continue
        if two == ']]': depth_l -= 1; cur += two; i += 2; continue
        if inner[i] == '|' and depth_t == 0 and depth_l == 0:
            parts.append(cur); cur = ''; i += 1; continue
        cur += inner[i]; i += 1
    parts.append(cur)
    name, pos, named = parts[0].strip(), [], {}
    for p in parts[1:]:
        m = re.match(r'^\s*([A-Za-z][A-Za-z0-9_-]*)\s*=(.*)$', p, re.S)
        if m and not p.lstrip().startswith('<math'):
            named[m.group(1)] = m.group(2).strip()
        else:
            pos.append(p.strip())
    return name, pos, named


def templates_in(s):
    """Yield (start, end, name, pos, named) for each top-level template call in s."""
    i = 0
    while True:
        j = s.find('{{', i)
        if j < 0:
            return
        k = find_template(s, j)
        yield j, k, *split_params(s[j + 2:k - 2])
        i = k


# ---------------------------------------------------------------- inline conversion
def math_inline(tex, in_table=False):
    tex = tex.strip()
    if in_table:   # a pipe table would split at | even inside math
        tex = tex.replace('\\|', '\\Vert ').replace('|', '\\vert ').strip()
    return tex


def link(target, text):
    page, _, anchor = target.partition('#')
    page = page.strip().replace('_', ' ')
    if page.startswith('Talk:'):
        return text
    if page and page not in ARTICLES:   # templates, MediaWiki: pages, ...: link to the wiki itself
        if WIKI_IS_PREVIEW:   # the static preview has the Statement/ templates only
            if page.startswith('Template:Statement/'):
                return f'[{text}]({WIKI}template-statement-{slug(page.split("/", 1)[1])}.html)'
            return text
        url = WIKI + page.replace(' ', '_') + ('#' + anchor.strip().replace(' ', '_') if anchor.strip() else '')
        return f'[{text}]({url})'
    a = anchor_id(anchor)
    href = (qmd_name(page) if page else '') + ('#' + a if a else '')
    return f'[{text}]({href})'


def inline(s, in_table=False):
    out, i = '', 0
    # <nowiki> text is literal: set it aside before the templates, links and formatting are converted
    literal = []
    def keep(m):
        literal.append(m.group(1)); return f'\x02{len(literal) - 1}\x02'
    s = re.sub(r'<nowiki>(.*?)</nowiki>', keep, s, flags=re.S)
    # templates first (they may contain math and links)
    pieces, last = [], 0
    for a, b, name, pos, named in templates_in(s):
        pieces.append(s[last:a]); last = b
        if name in BADGES:
            pieces.append(BADGES[name])
        elif name == 'Ref':
            label = pos[0]
            text = pos[1] if len(pos) > 1 else label
            if label.startswith(REF_PREFIXES):
                # in a table the number alone says too little: "Lemma 4.6 (finite energy)"
                pieces.append('@' + label + (f' ({inline(text, in_table)})' if in_table and len(pos) > 1 else ''))
            else:
                pieces.append(link(named.get('page', '') + '#' + label, inline(text, in_table)))
        elif name == 'Anchor':
            pieces.append(f'[]{{#{pos[0]}}}')
        elif name.startswith('DISPLAYTITLE:'):
            pass
        else:
            problems.append(f'inline template not converted: {name}')
            pieces.append('')
    pieces.append(s[last:])
    s = ''.join(pieces)
    # math
    def mrepl(m):
        attrs, tex = m.group(1) or '', m.group(2)
        if 'display="block"' in attrs:
            return '$$' + math_inline(tex, in_table) + '$$'
        return '$' + math_inline(tex, in_table) + '$'
    tokens = []
    def protect(m):
        tokens.append(mrepl(m)); return f'\x00{len(tokens) - 1}\x00'
    s = re.sub(r'<math([^>]*)>(.*?)</math>', protect, s, flags=re.S)
    s = re.sub(r'<nowiki>(.*?)</nowiki>', r'\1', s, flags=re.S)
    s = s.replace('&#32;', ' ')
    s = re.sub(r'<code>(.*?)</code>', r'`\1`', s)
    s = re.sub(r"'''(.+?)'''", r'**\1**', s)
    s = re.sub(r"''(.+?)''", r'*\1*', s)
    s = re.sub(r'<sup>(.*?)</sup>', r'^\1^', s)
    # placeholders' "Propose a text on the talk page" links are replaced by the Zulip link of page-links.lua
    s = re.sub(r'\s*\[\[Talk:[^\]|]*\|(?:Propose a text[^\]]*|[^\]]*→\s*)\]\]', '', s)
    s = re.sub(r'\[\[([^\]|]+)\|([^\]]+)\]\]', lambda m: link(m.group(1), m.group(2)), s)
    s = re.sub(r'\[\[([^\]|]+)\]\]', lambda m: link(m.group(1), m.group(1).replace('_', ' ')), s)
    s = re.sub(r'\[(https?://\S+) ([^\]]+)\]', r'[\2](\1)', s)
    if in_table:
        s = s.replace('|', '\\|')
    s = re.sub('\x00(\\d+)\x00', lambda m: tokens[int(m.group(1))], s)
    s = re.sub('\x02(\\d+)\x02', lambda m: literal[int(m.group(1))].replace('|', '\\|') if in_table else literal[int(m.group(1))], s)
    if re.search(r'<(?!-)[a-z]+[ >]', s):
        problems.append('raw HTML left inline: ' + s[:80])
    return s


def attr_title(t):
    return re.sub(r'\s+', ' ', inline(t)).replace('"', '\\"')


# ---------------------------------------------------------------- block conversion
def convert_page(title, text, statements):
    meta = {}
    m = re.search(r'\{\{DISPLAYTITLE:(.*?)\}\}', text)
    display = m.group(1) if m else title.split('/')[-1]
    display = display.replace('<sup>p</sup>', 'ᵖ')
    m = re.search(r'<div class="discuss-line">(.*?)</div>', text)
    if m and ZULIP_HOST:
        line = m.group(1)
        z = re.search(r'\[(https://' + re.escape(ZULIP_HOST) + r'/\S+) Zulip topic\]', line)
        if z:
            meta['zulip'] = z.group(1)
            rest = line[z.end():].strip(' ·')
            if rest:
                meta['zulip-related'] = inline(rest).strip(' ·')
    # a badge followed by a placeholder on the same line: the badge goes on a line of its own
    text = re.sub(r'^((?:\{\{(?:Demo|Claim|Heuristic|Numeric)\}\}[ \t]*)+)(?=\{\{Placeholder start\}\})', r'\1\n', text, flags=re.M)
    lines = text.split('\n')
    out, has_meta = [], '<div class="mod-meta">' in text
    used_ids = collections.Counter()
    i, n = 0, len(lines)
    fence = lambda f: out.extend(['', f, ''])
    # edit buttons: the editable paragraphs (wikitex.edit_units), each in a div with its id
    ustart = {a: (b, uid) for a, b, _, uid in wikitex.edit_units(text)} if EDIT and not WIKI_IS_PREVIEW else {}
    uend = None
    while i < n:
        if uend is not None and i > uend:
            fence(':::'); uend = None
        if uend is None and i in ustart:
            uend, uid = ustart[i]
            fence('::: {.edit-unit data-unit="' + uid + '"}')
        raw = lines[i]
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            out.append(''); i += 1; continue
        if stripped.startswith('{{DISPLAYTITLE:'):
            i += 1; continue
        # code: <pre data-lang="python"> ... </pre> (MediaWiki shows <pre> verbatim, entities decoded)
        if stripped.startswith('<pre') and re.match(r'^<pre(\s[^>]*)?>', stripped):
            attrs = re.match(r'^<pre(\s[^>]*)?>', stripped).group(1) or ''
            lang = re.search(r'data-lang="([\w+#.-]+)"', attrs)
            first = raw[raw.index('>') + 1:]
            code = []
            if '</pre>' in first:
                code.append(first.split('</pre>')[0]); i += 1
            else:
                if first.strip():
                    code.append(first)
                i += 1
                while i < n and '</pre>' not in lines[i]:
                    code.append(lines[i]); i += 1
                if i < n:
                    if lines[i].split('</pre>')[0].strip():
                        code.append(lines[i].split('</pre>')[0])
                    i += 1
            out += ['', '```' + (lang.group(1) if lang else ''), *[html.unescape(c) for c in code], '```', '']
            continue
        # single-line divs
        m = re.match(r'^<div class="([^"]+)">(.*)</div>$', stripped)
        if m:
            cls, body = m.groups()
            if cls == 'discuss-line':
                if not has_meta:
                    fence('::: {.discuss}'); fence(':::')
            else:
                cls_md = {'mod-meta': 'module-meta'}.get(cls, cls)
                fence('::: {.' + cls_md + '}'); out.append(inline(body)); fence(':::')
            i += 1; continue
        # headings
        m = re.match(r'^(={2,4})\s*(.*?)\s*\1$', stripped)
        if m:
            level = len(m.group(1))
            htext = m.group(2)
            a = re.search(r'\{\{Anchor\|([^}]+)\}\}', htext)
            htext = re.sub(r'\{\{Anchor\|[^}]+\}\}', '', htext).strip()
            attrs = []
            if a:
                attrs.append('#' + a.group(1))
            else:   # the wiki's section anchor, slugged, so that [[Page#Section]] links resolve
                plain_h = re.sub(r"'{2,}", '', re.sub(r'\[\[(?:[^\]|]*\|)?([^\]]*)\]\]', r'\1', htext))
                hid = slug(plain_h)
                used_ids[hid] += 1
                if used_ids[hid] > 1:
                    hid += f'-{used_ids[hid]}'
                if hid:
                    attrs.append('#' + hid)
            if htext in ('Sources', 'References'):
                attrs.append('.unnumbered')
            out += ['', '#' * level + ' ' + inline(htext) + (' {' + ' '.join(attrs) + '}' if attrs else ''), '']
            i += 1; continue
        # tables
        if stripped.startswith('{|'):
            j = i
            while not lines[j].strip().startswith('|}'):
                j += 1
            out += convert_table(lines[i:j + 1]); i = j + 1; continue
        # lines made of block templates (possibly followed by text)
        if stripped.startswith('{{'):
            end = find_template(stripped, 0)
            name, pos, named = split_params(stripped[2:end - 2])
            rest = stripped[end:].strip()
            handled = True
            if name == 'Result start':
                kind = named.get('kind', 'Theorem')
                label = named.get('id', '')
                classes = ' '.join('.' + c for c in named.get('class', '').split())
                head = inline(named['name']) if named.get('name') else ''
                if label.startswith(THEOREM_PREFIXES):
                    # a numbered Quarto environment: the name becomes its title
                    fence('::: {#' + label + (' ' + classes if classes else '') + '}')
                    if head:
                        out += ['## ' + head, '']
                else:
                    # an unnumbered box (a remark, or a claim not yet verified), with an optional anchor
                    fence('::: {' + ('#' + label + ' ' if label else '') + '.' + kind.lower()
                          + (' ' + classes if classes else '') + '}')
                    if kind in QUARTO_TITLED:
                        if head:
                            out += ['*' + head + '.*', '']
                    else:
                        out += ['**' + kind + (' (' + head + ')' if head else '') + '.**', '']
                if named.get('status'):
                    out += [inline(named['status']), '']
            elif name == 'Theorem start':
                mk = THEOREM_TITLE.match(named.get('title', '').strip())
                mu = UNNUMBERED_TITLE.match(named.get('title', '').strip())
                if mk:
                    kind, head_txt = mk.group(1), mk.group(2).strip()
                elif mu:
                    kind, head_txt = mu.group(1), (mu.group(2) or '').strip()
                else:
                    kind, head_txt = 'Theorem', named.get('title', '').strip().rstrip('.')
                label = LABEL_RENAME.get(named.get('id', ''), named.get('id', ''))
                if label.startswith(THEOREM_PREFIXES):
                    fence('::: {#' + label + '}')
                    if head_txt:
                        out += ['## ' + inline(head_txt), '']
                else:
                    fence('::: {' + ('#' + label + ' ' if label else '') + '.' + kind.lower() + '}')
                    out += ['**' + kind + (' (' + inline(head_txt) + ')' if head_txt else '') + '.**', '']
            elif name in ('Result end', 'Theorem end', 'Proof end', 'Level end', 'Fold end', 'Quote end', 'Card end'):
                fence(':::')
            elif name == 'Proof start':
                collapse = 'false' if named.get('open') == 'yes' else 'true'
                fence(f'::: {{.callout-note .lvl-proof icon="false" title="{attr_title(named.get("title", "Proof"))}" collapse="{collapse}"}}')
            elif name == 'Level start':
                kind = named.get('kind', 'idea')
                ctype = 'tip' if kind == 'idea' else 'note'
                fence(f'::: {{.callout-{ctype} .lvl-{kind} title="{attr_title(named.get("title", "Idea"))}"}}')
            elif name == 'Fold start':
                kind = named.get('kind', 'note')
                ctype = 'tip' if kind == 'idea' else 'note'
                fence(f'::: {{.callout-{ctype} .lvl-{kind} collapse="true" title="{attr_title(named.get("title", ""))}"}}')
            elif name == 'Quote start':
                label = named.get('id', '')
                fence('::: {' + ('#' + label + ' ' if label else '') + '.source-quote}')
                if named.get('head'):
                    fence('::: {.quote-head}'); out.append(inline(named['head'])); fence(':::')
            elif name == 'Card start':
                classes = ' '.join('.' + c for c in named.get('class', '').split())
                fence('::: {.statement-card' + (' ' + classes if classes else '') + '}')
                fence('::: {.card-head}'); out.append(inline(named.get('head', ''))); fence(':::')
            elif name == 'Placeholder start':
                m2 = re.match(r'^(.*?)\{\{Placeholder end\}\}(.*)$', rest)
                if not m2:
                    problems.append(f'{title}: multi-line placeholder not supported'); rest = ''
                else:
                    fence('::: {.placeholder}'); out.append(inline(m2.group(1)).strip()); fence(':::')
                    rest = m2.group(2).strip()
            elif name == 'Proof link':
                fence('::: {.proof-link}'); out.append('→ ' + link(pos[0], inline(pos[1] if len(pos) > 1 else 'Proof'))); fence(':::')
            elif name == 'Crumbs':
                fence('::: {.crumbs}'); out.append(' › '.join(inline(p) for p in pos if p)); fence(':::')
            elif name == 'Contributed by':   # the contributors of a section, most recent first
                fence('::: {.section-contributors}'); out.append('Contributors: [' + inline(pos[0] if pos else '') + ']{.sc-names}'); fence(':::')
            elif name == 'Media':
                out += media_block(title, named)
            elif name == 'Lean':
                status = (pos[0] if pos else named.get('status', '')).strip()
                url = (pos[1] if len(pos) > 1 else named.get('link', '')).strip()
                if status == 'formalized':
                    fence('::: {.lean-banner .lean-done}')
                    out.append('Lean: formalized' + (f' · [certificate]({url})' if url else ''))
                else:
                    fence('::: {.lean-banner .lean-todo}')
                    out.append('Lean: not yet formalized · ' + link('Lean formalization', 'add a certificate'))
                fence(':::')
            elif name == 'Discuss':
                ch = named.get('channel', '').strip()
                topic = named.get('topic', '').strip() or title
                if ZULIP_HOST and ch:
                    meta['zulip'] = (f'https://{ZULIP_HOST}/#narrow/channel/{zulip_hash(ZULIP_CHANNELS.get(ch, ch))}'
                                     f'/topic/{zulip_hash(topic)}')
                elif ch:
                    meta['zulip-related'] = f'Zulip: #{ch} › {topic} (link when the Zulip exists)'
                if not has_meta:
                    fence('::: {.discuss}'); fence(':::')
            elif name.startswith('Statement/'):
                key = slug(name.split('/', 1)[1])
                statements.add(name)
                fence('{{< include _statements/' + key + '.md >}}')
            else:
                handled = False
            if handled:
                if rest:
                    out.append(inline(rest))
                i += 1; continue
        # lists
        m = re.match(r'^([*#;:])\s*(.*)$', stripped)
        if m:
            if out and out[-1] != '':
                out.append('')
            while i < n and re.match(r'^[*#;:]', lines[i].strip()):
                mk, body = re.match(r'^([*#;:])\s*(.*)$', lines[i].strip()).groups()
                if mk == '*': out.append('- ' + inline(body))
                elif mk == '#': out.append('1. ' + inline(body))
                elif mk == ';': out.append(inline(body))
                elif mk == ':': out += [':   ' + inline(body), '']
                i += 1
            out.append('')
            continue
        out.append(inline(line))
        i += 1
    if uend is not None:
        fence(':::')
    body = '\n'.join(out)
    body = re.sub(r'\n{3,}', '\n\n', body).strip() + '\n'
    return display, meta, body


def convert_table(rows):
    first = rows[0]
    m_lv = re.search(r'class="(levels[^"]*)"', first)
    if m_lv:
        out = ['', '::: {' + ' '.join('.' + c for c in m_lv.group(1).split()) + '}', '']
        for r in rows[1:-1]:
            r = r.strip()
            if r.startswith('|-') or not r:
                continue
            cells = [c.strip() for c in r[1:].split('||')]
            out += [f'[{inline(cells[0])}]{{.lv}} [{inline(cells[1])}]{{.lv-text}}', '']
        return out + [':::', '']
    header, data, cur = None, [], None
    for r in rows[1:-1]:
        r = r.strip()
        if r.startswith('|-'):
            if cur: data.append(cur)
            cur = None; continue
        if r.startswith('!'):
            header = [c.strip() for c in r[1:].split('!!')]; continue
        if r.startswith('|'):
            cur = [c.strip() for c in split_cells(r[1:])]
    if cur: data.append(cur)
    out = ['', '| ' + ' | '.join(inline(h, True) for h in header) + ' |',
           '|' + '|'.join(':--' for _ in header) + '|']
    for d in data:
        out.append('| ' + ' | '.join(inline(c, True) for c in d) + ' |')
    return out + ['']


def split_cells(r):
    """Split a wikitext table row at '||' outside templates, links and math."""
    cells, cur, i, depth = [], '', 0, 0
    while i < len(r):
        if r.startswith('<math', i):
            j = r.find('</math>', i) + 7; cur += r[i:j]; i = j; continue
        if r.startswith('{{', i) or r.startswith('[[', i): depth += 1; cur += r[i:i + 2]; i += 2; continue
        if r.startswith('}}', i) or r.startswith(']]', i): depth -= 1; cur += r[i:i + 2]; i += 2; continue
        if r.startswith('||', i) and depth == 0:
            cells.append(cur); cur = ''; i += 2; continue
        cur += r[i]; i += 1
    cells.append(cur)
    return cells


# ---------------------------------------------------------------- book structure
def book_structure(sidebar):
    parts, cur = [], None
    for line in sidebar.split('\n'):
        if line.startswith('**'):
            target = line[2:].split('|')[0].strip()
            cur['chapters'].append(target)
        elif line.startswith('*'):
            name = line[1:].strip()
            if name in ('SEARCH', 'TOOLBOX', 'LANGUAGES'):
                cur = None; continue
            cur = {'part': name, 'chapters': []}
            parts.append(cur)
    return parts


QUARTO_YML = '''# Generated by wiki2qmd.py from the wiki export ({source}); do not edit by hand.
# Change the wiki (or this script) and run it again.
project:
  type: book
  output-dir: _book
  resources:
    - mathjax/tex-chtml-full.js
    - mathjax/output/chtml/fonts/woff-v2/*.woff
    - mathjax/LICENSE.txt
    - _headers
    - robots.txt

filters:
  - page-links.lua

# Each page links to its version in the wiki (page-links.lua adds the page title).
wiki-url: {wiki_url}

# No numbers on the website (10 November 2026): pages and sections are not numbered, and results are numbered within
# their page (Theorem 1, Lemma 2); the TeX sources and their PDFs keep the numbering of a paper.
crossref:
  chapters: false

book:
  title: {title}
  subtitle: {subtitle}
  author:{author}
  date: "{date}"
  search: true
  chapters:
{chapters}
  page-footer:
    left: {footer_left}
    right: {footer_right}

format:
  html:
    theme: [cosmo, theme.scss]
    toc: true
    toc-title: "On this page"
    number-sections: false
    crossrefs-hover: true
    link-external-newwindow: true
    include-in-header:
      text: '<meta name="robots" content="noindex, nofollow">'
    html-math-method:
      method: mathjax
      url: "mathjax/tex-chtml-full.js"
'''


def yaml_str(s):
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


# ---------------------------------------------------------------- formula check
def formulas_wiki(text, statements_text):
    text = re.sub(r'<noinclude>.*?</noinclude>', '', text, flags=re.S)
    return [re.sub(r'\s+', ' ', t.strip()) for t in re.findall(r'<math[^>]*>(.*?)</math>', text, flags=re.S)]


def formulas_qmd(text):
    found = []
    def take(m):
        found.append(re.sub(r'\s+', ' ', m.group(1).strip())); return ' '
    text = re.sub(r'\$\$(.+?)\$\$', take, text, flags=re.S)
    re.sub(r'(?<![\\$])\$([^$\n]+?)\$', take, text)
    return found


def badges_from_templates(pages):
    """Take the badge texts from the wiki's own templates, so that a label is changed in one place."""
    for name in list(BADGES):
        text = pages.get('Template:' + name)
        if text is None:
            continue
        m = re.search(r'<span class="(badge-[\w-]+)">(.*?)</span>', re.sub(r'<noinclude>.*?</noinclude>', '', text, flags=re.S))
        if m:
            BADGES[name] = '[' + m.group(2).strip() + ']{.' + m.group(1) + '}'
        else:
            problems.append('badge template not recognized: Template:' + name)


def main():
    global ZULIP_HOST
    pages = read_export(XML)
    badges_from_templates(pages)
    if not ZULIP_HOST:   # the address set once in the wiki, Template:Zulip host
        ZULIP_HOST = strip_noinclude(pages.get('Template:Zulip host', '')).strip()
    # Quarto labels for the results: the prefix must match the kind named in the title
    for t, txt in pages.items():
        for a, b, name, pos, named in templates_in(no_pre(txt)):
            if name == 'Theorem start' and named.get('id'):
                mk = THEOREM_TITLE.match(named.get('title', '').strip())
                wid = named['id']
                if mk and not wid.startswith(THEOREM_PREFIXES):
                    LABEL_RENAME[wid] = KIND_PREFIX[mk.group(1)] + wid.split('-', 1)[-1]
    def expand_inline_statements(text):
        # a statement alone on its line becomes a Quarto include; inside a line it is transcluded, as in MediaWiki
        out_lines = []
        for ln in text.split('\n'):
            if re.fullmatch(r'\s*\{\{Statement/[^{}]+\}\}\s*', ln):
                out_lines.append(ln); continue
            ln = re.sub(r'\{\{(Statement/[^{}|]+)\}\}', lambda m: strip_noinclude(pages.get('Template:' + m.group(1).strip(), '')), ln)
            out_lines.append(ln)
        return '\n'.join(out_lines)
    articles = [t for t in pages if ':' not in t.split('/')[0] and t != 'Main Page']
    lit = wikitex.literature({t: pages[t] for t in articles}) if EDIT else {}
    ARTICLES.update(articles)
    for t, txt in pages.items():
        for a, b, name, pos, named in templates_in(no_pre(txt)):
            if name in ('Theorem start', 'Quote start', 'Result start', 'Media') and named.get('id'):
                IDS.add(named['id'])
            elif name == 'Anchor' and pos:
                IDS.add(pos[0])
    os.makedirs(os.path.join(OUT, '_statements'), exist_ok=True)
    statements, report, mismatches = set(), [], []
    for title in articles:
        source = expand_inline_statements(pages[title])
        display, meta, body = convert_page(title, source, statements)
        if '{{Contributed by' in source:
            body += '\n\n```{=html}\n' + CONTRIB_SCRIPT + '\n```\n'
        if EDIT and not WIKI_IS_PREVIEW:
            tex = wikitex.units_tex(pages[title], lit)
            if tex:
                body += edit_block(title, tex)
        fm = ['---']
        if title != 'Overview':
            fm.append('title: ' + yaml_str(display))
        for k in ('zulip', 'zulip-related'):
            if k in meta:
                fm.append(f'{k}: ' + yaml_str(meta[k]))
        fm.append('wiki-page: ' + yaml_str(title))
        tex = 'tex/' + slug(title) + '.tex'   # the TeX source is named after the page (overview.tex, couette-flow.tex)
        if os.path.exists(os.path.join(OUT, tex)):
            z = tex[:-4] + '.zip'   # a page with pictures: its TeX source and the pictures, in one zip (build-site.sh)
            fm.append('tex-source: ' + yaml_str(z if os.path.exists(os.path.join(OUT, z)) else tex))
            if os.path.exists(os.path.join(OUT, tex[:-4] + '.pdf')):   # compiled by build-site.sh when pdflatex exists
                fm.append('pdf-source: ' + yaml_str(tex[:-4] + '.pdf'))
            if title == 'Overview':   # the whole wiki: one document (and its PDF), and the LaTeX project of all pages
                for k, f in (('book-tex', 'tex/whole-wiki.tex'), ('book-pdf', 'tex/whole-wiki.pdf'), ('book-zip', 'tex/all-pages.zip')):
                    if os.path.exists(os.path.join(OUT, f)):
                        fm.append(k + ': ' + yaml_str(f))
        fm.append('---')
        head = '\n'.join(fm) + '\n\n'
        if title == 'Overview':
            head += '# Overview {.unnumbered}\n\n'
        content = head + body
        open(os.path.join(OUT, qmd_name(title)), 'w').write(content)
        # every formula of the wiki page must appear in the output (pipes in tables are rewritten)
        fw = collections.Counter(formulas_wiki(source, ''))
        fq = collections.Counter(formulas_qmd(body))
        norm = lambda f: f.replace('\\Vert ', '\\|').replace('\\Vert', '\\|').replace('\\vert ', '|').replace('\\vert', '|').replace(' ', '')
        def normalized(counts):
            # sum, rather than overwrite, the counts of formulas that differ only by the table rewrite
            out = collections.Counter()
            for k, v in counts.items():
                out[norm(k)] += v
            return out
        missing = normalized(fw) - normalized(fq)
        if missing:
            mismatches.append((title, list(missing.items())[:5]))
        report.append((qmd_name(title), sum(fw.values())))
    for name in sorted(statements):
        if name not in pages and 'Template:' + name not in pages:
            problems.append('missing statement ' + name); continue
        text = strip_noinclude(pages['Template:' + name])
        key = slug(name.split('/', 1)[1])
        md = inline(text) + '\n'
        open(os.path.join(OUT, '_statements', key + '.md'), 'w').write(md)
        miss = collections.Counter(formulas_wiki(text, '')) - collections.Counter(formulas_qmd(md))
        if miss:
            mismatches.append(('Template:' + name, list(miss.items())[:5]))
    media_out = os.path.join(OUT, 'media')
    shutil.rmtree(media_out, ignore_errors=True)
    if MEDIA_USED:
        os.makedirs(media_out)
        for f in sorted(MEDIA_USED):
            src = os.path.join(MEDIA_DIR, f) if MEDIA_DIR else ''
            if src and os.path.exists(src):
                shutil.copy2(src, os.path.join(media_out, f))
            else:
                problems.append('media file not found (run with --media DIR): ' + f)
    parts = book_structure(pages.get('MediaWiki:Sidebar', ''))
    ch = ['    - index.qmd']
    for p in parts:
        chapters = [c for c in p['chapters'] if c != 'Overview']
        if not chapters:
            continue
        if p['part'].lower() == 'navigation':   # a plain sidebar: chapters without parts
            ch += ['    - ' + qmd_name(c) for c in chapters]
            continue
        if len(chapters) == 1 and chapters[0] == p['part']:   # a part with one page of the same name: a plain chapter
            ch.append('    - ' + qmd_name(chapters[0]))
            continue
        ch.append('    - part: ' + yaml_str(p['part']))
        ch.append('      chapters:')
        ch += ['        - ' + qmd_name(c) for c in chapters]
    import datetime
    if MEDIA_USED:   # files referenced from raw HTML (videos, posters) are not found by Quarto itself
        QUARTO = QUARTO_YML.replace('    - robots.txt\n', '    - robots.txt\n    - media/*\n')
    else:
        QUARTO = QUARTO_YML
    if CONFIG.get('contributors'):   # kit v2.1: the title block lists the groups of contributors, each with its page
        author = ''.join('\n    - name: ' + yaml_str(c['name']) + ('\n      url: ' + yaml_str(c['url']) if c.get('url') else '')
                         for c in CONFIG['contributors'])
        QUARTO = QUARTO.replace('format:\n', 'language:\n  title-block-author-single: "Contributors"\n'
                                '  title-block-author-plural: "Contributors"\n\nformat:\n', 1)
    else:
        author = ' ' + yaml_str(CONFIG['author'])
    if os.path.isdir(os.path.join(OUT, 'tex')):   # TeX sources written by wikitex.py page2tex
        QUARTO = QUARTO.replace('    - robots.txt\n', '    - robots.txt\n    - tex/*.tex\n    - tex/*.pdf\n    - tex/*.zip\n', 1)
    yml = QUARTO.format(source=os.path.basename(XML), date=DATE or datetime.date.today().isoformat(), chapters='\n'.join(ch), author=author,
                        **{k: yaml_str(CONFIG[k]) for k in ('wiki_url', 'title', 'subtitle', 'footer_left', 'footer_right')})
    if CONFIG.get('wiki_note'):   # kit v2.1: e.g. "members", shown after the link to the real wiki
        yml = yml.replace('\nwiki-url: ', '\nwiki-note: ' + yaml_str(CONFIG['wiki_note']) + '\nwiki-url: ', 1)
    if EDIT and EDIT.get('preload_block') and not WIKI_IS_PREVIEW:   # the "Propose a change" link of page-links.lua
        yml = yml.replace('\nwiki-url: ', '\npropose-preload: ' + yaml_str(EDIT['preload_block']) + '\nwiki-url: ', 1)
    open(os.path.join(OUT, '_quarto.yml'), 'w').write(yml)
    print(json.dumps({'pages': report, 'statements': sorted(statements), 'media': sorted(MEDIA_USED), 'formula_mismatches': mismatches,
                      'problems': sorted(set(problems))}, indent=1, ensure_ascii=False))
    if mismatches or problems:
        sys.exit(1)


main()

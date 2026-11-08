#!/usr/bin/env python3
"""wikikit.py: the wiki as a folder of page files, and the MediaWiki XML that Special:Import takes.

  split  <export.xml> <pages-dir>        a Special:Export (or importDump) XML -> one file per page
  build  <pages-dir> <out.xml> [options] page files -> XML for importDump.php or Special:Import
  lint   <pages-dir>                     conventions of the kit (math, boxes, links, anchors, sidebar)
  mathcheck-js <pages-dir> [out.js] [--only "T1|T2"] [--max-chars 20000]
                                         script(s) to run in a browser tab of a Miraheze wiki (the Math
                                         extension): every distinct formula is parsed there (read-only
                                         API) and the failures are listed; split into out-1.js, out-2.js,
                                         ... when longer than --max-chars
  titles <pages-dir> [--wiki URL]        titles for Special:Export (sidebar pages + MediaWiki:Sidebar),
                                         and the export URL when --wiki is given

Layout of a pages directory: one sub-folder per namespace (Main, Talk, Template, MediaWiki, Help, ...);
file name = title without the namespace, with / \\ : * ? " < > | % percent-encoded; wikitext pages
end in .wiki, CSS and JavaScript pages keep their own name (MediaWiki/Common.css, MediaWiki/Common.js).
Example: Template:Statement/Main result -> Template/Statement%2FMain result.wiki

build options: --user NAME (contributor of the imported revisions, default MicDol), --comment TEXT,
--timestamp YYYY-MM-DDTHH:MM:SSZ (default: now), --sitename TEXT. Build the file on the day of an
import into a real wiki: a revision older than the page's current one does not become current.
Python 3.8+, standard library only. Part of the wiki kit (2026); drafted by Claude (AI).
"""
import collections, datetime, hashlib, json, os, re, sys, unicodedata, urllib.parse
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape, quoteattr

NAMESPACES = {0: '', 1: 'Talk', 2: 'User', 3: 'User talk', 4: 'Project', 5: 'Project talk', 6: 'File',
              7: 'File talk', 8: 'MediaWiki', 9: 'MediaWiki talk', 10: 'Template', 11: 'Template talk',
              12: 'Help', 13: 'Help talk', 14: 'Category', 15: 'Category talk'}
DIR_OF = {k: (v or 'Main') for k, v in NAMESPACES.items()}
NS_OF_DIR = {v: k for k, v in DIR_OF.items()}
NS_OF_PREFIX = {v.lower(): k for k, v in NAMESPACES.items() if v}
NS_OF_PREFIX.update({'image': 6, 'project': 4})
MODELS = {'.css': ('css', 'text/css'), '.js': ('javascript', 'text/javascript'), '.json': ('json', 'application/json')}
WIKITEXT = ('wikitext', 'text/x-wiki')
UNSAFE = set('%/\\:*?"<>|')
INTERWIKI = {'w', 'wikipedia', 'wikt', 'wiktionary', 'mw', 'mediawikiwiki', 'meta', 'm', 'commons', 'c', 'd',
             'wikidata', 'mh', 'miraheze', 'arxiv', 'doi', 'google'}
BOXES = ('Theorem', 'Level', 'Proof', 'Fold', 'Quote', 'Placeholder', 'Card')
ID_PREFIXES = ('thm-', 'prp-', 'prop-', 'lem-', 'cor-', 'def-', 'clm-')
MAGIC = {'PAGENAME', 'FULLPAGENAME', 'BASEPAGENAME', 'SUBPAGENAME', 'NAMESPACE', 'TALKPAGENAME', 'SITENAME',
         'SERVER', 'SCRIPTPATH', 'CURRENTYEAR', 'CURRENTMONTH', 'CURRENTDAY', 'CURRENTTIMESTAMP', 'REVISIONID',
         '!', '=', 'PAGENAMEE', 'FULLPAGENAMEE'}
# Checked against the Math extension of Miraheze (MediaWiki 1.46.2) on 5 Nov 2026: all of these are rejected.
TEX_ERRORS = {
    r'\newcommand': r'macro definitions are rejected; write the macro out', r'\renewcommand': r'macro definitions are rejected',
    r'\def': r'macro definitions are rejected', r'\let': r'macro definitions are rejected',
    r'\DeclareMathOperator': r'macro definitions are rejected; use \operatorname{...}',
    r'\label': r'rejected; give the box an id= and link to it', r'\eqref': r'rejected; link to a box id',
    r'\ref': r'rejected; link to a box id', r'\tag': r'rejected; name the box instead of numbering the formula',
    r'\substack': r'rejected; use \begin{smallmatrix} or put the conditions in the text',
    r'\mathds': r'unknown; use \mathbb{1} or \mathbf{1}', r'\mathbbm': r'unknown; use \mathbb{1} or \mathbf{1}',
    r'\mathscr': r'rejected; use \mathcal', r'\bm': r'unknown; use \boldsymbol',
    r'\coloneqq': r'unknown; use :=', r'\eqqcolon': r'unknown; use =:', r'\vcentcolon': r'unknown; use :',
    r'\llbracket': r'unknown; use [\![', r'\rrbracket': r'unknown; use ]\!]', r'\fint': r'unknown; write the average out',
    r'\middle': r'unknown; use \mid or \,\big|\,', r'\genfrac': r'rejected; use \frac or \binom',
    r'\hspace': r'rejected; use \quad, \qquad, \, or \;', r'\:': r'rejected; use \, or \;',
    r'\boxed': r'rejected', r'\mathring': r'rejected; use \overset{\circ}{u}',
    r'\lvert': r'unknown; use | or \vert', r'\rvert': r'unknown; use | or \vert', r'\nobreakspace': r'rejected; use "\ "',
    r'\begin{gathered}': r'unknown; use \begin{matrix} or \begin{array}{c}', r'\begin{split}': r'unknown; use \begin{aligned}',
    r'\qed': r'unknown; use \square', r'\textup': r'rejected; use \text', r'\textnormal': r'rejected; use \text',
    r'\textsc': r'unknown; use \text', r'\idotsint': r'unknown; use \int\cdots\int', r'\emph': r'fails to render; use \textit'}
TEX_WARNINGS = {}


# ------------------------------------------------------------------ titles and files
def norm_title(t):
    """MediaWiki normalisation: underscores, spaces, first letter of the namespace and of the title."""
    t = t.replace('_', ' ').strip()
    t = re.sub(r'\s+', ' ', t)
    ns, rest = 0, t
    if ':' in t:
        p, r = t.split(':', 1)
        if p.strip().lower() in NS_OF_PREFIX:
            ns, rest = NS_OF_PREFIX[p.strip().lower()], r.strip()
    rest = rest[:1].upper() + rest[1:]
    return (NAMESPACES[ns] + ':' + rest) if ns else rest


def split_title(title):
    if ':' in title:
        p, r = title.split(':', 1)
        if p.lower() in NS_OF_PREFIX:
            return NS_OF_PREFIX[p.lower()], r
    return 0, title


def encode_name(s):
    return ''.join('%%%02X' % ord(c) if (c in UNSAFE or ord(c) < 32) else c for c in s)


def file_for(title, model):
    ns, rest = split_title(title)
    name = encode_name(rest)
    if model == 'wikitext' or not os.path.splitext(rest)[1] in MODELS:
        name += '.wiki'
    return os.path.join(DIR_OF[ns], name)


def read_pages(pdir):
    """{title: (ns, model, format, text)} from a pages directory."""
    pages = {}
    for d in sorted(os.listdir(pdir)):
        full = os.path.join(pdir, d)
        if not os.path.isdir(full) or d.startswith('.'):
            continue
        if d not in NS_OF_DIR:
            sys.exit(f'unknown namespace folder: {d} (expected one of {", ".join(sorted(NS_OF_DIR))})')
        ns = NS_OF_DIR[d]
        for f in sorted(os.listdir(full)):
            if f.startswith('.'):
                continue
            stem, ext = os.path.splitext(f)
            if ext == '.wiki':
                model, fmt = WIKITEXT
                name = urllib.parse.unquote(stem)
            elif ext in MODELS:
                model, fmt = MODELS[ext]
                name = urllib.parse.unquote(f)
            else:
                print(f'skipped (unknown extension): {d}/{f}', file=sys.stderr)
                continue
            title = (NAMESPACES[ns] + ':' + name) if ns else name
            text = open(os.path.join(full, f), encoding='utf-8').read().rstrip()
            pages[title] = (ns, model, fmt, text)
    return pages


# ------------------------------------------------------------------ split / build
def cmd_split(xml, pdir):
    root = ET.parse(xml).getroot()
    q = root.tag.split('}')[0] + '}'
    n = 0
    for p in root.findall(q + 'page'):
        title = p.find(q + 'title').text
        ns = int(p.find(q + 'ns').text)
        if ns not in NAMESPACES:
            print(f'skipped (namespace {ns}): {title}', file=sys.stderr)
            continue
        rev = p.findall(q + 'revision')[-1]
        model_el = rev.find(q + 'model')
        model = model_el.text if model_el is not None else 'wikitext'
        text = rev.find(q + 'text').text or ''
        path = os.path.join(pdir, file_for(title, model))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text.rstrip() + '\n')
        n += 1
    print(f'{n} pages written to {pdir}')


def sha1_base36(text):
    v = int(hashlib.sha1(text.encode('utf-8')).hexdigest(), 16)
    digits = '0123456789abcdefghijklmnopqrstuvwxyz'
    out = ''
    while v:
        v, r = divmod(v, 36)
        out = digits[r] + out
    return out.rjust(31, '0')


def cmd_build(pdir, out, user='MicDol', comment=None, timestamp=None, sitename='Wiki (from the wiki kit)'):
    pages = read_pages(pdir)
    ts = timestamp or datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    comment = comment or 'Imported from the wiki kit; text drafted by Claude (AI) for Michele'
    # templates and interface pages first, then articles, then talk pages
    order = sorted(pages, key=lambda t: ({10: 0, 8: 1, 0: 2, 1: 3}.get(pages[t][0], 4), t))
    L = ['<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/" '
         'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
         'xsi:schemaLocation="http://www.mediawiki.org/xml/export-0.11/ http://www.mediawiki.org/xml/export-0.11.xsd" '
         'version="0.11" xml:lang="en">',
         '  <siteinfo>', f'    <sitename>{escape(sitename)}</sitename>', '    <dbname>wikikit</dbname>',
         '    <base>http://127.0.0.1:8080/index.php/Main_Page</base>', '    <generator>wikikit.py</generator>',
         '    <case>first-letter</case>', '    <namespaces>']
    for k, v in sorted(NAMESPACES.items()):
        L.append(f'      <namespace key="{k}" case="first-letter"' + (f'>{escape(v)}</namespace>' if v else ' />'))
    L += ['    </namespaces>', '  </siteinfo>']
    for i, title in enumerate(order, 1):
        ns, model, fmt, text = pages[title]
        L += ['  <page>', f'    <title>{escape(title)}</title>', f'    <ns>{ns}</ns>', f'    <id>{i}</id>']
        m = re.match(r'#REDIRECT\s*\[\[([^\]|#]+)', text, re.I)
        if m:
            L.append(f'    <redirect title={quoteattr(norm_title(m.group(1)))} />')
        L += ['    <revision>', f'      <id>{i}</id>', f'      <timestamp>{ts}</timestamp>',
              f'      <contributor>', f'        <username>{escape(user)}</username>', '      </contributor>',
              f'      <comment>{escape(comment)}</comment>', f'      <model>{model}</model>', f'      <format>{fmt}</format>',
              f'      <text bytes="{len(text.encode("utf-8"))}" xml:space="preserve">{escape(text)}</text>',
              f'      <sha1>{sha1_base36(text)}</sha1>', '    </revision>', '  </page>']
    L.append('</mediawiki>')
    with open(out, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(L) + '\n')
    ET.parse(out)   # well-formed
    print(f'{len(order)} pages -> {out} (timestamp {ts}, contributor {user})')


# ------------------------------------------------------------------ wikitext helpers
def strip_noise(text):
    text = re.sub(r'<!--.*?-->', '', text, flags=re.S)
    text = re.sub(r'<nowiki>.*?</nowiki>', '', text, flags=re.S)
    text = re.sub(r'<(pre|syntaxhighlight|source)[^>]*>.*?</\1>', '', text, flags=re.S)
    return text


def mask_math(text):
    return re.sub(r'<math[^>]*>.*?</math>', lambda m: '\x01' * len(m.group(0)), text, flags=re.S)


def plain(s):
    s = re.sub(r'<math[^>]*>.*?</math>', '…', s, flags=re.S)
    s = re.sub(r'\{\{[^{}]*\}\}', '', s)
    s = re.sub(r'\[\[(?:[^\]|]*\|)?([^\]]*)\]\]', r'\1', s)
    s = re.sub(r"'{2,}", '', s)
    s = re.sub(r'<[^>]+>', '', s)
    return re.sub(r'\s+', ' ', s).strip()


def template_calls(text):
    """(name, params, line) for every {{...}} call, innermost included; {{{params}}} skipped."""
    out, stack, i, line = [], [], 0, 1
    t = mask_math(text)
    while i < len(t):
        if t.startswith('{{{', i):
            j = t.find('}}}', i)
            i = j + 3 if j > 0 else i + 3
            continue
        if t.startswith('{{', i):
            stack.append((i, line)); i += 2; continue
        if t.startswith('}}', i) and stack:
            s, ln = stack.pop()
            inner = text[s + 2:i]
            name = re.split(r'[|]', inner, maxsplit=1)[0].strip()
            out.append((name, inner, ln))
            i += 2; continue
        if t[i] == '\n':
            line += 1
        i += 1
    return out


def param(inner, name):
    m = re.search(r'\|\s*' + name + r'\s*=([^|}]*)', inner)
    return m.group(1).strip() if m else ''


def anchors_of(text):
    """Section anchors and box ids that [[Page#anchor]] can reach."""
    text = strip_noise(text)
    a = set()
    for m in re.finditer(r'^(={2,6})\s*(.+?)\s*\1\s*$', text, flags=re.M):
        a.add(plain(m.group(2)))
    for name, inner, _ in template_calls(text):
        if name in ('Theorem start', 'Quote start', 'Media') and param(inner, 'id'):
            a.add(param(inner, 'id'))
        elif name == 'Level start':
            a.add(param(inner, 'id') or plain(param(inner, 'title')) or 'Idea')
        elif name == 'Proof start':
            a.add(param(inner, 'id') or 'Proof')
        elif name == 'Anchor':
            a.update(p.strip() for p in inner.split('|')[1:])
    for m in re.finditer(r'\bid\s*=\s*"([^"{}]+)"', text):
        a.add(m.group(1))
    return a


MULTIWORD_SURNAMES = ('Coti Zelati', 'Del Zotto', 'De Lellis', 'Punshon-Smith')   # sorted under their first word


def first_author_key(item):
    authors = re.split(r",\s*''", item, maxsplit=1)[0]
    first = re.split(r'\s+and\s+|,\s*', authors.strip())[0]
    first = re.sub(r'^\{\{Anchor\|[^}]*\}\}\s*', '', first)
    for ms in MULTIWORD_SURNAMES:
        if first.strip().endswith(ms):
            return unicodedata.normalize('NFKD', ms).encode('ascii', 'ignore').decode().lower()
    surname = re.sub(r"[^\w\s'-]", '', first).split()
    s = surname[-1] if surname else first
    return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()


# ------------------------------------------------------------------ lint
def cmd_lint(pdir):
    pages = read_pages(pdir)
    errors, warnings = [], []
    E = lambda t, msg: errors.append(f'{t}: {msg}')
    W = lambda t, msg: warnings.append(f'{t}: {msg}')
    redirects = {t for t, (ns, m, f, x) in pages.items() if re.match(r'#REDIRECT', x, re.I)}
    anchors = {t: anchors_of(x) for t, (ns, m, f, x) in pages.items() if m == 'wikitext'}
    box_ids = collections.defaultdict(list)
    for title, (ns, model, fmt, text) in pages.items():
        if model != 'wikitext':
            continue
        if title == 'History':
            E(title, 'do not call a page "History": the word clashes with the history link of the sidebar')
        body = strip_noise(text)
        is_tpl = ns == 10
        own = (not is_tpl) or title.startswith(('Template:Statement/', 'Template:Module/'))
        view = re.sub(r'<includeonly>.*?</includeonly>', '', body, flags=re.S) if is_tpl else body
        # math
        for m in re.finditer(r'<math(\s[^>]*)?>(.*?)</math>', body, flags=re.S):
            attrs, tex = m.group(1) or '', m.group(2)
            ln = body[:m.start()].count('\n') + 1
            d = re.search(r'display\s*=\s*"([^"]*)"', attrs)
            if not d:
                E(title, f'line {ln}: <math> without display="inline" or display="block": {tex[:50]}')
            elif d.group(1) not in ('inline', 'block'):
                E(title, f'line {ln}: display="{d.group(1)}" (use inline or block)')
            for cmd, why in TEX_ERRORS.items():
                if re.search(re.escape(cmd) + (r'(?![A-Za-z])' if cmd[-1].isalpha() else ''), tex):
                    E(title, f'line {ln}: {cmd} in a formula: {why}')
            for cmd, why in TEX_WARNINGS.items():
                if re.search(re.escape(cmd) + (r'(?![A-Za-z])' if cmd[-1].isalpha() else ''), tex):
                    W(title, f'line {ln}: {cmd} in a formula: {why}')
            depth = 0
            for c in re.sub(r'\\[{}]', '', tex):
                depth += (c == '{') - (c == '}')
                if depth < 0:
                    break
            if depth != 0:
                E(title, f'line {ln}: unbalanced braces in {tex[:60]}')
        if re.search(r'<math(?![^>]*>.*?</math>)', body, flags=re.S):
            E(title, '<math> tag not closed')
        # boxes
        if own:
            stack = []
            for name, inner, ln in template_calls(view):
                m = re.match(r'^(%s) (start|end)$' % '|'.join(BOXES), name)
                if not m:
                    continue
                kind, se = m.groups()
                if se == 'start':
                    stack.append((kind, ln))
                elif not stack or stack[-1][0] != kind:
                    E(title, f'line {ln}: {kind} end without a matching {kind} start' + (f' (open: {stack[-1][0]} start, line {stack[-1][1]})' if stack else ''))
                else:
                    k0, l0 = stack.pop()
                    if kind == 'Placeholder' and l0 != ln:
                        E(title, f'line {l0}: a placeholder must start and end on the same line (Quarto converter)')
            for kind, ln in stack:
                E(title, f'line {ln}: {kind} start is never closed')
            for name, inner, ln in template_calls(view):
                if name == 'Theorem start':
                    tid, ttl = param(inner, 'id'), param(inner, 'title')
                    if not tid or not ttl:
                        E(title, f'line {ln}: Theorem start needs id= and title=')
                    elif not tid.startswith(ID_PREFIXES):
                        W(title, f'line {ln}: id "{tid}" should start with one of {", ".join(ID_PREFIXES)}')
                    if tid:
                        box_ids[tid].append(title)
                    if ttl and not re.match(r'^(Theorem|Lemma|Proposition|Corollary|Definition|Remark|Conjecture|Claim)\b', ttl):
                        W(title, f'line {ln}: title "{ttl}" should read "Theorem (name)." (or Lemma, Proposition, ...)')
        # media files (kit v2.1): {{Media|file=...|poster=...}} must exist in <pages-dir>/../media
        if not is_tpl:
            mdir = os.path.join(os.path.dirname(os.path.abspath(pdir)), 'media')
            for name, inner, ln in template_calls(view):
                if name == 'Media':
                    for key in ('file', 'poster'):
                        f = param(inner, key)
                        if key == 'file' and not f:
                            E(title, f'line {ln}: Media without file=')
                        elif f and not os.path.exists(os.path.join(mdir, f)):
                            (E if os.path.isdir(mdir) else W)(title, f'line {ln}: media file not found in {mdir}: {f}')
        # templates used
        if not is_tpl or own:
            for name, inner, ln in template_calls(view):
                n = name.strip()
                if not n or n.startswith('#') or ':' in n or n in MAGIC:
                    continue
                if 'Template:' + n[:1].upper() + n[1:] not in pages:
                    E(title, f'line {ln}: template {{{{{n}}}}} does not exist')
        # links
        for m in re.finditer(r'\[\[([^\[\]|]*)(?:\|[^\[\]]*)?\]\]', view):
            target = m.group(1).strip()
            ln = view[:m.start()].count('\n') + 1
            if not target or '{{' in target or target.startswith(':') and target[1:].lower().startswith(('category:', 'file:')):
                continue
            page_part, _, anchor = target.partition('#')
            pref = page_part.split(':', 1)[0].strip().lower() if ':' in page_part else ''
            if pref in ('file', 'image', 'media', 'category', 'special') or pref in INTERWIKI:
                continue
            tgt = norm_title(page_part) if page_part.strip() else title
            if tgt not in pages:
                (W if tgt.startswith('Talk:') else E)(title, f'line {ln}: link to a missing page [[{target}]]')
                continue
            if tgt in redirects:
                W(title, f'line {ln}: link to a redirect [[{target}]]')
            if anchor and pages[tgt][1] == 'wikitext' and anchor.replace('_', ' ').strip() not in anchors[tgt] \
                    and anchor.strip() not in anchors[tgt]:
                E(title, f'line {ln}: anchor not found on {tgt}: #{anchor}')
        # headings
        heads = [plain(h) for _, h in re.findall(r'^(={2,6})\s*(.+?)\s*\1\s*$', body, flags=re.M)]
        for h, c in collections.Counter(heads).items():
            if c > 1 and not is_tpl:
                W(title, f'heading "{h}" appears {c} times; links reach only the first')
        if re.search(r'^={2,6}.*<math.*={2,6}\s*$', body, flags=re.M):
            W(title, 'a formula in a heading makes its anchor fragile')
        # references
        m = re.search(r'^==\s*References\s*==\s*$(.*?)(?=^==[^=]|\Z)', body, flags=re.M | re.S)
        if m:
            items = [x[1:].strip() for x in m.group(1).split('\n') if x.startswith('#')]
            keys = [first_author_key(x) for x in items]
            for a, b, x in zip(keys, keys[1:], items[1:]):
                if b < a:
                    W(title, f'references not in alphabetical order of the first author near: {x[:60]}')
                    break
    # wiki-wide checks
    for tid, where in box_ids.items():
        if len(where) > 1:
            E(', '.join(where), f'box id "{tid}" used more than once (labels must be unique in the Quarto book)')
    side = pages.get('MediaWiki:Sidebar')
    listed = []
    if side is None:
        E('MediaWiki:Sidebar', 'missing')
    else:
        for line in side[3].split('\n'):
            if line.startswith('**'):
                t = norm_title(line[2:].split('|')[0])
                listed.append(t)
                if t not in pages:
                    E('MediaWiki:Sidebar', f'lists a missing page: {t}')
    for title, (ns, model, fmt, text) in pages.items():
        if ns == 0 and title not in redirects and title != 'Main Page':
            if side is not None and title not in listed:
                W(title, 'not listed in MediaWiki:Sidebar (no menu entry, no navigation tree, not in the Quarto edition)')
            talk = pages.get('Talk:' + title)
            if talk is None:
                W(title, 'no talk page')
            elif not talk[3].lstrip().startswith('== How to use this page =='):
                W('Talk:' + title, 'should start with the section "How to use this page"')
    if 'Main Page' not in pages:
        W('Main Page', 'missing (the kit makes it a redirect to Overview)')
    for e in errors:
        print('ERROR  ' + e)
    for w in warnings:
        print('warn   ' + w)
    n_math = sum(len(re.findall(r'<math', strip_noise(p[3]))) for p in pages.values() if p[1] == 'wikitext')
    print(f'{len(pages)} pages, {n_math} formulas: {len(errors)} errors, {len(warnings)} warnings')
    return 1 if errors else 0


# ------------------------------------------------------------------ math check in a browser tab
MATHCHECK_JS = r"""// Generated by wikikit.py mathcheck-js. Run it in a browser tab of a wiki with the Math extension
// (for instance https://meta.miraheze.org/wiki/Main_Page, or the project's own wiki): it parses the
// formulas with the read-only API (action=parse; nothing is saved) and returns the failures.
const __mathcheck = await (async () => {
  const F = __FORMULAS__;
  const api = (typeof mw !== 'undefined' && mw.util && mw.util.wikiScript) ? mw.util.wikiScript('api') : '/w/api.php';
  const errors = [], CHUNK = 40;
  for (let i = 0; i < F.length; i += CHUNK) {
    const chunk = F.slice(i, i + CHUNK);
    const text = chunk.map((f, j) => `<div id="mc-${i + j}">${f.tag}</div>`).join('\n');
    const body = new URLSearchParams({action: 'parse', format: 'json', formatversion: '2', contentmodel: 'wikitext',
                                      prop: 'text', disablelimitreport: '1', text});
    const r = await fetch(api, {method: 'POST', body}).then(x => x.json());
    if (!r.parse) { errors.push({chunk: i, api: r.error || r}); continue; }
    const doc = new DOMParser().parseFromString(r.parse.text, 'text/html');
    chunk.forEach((f, j) => {
      const d = doc.getElementById('mc-' + (i + j));
      const e = d && d.querySelector('.error, .texerror, .mwe-math-error');
      if (!d || e) errors.push({pages: f.pages, tag: f.tag, error: e ? e.textContent.slice(0, 300) : 'not rendered'});
    });
    await new Promise(res => setTimeout(res, 300));
  }
  return {checked: F.length, errors};
})();
__mathcheck
"""


def cmd_mathcheck_js(pdir, out=None, only=None, max_chars=20000):
    """Write one or more self-contained scripts (check.js, or check-1.js, check-2.js, ... when the
    formulas do not fit in max_chars characters); --only "Title|Title" restricts to some pages."""
    pages = read_pages(pdir)
    keep = set(t.strip() for t in only.split('|')) if only else None
    seen = collections.OrderedDict()
    for title, (ns, model, fmt, text) in pages.items():
        if model != 'wikitext' or (keep and title not in keep):
            continue
        for m in re.finditer(r'<math[^>]*>.*?</math>', strip_noise(text), flags=re.S):
            seen.setdefault(m.group(0), []).append(title)
    data = [{'tag': k, 'pages': sorted(set(v))} for k, v in seen.items()]
    groups, cur, size = [], [], 0
    for d in data:
        n = len(json.dumps(d, ensure_ascii=False)) + 2
        if cur and size + n > max_chars:
            groups.append(cur); cur, size = [], 0
        cur.append(d); size += n
    if cur or not groups:
        groups.append(cur)
    scripts = [MATHCHECK_JS.replace('__FORMULAS__', json.dumps(g, ensure_ascii=False)) for g in groups]
    if not out:
        print('\n'.join(scripts)); return
    stem, ext = os.path.splitext(out)
    names = [out] if len(scripts) == 1 else [f'{stem}-{i}{ext or ".js"}' for i in range(1, len(scripts) + 1)]
    for name, js in zip(names, scripts):
        open(name, 'w', encoding='utf-8').write(js)
    print(f'{len(data)} distinct formulas -> ' + ', '.join(f'{n} ({len(j)} characters)' for n, j in zip(names, scripts)))


def cmd_titles(pdir, wiki=None):
    pages = read_pages(pdir)
    side = pages.get('MediaWiki:Sidebar')
    titles = []
    if side:
        for line in side[3].split('\n'):
            if line.startswith('**'):
                t = norm_title(line[2:].split('|')[0])
                if t not in titles:
                    titles.append(t)
    titles.append('MediaWiki:Sidebar')
    print('\n'.join(titles))
    if wiki:
        url = wiki.rstrip('/') + '/wiki/Special:Export?pages=' + urllib.parse.quote('\n'.join(titles)) + '&templates=1&wpDownload=1'
        print('\nExport URL (open it while logged in; it includes the templates):\n' + url)


def main(argv):
    if len(argv) < 2 or argv[1] in ('-h', '--help'):
        print(__doc__); return 0
    cmd, args = argv[1], argv[2:]
    opts = {}
    pos = []
    i = 0
    while i < len(args):
        if args[i].startswith('--'):
            opts[args[i][2:]] = args[i + 1]; i += 2
        else:
            pos.append(args[i]); i += 1
    if cmd == 'split':
        cmd_split(*pos)
    elif cmd == 'build':
        cmd_build(pos[0], pos[1], user=opts.get('user', 'MicDol'), comment=opts.get('comment'),
                  timestamp=opts.get('timestamp'), sitename=opts.get('sitename', 'Wiki (from the wiki kit)'))
    elif cmd == 'lint':
        return cmd_lint(pos[0])
    elif cmd == 'mathcheck-js':
        cmd_mathcheck_js(pos[0], pos[1] if len(pos) > 1 else None, only=opts.get('only'),
                         max_chars=int(opts.get('max-chars', 20000)))
    elif cmd == 'titles':
        cmd_titles(pos[0], opts.get('wiki'))
    else:
        print(__doc__); return 2
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))

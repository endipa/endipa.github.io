#!/usr/bin/env python3
r"""wikitex.py: the TeX format of the wiki, in both directions (wiki kit v2.1).

Every page of the wiki has a TeX source: one file, written like a standard paper (article class,
\title and \maketitle, numbered sections and statements, amsthm proofs, natbib citations with the
bibliography at the end), that compiles as it is with pdflatex and no other file. Its preamble is
fixed; contributors download the file, change what they want, and post only the blocks they change.
This script writes the TeX sources, converts TeX back to wikitext, and applies a proposal to a page.

  page2tex <pages-dir | export.xml> <out-dir> [--date YYYY-MM-DD] [--site NAME]
        one <slug>.tex per article (the slug is the file name of the page in the edition)
  tex2page <file.tex>
        the wikitext of a whole page, on standard output
  apply <pages-dir> <proposal.tex> [--write]
        a proposal names its page with \title{...} and contains blocks: \section{...} (with
        everything up to the next section of the same level) or a labelled environment
        (\begin{theorem}[...]\label{thm-x} ... \end{theorem}, \begin{proof}\label{proof-x} ...).
        Each block replaces the block of the same title or label on the page; a block preceded by a
        line "%% after: <title or label>" is inserted there. Prints the change as a diff, and flags
        what an editor must look at: new citations (they are also added to the page's reference
        list, from the Literature page), new links, blocks that did not change. --write saves the
        new page file.
  check <file.tex> [--pages <pages-dir>]
        what the conversion does not accept: macros, numbered equations, labels on equations,
        \ref, unknown citation keys (with --pages: the keys of the Literature page are known), unknown
        commands, formulas the wiki's renderer rejects
  book <pages-dir | export.xml> <tex-dir> <out.tex> [--site NAME] [--date YYYY-MM-DD]
        the whole wiki in one document (a section per page, in the order of the menu), from the page files
  roundtrip <pages-dir>
        page -> TeX -> page on every article: must give back the page

Correspondence (wiki -> TeX): [[Literature#Key|Names (year)]] -> \citet{Key} and ([[Literature#Key|Names,
year]]) -> \citep{Key}, when Key is in the page's reference list; [[#label|text]] -> \hyperref[label]{text},
when the label is on the page; other links -> \wikilink{Page#anchor}{text}. The reference list of a page
(between <!-- refs-begin: ... --> and <!-- refs-end -->) is the thebibliography, the entries being those of
the Literature page.

Python 3.8+, standard library only. Part of the wiki kit (2026); drafted by Claude (AI).
"""
import datetime, difflib, os, re, sys, unicodedata
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wikikit  # noqa: E402  (read_pages, TEX_ERRORS)

STATEMENTS = ('Theorem', 'Proposition', 'Lemma', 'Corollary', 'Definition', 'Claim', 'Remark', 'Conjecture', 'Example')
STATEMENT_ENVS = {k.lower(): k for k in STATEMENTS}
BADGES = {'Demo': 'demo', 'Heuristic': 'heuristic', 'Numeric': 'numerics', 'Preprint': 'preprint',
          'Published': 'published', 'Raw': 'raw'}
BADGE_OF_CMD = {v: k for k, v in BADGES.items()}
FOLD_ENVS = {'idea': ('idea', 'Idea'), 'arch': ('architecture', 'Proof architecture'), 'note': ('note', '')}
FOLD_KIND = {v[0]: (k, v[1]) for k, v in FOLD_ENVS.items()}
FOLD_KIND['fold'] = ('note', '')   # name of the environment in the first TeX format (8 November 2026)
CITE_CMDS = ('cite', 'citet', 'citep', 'citeauthor', 'citeyear')
IGNORED_CMDS = ('noindent', 'medskip', 'smallskip', 'bigskip', 'newpage', 'clearpage', 'phantomsection')
MONTHS = ('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October',
          'November', 'December')
SECTION_CMDS = {2: 'section', 3: 'subsection', 4: 'subsubsection'}
LEVEL_OF_CMD = {v: k for k, v in SECTION_CMDS.items()}
SPECIAL = {'\\': r'\textbackslash{}', '{': r'\{', '}': r'\}', '$': r'\$', '&': r'\&', '#': r'\#',
           '^': r'\textasciicircum{}', '_': r'\_', '~': r'\textasciitilde{}', '%': r'\%'}


def slug(title):
    title = title.replace('–', '-').replace('—', '-')
    s = unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode().lower().replace("'", '').replace('’', '')
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')


def esc(s):
    return ''.join(SPECIAL.get(c, c) for c in s)


def long_date(iso):
    try:
        d = datetime.date.fromisoformat(iso)
    except ValueError:
        return iso
    return '%d %s %d' % (d.day, MONTHS[d.month - 1], d.year)


# ------------------------------------------------------------------ references
def literature(arts):
    """{key: entry} from the Literature page, whose lines are '# {{Anchor|Key}} entry'."""
    out = {}
    for line in arts.get('Literature', '').split('\n'):
        m = re.match(r'^[#*]\s*\{\{Anchor\|([^}|]+)\}\}\s*(.*)$', line.strip())
        if m:
            out[m.group(1).strip()] = m.group(2).strip()
    return out


def cite_info(entry):
    """(names, year) of an entry 'A. Author and B. Author, ''Title'', Journal (year), ...': the text of
    its citations, 'Names (year)'; None if the entry is not in this form."""
    k = entry.find(", ''")
    t = entry.find("''", k + 3) if k > 0 else -1
    if t < 0:
        return None
    names = []
    for a in re.split(r', | and ', entry[:k]):
        toks = a.split()
        while len(toks) > 1 and toks[0].endswith('.'):
            toks = toks[1:]
        names.append(' '.join(toks))
    m = re.search(r'\((\d{4})\)', entry[t:])
    if not m or not all(names):
        return None
    return (names[0] if len(names) == 1 else ', '.join(names[:-1]) + ' and ' + names[-1]), m.group(1)


def ref_order(entry, key):
    """The order of a reference list (refs_from_catalog.py): first author, year of publication, key."""
    first = re.split(r', | and ', entry.split(", ''")[0])[0].split()
    while len(first) > 1 and first[0].endswith('.'):
        first = first[1:]
    surname = unicodedata.normalize('NFKD', ' '.join(first)).encode('ascii', 'ignore').decode().lower()
    info = cite_info(entry)
    year = 0 if (not info or re.search(r'preprint \(\d{4}\)', entry)) else int(info[1])
    return surname, year, key


def unesc(s):
    s = s.replace(r'\textbackslash{}', '\x01').replace(r'\textasciicircum{}', '^').replace(r'\textasciitilde{}', '~')
    s = re.sub(r'\\([{}$&#_%])', r'\1', s)
    return s.replace('\x01', '\\')


# ------------------------------------------------------------------ wikitext helpers
def template_end(s, i):
    """End (exclusive) of the template call that starts at s[i] == '{{'."""
    depth = 0
    while i < len(s):
        if s.startswith('<math', i):
            j = s.find('</math>', i)
            i = j + 7 if j >= 0 else len(s)
            continue
        if s.startswith('{{', i):
            depth += 1; i += 2; continue
        if s.startswith('}}', i):
            depth -= 1; i += 2
            if depth == 0:
                return i
            continue
        i += 1
    raise ValueError('unbalanced template: ' + s[:60])


def split_params(inner):
    parts, dt, dl, cur, i = [], 0, 0, '', 0
    while i < len(inner):
        if inner.startswith('<math', i):
            j = inner.find('</math>', i) + 7
            cur += inner[i:j]; i = j; continue
        two = inner[i:i + 2]
        if two in ('{{', '}}', '[[', ']]'):
            dt += (two == '{{') - (two == '}}'); dl += (two == '[[') - (two == ']]')
            cur += two; i += 2; continue
        if inner[i] == '|' and dt == 0 and dl == 0:
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


def link_end(s, i):
    """End (exclusive) of the [[...]] link starting at s[i]."""
    j = i + 2
    while j < len(s):
        if s.startswith('<math', j):
            j = s.find('</math>', j) + 7; continue
        if s.startswith(']]', j):
            return j + 2
        j += 1
    raise ValueError('unclosed link: ' + s[i:i + 60])


# ------------------------------------------------------------------ wiki -> TeX
class W2T:
    def __init__(self, lit=None):
        self.problems = []
        self.lit = lit or {}                                # the entries of the Literature page
        self.key_of = {v: k for k, v in self.lit.items()}
        self.labels = set()                                 # anchors of the page: \hyperref targets
        self.bib = {}                                       # key -> (names, year), the page's reference list

    def inline(self, s):
        tokens, out, i = [], [], 0

        def tok(x):
            tokens.append(x)
            return '\x00%d\x00' % (len(tokens) - 1)
        while i < len(s):
            if s.startswith('<math', i):
                m = re.match(r'<math([^>]*)>(.*?)</math>', s[i:], re.S)
                block = 'display="block"' in m.group(1)
                out.append(tok((r'\[' + m.group(2) + r'\]') if block else ('$' + m.group(2) + '$')))
                i += m.end(); continue
            m = re.match(r'<code><nowiki>(.*?)</nowiki></code>', s[i:], re.S)
            if m:
                code = re.sub(r'(\||\\#|\\\}|/)(?!$)', lambda x: x.group(1) + r'\allowbreak{}', esc(m.group(1)))
                out.append(tok(r'\nowikicode{' + code + '}')); i += m.end(); continue
            m = re.match(r'<code>(.*?)</code>', s[i:], re.S)
            if m:
                out.append(tok(r'\texttt{' + esc(m.group(1)) + '}')); i += m.end(); continue
            m = re.match(r'<nowiki>(.*?)</nowiki>', s[i:], re.S)
            if m:
                out.append(tok(r'\nowiki{' + esc(m.group(1)) + '}')); i += m.end(); continue
            m = re.match(r'<sup>(.*?)</sup>', s[i:], re.S)
            if m:
                out.append(tok(r'\textsuperscript{' + self.inline(m.group(1)) + '}')); i += m.end(); continue
            if s.startswith('{{', i):
                j = template_end(s, i)
                out.append(tok(self.template_inline(s[i:j]))); i = j; continue
            m = re.match(r'\(\[\[Literature#([^\]|]+)\|([^\]]*)\]\]\)', s[i:])
            if m and m.group(1) in self.bib and m.group(2) == '%s, %s' % self.bib[m.group(1)]:
                out.append(tok(r'\citep{' + m.group(1) + '}')); i += m.end(); continue
            if s.startswith('[[', i):
                j = link_end(s, i)
                inner = s[i + 2:j - 2]
                target, text = inner.split('|', 1) if '|' in inner else (inner, None)
                key = target[len('Literature#'):] if target.startswith('Literature#') else None
                if text is not None and target.startswith('#') and target[1:] in self.labels:
                    out.append(tok(r'\hyperref[' + target[1:] + ']{' + self.inline(text) + '}'))
                elif key in self.bib and text == '%s (%s)' % self.bib[key]:
                    out.append(tok(r'\citet{' + key + '}'))
                elif key in self.bib and text == self.bib[key][0]:
                    out.append(tok(r'\citeauthor{' + key + '}'))
                elif text is not None:
                    out.append(tok(r'\wikilink{' + esc(target) + '}{' + self.inline(text) + '}'))
                else:
                    out.append(tok(r'\wikilink{' + esc(inner) + '}{}'))
                i = j; continue
            m = re.match(r'\[(https?://[^\s\]]+)(?: ([^\]]*))?\]', s[i:])
            if m:
                out.append(tok(r'\href{' + m.group(1).replace('%', r'\%').replace('#', r'\#') + '}{'
                               + self.inline(m.group(2) or '') + '}'))
                i += m.end(); continue
            if s[i] == '<' and re.match(r'</?[a-zA-Z]', s[i:]):
                self.problems.append('HTML tag in the text, kept as text: ' + s[i:i + 40])
            out.append(s[i]); i += 1
        text = esc(''.join(out))
        text = re.sub(r"'''(.+?)'''", r'\\textbf{\1}', text)
        text = re.sub(r"''(.+?)''", r'\\emph{\1}', text)
        while '\x00' in text:
            text = re.sub('\x00(\\d+)\x00', lambda m: tokens[int(m.group(1))], text)
        return text

    def template_inline(self, call):
        name, pos, named = split_params(call[2:-2])
        if name in BADGES and not pos and not named:
            return '\\' + BADGES[name] + '{}'
        if name == 'Anchor' and pos:
            return r'\wikianchor{' + esc(pos[0]) + '}'
        self.problems.append('template kept verbatim: ' + call[:60])
        return r'\wikitemplate{' + esc(call[2:-2]) + '}'

    def scan(self, text):
        """The anchors of the page and its reference list, before the conversion."""
        t = re.sub(r'<nowiki>.*?</nowiki>', '', text, flags=re.S)
        self.labels = set(a.strip() for a in re.findall(r'\{\{Anchor\|([^}|]+)\}\}', t))
        for m in re.finditer(r'\{\{(?:Theorem|Proof) start\|[^\n]*', t):
            _, _, named = split_params(m.group(0)[2:template_end(m.group(0), 0) - 2])
            if named.get('id'):
                self.labels.add(named['id'].strip())
        self.bib = {}
        for block in re.findall(r'<!-- refs-begin:[^>]*-->\n(.*?)<!-- refs-end -->', t, re.S):
            for line in block.split('\n'):
                key = self.key_of.get(line[1:].strip()) if line.startswith('#') else None
                info = cite_info(self.lit[key]) if key else None
                if info:
                    self.bib[key] = info

    def bibliography(self, entries):
        """The entries of a reference list as a thebibliography, or None if one is not in the Literature."""
        out = [r'\begin{thebibliography}{}']
        for e in entries:
            key = self.key_of.get(e)
            if key not in self.bib:
                self.problems.append('reference not found on the Literature page, kept as a list: ' + e[:50])
                return None
            out.append(r'\bibitem[%s(%s)]{%s} ' % (esc(self.bib[key][0]), self.bib[key][1], key) + self.inline(e))
        return out + [r'\end{thebibliography}']

    def page(self, title, text, date='', site=''):
        self.scan(text)
        lines = text.split('\n')
        out, envs, lists = [], [], []
        i, n = 0, len(lines)

        def close_lists(depth=0):
            while len(lists) > depth:
                out.append('  ' * (len(lists) - 1) + ('\\end{itemize}' if lists.pop() == '*' else '\\end{enumerate}'))
        while i < n:
            line = lines[i]
            s = line.strip()
            if not re.match(r'^[*#]', s):
                close_lists()
            if not s:
                out.append(''); i += 1; continue
            # code
            m = re.match(r'^<pre(\s[^>]*)?>(.*)$', s)
            if m:
                lang = re.search(r'data-lang="([\w+#.-]+)"', m.group(1) or '')
                out.append(r'\begin{wikicode}' + ('[' + lang.group(1) + ']' if lang else ''))
                first = line[line.index('>') + 1:]
                if '</pre>' in first:
                    out.append(first.split('</pre>')[0]); i += 1
                else:
                    if first.strip():
                        out.append(first)
                    i += 1
                    while i < n and '</pre>' not in lines[i]:
                        out.append(lines[i]); i += 1
                    if i < n and lines[i].split('</pre>')[0].strip():
                        out.append(lines[i].split('</pre>')[0])
                    i += 1
                out.append(r'\end{wikicode}')
                continue
            # the reference list: a thebibliography between the two comment lines
            if s.startswith('<!-- refs-begin:') and s.endswith('-->'):
                j = i + 1
                while j < n and lines[j].strip().startswith('#'):
                    j += 1
                if j < n and lines[j].strip() == '<!-- refs-end -->':
                    entries = [l.strip()[1:].strip() for l in lines[i + 1:j]]
                    bib = self.bibliography(entries) if entries else []
                    if bib is not None:
                        out += ['%%wiki ' + lines[i]] + bib + ['%%wiki ' + lines[j]]
                        i = j + 1; continue
            # comments (refs-begin / refs-end and others): kept, invisible
            if s.startswith('<!--'):
                while True:
                    out.append('%%wiki ' + lines[i])
                    if '-->' in lines[i] or i + 1 >= n:
                        break
                    i += 1
                i += 1; continue
            # headings
            m = re.match(r'^(={2,4})\s*(.*?)\s*\1$', s)
            if m:
                htext = m.group(2)
                a = re.search(r'\s*\{\{Anchor\|([^}|]+)\}\}\s*$', htext)
                if a:
                    htext = htext[:a.start()]
                star = '*' if htext in ('References', 'Bibliography') else ''
                out.append('\\%s%s{%s}' % (SECTION_CMDS[len(m.group(1))], star, self.inline(htext))
                           + (r'\label{' + a.group(1) + '}' if a else ''))
                i += 1; continue
            # tables
            if s.startswith('{|'):
                j = i
                while j < n and not lines[j].strip().startswith('|}'):
                    j += 1
                out += self.table(lines[i:j + 1]); i = j + 1; continue
            # one-line boxes
            m = re.match(r'^<div class="([^"]+)">(.*)</div>$', s)
            if m:
                if m.group(1) == 'mod-meta':
                    out.append(r'\pagestatus{' + self.inline(m.group(2)) + '}')
                else:
                    out.append(r'\wikidiv{' + m.group(1) + '}{' + self.inline(m.group(2)) + '}')
                i += 1; continue
            # lists
            m = re.match(r'^([*#]+)\s*(.*)$', s)
            if m:
                marks = m.group(1)
                while len(lists) > len(marks) or (lists and lists[len(lists) - 1] != marks[len(lists) - 1]):
                    close_lists(len(lists) - 1)
                while len(lists) < len(marks):
                    kind = marks[len(lists)]
                    out.append('  ' * len(lists) + ('\\begin{itemize}' if kind == '*' else '\\begin{enumerate}'))
                    lists.append(kind)
                out.append('  ' * len(lists) + r'\item ' + self.inline(m.group(2)))
                i += 1; continue
            # block templates
            if s.startswith('{{'):
                j = template_end(s, 0)
                name, pos, named = split_params(s[2:j - 2])
                rest = s[j:].strip()
                done = True
                if name == 'Theorem start':
                    title_t = named.get('title', '').strip()
                    mk = re.match(r'^(%s)\s*(?:\((.*)\))?\.$' % '|'.join(STATEMENTS), title_t, re.S)
                    if not mk:
                        self.problems.append('statement title not of the form "Kind (name).": ' + title_t)
                        mk = re.match(r'^(\w+)\s*(?:\((.*)\))?\.?$', title_t, re.S)
                    env = mk.group(1).lower()
                    envs.append(env)
                    out.append('\\begin{%s}%s%s' % (env, '[' + self.inline(mk.group(2)) + ']' if mk.group(2) is not None else '',
                                                    r'\label{' + named['id'] + '}' if named.get('id') else ''))
                elif name == 'Theorem end':
                    out.append('\\end{%s}' % (envs.pop() if envs else 'theorem'))
                elif name == 'Fold start':
                    env, default = FOLD_ENVS.get(named.get('kind', 'note'), FOLD_ENVS['note'])
                    t = named.get('title', '')
                    envs.append(env)
                    out.append('\\begin{%s}%s' % (env, '' if (t == default and default) else '[' + self.inline(t) + ']'))
                elif name == 'Fold end':
                    out.append('\\end{%s}' % (envs.pop() if envs else 'fold'))
                elif name == 'Proof start':
                    envs.append('proof')
                    out.append(r'\begin{proof}' + ('[' + self.inline(named['title']) + ']' if named.get('title') else '')
                               + (r'\label{' + named['id'] + '}' if named.get('id') else ''))
                elif name == 'Proof end':
                    if envs and envs[-1] == 'proof':
                        envs.pop()
                    out.append(r'\end{proof}')
                elif name == 'Lean':
                    status = pos[0] if pos else ''
                    url = pos[1] if len(pos) > 1 else ''
                    out.append(r'\lean' + ('[' + url.replace('%', r'\%').replace('#', r'\#') + ']' if url else '') + '{' + status + '}')
                elif name == 'Media':
                    opts = ','.join('%s=%s' % (k, named[k]) for k in ('poster', 'record', 'id') if named.get(k))
                    out.append(r'\media' + ('[' + opts + ']' if opts else '') + '{' + named.get('kind', 'image') + '}{'
                               + named.get('file', '') + '}{' + self.inline(named.get('caption', '')) + '}')
                elif name == 'Discuss':
                    out.append(r'\zulip' + ('[' + esc(named['topic']) + ']' if named.get('topic') else '') + '{' + named.get('channel', '') + '}')
                elif name == 'Placeholder start':
                    m2 = re.match(r'^(.*?)\{\{Placeholder end\}\}(.*)$', rest)
                    if m2:
                        out.append(r'\placeholder{' + self.inline(m2.group(1)) + '}')
                        rest = m2.group(2).strip()
                    else:
                        self.problems.append('multi-line placeholder: ' + s[:60])
                        out.append(r'\placeholder{' + self.inline(rest) + '}'); rest = ''
                elif name.startswith('DISPLAYTITLE:'):
                    out.append('%%wiki ' + s); rest = ''
                else:
                    done = False
                if done:
                    if rest:
                        self.problems.append('text after a block template, on the same line: ' + s[:60])
                        out.append(self.inline(rest))
                    i += 1; continue
            out.append(self.inline(line))
            i += 1
        close_lists()
        body = '\n'.join(out).rstrip('\n')
        return render_document(title, body, date, site)

    def table(self, rows):
        first = rows[0].strip()
        m = re.search(r'class="levels(?:\s+([^"]*))?"', first)
        cells_rows, header, cur = [], None, None
        if m:
            out = [r'\begin{levels}' + ('[' + m.group(1).strip() + ']' if m.group(1) else '')]
            for r in rows[1:-1]:
                r = r.strip()
                if not r or r.startswith('|-'):
                    continue
                a, b = [c.strip() for c in split_cells(r[1:])][:2]
                out.append(r'\lv{' + self.inline(a) + '}{' + self.inline(b) + '}')
            return out + [r'\end{levels}']
        if 'wikitable' not in first:
            self.problems.append('table class not supported: ' + first)
        for r in rows[1:-1]:
            r = r.strip()
            if r.startswith('|-'):
                if cur is not None:
                    cells_rows.append(cur)
                cur = None; continue
            if r.startswith('!'):
                header = [c.strip() for c in r[1:].split('!!')]; continue
            if r.startswith('|'):
                cur = [c.strip() for c in split_cells(r[1:])]
        if cur is not None:
            cells_rows.append(cur)
        ncol = len(header or (cells_rows[0] if cells_rows else [1]))
        out = [r'\begin{wikitable}{%d}' % ncol]
        if header:
            out.append(r'\header{' + ' & '.join(self.inline(h) for h in header) + '}')
        for row in cells_rows:
            out.append(r'\row{' + ' & '.join(self.inline(c) for c in row) + '}')
        return out + [r'\end{wikitable}']


def split_cells(r):
    cells, cur, i, depth = [], '', 0, 0
    while i < len(r):
        if r.startswith('<math', i):
            j = r.find('</math>', i) + 7; cur += r[i:j]; i = j; continue
        if r.startswith('{{', i) or r.startswith('[[', i):
            depth += 1; cur += r[i:i + 2]; i += 2; continue
        if r.startswith('}}', i) or r.startswith(']]', i):
            depth -= 1; cur += r[i:i + 2]; i += 2; continue
        if r.startswith('||', i) and depth == 0:
            cells.append(cur); cur = ''; i += 2; continue
        cur += r[i]; i += 1
    cells.append(cur)
    return cells


# ------------------------------------------------------------------ the TeX document
PREAMBLE = r"""\documentclass[11pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage[a4paper,margin=2.5cm]{geometry}
\usepackage{amsmath,amssymb,amsthm}
\usepackage{graphicx,tabularx,listings}
\usepackage[round]{natbib}
\usepackage[hidelinks]{hyperref}
\setlength{\emergencystretch}{2em}

\newtheorem{theorem}{Theorem}
\newtheorem{proposition}[theorem]{Proposition}
\newtheorem{lemma}[theorem]{Lemma}
\newtheorem{corollary}[theorem]{Corollary}
\newtheorem{conjecture}[theorem]{Conjecture}
\newtheorem*{claim}{Claim}
\theoremstyle{definition}
\newtheorem{definition}[theorem]{Definition}
\newtheorem{example}[theorem]{Example}
\theoremstyle{remark}
\newtheorem{remark}[theorem]{Remark}

%% The commands of the wiki. This preamble is the same for every page: do not change it, and do not
%% define commands of your own (the wiki has none).
\makeatletter
% after a statement: \begin{idea}, \begin{architecture}, \begin{note}[Title] (and \begin{proof}[Title])
\newcommand{\ed@runin}[1]{\par\topsep6\p@\@plus6\p@\relax\trivlist\item[\hskip\labelsep\itshape#1\@addpunct{.}]\ignorespaces}
\newenvironment{idea}[1][Idea]{\ed@runin{#1}}{\endtrivlist\@endpefalse}
\newenvironment{architecture}[1][Proof architecture]{\ed@runin{#1}}{\endtrivlist\@endpefalse}
\newenvironment{note}[1][Note]{\ed@runin{#1}}{\endtrivlist\@endpefalse}
% text still to be written; labels of the text; the Lean banner of the statement above
\newcommand{\placeholder}[1]{\if@inlabel\else\par\noindent\fi\textit{[#1]}\@ifnextchar\end{}{\par}}
\newcommand{\ed@label}[1]{\mbox{\footnotesize[#1]}}
\newcommand{\demo}[1]{\ed@label{demo text}}
\newcommand{\heuristic}[1]{\ed@label{heuristic}}
\newcommand{\numerics}[1]{\ed@label{numerics}}
\newcommand{\published}[1]{\ed@label{published}}
\newcommand{\preprint}[1]{\ed@label{preprint, to be verified}}
\newcommand{\raw}[1]{\ed@label{raw, unchecked}}
\def\ed@formalized{formalized}\def\ed@image{image}\def\ed@video{video}\def\ed@diagram{diagram}
\newcommand{\lean}[2][]{\par{\noindent\footnotesize\def\ed@a{#2}Lean: \ifx\ed@a\ed@formalized formalized\ifx\relax#1\relax\else\
  (\href{#1}{certificate})\fi\else not yet formalized\fi.\par}}
% the two lines under the title: the page's team and status, its Zulip topic (default: the title)
\def\ed@title{}\let\ed@maketitle\maketitle\renewcommand{\maketitle}{\let\ed@title\@title\ed@maketitle}
\newcommand{\pagestatus}[1]{{\par\centering\small#1\par}}
\newcommand{\zulip}[2][]{{\par\centering\small Discuss on Zulip: \##2, topic
  ``\ifx\relax#1\relax\ed@title\else#1\fi''.\par}\medskip}
% links to other pages of the wiki, anchors, wiki code shown as text
\newcommand{\wikilink}[2]{\ifx\relax#2\relax#1\else#2\fi}
\newcommand{\wikianchor}[1]{\phantomsection\label{#1}}
\newcommand{\nowikicode}[1]{\texttt{\frenchspacing#1}}
\newcommand{\nowiki}[1]{#1}
\newcommand{\wikitemplate}[1]{\texttt{\{\{#1\}\}}}
\newcommand{\wikidiv}[2]{\par#2\par}
% pictures, videos, diagrams: shown in the online edition; an image next to this file, or in ../media, is shown here
\newcommand{\ed@picture}[1]{\begin{center}\includegraphics[width=0.8\linewidth]{#1}\end{center}}
\newcommand{\media}[4][]{\par\medskip\def\ed@a{#2}{\noindent\small\ifx\ed@a\ed@video Video\else\ifx\ed@a\ed@diagram Diagram\else
  Figure\fi\fi: \texttt{#3}, shown in the online edition.\par}\ifx\ed@a\ed@image\IfFileExists{#3}{\ed@picture{#3}}{\IfFileExists{../media/#3}{%
  \ed@picture{../media/#3}}{}}\fi{\noindent\small#4\par}\medskip}
% tables (\lv{label}{text}; \header{a & b}, \row{a & b}) and code
\newenvironment{levels}[1][]{\par\smallskip\noindent\tabularx{\linewidth}{@{}>{\bfseries\raggedright\arraybackslash}p{0.2\linewidth}X@{}}}{\endtabularx\par\smallskip}
\newcommand{\lv}[2]{#1 & #2\\[3pt]}
\newenvironment{wikitable}[1]{\par\smallskip\noindent\tabularx{\linewidth}{|*{#1}{>{\raggedright\arraybackslash}X|}}\hline}{\endtabularx\par\smallskip}
\newcommand{\header}[1]{#1\\\hline\hline}
\newcommand{\row}[1]{#1\\\hline}
\lstnewenvironment{wikicode}[1][]{\lstset{basicstyle=\ttfamily\footnotesize,breaklines=true,columns=fullflexible,
  keepspaces=true,showstringspaces=false,frame=single}\ifx\relax#1\relax\else\lstset{language=#1}\fi}{}
% the heading of the reference list is the section References of the page
\renewcommand{\bibsection}{}
% characters of the wiki's text that LaTeX does not know
\DeclareUnicodeCharacter{2192}{\ensuremath{\rightarrow}}\DeclareUnicodeCharacter{203A}{\ensuremath{\rangle}}
\DeclareUnicodeCharacter{2713}{\ensuremath{\checkmark}}\DeclareUnicodeCharacter{25CB}{\ensuremath{\circ}}
\DeclareUnicodeCharacter{2248}{\ensuremath{\approx}}\DeclareUnicodeCharacter{2264}{\ensuremath{\leq}}
\DeclareUnicodeCharacter{2265}{\ensuremath{\geq}}\DeclareUnicodeCharacter{2212}{\ensuremath{-}}
\makeatother"""


def render_document(title, body, date='', site=''):
    head = ['% !TEX TS-program = pdflatex', '% !TEX encoding = UTF-8 Unicode',
            '% {}: a page of the wiki{}{}.'.format(title, ' "%s"' % site if site else '',
                                                 ', generated from the wiki on ' + long_date(date) if date else ''),
            '% It compiles as it is with pdflatex (Overleaf, TeXShop, TeXstudio, ...); typeset twice for the citations.',
            '% To propose a change: keep the preamble and the line \\title{...}; keep only the blocks you change',
            '% (a \\section{...} with its content, or a statement or proof with its \\label{...}), change them, and post',
            '% the file in a new topic of the Zulip channel of the part. The rules: page "How to contribute" of the wiki.']
    top = [r'\title{' + esc(title) + '}', r'\author{' + (r'Wiki \emph{' + esc(site) + '}' if site else '') + '}',
           r'\date{' + long_date(date) + '}', r'\maketitle']
    return '\n'.join(head) + '\n' + PREAMBLE + '\n\n\\begin{document}\n' + '\n'.join(top) + '\n' + body + '\n\\end{document}\n'


# ------------------------------------------------------------------ TeX -> wiki
FORBIDDEN_DEF = ('newcommand', 'renewcommand', 'providecommand', 'def', 'let', 'DeclareMathOperator', 'newenvironment',
                 'renewenvironment', 'NewDocumentCommand', 'RenewDocumentCommand', 'newtheorem', 'usepackage', 'input', 'include')
DISPLAY_ENVS = {'equation*': None, 'displaymath': None, 'align*': 'aligned', 'aligned': 'aligned', 'gather*': 'gathered',
                'multline*': None}
NUMBERED_ENVS = ('equation', 'align', 'gather', 'multline', 'eqnarray', 'eqnarray*', 'flalign')


def read_group(s, i, open_='{', close='}'):
    """s[i] == open_: return (content, end index after the closing brace); escaped braces are skipped."""
    depth, j = 0, i
    while j < len(s):
        c = s[j]
        if c == '\\':
            j += 2; continue
        if c == open_:
            depth += 1
        elif c == close:
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    raise ValueError('unbalanced %s%s in: %s' % (open_, close, s[i:i + 60]))


def strip_comment(line):
    """Remove an unescaped % comment."""
    j = 0
    while j < len(line):
        if line[j] == '\\':
            j += 2; continue
        if line[j] == '%':
            return line[:j]
        j += 1
    return line


BIBITEM = re.compile(r'\\bibitem\s*(?:\[([^\]]*)\])?\s*\{([^}]*)\}')


def bibitem_refs(tex):
    """{key: (names, year)} from the labels of the \\bibitem[Names(year)]{key} of a TeX text."""
    out = {}
    for m in BIBITEM.finditer(tex):
        lab = re.match(r'^(.*)\((\d{4}[a-z]?)\)', m.group(1) or '', re.S)
        if lab:
            out[m.group(2).strip()] = (T2W().inline(lab.group(1).strip()), lab.group(2))
    return out


class T2W:
    def __init__(self, refs=None):
        self.problems = []
        self.title = None
        self.author = None
        self.refs = dict(refs or {})     # key -> (names, year): the text of the citations

    def math(self, tex):
        tex = ' '.join(tex.split())
        for cmd in ('\\nonumber', '\\notag'):
            if re.search(re.escape(cmd) + r'(?![A-Za-z])', tex):
                self.problems.append(cmd + ' in a formula: equations are not numbered or labelled on the wiki')
        for cmd, why in wikikit.TEX_ERRORS.items():
            if re.search(re.escape(cmd) + (r'(?![A-Za-z])' if cmd[-1].isalpha() else ''), tex):
                self.problems.append('%s in a formula: %s' % (cmd, why))
        return tex

    def inline(self, s):
        out, i = [], 0
        while i < len(s):
            c = s[i]
            if s.startswith('$$', i):
                j = s.find('$$', i + 2)
                out.append('<math display="block">' + self.math(s[i + 2:j]) + '</math>'); i = j + 2; continue
            if c == '$':
                j = i + 1
                while j < len(s) and not (s[j] == '$' and s[j - 1] != '\\'):
                    j += 1
                out.append('<math display="inline">' + self.math(s[i + 1:j]) + '</math>'); i = j + 1; continue
            if s.startswith(r'\[', i):
                j = s.find(r'\]', i)
                out.append('<math display="block">' + self.math(s[i + 2:j]) + '</math>'); i = j + 2; continue
            if s.startswith(r'\(', i):
                j = s.find(r'\)', i)
                out.append('<math display="inline">' + self.math(s[i + 2:j]) + '</math>'); i = j + 2; continue
            if c == '\\':
                m = re.match(r'\\([A-Za-z]+)\*?', s[i:])
                if not m:   # escaped character, or \\ and similar
                    nxt = s[i + 1:i + 2]
                    if nxt in '{}$&#_%':
                        out.append(nxt)
                    elif nxt in ',;: ':
                        out.append(' ')
                    elif nxt == '\\':
                        out.append(' ')
                    else:
                        self.problems.append('unknown command: \\' + nxt)
                    i += 2; continue
                cmd, j = m.group(1), i + m.end()

                def arg(k):
                    while k < len(s) and s[k] == ' ':
                        k += 1
                    if k < len(s) and s[k] == '{':
                        return read_group(s, k)
                    self.problems.append('\\%s without its argument' % cmd)
                    return '', k
                if cmd in ('textbf',):
                    a, j = arg(j); out.append("'''" + self.inline(a) + "'''")
                elif cmd in ('emph', 'textit'):
                    a, j = arg(j); out.append("''" + self.inline(a) + "''")
                elif cmd == 'texttt':
                    a, j = arg(j); out.append('<code>' + unesc(a) + '</code>')
                elif cmd == 'nowikicode':
                    a, j = arg(j); out.append('<code><nowiki>' + unesc(a.replace('\\allowbreak{}', '')) + '</nowiki></code>')
                elif cmd == 'nowiki':
                    a, j = arg(j); out.append('<nowiki>' + unesc(a) + '</nowiki>')
                elif cmd == 'textsuperscript':
                    a, j = arg(j); out.append('<sup>' + self.inline(a) + '</sup>')
                elif cmd == 'wikilink':
                    t, j = arg(j); x, j = arg(j)
                    out.append('[[' + unesc(t) + (('|' + self.inline(x)) if x.strip() else '') + ']]')
                elif cmd == 'hyperref':
                    if j < len(s) and s[j] == '[':
                        lab, j = read_group(s, j, '[', ']'); x, j = arg(j)
                        out.append('[[#' + lab.strip() + '|' + self.inline(x) + ']]')
                    else:
                        self.problems.append('\\hyperref without [label]: write \\hyperref[label]{text}')
                elif cmd in CITE_CMDS:
                    opt = []
                    while j < len(s) and s[j] == '[' and len(opt) < 2:
                        o, j = read_group(s, j, '[', ']'); opt.append(self.inline(o).strip())
                    keys, j = arg(j)
                    out.append(self.citation(cmd, [k.strip() for k in keys.split(',') if k.strip()], opt))
                elif cmd in IGNORED_CMDS:
                    pass
                elif cmd in ('vspace', 'hspace'):
                    _, j = arg(j)
                elif cmd == 'label':
                    a, j = arg(j)
                    self.problems.append('\\label{%s} here: only sections, statements and proofs have labels on the wiki' % a)
                elif cmd == 'href':
                    u, j = arg(j); x, j = arg(j)
                    u = u.replace(r'\%', '%').replace(r'\#', '#')
                    out.append('[' + u + (' ' + self.inline(x) if x.strip() else '') + ']')
                elif cmd == 'url':
                    u, j = arg(j); out.append('[' + u.replace(r'\%', '%').replace(r'\#', '#') + ']')
                elif cmd == 'wikianchor':
                    a, j = arg(j); out.append('{{Anchor|' + unesc(a) + '}}')
                elif cmd == 'wikitemplate':
                    a, j = arg(j); out.append('{{' + unesc(a) + '}}')
                elif cmd in BADGE_OF_CMD:
                    if j < len(s) and s[j] == '{':
                        _, j = read_group(s, j)
                    out.append('{{' + BADGE_OF_CMD[cmd] + '}}')
                elif cmd in ('textbackslash', 'textasciicircum', 'textasciitilde'):
                    if j < len(s) and s[j] == '{':
                        _, j = read_group(s, j)
                    out.append({'textbackslash': '\\', 'textasciicircum': '^', 'textasciitilde': '~'}[cmd])
                elif cmd in ('ldots', 'dots', 'textellipsis'):
                    out.append('…')
                elif cmd in ('ref', 'eqref', 'autoref', 'cref', 'Cref', 'pageref'):
                    a, j = arg(j)
                    self.problems.append('\\%s{%s}: the wiki has no numbers; write \\hyperref[%s]{text}, e.g. '
                                         '\\hyperref[%s]{the theorem above}' % (cmd, a, a, a))
                    out.append('[' + cmd + ':' + a + ']')
                elif cmd == 'footnote':
                    a, j = arg(j)
                    self.problems.append('\\footnote: the wiki has no footnotes; write the text in brackets')
                    out.append(' (' + self.inline(a) + ')')
                elif cmd in FORBIDDEN_DEF:
                    self.problems.append('\\%s: macros and packages cannot be defined in a contribution' % cmd)
                else:
                    self.problems.append('unknown command \\%s (kept as text)' % cmd)
                    out.append('\\' + cmd)
                i = j; continue
            if c == '~':
                out.append(' '); i += 1; continue
            if s.startswith('``', i):
                out.append('“'); i += 2; continue
            if s.startswith("''", i):
                out.append('”'); i += 2; continue
            if s.startswith('---', i):
                out.append('—'); i += 3; continue
            if s.startswith('--', i):
                out.append('–'); i += 2; continue
            if c == '{':
                a, j = read_group(s, i)
                out.append(self.inline(a)); i = j; continue
            if c == '}':
                self.problems.append('unbalanced } in: ' + s[max(0, i - 30):i + 10]); i += 1; continue
            out.append(c); i += 1
        return ''.join(out)

    def citation(self, cmd, keys, opt):
        """The wikitext of \\cite, \\citet, \\citep, \\citeauthor, \\citeyear (natbib, author-year)."""
        parts = []
        for k in keys:
            if k not in self.refs:
                self.problems.append('\\%s{%s}: %s is neither on the Literature page nor in the bibliography of the file; '
                                     'a new paper is added to the reference catalogue first' % (cmd, k, k))
            names, year = self.refs.get(k, (k, '?'))
            parts.append((k, names, year))
        link = lambda k, t: '[[Literature#%s|%s]]' % (k, t)
        if cmd == 'citeauthor':
            return '; '.join(link(k, n) for k, n, y in parts)
        if cmd == 'citeyear':
            return '; '.join(link(k, y) for k, n, y in parts)
        post = opt[-1] if opt else ''
        if cmd == 'citep':
            pre = opt[0] + ' ' if len(opt) == 2 and opt[0] else ''
            return '(' + pre + '; '.join(link(k, '%s, %s' % (n, y)) for k, n, y in parts) + (', ' + post if post else '') + ')'
        texts = ['%s (%s)' % (n, y) for k, n, y in parts]
        if post:
            texts[-1] = '%s (%s, %s)' % (parts[-1][1], parts[-1][2], post)
        return '; '.join(link(p[0], t) for p, t in zip(parts, texts))

    def document(self, tex):
        """The wikitext of a TeX page or proposal."""
        self.refs.update(bibitem_refs(tex))
        lines = tex.split('\n')
        if any(l.strip().startswith(r'\begin{document}') for l in lines):
            k = next(i for i, l in enumerate(lines) if l.strip().startswith(r'\begin{document}'))
            pre = lines[:k]
            lines = lines[k + 1:]
            # the preamble is not converted; a line that is not in the current one is reported
            fixed = set(PREAMBLE.split('\n'))
            extra = []
            for l in pre:
                m = re.match(r'^\s*\\(title|author|date)\s*\{', l)
                if m:
                    lines.insert(0, l)          # \title{...} in the preamble: read as in the body
                elif l.strip() and not l.lstrip().startswith('%') and l.rstrip() not in fixed:
                    extra.append(l.strip())
            if extra:
                self.problems.append('the preamble differs from the current one (an older download, or edited): '
                                     '%d line(s), e.g. %s' % (len(extra), extra[0][:60]))
        out = self.blocks(lines)
        return '\n'.join(out).strip('\n') + '\n'

    def blocks(self, lines):
        out, envs, lists, para = [], [], [], []
        item = None   # index in out of the current list item, to append continuation lines
        i, n = 0, len(lines)

        def flush():
            nonlocal para
            if para:
                text = ' '.join(x.strip() for x in para)
                out.append(self.inline(text))
                para = []

        def end_lists():
            nonlocal item
            while lists:
                lists.pop()
            item = None

        while i < n:
            raw = lines[i]
            if raw.startswith('%%wiki '):
                flush(); out.append(raw[len('%%wiki '):]); i += 1; continue
            m = re.match(r'^\s*\\begin\{wikicode\}(?:\[([^\]]*)\])?\s*$', raw)
            if m:
                flush()
                out.append('<pre' + (' data-lang="%s"' % m.group(1) if m.group(1) else '') + '>')
                i += 1
                while i < n and lines[i].strip() != r'\end{wikicode}':
                    out.append(lines[i]); i += 1
                out.append('</pre>'); i += 1; continue
            line = strip_comment(raw).rstrip()
            s = line.strip()
            if raw.strip().startswith('%') and not s:
                i += 1; continue
            if not s:
                flush()
                if lists:
                    i += 1; continue
                out.append(''); i += 1; continue
            if s in (r'\begin{document}', r'\end{document}', r'\maketitle'):
                i += 1; continue
            m = re.match(r'^\\(title|author|date|wikipage)\s*(\{.*)$', s)
            if m:
                flush()
                arg_, k = m.group(2), i
                while arg_.count('{') - arg_.count('\\{') > arg_.count('}') - arg_.count('\\}') and k + 1 < n:
                    k += 1; arg_ += ' ' + strip_comment(lines[k]).strip()
                a, _ = read_group(arg_, 0)
                if m.group(1) in ('title', 'wikipage'):
                    self.title = unesc(a) if m.group(1) == 'wikipage' else self.inline(a)
                elif m.group(1) == 'author':
                    self.author = self.inline(a).strip()
                i = k + 1; continue
            if s.startswith(r'\begin{thebibliography}'):
                flush()
                items, i = [], i + 1
                while i < n and not lines[i].strip().startswith(r'\end{thebibliography}'):
                    t = strip_comment(lines[i]).strip()
                    m = BIBITEM.match(t)
                    if m:
                        items.append(t[m.end():].strip())
                    elif t and items:
                        items[-1] += ' ' + t
                    elif t:
                        self.problems.append('in thebibliography, text before the first \\bibitem: ' + t[:50])
                    i += 1
                out += ['# ' + self.inline(x) for x in items]
                i += 1; continue
            m = re.match(r'^\\paragraph\*?(\{.*)$', s)
            if m:                                # \paragraph{Step 1.} text -> '''Step 1.''' text, a new paragraph
                flush()
                if out and out[-1].strip() and not lists:
                    out.append('')
                a, k = read_group(m.group(1), 0)
                para.append("\\textbf{" + a + "}" + m.group(1)[k:])
                i += 1; continue
            m = re.match(r'^\\pagestatus(\{.*)$', s)
            if m:
                flush(); a, _ = read_group(m.group(1), 0)
                out.append('<div class="mod-meta">' + self.inline(a) + '</div>'); i += 1; continue
            m = re.match(r'^\\zulip(?:\[([^\]]*)\])?\{([^}]*)\}$', s)
            if m:
                flush()
                out.append('{{Discuss|channel=' + m.group(2) + ('|topic=' + unesc(m.group(1)) if m.group(1) else '') + '}}')
                i += 1; continue
            m = re.match(r'^\\(section|subsection|subsubsection)\*?(\{.*)$', s)
            if m:
                flush(); end_lists()
                h, k = read_group(m.group(2), 0)
                lab = re.match(r'\s*\\label\{([^}]*)\}', m.group(2)[k:])
                level = LEVEL_OF_CMD[m.group(1)]
                eq = '=' * level
                out.append(eq + ' ' + self.inline(h) + (' {{Anchor|' + lab.group(1) + '}}' if lab else '') + ' ' + eq)
                i += 1; continue
            m = re.match(r'^\\begin\{(%s)\}(.*)$' % '|'.join(STATEMENT_ENVS), s)
            if m:
                flush(); end_lists()
                env, rest = m.group(1), m.group(2)
                name = None
                if rest.startswith('['):
                    name, k = read_group(rest, 0, '[', ']'); rest = rest[k:]
                lab = re.match(r'\s*\\label\{([^}]*)\}(.*)$', rest)
                if not lab:
                    self.problems.append('\\begin{%s} without \\label{...}: the label is the anchor of the statement' % env)
                kind = STATEMENT_ENVS[env]
                title = kind + (' (' + self.inline(name) + ')' if name is not None else '') + '.'
                out.append('{{Theorem start|id=' + (lab.group(1) if lab else '') + '|title=' + title + '}}')
                envs.append(env)
                tail = (lab.group(2) if lab else rest).strip()
                if tail:
                    para.append(tail)
                i += 1; continue
            m = re.match(r'^\\begin\{(idea|architecture|note|fold)\}(?:\[(.*)\])?\s*$', s)
            if m:
                flush(); end_lists()
                kind, default = FOLD_KIND[m.group(1)]
                t = self.inline(m.group(2)) if m.group(2) is not None else default
                if not t:
                    self.problems.append('\\begin{note} needs a title: \\begin{note}[Title]')
                out.append('{{Fold start|kind=' + kind + '|title=' + t + '}}')
                envs.append(m.group(1)); i += 1; continue
            m = re.match(r'^\\begin\{proof\}(.*)$', s)
            if m:
                flush(); end_lists()
                rest, t = m.group(1), None
                if rest.startswith('['):
                    t, k = read_group(rest, 0, '[', ']'); rest = rest[k:]
                lab = re.match(r'\s*\\label\{([^}]*)\}(.*)$', rest)
                out.append('{{Proof start' + ('|id=' + lab.group(1) if lab else '') + ('|title=' + self.inline(t) if t else '') + '}}')
                envs.append('proof')
                tail = (lab.group(2) if lab else rest).strip()
                if tail:
                    para.append(tail)
                i += 1; continue
            m = re.match(r'^\\end\{([a-z*]+)\}\s*$', s)
            if m and m.group(1) in tuple(STATEMENT_ENVS) + ('idea', 'architecture', 'note', 'fold', 'proof'):
                flush(); end_lists()
                env = m.group(1)
                if envs and envs[-1] == env:
                    envs.pop()
                else:
                    self.problems.append('\\end{%s} does not close the open environment %s' % (env, envs[-1] if envs else '(none)'))
                out.append('{{Proof end}}' if env == 'proof' else '{{Fold end}}' if env in FOLD_KIND else '{{Theorem end}}')
                i += 1; continue
            m = re.match(r'^\\lean(?:\[([^\]]*)\])?\{([^}]*)\}$', s)
            if m:
                flush()
                url = (m.group(1) or '').replace(r'\%', '%').replace(r'\#', '#')
                out.append('{{Lean' + ('|' + m.group(2) if m.group(2) else '') + ('|' + url if url else '') + '}}')
                i += 1; continue
            m = re.match(r'^\\media(?:\[([^\]]*)\])?\{([^}]*)\}\{([^}]*)\}(\{.*)$', s)
            if m:
                flush()
                cap, _ = read_group(m.group(4), 0)
                opts = dict(kv.split('=', 1) for kv in (m.group(1) or '').split(',') if '=' in kv)
                parts = ['kind=' + m.group(2), 'file=' + m.group(3)]
                if opts.get('poster'):
                    parts.append('poster=' + opts['poster'])
                if cap.strip():
                    parts.append('caption=' + self.inline(cap))
                for k in ('record', 'id'):
                    if opts.get(k):
                        parts.append(k + '=' + opts[k])
                out.append('{{Media|' + '|'.join(parts) + '}}')
                i += 1; continue
            m = re.match(r'^\\placeholder(\{.*)$', s)
            if m:
                flush()
                a, _ = read_group(m.group(1), 0)
                out.append('{{Placeholder start}}' + self.inline(a) + '{{Placeholder end}}')
                i += 1; continue
            m = re.match(r'^\\wikidiv\{([^}]*)\}(\{.*)$', s)
            if m:
                flush()
                a, _ = read_group(m.group(2), 0)
                out.append('<div class="' + m.group(1) + '">' + self.inline(a) + '</div>')
                i += 1; continue
            m = re.match(r'^\\begin\{(itemize|enumerate)\}', s)
            if m:
                flush()
                lists.append('*' if m.group(1) == 'itemize' else '#'); i += 1; continue
            m = re.match(r'^\\end\{(itemize|enumerate)\}', s)
            if m:
                flush()
                if lists:
                    lists.pop()
                item = None; i += 1; continue
            m = re.match(r'^\\item\s*(.*)$', s)
            if m and lists:
                flush()
                out.append(''.join(lists) + ' ' + self.inline(m.group(1)))
                item = len(out) - 1; i += 1; continue
            m = re.match(r'^\\begin\{levels\}(?:\[([^\]]*)\])?', s)
            if m:
                flush()
                rows = []
                i += 1
                while i < n and not lines[i].strip().startswith(r'\end{levels}'):
                    t = strip_comment(lines[i]).strip()
                    if t.startswith(r'\lv'):
                        a, k = read_group(t, 3)
                        b, _ = read_group(t, k)
                        rows.append('| ' + self.inline(a) + ' || ' + self.inline(b))
                    elif t:
                        self.problems.append('in levels, only \\lv{..}{..} lines: ' + t[:50])
                    i += 1
                i += 1
                out.append('{| class="levels' + (' ' + m.group(1) if m.group(1) else '') + '"')
                out.append('\n|-\n'.join(rows))
                out.append('|}')
                continue
            m = re.match(r'^\\begin\{wikitable\}', s)
            if m:
                flush()
                out.append('{| class="wikitable"')
                first_row = True
                i += 1
                while i < n and not lines[i].strip().startswith(r'\end{wikitable}'):
                    t = strip_comment(lines[i]).strip()
                    mm = re.match(r'^\\(header|row)(\{.*)$', t)
                    if mm:
                        a, _ = read_group(mm.group(2), 0)
                        cells = [self.inline(c.strip()) for c in split_amp(a)]
                        if mm.group(1) == 'header':
                            out.append('! ' + ' !! '.join(cells))
                        else:
                            out.append('|-')
                            out.append('| ' + ' || '.join(cells))
                        first_row = False
                    elif t:
                        self.problems.append('in wikitable, only \\header{..} and \\row{..} lines: ' + t[:50])
                    i += 1
                i += 1
                out.append('|}')
                continue
            # displayed formulas on their own lines
            m = re.match(r'^\\begin\{([a-zA-Z]+\*?)\}', s)
            if m and (m.group(1) in DISPLAY_ENVS or m.group(1) in NUMBERED_ENVS):
                flush()
                env = m.group(1)
                if env in NUMBERED_ENVS:
                    self.problems.append('numbered equation (%s): use \\[ ... \\] or %s*' % (env, env.rstrip('*')))
                body = [s[m.end():]]
                i += 1
                while i < n and (r'\end{' + env + '}') not in lines[i]:
                    body.append(strip_comment(lines[i])); i += 1
                if i < n:
                    body.append(strip_comment(lines[i]).split(r'\end{' + env + '}')[0])
                i += 1
                tex = ' '.join(x.strip() for x in body if x.strip())
                inner = DISPLAY_ENVS.get(env) or ('aligned' if env.rstrip('*') in ('align', 'eqnarray', 'flalign') else None)
                if inner == 'gathered':
                    self.problems.append('gather* is rejected by the wiki: use \\[ \\begin{matrix} ... \\end{matrix} \\]')
                if inner:
                    tex = '\\begin{%s}%s\\end{%s}' % (inner, tex, inner)
                out.append('<math display="block">' + self.math(tex) + '</math>')
                continue
            if s.startswith(r'\[') and r'\]' not in s:
                flush()
                body = [s[2:]]
                i += 1
                while i < n and r'\]' not in lines[i]:
                    body.append(strip_comment(lines[i])); i += 1
                if i < n:
                    body.append(strip_comment(lines[i]).split(r'\]')[0])
                i += 1
                out.append('<math display="block">' + self.math(' '.join(x.strip() for x in body if x.strip())) + '</math>')
                continue
            if s.startswith(r'\[') and s.endswith(r'\]'):
                flush()
                out.append('<math display="block">' + self.math(s[2:-2]) + '</math>')
                i += 1; continue
            m = re.match(r'^\\begin\{([^}]*)\}', s)
            if m:
                self.problems.append('environment not available on the wiki: ' + m.group(1))
            if lists and item is not None and not para:
                out[item] += ' ' + self.inline(s)
                i += 1; continue
            para.append(s)
            i += 1
        flush()
        if envs:
            self.problems.append('environments not closed: ' + ', '.join(envs))
        return out


def split_amp(s):
    cells, cur, depth, i = [], '', 0, 0
    while i < len(s):
        c = s[i]
        if c == '\\':
            cur += s[i:i + 2]; i += 2; continue
        if c == '$':
            j = i + 1
            while j < len(s) and not (s[j] == '$' and s[j - 1] != '\\'):
                j += 1
            cur += s[i:j + 1]; i = j + 1; continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
        if c == '&' and depth == 0:
            cells.append(cur); cur = ''; i += 1; continue
        cur += c; i += 1
    cells.append(cur)
    return cells


# ------------------------------------------------------------------ pages and proposals
def articles(src):
    """{title: wikitext} of the articles, from a pages directory or an XML export."""
    if os.path.isfile(src) and src.endswith('.xml'):
        root = ET.parse(src).getroot()
        ns = {'mw': root.tag.split('}')[0].strip('{')}
        pages = {p.find('mw:title', ns).text: (p.find('mw:revision/mw:text', ns).text or '') for p in root.findall('mw:page', ns)}
    else:
        pages = {t: v[3] for t, v in wikikit.read_pages(src).items()}
    return {t: x for t, x in pages.items() if ':' not in t.split('/')[0] and not re.match(r'#REDIRECT', x, re.I)}


def normalize(text):
    """Adjacent text lines form one paragraph (MediaWiki joins them); join them, as the TeX does."""
    out = []
    block = re.compile(r'^(\{\{|<div|<pre|</pre|<!--|\{\||\||!|=|\*|#|<math display="block">)')
    in_pre = False
    for line in text.rstrip('\n').split('\n'):
        if line.startswith('<pre'):
            in_pre = True
        if not in_pre and out and line.strip() and out[-1].strip() and not block.match(line.strip()) \
                and not block.match(out[-1].strip()):
            out[-1] = out[-1].rstrip() + ' ' + line.strip()
        else:
            out.append(line)
        if line.startswith('</pre'):
            in_pre = False
    return '\n'.join(out).rstrip('\n') + '\n'


def units(text):
    """The blocks of a page that a proposal can replace: {key: (first line, end line)}; keys are
    'section:<title>' and 'label:<id>'."""
    lines = text.split('\n')
    heads = []
    for k, line in enumerate(lines):
        m = re.match(r'^(={2,4})\s*(.*?)\s*\1\s*$', line.strip())
        if m:
            heads.append((k, len(m.group(1)), wikikit.plain(m.group(2))))
    out = {}
    # the lead: after the first lines (status line, discussion line), up to the first heading
    a = 0
    while a < len(lines) and (not lines[a].strip() or lines[a].startswith('<div class="mod-meta">')
                              or lines[a].startswith('{{Discuss') or lines[a].startswith('{{DISPLAYTITLE')):
        a += 1
    b = heads[0][0] if heads else len(lines)
    while b > a and not lines[b - 1].strip():
        b -= 1
    out['lead'] = (a, max(a, b))
    for idx, (k, lev, t) in enumerate(heads):
        end = next((j for (j, l2, _) in heads[idx + 1:] if l2 <= lev), len(lines))
        while end - 1 > k and not lines[end - 1].strip():
            end -= 1
        out['section:' + t] = (k, end)
    for k, line in enumerate(lines):
        m = re.match(r'^\{\{(Theorem start|Proof start)\|(.*)$', line.strip())
        if not m:
            continue
        idm = re.search(r'(?:^|\|)id=([^|}]+)', m.group(2))
        if not idm:
            continue
        kind = m.group(1).split()[0]
        depth, j = 0, k
        while j < len(lines):
            t = lines[j].strip()
            if t.startswith('{{%s start' % kind):
                depth += 1
            if t.startswith('{{%s end}}' % kind):
                depth -= 1
                if depth == 0:
                    break
            j += 1
        out['label:' + idm.group(1).strip()] = (k, j + 1)
    return out


def proposal_blocks(tex):
    """Split the body of a proposal into blocks: (key, after, tex lines)."""
    lines = tex.split('\n')
    if any(l.strip().startswith(r'\begin{document}') for l in lines):
        k = next(i for i, l in enumerate(lines) if l.strip().startswith(r'\begin{document}'))
        lines = lines[k + 1:]
    lines = [l for l in lines if l.strip() != r'\end{document}']
    blocks, i, n, after, stray, lead = [], 0, len(lines), None, [], []
    while i < n:
        s = lines[i].strip()
        m = re.match(r'^%%\s*after:\s*(.+)$', s)
        if m:
            after = m.group(1).strip(); i += 1; continue
        if not s or (s.startswith('%') and not s.startswith('%%wiki')) or s == r'\maketitle' \
                or re.match(r'^\\(wikipage|title|author|date|pagestatus|zulip)\b', s):
            i += 1; continue
        if s.startswith(r'\begin{thebibliography}'):     # generated from the catalogue: not part of a proposal
            while i < n and not lines[i].strip().startswith(r'\end{thebibliography}'):
                i += 1
            i += 1; continue
        m = re.match(r'^\\(section|subsection|subsubsection)\*?\{', s)
        if m:
            level = LEVEL_OF_CMD[m.group(1)]
            h, _ = read_group(s, s.index('{'))
            j = i + 1
            while j < n:
                mm = re.match(r'^\\(section|subsection|subsubsection)\*?\{', lines[j].strip())
                if mm and LEVEL_OF_CMD[mm.group(1)] <= level:
                    break
                if re.match(r'^%%\s*after:', lines[j].strip()):
                    break
                j += 1
            key = 'section:' + wikikit.plain(T2W().inline(h))
            blocks.append((key, after, lines[i:j])); after = None; i = j; continue
        m = re.match(r'^\\begin\{(%s|proof)\}' % '|'.join(STATEMENT_ENVS), s)
        if m:
            env = m.group(1)
            lab = re.search(r'\\label\{([^}]*)\}', s)
            depth, j = 0, i
            while j < n:
                t = lines[j].strip()
                depth += len(re.findall(r'\\begin\{%s\}' % re.escape(env), t)) - len(re.findall(r'\\end\{%s\}' % re.escape(env), t))
                if depth == 0:
                    break
                j += 1
            blocks.append(('label:' + (lab.group(1) if lab else '?'), after, lines[i:j + 1])); after = None; i = j + 1; continue
        if not blocks and after is None:
            lead.append(lines[i])
        else:
            stray.append(s)
        i += 1
    if lead:
        blocks.insert(0, ('lead', None, lead))
    return blocks, stray


def refs_of(lit):
    """{key: (names, year)} of the entries of the Literature page."""
    return {k: cite_info(e) for k, e in lit.items() if cite_info(e)}


def cited(text):
    """The keys of the papers that a wikitext cites, in order (not counting code shown as text)."""
    text = re.sub(r'<nowiki>.*?</nowiki>', '', text, flags=re.S)
    return list(dict.fromkeys(k.strip() for k in re.findall(r'\[\[Literature#([^\]|]+)', text)))


def update_reference_list(text, old, lit):
    """Add to the page's reference list the papers that the change cites for the first time, and write the list
    again from the Literature page, in the order of refs_from_catalog.py. Returns (text, added keys, problems)."""
    first = [k for k in cited(text) if k not in cited(old)]
    problems = ['%s is cited but is not on the Literature page' % k for k in first if k not in lit]
    m = re.search(r'<!-- refs-begin:([^>]*?)-->\n(.*?)<!-- refs-end -->', text, re.S)
    if not m:
        if first:
            problems.append('the page has no reference list (lines <!-- refs-begin: --> and <!-- refs-end -->) for %s'
                            % ', '.join(first))
        return text, [], problems
    keys = m.group(1).split()
    new = [k for k in first if k not in keys and k in lit]
    if not new:
        return text, [], problems
    keys += new
    body = ''.join('# ' + lit[k] + '\n' for k in sorted((k for k in keys if k in lit), key=lambda k: ref_order(lit[k], k)))
    return text[:m.start()] + '<!-- refs-begin: %s -->\n%s<!-- refs-end -->' % (' '.join(keys), body) + text[m.end():], new, problems


def cmd_apply(pdir, tex_path, write=False):
    tex = open(tex_path, encoding='utf-8').read()
    pages = wikikit.read_pages(pdir)
    lit = literature({t: v[3] for t, v in pages.items()})
    refs = refs_of(lit)
    conv = T2W(refs)
    conv.document(tex)            # reads \title and reports what cannot be converted
    refs.update(conv.refs)
    title = conv.title
    if not title or title not in pages:
        sys.exit('the proposal must name an existing page with \\title{...} (found: %r)' % title)
    old = pages[title][3]
    lines = old.split('\n')
    blocks, stray = proposal_blocks(tex)
    report = {'page': title, 'author': conv.author if conv.author and not conv.author.startswith('Wiki') else '',
              'replaced': [], 'inserted': [], 'unchanged': [], 'not applied': [],
              'problems': list(dict.fromkeys(conv.problems))}
    if stray:
        report['problems'].append('text outside any block (a proposal contains only \\section blocks or labelled environments): '
                                  + ' | '.join(x[:40] for x in stray[:3]))
    # replace from the bottom of the page up, so that line numbers stay valid
    edits = []
    for key, after, blines in blocks:
        if key in ('section:References', 'section:Bibliography'):
            report['not applied'].append(key + ' (generated from the reference catalogue; new citations are added to it)')
            continue
        new = T2W(refs)
        wiki = '\n'.join(new.blocks(blines)).split('\n')
        while wiki and not wiki[-1].strip():
            wiki.pop()
        while wiki and not wiki[0].strip():
            wiki.pop(0)
        report['problems'] += new.problems
        u = units('\n'.join(lines))
        if after:
            target = u.get('section:' + after) or u.get('label:' + after)
            if not target:
                report['problems'].append('"after: %s" names no block of the page' % after); continue
            edits.append((target[1], target[1], [''] + wiki, key, 'inserted'))
        elif key in u:
            a, b = u[key]
            if [x.rstrip() for x in lines[a:b]] == [x.rstrip() for x in wiki]:
                report['unchanged'].append(key); continue
            edits.append((a, b, wiki, key, 'replaced'))
        else:
            report['problems'].append('%s: no block of this name on the page (to add a block, put "%%%% after: <title or label>" before it)' % key)
    for a, b, wiki, key, what in sorted(edits, key=lambda e: -e[0]):
        lines[a:b] = wiki
        report[what].append(key)
    new_text, added, probs = update_reference_list('\n'.join(lines), old, lit)
    ids = re.findall(r'\{\{(?:Theorem|Proof) start\|(?:[^\n]*?\|)?id=([^|}\n]+)', new_text)
    probs += ['the label %s appears twice after the change (a statement placed after a section of the proposal '
              'belongs to that section: send it before the section, or as a proposal of its own)' % x
              for x in sorted(set(i for i in ids if ids.count(i) > 1))]
    report['problems'] = list(dict.fromkeys(report['problems'] + probs))
    links = lambda t: set(x.strip() for x in re.findall(r'\[\[([^\]|]+)', t))
    exts = lambda t: set(re.findall(r'\[(https?://[^\s\]]+)', t))
    added_links = sorted(links(new_text) - links(old))
    report['new citations'] = [l for l in added_links if l.startswith('Literature#')]
    report['references added'] = added
    report['new links'] = [l for l in added_links if not l.startswith('Literature#')]
    report['new external links'] = sorted(exts(new_text) - exts(old))
    report['removed links'] = sorted(links(old) - links(new_text))
    diff = list(difflib.unified_diff(old.split('\n'), new_text.split('\n'), 'current: ' + title, 'proposed', n=1, lineterm=''))
    for k, v in report.items():
        if v:
            print('%-20s %s' % (k + ':', v if isinstance(v, str) else '\n'.join([v[0]] + ['                     ' + x for x in v[1:]])))
    print('\n'.join(diff) if diff else '(no change)')
    if write and diff:
        path = os.path.join(pdir, wikikit.file_for(title, 'wikitext'))
        open(path, 'w', encoding='utf-8', newline='\n').write(new_text.rstrip('\n') + '\n')
        print('written:', path)
    return 1 if report['problems'] else 0


def cmd_page2tex(src, out, date='', site=''):
    os.makedirs(out, exist_ok=True)
    for f in os.listdir(out):
        if f.endswith('.tex'):
            os.remove(os.path.join(out, f))
    problems = []
    arts = articles(src)
    lit = literature(arts)
    for title, text in sorted(arts.items()):
        conv = W2T(lit)
        tex = conv.page(title, text, date, site)
        problems += ['%s: %s' % (title, p) for p in conv.problems]
        open(os.path.join(out, ('index' if title == 'Overview' else slug(title)) + '.tex'), 'w', encoding='utf-8').write(tex)
    print('%d TeX sources -> %s' % (len(arts), out))
    for p in problems:
        print('note  ' + p)
    return 0


def sidebar_order(src):
    """[(part, [page titles])] from MediaWiki:Sidebar (pages dir or XML)."""
    if os.path.isfile(src) and src.endswith('.xml'):
        root = ET.parse(src).getroot()
        ns = {'mw': root.tag.split('}')[0].strip('{')}
        text = next(((p.find('mw:revision/mw:text', ns).text or '') for p in root.findall('mw:page', ns)
                     if p.find('mw:title', ns).text == 'MediaWiki:Sidebar'), '')
    else:
        text = wikikit.read_pages(src).get('MediaWiki:Sidebar', (0, 0, 0, ''))[3]
    out = []
    for line in text.split('\n'):
        if line.startswith('**') and out:
            out[-1][1].append(line[2:].split('|')[0].strip())
        elif line.startswith('*') and line[1:].strip() not in ('SEARCH', 'TOOLBOX', 'LANGUAGES'):
            out.append((line[1:].strip(), []))
    return [(p, t) for p, t in out if t]


def cmd_book(src, texdir, out, site='', date=''):
    """All the pages in one document (main.tex): a part per menu section with several pages, a section per page,
    one reference list at the end. Written from the TeX sources of the pages (page2tex); for reading and
    compiling the whole wiki, not for proposals (those use the page files)."""
    demote = [(r'\subsubsection', r'\paragraph'), (r'\subsection', r'\subsubsection'), (r'\section', r'\subsection')]
    body, bib, seen = [], [], set()
    for part, titles in sidebar_order(src):
        several = len(titles) > 1 or titles[0] != part
        if several:
            body.append('\\part{' + esc(part) + '}')
        for title in titles:
            f = os.path.join(texdir, ('index' if title == 'Overview' else slug(title)) + '.tex')
            if not os.path.exists(f):
                continue
            tex = open(f, encoding='utf-8').read()
            page = tex.split('\\maketitle\n', 1)[1].rsplit('\\end{document}', 1)[0].rstrip('\n')
            m = re.search(r'\\begin\{thebibliography\}\{[^}]*\}\n(.*?)\\end\{thebibliography\}\n?', page, re.S)
            if m:
                for item in m.group(1).strip('\n').split('\n'):
                    k = BIBITEM.match(item)
                    if k and k.group(2) not in seen:
                        seen.add(k.group(2)); bib.append(item)
                page = page[:m.start()] + page[m.end():]
            page = re.sub(r'\\section\*\{References\}\n(%%wiki [^\n]*\n?)*', '', page)
            lines = []
            for line in page.split('\n'):
                for a, b in demote:
                    if line.startswith(a + '{') or line.startswith(a + '*{'):
                        line = b + line[len(a):]; break
                lines.append(re.sub(r'^\\zulip\{', r'\\zulip[' + esc(title).replace('\\', '\\\\') + ']{', line))
            body.append('\\section{' + esc(title) + '}\\label{page-' + slug(title) + '}')
            body += lines
            body.append('')
    if bib:
        body += ['\\section*{References}', r'\begin{thebibliography}{}'] + bib + [r'\end{thebibliography}']
    head = ['% !TEX TS-program = pdflatex', '% !TEX encoding = UTF-8 Unicode',
            '% The whole wiki{} in one document{}: a section per page, in the order of the menu.'.format(
                ' "%s"' % site if site else '', ', generated on ' + long_date(date) if date else ''),
            '% It compiles as it is with pdflatex; typeset twice. The other .tex files of the project are the pages, one',
            '% file each: a proposal is made on the file of its page (see "How to contribute").']
    doc = ('\n'.join(head) + '\n' + PREAMBLE + '\n\n\\begin{document}\n\\title{' + esc(site or 'Wiki') + '}\n\\author{}\n\\date{'
           + long_date(date) + '}\n\\maketitle\n\\tableofcontents\n\n' + '\n'.join(body).rstrip('\n') + '\n\\end{document}\n')
    open(out, 'w', encoding='utf-8').write(doc)
    print('book: %d lines -> %s' % (doc.count('\n'), out))
    return 0



def cmd_roundtrip(pdir):
    bad = 0
    arts = articles(pdir)
    lit = literature(arts)
    for title, text in sorted(arts.items()):
        w = W2T(lit)
        tex = w.page(title, text, '2026-01-01', 'Test')
        t = T2W()
        back = t.document(tex)
        a, b = normalize(text), normalize(back)
        ok = a == b and t.title == title
        if not ok:
            bad += 1
            print('MISMATCH', title)
            for d in list(difflib.unified_diff(a.split('\n'), b.split('\n'), 'wiki', 'via TeX', n=0, lineterm=''))[:12]:
                print('   ', d)
        probs = w.problems + t.problems
        print('%-32s %s%s' % (title, 'ok' if ok else 'DIFFERS', ('   notes: ' + '; '.join(probs)) if probs else ''))
    return 1 if bad else 0


def cmd_check(path, pdir=''):
    t = T2W(refs_of(literature({k: v[3] for k, v in wikikit.read_pages(pdir).items()})) if pdir else None)
    t.document(open(path, encoding='utf-8').read())
    for p in dict.fromkeys(t.problems):
        print('problem  ' + p)
    print('%s: %d problem(s)' % (path, len(set(t.problems))))
    return 1 if t.problems else 0


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 2
    cmd, args = argv[1], argv[2:]
    opt = lambda k, d='': args[args.index(k) + 1] if k in args else d
    if cmd == 'page2tex':
        return cmd_page2tex(args[0], args[1], opt('--date', datetime.date.today().isoformat()), opt('--site'))
    if cmd == 'tex2page':
        t = T2W(); sys.stdout.write(t.document(open(args[0], encoding='utf-8').read()))
        for p in dict.fromkeys(t.problems):
            print('problem  ' + p, file=sys.stderr)
        return 1 if t.problems else 0
    if cmd == 'apply':
        return cmd_apply(args[0], args[1], '--write' in args)
    if cmd == 'check':
        return cmd_check(args[0], opt('--pages'))
    if cmd == 'book':
        return cmd_book(args[0], args[1], args[2], opt('--site'), opt('--date', datetime.date.today().isoformat()))
    if cmd == 'roundtrip':
        return cmd_roundtrip(args[0])
    print(__doc__); return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))

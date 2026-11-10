#!/usr/bin/env python3
"""refs_from_catalog.py: the wiki's references from references/catalog.json (one source of truth).

  literature <catalog.json> <pages-dir>     writes Main/Literature.wiki: one line per paper, grouped by
                                            theme (topic_group, and topic_subgroup as folded boxes; see SECTIONS),
                                            newest first (arXiv submission, else publication date), each with an
                                            anchor {{Anchor|Key}} for links [[Literature#Key|...]]
  apply <catalog.json> <pages-dir>          in every page, regenerates the numbered list between the lines
                                            <!-- refs-begin: Key1 Key2 ... --> and <!-- refs-end -->
                                            (alphabetical order of the first author, the kit's format)
  entry <catalog.json> Key [Key ...]        prints the entries

Entry format (wiki kit §3.5):
  A. Author and B. Author, ''Title'', Journal '''volume''' (year), pages, [https://arxiv.org/abs/ID arXiv:ID].
Part of the enhanced-dissipation wiki (Nov 2026); drafted by Claude (AI).
"""
import json, os, re, sys, unicodedata

MULTIWORD_SURNAMES = ('Coti Zelati', 'Del Zotto', 'De Lellis', 'Van Den', 'Punshon-Smith', 'Thomson (Lord Kelvin)')


def split_name(name):
    name = name.strip()
    for s in MULTIWORD_SURNAMES:
        if name.endswith(' ' + s):
            return name[:-len(s) - 1], s
    parts = name.split()
    return ' '.join(parts[:-1]), parts[-1]


def short_author(name):
    given, surname = split_name(name)
    initials = ' '.join(p[0] + '.' if not p.endswith('.') else p for p in given.split())
    return (initials + ' ' + surname).strip()


def authors_text(authors):
    a = [short_author(x) for x in authors]
    if len(a) == 1:
        return a[0]
    return ', '.join(a[:-1]) + ' and ' + a[-1]


def surname_key(name):
    s = split_name(name)[1]
    return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()


def journal_text(rec):
    """'Journal volume (year), pages' from the catalogue's journal string."""
    j = (rec.get('journal') or '').strip()
    year = rec.get('publication_year') or rec.get('preprint_year')
    if not j:
        return None
    j = j.replace('(%d)' % year, '').replace('  ', ' ').strip().rstrip(',')
    # "Journal 224(3), 1161–1204" | "Journal 64, 507–518" | "Journal 22, no. 3, 301-352" | "Journal 248, Article 84"
    m = re.match(r'^(?P<j>.+?)\s+(?P<v>\d+)\s*(?:\((?P<i>[^)]*)\))?\s*,?\s*(?P<rest>.*)$', j)
    if not m:
        return j + ' (%s)' % year
    name, vol, rest = m.group('j').strip(), m.group('v'), m.group('rest').strip().strip(',').strip()
    rest = re.sub(r'^no\.\s*\d+,\s*', '', rest)
    rest = rest.replace('-', '–') if re.match(r'^\d+-\d+$', rest) else rest
    out = "%s '''%s''' (%s)" % (name, vol, year)
    if rest:
        out += ', ' + rest
    return out


def entry(rec, with_anchor=False):
    title = rec['title'].rstrip('.')
    parts = [authors_text(rec['authors']), "''%s''" % title]
    jt = journal_text(rec)
    if jt:
        parts.append(jt)
    else:
        parts.append('preprint (%s)' % (rec.get('preprint_year') or rec.get('publication_year')))
    if rec.get('arxiv'):
        parts.append('[https://arxiv.org/abs/%s arXiv:%s]' % (rec['arxiv'], rec['arxiv']))
    elif rec.get('doi'):
        parts.append('[https://doi.org/%s doi:%s]' % (rec['doi'], rec['doi']))
    text = ', '.join(parts) + '.'
    if with_anchor:
        text = '{{Anchor|%s}} ' % rec['key'] + text
    return text


def load(path):
    recs = json.load(open(path, encoding='utf-8'))['records']
    return {r['key']: r for r in recs}, recs


def sort_keys(recs, keys):
    return sorted(keys, key=lambda k: (surname_key(recs[k]['authors'][0]), recs[k].get('publication_year') or 0, k))


# The themes of the Literature page (10 November 2026), in order; a theme with sub-themes shows each of them as a folded
# box. Every record has topic_group (the theme) and, in a theme with sub-themes, topic_subgroup.
SECTIONS = [
    ('Reviews', []),
    ('Deterministic enhanced dissipation', ['Shear, radial and other symmetric flows', 'Other smooth flows', 'Rough velocity fields',
                                            'General criteria and limits']),
    ('Stochastic enhanced dissipation', ['Random velocity fields', 'Transport noise']),
    ('Deterministic mixing', []),
    ('Stochastic mixing', []),
]


def date_key(rec):
    """Newest first: the date of the arXiv submission, read from the identifier (new style 2308.00358, old style
    math/0509663), otherwise the publication date (field date, YYYY-MM, or publication_year; an unknown month comes after
    the papers of the same year)."""
    a = (rec.get('arxiv') or '').strip()
    m = re.match(r'^(\d{2})(\d{2})\.(\d{4,5})', a)
    if m:
        return (2000 + int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r'^[a-z-]+(?:\.[A-Za-z-]+)?/(\d{2})(\d{2})(\d{3})', a)
    if m:
        y = int(m.group(1))
        return ((1900 if y > 90 else 2000) + y, int(m.group(2)), int(m.group(3)))
    d = re.match(r'^(\d{4})(?:-(\d{2}))?', str(rec.get('date') or rec.get('publication_year') or rec.get('preprint_year') or 0))
    return (int(d.group(1)), int(d.group(2) or 0), 0) if d else (0, 0, 0)


def cmd_literature(cat, pdir):
    recs, order = load(cat)
    data = json.load(open(cat, encoding='utf-8'))
    checked = data.get('checked_on') or 'date not recorded'
    known = {s: set(subs) for s, subs in SECTIONS}
    place = {}
    for r in order:
        s, sub = r.get('topic_group'), r.get('topic_subgroup') or None
        if s not in known or (known[s] and sub not in known[s]) or (not known[s] and sub):
            sys.exit('%s: theme %r / %r is not one of the themes of the Literature page (SECTIONS)' % (r['key'], s, sub))
        place.setdefault((s, sub), []).append(r['key'])
    newest = lambda keys: sorted(keys, key=lambda k: (date_key(recs[k]), k), reverse=True)
    DISCUSS_TEMPLATE = os.path.exists(os.path.join(pdir, 'Template', 'Discuss.wiki'))
    L = ['<div class="mod-meta">Contributors: to be named · Status: generated from the reference catalogue (references/catalog.json, checked %s)</div>' % checked,
         '{{Discuss|channel=contributing}}' if DISCUSS_TEMPLATE else '<div class="discuss-line">Discuss or propose a change: [[Talk:Literature|talk page]]</div>', '',
         'The papers of the reference catalogue, one line each, grouped by theme; in each theme the newest come first, by the date of their arXiv submission or, without one, of their publication. Each paper is listed once, under its main theme; a page cites what it needs, and its own list of references contains only those papers. This page is generated by a script from the catalogue; a new paper usually arrives with the proposal that cites it, and an entry is corrected by a proposal on the talk page of this page (see [[How to contribute#The TeX format|How to contribute]]); the catalogue is updated first. Pages cite these entries by their key, for instance [[Literature#BedrossianCotiZelati2017|Bedrossian and Coti Zelati (2017)]]. The list is a working bibliography, not a survey of the field.', '']
    n = 0
    for s, subs in SECTIONS:
        if not any(place.get((s, x)) for x in (subs or [None])):
            continue
        L.append('== %s ==' % s)
        for sub in (subs or [None]):
            keys = place.get((s, sub), [])
            if not keys:
                continue
            if sub:
                L.append('{{Fold start|kind=note|title=%s}}' % sub)
            L += ['* ' + entry(recs[k], with_anchor=True) for k in newest(keys)]
            if sub:
                L.append('{{Fold end}}')
            n += len(keys)
        L.append('')
    path = os.path.join(pdir, 'Main', 'Literature.wiki')
    open(path, 'w', encoding='utf-8', newline='\n').write('\n'.join(L).rstrip() + '\n')
    print('%d entries -> %s' % (n, path))


def cmd_apply(cat, pdir):
    recs, _ = load(cat)
    n = 0
    for root, _, files in os.walk(pdir):
        for f in files:
            if not f.endswith('.wiki'):
                continue
            p = os.path.join(root, f)
            t = open(p, encoding='utf-8').read()
            def repl(m):
                keys = m.group(1).split()
                missing = [k for k in keys if k not in recs]
                if missing:
                    sys.exit('%s: unknown keys %s' % (p, missing))
                body = '\n'.join('# ' + entry(recs[k]) for k in sort_keys(recs, keys))
                return '<!-- refs-begin: %s -->\n%s\n<!-- refs-end -->' % (' '.join(keys), body)
            t2, c = re.subn(r'<!-- refs-begin: ([^>]*?) -->\n.*?<!-- refs-end -->', repl, t, flags=re.S)
            if c:
                open(p, 'w', encoding='utf-8', newline='\n').write(t2)
                n += 1
    print('%d pages updated' % n)


def main(argv):
    if len(argv) < 3:
        print(__doc__); return 2
    cmd, cat = argv[1], argv[2]
    if cmd == 'literature':
        cmd_literature(cat, argv[3])
    elif cmd == 'apply':
        cmd_apply(cat, argv[3])
    elif cmd == 'entry':
        recs, _ = load(cat)
        for k in argv[3:]:
            print(entry(recs[k]))
    else:
        print(__doc__); return 2
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))

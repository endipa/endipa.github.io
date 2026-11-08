#!/usr/bin/env python3
"""prepare-app-preview.py: make the built site publishable as a private page in the Claude app (Artifact tool).

Usage: python3 prepare-app-preview.py <_book dir> <out dir> [--title "Name of the wiki"]

The Artifact tool reserves index.html for the page it publishes, and wraps that page in its own skeleton,
so a Quarto index cannot be the published page. This script copies the built site to <out dir>, renames
index.html to overview.html, rewrites the links to it (not those into wiki-preview/, whose own index.html
stays), drops files that only Netlify uses (_headers, robots.txt), writes a small landing page
<out dir>/app-preview.html (publish it with the Artifact tool, root = <out dir>) and <out dir>/files.json,
the list to pass as the tool's `files` argument (one publish takes at most 255 files and 64 MB).
Files whose extension says nothing (for instance a PNG saved as load.php) get an explicit contentType.
Part of the wiki kit v2 (Nov 2026); drafted by Claude (AI).
"""
import json, os, re, shutil, sys

MAGIC = [(b'\x89PNG', 'image/png'), (b'\xff\xd8\xff', 'image/jpeg'), (b'GIF8', 'image/gif'), (b'wOFF', 'font/woff'),
         (b'wOF2', 'font/woff2'), (b'<svg', 'image/svg+xml'), (b'<?xml', 'image/svg+xml')]
KNOWN = {'.html', '.css', '.js', '.json', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.woff', '.woff2', '.txt', '.ico', '.webp'}
EXPLICIT = {'.mp4': 'video/mp4', '.m4v': 'video/mp4', '.webm': 'video/webm', '.ogv': 'video/ogg',   # kit v2.1: videos,
            '.tex': 'text/plain'}                                                  # and TeX sources


def main():
    if len(sys.argv) < 3:
        print(__doc__); return 2
    src, out = sys.argv[1], sys.argv[2]
    title = sys.argv[sys.argv.index('--title') + 1] if '--title' in sys.argv else 'Wiki preview'
    if os.path.exists(out):
        shutil.rmtree(out)
    shutil.copytree(src, out)
    for f in ('_headers', 'robots.txt'):
        p = os.path.join(out, f)
        if os.path.exists(p):
            os.remove(p)
    os.rename(os.path.join(out, 'index.html'), os.path.join(out, 'overview.html'))
    n = 0
    for f in os.listdir(out):
        p = os.path.join(out, f)
        if os.path.isfile(p) and (f.endswith('.html') or f == 'search.json'):
            t = open(p, encoding='utf-8').read()
            t2 = re.sub(r'(?<!wiki-preview/)(?<![\w-])(\./)?index\.html', 'overview.html', t)
            t2 = re.sub(r' download="[^"]*"', '', t2)   # the app's frame blocks downloads: the TeX link opens the text
            if t2 != t:
                open(p, 'w', encoding='utf-8').write(t2); n += 1
    files = []
    for r, _, fs in os.walk(out):
        for f in fs:
            p = os.path.join(r, f); rel = os.path.relpath(p, out)
            entry = {'path': rel}
            if os.path.splitext(f)[1].lower() in EXPLICIT:
                entry['contentType'] = EXPLICIT[os.path.splitext(f)[1].lower()]
            elif os.path.splitext(f)[1].lower() not in KNOWN:
                head = open(p, 'rb').read(8)
                for magic, ct in MAGIC:
                    if head.startswith(magic):
                        entry['contentType'] = ct; break
                else:
                    entry['contentType'] = 'application/octet-stream'
            files.append(entry)
    files.sort(key=lambda e: e['path'])
    json.dump(files, open(os.path.join(out, 'files.json'), 'w'), indent=0)
    has_copy = os.path.isdir(os.path.join(out, 'wiki-preview'))
    intro = ('Preview of the edition built from the wiki, with the static copy of the wiki under “This page in the wiki”.'
             if has_copy else 'Preview of the edition built from the wiki.')
    copy_line = ('  <p><a href="wiki-preview/index.html">The wiki itself</a>: pages, edit view, history, talk pages (static copy).</p>\n'
                 if has_copy else '')
    landing = f'''<title>{title}</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>
  :root {{ --bg: #fbfbf9; --fg: #1c222b; --muted: #59616e; --accent: #1f4e79; }}
  @media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg: #14181f; --fg: #e6e9ee; --muted: #a3acb8; --accent: #8fb4d9; color-scheme: dark; }} }}
  :root[data-theme="dark"] {{ --bg: #14181f; --fg: #e6e9ee; --muted: #a3acb8; --accent: #8fb4d9; color-scheme: dark; }}
  body {{ background: var(--bg); color: var(--fg); font-family: Georgia, serif; padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); padding-block: 3rem; }}
  main {{ max-width: 36rem; margin: 0 auto; display: grid; gap: 1rem; }}
  h1 {{ font-family: system-ui, sans-serif; font-size: 1.5rem; margin: 0; }}
  p {{ margin: 0; line-height: 1.5; }} .muted {{ color: var(--muted); font-size: 0.95rem; }}
  a {{ color: var(--accent); }} a.go {{ font-family: system-ui, sans-serif; display: inline-block; padding: 0.55rem 1rem; border-radius: 4px; background: var(--accent); color: var(--bg); text-decoration: none; }}
</style>
<main>
  <h1>{title}</h1>
  <p>{intro}</p>
  <p><a class="go" href="overview.html">Open the edition</a></p>
{copy_line}  <p class="muted">If this page does not move on by itself, use the button.</p>
</main>
<script>setTimeout(function () {{ window.location.href = "overview.html"; }}, 1500);</script>
'''
    open(os.path.join(out, 'app-preview.html'), 'w', encoding='utf-8').write(landing)
    print(f'{len(files)} files listed in {out}/files.json ({n} pages rewritten); publish {out}/app-preview.html with root={out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

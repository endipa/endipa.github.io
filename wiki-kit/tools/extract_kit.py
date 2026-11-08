#!/usr/bin/env python3
"""extract_kit.py: write the files embedded in the wiki-kit handover and check them against its manifest.

Usage: python3 extract_kit.py <handover.md> <out-dir>

Each file sits in the handover between a line "~~~~~<lang> file=<path>" and a line "~~~~~".
The last block, MANIFEST.json, gives the size and SHA-256 of every file.
"""
import hashlib, json, os, re, stat, sys

md, out = sys.argv[1], sys.argv[2]
text = open(md, encoding='utf-8').read().replace('\r\n', '\n')
blocks = re.findall(r'^~~~~~[\w-]* file=([^\n]+)\n(.*?)\n~~~~~$', text, flags=re.M | re.S)
manifest, written = {}, []
for path, body in blocks:
    path = path.strip()
    if path == 'MANIFEST.json':
        manifest = json.loads(body)
        continue
    if path.startswith('/') or '..' in path.split('/'):
        sys.exit('refusing path ' + path)
    dest = os.path.join(out, path)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, 'w', encoding='utf-8', newline='\n') as f:
        f.write(body + '\n')
    if path.endswith(('.sh', '.py')):
        os.chmod(dest, os.stat(dest).st_mode | stat.S_IXUSR)
    written.append(path)
bad = [p for p in manifest if p not in written or
       hashlib.sha256(open(os.path.join(out, p), 'rb').read()).hexdigest() != manifest[p]['sha256']]
extra = [p for p in written if p not in manifest]
print(f'{len(written)} files written to {out}; ' +
      ('all match the manifest' if not bad and not extra else f'DIFFERENT: {bad}; not in manifest: {extra}'))
sys.exit(1 if bad else 0)

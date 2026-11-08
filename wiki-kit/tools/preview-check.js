// preview-check.js: checks of the static preview written by wiki-export.js.
// Serve the folder first (e.g. `python3 -m http.server 8790 -d <dir>`), with the wiki server stopped,
// so that any request back to the wiki shows up as a failure.
// Usage: DIR=<dir> [BASE=http://127.0.0.1:8790/] [OUT=<screenshots dir>] node preview-check.js
// Reports: failed or external requests, pages without math, with scripts or without banner, links to
// missing files, the folded-proof toggle, the navigation tree, and horizontal scrolling at 375 px.
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const DIR = process.env.DIR, BASE = process.env.BASE || 'http://127.0.0.1:8790/', SHOTS = process.env.OUT;
(async () => {
  const files = fs.readdirSync(DIR).filter(f => f.endsWith('.html')).sort();
  const b = await chromium.launch();
  const ctx = await b.newContext({viewport: {width: 1280, height: 900}});
  const p = await ctx.newPage();
  const base = new URL(BASE);
  const bad = [], external = new Set(), missingLinks = new Set(), missingAnchors = new Set();
  p.on('response', r => { if (r.status() >= 400) bad.push(r.status() + ' ' + r.url()); });
  p.on('requestfailed', r => bad.push('failed ' + r.url()));
  p.on('request', r => { const u = new URL(r.url()); if (u.host !== base.host && !u.protocol.startsWith('data')) external.add(u.host); });
  const summary = [];
  for (const f of files) {
    await p.goto(BASE + f, {waitUntil: 'load'});
    await p.waitForTimeout(100);
    const r = await p.evaluate(() => ({
      mjx: document.querySelectorAll('mjx-container').length,
      hrefs: [...document.querySelectorAll('a[href]')].map(a => a.getAttribute('href')).filter(h => !/^(https?:|mailto:)/.test(h)),
      ids: [...document.querySelectorAll('[id]')].map(e => e.id),
      scripts: document.querySelectorAll('script').length,
      banner: !!document.querySelector('.preview-banner'),
      robots: (document.querySelector('meta[name=robots]') || {}).content || null
    }));
    for (const h of r.hrefs) {
      const [file, anchor] = h.split('#');
      const target = file ? decodeURIComponent(file) : f;
      if (file && !fs.existsSync(path.join(DIR, target))) { missingLinks.add(f + ' -> ' + h); continue; }
      if (anchor && target.endsWith('.html')) {
        const html = target === f ? null : fs.readFileSync(path.join(DIR, target), 'utf8');
        const id = decodeURIComponent(anchor);
        const ok = target === f ? r.ids.includes(id) : (html.includes(`id="${id}"`) || html.includes(`id="${id.replace(/"/g, '&quot;')}"`));
        if (!ok) missingAnchors.add(f + ' -> ' + h);
      }
    }
    summary.push({f, mjx: r.mjx, scripts: r.scripts, banner: r.banner, robots: r.robots});
  }
  // Interaction: a folded proof, and the navigation tree
  const withProof = files.find(f => !/-(edit|history|diff)/.test(f) && fs.readFileSync(path.join(DIR, f), 'utf8').includes('lvl-proof'));
  let proofToggle = null;
  if (withProof) {
    await p.goto(BASE + withProof, {waitUntil: 'load'});
    const before = await p.evaluate(() => document.querySelector('details.lvl-proof').open);
    await p.click('details.lvl-proof > summary');
    const after = await p.evaluate(() => document.querySelector('details.lvl-proof').open);
    proofToggle = {page: withProof, before, after};
    if (SHOTS) await p.screenshot({path: path.join(SHOTS, 'pv-module-proof.png'), fullPage: true});
  }
  await p.goto(BASE + 'index.html', {waitUntil: 'load'});
  const tree = await p.evaluate(() => ({pages: document.querySelectorAll('li.navtree-static').length,
    open: [...document.querySelectorAll('li.navtree-page > details[open] > summary')].map(s => s.textContent.trim())}));
  // click the triangle (the summary's ::before, in the left padding of the li), not the link
  const box = await p.evaluate(() => { const li = document.querySelector('li.navtree-page > details:not([open])');
    if (!li) return null; const r = li.parentElement.getBoundingClientRect(); return {x: r.left + 4, y: r.top + 8}; });
  if (box) { await p.mouse.click(box.x, box.y); await p.waitForTimeout(100);
    tree.toggledOpen = await p.evaluate(() => document.querySelectorAll('li.navtree-page > details[open]').length); tree.url = p.url(); }
  if (SHOTS) {
    await p.screenshot({path: path.join(SHOTS, 'pv-index.png')});
    const ed = files.find(f => f.endsWith('-edit.html')), hi = files.find(f => f.endsWith('-history.html'));
    if (ed) { await p.goto(BASE + ed, {waitUntil: 'load'}); await p.screenshot({path: path.join(SHOTS, 'pv-edit.png')}); }
    if (hi) { await p.goto(BASE + hi, {waitUntil: 'load'}); await p.screenshot({path: path.join(SHOTS, 'pv-history.png')}); }
  }
  const ph = await (await b.newContext({viewport: {width: 375, height: 812}})).newPage();
  const hscroll = {};
  for (const f of files.filter(f => !/-(edit|history|diff)/.test(f))) {
    await ph.goto(BASE + f, {waitUntil: 'load'});
    const w = await ph.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    if (w > 0) hscroll[f] = w;
  }
  if (SHOTS) { await ph.goto(BASE + 'index.html', {waitUntil: 'load'}); await ph.screenshot({path: path.join(SHOTS, 'pv-phone.png')}); }
  await b.close();
  console.log(JSON.stringify({pages: summary.length,
    noMath: summary.filter(s => s.mjx === 0 && !/-(edit|history)|^talk-/.test(s.f)).map(s => s.f),
    withScripts: summary.filter(s => s.scripts).map(s => s.f), noBanner: summary.filter(s => !s.banner).map(s => s.f),
    notNoindex: summary.filter(s => !/noindex/.test(s.robots || '')).map(s => s.f),
    bad: bad.slice(0, 10), external: [...external], missingLinks: [...missingLinks].slice(0, 15),
    missingAnchors: [...missingAnchors].slice(0, 15), proofToggle, tree, phoneHscroll: hscroll}, null, 1));
})();

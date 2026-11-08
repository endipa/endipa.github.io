// Checks the built Quarto book: failed or external requests, MathJax errors, unresolved
// cross-references, internal links and anchors (also into wiki-preview/), and horizontal overflow at 375 px.
// Usage: node site-check.js http://127.0.0.1:PORT/ <_book dir> [<screenshots dir>]   (serve _book first)
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const [base, dir, shots] = process.argv.slice(2);
const pages = fs.readdirSync(dir).filter(f => f.endsWith('.html'));
(async () => {
  const b = await chromium.launch();
  const report = [];
  for (const vw of [{width: 1280, height: 900}, {width: 375, height: 812}]) {
    const ctx = await b.newContext({viewport: vw});
    for (const pg of pages) {
      const p = await ctx.newPage();
      const failed = [], external = [];
      p.on('requestfailed', r => failed.push(r.url()));
      p.on('request', r => { const u = new URL(r.url()); if (!['127.0.0.1', 'localhost'].includes(u.hostname) && !u.protocol.startsWith('data')) external.push(u.hostname + u.pathname.slice(0, 40)); });
      await p.goto(base + pg, {waitUntil: 'networkidle'});
      await p.waitForFunction(() => !window.MathJax || (window.MathJax.startup && window.MathJax.startup.promise), null, {timeout: 15000}).catch(() => {});
      await p.evaluate(() => window.MathJax && MathJax.startup && MathJax.startup.promise).catch(() => {});
      const r = await p.evaluate(() => {
        const W = document.documentElement.clientWidth;
        const ids = new Set([...document.querySelectorAll('[id]')].map(e => e.id));
        const links = [...document.querySelectorAll('main a[href]')].map(a => a.getAttribute('href'));
        const clipped = e => { for (let a = e.parentElement; a && a !== document.body; a = a.parentElement) { const o = getComputedStyle(a).overflowX; if (o === 'auto' || o === 'scroll' || o === 'hidden') return true; } return false; };
        const overflow = [...document.querySelectorAll('main *')].filter(e => { const rc = e.getBoundingClientRect(); return rc.right > W + 1 && rc.width > 0 && !clipped(e); }).slice(0, 3).map(e => e.tagName + '.' + String(e.className).slice(0, 30) + ' «' + (e.textContent || '').trim().slice(0, 40) + '»');
        return {mjx: document.querySelectorAll('mjx-container').length, merror: document.querySelectorAll('mjx-merror').length,
                unresolved: (document.body.innerText.match(/\?@[a-z]+-/g) || []).length,
                localAnchorsMissing: links.filter(h => h.startsWith('#') && h.length > 1 && !ids.has(decodeURIComponent(h.slice(1)))),
                pageLinks: links.filter(h => /^([a-z0-9-]+\/)*[a-z0-9-]+\.html/.test(h)),
                theorems: [...document.querySelectorAll('.theorem-title, .lemma-title, .proposition-title')].map(e => e.parentElement.textContent.trim().slice(0, 50)),
                docOverflow: document.documentElement.scrollWidth > W + 1, overflow,
                zulip: !!document.querySelector('a.zulip-btn'), wiki: (document.querySelector('a.edit-link') || {}).href || null};
      });
      // page links: target file and anchor must exist
      const broken = [];
      for (const h of r.pageLinks) { const [f, a] = h.split('#'); const fp = path.join(dir, f); if (!fs.existsSync(fp)) { broken.push(h); continue; } if (a && !fs.readFileSync(fp, 'utf8').includes(`id="${a}"`)) broken.push(h); }
      if (shots && vw.width === 1280 && /^index/.test(pg)) await p.screenshot({path: path.join(shots, pg.replace('.html', '') + '.png'), fullPage: false});
      report.push({vw: vw.width, pg, mjx: r.mjx, merror: r.merror, unresolved: r.unresolved, missingAnchors: r.localAnchorsMissing, broken, failed, external: [...new Set(external)], docOverflow: r.docOverflow, overflow: vw.width < 500 ? r.overflow : undefined, theorems: vw.width > 500 ? r.theorems : undefined, zulip: r.zulip, wiki: vw.width > 500 ? r.wiki : undefined});
      await p.close();
    }
    await ctx.close();
  }
  await b.close();
  console.log(JSON.stringify(report, null, 0).replace(/\},\{/g, '},\n{'));
})();

// shoot.js: screenshots of the built edition, for the status note and for Michele.
// Usage: BASE=http://127.0.0.1:8791/ OUT=shots PAGES="index.html,couette-flow.html" [OPEN_PROOF=1] node shoot.js
// Serve _book first (python3 -m http.server 8791 -d site/_book). Waits for MathJax before each shot.
// Part of the wiki kit v2 (Nov 2026); drafted by Claude (AI).
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const BASE = process.env.BASE || 'http://127.0.0.1:8791/', OUT = process.env.OUT || 'shots';
const PAGES = (process.env.PAGES || 'index.html').split(',').map(s => s.trim()).filter(Boolean);
(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1280, height: 860 }, deviceScaleFactor: 2 });
  const p = await ctx.newPage();
  const wait = async () => {
    await p.waitForFunction(() => window.MathJax && MathJax.startup && MathJax.startup.promise, null, { timeout: 20000 }).catch(() => {});
    await p.evaluate(() => MathJax.startup.promise).catch(() => {});
    await p.waitForTimeout(600);
  };
  for (const pg of PAGES) {
    await p.goto(BASE + pg); await wait();
    const stem = pg.replace(/\.html$/, '');
    await p.screenshot({ path: path.join(OUT, `edition-${stem}.png`) });
    if (process.env.OPEN_PROOF) {
      const btn = await p.$('.lvl-proof .callout-header');
      if (btn) {
        await btn.click(); await p.waitForTimeout(500); await btn.scrollIntoViewIfNeeded();
        await p.evaluate(() => window.scrollBy(0, -80)); await p.waitForTimeout(300);
        await p.screenshot({ path: path.join(OUT, `edition-${stem}-proof.png`) });
      }
    }
  }
  await b.close();
  console.log('screenshots in ' + OUT);
})();

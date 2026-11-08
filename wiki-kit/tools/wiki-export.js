// wiki-export.js: a static, clickable copy of the local preview wiki (local-wiki.sh), for Netlify.
// Pages are found through the API: every article (Overview -> index.html, others -> <slug>.html, the
// same names as the Quarto edition), its talk page, edit view and history, the Statement/ templates,
// and diff pages for one page with several revisions. Scripts are removed; folded boxes and the
// navigation tree become <details>, so the copy works without JavaScript; every page gets a banner
// and a robots noindex tag. Part of the wiki kit (2026), adapted from the 2D Euler reading group.
//
// Usage: OUT=<dir> [HOST=http://127.0.0.1:8080] [SITE="Name of the wiki"] [QUARTO=../]
//        [HISTORY_PAGE="Title"] node wiki-export.js
//   QUARTO: relative link from the preview to a Quarto edition (omit when there is none);
//   HISTORY_PAGE: page whose revisions get diff pages (default: the article with most revisions, if >1).
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const HOST = (process.env.HOST || 'http://127.0.0.1:8080').replace(/\/$/, '');
const OUT = process.env.OUT;
const QUARTO = process.env.QUARTO || '';
const SITE = process.env.SITE || '';
const MJFONTS = '/usr/share/mediawiki/extensions/SimpleMathJax/resources/MathJax/es5/output/chtml/fonts/woff-v2';
if (!OUT) { console.error('set OUT=<output dir>'); process.exit(2); }

// Same rule as slug() in wiki2qmd.py, so that the preview and the edition use the same file names.
const slug = t => t.replace(/[–—]/g, '-').normalize('NFKD').replace(/[^\x00-\x7f]/g, '').toLowerCase()
  .replace(/'/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');

const BANNERS = {
  view: 'Preview of the project wiki' + (SITE ? ` <i>${SITE}</i>` : '') + '. This is a static copy: editing, search and log-in are switched off. Use the <b>Edit</b> and <b>View history</b> tabs to see what editors see.',
  talk: 'The discussion page attached to every page of the wiki. Static copy: posting is switched off.',
  edit: 'What an editor sees after clicking <b>Edit</b>: the page source, with formulas in &lt;math&gt; tags. In this static copy the box is read-only and saving is switched off.',
  history: 'Every edit is kept, with its author, date and summary. Open a diff to see exactly what changed.',
  diff: 'A diff: what one edit changed, line by line. Below it, the page as it looks after the edit.',
  template: 'A shared statement: stored once and shown on every page that includes it. Editing it here would change all of them.',
};

(async () => {
  fs.mkdirSync(path.join(OUT, 'assets', 'css'), { recursive: true });
  fs.mkdirSync(path.join(OUT, 'assets', 'mjfonts'), { recursive: true });
  for (const f of fs.readdirSync(MJFONTS)) fs.copyFileSync(path.join(MJFONTS, f), path.join(OUT, 'assets', 'mjfonts', f));
  fs.writeFileSync(path.join(OUT, 'robots.txt'), 'User-agent: *\nDisallow: /\n');
  fs.writeFileSync(path.join(OUT, '_headers'), '/*\n  X-Robots-Tag: noindex, nofollow\n');

  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  const api = async params => (await (await ctx.request.get(HOST + '/api.php?' + new URLSearchParams({ format: 'json', formatversion: '2', ...params }))).json());
  const allpages = async (ns, extra = {}) => ((await api({ action: 'query', list: 'allpages', apnamespace: String(ns), aplimit: 'max', ...extra })).query.allpages || []).map(p => p.title);

  // ---- which pages, under which file names
  const articles = await allpages(0, { apfilterredir: 'nonredirects' });
  const redirects = await allpages(0, { apfilterredir: 'redirects' });
  const statements = await allpages(10, { apprefix: 'Statement/' });
  const talks = new Set(await allpages(1));
  const MAP = {};                                   // title -> file stem
  for (const t of articles) MAP[t] = t === 'Overview' ? 'index' : slug(t);
  for (const t of statements) MAP[t] = 'template-statement-' + slug(t.slice('Template:Statement/'.length));
  if (redirects.length) {
    const r = await api({ action: 'query', titles: redirects.join('|'), redirects: '1' });
    for (const x of (r.query.redirects || [])) if (MAP[x.to]) MAP[x.from] = MAP[x.to];
  }
  const stem = t => (MAP[t] === 'index' ? 'overview' : MAP[t]);   // talk-overview.html, overview-edit.html

  // ---- the page with a history worth showing
  let histPage = process.env.HISTORY_PAGE || null, revs = [];
  const revsOf = async t => ((await api({ action: 'query', prop: 'revisions', titles: t, rvlimit: '50', rvprop: 'ids' })).query.pages[0].revisions || []).map(r => r.revid).sort((a, b) => a - b);
  if (histPage) revs = await revsOf(histPage);
  else for (const t of articles) { const r = await revsOf(t); if (r.length > Math.max(1, revs.length)) { histPage = t; revs = r; } }
  if (revs.length < 2) { histPage = null; revs = []; }
  const latest = revs[revs.length - 1];
  const hslug = histPage ? MAP[histPage] : null;
  const diffPairs = revs.slice(1).map((r, i) => [revs[i], r]);
  const diffFile = (a, b) => `${hslug}-diff-${a}-${b}.html`;

  const q = t => encodeURIComponent(t.replace(/ /g, '_'));
  const targets = [];
  for (const t of articles) {
    targets.push({ url: `${HOST}/index.php?title=${q(t)}`, file: `${MAP[t]}.html`, kind: 'view' });
    if (talks.has('Talk:' + t)) targets.push({ url: `${HOST}/index.php?title=Talk:${q(t)}`, file: `talk-${stem(t)}.html`, kind: 'talk' });
    targets.push({ url: `${HOST}/index.php?title=${q(t)}&action=edit`, file: `${stem(t)}-edit.html`, kind: 'edit' });
    targets.push({ url: `${HOST}/index.php?title=${q(t)}&action=history`, file: `${stem(t)}-history.html`, kind: 'history' });
  }
  for (const [a, b] of diffPairs) targets.push({ url: `${HOST}/index.php?title=${q(histPage)}&diff=${b}&oldid=${a}`, file: diffFile(a, b), kind: 'diff' });
  for (const t of statements) targets.push({ url: `${HOST}/index.php?title=${q(t)}`, file: `${MAP[t]}.html`, kind: 'template' });

  const cssCache = new Map();
  const saveCss = async (href) => {
    if (cssCache.has(href)) return cssCache.get(href);
    const res = await ctx.request.get(HOST + href.replace(/&amp;/g, '&'));
    let css = await res.text();
    const refs = [...css.matchAll(/url\((['"]?)(\/[^)'"]+)\1\)/g)].map(m => m[2]);
    for (const ref of new Set(refs)) {
      const clean = ref.split('?')[0];
      const dest = path.join(OUT, 'assets', 'files', clean);
      if (!fs.existsSync(dest)) {
        const r = await ctx.request.get(HOST + ref);
        if (r.ok()) { fs.mkdirSync(path.dirname(dest), { recursive: true }); fs.writeFileSync(dest, await r.body()); }
      }
      css = css.split(ref).join('../files' + clean);
    }
    const name = 's-' + crypto.createHash('sha1').update(href).digest('hex').slice(0, 10) + '.css';
    fs.writeFileSync(path.join(OUT, 'assets', 'css', name), css);
    cssCache.set(href, 'assets/css/' + name);
    return 'assets/css/' + name;
  };

  const report = [];
  for (const tg of targets) {
    await page.goto(tg.url, { waitUntil: 'load', timeout: 30000 });
    try {
      await page.waitForFunction(() => document.querySelectorAll('.smj-container').length === document.querySelectorAll('.smj-container mjx-container').length, null, { timeout: 20000 });
    } catch (e) { report.push(['math wait timeout', tg.file]); }
    try { await page.waitForFunction(() => document.documentElement.getAttribute('data-navtree'), null, { timeout: 10000 }); }
    catch (e) { report.push(['no navigation tree', tg.file]); }
    await page.waitForTimeout(300);
    const info = await page.evaluate((cfg) => {
      const { MAP, revs, latest, hslug, banner, quarto } = cfg;
      const stem = t => (MAP[t] === 'index' ? 'overview' : MAP[t]);
      const prevOf = r => revs[revs.indexOf(r) - 1], nextOf = r => revs[revs.indexOf(r) + 1];
      const pairs = new Set(revs.slice(1).map((r, i) => `${revs[i]}-${r}`));
      const off = a => { a.removeAttribute('href'); a.classList.add('preview-off'); a.title = 'Not available in the static preview'; };
      // Navigation tree -> nested <details> (before the links are rewritten; the links move along)
      for (const li of [...document.querySelectorAll('li.navtree-page, li.navtree-item')]) {
        const btn = li.querySelector(':scope > button.navtree-toggle');
        const ul = li.querySelector(':scope > ul.navtree-list');
        const a = li.querySelector(':scope > a');
        if (btn) btn.remove();
        if (!ul || !a) continue;
        const det = document.createElement('details');
        det.open = li.classList.contains('navtree-open');
        const sum = document.createElement('summary');
        sum.appendChild(a);
        det.appendChild(sum);
        det.appendChild(ul);
        li.appendChild(det);
        li.classList.remove('navtree-open', 'navtree-closed');
        li.classList.add('navtree-static');
      }
      let offCount = 0, mapped = 0;
      for (const a of [...document.querySelectorAll('a[href]')]) {
        if (/^javascript:/i.test(a.getAttribute('href'))) { off(a); offCount++; continue; }
        let u; try { u = new URL(a.getAttribute('href'), location.href); } catch (e) { continue; }
        if (u.origin !== location.origin) { a.target = '_blank'; a.rel = 'noopener'; continue; }
        if (!(u.pathname === '/index.php' || u.pathname.startsWith('/index.php/'))) { off(a); offCount++; continue; }
        let title = u.searchParams.get('title') || decodeURIComponent(u.pathname.replace(/^\/index\.php\/?/, ''));
        title = (title || 'Main Page').replace(/_/g, ' ');
        const action = u.searchParams.get('action') || 'view';
        const diff = u.searchParams.get('diff'), oldid = u.searchParams.get('oldid') && Number(u.searchParams.get('oldid'));
        const talk = title.startsWith('Talk:');
        const base = talk ? title.slice(5) : title;
        let target = null;
        if (!MAP[base]) { off(a); offCount++; continue; }
        if (diff !== null || (oldid && action === 'view')) {
          if (!hslug || MAP[base] !== hslug || talk) { off(a); offCount++; continue; }
          let x = null, y = null;
          if (diff === 'prev') { x = prevOf(oldid); y = oldid; }
          else if (diff === 'next') { x = oldid; y = nextOf(oldid); }
          else if (diff === 'cur') { x = oldid; y = latest; }
          else if (diff) { y = Number(diff); x = oldid || prevOf(y); }
          if (x && y && pairs.has(`${x}-${y}`)) target = `${hslug}-diff-${x}-${y}.html`;
        } else if (action === 'view' && !u.searchParams.get('redlink')) {
          target = talk ? (cfg.talks.includes(title) ? `talk-${stem(base)}.html` : null) : `${MAP[base]}.html`;
        } else if (action === 'edit' && !talk && !u.searchParams.get('undo') && u.searchParams.get('section') !== 'new' && !base.startsWith('Template:')) {
          target = `${stem(base)}-edit.html`;
        } else if (action === 'history' && !talk && !base.startsWith('Template:')) {
          target = `${stem(base)}-history.html`;
        }
        if (target) { a.setAttribute('href', target + (u.hash || '')); mapped++; } else { off(a); offCount++; }
      }
      // Folded boxes become <details>, so they work without JavaScript
      for (const box of [...document.querySelectorAll('div.mw-collapsible')]) {
        const title = box.querySelector(':scope > .lvl-title');
        const content = box.querySelector(':scope > .mw-collapsible-content');
        box.querySelectorAll('.mw-collapsible-toggle').forEach(t => t.remove());
        const det = document.createElement('details');
        det.className = box.className.replace(/\bmw-(collapsible|collapsed|made-collapsible)\b/g, '').trim();
        if (box.id) det.id = box.id;
        const sum = document.createElement('summary');
        sum.className = 'lvl-title';
        sum.innerHTML = title ? title.innerHTML : 'Show';
        det.appendChild(sum);
        if (content) { content.style.removeProperty('display'); content.removeAttribute('hidden'); det.appendChild(content); }
        box.replaceWith(det);
      }
      // Static copy: no scripts, no forms that submit, no log-in or search
      document.querySelectorAll('script, noscript').forEach(s => s.remove());
      document.querySelectorAll('link').forEach(l => { if (l.rel !== 'stylesheet') l.remove(); });
      document.querySelectorAll('meta[name="robots"]').forEach(m => m.remove());
      const robots = document.createElement('meta'); robots.name = 'robots'; robots.content = 'noindex, nofollow';
      document.head.prepend(robots);
      document.querySelectorAll('form').forEach(f => { f.removeAttribute('action'); f.setAttribute('onsubmit', 'return false'); });
      document.querySelectorAll('input[type=submit], button').forEach(b => b.setAttribute('disabled', ''));
      document.querySelectorAll('textarea').forEach(t => t.setAttribute('readonly', ''));
      document.querySelectorAll('#mw-anon-edit-warning, .mw-anon-edit-warning, #footer-icons, #editpage-copywarn, img.mw-logo-icon').forEach(e => e.remove());
      const style = document.createElement('style');
      style.textContent = `
        .preview-banner { background: #fef6e7; border-bottom: 1px solid #e7c475; color: #202122; font: 14px/1.45 sans-serif; padding: 9px 16px; }
        .preview-banner a { color: #36c; }
        .preview-off { color: #72777d !important; cursor: not-allowed; text-decoration: none !important; }
        .vector-user-links, #p-search, .vector-search-box, #p-tb, #p-personal, .vector-page-toolbar .vector-menu-dropdown { display: none !important; }
        details.lvl > summary { cursor: pointer; }
        details.lvl > summary::marker { color: #72777d; }
        li.navtree-static > details > summary { list-style: none; cursor: pointer; }
        li.navtree-static > details > summary::-webkit-details-marker { display: none; }
        li.navtree-static > details > summary::before { content: "\\25B8"; position: absolute; left: 0; top: 0.1em; width: 1em; color: #54595d; font-size: 0.8em; line-height: 1.6; }
        li.navtree-static > details[open] > summary::before { content: "\\25BE"; }
        @media (max-width: 720px) { .mw-page-container { min-width: 0 !important; } .mw-parser-output table { display: block; overflow-x: auto; max-width: 100%; }
          .mw-parser-output mjx-container[display="true"] { overflow-x: auto; overflow-y: hidden; max-width: 100%; }
          .mw-parser-output mjx-container:not([display="true"]) { display: inline-block; max-width: 100%; overflow-x: auto; overflow-y: hidden; vertical-align: middle; }
          .mw-page-title-main, h1, .mw-parser-output code { overflow-wrap: anywhere; } }`;
      document.head.appendChild(style);
      const div = document.createElement('div');
      div.className = 'preview-banner';
      div.innerHTML = banner + ' · <a href="index.html">Wiki overview</a>' + (quarto ? ` · <a href="${quarto}">The same pages in Quarto</a>` : '');
      document.body.insertBefore(div, document.body.firstChild);
      return { mapped, offCount };
    }, { MAP, revs, latest, hslug, banner: BANNERS[tg.kind], quarto: QUARTO, talks: [...talks] });

    let html = await page.content();
    // Stylesheets from ResourceLoader become local files
    const hrefs = [...html.matchAll(/<link[^>]+rel="stylesheet"[^>]+href="([^"]+)"/g)].map(m => m[1]);
    for (const h of new Set(hrefs)) {
      if (!h.startsWith('/')) continue;
      const local = await saveCss(h);
      html = html.split(`href="${h}"`).join(`href="${local}"`);
    }
    // Assets referenced from inline <style> blocks
    for (const ref of new Set([...html.matchAll(/url\((['"]?)(\/(?:resources|extensions|skins)\/[^)'"]+)\1\)/g)].map(m => m[2]))) {
      const clean = ref.split('?')[0];
      const dest = path.join(OUT, 'assets', 'files', clean);
      if (!fs.existsSync(dest)) { const r = await ctx.request.get(HOST + ref); if (r.ok()) { fs.mkdirSync(path.dirname(dest), { recursive: true }); fs.writeFileSync(dest, await r.body()); } }
      html = html.split(ref).join('assets/files' + clean);
    }
    html = html.split(HOST + '/extensions/SimpleMathJax/resources/MathJax/es5/output/chtml/fonts/woff-v2/').join('assets/mjfonts/');
    fs.writeFileSync(path.join(OUT, tg.file), html);
    report.push([tg.file, info.mapped, info.offCount]);
  }
  await browser.close();
  console.log(JSON.stringify({ articles: articles.length, statements: statements.length, talkPages: talks.size,
    historyPage: histPage, revisions: revs, files: report.length, problems: report.filter(r => typeof r[1] !== 'number') }, null, 1));
})();

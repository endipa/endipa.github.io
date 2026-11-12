-- page-links.lua: the links under each page's title (wiki kit, from the 2D Euler reading group).
--
-- The pages are generated from the wiki by wiki2qmd.py. A page may name its Zulip topic in the
-- front matter (taken from a "Zulip topic" link in the page's discuss-line, when edition.json
-- sets zulip_host):
--   zulip: "https://<org>.zulipchat.com/#narrow/channel/<id>-<channel>/topic/<topic>"
--   zulip-related: "..."   (optional)
-- and _quarto.yml sets, for all pages,
--   wiki-url: "https://<slug>.miraheze.org/wiki/"   (the real wiki; the page title is taken from
--   wiki-page in the front matter) or "wiki-preview/" (a relative address: the static preview,
--   whose files have the same names as the edition's).
--
-- The filter adds, after the page's module-meta block (or inside an empty `::: {.discuss}` div
-- on pages without one):
--   * a "Discuss on Zulip" link, when the page has a Zulip topic (a filled button until 10 November 2026; since
--     11 November 2026 it carries the round Zulip icon instead of a speech bubble),
--   * a "This page in the wiki" link: the wiki is where the text is edited; this edition is
--     rebuilt from it by a script and never edited by hand (wiki-note, from edition.json, e.g. "members" for a
--     wiki by invitation: when the link goes to the real wiki, the line opens with "For members:"),
--   * kit v2.1: a "TeX source" link that downloads the page's TeX source (tex-source in the front
--     matter), a "PDF" link to the PDF compiled from it (pdf-source), and, on the Overview only, "PDF of the whole wiki" and "TeX of the whole
--     wiki (zip)": tex/all-pages.zip, a LaTeX project with main.tex and every page as a file of pages/ (it also opens in
--     Overleaf; November 2026: no "Open in Overleaf" button any more); on a page with pictures, "TeX source" downloads a zip
--     (the .tex and the folder figures/; said by the tooltip of the link),
--   * (November 2026) a "Propose a change" link, when _quarto.yml sets propose-preload (edition.json, edit_paragraphs.preload_block)
--     and the wiki is the real one: a new topic on the page's talk page, filled in with that preload page,
-- and a "Propose a text" link at the end of every placeholder: the same new topic, or the Zulip topic when there is none.
--
-- 11 November 2026: the hosting of the project's Zulip is sponsored by Zulip (Zulip Cloud Standard, free of charge).
-- Following https://zulip.com/help/linking-to-zulip-website (round Zulip icon, link to zulip.com), the pages named in
-- ACK_PAGES end with a line of acknowledgement. The line is written by this filter, not in the wiki: the wiki pages,
-- their TeX sources and their PDFs do not have it.

local zulip, related, wiki, tex, pdf, wiki_note, wiki_real = nil, nil, nil, nil, nil, nil, false
local book_pdf, book_zip = nil, nil
local propose_preload, propose = nil, nil
local page_title = nil   -- the title of the page in the wiki (wiki-page in the front matter)

-- The round Zulip icon: the file static/images/logo/zulip-icon-circle.svg of Zulip, unchanged (a copy is next to this
-- file, zulip-icon-circle.svg, SHA-1 348706c36fba0fabf3e934a271fddcf9a1ff19d3), written as a data address so that the
-- build needs no extra file. Its size is set in theme.scss (img.zulip-mark).
local ZULIP_ICON = '<img class="zulip-mark" alt="" aria-hidden="true" width="16" height="16" src="data:image/svg+xml;base64,'
  .. 'PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA3NzMuMTIgNzczLjEyIj48bGluZWFyR3JhZGllbnQgaWQ9ImEiIHgxPSIwIiB5MT0iMCIgeDI9IjAiIHkyPSIxIj48c3RvcCBvZmZzZXQ9IjAiIHN0b3AtY29sb3I9IiM1MGFkZmYiLz48c3RvcCBvZmZzZXQ9IjEiIHN0b3AtY29sb3I9IiM3ODc3ZmMiLz48L2xpbmVhckdyYWRpZW50PjxjaXJjbGUgY3g9IjM4Ni41NiIgY3k9IjM4Ni41NiIgcj0iMzg2LjU2IiBmaWxsPSJ1cmwoI2EpIi8+PHBhdGggZD0iTTU2Ni42NiA1MjcuMjVjMCAzMy4wMy0yNC4yMyA2MC4wNS01My44NCA2MC4wNUgyNjAuMjljLTI5LjYxIDAtNTMuODQtMjcuMDItNTMuODQtNjAuMDUgMC0yMC4yMiA5LjA5LTM4LjIgMjIuOTMtNDkuMDlsMTM0LjM3LTEyMGMyLjUtMi4xNCA1Ljc0IDEuMzEgMy45NCA0LjE5bC00OS4yOSA5OC42OWMtMS4zOCAyLjc2LjQxIDYuMTYgMy4yNSA2LjE2aDE5MS4xOGMyOS42MSAwIDUzLjgzIDI3LjAzIDUzLjgzIDYwLjA1em0wLTI4MS4zOWMwIDIwLjIyLTkuMDkgMzguMi0yMi45MyA0OS4wOWwtMTM0LjM3IDEyMGMtMi41IDIuMTQtNS43NC0xLjMxLTMuOTQtNC4xOWw0OS4yOS05OC42OWMxLjM4LTIuNzYtLjQxLTYuMTYtMy4yNS02LjE2SDI2MC4yOWMtMjkuNjEgMC01My44NC0yNy4wMi01My44NC02MC4wNXMyNC4yMy02MC4wNSA1My44NC02MC4wNWgyNTIuNTRjMjkuNjEgMCA1My44MyAyNy4wMiA1My44MyA2MC4wNXoiIGZpbGw9IiNmZmYiLz48L3N2Zz4='
  .. '">'
-- The acknowledgement of the sponsored hosting, at the end of these pages (titles as in the wiki).
local ACK_PAGES = { ["Overview"] = true, ["Contributors"] = true }
local ACK_HTML = '<div class="site-ack">\n<span class="site-ack-label">Acknowledgements</span>\n'
  .. '<p>The discussion forum runs on <a class="site-ack-link" href="https://zulip.com/" '
  .. 'title="Zulip is an organized team chat app designed for efficient communication.">' .. ZULIP_ICON
  .. 'Zulip</a>, with hosting sponsored by Zulip.</p>\n</div>'

-- MediaWiki page address: spaces become underscores, other characters are percent-encoded.
local function wiki_title(t)
  t = t:gsub(" ", "_")
  return (t:gsub("[^%w%-%._~/:]", function(c) return string.format("%%%02X", string.byte(c)) end))
end

local function read_meta(m)
  if m.zulip then zulip = pandoc.utils.stringify(m.zulip) end
  if m["wiki-page"] then page_title = pandoc.utils.stringify(m["wiki-page"]) end
  if m["zulip-related"] then related = m["zulip-related"] end
  if m["tex-source"] then tex = pandoc.utils.stringify(m["tex-source"]) end   -- kit v2.1
  if m["book-pdf"] then book_pdf = pandoc.utils.stringify(m["book-pdf"]) end
  if m["book-zip"] then book_zip = pandoc.utils.stringify(m["book-zip"]) end
  if m["pdf-source"] then pdf = pandoc.utils.stringify(m["pdf-source"]) end
  if m["wiki-note"] then wiki_note = pandoc.utils.stringify(m["wiki-note"]) end
  if m["propose-preload"] then propose_preload = pandoc.utils.stringify(m["propose-preload"]) end
  if m["wiki-url"] then
    local base = pandoc.utils.stringify(m["wiki-url"])
    if m["wiki-page"] and base:match("^https?://") then
      -- the real wiki: link to the page by its title
      wiki = base .. wiki_title(pandoc.utils.stringify(m["wiki-page"]))
      wiki_real = true
      if propose_preload then
        propose = base .. "Talk:" .. wiki_title(pandoc.utils.stringify(m["wiki-page"]))
          .. "?action=edit&section=new&preload=" .. wiki_title(propose_preload) .. "&preloadtitle=Proposal%3A+"
      end
    elseif quarto and quarto.doc and quarto.doc.input_file then
      -- a static preview of the wiki: link to the file of the same name
      local stem = pandoc.path.split_extension(pandoc.path.filename(quarto.doc.input_file))
      wiki = base .. stem .. ".html"
    end
  end
end

local function note(inlines)
  return pandoc.Span(inlines, pandoc.Attr("", {"discuss-note"}))
end

local function links_row()
  -- One quiet line (10 November 2026; before, a filled "Discuss on Zulip" button and a sentence): the links that need an
  -- account first, after "For members:" (wiki-note of edition.json), then a thin rule and the downloads.
  local inlines = {}
  local function add(el)
    if #inlines > 0 then table.insert(inlines, pandoc.Space()) end
    table.insert(inlines, el)
  end
  local function link(icon, label, target, title, classes, attrs)
    -- icon: the name of a Bootstrap icon, or ready HTML (the Zulip icon)
    local i = pandoc.RawInline("html", icon:sub(1, 1) == "<" and icon or ('<i class="bi bi-' .. icon .. '" aria-hidden="true"></i>'))
    return pandoc.Link({i, pandoc.Space(), pandoc.Str(label)}, target, title or "", pandoc.Attr("", classes, attrs or {}))
  end
  local who = (wiki_real and wiki_note and wiki_note ~= "") and wiki_note or nil   -- e.g. "members": Zulip and wiki by invitation
  if who and (zulip or wiki) then add(note({pandoc.Str("For " .. who .. ":")})) end
  if zulip then
    -- the class zulip-btn is kept for site-check.js; it is styled as the other links
    add(link(ZULIP_ICON, "Discuss on Zulip", zulip,
             "The Zulip topic of this page" .. (who and " (the Zulip is by invitation)" or ""), {"edit-link", "zulip-btn"}))
  end
  if wiki then
    add(link("pencil-square", "This page in the wiki", wiki,
             wiki_real and ("The page in the wiki, where the text is written" .. (who and " (the wiki is by invitation)" or "")) or "",
             {"edit-link"}))
  end
  if propose then
    add(link("journal-plus", "Propose a change", propose, "A new proposal on the talk page of this page in the wiki (members)",
             {"edit-link", "propose-link"}))
  end
  if tex then
    if #inlines > 0 then
      add(pandoc.RawInline("html", '<span class="discuss-sep" aria-hidden="true"></span>'))
    end
    local zip = tex:match("%.zip$")
    add(link("file-earmark-code", "TeX source", tex,
             zip and "A zip with the TeX source of this page and its figures" or "The TeX source of this page",
             {"edit-link", "tex-link"}, {{"download", tex:match("([^/]+)$")}}))
    if pdf then
      add(link("file-earmark-pdf", "PDF", pdf, "The PDF of this page, compiled from its TeX source",
               {"edit-link", "pdf-link"}, {{"download", pdf:match("([^/]+)$")}}))
    end
    if book_pdf then
      add(link("book", "PDF of the whole wiki", book_pdf, "", {"edit-link", "pdf-link"}, {{"download", book_pdf:match("([^/]+)$")}}))
    end
    if book_zip then
      add(link("file-earmark-zip", "TeX of the whole wiki (zip)", book_zip, "", {"edit-link", "tex-link"},
               {{"download", book_zip:match("([^/]+)$")}}))
    end
  end
  if related then
    add(note(related))
  end
  return pandoc.Div({pandoc.Plain(inlines)}, pandoc.Attr("", {"discuss"}))
end

local function div(el)
  if not (zulip or wiki) then return nil end
  if el.classes:includes("module-meta") then
    return {el, links_row()}
  elseif el.classes:includes("discuss") and #el.content == 0 then
    return links_row()
  elseif el.classes:includes("placeholder") and (propose or zulip) then
    el.content:insert(pandoc.Para({
      pandoc.Link({pandoc.Str(propose and "Propose a text →" or "Propose a text on Zulip →")}, propose or zulip, "",
                  pandoc.Attr("", {"propose"}))
    }))
    return el
  end
end

-- A link to an anchor inside a folded box (for instance literature.html#Key, or a proof inside a fold) opens the box
-- (November 2026): Quarto's collapsed callouts do not open by themselves.
local FOLD_SCRIPT = [=[
<script>
(function () {
  function openTarget() {
    var id = decodeURIComponent(location.hash.slice(1)), el = id && document.getElementById(id), opened = false;
    if (!el) return;
    var c = el.closest('.callout-collapse');
    while (c) {
      if (!c.classList.contains('show')) {
        c.classList.add('show'); opened = true;
        var h = c.parentElement && c.parentElement.querySelector(':scope > .callout-header');
        if (h) { h.classList.remove('collapsed'); h.setAttribute('aria-expanded', 'true'); }
      }
      c = c.parentElement && c.parentElement.closest('.callout-collapse');
    }
    if (opened) setTimeout(function () { el.scrollIntoView(); }, 50);
  }
  window.addEventListener('hashchange', openTarget);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', openTarget); else openTarget();
})();
</script>
]=]


-- Reading mode and text size (10 November 2026): the buttons "Reading mode", A- and A+ above "On this page" (on phones:
-- the button "Aa" of the top bar). Reading mode sets the class "reading" on <html> and the text size sets --text-scale
-- there; the styles are in theme.scss. In reading mode on a computer the menu is folded into the button "Menu" at the
-- top left (class "menu-open" on <html> while it is open; not remembered: every page opens with the menu folded). Both are remembered in the browser (localStorage; without it they last for the
-- page only). READING_HEAD runs in the <head>, so that a page opens directly in the chosen mode and size.
-- (12 November 2026) Three more sizes, 160%, 175% and 200% (the largest was 145%); READING_HEAD accepts them.
-- (12 November 2026) The buttons stay under the pointer: a click changes the size of the text or the mode, hence the
-- place of the column of the buttons (in reading mode the column follows the width of the text, and the line of the
-- buttons may fold), so a second click without moving the mouse used to land elsewhere: after A+, on A-. Now the
-- clicked button is put back where it was (keepUnder): the group is held there, fixed in the window (class "held";
-- an empty box of its size keeps its place in the column), while the pointer is on it, and glides back to its place
-- when the pointer leaves (release). It is held after every click, also when nothing moved at once: on tablets the top
-- bar may come back a moment later and push the column down. The buttons themselves no longer grow with the text
-- (theme.scss).
local READING_HEAD = [=[
<script>
(function () { try { var d = document.documentElement, s = window.localStorage, t = parseFloat(s.getItem('wiki-text-scale'));
  if (s.getItem('wiki-reading') === '1') d.classList.add('reading');
  if (t >= 0.8 && t <= 2 && t !== 1) d.style.setProperty('--text-scale', t); } catch (e) {} })();
</script>
]=]

local READING_SCRIPT = [=[
<script>
(function () {
  var R = 'wiki-reading', T = 'wiki-text-scale', STEPS = [0.85, 0.92, 1, 1.1, 1.2, 1.32, 1.45, 1.6, 1.75, 2];
  var root = document.documentElement, panels = [], menuBtn = null;
  // the sizes above 145% (12 November 2026) are offered on tablets and computers only: on a phone long links and
  // titles no longer fit in the width of the screen
  function top() { return window.innerWidth < 768 ? STEPS.indexOf(1.45) : STEPS.length - 1; }
  function put(k, v) { try { window.localStorage.setItem(k, v); } catch (e) {} }
  function step() {
    var s = parseFloat(root.style.getPropertyValue('--text-scale')) || 1, best = 0;
    STEPS.forEach(function (v, i) { if (Math.abs(v - s) < Math.abs(STEPS[best] - s)) best = i; });
    return best;
  }
  // the reader keeps the place: the first visible block stays where it was
  function keepPlace(change) {
    var els = document.querySelectorAll('main h1, main h2, main h3, main h4, main p, main li, main mjx-container[display="true"]'), a = null;
    for (var i = 0; i < els.length; i++) { var r = els[i].getBoundingClientRect(); if (r.height && r.bottom > 0) { a = {el: els[i], top: r.top}; break; } }
    change();
    if (a && window.scrollY > 0) window.scrollBy(0, a.el.getBoundingClientRect().top - a.top);
  }
  function render() {
    var on = root.classList.contains('reading'), i = step(), pct = Math.round(STEPS[i] * 100) + '%';
    panels.forEach(function (p) {
      var b = p.querySelector('.vt-read');
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
      b.querySelector('span').textContent = on ? 'Exit reading mode' : 'Reading mode';
      b.querySelector('i').className = on ? 'bi bi-x-lg' : 'bi bi-book';
      b.title = on ? 'Show the menu and the editing tools again' : 'The text as in a paper: the menu folded away, no editing tools';
      var m = p.querySelector('.vt-minus'), q = p.querySelector('.vt-plus');
      m.disabled = i === 0; q.disabled = i >= top();
      m.title = 'Smaller text (now ' + pct + ')'; q.title = 'Larger text (now ' + pct + ')';
    });
  }
  // reading mode on a computer: the menu is folded into a button at the top left, which opens it beside the text
  function setMenu(open) {
    root.classList.toggle('menu-open', open);
    if (!menuBtn) return;
    menuBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
    menuBtn.querySelector('i').className = open ? 'bi bi-x-lg' : 'bi bi-layout-text-sidebar-reverse';
    menuBtn.querySelector('span').textContent = open ? 'Close' : 'Menu';
  }
  // the buttons stay under the pointer: the group p is held where the clicked button was, until the pointer leaves it
  function shift(p, dx, dy) {
    p.style.left = (parseFloat(p.style.left) + dx) + 'px'; p.style.top = (parseFloat(p.style.top) + dy) + 'px';
  }
  function release(p, now) {
    if (!p.vtHeld) return;
    clearTimeout(p.vtTimer);
    var done = function () {
      p.classList.remove('held', 'gliding'); p.style.left = p.style.top = p.style.width = '';
      if (p.vtSlot) { p.vtSlot.remove(); p.vtSlot = null; p.parentNode.classList.remove('vt-holding'); }
      p.vtHeld = false;
    };
    if (now || !p.vtSlot) { done(); return; }
    var to = p.vtSlot.getBoundingClientRect(), from = p.getBoundingClientRect();
    p.classList.add('gliding'); shift(p, to.left - from.left, to.top - from.top);
    p.vtTimer = setTimeout(done, 220);
  }
  function keepUnder(p, e, change) {
    if (!e.detail && !p.vtHeld) { change(); return; }   // from the keyboard: there is no pointer to stay under
    var b = e.currentTarget, a = b.getBoundingClientRect(), c;
    clearTimeout(p.vtTimer); p.classList.remove('gliding');
    change();
    if (!p.vtHeld) {
      var r = p.getBoundingClientRect(), cs = window.getComputedStyle(p);
      if (cs.position === 'static') {
        p.vtSlot = document.createElement('div');
        p.vtSlot.style.height = r.height + 'px'; p.vtSlot.style.marginBottom = cs.marginBottom;
        p.parentNode.insertBefore(p.vtSlot, p); p.parentNode.classList.add('vt-holding');
      }
      p.style.left = r.left + 'px'; p.style.top = r.top + 'px'; p.style.width = r.width + 'px';
      p.classList.add('held'); p.vtHeld = true;
    }
    for (var k = 0; k < 2; k++) { c = b.getBoundingClientRect(); shift(p, a.left - c.left, a.top - c.top); }
  }
  function setReading(on, p, e) {
    keepUnder(p, e, function () {
      if (!on) setMenu(false);
      keepPlace(function () { root.classList.toggle('reading', on); }); put(R, on ? '1' : '0'); render();
    });
  }
  function setStep(i, p, e) {
    i = Math.max(0, Math.min(i, Math.max(top(), step())));
    keepUnder(p, e, function () {
      keepPlace(function () { if (STEPS[i] === 1) root.style.removeProperty('--text-scale'); else root.style.setProperty('--text-scale', STEPS[i]); });
      put(T, String(STEPS[i])); render();
    });
  }
  function panel() {
    var p = document.createElement('div');
    p.className = 'view-tools'; p.setAttribute('role', 'group'); p.setAttribute('aria-label', 'Reading settings');
    p.innerHTML = '<button type="button" class="vt-read"><i aria-hidden="true"></i><span></span></button>' +
      '<span class="vt-sizes"><button type="button" class="vt-minus" aria-label="Smaller text">A−</button>' +
      '<button type="button" class="vt-plus" aria-label="Larger text">A+</button></span>';
    p.querySelector('.vt-read').addEventListener('click', function (e) { setReading(!root.classList.contains('reading'), p, e); });
    p.querySelector('.vt-minus').addEventListener('click', function (e) { setStep(step() - 1, p, e); });
    p.querySelector('.vt-plus').addEventListener('click', function (e) { setStep(step() + 1, p, e); });
    panels.push(p);
    return p;
  }
  function init() {
    var side = document.getElementById('quarto-margin-sidebar');
    if (side) side.insertBefore(panel(), side.firstChild);
    var bar = document.querySelector('#quarto-header .quarto-secondary-nav .container-fluid');
    if (bar) {
      var open = document.createElement('button'), drop = panel();
      open.type = 'button'; open.className = 'btn vt-open'; open.textContent = 'Aa';
      open.setAttribute('aria-label', 'Reading settings'); open.setAttribute('aria-expanded', 'false');
      bar.insertBefore(open, bar.querySelector('.quarto-search-button'));
      bar.parentElement.style.position = 'relative';
      bar.parentElement.appendChild(drop);
      var show = function (v) { if (!v) release(drop, true); drop.classList.toggle('open', v); open.setAttribute('aria-expanded', v ? 'true' : 'false'); };
      open.addEventListener('click', function (e) { e.stopPropagation(); show(!drop.classList.contains('open')); });
      drop.addEventListener('click', function (e) { e.stopPropagation(); });
      document.addEventListener('click', function () { show(false); });
      document.addEventListener('keydown', function (e) { if (e.key === 'Escape') show(false); });
    }
    var nav = document.getElementById('quarto-sidebar');
    if (nav) {
      menuBtn = document.createElement('button');
      menuBtn.type = 'button'; menuBtn.className = 'vt-menu'; menuBtn.setAttribute('aria-controls', 'quarto-sidebar');
      menuBtn.title = 'The menu of the wiki';
      menuBtn.innerHTML = '<i aria-hidden="true"></i><span></span>';
      document.body.appendChild(menuBtn);
      menuBtn.addEventListener('click', function (e) { e.stopPropagation(); setMenu(!root.classList.contains('menu-open')); });
      document.addEventListener('keydown', function (e) { if (e.key === 'Escape') setMenu(false); });
      // a click on the page closes the menu when it covers the text (narrow windows); beside the text it stays open
      document.addEventListener('click', function (e) {
        if (!root.classList.contains('menu-open') || nav.contains(e.target)) return;
        var m = document.querySelector('main');
        if (m && nav.getBoundingClientRect().right > m.getBoundingClientRect().left) setMenu(false);
      });
      setMenu(false);
    }
    // a held group is let go when the mouse leaves it, at a click or a touch elsewhere, and when the window changes
    document.addEventListener('pointermove', function (e) {
      if (e.pointerType === 'touch') return;
      panels.forEach(function (p) {
        if (!p.vtHeld || p.classList.contains('gliding')) return;
        var r = p.getBoundingClientRect();
        if (e.clientX < r.left - 6 || e.clientX > r.right + 6 || e.clientY < r.top - 6 || e.clientY > r.bottom + 6) release(p);
      });
    });
    document.addEventListener('pointerdown', function (e) { panels.forEach(function (p) { if (!p.contains(e.target)) release(p); }); }, true);
    window.addEventListener('resize', function () { panels.forEach(function (p) { release(p, true); }); render(); });
    render();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
</script>
]=]

-- (11 November 2026) An inline formula stays on the line of the text glued to it: the comma, full stop or bracket
-- after it, the bracket before it, the rest of a word such as "k-mode". For a browser a formula is a box of its own,
-- and it may break the line between the box and the punctuation, which then starts the next line. The formula and
-- the text glued to it (everything up to the next space, on both sides) go into <span class="math-glue">
-- (white-space: nowrap, theme.scss). Only the HTML edition changes: the wiki, the TeX sources and the PDFs do not.
local function is_inline_math(el) return el.t == "Math" and tostring(el.mathtype) == "InlineMath" end
local function glue_math(inlines)
  local out, i, n, changed = pandoc.List(), 1, #inlines, false
  while i <= n do
    local el = inlines[i]
    if is_inline_math(el) then
      local group = pandoc.List()
      if #out > 0 and out[#out].t == "Str" then group:insert(out:remove()) end
      group:insert(el)
      i = i + 1
      while i <= n and (inlines[i].t == "Str" or is_inline_math(inlines[i])) do group:insert(inlines[i]); i = i + 1 end
      if #group > 1 then out:insert(pandoc.Span(group, pandoc.Attr("", {"math-glue"}))); changed = true else out:insert(el) end
    else
      out:insert(el); i = i + 1
    end
  end
  if changed then return out end
end
local function glue_all(doc)
  if quarto and quarto.doc and quarto.doc.is_format and quarto.doc.is_format("html") then
    doc.blocks = doc.blocks:walk({ Inlines = glue_math })
  end
  return doc
end

local function add_script(doc)
  if page_title and ACK_PAGES[page_title] and quarto and quarto.doc and quarto.doc.is_format and quarto.doc.is_format("html") then
    doc.blocks:insert(pandoc.RawBlock("html", ACK_HTML))
  end
  doc.blocks:insert(pandoc.RawBlock("html", FOLD_SCRIPT))
  if quarto and quarto.doc and quarto.doc.is_format and quarto.doc.is_format("html") then
    quarto.doc.include_text("in-header", READING_HEAD)
    doc.blocks:insert(pandoc.RawBlock("html", READING_SCRIPT))
  end
  return doc
end

return { {Meta = read_meta}, {Div = div}, {Pandoc = glue_all}, {Pandoc = add_script} }

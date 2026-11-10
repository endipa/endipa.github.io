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
--   * a "Discuss on Zulip" link, when the page has a Zulip topic (a filled button until 10 November 2026),
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

local zulip, related, wiki, tex, pdf, wiki_note, wiki_real = nil, nil, nil, nil, nil, nil, false
local book_pdf, book_zip = nil, nil
local propose_preload, propose = nil, nil

-- MediaWiki page address: spaces become underscores, other characters are percent-encoded.
local function wiki_title(t)
  t = t:gsub(" ", "_")
  return (t:gsub("[^%w%-%._~/:]", function(c) return string.format("%%%02X", string.byte(c)) end))
end

local function read_meta(m)
  if m.zulip then zulip = pandoc.utils.stringify(m.zulip) end
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
    local i = pandoc.RawInline("html", '<i class="bi bi-' .. icon .. '" aria-hidden="true"></i>')
    return pandoc.Link({i, pandoc.Space(), pandoc.Str(label)}, target, title or "", pandoc.Attr("", classes, attrs or {}))
  end
  local who = (wiki_real and wiki_note and wiki_note ~= "") and wiki_note or nil   -- e.g. "members": Zulip and wiki by invitation
  if who and (zulip or wiki) then add(note({pandoc.Str("For " .. who .. ":")})) end
  if zulip then
    -- the class zulip-btn is kept for site-check.js; it is styled as the other links
    add(link("chat-left-text", "Discuss on Zulip", zulip,
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
local READING_HEAD = [=[
<script>
(function () { try { var d = document.documentElement, s = window.localStorage, t = parseFloat(s.getItem('wiki-text-scale'));
  if (s.getItem('wiki-reading') === '1') d.classList.add('reading');
  if (t >= 0.8 && t <= 1.5 && t !== 1) d.style.setProperty('--text-scale', t); } catch (e) {} })();
</script>
]=]

local READING_SCRIPT = [=[
<script>
(function () {
  var R = 'wiki-reading', T = 'wiki-text-scale', STEPS = [0.85, 0.92, 1, 1.1, 1.2, 1.32, 1.45];
  var root = document.documentElement, panels = [], menuBtn = null;
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
      m.disabled = i === 0; q.disabled = i === STEPS.length - 1;
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
  function setReading(on) {
    if (!on) setMenu(false);
    keepPlace(function () { root.classList.toggle('reading', on); }); put(R, on ? '1' : '0'); render();
  }
  function setStep(i) {
    i = Math.max(0, Math.min(STEPS.length - 1, i));
    keepPlace(function () { if (STEPS[i] === 1) root.style.removeProperty('--text-scale'); else root.style.setProperty('--text-scale', STEPS[i]); });
    put(T, String(STEPS[i])); render();
  }
  function panel() {
    var p = document.createElement('div');
    p.className = 'view-tools'; p.setAttribute('role', 'group'); p.setAttribute('aria-label', 'Reading settings');
    p.innerHTML = '<button type="button" class="vt-read"><i aria-hidden="true"></i><span></span></button>' +
      '<span class="vt-sizes"><button type="button" class="vt-minus" aria-label="Smaller text">A−</button>' +
      '<button type="button" class="vt-plus" aria-label="Larger text">A+</button></span>';
    p.querySelector('.vt-read').addEventListener('click', function () { setReading(!root.classList.contains('reading')); });
    p.querySelector('.vt-minus').addEventListener('click', function () { setStep(step() - 1); });
    p.querySelector('.vt-plus').addEventListener('click', function () { setStep(step() + 1); });
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
      var show = function (v) { drop.classList.toggle('open', v); open.setAttribute('aria-expanded', v ? 'true' : 'false'); };
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
    render();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
</script>
]=]

local function add_script(doc)
  doc.blocks:insert(pandoc.RawBlock("html", FOLD_SCRIPT))
  if quarto and quarto.doc and quarto.doc.is_format and quarto.doc.is_format("html") then
    quarto.doc.include_text("in-header", READING_HEAD)
    doc.blocks:insert(pandoc.RawBlock("html", READING_SCRIPT))
  end
  return doc
end

return { {Meta = read_meta}, {Div = div}, {Pandoc = add_script} }

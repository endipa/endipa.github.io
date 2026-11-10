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
--   * a "Discuss on Zulip" button, when the page has a Zulip topic,
--   * a "This page in the wiki" link: the wiki is where the text is edited; this edition is
--     rebuilt from it by a script and never edited by hand (wiki-note, from edition.json, is added
--     in brackets when the link goes to the real wiki, e.g. "members" for a wiki by invitation),
--   * kit v2.1: a "TeX source" link that downloads the page's TeX source (tex-source in the front
--     matter), a "PDF" link to the PDF compiled from it (pdf-source), and, on the Overview only, "PDF of the whole wiki" and "TeX of the whole
--     wiki (zip)": tex/all-pages.zip, a LaTeX project with main.tex and every page as a file of pages/ (it also opens in
--     Overleaf; November 2026: no "Open in Overleaf" button any more); on a page with pictures, "TeX source" downloads a zip
--     (the .tex and the folder figures/),
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
  local inlines = {}
  if zulip then
    local icon = pandoc.RawInline("html", '<i class="bi bi-chat-left-text" aria-hidden="true"></i>')
    table.insert(inlines, pandoc.Link({icon, pandoc.Space(), pandoc.Str("Discuss on Zulip")},
                                      zulip, "", pandoc.Attr("", {"zulip-btn"})))
    table.insert(inlines, pandoc.Space())
    table.insert(inlines, note({pandoc.Str("For project members: the Zulip and the wiki are by invitation.")}))
  end
  if wiki then
    local icon = pandoc.RawInline("html", '<i class="bi bi-pencil-square" aria-hidden="true"></i>')
    table.insert(inlines, pandoc.Space())
    local label = "This page in the wiki"
    if wiki_real and wiki_note and wiki_note ~= "" then label = label .. " (" .. wiki_note .. ")" end
    table.insert(inlines, pandoc.Link({icon, pandoc.Space(), pandoc.Str(label)},
                                      wiki, "", pandoc.Attr("", {"edit-link"})))
  end
  if propose then
    local iconp = pandoc.RawInline("html", '<i class="bi bi-journal-plus" aria-hidden="true"></i>')
    table.insert(inlines, pandoc.Space())
    table.insert(inlines, pandoc.Link({iconp, pandoc.Space(), pandoc.Str("Propose a change")}, propose,
                                      "A new proposal on the talk page of this page in the wiki (members)",
                                      pandoc.Attr("", {"edit-link", "propose-link"})))
  end
  if tex then
    local icon = pandoc.RawInline("html", '<i class="bi bi-file-earmark-code" aria-hidden="true"></i>')
    table.insert(inlines, pandoc.Space())
    local file = tex:match("([^/]+)$")
    local label = tex:match("%.zip$") and "TeX source (zip, with figures)" or "TeX source"
    table.insert(inlines, pandoc.Link({icon, pandoc.Space(), pandoc.Str(label)}, tex, "",
                                      pandoc.Attr("", {"edit-link", "tex-link"}, {{"download", file}})))
    if pdf then
      local iconp = pandoc.RawInline("html", '<i class="bi bi-file-earmark-pdf" aria-hidden="true"></i>')
      table.insert(inlines, pandoc.Space())
      table.insert(inlines, pandoc.Link({iconp, pandoc.Space(), pandoc.Str("PDF")}, pdf, "",
                                        pandoc.Attr("", {"edit-link", "pdf-link"}, {{"download", pdf:match("([^/]+)$")}})))
    end
    if book_pdf then
      local iconb = pandoc.RawInline("html", '<i class="bi bi-book" aria-hidden="true"></i>')
      table.insert(inlines, pandoc.Space())
      table.insert(inlines, pandoc.Link({iconb, pandoc.Space(), pandoc.Str("PDF of the whole wiki")}, book_pdf, "",
                                        pandoc.Attr("", {"edit-link", "pdf-link"}, {{"download", book_pdf:match("([^/]+)$")}})))
    end
    if book_zip then
      local icon2 = pandoc.RawInline("html", '<i class="bi bi-file-earmark-zip" aria-hidden="true"></i>')
      table.insert(inlines, pandoc.Space())
      table.insert(inlines, pandoc.Link({icon2, pandoc.Space(), pandoc.Str("TeX of the whole wiki (zip)")}, book_zip, "",
                                        pandoc.Attr("", {"edit-link", "tex-link"}, {{"download", book_zip:match("([^/]+)$")}})))
    end
  end
  if related then
    table.insert(inlines, pandoc.Space())
    table.insert(inlines, note(related))
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

local function add_script(doc)
  doc.blocks:insert(pandoc.RawBlock("html", FOLD_SCRIPT))
  return doc
end

return { {Meta = read_meta}, {Div = div}, {Pandoc = add_script} }

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
--   * a "Discuss or propose a change on Zulip" button, when the page has a Zulip topic,
--   * a "This page in the wiki" link: the wiki is where the text is edited; this edition is
--     rebuilt from it by a script and never edited by hand (wiki-note, from edition.json, is added
--     in brackets when the link goes to the real wiki, e.g. "members" for a wiki by invitation),
--   * kit v2.1: a "TeX source" link that downloads the page's TeX source (tex-source in the front
--     matter), a "PDF" link to the PDF compiled from it (pdf-source), and, on the Overview only, "PDF of the whole wiki" and "Open the whole wiki in Overleaf": a new
--     project with whole-wiki.tex as main document and every page as a file (Overleaf fetches tex/all-pages.zip:
--     public site only),
-- and a "Propose a text on Zulip" link at the end of every placeholder (pages with a Zulip topic).

local zulip, related, wiki, tex, pdf, wiki_note, wiki_real = nil, nil, nil, nil, nil, nil, false
local book_pdf, book_zip = nil, nil

local OVERLEAF_SCRIPT = [=[
<script>
(function () {
  // Open the whole wiki in Overleaf: one project with whole-wiki.tex (main document) and the TeX file of every page
  // (tex/all-pages.zip). Overleaf downloads the zip itself, so this works on the public site only.
  document.querySelectorAll('a.overleaf-link').forEach(function (a) {
    var zip = new URL(a.getAttribute('data-zip'), window.location.href).href;
    a.href = 'https://www.overleaf.com/docs?engine=pdflatex&main_document=' + encodeURIComponent(a.getAttribute('data-main'))
      + '&snip_uri=' + encodeURIComponent(zip);
  });
})();
</script>
]=]

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
  if m["wiki-url"] then
    local base = pandoc.utils.stringify(m["wiki-url"])
    if m["wiki-page"] and base:match("^https?://") then
      -- the real wiki: link to the page by its title
      wiki = base .. wiki_title(pandoc.utils.stringify(m["wiki-page"]))
      wiki_real = true
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
    table.insert(inlines, pandoc.Link({icon, pandoc.Space(), pandoc.Str("Discuss or propose a change on Zulip")},
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
  if tex then
    local icon = pandoc.RawInline("html", '<i class="bi bi-file-earmark-code" aria-hidden="true"></i>')
    table.insert(inlines, pandoc.Space())
    local file = tex:match("([^/]+)$")
    table.insert(inlines, pandoc.Link({icon, pandoc.Space(), pandoc.Str("TeX source")}, tex, "",
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
      local icon2 = pandoc.RawInline("html", '<i class="bi bi-box-arrow-up-right" aria-hidden="true"></i>')
      table.insert(inlines, pandoc.Space())
      table.insert(inlines, pandoc.Link({icon2, pandoc.Space(), pandoc.Str("Open the whole wiki in Overleaf")}, book_zip, "",
                                        pandoc.Attr("", {"edit-link", "overleaf-link"},
                                                    {{"data-zip", book_zip}, {"data-main", "whole-wiki.tex"},
                                                     {"target", "_blank"}, {"rel", "noopener"}})))
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
  elseif el.classes:includes("placeholder") and zulip then
    el.content:insert(pandoc.Para({
      pandoc.Link({pandoc.Str("Propose a text on Zulip →")}, zulip, "", pandoc.Attr("", {"propose"}))
    }))
    return el
  end
end

local function add_script(doc)
  if book_zip then doc.blocks:insert(pandoc.RawBlock("html", OVERLEAF_SCRIPT)) end
  return doc
end

return { {Meta = read_meta}, {Div = div}, {Pandoc = add_script} }

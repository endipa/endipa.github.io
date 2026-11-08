/* Navigation tree in the main menu (wiki kit, 2026; script drafted by Claude, AI).
 * Every page listed in MediaWiki:Sidebar gets a triangle that expands it into its sections
 * (== headings ==) and the boxes it contains: results ({{Theorem start}}), levels ({{Level start}})
 * and proofs ({{Proof start}}). Sections expand in turn. The current page is open.
 * The sidebar may have several parts; every page link in the main menu gets a tree.
 * The tree is read from the pages' wikitext with one API call and cached in the browser per revision.
 * Works with any article path (/wiki/Title, /index.php/Title, /index.php?title=Title); when it is done
 * it sets data-navtree on <html> ("ready" or "none"), which the static export waits for.
 */
(function () {
	'use strict';
	var CACHE_KEY = 'navtree-v2';

	function plain(s) {
		return String(s)
			.replace(/<math[^>]*>[\s\S]*?<\/math>/g, '…')
			.replace(/\{\{[^{}]*\}\}/g, '')
			.replace(/\[\[(?:[^\]|]*\|)?([^\]]*)\]\]/g, '$1')
			.replace(/'{2,}/g, '')
			.replace(/<[^>]+>/g, '')
			.replace(/\s+/g, ' ')
			.trim();
	}

	function param(call, name) {
		var m = call.match(new RegExp('\\|\\s*' + name + '\\s*=([^|}]*)'));
		return m ? m[1].trim() : '';
	}

	function entries(text) {
		text = text.replace(/<nowiki>[\s\S]*?<\/nowiki>/g, '').replace(/<!--[\s\S]*?-->/g, '');
		var root = { children: [], level: 0 }, stack = [root];
		text.split('\n').forEach(function (line) {
			var h = line.match(/^(={2,4})\s*(.+?)\s*\1\s*$/), node, label, t,
				re = /\{\{\s*(Theorem start|Level start|Proof start)\s*((?:\|[^{}]*)?)\}\}/g;
			if (h) {
				label = plain(h[2]);
				node = { label: label, anchor: label, kind: 'section', level: h[1].length - 1, children: [] };
				while (stack.length > 1 && stack[stack.length - 1].level >= node.level) { stack.pop(); }
				stack[stack.length - 1].children.push(node);
				stack.push(node);
				return;
			}
			while ((t = re.exec(line)) !== null) {
				if (t[1] === 'Theorem start') {
					label = plain(param(t[0], 'title')).replace(/\.$/, '');
					node = { label: label, anchor: param(t[0], 'id'), kind: 'result', children: [] };
				} else if (t[1] === 'Level start') {
					label = plain(param(t[0], 'title')) || 'Idea';
					node = { label: label, anchor: param(t[0], 'id') || label, kind: 'level', children: [] };
				} else {
					label = plain(param(t[0], 'title')) || 'Proof';
					node = { label: label, anchor: param(t[0], 'id') || 'Proof', kind: 'proof', children: [] };
				}
				if (node.anchor) { stack[stack.length - 1].children.push(node); }
			}
		});
		return root.children;
	}

	function toggle(li, open) {
		var b = document.createElement('button');
		b.type = 'button';
		b.className = 'navtree-toggle';
		b.setAttribute('aria-expanded', open ? 'true' : 'false');
		b.setAttribute('aria-label', open ? 'Collapse' : 'Expand');
		b.addEventListener('click', function (e) {
			var isOpen;
			e.preventDefault();
			e.stopPropagation();
			isOpen = !li.classList.contains('navtree-open');
			li.classList.toggle('navtree-open', isOpen);
			li.classList.toggle('navtree-closed', !isOpen);
			b.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
			b.setAttribute('aria-label', isOpen ? 'Collapse' : 'Expand');
		});
		return b;
	}

	function buildList(items, title) {
		var ul = document.createElement('ul');
		ul.className = 'navtree-list';
		items.forEach(function (it) {
			var li = document.createElement('li'), a = document.createElement('a');
			li.className = 'navtree-item navtree-' + it.kind;
			a.href = mw.util.getUrl(title) + '#' + mw.util.escapeIdForLink(it.anchor);
			a.textContent = it.label;
			if (it.children && it.children.length) {
				li.classList.add('navtree-closed');
				li.appendChild(toggle(li, false));
				li.appendChild(a);
				li.appendChild(buildList(it.children, title));
			} else {
				li.classList.add('navtree-leaf');
				li.appendChild(a);
			}
			ul.appendChild(li);
		});
		return ul;
	}

	function titleOf(href) {
		var prefix = mw.config.get('wgArticlePath').split('$1')[0], t;
		if (!href) { return null; }
		t = mw.util.getParamValue('title', href);
		if (!t && href.indexOf(prefix) === 0) { t = href.slice(prefix.length).split(/[?#]/)[0]; }
		return t ? decodeURIComponent(t).replace(/_/g, ' ') : null;
	}

	function sidebarPages() {
		var out = [];
		$('#vector-main-menu, #mw-panel').find('li[id^="n-"]').each(function () {
			var a = this.querySelector('a'), title = a && titleOf(a.getAttribute('href'));
			if (title) { out.push({ li: this, title: title }); }
		});
		return out;
	}

	function load(titles) {
		var api = new mw.Api(), cache = null;
		try { cache = JSON.parse(window.localStorage.getItem(CACHE_KEY) || 'null'); } catch (e) {}
		return api.get({ action: 'query', prop: 'info', titles: titles.join('|'), formatversion: 2 }).then(function (r) {
			var revs = {};
			(r.query.pages || []).forEach(function (p) { revs[p.title] = p.lastrevid || 0; });
			if (cache && JSON.stringify(cache.revs) === JSON.stringify(revs)) { return cache.tree; }
			return api.get({ action: 'query', prop: 'revisions', rvprop: 'content', rvslots: 'main', titles: titles.join('|'), formatversion: 2 }).then(function (r2) {
				var tree = {};
				(r2.query.pages || []).forEach(function (p) {
					if (p.revisions) { tree[p.title] = entries(p.revisions[0].slots.main.content); }
				});
				try { window.localStorage.setItem(CACHE_KEY, JSON.stringify({ revs: revs, tree: tree })); } catch (e) {}
				return tree;
			});
		});
	}

	$(function () {
		var pages = [], done = function (state) { document.documentElement.setAttribute('data-navtree', state); };
		mw.loader.using(['mediawiki.api', 'mediawiki.util']).then(function () {
			// a part of the menu with one page of the same name shows the page only (kit v2.1)
			$('#vector-main-menu .mw-portlet, #mw-panel .mw-portlet').each(function () {
				var items = this.querySelectorAll('li[id^="n-"]'), head = this.querySelector('.vector-menu-heading, h3'),
					a = items.length === 1 ? items[0].querySelector('a') : null;
				if (a && head && head.textContent.trim() === a.textContent.trim()) { this.classList.add('navtree-single'); }
			});
			pages = sidebarPages();
			return pages.length ? load(pages.map(function (x) { return x.title; })) : null;
		}).then(function (tree) {
			var here = mw.config.get('wgNamespaceNumber') === 0 ? mw.config.get('wgTitle') : null;
			if (!tree) { done('none'); return; }
			pages.forEach(function (x) {
				var list = tree[x.title], open = (x.title === here);
				if (!list || !list.length) { x.li.classList.add('navtree-page', 'navtree-leaf'); return; }
				x.li.classList.add('navtree-page', open ? 'navtree-open' : 'navtree-closed');
				if (open) { x.li.classList.add('navtree-current'); }
				x.li.insertBefore(toggle(x.li, open), x.li.firstChild);
				x.li.appendChild(buildList(list, x.title));
			});
			done('ready');
		}, function () { done('none'); });
	});
}());

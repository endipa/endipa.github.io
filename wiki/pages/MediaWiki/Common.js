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

/* Proposal boxes (wiki kit, November 2026; drafted by Claude, AI).
 * The box of an open proposal ({{Proposal}}, on a talk page) gets a text field and buttons: Support, Oppose and Comment
 * for everyone who can edit the page, which add the text as a signed reply at the end of the topic; Accept and Decline
 * for editors, which also change status=open in the first line of the topic to status=accepted (or declined). A declined
 * topic is then moved to the subpage /Archive of the talk page (accepted ones are moved there once applied). The box
 * counts the Support and Oppose replies. Everything can also be done by hand, by editing the topic.
 */
(function () {
	'use strict';
	var EDITORS = ['editor', 'sysop', 'bureaucrat'];
	var groups = mw.config.get('wgUserGroups') || [];
	var isEditor = groups.some(function (g) { return EDITORS.indexOf(g) >= 0; });
	if (mw.config.get('wgAction') !== 'view' || !mw.config.get('wgUserName') || !mw.config.get('wgIsProbablyEditable')) {
		return;
	}
	var LABEL = { support: 'Support.', oppose: 'Oppose.', comment: '', accepted: 'Accepted.', declined: 'Declined.' };
	// the topic of a box: the last section edit link before it in the page
	function topicOf(box) {
		var links = document.querySelectorAll('.mw-editsection a[href*="section="]'), found = null;
		Array.prototype.forEach.call(links, function (a) {
			if (a.compareDocumentPosition(box) & Node.DOCUMENT_POSITION_FOLLOWING) {
				found = a;
			}
		});
		if (!found) {
			return null;
		}
		var section = new URL(found.href, location.href).searchParams.get('section');
		var head = found.closest('.mw-heading, h2');
		var h = head && (head.querySelector('.mw-headline') || head.querySelector('h2') || head);
		return /^\d+$/.test(section) ? { section: section, heading: h ? h.textContent.trim() : '' } : null;
	}
	// the lines of a topic (level-2 heading) in the wikitext of a talk page
	function topicBounds(text, heading) {
		var lines = text.split('\n'), start = -1, end = lines.length, i, m;
		for (i = 0; i < lines.length; i++) {
			m = lines[i].match(/^==(?!=)\s*(.*?)\s*==\s*$/);
			if (m) {
				if (start >= 0) {
					end = i;
					break;
				}
				if (m[1] === heading) {
					start = i;
				}
			}
		}
		return start < 0 ? null : { lines: lines, start: start, end: end };
	}
	// move a decided topic to the subpage /Archive of the talk page
	function archive(api, title, heading) {
		var talk = title.replace(/_/g, ' '), arch = talk + '/Archive';
		return api.get({ action: 'query', titles: talk + '|' + arch, prop: 'revisions', rvprop: 'content|timestamp',
			rvslots: 'main', formatversion: 2 }).then(function (r) {
			var revs = {};
			r.query.pages.forEach(function (p) {
				revs[p.title] = p.missing ? null : p.revisions[0];
			});
			var cur = revs[talk], old = revs[arch], b = cur && topicBounds(cur.slots.main.content, heading);
			if (!b) {
				return null;
			}
			var topic = b.lines.slice(b.start, b.end).join('\n').replace(/\s+$/, '');
			var before = b.lines.slice(0, b.start).join('\n').replace(/\s+$/, ''), after = b.lines.slice(b.end).join('\n');
			var head = 'Proposals for [[' + talk.replace(/^Talk:/, '') + ']] that were applied or declined, moved here from [['
				+ talk + ']], oldest first. New proposals and replies go on the talk page.';
			var p = { action: 'edit', title: arch, text: (old ? old.slots.main.content.replace(/\s+$/, '') : head) + '\n\n' + topic,
				summary: 'Archived from [[' + talk + ']]: ' + heading };
			if (old) {
				p.basetimestamp = old.timestamp;
				p.nocreate = 1;
			} else {
				p.createonly = 1;
			}
			return api.postWithEditToken(p).then(function () {
				return api.postWithEditToken({ action: 'edit', title: talk, text: before + (after ? '\n\n' + after : ''), nocreate: 1,
					basetimestamp: cur.timestamp, summary: 'Archived to [[' + arch + ']]: ' + heading });
			});
		});
	}
	// the Support and Oppose replies of a topic, as shown on the page: after the box, up to the next heading
	function tally(box) {
		var n = { support: 0, oppose: 0 }, el = box.nextElementSibling;
		while (el && !(el.classList.contains('mw-heading') || /^H[1-6]$/.test(el.tagName))) {
			Array.prototype.forEach.call(el.querySelectorAll('dd > b:first-child'), function (b) {
				var w = b.textContent.trim();
				if (w === 'Support.') {
					n.support++;
				} else if (w === 'Oppose.') {
					n.oppose++;
				}
			});
			el = el.nextElementSibling;
		}
		return n;
	}
	function act(topic, kind, text, msg) {
		var api = new mw.Api(), title = mw.config.get('wgPageName'), heading = topic.heading;
		var decision = kind === 'accepted' || kind === 'declined';
		msg.textContent = 'Saving…';
		api.get({ action: 'query', titles: title, prop: 'revisions', rvprop: 'content|timestamp', rvslots: 'main',
			rvsection: topic.section, formatversion: 2 }).then(function (r) {
			var rev = r.query.pages[0].revisions[0], src = rev.slots.main.content, neu = src;
			var hm = src.match(/^==(?!=)\s*(.*?)\s*==\s*$/m);
			heading = hm ? hm[1] : heading;
			if (decision) {
				neu = src.replace(/(\{\{\s*Proposal\s*\|[^{}]*?)status\s*=\s*open\b/, '$1status=' + kind);
				if (neu === src) {
					msg.textContent = 'This topic no longer says status=open: reload the page.';
					return null;
				}
			}
			var label = LABEL[kind] ? "'''" + LABEL[kind] + "'''" + (text ? ' ' : '') : '';
			neu = neu.replace(/\s+$/, '') + '\n:' + label + text + ' ~~' + '~~';
			return api.postWithEditToken({ action: 'edit', title: title, section: topic.section, text: neu, nocreate: 1,
				basetimestamp: rev.timestamp, summary: '/* ' + heading + ' */ ' + (decision ? 'proposal ' + kind : kind) });
		}).then(function (res) {
			if (res && kind === 'declined') {
				msg.textContent = 'Declined; moving the topic to the archive…';
				return archive(api, title, heading).then(function () {
					return res;
				});
			}
			return res;
		}).then(function (res) {
			if (res) {
				location.reload();
			}
		}, function (code) {
			msg.textContent = 'Not saved (' + code + '): reload the page and try again.';
		});
	}
	mw.hook('wikipage.content').add(function ($content) {
		$content.find('.proposal-box.proposal-open').each(function () {
			var box = this, topic = topicOf(box);
			if (!topic || box.querySelector('.proposal-decide')) {
				return;
			}
			var n = tally(box), form = document.createElement('div');
			form.className = 'proposal-decide';
			form.innerHTML = '<span class="proposal-tally">Support ' + n.support + ' · Oppose ' + n.oppose + '</span>'
				+ '<input type="text" maxlength="1000" placeholder="Your reply or reason (signed automatically)">'
				+ '<button type="button" data-kind="support">Support</button>'
				+ '<button type="button" data-kind="oppose">Oppose</button>'
				+ '<button type="button" data-kind="comment">Comment</button>'
				+ (isEditor ? '<span class="proposal-editor"><button type="button" data-kind="accepted">Accept</button>'
					+ '<button type="button" data-kind="declined">Decline</button></span>' : '')
				+ '<span class="proposal-decide-msg"></span>';
			var input = form.querySelector('input'), msg = form.querySelector('.proposal-decide-msg');
			Array.prototype.forEach.call(form.querySelectorAll('button'), function (b) {
				b.addEventListener('click', function () {
					var kind = b.getAttribute('data-kind'), text = input.value.trim();
					if (kind === 'comment' && !text) {
						msg.textContent = 'Write the comment in the field first.';
						return;
					}
					Array.prototype.forEach.call(form.querySelectorAll('button'), function (x) { x.disabled = true; });
					act(topic, kind, text, msg);
				});
			});
			box.appendChild(form);
		});
	});
}());

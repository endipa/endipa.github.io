// proposals.js: the proposals on the talk pages of the wiki, from the browser (wiki kit, November 2026).
//
// The wiki has a copy as MediaWiki:Proposals.js: on any page of the wiki, logged in as an editor, load it with
//   await mw.loader.getScript('/w/index.php?title=MediaWiki:Proposals.js&action=raw&ctype=text/javascript')
// (or paste this file in the browser console). It defines window.Proposals:
//   await Proposals.list('accepted')   the accepted proposals (or 'open', 'applied', 'declined'): for each, the talk
//                                      page and its page, the heading of the topic, the paragraph id (proposals made
//                                      with the edit button of the edition), the author (who opened the topic), the
//                                      acceptor (who changed the status to accepted) and the acceptor's groups,
//                                      eligible (the acceptor is an editor), the wikitext of the topic and its SHA-1
//   await Proposals.save(page, text, sha1, summary)
//                                      writes the new text of a page (from wikitex.py apply-proposal --write), if its
//                                      SHA-1 is the expected one, and checks the saved text; returns the new revision
//   await Proposals.markApplied(talk, heading, revid)
//                                      changes status=accepted to status=applied|revision=<revid> in the box of the topic
//   await Proposals.archive(talk, heading)
//                                      moves an applied or declined topic to the subpage <talk>/Archive
//   Proposals.summary(p)               the edit summary of the page: the topic, its author and its acceptor
// The editor copies the wikitext of the topic to a file (and checks its SHA-1), runs
//   python3 wikitex.py apply-proposal <pages-dir> <page> <topic.wiki> [--write]
// and saves the page and the status with the two functions above. See RUNBOOK.md, "Proposals".
(function () {
  var EDITOR_GROUPS = ['editor', 'sysop', 'bureaucrat'];
  var api = function () { return new mw.Api(); };
  function sha1(s) {
    return crypto.subtle.digest('SHA-1', new TextEncoder().encode(s)).then(function (b) {
      return Array.from(new Uint8Array(b)).map(function (x) { return x.toString(16).padStart(2, '0'); }).join('');
    });
  }
  // the level-2 topics of a talk page: [{heading, start, end, text}]
  function topics(text) {
    var lines = text.split('\n'), out = [], cur = null;
    lines.forEach(function (l, i) {
      var m = l.match(/^==(?!=)\s*(.*?)\s*==\s*$/);
      if (m) { if (cur) { cur.end = i; out.push(cur); } cur = {heading: m[1], start: i}; }
    });
    if (cur) { cur.end = lines.length; out.push(cur); }
    out.forEach(function (t) { t.text = lines.slice(t.start, t.end).join('\n').replace(/\n+$/, ''); });
    return out;
  }
  function box(text) {
    var m = text.match(/\{\{\s*Proposal\s*\|([^{}]*)\}\}/);
    if (!m) return null;
    var p = {};
    m[1].split('|').forEach(function (x) { var k = x.split('='); p[k[0].trim().toLowerCase()] = k.slice(1).join('=').trim(); });
    p.status = (p.status || 'open').toLowerCase();
    return p;
  }
  async function history(title) {
    var revs = [], cont = {};
    for (;;) {
      var r = await api().get(Object.assign({action: 'query', titles: title, prop: 'revisions', rvprop: 'ids|user|timestamp|content',
        rvslots: 'main', rvdir: 'newer', rvlimit: 50, formatversion: 2}, cont));
      (r.query.pages[0].revisions || []).forEach(function (v) { revs.push({revid: v.revid, user: v.user, timestamp: v.timestamp, text: v.slots.main.content}); });
      if (!r.continue) return revs;
      cont = r.continue;
    }
  }
  async function current(title) {
    var r = await api().get({action: 'query', titles: title, prop: 'revisions', rvprop: 'ids|timestamp|sha1|content', rvslots: 'main', formatversion: 2});
    var p = r.query.pages[0];
    if (p.missing) return null;
    var v = p.revisions[0];
    return {revid: v.revid, timestamp: v.timestamp, sha1: v.sha1, text: v.slots.main.content};
  }
  async function groups(users) {
    if (!users.length) return {};
    var r = await api().get({action: 'query', list: 'users', ususers: users.join('|'), usprop: 'groups', formatversion: 2});
    var g = {};
    r.query.users.forEach(function (u) { g[u.name] = (u.groups || []).filter(function (x) { return x !== '*' && x !== 'user' && x !== 'autoconfirmed'; }); });
    return g;
  }
  async function list(status) {
    status = (status || 'accepted').toLowerCase();
    var cat = 'Category:' + status.charAt(0).toUpperCase() + status.slice(1) + ' proposals';
    var r = await api().get({action: 'query', list: 'categorymembers', cmtitle: cat, cmlimit: 'max', formatversion: 2});
    var out = [];
    for (var m of r.query.categorymembers) {
      var talk = m.title, revs = await history(talk), last = revs[revs.length - 1];
      for (var t of topics(last.text)) {
        var p = box(t.text);
        if (!p || p.status !== status) continue;
        var author = null, acceptor = null, prev = null;
        revs.forEach(function (v) {
          var s = topics(v.text).filter(function (x) { return x.heading === t.heading; })[0];
          var st = s && box(s.text) ? box(s.text).status : null;
          if (s && !author) author = v.user;
          if (st === 'accepted' && prev !== 'accepted') acceptor = {user: v.user, revid: v.revid, timestamp: v.timestamp};
          prev = st;
        });
        out.push({talk: talk, page: talk.replace(/^Talk:/, ''), heading: t.heading, status: p.status, paragraph: p.paragraph || '',
                  author: author, acceptor: acceptor, text: t.text, sha1: await sha1(t.text), talkRevid: last.revid});
      }
    }
    var users = Array.from(new Set(out.map(function (p) { return p.acceptor && p.acceptor.user; }).filter(Boolean)));
    var g = await groups(users);
    out.forEach(function (p) {
      p.acceptorGroups = p.acceptor ? (g[p.acceptor.user] || []) : [];
      p.eligible = p.acceptorGroups.some(function (x) { return EDITOR_GROUPS.indexOf(x) >= 0; });
      p.selfAccepted = !!(p.acceptor && p.acceptor.user === p.author);
    });
    return out;
  }
  async function save(page, text, want, summary) {
    var cur = await current(page);
    if (!cur) throw new Error('no page ' + page);
    var h = await sha1(text);
    if (h !== want) throw new Error('the text has SHA-1 ' + h + ', not ' + want + ': it was not copied exactly');
    var r = await api().postWithEditToken({action: 'edit', title: page, text: text, summary: summary, basetimestamp: cur.timestamp, nocreate: 1});
    var after = await current(page);
    return {result: r.edit.result, revid: after.revid, verified: after.sha1 === want};
  }
  async function markApplied(talk, heading, revid) {
    var cur = await current(talk), lines = cur.text.split('\n');
    var t = topics(cur.text).filter(function (x) { return x.heading === heading; })[0];
    if (!t) throw new Error('no topic "' + heading + '" on ' + talk);
    var body = lines.slice(t.start, t.end).join('\n');
    var neu = body.replace(/(\{\{\s*Proposal\s*\|[^{}]*?)status\s*=\s*accepted([^{}]*\}\})/, '$1status=applied|revision=' + revid + '$2');
    if (neu === body) throw new Error('the box of "' + heading + '" does not say status=accepted');
    var text = lines.slice(0, t.start).join('\n') + (t.start ? '\n' : '') + neu + (t.end < lines.length ? '\n' + lines.slice(t.end).join('\n') : '');
    var r = await api().postWithEditToken({action: 'edit', title: talk, text: text, basetimestamp: cur.timestamp, nocreate: 1,
      summary: '/* ' + heading + ' */ applied: [[Special:Diff/' + revid + ']]'});
    return r.edit.result;
  }
  async function archive(talk, heading) {
    var cur = await current(talk), lines = cur.text.split('\n');
    var t = topics(cur.text).filter(function (x) { return x.heading === heading; })[0];
    if (!t) throw new Error('no topic "' + heading + '" on ' + talk);
    var st = (box(t.text) || {}).status;
    if (st !== 'applied' && st !== 'declined') throw new Error('"' + heading + '" is ' + st + ': only applied or declined proposals are archived');
    var arch = talk + '/Archive', old = await current(arch);
    var head = 'Proposals for [[' + talk.replace(/^Talk:/, '') + ']] that were applied or declined, moved here from [[' + talk
      + ']], oldest first. New proposals and replies go on the talk page.';
    var p = {action: 'edit', title: arch, text: (old ? old.text.replace(/\s+$/, '') : head) + '\n\n' + t.text,
             summary: 'Archived from [[' + talk + ']]: ' + heading};
    if (old) { p.basetimestamp = old.timestamp; p.nocreate = 1; } else { p.createonly = 1; }
    await api().postWithEditToken(p);
    var before = lines.slice(0, t.start).join('\n').replace(/\s+$/, ''), after = lines.slice(t.end).join('\n');
    var r = await api().postWithEditToken({action: 'edit', title: talk, text: before + (after ? '\n\n' + after : ''), nocreate: 1,
      basetimestamp: cur.timestamp, summary: 'Archived to [[' + arch + ']]: ' + heading});
    return r.edit.result;
  }
  function summary(p) {
    var who = function (u) { return u ? '[[User:' + u + '|' + u + ']]' : 'unknown'; };
    return 'Proposal by ' + who(p.author) + ', accepted by ' + who(p.acceptor && p.acceptor.user) + ': [[' + p.talk + '/Archive#' + p.heading + '|discussion]]';   // the topic is archived once applied
  }
  window.Proposals = {list: list, save: save, markApplied: markApplied, archive: archive, summary: summary, topics: topics, box: box, sha1: sha1};
})();

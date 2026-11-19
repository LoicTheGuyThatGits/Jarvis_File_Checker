/* Settings > Notes: the notes Jarvis took ("note that ..."). They live in the Jarvis program on this PC. */
(function () {
  'use strict';
  function $(id) { return document.getElementById(id); }
  if (!$('notes-list')) return;
  var timer = null;
  function api(path, body) {
    var opts = body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined;
    return fetch(path, opts).then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || 'Request failed'); return d; }); });
  }
  function when(ts) {
    var d = new Date(ts * 1000), now = new Date(), day = Math.round((new Date(now.getFullYear(), now.getMonth(), now.getDate()) - new Date(d.getFullYear(), d.getMonth(), d.getDate())) / 86400000);
    if (day === 0) return 'today'; if (day === 1) return 'yesterday';
    return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: d.getFullYear() === now.getFullYear() ? undefined : 'numeric' });
  }
  function show(d) {
    var list = $('notes-list'); list.textContent = '';
    d.notes.forEach(function (n) {
      var li = document.createElement('li'); li.className = 'tool-item';
      var t = document.createElement('span'); t.className = 'tool-text'; t.textContent = n.text + '  (' + when(n.created) + ')'; li.appendChild(t);
      var x = document.createElement('button'); x.type = 'button'; x.className = 'plan-del'; x.textContent = '✕'; x.setAttribute('aria-label', 'Delete note');
      x.addEventListener('click', function () { send('/api/notes/delete', { id: n.id }); }); li.appendChild(x);
      list.appendChild(li);
    });
    if (!d.notes.length) { var e = document.createElement('li'); e.className = 'tool-item'; e.textContent = $('notes-find').value.trim() ? 'No note matches that.' : 'No notes yet.'; list.appendChild(e); }
  }
  function load() { api('/api/notes' + ($('notes-find').value.trim() ? '?q=' + encodeURIComponent($('notes-find').value.trim()) : '')).then(show).catch(function () {}); }
  function send(path, body) { return api(path, body).then(function () { $('notes-status').textContent = ''; load(); }).catch(function (e) { $('notes-status').textContent = e.message; }); }
  $('notes-add').addEventListener('click', function () {
    if (!$('notes-text').value.trim()) return;
    send('/api/notes/add', { text: $('notes-text').value }).then(function () { if (!$('notes-status').textContent) $('notes-text').value = ''; });
  });
  $('notes-text').addEventListener('keydown', function (e) { if (e.key === 'Enter') $('notes-add').click(); });
  $('notes-find').addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(load, 200); });
  function showStudy(d) {
    var done = d.sessions || [], asked = 0, right = 0; done.forEach(function (x) { asked += x.asked; right += x.correct; });
    $('study-stats').textContent = (done.length ? 'Last ' + done.length + ' sessions: ' + right + ' of ' + asked + ' right. ' : 'No quiz done yet. ') + (d.missed ? d.missed + ' missed question' + (d.missed === 1 ? '' : 's') + ' waiting.' : '');
    $('study-clear').disabled = !d.missed;
    var dk = d.deck || { total: 0, due: 0, learned: 0 }, today = new Date().toISOString().slice(0, 10);
    $('deck-stats').textContent = dk.total ? dk.due + ' card' + (dk.due === 1 ? '' : 's') + ' due today, ' + dk.total + ' in the deck, ' + dk.learned + ' well learned.' + (!dk.due && dk.next ? ' Next due ' + dk.next + '.' : '') : 'The deck is empty.';
    $('deck-review').disabled = !dk.due; $('deck-summary').textContent = 'Cards (' + dk.total + ')';
    var list = $('deck-list'); list.textContent = '';
    (d.cards || []).forEach(function (c) {
      var li = document.createElement('li'), text = document.createElement('span'), due = document.createElement('span'), x = document.createElement('button');
      text.className = 'deck-text'; text.textContent = c.q + ' → ' + c.a;
      due.className = 'deck-due' + (c.due <= today ? ' now' : ''); due.textContent = c.due <= today ? 'due' : c.due;
      x.type = 'button'; x.className = 'settings-action'; x.textContent = 'Remove'; x.setAttribute('aria-label', 'Remove the card ' + c.q);
      x.addEventListener('click', function () { api('/api/study/deck', { remove: c.id }).then(showStudy).catch(function () {}); });
      li.append(text, due, x); list.append(li);
    });
  }
  $('deck-add').addEventListener('click', function () {
    api('/api/study/deck', { add: { q: $('deck-q').value, a: $('deck-a').value } }).then(function (d) { showStudy(d); $('deck-q').value = ''; $('deck-a').value = ''; $('deck-q').focus(); })
      .catch(function (e) { $('deck-stats').textContent = e.message; });
  });
  $('deck-review').addEventListener('click', function () {
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    if (typeof window.sendMessage === 'function') window.sendMessage('review my cards');
  });
  window.addEventListener('jarvis:reply', function (e) { if (e.detail && /deck|card|review/i.test(e.detail.text || '')) loadStudy(); });
  function loadStudy() { api('/api/study').then(showStudy).catch(function () {}); }
  $('study-clear').addEventListener('click', function () { api('/api/study/clear', {}).then(showStudy).catch(function () {}); });
  window.addEventListener('jarvis:pane', function (e) { if (e.detail && e.detail.pane === 'notes') { load(); loadStudy(); } });
})();

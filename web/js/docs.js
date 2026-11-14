/* Document and file chat: add files, switch "answer from my documents" on, see sources. */
(function () {
  'use strict';
  function $(id) { return document.getElementById(id); }
  function get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  function el(tag, cls, text) { var n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; }
  var items = [], on = get('jarvis-docs-on') === '1', busy = false;
  var list = $('docs-list'), note = $('docs-note'), toggle = $('docs-toggle'), attach = $('docs-attach'), file = $('docs-file'), check = $('docs-on'), addBtn = $('docs-add');
  if (!list || !toggle) return;
  var defaultNote = note.textContent;

  function size(n) { return n > 1048576 ? (n / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB'; }
  function sync() {
    if (!items.length) on = false;
    window.JARVIS_USE_DOCS = on && items.length > 0;
    toggle.classList.toggle('hidden', !items.length);
    toggle.setAttribute('aria-pressed', window.JARVIS_USE_DOCS ? 'true' : 'false');
    toggle.textContent = window.JARVIS_USE_DOCS ? '▤ Docs on (' + items.length + ')' : '▤ Docs off';
    check.checked = window.JARVIS_USE_DOCS; check.disabled = !items.length;
    set('jarvis-docs-on', on ? '1' : '0');
  }
  function render() {
    while (list.firstChild) list.removeChild(list.firstChild);
    if (!items.length) list.appendChild(el('li', 'tool-empty', 'No documents yet.'));
    items.forEach(function (d) {
      var li = el('li', 'tool-item');
      li.appendChild(el('span', 'tool-kind', d.kind === 'Excel' || d.kind === 'Table' ? '▦' : '▤'));
      li.appendChild(el('span', 'tool-text', d.name));
      li.appendChild(el('span', 'tool-time', size(d.size)));
      var del = el('button', 'tool-del', '×'); del.type = 'button'; del.setAttribute('aria-label', 'Remove ' + d.name);
      del.addEventListener('click', function () {
        fetch('/api/documents/delete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: d.id }) })
          .then(function (r) { return r.json(); }).then(function (j) { items = j.items || []; render(); sync(); }).catch(function () {});
      });
      li.appendChild(del); list.appendChild(li);
    });
    sync();
  }
  function say(t) { note.textContent = t; }
  function upload(files) {
    files = Array.prototype.slice.call(files || []);
    if (!files.length || busy) return;
    busy = true; addBtn.disabled = true; var done = 0, problems = [], cut = [];
    function next() {
      var f = files.shift();
      if (!f) {
        busy = false; addBtn.disabled = false;
        say((done ? 'Added ' + done + ' document' + (done === 1 ? '' : 's') + '. ' : '') + (cut.length ? cut.join(', ') + ' was long, so only the first part is searchable. ' : '') + problems.join(' '));
        if (done && !on) { on = true; } render(); return;
      }
      say('Reading ' + f.name + '…');
      fetch('/api/documents?name=' + encodeURIComponent(f.name), { method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: f })
        .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || 'Upload failed'); return j; }); })
        .then(function (j) { done++; items = j.items || items; if (j.truncated) cut.push(f.name); render(); })
        .catch(function (e) { problems.push(f.name + ': ' + e.message); })
        .then(next);
    }
    next();
  }
  function open() { file.click(); }
  attach.addEventListener('click', open); addBtn.addEventListener('click', open);
  file.addEventListener('change', function () { upload(file.files); file.value = ''; });
  toggle.addEventListener('click', function () { on = !on; sync(); });
  check.addEventListener('change', function () { on = check.checked; sync(); });
  var form = $('composer');
  ['dragenter', 'dragover'].forEach(function (t) { document.addEventListener(t, function (e) { if (e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types || [], 'Files') >= 0) { e.preventDefault(); form.classList.add('drop-ready'); } }); });
  document.addEventListener('dragleave', function (e) { if (!e.relatedTarget) form.classList.remove('drop-ready'); });
  document.addEventListener('drop', function (e) {
    form.classList.remove('drop-ready');
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) { e.preventDefault(); upload(e.dataTransfer.files); }
  });
  window.addEventListener('jarvis:sources', function (e) {
    var rows = document.querySelectorAll('.message-row.assistant'); var row = rows[rows.length - 1];
    if (!row || !Array.isArray(e.detail)) return;
    var web = e.detail.some(function (s) { return s && /^https?:\/\//i.test(s.url || ''); });
    var box = el('div', 'doc-sources'); box.appendChild(el('span', 'doc-sources-label', web ? 'SOURCES' : e.detail.length ? 'FROM YOUR DOCUMENTS' : 'NO MATCHING PASSAGES'));
    var seen = {};
    e.detail.forEach(function (s) {
      if (web) {   // web research: numbered links that match the [1], [2] marks in the answer
        if (!/^https?:\/\//i.test(s.url || '')) return;
        var a = el('a', 'doc-chip doc-link', '[' + s.n + '] ' + s.name + ' · ' + s.where);
        a.href = s.url; a.target = '_blank'; a.rel = 'noopener noreferrer'; a.title = s.url; box.appendChild(a); return;
      }
      var t = s.name + ' · ' + s.where; if (seen[t]) return; seen[t] = 1; box.appendChild(el('span', 'doc-chip', t));
    });
    row.after(box);   // under the answer, in line with its text
  });
  fetch('/api/documents').then(function (r) { return r.json(); }).then(function (j) { items = j.items || []; render(); }).catch(function () {});
})();

/* Settings > Shortcuts (dictation, quick actions) and the quick-actions panel that opens when the shortcut is pressed. */
(function () {
  'use strict';
  function $(id) { return document.getElementById(id); }
  function api(path, body) {
    var opts = body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined;
    return fetch(path, opts).then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || 'Request failed'); return d; }); });
  }
  // ---- settings ----
  if ($('dict-enabled')) {
    var busy = false;
    var fill = function (sel, keys, value) {
      var have = Array.prototype.map.call(sel.options, function (o) { return o.value; }).join('|');
      if (have !== Object.keys(keys).join('|')) { sel.textContent = ''; Object.keys(keys).forEach(function (k) { var o = document.createElement('option'); o.value = k; o.textContent = keys[k]; sel.appendChild(o); }); }
      sel.value = value;
    };
    var show = function (d) {
      $('dict-enabled').checked = d.dictation.enabled; $('quick-enabled').checked = d.quick.enabled;
      fill($('dict-key'), d.dictation_keys, d.dictation.key); fill($('quick-key'), d.quick_keys, d.quick.key);
      $('keys-status').textContent = d.state === 'error' ? d.error : d.state === 'recording' ? 'Listening…' : d.error ? d.error : d.dictation.enabled || d.quick.enabled ? 'Ready.' : '';
      var log = $('dict-log'); log.textContent = '';
      (d.recent || []).slice().reverse().forEach(function (e) { var li = document.createElement('li'); li.className = 'tool-item'; li.textContent = e.time + '  ' + e.text; log.appendChild(li); });
      if (!(d.recent || []).length) { var li = document.createElement('li'); li.className = 'tool-item'; li.textContent = 'Nothing yet.'; log.appendChild(li); }
    };
    var send = function (body) { busy = true; return api('/api/shortcuts', body).then(show).catch(function (e) { $('keys-status').textContent = e.message; }).then(function () { busy = false; }); };
    $('dict-enabled').addEventListener('change', function () { send({ dictation: { enabled: $('dict-enabled').checked } }); });
    $('dict-key').addEventListener('change', function () { send({ dictation: { key: $('dict-key').value } }); });
    $('quick-enabled').addEventListener('change', function () { send({ quick: { enabled: $('quick-enabled').checked } }); });
    $('quick-key').addEventListener('change', function () { send({ quick: { key: $('quick-key').value } }); });
    var refresh = function () { if (!busy && !$('pane-keys').classList.contains('hidden')) api('/api/shortcuts').then(show).catch(function () {}); };
    var loadKeys = function () { api('/api/shortcuts').then(show).catch(function () {}); };
    $('tab-keys').addEventListener('click', loadKeys);
    window.addEventListener('jarvis:pane', function (e) { if (e.detail.pane === 'keys') loadKeys(); });
    setInterval(refresh, 2500);
  }
  // ---- quick-actions panel ----
  var panel = $('quick-panel');
  if (!panel) return;
  var lastId = null, working = false;
  function open(text) { $('quick-text').value = text; $('quick-result').classList.add('hidden'); $('quick-copy').classList.add('hidden'); $('quick-replace').classList.add('hidden'); panel.classList.remove('hidden'); }
  function run(action) {
    if (working) return; working = true;
    var out = $('quick-result'); out.classList.remove('hidden'); out.textContent = 'Working…';
    api('/api/quick/run', { action: action, text: $('quick-text').value, language: $('quick-lang').value, instruction: $('quick-custom').value })
      .then(function (d) { out.textContent = d.result; $('quick-copy').classList.remove('hidden'); $('quick-replace').classList.remove('hidden'); })
      .catch(function (e) { out.textContent = e.message; })
      .then(function () { working = false; });
  }
  Array.prototype.forEach.call(document.querySelectorAll('.quick-act'), function (b) { b.addEventListener('click', function () { run(b.getAttribute('data-action')); }); });
  $('quick-go').addEventListener('click', function () { run('custom'); });
  $('quick-custom').addEventListener('keydown', function (e) { if (e.key === 'Enter') run('custom'); });
  $('quick-close').addEventListener('click', function () { panel.classList.add('hidden'); });
  $('quick-copy').addEventListener('click', function () {
    var text = $('quick-result').textContent, done = function () { $('quick-copy').textContent = 'Copied'; setTimeout(function () { $('quick-copy').textContent = 'Copy'; }, 1500); };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, function () {}); else done();
  });
  $('quick-replace').addEventListener('click', function () {
    api('/api/quick/replace', { text: $('quick-result').textContent }).then(function () { panel.classList.add('hidden'); }).catch(function (e) { $('quick-result').textContent = e.message; });
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !panel.classList.contains('hidden')) panel.classList.add('hidden'); });
  function poll() {
    if (document.visibilityState === 'hidden') return;
    api('/api/quick').then(function (d) {
      if (lastId === null) { lastId = d.id; if (d.id && d.age !== null && d.age < 30) open(d.text); return; }   // a page opened by the shortcut shows it at once
      if (d.id !== lastId) { lastId = d.id; open(d.text); }
    }).catch(function () {});
  }
  poll(); setInterval(poll, 1500);
})();

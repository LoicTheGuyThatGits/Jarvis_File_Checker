/* Settings > Mail: connect Gmail (read-only) and test it. The checking itself runs in the Jarvis program. */
(function () {
  'use strict';
  function $(id) { return document.getElementById(id); }
  if (!$('mail-save')) return;
  function api(path, body) {
    var opts = body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined;
    return fetch(path, opts).then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || 'Request failed'); return d; }); });
  }
  function show(d) {
    $('mail-address').value = d.address || '';
    $('mail-password').value = '';
    $('mail-password').placeholder = d.has_password ? 'Saved. Leave empty to keep it.' : '16 letters from Google (not your normal password)';
    $('mail-filter').value = d.filter; $('mail-summarize').checked = d.summarize; $('mail-cloud').checked = d.body_to_cloud;
    $('mail-disconnect').classList.toggle('hidden', !d.has_password);
    $('mail-status').textContent = d.enabled ? 'Connected as ' + d.address + (d.last_check ? '. Last checked ' + d.last_check + '.' : '.') : 'Not connected. Jarvis can tell you how many emails arrived while you were away and what they were about. It only reads: it never sends, deletes or moves anything.';
  }
  function load() { api('/api/mail').then(show).catch(function () {}); }
  $('mail-save').addEventListener('click', function () {
    var btn = $('mail-save'); btn.disabled = true; $('mail-result').textContent = 'Checking…';
    var body = { address: $('mail-address').value, filter: $('mail-filter').value, summarize: $('mail-summarize').checked, body_to_cloud: $('mail-cloud').checked, enabled: true };
    if ($('mail-password').value.trim()) body.password = $('mail-password').value;
    api('/api/mail', body).then(function () { return api('/api/mail/check', {}); })
      .then(function (d) { show(d); $('mail-result').textContent = d.reply; })
      .catch(function (e) { $('mail-result').textContent = e.message; })
      .then(function () { btn.disabled = false; });
  });
  $('mail-disconnect').addEventListener('click', function () {
    api('/api/mail/disconnect', {}).then(function (d) { show(d); $('mail-result').textContent = 'Disconnected. The saved password was removed.'; }).catch(function (e) { $('mail-result').textContent = e.message; });
  });
  $('tab-mail').addEventListener('click', load);
  window.addEventListener('jarvis:pane', function (e) { if (e.detail.pane === 'mail') load(); });
  load();
})();

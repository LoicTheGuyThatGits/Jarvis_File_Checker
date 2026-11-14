/* Settings: Spotify connection and the PC health check. */
(function () {
  'use strict';
  function $(id) { return document.getElementById(id); }
  function api(path, body) {
    var opts = body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined;
    return fetch(path, opts).then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || 'Request failed'); return d; }); });
  }
  if ($('spotify-status')) {
    var polling = null;
    var show = function (d) {
      $('spotify-redirect').value = d.redirect_uri;
      if (document.activeElement !== $('spotify-client')) $('spotify-client').value = d.client_id || '';
      $('spotify-status').textContent = d.connected ? 'Connected' + (d.user ? ' as ' + d.user : '') + '.' : 'Not connected.';
      $('spotify-disconnect').disabled = !d.connected;
      if (d.connected && polling) { clearInterval(polling); polling = null; }
    };
    var load = function () { api('/api/spotify').then(show).catch(function () {}); };
    $('spotify-connect').addEventListener('click', function () {
      api('/api/spotify/connect', { client_id: $('spotify-client').value.trim() }).then(function (d) {
        $('spotify-status').textContent = 'Allow access in the browser tab that opened…';
        window.open(d.url, '_blank', 'noopener');
        if (polling) clearInterval(polling);
        var n = 0; polling = setInterval(function () { load(); if (++n > 90) { clearInterval(polling); polling = null; } }, 2000);
      }).catch(function (e) { $('spotify-status').textContent = e.message; });
    });
    $('spotify-disconnect').addEventListener('click', function () { api('/api/spotify/disconnect', {}).then(show).catch(function () {}); });
    window.addEventListener('jarvis:pane', function (e) { if (e.detail && e.detail.pane === 'keys') load(); });
  }
  if ($('files-check')) {
    var last = null;
    var busy = function (on) { $('files-check').disabled = on; $('files-repair').disabled = on || !last || !(last.missing.length || ($('files-changed').checked && last.changed.length)); };
    var run = function () {
      busy(true); $('files-report').textContent = 'Checking…';
      return api('/api/files').then(function (d) { last = d; $('files-report').textContent = d.text; }).catch(function (e) { last = null; $('files-report').textContent = e.message; }).then(function () { busy(false); });
    };
    $('files-check').addEventListener('click', run);
    $('files-changed').addEventListener('change', function () { busy(false); });
    $('files-repair').addEventListener('click', function () {
      var n = last.missing.length + ($('files-changed').checked ? last.changed.length : 0);
      busy(true); $('files-report').textContent = 'Downloading ' + n + ' file' + (n === 1 ? '' : 's') + '…';
      api('/api/files/repair', { changed: $('files-changed').checked }).then(function (d) { $('files-report').textContent = d.text; last = null; }).catch(function (e) { $('files-report').textContent = e.message; }).then(function () { busy(false); });
    });
  }
  if ($('health-run')) {
    $('health-run').addEventListener('click', function () {
      $('health-run').disabled = true; $('health-report').textContent = 'Checking… (this can take a few seconds)';
      api('/api/maintenance').then(function (d) { $('health-report').textContent = d.report; }).catch(function (e) { $('health-report').textContent = e.message; }).then(function () { $('health-run').disabled = false; });
    });
  }
})();

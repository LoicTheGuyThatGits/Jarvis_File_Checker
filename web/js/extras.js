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
    var upd = null;
    var busyU = function (on) { $('files-update').disabled = on; $('files-install').disabled = on || !upd || !(upd.missing.length || upd.updates.length || ($('files-changed').checked && (upd.conflicts.length || upd.unknown.length))); };
    $('files-update').addEventListener('click', function () {
      busyU(true); $('files-report').textContent = 'Looking for updates…';
      api('/api/files/update').then(function (d) { upd = d; $('files-auto').checked = d.auto !== false; $('files-report').textContent = d.text; }).catch(function (e) { upd = null; $('files-report').textContent = e.message; }).then(function () { busyU(false); });
    });
    $('files-install').addEventListener('click', function () {
      busyU(true); $('files-report').textContent = 'Downloading…';
      api('/api/files/repair', { mode: 'update', changed: $('files-changed').checked }).then(function (d) { $('files-report').textContent = d.text; upd = null; }).catch(function (e) { $('files-report').textContent = e.message; }).then(function () { busyU(false); });
    });
    $('files-auto').addEventListener('change', function () { api('/api/files/auto', { on: $('files-auto').checked }).catch(function () {}); });
    $('files-check').addEventListener('click', run);
    $('files-changed').addEventListener('change', function () { busy(false); busyU(false); });
    $('files-repair').addEventListener('click', function () {
      var n = last.missing.length + ($('files-changed').checked ? last.changed.length : 0);
      busy(true); $('files-report').textContent = 'Downloading ' + n + ' file' + (n === 1 ? '' : 's') + '…';
      api('/api/files/repair', { changed: $('files-changed').checked }).then(function (d) { $('files-report').textContent = d.text; last = null; }).catch(function (e) { $('files-report').textContent = e.message; }).then(function () { busy(false); });
    });
  }
  if ($('train-bar')) {
    // Rough guide to how many 👍 answers are worth having before a training run (see the README).
    var STAGES = [[50, 'check that the pipeline works'], [300, 'fix tone and style'], [800, 'teach Jarvis\' habits and commands'], [3000, 'broad improvement']];
    var showTrain = function (t) {
      var up = t.up || 0, next = null, i;
      for (i = 0; i < STAGES.length; i++) { if (up < STAGES[i][0]) { next = STAGES[i]; break; } }
      var prev = i > 0 ? STAGES[i - 1][0] : 0;
      $('train-bar').max = next ? next[0] - prev : 1; $('train-bar').value = next ? up - prev : 1;
      var rate = t.exchanges > 0 ? Math.max(0.15, Math.min(0.9, up / t.exchanges)) : 0.4;
      $('train-goal').textContent = next
        ? up + ' answers marked good. Next goal: ' + next[0] + ' (' + next[1] + '), ' + (next[0] - up) + ' to go, roughly ' + Math.ceil((next[0] - up) / rate) + ' more exchanges at your current rating rate.'
        : up + ' answers marked good: past every goal. More only helps if the requests stay varied.';
      var list = $('train-stages'); list.textContent = '';
      STAGES.forEach(function (st) { var li = document.createElement('li'); li.textContent = (up >= st[0] ? '✓ ' : '○ ') + st[0] + ': ' + st[1]; list.appendChild(li); });
    };
    var loadTrain = function () { api('/api/training').then(showTrain).catch(function () {}); };
    window.addEventListener('jarvis:pane', function (e) { if (e.detail && e.detail.pane === 'ai') loadTrain(); });
    loadTrain();
  }
  if ($('backup-run')) {
    var sel = $('backup-file');
    var showB = function (d) {
      if (document.activeElement !== $('backup-folder')) $('backup-folder').value = d.folder;
      $('backup-last').textContent = 'Last backup: ' + d.last_text + '.';
      var keep = sel.value; sel.textContent = '';
      d.backups.forEach(function (b) { var o = document.createElement('option'); o.value = b.name; o.textContent = b.name + '  (' + new Date(b.at * 1000).toLocaleString() + ', ' + Math.max(1, Math.round(b.bytes / 1024)) + ' KB)'; sel.appendChild(o); });
      if (!d.backups.length) { var o = document.createElement('option'); o.value = ''; o.textContent = 'No backup found in that folder'; sel.appendChild(o); }
      if (keep) sel.value = keep;
      $('backup-restore').disabled = !d.backups.length;
    };
    var loadB = function () { api('/api/backup').then(showB).catch(function () {}); };
    var done = function (d) { $('backup-pass').value = ''; $('backup-status').textContent = d.message; showB(d.state); };
    var fail = function (e) { $('backup-status').textContent = e.message; };
    $('backup-run').addEventListener('click', function () {
      $('backup-status').textContent = 'Backing up…';
      api('/api/backup/run', { folder: $('backup-folder').value, passphrase: $('backup-pass').value }).then(done).catch(fail);
    });
    $('backup-restore').addEventListener('click', function () {
      $('backup-status').textContent = 'Restoring…';
      api('/api/backup/restore', { folder: $('backup-folder').value, file: sel.value, passphrase: $('backup-pass').value }).then(done).catch(fail);
    });
    $('backup-folder').addEventListener('change', function () { api('/api/backup/folder', { folder: $('backup-folder').value }).then(showB).catch(fail); });
    window.addEventListener('jarvis:pane', function (e) { if (e.detail && e.detail.pane === 'timers') loadB(); });
  }
  if ($('health-run')) {
    $('health-run').addEventListener('click', function () {
      $('health-run').disabled = true; $('health-report').textContent = 'Checking… (this can take a few seconds)';
      api('/api/maintenance').then(function (d) { $('health-report').textContent = d.report; }).catch(function (e) { $('health-report').textContent = e.message; }).then(function () { $('health-run').disabled = false; });
    });
  }
})();

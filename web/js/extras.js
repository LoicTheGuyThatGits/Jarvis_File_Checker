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
  if ($('recap-on')) {
    var loadR = function () {
      api('/api/recap').then(function (d) { $('recap-on').checked = d.enabled; if (document.activeElement !== $('recap-time')) $('recap-time').value = d.time; }).catch(function () {});
    };
    var saveR = function () {
      api('/api/recap', { enabled: $('recap-on').checked, time: $('recap-time').value }).then(function (d) { $('recap-text').textContent = d.enabled ? 'Saved. Jarvis will post it after ' + d.time + ' each day.' : 'Saved. Automatic recap is off.'; }).catch(function (e) { $('recap-text').textContent = e.message; });
    };
    $('recap-on').addEventListener('change', saveR);
    $('recap-time').addEventListener('change', saveR);
    $('recap-show').addEventListener('click', function () {
      api('/api/recap/show', {}).then(function (d) { $('recap-text').textContent = d.text; }).catch(function (e) { $('recap-text').textContent = e.message; });
    });
    window.addEventListener('jarvis:pane', function (e) { if (e.detail && e.detail.pane === 'plan') loadR(); });
  }
  if ($('router-on')) {
    var loadRouter = function () {
      api('/api/router').then(function (d) { $('router-on').checked = d.enabled; $('router-note').textContent = d.tools.length + ' tools available to it.'; }).catch(function () {});
    };
    $('router-on').addEventListener('change', function () {
      api('/api/router', { enabled: $('router-on').checked }).then(function (d) { $('router-note').textContent = d.enabled ? 'On. Jarvis shows which tool it chose under each such reply.' : 'Off.'; }).catch(function (e) { $('router-note').textContent = e.message; });
    });
    window.addEventListener('jarvis:pane', function (e) { if (e.detail && e.detail.pane === 'ai') loadRouter(); });
  }
  if ($('exam-add')) {
    var drawExams = function (d) {
      var list = $('exam-list'); list.textContent = '';
      (d.exams || []).forEach(function (e) {
        var li = document.createElement('li');
        var when = new Date(e.start * 1000);
        li.textContent = e.title + ': ' + (e.days === 0 ? 'today' : e.days === 1 ? 'tomorrow' : 'in ' + e.days + ' days') + ' (' + when.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' }) + ') · '
          + (e.planned ? e.done + ' of ' + e.planned + ' revision sessions done' : 'no revision planned yet');
        list.append(li);
      });
      if (!(d.exams || []).length) { var li = document.createElement('li'); li.textContent = 'No exams in your calendar.'; list.append(li); }
    };
    var loadExams = function () { api('/api/exams').then(drawExams).catch(function () {}); };
    $('exam-add').addEventListener('click', function () {
      api('/api/exams', { subject: $('exam-subject').value, date: $('exam-date').value, time: $('exam-time').value }).then(function (d) { drawExams(d); $('exam-status').textContent = d.text; $('exam-subject').value = ''; }).catch(function (e) { $('exam-status').textContent = e.message; });
    });
    $('exam-plan').addEventListener('click', function () {
      api('/api/exams/plan', {}).then(function (d) { drawExams(d); $('exam-status').textContent = d.text; }).catch(function (e) { $('exam-status').textContent = e.message; });
    });
    var drawFocus = function (d) {
      var mins = function (m) { return m >= 60 ? Math.floor(m / 60) + ' h ' + String(m % 60).padStart(2, '0') : m + ' min'; };
      var a = d.active;
      $('focus-status').textContent = (d.text ? d.text + ' ' : (a ? (a.phase === 'work' ? 'Focusing' + (a.label ? ' on ' + a.label : '') : 'On a break') + ': ' + Math.ceil(a.left / 60) + ' min left. ' : 'No session running. '))
        + 'Today: ' + mins(d.today) + ' · this week: ' + mins(d.week) + '.';
    };
    var loadFocus = function () { api('/api/focus').then(drawFocus).catch(function () {}); };
    $('focus-start').addEventListener('click', function () {
      api('/api/focus', { action: 'start', minutes: Number($('focus-minutes').value), label: $('focus-label').value }).then(drawFocus).catch(function (e) { $('focus-status').textContent = e.message; });
    });
    $('focus-stop').addEventListener('click', function () { api('/api/focus', { action: 'stop' }).then(drawFocus).catch(function (e) { $('focus-status').textContent = e.message; }); });
    window.addEventListener('jarvis:pane', function (e) { if (e.detail && e.detail.pane === 'plan') { loadExams(); loadFocus(); } });
  }
  if ($('net-check')) {
    var netBusy = function (on, msg) { ['net-check', 'net-devices', 'net-mine'].forEach(function (id) { $(id).disabled = on; }); if (msg) $('net-report').textContent = msg; };
    var netShow = function (d) { $('net-report').textContent = d.text || ''; $('net-mine').hidden = !d.confirm; };
    var netFail = function (e) { $('net-report').textContent = e.message; };
    $('net-check').addEventListener('click', function () {
      netBusy(true, 'Measuring… (about 20 seconds)'); $('net-mine').hidden = true;
      api('/api/network/check', {}).then(netShow).catch(netFail).then(function () { netBusy(false); });
    });
    $('net-devices').addEventListener('click', function () {
      netBusy(true, 'Looking for devices… (about 15 seconds)');
      api('/api/network/devices', {}).then(netShow).catch(netFail).then(function () { netBusy(false); });
    });
    $('net-mine').addEventListener('click', function () {
      netBusy(true, 'Scanning… (about 15 seconds)');
      api('/api/network/devices', { mine: true }).then(netShow).catch(netFail).then(function () { netBusy(false); });
    });
    $('net-watch').addEventListener('change', function () { api('/api/network', { watch: $('net-watch').checked }).catch(netFail); });
    window.addEventListener('jarvis:pane', function (e) { if (e.detail && e.detail.pane === 'timers') api('/api/network').then(function (d) { $('net-watch').checked = d.watch; }).catch(function () {}); });
  }
  if ($('jm-build')) {
    var jmTimer = null;
    var jmShow = function (d) {
      var b = d.build || {};
      $('jm-base').textContent = d.base || '?';
      $('jm-file').textContent = d.modelfile + (d.modelfile_exists ? '' : '  (made from the template on the first build)');
      $('jm-state').textContent = b.running ? 'Building: ' + (b.step || 'starting') + '…'
        : !d.ollama ? 'Ollama is not installed (ollama.com/download)'
        : !d.ollama_running ? 'Ollama is not running'
        : d.installed ? (d.in_use ? 'Installed and in use' : 'Installed; the local model in use is ' + d.local_model)
        : 'Not built yet';
      $('jm-build').textContent = d.installed ? 'Rebuild the Jarvis model' : 'Build the Jarvis model';
      $('jm-build').disabled = !!b.running || !d.ollama;
      if (!b.running && b.message) $('jm-status').textContent = b.message;
      clearTimeout(jmTimer);
      if (b.running) jmTimer = setTimeout(jmLoad, 2000);
      else if (b.ok && $('model-refresh') && jmShow.wasRunning) $('model-refresh').click();
      jmShow.wasRunning = !!b.running;
    };
    var jmLoad = function () { api('/api/jarvis-model').then(jmShow).catch(function (e) { $('jm-status').textContent = e.message; }); };
    $('jm-build').addEventListener('click', function () {
      $('jm-build').disabled = true;
      api('/api/jarvis-model', {}).then(function (d) { $('jm-status').textContent = d.message; jmShow(d); })
        .catch(function (e) { $('jm-status').textContent = e.message; $('jm-build').disabled = false; });
    });
    window.addEventListener('jarvis:pane', function (e) { if (e.detail && e.detail.pane === 'ai') jmLoad(); });
  }
  if ($('install-folder')) {
    var installLoad = function () {
      api('/api/install').then(function (d) {
        $('install-folder').textContent = d.folder; $('install-data').textContent = d.data;
        $('install-python').textContent = d.python + (d.venv ? '' : '  (not Jarvis\'s own .venv)');
        $('install-pc').textContent = d.pc;
        $('install-changed').textContent = d.files_changed ? new Date(d.files_changed * 1000).toLocaleString() : 'unknown';
        var mark = $('install-mark'); if (mark) { mark.textContent = d.folder; mark.title = 'Jarvis is running from ' + d.folder; }
      }).catch(function (e) { $('install-status').textContent = e.message; });
    };
    var installOpen = function (what) { api('/api/install/open', { what: what }).then(function () { $('install-status').textContent = 'Opened in Explorer.'; }).catch(function (e) { $('install-status').textContent = e.message; }); };
    $('install-open').addEventListener('click', function () { installOpen('folder'); });
    $('install-open-data').addEventListener('click', function () { installOpen('data'); });
    $('install-copy').addEventListener('click', function () {
      var text = $('install-folder').textContent;
      (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject(new Error('no clipboard'))).then(function () { $('install-status').textContent = 'Copied.'; },
        function () { var r = document.createRange(); r.selectNodeContents($('install-folder')); var sel = getSelection(); sel.removeAllRanges(); sel.addRange(r); $('install-status').textContent = 'Selected: press Ctrl+C to copy.'; });
    });
    window.addEventListener('jarvis:pane', function (e) { if (e.detail && e.detail.pane === 'look') installLoad(); });
    installLoad();
  }
  if ($('selftest-run')) {
    $('selftest-run').addEventListener('click', function () {
      var b = $('selftest-run'); b.disabled = true; $('selftest-copy').disabled = true; $('selftest-report').textContent = 'Checking… (up to a minute)';
      api('/api/selftest', {}).then(function (d) { $('selftest-report').textContent = d.text; $('selftest-copy').disabled = false; })
        .catch(function (e) { $('selftest-report').textContent = e.message; }).then(function () { b.disabled = false; });
    });
    $('selftest-copy').addEventListener('click', function () {
      var text = $('selftest-report').textContent;
      (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject()).then(function () { $('selftest-copy').textContent = 'Copied'; setTimeout(function () { $('selftest-copy').textContent = 'Copy the report'; }, 2000); },
        function () { var r = document.createRange(); r.selectNodeContents($('selftest-report')); var sel = getSelection(); sel.removeAllRanges(); sel.addRange(r); });
    });
  }
  if ($('ctl-sight')) {
    var ctlShow = function (d) {
      $('ctl-sight').value = d.sight; $('ctl-ocr').checked = d.ocr !== false; $('ctl-overlay').checked = d.overlay !== false;
      var steps = String(d.max_steps); if (![].some.call($('ctl-steps').options, function (o) { return o.value === steps; })) { var o = document.createElement('option'); o.value = o.textContent = steps; $('ctl-steps').append(o); }
      $('ctl-steps').value = steps;
      $('ctl-sight-now').textContent = d.sight_now === 'picture' ? 'Right now: screenshot and text.' : 'Right now: text only (the chosen model cannot see pictures).';
      var list = $('ctl-folders'); list.textContent = '';
      (d.folders || []).forEach(function (f) {
        var li = document.createElement('li'), code = document.createElement('code'), x = document.createElement('button');
        code.textContent = f; x.type = 'button'; x.textContent = 'Remove'; x.className = 'settings-action';
        x.addEventListener('click', function () { ctlSave({ folders: d.folders.filter(function (g) { return g !== f; }) }); });
        li.append(code, ' ', x); list.append(li);
      });
      if (!(d.folders || []).length) { var li = document.createElement('li'); li.textContent = 'None yet.'; list.append(li); }
      ctlState = d;
    };
    var ctlState = { folders: [] };
    var ctlSave = function (update) { return api('/api/control', update).then(function (d) { ctlShow(d); $('ctl-status').textContent = 'Saved.'; }).catch(function (e) { $('ctl-status').textContent = e.message; }); };
    $('ctl-sight').addEventListener('change', function () { ctlSave({ sight: $('ctl-sight').value }); });
    $('ctl-ocr').addEventListener('change', function () { ctlSave({ ocr: $('ctl-ocr').checked }); });
    $('ctl-overlay').addEventListener('change', function () { ctlSave({ overlay: $('ctl-overlay').checked }); });
    $('ctl-overlay-test').addEventListener('click', function () {
      api('/api/control', { test_overlay: true }).then(function (d) {
        $('ctl-status').textContent = d.ok ? 'Look at the screen around your mouse pointer for a few seconds.' + (d.left_out_of_screenshots ? '' : ' (This Windows cannot leave it out of screenshots, so it is hidden for each screenshot instead.)') : 'The overlay cannot be shown: ' + d.error + '.';
      }).catch(function (e) { $('ctl-status').textContent = e.message; });
    });
    $('ctl-steps').addEventListener('change', function () { ctlSave({ max_steps: Number($('ctl-steps').value) }); });
    $('ctl-folder-add').addEventListener('click', function () {
      var f = $('ctl-folder').value.trim(); if (!f) return;
      ctlSave({ folders: (ctlState.folders || []).concat([f]) }).then(function () { if ($('ctl-status').textContent === 'Saved.') $('ctl-folder').value = ''; });
    });
    window.addEventListener('jarvis:pane', function (e) { if (e.detail && e.detail.pane === 'ai') api('/api/control').then(ctlShow).catch(function () {}); });
  }
})();

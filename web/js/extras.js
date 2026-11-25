/* Settings: Spotify connection and the PC health check. */
(function () {
  'use strict';
  function $(id) { return document.getElementById(id); }
  function api(path, body) {
    var opts = body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined;
    return fetch(path, opts).then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || 'Request failed'); return d; }); });
  }
  if ($('adv-roles')) {
    var advTimer = 0, tr = function (t) { return window.JarvisI18n ? window.JarvisI18n.t(t) : t; };
    var WHERE = { gpu: 'all on the graphics card', split: 'partly on the processor (slow)', cpu: 'on the processor', no: 'too big for this PC' };
    var ROLE = { chat: ['Chat', 'Answers you in chat and by voice; it should feel instant.'], vision: ['Pictures', 'Looks at photos and screenshots you send.'],
      autopilot: ['Autopilot', 'Sees the screen and works the mouse and keyboard.'], code: ['Jarvis Code', 'Writes and fixes code; bigger makes fewer mistakes.'] };
    var speed = function (m) { return m.where === 'no' ? tr('too big for this PC') : '~' + Math.round(m.tps) + ' ' + tr('words/s') + ', ' + tr(WHERE[m.where]) + (m.measured ? ' ' + tr('(measured)') : ''); };
    var advShow = function (d) {
      var pc = d.pc;
      $('adv-pc').textContent = (pc.gpu || tr('No graphics card for AI')) + ' · ' + Math.round(pc.ram_gb) + ' GB RAM · ' + (pc.cpu || '') + ' · ' + Math.round(pc.disk_free_gb) + ' GB ' + tr('free on the disk') + ' · ' + pc.vram_free_gb.toFixed(1) + ' GB ' + tr('free for models on the card');
      var box = $('adv-roles'); box.textContent = '';
      var busy = d.pull && d.pull.running;
      d.roles.forEach(function (r) {
        var card = document.createElement('div'), b = r.best;
        card.className = 'adv-role' + (r.same ? ' ok' : '');
        var h = document.createElement('h3'); h.textContent = tr(ROLE[r.role][0]);
        var why = document.createElement('div'); why.className = 'adv-why'; why.textContent = tr(ROLE[r.role][1]);
        var pick = document.createElement('div'); pick.className = 'adv-pick'; pick.setAttribute('data-no-i18n', '');
        pick.textContent = b ? (r.same ? b.name : b.name + (r.current ? '   (' + tr('now') + ': ' + r.current + ')' : '')) : tr('Nothing suitable runs here.');
        var sp = document.createElement('div'); sp.className = 'adv-speed'; if (b) sp.textContent = speed(b);
        card.append(h, why, pick, sp);
        if (r.note) { var n = document.createElement('div'); n.className = 'adv-note'; n.setAttribute('data-no-i18n', ''); n.textContent = r.note; card.append(n); }
        if (b && !r.same) {
          var btn = document.createElement('button'); btn.type = 'button';
          btn.textContent = b.installed ? tr('Use it') : tr('Download') + ' (' + b.size_gb.toFixed(1) + ' GB)';
          btn.disabled = !b.installed && busy;
          btn.addEventListener('click', function () {
            btn.disabled = true;
            api('/api/advisor', b.installed ? { apply: { role: r.role, model: b.name } } : { pull: b.name }).then(function (n) { advShow(n); $('adv-status').textContent = n.message || tr('Downloading… the button changes to “Use it” when it is done.'); })
              .catch(function (e) { btn.disabled = false; $('adv-status').textContent = e.message; });
          });
          card.append(btn);
        }
        box.append(card);
      });
      var adv = $('adv-advice'); adv.textContent = '';
      d.advice.forEach(function (t) { var li = document.createElement('li'); li.setAttribute('data-no-i18n', ''); li.textContent = t; adv.append(li); });
      var tb = $('adv-models').tBodies[0]; tb.textContent = '';
      d.models.forEach(function (m) {
        var tr2 = document.createElement('tr'); if (m.where === 'no') tr2.className = 'no';
        [m.name + (m.installed ? '' : '  ↓'), m.size_gb.toFixed(1) + ' GB', tr(m.where === 'no' ? 'no' : m.where === 'split' ? 'slow' : 'yes'), m.where === 'no' ? '—' : '~' + Math.round(m.tps) + ' ' + tr('words/s') + (m.measured ? ' ✓' : '')].forEach(function (t, i) {
          var td = document.createElement('td'); td.textContent = t; if (i === 0) td.setAttribute('data-no-i18n', ''); tr2.append(td);
        });
        tb.append(tr2);
      });
      var fl = $('adv-features'); fl.textContent = '';
      d.features.forEach(function (f) { var li = document.createElement('li'); li.className = f.ok ? '' : 'no'; li.setAttribute('data-no-i18n', ''); li.textContent = (f.ok ? '✓ ' : '✕ ') + f.name + ': ' + f.detail; fl.append(li); });
      var ms = d.measure;
      $('adv-measure').disabled = ms.running;
      if (ms.running) $('adv-status').textContent = tr('Measuring') + ' ' + ms.model + ' (' + (ms.done.length + 1) + ' / ' + ms.total + ')…';
      else if (d.pull && d.pull.running) $('adv-status').textContent = tr('Downloading') + ' ' + d.pull.model + (d.pull.total ? ': ' + Math.round(100 * d.pull.done / d.pull.total) + ' %' : '…');
      clearTimeout(advTimer);
      if (ms.running || (d.pull && d.pull.running)) advTimer = setTimeout(advLoad, 2500);
    };
    var advLoad = function () { $('adv-refresh').disabled = true; return api('/api/advisor').then(advShow).catch(function (e) { $('adv-status').textContent = e.message; }).then(function () { $('adv-refresh').disabled = false; }); };
    $('adv-refresh').addEventListener('click', function () { $('adv-status').textContent = ''; advLoad(); });
    $('adv-measure').addEventListener('click', function () {
      if (!window.confirm('Try each installed model with a short answer to measure its real speed? It takes about 20 seconds per model, and chat is slower meanwhile.')) return;
      api('/api/advisor', { measure: true }).then(advShow).catch(function (e) { $('adv-status').textContent = e.message; });
    });
    window.addEventListener('jarvis:pane', function (e) { if (e.detail && paneHas(e.detail.pane, 'adv-roles')) advLoad(); });
  }
  if ($('spotify-status')) {
    var polling = null;
    var show = function (d) {
      $('spotify-redirect').value = d.redirect_uri;
      if (document.activeElement !== $('spotify-client')) $('spotify-client').value = d.client_id || '';
      $('spotify-status').textContent = d.connected ? 'Connected' + (d.user ? ' as ' + d.user : '') + '.' + (d.reconnect ? ' To play your Liked Songs, press Disconnect, then Connect again: Spotify has to allow one more permission.' : '') : 'Not connected.';
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
    window.addEventListener('jarvis:pane', function (e) { if (e.detail && paneHas(e.detail.pane, 'spotify-status')) load(); });
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
    window.addEventListener('jarvis:pane', function (e) { if (e.detail && paneHas(e.detail.pane, 'train-bar')) loadTrain(); });
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
    window.addEventListener('jarvis:pane', function (e) { if (e.detail && paneHas(e.detail.pane, 'backup-folder')) loadB(); });
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
    window.addEventListener('jarvis:pane', function (e) { if (e.detail && paneHas(e.detail.pane, 'recap-on')) loadR(); });
  }
  if ($('router-on')) {
    var loadRouter = function () {
      api('/api/router').then(function (d) { $('router-on').checked = d.enabled; $('router-note').textContent = d.tools.length + ' tools available to it.'; }).catch(function () {});
    };
    $('router-on').addEventListener('change', function () {
      api('/api/router', { enabled: $('router-on').checked }).then(function (d) { $('router-note').textContent = d.enabled ? 'On. Jarvis shows which tool it chose under each such reply.' : 'Off.'; }).catch(function (e) { $('router-note').textContent = e.message; });
    });
    window.addEventListener('jarvis:pane', function (e) { if (e.detail && paneHas(e.detail.pane, 'router-on')) loadRouter(); });
  }
  if ($('mcp-save')) {
    var mcpEditing = null;
    var mcpType = function () { var http = $('mcp-type').value === 'http'; $('mcp-url').classList.toggle('hidden', !http); $('mcp-headers').classList.toggle('hidden', !http); $('mcp-command').classList.toggle('hidden', http); $('mcp-env').classList.toggle('hidden', http); };
    var mcpReset = function () { mcpEditing = null; ['mcp-name', 'mcp-command', 'mcp-url', 'mcp-headers', 'mcp-env', 'mcp-words'].forEach(function (id) { $(id).value = ''; }); $('mcp-type').value = 'command'; $('mcp-enabled').checked = true; mcpType(); $('mcp-add-title').textContent = 'Add a server'; $('mcp-cancel').classList.add('hidden'); };
    var mcpDraw = function (d) {
      var list = $('mcp-list'); list.textContent = '';
      (d.servers || []).forEach(function (sv) {
        var li = document.createElement('li'), head = document.createElement('div'); head.className = 'mcp-head';
        var name = document.createElement('strong'); name.textContent = sv.name;
        var state = document.createElement('span'); state.className = 'mcp-state ' + (sv.connected ? 'ok' : sv.enabled ? 'bad' : '');
        state.textContent = !sv.enabled ? 'switched off' : sv.connected ? 'connected · ' + sv.tool_list.length + ' tool' + (sv.tool_list.length === 1 ? '' : 's') : 'not connected' + (sv.error ? ': ' + sv.error : '');
        var btns = [['Reconnect', function () { api('/api/mcp', { connect: sv.name }).then(function (r) { mcpDraw(r); $('mcp-status').textContent = r.text; }).catch(function (e) { $('mcp-status').textContent = e.message; }); }],
                    ['Edit', function () {
                      mcpEditing = sv.name; $('mcp-name').value = sv.name; $('mcp-type').value = sv.type; $('mcp-enabled').checked = sv.enabled; $('mcp-command').value = sv.command || ''; $('mcp-url').value = sv.url || '';
                      $('mcp-headers').value = Object.keys(sv.headers || {}).map(function (k) { return k + ': ' + sv.headers[k]; }).join('\n');
                      $('mcp-env').value = Object.keys(sv.env || {}).map(function (k) { return k + '=' + sv.env[k]; }).join('\n');
                      $('mcp-words').value = (sv.words || []).join(', '); mcpType(); $('mcp-add').open = true; $('mcp-add-title').textContent = 'Change ' + sv.name; $('mcp-cancel').classList.remove('hidden');
                    }],
                    ['Remove', function () { if (!window.confirm('Remove ' + sv.name + '?')) return; api('/api/mcp', { remove: sv.name }).then(function (r) { mcpDraw(r); if (mcpEditing === sv.name) mcpReset(); }).catch(function (e) { $('mcp-status').textContent = e.message; }); }]];
        head.append(name, state);
        btns.forEach(function (b) { var x = document.createElement('button'); x.type = 'button'; x.className = 'settings-action'; x.textContent = b[0]; x.setAttribute('aria-label', b[0] + ' ' + sv.name); x.addEventListener('click', b[1]); head.append(x); });
        li.append(head);
        if (sv.tool_list.length) {
          var tl = document.createElement('ul'); tl.className = 'mcp-tools';
          sv.tool_list.forEach(function (t) {
            var row = document.createElement('li'), tn = document.createElement('span'), td = document.createElement('span');
            tn.className = 'mcp-tname'; tn.textContent = t.name; td.className = 'mcp-tdesc'; td.textContent = (t.usable ? '' : '(needs lists or objects, which Jarvis cannot fill in) ') + t.description + (t.read_only ? ' · says it only reads' : '');
            var use = document.createElement('label'), uc = document.createElement('input'); uc.type = 'checkbox'; uc.checked = t.use; uc.disabled = !t.usable; use.append(uc, document.createTextNode('use'));
            var auto = document.createElement('label'), ac = document.createElement('input'); ac.type = 'checkbox'; ac.checked = t.auto; ac.disabled = !t.usable; auto.append(ac, document.createTextNode('without asking'));
            var setTool = function (body) { api('/api/mcp', { tool: Object.assign({ server: sv.name, tool: t.name }, body) }).then(mcpDraw).catch(function (e) { $('mcp-status').textContent = e.message; }); };
            uc.addEventListener('change', function () { setTool({ use: uc.checked }); });
            ac.addEventListener('change', function () {
              if (ac.checked && !window.confirm('Let Jarvis run ' + sv.name + '’s “' + t.name + '” without asking you first? Only do this for tools that just read information.')) { ac.checked = false; return; }
              setTool({ auto: ac.checked });
            });
            row.append(tn, td, use, auto); tl.append(row);
          });
          li.append(tl);
        }
        list.append(li);
      });
      if (!(d.servers || []).length) { var li = document.createElement('li'); li.textContent = 'No servers yet.'; list.append(li); }
    };
    var mcpLoad = function () { api('/api/mcp').then(mcpDraw).catch(function () {}); };
    $('mcp-type').addEventListener('change', mcpType);
    $('mcp-cancel').addEventListener('click', function () { mcpReset(); $('mcp-add').open = false; });
    $('mcp-save').addEventListener('click', function () {
      $('mcp-status').textContent = 'Connecting…'; $('mcp-save').disabled = true;
      api('/api/mcp', { replace: mcpEditing, save: { name: $('mcp-name').value, type: $('mcp-type').value, enabled: $('mcp-enabled').checked, command: $('mcp-command').value, url: $('mcp-url').value,
        headers: $('mcp-headers').value, env: $('mcp-env').value, words: $('mcp-words').value } })
        .then(function (d) { mcpDraw(d); $('mcp-status').textContent = d.text; mcpReset(); $('mcp-add').open = false; })
        .catch(function (e) { $('mcp-status').textContent = e.message; })
        .then(function () { $('mcp-save').disabled = false; });
    });
    mcpType();
    window.addEventListener('jarvis:pane', function (e) { if (e.detail && paneHas(e.detail.pane, 'mcp-list')) mcpLoad(); });
  }
  if ($('gr-add')) {
    var grFmt = function (x) { return x == null ? '–' : String(Math.round(x * 100) / 100); };
    var grDraw = function (d) {
      var sel = $('gr-preset');
      if (!sel.options.length) { Object.keys(d.presets).forEach(function (k) { var o = document.createElement('option'); o.value = k; o.textContent = d.presets[k]; sel.append(o); }); var c = document.createElement('option'); c.value = 'custom'; c.textContent = 'My own scale'; sel.append(c); }
      sel.value = d.scale.preset; $('gr-custom').classList.toggle('hidden', d.scale.preset !== 'custom');
      $('gr-min').value = d.scale.min; $('gr-max').value = d.scale.max; $('gr-pass').value = d.scale.pass; $('gr-higher').checked = !!d.scale.higher_better;
      $('gr-value').min = d.scale.min; $('gr-value').max = d.scale.max;
      var dl = $('gr-subjects'); dl.textContent = ''; (d.known || []).forEach(function (n) { var o = document.createElement('option'); o.value = n; dl.append(o); });
      var list = $('gr-list'); list.textContent = '';
      d.subjects.forEach(function (sub) {
        var li = document.createElement('li'), head = document.createElement('div'), chips = document.createElement('div');
        head.className = 'gr-head'; chips.className = 'gr-chips';
        var name = document.createElement('strong'); name.textContent = sub.subject;
        var avg = document.createElement('span'); avg.className = 'gr-avg' + (sub.passing ? '' : ' low'); avg.textContent = grFmt(sub.average) + (sub.rounded != null && sub.rounded !== sub.average ? ' → ' + grFmt(sub.rounded) : '');
        var n = document.createElement('span'); n.className = 'settings-note'; n.textContent = sub.count + ' grade' + (sub.count === 1 ? '' : 's');
        head.append(name, avg, n);
        sub.grades.forEach(function (g) {
          var chip = document.createElement('span'), x = document.createElement('button');
          chip.className = 'gr-chip'; chip.title = g.date + (g.note ? ' · ' + g.note : '') + (g.weight !== 1 ? ' · weight ' + g.weight : '');
          chip.textContent = grFmt(g.value) + (g.weight === 2 ? '×2' : g.weight === 3 ? '×3' : g.weight === 0.5 ? '×½' : '');
          x.type = 'button'; x.textContent = '×'; x.setAttribute('aria-label', 'Remove ' + g.value + ' in ' + sub.subject + ' from ' + g.date);
          x.addEventListener('click', function () { api('/api/grades', { remove: g.id }).then(grDraw).catch(function (e) { $('gr-status').textContent = e.message; }); });
          chip.append(x); chips.append(chip);
        });
        li.append(head, chips); list.append(li);
      });
      if (!d.subjects.length) { var li = document.createElement('li'); li.textContent = 'No grades yet' + (d.term_start ? ' this term' : '') + '.'; list.append(li); }
      $('gr-overall').textContent = d.overall == null ? '' : 'Overall average (mean of the subject averages): ' + grFmt(d.overall) + (d.term_start ? ' · term started ' + d.term_start : '') + (d.earlier ? ' · ' + d.earlier + ' earlier grade' + (d.earlier === 1 ? '' : 's') + ' kept' : '');
    };
    var grLoad = function () { api('/api/grades').then(grDraw).catch(function () {}); };
    var grErr = function (e) { $('gr-status').textContent = e.message; };
    $('gr-date').value = new Date().toISOString().slice(0, 10);
    $('gr-add').addEventListener('click', function () {
      api('/api/grades', { add: { subject: $('gr-subject').value, value: $('gr-value').value, weight: $('gr-weight').value, date: $('gr-date').value, note: $('gr-note').value } })
        .then(function (d) { grDraw(d); $('gr-status').textContent = 'Added.'; $('gr-value').value = ''; $('gr-note').value = ''; $('gr-weight').value = '1'; $('gr-value').focus(); }).catch(grErr);
    });
    $('gr-preset').addEventListener('change', function () {
      if (this.value === 'custom') { $('gr-custom').classList.remove('hidden'); return; }
      api('/api/grades', { scale: { preset: this.value } }).then(function (d) { grDraw(d); $('gr-status').textContent = 'Scale saved.'; }).catch(function (e) { grErr(e); grLoad(); });
    });
    $('gr-scale-save').addEventListener('click', function () {
      api('/api/grades', { scale: { min: $('gr-min').value, max: $('gr-max').value, pass: $('gr-pass').value, higher_better: $('gr-higher').checked, round: 0 } }).then(function (d) { grDraw(d); $('gr-status').textContent = 'Scale saved.'; }).catch(grErr);
    });
    $('gr-term').addEventListener('click', function () {
      if (!window.confirm('Start a new term? Averages will count only the grades you add from now on. Earlier grades are kept.')) return;
      api('/api/grades', { new_term: true }).then(function (d) { grDraw(d); $('gr-status').textContent = 'New term started.'; }).catch(grErr);
    });
    window.addEventListener('jarvis:pane', function (e) { if (e.detail && paneHas(e.detail.pane, 'gr-list')) grLoad(); });
    window.addEventListener('jarvis:reply', function (e) { if (e.detail && /grade|average|term/i.test(e.detail.text || '')) grLoad(); });
  }
  if ($('bench-start')) {
    var benchTimer = null, benchRunId = null, benchShown = '';
    var esc = function (t) { var d = document.createElement('div'); d.textContent = t == null ? '' : String(t); return d.innerHTML; };
    var letters = 'ABCD';
    var order = function (run, i) {            // the same shuffled order for a question every time it is drawn
      var m = run.models.slice(), seed = 7 + i * 31 + run.id.length;
      for (var k = m.length - 1; k > 0; k--) { seed = (seed * 9301 + 49297) % 233280; var j = Math.floor(seed / 233280 * (k + 1)); var t = m[k]; m[k] = m[j]; m[j] = t; }
      return m;
    };
    var drawRun = function (run) {
      var box = $('bench-results');
      if (!run) { box.textContent = ''; return; }
      var key = JSON.stringify([run.id, run.summary, run.questions.map(function (q) { return q.pick; })]);
      if (key === benchShown) return; benchShown = key; benchRunId = run.id;
      var html = '<p class="settings-note">Comparison of ' + esc(run.at) + (run.stopped ? ' (stopped early)' : '') + ':</p><div class="bench-wrap"><table class="bench-table"><thead><tr><th>Model</th><th>Seconds per answer</th><th>Tokens per second</th><th>Checks passed</th><th>Your picks</th>' + (run.smart ? '<th>Smart commands</th>' : '') + '</tr></thead><tbody>';
      run.models.forEach(function (m) {
        var s = run.summary[m] || {}, sm = (run.smart || {})[m] || {};
        html += '<tr><td>' + esc(m) + (s.errors ? ' <span class="bench-check bad">(' + s.errors + ' failed)</span>' : '') + '</td><td class="num">' + (s.avg_seconds == null ? '–' : s.avg_seconds) + '</td><td class="num">' + (s.tokens_per_second == null ? '–' : s.tokens_per_second) + '</td><td class="num">' + (s.checks_pct == null ? '–' : s.checks_passed + '/' + s.checks_total + ' (' + s.checks_pct + '%)') + '</td><td class="num">' + (s.picks || 0) + '</td>' + (run.smart ? '<td class="num">' + (sm.right_tool_pct == null ? (sm.error ? 'failed' : '–') : sm.right_tool_pct + '% right, ' + sm.false_alarm_pct + '% false alarms') + '</td>' : '') + '</tr>';
      });
      html += '</tbody></table></div>';
      run.questions.forEach(function (q, i) {
        var models = order(run, i), picked = q.pick;
        html += '<details class="bench-q"><summary>' + (i + 1) + '. ' + esc(q.text) + (q.source === 'mine' ? ' <em>(yours)</em>' : '') + (picked ? '<span class="bench-pickmark">✓ ' + esc(picked) + '</span>' : '') + '</summary>';
        models.forEach(function (m, k) {
          var a = q.answers[m]; if (!a) return;
          var label = picked ? esc(m) : 'Answer ' + letters[k];
          html += '<div class="bench-ans' + (picked === m ? ' picked' : '') + '"><div class="bench-ans-head"><strong>' + label + '</strong>' + (a.seconds != null ? '<span>' + a.seconds + ' s</span>' : '') +
            (a.checks || []).map(function (c) { return '<span class="bench-check ' + (c[1] ? 'ok' : 'bad') + '">' + (c[1] ? '✓ ' : '✗ ') + esc(c[0]) + '</span>'; }).join('') +
            '<button type="button" class="settings-action bench-pick" data-i="' + i + '" data-m="' + esc(m) + '">' + (picked === m ? 'Picked' : 'Best') + '</button></div>' +
            (a.error ? '<p class="bench-check bad">' + esc(a.error) + '</p>' : '<pre>' + esc(a.text) + '</pre>') + '</div>';
        });
        html += '</details>';
      });
      var open = Array.prototype.map.call(box.querySelectorAll('details.bench-q'), function (d) { return d.open; });
      box.innerHTML = html;
      Array.prototype.forEach.call(box.querySelectorAll('details.bench-q'), function (d, i) { if (open[i]) d.open = true; });
    };
    var drawState = function (d) {
      var models = d.models || [], box = $('bench-models');
      if (box.dataset.list !== models.join('|')) {
        var was = Array.prototype.filter.call(box.querySelectorAll('input:checked'), function () { return true; }).map(function (x) { return x.value; });
        box.dataset.list = models.join('|'); box.textContent = '';
        models.forEach(function (m) {
          var l = document.createElement('label'), c = document.createElement('input'); c.type = 'checkbox'; c.value = m;
          c.checked = was.length ? was.indexOf(m) >= 0 : (m === d.current || m.split(':')[0] === d.current || models.length <= 2);
          l.append(c, document.createTextNode(m)); box.append(l);
        });
        if (!models.length) box.textContent = d.ollama ? 'No models in Ollama yet.' : 'Ollama is not running, so the models cannot be listed.';
      }
      $('bench-start').classList.toggle('hidden', !!d.running); $('bench-stop').classList.toggle('hidden', !d.running);
      $('bench-status').textContent = d.running ? 'Working: ' + d.step + ' (' + d.done + ' of ' + d.total + ')…' : d.error ? 'Stopped: ' + d.error : '';
      if (d.own_available === 0) { var o = $('bench-set').querySelector('option[value="mine"]'); if (o) o.textContent = 'My own questions (none logged yet)'; }
      if (!d.running) drawRun(d.run);
      clearTimeout(benchTimer); if (d.running) benchTimer = setTimeout(benchLoad, 1500);
    };
    var benchLoad = function () { api('/api/bench').then(drawState).catch(function (e) { $('bench-status').textContent = e.message; }); };
    $('bench-start').addEventListener('click', function () {
      var models = Array.prototype.map.call(document.querySelectorAll('#bench-models input:checked'), function (x) { return x.value; });
      if (models.length > 4) { $('bench-status').textContent = 'Pick at most four models.'; return; }
      api('/api/bench', { start: { models: models, set: $('bench-set').value, smart: $('bench-smart').checked } }).then(drawState).catch(function (e) { $('bench-status').textContent = e.message; });
    });
    $('bench-stop').addEventListener('click', function () { api('/api/bench', { stop: true }).then(drawState).catch(function () {}); });
    $('bench-results').addEventListener('click', function (e) {
      var b = e.target.closest('.bench-pick'); if (!b || !benchRunId) return;
      api('/api/bench', { pick: { run: benchRunId, index: +b.dataset.i, model: b.dataset.m } }).then(drawState).catch(function (err) { $('bench-status').textContent = err.message; });
    });
    window.addEventListener('jarvis:pane', function (e) { if (e.detail && paneHas(e.detail.pane, 'bench-models')) benchLoad(); });
  }
  if ($('aware-on')) {
    var awPost = function (body) {
      return fetch('/api/awareness', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
        .then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || 'Request failed'); awDraw(d); return d; }); });
    };
    var awDraw = function (d) {
      $('aware-on').checked = !!d.on; $('aware-every').value = String(d.every); $('aware-keep').value = String(d.keep);
      if (document.activeElement !== $('aware-skip')) $('aware-skip').value = d.skip || '';
      var badge = $('aware-badge'); badge.classList.toggle('hidden', !d.on); badge.classList.toggle('aware-paused', !!d.paused);
      var st = $('aware-status'); st.textContent = '';
      var part = function (cls, text, raw) { var e = document.createElement('span'); e.className = cls; e.textContent = text; if (raw) e.setAttribute('data-no-i18n', ''); st.append(e, ' '); };
      if (!d.on) part('aw-l', 'Off.');
      else if (d.paused) { part('aw-l', 'Paused until'); part('aw-v', new Date(d.paused_until * 1000).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }) + '.', true); }
      else { part('aw-l', 'On.'); part('aw-l', 'Moments in memory:'); part('aw-v', String(d.moments), true); }
      $('aware-pause').textContent = d.paused ? 'Resume now' : 'Pause for an hour';
    };
    var awLoad = function () { fetch('/api/awareness').then(function (r) { return r.json(); }).then(awDraw).catch(function () {}); };
    $('aware-on').addEventListener('change', function () { awPost({ on: $('aware-on').checked }).catch(function (e) { $('aware-status').textContent = e.message; }); });
    $('aware-save').addEventListener('click', function () {
      awPost({ every: +$('aware-every').value, keep: +$('aware-keep').value, skip: $('aware-skip').value }).then(function () { $('aware-status').prepend('Saved. '); }).catch(function (e) { $('aware-status').textContent = e.message; });
    });
    $('aware-pause').addEventListener('click', function () { awPost({ pause_minutes: $('aware-badge').classList.contains('aware-paused') ? 0 : 60 }).catch(function () {}); });
    $('aware-badge').addEventListener('click', function () { awPost({ pause_minutes: $('aware-badge').classList.contains('aware-paused') ? 0 : 60 }).catch(function () {}); });
    window.addEventListener('jarvis:pane', function (e) { if (e.detail && paneHas(e.detail.pane, 'aware-on')) awLoad(); });
    window.addEventListener('jarvis:reply', function (e) { if (e.detail && /screen awareness|écran/i.test(e.detail.text || '')) awLoad(); });
    awLoad(); setInterval(awLoad, 60000);
  }
  if ($('tr-save')) {
    var trPost = function (body) {
      return fetch('/api/transport', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
        .then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || 'Request failed'); return d; }); });
    };
    var trDraw = function (d) {
      var c = d.settings || {};
      $('tr-home').value = c.home || ''; $('tr-school').value = c.school || ''; $('tr-walk-home').value = c.walk_home; $('tr-walk-school').value = c.walk_school;
      $('tr-margin').value = c.margin; $('tr-notice').value = c.notice; $('tr-morning').checked = !!c.morning; $('tr-call').checked = !!c.call;
    };
    var trLoad = function () { fetch('/api/transport').then(function (r) { return r.json(); }).then(trDraw).catch(function () {}); };
    $('tr-save').addEventListener('click', function () {
      $('tr-status').textContent = 'Looking up the stops…';
      trPost({ settings: { home: $('tr-home').value, school: $('tr-school').value, walk_home: +$('tr-walk-home').value, walk_school: +$('tr-walk-school').value,
        margin: +$('tr-margin').value, notice: +$('tr-notice').value, morning: $('tr-morning').checked, call: $('tr-call').checked } })
        .then(function (d) { trDraw(d); $('tr-status').textContent = 'Saved.'; }).catch(function (e) { $('tr-status').textContent = e.message; });
    });
    $('tr-test').addEventListener('click', function () {
      $('tr-status').textContent = 'Asking the timetable…';
      trPost({ test: true }).then(function (d) {
        var list = $('tr-list'); list.textContent = '';
        (d.lines || []).forEach(function (t) { var li = document.createElement('li'); li.textContent = t; list.append(li); });
        $('tr-status').textContent = (d.lines || []).length ? '' : 'No connections found.';
      }).catch(function (e) { $('tr-status').textContent = e.message; });
    });
    window.addEventListener('jarvis:pane', function (e) { if (e.detail && paneHas(e.detail.pane, 'tr-home')) trLoad(); });
  }
  if ($('coach-save')) {
    var coachPost = function (body) {
      return fetch('/api/coach', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
        .then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || 'Request failed'); if (d.settings) coachDraw(d); return d; }); });
    };
    var coachStatus = function (t) { $('coach-status').textContent = t || ''; };
    var coachDraw = function (d) {
      var c = d.settings || {}, wd = (c.weekday || '17:00-20:00').split('-'), we = (c.weekend || '10:00-17:00').split('-');
      if (document.activeElement && document.activeElement.closest && document.activeElement.closest('.coach-form')) { /* do not overwrite what is being typed */ } else {
        $('coach-auto').checked = !!c.auto; $('coach-horizon').value = c.horizon; $('coach-wd-from').value = wd[0]; $('coach-wd-to').value = wd[1];
        $('coach-we-from').value = we[0]; $('coach-we-to').value = we[1]; $('coach-minutes').value = String(c.minutes); $('coach-per-day').value = String(c.per_day);
        $('coach-break').value = String(c.after_school); $('coach-weekly').checked = !!c.weekly; $('coach-weekly-day').value = String(c.weekly_day); $('coach-weekly-time').value = c.weekly_time;
      }
      var list = $('coach-list'); list.textContent = '';
      (d.sessions || []).forEach(function (x) {
        var li = document.createElement('li'), text = document.createElement('span'), when = document.createElement('span');
        li.className = 'coach-item' + (x.done ? ' coach-done' : '');
        when.className = 'coach-when'; when.setAttribute('data-no-i18n', '');
        when.textContent = new Date(x.due * 1000).toLocaleString(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
        text.className = 'coach-text'; text.setAttribute('data-no-i18n', ''); text.textContent = x.subject + ' · ' + x.minutes + ' min · ' + x.exam;
        li.append(when, text);
        if (x.done) { var ok = document.createElement('span'); ok.className = 'coach-ok'; ok.textContent = '✓ done'; li.append(ok); }
        else {
          var done = document.createElement('button'), skip = document.createElement('button');
          done.type = skip.type = 'button'; done.className = skip.className = 'settings-action';
          done.textContent = 'Done'; skip.textContent = 'Skip';
          done.addEventListener('click', function () { coachPost({ done: x.id }).catch(function (e) { coachStatus(e.message); }); });
          skip.addEventListener('click', function () { coachPost({ skip: x.id }).then(function (r) { coachStatus(r.text); }).catch(function (e) { coachStatus(e.message); }); });
          li.append(done, skip);
        }
        list.append(li);
      });
      if (!(d.sessions || []).length) { var li = document.createElement('li'); li.textContent = 'No revision planned. Add a test above, or say “my physics test is on Friday at 8am”.'; list.append(li); }
    };
    var coachLoad = function () { fetch('/api/coach').then(function (r) { return r.json(); }).then(coachDraw).catch(function () {}); };
    var coachSettings = function () {
      return { auto: $('coach-auto').checked, horizon: +$('coach-horizon').value, weekday: $('coach-wd-from').value + '-' + $('coach-wd-to').value,
        weekend: $('coach-we-from').value + '-' + $('coach-we-to').value, minutes: +$('coach-minutes').value, per_day: +$('coach-per-day').value,
        after_school: +$('coach-break').value, weekly: $('coach-weekly').checked, weekly_day: +$('coach-weekly-day').value, weekly_time: $('coach-weekly-time').value };
    };
    $('coach-save').addEventListener('click', function () {
      coachPost({ settings: coachSettings(), replan_after: true }).then(function () { coachStatus('Saved. Your revision is planned again with these times.'); }).catch(function (e) { coachStatus(e.message); });
    });
    $('coach-replan').addEventListener('click', function () {
      coachPost({ replan: true }).then(function () { coachStatus('Your revision is planned again.'); }).catch(function (e) { coachStatus(e.message); });
    });
    ['coach-auto', 'coach-weekly'].forEach(function (id) {
      $(id).addEventListener('change', function () { coachPost({ settings: coachSettings() }).then(function () { coachStatus('Saved.'); }).catch(function (e) { coachStatus(e.message); }); });
    });
    var readFile = function (f) {
      return new Promise(function (ok, bad) { var r = new FileReader(); r.onload = function () { ok(String(r.result).replace(/^data:[^,]*,/, '')); }; r.onerror = bad; r.readAsDataURL(f); });
    };
    $('cards-make').addEventListener('click', function () {
      var files = Array.prototype.slice.call($('cards-files').files || [], 0, 4), text = $('cards-text').value.trim();
      if (!files.length && !text) { $('cards-status').textContent = 'Choose photos of your notes, or paste the text.'; return; }
      $('cards-status').textContent = 'Reading your notes… this can take a minute.'; $('cards-make').disabled = true;
      Promise.all(files.map(readFile)).then(function (images) {
        return coachPost({ cards: { subject: $('cards-subject').value, text: text, images: images } });
      }).then(function (d) {
        var list = $('cards-result'); list.textContent = '';
        (d.cards || []).forEach(function (c) { var li = document.createElement('li'); li.setAttribute('data-no-i18n', ''); li.textContent = c.q + ' → ' + c.a; list.append(li); });
        $('cards-status').textContent = (d.cards || []).length + ' flashcards added to your deck.';
        $('cards-files').value = ''; $('cards-text').value = '';
      }).catch(function (e) { $('cards-status').textContent = e.message; }).then(function () { $('cards-make').disabled = false; });
    });
    window.addEventListener('jarvis:pane', function (e) { if (e.detail && paneHas(e.detail.pane, 'coach-list')) coachLoad(); });
    window.addEventListener('jarvis:reply', function (e) { if (e.detail && /revis|test|exam/i.test(e.detail.text || '')) coachLoad(); });
  }
  if ($('hw-add')) {
    var hwStatus = function (t) { $('hw-status').textContent = t || ''; };
    var hwPost = function (body) {
      return fetch('/api/homework', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
        .then(function (r) { return r.json().then(function (d) { if (d.items) hwDraw(d); if (!r.ok) throw new Error(d.error || 'Request failed'); return d; }); });
    };
    var hwDraw = function (d) {
      var list = $('homework-list'); list.textContent = '';
      (d.items || []).forEach(function (h) {
        var li = document.createElement('li'), box = document.createElement('input'), text = document.createElement('span'), when = document.createElement('span'), x = document.createElement('button');
        li.className = 'hw-item' + (h.late ? ' hw-late' : '');
        box.type = 'checkbox'; box.setAttribute('aria-label', 'Done: ' + h.text);
        box.addEventListener('change', function () { hwPost({ done: h.id }).catch(function (e) { hwStatus(e.message); }); });
        text.className = 'hw-text'; text.setAttribute('data-no-i18n', ''); text.textContent = h.text;
        when.className = 'hw-when'; when.textContent = h.due ? (h.late ? 'late' : new Date(h.due * 1000).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })) : 'no date';
        li.append(box, text, when);
        if (h.link) { var a = document.createElement('a'); a.href = h.link; a.target = '_blank'; a.rel = 'noopener'; a.className = 'hw-link'; a.textContent = 'Classroom'; li.append(a); }
        x.type = 'button'; x.className = 'settings-action'; x.textContent = 'Remove'; x.setAttribute('aria-label', 'Remove ' + h.text);
        x.addEventListener('click', function () { hwPost({ remove: h.id }).catch(function (e) { hwStatus(e.message); }); });
        li.append(x); list.append(li);
      });
      if (!(d.items || []).length) { var li = document.createElement('li'); li.textContent = 'No homework. Well done.'; list.append(li); }
      var dl = $('hw-subjects'); dl.textContent = '';
      (d.subjects || []).forEach(function (s) { var o = document.createElement('option'); o.value = s; dl.append(o); });
      var c = d.classroom || {};
      $('classroom-redirect').value = c.redirect_uri || '';
      if (c.client_id && !$('classroom-id').value) $('classroom-id').value = c.client_id;
      $('classroom-secret').placeholder = c.has_secret ? 'saved (leave empty to keep it)' : '';
      $('classroom-sync').classList.toggle('hidden', !c.connected); $('classroom-disconnect').classList.toggle('hidden', !c.connected);
      $('classroom-connect').textContent = c.connected ? 'Connect again' : 'Connect';
      var box = $('classroom-status'); box.textContent = '';
      var part = function (cls, text, data) { var e = document.createElement('span'); e.className = cls; if (data) e.setAttribute('data-no-i18n', ''); e.textContent = text; box.append(e, ' '); };
      part('cr-state', c.connected ? 'Connected.' : 'Not connected.');
      if (c.connected && c.courses && c.courses.length) { part('cr-label', 'Classes:'); part('cr-courses', c.courses.join(', ') + '.', true); }
      if (c.connected && c.last_sync) { part('cr-label', 'Last checked:'); part('cr-when', new Date(c.last_sync * 1000).toLocaleString(undefined, { weekday: 'short', hour: '2-digit', minute: '2-digit' }) + '.', true); }
      if (c.last_error) part('cr-error', c.last_error, true);
    };
    var hwLoad = function () { fetch('/api/homework').then(function (r) { return r.json(); }).then(hwDraw).catch(function () {}); };
    $('hw-due').addEventListener('change', function () { $('hw-date').classList.toggle('hidden', $('hw-due').value !== 'date'); });
    $('hw-add').addEventListener('click', function () {
      var due = $('hw-due').value === 'date' ? $('hw-date').value : 'next';
      if (!due) { hwStatus('Choose the date.'); return; }
      hwPost({ add: { subject: $('hw-subject').value, what: $('hw-what').value, due: due } })
        .then(function () { hwStatus(''); $('hw-what').value = ''; $('hw-what').focus(); }).catch(function (e) { hwStatus(e.message); });
    });
    $('hw-what').addEventListener('keydown', function (e) { if (e.key === 'Enter') $('hw-add').click(); });
    $('classroom-connect').addEventListener('click', function () {
      var tab = window.open('about:blank', '_blank');
      hwPost({ classroom: { connect: { client_id: $('classroom-id').value, client_secret: $('classroom-secret').value } } })
        .then(function (d) {
          $('classroom-secret').value = '';
          if (tab) tab.location.href = d.url; else window.location.href = d.url;
          $('classroom-status').textContent = 'Sign in with your school account in the new tab, then come back here.';
          var tries = 0, poll = setInterval(function () {
            tries += 1; if (tries > 60) { clearInterval(poll); return; }
            fetch('/api/homework').then(function (r) { return r.json(); }).then(function (x) { if (x.classroom && (x.classroom.connected && x.classroom.last_sync || x.classroom.last_error)) { clearInterval(poll); hwDraw(x); } }).catch(function () {});
          }, 3000);
        })
        .catch(function (e) { if (tab) tab.close(); $('classroom-status').textContent = e.message; });
    });
    $('classroom-sync').addEventListener('click', function () {
      $('classroom-status').textContent = 'Checking Classroom…';
      hwPost({ classroom: { sync: true } }).then(function (d) { hwStatus(d.new ? d.new + ' new from Classroom.' : 'Nothing new on Classroom.'); }).catch(function (e) { hwStatus(e.message); });
    });
    $('classroom-disconnect').addEventListener('click', function () {
      if (!confirm('Disconnect Google Classroom? Its assignments that are not done leave your homework list.')) return;
      hwPost({ classroom: { disconnect: true } }).catch(function (e) { hwStatus(e.message); });
    });
    window.addEventListener('jarvis:pane', function (e) { if (e.detail && paneHas(e.detail.pane, 'homework-list')) hwLoad(); });
    window.addEventListener('jarvis:reply', function (e) { if (e.detail && /homework|classroom/i.test(e.detail.text || '')) hwLoad(); });
  }
  if ($('tt-add')) {
    var ttDraw = function (d) {
      var list = $('tt-list'), last = -1; list.textContent = '';
      (d.lessons || []).forEach(function (l) {
        if (l.day !== last) { last = l.day; var h = document.createElement('li'); h.className = 'tt-day'; h.textContent = d.days[l.day]; list.append(h); }
        var li = document.createElement('li'), text = document.createElement('span'), x = document.createElement('button');
        text.className = 'tt-text'; text.textContent = l.start + '–' + l.end + '  ' + l.subject + (l.room ? ' · ' + l.room : '') + (l.bring ? ' · bring ' + l.bring : '');
        x.type = 'button'; x.className = 'settings-action'; x.textContent = 'Remove'; x.setAttribute('aria-label', 'Remove ' + l.subject + ' on ' + d.days[l.day] + ' at ' + l.start);
        x.addEventListener('click', function () { api('/api/timetable', { remove: l.id }).then(ttDraw).catch(function (e) { $('tt-status').textContent = e.message; }); });
        li.append(text, x); list.append(li);
      });
      if (!(d.lessons || []).length) { var li = document.createElement('li'); li.textContent = 'No lessons yet.'; list.append(li); }
      if (d.prep) { $('tt-prep').checked = !!d.prep.on; $('tt-prep-time').value = d.prep.time; }
      if (d.text) $('tt-status').textContent = d.text;
    };
    var ttLoad = function () { api('/api/timetable').then(ttDraw).catch(function () {}); };
    $('tt-add').addEventListener('click', function () {
      api('/api/timetable', { day: +$('tt-day').value, start: $('tt-start').value, end: $('tt-end').value, subject: $('tt-subject').value, room: $('tt-room').value, bring: $('tt-bring').value })
        .then(function (d) { ttDraw(d); $('tt-subject').value = ''; $('tt-room').value = ''; $('tt-bring').value = ''; $('tt-start').value = $('tt-end').value; $('tt-subject').focus(); })
        .catch(function (e) { $('tt-status').textContent = e.message; });
    });
    var ttPrep = function () { api('/api/timetable', { prep: { on: $('tt-prep').checked, time: $('tt-prep-time').value } }).then(ttDraw).catch(function (e) { $('tt-status').textContent = e.message; }); };
    $('tt-prep').addEventListener('change', ttPrep); $('tt-prep-time').addEventListener('change', ttPrep);
    window.addEventListener('jarvis:pane', function (e) { if (e.detail && paneHas(e.detail.pane, 'tt-list')) ttLoad(); });
    window.addEventListener('jarvis:reply', function (e) { if (e.detail && /timetable|lesson/i.test(e.detail.text || '')) ttLoad(); });
  }
  if ($('cd-add')) {
    var cdShort = function (c) { return c.on ? (c.left === 0 ? 'last day' : c.left + ' d left') : c.days === 0 ? 'today' : c.days === 1 ? 'tomorrow' : c.days + ' d'; };
    var drawCountdowns = function (d) {
      var items = d.items || [], list = $('cd-list'); list.textContent = '';
      items.forEach(function (c) {
        var li = document.createElement('li'), text = document.createElement('span'), x = document.createElement('button');
        if (c.past) li.className = 'cd-past';
        text.className = 'cd-text'; text.textContent = c.name + ': ' + c.text;
        x.type = 'button'; x.className = 'settings-action'; x.textContent = 'Remove';
        x.addEventListener('click', function () { api('/api/countdowns', { remove: c.id }).then(function (r) { drawCountdowns(r); $('cd-status').textContent = r.text; }).catch(function (e) { $('cd-status').textContent = e.message; }); });
        li.append(text, x); list.append(li);
      });
      if (!items.length) { var li = document.createElement('li'); li.textContent = 'No countdowns yet.'; list.append(li); }
      var next = items.filter(function (c) { return !c.past; })[0], chip = $('countdown-chip');
      if (chip) {
        chip.classList.toggle('hidden', !next);
        if (next) { $('countdown-days').textContent = cdShort(next); $('countdown-name').textContent = next.name; chip.title = next.name + ': ' + next.text + ' Click to see all your countdowns.'; }
      }
    };
    var loadCountdowns = function () { api('/api/countdowns').then(drawCountdowns).catch(function () {}); };
    $('cd-add').addEventListener('click', function () {
      api('/api/countdowns', { name: $('cd-name').value, start: $('cd-start').value, end: $('cd-end').value || null }).then(function (d) {
        drawCountdowns(d); $('cd-status').textContent = d.text; $('cd-name').value = ''; $('cd-start').value = ''; $('cd-end').value = '';
      }).catch(function (e) { $('cd-status').textContent = e.message; });
    });
    if ($('countdown-chip')) $('countdown-chip').addEventListener('click', function () { if (window.JarvisUI) window.JarvisUI.openPane('plan'); });
    window.addEventListener('jarvis:pane', function (e) { if (e.detail && paneHas(e.detail.pane, 'cd-list')) loadCountdowns(); });
    window.addEventListener('jarvis:reply', loadCountdowns);
    loadCountdowns(); setInterval(loadCountdowns, 30 * 60 * 1000);
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
    window.addEventListener('jarvis:pane', function (e) { if (e.detail && e.detail.pane) { if (paneHas(e.detail.pane, 'exam-status')) loadExams(); if (paneHas(e.detail.pane, 'focus-status')) loadFocus(); } });
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
    window.addEventListener('jarvis:pane', function (e) { if (e.detail && paneHas(e.detail.pane, 'net-watch')) api('/api/network').then(function (d) { $('net-watch').checked = d.watch; }).catch(function () {}); });
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
    window.addEventListener('jarvis:pane', function (e) { if (e.detail && paneHas(e.detail.pane, 'jm-build')) jmLoad(); });
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
    window.addEventListener('jarvis:pane', function (e) { if (e.detail && paneHas(e.detail.pane, 'install-folder')) installLoad(); });
    installLoad();
  }
  var selftestFixes = function (results) {
    var box = $('selftest-fixes'), tr = function (t) { return window.JarvisI18n ? window.JarvisI18n.t(t) : t; };
    results.filter(function (r) { return r.fix; }).forEach(function (r) {
      var btn = document.createElement('button'); btn.type = 'button'; btn.textContent = tr(r.fix.label); btn.title = r.name; btn.setAttribute('data-fix', r.fix.do);
      btn.addEventListener('click', function () {
        var how = r.fix.do;
        if (how.indexOf('pane:') === 0) { window.JarvisUI.openPane(how.slice(5)); return; }
        if (how === 'pull_coder') { btn.disabled = true; api('/api/coder', { pull: true }).then(function () { btn.textContent = tr('Downloading: the progress is in Jarvis Code.'); }).catch(function (e) { btn.disabled = false; btn.textContent = e.message; }); return; }
        var body = how === 'pull' ? { pull: 'qwen3-vl:8b-instruct' } : how === 'install_browser' ? { install_browser: true } : how === 'install_recording' ? { install_recording: true } : null;
        if (!body) return;
        btn.disabled = true;
        api('/api/control', body).then(function () { btn.textContent = tr('Started: the progress is in Settings > Computer control.'); window.JarvisUI.openPane('control'); })
          .catch(function (e) { btn.disabled = false; btn.textContent = e.message; });
      });
      box.append(btn);
    });
    box.classList.toggle('hidden', !box.children.length);
  };
  if ($('selftest-run')) {
    $('selftest-run').addEventListener('click', function () {
      var b = $('selftest-run'); b.disabled = true; $('selftest-copy').disabled = true; $('selftest-report').textContent = 'Checking… (up to a minute)';
      $('selftest-fixes').textContent = ''; $('selftest-fixes').classList.add('hidden');
      api('/api/selftest', {}).then(function (d) { $('selftest-report').textContent = d.text; $('selftest-copy').disabled = false; selftestFixes(d.results || []); })
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
      $('ctl-marks').checked = d.marks !== false; $('ctl-screens').value = d.screens || 'main'; $('ctl-browser').checked = d.browser !== false; $('ctl-learn').checked = d.learn !== false;
      var mn = $('ctl-model-now'), mk = function (cls, text, raw) { var e = document.createElement('span'); e.className = cls; e.textContent = text; if (raw) e.setAttribute('data-no-i18n', ''); return e; };
      mn.textContent = '';
      mn.append(mk('ctl-l', 'Autopilot uses:'), ' ', mk('ctl-m', d.model_now || '?', true), ' ', mk('ctl-l', d.sight_now === 'picture' ? (d.coords_now === 'thousandths' ? '(sees the screen, positions in thousandths)' : '(sees the screen)') : '(text only: this model cannot see pictures)'));
      var sel = $('ctl-model'), keep = d.model || '';
      while (sel.options.length > 1) sel.remove(1);
      (d.vision_models || []).concat(keep && (d.vision_models || []).indexOf(keep) < 0 ? [keep] : []).forEach(function (m) { var o = document.createElement('option'); o.value = o.textContent = m; sel.append(o); });
      sel.value = keep;
      var p = d.pull || {};
      $('ctl-pull').classList.toggle('hidden', !!d.has_recommended || !d.local);
      $('ctl-pull').disabled = !!p.running;
      $('ctl-pull-status').textContent = p.running ? (window.JarvisI18n ? window.JarvisI18n.t('Downloading…') : 'Downloading…') + ' ' + (p.total ? Math.round(100 * p.done / p.total) + ' %' : (p.status || ''))
        : p.error ? p.error : (p.status === 'success' ? (window.JarvisI18n ? window.JarvisI18n.t('Downloaded. Autopilot uses it now.') : 'Downloaded. Autopilot uses it now.') : (d.has_recommended ? (window.JarvisI18n ? window.JarvisI18n.t('qwen3-vl is installed.') : 'qwen3-vl is installed.')
          : d.slow_model ? (window.JarvisI18n ? window.JarvisI18n.t('The model Autopilot uses now thinks for a long time before each step. Download the instruct version for quick steps.') : 'The model Autopilot uses now thinks for a long time before each step. Download the instruct version for quick steps.') : ''));
      var inst = d.install || {};
      var forBrowser = (inst.package || 'playwright') === 'playwright';
      $('ctl-install').classList.toggle('hidden', !!d.browser_ready || !!inst.running);
      $('ctl-browser-status').textContent = d.browser_ready ? 'Browser control is ready.' : inst.running && forBrowser ? 'Installing browser control… (a minute or two)' : inst.error && forBrowser ? inst.error : 'Browser control needs a small extra package (Playwright).';
      $('teach-install').classList.toggle('hidden', !!d.recording_ready || !!inst.running);
      if (!teachState.recording && (!d.recording_ready || teachState.needed)) $('teach-status').textContent = d.recording_ready ? '' : inst.running && !forBrowser ? 'Installing recording… (under a minute)' : inst.error && !forBrowser ? inst.error : 'Recording what you do needs a small extra package (pynput).';
      $('teach-start').disabled = !d.recording_ready; teachState.needed = !d.recording_ready;
      var learned = $('ctl-learned'); learned.textContent = '';
      (d.learned || []).forEach(function (it) {
        var li = document.createElement('li'), t = document.createElement('span'), n = document.createElement('span'), x = document.createElement('button');
        t.className = 'ctl-task'; t.setAttribute('data-no-i18n', ''); t.textContent = it.task;
        n.className = 'ctl-steps'; n.textContent = ' · ' + it.steps + ' steps' + (it.taught ? ' · shown by you' : '') + (it.uses ? ' · reused ' + it.uses + '×' : '');
        x.type = 'button'; x.className = 'settings-action'; x.textContent = 'Forget';
        x.addEventListener('click', function () { ctlSave({ forget: it.id }); });
        li.append(t, n, ' ', x); learned.append(li);
      });
      if (!(d.learned || []).length) { var none = document.createElement('li'); none.textContent = window.JarvisI18n ? window.JarvisI18n.t('Nothing yet.') : 'Nothing yet.'; learned.append(none); }
      ctlState = d;
      clearTimeout(ctlTimer);
      if (p.running || inst.running) ctlTimer = setTimeout(function () { api('/api/control').then(ctlShow).catch(function () {}); }, 1500);
    };
    var ctlTimer = 0;
    var ctlState = { folders: [] };
    var teachState = { recording: false }, teachTimer = 0;
    var teachShow = function (d) {
      teachState = d;
      $('teach-start').classList.toggle('hidden', !!d.recording); $('teach-task').disabled = !!d.recording;
      $('teach-stop').classList.toggle('hidden', !d.recording); $('teach-cancel').classList.toggle('hidden', !d.recording);
      var steps = d.recording ? d.steps : (d.result && d.result.steps) || [], ol = $('teach-steps'); ol.textContent = '';
      steps.forEach(function (s) { var li = document.createElement('li'); li.textContent = s; ol.append(li); });
      if (d.recording) $('teach-status').textContent = (window.JarvisI18n ? window.JarvisI18n.t('Watching you… Press Ctrl+Shift+F9 when you are done.') : 'Watching you… Press Ctrl+Shift+F9 when you are done.');
      else if (d.result) $('teach-status').textContent = d.result.saved ? (window.JarvisI18n ? window.JarvisI18n.t('Learned. Autopilot will do it this way next time.') : 'Learned. Autopilot will do it this way next time.')
        : (window.JarvisI18n ? window.JarvisI18n.t('Nothing was kept.') : 'Nothing was kept.');
      clearTimeout(teachTimer);
      if (d.recording) teachTimer = setTimeout(function () { api('/api/teach').then(function (n) { teachShow(n); if (!n.recording) api('/api/control').then(ctlShow).catch(function () {}); }).catch(function () {}); }, 1500);
    };
    var teachSend = function (body) { return api('/api/teach', body).then(function (d) { teachShow(d); api('/api/control').then(ctlShow).catch(function () {}); }).catch(function (e) { $('teach-status').textContent = e.message; }); };
    $('teach-start').addEventListener('click', function () {
      var t = $('teach-task').value.trim();
      if (!t) { $('teach-status').textContent = window.JarvisI18n ? window.JarvisI18n.t('Write first what you are going to show.') : 'Write first what you are going to show.'; $('teach-task').focus(); return; }
      teachSend({ start: t });
    });
    $('teach-stop').addEventListener('click', function () { teachSend({ stop: true }); });
    $('teach-cancel').addEventListener('click', function () { teachSend({ cancel: true }); });
    $('teach-install').addEventListener('click', function () { api('/api/control', { install_recording: true }).then(ctlShow).catch(function (e) { $('teach-status').textContent = e.message; }); });
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
    $('ctl-marks').addEventListener('change', function () { ctlSave({ marks: $('ctl-marks').checked }); });
    $('ctl-screens').addEventListener('change', function () { ctlSave({ screens: $('ctl-screens').value }); });
    $('ctl-browser').addEventListener('change', function () { ctlSave({ browser: $('ctl-browser').checked }); });
    $('ctl-learn').addEventListener('change', function () { ctlSave({ learn: $('ctl-learn').checked }); });
    $('ctl-model').addEventListener('change', function () { ctlSave({ model: $('ctl-model').value }); });
    $('ctl-pull').addEventListener('click', function () { api('/api/control', { pull: ctlState.recommended || 'qwen3-vl:8b-instruct' }).then(ctlShow).catch(function (e) { $('ctl-pull-status').textContent = e.message; }); });
    $('ctl-install').addEventListener('click', function () { api('/api/control', { install_browser: true }).then(ctlShow).catch(function (e) { $('ctl-browser-status').textContent = e.message; }); });
    $('ctl-close-browser').addEventListener('click', function () { api('/api/control', { close_browser: true }).then(function (d) { ctlShow(d); $('ctl-status').textContent = 'The Jarvis browser is closed.'; }).catch(function () {}); });
    $('ctl-folder-add').addEventListener('click', function () {
      var f = $('ctl-folder').value.trim(); if (!f) return;
      ctlSave({ folders: (ctlState.folders || []).concat([f]) }).then(function () { if ($('ctl-status').textContent === 'Saved.') $('ctl-folder').value = ''; });
    });
    window.addEventListener('jarvis:pane', function (e) { if (e.detail && paneHas(e.detail.pane, 'ctl-status')) { api('/api/control').then(ctlShow).catch(function () {}); api('/api/teach').then(teachShow).catch(function () {}); } });
  }
})();

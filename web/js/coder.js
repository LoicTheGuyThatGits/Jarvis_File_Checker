/* Jarvis Code: pick a project, say what to build or fix, and follow the model as it reads, edits and checks the page. */
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var tr = function (s) { return window.JarvisI18n ? window.JarvisI18n.t(s) : s; };
  var state = { since: 0, shotAt: 0, sid: '', data: null, file: '', checkAt: 0, timer: 0 };
  var ICONS = { start: '▶', think: '…', read: '📄', list: '📁', find: '🔍', write: '✚', edit: '✎', check: '◉', run: '⚙', ask: '?', error: '✕', done: '✓', undo: '↶' };

  // the colours of the theme chosen in Jarvis
  try {
    var src = window.opener && window.opener.document ? getComputedStyle(window.opener.document.documentElement) : null;
    if (src) {
      [['--bg', '--bg'], ['--bg2', '--bg2'], ['--panel', '--panel'], ['--text', '--text'], ['--muted', '--muted'], ['--accent', '--t-accent']].forEach(function (p) {
        var v = src.getPropertyValue(p[1]).trim(); if (v) document.documentElement.style.setProperty(p[0], v);
      });
    }
  } catch (e) {}

  function api(path, body) {
    return fetch(path, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {})
      .then(function (r) { return r.json().then(function (d) { if (!r.ok) { var e = new Error(d.error || 'Something went wrong.'); e.data = d; throw e; } return d; }); });
  }
  function say(text, cls) { var s = $('status'); s.textContent = text; s.className = 'status' + (cls ? ' ' + cls : ''); }

  function diffHtml(pre, text, isDiff) {
    pre.textContent = '';
    text.split('\n').forEach(function (line, i) {
      var span = document.createElement('span');
      if (isDiff) span.className = line.charAt(0) === '+' ? 'add' : line.charAt(0) === '-' ? 'del' : line.indexOf('@@') === 0 ? 'at' : '';
      span.textContent = (i ? '\n' : '') + line;
      pre.append(span);
    });
  }

  function addEntry(e) {
    var log = $('log');
    var row = document.createElement(e.detail ? 'details' : 'div');
    row.className = 'entry ' + e.kind + (e.ok ? (e.kind === 'check' ? ' good' : '') : ' bad');
    var head = document.createElement(e.detail ? 'summary' : 'div');
    var ico = document.createElement('span'); ico.className = 'ico'; ico.textContent = ICONS[e.kind] || '•';
    var title = document.createElement('span'); title.setAttribute('data-no-i18n', ''); title.textContent = e.title;
    head.append(ico, title); row.append(head);
    if (e.detail) {
      var pre = document.createElement('pre'); pre.className = 'detail'; pre.setAttribute('data-no-i18n', '');
      diffHtml(pre, e.detail, e.kind === 'edit' || e.kind === 'write');
      row.append(pre);
      if ((e.kind === 'edit' || e.kind === 'write') && e.detail.split('\n').length < 30) row.open = true;
    }
    var near = log.scrollHeight - log.scrollTop - log.clientHeight < 80;
    log.insertBefore(row, $('live-box'));
    if (near) log.scrollTop = log.scrollHeight;
  }

  function liveBox() {
    var box = $('live-box');
    if (!box) { box = document.createElement('div'); box.id = 'live-box'; box.className = 'live hidden'; box.setAttribute('data-no-i18n', ''); $('log').append(box); }
    return box;
  }

  function showProjects(d) {
    var sel = $('project'), cur = d.session ? d.session.project : '';
    sel.textContent = '';
    var none = document.createElement('option'); none.value = ''; none.textContent = tr('Choose a project…'); sel.append(none);
    d.projects.forEach(function (p) {
      var o = document.createElement('option'); o.value = p.path; o.textContent = p.name + (p.source === 'workspace' ? '' : ' · ' + p.path);
      o.setAttribute('data-no-i18n', ''); sel.append(o);
    });
    sel.value = cur;
  }

  function showModel(d) {
    $('model-name').textContent = d.model || '?';
    var pulling = d.pull && d.pull.running && d.pull.model === d.recommended;
    $('pull').classList.toggle('hidden', d.has_recommended && !pulling);
    $('pull').disabled = !!pulling;
    if (pulling) $('pull').textContent = tr('Downloading…') + (d.pull.total ? ' ' + Math.round(100 * d.pull.done / d.pull.total) + ' %' : '');
    else if (d.pull && d.pull.error && d.pull.model === d.recommended) $('pull').textContent = d.pull.error;
    else $('pull').textContent = tr('Download qwen3.5:9b (6.6 GB)');
    $('model-chip').title = d.installed ? '' : tr('This model is not installed in Ollama.');
    var sm = $('set-model'); sm.textContent = '';
    var auto = document.createElement('option'); auto.value = ''; auto.textContent = tr('Automatic (best installed)'); sm.append(auto);
    d.models.forEach(function (m) { var o = document.createElement('option'); o.value = m; o.textContent = m; o.setAttribute('data-no-i18n', ''); sm.append(o); });
    sm.value = d.settings.model || '';
    $('set-steps').value = String(d.settings.max_turns);
  }

  function showCheck(s) {
    var c = s.check, box = $('problems');
    box.textContent = '';
    if (!c) return;
    var add = function (cls, text) { var div = document.createElement('div'); div.className = cls; div.textContent = text; box.append(div); };
    var bad = (c.errors || []).concat(c.failed || [], c.step_errors || []);
    bad.forEach(function (x) { add('err', '✕ ' + x); });
    (c.warnings || []).slice(0, 6).forEach(function (x) { add('warn', '⚠ ' + x); });
    if (c.blank) add('err', '✕ ' + tr('The page looks empty.'));
    if (!bad.length && !c.blank) add('ok', '✓ ' + tr('No errors in the last check.'));
    if (c.shot) { $('shot').src = 'data:image/jpeg;base64,' + c.shot; state.shotAt = c.at; $('shot-empty').classList.add('hidden'); }
    if (c.at) $('shot-when').textContent = tr('Looked at') + ' ' + new Date(c.at * 1000).toLocaleTimeString();
    if (c.at && c.at !== state.checkAt) { state.checkAt = c.at; reloadFrame(); }
  }

  function reloadFrame() {
    var s = state.data && state.data.session;
    if (!s || !s.preview) { $('frame').removeAttribute('src'); $('frame-empty').classList.remove('hidden'); $('url').value = ''; return; }
    $('frame-empty').classList.add('hidden');
    $('url').value = s.preview;
    $('frame').src = s.preview + (s.preview.indexOf('?') < 0 ? '?' : '&') + 'v=' + Date.now();
  }

  function show(d) {
    state.data = d;
    var s = d.session;
    showModel(d);
    if (document.activeElement !== $('project')) showProjects(d);
    var busy = !!s && (s.status === 'working' || s.status === 'waiting');
    $('start').classList.toggle('hidden', busy); $('stop').classList.toggle('hidden', !busy);
    $('start').disabled = !s; $('task').disabled = busy; $('project').disabled = busy; $('new-project').disabled = busy;
    $('check').disabled = busy || !s || !s.page; $('open-folder').disabled = !s;
    if (!s) { say(tr('Choose a project, or make a new one.')); return; }
    if (s.id !== state.sid) {                         // another task: start the log again
      state.sid = s.id; state.since = 0; $('log').textContent = ''; liveBox(); reloadFrame(); loadFiles();
      if (s.task && !$('task').value) $('task').value = s.task;
    }
    s.log.forEach(function (e) { if (e.n > state.since) { addEntry(e); state.since = e.n; if (e.kind === 'edit' || e.kind === 'write' || e.kind === 'undo') loadFiles(); } });
    var live = liveBox();
    live.classList.toggle('hidden', !(busy && s.live));
    if (busy && s.live) { live.textContent = s.live.split('\n').slice(-40).join('\n'); live.scrollTop = live.scrollHeight; }
    var words = { ready: tr('Ready.'), working: tr('Working') + ' · ' + tr('step') + ' ' + s.turn + ' / ' + s.max_turns, waiting: tr('Waiting for your OK.'),
      done: tr('Done.'), stopped: tr('Stopped.'), out_of_steps: tr('Out of steps.'), error: tr('Something went wrong.') };
    say(words[s.status] || s.status, busy ? 'working' : '');
    $('ask').classList.toggle('hidden', !s.pending);
    if (s.pending) $('ask-cmd').textContent = s.pending.command;
    var finished = ['done', 'stopped', 'out_of_steps', 'error'].indexOf(s.status) >= 0 || (s.status === 'ready' && s.can_undo);
    $('summary').classList.toggle('hidden', !finished);
    $('summary').classList.toggle('bad', s.status === 'error');
    $('summary-text').textContent = s.status === 'error' ? s.error : (s.summary || '') + (s.changed.length ? '\n' + tr('Changed:') + ' ' + s.changed.join(', ') : '');
    $('summary-text').style.whiteSpace = 'pre-wrap';
    $('undo-last').disabled = $('undo-all').disabled = !s.can_undo;
    showCheck(s);
    if (!$('url').value && s.preview) reloadFrame();
    $('set-trust').checked = d.settings.trusted.indexOf(s.project) >= 0;
  }

  function poll() {
    clearTimeout(state.timer);
    api('/api/coder?since=' + state.since + '&shot=' + state.shotAt).then(show).catch(function (e) { say(e.message); }).then(function () {
      var s = state.data && state.data.session, busy = s && (s.status === 'working' || s.status === 'waiting');
      var pulling = state.data && state.data.pull && state.data.pull.running;
      state.timer = setTimeout(poll, busy || pulling ? 800 : 4000);
    });
  }
  function act(body) {
    return api('/api/coder', body).then(function (d) { show(d); poll(); return d; }).catch(function (e) { say(e.message); if (e.data && e.data.projects) show(e.data); });
  }

  // ----- files -----
  function loadFiles() {
    api('/api/coder/files').then(function (d) {
      var ul = $('file-list'), changed = (state.data && state.data.session && state.data.session.changed) || [];
      ul.textContent = '';
      if (!d.files.length) { var li = document.createElement('li'); li.className = 'status'; li.textContent = tr('No files yet.'); ul.append(li); }
      d.files.forEach(function (f) {
        var li = document.createElement('li'), b = document.createElement('button'); b.type = 'button'; b.textContent = f.path;
        if (changed.indexOf(f.path) >= 0) { var m = document.createElement('span'); m.className = 'changed'; m.textContent = '●'; m.title = tr('changed by Jarvis'); b.append(m); }
        b.setAttribute('aria-current', String(f.path === state.file));
        b.addEventListener('click', function () { openFile(f.path); });
        li.append(b); ul.append(li);
      });
      if (state.file) openFile(state.file, true);
    }).catch(function () {});
  }
  function openFile(path, quiet) {
    state.file = path;
    document.querySelectorAll('#file-list button').forEach(function (b) { b.setAttribute('aria-current', String(b.firstChild && b.firstChild.textContent === path)); });
    api('/api/coder/file?path=' + encodeURIComponent(path)).then(function (d) {
      var pre = $('file-view'); pre.textContent = '';
      d.text.replace(/\n$/, '').split('\n').forEach(function (line, i) {
        var ln = document.createElement('span'); ln.className = 'ln'; ln.textContent = i + 1;
        pre.append(ln, document.createTextNode(line + '\n'));
      });
    }).catch(function (e) { if (!quiet) $('file-view').textContent = e.message; });
  }

  // ----- tabs -----
  ['browser', 'shot', 'files'].forEach(function (name) {
    $('tab-' + name).addEventListener('click', function () {
      ['browser', 'shot', 'files'].forEach(function (n) { $('tab-' + n).setAttribute('aria-selected', String(n === name)); $('pane-' + n).classList.toggle('hidden', n !== name); });
      if (name === 'files') loadFiles();
    });
  });

  // ----- buttons -----
  $('project').addEventListener('change', function () { if (this.value) { $('task').value = ''; act({ open: this.value }); } });
  $('new-project').addEventListener('click', function () {
    var name = window.prompt('Name of the new project (a folder in Jarvis\'s workspace):', '');
    if (name && name.trim()) { $('task').value = ''; act({ new: name.trim() }); }
  });
  $('start').addEventListener('click', function () {
    var t = $('task').value.trim();
    if (!t) { say(tr('Write first what Jarvis should do.')); $('task').focus(); return; }
    act({ start: t });
  });
  $('task').addEventListener('keydown', function (e) { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); $('start').click(); } });
  $('stop').addEventListener('click', function () { act({ stop: true }); });
  $('ask-yes').addEventListener('click', function () { act({ decide: 'yes' }); });
  $('ask-always').addEventListener('click', function () { act({ decide: 'always' }); });
  $('ask-no').addEventListener('click', function () { act({ decide: 'no' }); });
  $('undo-last').addEventListener('click', function () { act({ undo: 'last' }).then(function () { state.checkAt = 0; reloadFrame(); loadFiles(); }); });
  $('undo-all').addEventListener('click', function () { if (window.confirm('Undo every change Jarvis made to this project in this window?')) act({ undo: 'all' }).then(function () { reloadFrame(); loadFiles(); }); });
  $('check').addEventListener('click', function () { say(tr('Looking at the page…')); act({ check: true }); });
  $('reload').addEventListener('click', reloadFrame);
  $('external').addEventListener('click', function () { var s = state.data && state.data.session; if (s && s.preview) window.open(s.preview, '_blank'); });
  $('open-folder').addEventListener('click', function () { act({ open_folder: true }); });
  $('pull').addEventListener('click', function () { act({ pull: true }); });
  $('settings-open').addEventListener('click', function () { $('settings').showModal(); });
  $('set-cancel').addEventListener('click', function () { $('settings').close(); });
  $('set-save').addEventListener('click', function () {
    var s = state.data && state.data.session, body = { model: $('set-model').value, max_turns: Number($('set-steps').value) };
    var trusted = s && state.data.settings.trusted.indexOf(s.project) >= 0;
    if (s && $('set-trust').checked !== trusted) body[$('set-trust').checked ? 'trust' : 'untrust'] = s.project;
    $('settings').close();
    act({ settings: body });
  });

  window.JarvisCode = { state: state };
  poll();
})();

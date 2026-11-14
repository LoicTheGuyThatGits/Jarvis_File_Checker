/* Settings > Planner: to-do list, calendar and phone alerts. The planner itself lives in the Jarvis program. */
(function () {
  'use strict';
  function $(id) { return document.getElementById(id); }
  if (!$('plan-tasks')) return;
  function api(path, body) {
    var opts = body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined;
    return fetch(path, opts).then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || 'Request failed'); return d; }); });
  }
  function when(ts, hasTime) {
    var d = new Date(ts * 1000), now = new Date(), day = Math.round((new Date(d.getFullYear(), d.getMonth(), d.getDate()) - new Date(now.getFullYear(), now.getMonth(), now.getDate())) / 86400000);
    var name = day === 0 ? 'today' : day === 1 ? 'tomorrow' : d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
    return hasTime ? name + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : name;
  }
  function row(list, text, extra, onDelete, onToggle, done) {
    var li = document.createElement('li'); li.className = 'tool-item';
    if (onToggle) { var box = document.createElement('input'); box.type = 'checkbox'; box.checked = !!done; box.setAttribute('aria-label', 'Done'); box.addEventListener('change', onToggle); li.appendChild(box); }
    var t = document.createElement('span'); t.className = 'tool-text'; t.textContent = ' ' + text + (extra ? '  (' + extra + ')' : ''); if (done) t.style.textDecoration = 'line-through';
    li.appendChild(t);
    var x = document.createElement('button'); x.type = 'button'; x.className = 'plan-del'; x.textContent = '✕'; x.setAttribute('aria-label', 'Delete'); x.addEventListener('click', onDelete); li.appendChild(x);
    list.appendChild(li);
  }
  function show(d) {
    var tasks = $('plan-tasks'), events = $('plan-events'); tasks.textContent = ''; events.textContent = '';
    d.tasks.forEach(function (t) {
      row(tasks, t.text, t.due ? 'due ' + when(t.due, t.has_time) : '', function () { send('/api/planner/delete', { kind: 'task', id: t.id }); }, function () { send('/api/planner/toggle', { id: t.id }); }, t.done);
    });
    if (!d.tasks.length) { var li = document.createElement('li'); li.className = 'tool-item'; li.textContent = 'No tasks.'; tasks.appendChild(li); }
    d.events.forEach(function (e) { row(events, e.title, when(e.start, true), function () { send('/api/planner/delete', { kind: 'event', id: e.id }); }); });
    if (!d.events.length) { var l2 = document.createElement('li'); l2.className = 'tool-item'; l2.textContent = 'No upcoming events.'; events.appendChild(l2); }
  }
  function send(path, body) { return api(path, body).then(function (d) { $('plan-status').textContent = ''; show(d); }).catch(function (e) { $('plan-status').textContent = e.message; }); }
  function load() { loadCal(); api('/api/planner').then(show).catch(function () {}); api('/api/proactive').then(showPro).catch(function () {}); }
  $('plan-task-add').addEventListener('click', function () {
    if (!$('plan-task-text').value.trim()) return;
    send('/api/planner/task', { text: $('plan-task-text').value, due: $('plan-task-due').value }).then(function () { $('plan-task-text').value = ''; $('plan-task-due').value = ''; });
  });
  $('plan-task-text').addEventListener('keydown', function (e) { if (e.key === 'Enter') $('plan-task-add').click(); });
  $('plan-event-add').addEventListener('click', function () {
    send('/api/planner/event', { title: $('plan-event-title').value, start: $('plan-event-start').value }).then(function () { if (!$('plan-status').textContent) { $('plan-event-title').value = ''; $('plan-event-start').value = ''; } });
  });
  // ---- proactive Jarvis ----
  var WATCH = ['events', 'tasks', 'mail', 'health', 'finished'], DELIVER = ['chat', 'speak', 'toast', 'telegram'];
  var NUMBERS = { 'pro-idle': 'idle_minutes', 'pro-cap': 'per_hour' }, TIMES = { 'pro-quiet-from': 'quiet_from', 'pro-quiet-to': 'quiet_to' };
  var proNote = '';
  function clock(ts) { return new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); }
  function showPro(p) {
    $('pro-on').checked = p.enabled;
    WATCH.forEach(function (k) { $('pro-w-' + k).checked = p.watch[k]; $('pro-w-' + k).disabled = !p.enabled; });
    DELIVER.forEach(function (k) { $('pro-d-' + k).checked = p.deliver[k]; $('pro-d-' + k).disabled = !p.enabled; });
    Object.keys(NUMBERS).concat(Object.keys(TIMES)).forEach(function (id) { if (document.activeElement !== $(id)) $(id).value = p[NUMBERS[id] || TIMES[id]]; });
    if (document.activeElement !== $('al-lead')) $('al-lead').value = p.lead_minutes;
    $('pro-mute').textContent = p.muted_until ? 'Speak again (quiet until ' + clock(p.muted_until) + ')' : 'Not now'; $('pro-mute').dataset.muted = p.muted_until ? '1' : '';
    var notes = [];
    if (p.enabled && p.quiet_now) notes.push('Quiet hours are in effect now.');
    if (p.held) notes.push(p.held + ' thing' + (p.held === 1 ? ' is' : 's are') + ' being held for later.');
    if (p.enabled && p.deliver.telegram && !p.telegram_paired) notes.push('Telegram is not paired yet, so nothing is sent there (Settings > Telegram).');
    if (p.enabled && p.watch.mail && !p.mail_connected) notes.push('Email is not connected yet (Settings > Mail).');
    $('pro-status').textContent = (proNote ? proNote + ' ' : '') + notes.join(' ');
  }
  function savePro() {
    var body = { enabled: $('pro-on').checked, watch: {}, deliver: {} };
    WATCH.forEach(function (k) { body.watch[k] = $('pro-w-' + k).checked; });
    DELIVER.forEach(function (k) { body.deliver[k] = $('pro-d-' + k).checked; });
    Object.keys(NUMBERS).forEach(function (id) { body[NUMBERS[id]] = parseInt($(id).value, 10); });
    Object.keys(TIMES).forEach(function (id) { if ($(id).value) body[TIMES[id]] = $(id).value; });
    api('/api/proactive', body).then(function (p) { proNote = 'Saved.'; showPro(p); }).catch(function (e) { proNote = ''; $('pro-status').textContent = e.message; });
  }
  ['pro-on', 'pro-idle', 'pro-cap', 'pro-quiet-from', 'pro-quiet-to'].concat(WATCH.map(function (k) { return 'pro-w-' + k; }), DELIVER.map(function (k) { return 'pro-d-' + k; }))
    .forEach(function (id) { $(id).addEventListener('change', savePro); });
  $('al-lead').addEventListener('change', function () {
    api('/api/alerts', { lead_minutes: parseInt($('al-lead').value, 10) }).then(function () { proNote = 'Saved.'; load(); }).catch(function (e) { $('pro-status').textContent = e.message; });
  });
  $('pro-test').addEventListener('click', function () {
    $('pro-status').textContent = 'Sending…';
    api('/api/proactive/test', {}).then(function (p) {
      var idle = p.idle_seconds == null ? '' : ' The keyboard or mouse was last touched ' + p.idle_seconds + ' seconds ago' + (p.used.indexOf('telegram') < 0 && p.deliver.telegram ? ', so Telegram was skipped.' : '.');
      proNote = 'Sent to: ' + (p.used.length ? p.used.join(', ') : 'nowhere') + '.' + idle; showPro(p);
    }).catch(function (e) { $('pro-status').textContent = e.message; });
  });
  $('pro-mute').addEventListener('click', function () {
    api('/api/proactive/mute', $('pro-mute').dataset.muted ? { off: true } : {}).then(function (p) { proNote = ''; showPro(p); }).catch(function (e) { $('pro-status').textContent = e.message; });
  });
  // ---- calendar import ----
  function showCal(d) {
    var list = $('cal-sources'); list.textContent = '';
    d.sources.forEach(function (c) {
      var li = document.createElement('li'); li.className = 'tool-item';
      var t = document.createElement('span'); t.className = 'tool-text';
      t.textContent = c.name + ' (' + (c.kind === 'link' ? 'link' : 'file') + ') – ' + (c.error ? 'problem: ' + c.error : c.count + ' events in the next weeks'); li.appendChild(t);
      var x = document.createElement('button'); x.type = 'button'; x.className = 'plan-del'; x.textContent = '✕'; x.setAttribute('aria-label', 'Remove calendar');
      x.addEventListener('click', function () { calSend('/api/calendar/remove', { id: c.id }); }); li.appendChild(x); list.appendChild(li);
    });
    if (!d.sources.length) { var e = document.createElement('li'); e.className = 'tool-item'; e.textContent = 'No calendar imported.'; list.appendChild(e); }
    $('cal-alerts').checked = !!d.alerts;
  }
  function calSend(path, body) { $('cal-status').textContent = 'Working…'; return api(path, body).then(function (d) { $('cal-status').textContent = ''; showCal(d); load(); return true; }).catch(function (e) { $('cal-status').textContent = e.message; return false; }); }
  $('cal-add').addEventListener('click', function () {
    var url = $('cal-url').value.trim(), file = $('cal-file').files[0];
    if (!url && !file) { $('cal-status').textContent = 'Paste a calendar link or choose an .ics file.'; return; }
    function done(ok) { if (ok) { $('cal-url').value = ''; $('cal-name').value = ''; $('cal-file').value = ''; } }
    if (url) { calSend('/api/calendar/add', { url: url, name: $('cal-name').value }).then(done); return; }
    var r = new FileReader(); r.onload = function () { calSend('/api/calendar/add', { ics: String(r.result), name: $('cal-name').value || file.name.replace(/\.ics$/i, '') }).then(done); };
    r.onerror = function () { $('cal-status').textContent = 'I could not read that file.'; }; r.readAsText(file);
  });
  $('cal-sync').addEventListener('click', function () { calSend('/api/calendar/sync', {}); });
  $('cal-alerts').addEventListener('change', function () { calSend('/api/calendar/alerts', { on: $('cal-alerts').checked }); });
  function loadCal() { api('/api/calendar').then(showCal).catch(function () {}); }
  $('tab-plan').addEventListener('click', load);
  window.addEventListener('jarvis:pane', function (e) { if (e.detail.pane === 'plan') load(); });
  setInterval(function () { if (!$('pane-plan').classList.contains('hidden') && document.activeElement.tagName !== 'INPUT') load(); }, 5000);
})();

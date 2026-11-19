// Debug mode: shows what Jarvis did for a reply (the trace the server sends back when debug mode is on).
(function () {
  'use strict';
  var KINDS = {
    message: 'Message', french: 'French', command: 'Command', router: 'Smart cmds', tool: 'Tool', mcp: 'MCP', web: 'Web',
    documents: 'Docs', memory: 'Memory', model: 'Model', thinking: 'Thinking', action: 'Action', autopilot: 'Autopilot', error: 'Error'
  };
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function ms(n) { n = Number(n) || 0; return n >= 10000 ? (n / 1000).toFixed(1) + ' s' : n >= 1000 ? (n / 1000).toFixed(2) + ' s' : n + ' ms'; }
  function copy(text, button, label) {
    var done = function () { button.textContent = 'Copied'; setTimeout(function () { button.textContent = label; }, 1800); };
    if (navigator.clipboard) navigator.clipboard.writeText(text).then(done, function () { window.prompt('Copy the trace:', text); });
    else window.prompt('Copy the trace:', text);
  }
  function steps(trace) {
    var list = el('ol', 'debug-steps');
    (trace.steps || []).forEach(function (s) {
      var li = el('li', 'debug-step debug-' + (KINDS[s.kind] ? s.kind : 'other'));
      var head = el('div', 'debug-line');
      head.append(el('span', 'debug-time', '+' + ms(s.ms)), el('span', 'debug-kind', KINDS[s.kind] || s.kind), el('span', 'debug-text', s.text));
      li.append(head);
      if (s.detail) {
        var d = el('details', 'debug-detail'), sum = el('summary', null, s.kind === 'thinking' ? 'Show the thinking' : s.kind === 'model' && /^Asking/.test(s.text) ? 'Show the instructions and messages sent' : 'Show details');
        var pre = el('pre', null, s.detail);
        if (s.kind === 'thinking') d.open = true;
        d.append(sum, pre); li.append(d);
      }
      list.append(li);
    });
    return list;
  }
  function summaryText(trace) {
    var n = (trace.steps || []).length;
    return 'Debug · ' + ms(trace.total_ms) + ' · answered by ' + (trace.answered_by || 'Jarvis') + ' · ' + n + ' step' + (n === 1 ? '' : 's');
  }
  function panel(trace) {
    var box = el('details', 'debug-trace');
    box.append(el('summary', null, summaryText(trace)), steps(trace));
    var tools = el('div', 'debug-tools'), b = el('button', null, 'Copy trace');
    b.type = 'button'; b.addEventListener('click', function () { copy(JSON.stringify(trace, null, 1), b, 'Copy trace'); });
    tools.append(b); box.append(tools);
    return box;
  }
  window.JarvisDebug = {
    panel: panel, steps: steps,
    // put the trace under a reply in the chat
    attach: function (trace, row) {
      if (!trace || !trace.steps) return null;
      var p = panel(trace);
      if (row && row.parentNode) row.after(p); else { var c = document.querySelector('#conversation'); if (c) c.append(p); }
      return p;
    }
  };

  // ---------- Settings → Jarvis & updates → Debug mode ----------
  var $ = function (id) { return document.getElementById(id); };
  if (!$('debug-on')) return;
  var last = [];
  function call(body) {
    return fetch('/api/debug', body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {})
      .then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || 'Something went wrong.'); return d; }); });
  }
  function show(d) {
    $('debug-on').checked = !!d.enabled; last = d.traces || [];
    var list = $('debug-list'); list.textContent = '';
    $('debug-copy').disabled = $('debug-clear').disabled = !last.length;
    $('debug-status').textContent = !d.enabled && !last.length ? 'Debug mode is off.' : last.length ? last.length + ' recent trace' + (last.length === 1 ? '' : 's') + ' (newest first).' : 'Debug mode is on. Send Jarvis a message and its trace appears here and under the reply.';
    last.forEach(function (t) {
      var li = el('li', 'debug-item'), d2 = el('details');
      var msg = (t.message || '').replace(/\s+/g, ' '); if (msg.length > 70) msg = msg.slice(0, 69) + '…';
      d2.append(el('summary', null, t.at + ' · “' + msg + '” · ' + ms(t.total_ms) + ' · ' + (t.answered_by || 'Jarvis') + (t.source && t.source !== 'page' ? ' · from ' + t.source : '')));
      d2.addEventListener('toggle', function () { if (d2.open && !d2.querySelector('ol')) { d2.append(steps(t)); if (t.reply) { var r = el('p', 'settings-note debug-reply'); r.append(el('strong', null, 'Reply: '), document.createTextNode(t.reply)); d2.append(r); } } });
      li.append(d2); list.append(li);
    });
  }
  function load() { call().then(show).catch(function (e) { $('debug-status').textContent = e.message; }); }
  $('debug-on').addEventListener('change', function () {
    var on = $('debug-on').checked;
    call({ on: on }).then(function (d) { show(d); $('debug-status').textContent = on ? 'Debug mode is on. Each reply now has a folded “Debug” line under it.' : 'Debug mode is off. The recorded traces were cleared.'; })
      .catch(function (e) { $('debug-on').checked = !on; $('debug-status').textContent = e.message; });
  });
  $('debug-refresh').addEventListener('click', load);
  $('debug-clear').addEventListener('click', function () { call({ clear: true }).then(show).catch(function (e) { $('debug-status').textContent = e.message; }); });
  $('debug-copy').addEventListener('click', function () { copy(JSON.stringify(last, null, 1), $('debug-copy'), 'Copy all (JSON)'); });
  window.addEventListener('jarvis:pane', function (e) { if (e.detail && window.paneHas(e.detail.pane, 'debug-on')) load(); });
})();

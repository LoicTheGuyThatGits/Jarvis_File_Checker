/* The quick-ask window: a small Jarvis box that opens over any app with a shortcut (Settings > Shortcuts > Quick ask).
   Ask, get the answer right there, Esc to put it away. It remembers the conversation while it is put away (for follow-ups),
   starts over after 15 quiet minutes, and "Open in Jarvis" carries the conversation on in the big window. */
(function () {
  'use strict';
  function $(id) { return document.getElementById(id); }
  function tr(s) { return window.JarvisI18n ? window.JarvisI18n.t(s) : s; }
  var input = $('ask-input'), out = $('ask-out'), form = $('ask-form'), send = $('ask-send');
  var KEY = 'jarvis-ask-v1', IDLE = 15 * 60 * 1000;
  var msgs = [], last = Date.now(), controller = null, requestId = null;
  try { var saved = JSON.parse(sessionStorage.getItem(KEY) || 'null'); if (saved && Array.isArray(saved.msgs) && Date.now() - saved.at < IDLE) { msgs = saved.msgs; last = saved.at; } } catch (e) {}
  function keep() { last = Date.now(); try { sessionStorage.setItem(KEY, JSON.stringify({ msgs: msgs.slice(-20), at: last })); } catch (e) {} }
  function post(path, body) { return fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) }); }

  function fill(el, text) {
    el.textContent = '';
    var parts = String(text).split(/```[^\n`]*\n?/);
    parts.forEach(function (p, i) {
      if (!p) return;
      if (i % 2) { var pre = document.createElement('pre'); pre.textContent = p.replace(/\n$/, ''); el.append(pre); }
      else el.append(document.createTextNode(p.replace(/^\n+|\n+$/g, '')));
    });
  }
  function add(cls, text) { var el = document.createElement('div'); el.className = cls; if (cls === 'ask-q') el.textContent = text; else fill(el, text); out.append(el); out.scrollTop = out.scrollHeight; return el; }
  function tools(answerEl, text) {
    var bar = document.createElement('div'); bar.className = 'ask-tools';
    var copy = document.createElement('button'); copy.type = 'button'; copy.textContent = tr('Copy');
    copy.addEventListener('click', function () {
      navigator.clipboard.writeText(text).then(function () { copy.textContent = tr('Copied'); }, function () { copy.textContent = tr('Press Ctrl+C'); });
      setTimeout(function () { copy.textContent = tr('Copy'); }, 1500);
      input.focus();
    });
    bar.append(copy); answerEl.after(bar);
  }
  function clipList(after, items) {
    var list = document.createElement('ol'); list.className = 'ask-clips';
    items.forEach(function (item) {
      var li = document.createElement('li'), span = document.createElement('span'), b = document.createElement('button');
      span.textContent = item.text.replace(/\s+/g, ' ').trim(); span.title = item.text.slice(0, 600);
      b.type = 'button'; b.textContent = tr('Copy');
      b.addEventListener('click', function () {
        post('/api/clipboard', { copy: item.id }).then(function (r) { b.textContent = r.ok ? tr('Copied') : tr('Could not copy'); }, function () { b.textContent = tr('Could not copy'); });
        setTimeout(function () { b.textContent = tr('Copy'); }, 1800); input.focus();
      });
      li.append(span, b); list.append(li);
    });
    after.append(list);
  }
  function render() {
    out.textContent = '';
    if (!msgs.length) { var p = document.createElement('p'); p.className = 'ask-empty'; p.id = 'ask-empty'; p.innerHTML = tr('Ask anything, or give a command (“set a timer for 10 minutes”). The answer stays here; <strong>Copy</strong> puts it on the clipboard for the app you were in.'); out.append(p); return; }
    msgs.forEach(function (m) { var el = add(m.role === 'user' ? 'ask-q' : 'ask-a', m.content); if (m.role === 'assistant') tools(el, m.content); });
  }
  function busy(on) {
    send.textContent = on ? tr('Stop') : '↑'; send.classList.toggle('stop', on); send.setAttribute('aria-label', on ? tr('Stop') : tr('Ask'));
  }
  function readStream(response, onDelta) {
    var reader = response.body.getReader(), decoder = new TextDecoder(), buffer = '', final = null;
    function handle(line) {
      if (!line.trim()) return; var ev; try { ev = JSON.parse(line); } catch (e) { return; }
      if (ev.type === 'delta' && typeof ev.text === 'string') onDelta(ev.text);
      else if (ev.type === 'final') final = ev;
      else if (ev.type === 'error') throw new Error(ev.error || 'Something went wrong.');
    }
    function pump() {
      return reader.read().then(function (r) {
        if (r.done) { buffer += decoder.decode(); handle(buffer); if (!final) throw new Error('The reply was cut off before it finished.'); return final; }
        buffer += decoder.decode(r.value, { stream: true }); var nl;
        while ((nl = buffer.indexOf('\n')) >= 0) { var line = buffer.slice(0, nl); buffer = buffer.slice(nl + 1); handle(line); }
        return pump();
      });
    }
    return pump();
  }
  function ask(text) {
    text = text.trim(); if (!text || controller) return;
    if (Date.now() - last > IDLE) { msgs = []; render(); }
    if (!msgs.length) out.textContent = '';
    msgs.push({ role: 'user', content: text }); keep(); add('ask-q', text);
    input.value = ''; size();
    var thinking = add('ask-thinking', tr('Jarvis is thinking…')), answer = null, streamed = '';
    controller = new AbortController(); requestId = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now())); busy(true);
    post('/api/chat', { messages: msgs.slice(-20), request_id: requestId, stream: true, source: 'ask' }).then(function (r) {
      if ((r.headers.get('Content-Type') || '').indexOf('application/x-ndjson') >= 0)
        return readStream(r, function (piece) { if (!answer) { thinking.remove(); answer = add('ask-a', ''); } streamed += piece; fill(answer, streamed); out.scrollTop = out.scrollHeight; });
      return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || 'Something went wrong.'); return d; });
    }).then(function (d) {
      var reply = d.reply || (d.cancelled ? streamed : '') || tr('I do not have a response for that yet.');
      thinking.remove(); if (!answer) answer = add('ask-a', reply); else fill(answer, reply);
      msgs.push({ role: 'assistant', content: reply }); keep(); tools(answer, reply);
      if (Array.isArray(d.clipboard)) clipList(answer, d.clipboard);
      if (d.action) { var note = document.createElement('div'); note.className = 'ask-note'; note.textContent = tr('This needs your approval, which only the big Jarvis window can give. Ask it there.'); answer.append(note); }
      if (d.ui_language && window.JarvisI18n && d.ui_language !== window.JarvisI18n.code()) window.JarvisI18n.set(d.ui_language);
    }).catch(function (e) {
      thinking.remove(); var el = add('ask-a error', tr("I couldn't complete that:") + ' ' + (e.name === 'AbortError' ? tr('Stopped.') : e.message));
      msgs.pop(); keep(); input.value = text; size();
    }).then(function () { controller = null; requestId = null; busy(false); input.focus(); });
  }
  function stop() {
    if (!controller) return;
    var id = requestId;
    post('/api/chat/cancel', { request_id: id }).then(function (r) { if (!r.ok) throw 0; }).catch(function () { if (controller) controller.abort(); });
  }
  function size() { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 120) + 'px'; }
  function hide() {
    post('/api/ask/hide').then(function (r) { if (!r.ok) throw 0; }).catch(function () { try { window.close(); } catch (e) {} });
  }
  function fresh() { if (controller) return; msgs = []; keep(); render(); input.value = ''; size(); input.focus(); }
  function toMain() {
    if (!msgs.length) { post('/api/ask/main'); return; }
    try {
      var chats = JSON.parse(localStorage.getItem('jarvis-chats-v1') || '[]'); if (!Array.isArray(chats)) chats = [];
      var first = msgs[0].content.replace(/\s+/g, ' ');
      var chat = { id: crypto.randomUUID ? crypto.randomUUID() : 'ask-' + Date.now(), title: first.slice(0, 36) + (first.length > 36 ? '…' : ''), messages: msgs.slice(-100) };
      chats.push(chat); localStorage.setItem('jarvis-chats-v1', JSON.stringify(chats)); localStorage.setItem('jarvis-current-chat-v1', chat.id);
    } catch (e) {}
    msgs = []; keep(); render(); post('/api/ask/main');
  }
  form.addEventListener('submit', function (e) { e.preventDefault(); if (controller) stop(); else ask(input.value); });
  input.addEventListener('input', size);
  input.addEventListener('keydown', function (e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); if (!controller) ask(input.value); } });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { e.preventDefault(); if (controller) stop(); else hide(); }
    else if ((e.ctrlKey || e.metaKey) && (e.key === 'n' || e.key === 'N')) { e.preventDefault(); fresh(); }
  });
  $('ask-close').addEventListener('click', hide);
  $('ask-new').addEventListener('click', fresh);
  $('ask-main').addEventListener('click', toMain);
  /* each time it comes back: the box ready to type in, and a fresh start after a long pause */
  function back() { if (Date.now() - last > IDLE && msgs.length && !controller) { msgs = []; keep(); render(); } input.focus(); input.select(); }
  window.addEventListener('focus', back);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) back(); });
  render(); input.focus();
  window.JarvisAsk = { ask: ask, msgs: function () { return msgs; } };
})();

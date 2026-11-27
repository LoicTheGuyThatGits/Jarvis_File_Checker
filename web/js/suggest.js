/* Command suggestions in the message box, and the keyboard shortcut list.
   Type "/" to see what Jarvis can do (keep typing to narrow it down), or start typing a command ("set a ti…") and the
   matching commands show up. ↑ ↓ choose, Tab or Enter takes one, Esc closes. Ctrl+/ shows every keyboard shortcut.
   The commands stay in English: they are what Jarvis understands best (many also work in French). */
(function () {
  'use strict';
  var input = document.getElementById('message'), form = document.getElementById('composer');
  if (!input || !form) return;
  function tr(s) { return window.JarvisI18n ? window.JarvisI18n.t(s) : s; }
  var C = [
    ['Timers and reminders', ['set a timer for 10 minutes', 'set a 25 minute timer called pomodoro', 'remind me in 20 minutes to check the oven', 'remind me tomorrow at 9am to send the report', 'set an alarm for 7am', 'what timers do I have?', 'cancel my timer', 'call me at 6:45 to wake me up']],
    ['Planner', ["what's on my calendar tomorrow", 'add buy milk to my to-do list', "what's on my to-do list", 'clear completed tasks', 'add a countdown for my birthday on 3 March', 'start a 25 minute focus', 'recap my day', 'brief me']],
    ['School', ["what's my next class?", 'what classes do I have tomorrow?', 'what homework do I have?', 'maths homework: exercises 4 to 7', 'what do I need to bring tomorrow?', "what's my average in maths?", 'my grades', 'show my revision plan', 'start revision', 'review my cards', 'make flashcards from my notes on photosynthesis']],
    ['Notes and memory', ['take a note: buy a USB cable', 'show my notes', 'what did I note about the exam?', 'remember that my printer is the HP in the office', 'what do you remember?', 'forget the printer']],
    ['Web and files', ['search the internet for the best budget laptops', 'search youtube for lofi music', 'go to the BBC website', 'find files named report', 'search my files for budget.xlsx', 'translate report.docx into French']],
    ['Music', ['play my study playlist', 'queue Yellow by Coldplay', "what's in my queue", 'what song is next']],
    ['Clipboard', ['what did I copy?', 'put back what I copied before', 'put back number 3', 'clear my clipboard history']],
    ['PC', ['show the desktop', 'minimize all windows', 'turn the volume up', 'volume down by 20', 'mute', 'lock the computer', 'take a screenshot', "what's on my screen?", 'what models can my PC run?', 'clean up my temp files', 'when was my last backup?']],
    ['Routines', ['my routines', 'run good night', 'run good night every day at 22:30', 'create a routine called study mode: open OneNote, start a 25 minute focus, then play my study playlist']],
    ['Travel', ['next departures', 'next bus to Zürich HB', 'how do I get to Lausanne by 5pm?', 'is my bus late?', "what's the weather"]],
    ['Email', ['any new emails?', 'check my email']],
    ['Jarvis', ['check for updates', 'check my files', 'switch to French', 'set my town to Lyon', 'open Jarvis Code', 'debug mode on', 'what time is it?']]
  ];
  var ALL = [];
  C.forEach(function (g) { g[1].forEach(function (cmd) { ALL.push({ cmd: cmd, group: g[0], low: cmd.toLowerCase() }); }); });

  var box = document.createElement('div'); box.id = 'cmd-suggest'; box.className = 'cmd-suggest hidden'; box.setAttribute('role', 'listbox');
  box.setAttribute('aria-label', 'Commands'); box.setAttribute('data-no-i18n', '');
  form.insertBefore(box, input);
  input.setAttribute('aria-autocomplete', 'list'); input.setAttribute('aria-controls', 'cmd-suggest');
  var shown = [], pick = -1, slash = false, closedFor = null;

  function matches(text) {
    if (text.charAt(0) === '/') {
      var q = text.slice(1).trim().toLowerCase(); slash = true;
      if (!q) return ALL.slice();
      var words = q.split(/\s+/);
      return ALL.filter(function (c) { var hay = c.low + ' ' + tr(c.group).toLowerCase() + ' ' + c.group.toLowerCase(); return words.every(function (w) { return hay.indexOf(w) >= 0; }); });
    }
    slash = false;
    var t = text.toLowerCase().replace(/\s+/g, ' ');
    if (t.trim().length < 3 || t.length > 40) return [];
    return ALL.filter(function (c) { return c.low.indexOf(t) === 0 && c.low !== t; }).slice(0, 5);
  }
  function render() {
    box.textContent = '';
    if (!shown.length) {
      if (slash) { var none = document.createElement('div'); none.className = 'cmd-none'; none.textContent = tr('No command matches. Press Enter to send it to Jarvis as it is.'); box.append(none); }
      else { hide(); return; }
    }
    var last = null;
    shown.forEach(function (c, i) {
      if (slash && c.group !== last) { var h = document.createElement('div'); h.className = 'cmd-group'; h.textContent = tr(c.group); box.append(h); last = c.group; }
      var item = document.createElement('div'); item.className = 'cmd-item' + (i === pick ? ' picked' : ''); item.setAttribute('role', 'option'); item.id = 'cmd-' + i;
      item.setAttribute('aria-selected', String(i === pick)); item.textContent = c.cmd; item.title = tr(c.group);
      item.addEventListener('mousedown', function (e) { e.preventDefault(); take(i); });
      box.append(item);
    });
    var hint = document.createElement('div'); hint.className = 'cmd-hint'; hint.textContent = tr('↑ ↓ to choose · Tab or Enter to take it · Esc to close'); box.append(hint);
    box.classList.remove('hidden'); input.setAttribute('aria-expanded', 'true');
    if (pick >= 0) { input.setAttribute('aria-activedescendant', 'cmd-' + pick); var el = document.getElementById('cmd-' + pick); if (el && el.scrollIntoView) el.scrollIntoView({ block: 'nearest' }); }
    else input.removeAttribute('aria-activedescendant');
  }
  function hide() { box.classList.add('hidden'); shown = []; pick = -1; input.setAttribute('aria-expanded', 'false'); input.removeAttribute('aria-activedescendant'); }
  function update() {
    var text = input.value;
    if (closedFor !== null && text === closedFor) return;
    closedFor = null;
    if (/\n/.test(text)) { hide(); return; }
    shown = matches(text); pick = slash && shown.length ? 0 : -1;
    if (!shown.length && !slash) { hide(); return; }
    render();
  }
  function take(i) {
    var c = shown[i]; if (!c) return;
    input.value = c.cmd; hide(); closedFor = c.cmd;
    input.dispatchEvent(new Event('input')); input.focus();
    input.setSelectionRange(c.cmd.length, c.cmd.length);   // the cursor at the end, ready to change the details
  }
  input.addEventListener('input', update);
  input.addEventListener('blur', function () { setTimeout(hide, 120); });
  form.addEventListener('keydown', function (e) {
    if (e.target !== input || box.classList.contains('hidden')) return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      if (!shown.length) return;
      e.preventDefault(); e.stopPropagation();
      pick = e.key === 'ArrowDown' ? (pick + 1) % shown.length : (pick <= 0 ? shown.length - 1 : pick - 1); render();
    } else if ((e.key === 'Tab' && !e.shiftKey) || (e.key === 'Enter' && !e.shiftKey && pick >= 0)) {
      if (pick < 0 && e.key === 'Tab') pick = 0;
      e.preventDefault(); e.stopPropagation(); take(pick);
    } else if (e.key === 'Escape') {
      e.preventDefault(); e.stopPropagation(); closedFor = input.value; hide();
    }
  }, true);
  form.addEventListener('submit', hide, true);

  /* ---- the keyboard shortcut list (Ctrl+/) ---- */
  var keysBox = null;
  function row(keys, what) { return '<tr><td>' + keys.split(' + ').map(function (k) { return '<kbd>' + k + '</kbd>'; }).join(' + ') + '</td><td>' + what + '</td></tr>'; }
  function openKeys() {
    if (!keysBox) {
      keysBox = document.createElement('div'); keysBox.id = 'keys-help'; keysBox.className = 'keys-help hidden'; keysBox.setAttribute('role', 'dialog'); keysBox.setAttribute('aria-modal', 'true'); keysBox.setAttribute('aria-labelledby', 'keys-help-title');
      keysBox.innerHTML = '<div class="keys-help-card"><div class="keys-help-head"><h2 id="keys-help-title">Keyboard shortcuts</h2><button type="button" class="keys-help-close" aria-label="Close">×</button></div>' +
        '<h3>In this window</h3><table>' + row('Enter', 'Send the message') + row('Shift + Enter', 'New line in the message') + row('/', 'Show what Jarvis can do') +
        row('↑', 'Edit your last message (in an empty box)') + row('Esc', 'Stop editing, or close a list') + row('Ctrl + K', 'Search the settings') + row('Ctrl + /', 'This list') + '</table>' +
        '<h3>Anywhere on the PC</h3><table id="keys-global"></table><p class="keys-help-note">Shortcuts that are off can be turned on in Settings > Shortcuts &amp; apps.</p></div>';
      document.body.append(keysBox);
      keysBox.addEventListener('click', function (e) { if (e.target === keysBox || e.target.closest('.keys-help-close')) closeKeys(); });
    }
    var g = keysBox.querySelector('#keys-global');
    var fill = function (d) {
      var on = function (part) { return part && part.enabled ? '' : ' <span class="keys-off">(' + tr('off') + ')</span>'; };
      var label = function (map, key, fallback) { return (map && map[key]) || fallback; };
      g.innerHTML = row('Ctrl + Alt + J', 'Bring back the Jarvis window') +
        (d ? row(label(d.ask_keys, d.ask && d.ask.key, 'Ctrl+Alt+Space').replace(/\+/g, ' + '), 'Ask Jarvis from any app' + on(d.ask)) +
             row(label(d.dictation_keys, d.dictation.key, 'Ctrl+Alt+D').replace(/\+/g, ' + '), 'Hold to dictate into any app' + on(d.dictation)) +
             row(label(d.quick_keys, d.quick.key, 'Ctrl+Alt+Q').replace(/\+/g, ' + '), 'Quick actions on the selected text' + on(d.quick)) : '') +
        row('Ctrl + Shift + F10', 'Stop Autopilot');
    };
    fill(null);
    fetch('/api/shortcuts').then(function (r) { return r.ok ? r.json() : null; }).then(function (d) { if (d && d.dictation) fill(d); }).catch(function () {});
    keysBox.classList.remove('hidden'); keysBox.querySelector('.keys-help-close').focus();
  }
  function closeKeys() { if (keysBox) keysBox.classList.add('hidden'); input.focus(); }
  document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && (e.key === '/' || e.code === 'Slash')) { e.preventDefault(); if (keysBox && !keysBox.classList.contains('hidden')) closeKeys(); else openKeys(); }
    else if (e.key === 'Escape' && keysBox && !keysBox.classList.contains('hidden')) { e.preventDefault(); e.stopPropagation(); closeKeys(); }
  }, true);
  window.JarvisSuggest = { commands: ALL, openKeys: openKeys };
})();

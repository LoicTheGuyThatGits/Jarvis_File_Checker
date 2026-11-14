/* Interface styles + cosmetic startup sequence. Independent of app.js; everything is saved in localStorage. */
(function () {
  'use strict';
  var root = document.documentElement;
  var THEMES = [
    { id: 'arc', name: 'Arc Reactor', desc: 'Classic cyan HUD', colors: ['#02070d', '#0b4a5f', '#5ee7ff', '#ff9a2e'] },
    { id: 'stark', name: 'Mark III', desc: 'Red and gold armor', colors: ['#0c0603', '#5b1b0f', '#f5bd50', '#ff6a2b'] },
    { id: 'crimson', name: 'Crimson', desc: 'Red alert', colors: ['#0d0502', '#5d0d11', '#ff5a5f', '#ffa53a'] },
    { id: 'amber', name: 'Amber CRT', desc: 'Retro terminal gold', colors: ['#0d0d02', '#5f440b', '#ffbc5e', '#ff5a1f'] },
    { id: 'toxic', name: 'Toxic', desc: 'Acid lime', colors: ['#050d02', '#3c5d0d', '#c6ff3d', '#ffd426'] },
    { id: 'emerald', name: 'Emerald', desc: 'Green terminal glow', colors: ['#030c0b', '#0f5b3b', '#66f7ac', '#38e8e0'] },
    { id: 'midnight', name: 'Midnight', desc: 'Deep royal blue', colors: ['#03030f', '#12256e', '#6f9dff', '#9a86ff'] },
    { id: 'nebula', name: 'Nebula', desc: 'Deep violet', colors: ['#09030c', '#361159', '#b07cff', '#ff5fd2'] },
    { id: 'sakura', name: 'Sakura', desc: 'Neon pink', colors: ['#0c0304', '#5b0f31', '#ff7ac8', '#b58cff'] },
    { id: 'stealth', name: 'Stealth', desc: 'Quiet monochrome', colors: ['#070708', '#313639', '#dfe8ec', '#5aa9ff'] }
  ];
  var K = { theme: 'jarvis-theme-v1', mode: 'jarvis-boot-mode', seen: 'jarvis-boot-seen', id: 'jarvis-boot-id' };
  function get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  function $(id) { return document.getElementById(id); }

  /* ---------- themes ---------- */
  function currentTheme() { var t = root.getAttribute('data-theme'); return THEMES.some(function (x) { return x.id === t; }) ? t : 'arc'; }
  function applyTheme(id) {
    if (id === 'arc') root.removeAttribute('data-theme'); else root.setAttribute('data-theme', id);
    set(K.theme, id);
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', getComputedStyle(root).getPropertyValue('--bg').trim() || '#02070d');
    markSelected();
  }
  function buildThemeGrid() {
    var grid = $('theme-grid'); grid.textContent = '';
    THEMES.forEach(function (t) {
      var b = document.createElement('button');
      b.type = 'button'; b.className = 'theme-option'; b.setAttribute('role', 'radio'); b.dataset.theme = t.id;
      var sw = document.createElement('span'); sw.className = 'theme-swatch';
      sw.style.background = 'linear-gradient(90deg,' + t.colors[0] + ' 0%,' + t.colors[1] + ' 50%,' + t.colors[2] + ' 100%)';
      var dot = document.createElement('i'); dot.style.background = t.colors[3]; dot.style.color = t.colors[3]; dot.title = 'Thinking color'; sw.appendChild(dot);
      var name = document.createElement('span'); name.textContent = t.name;
      var desc = document.createElement('small'); desc.textContent = t.desc;
      b.append(sw, name, desc);
      b.addEventListener('click', function () { applyTheme(t.id); });
      grid.appendChild(b);
    });
    markSelected();
  }
  function markSelected() {
    var cur = currentTheme();
    document.querySelectorAll('.theme-option').forEach(function (b) { b.setAttribute('aria-checked', String(b.dataset.theme === cur)); });
  }

  /* ---------- settings popup ---------- */
  var panel = $('settings'), openBtn = $('open-settings'), backdrop = $('settings-backdrop'), search = $('settings-search'), emptyNote = $('settings-empty');
  var tabs = Array.prototype.slice.call(document.querySelectorAll('.settings-tab'));
  var curPane = 'look', searching = false, searchTimer = null, seenSearchOnce = false;
  var SYNONYMS = {
    'wake word': 'hey jarvis hotword listen listening microphone mic always on', 'voice replies': 'speak speech talk read aloud tts sound',
    'dictation anywhere': 'type typing speech to text dictate hold key microphone', 'quick actions on text': 'summarise summarize translate fix grammar explain selection clipboard hotkey',
    'phone app (android)': 'android phone link pairing code mobile app network', 'gmail': 'email mail inbox imap app password google',
    'to-do list': 'tasks todo checklist', 'import a calendar': 'timetable school lessons ics ical google outlook schedule webcal', 'notes': 'note jot write down memo remember find', 'spotify': 'music play song playlist album premium', 'file check': 'missing files repair restore github update manifest download install broken',
    'pc health': 'maintenance disk space storage memory ram temp files startup slow cleanup',
    'study mode': 'quiz flashcards revise revision exam test homework learn practise', 'calendar': 'events agenda schedule appointments', 'alerts to your phone (telegram)': 'notifications push battery',
    'interface style': 'theme colour color look appearance dark light', 'telegram': 'bot token phone remote'
  };
  function norm(t) { return String(t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, ''); }
  function setPanel(open) {
    panel.classList.toggle('hidden', !open);
    backdrop.classList.toggle('hidden', !open);
    openBtn.setAttribute('aria-expanded', String(open));
    document.documentElement.classList.toggle('settings-open', open);
    if (open) {
      if (window.matchMedia('(max-width:700px)').matches) { var tab = panel.querySelector('.settings-tab[aria-selected="true"]'); if (tab) tab.focus(); }
      else search.focus();
    } else if (search.value) { search.value = ''; runSearch(); }
  }
  function sectionsOf(pane) { var list = pane.querySelectorAll('.settings-section'); return list.length ? Array.prototype.slice.call(list) : [pane]; }
  function entries() {
    var out = [];
    tabs.forEach(function (t) {
      var pane = document.getElementById('pane-' + t.dataset.pane); if (!pane) return;
      sectionsOf(pane).forEach(function (el) { out.push({ tab: t, pane: pane, el: el }); });
    });
    return out;
  }
  function textOf(e) {
    var el = e.el, extra = '';
    Array.prototype.forEach.call(el.querySelectorAll('[placeholder],[title],[aria-label]'), function (n) { extra += ' ' + (n.getAttribute('placeholder') || '') + ' ' + (n.getAttribute('title') || '') + ' ' + (n.getAttribute('aria-label') || ''); });
    var h = el.querySelector && el.querySelector('.settings-heading');
    return norm(e.tab.textContent + ' ' + el.textContent + extra + ' ' + (h ? (SYNONYMS[norm(h.textContent)] || '') : ''));
  }
  function clearSearchMarks() {
    Array.prototype.forEach.call(document.querySelectorAll('.settings-group-label'), function (n) { n.remove(); });
    entries().forEach(function (e) { e.el.classList.remove('search-hidden'); });
    tabs.forEach(function (t) { t.classList.remove('has-match', 'no-match'); });
    emptyNote.classList.add('hidden');
  }
  function runSearch() {
    var q = norm(search.value.trim());
    if (!q) { if (searching) { searching = false; clearSearchMarks(); selectPane(curPane, false); } return; }
    if (!searching) {
      searching = true;
      if (!seenSearchOnce) { seenSearchOnce = true; tabs.forEach(function (t) { window.dispatchEvent(new CustomEvent('jarvis:pane', { detail: { pane: t.dataset.pane } })); }); }   // lets every pane load its data once
    }
    Array.prototype.forEach.call(document.querySelectorAll('.settings-group-label'), function (n) { n.remove(); });
    var words = q.split(/\s+/), hits = 0, paneHits = {};
    entries().forEach(function (e) {
      var text = textOf(e), ok = words.every(function (w) { return text.indexOf(w) >= 0; });
      e.el.classList.toggle('search-hidden', !ok);
      if (ok) { hits++; paneHits[e.tab.dataset.pane] = true; }
    });
    tabs.forEach(function (t) {
      var pane = document.getElementById('pane-' + t.dataset.pane), on = !!paneHits[t.dataset.pane];
      t.classList.toggle('has-match', on); t.classList.toggle('no-match', !on); t.setAttribute('aria-selected', 'false'); t.tabIndex = -1;
      if (pane) {
        pane.classList.toggle('hidden', !on);
        if (on) { var label = document.createElement('div'); label.className = 'settings-group-label'; label.textContent = t.textContent; pane.insertBefore(label, pane.firstChild); }
      }
    });
    emptyNote.classList.toggle('hidden', hits > 0);
    $('settings-content').scrollTop = 0;
  }
  /* tabs: Look / Voice / AI model / ... */
  function selectPane(name, focus) {
    if (searching && !focus && name !== curPane) { search.value = ''; searching = false; clearSearchMarks(); }
    curPane = name;
    tabs.forEach(function (t) {
      var on = t.dataset.pane === name;
      t.setAttribute('aria-selected', String(on)); t.tabIndex = on ? 0 : -1;
      var pane = document.getElementById('pane-' + t.dataset.pane); if (pane) pane.classList.toggle('hidden', !on);
      if (on && focus) t.focus();
    });
    window.dispatchEvent(new CustomEvent('jarvis:pane', { detail: { pane: name } }));
  }
  tabs.forEach(function (t, i) {
    t.addEventListener('click', function () { if (searching) { search.value = ''; searching = false; clearSearchMarks(); } selectPane(t.dataset.pane, false); });
    t.addEventListener('keydown', function (e) {
      var next = e.key === 'ArrowDown' || e.key === 'ArrowRight' ? i + 1 : e.key === 'ArrowUp' || e.key === 'ArrowLeft' ? i - 1 : e.key === 'Home' ? 0 : e.key === 'End' ? tabs.length - 1 : null;
      if (next === null) return;
      e.preventDefault(); if (searching) { search.value = ''; searching = false; clearSearchMarks(); } selectPane(tabs[(next + tabs.length) % tabs.length].dataset.pane, true);
    });
  });
  window.JarvisUI = { openPane: function (name) { if (searching) { search.value = ''; searching = false; clearSearchMarks(); } selectPane(name, false); setPanel(true); } };
  search.addEventListener('input', function () { clearTimeout(searchTimer); searchTimer = setTimeout(runSearch, 70); });
  search.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { var first = panel.querySelector('.settings-pane:not(.hidden) .settings-section:not(.search-hidden) input,.settings-pane:not(.hidden) .settings-section:not(.search-hidden) select,.settings-pane:not(.hidden) .settings-section:not(.search-hidden) button'); if (first) first.focus(); }
  });
  $('settings-close').addEventListener('click', function () { setPanel(false); openBtn.focus(); });
  backdrop.addEventListener('click', function () { setPanel(false); });
  openBtn.addEventListener('click', function (e) { e.stopPropagation(); setPanel(panel.classList.contains('hidden')); });
  panel.addEventListener('click', function (e) { e.stopPropagation(); });
  document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) { e.preventDefault(); setPanel(true); search.focus(); search.select(); return; }
    if (e.key === 'Escape' && !panel.classList.contains('hidden')) {
      if (search.value) { search.value = ''; runSearch(); search.focus(); return; }
      setPanel(false); openBtn.focus();
    }
  });

  /* ---------- startup sequence (cosmetic) ---------- */
  var boot = $('boot'), log = $('boot-log'), fill = $('boot-bar-fill'), sub = $('boot-sub');
  var LINES = [
    ['Initializing core systems', 'OK'], ['Loading neural interface', 'OK'], ['Calibrating display array', 'OK'],
    ['Syncing voice systems', 'OK'], ['Establishing secure link', 'OK'], ['All systems nominal', '']
  ];
  var timers = [], running = false;
  function later(fn, ms) { timers.push(setTimeout(fn, ms)); }
  function finishBoot(fast) {
    if (!running) return;
    running = false; timers.forEach(clearTimeout); timers = [];
    boot.classList.add('boot-out');
    later(function () { root.removeAttribute('data-boot'); boot.classList.remove('boot-out'); }, fast ? 350 : 650);
  }
  function playBoot() {
    if (running) return;
    running = true; timers.forEach(clearTimeout); timers = [];
    set(K.seen, '1'); set(K.id, window.__bootId || '');
    root.setAttribute('data-boot', 'play'); boot.classList.remove('boot-out');
    log.textContent = ''; fill.style.width = '0'; sub.className = 'boot-sub'; sub.textContent = 'Just A Rather Very Intelligent System';
    var step = 470, start = 900;
    LINES.forEach(function (line, i) {
      later(function () {
        var li = document.createElement('li');
        var label = document.createElement('span'); label.textContent = '> ' + line[0].toUpperCase();
        li.appendChild(label);
        if (line[1]) { var lead = document.createElement('i'); lead.className = 'lead'; var ok = document.createElement('span'); ok.className = 'ok'; ok.textContent = line[1]; li.append(lead, ok); }
        else li.className = 'final';
        log.appendChild(li);
        fill.style.width = Math.round(((i + 1) / LINES.length) * 100) + '%';
      }, start + i * step);
    });
    var end = start + LINES.length * step;
    later(function () { sub.className = 'boot-sub welcome'; sub.textContent = 'Welcome back, ' + (window.JARVIS_ADDRESS || 'sir'); }, end + 150);
    later(function () { finishBoot(false); }, end + 1100);
  }
  $('boot-skip').addEventListener('click', function () { finishBoot(true); });
  document.addEventListener('keydown', function (e) { if (running && (e.key === 'Escape' || e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); finishBoot(true); } });
  boot.addEventListener('click', function (e) { if (e.target === boot) finishBoot(true); });

  $('boot-replay').addEventListener('click', function () { setPanel(false); playBoot(); });
  var modeSel = $('boot-mode');
  modeSel.value = get(K.mode) || 'first';
  modeSel.addEventListener('change', function () { set(K.mode, modeSel.value); });

  /* ---------- animations: follow the Windows "Animation effects" setting, or always animate ---------- */
  var motionSel = $('motion-mode'), reduced = window.matchMedia ? matchMedia('(prefers-reduced-motion: reduce)') : null;
  function showMotion() {
    var always = motionSel.value === 'always', off = !!(reduced && reduced.matches);
    if (always) document.documentElement.setAttribute('data-motion', 'always'); else document.documentElement.removeAttribute('data-motion');
    $('motion-note').textContent = off
      ? (always ? 'Windows animation effects are off on this PC, but Jarvis animates anyway.' : 'Windows animation effects are off on this PC, so Jarvis stays still. Choose “Always animate” to bring the movement back.')
      : 'Windows animation effects are on, so Jarvis animates either way.';
  }
  motionSel.value = get('jarvis-motion') === 'always' ? 'always' : 'system';
  motionSel.addEventListener('change', function () { set('jarvis-motion', motionSel.value); showMotion(); });
  if (reduced && reduced.addEventListener) reduced.addEventListener('change', showMotion);
  showMotion();

  /* ---------- reactor spins up while Jarvis is thinking ---------- */
  var thinkingEl = $('thinking'), spin = 0, spinRaf = 0;
  function isThinking() { return thinkingEl && !thinkingEl.classList.contains('hidden'); }
  function spinStep() {
    var goal = isThinking() ? 1 : 0;
    spin += (goal - spin) * 0.09;                  /* ease toward the goal so speed changes feel smooth */
    if (Math.abs(goal - spin) < 0.01) spin = goal;
    document.getAnimations().forEach(function (a) {
      var name = a.animationName;
      if (name === 'spin') a.updatePlaybackRate(1 + 5 * spin);        /* rings: up to 6x faster */
      else if (name === 'breathe') a.updatePlaybackRate(1 + 1.6 * spin); /* core pulses faster */
    });
    spinRaf = spin === goal ? 0 : requestAnimationFrame(spinStep);
  }
  if (thinkingEl && window.MutationObserver && document.getAnimations) {
    new MutationObserver(function () { if (!spinRaf) spinRaf = requestAnimationFrame(spinStep); })
      .observe(thinkingEl, { attributes: true, attributeFilter: ['class'] });
  }

  /* ---------- HUD dressing: startup reactor copy + clock ---------- */
  var mainReactor = document.querySelector('#orb-stage .reactor'), bootReactor = $('boot-reactor');
  if (mainReactor && bootReactor) bootReactor.innerHTML = mainReactor.innerHTML;
  var timeEl = $('hud-time'), dateEl = $('hud-date'), upEl = $('hud-uptime'), opened = Date.now();
  function two(n) { return (n < 10 ? '0' : '') + n; }
  function tick() {
    var now = new Date(), up = Math.floor((Date.now() - opened) / 1000);
    if (timeEl) { timeEl.firstChild.nodeValue = two(now.getHours()) + ':' + two(now.getMinutes()); timeEl.lastChild.textContent = two(now.getSeconds()); }
    if (dateEl) dateEl.textContent = now.toLocaleDateString(undefined, { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' }).toUpperCase();
    if (upEl) upEl.textContent = 'T+ ' + two(Math.floor(up / 3600)) + ':' + two(Math.floor(up / 60) % 60) + ':' + two(up % 60);
  }
  if (timeEl) { tick(); setInterval(tick, 1000); }

  buildThemeGrid();
  applyTheme(currentTheme());
  if (root.getAttribute('data-boot') === 'play') playBoot();
})();

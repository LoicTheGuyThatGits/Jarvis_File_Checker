/* First-run setup: a short guide the first time Jarvis opens on a new PC (language, how to address you, your town,
   the AI model, voice, what else there is). Settings > Jarvis & updates > Setup brings it back. Everything it sets is an
   ordinary setting, so it uses the same controls and requests as the Settings window. */
(function () {
  'use strict';
  function $(id) { return document.getElementById(id); }
  var panel = $('setup'), backdrop = $('setup-backdrop');
  if (!panel) return;
  var STEPS = ['welcome', 'you', 'place', 'brain', 'voice', 'more', 'done'];
  var at = 0, firstRun = false, brainTimer = null, pulledByUs = '', opened = false;

  function t(s) { return window.JarvisI18n ? window.JarvisI18n.t(s) : s; }
  function api(url, body) {
    var opts = body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined;
    return fetch(url, opts).then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || 'Request failed'); return d; }); });
  }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function nudge(real, value) { if (!real) return; if (real.type === 'checkbox') real.checked = value; else real.value = value; real.dispatchEvent(new Event('change', { bubbles: true })); }

  /* ---------- language: mirrors the selects in Settings > Voice & language ---------- */
  function copyOptions(from, to) {
    if (!from || !to || !from.options.length) return false;
    var keep = to.value; to.textContent = '';
    Array.prototype.forEach.call(from.options, function (o) { var c = o.cloneNode(true); to.appendChild(c); });
    to.value = from.value || keep;
    return true;
  }
  function syncLanguages() { copyOptions($('lang-select'), $('setup-lang')); copyOptions($('ui-lang-select'), $('setup-ui')); }
  function browserLanguage() {
    var want = String(navigator.language || '').slice(0, 2).toLowerCase(), sel = $('lang-select');
    if (!sel || want === 'en') return '';
    return Array.prototype.some.call(sel.options, function (o) { return o.value === want; }) ? want : '';
  }
  $('setup-lang').addEventListener('change', function () { nudge($('lang-select'), $('setup-lang').value); setTimeout(syncLanguages, 600); });
  $('setup-ui').addEventListener('change', function () { nudge($('ui-lang-select'), $('setup-ui').value); setTimeout(syncLanguages, 600); });
  window.addEventListener('jarvis:ui-language', function () { setTimeout(syncLanguages, 300); });

  /* ---------- how Jarvis addresses you ---------- */
  function addressChoice() { var c = panel.querySelector('input[name="setup-address"]:checked'); return c ? c.value : 'sir'; }
  function showAddress(d) {
    var kind = d.address_kind || 'sir';
    var box = panel.querySelector('input[name="setup-address"][value="' + kind + '"]') || panel.querySelector('input[name="setup-address"]');
    box.checked = true;
    $('setup-name').value = kind === 'name' ? d.address : '';
    $('setup-name').classList.toggle('hidden', kind !== 'name');
  }
  Array.prototype.forEach.call(panel.querySelectorAll('input[name="setup-address"]'), function (r) {
    r.addEventListener('change', function () { var named = addressChoice() === 'name'; $('setup-name').classList.toggle('hidden', !named); if (named) $('setup-name').focus(); });
  });
  function saveAddress() {
    var kind = addressChoice(), name = kind === 'name' ? $('setup-name').value.trim() : kind;
    if (!name) { $('setup-name').focus(); return Promise.reject(new Error('Type a name, or choose Sir or Ma’am.')); }
    return api('/api/setup', { address: name }).then(function (d) { window.JARVIS_ADDRESS = d.address; });
  }

  /* ---------- your town, for the weather ---------- */
  var placeFound = false;
  function placeLabel(l) { return [l.name, l.region, l.country].filter(Boolean).join(', '); }
  function findPlace() {
    var name = $('setup-place').value.trim(), note = $('setup-place-note');
    if (!name) return Promise.resolve(false);
    note.textContent = t('Looking it up…');
    return api('/api/location', { name: name }).then(function (d) {
      placeFound = true; $('setup-place').value = d.location.name;
      note.textContent = ''; note.appendChild(el('span', 'setup-ok', '✓ ')); note.appendChild(el('span', '', placeLabel(d.location)));
      if ($('brief-place')) $('brief-place').value = d.location.name;
      return true;
    }).catch(function (e) { placeFound = false; note.textContent = e.message; return false; });
  }
  $('setup-find').addEventListener('click', findPlace);
  $('setup-place').addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); findPlace(); } });
  $('setup-place').addEventListener('input', function () { placeFound = false; });

  /* ---------- the AI model ---------- */
  function row(k, v, extra) {
    var r = el('div', 'setup-row'); r.appendChild(el('div', 'setup-k', k));
    var val = el('div', 'setup-v'); val.appendChild(el('div', 'setup-name', v)); if (extra) val.appendChild(el('div', 'setup-sub', extra));
    r.appendChild(val); return r;
  }
  function button(text, fn, primary) { var b = el('button', 'settings-action setup-inline' + (primary ? ' primary' : ''), text); b.type = 'button'; b.addEventListener('click', fn); return b; }
  function renderBrain(b) {
    var box = $('setup-brain'); box.textContent = '';
    clearTimeout(brainTimer);
    if (!b.local) {
      box.appendChild(el('p', 'setup-line', 'Jarvis uses a cloud AI model. Your messages go to that provider.'));
      box.appendChild(row('Chat', b.model, b.ready ? 'Ready.' : 'The cloud key is missing.'));
      return;
    }
    if (!b.running) {
      if (!b.ollama_installed) {
        box.appendChild(el('p', 'setup-line warn', 'Ollama is not installed yet.'));
        box.appendChild(el('p', 'setup-sub', 'Ollama is a free program that runs AI models on this PC. Install it from ollama.com, then press Check again.'));
        var a = el('a', 'settings-action setup-inline primary', 'Open ollama.com'); a.href = 'https://ollama.com/download'; a.target = '_blank'; a.rel = 'noopener';
        var line = el('div', 'setup-buttons'); line.appendChild(a); line.appendChild(button('Check again', function () { loadBrain(false); })); box.appendChild(line);
      } else {
        box.appendChild(el('p', 'setup-line warn', 'Ollama is installed but not running.'));
        var l2 = el('div', 'setup-buttons'); l2.appendChild(button('Start Ollama', function () { loadBrain(true); }, true)); box.appendChild(l2);
      }
      return;
    }
    if (b.pc) box.appendChild(row('This PC', b.pc.gpu || t('No graphics card for AI')));
    box.appendChild(row('Chat model', b.model, b.ready ? 'Ready.' : 'Not downloaded yet.'));
    var best = b.best, pull = b.pull || {};
    var sameAsBest = best && (best.name === b.model || (best.own && /^jarvis/.test(b.model)));
    if (pull.running) {
      var bar = el('div', 'setup-progress'), fill = el('i'); bar.appendChild(fill);
      var pct = pull.total ? Math.round(100 * pull.done / pull.total) : 0; fill.style.width = pct + '%';
      box.appendChild(row('Download in progress', pull.model, pull.total ? pct + ' %' : (pull.status || '')));
      box.appendChild(bar);
      box.appendChild(el('p', 'setup-sub', 'You can go on with the setup meanwhile.'));
      brainTimer = setTimeout(function () { loadBrain(false); }, 2000);
      return;
    }
    if (pull.error) box.appendChild(el('p', 'setup-line warn', pull.error));
    if (best && !sameAsBest) {
      var how = (best.size_gb ? best.size_gb + ' GB' : '') + (best.tps ? ' · ~' + Math.round(best.tps) + ' ' + t('words/s') : '');
      box.appendChild(row('Best for this PC', best.name, how));
      var l3 = el('div', 'setup-buttons');
      if (best.installed) {
        l3.appendChild(button('Use it', function () { useModel(best.name); }, true));
      } else {
        l3.appendChild(button('Download', function () { pulledByUs = best.name; api('/api/advisor', { pull: best.name }).then(function () { loadBrain(false); }).catch(function (e) { $('setup-brain').appendChild(el('p', 'setup-line warn', e.message)); }); }, !b.ready));
      }
      box.appendChild(l3);
      if (b.ready) box.appendChild(el('p', 'setup-sub', 'The chat model you have works, but the one above suits this PC better. It is your choice.'));
    } else if (!best && !b.ready) {
      box.appendChild(el('p', 'setup-line warn', 'Nothing suitable runs here.'));
    }
    if (b.ready && (sameAsBest || !best)) box.appendChild(el('p', 'setup-line ok', 'Jarvis is ready to think on this PC.'));
    if (pulledByUs && best && best.name === pulledByUs && best.installed && !b.ready) { pulledByUs = ''; useModel(best.name); }
  }
  function useModel(name) {
    api('/api/advisor', { apply: { role: 'chat', model: name } }).then(function () { loadBrain(false); }).catch(function (e) { $('setup-brain').appendChild(el('p', 'setup-line warn', e.message)); });
  }
  function loadBrain(start) {
    if (start || !$('setup-brain').children.length) { $('setup-brain').textContent = ''; $('setup-brain').appendChild(el('p', 'setup-line', start ? 'Starting Ollama…' : 'Checking this PC…')); }
    api('/api/setup?brain=1' + (start ? '&start=1' : '')).then(function (d) { if (opened && STEPS[at] === 'brain') renderBrain(d.brain); })
      .catch(function (e) { $('setup-brain').textContent = e.message; });
  }

  /* ---------- voice: mirrors Settings > Voice & language ---------- */
  function syncVoice() {
    $('setup-voice').checked = !!($('voice-on') && $('voice-on').checked);
    $('setup-wake').checked = !!($('ww-enabled') && $('ww-enabled').checked);
    $('setup-wake-note').textContent = $('ww-status') ? $('ww-status').textContent : '';
  }
  $('setup-voice').addEventListener('change', function () { nudge($('voice-on'), $('setup-voice').checked); });
  $('setup-wake').addEventListener('change', function () { nudge($('ww-enabled'), $('setup-wake').checked); setTimeout(syncVoice, 1500); setTimeout(syncVoice, 4000); });
  $('setup-voice-test').addEventListener('click', function () { if (!$('voice-on').checked) { $('setup-voice').checked = true; nudge($('voice-on'), true); } if ($('voice-test')) $('voice-test').click(); });

  /* ---------- more, and trying it ---------- */
  Array.prototype.forEach.call(panel.querySelectorAll('[data-open-pane]'), function (b) {
    b.addEventListener('click', function () { finish().then(function () { if (window.JarvisUI) window.JarvisUI.openPane(b.getAttribute('data-open-pane')); }); });
  });
  Array.prototype.forEach.call(panel.querySelectorAll('[data-try]'), function (b) {
    b.addEventListener('click', function () {
      var said = b.textContent.replace(/[“”]/g, '');
      finish();
      var box = $('message'); if (!box) return;
      box.value = said; box.dispatchEvent(new Event('input', { bubbles: true })); box.focus();
    });
  });

  /* ---------- moving through the steps ---------- */
  function show(i) {
    at = Math.max(0, Math.min(STEPS.length - 1, i));
    Array.prototype.forEach.call(panel.querySelectorAll('.setup-step'), function (s) { s.classList.toggle('hidden', s.getAttribute('data-step') !== STEPS[at]); });
    Array.prototype.forEach.call(panel.querySelectorAll('.setup-dots li'), function (d, n) { d.className = n < at ? 'done' : n === at ? 'now' : ''; });
    $('setup-back').classList.toggle('invisible', at === 0);
    $('setup-skip').classList.toggle('invisible', at === 0 || at === STEPS.length - 1);
    $('setup-next').textContent = at === STEPS.length - 1 ? 'Start using Jarvis' : 'Next';
    $('setup-error').textContent = '';
    var step = STEPS[at];
    if (step === 'welcome') syncLanguages();
    if (step === 'brain') loadBrain(false); else clearTimeout(brainTimer);
    if (step === 'voice') syncVoice();
    var focus = panel.querySelector('.setup-step[data-step="' + step + '"] input:not([type=radio]):not(.hidden), .setup-step[data-step="' + step + '"] select');
    if (focus && step !== 'brain') setTimeout(function () { try { focus.focus({ preventScroll: true }); } catch (e) {} }, 60);
    $('setup-body').scrollTop = 0;
  }
  function next() {
    var step = STEPS[at], err = $('setup-error');
    var go = Promise.resolve();
    if (step === 'you') go = saveAddress();
    if (step === 'place' && $('setup-place').value.trim() && !placeFound) go = findPlace().then(function (ok) { if (!ok) throw new Error($('setup-place-note').textContent || 'I could not find that place.'); });
    if (step === 'done') return finish();
    $('setup-next').disabled = true;
    return go.then(function () { show(at + 1); }).catch(function (e) { err.textContent = e.message; }).then(function () { $('setup-next').disabled = false; });
  }
  function finish() {
    close();
    return api('/api/setup', { done: true }).catch(function () {});
  }
  function open(isFirst) {
    firstRun = !!isFirst; opened = true;
    panel.classList.remove('hidden'); backdrop.classList.remove('hidden');
    document.documentElement.classList.add('setup-open');
    api('/api/setup').then(showAddress).catch(function () {});
    api('/api/location').then(function (d) { if (!firstRun && d.location) $('setup-place').value = d.location.name; }).catch(function () {});
    var tries = 0;
    (function waitForLanguages() {
      if (copyOptions($('lang-select'), $('setup-lang')) || tries++ > 40) {
        syncLanguages();
        var want = firstRun ? browserLanguage() : '';
        if (want && $('lang-select').value === 'en') { $('setup-lang').value = want; nudge($('lang-select'), want); setTimeout(syncLanguages, 800); }
        return;
      }
      setTimeout(waitForLanguages, 150);
    })();
    show(0);
  }
  function close() {
    opened = false; clearTimeout(brainTimer);
    panel.classList.add('hidden'); backdrop.classList.add('hidden');
    document.documentElement.classList.remove('setup-open');
  }
  $('setup-next').addEventListener('click', next);
  $('setup-back').addEventListener('click', function () { show(at - 1); });
  $('setup-skip').addEventListener('click', function () { show(at + 1); });
  $('setup-close').addEventListener('click', finish);
  panel.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { e.preventDefault(); finish(); }
    if (e.key === 'Enter' && e.target.tagName !== 'BUTTON' && e.target.tagName !== 'A' && e.target.id !== 'setup-place') { e.preventDefault(); next(); }
  });
  if ($('setup-again')) $('setup-again').addEventListener('click', function () { var s = $('settings-close'); if (s) s.click(); open(false); });

  window.JarvisSetup = { open: open, close: close, step: function () { return STEPS[at]; } };

  /* the first time Jarvis opens on this PC: after the startup animation */
  api('/api/setup').then(function (d) {
    if (!d.needed) return;
    (function whenBooted() {
      if (document.documentElement.hasAttribute('data-boot')) return setTimeout(whenBooted, 300);
      open(true);
    })();
  }).catch(function () {});
})();

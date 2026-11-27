/* Safe mode: when Jarvis started with only chat and Settings (after it kept stopping, or when asked), a banner says why, shows
   what went wrong and offers “Start normally”. It also shows one-time notices, like a damaged settings file. */
(function () {
  'use strict';
  function $(id) { return document.getElementById(id); }
  var banner = $('safe-banner');
  if (!banner) return;
  var state = null;
  function t(s) { return window.JarvisI18n ? window.JarvisI18n.t(s) : s; }
  function api(path, body) {
    var opts = body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined;
    return fetch(path, opts).then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || 'Request failed'); return d; }); });
  }
  var WHY = {
    crashes: 'Jarvis kept stopping, so it started in safe mode. Voice, Telegram, connected tools, the phone link, shortcuts and background tasks are off; chat and Settings work.',
    asked: 'Jarvis started in safe mode, as asked. Voice, Telegram, connected tools, the phone link, shortcuts and background tasks are off; chat and Settings work.'
  };
  function restart(safe) {
    var before = state && state.started;
    api('/api/install').then(function (d) {
      before = d.started;
      $('sb-title').textContent = t('Restarting Jarvis…');
      return api('/api/safe', { safe: safe });
    }).then(function () {
      var n = 0, timer = setInterval(function () {
        fetch('/api/install').then(function (r) { return r.json(); }).then(function (d) { if (d.started !== before) { clearInterval(timer); location.reload(); } }).catch(function () {});
        if (++n > 60) clearInterval(timer);
      }, 1000);
    }).catch(function (e) { $('sb-text').textContent = e.message; });
  }
  function show(d) {
    state = d;
    if ($('safe-restart')) $('safe-restart').textContent = t(d.safe ? 'Start normally' : 'Restart in safe mode');
    if (d.safe) {
      banner.classList.remove('hidden');
      $('sb-title').textContent = t('Safe mode');
      $('sb-text').textContent = t(WHY[d.reason] || WHY.asked);
      if (d.notices && d.notices.length) { var n = document.createElement('div'); n.textContent = d.notices.join(' '); $('sb-text').appendChild(n); }
      $('sb-crash').textContent = d.crash || t('Nothing was written down.');
      $('sb-details').classList.toggle('hidden', !d.crash);
      ['sb-updates', 'sb-normal'].forEach(function (id) { $(id).classList.remove('hidden'); });
      $('sb-ok').classList.add('hidden');
    } else if (d.notices && d.notices.length) {
      banner.classList.remove('hidden'); banner.classList.add('notice');
      $('sb-title').textContent = t('Note');
      $('sb-text').textContent = d.notices.join(' ');
      ['sb-details', 'sb-updates', 'sb-normal'].forEach(function (id) { $(id).classList.add('hidden'); });
      $('sb-ok').classList.remove('hidden');
    }
  }
  $('sb-details').addEventListener('click', function () { $('sb-more').classList.toggle('hidden'); });
  $('sb-copy').addEventListener('click', function () {
    var text = 'Jarvis safe mode (' + (state && state.reason) + ')\n\n' + $('sb-crash').textContent;
    (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject()).then(function () { $('sb-copy').textContent = t('Copied'); }).catch(function () {
      var r = document.createRange(); r.selectNodeContents($('sb-crash')); var sel = getSelection(); sel.removeAllRanges(); sel.addRange(r); $('sb-copy').textContent = t('Press Ctrl+C');
    });
  });
  $('sb-updates').addEventListener('click', function () { if (window.JarvisUI) window.JarvisUI.openPane('system'); if (window.JarvisUpdates) window.JarvisUpdates.check(); });
  $('sb-normal').addEventListener('click', function () { restart(false); });
  $('sb-ok').addEventListener('click', function () { banner.classList.add('hidden'); api('/api/safe', { seen: true }).catch(function () {}); });
  if ($('safe-restart')) $('safe-restart').addEventListener('click', function () { restart(!(state && state.safe)); });
  api('/api/safe').then(show).catch(function () {});
  window.JarvisSafe = { state: function () { return state; } };
})();

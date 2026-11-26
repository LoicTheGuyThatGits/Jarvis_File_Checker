/* Updates: a banner when a new version of Jarvis is out (with what's new and “Update and restart”), the Updates section at
   the top of Settings > Jarvis & updates, and a short note after Jarvis restarted on a new version. The server does the work
   (GET/POST /api/updates): it downloads only the files that changed, installs new Python packages, then restarts. */
(function () {
  'use strict';
  function $(id) { return document.getElementById(id); }
  var banner = $('update-banner');
  if (!banner) return;
  var state = null, polling = null, startedAt = null, notesOpen = false, DISMISS = 'jarvis-update-later';

  function t(s) { return window.JarvisI18n ? window.JarvisI18n.t(s) : s; }
  function api(path, body) {
    var opts = body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined;
    return fetch(path, opts).then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || 'Request failed'); return d; }); });
  }
  function get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  function versionLabel(d) { return d.version || t('Follows every change on GitHub'); }
  function newLabel(d) { return d.new_version ? t('Version') + ' ' + d.new_version : t('The latest changes from GitHub'); }
  function fillNotes(list, notes) {
    list.textContent = '';
    (notes && notes.lines || []).forEach(function (line) { var li = document.createElement('li'); li.textContent = line; list.appendChild(li); });
    return list.children.length;
  }
  var STEP = { downloading: 'Downloading the update…', packages: 'Installing the new Python packages…', restarting: 'Restarting Jarvis…' };
  var PCT = { downloading: 35, packages: 70, restarting: 95 };

  /* ---------- the banner ---------- */
  function showBanner(d) {
    var busy = !!STEP[d.install];
    var wanted = d.available && (busy || get(DISMISS) !== d.signature);
    banner.classList.toggle('hidden', !wanted);
    if (!wanted) return;
    $('ub-title').textContent = busy ? STEP[d.install] : d.install === 'failed' ? t('The update did not finish.') : t('A new version of Jarvis is ready.');
    $('ub-sub').textContent = d.install === 'failed' ? (d.install_error || '') : newLabel(d);
    $('ub-install').textContent = d.install === 'failed' ? t('Try again') : t('Update and restart');
    $('ub-install').classList.toggle('hidden', busy);
    $('ub-later').classList.toggle('hidden', busy);
    var n = fillNotes($('ub-list'), d.notes);
    $('ub-notes').classList.toggle('hidden', !n || busy);
    $('ub-list').classList.toggle('hidden', !n || !notesOpen || busy);
    $('ub-progress').classList.toggle('hidden', !busy);
    $('ub-progress').firstChild.style.width = (PCT[d.install] || 0) + '%';
    banner.classList.toggle('failed', d.install === 'failed');
  }
  function showDone(done) {
    banner.classList.remove('hidden', 'failed');
    banner.classList.add('done');
    $('ub-title').textContent = t('Jarvis was updated.');
    $('ub-sub').textContent = done.version ? t('Version') + ' ' + done.version : '';
    var n = fillNotes($('ub-list'), done.notes);
    $('ub-notes').classList.toggle('hidden', !n);
    $('ub-list').classList.add('hidden');
    $('ub-install').classList.add('hidden'); $('ub-progress').classList.add('hidden');
    $('ub-later').classList.remove('hidden'); $('ub-later').textContent = t('Close');
    api('/api/updates', { seen: true }).catch(function () {});
  }

  /* ---------- the Updates section in Settings ---------- */
  function showSection(d) {
    if (!$('upd-version')) return;
    $('upd-version').textContent = versionLabel(d);
    var busy = !!STEP[d.install], status = '';
    if (busy) status = STEP[d.install];
    else if (d.checking) status = 'Checking…';
    else if (d.error) status = '';
    else if (d.available) status = 'A new version of Jarvis is ready.';
    else if (d.checked) status = 'Jarvis is up to date.';
    $('upd-status').textContent = t(status);
    if (d.available && !busy) { var s = document.createElement('div'); s.className = 'upd-new'; s.setAttribute('data-no-i18n', ''); s.textContent = newLabel(d); $('upd-status').appendChild(s); }
    if (d.checked && !busy && !d.checking) {
      var c = document.createElement('div'); c.className = 'upd-when'; c.setAttribute('data-no-i18n', '');
      c.textContent = t('Last checked:') + ' ' + new Date(d.checked * 1000).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
      $('upd-status').appendChild(c);
    }
    var n = fillNotes($('upd-notes'), d.notes);
    $('upd-notes-box').classList.toggle('hidden', !(d.available && n));
    $('upd-install').classList.toggle('hidden', !d.available || busy);
    $('upd-install').textContent = d.install === 'failed' ? t('Try again') : t('Update and restart');
    $('upd-check').disabled = busy || d.checking;
    $('upd-progress').classList.toggle('hidden', !busy);
    $('upd-progress').firstChild.style.width = (PCT[d.install] || 0) + '%';
    var err = d.install === 'failed' ? t('The update did not finish:') + ' ' + d.install_error : d.error ? t('Could not check for updates:') + ' ' + d.error : '';
    $('upd-error').textContent = err; $('upd-error').classList.toggle('hidden', !err);
    if ($('files-auto')) $('files-auto').checked = d.auto !== false;
  }

  function show(d) {
    state = d;
    if (startedAt === null) startedAt = d.started;
    else if (d.started !== startedAt) { location.reload(); return; }       // Jarvis came back on the new version
    showSection(d);
    if (d.updated && !STEP[d.install]) { showDone(d.updated); return; }
    if (!banner.classList.contains('done')) showBanner(d);
    var busy = !!STEP[d.install] || d.checking;
    if (busy && !polling) polling = setInterval(poll, 1500);
    if (!busy && polling) { clearInterval(polling); polling = null; }
  }
  function poll() { fetch('/api/updates').then(function (r) { return r.json(); }).then(show).catch(function () { /* restarting: not answering for a moment */ }); }
  function check() {
    if ($('upd-status')) $('upd-status').textContent = t('Checking…');
    $('upd-check').disabled = true;
    api('/api/updates?check=1').then(show).catch(function (e) { $('upd-error').textContent = e.message; $('upd-error').classList.remove('hidden'); $('upd-check').disabled = false; });
  }
  function install() {
    notesOpen = false;
    api('/api/updates', { install: true }).then(show).catch(function (e) {
      $('ub-title').textContent = t('The update did not finish.'); $('ub-sub').textContent = e.message;
      if ($('upd-error')) { $('upd-error').textContent = e.message; $('upd-error').classList.remove('hidden'); }
    });
  }

  $('ub-install').addEventListener('click', install);
  $('ub-later').addEventListener('click', function () {
    if (banner.classList.contains('done')) banner.classList.remove('done');
    else if (state && state.signature) set(DISMISS, state.signature);        // this version: not again; a newer one shows again
    banner.classList.add('hidden'); $('ub-later').textContent = t('Later');
  });
  $('ub-notes').addEventListener('click', function () { notesOpen = !notesOpen; $('ub-list').classList.toggle('hidden', !notesOpen); });
  $('upd-check').addEventListener('click', check);
  $('upd-install').addEventListener('click', install);
  window.addEventListener('jarvis:update', function (e) { if (e.detail) show(e.detail); });
  window.addEventListener('jarvis:update-recheck', check);
  window.addEventListener('jarvis:pane', function (e) { if (e.detail && window.paneHas && window.paneHas(e.detail.pane, 'upd-version')) poll(); });
  poll();
  window.JarvisUpdates = { state: function () { return state; }, check: check };
})();

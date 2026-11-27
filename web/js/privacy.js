/* Settings > Your data: what Jarvis keeps and what leaves the PC (GET /api/privacy), and deleting it (POST /api/privacy/delete).
   Every delete asks for a second click. The server restarts Jarvis afterwards; the page reloads when it is back. */
(function () {
  'use strict';
  function $(id) { return document.getElementById(id); }
  if (!$('pane-privacy')) return;
  var CHATS = 'jarvis-chats-v1', armed = null, armTimer = null;

  function t(s) { return window.JarvisI18n ? window.JarvisI18n.t(s) : s; }
  function api(path, body) {
    var opts = body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined;
    return fetch(path, opts).then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || 'Request failed'); return d; }); });
  }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function size(bytes) {
    if (bytes < 1024) return bytes + ' B';
    var u = ['KB', 'MB', 'GB'], i = -1;
    do { bytes /= 1024; i++; } while (bytes >= 1024 && i < u.length - 1);
    return (bytes >= 10 ? Math.round(bytes) : bytes.toFixed(1)) + ' ' + u[i];
  }
  function amount(files, bytes) { return files ? files + ' ' + t(files === 1 ? 'file' : 'files') + ' · ' + size(bytes) : t('Nothing kept'); }
  function browserChats() {
    var raw = null; try { raw = localStorage.getItem(CHATS); } catch (e) {}
    var n = 0; try { n = (JSON.parse(raw || '[]') || []).length; } catch (e) {}
    return { count: n, bytes: raw ? raw.length * 2 : 0 };
  }

  /* a delete button that needs a second click within five seconds */
  function arm(btn, action) {
    if (armed === btn) { clearTimeout(armTimer); armed = null; btn.classList.remove('armed'); action(); return; }
    if (armed) { armed.textContent = armed.getAttribute('data-label'); armed.classList.remove('armed'); }
    armed = btn; btn.setAttribute('data-label', btn.textContent); btn.textContent = t('Click again to delete'); btn.classList.add('armed');
    clearTimeout(armTimer);
    armTimer = setTimeout(function () { if (armed === btn) { btn.textContent = btn.getAttribute('data-label'); btn.classList.remove('armed'); armed = null; } }, 5000);
  }
  function waitForRestart(before) {
    $('privacy-status').textContent = t('Deleted. Restarting Jarvis…');
    var n = 0, timer = setInterval(function () {
      fetch('/api/install').then(function (r) { return r.json(); }).then(function (d) { if (d.started !== before) { clearInterval(timer); location.reload(); } }).catch(function () {});
      if (++n > 60) { clearInterval(timer); $('privacy-status').textContent = t('Jarvis did not come back. Start it again from the Start menu.'); }
    }, 1000);
  }
  function remove(keys, alsoBrowser) {
    api('/api/install').then(function (before) {
      return api('/api/privacy/delete', { keys: keys }).then(function (d) {
        if (alsoBrowser) {
          try { Object.keys(localStorage).filter(function (k) { return k.indexOf('jarvis-') === 0; }).forEach(function (k) { localStorage.removeItem(k); }); } catch (e) {}
        }
        if (d.failed && d.failed.length) $('privacy-status').textContent = t('Some files could not be deleted:') + ' ' + d.failed.map(function (f) { return f[0]; }).join(', ');
        waitForRestart(before.started);
      });
    }).catch(function (e) { $('privacy-status').textContent = e.message; });
  }

  function render(d) {
    var out = $('privacy-outside'); out.textContent = '';
    d.outside.forEach(function (o) {
      var li = el('li', 'privacy-out' + (o.on ? ' on' : ''));
      var head = el('div', 'privacy-out-head');
      head.appendChild(el('span', 'privacy-dot')); head.appendChild(el('span', 'privacy-name', o.name));
      head.appendChild(el('span', 'privacy-state', o.on ? (o.when || 'In use') : 'Not in use'));
      li.appendChild(head); li.appendChild(el('div', 'privacy-what', o.what));
      out.appendChild(li);
    });
    var box = $('privacy-groups'); box.textContent = '';
    var bc = browserChats();
    var rows = d.groups.concat([{ key: 'browser', name: 'Chats in this browser', description: 'The conversations in the chat list, kept by this browser.', files: bc.count, bytes: bc.bytes, browser: true }]);
    rows.forEach(function (g) {
      var row = el('div', 'privacy-group');
      var text = el('div', 'privacy-group-text');
      text.appendChild(el('div', 'privacy-name', g.name)); text.appendChild(el('div', 'privacy-what', g.description));
      var amt = el('div', 'privacy-amount', g.browser ? (g.files ? g.files + ' ' + t(g.files === 1 ? 'chat' : 'chats') + ' · ' + size(g.bytes) : t('Nothing kept')) : amount(g.files, g.bytes));
      amt.setAttribute('data-no-i18n', ''); text.appendChild(amt);
      var btn = el('button', 'privacy-delete', 'Delete'); btn.type = 'button'; btn.disabled = !g.files;
      btn.setAttribute('data-key', g.key);
      btn.addEventListener('click', function () {
        arm(btn, function () {
          if (g.browser) { try { localStorage.removeItem(CHATS); } catch (e) {} location.reload(); return; }
          remove([g.key], false);
        });
      });
      row.appendChild(text); row.appendChild(btn); box.appendChild(row);
    });
  }
  function load() { api('/api/privacy').then(render).catch(function (e) { $('privacy-status').textContent = e.message; }); }

  $('privacy-all').addEventListener('click', function () { arm($('privacy-all'), function () { remove('all', true); }); });
  $('privacy-open').addEventListener('click', function () {
    api('/api/install/open', { what: 'data' }).then(function () { $('privacy-status').textContent = t('Opened in Explorer.'); }).catch(function (e) { $('privacy-status').textContent = e.message; });
  });
  $('privacy-backup').addEventListener('click', function () {
    if (!window.JarvisUI) return;
    window.JarvisUI.openPane('system');
    setTimeout(function () { var b = $('backup-folder'); if (b) { b.scrollIntoView({ block: 'center' }); b.focus(); } }, 200);
  });
  window.addEventListener('jarvis:pane', function (e) { if (e.detail && e.detail.pane === 'privacy') load(); });
  window.JarvisPrivacy = { load: load };
})();

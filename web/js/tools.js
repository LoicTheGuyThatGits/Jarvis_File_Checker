/* System panel, long-term memory, and timers/reminders. */
(function () {
  'use strict';
  function $(id) { return document.getElementById(id); }
  function get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); }
  function el(tag, cls, text) { var n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; }
  function api(path, body) {
    var opts = body !== undefined ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined;
    return fetch(path, opts).then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || 'Request failed'); return d; }); });
  }

  /* ================= system charts (Task Manager style) ================= */
  var sys = $('sysmon'), sysCharts = $('sys-charts'), sysBox = $('sysmon-on'), big = $('sysbig'), bigGrid = $('sysbig-grid'), bigCores = $('sysbig-cores'), bigStats = $('sysbig-stats');
  var sysEnabled = get('jarvis-sysmon') !== '0', bigOpen = false, bigOpener = null, autoZoom = get('jarvis-chartscale') !== 'fixed';
  var HIST_MS = 125000, hist = { cpu: [], ram: [], gpu: [], vram: [], disk: [], net: [] }, latest = null, charts = [];
  var METRICS = {
    cpu: { label: 'CPU' }, ram: { label: 'RAM' }, gpu: { label: 'GPU' }, vram: { label: 'VRAM' },
    disk: { label: 'DISK', auto: true, names: ['read', 'write'] }, net: { label: 'NETWORK', auto: true, names: ['down', 'up'] }
  };
  var SIDEBAR_KEYS = ['cpu', 'ram', 'gpu', 'vram'], BIG_KEYS = ['cpu', 'ram', 'gpu', 'vram', 'disk', 'net'];
  function has(key) { return hist[key].length > 0; }
  function push(key, v, v2) {
    var a = hist[key], t = Date.now(); a.push({ t: t, v: v, v2: v2 == null ? null : v2 });
    while (a.length && a[0].t < t - HIST_MS) a.shift();
  }
  function ingest(d) {
    latest = d;
    if (d.cpu != null) push('cpu', d.cpu);
    if (d.ram) push('ram', d.ram.percent);
    if (d.gpu && d.gpu.util != null) { push('gpu', d.gpu.util); if (d.gpu.mem_total_mb) push('vram', 100 * d.gpu.mem_used_mb / d.gpu.mem_total_mb); }
    if (d.disk) push('disk', d.disk.read_mbps, d.disk.write_mbps);
    if (d.net) push('net', d.net.down_mbps, d.net.up_mbps);
    buildCharts(); updateTexts(); updateBattery(d.battery); updateCores(); kick();
  }
  function fmtRate(v) { return v >= 100 ? v.toFixed(0) : v >= 10 ? v.toFixed(1) : v.toFixed(2); }
  function valueText(key) {
    var d = latest; if (!d) return '';
    if (key === 'cpu') return Math.round(d.cpu) + '%';
    if (key === 'ram') return Number(d.ram.used_gb).toFixed(1) + ' / ' + Number(d.ram.total_gb).toFixed(d.ram.total_gb % 1 ? 1 : 0) + ' GB';
    if (key === 'gpu') return Math.round(d.gpu.util) + '%' + (d.gpu.temp_c != null ? ' · ' + Math.round(d.gpu.temp_c) + '°C' : '');
    if (key === 'vram') return (d.gpu.mem_used_mb / 1024).toFixed(1) + ' / ' + (d.gpu.mem_total_mb / 1024).toFixed(1) + ' GB';
    if (key === 'disk') return 'R ' + fmtRate(d.disk.read_mbps) + '  W ' + fmtRate(d.disk.write_mbps) + ' MB/s';
    if (key === 'net') return '↓ ' + fmtRate(d.net.down_mbps) + '  ↑ ' + fmtRate(d.net.up_mbps) + ' MB/s';
    return '';
  }
  function subText(key) {
    var d = latest; if (!d) return '';
    if (key === 'cpu' && d.cpu_info) return d.cpu_info.logical + ' threads' + (d.cpu_info.ghz ? ' · ' + d.cpu_info.ghz + ' GHz' : '');
    if (key === 'ram') return Math.round(d.ram.percent) + '% in use';
    if (key === 'gpu') return d.gpu.name || '';
    if (key === 'vram') return Math.round(100 * d.gpu.mem_used_mb / d.gpu.mem_total_mb) + '% in use';
    return '';
  }
  function makeChart(parent, key, windowMs, big) {
    var wrap = el('div', 'sys-chart' + (big ? ' big' : '')), head = el('div', 'sys-chart-head'), label = el('span', 'sys-chart-label', METRICS[key].label), val = el('span', 'sys-chart-val');
    var cv = document.createElement('canvas'), sub = el('div', 'sys-chart-sub'); wrap.dataset.key = key;
    head.append(label, val); wrap.append(head, cv, sub); parent.appendChild(wrap);
    if (!big) { wrap.tabIndex = 0; wrap.setAttribute('role', 'button'); wrap.setAttribute('aria-label', 'Open the system monitor'); wrap.addEventListener('click', openBig); wrap.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openBig(); } }); }
    var c = { key: key, wrap: wrap, cv: cv, val: val, sub: sub, windowMs: windowMs, max: METRICS[key].auto ? 1 : 100 };
    charts.push(c); return c;
  }
  function buildCharts() {
    SIDEBAR_KEYS.forEach(function (k) { if (has(k) && !charts.some(function (c) { return c.key === k && !c.wrap.classList.contains('big'); })) makeChart(sysCharts, k, 60000, false); });
    if (bigOpen) BIG_KEYS.forEach(function (k) { if (has(k) && !charts.some(function (c) { return c.key === k && c.wrap.classList.contains('big'); })) makeChart(bigGrid, k, 120000, true); });
    sys.classList.toggle('empty', !charts.length);
  }
  function updateTexts() {
    charts.forEach(function (c) { if (has(c.key)) { c.val.textContent = valueText(c.key); c.sub.textContent = subText(c.key); } });
    if (bigOpen && latest) {
      var bits = [];
      if (latest.processes != null) bits.push('<b>' + latest.processes + '</b> processes');
      if (latest.uptime_s != null) { var u = latest.uptime_s, d = Math.floor(u / 86400), h = Math.floor(u % 86400 / 3600), m = Math.floor(u % 3600 / 60); bits.push('up <b>' + (d ? d + 'd ' : '') + h + 'h ' + m + 'm</b>'); }
      if (latest.cpu_info) bits.push('<b>' + latest.cpu_info.logical + '</b> threads' + (latest.cpu_info.physical ? ' on <b>' + latest.cpu_info.physical + '</b> cores' : ''));
      if (latest.gpu && latest.gpu.name) bits.push(latest.gpu.name);
      bigStats.innerHTML = ''; bits.forEach(function (b) { var s = el('span', 'sysbig-stat'); s.innerHTML = b; bigStats.appendChild(s); });
    }
  }
  function updateBattery(b) {
    var row = $('sys-battery'); if (!b) { row.classList.add('hidden'); return; }
    row.classList.remove('hidden'); row.querySelector('i').style.width = Math.max(0, Math.min(100, b.percent)) + '%';
    row.querySelector('.sys-val').textContent = Math.round(b.percent) + '%' + (b.plugged ? ' ⚡' : ''); row.classList.toggle('hot', b.percent <= 10 && !b.plugged);
  }
  var coreEls = [];
  function updateCores() {
    if (!bigOpen || !latest || !latest.cpu_cores) { bigCores.classList.toggle('hidden', true); return; }
    bigCores.classList.remove('hidden');
    if (coreEls.length !== latest.cpu_cores.length) {
      clear(bigCores); coreEls = [];
      latest.cpu_cores.forEach(function (_, n) { var c = el('div', 'core'), bar = el('i'); c.title = 'Thread ' + n; c.append(bar, el('span', null, String(n))); bigCores.appendChild(c); coreEls.push(bar); });
    }
    latest.cpu_cores.forEach(function (v, n) { coreEls[n].style.height = Math.max(2, v) + '%'; coreEls[n].parentNode.classList.toggle('hot', v >= 90); coreEls[n].parentNode.title = 'Thread ' + n + ': ' + Math.round(v) + '%'; });
  }

  /* ----- drawing ----- */
  var colors = { accent: [94, 231, 255], ice: [191, 246, 255], at: 0 }, probeA = el('span', 'sys-probe'), probeI = el('span', 'sys-probe');
  probeA.style.color = 'var(--tk-accent)'; probeI.style.color = 'var(--tk-ice)'; document.body.append(probeA, probeI);
  function parseColor(str, fallback) {
    var m = str.match(/color\(srgb\s+([\d.e+-]+)\s+([\d.e+-]+)\s+([\d.e+-]+)/);
    if (m) return [m[1], m[2], m[3]].map(function (x) { return Math.round(parseFloat(x) * 255); });
    m = str.match(/rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/);
    return m ? [parseFloat(m[1]), parseFloat(m[2]), parseFloat(m[3])] : fallback;
  }
  function refreshColors(now) {
    if (now - colors.at < 120) return; colors.at = now;
    colors.accent = parseColor(getComputedStyle(probeA).color, colors.accent); colors.ice = parseColor(getComputedStyle(probeI).color, colors.ice);
  }
  function rgba(c, a) { return 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',' + a + ')'; }
  function niceMax(v) { var steps = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]; for (var k = 0; k < steps.length; k++) if (v * 1.15 <= steps[k]) return steps[k]; return Math.ceil(v * 1.15); }
  function drawChart(c, now) {
    var cv = c.cv, w = cv.clientWidth, h = cv.clientHeight; if (!w || !h) return;
    var dpr = window.devicePixelRatio || 1;
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
    var g = cv.getContext('2d'), arr = hist[c.key], win = c.windowMs, meta = METRICS[c.key];
    g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, w, h);
    var max = 100, zoomLabel = null;
    if (!meta.auto && autoZoom && (c.key === 'cpu' || c.key === 'gpu')) {
      /* zoom in on small values so changes stay visible: 10%, 20%, 30%, 50%, 75% or 100% full scale */
      var peak = 0; arr.forEach(function (p) { if (p.t > now - win) peak = Math.max(peak, p.v); });
      var target = 100, steps = [10, 20, 30, 50, 75, 100];
      for (var z = 0; z < steps.length; z++) if (peak * 1.25 <= steps[z]) { target = steps[z]; break; }
      c.max += (target - c.max) * 0.12; max = c.max; zoomLabel = target + '%';
    }
    if (meta.auto) { var m = 0.5; arr.forEach(function (p) { if (p.t > now - win) m = Math.max(m, p.v, p.v2 || 0); }); c.max += (niceMax(m) - c.max) * 0.12; max = c.max; }
    var last = arr[arr.length - 1], hot = !meta.auto && last && last.v >= 90, line = hot ? [255, 90, 77] : colors.accent;
    /* grid: horizontal quarters + vertical lines that scroll with time */
    g.lineWidth = 1; g.setLineDash([2, 4]); g.strokeStyle = rgba(colors.accent, 0.14); g.beginPath();
    for (var q = 1; q < 4; q++) { var gy = Math.round(h * q / 4) + 0.5; g.moveTo(0, gy); g.lineTo(w, gy); }
    var stepMs = win > 90000 ? 20000 : 10000;
    for (var t = Math.ceil((now - win) / stepMs) * stepMs; t <= now; t += stepMs) { var gx = Math.round(w * (1 - (now - t) / win)) + 0.5; g.moveTo(gx, 0); g.lineTo(gx, h); }
    g.stroke(); g.setLineDash([]);
    function points(sel) {
      var out = [];
      arr.forEach(function (p) { var v = sel(p); if (v == null || p.t < now - win - 2500) return; out.push([w * (1 - (now - p.t) / win), (h - 1) - Math.min(1, v / max) * (h - 3)]); });
      if (out.length) out.push([w, out[out.length - 1][1]]);
      return out;
    }
    var main = points(function (p) { return p.v; });
    if (main.length > 1) {
      var grad = g.createLinearGradient(0, 0, 0, h); grad.addColorStop(0, rgba(line, 0.42)); grad.addColorStop(1, rgba(line, 0.02));
      g.beginPath(); g.moveTo(main[0][0], h); main.forEach(function (p) { g.lineTo(p[0], p[1]); }); g.lineTo(main[main.length - 1][0], h); g.closePath(); g.fillStyle = grad; g.fill();
      g.beginPath(); main.forEach(function (p, n) { n ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1]); });
      g.lineWidth = 1.6; g.strokeStyle = rgba(line, 0.95); g.shadowColor = rgba(line, 0.75); g.shadowBlur = 6; g.stroke(); g.shadowBlur = 0;
    }
    if (meta.auto) {
      var second = points(function (p) { return p.v2; });
      if (second.length > 1) { g.beginPath(); second.forEach(function (p, n) { n ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1]); }); g.lineWidth = 1.3; g.strokeStyle = rgba(colors.ice, 0.9); g.stroke(); }
      g.font = '9px "DM Mono", Consolas, monospace'; g.fillStyle = rgba(colors.accent, 0.6); g.textBaseline = 'top'; g.fillText(fmtRate(max) + ' MB/s', 4, 3);
    } else if (zoomLabel || c.wrap.classList.contains('big')) { g.font = '9px "DM Mono", Consolas, monospace'; g.fillStyle = rgba(colors.accent, 0.6); g.textBaseline = 'top'; g.fillText(zoomLabel || '100%', 4, 3); }
    if (main.length) {  /* live dot with a pulsing ring */
      var tip = main[main.length - 1], pulse = (now % 1100) / 1100;
      g.fillStyle = rgba(colors.ice, 1); g.beginPath(); g.arc(Math.min(w - 3, tip[0] - 1), tip[1], 2.2, 0, 6.283); g.fill();
      g.strokeStyle = rgba(line, 0.55 * (1 - pulse)); g.lineWidth = 1; g.beginPath(); g.arc(Math.min(w - 3, tip[0] - 1), tip[1], 2.5 + pulse * 6, 0, 6.283); g.stroke();
    }
  }
  var raf = 0, lastFrame = 0;
  function running() { return !document.hidden && ((sysEnabled && !sys.classList.contains('hidden')) || bigOpen); }
  function frame(ts) {
    raf = 0; if (!running()) return;
    if (ts - lastFrame >= 33) { lastFrame = ts; var now = Date.now(); refreshColors(ts); charts.forEach(function (c) { if (has(c.key) && c.cv.clientWidth) drawChart(c, now); }); }
    raf = requestAnimationFrame(frame);
  }
  function kick() { if (!raf && running()) raf = requestAnimationFrame(frame); }

  /* ----- polling ----- */
  function pollSys() { if (running()) api('/api/system').then(ingest).catch(function () {}); }
  function applySysPref() { sys.classList.toggle('hidden', !sysEnabled); sysBox.checked = sysEnabled; if (sysEnabled) { pollSys(); kick(); } }
  var scaleSel = $('chart-scale'); scaleSel.value = autoZoom ? 'auto' : 'fixed';
  scaleSel.addEventListener('change', function () { autoZoom = scaleSel.value !== 'fixed'; set('jarvis-chartscale', scaleSel.value); charts.forEach(function (c) { if (!METRICS[c.key].auto) c.max = 100; }); });
  sysBox.addEventListener('change', function () { sysEnabled = sysBox.checked; set('jarvis-sysmon', sysEnabled ? '1' : '0'); applySysPref(); });
  setInterval(pollSys, 1000); document.addEventListener('visibilitychange', function () { pollSys(); kick(); }); applySysPref();

  /* ----- the larger system monitor window ----- */
  function openBig() {
    if (bigOpen) return; bigOpen = true; bigOpener = document.activeElement;
    big.classList.remove('hidden'); charts = charts.filter(function (c) { if (c.wrap.classList.contains('big')) { c.wrap.remove(); return false; } return true; });
    clear(bigGrid); coreEls = []; clear(bigCores); buildCharts(); updateTexts(); updateCores(); pollSys(); kick(); $('sysbig-close').focus();
  }
  function closeBig() {
    if (!bigOpen) return; bigOpen = false; big.classList.add('hidden');
    charts = charts.filter(function (c) { if (c.wrap.classList.contains('big')) { c.wrap.remove(); return false; } return true; });
    if (bigOpener && bigOpener.focus) bigOpener.focus();
  }
  $('sys-expand').addEventListener('click', function (e) { e.stopPropagation(); openBig(); });
  $('sys-open-big').addEventListener('click', function (e) { e.stopPropagation(); openBig(); });
  $('sysbig-close').addEventListener('click', closeBig);
  big.addEventListener('click', function (e) { e.stopPropagation(); });
  document.addEventListener('click', function () { if (bigOpen) closeBig(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && bigOpen) { e.stopPropagation(); closeBig(); } }, true);

  /* ================= long-term memory ================= */
  var memList = $('memory-list'), memInput = $('memory-input'), memNote = $('memory-note'), memNoteDefault = memNote.textContent;
  function renderMemory(items) {
    clear(memList);
    if (!items.length) { memList.appendChild(el('li', 'tool-empty', 'Nothing remembered yet.')); return; }
    items.slice().reverse().forEach(function (item) {
      var li = el('li', 'tool-item' + (item.source === 'learned' ? ' mem-learned' : '')), text = el('span', 'tool-text', item.text), del = el('button', 'tool-del', '×'), edit = el('button', 'tool-act mem-edit', '✎');
      text.setAttribute('data-no-i18n', '');
      if (item.origin) text.title = 'From: “' + item.origin + '”';
      edit.type = 'button'; edit.setAttribute('aria-label', 'Correct: ' + item.text); edit.title = 'Correct this';
      edit.addEventListener('click', function () {
        var now = prompt('Correct this memory:', item.text); if (now == null || !now.trim() || now.trim() === item.text) return;
        api('/api/memory/edit', { id: item.id, text: now.trim() }).then(function (r) { renderMemory(r.items); }).catch(function (e) { memNote.textContent = e.message; });
      });
      del.type = 'button'; del.setAttribute('aria-label', 'Forget: ' + item.text); del.title = 'Forget this';
      del.addEventListener('click', function () { api('/api/memory/delete', { id: item.id }).then(function (r) { renderMemory(r.items); }); });
      if (item.source === 'learned') li.append(el('span', 'mem-tag', 'learned'));
      li.append(text, edit, del); memList.appendChild(li);
    });
  }
  function renderRecall(r) {
    if (!$('mem-learn') || !r.settings) return;
    $('mem-learn').checked = !!r.settings.learn; $('mem-history').checked = !!r.settings.history; $('mem-keep').value = String(r.settings.keep_days);
    var h = r.history || {}, box = $('mem-stats'); clear(box);
    if (!r.settings.history) { box.textContent = 'The chat history is off.'; return; }
    if (!h.count) { box.textContent = 'No chats in the history yet.'; return; }
    var n = el('span', 'mem-n', String(h.count)), d = el('span', 'mem-d', new Date(h.oldest * 1000).toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' }));
    n.setAttribute('data-no-i18n', ''); d.setAttribute('data-no-i18n', '');
    box.append(el('span', 'mem-l', 'Messages in the history:'), ' ', n, ' ', el('span', 'mem-l', 'since'), ' ', d);
  }
  function refreshMemory() { api('/api/memory').then(function (r) { renderMemory(r.items); renderRecall(r); }).catch(function () {}); }
  if ($('mem-learn')) {
    var saveRecall = function () {
      api('/api/memory/settings', { learn: $('mem-learn').checked, history: $('mem-history').checked, keep_days: +$('mem-keep').value })
        .then(function (r) { renderRecall(r); }).catch(function (e) { $('mem-stats').textContent = e.message; });
    };
    ['mem-learn', 'mem-history', 'mem-keep'].forEach(function (id) { $(id).addEventListener('change', saveRecall); });
    var searchMem = function () {
      var q = $('mem-search').value.trim(), list = $('mem-results'); if (!q) return;
      api('/api/memory/search?q=' + encodeURIComponent(q)).then(function (r) {
        clear(list);
        (r.memory || []).forEach(function (m) { list.appendChild(el('li', 'tool-item', '• ' + m.text)); });
        (r.history || []).forEach(function (x) {
          var li = el('li', 'tool-item mem-hit'), when = el('span', 'mem-when', new Date(x.at * 1000).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }));
          li.append(when, el('span', 'tool-text', x.user + ' → ' + x.reply)); list.appendChild(li);
        });
        if (!list.children.length) list.appendChild(el('li', 'tool-empty', window.JarvisI18n ? window.JarvisI18n.t('Nothing found.') : 'Nothing found.'));
      }).catch(function () {});
    };
    $('mem-search-go').addEventListener('click', searchMem);
    $('mem-search').addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); searchMem(); } });
    var hb = $('mem-history-clear'), hbTimer = 0;
    hb.addEventListener('click', function () {
      if (!hb.dataset.armed) {
        hb.dataset.armed = '1'; hb.textContent = 'Click again to delete every chat';
        hbTimer = setTimeout(function () { delete hb.dataset.armed; hb.textContent = 'Delete the chat history'; }, 3500); return;
      }
      clearTimeout(hbTimer); delete hb.dataset.armed; hb.textContent = 'Delete the chat history';
      api('/api/memory/history/clear', {}).then(function (r) { renderRecall(r); clear($('mem-results')); }).catch(function (e) { $('mem-stats').textContent = e.message; });
    });
  }
  function addMemory() {
    var text = memInput.value.trim(); if (!text) return;
    api('/api/memory', { text: text }).then(function (r) { memInput.value = ''; renderMemory(r.items); memNote.textContent = r.added ? memNoteDefault : 'I already had that one.'; })
      .catch(function (e) { memNote.textContent = e.message; });
  }
  $('memory-add').addEventListener('click', addMemory);
  memInput.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); addMemory(); } });
  var clearBtn = $('memory-clear'), clearTimer = 0;
  clearBtn.addEventListener('click', function () {
    if (!clearBtn.dataset.armed) {
      clearBtn.dataset.armed = '1'; clearBtn.textContent = 'Click again to erase everything';
      clearTimer = setTimeout(function () { delete clearBtn.dataset.armed; clearBtn.textContent = 'Clear all memories'; }, 3500); return;
    }
    clearTimeout(clearTimer); delete clearBtn.dataset.armed; clearBtn.textContent = 'Clear all memories';
    api('/api/memory/clear', {}).then(function (r) { renderMemory(r.items); });
  });

  /* ================= timers and reminders ================= */
  var timerList = $('timer-list'), chip = $('timer-chip'), chipText = $('timer-chip-text'), alertsBox = $('alerts');
  var items = [], offset = 0, shown = {}, ctx = null, beepLoop = 0, beepCount = 0, flashLoop = 0, baseTitle = document.title;
  function nowSec() { return Date.now() / 1000 + offset; }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function fmtRemaining(s) {
    s = Math.max(0, Math.ceil(s)); var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    return h ? h + ':' + pad(m) + ':' + pad(sec) : m + ':' + pad(sec);
  }
  function fmtDur(s) {
    s = Math.round(s); var parts = [], units = [['hour', 3600], ['minute', 60], ['second', 1]];
    units.forEach(function (u) { if (s >= u[1]) { var n = Math.floor(s / u[1]); s -= n * u[1]; parts.push(n + ' ' + u[0] + (n === 1 ? '' : 's')); } });
    return parts.slice(0, 2).join(' and ') || '0 seconds';
  }
  function fmtClock(ts) {
    var d = new Date(ts * 1000), same = d.toDateString() === new Date().toDateString();
    return (same ? '' : d.toLocaleDateString([], { weekday: 'short' }) + ' ') + d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  }
  function labelFor(i) { return i.text || (i.seconds ? fmtDur(i.seconds) + ' timer' : 'Timer'); }
  function setItems(list, serverNow) { items = list.slice().sort(function (a, b) { return a.due - b.due; }); if (serverNow) offset = serverNow - Date.now() / 1000; renderTimers(); }
  function refreshTimers() { return api('/api/reminders').then(function (r) { setItems(r.items, r.now); }).catch(function () {}); }
  function renderTimers() {
    clear(timerList);
    if (!items.length) timerList.appendChild(el('li', 'tool-empty', 'No active timers or reminders.'));
    items.forEach(function (i) {
      var li = el('li', 'tool-item'); li.dataset.id = i.id;
      var kind = el('span', 'tool-kind', i.kind === 'timer' ? '⏱' : '⏰'), text = el('span', 'tool-text', labelFor(i)), time = el('span', 'tool-time');
      time.dataset.due = i.due; time.dataset.kind = i.kind;
      var cancel = el('button', 'tool-del', '×'); cancel.type = 'button'; cancel.setAttribute('aria-label', 'Cancel ' + labelFor(i)); cancel.title = 'Cancel';
      cancel.addEventListener('click', function () { api('/api/reminders/cancel', { id: i.id }).then(function (r) { setItems(r.items, r.now); }); });
      li.append(kind, text, time, cancel); timerList.appendChild(li);
    });
    tick();
  }
  function tick() {
    var now = nowSec();
    items = items.filter(function (i) { return i.due > now - 2; });
    timerList.querySelectorAll('.tool-time').forEach(function (t) {
      var due = parseFloat(t.dataset.due), left = due - now;
      t.textContent = left < 3600 || t.dataset.kind === 'timer' ? fmtRemaining(left) : fmtClock(due);
    });
    if (items.length) {
      var next = items[0], left = next.due - now;
      chip.classList.remove('hidden');
      chipText.textContent = left < 3600 || next.kind === 'timer' ? fmtRemaining(left) : fmtClock(next.due);
      chip.firstChild.textContent = (next.kind === 'timer' ? '⏱ ' : '⏰ ');
      chip.title = labelFor(next) + (items.length > 1 ? ' (+' + (items.length - 1) + ' more)' : '');
    } else chip.classList.add('hidden');
  }
  setInterval(tick, 1000);
  chip.addEventListener('click', function (e) { e.stopPropagation(); window.JarvisUI.openPane('timers'); });
  function startTimer(minutes, label) {
    var seconds = Math.round(minutes * 60);
    if (!(seconds >= 1)) return;
    api('/api/reminders', { kind: 'timer', seconds: seconds, text: label || '' }).then(function (r) { setItems(r.items, r.now); $('timer-label').value = ''; })
      .catch(function (e) { $('timer-note').textContent = e.message; });
  }
  document.querySelectorAll('.quick-timers button').forEach(function (b) { b.addEventListener('click', function () { startTimer(parseFloat(b.dataset.min), ''); }); });
  $('timer-start').addEventListener('click', function () { startTimer(parseFloat($('timer-min').value), $('timer-label').value.trim()); });

  /* ----- alerts: card + sound + notification + title flash ----- */
  function audio() { try { ctx = ctx || new (window.AudioContext || window.webkitAudioContext)(); if (ctx.state === 'suspended') ctx.resume(); } catch (e) {} return ctx; }
  ['pointerdown', 'keydown'].forEach(function (t) { document.addEventListener(t, function () { audio(); }, { once: true, capture: true }); });
  function beepOnce() {
    var c = audio(); if (!c) return;
    for (var k = 0; k < 3; k++) {
      var o = c.createOscillator(), g = c.createGain(), t0 = c.currentTime + k * 0.28;
      o.type = 'sine'; o.frequency.value = 880; g.gain.setValueAtTime(0.0001, t0); g.gain.exponentialRampToValueAtTime(0.25, t0 + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.2);
      o.connect(g); g.connect(c.destination); o.start(t0); o.stop(t0 + 0.22);
    }
  }
  function startAlarmEffects(text) {
    if (!beepLoop) { beepCount = 0; beepOnce(); beepLoop = setInterval(function () { if (++beepCount > 10) stopBeeping(); else beepOnce(); }, 3500); }
    if (!flashLoop) { var on = false; flashLoop = setInterval(function () { on = !on; document.title = on ? '⏰ ' + text.slice(0, 40) : baseTitle; }, 900); }
  }
  function stopBeeping() { clearInterval(beepLoop); beepLoop = 0; }
  function stopEffectsIfIdle() {
    if (alertsBox.children.length) return;
    stopBeeping(); clearInterval(flashLoop); flashLoop = 0; document.title = baseTitle;
  }
  function alertMessage(ev) {
    var lead = ev.missed ? 'While Jarvis was closed, ' : '';
    if (ev.kind === 'timer') return lead + 'your ' + (ev.seconds ? fmtDur(ev.seconds) + ' ' : '') + 'timer' + (ev.text ? ' “' + ev.text + '”' : '') + ' is up, ' + (window.JARVIS_ADDRESS || 'sir') + '.';
    return (ev.missed ? 'Missed reminder, ' + (window.JARVIS_ADDRESS || 'sir') + ' (' + fmtClock(ev.due) + '): ' : 'Reminder, ' + (window.JARVIS_ADDRESS || 'sir') + ': ') + ev.text + (/[.!?]$/.test(ev.text) ? '' : '.');
  }
  function dismissAlert(card, ev) {
    api('/api/reminders/ack', { id: ev.id }).catch(function () {}); card.remove(); stopEffectsIfIdle();
  }
  function showAlert(ev) {
    if (shown[ev.id]) return; shown[ev.id] = true;
    var msg = alertMessage(ev), card = el('div', 'alert-card'); card.dataset.id = ev.id;
    var head = el('div', 'alert-head', ev.kind === 'timer' ? '⏱ Timer' : '⏰ Reminder'), body = el('div', 'alert-body', msg), row = el('div', 'alert-actions');
    var ok = el('button', 'approve', 'Dismiss'), snooze = el('button', 'dismiss', 'Snooze 5 min'); ok.type = snooze.type = 'button';
    ok.addEventListener('click', function () { dismissAlert(card, ev); });
    snooze.addEventListener('click', function () {
      api('/api/reminders/snooze', { id: ev.id, kind: ev.kind, text: ev.text, minutes: 5 }).then(function (r) { setItems(r.items, r.now); });
      card.remove(); stopEffectsIfIdle();
    });
    row.append(ok, snooze); card.append(head, body, row); alertsBox.appendChild(card); ok.focus({ preventScroll: true });
    startAlarmEffects(msg);
    if ('Notification' in window && Notification.permission === 'granted') {
      try { var n = new Notification('Jarvis', { body: msg, tag: ev.id, requireInteraction: true }); n.onclick = function () { window.focus(); n.close(); }; } catch (e) {}
    }
    if (typeof addMessage === 'function') addMessage('assistant', msg);
    window.dispatchEvent(new CustomEvent('jarvis:reply', { detail: { text: msg, streamed: false } }));
    refreshTimers();
  }
  /* ----- proactive Jarvis: things it says without being asked ----- */
  var proShown = {};
  function showProactive(ev) {
    if (!ev.id || proShown[ev.id] || typeof ev.text !== 'string') return; proShown[ev.id] = true;
    var text = (ev.missed ? 'While this window was closed: ' : '') + ev.text;
    if (ev.chat !== false && typeof addMessage === 'function') {
      var row = addMessage('assistant', text); row.classList.add('proactive');
      try { if (Array.isArray(history)) { history.push({ role: 'assistant', content: text }); saveHistory(); } } catch (e) {}
      var bar = el('div', 'reply-tools proactive-bar'); bar.appendChild(el('span', 'proactive-label', ev.urgent ? 'JARVIS · URGENT' : 'JARVIS SPOKE FIRST'));
      var quiet = el('button', 'reply-tool', 'Not now'); quiet.type = 'button'; quiet.title = 'Hold anything that is not urgent for a while';
      quiet.addEventListener('click', function () {
        quiet.disabled = true;
        api('/api/proactive/mute', {}).then(function (r) { quiet.textContent = 'Quiet until ' + fmtClock(r.muted_until); }).catch(function () { quiet.disabled = false; });
      });
      bar.appendChild(quiet); row.after(bar);
      if (ev.download && typeof window.addDownloadCard === 'function') window.addDownloadCard(ev.download, bar);
      if (ev.action && typeof showAction === 'function') showAction(ev.action);
    }
    if (ev.speak !== false && !ev.missed) window.dispatchEvent(new CustomEvent('jarvis:reply', { detail: { text: text, streamed: false } }));
  }
  var source = null;
  function connect() {
    if (!window.EventSource) return;
    source = new EventSource('/api/events');
    source.onmessage = function (e) { try { var ev = JSON.parse(e.data); if (ev.type === 'reminder') showAlert(ev); else if (ev.type === 'proactive') showProactive(ev); else if (ev.type === 'call') window.dispatchEvent(new CustomEvent('jarvis:call', { detail: ev })); else if (ev.type === 'update') window.dispatchEvent(new CustomEvent('jarvis:update', { detail: ev })); } catch (err) {} };
  }
  connect();

  /* ----- training log: thumbs under answers, and the switch in Settings > AI ----- */
  window.addEventListener('jarvis:exchange', function (e) {
    var row = e.detail && e.detail.row, id = e.detail && e.detail.id; if (!row || !id) return;
    var bar = el('div', 'reply-tools'), current = 'none';
    function button(rating, label, title) {
      var b = el('button', 'reply-tool', label); b.type = 'button'; b.title = title; b.setAttribute('aria-pressed', 'false');
      b.addEventListener('click', function () {
        var next = current === rating ? 'none' : rating;
        api('/api/feedback', { id: id, rating: next }).then(function () {
          current = next; Array.prototype.forEach.call(bar.children, function (c) { c.setAttribute('aria-pressed', String(c === b && next !== 'none')); });
        }).catch(function () {});
      });
      return b;
    }
    bar.append(button('up', '👍', 'A good answer: keep it as a training example'), button('down', '👎', 'A poor answer: leave it out of training'));
    var after = row; while (after.nextElementSibling && after.nextElementSibling.classList.contains('doc-sources')) after = after.nextElementSibling;
    after.after(bar);
  });
  var trainBox = $('train-on');
  function showTraining(t) {
    trainBox.checked = t.enabled;
    $('train-note').textContent = t.exchanges + ' exchange' + (t.exchanges === 1 ? '' : 's') + ' saved (' + t.up + ' marked good, ' + t.down + ' marked poor), in ' + t.folder + '. They stay on this PC.';
  }
  if (trainBox) {
    trainBox.addEventListener('change', function () { api('/api/training', { enabled: trainBox.checked }).then(showTraining).catch(function () {}); });
    window.addEventListener('jarvis:pane', function (e) { if (paneHas(e.detail.pane, 'train-on')) api('/api/training').then(showTraining).catch(function () {}); });
    api('/api/training').then(showTraining).catch(function () {});
  }

  /* ----- desktop notifications ----- */
  var notifyBtn = $('notify-enable');
  function syncNotify() {
    if (!('Notification' in window)) { notifyBtn.disabled = true; notifyBtn.textContent = 'Notifications are not supported here'; return; }
    var p = Notification.permission;
    notifyBtn.disabled = p !== 'default';
    notifyBtn.textContent = p === 'granted' ? '🔔 Desktop notifications are on' : p === 'denied' ? '🔕 Blocked in browser settings' : '🔔 Enable desktop notifications';
  }
  notifyBtn.addEventListener('click', function () { Notification.requestPermission().then(syncNotify); });
  $('composer').addEventListener('submit', function () {
    var box = $('message');
    if ('Notification' in window && Notification.permission === 'default' && /\b(remind|timer|alarm)\b/i.test(box.value)) Notification.requestPermission().then(syncNotify);
  }, true);
  syncNotify();

  /* ----- keep lists fresh ----- */
  window.addEventListener('jarvis:pane', function (e) { if (paneHas(e.detail.pane, 'memory-list')) refreshMemory(); if (paneHas(e.detail.pane, 'timer-list')) { refreshTimers(); syncNotify(); } });
  window.addEventListener('jarvis:reply', function () { setTimeout(refreshTimers, 150); setTimeout(refreshMemory, 150); });
  refreshTimers(); refreshMemory();
  /* ================= startup briefing ================= */
  var briefKeys = { mode: 'jarvis-brief-mode', weather: 'jarvis-brief-weather', reminders: 'jarvis-brief-reminders', system: 'jarvis-brief-system', seen: 'jarvis-brief-seen' };
  function briefFlag(k) { return get(briefKeys[k]) !== '0'; }
  var briefMode = $('brief-mode'), briefNote = $('brief-note');
  briefMode.value = get(briefKeys.mode) || 'startup';
  briefMode.addEventListener('change', function () { set(briefKeys.mode, briefMode.value); });
  ['weather', 'reminders', 'system'].forEach(function (k) {
    var box = $('brief-' + k); box.checked = briefFlag(k);
    box.addEventListener('change', function () { set(briefKeys[k], box.checked ? '1' : '0'); });
  });
  function placeLabel(l) { return [l.name, l.region, l.country].filter(Boolean).join(', '); }
  function showPlace() {
    api('/api/location').then(function (d) { if (!d.location) return; $('brief-place').value = d.location.name; $('brief-place').title = placeLabel(d.location); }).catch(function () {});
  }
  function findPlace() {
    var name = $('brief-place').value.trim(); if (!name) return;
    briefNote.textContent = 'Looking for “' + name + '”…';
    api('/api/location', { name: name }).then(function (d) {
      $('brief-place').value = d.location.name; briefNote.textContent = 'Weather location set to ' + placeLabel(d.location) + '.';
    }).catch(function (e) { briefNote.textContent = e.message; });
  }
  $('brief-find').addEventListener('click', findPlace);
  $('brief-place').addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); findPlace(); } });
  function runBriefing() {
    var q = '?weather=' + (briefFlag('weather') ? 1 : 0) + '&reminders=' + (briefFlag('reminders') ? 1 : 0) + '&system=' + (briefFlag('system') ? 1 : 0);
    return api('/api/briefing' + q).then(function (d) {
      if (!d || !d.text || typeof window.addMessage !== 'function') return;
      window.addMessage('assistant', d.text);
      window.dispatchEvent(new CustomEvent('jarvis:reply', { detail: { text: d.text, streamed: false, cancelled: false, language: d.language || null } }));
    }).catch(function () {});
  }
  $('brief-now').addEventListener('click', function () {
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    runBriefing();
  });
  function whenBootDone(fn) {
    var tries = 0, timer = setInterval(function () {
      tries++;
      if (!document.documentElement.hasAttribute('data-boot') || tries > 60) { clearInterval(timer); setTimeout(fn, 400); }
    }, 300);
  }
  (function maybeStartupBriefing() {
    var mode = get(briefKeys.mode) || 'startup'; if (mode === 'off') return;
    var key = mode + ':' + (mode === 'daily' ? new Date().toDateString() : (window.__bootId || 'x'));
    if (get(briefKeys.seen) === key) return;
    set(briefKeys.seen, key);
    whenBootDone(runBriefing);
  })();
  showPlace();
  /* ================= routines ================= */
  var routines = [], draft = [], editingId = null, rList = $('routine-list'), rSteps = $('routine-steps'), rNote = $('routine-note');
  var STEP_HINTS = { open_app: ['App name, e.g. Notepad', ''], open_url: ['https://…', ''], open_folder: ['Downloads, or a full path like C:\\Users\\Me\\Work', ''], show_desktop: ['', ''], close_app: ['Program name, e.g. chrome', ''], command: ['e.g. set an alarm for 7am', ''],
    say: ['What Jarvis says', ''], volume_down: ['Steps (each is about 2%)', '5'], volume_up: ['Steps (each is about 2%)', '5'], wait: ['Seconds (1–30)', '2'], briefing: ['', ''], run_command: ['PowerShell command', ''] };
  function describeStep(s) {
    switch (s.type) {
      case 'open_app': return 'Open ' + s.name; case 'open_url': return 'Open ' + s.url; case 'open_folder': return 'Open folder ' + s.path; case 'show_desktop': return 'Show the desktop'; case 'close_app': return 'Close ' + s.name;
      case 'command': return 'Tell Jarvis: “' + s.text + '”'; case 'say': return 'Say: “' + s.text + '”';
      case 'volume': return 'Volume ' + s.direction + ' (' + s.steps + ')'; case 'wait': return 'Wait ' + s.seconds + ' s';
      case 'run_command': return 'PowerShell: ' + s.command; default: return 'Give the briefing';
    }
  }
  function renderRoutines() {
    clear(rList);
    if (!routines.length) rList.appendChild(el('li', 'tool-empty', 'No routines yet.'));
    routines.forEach(function (r) {
      var li = el('li', 'tool-item'), text = el('span', 'tool-text', r.name + ' · ' + r.steps.length + ' step' + (r.steps.length === 1 ? '' : 's') + (r.schedule ? ' · ' + schedText(r.schedule) : ''));
      var run = el('button', 'tool-act', 'Run'), edit = el('button', 'tool-act', 'Edit'), del = el('button', 'tool-del', '×');
      [run, edit, del].forEach(function (b) { b.type = 'button'; });
      del.setAttribute('aria-label', 'Delete ' + r.name); del.title = 'Delete';
      run.addEventListener('click', function () {
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        if (typeof window.sendMessage === 'function') window.sendMessage('run ' + r.name);
      });
      edit.addEventListener('click', function () {
        stopStepEdit(); editingId = r.id; draft = JSON.parse(JSON.stringify(r.steps)); $('routine-name').value = r.name; $('routine-phrases').value = (r.phrases || []).join(', ');
        $('routine-auto').checked = !!r.auto; setSched(r.schedule); renderDraft(); rNote.textContent = 'Editing “' + r.name + '”. Change the steps and press Save routine.';
      });
      del.addEventListener('click', function () { api('/api/routines/delete', { id: r.id }).then(function (d) { routines = d.items; if (editingId === r.id) resetDraft(); renderRoutines(); }).catch(function (e) { rNote.textContent = e.message; }); });
      li.append(text, run, edit, del); rList.appendChild(li);
    });
  }
  var editingStep = -1;
  function stepToForm(s) {
    var m = { open_app: ['open_app', s.name], open_url: ['open_url', s.url], open_folder: ['open_folder', s.path], close_app: ['close_app', s.name], command: ['command', s.text], say: ['say', s.text],
      wait: ['wait', String(s.seconds)], run_command: ['run_command', s.command], show_desktop: ['show_desktop', ''], briefing: ['briefing', ''] };
    if (s.type === 'volume') return [s.direction === 'up' ? 'volume_up' : 'volume_down', String(s.steps)];
    return m[s.type] || ['briefing', ''];
  }
  function stopStepEdit() { editingStep = -1; $('step-add').textContent = 'Add'; $('step-cancel').classList.add('hidden'); }
  function renderDraft() {
    clear(rSteps);
    draft.forEach(function (s, i) {
      var li = el('li', 'tool-item' + (i === editingStep ? ' editing' : '')), text = el('span', 'tool-text', (i + 1) + '. ' + describeStep(s));
      var edit = el('button', 'tool-act', 'Edit'), up = el('button', 'tool-act', '↑'), down = el('button', 'tool-act', '↓'), del = el('button', 'tool-del', '×');
      [edit, up, down, del].forEach(function (b) { b.type = 'button'; });
      edit.setAttribute('aria-label', 'Edit step ' + (i + 1)); up.setAttribute('aria-label', 'Move step ' + (i + 1) + ' up'); down.setAttribute('aria-label', 'Move step ' + (i + 1) + ' down'); del.setAttribute('aria-label', 'Remove step ' + (i + 1));
      up.disabled = i === 0; down.disabled = i === draft.length - 1;
      edit.addEventListener('click', function () {
        var f = stepToForm(s); editingStep = i; $('step-type').value = f[0]; syncStepInput(); $('step-value').value = f[1];
        $('step-add').textContent = 'Update step'; $('step-cancel').classList.remove('hidden'); renderDraft();
        rNote.textContent = 'Editing step ' + (i + 1) + '. Change it above and press Update step. The other steps stay as they are.'; $('step-value').focus();
      });
      function move(by) { var j = i + by, t = draft[i]; draft[i] = draft[j]; draft[j] = t; if (editingStep === i) editingStep = j; else if (editingStep === j) editingStep = i; renderDraft(); }
      up.addEventListener('click', function () { move(-1); }); down.addEventListener('click', function () { move(1); });
      del.addEventListener('click', function () { if (editingStep === i) stopStepEdit(); else if (editingStep > i) editingStep--; draft.splice(i, 1); renderDraft(); });
      li.append(text, edit, up, down, del); rSteps.appendChild(li);
    });
  }
  function resetDraft() { editingId = null; draft = []; stopStepEdit(); $('routine-name').value = ''; $('routine-phrases').value = ''; $('routine-auto').checked = false; setSched(null); renderDraft(); }
  var DAY_NAMES = ['Mondays', 'Tuesdays', 'Wednesdays', 'Thursdays', 'Fridays', 'Saturdays', 'Sundays'];
  function schedText(sc) {
    var d = sc.days.join(','), when = d === '0,1,2,3,4,5,6' ? 'every day' : d === '0,1,2,3,4' ? 'weekdays' : d === '5,6' ? 'weekends' : sc.days.map(function (i) { return DAY_NAMES[i]; }).join(', ');
    return when + ' at ' + sc.time;
  }
  function dayBoxes() { return Array.prototype.slice.call(document.querySelectorAll('#routine-days input')); }
  function setSched(sc) {
    $('routine-sched-on').checked = !!sc; $('routine-schedule').classList.toggle('hidden', !sc);
    dayBoxes().forEach(function (b) { b.checked = sc ? sc.days.indexOf(+b.value) >= 0 : +b.value < 5; });
    $('routine-time').value = sc ? sc.time : '07:30';
  }
  function getSched() {
    if (!$('routine-sched-on').checked) return null;
    return { days: dayBoxes().filter(function (b) { return b.checked; }).map(function (b) { return +b.value; }), time: $('routine-time').value };
  }
  $('routine-sched-on').addEventListener('change', function () { $('routine-schedule').classList.toggle('hidden', !this.checked); });
  function syncStepInput() { var h = STEP_HINTS[$('step-type').value] || ['', '']; $('step-value').placeholder = h[0]; $('step-value').value = h[1]; $('step-value').disabled = $('step-type').value === 'briefing' || $('step-type').value === 'show_desktop'; }
  $('step-type').addEventListener('change', syncStepInput); syncStepInput();
  function addStep() {
    var type = $('step-type').value, v = $('step-value').value.trim(), s;
    if (type !== 'briefing' && type !== 'show_desktop' && !v) { rNote.textContent = 'Type the detail for that step first.'; return; }
    if (type === 'open_app') s = { type: type, name: v }; else if (type === 'open_url') s = { type: type, url: v }; else if (type === 'open_folder') s = { type: type, path: v }; else if (type === 'show_desktop') s = { type: type }; else if (type === 'close_app') s = { type: type, name: v };
    else if (type === 'command' || type === 'say') s = { type: type, text: v }; else if (type === 'volume_down' || type === 'volume_up') s = { type: 'volume', direction: type === 'volume_up' ? 'up' : 'down', steps: parseInt(v, 10) || 5 };
    else if (type === 'wait') s = { type: type, seconds: parseInt(v, 10) || 2 }; else if (type === 'run_command') s = { type: type, command: v }; else s = { type: 'briefing' };
    if (editingStep >= 0 && editingStep < draft.length) { draft[editingStep] = s; stopStepEdit(); renderDraft(); rNote.textContent = 'Step updated. Press Save routine to keep the change.'; syncStepInput(); return; }
    draft.push(s); renderDraft(); rNote.textContent = 'Step added. Add more, then press Save routine.'; syncStepInput();
  }
  $('step-cancel').addEventListener('click', function () { stopStepEdit(); renderDraft(); syncStepInput(); rNote.textContent = 'Step edit cancelled.'; });
  $('step-add').addEventListener('click', addStep);
  $('step-value').addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); addStep(); } });
  $('routine-save').addEventListener('click', function () {
    var risky = draft.some(function (s) { return s.type === 'close_app' || s.type === 'run_command'; });
    if ($('routine-auto').checked && risky && !window.confirm('This routine will close apps or run PowerShell commands as soon as you start it, without asking. Save it that way?')) return;
    api('/api/routines', { id: editingId, name: $('routine-name').value, phrases: $('routine-phrases').value, steps: draft, auto: $('routine-auto').checked, schedule: getSched() }).then(function (d) {
      routines = d.items; var n = $('routine-name').value.trim(); resetDraft(); renderRoutines(); rNote.textContent = 'Saved “' + n + '”. Say its name, or press Run.';
    }).catch(function (e) { rNote.textContent = e.message; });
  });
  api('/api/routines').then(function (d) { routines = d.items; renderRoutines(); }).catch(function () {}); setSched(null); renderDraft();
  window.addEventListener('jarvis:reply', function (e) { if (e.detail && /routine/i.test(e.detail.text || '')) api('/api/routines').then(function (d) { routines = d.items; renderRoutines(); }).catch(function () {}); });
})();

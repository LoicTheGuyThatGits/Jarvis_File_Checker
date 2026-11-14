/* Wake word: settings, the status chip in the top bar, and the list of what Jarvis heard. The listening itself runs in the Jarvis program. */
(function () {
  'use strict';
  function $(id) { return document.getElementById(id); }
  if (!$('ww-enabled')) return;
  var busy = false;
  function api(body) {
    var opts = body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined;
    return fetch('/api/voice', opts).then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || 'Request failed'); return d; }); });
  }
  var LABEL = { starting: 'Starting…', listening: 'Listening for “Hey Jarvis”.', heard: 'Hearing you…', awake: 'Yes? I am listening.', thinking: 'Thinking…', speaking: 'Speaking…', off: 'Off.', error: '' };
  var CHIP = { starting: 'STARTING', listening: 'LISTENING', heard: 'HEARING', awake: 'AWAKE', thinking: 'THINKING', speaking: 'SPEAKING', error: 'MIC ERROR' };
  function show(d) {
    $('ww-enabled').checked = d.enabled;
    $('ww-options').classList.toggle('hidden', !d.enabled);
    var chip = $('wake-chip');
    chip.classList.toggle('hidden', !d.enabled);
    chip.classList.toggle('awake', d.state === 'awake' || d.state === 'heard' || d.state === 'thinking' || d.state === 'speaking');
    chip.classList.toggle('bad', d.state === 'error');
    $('wake-chip-text').textContent = CHIP[d.state] || 'LISTENING';
    $('ww-status').textContent = !d.enabled ? 'Off. Jarvis does not listen to the microphone.' : d.state === 'error' ? (d.error || 'There is a problem with the microphone.') : (LABEL[d.state] || '');
    if (document.activeElement !== $('ww-sens')) $('ww-sens').value = d.sensitivity;
    $('ww-speak').checked = d.speak; $('ww-follow').checked = d.followup;
    var sel = $('ww-device');
    if (document.activeElement !== sel) {
      var have = Array.prototype.map.call(sel.options, function (o) { return o.value; }).join('|'), want = [''].concat(d.microphones || []);
      if (d.device && want.indexOf(d.device) < 0) want.push(d.device);
      if (have !== want.join('|')) {
        sel.textContent = '';
        want.forEach(function (n) { var o = document.createElement('option'); o.value = n; o.textContent = n || 'Default microphone'; sel.appendChild(o); });
      }
      sel.value = d.device || '';
    }
    var log = $('ww-log'); log.textContent = '';
    (d.events || []).slice().reverse().forEach(function (e) {
      var li = document.createElement('li'); li.className = 'tool-item';
      var t = document.createElement('span'); t.className = 'tool-text'; t.textContent = e.time + '  “' + e.heard + '” → ' + e.reply.slice(0, 140);
      li.appendChild(t); log.appendChild(li);
    });
    if (!(d.events || []).length) { var li = document.createElement('li'); li.className = 'tool-item'; li.textContent = 'Nothing yet.'; log.appendChild(li); }
  }
  function fail(e) { $('ww-status').textContent = e.message; }
  function refresh() { if (!busy) api().then(show).catch(function () {}); }
  function send(body) { busy = true; return api(body).then(show).catch(fail).then(function () { busy = false; }); }
  $('ww-enabled').addEventListener('change', function () { send({ enabled: $('ww-enabled').checked }); });
  $('ww-sens').addEventListener('change', function () { send({ sensitivity: $('ww-sens').value }); });
  $('ww-device').addEventListener('change', function () { send({ device: $('ww-device').value }); });
  $('ww-speak').addEventListener('change', function () { send({ speak: $('ww-speak').checked }); });
  $('ww-follow').addEventListener('change', function () { send({ followup: $('ww-follow').checked }); });
  $('wake-chip').addEventListener('click', function () { send({ enabled: false }); });
  refresh(); setInterval(refresh, 2500);
})();

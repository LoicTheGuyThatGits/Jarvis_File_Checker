/* Telegram settings: connect the bot, show the pairing code, and choose what is sent to the phone. */
(function () {
  'use strict';
  function $(id) { return document.getElementById(id); }
  if (!$('tg-status')) return;
  function api(body) {
    var opts = body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined;
    return fetch('/api/telegram', opts).then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || 'Request failed'); return d; }); });
  }
  function show(d) {
    var st = $('tg-status'), name = d.username ? '@' + d.username : 'the bot';
    $('tg-connect').classList.toggle('hidden', d.configured);
    $('tg-options').classList.toggle('hidden', !d.configured);
    $('tg-pair').classList.toggle('hidden', !(d.configured && !d.paired && d.pair_code));
    $('tg-code').textContent = d.pair_code || '';
    $('tg-unpair').classList.toggle('hidden', !d.paired);
    if (!d.configured) st.textContent = 'Not connected. Create a bot with @BotFather in Telegram and paste its token below.';
    else if (d.state === 'error') st.textContent = d.error || 'There is a problem with the connection.';
    else if (!d.paired) st.textContent = 'Connected to ' + name + '. Waiting for you to pair it.';
    else st.textContent = 'Connected to ' + name + ' and paired. Message it from your phone.';
    $('tg-mirror').checked = d.mirror_reminders; $('tg-shot').checked = d.screenshot_after; $('tg-verify').checked = d.verify_screen;
    if (document.activeElement !== $('tg-brief')) $('tg-brief').value = d.brief_time || '';
  }
  function fail(e) { $('tg-status').textContent = e.message; }
  function refresh() { api().then(show).catch(function () {}); }
  $('tg-save').addEventListener('click', function () { var t = $('tg-token').value.trim(); if (!t) return; api({ token: t }).then(function (d) { $('tg-token').value = ''; show(d); }).catch(fail); });
  $('tg-mirror').addEventListener('change', function () { api({ mirror_reminders: $('tg-mirror').checked }).then(show).catch(fail); });
  $('tg-shot').addEventListener('change', function () { api({ screenshot_after: $('tg-shot').checked }).then(show).catch(fail); });
  $('tg-verify').addEventListener('change', function () { api({ verify_screen: $('tg-verify').checked }).then(show).catch(fail); });
  $('tg-brief-save').addEventListener('click', function () { api({ brief_time: $('tg-brief').value }).then(function (d) { show(d); $('tg-status').textContent = d.brief_time ? 'Daily briefing set for ' + d.brief_time + '.' : 'Daily briefing turned off.'; }).catch(fail); });
  $('tg-unpair').addEventListener('click', function () { api({ unpair: true }).then(show).catch(fail); });
  $('tg-disconnect').addEventListener('click', function () { if (confirm('Disconnect the Telegram bot?')) api({ disconnect: true }).then(show).catch(fail); });
  refresh(); setInterval(refresh, 4000);
})();

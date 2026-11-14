/* Settings > Daily > Phone app: lets the Jarvis Android app connect to this PC over the local network. */
(function () {
  'use strict';
  function $(id) { return document.getElementById(id); }
  if (!$('phone-enabled')) return;
  function api(body) {
    var opts = body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined;
    return fetch('/api/phone', opts).then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || 'Request failed'); return d; }); });
  }
  function show(d) {
    $('phone-enabled').checked = d.enabled;
    $('phone-details').classList.toggle('hidden', !d.enabled);
    $('phone-address').textContent = (d.addresses.length ? d.addresses : ['(no network address found)']).map(function (a) { return a + ':' + d.port; }).join('   or   ');
    $('phone-code').textContent = d.code;
    $('phone-status').textContent = d.enabled === d.listening
      ? (d.enabled ? 'On. Phones on your network can connect with the pairing code.' : 'Off. Jarvis only answers on this PC.')
      : 'Saved. Restart Jarvis to ' + (d.enabled ? 'start' : 'stop') + ' listening on the network. Windows may ask to allow it through the firewall: choose private networks.';
  }
  function fail(e) { $('phone-status').textContent = e.message; }
  $('phone-enabled').addEventListener('change', function () { api({ enabled: $('phone-enabled').checked }).then(show).catch(fail); });
  $('phone-new-code').addEventListener('click', function () { api({ new_code: true }).then(show).catch(fail); });
  $('tab-timers').addEventListener('click', function () { api().then(show).catch(fail); });
  api().then(show).catch(function () {});
})();

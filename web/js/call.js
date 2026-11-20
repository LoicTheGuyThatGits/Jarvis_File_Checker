// Calls: talk with Jarvis hands-free. You call Jarvis with the ☎ Call button; Jarvis calls you (the window rings).
// The server (app/calls.py) keeps what is ringing and who answered; this page does the listening, thinking and speaking.
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var screen = $('call-screen');
  if (!screen) return;
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  var BYE = /^(?:(?:ok(?:ay)?|right|alright|well)[, ]+)?(?:(?:good ?bye|bye(?: bye)?|hang up|end (?:the )?call|that'?s (?:all|it)(?: for now)?|see you(?: later| soon)?|talk (?:to you )?later|au revoir|salut|raccroche|c'?est tout|à plus)(?:[, ]+(?:jarvis|sir|then|thanks?|thank you|merci|for now))*)[.!]*$/i;
  var st = fresh();
  function fresh() { return { call: null, incoming: false, messages: [], phase: 'idle', muted: false, startedAt: 0, timer: 0, beat: 0, rec: null, recorder: null, silent: 0, ring: null, ended: true, hangAfter: false, srBroken: false, flash: 0, title: document.title, token: 0 }; }
  function address() { return window.JARVIS_ADDRESS || 'sir'; }

  function api(body) {
    return fetch('/api/call', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || 'The call failed.'); return d; }); });
  }
  function setPhase(phase, text) { st.phase = phase; screen.dataset.phase = phase; $('call-state').textContent = text; }
  function show(incoming) {
    screen.classList.remove('hidden');
    $('call-incoming').classList.toggle('hidden', !incoming);
    $('call-active').classList.toggle('hidden', incoming);
  }
  function clock() {
    if (!st.startedAt) { $('call-timer').textContent = ''; return; }
    var s = Math.floor((Date.now() - st.startedAt) / 1000);
    $('call-timer').textContent = Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
  }

  /* ---------- the ringtone (and a blinking title while the window is in the background) ---------- */
  function ringStart() {
    ringStop();
    try {
      var ctx = new (window.AudioContext || window.webkitAudioContext)();
      var beep = function () {
        var t = ctx.currentTime;
        [0, 0.45].forEach(function (off) {
          [440, 480].forEach(function (f) {
            var o = ctx.createOscillator(), g = ctx.createGain();
            o.frequency.value = f; g.gain.setValueAtTime(0.0001, t + off);
            g.gain.exponentialRampToValueAtTime(0.07, t + off + 0.02); g.gain.setValueAtTime(0.07, t + off + 0.33);
            g.gain.exponentialRampToValueAtTime(0.0001, t + off + 0.38);
            o.connect(g); g.connect(ctx.destination); o.start(t + off); o.stop(t + off + 0.4);
          });
        });
      };
      if (ctx.state === 'suspended' && ctx.resume) ctx.resume();
      beep(); st.ring = { ctx: ctx, iv: setInterval(beep, 2600) };
    } catch (e) { st.ring = null; }
    var on = false; st.title = document.title;
    st.flash = setInterval(function () { on = !on; document.title = on ? '☎ Jarvis is calling' : st.title; }, 900);
  }
  function ringStop() {
    if (st.ring) { clearInterval(st.ring.iv); try { st.ring.ctx.close(); } catch (e) {} st.ring = null; }
    if (st.flash) { clearInterval(st.flash); st.flash = 0; document.title = st.title; }
  }

  /* ---------- starting and ending ---------- */
  function begin(call) {
    st.call = call; st.incoming = false; st.ended = false; st.messages = []; st.silent = 0; st.hangAfter = false;
    st.startedAt = Date.now(); clearInterval(st.timer); st.timer = setInterval(clock, 1000); clock();
    clearInterval(st.beat);
    st.beat = setInterval(function () { if (st.call) api({ action: 'heartbeat', id: st.call.id }).catch(function () { remoteEnded('The call ended.'); }); }, 20000);
    $('call-you').textContent = ''; $('call-jarvis').textContent = '';
    show(false);
  }
  function placeCall() {
    if (!st.ended || st.incoming) return;
    st = fresh(); st.ended = false;
    $('call-you').textContent = ''; $('call-jarvis').textContent = ''; $('call-timer').textContent = '';
    show(false); setPhase('connecting', 'Calling Jarvis…');
    api({ action: 'place' }).then(function (d) { begin(d.call); speakThenListen(d.greeting); })
      .catch(function (e) { setPhase('ended', e.message); setTimeout(close, 2500); });
  }
  function incoming(call) {
    if (!st.ended || st.incoming) return;            // already on a call: the server says it there instead
    st = fresh(); st.call = call; st.incoming = true;
    $('call-you').textContent = ''; $('call-jarvis').textContent = call.reason && call.reason !== 'Test call' ? call.reason : '';
    $('call-timer').textContent = '';
    show(true); setPhase('ringing', 'Jarvis is calling you…'); ringStart();
    try { window.focus(); } catch (e) {}
  }
  function accept() {
    if (!st.call || !st.incoming) return;
    ringStop();
    var call = st.call; setPhase('connecting', 'Connecting…');
    api({ action: 'answer', id: call.id }).then(function (d) { begin(d.call); speakThenListen(d.call.opening || ('Hello, ' + address() + '.')); })
      .catch(function (e) { setPhase('ended', e.message); setTimeout(close, 2500); });
  }
  function decline() {
    if (!st.call || !st.incoming) return;
    ringStop(); var id = st.call.id;
    api({ action: 'decline', id: id }).catch(function () {});
    setPhase('ended', 'Declined.'); setTimeout(close, 900);
  }
  function stopListening() {
    st.token++;
    if (st.rec) { var r = st.rec; st.rec = null; try { r.onend = r.onresult = r.onerror = null; r.abort(); } catch (e) {} }
    if (st.recorder) { var m = st.recorder; st.recorder = null; try { m.cancel(); } catch (e) {} }
  }
  function cleanup() {
    st.ended = true; stopListening(); ringStop();
    if (window.JarvisVoice) window.JarvisVoice.stop();
    clearInterval(st.timer); clearInterval(st.beat);
  }
  function save() {
    if (!st.messages.some(function (m) { return m.role === 'user'; }) || !window.JarvisChats) return;
    var s = Math.round((Date.now() - st.startedAt) / 1000), at = new Date(st.startedAt);
    window.JarvisChats.saveCall('☎ Call · ' + String(at.getHours()).padStart(2, '0') + ':' + String(at.getMinutes()).padStart(2, '0') + ' (' + Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0') + ')', st.messages);
  }
  function hangup() {
    if (st.ended) return;
    var id = st.call && st.call.id;
    cleanup(); save();
    if (id) api({ action: 'hangup', id: id }).catch(function () {});
    setPhase('ended', 'Call ended.'); setTimeout(close, 1200);
  }
  function remoteEnded(text) {
    if (st.ended && !st.incoming) return;
    var wasIncoming = st.incoming;
    cleanup(); if (!wasIncoming) save();
    st.incoming = false;
    setPhase('ended', text); setTimeout(close, 1800);
  }
  function close() { if (st.ended) { screen.classList.add('hidden'); st.call = null; st.incoming = false; screen.dataset.phase = 'idle'; } }

  /* ---------- talking ---------- */
  function speakThenListen(text) {
    if (st.ended) return;
    stopListening();
    if (!text) { listen(); return; }
    st.messages.push({ role: 'assistant', content: text });
    $('call-jarvis').textContent = text;
    setPhase('speaking', 'Jarvis is speaking…');
    var token = ++st.token;
    var said = window.JarvisVoice ? window.JarvisVoice.say(text) : Promise.resolve(false);
    said.then(function () {
      if (st.ended || token !== st.token) return;
      if (st.hangAfter) { hangup(); return; }
      listen();
    });
  }
  function listen() {
    if (st.ended) return;
    stopListening();
    if (st.muted) { setPhase('muted', 'Microphone muted. Press Mute again to talk.'); return; }
    setPhase('listening', 'Listening…');
    if (SR && !st.srBroken) listenSpeech(); else listenRecorder();
  }
  function noSpeech() {
    st.silent++;
    if (st.silent === 3) { speakThenListen('I am still here, ' + address() + '. Say goodbye when you are done.'); return; }
    if (st.silent >= 5) { st.hangAfter = true; speakThenListen('I will hang up now, ' + address() + '. Call me any time.'); return; }
    listen();
  }
  function listenSpeech() {
    var rec = new SR(), final = '', token = ++st.token;
    rec.lang = window.JARVIS_RECOGNITION_LANG || navigator.language || 'en-GB';
    rec.interimResults = true; rec.continuous = false;
    rec.onresult = function (e) {
      var interim = '';
      for (var i = e.resultIndex; i < e.results.length; i++) { if (e.results[i].isFinal) final += e.results[i][0].transcript; else interim += e.results[i][0].transcript; }
      $('call-you').textContent = (final + interim).trim();
    };
    rec.onerror = function (e) {
      if (token !== st.token) return;
      if (e.error === 'not-allowed' || e.error === 'service-not-allowed') { st.srBroken = !!window.MediaRecorder; if (!st.srBroken) { remoteEnded('The microphone is blocked. Allow it for Jarvis, then call again.'); } }
      else if (e.error === 'network' || e.error === 'language-not-supported') st.srBroken = !!window.MediaRecorder;
    };
    rec.onend = function () {
      if (token !== st.token || st.ended) return;
      st.rec = null;
      var text = final.trim();
      if (text) { st.silent = 0; heard(text); }
      else if (st.srBroken) listen();
      else noSpeech();
    };
    st.rec = rec;
    try { rec.start(); } catch (e) { st.srBroken = !!window.MediaRecorder; if (st.srBroken) listen(); }
  }
  // without speech recognition in this browser: record until a pause, then Jarvis transcribes it on the PC
  function listenRecorder() {
    if (!navigator.mediaDevices || !window.MediaRecorder) { remoteEnded('This browser cannot listen. Use Microsoft Edge or Chrome.'); return; }
    var token = ++st.token;
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      if (token !== st.token || st.ended) { stream.getTracks().forEach(function (t) { t.stop(); }); return; }
      var chunks = [], rec = new MediaRecorder(stream), ctx = new (window.AudioContext || window.webkitAudioContext)();
      var an = ctx.createAnalyser(); an.fftSize = 1024; ctx.createMediaStreamSource(stream).connect(an);
      var buf = new Uint8Array(an.fftSize), spoke = false, quietSince = 0, started = Date.now(), cancelled = false, loop = 0;
      function stopAll() { clearInterval(loop); try { ctx.close(); } catch (e) {} stream.getTracks().forEach(function (t) { t.stop(); }); }
      st.recorder = { cancel: function () { cancelled = true; try { rec.stop(); } catch (e) {} stopAll(); } };
      rec.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
      rec.onstop = function () {
        stopAll();
        if (cancelled || token !== st.token || st.ended) return;
        st.recorder = null;
        if (!spoke) { noSpeech(); return; }
        setPhase('thinking', 'Understanding…');
        var type = (rec.mimeType || 'audio/webm').split(';')[0], ext = type.indexOf('ogg') >= 0 ? 'ogg' : type.indexOf('mp4') >= 0 ? 'm4a' : 'webm';
        fetch('/api/transcribe?ext=' + ext, { method: 'POST', body: new Blob(chunks, { type: type }) })
          .then(function (r) { return r.json(); })
          .then(function (d) { if (token !== st.token || st.ended) return; var t = (d.text || '').trim(); if (t) { st.silent = 0; heard(t); } else noSpeech(); })
          .catch(function () { if (!st.ended) speakThenListen('Sorry, ' + address() + ', I could not hear that. Please say it again.'); });
      };
      rec.start();
      loop = setInterval(function () {
        an.getByteTimeDomainData(buf);
        var sum = 0; for (var i = 0; i < buf.length; i++) { var v = (buf[i] - 128) / 128; sum += v * v; }
        var loud = Math.sqrt(sum / buf.length) > 0.035, now = Date.now();
        if (loud) { spoke = true; quietSince = 0; } else if (spoke && !quietSince) quietSince = now;
        if ((spoke && quietSince && now - quietSince > 1100) || (!spoke && now - started > 8000) || now - started > 30000) { clearInterval(loop); try { rec.stop(); } catch (e) {} }
      }, 80);
    }).catch(function () { remoteEnded('The microphone is blocked. Allow it for Jarvis, then call again.'); });
  }
  function heard(text) {
    $('call-you').textContent = text;
    st.messages.push({ role: 'user', content: text });
    if (BYE.test(text.trim())) { st.hangAfter = true; speakThenListen('Goodbye, ' + address() + '.'); return; }
    think();
  }
  function think() {
    setPhase('thinking', 'Thinking…');
    var token = ++st.token;
    fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: st.messages.slice(-12), source: 'call', stream: false }) })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (token !== st.token || st.ended) return;
        var d = res.d || {};
        if (d.action && typeof window.showAction === 'function') { try { window.showAction(d.action); } catch (e) {} }
        speakThenListen(res.ok ? (d.reply || 'Done, ' + address() + '.') : 'Sorry, ' + address() + '. ' + (d.error || 'Something went wrong.'));
      })
      .catch(function () { if (token === st.token && !st.ended) speakThenListen('Sorry, ' + address() + ', I lost the connection for a moment. Please say that again.'); });
  }

  /* ---------- buttons ---------- */
  var button = $('call-button');
  if (button) button.addEventListener('click', placeCall);
  $('call-accept').addEventListener('click', accept);
  $('call-decline').addEventListener('click', decline);
  $('call-hangup').addEventListener('click', hangup);
  $('call-mute').addEventListener('click', function () {
    st.muted = !st.muted; $('call-mute').setAttribute('aria-pressed', String(st.muted));
    if (st.muted) { stopListening(); if (st.phase === 'listening') setPhase('muted', 'Microphone muted. Press Mute again to talk.'); }
    else if (st.phase === 'muted') listen();
  });
  $('call-skip').addEventListener('click', function () { if (st.phase === 'speaking') { if (window.JarvisVoice) window.JarvisVoice.stop(); } else if (st.phase === 'listening') {} });

  /* ---------- what the server says ---------- */
  window.addEventListener('jarvis:call', function (e) {
    var ev = e.detail || {};
    if (ev.state === 'ringing' && (ev.targets || []).indexOf('pc') >= 0) { incoming(ev); return; }
    if (!st.call || ev.id !== st.call.id) return;
    if (ev.say && !st.ended && !st.incoming) { speakThenListen(ev.say); return; }
    if (st.incoming && ev.state === 'active' && ev.device !== 'pc') { remoteEnded('Answered on the phone.'); return; }
    if (st.incoming && ev.state === 'declined' && ev.device !== 'pc') { remoteEnded('Declined on the phone.'); return; }
    if (['missed', 'cancelled', 'replaced'].indexOf(ev.state) >= 0 && st.incoming) { remoteEnded(ev.state === 'missed' ? 'Missed call.' : 'The call was cancelled.'); return; }
    if (ev.state === 'ended' && !st.ended) remoteEnded('The call ended.');
  });
  // a call that started ringing before this page opened (Jarvis opens the window to ring)
  fetch('/api/call').then(function (r) { return r.json(); }).then(function (d) {
    (d.calls || []).forEach(function (c) { if (c.state === 'ringing' && (c.targets || []).indexOf('pc') >= 0) incoming(c); });
  }).catch(function () {});
  window.JarvisCall = { place: placeCall, hangup: hangup, state: function () { return { phase: st.phase, call: st.call, messages: st.messages.slice(), ended: st.ended, incoming: st.incoming }; } };

  /* ---------- Settings > Phone & Telegram > Calls ---------- */
  if (!$('calls-on')) return;
  var boxes = { 'calls-on': 'on', 'calls-ring-pc': 'ring_pc', 'calls-ring-phone': 'ring_phone', 'calls-telegram': 'telegram_fallback' };
  var STATES = { ended: 'answered', missed: 'missed', declined: 'declined', cancelled: 'cancelled', replaced: 'replaced by a newer call' };
  function fill(d, keepStatus) {
    var s = d.settings || {};
    Object.keys(boxes).forEach(function (id) { $(id).checked = !!s[boxes[id]]; });
    $('calls-ring-seconds').value = s.ring_seconds || 40;
    if (d.phone_listening !== undefined && !keepStatus) $('calls-status').textContent = s.on ? ('Jarvis may call you. ' + (d.phone_listening ? 'The phone app is connected and can ring.' : 'The phone app is not connected right now, so only this PC rings.')) : 'Calls from Jarvis are off. You can still call Jarvis.';
    var list = $('calls-recent'); list.textContent = '';
    (d.recent || []).slice(0, 8).forEach(function (c) {
      var li = document.createElement('li'), at = new Date((c.answered || c.created) * 1000);
      var who = c.direction === 'to_jarvis' ? 'You called Jarvis' : 'Jarvis called you' + (c.reason ? ' (' + c.reason + ')' : '');
      var how = c.direction === 'to_jarvis' || c.state === 'ended' ? (c.seconds != null ? Math.floor(c.seconds / 60) + ':' + String(c.seconds % 60).padStart(2, '0') : '') : (STATES[c.state] || c.state);
      li.textContent = String(at.getHours()).padStart(2, '0') + ':' + String(at.getMinutes()).padStart(2, '0') + ' · ' + who + (how ? ' · ' + how : '') + (c.device ? ' · on the ' + (c.device === 'pc' ? 'PC' : 'phone') : '');
      list.append(li);
    });
  }
  function load(keepStatus) { fetch('/api/call').then(function (r) { return r.json(); }).then(function (d) { fill(d, keepStatus); }).catch(function () {}); }
  function saveSettings() {
    var settings = { ring_seconds: Number($('calls-ring-seconds').value) };
    Object.keys(boxes).forEach(function (id) { settings[boxes[id]] = $(id).checked; });
    api({ action: 'settings', settings: settings }).then(function () { load(); })
      .catch(function (e) { $('calls-status').textContent = e.message; load(true); });
  }
  Object.keys(boxes).forEach(function (id) { $(id).addEventListener('change', saveSettings); });
  $('calls-ring-seconds').addEventListener('change', saveSettings);
  $('calls-test').addEventListener('click', function () {
    $('calls-status').textContent = 'Ringing…';
    api({ action: 'test' }).then(function (d) { $('calls-status').textContent = d.call && d.call.state === 'ringing' ? 'Ringing now. Answer it to hear Jarvis.' : 'You are already on a call.'; })
      .catch(function (e) { $('calls-status').textContent = e.message; });
  });
  window.addEventListener('jarvis:pane', function (e) { if (e.detail && window.paneHas(e.detail.pane, 'calls-on')) load(); });
})();

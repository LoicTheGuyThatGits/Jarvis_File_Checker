/* Chat search + export/import, voice replies, and the model switcher. Independent of app.js except for the
   globals it exposes (chats, activeChat, renderChatList, chatFilter) and the jarvis:* events it fires. */
(function () {
  'use strict';
  function $(id) { return document.getElementById(id); }
  function get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  function clearChildren(n) { while (n.firstChild) n.removeChild(n.firstChild); }
  function download(filename, text, type) {
    var url = URL.createObjectURL(new Blob([text], { type: type + ';charset=utf-8' }));
    var a = document.createElement('a'); a.href = url; a.download = filename; a.addEventListener('click', function (e) { e.stopPropagation(); }); document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }
  function safeName(s) { return (s || 'chat').replace(/[^\w .-]+/g, '').trim().replace(/\s+/g, '-').slice(0, 40) || 'chat'; }

  /* ================= chat search ================= */
  var search = $('chat-search');
  search.addEventListener('input', function () { chatFilter = search.value; renderChatList(); });
  search.addEventListener('keydown', function (e) { if (e.key === 'Escape' && search.value) { search.value = ''; chatFilter = ''; renderChatList(); e.stopPropagation(); } });

  /* ================= export / import ================= */
  function chatToMarkdown(chat) {
    var out = ['# ' + (chat.title || 'Jarvis chat'), '', '_Exported from Jarvis on ' + new Date().toLocaleString() + '_', ''];
    chat.messages.forEach(function (m) { out.push('---', '', '**' + (m.role === 'user' ? 'You' : 'Jarvis') + ':**', '', m.content, ''); });
    return out.join('\n');
  }
  $('export-chat').addEventListener('click', function () {
    var chat = activeChat();
    if (!chat.messages.length) { $('chats-note').textContent = 'This chat is empty, so there is nothing to export yet.'; return; }
    download(safeName(chat.title) + '.md', chatToMarkdown(chat), 'text/markdown');
  });
  $('export-all').addEventListener('click', function () {
    var data = { app: 'jarvis', version: 1, exported: new Date().toISOString(), chats: chats };
    download('jarvis-chats-' + new Date().toISOString().slice(0, 10) + '.json', JSON.stringify(data, null, 2), 'application/json');
  });
  $('import-chats').addEventListener('click', function () { $('import-file').click(); });
  $('import-file').addEventListener('change', function () {
    var file = this.files && this.files[0], input = this; if (!file) return;
    var note = $('chats-note');
    file.text().then(function (text) {
      var data = JSON.parse(text), list = Array.isArray(data) ? data : data && data.chats;
      if (!Array.isArray(list)) throw new Error('This file does not look like a Jarvis export.');
      var known = {}; chats.forEach(function (c) { known[c.id] = true; });
      var added = 0, skipped = 0;
      list.forEach(function (c) {
        if (!c || typeof c.id !== 'string' || !Array.isArray(c.messages) || known[c.id]) { skipped++; return; }
        var messages = c.messages.filter(function (m) { return m && (m.role === 'user' || m.role === 'assistant') && typeof m.content === 'string'; })
          .slice(-200).map(function (m) { return { role: m.role, content: m.content.slice(0, 100000) }; });
        chats.push({ id: c.id, title: typeof c.title === 'string' && c.title ? c.title.slice(0, 80) : 'Imported chat', messages: messages });
        known[c.id] = true; added++;
      });
      set(chatsKey, JSON.stringify(chats)); renderChatList();
      note.textContent = 'Imported ' + added + ' chat' + (added === 1 ? '' : 's') + (skipped ? ' (' + skipped + ' already here or invalid, skipped).' : '.');
    }).catch(function (err) { note.textContent = 'Could not import: ' + err.message; }).then(function () { input.value = ''; });
  });

  /* ================= language ================= */
  var lang = { code: 'en', tag: 'en-GB', name: 'English', sample: '', list: [] };
  function recognitionTag() { return lang.code === 'en' && /^en/i.test(navigator.language || '') ? navigator.language : lang.tag; }
  function applyLanguage(code, silent) {
    var item = null; for (var i = 0; i < lang.list.length; i++) if (lang.list[i].code === code) item = lang.list[i];
    if (!item) return;
    lang.code = item.code; lang.tag = item.tag; lang.name = item.name; lang.sample = item.sample;
    var sel = $('lang-select'); if (sel) sel.value = code;
    window.JARVIS_RECOGNITION_LANG = recognitionTag();
    window.dispatchEvent(new CustomEvent('jarvis:language', { detail: { code: lang.code, tag: lang.tag, recognition: recognitionTag() } }));
    if (typeof loadVoices === 'function') { loadVoices(); }
    if (typeof syncEngineUi === 'function') syncEngineUi();
  }
  function loadLanguage() {
    fetch('/api/language').then(function (r) { return r.json(); }).then(function (d) {
      lang.list = d.languages || []; var sel = $('lang-select'); clearChildren(sel);
      lang.list.forEach(function (l) { var o = document.createElement('option'); o.value = l.code; o.textContent = l.name === l.native ? l.name : l.name + ' – ' + l.native; sel.appendChild(o); });
      applyLanguage(d.language);
    }).catch(function () {});
  }
  $('lang-select').addEventListener('change', function () {
    var code = $('lang-select').value;
    fetch('/api/language', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ language: code }) })
      .then(function (r) { return r.json(); }).then(function (d) { if (d && d.language) applyLanguage(d.language); }).catch(function () {});
  });
  window.addEventListener('jarvis:reply', function (e) { var c = e.detail && e.detail.language; if (c && c !== lang.code) applyLanguage(c); });
  function sayHello(english) { return lang.code === 'en' || !lang.sample ? english : lang.sample; }

  /* ================= voice replies ================= */
  var synth = window.speechSynthesis, supported = !!(synth && window.SpeechSynthesisUtterance);
  var voice = { on: false, uri: '', rate: 0.95, pitch: 0.9, chirp: true, engine: 'browser', cloudVoice: 'onyx', piperModel: '' };
  try { var saved = JSON.parse(get('jarvis-voice-v1') || '{}'); if (saved && typeof saved === 'object') voice = Object.assign(voice, saved); } catch (e) {}
  voice.rate = Math.min(1.4, Math.max(0.7, Number(voice.rate) || 1)); voice.pitch = Math.min(1.2, Math.max(0.6, Number(voice.pitch) || 1)); voice.chirp = voice.chirp !== false;
  if (['browser', 'cloud', 'piper'].indexOf(voice.engine) < 0) voice.engine = 'browser';
  var toggle = $('voice-toggle'), onBox = $('voice-on'), sel = $('voice-select'), rate = $('voice-rate'), pitch = $('voice-pitch');
  var spokenText = '', active = 0, voices = [];
  function saveVoice() { set('jarvis-voice-v1', JSON.stringify(voice)); }
  function syncVoiceUi() {
    toggle.setAttribute('aria-pressed', String(voice.on)); toggle.textContent = voice.on ? '♪ Voice on' : '♪ Voice off';
    onBox.checked = voice.on; $('voice-chirp').checked = voice.chirp;
    rate.value = voice.rate; pitch.value = voice.pitch;
    $('voice-rate-out').textContent = voice.rate.toFixed(2) + '×'; $('voice-pitch-out').textContent = voice.pitch.toFixed(2);
    syncEngineUi();
  }
  function syncEngineUi() {
    var e = voice.engine, engSel = $('voice-engine');
    if (engSel) engSel.value = e;
    $('field-browser-voice').classList.toggle('hidden', e !== 'browser');
    $('field-pitch').classList.toggle('hidden', e !== 'browser');
    $('field-cloud-voice').classList.toggle('hidden', e !== 'cloud');
    $('field-piper-voice').classList.toggle('hidden', e !== 'piper');
    if (e === 'browser') { if (typeof updateVoiceHint === 'function' && voices.length) updateVoiceHint(); return; }
    var note = $('voice-note');
    if (!tts.loaded) { note.textContent = 'Checking the natural voice…'; return; }
    if (e === 'cloud') note.textContent = tts.cloud
      ? 'Natural voice from your cloud AI provider (uses your API key, so speech may incur charges). Code is never read aloud.'
      : 'The cloud voice needs a cloud API key. Set OPENAI_API_KEY (or JARVIS_CLOUD_API_KEY) before starting Jarvis. Until then the browser voice is used.';
    else note.textContent = tts.piper
      ? 'Offline natural voice from Piper, running on this PC. Code is never read aloud.'
      : 'Piper is not set up yet. Put piper.exe and a voice file (.onnx and its .onnx.json) in a folder named “piper” next to server.py, then restart Jarvis. Until then the browser voice is used.';
  }
  function fillSelect(selectEl, values, current, emptyText) {
    clearChildren(selectEl);
    if (!values.length) { var o0 = document.createElement('option'); o0.textContent = emptyText; o0.value = ''; selectEl.appendChild(o0); return; }
    values.forEach(function (v) { var o = document.createElement('option'); o.value = v; o.textContent = v; if (v === current) o.selected = true; selectEl.appendChild(o); });
  }
  function loadTts() {
    fetch('/api/tts/status').then(function (r) { return r.json(); }).then(function (d) {
      tts.cloud = !!d.cloud; tts.piper = !!d.piper; tts.piperModels = d.piper_models || []; tts.cloudVoices = d.cloud_voices || ['onyx']; tts.loaded = true;
      if (!voice.piperModel || tts.piperModels.indexOf(voice.piperModel) < 0) voice.piperModel = tts.piperModels[0] || '';
      if (tts.cloudVoices.indexOf(voice.cloudVoice) < 0) voice.cloudVoice = tts.cloudVoices[0];
      fillSelect($('voice-cloud-voice'), tts.cloudVoices, voice.cloudVoice, 'No voices');
      fillSelect($('voice-piper-model'), tts.piperModels, voice.piperModel, 'No Piper voices found');
      var opts = $('voice-engine').options;
      for (var i = 0; i < opts.length; i++) {
        if (opts[i].value === 'cloud') opts[i].textContent = 'Natural voice (cloud AI)' + (tts.cloud ? '' : ' – needs API key');
        if (opts[i].value === 'piper') opts[i].textContent = 'Natural voice (offline, Piper)' + (tts.piper ? '' : ' – not set up');
      }
      syncEngineUi();
    }).catch(function () { tts.loaded = true; syncEngineUi(); });
  }
  function langMatch(v) { return (v.lang || '').toLowerCase().replace('_', '-').split('-')[0] === (lang.tag || 'en').toLowerCase().split('-')[0]; }
  function score(v) {
    var n = v.name || '', s = 0;
    if (lang.code !== 'en') return (langMatch(v) ? 10 : -10) + (/natural|neural/i.test(n) ? 3 : /online/i.test(n) ? 1 : 0) + (v.lang === lang.tag ? 2 : 0);
    if (/female|sonia|libby|maisie|hazel|susan|zira|aria|jenny|emma|amy|olivia|serena|kate|fiona|karen|moira|samantha|victoria/i.test(n)) s -= 20;
    s += v.lang === 'en-GB' ? 4 : /^en[-_]/i.test(v.lang) ? 1 : -3;
    if (/ryan/i.test(n)) s += 6; else if (/george|daniel|oliver|arthur|thomas|james|\bmale\b/i.test(n)) s += 3;
    if (/natural|neural/i.test(n)) s += 2; else if (/online/i.test(n)) s += 1;
    return s;
  }
  function updateVoiceHint() {
    var v = chosenVoice(), note = $('voice-note');
    if (!v && lang.code !== 'en') { note.textContent = 'No ' + lang.name + ' voice is installed in this browser, so the default voice is used. In Windows you can add one under Settings > Time & language > Speech > Add voices, or choose a natural voice engine above.'; return; }
    if (!v) { note.textContent = 'No voices were found in this browser.'; return; }
    if (lang.code !== 'en') { note.textContent = 'Using “' + v.name + '” for ' + lang.name + '. Code is never read aloud.'; return; }
    var good = v.lang === 'en-GB' && score(v) >= 7;
    note.textContent = 'Using “' + v.name + '”. ' + (good ? 'That is a good match for Jarvis. ' :
      'For the most Jarvis-like sound, use Microsoft Edge and pick “Microsoft Ryan Online (Natural) – English (United Kingdom)”, or add a British English voice in Windows Settings > Time & language > Speech. ') +
      'Code is never read aloud, and the reactor pulses while Jarvis speaks.';
  }
  function chosenVoice() {
    for (var i = 0; i < voices.length; i++) if (voices[i].voiceURI === voice.uri && (lang.code === 'en' || langMatch(voices[i]))) return voices[i];
    var best = voices.slice().sort(function (a, b) { return score(b) - score(a); })[0] || null;
    return best && lang.code !== 'en' && !langMatch(best) ? null : best;
  }
  function loadVoices() {
    if (!supported) return;
    voices = synth.getVoices() || [];
    clearChildren(sel);
    if (!voices.length) { var o = document.createElement('option'); o.textContent = 'No voices found'; sel.appendChild(o); return; }
    var sorted = voices.slice().sort(function (a, b) { return (langMatch(b) - langMatch(a)) || a.name.localeCompare(b.name); });
    var pick = chosenVoice();
    sorted.forEach(function (v) {
      var o = document.createElement('option'); o.value = v.voiceURI; o.textContent = v.name + ' (' + v.lang + ')';
      if (pick && v.voiceURI === pick.voiceURI) o.selected = true; sel.appendChild(o);
    });
    updateVoiceHint();
  }
  function setSpeaking(delta) { active = Math.max(0, active + delta); if (active) document.documentElement.setAttribute('data-speaking', ''); else document.documentElement.removeAttribute('data-speaking'); }
  var chirpCtx = null, pending = [], burstAt = 0;
  function chirp() {
    try {
      chirpCtx = chirpCtx || new (window.AudioContext || window.webkitAudioContext)();
      if (chirpCtx.state === 'suspended') chirpCtx.resume();
      var t = chirpCtx.currentTime;
      [[620, 0], [930, 0.075]].forEach(function (n) {
        var o = chirpCtx.createOscillator(), g = chirpCtx.createGain(), at = t + n[1];
        o.type = 'sine'; o.frequency.value = n[0]; g.gain.setValueAtTime(0.0001, at);
        g.gain.exponentialRampToValueAtTime(0.07, at + 0.012); g.gain.exponentialRampToValueAtTime(0.0001, at + 0.07);
        o.connect(g); g.connect(chirpCtx.destination); o.start(at); o.stop(at + 0.08);
      });
    } catch (e) {}
  }
  /* ---- natural voices: audio comes from the Jarvis server (cloud AI or offline Piper), sentence by sentence ---- */
  var tts = { cloud: false, piper: false, piperModels: [], cloudVoices: ['onyx'], loaded: false };
  var queue = [], playing = false, player = new Audio(), engineNote = '';
  function remoteReady() { return (voice.engine === 'cloud' && tts.cloud) || (voice.engine === 'piper' && tts.piper); }
  function useRemote() { return voice.engine !== 'browser' && remoteReady(); }
  function canSpeak() { return useRemote() || supported; }
  function piperFor() {
    if (lang.code === 'en') return voice.piperModel;
    var re = new RegExp('^' + lang.code + '[_-]', 'i');
    for (var i = 0; i < tts.piperModels.length; i++) if (re.test(tts.piperModels[i])) return tts.piperModels[i];
    return voice.piperModel;
  }
  function speakRemote(text) {
    var item = { text: text, blob: null, failed: false, ctrl: window.AbortController ? new AbortController() : null };
    var body = { engine: voice.engine, text: text, speed: voice.rate, lang: lang.code, voice: voice.engine === 'cloud' ? voice.cloudVoice : piperFor() };
    if (active === 0 && voice.chirp) chirp();
    setSpeaking(1);
    item.promise = fetch('/api/tts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal: item.ctrl ? item.ctrl.signal : undefined })
      .then(function (r) { if (r.ok) return r.blob(); return r.json().then(function (d) { throw new Error(d.error || 'Speech failed'); }); })
      .then(function (b) { item.blob = b; })
      .catch(function (e) { item.failed = true; item.err = e; });
    queue.push(item); pump();
  }
  function pump() {
    if (playing || !queue.length) return;
    var item = queue[0]; playing = true;
    item.promise.then(function () {
      if (queue[0] !== item) return;                       /* stopped while waiting */
      queue.shift();
      function next() { playing = false; setSpeaking(-1); pump(); }
      if (item.failed) {
        if (!item.ctrl || !item.ctrl.signal.aborted) {
          var note = $('voice-note'); if (note) note.textContent = 'The natural voice failed (' + (item.err && item.err.message || 'unknown error') + '), so the browser voice is used for now.';
          if (supported) speakBrowser(item.text);
        }
        next(); return;
      }
      var url = URL.createObjectURL(item.blob);
      var finish = function () { player.onended = player.onerror = null; URL.revokeObjectURL(url); next(); };
      player.onended = player.onerror = finish; player.src = url;
      var p = player.play(); if (p && p.catch) p.catch(finish);
    });
  }
  function stopRemote() {
    queue.forEach(function (i) { if (i.ctrl) { try { i.ctrl.abort(); } catch (e) {} } });
    queue = []; playing = false; player.onended = player.onerror = null;
    try { player.pause(); player.removeAttribute('src'); } catch (e) {}
  }
  function speakChunk(text) {
    if (!text) return;
    if (useRemote()) speakRemote(text); else speakBrowser(text);
  }
  function speakBrowser(text) {
    if (!supported || !text) return;
    var u = new SpeechSynthesisUtterance(text), v = chosenVoice(), now = Date.now();
    if (v) { u.voice = v; u.lang = v.lang; } else { u.lang = lang.tag; }
    u.rate = voice.rate; u.pitch = voice.pitch;
    var done = false; function end() { if (!done) { done = true; setSpeaking(-1); } }
    u.onstart = function () {}; u.onend = end; u.onerror = end;
    if (active === 0 && voice.chirp) { chirp(); burstAt = now + 190; }   /* a soft chirp, then the voice */
    setSpeaking(1);
    var delay = Math.max(0, burstAt - now);
    if (delay > 0) { var id = setTimeout(function () { pending = pending.filter(function (x) { return x !== id; }); synth.speak(u); }, delay); pending.push(id); }
    else synth.speak(u);
  }
  function stopSpeech() {
    spokenText = ''; pending.forEach(clearTimeout); pending = []; burstAt = 0;
    stopRemote(); active = 0; document.documentElement.removeAttribute('data-speaking');
    if (supported) synth.cancel();
  }
  function cleanForSpeech(raw) {
    var t = String(raw);
    t = t.replace(/```[\s\S]*?```/g, ' ');
    var open = t.indexOf('```'); if (open >= 0) t = t.slice(0, open);
    t = t.replace(/`([^`\n]*)`/g, '$1').replace(/`/g, '');
    t = t.replace(/\s*\[\d{1,2}(?:\s*,\s*\d{1,2})*\]/g, '');   // source marks like [1] or [2, 3] are for reading, not speaking
    t = t.replace(/!\[[^\]]*\]\([^)]*\)/g, '').replace(/\[([^\]]+)\]\([^)]*\)/g, '$1').replace(/https?:\/\/\S+/g, 'link');
    t = t.replace(/^\s{0,3}#{1,6}\s*/gm, '').replace(/^\s*[-*•]\s+/gm, '').replace(/^\s*\d+[.)]\s+/gm, '');
    t = t.replace(/(\*\*|__|\*)/g, '').replace(/[ \t]+/g, ' ').replace(/\n{2,}/g, '\n');
    t = t.replace(/\s[—–]\s?|[—–]/g, ', ').replace(/&/g, ' and ').replace(/\|/g, ', ').replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\uFE0F]/gu, '').replace(/(\d)\s?°C/g, '$1 degrees Celsius').replace(/(\d)\s?°F/g, '$1 degrees Fahrenheit').replace(/(\d)\s?%/g, '$1 percent').replace(/ {2,}/g, ' ');
    return t;
  }
  function nextBoundary(rest) {
    var re = /[.!?…]+["'”’)\]]*\s+|\n+/g, m;
    while ((m = re.exec(rest))) { var end = m.index + m[0].length; if (end >= 24) return end; }
    if (rest.length > 280) { var at = rest.lastIndexOf(' ', 260); if (at > 100) return at + 1; }
    return 0;
  }
  function feed(cleaned, final) {
    if (!cleaned.startsWith(spokenText)) { if (!final) return; stopSpeech(); }
    var rest = cleaned.slice(spokenText.length), cut;
    while ((cut = nextBoundary(rest)) > 0) {
      var chunk = rest.slice(0, cut); rest = rest.slice(cut);
      if (chunk.trim()) speakChunk(chunk.trim()); spokenText += chunk;
    }
    if (final && rest.trim()) { speakChunk(rest.trim()); spokenText += rest; }
  }
  window.addEventListener('jarvis:stream', function (e) { if (voice.on && canSpeak()) feed(cleanForSpeech(e.detail.text), false); });
  window.addEventListener('jarvis:reply', function (e) {
    var d = e.detail || {};
    if (!voice.on || !canSpeak() || d.cancelled) { spokenText = ''; return; }
    if (!d.streamed) stopSpeech();
    feed(cleanForSpeech(d.text), true); spokenText = '';
  });
  window.addEventListener('jarvis:stop', stopSpeech);
  $('composer').addEventListener('submit', stopSpeech, true);
  function setVoiceOn(on) {
    voice.on = on; saveVoice(); syncVoiceUi();
    if (!on) stopSpeech(); else speakChunk(sayHello('Voice systems online, ' + (window.JARVIS_ADDRESS || 'sir') + '.'));
  }
  if (!supported) {
    toggle.disabled = true; toggle.title = 'Speech is not supported by this browser'; onBox.disabled = true; sel.disabled = true; $('voice-test').disabled = true; $('voice-jarvis').disabled = true; $('voice-chirp').disabled = true;
    $('voice-note').textContent = 'This browser does not support speech synthesis. Try current Chrome or Edge.';
  } else {
    loadVoices(); if (synth.addEventListener) synth.addEventListener('voiceschanged', loadVoices);
    toggle.addEventListener('click', function () { setVoiceOn(!voice.on); });
    onBox.addEventListener('change', function () { setVoiceOn(onBox.checked); });
    sel.addEventListener('change', function () { voice.uri = sel.value; saveVoice(); updateVoiceHint(); });
    $('voice-chirp').addEventListener('change', function () { voice.chirp = $('voice-chirp').checked; saveVoice(); });
    $('voice-jarvis').addEventListener('click', function () {
      voice.uri = ''; voice.rate = 0.9; voice.pitch = 0.85; voice.chirp = true; saveVoice(); loadVoices(); syncVoiceUi(); stopSpeech();
      var h = new Date().getHours(); speakChunk('Good ' + (h < 12 ? 'morning' : h < 18 ? 'afternoon' : 'evening') + ', ' + (window.JARVIS_ADDRESS || 'sir') + '. All systems are online and fully operational.');
    });
    rate.addEventListener('input', function () { voice.rate = parseFloat(rate.value); $('voice-rate-out').textContent = voice.rate.toFixed(2) + '×'; saveVoice(); });
    pitch.addEventListener('input', function () { voice.pitch = parseFloat(pitch.value); $('voice-pitch-out').textContent = voice.pitch.toFixed(2); saveVoice(); });
    $('voice-test').addEventListener('click', function () { stopSpeech(); speakChunk(sayHello('At your service, ' + (window.JARVIS_ADDRESS || 'sir') + '. All systems are online.')); });
  }
  syncVoiceUi();
  $('voice-engine').addEventListener('change', function () { voice.engine = $('voice-engine').value; saveVoice(); stopSpeech(); syncEngineUi(); });
  $('voice-cloud-voice').addEventListener('change', function () { voice.cloudVoice = $('voice-cloud-voice').value; saveVoice(); });
  $('voice-piper-model').addEventListener('change', function () { voice.piperModel = $('voice-piper-model').value; saveVoice(); });
  loadTts();
  loadLanguage();

  /* ================= model switcher ================= */
  var provLocal = $('prov-local'), provCloud = $('prov-cloud'), modelSel = $('model-select'), aiNote = $('ai-note'), statusEl = $('connection');
  var ai = null, listToken = 0;
  function api(path, body) {
    var opts = body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined;
    return fetch(path, opts).then(function (r) { return r.json().then(function (data) { if (!r.ok) throw new Error(data.error || 'Request failed'); return data; }); });
  }
  function updateStatus() {
    if (!ai || !statusEl) return;
    var p = ai.providers[ai.provider];
    statusEl.textContent = !p.available ? 'Add cloud API key, or switch to Local' : ai.model + ' · ' + (ai.provider === 'local' ? 'Local' : 'Cloud');
  }
  function markProvider() {
    [provLocal, provCloud].forEach(function (b) { b.setAttribute('aria-checked', String(!!ai && b.dataset.provider === ai.provider)); });
    provCloud.disabled = !!ai && !ai.providers.cloud.available;
    provCloud.title = provCloud.disabled ? 'Set OPENAI_API_KEY or JARVIS_CLOUD_API_KEY before starting Jarvis to use the cloud' : '';
  }
  function fillModels() {
    if (!ai) return;
    var token = ++listToken, provider = ai.provider, current = ai.providers[provider].model;
    clearChildren(modelSel); var loading = document.createElement('option'); loading.textContent = 'Loading…'; modelSel.appendChild(loading);
    api('/api/models?provider=' + provider).then(function (res) {
      if (token !== listToken) return;
      var names = res.models.slice(); if (current && names.indexOf(current) < 0) names.unshift(current);
      clearChildren(modelSel);
      names.forEach(function (n) { var o = document.createElement('option'); o.value = n; o.textContent = n; if (n === current) o.selected = true; modelSel.appendChild(o); });
      var where = provider === 'local' ? 'Local model server: ' : 'Cloud provider: ';
      aiNote.textContent = (res.error ? res.error + ' ' : '') + where + ai.providers[provider].base + '. A new choice applies to your next message.';
    }).catch(function (err) { if (token === listToken) aiNote.textContent = err.message; });
  }
  function refreshAi(fill) {
    return api('/api/ai').then(function (data) { ai = data; markProvider(); updateStatus(); if (fill) fillModels(); }).catch(function () {});
  }
  function choose(body) {
    return api('/api/ai', body).then(function (data) { ai = data; markProvider(); updateStatus(); return data; })
      .catch(function (err) { aiNote.textContent = err.message; });
  }
  [provLocal, provCloud].forEach(function (b) {
    b.addEventListener('click', function () { if (b.disabled || (ai && ai.provider === b.dataset.provider)) return; choose({ provider: b.dataset.provider }).then(fillModels); });
  });
  modelSel.addEventListener('change', function () { if (ai && modelSel.value) choose({ provider: ai.provider, model: modelSel.value }); });
  $('model-refresh').addEventListener('click', function () { refreshAi(true); });
  window.addEventListener('jarvis:pane', function (e) { if (paneHas(e.detail.pane, 'model-refresh')) refreshAi(true); });
  if (statusEl) { statusEl.parentNode.style.cursor = 'pointer'; statusEl.parentNode.title = 'Change the AI model'; statusEl.parentNode.addEventListener('click', function (e) { e.stopPropagation(); window.JarvisUI.openPane('ai'); }); }
  refreshAi(false);
})();

/* Menus in other languages.
   The page is written in English. web/i18n/<code>.json maps each English text to its translation, and this script swaps
   them in: once when the page loads, and again whenever another script changes something (a status line, a list, a button).
   It goes by whole texts: a paragraph with bold words in it is one entry, written with the same <strong> or <code> tags.
   Chats, saved chat names and anything marked data-no-i18n are left as they are. Switching back to English restores the
   originals. JarvisI18n.t('Saved.') translates a text for scripts; confirm() and alert() messages are translated too. */
(function () {
  'use strict';
  var INLINE = { STRONG: 1, EM: 1, B: 1, I: 1, CODE: 1, KBD: 1, BR: 1, SMALL: 1, A: 1, SPAN: 1, ABBR: 1, SUP: 1, SUB: 1, Q: 1, MARK: 1, U: 1, S: 1 };
  var SKIP = { SCRIPT: 1, STYLE: 1, TEXTAREA: 1, PRE: 1, CANVAS: 1, TEMPLATE: 1, NOSCRIPT: 1, INPUT: 1, svg: 1, SVG: 1, IFRAME: 1, VIDEO: 1, IMG: 1 };
  var ATTRS = ['title', 'placeholder', 'aria-label'];
  var EXCLUDE = '#conversation, #chat-list, [data-no-i18n], [contenteditable="true"], .code-block, .debug-trace';
  var RTL = { ar: 1, he: 1, fa: 1, ur: 1 };
  var dict = null, code = 'en', blocks = new WeakMap(), texts = new WeakMap(), attrs = new WeakMap(), observer = null, collecting = null;

  function norm(s) { return String(s).replace(/\s+/g, ' ').trim(); }
  function wordy(s) { return /[A-Za-zÀ-ÿ]{2}/.test(s); }
  var patterns = [];
  function lookup(src) {
    var v = dict && Object.prototype.hasOwnProperty.call(dict, src) ? dict[src] : null;
    if (typeof v === 'string' && v) return v;
    for (var i = 0; i < patterns.length; i++) { if (patterns[i][0].test(src)) return src.replace(patterns[i][0], patterns[i][1]); }   // texts with numbers in them
    return null;
  }
  function t(s) { if (!dict || s == null) return s; var v = lookup(norm(s)); return v == null ? s : v; }

  /* an element whose content is only text and plain inline tags (no ids, no controls) is translated as one piece */
  function inlineOnly(el) {
    for (var c = el.firstChild; c; c = c.nextSibling) {
      if (c.nodeType === 3 || c.nodeType === 8) continue;
      if (c.nodeType !== 1 || !INLINE[c.tagName] || c.id || c.hasAttribute('data-no-i18n') || c.hasAttribute('style') || !inlineOnly(c)) return false;
      if (c.className && /^(SPAN|SMALL|I)$/.test(c.tagName)) return false;      // styled pieces (labels, badges, values) are translated on their own
    }
    return true;
  }
  function keyOf(el) { return el.children.length ? norm(el.innerHTML) : norm(el.textContent); }

  function doBlock(el) {
    var cur = keyOf(el), rec = blocks.get(el);
    var src = rec && rec.applied === cur ? rec.src : cur;        // what we wrote earlier → the English behind it; anything else is new
    if (collecting) { collecting.push(src); return; }
    var want = code === 'en' ? src : (lookup(src) || src);
    if (want !== cur) {
      if (/<[a-z]/i.test(want) || (rec && rec.markup) || el.children.length) el.innerHTML = want; else el.textContent = want;
    }
    blocks.set(el, { src: src, applied: keyOf(el), markup: /<[a-z]/i.test(src) });
  }
  function doText(node) {
    var cur = node.nodeValue, n = norm(cur);
    var rec = texts.get(node);
    if (!wordy(n) && !rec) return;                              // a translation in another script (日本語, العربية) still knows its English
    var src = rec && rec.applied === cur ? rec.src : n;
    if (collecting) { collecting.push(src); return; }
    var want = code === 'en' ? src : (lookup(src) || src);
    if (want !== n) node.nodeValue = cur.match(/^\s*/)[0] + want + cur.match(/\s*$/)[0];
    texts.set(node, { src: src, applied: node.nodeValue });
  }
  function doAttrs(el) {
    var list = ATTRS;
    if (el.tagName === 'INPUT' && /^(button|submit|reset)$/i.test(el.type)) list = ATTRS.concat(['value']);
    for (var i = 0; i < list.length; i++) {
      var name = list[i], cur = el.getAttribute(name);
      var all = attrs.get(el) || {}, rec = all[name];
      if (!cur || (!wordy(cur) && !rec)) continue;
      var src = rec && rec.applied === cur ? rec.src : norm(cur);
      if (collecting) { collecting.push(src); continue; }
      var want = code === 'en' ? src : (lookup(src) || src);
      if (want !== cur) el.setAttribute(name, want);
      all[name] = { src: src, applied: el.getAttribute(name) }; attrs.set(el, all);
    }
  }
  function walk(node) {
    if (node.nodeType === 3) { var p = node.parentElement; if (p && !SKIP[p.tagName] && !p.closest(EXCLUDE)) doText(node); return; }
    if (node.nodeType !== 1 || SKIP[node.tagName]) {
      if (node.nodeType === 1 && (node.tagName === 'INPUT' || node.tagName === 'TEXTAREA') && !node.closest(EXCLUDE)) doAttrs(node);
      return;
    }
    if (node.closest(EXCLUDE)) return;
    doAttrs(node);
    if (node.firstChild && (wordy(node.textContent) || blocks.has(node)) && inlineOnly(node)) { doBlock(node); return; }
    for (var c = node.firstChild; c; c = c.nextSibling) walk(c);
  }
  function run(root) {
    if (observer) observer.disconnect();
    try { walk(root); } finally { if (observer) observe(); }
  }
  function observe() { observer.observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRS.concat(['value']) }); }
  function changed(list) {
    if (code === 'en' && !dict) return;
    var roots = [];
    for (var i = 0; i < list.length; i++) {
      var m = list[i], target = m.type === 'characterData' ? m.target.parentElement : m.target;
      if (target && roots.indexOf(target) < 0) roots.push(target);
    }
    observer.disconnect();
    try {
      roots.forEach(function (r) {
        if (!r.isConnected) return;
        // a change inside a piece we translate as a whole: look at that whole piece again
        var up = r.parentElement;
        while (up && up !== document.body && INLINE[r.tagName] && !r.id) { r = up; up = r.parentElement; }
        walk(r);
      });
    } finally { observe(); }
  }

  /* ---------- switching ---------- */
  var cache = {};
  function load(lang) {
    if (lang === 'en') return Promise.resolve(null);
    if (cache[lang]) return Promise.resolve(cache[lang]);
    return fetch('/i18n/' + lang + '.json').then(function (r) { if (!r.ok) throw new Error('missing'); return r.json(); })
      .then(function (d) { cache[lang] = d; return d; });
  }
  function set(lang) {
    lang = String(lang || 'en').toLowerCase();
    return load(lang).then(function (d) {
      dict = d; code = d ? lang : 'en';
      patterns = [];
      ((d && d['@patterns']) || []).forEach(function (p) { try { patterns.push([new RegExp(p[0]), p[1]]); } catch (e) {} });
      document.documentElement.lang = code;
      document.documentElement.dir = RTL[code] ? 'rtl' : 'ltr';     // Arabic and Hebrew read from right to left
      try { localStorage.setItem('jarvis-ui-lang', code); } catch (e) {}
      if (!observer) { observer = new MutationObserver(changed); }
      run(document.body);
      if (document.title) document.title = code === 'en' ? 'Jarvis' : (lookup('Jarvis') || 'Jarvis');
      document.documentElement.classList.remove('i18n-pending');
      window.dispatchEvent(new CustomEvent('jarvis:ui-language', { detail: { code: code } }));
      return code;
    }).catch(function () {
      document.documentElement.classList.remove('i18n-pending');
      return code;
    });
  }
  function collect() {
    collecting = []; var saved = code; code = 'en';
    try { walk(document.body); } finally { code = saved; }
    var out = collecting; collecting = null; return out;
  }
  // dates and times that scripts format with the browser's default language follow the menus instead
  ['toLocaleDateString', 'toLocaleTimeString', 'toLocaleString'].forEach(function (name) {
    var native = Date.prototype[name];
    Date.prototype[name] = function (locales, options) {
      if (code !== 'en' && (locales === undefined || (Array.isArray(locales) && !locales.length))) locales = code === 'ar' ? 'ar-u-nu-latn' : code + (code === 'de' || code === 'fr' || code === 'it' ? '-CH' : '');
      return native.call(this, locales, options);
    };
  });
  // dialogs
  var nativeConfirm = window.confirm, nativeAlert = window.alert, nativePrompt = window.prompt;
  window.confirm = function (m) { return nativeConfirm.call(window, t(m)); };
  window.alert = function (m) { return nativeAlert.call(window, t(m)); };
  window.prompt = function (m, d) { return nativePrompt.call(window, t(m), d); };

  window.JarvisI18n = { t: t, set: set, collect: collect, code: function () { return code; } };

  var saved = 'en';
  try { saved = localStorage.getItem('jarvis-ui-lang') || 'en'; } catch (e) {}
  set(saved);
  setTimeout(function () { document.documentElement.classList.remove('i18n-pending'); }, 1500);   // never stay hidden
})();

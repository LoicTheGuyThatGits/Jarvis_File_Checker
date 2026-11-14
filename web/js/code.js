/* Code blocks: syntax colours, and a Preview that runs HTML / SVG / JavaScript in a locked-down box.
   The preview iframe has no access to Jarvis (sandbox without allow-same-origin) and no network (CSP default-src 'none'). */
(function () {
  const KW = {
    py: 'and as assert async await break class continue def del elif else except finally for from global if import in is lambda nonlocal not or pass raise return try while with yield None True False self print',
    js: 'async await break case catch class const continue debugger default delete do else export extends finally for from function if import in instanceof let new null of return static super switch this throw try typeof undefined var void while yield true false interface type enum implements public private protected readonly abstract namespace declare',
    c: 'auto break case char class const continue default do double else enum extern float for goto if inline int long namespace new nullptr operator private protected public register return short signed sizeof static struct switch template this throw try typedef union unsigned using virtual void volatile while bool true false null NULL string var fn let mut impl pub use mod match loop trait where func package go defer chan map range select interface fmt',
    sh: 'if then else elif fi for while do done case esac function in return echo exit export local set unset cd ls rm cp mv mkdir cat grep sudo goto call rem Get-ChildItem Set-Location Write-Host Write-Output ForEach-Object Where-Object param begin process end try catch finally',
    sql: 'select from where and or not insert into values update set delete create table drop alter add index primary key foreign references join left right inner outer on group by order having limit offset as distinct union all null is in like between exists case when then else end count sum avg min max asc desc default unique view',
  };
  const WORDS = {}; Object.keys(KW).forEach(k => { WORDS[k] = new Set(KW[k].split(/\s+/)); });
  const GROUP = { python: 'py', py: 'py', javascript: 'js', js: 'js', node: 'js', typescript: 'js', ts: 'js', jsx: 'js', tsx: 'js', java: 'c', c: 'c', cpp: 'c', 'c++': 'c', cs: 'c', csharp: 'c', go: 'c', rust: 'c', rs: 'c', php: 'c', kotlin: 'c', swift: 'c',
    bash: 'sh', sh: 'sh', shell: 'sh', zsh: 'sh', powershell: 'sh', ps1: 'sh', bat: 'sh', batch: 'sh', cmd: 'sh', sql: 'sql', html: 'html', htm: 'html', xml: 'html', svg: 'html', css: 'css', scss: 'css', json: 'json' };
  const EXT = { py: 'py', js: 'js', mjs: 'js', ts: 'js', tsx: 'js', jsx: 'js', java: 'c', c: 'c', h: 'c', cpp: 'c', cs: 'c', go: 'c', rs: 'c', php: 'c', kt: 'c', swift: 'c', sh: 'sh', ps1: 'sh', bat: 'sh', sql: 'sql', html: 'html', htm: 'html', xml: 'html', svg: 'html', css: 'css', scss: 'css', json: 'json' };
  const RX = {
    py: /(#[^\n]*)|("""[\s\S]*?(?:"""|$)|'''[\s\S]*?(?:'''|$)|[frbFRB]?"(?:[^"\\\n]|\\.)*"?|[frbFRB]?'(?:[^'\\\n]|\\.)*'?)|(\b\d[\d_.]*(?:e[+-]?\d+)?\b)|([A-Za-z_]\w*)/g,
    js: /(\/\/[^\n]*|\/\*[\s\S]*?(?:\*\/|$))|("(?:[^"\\\n]|\\.)*"?|'(?:[^'\\\n]|\\.)*'?|`(?:[^`\\]|\\[\s\S])*(?:`|$))|(\b0x[\da-fA-F]+\b|\b\d[\d_.]*(?:e[+-]?\d+)?\b)|([A-Za-z_$][\w$]*)/g,
    sh: /(#[^\n]*|^\s*(?:rem|::)[^\n]*)|("(?:[^"\\\n]|\\.)*"?|'[^'\n]*'?)|(\b\d+\b)|(\$\{?[A-Za-z_]\w*\}?|[A-Za-z_][\w-]*)/gm,
    sql: /(--[^\n]*|\/\*[\s\S]*?(?:\*\/|$))|('(?:[^'\\\n]|\\.|'')*'?)|(\b\d[\d.]*\b)|([A-Za-z_]\w*)/g,
    css: /(\/\*[\s\S]*?(?:\*\/|$))|("(?:[^"\\\n]|\\.)*"?|'(?:[^'\\\n]|\\.)*'?)|(#[\da-fA-F]{3,8}\b|-?\b\d[\d.]*(?:px|em|rem|%|vh|vw|s|ms|deg|fr)?\b)|(@[\w-]+|[\w-]+(?=\s*:)|[.#][\w-]+)/g,
    json: /()("(?:[^"\\\n]|\\.)*"(?=\s*:))|("(?:[^"\\\n]|\\.)*"?)|(-?\b\d[\d.]*(?:e[+-]?\d+)?\b)|\b(true|false|null)\b/g,
    html: /(<!--[\s\S]*?(?:-->|$))|((?<==\s*)(?:"[^"\n]*"?|'[^'\n]*'?))|(<\/?[A-Za-z][\w:-]*|\/?>)|([\w:-]+(?==))/g,
  };
  function span(cls, text) { const s = document.createElement('span'); s.className = 'tok-' + cls; s.textContent = text; return s; }
  function highlight(code, group) {
    const frag = document.createDocumentFragment();
    const rx = RX[group];
    if (!rx || code.length > 40000) { frag.append(document.createTextNode(code)); return frag; }
    rx.lastIndex = 0;
    let last = 0, m;
    while ((m = rx.exec(code))) {
      if (m[0] === '') { rx.lastIndex++; continue; }
      if (m.index > last) frag.append(document.createTextNode(code.slice(last, m.index)));
      let cls = null;
      if (group === 'json') cls = m[2] ? 'p' : m[3] ? 's' : m[4] ? 'n' : m[5] ? 'k' : null;
      else if (group === 'html') cls = m[1] ? 'c' : m[2] ? 's' : m[3] ? 't' : m[4] ? 'p' : null;
      else if (m[1]) cls = 'c';
      else if (m[2]) cls = 's';
      else if (m[3]) cls = 'n';
      else if (m[4]) {
        const w = m[4];
        if (group === 'css') cls = w[0] === '@' ? 'k' : /^[.#]/.test(w) ? 't' : 'p';
        else if (WORDS[group] && (WORDS[group].has(group === 'sql' ? w.toLowerCase() : w))) cls = 'k';
        else if (w[0] === '$') cls = 'p';
      }
      frag.append(cls ? span(cls, m[0]) : document.createTextNode(m[0]));
      last = m.index + m[0].length;
    }
    if (last < code.length) frag.append(document.createTextNode(code.slice(last)));
    return frag;
  }

  const CSP = "default-src 'none'; script-src 'unsafe-inline' 'unsafe-eval'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; media-src data: blob:; form-action 'none'";
  const META = '<meta http-equiv="Content-Security-Policy" content="' + CSP + '">';
  const BASE_CSS = '<style>html{color-scheme:light}body{margin:8px;font-family:system-ui,Segoe UI,sans-serif}</style>';
  const base = n => String(n || '').split('/').pop().toLowerCase();
  const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');

  function withCsp(html) {
    if (/<head[^>]*>/i.test(html)) return html.replace(/<head[^>]*>/i, m => m + META);
    if (/<html[^>]*>/i.test(html)) return html.replace(/<html[^>]*>/i, m => m + '<head>' + META + '</head>');
    if (/^\s*<!doctype[^>]*>/i.test(html)) return html.replace(/^\s*<!doctype[^>]*>/i, m => m + '<head>' + META + '</head>');
    return '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' + META + BASE_CSS + '</head><body>' + html + '</body></html>';
  }
  /* siblings: the other code blocks of the same message, as {name, lang, code}; used to inline linked style.css and script.js */
  function buildPreview(kind, code, siblings) {
    if (kind === 'svg') return withCsp('<!doctype html><html><body style="margin:0;display:flex;align-items:center;justify-content:center;min-height:100vh;background:#fff">' + code + '</body></html>');
    if (kind === 'js') {
      const safe = code.replace(/<\/script/gi, '<\\/script');
      return withCsp('<!doctype html><html><head><meta charset="utf-8">' + BASE_CSS + '<style>pre{white-space:pre-wrap;font:13px/1.5 Consolas,monospace;margin:0}.e{color:#b00020}</style></head><body><pre id="out"></pre><script>' +
        '(function(){var o=document.getElementById("out");function w(c,a){var t=Array.prototype.map.call(a,function(x){try{return typeof x==="object"?JSON.stringify(x):String(x)}catch(e){return String(x)}}).join(" ");var d=document.createElement("div");if(c)d.className=c;d.textContent=t;o.appendChild(d)}' +
        'console.log=function(){w("",arguments)};console.info=console.log;console.warn=function(){w("e",arguments)};console.error=function(){w("e",arguments)};' +
        'window.onerror=function(m){w("e",["Error: "+m])};window.onunhandledrejection=function(e){w("e",["Error: "+(e.reason&&e.reason.message||e.reason)])};})();</script>' +
        '<script>try{' + safe + '\n}catch(e){console.error(e&&e.message||e)}</script></body></html>');
    }
    let html = code;
    html = html.replace(/<link\b[^>]*href=["']?([^"'\s>]+)["']?[^>]*>/gi, (tag, href) => {
      const hit = siblings.find(s => base(s.name) === base(href) && /css/i.test(s.lang + s.name));
      return hit ? '<style>' + hit.code.replace(/<\/style/gi, '<\\/style') + '</style>' : tag;
    });
    html = html.replace(/<script\b[^>]*src=["']?([^"'\s>]+)["']?[^>]*>\s*<\/script>/gi, (tag, src) => {
      const hit = siblings.find(s => base(s.name) === base(src) && /(js|javascript|ts)/i.test(s.lang + s.name));
      return hit ? '<script>' + hit.code.replace(/<\/script/gi, '<\\/script') + '</script>' : tag;
    });
    return withCsp(html);
  }
  function kindOf(lang, file, code) {
    const ext = (file.split('.').pop() || '').toLowerCase();
    if (lang === 'html' || lang === 'htm' || ext === 'html' || ext === 'htm') return 'html';
    if (lang === 'svg' || ext === 'svg' || (lang === 'xml' && /^\s*<svg[\s>]/i.test(code))) return 'svg';
    if (['javascript', 'js', 'node'].includes(lang) || (ext === 'js' && !lang)) return /\b(require|import\s+.+from|export\s)/.test(code) || /\b(process\.|fs\.)/.test(code) ? null : 'js';
    return null;
  }

  function enhance(block, info) {
    const group = GROUP[info.lang] || EXT[(info.file.split('.').pop() || '').toLowerCase()] || null;
    const codeEl = block.querySelector('pre code');
    if (codeEl && group) { codeEl.textContent = ''; codeEl.append(highlight(info.code, group)); }
    const kind = info.complete ? kindOf(info.lang, info.file, info.code) : null;
    if (!kind) return;
    const tools = block.querySelector('.code-block-tools');
    const btn = document.createElement('button'); btn.type = 'button'; btn.textContent = 'Preview'; btn.className = 'code-preview-btn';
    let panel = null;
    function open() {
      panel = document.createElement('div'); panel.className = 'code-preview' + (kind === 'js' ? ' out' : '');
      const bar = document.createElement('div'); bar.className = 'code-preview-bar';
      const note = document.createElement('span'); note.textContent = kind === 'js' ? 'Output (runs in a sealed box)' : 'Preview (sealed box: no internet, no access to Jarvis)';
      const reload = document.createElement('button'); reload.type = 'button'; reload.textContent = 'Reload';
      const grow = document.createElement('button'); grow.type = 'button'; grow.textContent = 'Larger';
      const close = document.createElement('button'); close.type = 'button'; close.textContent = 'Close';
      const frame = document.createElement('iframe');
      frame.setAttribute('sandbox', 'allow-scripts');
      frame.setAttribute('referrerpolicy', 'no-referrer');
      frame.title = 'Code preview';
      const load = () => { frame.srcdoc = buildPreview(kind, info.code, info.siblings()); };
      reload.addEventListener('click', load);
      grow.addEventListener('click', () => { const big = panel.classList.toggle('big'); grow.textContent = big ? 'Smaller' : 'Larger'; });
      close.addEventListener('click', () => { panel.remove(); panel = null; btn.textContent = 'Preview'; });
      bar.append(note, reload, grow, close); panel.append(bar, frame); block.append(panel); load(); btn.textContent = 'Hide preview';
    }
    btn.addEventListener('click', () => { if (panel) { panel.remove(); panel = null; btn.textContent = 'Preview'; } else open(); });
    tools.prepend(btn);
  }
  window.JarvisCode = { enhance, highlight, buildPreview, kindOf };
})();

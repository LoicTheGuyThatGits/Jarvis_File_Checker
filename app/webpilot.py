"""The Jarvis browser: websites driven directly, not by clicking spots on a picture.

Autopilot opens its own window of Microsoft Edge (or Chrome) with a profile of its own (data/browser-profile), so it is
not signed in to your accounts unless you sign in there yourself. It reads each page as a numbered list of what can be
clicked or filled in (links, buttons, text boxes, menus) plus the page's text, and acts on an item by its number: exact,
whatever the zoom, the theme or the screen. It never types into password boxes.

Needs the Playwright package (py -m pip install playwright); it uses the Edge or Chrome already on the PC.

    WebPilot(profile_dir)  .open(url) .snapshot() .click(n) .type(n, text, enter) .select(n, option) .key(name)
                           .scroll(down) .back() .read(start) .tab(n) .close() .active()
    describe(snapshot)     the text given to the model
    blocked(url)           sites Autopilot does not touch (parental controls)
"""
from __future__ import annotations

import queue
import re
import threading
from pathlib import Path

BLOCKED = re.compile(r"(?:^|\.)(?:families\.google\.com|familylink\.google\.com|familysafety\.microsoft\.com)$|"
                     r"^(?:account\.microsoft\.com/family|myaccount\.google\.com/(?:family|security|signinoptions))", re.I)
KEYS = {"enter": "Enter", "esc": "Escape", "escape": "Escape", "tab": "Tab", "space": " ", "backspace": "Backspace", "delete": "Delete",
        "up": "ArrowUp", "down": "ArrowDown", "left": "ArrowLeft", "right": "ArrowRight", "pageup": "PageUp", "pagedown": "PageDown",
        "home": "Home", "end": "End", "f5": "F5"}
SNAPSHOT_JS = r"""() => {
  const sel = 'a[href], button, input:not([type=hidden]), textarea, select, summary, [role=button], [role=link], [role=tab], [role=menuitem], [role=checkbox], [role=radio], [role=option], [role=combobox], [role=switch], [role=searchbox], [role=textbox], [contenteditable=""], [contenteditable=true]';
  document.querySelectorAll('[data-jarvis-n]').forEach(e => e.removeAttribute('data-jarvis-n'));
  const items = []; let n = 0, offscreen = 0;
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect(), st = getComputedStyle(el);
    if (r.width < 2 || r.height < 2 || st.visibility === 'hidden' || st.display === 'none' || st.opacity === '0') continue;
    const inView = r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth;
    if (!inView && ++offscreen > 40) continue;
    const tag = el.tagName.toLowerCase(), type = (el.getAttribute('type') || '').toLowerCase();
    let label = el.getAttribute('aria-label') || (el.labels && el.labels[0] && el.labels[0].innerText) || el.getAttribute('placeholder')
      || (tag === 'select' ? '' : el.innerText) || el.getAttribute('title') || el.getAttribute('alt') || el.getAttribute('name') || '';
    if (!label && tag === 'input' && ['submit', 'button'].includes(type)) label = el.value;
    if (!label) { const img = el.querySelector('img[alt]'); if (img) label = img.alt; }
    label = String(label).replace(/\s+/g, ' ').trim().slice(0, 90);
    n += 1; el.setAttribute('data-jarvis-n', String(n));
    const item = {n, tag, type, role: el.getAttribute('role') || '', label, inView, password: type === 'password', disabled: !!el.disabled};
    if ((tag === 'input' || tag === 'textarea') && type !== 'password') item.value = String(el.value || '').slice(0, 60);
    if (tag === 'select') item.value = el.options[el.selectedIndex] ? el.options[el.selectedIndex].text.slice(0, 60) : '', item.options = Array.from(el.options).slice(0, 15).map(o => o.text.trim().slice(0, 40));
    if (type === 'checkbox' || type === 'radio') item.checked = !!el.checked;
    if (tag === 'a') item.href = (el.getAttribute('href') || '').slice(0, 100);
    items.push(item);
    if (items.length >= 160) break;
  }
  const text = (document.body ? document.body.innerText : '').replace(/[ \t]+/g, ' ').replace(/\n\s*\n+/g, '\n');
  return {title: document.title, url: location.href, items, text: text.slice(0, 60000), scroll: Math.round(scrollY), height: document.documentElement.scrollHeight, view: innerHeight};
}"""


class WebError(Exception):
    pass


def blocked(url: str) -> bool:
    m = re.match(r"https?://([^/?#]+)(/[^?#]*)?", url or "", re.I)
    if not m:
        return False
    host = m.group(1).lower().split(":")[0]
    return bool(BLOCKED.search(host) or BLOCKED.match(host + (m.group(2) or "")))


def available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except Exception:
        return False


class WebPilot:
    def __init__(self, profile_dir: Path, channels: tuple = ("msedge", "chrome"), headless: bool = False, executable: str | None = None):
        self.profile = Path(profile_dir)
        self.channels, self.headless, self.executable = channels, headless, executable
        self.jobs: "queue.Queue" = queue.Queue()
        self.thread: threading.Thread | None = None
        self.lock = threading.Lock()
        self._page = None
        self._open = False
        self.last: dict | None = None

    # ---- one thread owns the browser (Playwright's rule) ----
    def _run(self) -> None:
        from playwright.sync_api import sync_playwright
        pw = ctx = None
        while True:
            fn, args, box, done = self.jobs.get()
            if fn is None:
                break
            try:
                if ctx is None or not self._open:
                    if pw is None:
                        pw = sync_playwright().start()
                    ctx = self._launch(pw)
                    self._open = True
                box["value"] = fn(ctx, *args)
            except Exception as exc:                          # noqa: BLE001 — every failure goes back to the caller
                box["error"] = exc
            finally:
                done.set()
        try:
            if ctx is not None:
                ctx.close()
            if pw is not None:
                pw.stop()
        except Exception:
            pass
        self._open = False

    def _launch(self, pw):
        self.profile.mkdir(parents=True, exist_ok=True)
        last = None
        for channel in (self.channels or (None,)):
            try:
                kw = {"headless": self.headless, "no_viewport": not self.headless, "args": ["--start-maximized"] if not self.headless else []}
                if channel:
                    kw["channel"] = channel
                if self.executable:
                    kw["executable_path"] = self.executable
                ctx = pw.chromium.launch_persistent_context(str(self.profile), **kw)
                ctx.on("close", lambda *_: setattr(self, "_open", False))
                ctx.on("page", lambda p: setattr(self, "_page", p))
                self._page = ctx.pages[0] if ctx.pages else ctx.new_page()
                return ctx
            except Exception as exc:
                last = exc
        raise WebError("I could not start a browser for Autopilot (Edge or Chrome): " + str(last)[:200])

    def _call(self, fn, *args, timeout: float = 45):
        with self.lock:
            if self.thread is None or not self.thread.is_alive():
                if not available():
                    raise WebError("The Jarvis browser needs the Playwright package. Install it in Settings > Computer control (or run: py -m pip install playwright).")
                self.thread = threading.Thread(target=self._run, daemon=True)
                self.thread.start()
        box, done = {}, threading.Event()
        self.jobs.put((fn, args, box, done))
        if not done.wait(timeout):
            raise WebError("The browser did not answer in time.")
        if "error" in box:
            err = box["error"]
            raise err if isinstance(err, WebError) else WebError(_short(err))
        return box.get("value")

    def page(self, ctx):
        pages = [p for p in ctx.pages if not p.is_closed()]
        if self._page is None or self._page.is_closed():
            self._page = pages[-1] if pages else ctx.new_page()
        return self._page

    def active(self) -> bool:
        return bool(self._open and self.thread and self.thread.is_alive())

    # ---- what Autopilot can do ----
    def open(self, url: str) -> dict:
        if not re.match(r"https?://", url or "", re.I):
            raise WebError("Only http and https addresses can be opened.")
        if blocked(url):
            raise WebError("Autopilot does not open parental-control or account-security pages.")

        def go(ctx):
            p = self.page(ctx)
            p.goto(url, wait_until="domcontentloaded", timeout=30000)
            _settle(p)
            p.bring_to_front()
        self._call(go)
        return self.snapshot()

    def snapshot(self) -> dict:
        def snap(ctx):
            p = self.page(ctx)
            data = p.evaluate(SNAPSHOT_JS)
            pages = [x for x in ctx.pages if not x.is_closed()]
            data["tabs"] = [{"n": i + 1, "title": (x.title() or x.url)[:60], "active": x is p} for i, x in enumerate(pages)]
            return data
        self.last = self._call(snap)
        return self.last

    def _item(self, ctx, n: int):
        loc = self.page(ctx).locator(f'[data-jarvis-n="{int(n)}"]')
        if loc.count() == 0:
            raise WebError(f"There is no item B{int(n)} on the page any more; look at the page again.")
        return loc.first

    def click(self, n: int) -> dict:
        def do(ctx):
            p = self.page(ctx)
            self._item(ctx, n).click(timeout=8000)
            _settle(p)
        self._call(do)
        return self.snapshot()

    def type(self, n: int, text: str, enter: bool = False) -> dict:
        item = next((i for i in (self.last or {}).get("items", []) if i["n"] == int(n)), None)
        if item and item.get("password"):
            raise WebError("Autopilot never types passwords. Sign in yourself in the Jarvis browser, then let it continue.")

        def do(ctx):
            loc = self._item(ctx, n)
            if loc.evaluate("e => (e.getAttribute('type') || '').toLowerCase() === 'password'"):
                raise WebError("Autopilot never types passwords. Sign in yourself in the Jarvis browser, then let it continue.")
            if loc.evaluate("e => e.isContentEditable"):
                loc.click(timeout=8000)
                self.page(ctx).keyboard.type(text)
            else:
                loc.fill(text, timeout=8000)
            if enter:
                loc.press("Enter")
                _settle(self.page(ctx))
        self._call(do)
        return self.snapshot()

    def select(self, n: int, option: str) -> dict:
        def do(ctx):
            loc = self._item(ctx, n)
            try:
                loc.select_option(label=option, timeout=6000)
            except Exception:
                loc.select_option(value=option, timeout=6000)
        self._call(do)
        return self.snapshot()

    def key(self, name: str) -> dict:
        key = KEYS.get(name.lower(), name)

        def do(ctx):
            p = self.page(ctx)
            p.keyboard.press(key)
            _settle(p)
        self._call(do)
        return self.snapshot()

    def scroll(self, down: bool = True) -> dict:
        self._call(lambda ctx: self.page(ctx).mouse.wheel(0, (1 if down else -1) * 700) or self.page(ctx).wait_for_timeout(350))
        return self.snapshot()

    def back(self) -> dict:
        def do(ctx):
            p = self.page(ctx)
            p.go_back(wait_until="domcontentloaded", timeout=15000)
            _settle(p)
        self._call(do)
        return self.snapshot()

    def tab(self, n: int) -> dict:
        def do(ctx):
            pages = [x for x in ctx.pages if not x.is_closed()]
            if not 1 <= int(n) <= len(pages):
                raise WebError(f"There is no tab {int(n)}.")
            self._page = pages[int(n) - 1]
            self._page.bring_to_front()
        self._call(do)
        return self.snapshot()

    def read(self, start: int = 0) -> str:
        snap = self.snapshot()
        text = snap.get("text", "")
        part = text[start:start + 6000]
        more = f"\n[… {len(text) - start - 6000} more characters: read again from {start + 6000}]" if len(text) > start + 6000 else ""
        return f"Text of “{snap.get('title', '')}” from character {start}:\n{part}{more}"

    def close(self) -> None:
        if self.thread and self.thread.is_alive():
            self.jobs.put((None, (), {}, threading.Event()))
            self.thread.join(10)
        self._open = False


def _settle(page) -> None:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=8000)
    except Exception:
        pass
    try:
        page.wait_for_timeout(400)
    except Exception:
        pass


def _short(exc: Exception) -> str:
    text = str(exc).split("\n")[0]
    if "Timeout" in text:
        return "The page did not respond in time (the item may be hidden or covered)."
    return text[:220]


KIND = {"a": "link", "button": "button", "select": "drop-down", "textarea": "text box", "summary": "expander"}


def describe(snap: dict | None, text_chars: int = 1500, limit: int = 120) -> str:
    if not snap:
        return ""
    tabs = snap.get("tabs") or []
    current = next((t["n"] for t in tabs if t.get("active")), 1)
    where = f" (tab {current} of {len(tabs)})" if len(tabs) > 1 else ""
    lines = [f"Jarvis browser{where}: “{snap.get('title', '')}” — {snap.get('url', '')}"]
    if len(tabs) > 1:
        lines.append("Tabs: " + "; ".join(f"{t['n']}. {t['title']}" for t in tabs))
    items = snap.get("items") or []
    if items:
        lines.append("Items on the page (use web_click, web_type or web_select with \"item\": N; † = below or above the visible part):")
        for i in items[:limit]:
            kind = KIND.get(i["tag"]) or (("password box" if i.get("password") else "checkbox" if i["type"] == "checkbox" else "option" if i["type"] == "radio"
                                           else "button" if i["type"] in ("submit", "button") else "text box") if i["tag"] == "input" else (i.get("role") or i["tag"]))
            extra = ""
            if "value" in i and i["tag"] != "select":
                extra = f", containing “{i['value']}”" if i["value"] else ", empty"
            if i["tag"] == "select":
                extra = f", showing “{i.get('value', '')}”, options: " + " | ".join(i.get("options") or [])
            if "checked" in i:
                extra += ", ticked" if i["checked"] else ", not ticked"
            if i.get("disabled"):
                extra += " (greyed out)"
            lines.append(f"B{i['n']}. {kind} “{i['label'] or '(no name)'}”{extra}{'' if i.get('inView', True) else ' †'}")
    text = (snap.get("text") or "").strip()
    if text:
        more = f" (page text continues: web_read with \"start\": {text_chars})" if len(text) > text_chars else ""
        lines.append(f"Page text{more}:\n" + text[:text_chars])
    return "\n".join(lines)

"""Command suggestions in the message box ("/" and the start of a command) and the Ctrl+/ shortcut list."""
import os, sys, tempfile, threading, importlib.util
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp = Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0, "app")
spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT = tmp
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start(); PORT = app.server_address[1]
from playwright.sync_api import sync_playwright
errs, posts = [], []
with sync_playwright() as pw:
    br = pw.chromium.launch()
    pg = br.new_context(viewport={"width": 1280, "height": 900}).new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("request", lambda r: posts.append(r.url) if r.url.endswith("/api/chat") else None)
    pg.goto(f"http://127.0.0.1:{PORT}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload()
    pg.focus("#message"); pg.keyboard.type("/")
    assert pg.is_visible("#cmd-suggest") and pg.locator(".cmd-group").count() >= 8 and pg.locator(".cmd-item.picked").count() == 1
    pg.screenshot(path=str(tmp / "slash.png"))
    pg.keyboard.type("timer"); items = pg.locator(".cmd-item").all_inner_texts()
    assert "set a timer for 10 minutes" in items and "play my study playlist" not in items, items
    pg.keyboard.press("ArrowDown"); second = pg.locator(".cmd-item.picked").inner_text(); pg.keyboard.press("Enter")
    assert pg.input_value("#message") == second and pg.is_hidden("#cmd-suggest") and not posts, "taking a command does not send it"
    pg.fill("#message", ""); pg.keyboard.type("/zzqx"); assert "No command matches" in pg.inner_text("#cmd-suggest")
    pg.keyboard.press("Escape"); assert pg.is_hidden("#cmd-suggest") and pg.input_value("#message") == "/zzqx"
    # the start of a command
    pg.fill("#message", ""); pg.keyboard.type("remind me")
    items = pg.locator(".cmd-item").all_inner_texts(); assert items and all(i.startswith("remind me") for i in items) and pg.locator(".cmd-item.picked").count() == 0, items
    pg.keyboard.press("Tab"); assert pg.input_value("#message") == items[0]
    pg.fill("#message", ""); pg.keyboard.type("hello there friend"); assert pg.is_hidden("#cmd-suggest"), "ordinary messages get no list"
    pg.fill("#message", ""); pg.keyboard.press("ArrowUp"); assert pg.is_hidden("#cmd-suggest")
    # Ctrl+/
    pg.keyboard.press("Control+/"); pg.wait_for_selector("#keys-help:not(.hidden)")
    pg.wait_for_function("document.querySelector('#keys-global').textContent.includes('Ask Jarvis')"); txt = pg.inner_text("#keys-help"); assert "Edit your last message" in txt and "Ask Jarvis from any app" in txt and "Ctrl" in txt, txt
    pg.screenshot(path=str(tmp / "keys.png"))
    pg.keyboard.press("Escape"); assert pg.is_hidden("#keys-help")
    assert "/ for commands" in pg.inner_text("#voice-hint").lower(), pg.inner_text("#voice-hint")
    # French menus: the group names are translated, the commands stay as Jarvis understands them
    pg.evaluate("fetch('/api/language',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ui:'fr'})})"); pg.wait_for_timeout(300)
    pg.reload(); pg.wait_for_function("document.documentElement.lang === 'fr'"); pg.wait_for_timeout(300)
    pg.focus("#message"); pg.keyboard.type("/")
    groups = pg.locator(".cmd-group").all_inner_texts(); assert "Minuteurs et rappels".upper() in [g.upper() for g in groups], groups
    br.close()
assert not errs, errs
print("suggest ok", tmp)
os._exit(0)

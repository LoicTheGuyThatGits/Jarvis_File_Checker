import json, os, sys, tempfile, threading, importlib.util
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp = Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0, "app")
spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT = tmp
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start(); port = app.server_address[1]

from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch(); ctx = b.new_context(viewport={"width": 1280, "height": 900}); pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off');localStorage.setItem('jarvis-theme-v1','stark')"); pg.reload(); pg.wait_for_timeout(600)
    assert pg.locator("#play-game").count() == 0, "no button: it is a secret"
    # the easter egg: the “AI model” tab clicked 7 times in a row
    pg.evaluate("window.JarvisUI.openPane('ai')"); pg.wait_for_timeout(200)
    for _ in range(6): pg.click("#tab-ai")
    assert len(ctx.pages) == 1, "not after 6"
    with pg.expect_popup() as pop:
        pg.click("#tab-ai")
    game = pop.value; game.on("pageerror", lambda e: errs.append("game: " + str(e))); game.wait_for_function("window.JarvisGame")
    assert game.text_content("#status") == "You found the secret game." and game.locator(".cell:not(:empty)").count() == 2
    accent = pg.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--t-accent').trim()")
    assert game.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()") == accent, "the theme's colour"
    # every square the same size, numbers or not (the screenshot: rows with numbers were taller)
    game.evaluate("window.JarvisGame.set([8,0,0,0, 4,0,0,0, 0,0,0,0, 0,2,0,0])"); game.wait_for_timeout(300)
    sizes = game.evaluate("[...document.querySelectorAll('.cell')].map(c => { const r = c.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; })")
    assert len({tuple(x) for x in sizes}) == 1, sizes
    # the rules
    game.evaluate("window.JarvisGame.set([2,2,4,4, 0,0,0,0, 2,0,2,0, 0,0,0,0])")
    game.keyboard.press("ArrowLeft"); st = game.evaluate("window.JarvisGame.state()")
    assert st["grid"][:4] == [4, 8, 0, 0] and st["grid"][8] == 4 and st["score"] == 16 and st["grid"].count(0) == 12, st
    game.evaluate("Math.random = () => 0.1; window.JarvisGame.set([2,4,2,4, 4,2,4,2, 2,4,2,4, 4,2,8,8])"); game.keyboard.press("ArrowLeft")
    game.wait_for_selector("#over:not(.hidden)"); assert game.text_content("#over-title") == "Game over" and game.evaluate("window.JarvisGame.state().grid.slice(12)") == [4, 2, 16, 2]
    game.click("#again"); assert game.evaluate("window.JarvisGame.state().score") == 0
    game.keyboard.press("ArrowUp"); game.keyboard.press("ArrowLeft"); kept = game.evaluate("window.JarvisGame.state().grid")
    game.reload(); game.wait_for_function("window.JarvisGame"); assert game.evaluate("window.JarvisGame.state().grid") == kept, "the game is kept"
    assert not errs, errs
    b.close()
print("game ok"); os._exit(0)

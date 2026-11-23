import json, os, sys, tempfile, threading, time, importlib.util
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
tmp = Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0, "app")

# a slow pretend AI model, so there is a wait to play in
release = threading.Event()
class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        release.wait(30)
        if not body.get("stream"):
            raw = json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw); return
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        self.wfile.write(("data: " + json.dumps({"choices": [{"delta": {"content": "Here is your answer, sir."}}]}) + "\n\n").encode()); self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()
fake = ThreadingHTTPServer(("127.0.0.1", 0), Fake); threading.Thread(target=fake.serve_forever, daemon=True).start()
os.environ["OPENAI_BASE_URL"] = f"http://127.0.0.1:{fake.server_address[1]}/v1"; os.environ["OPENAI_API_KEY"] = "ollama"
spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT = tmp
S.ensure_ollama = lambda base, wait=25.0: True
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start(); port = app.server_address[1]

from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch(); ctx = b.new_context(viewport={"width": 1280, "height": 900}); pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(600)
    assert not pg.is_visible("#play-game"), "only while Jarvis is working on an answer"
    pg.fill("#message", "tell me something interesting about owls"); pg.keyboard.press("Enter")
    pg.wait_for_selector("#play-game:not(.hidden)")
    with pg.expect_popup() as pop:
        pg.click("#play-game")
    game = pop.value; game.on("pageerror", lambda e: errs.append("game: " + str(e))); game.wait_for_load_state()
    game.wait_for_function("window.JarvisGame && document.querySelector('#status').textContent === 'Jarvis is thinking…'")
    assert game.locator(".cell:not(:empty)").count() == 2, "a new game starts with two tiles"
    # the rules
    game.evaluate("window.JarvisGame.set([2,2,4,4, 0,0,0,0, 2,0,2,0, 0,0,0,0])")
    game.keyboard.press("ArrowLeft"); st = game.evaluate("window.JarvisGame.state()")
    assert st["grid"][:4] == [4, 8, 0, 0] and st["grid"][8] == 4 and st["score"] == 16 and st["grid"].count(0) == 12, st
    game.evaluate("Math.random = () => 0.1; window.JarvisGame.set([2,4,2,4, 4,2,4,2, 2,4,2,4, 4,2,8,8])"); game.keyboard.press("ArrowLeft")
    game.wait_for_selector("#over:not(.hidden)"); assert game.text_content("#over-title") == "Game over" and game.evaluate("window.JarvisGame.state().grid.slice(12)") == [4, 2, 16, 2]
    game.click("#again"); assert game.evaluate("window.JarvisGame.state().score") == 0
    game.keyboard.press("ArrowUp"); game.keyboard.press("ArrowLeft"); saved = game.evaluate("window.JarvisGame.state().grid")
    # the answer arrives: the game says so and pauses
    release.set()
    pg.wait_for_function("document.querySelector('#conversation').textContent.includes('Here is your answer')")
    game.wait_for_selector("#done:not(.hidden)"); assert game.text_content("#status") == "Jarvis has answered."
    assert not pg.is_visible("#play-game"), "the button goes when the answer is there"
    before = game.evaluate("window.JarvisGame.state().grid"); game.keyboard.press("ArrowDown"); assert game.evaluate("window.JarvisGame.state().grid") == before, "paused"
    game.click("#finish"); assert not game.is_visible("#done")
    # it remembers the game
    game.reload(); game.wait_for_function("window.JarvisGame")
    assert game.evaluate("window.JarvisGame.state().grid") == before
    game.click("#back") if game.is_visible("#back") else game.close()
    assert not errs, errs
    b.close()
print("game ok"); os._exit(0)

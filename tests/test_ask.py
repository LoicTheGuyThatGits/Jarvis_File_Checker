"""The quick-ask window: ask, a streamed answer with Copy, follow-ups, Esc puts it away, "Open in Jarvis" carries the
conversation on in the big window (which picks it up at once), and the endpoints are only for the PC."""
import json, os, sys, tempfile, threading, importlib.util, http.client
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
tmp = Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
asked = []
class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps({"object": "list", "data": [{"id": "llama3.2:3b"}]}).encode())
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        asked.append([m["content"].split("[End of context]")[-1].strip() for m in body["messages"] if m["role"] == "user"])
        text = "Paris is the capital, sir.\n```\nprint('hi')\n```" if len(asked) == 1 else "About 2.1 million people, sir."
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        for k in range(0, len(text), 6):
            self.wfile.write(("data: " + json.dumps({"choices": [{"delta": {"content": text[k:k + 6]}}]}) + "\n\n").encode()); self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()
fake = ThreadingHTTPServer(("127.0.0.1", 0), Fake); threading.Thread(target=fake.serve_forever, daemon=True).start()
for k in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL", "JARVIS_CLOUD_API_KEY", "JARVIS_PROVIDER"): os.environ.pop(k, None)
os.environ["JARVIS_LOCAL_BASE_URL"] = f"http://127.0.0.1:{fake.server_address[1]}/v1"
sys.path.insert(0, "app")
spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT = tmp
shown, hidden = [], []
S.show_jarvis_window = lambda: shown.append(1)
S.ask_hide = lambda: hidden.append(1) or True
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start(); PORT = app.server_address[1]
# the window it opens: Jarvis's own app window, small
cmd = S.ask_command(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")
assert any(c.startswith("--app=http://127.0.0.1:") and c.endswith("/ask.html") for c in cmd) and "--window-size=640,460" in cmd and any(c.startswith("--user-data-dir=") for c in cmd), cmd
import jarvis_window
assert not jarvis_window.is_app_title("Jarvis Ask"), "the tray never mistakes the box for the big window"

from playwright.sync_api import sync_playwright
errs = []
with sync_playwright() as pw:
    br = pw.chromium.launch(); ctx = br.new_context(viewport={"width": 640, "height": 460}, permissions=["clipboard-read", "clipboard-write"])
    main = ctx.new_page(); main.on("pageerror", lambda e: errs.append("main: " + str(e)))
    main.goto(f"http://127.0.0.1:{PORT}/"); main.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); main.reload(); main.wait_for_timeout(500)
    chats_before = main.locator("#chat-list .chat-item").count()
    pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append("ask: " + str(e)))
    pg.goto(f"http://127.0.0.1:{PORT}/ask.html"); pg.wait_for_timeout(400)
    assert pg.title() == "Jarvis Ask" and pg.evaluate("document.activeElement.id") == "ask-input" and pg.is_visible("#ask-empty")
    pg.keyboard.type("capital of France?"); pg.keyboard.press("Enter")
    pg.wait_for_selector(".ask-tools button"); assert pg.locator(".ask-a pre").inner_text() == "print('hi')" and "Paris" in pg.inner_text(".ask-a")
    pg.click(".ask-tools button"); pg.wait_for_timeout(200); assert pg.evaluate("navigator.clipboard.readText()").startswith("Paris is the capital")
    pg.screenshot(path=str(tmp / "ask.png"))
    pg.keyboard.type("and how many people live there?"); pg.keyboard.press("Enter"); pg.wait_for_function("document.querySelectorAll('.ask-a').length===2 && document.querySelectorAll('.ask-tools').length===2")
    assert asked[-1][0] == "capital of France?" and asked[-1][1].startswith("and how many people live there?"), "a follow-up keeps the conversation"
    pg.keyboard.press("Escape"); pg.wait_for_timeout(300); assert hidden == [1], "Esc puts the box away"
    pg.reload(); pg.wait_for_timeout(400); assert pg.locator(".ask-a").count() == 2, "put away, not forgotten"
    # Open in Jarvis: a chat of its own in the big window, which shows it straight away
    pg.click("#ask-main"); pg.wait_for_timeout(600)
    assert shown == [1] and hidden == [1, 1] and pg.is_visible("#ask-empty")
    assert main.locator("#chat-list .chat-item").count() == max(chats_before, 1) and "About 2.1 million" in main.inner_text("#conversation"), "an empty, never-saved New chat gives way to it"
    assert main.locator("#chat-list .chat-item.active .chat-title").inner_text().startswith("capital of France")
    # French menus: the box speaks French, its window keeps its name (that is how Jarvis finds it)
    pg.evaluate("localStorage.setItem('jarvis-ui-lang','fr')"); pg.reload(); pg.wait_for_function("document.documentElement.lang === 'fr'")
    assert pg.title() == "Jarvis Ask" and pg.get_attribute("#ask-input", "placeholder") != "Ask Jarvis…"
    br.close()
assert not errs, errs
# only from the PC
c = http.client.HTTPConnection("127.0.0.1", PORT); c.request("POST", "/api/ask/open", "{}", {"Content-Type": "application/json"}); r = c.getresponse()
assert r.status == 200 and json.loads(r.read())["how"] == "not-windows"
print("ask ok", tmp)
os._exit(0)

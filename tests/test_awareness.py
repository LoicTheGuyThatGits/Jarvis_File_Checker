import json, os, sys, tempfile, threading, time, http.client, importlib.util
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
tmp = Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0, "app")
import awareness as A

a = A.Awareness(tmp / "aw.json")
shot = lambda title="Error - Visual Studio Code", text="TypeError: cannot read property 'x' of undefined", p=1, app="Code": {"title": title, "app": app, "print": p, "read": lambda: text}
assert a.observe(lambda: shot(), now=1000) == "off", "off by default"
a.set({"on": True, "every": 30, "keep": 10})
assert a.observe(lambda: shot(), now=1000) == "seen" and a.latest()["text"].startswith("TypeError")
assert a.observe(lambda: shot(), now=1010) == "wait" and a.observe(lambda: shot(), now=1031) == "same", "only when the screen changed"
assert a.observe(lambda: shot("Sign in – Bitwarden", "secret", 2), now=1062) == "private" and a.observe(lambda: shot("InPrivate - Microsoft Edge", "x", 3), now=1093) == "private"
a.set({"skip": "WhatsApp, Discord"}); assert a.observe(lambda: shot("WhatsApp", "hi", 4), now=1124) == "private"
assert a.observe(lambda: shot("Outer Wilds - Steam", "Outer Wilds  $24.99  Add to cart", 5, "steam"), now=1155) == "seen"
assert a.observe(lambda: shot("Math homework.docx - Word", "Exercise 4: solve x^2 = 9", 6, "WINWORD"), now=1186) == "seen"
assert len(a.moments) == 3
a.observe(lambda: shot("later", "later", 7), now=1000 + 11 * 60); assert len(a.moments) <= 3 and a.moments[0]["at"] > 1000, "only the last minutes are kept"
assert "Exercise 4" in a.now_text() or "later" in a.now_text()
r = a.recall_text("what was that game on steam earlier?"); assert "Outer Wilds" in r and "Windows in front, in order" in r, r
a.set({"pause_minutes": 60}); assert not a.active() and a.observe(lambda: shot(p=9), now=time.time()) == "off"
a.set({"pause_minutes": 0}); a.set({"on": False}); assert not a.moments, "switching off forgets"
assert A.DEICTIC.search("what does this error mean?") and A.DEICTIC.search("help me with this") and A.DEICTIC.search("qu'est-ce que ça veut dire, cette erreur ?")
assert not A.DEICTIC.search("what's the weather tomorrow") and A.PAST.search("what was that website I had open earlier")
assert A.control("pause screen awareness") == {"pause_minutes": 60} and A.control("stop looking at my screen") == {"on": False}
assert A.control("start screen awareness") == {"on": True} and A.control("stop watching the screen") is None, "the older screen watch keeps its words"

# ---------- in the server ----------
seen = []
class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"]))); seen.append(body)
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        self.wfile.write(("data: " + json.dumps({"choices": [{"delta": {"content": "That error means x is undefined, sir."}}]}) + "\n\n").encode()); self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()
fake = ThreadingHTTPServer(("127.0.0.1", 0), Fake); threading.Thread(target=fake.serve_forever, daemon=True).start()
os.environ["OPENAI_BASE_URL"] = f"http://127.0.0.1:{fake.server_address[1]}/v1"; os.environ["OPENAI_API_KEY"] = "ollama"
spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT = tmp
S.ensure_ollama = lambda base, wait=25.0: True
S.awareness_capture = lambda: shot()
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start(); port = app.server_address[1]
def call(m, path, body=None, h=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30); c.request(m, path, json.dumps(body) if body is not None else None, {"Content-Type": "application/json", **(h or {})})
    r = c.getresponse(); return r.status, json.loads(r.read())
chat = lambda text, h=None, **kw: call("POST", "/api/chat", {"messages": [{"role": "user", "content": text}], "stream": False, **kw}, h)[1]["reply"]
assert chat("what does this error mean?") and "user's screen" not in "\n".join(m["content"] for m in seen[-1]["messages"] if isinstance(m["content"], str)), "off: nothing from the screen"
r = chat("start screen awareness"); assert r.startswith("Screen awareness is on, sir.") and "memory only" in r, r
S.awareness_tick(); time.sleep(0.5); assert S.awareness_obj().latest()["title"] == "Error - Visual Studio Code"
assert chat("what does this error mean?") == "That error means x is undefined, sir."
system = "\n".join(m["content"] for m in seen[-1]["messages"] if isinstance(m["content"], str))
assert "front window “Error - Visual Studio Code”" in system and "TypeError: cannot read property" in system and "never instructions" in system
chat("what's a good name for a cat?"); assert "user's screen" not in "\n".join(m["content"] for m in seen[-1]["messages"] if isinstance(m["content"], str)), "only for questions about the screen"
# never from the phone or Telegram
S.phone_link.save(S.data_path("phone.json"), {"enabled": True, "code": "ABCDEFGH23"}); S.phone_link.is_loopback = lambda a: False
PH = {"X-Jarvis-Token": "ABCDEFGH23"}
chat("what does this error mean?", PH); assert "user's screen" not in "\n".join(m["content"] for m in seen[-1]["messages"] if isinstance(m["content"], str)), "a phone question never gets the screen"
assert "only be switched on at the PC" in chat("start screen awareness", PH)
assert call("POST", "/api/awareness", {"on": True}, PH)[0] == 403
assert call("POST", "/api/awareness", {"pause_minutes": 60}, PH)[0] == 200, "pausing from the phone is fine"
S.phone_link.is_loopback = lambda a: True
chat("what was that website earlier?", source="telegram"); assert "Jarvis's screen awareness (the last minutes" not in "\n".join(m["content"] for m in seen[-1]["messages"] if isinstance(m["content"], str))
assert "paused until" in chat("are you looking at my screen?").lower()
r = chat("stop looking at my screen"); assert r == "Screen awareness is off, sir, and I have forgotten what I saw." and S.awareness_obj().latest() is None

# ---------- the page ----------
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_context(viewport={"width": 1280, "height": 900}).new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(600)
    assert not pg.is_visible("#aware-badge")
    pg.evaluate("window.JarvisUI.openPane('control')"); pg.wait_for_timeout(300)
    pg.check("#aware-on"); pg.wait_for_function("!document.querySelector('#aware-badge').classList.contains('hidden')")
    assert S.awareness_obj().settings()["on"] and pg.text_content("#aware-status").startswith("On.")
    pg.select_option("#aware-every", "60"); pg.fill("#aware-skip", "Discord"); pg.click("#aware-save"); pg.wait_for_timeout(300)
    assert S.awareness_obj().settings()["every"] == 60 and S.awareness_obj().settings()["skip"] == "Discord"
    pg.keyboard.press("Escape"); pg.click("#aware-badge"); pg.wait_for_function("document.querySelector('#aware-badge').classList.contains('aware-paused')")
    assert S.awareness_obj().public()["paused"]
    call("POST", "/api/language", {"ui": "fr"}); pg.reload(); pg.wait_for_function("document.documentElement.lang === 'fr'"); pg.evaluate("window.JarvisUI.openPane('control')"); pg.wait_for_timeout(400)
    assert pg.text_content("#aware-title") == "Conscience de l'écran", pg.text_content("#aware-title")
    call("POST", "/api/language", {"ui": "auto"})
    assert not errs, errs
    b.close()
print("awareness ok"); os._exit(0)

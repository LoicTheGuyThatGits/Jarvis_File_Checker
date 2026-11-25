import json, os, sys, tempfile, threading, time, http.client, importlib.util
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
tmp = Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0, "app")

# a fake Ollama: streamed chat, /api/ps saying the model expires in 5 minutes (Ollama's default), /api/generate for loading
CHATS, LOADS = [], []
EXPIRES = {"at": "2026-11-25T21:40:00+01:00"}
class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def reply(self, obj):
        raw = json.dumps(obj).encode(); self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        if self.path == "/api/ps":
            return self.reply({"models": [{"name": "jarvis:latest", "size": 5.2e9, "size_vram": 4.68e9, "expires_at": EXPIRES["at"]}]})
        return self.reply({"data": [{"id": "jarvis:latest"}]})
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/api/generate":
            LOADS.append(body); EXPIRES["at"] = "2318-01-01T00:00:00Z"; return self.reply({"done": True})
        CHATS.append(body)
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        time.sleep(0.3)
        for word in "Certainly, sir. The capital of France is Paris, a city on the Seine.".split(" "):
            self.wfile.write(("data: " + json.dumps({"choices": [{"delta": {"content": word + " "}}]}) + "\n\n").encode()); self.wfile.flush(); time.sleep(0.02)
        self.wfile.write(b"data: [DONE]\n\n")
fake = ThreadingHTTPServer(("127.0.0.1", 0), Fake); threading.Thread(target=fake.serve_forever, daemon=True).start()
os.environ["OPENAI_BASE_URL"] = f"http://127.0.0.1:{fake.server_address[1]}/v1"; os.environ["OPENAI_API_KEY"] = "ollama"
spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT = tmp
S.ensure_ollama = lambda base, wait=25.0: True
(tmp / "data" / "settings.json").write_text(json.dumps({"provider": "local", "models": {"local": "jarvis:latest"}})); S.SETTINGS_LOADED_FROM = None
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start(); port = app.server_address[1]
def call(m, path, body=None, h=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=60); c.request(m, path, json.dumps(body) if body is not None else None, {"Content-Type": "application/json", **(h or {})})
    r = c.getresponse(); return r.status, json.loads(r.read())
history = [{"role": "user", "content": "Hello Jarvis"}, {"role": "assistant", "content": "Good evening, sir."}]

# ---------- 3. the start of the prompt stays the same from one answer to the next ----------
clock = {"t": "Right now it is 21:30."}
S.clock_module.prompt_line = lambda now=None: clock["t"]
st, d1 = call("POST", "/api/chat", {"messages": history + [{"role": "user", "content": "What is the capital of France?"}], "stream": False})
clock["t"] = "Right now it is 21:31."
st, d2 = call("POST", "/api/chat", {"messages": history + [{"role": "user", "content": "What is the capital of France?"}, {"role": "assistant", "content": d1["reply"]}, {"role": "user", "content": "And of Italy?"}], "stream": False})
a, b = CHATS[-2]["messages"], CHATS[-1]["messages"]
assert a[0] == b[0] and a[1:3] == b[1:3], "the instructions and the earlier conversation are sent the same way"
assert "21:30" not in a[0]["content"] and "21:31" not in b[0]["content"], "the time is not in the instructions any more"
assert b[-1]["content"].startswith("[Context from Jarvis for this message; the user did not write it]\nRight now it is 21:31.") and "[End of context]\n\nAnd of Italy?" in b[-1]["content"], repr(b[-1]["content"][:400])
assert b[3]["content"] == "What is the capital of France?", "earlier messages carry no context"

# ---------- 5. how fast it answered comes with the reply ----------
sp = d2["speed"]
assert sp["model"] == "jarvis:latest" and 0.2 <= sp["first_s"] < 5 and sp["wps"] and sp["wps"] > 5 and abs(sp["gpu"] - 0.9) < 0.01, sp

# ---------- 1. the chat model is kept loaded ----------
for _ in range(30):
    if LOADS: break
    time.sleep(0.1)
assert LOADS == [{"model": "jarvis:latest", "keep_alive": "-1"}], LOADS
call("POST", "/api/chat", {"messages": [{"role": "user", "content": "Thanks"}], "stream": False}); time.sleep(0.5)
assert len(LOADS) == 1, "not again within 10 minutes"
S.WARM["at"] = 0; call("POST", "/api/chat", {"messages": [{"role": "user", "content": "Thanks"}], "stream": False}); time.sleep(0.5)
assert len(LOADS) == 1, "already loaded with no time limit: nothing to do"
st, d = call("POST", "/api/speed", {"keep_loaded": False}); assert d["keep_loaded"] is False
S.WARM["at"] = 0; EXPIRES["at"] = "2026-11-25T21:45:00+01:00"
call("POST", "/api/chat", {"messages": [{"role": "user", "content": "Thanks"}], "stream": False}); time.sleep(0.5)
assert len(LOADS) == 1, "switched off: Jarvis leaves it to Ollama"
call("POST", "/api/speed", {"keep_loaded": True}); time.sleep(0.5); assert len(LOADS) == 2

# ---------- 2. Ollama's speed settings ----------
started = {}
class P:
    def __init__(self, args, env=None, **kw): started["args"], started["env"] = args, env
spec2 = importlib.util.spec_from_file_location("srv2", "app/server.py")
real_ensure = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(real_ensure)
real_ensure.ollama_program = lambda: ("/usr/bin/ollama", ["serve"]); real_ensure.ollama_up = lambda base: False
import subprocess as _sp
_popen, _sp.Popen = _sp.Popen, P                     # only for this one call: Playwright needs the real one
try:
    real_ensure.ensure_ollama("http://127.0.0.1:11434/v1", wait=0.01)
finally:
    _sp.Popen = _popen
assert started["env"]["OLLAMA_FLASH_ATTENTION"] == "1" and started["env"]["OLLAMA_KV_CACHE_TYPE"] == "q8_0" and started["env"]["OLLAMA_KEEP_ALIVE"] == "-1", started
st, d = call("GET", "/api/speed"); assert d == {"keep_loaded": True, "ollama_fast": False, "windows": False}, d
assert call("POST", "/api/speed", {"ollama_fast": True})[0] == 400, "Windows only"
S.phone_link.save(S.data_path("phone.json"), {"enabled": True, "code": "ABCDEFGH23"}); S.phone_link.is_loopback = lambda a: False
assert call("POST", "/api/speed", {"keep_loaded": False}, {"X-Jarvis-Token": "ABCDEFGH23"})[0] == 403
S.phone_link.is_loopback = lambda a: True

# ---------- the page ----------
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_context(viewport={"width": 1280, "height": 900}).new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(500)
    pg.fill("#message", "What is the capital of France?"); pg.keyboard.press("Enter")
    pg.wait_for_selector(".message-row.assistant .msg-speed")
    t = pg.text_content(".msg-speed"); assert "s to the first word" in t and "words/s" in t and "90 % on the graphics card" in t and pg.get_attribute(".msg-speed", "title") == "jarvis:latest", t
    pg.evaluate("window.JarvisUI.openPane('ai')"); pg.wait_for_timeout(400)
    assert pg.is_checked("#speed-keep") and pg.is_checked("#speed-show") and "speed settings are off" in pg.text_content("#speed-fast-note") and pg.is_hidden("#speed-fast")
    pg.uncheck("#speed-show"); pg.keyboard.press("Escape")
    pg.fill("#message", "And of Italy?"); pg.keyboard.press("Enter"); pg.wait_for_timeout(1500)
    assert pg.locator(".msg-speed").count() == 1, "hidden when switched off"
    assert not errs, errs
    b.close()
print("speed ok"); os._exit(0)

import json, os, sys, tempfile, threading, http.client, importlib.util, random
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
tmp = Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0, "app")
import debugtrace as D

# ---------- the thinking splitter ----------
text = "<think>Plan: be brief.\nThen answer.</think>\n\n{\"reply\": \"Hello <b>there</b>, sir.\"} <thinking>second</thinking> end"
random.seed(3)
for _ in range(300):
    sp = D.ThinkSplitter(); out = ""; i = 0
    while i < len(text):
        k = random.randint(1, 6); out += sp.feed(text[i:i + k]); i += k
    out += sp.flush()
    assert out == "{\"reply\": \"Hello <b>there</b>, sir.\"}  end", repr(out)
    assert sp.thought() == "Plan: be brief.\nThen answer.second", sp.thought()
sp = D.ThinkSplitter(); assert sp.feed("<think>never closed") == "" and sp.flush() == "" and sp.thought() == "never closed"
sp = D.ThinkSplitter(); assert sp.feed("a < b and <thin") == "a < b and " and sp.feed("g>") == "<thing>" and sp.flush() == ""
# ---------- traces ----------
assert D.active() is None and D.finish() is None
D.start("hi", "page"); D.step("tool", "ran x", "result " * 10); D.answered("x"); D.answered("y")
t = D.finish(200, "the reply")
assert t["answered_by"] == "x" and [s["kind"] for s in t["steps"]] == ["message", "tool"] and t["reply"] == "the reply" and "started" not in t and D.active() is None
assert D.recent()[0] is t or D.recent()[0] == t
caught = D.traced("thing_command", lambda q: "yes" if q == "a" else None)
D.start("a"); assert caught("a") == "yes" and caught("b") is None; t = D.finish()
assert t["answered_by"] == "thing_command" and t["steps"][-1]["text"] == "Caught by thing_command"
D.clear(); assert D.recent() == []

# ---------- a pretend model server (OpenAI style) that thinks ----------
seen = []
class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b'{"data":[]}')
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        seen.append(body)
        user = body["messages"][-1]["content"]
        if not body.get("stream"):                                 # Smart commands asking which tool fits
            answer = json.dumps({"steps": [{"tool": "add_task", "args": {"text": "pack my sports bag"}}]}) if "sports bag" in user else '{"steps": []}'
            out = json.dumps({"choices": [{"message": {"content": "<think>The person wants a task.</think>" + answer}}]}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out); return
        if "break please" in user:
            self.send_response(500); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b'{"error":{"message":"the model fell over"}}'); return
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        def send(delta):
            self.wfile.write(b"data: " + json.dumps({"choices": [{"delta": delta}]}).encode() + b"\n\n"); self.wfile.flush()
        send({"reasoning": "Reasoning first. "})
        for piece in ["<thi", "nk>A joke about ", "robots fits.</th", "ink>\n\n", '{"reply": "Why did the robot ', 'go on holiday? To recharge, sir.", "action": null}']:
            send({"content": piece})
        self.wfile.write(b"data: [DONE]\n\n")
fake = ThreadingHTTPServer(("127.0.0.1", 0), Fake); threading.Thread(target=fake.serve_forever, daemon=True).start()
os.environ.update({"JARVIS_LOCAL_BASE_URL": f"http://127.0.0.1:{fake.server_address[1]}/v1", "JARVIS_PROVIDER": "local", "JARVIS_LOCAL_MODEL": "thinker:1b"})

spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT = tmp
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start(); port = app.server_address[1]
def call(method, path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=60); c.request(method, path, json.dumps(body) if body is not None else None, {"Content-Type": "application/json"})
    r = c.getresponse(); return r.status, json.loads(r.read())
def chat(text, source=None, stream=False):
    body = {"messages": [{"role": "user", "content": text}], "stream": stream}
    if source: body["source"] = source
    if not stream:
        return call("POST", "/api/chat", body)
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=60); c.request("POST", "/api/chat", json.dumps(body), {"Content-Type": "application/json"})
    events = [json.loads(l) for l in c.getresponse().read().decode().splitlines() if l.strip()]
    return events
kinds = lambda tr: [s["kind"] for s in tr["steps"]]

# off: nothing is recorded
st, d = call("GET", "/api/debug"); assert d == {"enabled": False, "traces": []}
st, d = chat("tell me a joke"); assert st == 200 and "debug" not in d and "think" not in d["reply"].lower() and d["reply"].startswith("Why did the robot"), d
assert call("GET", "/api/debug")[1]["traces"] == []
# on, by chat
st, d = chat("turn on debug mode"); assert d["reply"].startswith("Debug mode is on") and S.debug_enabled()
st, d = chat("debug mode on", source="telegram"); assert "only be switched on or off at the PC" in d["reply"]
# the model, with its thinking
st, d = chat("tell me a joke"); tr = d["debug"]
assert d["reply"] == "Why did the robot go on holiday? To recharge, sir.", d["reply"]
assert tr["answered_by"] == "the AI model" and tr["message"] == "tell me a joke" and tr["total_ms"] >= 0
think = next(s for s in tr["steps"] if s["kind"] == "thinking")
assert "Reasoning first." in think["detail"] and "A joke about robots fits." in think["detail"], think
asked = next(s for s in tr["steps"] if s["kind"] == "model" and s["text"].startswith("Asking thinker:1b"))
assert "SYSTEM:" in asked["detail"] and "USER:\ntell me a joke" in asked["detail"]
raw = [s for s in tr["steps"] if s["kind"] == "model" and s["text"].startswith("Answer:")][0]
assert "<think>" not in raw["detail"] and '"reply"' in raw["detail"]
# streamed: the thinking never reaches the page, and the final event carries the trace
events = chat("tell me a joke", stream=True)
shown = "".join(e["text"] for e in events if e["type"] == "delta"); final = events[-1]
assert final["type"] == "final" and "robot" in shown and "think" not in shown.lower() and "Reasoning" not in shown and "thinking" in kinds(final["debug"]), (shown, final)
# a built-in command
st, d = chat("how many days until christmas"); tr = d["debug"]
assert "Christmas" in d["reply"] and tr["answered_by"] == "countdown_command" and "Caught by countdown_command" in [s["text"] for s in tr["steps"]] and "model" not in kinds(tr)[2:], tr
# Smart commands: what the model was asked, what it answered, and the tool that ran
S.SETTINGS["tool_router"] = True; S.save_settings(); S.ROUTER["registry"] = None
st, d = chat("I need to pack my sports bag"); tr = d["debug"]
assert "Added" in d["reply"] or "pack my sports bag" in d["reply"], d["reply"]
router = next(s for s in tr["steps"] if s["kind"] == "router")
assert "which tool fits" in router["text"] and "add_task" in router["detail"] and "The person wants a task." in router["detail"], router
tool = next(s for s in tr["steps"] if s["kind"] == "tool")
assert tool["text"].startswith("Ran the tool add_task(text='pack my sports bag')") and tr["answered_by"] == "Smart commands: add_task", tr
S.SETTINGS["tool_router"] = False; S.save_settings()
# an error keeps its trace
st, d = chat("break please"); assert st >= 400 and d["debug"]["steps"][-1]["kind"] == "error", (st, d)
# Telegram never gets the trace, but it is kept for Settings
st, d = chat("tell me a joke", source="telegram"); assert "debug" not in d
st, d = call("GET", "/api/debug"); assert d["enabled"] and d["traces"][0]["source"] == "telegram" and len(d["traces"]) == 7, [t["message"] for t in d["traces"]]
# Settings: clear and switch off
st, d = call("POST", "/api/debug", {"clear": True}); assert d["traces"] == [] and d["enabled"]
chat("tell me a joke"); st, d = call("POST", "/api/debug", {"on": False}); assert d == {"enabled": False, "traces": []} and not S.debug_enabled()
st, d = chat("tell me a joke"); assert "debug" not in d

# ---------- the page ----------
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_context(viewport={"width": 1280, "height": 900}).new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(500)
    pg.evaluate("window.JarvisUI.openPane('system')"); pg.wait_for_function("document.querySelector('#debug-status').textContent.length > 0")
    assert not pg.is_checked("#debug-on") and pg.text_content("#debug-status") == "Debug mode is off."
    pg.check("#debug-on"); pg.wait_for_function("document.querySelector('#debug-status').textContent.startsWith('Debug mode is on')"); assert S.debug_enabled()
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
    pg.fill("#message", "tell me a joke"); pg.keyboard.press("Enter")
    pg.wait_for_selector(".debug-trace", timeout=20000)
    summary = pg.text_content(".debug-trace > summary"); assert summary.startswith("Debug · ") and "answered by the AI model" in summary, summary
    assert "think" not in pg.evaluate("[...document.querySelectorAll('.message-row.assistant .bubble')].pop().textContent").lower()
    pg.click(".debug-trace > summary")
    assert pg.locator(".debug-step.debug-thinking").count() == 1 and pg.is_visible(".debug-thinking pre"), "the thinking is shown open"
    assert "A joke about robots fits." in pg.text_content(".debug-thinking pre")
    assert pg.locator(".debug-step.debug-model .debug-detail").count() >= 2
    ph = b.new_context(viewport={"width": 390, "height": 844}).new_page(); ph.goto(f"http://127.0.0.1:{port}/"); ph.wait_for_timeout(400)
    ph.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); ph.reload(); ph.wait_for_timeout(400)
    ph.fill("#message", "how many days until christmas"); ph.keyboard.press("Enter"); ph.wait_for_selector(".debug-trace", timeout=20000); ph.click(".debug-trace > summary")
    assert ph.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "no sideways scroll on a phone"
    pg.evaluate("window.JarvisUI.openPane('system')"); pg.wait_for_selector("#debug-list li")
    assert pg.locator("#debug-list li").count() == 2 and "tell me a joke" in pg.text_content("#debug-list")
    pg.locator("#debug-list li summary").last.click(); pg.wait_for_function("document.querySelectorAll('#debug-list li:last-child .debug-step').length >= 3")
    pg.click("#debug-clear"); pg.wait_for_function("document.querySelectorAll('#debug-list li').length === 0")
    pg.uncheck("#debug-on"); pg.wait_for_function("document.querySelector('#debug-status').textContent.startsWith('Debug mode is off')"); assert not S.debug_enabled()
    assert not errs, errs
    b.close()
print("debug ok"); os._exit(0)

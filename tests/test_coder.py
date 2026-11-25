import json, os, sys, tempfile, threading, time, http.client, importlib.util, urllib.request
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
tmp = Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0, "app")
import coder as C

# ---------- the pieces ----------
t, cmds = C.parse("Fixing it.\nREAD js/game.js 10-40\nEDIT js/game.js\n```js\n<<<<<<< FIND\na()\n=======\nb()\n>>>>>>> REPLACE\n```\nCHECK index.html then click #start; press ArrowUp\nDONE Done.\nPress Start.")
assert t == "Fixing it." and [c["cmd"] for c in cmds] == ["READ", "EDIT", "CHECK", "DONE"] and cmds[0]["from"] == 10 and cmds[2]["steps"] == ["click #start", "press ArrowUp"], cmds
assert cmds[3]["text"] == "Done.\nPress Start."
_, aider = C.parse("index.html\n```html\n<<<<<<< SEARCH\n<h1>Hi</h1>\n=======\n<h1>Hello</h1>\n>>>>>>> REPLACE\n```")
assert aider == [{"cmd": "EDIT", "path": "index.html", "body": "<<<<<<< SEARCH\n<h1>Hi</h1>\n=======\n<h1>Hello</h1>\n>>>>>>> REPLACE"}], "the aider way works too"
src = "function go() {\n    if (x) {\n        a();\n    }\n}\n"
assert C.apply_edit(src, "if (x) {\n    a();\n}", "if (x) {\n    b();\n}")[0] == "function go() {\n    if (x) {\n        b();\n    }\n}\n", "re-indented to fit"
assert C.apply_edit(src, "  3|         a();", "  3|         c();")[0].count("c();") == 1, "line numbers copied from READ are dropped"
for bad, why in (("zzz()", "not in the file"), ("", "FIND is empty")):
    try:
        C.apply_edit(src, bad, "q"); raise AssertionError(bad)
    except C.CoderError as e:
        assert why in str(e), e
try:
    C.safe_path(tmp, "../outside.txt"); raise AssertionError("outside")
except C.CoderError:
    pass
try:
    C.safe_path(tmp, "evil.bat", write=True); raise AssertionError("bat")
except C.CoderError:
    pass

# ---------- a fake Ollama that codes like a (small) model: a bug first, then the fix ----------
SCRIPT = []      # a list of functions (messages) -> answer
SEEN = []
class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        body = json.dumps({"data": [{"id": "qwen3.5:9b"}, {"id": "llama3.2:3b"}]}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/api/show":
            raw = json.dumps({"capabilities": ["completion", "vision", "tools"]}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw); return
        if self.path == "/api/chat":
            SEEN.append(body)
            answer = SCRIPT.pop(0)(body["messages"]) if SCRIPT else "DONE Nothing left."
            self.send_response(200); self.send_header("Content-Type", "application/x-ndjson"); self.end_headers()
            try:
                for i in range(0, len(answer), 40):
                    self.wfile.write((json.dumps({"message": {"role": "assistant", "content": answer[i:i + 40]}, "done": False}) + "\n").encode()); self.wfile.flush()
                    if SLOW["on"]:
                        time.sleep(0.2)
                self.wfile.write((json.dumps({"message": {"content": ""}, "done": True}) + "\n").encode())
            except OSError:
                pass                                   # Jarvis stopped reading (the Stop button)
            return
        raw = json.dumps({"choices": [{"message": {"content": "Hello, sir."}}]}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
SLOW = {"on": False}
fake = ThreadingHTTPServer(("127.0.0.1", 0), Fake); threading.Thread(target=fake.serve_forever, daemon=True).start()
os.environ["OPENAI_BASE_URL"] = f"http://127.0.0.1:{fake.server_address[1]}/v1"; os.environ["OPENAI_API_KEY"] = "ollama"
spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT = tmp
S.ensure_ollama = lambda base, wait=25.0: True
events = []
real_publish = S.publish_event
S.publish_event = lambda e: (events.append(e), real_publish(e))
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start(); port = app.server_address[1]
def call(m, path, body=None, h=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=60); c.request(m, path, json.dumps(body) if body is not None else None, {"Content-Type": "application/json", **(h or {})})
    r = c.getresponse(); return r.status, json.loads(r.read())
def wait_for(cond, secs=60):
    end = time.time() + secs
    while time.time() < end:
        d = call("GET", "/api/coder")[1]
        if cond(d):
            return d
        time.sleep(0.2)
    raise AssertionError("timed out: " + json.dumps(d["session"], default=str)[:1500])

PAGE = """<!doctype html>
<html><head><title>Clicker</title><link rel="stylesheet" href="css/style.css"></head>
<body>
<h1>Clicker</h1>
<p id="score">Score: 0</p>
<button id="start">Start</button>
<script src="js/game.js"></script>
</body></html>"""
GAME_BUG = """let score = 0;
document.getElementById('start').addEventListener('click', function () {
    score += 1;
    showScore(score);
});
"""
def turn1(msgs):
    assert "a clicker game" in msgs[1]["content"] and "the folder is empty" in msgs[1]["content"], msgs[1]["content"]
    return f"I will make the page and the script.\nWRITE index.html\n```html\n{PAGE}\n```\nWRITE css/style.css\n```css\nbody {{ font-family: sans-serif; }}\n```\nWRITE js/game.js\n```js\n{GAME_BUG}```\nCHECK index.html then click #start"
def turn2(msgs):
    last = msgs[-1]
    assert "Uncaught ReferenceError: showScore is not defined (js/game.js:4)" in last["content"], last["content"]
    assert last.get("images") and all("images" not in m for m in msgs[:-1]), "the screenshot goes with the latest check only"
    # copied with line numbers and less indentation, the way small models do
    return "showScore does not exist: I will set the text directly.\nEDIT js/game.js\n```js\n<<<<<<< FIND\n4|     showScore(score);\n=======\n4|     document.getElementById('score').textContent = 'Score: ' + score;\n>>>>>>> REPLACE\n```"
def turn3(msgs):
    last = msgs[-1]["content"]
    assert "[CHECK index.html] (automatic, after your changes)" in last and "No errors." in last, last
    assert "It now reads (lines" in last and "textContent = 'Score: ' + score;" in last
    return "Trying the button twice.\nCHECK index.html then click #start; click #start; check the score\nWRITE tools/count.py\n```python\nimport sys\nprint('files:', len(sys.argv))\n```\nRUN tools/count.py a b"
def turn4(msgs):
    last = msgs[-1]["content"]
    assert "Score: 2" in last and "Ran tools/count.py (exit code 0):\nfiles: 3" in last, last
    assert "No errors." in last and "Steps the checker cannot do (it only knows click, press, type, wait and scroll" in last and "check the score" in last, "a step it does not know is a note, not an error of the page"
    return "DONE A clicker game: press Start to add a point; the score shows under the title."
SCRIPT[:] = [turn1, turn2, turn3, turn4]

d = call("POST", "/api/coder", {"new": "Clicker"})[1]
s = d["session"]; assert s["name"] == "Clicker" and s["status"] == "ready" and d["model"] == "qwen3.5:9b" and d["has_recommended"], d
assert any(p["name"] == "Clicker" for p in d["projects"])
assert call("POST", "/api/coder", {"start": "make a clicker game with a score and a start button"})[0] == 200
d = wait_for(lambda d: d["session"]["pending"])
assert d["session"]["pending"]["command"] == "tools/count.py a b" and d["session"]["status"] == "waiting"
assert any("waiting for your OK" in e["text"] for e in events)
call("POST", "/api/coder", {"decide": "yes"})
d = wait_for(lambda d: d["session"]["status"] == "done")
s = d["session"]
kinds = [e["kind"] for e in s["log"]]
assert kinds.count("write") == 4 and "edit" in kinds and kinds.count("check") == 3 and "run" in kinds and kinds[-1] == "done", kinds
first_check = next(e for e in s["log"] if e["kind"] == "check")
assert not first_check["ok"] and "showScore is not defined" in first_check["detail"]
assert s["summary"].startswith("A clicker game") and sorted(s["changed"]) == ["css/style.css", "index.html", "js/game.js", "tools/count.py"]
assert "gpu" in call("GET", "/api/coder")[1], "the window shows how much of the model is on the graphics card"
assert s["check"]["errors"] == [] and s["check"]["shot"] and s["preview"].startswith("http://127.0.0.2:"), s["check"]
assert "document.getElementById('score').textContent = 'Score: ' + score;" in (tmp / "workspace" / "Clicker" / "js" / "game.js").read_text()
assert SEEN[0]["options"]["num_ctx"] == S.CODER_CTX and SEEN[0]["think"] is False and SEEN[0]["stream"] is True
assert any(e.get("chat") and e["text"].startswith("Jarvis Code: A clicker game") for e in events), "the end is said in the chat"
# the page is served on its own address, and cannot send commands to Jarvis
assert "<h1>Clicker</h1>" in urllib.request.urlopen(s["preview"]).read().decode()
origin = s["preview"].split("/p/")[0]
assert call("POST", "/api/memory", {"text": "x"}, {"Origin": origin})[0] == 403, "a page Jarvis built cannot use Jarvis"
# undo
call("POST", "/api/coder", {"undo": "last"}); assert not (tmp / "workspace" / "Clicker" / "tools" / "count.py").exists()
call("POST", "/api/coder", {"undo": "last"}); assert "showScore(score);" in (tmp / "workspace" / "Clicker" / "js" / "game.js").read_text(), "the edit is undone"
# PC only, and only in allowed folders
S.phone_link.save(S.data_path("phone.json"), {"enabled": True, "code": "ABCDEFGH23"}); S.phone_link.is_loopback = lambda a: False
assert call("GET", "/api/coder", None, {"X-Jarvis-Token": "ABCDEFGH23"})[0] == 403 and call("POST", "/api/coder", {"stop": True}, {"X-Jarvis-Token": "ABCDEFGH23"})[0] == 403
S.phone_link.is_loopback = lambda a: True
assert call("POST", "/api/coder", {"open": str(tmp / "app")})[0] == 400, "not a project folder"
st, d = call("POST", "/api/chat", {"messages": [{"role": "user", "content": "open Jarvis Code"}], "stream": False}); assert d["open"] == "/coder.html", d

# ---------- stop in the middle; an edit that keeps failing gets a hint ----------
SLOW["on"] = True
SCRIPT[:] = [lambda m: "Looking.\n" + "READ index.html\n" * 30]
call("POST", "/api/coder", {"start": "change the title"})
wait_for(lambda d: d["session"]["status"] == "working" and d["session"]["live"])
call("POST", "/api/coder", {"stop": True})
d = wait_for(lambda d: d["session"]["status"] == "stopped")
SLOW["on"] = False
bad_edit = "EDIT index.html\n```\n<<<<<<< FIND\n<h1>Nope</h1>\n=======\n<h1>Yes</h1>\n>>>>>>> REPLACE\n```"
SCRIPT[:] = [lambda m: bad_edit, lambda m: bad_edit, lambda m: (m[-1]["content"].count("keep failing") == 1 and "The closest lines" in m[-1]["content"] or print(m[-1]["content"])) and "DONE gave up"]
call("POST", "/api/coder", {"start": "change the title"})
d = wait_for(lambda d: d["session"]["status"] == "done"); assert d["session"]["summary"] == "gave up", d["session"]["summary"]

# ---------- the window ----------
from playwright.sync_api import sync_playwright
SCRIPT[:] = [lambda m: "WRITE index.html\n```html\n<h1>Hello from the page</h1>\n```", lambda m: "DONE Changed the title."]
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_context(viewport={"width": 1360, "height": 880}).new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(500)
    with pg.expect_popup() as pop:
        pg.click("#open-code")
    w = pop.value; w.on("pageerror", lambda e: errs.append(str(e)))
    w.wait_for_function("document.querySelector('#model-name').textContent === 'qwen3.5:9b'")
    assert w.is_hidden("#pull") and w.input_value("#project").endswith("Clicker")
    w.fill("#task", "say hello in the title"); w.click("#start")
    w.wait_for_function("document.querySelector('#summary-text').textContent.includes('Changed the title.')", timeout=60000)
    assert w.text_content("#status") == "Done." and w.is_visible("#undo-last")
    assert "Wrote index.html" in w.text_content("#log") and w.query_selector("#log .entry.check.good")
    w.wait_for_function("document.querySelector('#frame').src.startsWith('http://127.0.0.2:')")
    w.wait_for_timeout(500)
    assert "Hello from the page" in w.frame_locator("#frame").locator("h1").text_content()
    w.click("#tab-shot"); assert w.get_attribute("#shot", "src").startswith("data:image/jpeg;base64,")
    w.click("#tab-files"); w.wait_for_selector("#file-list button"); w.click("#file-list button:has-text('index.html')")
    w.wait_for_function("document.querySelector('#file-view').textContent.includes('Hello from the page')")
    w.click("#undo-last"); w.wait_for_timeout(600)
    assert "Clicker" in (tmp / "workspace" / "Clicker" / "index.html").read_text(), "undone from the window"
    w.click("#tab-browser"); w.click("#check"); w.wait_for_function("document.querySelector('#problems').textContent.includes('No errors')")
    call("POST", "/api/language", {"ui": "fr"}); pg.reload(); pg.wait_for_function("document.documentElement.lang === 'fr'"); w.reload()
    w.wait_for_function("document.querySelector('#start').textContent !== 'Start'")
    assert w.text_content("#tab-files") == "Fichiers" and w.get_attribute("#task", "placeholder").startswith("Que doit"), w.get_attribute("#task", "placeholder")
    call("POST", "/api/language", {"ui": "auto"})
    assert not errs, errs
    b.close()
S.CODER["browser"].close()
print("coder ok"); os._exit(0)

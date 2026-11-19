import json, os, shutil, sys, tempfile, threading, time, http.client, importlib.util
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
tmp = Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
(tmp / "tools").mkdir(exist_ok=True)
for name in ("bench_questions.json", "router_examples.json", "router_eval.py"):
    shutil.copy(Path("tools") / name, tmp / "tools" / name)
sys.path.insert(0, "app")
import bench as B

# ---------- the checks ----------
q = {"text": "What is the capital of Australia?", "expect": ["Canberra"], "max_words": 40}
assert B.checks(q, "Canberra, sir.") == [("no exclamation marks or emoji", True), ("at most 40 words", True), ("right answer (Canberra)", True)]
assert [ok for _, ok in B.checks(q, "It's Sydney! 😀")] == [False, True, False]
assert B.checks({"text": "x", "lang": "fr"}, "Bonjour monsieur, je vais très bien et vous ?")[-1] == ("answers in French", True)
assert B.checks({"text": "x", "lang": "fr"}, "Hello sir, I am fine and you?")[-1] == ("answers in French", False)
assert B.checks({"text": "Open Notepad.", "action": "open_app"}, '{"reply":"Opening it.","action":{"type":"open_app","name":"Notepad"}}') == [("asks for the open_app action", True)]
assert B.checks({"text": "x", "action": "open_app"}, "I have opened Notepad for you.") == [("asks for the open_app action", False)]
assert B.checks({"text": "x", "code": "python"}, "Here:\n```python\ndef r(s):\n    return s[::-1]\n```") == [("code in a ```python block", True)]
assert B.checks({"text": "x", "code": "python"}, "def r(s): return s[::-1]") == [("code in a ```python block", False)]
assert B.checks({"text": "x"}, "if a != b: fine")[0][1] is True, "!= in prose is not an exclamation"
qs = B.load_questions(Path("tools/bench_questions.json")); assert len(qs) == 20 and all(x["source"] == "built-in" for x in qs)
# your own questions come from the training log, newest first, without repeats, chat only
logdir = tmp / "data" / "training"; logdir.mkdir(parents=True)
entries = [{"kind": "chat", "messages": [{"role": "user", "content": f"question {i}"}]} for i in range(15)] + [{"kind": "research", "messages": [{"role": "user", "content": "web thing"}]},
          {"kind": "chat", "messages": [{"role": "user", "content": "question 14"}]}]
(logdir / "exchanges-2026-11.jsonl").write_text("\n".join(json.dumps(e) for e in entries) + "\n")
own = B.own_questions(logdir, 10)
assert [o["text"] for o in own] == [f"question {i}" for i in range(14, 4, -1)] and all(o["source"] == "mine" for o in own), own

# ---------- running a comparison (two pretend models) ----------
def fake_ask(model, system, user):
    if model == "broken":
        raise OSError("model not found")
    time.sleep(0.01)
    good = model == "good"
    if "Australia" in user:
        return ("Canberra, sir." if good else "Sydney! 🎉"), 0.5 if good else 2.0, 5
    if "Notepad" in user:
        return ('{"reply":"Opening Notepad.","action":{"type":"open_app","name":"Notepad"}}' if good else "Sure! Opening Notepad."), 0.4, 20
    return ("Very well, sir." if good else "Sure thing!!!"), 0.6 if good else 1.5, 6
qs = [{"text": "What is the capital of Australia?", "expect": ["Canberra"]}, {"text": "Open Notepad.", "action": "open_app"}, {"text": "Hello"}]
bench = B.Bench(tmp / "bench", fake_ask, smart=lambda model, limit: {"right_tool_pct": 90.0 if model == "good" else 40.0, "false_alarm_pct": 0.0, "examples": limit})
assert bench.state()["run"] is None
assert bench.start(["good", "chatty", "broken"], qs, "SYSTEM", smart_limit=5) == "Comparing 3 models on 3 questions."
try:
    bench.start(["good"], qs, "S"); raise AssertionError("two at once")
except ValueError:
    pass
for _ in range(200):
    if not bench.state()["running"]: break
    time.sleep(0.02)
st = bench.state(); run = st["run"]
assert st["step"] == "done" and st["done"] == st["total"] == 12, st
s = run["summary"]
assert s["good"]["checks_pct"] == 100 and s["chatty"]["checks_pct"] < 50 and s["good"]["avg_seconds"] < s["chatty"]["avg_seconds"], s
assert s["good"]["tokens_per_second"] == round(31 / 1.5, 1), s["good"]
assert s["broken"]["errors"] == 3 and s["broken"]["answered"] == 0 and run["questions"][0]["answers"]["broken"]["error"] == "model not found"
assert run["smart"]["good"]["right_tool_pct"] == 90.0 and s["good"]["smart"]["right_tool_pct"] == 90.0
assert (tmp / "bench" / f"{run['id']}.json").exists()
# picking the best answer (blind in the page; stored by model)
run = bench.pick(run["id"], 0, "good"); run = bench.pick(run["id"], 2, "good"); run = bench.pick(run["id"], 2, "chatty")
assert run["summary"]["good"]["picks"] == 1 and run["summary"]["chatty"]["picks"] == 1
for bad in (("nope", 0, "good"), (run["id"], 9, "good"), (run["id"], 0, "other")):
    try:
        bench.pick(*bad); raise AssertionError(bad)
    except ValueError:
        pass
fresh = B.Bench(tmp / "bench", fake_ask); assert fresh.state()["run"]["id"] == run["id"], "the latest is shown after a restart"
text = B.report(run); assert "good" in text and "100%" in text and "Checks not passed:" in text and "chatty: no exclamation marks or emoji" in text, text
# stopping early
slow = B.Bench(tmp / "bench2", lambda m, s, u: (time.sleep(0.2), ("ok", 0.2, 1))[1])
slow.start(["a"], [{"text": str(i)} for i in range(20)], "S"); time.sleep(0.5); slow.stop()
for _ in range(100):
    if not slow.state()["running"]: break
    time.sleep(0.05)
assert slow.state()["run"]["stopped"] and slow.state()["step"] == "stopped"
for bad in (([], qs), (["a"], [])):
    try:
        B.Bench(tmp / "b3", fake_ask).start(bad[0], bad[1], "S"); raise AssertionError(bad)
    except ValueError:
        pass

# ---------- in the server, against a pretend Ollama ----------
asked = []
class O(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def reply(self, body):
        d = json.dumps(body).encode(); self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(d))); self.end_headers(); self.wfile.write(d)
    def do_GET(self):
        self.reply({"models": [{"name": "jarvis:latest"}, {"name": "llama3.2:3b"}, {"name": "nomic-embed-text:latest"}]} if self.path == "/api/tags" else {"data": []})
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        asked.append(body)
        user = body["messages"][-1]["content"]
        if body.get("response_format"):           # Smart commands
            content = '{"steps": []}'
        elif "Australia" in user:
            content = "Canberra, sir." if body["model"].startswith("jarvis") else "Sydney!"
        else:
            content = "Very well, sir."
        self.reply({"choices": [{"message": {"content": content}}], "usage": {"completion_tokens": 4}})
o = ThreadingHTTPServer(("127.0.0.1", 0), O); threading.Thread(target=o.serve_forever, daemon=True).start()
os.environ["JARVIS_LOCAL_BASE_URL"] = f"http://127.0.0.1:{o.server_address[1]}/v1"; os.environ["JARVIS_LOCAL_MODEL"] = "jarvis"; os.environ["JARVIS_PROVIDER"] = "local"
spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT = tmp
S.ensure_ollama = lambda base, wait=25.0: True
assert "Address the user as" in S.local_chat_instructions() and "ONLY when the user clearly asks you to do something on the PC" in S.local_chat_instructions()
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start(); port = app.server_address[1]
def call(method, path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=60); c.request(method, path, json.dumps(body) if body is not None else None, {"Content-Type": "application/json"})
    r = c.getresponse(); return r.status, json.loads(r.read())
st, d = call("GET", "/api/bench")
assert st == 200 and d["models"] == ["jarvis:latest", "llama3.2:3b"] and d["current"] == "jarvis" and d["own_available"] == 10 and d["run"] is None, d
st, d = call("POST", "/api/bench", {"start": {"models": ["jarvis:latest", "llama3.2:3b"], "set": "built-in", "smart": True}})
assert st == 200 and d["running"], d
for _ in range(600):
    st, d = call("GET", "/api/bench")
    if not d["running"]: break
    time.sleep(0.1)
run = d["run"]
assert len(run["questions"]) == 20 and run["summary"]["jarvis:latest"]["answered"] == 20, run["summary"]
q0 = next(q for q in run["questions"] if "Australia" in q["text"])
assert ["right answer (Canberra)", True] in q0["answers"]["jarvis:latest"]["checks"] and ["right answer (Canberra)", False] in q0["answers"]["llama3.2:3b"]["checks"]
assert run["smart"]["jarvis:latest"]["examples"] == 40 and "right_tool_pct" in run["smart"]["jarvis:latest"]
chat_calls = [a for a in asked if not a.get("response_format") and len(a["messages"]) == 2]
assert chat_calls and all(a["messages"][0]["content"].startswith("You are Jarvis") for a in chat_calls), "asked with Jarvis's own chat instructions"
assert {a["model"] for a in asked if a.get("response_format")} == {"jarvis:latest", "llama3.2:3b"}, "Smart commands asked each model, not the one in use"
st, d = call("POST", "/api/bench", {"pick": {"run": run["id"], "index": 1, "model": "llama3.2:3b"}}); assert d["run"]["summary"]["llama3.2:3b"]["picks"] == 1
st, d = call("POST", "/api/bench", {"start": {"models": [], "set": "built-in"}}); assert st == 400 and "at least one" in d["error"]
assert len(S.bench_questions("both")) == 30 and S.bench_questions("mine")[0]["text"] == "question 14"

# ---------- the page ----------
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_context(viewport={"width": 1280, "height": 900}).new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(500)
    pg.evaluate("window.JarvisUI.openPane('ai')"); pg.wait_for_selector("#bench-models label")
    assert pg.locator("#bench-models label").count() == 2 and pg.is_checked("#bench-models input[value='jarvis:latest']")
    pg.wait_for_selector(".bench-table")
    assert pg.locator(".bench-table tbody tr").count() == 2 and pg.locator("details.bench-q").count() == 20
    first = pg.locator("details.bench-q").nth(0); first.locator("summary").click()
    heads = first.locator(".bench-ans-head strong").all_text_contents()
    assert sorted(heads) == ["Answer A", "Answer B"], "blind until you pick"
    first.locator(".bench-pick").first.click()
    pg.wait_for_function("document.querySelectorAll('details.bench-q')[0].querySelector('.bench-pickmark') !== null")
    first = pg.locator("details.bench-q").nth(0)
    assert first.evaluate("d => d.open"), "stays open after picking"
    assert sorted(first.locator(".bench-ans-head strong").all_text_contents()) == ["jarvis:latest", "llama3.2:3b"], (first.inner_html()[:600], "names shown after the pick")
    pg.select_option("#bench-set", "mine"); pg.uncheck("#bench-models input[value='llama3.2:3b']"); pg.click("#bench-start")
    pg.wait_for_function("document.querySelectorAll('details.bench-q').length === 10", timeout=30000)
    assert "question 14" in pg.text_content("details.bench-q") and "(yours)" in pg.text_content("details.bench-q")
    ph = b.new_context(viewport={"width": 390, "height": 844}).new_page(); ph.goto(f"http://127.0.0.1:{port}/"); ph.wait_for_timeout(400)
    ph.evaluate("window.JarvisUI.openPane('ai')"); ph.wait_for_selector(".bench-table")
    assert ph.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "no sideways scroll on a phone"
    assert not errs, errs
    b.close()
print("model bench ok"); os._exit(0)

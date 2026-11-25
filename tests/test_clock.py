import json, os, sys, tempfile, threading, http.client, importlib.util
from datetime import datetime, timedelta
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
tmp = Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0, "app")
import clock as C, planner as P, french as fr

now = datetime(2026, 11, 23, 12, 45)
ask = lambda q: C.command(q, now, P.parse_when)
for q in ("what time is it?", "Jarvis, what's the time", "time", "what time is it now", "can you tell me the time please", "do you know what time it is"):
    assert ask(q) == "It is 12:45, sir.", (q, ask(q))
for q in ("what's the date", "what is today's date", "what day is it", "what day is it today", "what's today", "date", "what's the date today, sir?"):
    assert ask(q) == "Today is Monday 23 November 2026, sir.", (q, ask(q))
assert ask("what's the date tomorrow") == ask("what day is tomorrow") == "Tomorrow will be Tuesday 24 November 2026, sir."
assert ask("what day was it yesterday") == "Yesterday was Sunday 22 November 2026, sir."
assert ask("what year is it") == "It is 2026, sir." and ask("what month is it") == "It is November 2026, sir." and ask("what week is it") == "It is week 48 of 2026, sir."
assert ask("what's the date and time") == "It is 12:45 on Monday 23 November 2026, sir."
assert ask("what day is 25 December") == "25 December 2026 will be a Friday, sir."
assert ask("what day was 1 november") == "1 November 2026 was a Sunday, sir.", "“was”: the last one, not next year's"
for q in ("what time is my next class", "what time is the meeting", "set a timer", "what's the weather", "what day is my exam", "time to go", "date night ideas"):
    assert ask(q) is None, q
line = C.prompt_line(now); assert "Monday 23 November 2026, 12:45" in line and "week 48" in line and "never assume another date" in line
for f, e in (("quelle heure est-il ?", "what time is it"), ("il est quelle heure", "what time is it"), ("quelle est la date d'aujourd'hui", "what's the date"),
             ("on est le combien ?", "what's the date"), ("quel jour sommes-nous", "what's the date"), ("quel jour on sera demain", "what's the date tomorrow"),
             ("en quelle année sommes-nous", "what year is it"), ("quel jour tombe le 25 décembre", "what day is 25 december")):
    assert fr.to_english(f) == e, (f, fr.to_english(f))

# ---------- through the server: the PC's clock, never the model's guess ----------
seen = []
class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"]))); seen.append(body)
        if not body.get("stream"):
            raw = json.dumps({"choices": [{"message": {"content": "Il est 12 h 45, monsieur."}}]}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw); return
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        self.wfile.write(("data: " + json.dumps({"choices": [{"delta": {"content": "It is 2023, sir."}}]}) + "\n\n").encode()); self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()
fake = ThreadingHTTPServer(("127.0.0.1", 0), Fake); threading.Thread(target=fake.serve_forever, daemon=True).start()
os.environ["OPENAI_BASE_URL"] = f"http://127.0.0.1:{fake.server_address[1]}/v1"; os.environ["OPENAI_API_KEY"] = "ollama"
spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT = tmp
S.ensure_ollama = lambda base: None
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start()
def chat(text):
    c = http.client.HTTPConnection("127.0.0.1", app.server_address[1], timeout=30)
    c.request("POST", "/api/chat", json.dumps({"messages": [{"role": "user", "content": text}], "stream": False}), {"Content-Type": "application/json"})
    return json.loads(c.getresponse().read())["reply"]
before = len(seen)
r = chat("what time is it?"); t = datetime.now()
assert r in (f"It is {t.strftime('%H:%M')}, sir.", f"It is {(t - timedelta(minutes=1)).strftime('%H:%M')}, sir."), r
assert chat("what's the date") == f"Today is {C.long_date(datetime.now().date())}, sir."
assert len(seen) == before, "the model was not asked"
r = chat("quelle heure est-il ?"); assert r.startswith("Il est ") and r.endswith(", monsieur.") and len(seen) == before, ("French: the PC's answer, in French without asking the model", r)
chat("how old is someone born in 2010?")
system = "\n".join(m["content"] for m in seen[-1]["messages"] if isinstance(m["content"], str))
assert f"{C.long_date(datetime.now().date())}" in system and "never assume another date" in system, "the model gets the real date for everything else"
print("clock ok"); os._exit(0)

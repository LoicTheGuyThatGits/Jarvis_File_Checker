import json, os, sys, tempfile, threading, time, http.client, importlib.util
from datetime import datetime
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
tmp = Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0, "app")
import calls as C, french as fr

# ---------- the call state ----------
clock = [1000.0]
c = C.Calls(tmp / "calls-unit.json", clock=lambda: clock[0])
events, missed = [], []
c.publish, c.on_missed = events.append, missed.append
assert c.settings() == C.DEFAULTS
call = c.ring("Wake up", "Good morning, sir.")
assert call["state"] == "ringing" and call["targets"] == ["pc", "phone"] and call["ring_until"] == 1040 and events[-1]["type"] == "call"
again = c.ring("Second", "Hello again.")                              # a newer ring replaces the one still ringing
assert c.recent()[0]["state"] == "replaced" and len(c.current()) == 1 and c.current()[0]["id"] == again["id"]
assert c.answer(again["id"], "phone")["state"] == "active"
try:
    c.answer(again["id"], "pc"); raise AssertionError("answered twice")
except C.CallError as exc:
    assert "already answered on the phone" in str(exc)
said = c.ring("Reminder", "Sir, the oven.")                           # on a call: Jarvis says it there
assert said["said"] == "Sir, the oven." and events[-1]["say"] == "Sir, the oven." and events[-1]["id"] == again["id"]
clock[0] += 30; c.heartbeat(again["id"]); c.tick(); assert c.current()[0]["state"] == "active"
clock[0] += C.SILENT_AFTER + 1; ended = c.tick(); assert ended and ended[0]["state"] == "ended" and not c.current(), "the page went away"
r = c.ring("Late", "Hello."); clock[0] += 41; c.tick()
assert c.recent()[0]["state"] == "missed" and missed[-1]["id"] == r["id"]
r = c.ring("Declined", "Hello."); c.decline(r["id"], "pc"); assert missed[-1]["state"] == "declined"
p = c.place("pc"); assert p["direction"] == "to_jarvis" and p["state"] == "active"
c.hangup(p["id"]); assert c.recent()[0]["state"] == "ended" and c.recent()[0]["seconds"] == 0
r = c.ring("x", "y"); c.hangup(r["id"]); assert c.recent()[0]["state"] == "cancelled"
n = len(missed); c.update({"telegram_fallback": False}); r = c.ring("x", "y"); clock[0] += 99; c.tick(); assert len(missed) == n, "no Telegram when it is off"
c.update({"ring_pc": False}); assert c.ring("x", "y")["targets"] == ["phone"]
for bad in ({"ring_phone": False}, {"ring_seconds": 5}, {"on": "yes"}):
    try:
        c.update(bad); raise AssertionError(bad)
    except ValueError:
        pass
c.update({"on": False})
try:
    c.ring("x", "y"); raise AssertionError("calls are off")
except C.CallError as exc:
    assert "switched off" in str(exc)
# the phone's long poll returns as soon as something rings
c.update({"on": True, "ring_pc": True}); [c.hangup(x["id"]) for x in c.current()]
v = c.version; got = {}
th = threading.Thread(target=lambda: got.update(c.wait(v, 10))); th.start(); time.sleep(0.2)
assert c.waiting == 1
t0 = time.time(); c.ring("Poll", "Hi."); th.join(3)
assert time.time() - t0 < 1 and got["calls"][0]["reason"] == "Poll" and got["version"] > v and c.waiting == 0
assert c.wait(c.version, 0.2)["version"] == c.version
assert C.opening_for("Wake up", time.strptime("2026-11-21 06:45", "%Y-%m-%d %H:%M")) == "Good morning, sir. It is 06:45, time to wake up."
assert C.opening_for("check the oven", time.localtime(), "boss") == "Hello, boss. You asked me to call you: check the oven."
assert C.opening_for("Call", time.strptime("2026-11-21 16:05", "%Y-%m-%d %H:%M")).startswith("Hello, sir. You asked me to call you at 16:05.")
# ---------- French ----------
now = datetime(2026, 11, 20, 9)
for q, want in {"appelle-moi": "call me", "appelle-moi demain à 6h45 pour me réveiller": "call me tomorrow at 6:45am to wake me up",
                "appelle-moi dans 20 minutes pour sortir le gâteau": "call me in 20 minutes to sortir le gâteau",
                "réveille-moi avec un appel à 7h": "call me at 7:00am to wake me up", "annule mon appel de réveil": "cancel my calls",
                "quand vas-tu m'appeler": "when will you call me", "raccroche": "hang up", "appelle-moi avec le briefing": "call me with the briefing"}.items():
    assert fr.to_english(q, now) == want, (q, fr.to_english(q, now))

# ---------- a pretend model, to see what a call asks of it ----------
asked = []
class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b'{"data":[]}')
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"]))); asked.append(body)
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        piece = json.dumps({"reply": "Why did the robot go on holiday? To recharge, sir.", "action": None})
        self.wfile.write(b"data: " + json.dumps({"choices": [{"delta": {"content": piece}}]}).encode() + b"\n\ndata: [DONE]\n\n")
fake = ThreadingHTTPServer(("127.0.0.1", 0), Fake); threading.Thread(target=fake.serve_forever, daemon=True).start()
os.environ.update({"JARVIS_LOCAL_BASE_URL": f"http://127.0.0.1:{fake.server_address[1]}/v1", "JARVIS_PROVIDER": "local", "JARVIS_LOCAL_MODEL": "fake:1b"})

spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT = tmp
telegram = []; S.phone_notify = lambda text: telegram.append(text) or True
opened = []; S.open_app_window = lambda: opened.append(1) or True
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start(); port = app.server_address[1]
def call(method, path, body=None):
    h = http.client.HTTPConnection("127.0.0.1", port, timeout=30); h.request(method, path, json.dumps(body) if body is not None else None, {"Content-Type": "application/json"})
    r = h.getresponse(); return r.status, json.loads(r.read())
chat = lambda text, source=None: call("POST", "/api/chat", {"messages": [{"role": "user", "content": text}], "stream": False, **({"source": source} if source else {})})[1]["reply"]
obj = S.calls_obj()
def ringing():
    return [x for x in obj.current() if x["state"] == "ringing"]
def clear():
    for x in obj.current():
        obj.hangup(x["id"])

assert chat("call me") == "Calling you now, sir." and ringing()[0]["opening"] == "Here I am, sir. What can I do for you?" and opened, "no page open: the window is opened to ring"
assert chat("call me", source="call") == "We are already on a call, sir."
clear()
r = chat("call me tomorrow at 6:45 to wake me up"); assert r.startswith("Very good, sir. I will call you tomorrow at 6:45") and r.endswith("to wake you up."), r
item = [i for i in S.reminders_active() if i.get("call")][-1]
assert datetime.fromtimestamp(item["due"]).hour == 6 and item["text"] == "Wake up", "the morning, not 18:45"
r = chat("call me in 20 minutes to check the oven"); assert r == "Very good, sir. I will call you in 20 minutes: “check the oven”.", r
r = chat("remind me to leave for school in 10 minutes by calling me"); assert "call you" in r and "remind you" not in r, r
assert [i for i in S.reminders_active() if i["text"] == "leave for school"][0]["call"]
r = chat("wake me up with a call at 7"); assert "to wake you up" in r, r
r = chat("appelle-moi dans une heure pour réviser"); assert "réviser" in r and ("appellerai" in r or "call" in r.lower() or "appeler" in r), r
listing = chat("when will you call me"); assert listing.startswith("I will call you, sir:") and "check the oven" in listing and "Wake up" in listing, listing
assert "(I will call you)" in chat("what reminders do I have")
assert chat("call me") .startswith("Calling")
assert chat("hang up") == "Hung up, sir." and not obj.current()
assert chat("cancel my calls").startswith("Cancelled 5 planned calls") and chat("when will you call me") == "I have no calls planned, sir."
assert chat("call me Tony") != "Calling you now, sir.", "a name is not a call"
# a planned call rings when it is due; nobody answers → Telegram
S.reminder_add("reminder", time.time() + 1, "check the oven", call=True)
S.check_due(time.time() + 2)
rg = ringing(); assert rg and rg[0]["opening"] == "Hello, sir. You asked me to call you: check the oven." and rg[0]["reason"] == "check the oven"
assert not S.unacked_events(), "the call takes care of it: no alert on top"
obj.tick(time.time() + 100)
assert telegram[-1] == "📞 You missed a call from Jarvis. Hello, sir. You asked me to call you: check the oven.", telegram
# calls switched off: an ordinary reminder instead
obj.update({"on": False}); S.reminder_add("reminder", time.time() + 1, "the bins", call=True); fired = S.check_due(time.time() + 2)
assert fired and fired[0]["text"] == "the bins" and not ringing(); obj.update({"on": True})
assert chat("call me").startswith("Calls from Jarvis are switched off") is False
clear()
# “call me with the briefing” reads the briefing
r = chat("call me with the briefing"); assert r == "Calling you now, sir." and ringing()[0]["opening"], r
clear()
# ---------- the API ----------
st, d = call("GET", "/api/call"); assert d["settings"]["on"] and d["calls"] == [] and d["recent"] and d["phone_listening"] is False
st, d = call("POST", "/api/call", {"action": "test"}); test_id = d["call"]["id"]; assert d["call"]["state"] == "ringing"
st, d = call("POST", "/api/call", {"action": "answer", "id": test_id}); assert d["call"]["state"] == "active" and d["call"]["device"] == "pc"
st, d = call("POST", "/api/call", {"action": "heartbeat", "id": test_id}); assert st == 200
st, d = call("POST", "/api/call", {"action": "hangup", "id": test_id}); assert d["call"]["state"] == "ended"
st, d = call("POST", "/api/call", {"action": "hangup", "id": test_id}); assert st == 409
st, d = call("POST", "/api/call", {"action": "place"}); assert d["call"]["direction"] == "to_jarvis" and d["greeting"].startswith("Good ")
call("POST", "/api/call", {"action": "hangup", "id": d["call"]["id"]})
st, d = call("POST", "/api/call", {"action": "settings", "settings": {"ring_pc": False, "ring_phone": False}}); assert st == 400 and "at least one" in d["error"]
st, d = call("POST", "/api/call", {"action": "nonsense"}); assert st == 400
got = {}
th = threading.Thread(target=lambda: got.update(call("GET", f"/api/call/wait?since={obj.version}&timeout=10")[1])); th.start(); time.sleep(0.3)
assert call("GET", "/api/call")[1]["phone_listening"] is True, "a phone waiting counts as listening"
chat("call me"); th.join(5); assert got["calls"] and got["calls"][0]["state"] == "ringing"
clear()
# on a call, the model is told to talk, not to write
asked.clear(); r = chat("tell me a joke", source="call"); assert r.startswith("Why did the robot")
assert "live voice call" in asked[-1]["messages"][0]["content"]
asked.clear(); chat("tell me a joke"); assert "live voice call" not in asked[-1]["messages"][0]["content"]

# ---------- the page ----------
FAKES = """
window.__phrases = []; window.__spoken = [];
class FakeSR { constructor(){ this.onresult=null; this.onend=null; this.onerror=null; }
  start(){ const self=this; const tick=()=>{ if(self._stopped) return; const p=window.__phrases.shift(); if(p===undefined){ setTimeout(tick,60); return; }
    if(p) self.onresult && self.onresult({resultIndex:0, results:[Object.assign([{transcript:p}],{isFinal:true})]}); self.onend && self.onend(); }; setTimeout(tick,80); }
  abort(){ this._stopped=true; } stop(){ this._stopped=true; } }
window.SpeechRecognition = FakeSR; window.webkitSpeechRecognition = FakeSR;
window.SpeechSynthesisUtterance = class { constructor(t){ this.text=t; } };
Object.defineProperty(window, 'speechSynthesis', { configurable: true, value: { speak(u){ window.__spoken.push(u.text); setTimeout(()=>u.onend && u.onend(), 40); }, cancel(){}, getVoices(){ return []; },
  addEventListener(){}, removeEventListener(){}, speaking:false, pending:false } });
"""
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch(); ctx = b.new_context(viewport={"width": 1280, "height": 900}); ctx.add_init_script(FAKES); pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(600)
    # you call Jarvis
    pg.click("#call-button"); pg.wait_for_selector("#call-screen:not(.hidden)")
    pg.wait_for_function("document.querySelector('#call-screen').dataset.phase === 'listening'")
    assert pg.text_content("#call-jarvis").startswith("Good ") and any(t.startswith("Good ") for t in pg.evaluate("window.__spoken"))
    pg.evaluate("window.__phrases.push('tell me a joke')")
    pg.wait_for_function("document.querySelector('#call-jarvis').textContent.startsWith('Why did the robot')", timeout=15000)
    assert pg.text_content("#call-you") == "tell me a joke"
    pg.wait_for_function("document.querySelector('#call-screen').dataset.phase === 'listening'")
    pg.evaluate("window.__phrases.push('okay goodbye Jarvis')")
    pg.wait_for_function("document.querySelector('#call-screen').classList.contains('hidden')", timeout=10000)
    assert "Goodbye, sir." in pg.evaluate("window.__spoken")
    assert "☎ Call ·" in pg.text_content("#chat-list"), "the call is saved as a chat"
    assert obj.recent()[0]["direction"] == "to_jarvis" and obj.recent()[0]["state"] == "ended"
    # Jarvis calls you
    call("POST", "/api/call", {"action": "test"})
    pg.wait_for_selector("#call-incoming:not(.hidden)"); assert pg.text_content("#call-state") == "Jarvis is calling you…"
    pg.click("#call-accept"); pg.wait_for_function("document.querySelector('#call-jarvis').textContent.startsWith('This is a test call')")
    pg.wait_for_function("document.querySelector('#call-screen').dataset.phase === 'listening'")
    # something comes up during the call: Jarvis says it there
    S.reminder_add("reminder", time.time() + 1, "the pasta", call=True); S.check_due(time.time() + 2)
    pg.wait_for_function("document.querySelector('#call-jarvis').textContent.includes('the pasta')")
    pg.click("#call-hangup"); pg.wait_for_function("document.querySelector('#call-screen').classList.contains('hidden')")
    assert not obj.current()
    # answered on the phone: the PC stops ringing
    r = call("POST", "/api/call", {"action": "test"})[1]["call"]
    pg.wait_for_selector("#call-incoming:not(.hidden)")
    obj.answer(r["id"], "phone"); pg.wait_for_function("document.querySelector('#call-state').textContent === 'Answered on the phone.'")
    pg.wait_for_function("document.querySelector('#call-screen').classList.contains('hidden')"); clear()
    # declined at the PC → Telegram
    n = len(telegram); call("POST", "/api/call", {"action": "test"}); pg.wait_for_selector("#call-incoming:not(.hidden)")
    pg.click("#call-decline"); pg.wait_for_function("document.querySelector('#call-screen').classList.contains('hidden')")
    assert len(telegram) == n + 1 and telegram[-1].startswith("📞 You declined a call from Jarvis.")
    # a window opened while it rings shows the call at once
    r = call("POST", "/api/call", {"action": "test"})[1]["call"]
    pg2 = ctx.new_page(); pg2.goto(f"http://127.0.0.1:{port}/"); pg2.wait_for_selector("#call-incoming:not(.hidden)"); pg2.close(); clear()
    # Settings
    pg.wait_for_timeout(300); pg.evaluate("window.JarvisUI.openPane('devices')"); pg.wait_for_function("document.querySelector('#calls-status').textContent.length > 0")
    assert pg.is_checked("#calls-on") and pg.is_checked("#calls-ring-pc") and pg.input_value("#calls-ring-seconds") == "40"
    assert "Jarvis called you" in pg.text_content("#calls-recent") and "You called Jarvis" in pg.text_content("#calls-recent")
    pg.uncheck("#calls-telegram")
    for _ in range(50):
        if obj.settings()["telegram_fallback"] is False: break
        time.sleep(0.1)
    assert obj.settings()["telegram_fallback"] is False
    pg.uncheck("#calls-ring-pc"); pg.uncheck("#calls-ring-phone"); pg.wait_for_function("document.querySelector('#calls-status').textContent.includes('at least one')")
    assert obj.settings()["ring_pc"] is False and obj.settings()["ring_phone"] is True
    pg.check("#calls-ring-pc"); pg.wait_for_timeout(300); obj.update({"telegram_fallback": True})
    ph = b.new_context(viewport={"width": 390, "height": 844}); ph.add_init_script(FAKES); php = ph.new_page(); php.goto(f"http://127.0.0.1:{port}/"); php.wait_for_timeout(400)
    php.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); php.reload(); php.wait_for_timeout(400)
    php.click("#call-button"); php.wait_for_function("document.querySelector('#call-screen').dataset.phase === 'listening'")
    assert php.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "no sideways scroll on a phone"
    php.click("#call-hangup")
    assert not errs, errs
    b.close()
print("calls ok"); os._exit(0)

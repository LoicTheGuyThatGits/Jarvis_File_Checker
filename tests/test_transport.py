import json, os, sys, tempfile, threading, time, http.client, importlib.util, urllib.parse
from datetime import datetime, date, timedelta
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
tmp = Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0, "app")
import transport as T, planner as P, french as fr

# ---------- a pretend transport.opendata.ch: bus 47 from Laconnex every 15 minutes, 24 minutes to Bel-Air ----------
STOPS = {"laconnex": ("8587057", "Laconnex, village"), "bel-air": ("8587387", "Genève, Bel-Air"), "geneve": ("8587387", "Genève, Bel-Air"), "geneva": ("8587387", "Genève, Bel-Air"),
         "bernex": ("8587061", "Bernex, Vailly")}
DELAY, CANCEL, ASKED = {}, set(), []
def iso(ts): return datetime.fromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%S+0100")
def stop(name, key, ts, delay=0, platform=""):
    return {"station": {"id": "1", "name": name}, key: iso(ts), key + "Timestamp": int(ts), "delay": delay, "platform": platform,
            "prognosis": {key: iso(ts + delay * 60) if delay else None}}
def bus(dep):
    d = DELAY.get(int(dep), 0)
    return {"from": stop("Laconnex, village", "departure", dep, d), "to": stop("Genève, Bel-Air", "arrival", dep + 24 * 60, d), "duration": "00d00:24:00", "transfers": 0,
            "sections": [{"journey": {"name": "47", "category": "B", "number": "47", "to": "Genève, Bel-Air", "isCancelled": int(dep) in CANCEL},
                          "departure": stop("Laconnex, village", "departure", dep, d), "arrival": stop("Genève, Bel-Air", "arrival", dep + 24 * 60, d)}]}
def slots(start, end):
    t = datetime.fromtimestamp(start).replace(second=0, microsecond=0)
    t -= timedelta(minutes=(t.minute - 11) % 15)
    out = []
    while t.timestamp() <= end:
        if t.timestamp() >= start: out.append(t.timestamp())
        t += timedelta(minutes=15)
    return out
class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def reply(self, obj):
        raw = json.dumps(obj).encode(); self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        u = urllib.parse.urlparse(self.path); q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}; ASKED.append((u.path, q))
        key = lambda s: next((v for k, v in STOPS.items() if k in s.lower().replace("è", "e").replace("é", "e")), None)
        if u.path == "/v1/locations":
            s = key(q["query"]); return self.reply({"stations": [{"id": s[0], "name": s[1], "coordinate": {}}] if s else []})
        if u.path == "/v1/connections":
            if not key(q["from"]) or not key(q["to"]): return self.reply({"connections": []})
            at = datetime.strptime(q["date"] + " " + q["time"], "%Y-%m-%d %H:%M").timestamp() if "date" in q else time.time()
            deps = slots(at - 24 * 60 - 75 * 60, at - 24 * 60)[-5:] if q.get("isArrivalTime") == "1" else slots(at, at + 90 * 60)[:int(q.get("limit", 4))]
            return self.reply({"connections": [bus(d) for d in deps]})
        if u.path == "/v1/stationboard":
            s = key(q["station"]); now = time.time()
            return self.reply({"station": {"name": s[1] if s else q["station"]}, "stationboard": [
                {"stop": stop(s[1], "departure", d, DELAY.get(int(d), 0)), "name": "47", "category": "B", "number": "47", "to": "Genève, Bel-Air"} for d in slots(now, now + 3600)[:5]]})
        self.send_response(404); self.end_headers()
fake = ThreadingHTTPServer(("127.0.0.1", 0), Fake); threading.Thread(target=fake.serve_forever, daemon=True).start()
T.API = f"http://127.0.0.1:{fake.server_address[1]}/v1"

assert T.station("laconnex") == {"id": "8587057", "name": "Laconnex, village"} and T.station("Atlantis") is None
assert T.line_name({"category": "B", "number": "47"}) == "bus 47" and T.line_name({"category": "T", "number": "12"}) == "tram 12"
assert T.line_name({"category": "IR", "number": "90", "name": "IR 90"}) == "IR 90" and T.line_name({"category": "S", "number": "2"}) == "S2"
# ---------- the trip to school ----------
mon = date.today() + timedelta(days=7 - date.today().weekday())
at = lambda h, m: datetime.combine(mon, datetime.min.time()).replace(hour=h, minute=m)
store = T.Transport(tmp / "t.json")
store.set_settings({"home": "laconnex", "school": "bel-air", "walk_home": 5, "walk_school": 5, "margin": 5, "notice": 15}, T.station)
assert store.settings()["home"] == "Laconnex, village" and store.settings()["school"] == "Genève, Bel-Air", "stops looked up"
try: store.set_settings({"home": "Atlantis"}, T.station); raise SystemExit("unknown stop accepted")
except ValueError as e: assert "Atlantis" in str(e)
ctx = {"lessons": lambda d: [{"start": "08:15", "end": "09:00", "subject": "Maths"}] if d.weekday() < 5 else [], "parse_when": P.parse_when}
assert T.tick(store, at(5, 0), ctx) == [], "too early to look"
assert T.tick(store, at(5, 10), ctx) == [] and store.load()["trip"]["leave"] == at(7, 36).timestamp(), store.load()["trip"]       # bus 07:41, at Bel-Air 08:05
assert T.tick(store, at(6, 52), ctx) == [] and T.tick(store, at(7, 11), ctx) == []
out = T.tick(store, at(7, 21), ctx)
assert [m["text"] for m in out] == ["Leave in 15 min, at 07:36, sir: the bus 47 from Laconnex, village at 07:41, on time, at Genève, Bel-Air at 08:05. First lesson: Maths at 08:15."], out
assert T.brief_line(store, at(7, 0)) == "To be on time for Maths, leave at 07:36 for the 07:41 bus 47 from Laconnex, village."
DELAY[int(at(7, 41).timestamp())] = 6                                                  # the 07:41 is 6 minutes late: too late for 08:05
out = T.tick(store, at(7, 24), ctx)
assert len(out) == 1 and out[0]["urgent"] and out[0]["text"].startswith("Change of plan: the 07:41 is cancelled or too late now. Leave now (07:21), sir: the bus 47 from Laconnex, village at 07:26"), out
assert T.tick(store, at(7, 25), ctx) == [], "said once"
assert T.tick(store, at(6, 0) + timedelta(days=5), ctx) == [], "Saturday: no school"
DELAY.clear()
# ---------- in the chat (the module) ----------
now = at(16, 0)
ask = lambda q: T.command(q, store, now, {**ctx, "lookup": T.station})
r = ask("when's my next bus to Geneva"); assert r.startswith("From Laconnex, village to Genève, Bel-Air, sir:\n• 16:11 (in 11 min): bus 47 towards Genève, Bel-Air, arrives 16:35 (direct)"), r
r = ask("how do I get to Geneva by 6pm"); assert "to arrive by 18:00" in r and "arrives 17:50" in r and "18:05" not in r, r
r = ask("connections from Bernex to Laconnex at 7:30"); assert r is not None
r = ask("next bus to geneva at 7:30 tomorrow"); assert "from 07:30" in r and "07:41" in r, r
assert ask("how do I get to level 3 in this game") is None and ask("remind me to buy milk") is None and ask("what's the next lesson for maths") is None
assert ask("next train to Atlantis").startswith("I found no connection from Laconnex, village to Atlantis")
r = ask("when should I leave for school"); assert r.startswith("Tomorrow, leave at 07:36, sir: the bus 47"), r
for f, e in (("prochain bus pour Genève", "next bus to Genève"), ("comment aller à Lausanne pour 17h", "how do I get to Lausanne by 17:00"),
             ("les prochains départs", "departures"), ("quand dois-je partir pour l'école", "when should I leave for school"), ("mon bus est en retard ?", "is my bus late")):
    assert fr.to_english(f) == e, (f, fr.to_english(f))
# a service that is down
T.API, real = "http://127.0.0.1:9/v1", T.API
assert "could not reach the Swiss timetable" in ask("next bus to Geneva")
T.API = real

# ---------- through the server ----------
spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT = tmp / "srv"
stage(tmp / "srv"); S.transport_module.API = real
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start(); port = app.server_address[1]
def call(method, path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30); c.request(method, path, json.dumps(body) if body is not None else None, {"Content-Type": "application/json"})
    r = c.getresponse(); return r.status, json.loads(r.read())
chat = lambda text: call("POST", "/api/chat", {"messages": [{"role": "user", "content": text}], "stream": False})[1]["reply"]
assert "set your home stop" in chat("next departures")
st, d = call("POST", "/api/transport", {"settings": {"home": "Laconnex", "school": "Bel-Air", "walk_home": 7}}); assert st == 200 and d["settings"]["home"] == "Laconnex, village" and d["settings"]["walk_home"] == 7
r = chat("next bus to Geneva"); assert r.startswith("From Laconnex, village to Genève, Bel-Air, sir:") and "bus 47" in r, r
r = chat("departures"); assert r.startswith("Next departures from Laconnex, village, sir:\n• ") and "bus 47 to Genève, Bel-Air" in r, r
r = chat("prochain bus pour Genève"); assert "Laconnex" in r, r
for d in range(7):
    S.timetable_obj().add(d, "08:15", "09:00", "Maths")
r = chat("when should I leave for school"); assert "leave" in r.lower() and "07:3" in r, r
st, d = call("POST", "/api/transport", {"test": True}); assert st == 200 and len(d["lines"]) == 4 and "bus 47" in d["lines"][0]
st, d = call("POST", "/api/transport", {"settings": {"walk_home": 500}}); assert st == 400
# an urgent change calls you when you asked for that
rang, said = [], []
S.call_user = lambda reason, opening: rang.append(opening) or {}
S.publish_event = lambda e: said.append(e)
S.transport_module.tick = lambda store, now, ctx: [{"text": "Change of plan: leave now.", "urgent": True}]
S.transport_tick(time.time(), lambda t: None); assert said[-1]["text"] == "Change of plan: leave now." and said[-1]["speak"] is True and rang == []
call("POST", "/api/transport", {"settings": {"call": True}}); S.transport_tick(time.time(), lambda t: None); assert rang == ["Change of plan: leave now."]

# ---------- the settings page ----------
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_context(viewport={"width": 1280, "height": 900}).new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(600)
    pg.evaluate("window.JarvisUI.openPane('plan')"); pg.wait_for_function("document.querySelector('#tr-home').value === 'Laconnex, village'")
    assert pg.input_value("#tr-walk-home") == "7" and pg.is_checked("#tr-call")
    pg.fill("#tr-school", "bernex"); pg.click("#tr-save"); pg.wait_for_function("document.querySelector('#tr-status').textContent === 'Saved.'")
    assert pg.input_value("#tr-school") == "Bernex, Vailly"
    pg.fill("#tr-school", "Atlantis"); pg.click("#tr-save"); pg.wait_for_function("document.querySelector('#tr-status').textContent.includes('Atlantis')")
    pg.fill("#tr-school", "bel-air"); pg.click("#tr-save"); pg.wait_for_function("document.querySelector('#tr-status').textContent === 'Saved.'")
    pg.click("#tr-test"); pg.wait_for_selector("#tr-list li"); assert "bus 47" in pg.text_content("#tr-list")
    call("POST", "/api/language", {"ui": "fr"}); pg.reload(); pg.wait_for_function("document.documentElement.lang === 'fr'"); pg.evaluate("window.JarvisUI.openPane('plan')"); pg.wait_for_timeout(400)
    assert pg.text_content("#transport-title") == "Transports publics", pg.text_content("#transport-title")
    call("POST", "/api/language", {"ui": "auto"})
    ph = b.new_context(viewport={"width": 390, "height": 844}).new_page(); ph.goto(f"http://127.0.0.1:{port}/"); ph.wait_for_timeout(500)
    ph.evaluate("window.JarvisUI.openPane('plan')"); ph.wait_for_timeout(400)
    assert ph.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert not errs, errs
    b.close()
print("transport ok"); os._exit(0)

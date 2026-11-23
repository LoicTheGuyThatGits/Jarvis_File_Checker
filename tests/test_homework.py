import json, os, sys, re, tempfile, threading, time, http.client, importlib.util, urllib.parse
from datetime import datetime, date, timedelta
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
tmp = Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0, "app")
import homework as H, planner as P, timetable as T, classroom as C, french as fr

# ---------- the module, with a timetable ----------
tt = T.Timetable(tmp / "tt.json")
tt.add(0, "08:15", "09:00", "Maths", "B12"); tt.add(3, "08:15", "09:00", "Maths", "B12"); tt.add(1, "10:15", "11:00", "Biology")
tt.add(4, "09:10", "09:55", "French")
pl = P.Planner(tmp / "planner.json")
now = datetime(2026, 11, 19, 12, 0)                # a Thursday, after maths
def next_lesson(subject, after):
    for ahead in range(60):
        day = after.date() + timedelta(days=ahead)
        for l in T.lessons_on(tt, day):
            s = T.at(day, l["start"])
            if s > after and H.key(l["subject"]) == H.key(subject):
                return l, s
ctx = {"next_lesson": next_lesson, "subjects": lambda: ["Maths", "Biology", "French"], "parse_when": P.parse_when}
ask = lambda q, n=now: H.command(q, pl, n, ctx)

assert H.parse_add("maths homework: exercises 4 to 7, for next lesson") == {"subject": "maths", "what": "exercises 4 to 7", "when": "next lesson"}
for not_ours in ("what's the weather", "I got a 5 in maths", "remind me to do my homework at 6", "how do I do my homework faster?"):
    assert H.parse_add(not_ours) is None, not_ours
r = ask("maths homework: exercises 4 to 7 on page 52")
assert r == "Noted, sir: Maths: exercises 4 to 7 on page 52, due Monday (your next lesson).", r
t = H.pending(pl)[0]
assert datetime.fromtimestamp(t["due"]) == datetime(2026, 11, 23, 8, 15) and t["homework"]["subject"] == "Maths" and t["notified"] and not t["has_time"]
r = ask("homework: read chapter 3 for the next biology lesson"); assert r == "Noted, sir: Biology: read chapter 3, due Tuesday (your next lesson).", r
r = ask("french homework for tomorrow: learn the vocabulary of unit 4"); assert "due tomorrow" in r and "French: learn the vocabulary of unit 4" in r, r
assert datetime.fromtimestamp([t for t in H.pending(pl) if "unit 4" in t["text"]][0]["due"]) == datetime(2026, 11, 20, 9, 10), "due at the start of that day's lesson"
r = ask("what homework do I have"); assert r.startswith("Your homework, sir (3):\n• Tomorrow: French"), r
r = ask("what homework do I have for tomorrow"); assert r == "Homework for tomorrow, sir:\n• Tomorrow: French: learn the vocabulary of unit 4", r
r = ask("do I have homework in maths"); assert "Maths: exercises" in r and "French" not in r, r
r = ask("I did my maths homework"); assert r == "Well done, sir. Marked as done: Maths: exercises 4 to 7 on page 52.", r
assert ask("I finished my homework").startswith("Which one, sir?")
assert ask("remove my biology homework") == "Removed: Biology: read chapter 3."
assert ask("what homework do I have this week").startswith("Homework this week, sir:")
assert ask("what homework do I have next week") == "No homework next week, sir."
for not_ours in ("what's my next class", "remind me to buy milk", "add maths every monday at 8"):
    assert ask(not_ours) is None, not_ours
# French
for f, e in (("devoirs de maths : exercices 4 à 7 pour le prochain cours", "maths homework: exercices 4 à 7, for next lesson"),
             ("qu'est-ce que j'ai comme devoirs pour demain ?", "what homework do I have for tomorrow"),
             ("j'ai fini mes devoirs de maths", "I did my maths homework"), ("mes devoirs", "my homework")):
    assert fr.to_english(f) == e, (f, fr.to_english(f))

# ---------- sync: new ones come in, handed-in ones are ticked off, removed ones go ----------
sp = P.Planner(tmp / "sync.json"); subj = lambda c: "Maths" if "math" in c.lower() else c
items = [{"id": "c/1", "course": "Mathématiques", "title": "Sheet 1", "due": 2e9, "link": "L1", "done": False},
         {"id": "c/2", "course": "Physics", "title": "Lab", "due": None, "link": "", "done": False}, {"id": "c/3", "course": "Physics", "title": "Old", "due": None, "done": True}]
new = H.sync(sp, items, subj); assert [t["text"] for t in new] == ["Maths: Sheet 1", "Physics: Lab"], "a handed-in one never comes in"
assert H.sync(sp, items, subj) == [], "nothing new the second time"
items[0]["done"] = True; items.pop(1); H.sync(sp, items, subj)
left = H.pending(sp, include_done=True); assert [(t["text"], t["done"]) for t in left] == [("Maths: Sheet 1", True)], left
# ---------- Classroom: a fake Google ----------
GOOGLE = {"refresh_ok": True, "codes": [], "courses_status": 200}
class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def reply(self, code, body):
        raw = json.dumps(body).encode(); self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_POST(self):
        form = urllib.parse.parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
        GOOGLE["codes"].append(form)
        if form["grant_type"] == ["authorization_code"]:
            assert form["code_verifier"][0] and form["redirect_uri"][0].startswith("http://127.0.0.1:")
            return self.reply(200, {"access_token": "AT1", "expires_in": 3600, "refresh_token": "RT1"})
        if not GOOGLE["refresh_ok"]:
            return self.reply(400, {"error": "invalid_grant", "error_description": "Token has been expired or revoked."})
        return self.reply(200, {"access_token": "AT2", "expires_in": 3600})
    def do_GET(self):
        if self.path.startswith("/auth"):
            return self.reply(200, {"sign": "in"})
        assert self.headers["Authorization"].startswith("Bearer AT")
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
        if u.path == "/v1/courses":
            if GOOGLE["courses_status"] == 403:
                return self.reply(403, {"error": {"code": 403, "message": "Google Classroom API has not been used in project 1 before or it is disabled.", "status": "PERMISSION_DENIED"}})
            assert q["studentId"] == ["me"]
            return self.reply(200, {"courses": [{"id": "c1", "name": "3M Mathématiques"}, {"id": "c2", "name": "Physics 3M"}]})
        if u.path == "/v1/courses/c1/courseWork":
            if "pageToken" not in q:
                return self.reply(200, {"courseWork": [{"id": "w1", "title": "Worksheet 12", "state": "PUBLISHED", "dueDate": {"year": 2026, "month": 11, "day": 26}, "dueTime": {"hours": 7, "minutes": 0}, "alternateLink": "https://classroom.google.com/c/x/a/w1"}], "nextPageToken": "p2"})
            return self.reply(200, {"courseWork": [{"id": "w2", "title": "Old one", "dueDate": {"year": 2025, "month": 1, "day": 1}}, {"id": "w3", "title": "Draft", "state": "DRAFT"},
                                                   {"id": "w4", "title": "Handed in", "dueDate": {"year": 2026, "month": 12, "day": 1}}]})
        if u.path == "/v1/courses/c2/courseWork":
            return self.reply(200, {"courseWork": [{"id": "p1", "title": "Lab report", "dueDate": {"year": 2026, "month": 12, "day": 3}}]})
        if u.path.endswith("/studentSubmissions"):
            assert q["userId"] == ["me"]
            return self.reply(200, {"studentSubmissions": [{"courseWorkId": "w4", "state": "TURNED_IN"}, {"courseWorkId": "w1", "state": "CREATED"}]})
        self.reply(404, {})
g = ThreadingHTTPServer(("127.0.0.1", 0), Fake); threading.Thread(target=g.serve_forever, daemon=True).start(); gp = g.server_address[1]
C.TOKEN_URL = f"http://127.0.0.1:{gp}/token"; C.API = f"http://127.0.0.1:{gp}/v1"; C.AUTH_URL = f"http://127.0.0.1:{gp}/auth"
assert C.due_of({"dueDate": {"year": 2026, "month": 11, "day": 26}, "dueTime": {"hours": 7}}) == datetime(2026, 11, 26, 7, tzinfo=__import__("datetime").timezone.utc).timestamp()
assert C.explain_error("admin_policy_enforced").startswith("Your school's Google settings do not allow")
try: C.read_client("not an id", "x"); raise SystemExit("bad id accepted")
except C.ClassroomError: pass
assert C.read_client(json.dumps({"installed": {"client_id": "123-abc.apps.googleusercontent.com", "client_secret": "S"}}), "") == ("123-abc.apps.googleusercontent.com", "S")

# ---------- through the server ----------
spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT = tmp
S.classroom_module.TOKEN_URL, S.classroom_module.API, S.classroom_module.AUTH_URL = C.TOKEN_URL, C.API, C.AUTH_URL
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start(); port = app.server_address[1]
S.PORT = port
def call(method, path, body=None, raw=False):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30); c.request(method, path, json.dumps(body) if body is not None else None, {"Content-Type": "application/json"})
    r = c.getresponse(); data = r.read(); return r.status, (data.decode() if raw else json.loads(data))
chat = lambda text: call("POST", "/api/chat", {"messages": [{"role": "user", "content": text}], "stream": False})[1]["reply"]
for l in ("add maths every monday and thursday from 8:15 to 9:00 in B12", "add physics every wednesday from 10:15 to 11:00"):
    assert chat(l).startswith("Added")
r = chat("maths homework: worksheet 3, for next lesson"); assert r.startswith("Noted, sir: Maths: worksheet 3, due "), r
assert chat("devoirs de physique : finir le rapport pour le prochain cours").startswith("Noted, sir: Physics: finir le rapport")
st, d = call("GET", "/api/homework"); assert st == 200 and len(d["items"]) == 2 and "Physics" in d["subjects"] and not d["classroom"]["connected"], d
# the evening note lists homework due tomorrow (it is a planner task)
due = d["items"][0]["due"]; day = datetime.fromtimestamp(due).date()
assert any("worksheet 3" in x or "finir" in x for x in S.timetable_extras()["due"](day))
st, d = call("POST", "/api/homework", {"add": {"subject": "maths", "what": "revise for the test", "due": (date.today() + timedelta(days=3)).isoformat()}})
assert st == 200 and any(i["text"] == "Maths: revise for the test" for i in d["items"]), d
st, d = call("POST", "/api/homework", {"add": {"subject": "", "what": ""}}); assert st == 400
hid = [i["id"] for i in call("GET", "/api/homework")[1]["items"] if "revise" in i["text"]][0]
assert len(call("POST", "/api/homework", {"done": hid})[1]["items"]) == 2
assert len(call("POST", "/api/homework", {"undo": hid})[1]["items"]) == 3
assert len(call("POST", "/api/homework", {"remove": hid})[1]["items"]) == 2
assert "not connected" in chat("check classroom")
# connecting
st, d = call("POST", "/api/homework", {"classroom": {"connect": {"client_id": "123-abc.apps.googleusercontent.com", "client_secret": ""}}}); assert st == 409 and "secret is missing" in d["error"]
st, d = call("POST", "/api/homework", {"classroom": {"connect": {"client_id": "123-abc.apps.googleusercontent.com", "client_secret": "SEC"}}})
assert st == 200 and d["url"].startswith(C.AUTH_URL), d
q = urllib.parse.parse_qs(urllib.parse.urlparse(d["url"]).query)
assert q["redirect_uri"] == [f"http://127.0.0.1:{port}/"] and q["code_challenge_method"] == ["S256"] and "classroom.coursework.me.readonly" in q["scope"][0] and q["access_type"] == ["offline"]
assert "SEC" not in json.dumps(call("GET", "/api/homework")[1]), "the secret never goes back to the page"
# a stranger's state is just the normal page
st, page = call("GET", "/?state=nope&code=x", raw=True); assert st == 200 and "<html" in page.lower() and "Classroom" not in page[:300]
st, page = call("GET", "/?" + urllib.parse.urlencode({"state": q["state"][0], "code": "CODE"}), raw=True)
assert st == 200 and "Google Classroom connected" in page and "2 assignments came in" in page, page
st, d = call("GET", "/api/homework")
cr = [i for i in d["items"] if i["source"] == "classroom"]
assert sorted(i["text"] for i in cr) == ["Maths: Worksheet 12", "Physics: Lab report"], cr
assert d["classroom"]["connected"] and d["classroom"]["courses"] == ["3M Mathématiques", "Physics 3M"] and cr[0]["link"].startswith("https://classroom.google.com")
saved = json.loads((tmp / "data" / "classroom.json").read_text()); assert saved["refresh_token"] == "RT1"
assert "Nothing new on Classroom" in chat("check classroom")
# ticked off in Classroom → done in Jarvis; gone from Classroom → gone
GOOGLE["courses_status"] = 403
st, d = call("POST", "/api/homework", {"classroom": {"sync": True}}); assert st == 409 and "API is not turned on" in d["error"] and d["classroom"]["last_error"], d
GOOGLE["courses_status"] = 200
assert "Worksheet 12" in chat("what homework do I have in maths")
# a cancelled or school-blocked sign-in
st, d = call("POST", "/api/homework", {"classroom": {"connect": {"client_id": "123-abc.apps.googleusercontent.com", "client_secret": ""}}}); state = urllib.parse.parse_qs(urllib.parse.urlparse(d["url"]).query)["state"][0]
st, page = call("GET", "/?" + urllib.parse.urlencode({"state": state, "error": "admin_policy_enforced"}), raw=True)
assert st == 400 and "school" in page and "IT" in page, page
# an expired sign-in
saved = json.loads((tmp / "data" / "classroom.json").read_text()); saved["expires_at"] = 0; (tmp / "data" / "classroom.json").write_text(json.dumps(saved))
GOOGLE["refresh_ok"] = False
assert "Press Connect again" in chat("sync classroom")
GOOGLE["refresh_ok"] = True
# the phone cannot connect it
S.phone_link.save(S.data_path("phone.json"), {"enabled": True, "code": "ABCDEFGH23"}); S.phone_link.is_loopback = lambda a: False
c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
c.request("POST", "/api/homework", json.dumps({"classroom": {"connect": {"client_id": "123-abc.apps.googleusercontent.com", "client_secret": "X"}}}), {"Content-Type": "application/json", "X-Jarvis-Token": "ABCDEFGH23"})
r = c.getresponse(); assert r.status == 403 and "at the PC" in json.loads(r.read())["error"]
c = http.client.HTTPConnection("127.0.0.1", port, timeout=30); c.request("GET", "/api/homework", headers={"X-Jarvis-Token": "ABCDEFGH23"})
r = c.getresponse(); assert r.status == 200 and len(json.loads(r.read())["items"]) == 4, "the phone app can read homework"
S.phone_link.is_loopback = lambda a: True
# disconnecting removes Classroom homework that is not done; your own stays
st, d = call("POST", "/api/homework", {"classroom": {"disconnect": True}})
assert not d["classroom"]["connected"] and all(i["source"] == "chat" for i in d["items"]) and len(d["items"]) == 2, d
assert "refresh_token" not in json.loads((tmp / "data" / "classroom.json").read_text())

# ---------- the settings page ----------
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_context(viewport={"width": 1280, "height": 900}).new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(600)
    pg.evaluate("window.JarvisUI.openPane('school')"); pg.wait_for_selector("#homework-list .hw-item")
    assert pg.locator("#homework-list .hw-item").count() == 2
    assert "Physics" in pg.evaluate("[...document.querySelectorAll('#hw-subjects option')].map(o=>o.value).join(',')")
    pg.fill("#hw-subject", "Maths"); pg.fill("#hw-what", "learn the formulas"); pg.click("#hw-add")
    pg.wait_for_function("document.querySelectorAll('#homework-list .hw-item').length === 3")
    assert "Maths: learn the formulas" in pg.text_content("#homework-list")
    pg.locator("#homework-list .hw-item", has_text="learn the formulas").locator("input[type=checkbox]").check()
    pg.wait_for_function("document.querySelectorAll('#homework-list .hw-item').length === 2")
    assert pg.is_visible("#classroom-connect") and not pg.is_visible("#classroom-disconnect")
    assert pg.input_value("#classroom-redirect") == f"http://127.0.0.1:{port}/"
    pg.fill("#classroom-id", "123-abc.apps.googleusercontent.com"); pg.fill("#classroom-secret", "SEC")
    with pg.expect_popup() as pop:
        pg.click("#classroom-connect")
    popup = pop.value; popup.wait_for_url(C.AUTH_URL + "*")
    state = urllib.parse.parse_qs(urllib.parse.urlparse(popup.url).query)["state"][0]; popup.close()
    pg.goto(f"http://127.0.0.1:{port}/?" + urllib.parse.urlencode({"state": state, "code": "CODE"})); assert "Google Classroom connected" in pg.content()
    pg.goto(f"http://127.0.0.1:{port}/"); pg.wait_for_timeout(500); pg.evaluate("window.JarvisUI.openPane('school')")
    pg.wait_for_function("document.querySelector('#classroom-status').textContent.includes('Connected.')")
    assert pg.is_visible("#classroom-disconnect") and pg.locator("#homework-list a[href^='https://classroom.google.com']").count() == 1
    call("POST", "/api/language", {"ui": "fr"}); pg.reload(); pg.wait_for_function("document.documentElement.lang === 'fr'"); pg.evaluate("window.JarvisUI.openPane('school')")
    pg.wait_for_selector("#homework-list .hw-item"); pg.wait_for_timeout(300)
    assert pg.text_content("#homework-title") == "Devoirs" and pg.text_content("#classroom-status .cr-state") == "Connecté.", pg.text_content("#classroom-status")
    call("POST", "/api/language", {"ui": "auto"})
    ph = b.new_context(viewport={"width": 390, "height": 844}).new_page(); ph.goto(f"http://127.0.0.1:{port}/"); ph.wait_for_timeout(500)
    ph.evaluate("window.JarvisUI.openPane('school')"); ph.wait_for_selector("#homework-list .hw-item")
    assert ph.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert not errs, errs
    b.close()
print("homework ok"); os._exit(0)

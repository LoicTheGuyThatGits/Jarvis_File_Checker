import json, os, sys, tempfile, threading, http.client, importlib.util
from datetime import datetime, date
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp = Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0, "app")
import grades as G, planner as P, french as fr

st = G.Grades(tmp / "g.json")
now = datetime(2026, 11, 19, 12)
ask = lambda q: G.command(q, st, now, ["Maths", "French", "PE"], P.parse_when)

assert ask("what are my grades").startswith("You have no grades yet this term, sir.")
# ---------- recording ----------
assert ask("I got a 5 in maths") == "Recorded 5 in Maths, sir. It is your first Maths grade this term."
assert ask("I got 4.5 on the maths test, counts double") == "Recorded 4.5 in Maths (counts double), sir. Your Maths average is now 4.67 (rounds to 4.5), from 2 grades."
assert ask("i got a 5,5 in math yesterday") == "Recorded 5.5 in Maths, sir. Your Maths average is now 4.88 (rounds to 5), from 3 grades."
assert st.data()["grades"][-1]["date"] == "2026-11-18", "yesterday"
assert ask("I got 17/20 in French") == "Recorded 5.25 (17/20 on your 1–6 scale) in French, sir. It is your first French grade this term."
assert ask("got a 3.5 in french").startswith("Recorded 3.5 in French")
assert ask("I got a 3 in the french test") == "Recorded 3 in French, sir. Your French average is now 3.92 (rounds to 4), from 3 grades. That is just under 4."
assert st.data()["grades"][-1]["note"] == "test"
assert ask("add a grade of 5 in PE") == "Recorded 5 in PE, sir. It is your first PE grade this term."
assert ask("I got a 10 in history") == "A grade must be between 1 and 6 on your scale."
assert ask("I got 21/20 in history") == "21 out of 20 does not add up, sir."
for chatter in ("I got 3 hours of sleep", "i got a 2 in a row", "I got 5 minutes in the queue", "what is my average speed", "I got a new phone"):
    assert ask(chatter) is None, chatter
# ---------- asking ----------
assert ask("what's my average in maths") == "Maths: 4.88 (rounds to 5), from 3 grades: 5.5, 5, 4.5 (double)."
assert ask("my maths average") == ask("how am I doing in maths")
assert ask("how am I doing in french") == "French: 3.92 (rounds to 4), just under 4, from 3 grades: 5.25, 3.5, 3."
assert ask("what's my average in biology") == "You have no Biology grades yet this term, sir. Tell me one with, for example, “I got a 5 in Biology”."
r = ask("what are my averages")
assert r.startswith("Your averages this term, sir (overall 4.6):\n• French: 3.92") and "• PE: 5" in r and r.endswith("Below 4: French."), r
# ---------- what is needed ----------
assert ask("what do I need on the next french test to get a 4") == "You need at least 4.25 on the next French test to bring your average from 3.92 to 4, sir."
assert ask("what do I need to pass french") == ask("what do I need on the next french test to get a 4")
assert ask("what do I need on the next french test to get 4.5, it counts double") == "You need at least 5.38 on the next French test (if it counts double) to bring your average from 3.92 to 4.5, sir."
assert ask("what do I need on the next french test to get 5.5") == "Even a 6 on the next French test would only bring your average from 3.92 to 4.44, sir, so 5.5 is out of reach with one test."
assert ask("what do I need on the next maths test to keep a 4") == "Your Maths average is 4.88, sir: even a 1 on the next test keeps it at 4 or above."
assert ask("what do I need on the next history test to get a 5").startswith("You have no History grades yet this term")
# ---------- removing, terms ----------
assert ask("remove my last grade") == "Removed the 5 in PE, sir."
assert ask("delete the 3.5 in french") == "Removed the 3.5 in French (2026-11-19), sir."
assert ask("start a new term").startswith("New term started on")
assert ask("my grades").startswith("You have no grades yet this term")
assert ask("I got a 6 in maths") == "Recorded 6 in Maths, sir. It is your first Maths grade this term."
assert G.summary(st)["earlier"] == 5
# ---------- other scales ----------
s2 = G.Grades(tmp / "g2.json"); s2.set_scale("germany")
a2 = lambda q: G.command(q, s2, now, [], P.parse_when)
a2("I got a 2 in maths"); a2("I got a 3 in maths")
assert a2("what do I need on the next maths test to get a 2") == "You need 1.5 or better on the next Maths test to bring your average from 2.5 to 2, sir." or a2("what do I need on the next maths test to get a 2") == "You need 1 or better on the next Maths test to bring your average from 2.5 to 2, sir."
assert a2("what do I need to pass maths") == "Your Maths average is 2.5, sir: even a 6 on the next test keeps it at 4 or better."
assert a2("I got 18/20 in physics").startswith("Recorded 1.5 (18/20 on your 1–6 scale) in Physics")
assert G.passing(3.0, s2.scale()) and not G.passing(4.5, s2.scale())
s3 = G.Grades(tmp / "g3.json"); s3.set_scale("france")
assert G.command("I got 15/20 in maths", s3, now, [], None).startswith("Recorded 15 (15/20 on your 0–20 scale)")
try:
    st.set_scale("france"); st.set_scale("swiss")
    s3.set_scale("swiss"); raise AssertionError("15 is not on the Swiss scale")
except ValueError as exc:
    assert "outside that scale" in str(exc)
try:
    st.set_scale(None, min=1, max=6, pass_=9); raise AssertionError()
except ValueError:
    pass
# ---------- French ----------
for q, want in {"j'ai eu un 5 en maths": "I got a 5 in maths", "j'ai eu 4,5 en français, coefficient 2": "I got a 4,5 in français, counts double",
                "j'ai eu 17 sur 20 en anglais hier": "I got a 17/20 in anglais yesterday", "quelle est ma moyenne en maths ?": "what's my average in maths",
                "mes notes": "my grades", "il me faut combien au prochain test de maths pour avoir 4,5": "what do I need on the next maths test to get 4.5",
                "supprime ma dernière note": "remove my last grade", "nouveau semestre": "start a new term"}.items():
    assert fr.to_english(q, now) == want, (q, fr.to_english(q, now))
assert fr.to_english("j'ai eu faim", now) is None
assert G.command("I got a 4,5 in français, counts double", st, now, [], None).startswith("Recorded 4.5 in Français (counts double)")

# ---------- in the server ----------
spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT = tmp
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start(); port = app.server_address[1]
def call(method, path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30); c.request(method, path, json.dumps(body) if body is not None else None, {"Content-Type": "application/json"})
    r = c.getresponse(); return r.status, json.loads(r.read())
chat = lambda text: call("POST", "/api/chat", {"messages": [{"role": "user", "content": text}], "stream": False})[1]["reply"]
S.timetable_obj().add(0, "08:15", "09:00", "Mathematics")
assert chat("I got a 5 in mathematics").startswith("Recorded 5 in Mathematics"), "the timetable's subject name is used"
assert chat("I got a 4 on the maths test").startswith("Recorded 4 in Mathematics"), "maths = mathematics"
assert chat("what do I need on my next maths test to keep a 4.5").startswith("You need at least 4.5")
assert "Moyenne" in chat("quelle est ma moyenne en maths ?") or "4,5" in chat("quelle est ma moyenne en maths ?") or "4.5" in chat("quelle est ma moyenne en maths ?")
st_, d = call("GET", "/api/grades"); assert d["subjects"][0]["subject"] == "Mathematics" and d["subjects"][0]["average"] == 4.5 and d["scale"]["preset"] == "swiss" and "Mathematics" in d["known"]
st_, d = call("POST", "/api/grades", {"add": {"subject": "Biology", "value": "5,5", "weight": 2, "date": "2026-11-10", "note": "oral"}}); assert st_ == 200 and [s["subject"] for s in d["subjects"]] == ["Biology", "Mathematics"]
st_, d = call("POST", "/api/grades", {"add": {"subject": "Biology", "value": "x"}}); assert st_ == 400 and "number" in d["error"]
st_, d = call("POST", "/api/grades", {"scale": {"preset": "france"}}); assert d["scale"]["max"] == 20
st_, d = call("POST", "/api/grades", {"scale": {"min": 0, "max": 10, "pass": 20}}); assert st_ == 400 and "pass mark" in d["error"]
st_, d = call("POST", "/api/grades", {"scale": {"preset": "swiss"}})

# ---------- the page ----------
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_context(viewport={"width": 1280, "height": 900}).new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda dlg: dlg.accept())
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(500)
    pg.evaluate("window.JarvisUI.openPane('plan')"); pg.wait_for_selector("#gr-list .gr-head")
    assert pg.input_value("#gr-preset") == "swiss" and pg.locator("#gr-list li").count() == 2
    assert pg.text_content("#gr-list li:nth-child(2) .gr-avg") == "4.5" and "Overall average" in pg.text_content("#gr-overall")
    pg.fill("#gr-subject", "Biology"); pg.fill("#gr-value", "3.5"); pg.click("#gr-add")
    pg.wait_for_function("document.querySelector('#gr-status').textContent === 'Added.'")
    assert pg.text_content("#gr-list li:nth-child(1) .gr-avg") == "4.83 → 5"
    pg.locator("#gr-list li", has_text="Biology").locator(".gr-chip", has_text="3.5").locator("button").click(); pg.wait_for_timeout(300)
    assert pg.text_content("#gr-list li:nth-child(1) .gr-avg") == "5.5"
    pg.select_option("#gr-preset", "custom"); assert pg.is_visible("#gr-custom")
    pg.fill("#gr-min", "0"); pg.fill("#gr-max", "10"); pg.fill("#gr-pass", "5"); pg.click("#gr-scale-save"); pg.wait_for_timeout(300)
    assert S.grades_obj().scale()["max"] == 10 and S.grades_obj().scale()["preset"] == "custom"
    pg.click("#gr-term"); pg.wait_for_function("document.querySelector('#gr-status').textContent === 'New term started.'")
    assert "No grades yet this term" in pg.text_content("#gr-list")
    ph = b.new_context(viewport={"width": 390, "height": 844}).new_page(); ph.goto(f"http://127.0.0.1:{port}/"); ph.wait_for_timeout(400)
    ph.evaluate("window.JarvisUI.openPane('plan')"); ph.wait_for_timeout(300)
    assert ph.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "no sideways scroll on a phone"
    assert not errs, errs
    b.close()
print("grades ok"); os._exit(0)

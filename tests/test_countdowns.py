import json, os, sys, tempfile, threading, http.client, importlib.util
from datetime import datetime, date, timedelta
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp = Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0, "app")
import countdowns as cd, planner as pl, french as fr

now = datetime(2026, 11, 18, 20, 50)   # a Wednesday
store = cd.Countdowns(tmp / "c.json")
events = [{"title": "Dentist appointment", "start": datetime(2026, 11, 20, 15, 30).timestamp()},
          {"title": "Physics test", "start": datetime(2026, 11, 25, 9, 0).timestamp()}]
ask = lambda q, when=now: cd.command(q, store, events, when, pl.parse_when)

# ---------- adding ----------
assert ask("how many days until the christmas vacation?").startswith("I do not have a date for the Christmas vacation, sir. Tell me when it is, for example: “add a countdown for the Christmas vacation from 19 December to 4 January”.")
r = ask("Add a countdown for the Christmas vacation from 19 December to 4 January")
assert r == "Added the countdown for the Christmas vacation, sir. 31 days until the Christmas vacation: it starts on Saturday 19 December and lasts until Monday 4 January.", r
r = ask("the christmas holidays are from 19 December to 5 January")
assert r.startswith("Updated the countdown for the Christmas vacation, sir.") and "Tuesday 5 January" in r, "same thing, other words: updated, name kept"
assert len(store.items(now.date())) == 1 and store.items(now.date())[0]["end"] == date(2027, 1, 5)
assert ask("add a countdown for my birthday").startswith("When is your birthday, sir?")
assert ask("add a countdown for my birthday on 3 March").startswith("Added the countdown for your birthday, sir. 105 days until your birthday: Wednesday 3 March.")
assert ask("count down to the ski trip on 14 February").startswith("Added the countdown for the ski trip, sir.")
assert "Wednesday 3 March and lasts until Wednesday 10 March" in ask("add a countdown for the trip to Paris from 3 March to 10 March")
assert ask("the Christmas holidays start on 19 December").endswith("it starts on Saturday 19 December and lasts until Tuesday 5 January."), "the last day is kept"
assert ask("add a countdown for the summer holidays on 3 July 2025") == "That date has already passed, sir."
for timer in ("start a countdown for 10 minutes", "set a countdown for 5pm", "stop the countdown", "start a countdown"):
    assert ask(timer) is None, timer          # timers are handled elsewhere
# ---------- asking ----------
assert ask("how many days until the christmas holidays") == "31 days until the Christmas vacation, sir: it starts on Saturday 19 December and lasts until Tuesday 5 January."
assert ask("How many weeks until the Christmas vacation?").startswith("4 weeks and 3 days (31 days) until the Christmas vacation, sir")
assert ask("how many days until christmas") == "37 days until Christmas, sir: Friday 25 December. That is 5 weeks and 2 days."
assert ask("how many days until christmas eve").startswith("36 days until Christmas Eve, sir: Thursday 24 December.")
assert ask("how long until new year").startswith("44 days until New Year's Day, sir: Friday 1 January.")
assert ask("when is easter") == "Easter is on Sunday 28 March, sir: in 130 days."
assert ask("when is the christmas vacation") == "The Christmas vacation is from Saturday 19 December to Tuesday 5 January, sir: it starts in 31 days."
assert ask("how many days until 25 december") == "37 days until Friday 25 December, sir."
assert ask("how many days until friday") == "2 days until Friday 20 November, sir."
assert ask("how many days until the dentist") == "2 days until “Dentist appointment”, sir: Friday 20 November at 15:30."
assert ask("how many days until my physics test") is None, "the exam countdown answers that"
assert ask("how many sleeps until my birthday").startswith("105 sleeps until your birthday, sir")
assert ask("how many days until the weekend") == "3 days until the weekend, sir."
assert ask("how many days until the weekend", datetime(2026, 11, 21, 10)) == "It is the weekend, sir. Tomorrow is Sunday."
assert ask("how long until dinner") is None and ask("how long until 5pm") is None, "not ours: the AI answers"
assert "Your countdowns, sir:\n- 31 days until the Christmas vacation" in ask("my countdowns")
# during and after the holiday
during = datetime(2026, 12, 24, 10)
assert ask("how many days until the christmas vacation", during) == "The Christmas vacation is on now, sir: 12 more days after today, until Tuesday 5 January."
assert ask("how many days left of the christmas vacation", during).startswith("The Christmas vacation is on now")
assert ask("how many days left of the christmas vacation").startswith("The Christmas vacation has not started yet, sir. 31 days until")
assert ask("how many days until the christmas vacation", datetime(2027, 1, 5, 9)) == "Today is the last day of the Christmas vacation, sir."
assert ask("how many days until the christmas vacation", datetime(2027, 1, 10)) == "The Christmas vacation was on Tuesday 5 January; it has passed, sir."
gone_by = datetime(2027, 3, 1)
assert all(i["name"] != "Christmas vacation" for i in store.items(gone_by.date())), "forgotten a month after it ended"
store = cd.Countdowns(tmp / "c2.json")
ask("add a countdown for the Christmas vacation from 19 December to 4 January"); ask("add a countdown for my birthday on 3 March")
# grammar for plural names
assert ask("add a countdown for the summer holidays from 4 July to 21 August").endswith("they start on Sunday 4 July and last until Saturday 21 August.")
# ---------- removing ----------
assert ask("remove the summer holidays countdown") == "Removed the countdown for the summer holidays, sir."
assert ask("delete the countdown for the moon landing").startswith("I have no countdown called “moon landing”")
assert ask("cancel the timer countdown") is None
# ---------- the briefing ----------
assert cd.soon(store, datetime(2026, 12, 16)) == ["The Christmas vacation starts in 3 days."]
assert cd.soon(store, datetime(2026, 12, 18)) == ["The Christmas vacation starts tomorrow."] and cd.soon(store, datetime(2027, 1, 4)) == ["Today is the last day of the Christmas vacation."]
assert cd.soon(store, now) == []
# ---------- Easter ----------
assert [cd.easter(y) for y in (2024, 2025, 2026, 2027)] == [date(2024, 3, 31), date(2025, 4, 20), date(2026, 4, 5), date(2027, 3, 28)]
# ---------- French ----------
fr_cases = {
    "ajoute un compte à rebours pour les vacances de Noël du 19 décembre au 4 janvier": "add a countdown for les vacances de Noël from 19 december to 4 january",
    "les vacances de Noël sont du 19 au 23 décembre": "add a countdown for les vacances de Noël from 19 december to 23 december",
    "combien de jours avant les vacances de Noël ?": "how many days until les vacances de Noël",
    "dans combien de jours sont les vacances de Noël": "how many days until les vacances de Noël",
    "combien de semaines jusqu'à mon anniversaire": "how many weeks until mon anniversaire",
    "c'est quand Pâques ?": "when is Pâques",
    "mes comptes à rebours": "my countdowns",
    "supprime le compte à rebours pour les vacances de Noël": "remove the countdown for les vacances de Noël",
    "lance un compte à rebours de 10 minutes": "set a timer for 10 minutes",
    "combien de jours avant mon contrôle de maths": "exam countdown",
}
for q, want in fr_cases.items():
    assert fr.to_english(q, now) == want, (q, fr.to_english(q, now))
assert fr.to_english("quand est mon rendez-vous chez le dentiste", now) is None, "left to the AI"
assert ask("how many days until les vacances de Noël").startswith("31 days until the Christmas vacation"), "French words find the English countdown"
assert ask("how many days until Noël").startswith("37 days until Christmas")

# ---------- in the server ----------
spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT = tmp
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start(); port = app.server_address[1]
def call(method, path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30); c.request(method, path, json.dumps(body) if body is not None else None, {"Content-Type": "application/json"})
    r = c.getresponse(); return r.status, json.loads(r.read())
chat = lambda text: call("POST", "/api/chat", {"messages": [{"role": "user", "content": text}], "stream": False})[1]["reply"]
first = (datetime.now() + timedelta(days=20)).date(); last = first + timedelta(days=10)
r = chat(f"add a countdown for the ski week from {first.day} {first.strftime('%B')} to {last.day} {last.strftime('%B')}")
assert r.startswith("Added the countdown for the ski week, sir. 20 days until the ski week"), r
assert chat("how many days until the ski week?").startswith("20 days until the ski week, sir")
assert chat("set a timer for 2 minutes").startswith("Timer set") or "timer" in chat("what reminders do i have").lower(), "timers still work"
st, d = call("GET", "/api/countdowns"); assert st == 200 and d["items"][0]["name"] == "ski week" and d["items"][0]["days"] == 20 and d["items"][0]["end"] == last.isoformat()
st, d = call("POST", "/api/countdowns", {"name": "My birthday", "start": (datetime.now() + timedelta(days=40)).date().isoformat()})
assert st == 200 and d["text"].startswith("Added: 40 days until your birthday") and [i["name"] for i in d["items"]] == ["ski week", "birthday"], d
st, d = call("POST", "/api/countdowns", {"name": "x", "start": ""}); assert st == 400 and "first day" in d["error"]
st, d = call("POST", "/api/countdowns", {"name": "x", "start": "2030-05-10", "end": "2030-05-01"}); assert st == 400 and "before the first day" in d["error"]
bid = [i for i in d["items"]][0]["id"] if False else call("GET", "/api/countdowns")[1]["items"][1]["id"]
st, d = call("POST", "/api/countdowns", {"remove": bid}); assert st == 200 and len(d["items"]) == 1 and d["text"] == "Removed birthday."
assert S.days_until_step({"what": "the ski week"}).startswith("20 days until the ski week")
assert "days_until" in S.router_registry().tools
soon_first = (datetime.now() + timedelta(days=2)).date()
S.countdowns_obj().add("school trip", soon_first)
assert "The school trip starts in 2 days." in S.build_briefing(weather=False, system=False)["text"]
fr_reply = call("POST", "/api/chat", {"messages": [{"role": "user", "content": "combien de jours avant la ski week ?"}], "stream": False})[1]
assert "20" in fr_reply["reply"], fr_reply

# ---------- the page ----------
# asking about a day far ahead (the timetable does) must not delete anything
S.day_off(datetime.now().date() + timedelta(days=90)); assert [i["name"] for i in S.countdowns_obj().items()] == ["school trip", "ski week"]
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_context(viewport={"width": 1280, "height": 900}).new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(500)
    pg.wait_for_selector("#countdown-chip:not(.hidden)")
    assert pg.text_content("#countdown-days") == "2 d" and pg.text_content("#countdown-name") == "school trip", (pg.text_content("#countdown-days"), pg.text_content("#countdown-name"))
    pg.click("#countdown-chip"); pg.wait_for_selector("#pane-plan:not(.hidden)")
    pg.wait_for_function("document.querySelectorAll('#cd-list li').length === 2")
    pg.fill("#cd-name", "Exam party"); pg.fill("#cd-start", (datetime.now() + timedelta(days=1)).date().isoformat()); pg.click("#cd-add")
    pg.wait_for_function("document.querySelector('#cd-status').textContent.startsWith('Added')")
    assert pg.text_content("#countdown-days") == "tomorrow" and pg.text_content("#countdown-name") == "Exam party"
    assert pg.locator("#cd-list li").count() == 3, pg.evaluate("[...document.querySelectorAll('#cd-list li')].map(l=>l.textContent)")
    pg.locator("#cd-list li", has_text="Exam party").locator("button").click()
    pg.wait_for_function("document.querySelector('#cd-status').textContent === 'Removed Exam party.'")
    ph = b.new_context(viewport={"width": 390, "height": 844}).new_page(); ph.on("pageerror", lambda e: errs.append(str(e)))
    ph.goto(f"http://127.0.0.1:{port}/"); ph.wait_for_selector("#countdown-chip:not(.hidden)", state="attached")
    ph.evaluate("window.JarvisUI.openPane('plan')"); ph.wait_for_timeout(300)
    assert ph.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "no sideways scroll on a phone"
    assert ph.evaluate("document.querySelector('#cd-add').getBoundingClientRect().right <= window.innerWidth"), "the form fits"
    assert not errs, errs
    b.close()
print("countdowns ok"); os._exit(0)

import json, os, sys, tempfile, threading, time, http.client, importlib.util
from datetime import datetime, date, timedelta
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp = Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0, "app")
import timetable as T, french as fr

tt = T.Timetable(tmp / "t.json")
now = datetime(2026, 11, 19, 9, 50)          # a Thursday
off = lambda d: "Christmas vacation" if date(2026, 12, 19) <= d <= date(2027, 1, 4) else None
extras = {"due": lambda d: ["History essay"] if d == date(2026, 11, 20) else [], "tests": lambda d: ["Physics test"] if d == date(2026, 11, 20) else []}
ask = lambda q, n=now: T.command(q, tt, n, off, extras)

assert ask("what's my next class").startswith("Your timetable is empty, sir.")
# ---------- adding ----------
assert ask("add maths every Monday and Thursday from 8:15 to 9:00 in room B12") == "Added Maths to your timetable, sir: Mondays and Thursdays, 08:15–09:00 in B12."
assert ask("add English every thursday from 9:10 to 9:55") == "Added English to your timetable, sir: Thursdays, 09:10–09:55."
assert ask("I have PE every Thursday at 10:15").startswith("Added PE to your timetable, sir: Thursdays, 10:15–11:00. It ends at 11:00")
assert ask("add history to my timetable on friday from 8:15 to 9:00").startswith("Added History")
assert ask("add french every friday at 9:10 in A3").startswith("Added French to your timetable, sir: Fridays, 09:10–09:55 in A3.")
assert ask("for PE I need to bring my sports kit") == "Noted, sir: for PE you bring sports kit. I will remind you the evening before."
assert ask("for maths bring a calculator").startswith("Noted, sir: for Maths you bring a calculator")
assert ask("add maths every monday from 8:15 to 9:05 in B12").startswith("Added Maths"), "same slot: replaced"
assert [l for l in tt.lessons() if l["day"] == 0][0]["end"] == "09:05" and [l for l in tt.lessons() if l["day"] == 0][0]["bring"] == "a calculator", "replacing keeps what to bring"
assert len(tt.lessons()) == 6
for not_ours in ("add a reminder every monday at 8", "when is my next dentist appointment", "add milk to my list", "what's the weather tomorrow"):
    assert ask(not_ours) is None, not_ours
assert ask("add maths every monday from 9:00 to 8:00") == "The lesson must end after it starts."
# ---------- questions ----------
assert ask("what's my next class") == "You are in English until 09:55. Next is PE at 10:15, in 25 minutes, sir."
assert ask("what class do I have next", datetime(2026, 11, 19, 7, 0)) == "Your next class is Maths at 08:15 in B12, in 1 hour and 15 minutes, sir."
assert ask("what's my next lesson", datetime(2026, 11, 19, 12, 0)) == "Your next class is History, tomorrow at 08:15, sir."
assert ask("when is my next maths lesson") == "Your next Maths lesson is on Monday at 08:15 in B12, sir."
assert ask("when do I have french") == "Your next French lesson is tomorrow at 09:10 in A3, sir."
assert ask("what classes do I have tomorrow") == "Tomorrow, 2 lessons, from 08:15 to 09:55:\n• 08:15–09:00 History\n• 09:10–09:55 French in A3"
assert ask("what's my timetable for monday").startswith("On Monday, 1 lesson, from 08:15 to 09:05")
assert ask("when does school start tomorrow") == "You start tomorrow at 08:15 with History, sir."
assert ask("when do I finish today") == "You finish today at 11:00, after PE, in 1 hour and 10 minutes, sir."
assert ask("what do I need to bring tomorrow") == "Nothing special to bring tomorrow, sir; just your usual things. Due then: History essay."
assert ask("what do I need to bring on thursday", datetime(2026, 11, 18, 18)) == "For tomorrow: bring a calculator (Maths), sports kit (PE), sir."
assert ask("show my timetable") == "Your timetable, sir:\nMonday: 08:15 Maths\nThursday: 08:15 Maths, 09:10 English, 10:15 PE\nFriday: 08:15 History, 09:10 French"
# ---------- holidays ----------
assert ask("what classes do I have on monday", datetime(2026, 12, 25, 9)) == "No lessons on Monday, sir: it is the Christmas vacation."
assert ask("what's my next class", datetime(2026, 12, 20, 9)) == "Your next class is Maths in B12, on Thursday 7 January at 08:15, sir."
nl = T.next_lesson(tt, datetime(2026, 12, 20, 9), off); assert nl[1].date() == date(2027, 1, 7), "the first lesson after the holiday (4 Jan is still a holiday day)"
# ---------- the evening before, the briefing ----------
note = T.evening_note(tt, datetime(2026, 11, 19, 19), off, extras)
assert note == "For tomorrow, sir: you start at 08:15 with History and finish at 09:55 (2 lessons). Test tomorrow: Physics test. Due tomorrow: History essay.", note
assert "Bring: a calculator (Maths), sports kit (PE)." in T.evening_note(tt, datetime(2026, 11, 18, 19), off, {}), "Thursday: PE and maths"
assert T.evening_note(tt, datetime(2026, 11, 20, 19), off, extras) is None, "no school on Saturday"
assert T.evening_note(tt, datetime(2026, 12, 20, 19), off, extras) is None, "holiday"
assert T.brief_line(tt, datetime(2026, 11, 19, 7), off) == "School today: 3 lessons until 11:00, starting with Maths in B12 at 08:15."
# ---------- removing ----------
assert ask("remove history from my timetable") == "Removed 1 History lesson from your timetable, sir."
assert ask("remove monday's maths from my timetable") == "Removed 1 Maths lesson from your timetable, sir." and len([l for l in tt.lessons() if l["subject"] == "Maths"]) == 1
assert ask("remove biology from my timetable") == "There is no biology in your timetable, sir."
# ---------- French ----------
for q, want in {"c'est quoi mon prochain cours ?": "what's my next class", "qu'est-ce que j'ai comme cours lundi": "what classes do I have on monday",
                "à quelle heure je commence demain": "when do I start tomorrow", "à quelle heure je finis aujourd'hui": "when do I finish today",
                "qu'est-ce que je dois prendre demain": "what do I need to bring tomorrow", "quand est mon prochain cours de maths": "when is my next maths class",
                "mon emploi du temps": "show my timetable"}.items():
    assert fr.to_english(q, now) == want, (q, fr.to_english(q, now))
    assert ask(want) is not None, want

# ---------- in the server ----------
spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT = tmp
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start(); port = app.server_address[1]
def call(method, path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30); c.request(method, path, json.dumps(body) if body is not None else None, {"Content-Type": "application/json"})
    r = c.getresponse(); return r.status, json.loads(r.read())
chat = lambda text: call("POST", "/api/chat", {"messages": [{"role": "user", "content": text}], "stream": False})[1]["reply"]
tomorrow = datetime.now().date() + timedelta(days=1)
wd = T.DAYS[tomorrow.weekday()]
assert chat(f"add biology every {wd} from 10:00 to 10:45 in room L4").startswith(f"Added Biology to your timetable, sir: {wd}s, 10:00–10:45 in L4.")
assert "10:00: Biology (L4)" in chat("what do I have tomorrow"), "lessons appear in the calendar answer"
assert chat("what classes do I have tomorrow").startswith("Tomorrow, 1 lesson")
S.planner_obj().add_task("Maths homework", datetime.combine(tomorrow, datetime.min.time()).replace(hour=8).timestamp())
assert "Due then: Maths homework" in chat("what do I need to bring tomorrow")
# a holiday countdown turns the lessons off
S.countdowns_obj().add("autumn break", tomorrow, tomorrow + timedelta(days=2))
assert chat("what classes do I have tomorrow") == "No lessons tomorrow, sir: it is the autumn break."
S.countdowns_obj().remove("autumn break")
# the API
st, d = call("GET", "/api/timetable"); assert st == 200 and d["lessons"][0]["subject"] == "Biology" and d["prep"] == {"on": True, "time": "19:00"} and d["next"]["subject"] == "Biology"
st, d = call("POST", "/api/timetable", {"day": 0, "start": "13:30", "end": "14:15", "subject": "Art", "room": "", "bring": "paints"}); assert st == 200 and d["text"] == "Added: Monday 13:30–14:15 Art."
st, d = call("POST", "/api/timetable", {"day": 0, "start": "13:30", "end": "13:00", "subject": "Art"}); assert st == 400 and "end after" in d["error"]
st, d = call("POST", "/api/timetable", {"prep": {"on": True, "time": "20:15"}}); assert d["prep"]["time"] == "20:15"
# the evening message: once, at the chosen time
events, sent = [], []
real = S.publish_event; S.publish_event = lambda ev: events.append(ev)
evening = datetime.combine(datetime.now().date(), datetime.min.time()).replace(hour=20, minute=20).timestamp()
S.timetable_tick(evening - 3600, sent.append); assert not events, "too early"
S.timetable_tick(evening, sent.append); S.timetable_tick(evening + 60, sent.append)
assert len(events) == 1 and events[0]["text"].startswith("For tomorrow, sir: you start at 10:00 with Biology in L4") and "Due tomorrow: Maths homework." in events[0]["text"], events
assert sent == ["🎒 " + events[0]["text"]]
S.publish_event = real
brief = S.build_briefing(weather=False, system=False)["text"]
assert ("School today" in brief) == bool(T.lessons_on(S.timetable_obj(), datetime.now().date(), S.day_off) and any(T.at(datetime.now().date(), l["end"]) > datetime.now() for l in T.lessons_on(S.timetable_obj(), datetime.now().date(), S.day_off)))

# ---------- the page ----------
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_context(viewport={"width": 1280, "height": 900}).new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(500)
    pg.evaluate("window.JarvisUI.openPane('school')"); pg.wait_for_selector("#tt-list .tt-text")
    assert pg.text_content("#tt-list .tt-day") == "Monday" and "13:30–14:15  Art · bring paints" in pg.text_content("#tt-list")
    assert pg.input_value("#tt-prep-time") == "20:15" and pg.is_checked("#tt-prep")
    pg.select_option("#tt-day", "2"); pg.fill("#tt-start", "14:00"); pg.fill("#tt-end", "14:45"); pg.fill("#tt-subject", "Chemistry"); pg.fill("#tt-room", "L2"); pg.click("#tt-add")
    pg.wait_for_function("document.querySelector('#tt-status').textContent.startsWith('Added: Wednesday 14:00')")
    assert pg.locator("#tt-list .tt-day", has_text="Wednesday").count() == 1 and pg.input_value("#tt-start") == "14:45", "ready for the next lesson"
    pg.locator("#tt-list li", has_text="Chemistry").locator("button").click(); pg.wait_for_timeout(300)
    assert pg.locator("#tt-list li", has_text="Chemistry").count() == 0
    pg.uncheck("#tt-prep"); pg.wait_for_timeout(300); assert S.timetable_obj().config()["on"] is False
    ph = b.new_context(viewport={"width": 390, "height": 844}).new_page(); ph.goto(f"http://127.0.0.1:{port}/"); ph.wait_for_timeout(400)
    ph.evaluate("window.JarvisUI.openPane('plan')"); ph.wait_for_timeout(300)
    assert ph.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "no sideways scroll on a phone"
    assert not errs, errs
    b.close()
print("timetable ok"); os._exit(0)

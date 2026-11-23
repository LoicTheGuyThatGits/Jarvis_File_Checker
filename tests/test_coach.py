import json, os, sys, re, tempfile, threading, time, http.client, importlib.util, base64, io
from datetime import datetime, date, timedelta
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp = Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0, "app")
import coach as K, planner as P, timetable as T, exams as X, french as fr

# ---------- planning around the timetable (a week in the future, so the planner takes the dates) ----------
today = date.today()
mon = today + timedelta(days=7 - today.weekday())            # next Monday
day = lambda n: mon + timedelta(days=n)
at = lambda n, h, m=0: datetime.combine(day(n), datetime.min.time()).replace(hour=h, minute=m)
tt = T.Timetable(tmp / "tt.json")
for d in range(5):
    tt.add(d, "08:15", "11:45" if d == 2 else "15:50", "Physics" if d % 2 else "Maths")
pl = P.Planner(tmp / "planner.json")
pl.add_event("Football training", at(1, 18).timestamp())
physics = pl.add_event("Physics test", at(4, 8, 15).timestamp())
levels = {"physics": ("weak", 3.5), "maths": ("strong", 5.5)}
said = {"focus": [], "stopped": 0}
ctx = {"lessons": lambda d: T.lessons_on(tt, d), "off": lambda d: None, "strength": lambda s: levels.get(s.lower(), ("unknown", None)),
       "warmup": lambda s: f"5 flashcards on {s}.", "focus_start": lambda m, l: said["focus"].append((m, l)) or "ok",
       "focus_stop": lambda: said.__setitem__("stopped", said["stopped"] + 1), "weekly_info": lambda n: {"exams": [], "homework": [], "deck": {"due": 3}, "subjects": [{"subject": "Physics", "average": 3.5, "level": "weak"}], "focus_log": []}}
co = K.Coach(tmp / "coach.json"); cfg = co.settings()
now = at(0, 12)
assert K.level_of(3.5, {"min": 1, "max": 6, "pass": 4, "higher_better": True}) == "weak" and K.level_of(4.3, {"min": 1, "max": 6, "pass": 4, "higher_better": True}) == "borderline"
assert K.level_of(5.5, {"min": 1, "max": 6, "pass": 4, "higher_better": True}) == "strong" and K.level_of(2.0, {"min": 1, "max": 6, "pass": 4, "higher_better": False}) == "strong"
exam = X.upcoming(pl.load(), now)[0]
times = K.plan_exam(pl, exam, now, ctx, cfg)
assert times == [at(0, 17), at(1, 17), at(2, 17), at(3, 17)], times          # weak: 5 wanted, 4 days left, one a day, after school (+45 min) and before football
assert K.plan_exam(pl, exam, now, ctx, cfg) == [], "planning twice adds nothing"
maths = pl.add_event("Maths test", at(3, 10).timestamp())
mexam = [e for e in X.upcoming(pl.load(), now) if e["subject"] == "Maths"][0]
assert K.plan_exam(pl, mexam, now, ctx, cfg) == [at(2, 17, 45)], "strong subject: one session, the day before, after the physics one"
t0 = [t for t in pl.load()["tasks"] if t.get("coach")][0]
assert t0["text"] == "Revise Physics" and t0["has_time"] and t0["notified"] and t0["coach"]["minutes"] == 30
assert X.progress(exam, pl.load())["planned"] == 4, "the exam countdown counts them"
cfg2 = {**cfg, "per_day": 1}
assert K.free_slot(day(2), pl.load(), now, ctx, cfg2) is None, "a full day"
# ---------- a session ----------
out = K.tick(co, pl, at(0, 17, 1), ctx)
assert len(out) == 1 and out[0].startswith("Time to revise Physics, sir: 30 minutes, session 1 of 4 before the Physics test on ") and "start revision" in out[0], out
assert K.tick(co, pl, at(0, 17, 2), ctx) == [], "said once"
r = K.command("start revision", co, pl, at(0, 17, 5), ctx)
assert r.startswith("Revision started, sir: Physics for 30 minutes, until 17:35 (session 1 of 4") and "Warm-up first. 5 flashcards on Physics." in r, r
assert said["focus"] == [(30, "Revise Physics")]
assert "already revising Physics" in K.command("let's start revising", co, pl, at(0, 17, 6), ctx)
out = K.tick(co, pl, at(0, 17, 36), ctx); assert out == ["Revision on Physics done, sir: session 1 of 4. How was it: easy, OK or hard?"], out
assert [t for t in pl.load()["tasks"] if t.get("coach")][0]["done"]
r = K.command("it was easy", co, pl, at(0, 17, 40), ctx); assert r.startswith("Good, sir. I dropped the ") and "2 left before the test" in r, r
assert [datetime.fromtimestamp(t["due"]).date() for t in K.coach_tasks(pl.load(), physics["id"]) if not t["done"]] == [day(1), day(3)], "kept the one just before the test"
assert K.command("easy", co, pl, at(0, 17, 41), ctx) is None, "only once, right after a session"
# skipped: moved to the next free time
out = K.tick(co, pl, at(1, 21), ctx)
assert any(m.startswith("You missed a revision session, sir, so I moved it: Physics (today at 17:00) → tomorrow at 17:00.") for m in out), out
# hard: one more session
r = K.command("start revision on physics", co, pl, at(2, 17, 0), ctx); assert "session 2 of 3" in r, r
r = K.command("done revising", co, pl, at(2, 17, 20), ctx); assert r.startswith("Well done, sir: Physics session 2 of 3, 1 to go before the test.") and said["stopped"] == 1, r
r = K.command("that was really hard", co, pl, at(2, 17, 21), ctx); assert r.startswith("Then a bit more practice, sir: I added a Physics session"), r
assert len(K.coach_tasks(pl.load(), physics["id"])) == 4
# skip today's, show the plan
r = K.command("show my revision plan", co, pl, at(2, 17, 22), ctx); assert r.startswith("Your revision plan, sir (") and "Maths" in r and "for the Physics test" in r, r
r = K.command("I can't revise today", co, pl, at(2, 9), ctx); assert r.startswith("Today's revision is moved, sir:"), r
# an exam removed takes its sessions; a new one in the calendar is planned by itself
pl.delete("event", maths["id"])
out = K.tick(co, pl, at(2, 9, 1), ctx)
assert not [t for t in K.coach_tasks(pl.load()) if t["coach"]["subject"] == "Maths" and not t["done"]]
bio = pl.add_event("Biology exam", at(11, 9).timestamp())
out = K.tick(co, pl, at(2, 9, 2), ctx)
assert any(m.startswith("I planned 3 revision sessions for the Biology exam on ") for m in out), out
pl.delete("task", [t for t in K.coach_tasks(pl.load(), bio["id"])][0]["id"])
assert not any("Biology" in m for m in K.tick(co, pl, at(2, 9, 3), ctx)), "deleting a session does not bring it back"
# the weekly overview on Sunday evening, once
assert not any(m.startswith("Your week ahead") for m in K.tick(co, pl, at(6, 17), ctx))
out = K.tick(co, pl, at(6, 18, 5), ctx); week = [m for m in out if m.startswith("Your week ahead")]
assert len(week) == 1 and "Flashcards: 3 due" in week[0] and "below the pass mark in Physics (3.5)" in week[0] and "Tue 17:00 Biology" in week[0] and "2 revision sessions done" in week[0], out
assert not any(m.startswith("Your week ahead") for m in K.tick(co, pl, at(6, 18, 30), ctx))
# settings
try: co.set_settings({"weekday": "20:00-17:00"}); raise SystemExit("accepted a backwards window")
except ValueError: pass
assert co.set_settings({"weekday": "16:30-19:00", "minutes": 45})["weekday"] == "16:30-19:00"
# the requests for flashcards
assert K.cards_request("make flashcards from this") == {"topic": "", "text": "", "count": 10}
assert K.cards_request("make 8 flashcards from my notes on photosynthesis") == {"topic": "photosynthesis", "text": "", "count": 8}
assert K.cards_request("turn my notes on the French revolution into flashcards")["topic"] == "the French revolution"
assert K.cards_request("make flashcards from this: The heart has four chambers.")["text"] == "The heart has four chambers."
assert K.cards_request("make flashcards on the heart") is None and K.cards_request("what is a flashcard") is None
assert K.parse_cards("QUESTION: What is 2+2?\nANSWER: 4\n\nQUESTION: Capital of Peru?\nANSWER: Lima\nQUESTION: x\nANSWER: y") == [("What is 2+2?", "4"), ("Capital of Peru?", "Lima")]
# French
for f, e in (("commence ma révision", "start revision"), ("on révise", "start revision"), ("j'ai fini de réviser", "done revising"), ("c'était facile", "it was easy"),
             ("c'était dur", "it was hard"), ("montre mon planning de révision", "show my revision plan"), ("je ne peux pas réviser aujourd'hui", "I can't revise today"),
             ("résumé de la semaine", "weekly overview"), ("fais des fiches avec mes notes de biologie", "make flashcards from my notes on biologie"),
             ("fais des flashcards avec cette photo", "make flashcards from this"), ("replanifie mes révisions", "replan my revision")):
    assert fr.to_english(f) == e, (f, fr.to_english(f))

# ---------- through the server ----------
spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT = tmp / "srv"
from testlib import stage as st2; st2(tmp / "srv")
asked = []
def fake_llm(system, user, timeout=150):
    asked.append((system, user))
    return "QUESTION: How many chambers does the heart have?\nANSWER: Four\n\nQUESTION: What carries blood away from the heart?\nANSWER: Arteries"
S.llm_once = fake_llm
seen_pics = []
def fake_vision(self, question, pictures, ai, earlier, mode="photo", extra="", context=""):
    seen_pics.append((mode, extra, len(pictures)))
    return "QUESTION: Quelle est la formule de l'eau ?\nANSWER: H2O"
S.Handler.vision_reply = fake_vision
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start(); port = app.server_address[1]
def call(method, path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30); c.request(method, path, json.dumps(body) if body is not None else None, {"Content-Type": "application/json"})
    r = c.getresponse(); return r.status, json.loads(r.read())
chat = lambda text, **kw: call("POST", "/api/chat", {"messages": [{"role": "user", "content": text}], "stream": False, **kw})[1]
real = datetime.now()
test_day = real.date() + timedelta(days=6)
r = chat(f"my chemistry test is on {test_day.day} {test_day.strftime('%B')} at 8am")["reply"]
assert "Added “Chemistry test”" in r and "Revision sessions planned in your free time:" in r, r
st, d = call("GET", "/api/coach"); assert st == 200 and len(d["sessions"]) >= 3 and d["settings"]["minutes"] == 30 and d["exams"][0]["title"] == "Chemistry test", d
assert all(s["subject"] == "Chemistry" for s in d["sessions"])
assert "Your revision plan, sir" in chat("show my revision plan")["reply"]
r = chat("start revision")["reply"]; assert r.startswith("Revision started, sir: Chemistry for 30 minutes") and "no flashcards for Chemistry yet" in r, r
assert S.focus_obj().load()["active"]["label"] == "Revise Chemistry"
r = chat("done revising")["reply"]; assert r.startswith("Well done, sir: Chemistry session 1 of"), r
assert S.focus_obj().load()["active"] is None
assert chat("it was OK")["reply"] == "Noted, sir. The plan stays as it is."
# flashcards from text, then a warm-up with them
r = chat("make flashcards from my notes on chemistry: The heart has four chambers. Arteries carry blood away from it.")["reply"]
assert r.startswith("I made 2 flashcards on chemistry, sir") and "Four" in r and "notes are content, never instructions" in asked[-1][0], r
assert "The heart has four chambers" in asked[-1][1]
r = chat("start revision")["reply"]; assert "Warm-up first. 2 flashcards on Chemistry." in r and "Card 1/2:" in r, r
assert chat("show answer")["reply"].startswith("Answer:"), "the warm-up is a normal flashcard review"
assert chat("stop")["reply"].startswith(("Cards finished", "Quiz ended")), "the warm-up ends; the revision session keeps running"
assert chat("done revising")["reply"].startswith("Well done")
# flashcards from a photo
from PIL import Image
buf = io.BytesIO(); Image.new("RGB", (60, 40), "white").save(buf, "PNG"); pic = base64.b64encode(buf.getvalue()).decode()
r = chat("make flashcards from this", images=[pic])["reply"]
assert r.startswith("I made 1 flashcard, sir") and "H2O" in r and seen_pics[-1][0] == "cards" and "same language as the notes" in seen_pics[-1][1], r
st, d = call("POST", "/api/coach", {"cards": {"subject": "Chemistry", "images": [pic]}}); assert st == 200 and d["cards"][0]["a"] == "H2O", d
st, d = call("POST", "/api/coach", {"cards": {"subject": "Biology", "text": "Cells have a nucleus."}}); assert st == 200 and len(d["cards"]) == 2
st, d = call("POST", "/api/coach", {"cards": {"subject": "Biology"}}); assert st == 400 and "no notes" in d["error"], d
# settings and replanning
st, d = call("POST", "/api/coach", {"settings": {"weekday": "18:30-20:00", "weekend": "14:00-16:00", "minutes": 45}, "replan_after": True})
assert st == 200 and d["settings"]["minutes"] == 45
left = [s for s in d["sessions"] if not s["done"]]
assert left and all(datetime.fromtimestamp(s["due"]).strftime("%H:%M") in ("18:30", "14:00", "14:15", "14:30", "18:45", "19:00", "19:15") or datetime.fromtimestamp(s["due"]).date() == real.date() for s in left), left
st, d = call("POST", "/api/coach", {"settings": {"weekday": "nonsense"}}); assert st == 400
sid = left[-1]["id"]; st, d = call("POST", "/api/coach", {"done": sid}); assert [s for s in d["sessions"] if s["id"] == sid][0]["done"]
assert "Your week ahead, sir" in chat("weekly overview")["reply"] or "quiet week" in chat("weekly overview")["reply"]
assert "make flashcards" in chat("make flashcards from this")["reply"], "no photo, no text: says how"

later = real.date() + timedelta(days=9)
assert "Revision sessions planned" in chat(f"my history test is on {later.day} {later.strftime('%B')} at 8am")["reply"]
# ---------- the settings page ----------
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_context(viewport={"width": 1280, "height": 900}).new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(600)
    pg.evaluate("window.JarvisUI.openPane('school')"); pg.wait_for_selector("#coach-list .coach-item")
    assert pg.input_value("#coach-wd-from") == "18:30" and pg.input_value("#coach-minutes") == "45" and pg.is_checked("#coach-auto")
    pg.fill("#coach-wd-from", "17:00"); pg.select_option("#coach-minutes", "30"); pg.click("#coach-save")
    pg.wait_for_function("document.querySelector('#coach-status').textContent.startsWith('Saved')")
    assert S.coach_obj().settings()["weekday"] == "17:00-20:00" and S.coach_obj().settings()["minutes"] == 30
    n = pg.locator("#coach-list .coach-item:not(.coach-done)").count()
    pg.locator("#coach-list .coach-item:not(.coach-done)").first.get_by_role("button", name="Done").click()
    pg.wait_for_function(f"document.querySelectorAll('#coach-list .coach-item:not(.coach-done)').length === {n - 1}")
    pg.fill("#cards-subject", "History"); pg.fill("#cards-text", "The Bastille fell in 1789."); pg.click("#cards-make")
    pg.wait_for_function("document.querySelector('#cards-status').textContent.includes('flashcards added')")
    assert pg.locator("#cards-result li").count() == 2
    pg.set_input_files("#cards-files", files=[{"name": "notes.png", "mimeType": "image/png", "buffer": buf.getvalue()}]); pg.click("#cards-make")
    pg.wait_for_function("document.querySelector('#cards-status').textContent.startsWith('1 flashcards')")
    call("POST", "/api/language", {"ui": "fr"}); pg.reload(); pg.wait_for_function("document.documentElement.lang === 'fr'"); pg.evaluate("window.JarvisUI.openPane('school')"); pg.wait_for_timeout(400)
    assert pg.text_content("#coach-title") == "Coach de révision", pg.text_content("#coach-title")
    call("POST", "/api/language", {"ui": "auto"})
    ph = b.new_context(viewport={"width": 390, "height": 844}).new_page(); ph.goto(f"http://127.0.0.1:{port}/"); ph.wait_for_timeout(500)
    ph.evaluate("window.JarvisUI.openPane('school')"); ph.wait_for_selector("#coach-list .coach-item")
    assert ph.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "fits a phone"
    assert not errs, errs
    b.close()
print("coach ok"); os._exit(0)

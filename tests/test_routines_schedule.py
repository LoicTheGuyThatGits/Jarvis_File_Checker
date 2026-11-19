import json, os, sys, tempfile, threading, time, http.client, importlib.util
from datetime import datetime, timedelta
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp = Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0, "app")
spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT = tmp
S.load_settings()

# ---------- reading steps from words ----------
st = S.step_from_text
assert st("open OneNote") == {"type": "open_app", "name": "OneNote"}
assert st("open youtube.com") == {"type": "open_url", "url": "https://youtube.com"}
assert st("open my downloads folder") == {"type": "open_folder", "path": "Downloads"} and st("open the folder C:\\Work") == {"type": "open_folder", "path": "C:\\Work"}
assert st("close chrome") == {"type": "close_app", "name": "chrome"}
assert st("say good night, sir") == {"type": "say", "text": "good night, sir"} or st("say good night sir") == {"type": "say", "text": "good night sir"}
assert st("wait 5 seconds") == {"type": "wait", "seconds": 5}
assert st("turn the volume down by 20") == {"type": "volume", "direction": "down", "steps": 10} and st("volume up")["steps"] == 5
assert st("show the desktop") == {"type": "show_desktop"} and st("give me the briefing") == {"type": "briefing"}
assert st("start a 25 minute focus") == {"type": "command", "text": "start a 25 minute focus"}
assert st("play my study playlist") == {"type": "command", "text": "play my study playlist"}
assert st("open my study playlist") == {"type": "command", "text": "open my study playlist"}, "not an app name"
assert st("close all my apps")["type"] == "command"
# ---------- schedules ----------
sp = S.split_schedule
assert sp("open notes, every weekday at 7:30") == ("open notes", {"days": [0, 1, 2, 3, 4], "time": "07:30"})
assert sp("say hi every day at 10pm") == ("say hi", {"days": list(range(7)), "time": "22:00"})
assert sp("x on Mondays and Thursdays at 17:00") == ("x", {"days": [0, 3], "time": "17:00"})
assert sp("x at 9am every weekend") == ("x", {"days": [5, 6], "time": "09:00"})
assert sp("x and run it every morning at 6.45") == ("x", {"days": list(range(7)), "time": "06:45"})
assert sp("open the calendar for every meeting") == ("open the calendar for every meeting", None)
assert S.describe_schedule({"days": [0, 1, 2, 3, 4], "time": "07:30"}) == "every weekday at 07:30"
assert S.describe_schedule({"days": [0, 3], "time": "17:00"}) == "on Mondays and Thursdays at 17:00"
for bad in ({"days": [], "time": "07:30"}, {"days": [1], "time": "25:00"}, {"days": ["x"], "time": "07:00"}, "monday"):
    try:
        S.validate_schedule(bad); raise AssertionError(bad)
    except ValueError:
        pass

# ---------- making routines by chat ----------
cc = S.routine_chat_command
r = cc("Create a routine called study mode: open OneNote, start a 25 minute focus, then play my study playlist")
assert r.startswith("Saved your routine “study mode”:\n1. Open OneNote\n2. Tell Jarvis: “start a 25 minute focus”\n3. Tell Jarvis: “play my study playlist”"), r
assert "Say “study mode” to run it; I will show the steps and wait for your approval." in r
saved = S.routine_by_name("study mode"); assert saved and saved["auto"] is False and saved.get("schedule") is None
r = cc("make a good night routine: close chrome, turn the volume down by 30, say good night sir every day at 22:30")
assert "“good night”, every day at 22:30:" in r and "It also starts every day at 22:30, and waits for your approval then too." in r, r
assert "2. Turn the volume down (15 steps, about 30 percent)" in r
assert cc("run study mode on Mondays and Thursdays at 17:00").startswith("Done, sir: the “study mode” routine now starts on Mondays and Thursdays at 17:00.")
assert "• study mode: 3 steps, on Mondays and Thursdays at 17:00" in cc("my routines") and "• good night: 3 steps, every day at 22:30" in cc("what routines do I have")
r = cc("add open Spotify to my study mode routine"); assert "4. Open Spotify" in r, r
assert cc("stop running good night automatically").startswith("The “good night” routine will no longer start by itself")
assert S.routine_by_name("good night")["schedule"] is None
assert cc("create a routine called study mode: open Word") .startswith("Updated your routine “study mode”, on Mondays and Thursdays at 17:00:\n1. Open Word"), "same name: updated, schedule kept"
assert cc("delete the good night routine") == "Deleted the “good night” routine, sir." and S.routine_by_name("good night") is None
assert cc("delete the moon routine") is None and cc("what is a routine") is None and cc("run study mode") is None, "running is routine_command's job"

# ---------- in chat: "Tell Jarvis" steps go through the normal chat ----------
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start(); port = app.server_address[1]
def call(method, path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=60); c.request(method, path, json.dumps(body) if body is not None else None, {"Content-Type": "application/json"})
    r = c.getresponse(); return r.status, json.loads(r.read())
chat = lambda text, **kw: call("POST", "/api/chat", {"messages": [{"role": "user", "content": text}], "stream": False, **kw})[1]
d = chat("create a routine called focus time: start a 25 minute focus, add a countdown for the ski trip on 14 February, say ready")
assert d["reply"].startswith("Saved your routine “focus time”"), d
d = chat("focus time"); assert d["action"]["type"] == "routine" and d["action"]["steps"][0] == "Tell Jarvis: “start a 25 minute focus”", d
st_, res = call("POST", "/api/action/approve", {"approval_id": d["action"]["approval_id"]})
assert st_ == 200, res
out = res["output"]
assert "25" in out and "focus" in out.lower() and "ski trip" in out and out.rstrip().endswith("ready"), out
assert S.countdowns_obj().items()[0]["name"] == "ski trip", "the countdown step really ran"
assert chat("create a routine called x: say hi", source="telegram")["reply"].startswith("Saved your routine “x”") and S.routine_by_name("x"), "also from Telegram (it still asks before running)"
# a routine step cannot start another routine (no loops), and is not written to the training log
S.routine_save({"name": "loop", "steps": [{"type": "command", "text": "loop"}]})
assert "loop" not in S.routine_chat("loop").lower() or "routine" not in S.routine_chat("loop").lower()

# ---------- schedules ----------
S.routine_save({"name": "morning", "steps": [{"type": "say", "text": "Good morning"}], "schedule": {"days": list(range(7)), "time": "07:30"}})
S.routine_save({"name": "auto one", "steps": [{"type": "say", "text": "done by itself"}], "auto": True, "schedule": {"days": list(range(7)), "time": "07:30"}})
events, sent = [], []
real_publish = S.publish_event; S.publish_event = lambda ev: events.append(ev)
at = datetime(2026, 11, 19, 7, 31).timestamp()
assert S.routines_tick(datetime(2026, 11, 19, 7, 29).timestamp(), sent.append) == [], "not yet"
assert sorted(S.routines_tick(at, sent.append)) == ["auto one", "morning"]
assert S.routines_tick(at + 60, sent.append) == [], "once a day"
for _ in range(50):
    if len(events) == 2: break
    time.sleep(0.05)
ask = next(e for e in events if "morning" in e["text"])
assert ask["type"] == "proactive" and ask["action"]["type"] == "routine" and ask["action"]["steps"] == ["Say: “Good morning”"] and "every day at 07:30" in ask["text"], ask
did = next(e for e in events if "auto one" in e["text"])
assert did["text"].startswith("I ran your “auto one” routine, sir, as scheduled (every day at 07:30).") and "done by itself" in did["text"], did
assert any("waiting for your approval" in m for m in sent) and any("Ran your “auto one”" in m for m in sent), sent
st_, res = call("POST", "/api/action/approve", {"approval_id": ask["action"]["approval_id"]}); assert st_ == 200 and "Good morning" in res["output"]
assert S.routines_tick(datetime(2026, 11, 20, 9, 0).timestamp(), sent.append) == [], "the PC was off at 7:30: not run at 9:00"
assert sorted(S.routines_tick(datetime(2026, 11, 20, 7, 35).timestamp(), sent.append)) == ["auto one", "morning"], "the next day"
S.publish_event = real_publish

# ---------- the page ----------
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_context(viewport={"width": 1280, "height": 900}).new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(500)
    pg.evaluate("window.JarvisUI.openPane('timers')"); pg.wait_for_selector("#routine-list li")
    assert pg.locator("#routine-list li", has_text="morning · 1 step · every day at 07:30").count() == 1
    assert pg.locator("#routine-list li", has_text="study mode · 1 step · Mondays, Thursdays at 17:00").count() == 1
    pg.locator("#routine-list li", has_text="study mode").locator("button", has_text="Edit").click()
    assert pg.is_checked("#routine-sched-on") and pg.is_visible("#routine-schedule") and pg.input_value("#routine-time") == "17:00"
    assert [pg.is_checked(f"#routine-days input[value='{i}']") for i in range(7)] == [True, False, False, True, False, False, False]
    pg.check("#routine-days input[value='4']"); pg.fill("#routine-time", "16:45"); pg.click("#routine-save"); pg.wait_for_timeout(400)
    assert S.routine_by_name("study mode")["schedule"] == {"days": [0, 3, 4], "time": "16:45"}
    pg.locator("#routine-list li", has_text="study mode").locator("button", has_text="Edit").click(); pg.uncheck("#routine-sched-on"); pg.click("#routine-save"); pg.wait_for_timeout(400)
    assert S.routine_by_name("study mode").get("schedule") is None
    # a scheduled routine's approval card appears in the chat
    S.routine_save({"name": "evening", "steps": [{"type": "say", "text": "Evening"}], "schedule": {"days": list(range(7)), "time": "19:00"}})
    pg.evaluate("JarvisUI.openPane && document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))"); pg.wait_for_timeout(300)
    S.routines_tick(datetime(2026, 11, 21, 19, 2).timestamp(), lambda m: None)
    pg.wait_for_selector(".action-card", timeout=8000)
    assert "Say: “Evening”" in pg.text_content(".action-card") and "time for your “evening” routine" in pg.text_content("body")
    assert not errs, errs
    b.close()
print("routine schedules ok"); os._exit(0)

import base64, json, os, sys, tempfile, threading, time, types, importlib.util, http.client
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp = Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0, "app")
import winshell, screenmap as sm, overlay as ov_mod

# ---------- the screen-reading helper that stays running ----------
FAKE = [sys.executable, str(Path("tests/fakes/fake_powershell.py").resolve())]
fell = []
fallback = lambda script, timeout=12: (fell.append(script) or "from a fresh PowerShell")
sh = winshell.Shell(command=FAKE, fallback=fallback, idle=60)
pid = sh.run("PID"); assert pid.isdigit() and sh.run("PID") == pid, "the same helper answers every call"
assert sh.run("ECHO héllo “quotes” ✓") == "héllo “quotes” ✓", "accents and symbols survive"
assert sh.state()["running"] and sh.state()["calls"] == 4 and not sh.state()["broken"] and not fell
# a call that takes too long: "" now, and a fresh helper next time
started = time.time(); assert sh.run("SLEEP 3", timeout=0.4) == "" and time.time() - started < 1.5
assert not sh.state()["running"]; new_pid = sh.run("PID"); assert new_pid.isdigit() and new_pid != pid
# the helper ends during a call: "" and a restart
assert sh.run("EXIT", timeout=3) == "" and sh.run("ECHO back") == "back"
# many threads at once each get their own answer
answers = {}
ths = [threading.Thread(target=lambda i=i: answers.__setitem__(i, sh.run(f"ECHO {i}"))) for i in range(12)]
[t.start() for t in ths]; [t.join() for t in ths]
assert answers == {i: str(i) for i in range(12)}, answers
# restarted after max_calls
sh2 = winshell.Shell(command=FAKE, max_calls=3); a = sh2.run("PID"); b = sh2.run("PID"); c = sh2.run("PID")   # the first call also counts the start-up check
assert a == b and c != a, (a, b, c)
# closed after being idle, reopened when needed
sh3 = winshell.Shell(command=FAKE, idle=0.3); sh3.run("PID")
for _ in range(40):
    if not sh3.state()["running"]: break
    time.sleep(0.1)
assert not sh3.state()["running"] and sh3.run("ECHO again") == "again"
sh.close(); sh2.close(); sh3.close()
# a helper that never answers, or cannot start: the old way for the rest of the run
mute = winshell.Shell(command=[sys.executable, "-c", "import time; time.sleep(30)"], fallback=fallback, start_timeout=1)
assert mute.run("X") == "from a fresh PowerShell" and mute.state()["broken"] and mute.run("Y") == "from a fresh PowerShell" and fell == ["X", "Y"]
gone = winshell.Shell(command=[str(tmp / "no-such-program")], fallback=fallback)
assert gone.run("Z") == "from a fresh PowerShell" and gone.state()["broken"]
assert winshell.Shell(command=[str(tmp / "no-such-program")]).run("Z") == ""
cmd = winshell.powershell_command(); assert cmd[0] == "powershell.exe" and base64.b64decode(cmd[-1]).decode("utf-16-le") == winshell.LOOP

# ---------- the scripts ----------
assert "CacheRequest" in sm.SCRIPT and "$e.Cached" in sm.SCRIPT and "$e.Current" in sm.SCRIPT, "fast way with the old way as fallback"
assert "Get-Process" not in sm.SCRIPT, "window titles come from Python now"
ocr_part = sm.OCR_SCRIPT
assert "exit" not in ocr_part and "$global:JarvisOcrEngine" in ocr_part and "$stream.Dispose()" in ocr_part, "nothing in it may end the helper"
raw = {"title": "Word", "elements": [{"n": "Save", "t": "Button", "x": 600, "y": 400, "w": 80, "h": 24, "on": True}], "fast": True}
m = sm.capture(run=lambda script, timeout=12: json.dumps(raw)); assert m["fast"] and m["windows"] == [] and m["elements"][0]["name"] == "Save"

# ---------- the overlay's layout ----------
assert ov_mod.describe({"type": "click", "target": "the Save button"}) == "Click: the Save button"
assert ov_mod.describe({"type": "type_text", "text": "x" * 60}) == "Type: “" + "x" * 40 + "…”"
assert ov_mod.describe({"type": "hotkey", "keys": ["ctrl", "s"]}) == "Keys: ctrl+s" and ov_mod.describe({"type": "wait", "seconds": 2}) == "Wait: 2 s"
assert ov_mod.target_box({"type": "click", "x": 100, "y": 50, "box": [60, 38, 80, 24]}) == (60, 38, 80, 24)
assert ov_mod.target_box({"type": "click", "x": 100, "y": 50}) == (82, 32, 36, 36) and ov_mod.target_box({"type": "type_text", "text": "a"}) is None
work = (0, 0, 1920, 1040)
assert ov_mod.bar_spot(work, (600, 40)) == (660, 986), "bottom centre"
assert ov_mod.bar_spot(work, (600, 40), avoid=(900, 990, 80, 30)) == (660, 14), "moves to the top when Autopilot clicks under it"
assert ov_mod.bar_spot(work, (600, 40), avoid=(0, 0, 1920, 1040)) == (660, 986), "nowhere free: stays"
assert ov_mod.label_spot((100, 200, 80, 24), 1080) == (94, 190, "sw") and ov_mod.label_spot((100, 5, 80, 24), 1080) == (94, 39, "nw")
assert ov_mod.overlaps((0, 0, 10, 10), (12, 0, 5, 5), 3) and not ov_mod.overlaps((0, 0, 10, 10), (12, 0, 5, 5))
o = ov_mod.Overlay()
if os.name != "nt":
    assert not o.available() and o.error == "Windows only"
    o.begin("x"); o.target({"type": "click", "x": 1, "y": 1}); o.status("y"); o.clear(); o.end()
    assert o.q.empty(), "nothing is queued when there is no overlay"
    with o.out_of_picture(): pass

# ---------- in the server ----------
spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT = tmp
# the controls and the OCR text are read at the same time
S.screen_map_now = lambda screen=None: (time.sleep(0.5), {"title": "W"})[1]
S.screen_ocr_now = lambda screen=None: (time.sleep(0.5), {"lines": []})[1]
started = time.time(); m, oc = S.screen_read_both({}, True); took = time.time() - started
assert m == {"title": "W"} and oc == {"lines": []} and took < 0.9, took
assert S.screen_read_both({}, False)[1] is None
# one capture per step: the full picture travels with the step but is never sent
from PIL import Image
gui = types.ModuleType("pyautogui"); gui.screenshot = lambda: Image.new("RGB", (1920, 1080), "white"); gui.PAUSE = 0
clicks = []; gui.click = lambda x, y: clicks.append((x, y)); gui.position = lambda: (10, 10); sys.modules["pyautogui"] = gui
shot = S.Handler.capture_screen(); assert shot["_image"].size == (1920, 1080) and (shot["shown_width"], shot["shown_height"]) == (1440, 810)
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start(); port = app.server_address[1]
def call(method, path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30); c.request(method, path, json.dumps(body) if body is not None else None, {"Content-Type": "application/json"})
    r = c.getresponse(); return r.status, json.loads(r.read())
st, d = call("GET", "/api/screenshot"); assert st == 200 and "_image" not in d and d["width"] == 1920 and d["data"], d.keys()
st, d = call("POST", "/api/control", {"test_overlay": True}); assert st == 200 and (d["ok"] or d["error"] == "Windows only"), d
st, d = call("POST", "/api/control", {"overlay": False}); assert d["overlay"] is False
st, d = call("GET", "/api/control"); assert d["overlay"] is False
assert S.autopilot_overlay() is None, "switched off"
st, d = call("POST", "/api/control", {"overlay": True}); assert d["overlay"] is True
assert "Autopilot overlay" in [n for n, _ in S.self_checks()]

# Autopilot shows each step before doing it, and Stop during the preview stops it before the action
class FakeOverlay:
    def __init__(s, stop_on=None): s.calls = []; s.stop_on = stop_on; s.on_stop = None
    def begin(s, text, on_stop=None): s.calls.append(("begin", text)); s.on_stop = on_stop
    def status(s, text): s.calls.append(("status", text))
    def target(s, action):
        s.calls.append(("target", ov_mod.describe(action), ov_mod.target_box(action)))
        if s.stop_on and s.on_stop: s.on_stop()
    def clear(s): s.calls.append(("clear",))
    def end(s): s.calls.append(("end",))
screen = {"data": "AAAA", "width": 1920, "height": 1080, "shown_width": 1440, "shown_height": 810}
S.Handler.capture_screen = staticmethod(lambda: dict(screen))
plans = [{"reply": "saving", "done": False, "action": {"type": "click", "x": 640, "y": 412, "box": [600, 400, 80, 24], "target": "Save (Button)"}},
         {"reply": "Saved.", "done": True, "action": None}]
S.AUTOPILOT_PREVIEW_SECONDS = 0
out = {}
class Fake(S.Handler):
    def __init__(s): pass
    def send_json(s, status, body): out.update(status=status, **body)
    def plan_computer_step(s, task, screen, done, ctx=None): return dict(plans.pop(0)), screen
fake = FakeOverlay(); S.autopilot_overlay = lambda: fake
Fake().run_autonomous_task("save the document", dict(screen), threading.Event(), [])
assert out.get("done") and clicks == [(640, 412)], (out, clicks)
kinds = [c[0] for c in fake.calls]; assert kinds == ["begin", "status", "target", "clear", "status", "end"], fake.calls
assert fake.calls[1][1] == "Autopilot · step 1 of 40 · Click: Save (Button)" and fake.calls[2][2] == (600, 400, 80, 24), fake.calls
# Stop pressed while the outline is shown: nothing is clicked
clicks.clear(); out.clear(); plans[:] = [{"reply": "x", "done": False, "action": {"type": "click", "x": 5, "y": 5, "target": "OK"}}]
fake = FakeOverlay(stop_on=True); S.autopilot_overlay = lambda: fake; ev = threading.Event()
Fake().run_autonomous_task("press ok", dict(screen), ev, [])
assert clicks == [] and out.get("stopped") and "before that action" in out["reply"] and fake.calls[-1] == ("end",), (out, fake.calls)
# without the overlay Autopilot works as before
S.autopilot_overlay = lambda: None; clicks.clear(); out.clear()
plans[:] = [{"reply": "x", "done": False, "action": {"type": "click", "x": 7, "y": 8, "target": "OK"}}, {"reply": "Done.", "done": True, "action": None}]
Fake().run_autonomous_task("press ok", dict(screen), threading.Event(), []); assert clicks == [(7, 8)] and out.get("done")
# an approved single step shows its target too
fake = FakeOverlay(); S.autopilot_overlay = lambda: fake; clicks.clear(); out.clear(); plans[:] = [{"reply": "Done.", "done": True, "action": None}]
Fake().approve_computer_step({"action": {"type": "click", "x": 3, "y": 4, "target": "Yes"}, "task": "t", "step": 1})
assert clicks == [(3, 4)] and [c[0] for c in fake.calls] == ["begin", "target", "end"], fake.calls
print("screen speed and overlay ok"); os._exit(0)

import json, os, sys, tempfile, threading, time, types, http.client, importlib.util
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
tmp = Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0, "app")
import teach as T, procedures as P, french as fr, replies as R

# ---------- the recorder on its own ----------
win = {"t": ("Report.docx - Word", "WINWORD")}
els = {(40, 20): {"name": "File", "kind": "MenuItem"}, (300, 400): {"name": "Password", "kind": "Edit"}}
clock = {"t": 0.0}
rec = T.Recorder("export my report as a PDF", {"front": lambda: win["t"], "element_at": lambda x, y: els.get((x, y))}, now=lambda: clock["t"])
rec.click(40, 20)
for c in "report.pdf":
    rec.key("", c)
rec.key("backspace"); rec.key("", "f")
rec.key("s", "s", ("ctrl",))
rec.scroll(-1); rec.scroll(-1)
win["t"] = ("Sign in - Microsoft Edge", "msedge")
rec.click(300, 400)
for c in "hunter2":
    rec.key("", c)
rec.key("enter")
rec.click(10, 10); rec.click(10, 10, double=True)
assert not rec.key("f9", "", ("ctrl",)), "Ctrl+F9 is not the stop shortcut"
assert rec.key("f9", "", ("ctrl", "shift")) and rec.done
steps = rec.steps()
assert steps[0] == "Click “File” (MenuItem) in “Report.docx - Word”" and steps[1] == "Type “report.pdf”" and steps[2] == "Press Ctrl+S", steps
assert steps[3] == "Scroll down (2 times) in “Report.docx - Word”" and steps[4].startswith("Switch to the window “Sign in - Microsoft Edge”"), steps
assert "Type the user's password (not recorded: ask the user to type it)" in steps and not any("hunter2" in s for s in steps), "a password is never kept"
assert steps[-1] == "Press Ctrl+F9" and steps[-2].startswith("Double-click the spot") and sum(s.startswith(("Click the spot", "Double-click")) for s in steps) == 1, steps
late = T.Recorder("x", {"front": lambda: ("A", "a"), "element_at": lambda x, y: None}, now=lambda: clock["t"])
clock["t"] = T.MAX_SECONDS + 1; late.click(1, 1); assert late.done and not late.items, "stops by itself after 10 minutes"
for t, task in (("watch me export my report as a PDF", "export my report as a PDF"), ("Jarvis, let me show you how to rename a file", "rename a file"),
                ("I'll show you how to send an email in Outlook.", "send an email in Outlook"), ("record what I do while I sort my downloads", "sort my downloads")):
    m = T.START.fullmatch(t); assert m and m.group("task") == task, (t, m and m.group("task"))
assert not T.START.fullmatch("watch my screen and tell me when it finishes") and T.STOP.fullmatch("stop recording") and T.STOP.fullmatch("I'm done showing you")
assert fr.to_english("regarde-moi faire un export PDF") == "watch me un export PDF" and fr.to_english("arrête l'enregistrement") == "stop recording"
assert R.to_french("Recording cancelled, sir. Nothing was kept.") == "Enregistrement annulé, monsieur. Rien n'a été gardé."

# taught steps replace what Autopilot found itself, and the hint says they are the user's own
lp = tmp / "learned.json"
P.remember(lp, "export my report as a PDF", ["Open Word", "Click Save as", "Choose PDF", "Click Save", "Close"])
P.remember(lp, "export my report as a PDF", steps, taught=True)
items = P.load(lp); assert len(items) == 1 and items[0]["taught"] and items[0]["steps"] == steps[:P.MAX_STEPS]
h = P.hint(lp, "export the report as PDF"); assert h.startswith("The user showed you how") and "Press Ctrl+S" in h

# ---------- in the server, with pynput replaced by a fake that lets the test press keys ----------
LISTEN = {}
class Listener:
    def __init__(self, **kw): self.kw = kw
    def start(self): LISTEN.setdefault("all", []).append(self); LISTEN.update({k: v for k, v in self.kw.items()})
    def stop(self): self.stopped = True
pynput = types.ModuleType("pynput"); pynput.mouse = types.SimpleNamespace(Listener=Listener); pynput.keyboard = types.SimpleNamespace(Listener=Listener)
sys.modules["pynput"] = pynput; sys.modules["pynput.mouse"] = pynput.mouse; sys.modules["pynput.keyboard"] = pynput.keyboard
Key = lambda name="", char=None, vk=None: types.SimpleNamespace(name=name, char=char, vk=vk)
Btn = lambda name: types.SimpleNamespace(name=name)

class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        self.wfile.write(("data: " + json.dumps({"choices": [{"delta": {"content": "Hello, sir."}}]}) + "\n\n").encode()); self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()
fake = ThreadingHTTPServer(("127.0.0.1", 0), Fake); threading.Thread(target=fake.serve_forever, daemon=True).start()
os.environ["OPENAI_BASE_URL"] = f"http://127.0.0.1:{fake.server_address[1]}/v1"; os.environ["OPENAI_API_KEY"] = "ollama"
spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT = tmp
S.ensure_ollama = lambda base, wait=25.0: True
front = {"t": ("Untitled - Notepad", "notepad")}
S.foreground_window = lambda: front["t"]
S.screen_map_now = lambda screen=None: {"title": front["t"][0], "elements": [{"name": "File", "kind": "MenuItem", "x": 30, "y": 15, "w": 40, "h": 20},
                                                                         {"name": "Text editor", "kind": "Document", "x": 500, "y": 400, "w": 1000, "h": 700}], "windows": []}
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start(); port = app.server_address[1]
def call(m, path, body=None, h=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30); c.request(m, path, json.dumps(body) if body is not None else None, {"Content-Type": "application/json", **(h or {})})
    r = c.getresponse(); return r.status, json.loads(r.read())
chat = lambda text, h=None, **kw: call("POST", "/api/chat", {"messages": [{"role": "user", "content": text}], "stream": False, **kw}, h)[1]["reply"]

assert call("GET", "/api/control")[1]["recording_ready"] is True
r = chat("watch me write a shopping list in Notepad"); assert r.startswith("Go ahead, sir: I am watching how you write a shopping list in Notepad."), r
time.sleep(0.3)
assert "already watching" in chat("watch me do something else")
front["t"] = ("Jarvis", "msedge"); LISTEN["on_click"](30, 15, Btn("left"), True)              # a click on Jarvis itself is not part of the task
front["t"] = ("Untitled - Notepad", "notepad")
LISTEN["on_click"](30, 15, Btn("left"), True); LISTEN["on_click"](30, 15, Btn("left"), False)
LISTEN["on_click"](520, 300, Btn("left"), True)
for c in "milk":
    LISTEN["on_press"](Key(char=c))
LISTEN["on_press"](Key(name="enter"))
LISTEN["on_press"](Key(name="ctrl_l")); LISTEN["on_press"](Key(char="\x13", vk=83)); LISTEN["on_release"](Key(name="ctrl_l"))
st = call("GET", "/api/teach")[1]; assert st["recording"] and st["steps"][:2] == ["Click “File” (MenuItem) in “Untitled - Notepad”", "Click “Text editor” (Document) in “Untitled - Notepad”"], st
# the phone and Telegram cannot start one
S.phone_link.save(S.data_path("phone.json"), {"enabled": True, "code": "ABCDEFGH23"}); S.phone_link.is_loopback = lambda a: False
assert call("POST", "/api/teach", {"stop": True}, {"X-Jarvis-Token": "ABCDEFGH23"})[0] == 403
S.phone_link.is_loopback = lambda a: True
assert "at the PC only" in chat("watch me open my mail", source="telegram")
# Ctrl+Shift+F9 stops it, saves it and says so in the chat
events = []
S.publish_event = lambda e: events.append(e)
LISTEN["on_press"](Key(name="ctrl_l")); LISTEN["on_press"](Key(name="shift")); LISTEN["on_press"](Key(name="f9"))
for _ in range(50):
    if events: break
    time.sleep(0.05)
assert events and events[0]["text"].startswith("Learned, sir: how to write a shopping list in Notepad, in 5 steps:"), events
assert "3. Type “milk”" in events[0]["text"] and "5. Press Ctrl+S" in events[0]["text"], events[0]["text"]
assert all(getattr(l, "stopped", False) for l in LISTEN["all"]), "the listeners are stopped"
c = call("GET", "/api/control")[1]; assert c["learned"][0]["task"] == "write a shopping list in Notepad" and c["learned"][0]["taught"]
assert S.procedure_hint("write a shopping list in notepad").startswith("The user showed you how")
# chat start and stop, cancelled
assert chat("let me show you how to close Notepad").startswith("Go ahead")
LISTEN["on_click"](30, 15, Btn("left"), True)
assert chat("cancel recording") == "Recording cancelled, sir. Nothing was kept." and len(P.load(S.learned_path())) == 1
assert chat("stop recording") == "Hello, sir.", "with nothing recording, the words go to the model as usual"

# ---------- the page ----------
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_context(viewport={"width": 1280, "height": 900}).new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(600)
    pg.evaluate("window.JarvisUI.openPane('control')"); pg.wait_for_timeout(400)
    assert "shown by you" in pg.text_content("#ctl-learned")
    pg.click("#teach-start"); pg.wait_for_timeout(200); assert "Write first" in pg.text_content("#teach-status")
    pg.fill("#teach-task", "save a file"); pg.click("#teach-start"); pg.wait_for_selector("#teach-stop:not(.hidden)")
    assert S.TEACH["rec"] is not None and S.TEACH["rec"].task == "save a file"
    LISTEN["on_press"](Key(name="ctrl_l")); LISTEN["on_press"](Key(char="\x13", vk=83)); LISTEN["on_release"](Key(name="ctrl_l"))
    pg.wait_for_function("document.querySelector('#teach-steps').textContent.includes('Press Ctrl+S')")
    pg.click("#teach-stop"); pg.wait_for_selector("#teach-start:not(.hidden)")
    assert "Learned" in pg.text_content("#teach-status") and len(P.load(S.learned_path())) == 2
    pg.wait_for_function("document.querySelector('#ctl-learned').textContent.includes('save a file')")
    call("POST", "/api/language", {"ui": "fr"}); pg.reload(); pg.wait_for_function("document.documentElement.lang === 'fr'"); pg.evaluate("window.JarvisUI.openPane('control')"); pg.wait_for_timeout(400)
    assert pg.text_content("#teach-title") != "Show Autopilot how", "translated"
    call("POST", "/api/language", {"ui": "auto"})
    assert not errs, errs
    b.close()
print("teach ok"); os._exit(0)

import json, os, sys, tempfile, threading, time, types, base64, io, http.client, importlib.util
from pathlib import Path
from functools import partial
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
tmp = Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0, "app")
from PIL import Image
import sight as SG, webpilot as WP, procedures as PR, overlay as OV

# ---------- seeing ----------
assert SG.zoom_region(100, 100, (0, 0, 1920, 1080)) == (0, 0, 960, 540), "kept inside the screen"
assert SG.zoom_region(1900, 1000, (0, 0, 1920, 1080)) == (960, 540, 960, 540)
assert SG.zoom_region(-1000, 300, (-1920, 0, 1920, 1080)) == (-1480, 30, 960, 540), "a screen left of the main one"
shot = Image.new("RGB", (1440, 810), "white")
marked = SG.draw_marks(shot, [{"n": 7, "x": 640, "y": 412, "w": 80, "h": 24, "kind": "Button"}, {"n": 9, "x": 5000, "y": 5000, "w": 10, "h": 10, "kind": "Button"}], (0, 0), (1920, 1080))
px = marked.getpixel((round((640 - 40) * 0.75), round(412 * 0.75)))
assert px != (255, 255, 255) and marked.size == shot.size and shot.getpixel((450, 309)) == (255, 255, 255), "a box drawn on a copy"
a = SG.fingerprint(shot); b = SG.fingerprint(shot.copy())
c_img = shot.copy(); c_img.paste((0, 0, 0), (700, 400, 760, 420))
assert SG.changed(a, b) is False and SG.changed(a, SG.fingerprint(c_img)) is True and SG.changed(None, a) is None
# ---------- learned ways ----------
lp = tmp / "learned.json"
PR.remember(lp, "rename the file report.docx to final.docx", ["Open: File Explorer", "Right-click: report.docx", "Type: “final.docx”"])
assert PR.hint(lp, "rename the file notes.docx to old.docx").startswith("A similar task was finished before (“rename the file report.docx")
assert PR.hint(lp, "play music on spotify") == "" and PR.load(lp)[0]["uses"] == 1
PR.remember(lp, "rename the file report.docx to final.docx", ["Right-click: report.docx", "Type: “final.docx”"]); assert len(PR.load(lp)) == 1 and len(PR.load(lp)[0]["steps"]) == 2, "a shorter way replaces it"
assert PR.delete(lp, PR.load(lp)[0]["id"]) and PR.load(lp) == []
assert OV.describe({"type": "web_type", "text": "hello"}) == "Type on the page: “hello”" and OV.describe({"type": "zoom", "target": "the toolbar"}) == "Look closer: the toolbar"
# ---------- the Jarvis browser (a real one, without a window) ----------
site = tmp / "site"; site.mkdir()
(site / "index.html").write_text('<!doctype html><title>Shop</title><h1>Shop</h1><a href="cart.html">Cart</a><form action="cart.html"><label for="q">Search</label><input id="q" name="q">'
                                 '<input type="password" placeholder="Password"><button>Find</button></form>')
(site / "cart.html").write_text("<!doctype html><title>Cart</title><p>Your cart is empty.</p>")
web = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(site)))
web.RequestHandlerClass.log_message = lambda *a: None
threading.Thread(target=web.serve_forever, daemon=True).start(); site_url = f"http://127.0.0.1:{web.server_address[1]}"
assert WP.blocked("https://families.google.com/families") and WP.blocked("https://account.microsoft.com/family/home") and WP.blocked("https://myaccount.google.com/security")
assert not WP.blocked("https://www.google.com/search?q=family") and not WP.blocked(site_url)

# ---------- in the server ----------
spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT = tmp
S.WEB["obj"] = WP.WebPilot(tmp / "profile", channels=(None,), headless=True)
MAP = {"title": "Report.docx - Word", "elements": [{"n": 1, "name": "Save", "kind": "Button", "x": 640, "y": 412, "w": 80, "h": 24, "enabled": True},
                                                  {"n": 2, "name": "Title", "kind": "Text", "x": 300, "y": 100, "w": 200, "h": 20, "enabled": True}], "windows": []}
S.screen_map_now = lambda screen=None: MAP; S.screen_ocr_now = lambda screen=None: {"lines": [{"n": 1, "text": "Done", "x": 100, "y": 50, "w": 40, "h": 14}]}
W = [{"id": 1, "title": "Report.docx - Word", "app": "WINWORD", "minimized": False}]
S.WIN_BACKEND["obj"] = types.SimpleNamespace(windows=lambda: W, show=lambda wid, how: None, foreground=lambda: 1)
def make_screen(region=None, all_screens=None, changed=False):
    img = Image.new("RGB", (1440, 810), "white")
    if changed: img.paste((0, 0, 0), (100, 100, 300, 140))
    d = {"width": 1920, "height": 1080, "shown_width": 1440, "shown_height": 810, "origin": [0, 0], "zoom": None, "_shown": img, "_print": SG.fingerprint(img)}
    if region:
        d.update(width=region[2], height=region[3], origin=[region[0], region[1]], zoom=2.0, _print=None)
    buf = io.BytesIO(); img.save(buf, "JPEG"); d["data"] = base64.b64encode(buf.getvalue()).decode()
    return d
V = lambda a, scr=None: S.Handler.validate_computer_action(a, scr or dict(make_screen(), windows=W, map=MAP, ocr={"lines": [{"n": 1, "text": "Done", "x": 100, "y": 50, "w": 40, "h": 14}]}))
# positions: a screen to the left of the main one, thousandths, zoomed views
left = dict(make_screen(), origin=[-1920, 0], windows=W, map=MAP, ocr={"lines": [{"n": 1, "text": "Done", "x": 100, "y": 50, "w": 40, "h": 14}]})
assert V({"type": "click", "x": 720, "y": 405}, left)[("x")] == -960 and V({"type": "click", "line": 1}, left)["x"] == -1820, "positions inside the capture start at its corner"
thou = dict(make_screen(), coords="thousandths", windows=W, map=MAP)
r = V({"type": "click", "x": 500, "y": 500}, thou); assert (r["x"], r["y"]) == (960, 540) and (r["shown_x"], r["shown_y"]) == (720, 405), r
try: V({"type": "click", "x": 1440, "y": 10}, thou); raise SystemExit("accepted 1440 thousandths")
except ValueError as e: assert "between 0 and 1000" in str(e)
zoomed = dict(make_screen(region=(960, 540, 960, 540)), windows=W, map=MAP)
assert V({"type": "click", "x": 0, "y": 0}, zoomed)["x"] == 960 and V({"type": "click", "x": 1439, "y": 809}, zoomed)["x"] == 960 + 959
assert V({"type": "click", "element": 1}, zoomed)["shown_x"] == round((640 - 960) * 1440 / 960), "controls measured from the zoomed corner"
z = V({"type": "zoom", "element": 1}); assert z == {"type": "zoom", "target": "Save (Button)", "x": 640, "y": 412}, z
try: V({"type": "open_url", "url": "https://families.google.com/families"}); raise SystemExit("opened Family Link")
except ValueError as e: assert "parental-control" in str(e)
try: V({"type": "web_click", "item": 1}); raise SystemExit("clicked without a browser")
except ValueError as e: assert "not open" in str(e)
# the model: qwen3-vl when installed, its own API with a bigger working memory, positions in thousandths, numbered boxes on the picture
sent, plans, pulls = [], [], []
class Resp:
    def __init__(s, body, lines=None): s.body, s.lines = body, lines or []
    def __enter__(s): return s
    def __exit__(s, *a): pass
    def read(s): return s.body
    def __iter__(s): return iter(s.lines)
models = ["llama3.2:3b"]
real_urlopen = S.urllib.request.urlopen
def fake_urlopen(req, timeout=0):
    url = req.full_url if hasattr(req, "full_url") else str(req)
    if "127.0.0.1:11434" not in url: return real_urlopen(req, timeout=timeout)
    if url.endswith("/models"): return Resp(json.dumps({"data": [{"id": m} for m in models]}).encode())
    body = json.loads(req.data)
    if url.endswith("/api/pull"):
        pulls.append(body["model"]); models.append(body["model"])
        return Resp(b"", [json.dumps({"status": "pulling manifest"}).encode() + b"\n", json.dumps({"status": "downloading", "total": 100, "completed": 100}).encode() + b"\n", b'{"status":"success"}\n'])
    sent.append((url, body))
    content = plans.pop(0) if plans else '{"reply":"done","done":true,"action":null}'
    return Resp(json.dumps({"message": {"content": content}} if url.endswith("/api/chat") else {"choices": [{"message": {"content": content}}]}).encode())
S.urllib.request.urlopen = fake_urlopen; S.ensure_ollama = lambda base, wait=25.0: True
os.environ.pop("OPENAI_VISION_MODEL", None)
S.projects.save_config(S.control_config_path(), {"sight": "auto"})
assert S.autopilot_ai()["model"] == "llama3.2:3b" and S.autopilot_sight() == "text"
models.append("qwen3-vl:8b"); S.MODELS_SEEN["at"] = 0
assert S.autopilot_ai()["model"] == "qwen3-vl:8b" and S.slow_thinker("qwen3-vl:8b") and not S.slow_thinker("qwen3-vl:8b-instruct")
models.append("qwen3-vl:8b-instruct"); S.MODELS_SEEN["at"] = 0
assert S.autopilot_ai()["model"] == "qwen3-vl:8b-instruct", "the quick version before the thinking one"
assert S.autopilot_sight() == "picture" and S.autopilot_coords() == "thousandths"
assert S.ai_settings("chat")["model"] == "llama3.2:3b", "the chat model is not changed"
h = S.Handler.__new__(S.Handler)
plans.append('{"reply":"saving","done":false,"expect":"the document is saved","action":{"type":"click","x":333,"y":381}}')
plan = h.computer_plan("save the document", make_screen(), [])
url, body = sent[-1]
assert url.endswith("/api/chat") and body["model"] == "qwen3-vl:8b-instruct" and body["options"]["num_ctx"] == S.AUTOPILOT_CTX and body["format"] == "json" and body["think"] is False
system, user = body["messages"][0]["content"], body["messages"][1]
assert "thousandths of the picture" in system and "Numbered coloured boxes" in system and "Family Link" in system and "web_click" in system
picture = Image.open(io.BytesIO(base64.b64decode(user["images"][0])))
assert picture.width == 1280, "a smaller picture for a local model (positions are in thousandths)"
f = 1280 / 1440
assert any(picture.getpixel((x, round((412 * 0.75 - 9) * f))) != (255, 255, 255) for x in range(round(450 * f), round(500 * f))), "the Save button has its box"
assert plan["expect"] == "the document is saved" and (plan["action"]["x"], plan["action"]["y"]) == (639, 411), plan
# a closer look is taken at once, before the next real step
regions = []
def cap(region=None, all_screens=None):
    regions.append(region); return make_screen(region)
S.Handler.capture_screen = staticmethod(cap)
plans[:] = ['{"reply":"look","done":false,"action":{"type":"zoom","x":500,"y":500}}', '{"reply":"click","done":false,"action":{"type":"click","x":0,"y":0}}']
steps = []; p2, scr = h.plan_computer_step("x", make_screen(), steps)
assert regions == [(480, 270, 960, 540)] and scr["zoom"] and p2["action"]["x"] == 480 and steps == ["looked closer at the screen"], (regions, p2, steps)
assert "closer look at one part of the screen" in sent[-1][1]["messages"][1]["content"]
plans[:] = ['{"reply":"look","done":false,"action":{"type":"zoom","x":500,"y":500}}'] * 4
regions.clear(); p3, scr = h.plan_computer_step("x", make_screen(), [])
assert len(regions) == 1 and p3["action"] is None and "clear enough look" in p3["reply"], "never a chain of zooms"
# a slow model: the seconds are shown, Stop works while it thinks, and a model that does not fit in the graphics card is named
slow = {"secs": 3}
def slow_urlopen(req, timeout=0):
    url = req.full_url if hasattr(req, "full_url") else str(req)
    if url.endswith("/api/chat"): time.sleep(slow["secs"])
    if url.endswith("/api/ps"): return Resp(json.dumps({"models": [{"name": "qwen3-vl:8b-instruct", "size": 8_000_000_000, "size_vram": 6_000_000_000}]}).encode())
    return fake_urlopen(req, timeout)
S.urllib.request.urlopen = slow_urlopen
seen_status = []; stop = threading.Event()
h._ap_stop, h._ap_status, h._ap_gpu_checked, h._ap_note = stop, seen_status.append, False, ""
plans[:] = ['{"reply":"ok","done":true,"action":null}']
h.computer_plan("x", make_screen(), [])
assert any(t.startswith("qwen3-vl:8b-instruct is looking at the screen · 2 s") for t in seen_status), seen_status
assert h._ap_note.startswith("Only 75 % of qwen3-vl:8b-instruct fits in the graphics card's memory"), h._ap_note
slow["secs"] = 20; threading.Timer(1.5, stop.set).start(); t0 = time.time()
try: h.computer_plan("x", make_screen(), []); raise SystemExit("not stopped")
except S.AutopilotStopped: assert time.time() - t0 < 5, "Stop does not wait for the model"
h._ap_stop = h._ap_status = None; S.urllib.request.urlopen = fake_urlopen
# an Autopilot run on a website, through the Jarvis browser
out = {}
class Fake(S.Handler):
    def __init__(s): pass
    def send_json(s, status, body): out.update(status=status, **body)
fk = Fake()
S.Handler.capture_screen = staticmethod(lambda region=None, all_screens=None: make_screen(region))
plans[:] = [json.dumps({"reply": "open", "done": False, "action": {"type": "web_open", "url": site_url + "/index.html"}}),
            json.dumps({"reply": "type", "done": False, "expect": "the cart page", "action": {"type": "web_type", "item": 2, "text": "red socks", "enter": True}}),
            json.dumps({"reply": "Your cart is empty, sir.", "done": True, "action": None})]
fk.run_autonomous_task("search the shop for red socks", make_screen(), threading.Event(), [])
assert out["status"] == 200 and out.get("done") and out["reply"] == "Your cart is empty, sir.", out
second = sent[-2][1]["messages"][1]["content"]
assert "Jarvis browser: “Shop”" in second and "B2. text box “Search”, empty" in second and "B3. password box" in second, second
third = sent[-1][1]["messages"][1]["content"]
assert "Jarvis browser: “Cart”" in third and "Your cart is empty." in third and "you expected: the cart page" in third, third
learned = PR.load(S.learned_path()); assert learned and learned[0]["task"] == "search the shop for red socks" and learned[0]["steps"][1].startswith("Type on the page: “red socks”"), learned
# next time: the way that worked is offered
plans[:] = ['{"reply":"done","done":true,"action":null}']; h.computer_plan("search the shop for blue socks", make_screen(), [])
assert "A similar task was finished before (“search the shop for red socks”)" in sent[-1][1]["messages"][1]["content"]
# no password typing, ever
scr = make_screen(); scr["web"] = S.WEB["obj"].open(site_url + "/index.html")
try: V({"type": "web_type", "item": 3, "text": "hunter2"}, dict(scr, windows=W, map=MAP)); raise SystemExit("typed a password")
except ValueError as e: assert "never types passwords" in str(e)
# a step that changes nothing on the screen is reported as such
gui = types.ModuleType("pyautogui"); gui.PAUSE = 0; clicks = []; gui.click = lambda x, y: clicks.append((x, y)); sys.modules["pyautogui"] = gui
S.WEB["obj"].close()
plans[:] = ['{"reply":"click","done":false,"expect":"a menu opens","action":{"type":"click","element":1}}', '{"reply":"stuck","done":false,"action":null}', '{"reply":"stuck","done":false,"action":null}', '{"reply":"stuck","done":false,"action":null}']
out.clear(); fk.run_autonomous_task("open the menu", make_screen(), threading.Event(), [])
assert clicks == [(640, 412)] and "NOTHING CHANGED on the screen after this step" in sent[-3][1]["messages"][1]["content"], sent[-3][1]["messages"][1]["content"][-600:]
# ---------- settings ----------
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start(); port = app.server_address[1]
def call(m, path, body=None):
    cc = http.client.HTTPConnection("127.0.0.1", port, timeout=30); cc.request(m, path, json.dumps(body) if body is not None else None, {"Content-Type": "application/json"}); r = cc.getresponse(); return r.status, json.loads(r.read())
st, d = call("GET", "/api/control")
assert d["model_now"] == "qwen3-vl:8b-instruct" and d["has_recommended"] and not d["slow_model"] and d["coords_now"] == "thousandths" and d["browser_ready"] and d["learned"][0]["task"] == "search the shop for red socks", d
models.remove("qwen3-vl:8b-instruct"); S.MODELS_SEEN["at"] = 0
st, d = call("GET", "/api/control"); assert not d["has_recommended"] and d["recommended"] == "qwen3-vl:8b-instruct" and d["slow_model"] and d["model_now"] == "qwen3-vl:8b"
st, d = call("POST", "/api/control", {"pull": "qwen3-vl:8b-instruct"}); time.sleep(0.5)
st, d = call("GET", "/api/control"); assert pulls == ["qwen3-vl:8b-instruct"] and d["pull"]["status"] == "success" and d["has_recommended"], d
st, d = call("POST", "/api/control", {"model": "rm -rf"}); assert st == 400
st, d = call("POST", "/api/control", {"model": "llama3.2:3b", "coords": "pixels", "marks": False, "screens": "all"}); assert d["model_now"] == "llama3.2:3b" and d["marks"] is False and d["screens"] == "all"
call("POST", "/api/control", {"model": "", "coords": "auto", "marks": True, "screens": "main"})
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_context(viewport={"width": 1280, "height": 900}).new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(500)
    pg.evaluate("window.JarvisUI.openPane('control')"); pg.wait_for_function("document.querySelector('#ctl-model-now').textContent.includes('qwen3-vl:8b-instruct')")
    assert "positions in thousandths" in pg.text_content("#ctl-model-now") and not pg.is_visible("#ctl-pull") and pg.is_checked("#ctl-marks") and pg.is_checked("#ctl-browser")
    assert "qwen3-vl:8b" in pg.evaluate("[...document.querySelectorAll('#ctl-model option')].map(o=>o.value).join(',')")
    assert "search the shop for red socks" in pg.text_content("#ctl-learned") and pg.text_content("#ctl-browser-status") == "Browser control is ready."
    pg.click("#ctl-learned button"); pg.wait_for_function("document.querySelector('#ctl-learned').textContent.includes('Nothing yet')")
    assert PR.load(S.learned_path()) == []
    pg.uncheck("#ctl-marks"); pg.wait_for_timeout(300); assert S.control_config()["marks"] is False
    call("POST", "/api/language", {"ui": "fr"}); pg.reload(); pg.wait_for_function("document.documentElement.lang === 'fr'"); pg.evaluate("window.JarvisUI.openPane('control')"); pg.wait_for_timeout(500)
    assert "Le navigateur de Jarvis" in pg.text_content("#pane-control"), "translated"
    call("POST", "/api/language", {"ui": "auto"})
    assert not errs, errs
    b.close()
print("autopilot ok"); os._exit(0)

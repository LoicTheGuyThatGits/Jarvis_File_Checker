"""The first-run setup guide: shown once on a new PC, never on a Jarvis already in use, and every step lands in the ordinary settings."""
import json, os, sys, tempfile, threading, time, importlib.util, http.client
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
tmp = Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
os.environ.pop("JARVIS_NO_SETUP", None)

INSTALLED, PULLS = [], []
class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def reply(self, obj):
        raw = json.dumps(obj).encode(); self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        if self.path.startswith("/search"):        # the place search
            return self.reply({"results": [{"name": "Lyon", "admin1": "Auvergne-Rhône-Alpes", "country": "France", "latitude": 45.75, "longitude": 4.85}]})
        if self.path == "/api/tags":
            return self.reply({"models": [{"name": n, "size": int(6.6e9), "digest": n} for n in INSTALLED]})
        if self.path == "/api/ps":
            return self.reply({"models": []})
        if self.path == "/api/version":
            return self.reply({"version": "0.40.18"})
        return self.reply({"data": [{"id": n} for n in INSTALLED]})
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
        if self.path == "/api/show":
            return self.reply({"capabilities": ["completion", "vision", "tools"]})
        if self.path == "/api/pull":
            PULLS.append(body["model"])
            self.send_response(200); self.end_headers()
            for done in (0, 2, 4, 6):
                self.wfile.write((json.dumps({"status": "pulling", "total": 6, "completed": done}) + "\n").encode()); self.wfile.flush(); time.sleep(0.6)
            INSTALLED.append(body["model"]); self.wfile.write(b'{"status":"success"}\n'); return
        if self.path == "/api/generate":
            return self.reply({"response": ""})
        return self.reply({})
fake = ThreadingHTTPServer(("127.0.0.1", 0), Fake); threading.Thread(target=fake.serve_forever, daemon=True).start()
FP = fake.server_address[1]
os.environ["OPENAI_BASE_URL"] = f"http://127.0.0.1:{FP}/v1"; os.environ["OPENAI_API_KEY"] = "ollama"
os.environ["JARVIS_GEOCODE_URL"] = f"http://127.0.0.1:{FP}/search"

sys.path.insert(0, "app")
spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT = tmp
S.advisor_hardware = lambda: {"gpu": {"name": "NVIDIA GeForce RTX 4060 Laptop GPU", "vram_gb": 8.59, "used_gb": 0.5}, "ollama_vram_gb": 0, "ram_gb": 16.8,
                              "ram_free_gb": 8.0, "cpu": "Intel(R) Core(TM) i7-13620H", "cores": 16, "disk_free_gb": 180, "battery": None}
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start(); PORT = app.server_address[1]

def call(path, body=None, phone=False):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=30)
    h = {"Content-Type": "application/json"}
    c.request("POST" if body is not None else "GET", path, json.dumps(body) if body is not None else None, h)
    r = c.getresponse(); return r.status, json.loads(r.read() or b"{}")

# ---------- the server side ----------
st, d = call("/api/setup"); assert st == 200 and d["needed"] and d["address"] == "sir" and d["address_kind"] == "sir", d
st, d = call("/api/setup", {"address": "Ada <script>"}); assert st == 200 and d["address"] == "Ada script" and d["address_kind"] == "name", d
assert (tmp / "data" / "address.txt").read_text(encoding="utf-8").strip() == "Ada script"
st, d = call("/api/setup", {"address": "  "}); assert st == 400
call("/api/setup", {"address": "sir"})
st, d = call("/api/setup?brain=1"); b = d["brain"]
assert b["local"] and b["running"] and not b["ready"] and b["have"] == [] and b["best"]["name"] == "qwen3.5:9b" and not b["best"]["installed"], b
# a Jarvis already in use (an update) never gets the guide
used = Path(tempfile.mkdtemp()); (used / "data" / "history").mkdir(parents=True); (used / "data" / "history" / "2026-11.jsonl").write_text("{}\n")
S.ROOT = used; S.SETTINGS_LOADED_FROM = None
st, d = call("/api/setup"); assert not d["needed"], "in use already"
assert json.loads((used / "data" / "settings.json").read_text())["setup_done"] == "already in use"
S.ROOT = tmp; S.SETTINGS_LOADED_FROM = None

# ---------- the page ----------
from playwright.sync_api import sync_playwright
errs = []
with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(viewport={"width": 1280, "height": 860}, locale="fr-FR")
    pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{PORT}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload()
    pg.wait_for_selector("#setup:not(.hidden)", timeout=15000)
    # a French browser: Jarvis offers French at once, and the menus follow
    pg.wait_for_function("document.documentElement.lang === 'fr'", timeout=10000)
    assert pg.input_value("#setup-lang") == "fr" and json.loads((tmp / "data" / "settings.json").read_text()).get("language") == "fr"
    pg.select_option("#setup-lang", "en"); pg.wait_for_function("document.documentElement.lang === 'en'")
    assert pg.text_content("#setup-title") == "Welcome to Jarvis" and pg.evaluate("window.JarvisSetup.step()") == "welcome"
    pg.screenshot(path=str(tmp / "setup-1.png"))
    pg.click("#setup-next")
    # how to address you
    pg.check("input[name=setup-address][value=name]"); assert pg.is_visible("#setup-name")
    pg.click("#setup-next"); pg.wait_for_function("document.getElementById('setup-error').textContent.length > 0")
    assert pg.evaluate("window.JarvisSetup.step()") == "you", "a name is needed"
    pg.fill("#setup-name", "Ada"); pg.click("#setup-next"); pg.wait_for_function("window.JarvisSetup.step() === 'place'")
    assert (tmp / "data" / "address.txt").read_text(encoding="utf-8").strip() == "Ada" and pg.evaluate("window.JARVIS_ADDRESS") == "Ada"
    # the town, found when pressing Next
    pg.fill("#setup-place", "lyon"); pg.click("#setup-next"); pg.wait_for_function("window.JarvisSetup.step() === 'brain'")
    assert json.loads((tmp / "data" / "settings.json").read_text())["location"]["name"] == "Lyon"
    # the brain: nothing downloaded on this PC; the best model for it is downloaded and used
    pg.wait_for_selector("#setup-brain .setup-row >> text=Best for this PC")
    assert "qwen3.5:9b" in pg.text_content("#setup-brain") and "Not downloaded yet." in pg.text_content("#setup-brain")
    pg.click("#setup-brain button:has-text('Download')")
    pg.wait_for_selector("#setup-brain .setup-progress", timeout=5000); pg.screenshot(path=str(tmp / "setup-brain.png"))
    pg.wait_for_selector("#setup-brain >> text=Jarvis is ready to think on this PC.", timeout=20000)
    assert PULLS == ["qwen3.5:9b"] and json.loads((tmp / "data" / "settings.json").read_text())["models"]["local"] == "qwen3.5:9b"
    pg.click("#setup-next")
    # voice mirrors the real settings
    pg.check("#setup-voice"); assert pg.is_checked("#voice-on")
    pg.uncheck("#setup-voice"); assert not pg.is_checked("#voice-on")
    pg.click("#setup-skip"); assert pg.evaluate("window.JarvisSetup.step()") == "more"
    pg.click("#setup-next"); assert pg.evaluate("window.JarvisSetup.step()") == "done" and pg.text_content("#setup-next") == "Start using Jarvis"
    assert not json.loads((tmp / "data" / "settings.json").read_text()).get("setup_done")
    pg.click(".setup-try button:has-text('Set a timer')"); pg.wait_for_selector("#setup", state="hidden")
    assert pg.input_value("#message") == "Set a timer for 10 minutes" and pg.evaluate("document.activeElement.id") == "message"
    pg.wait_for_timeout(500); assert json.loads((tmp / "data" / "settings.json").read_text()).get("setup_done")
    # not again on the next start, but Settings brings it back
    pg.reload(); pg.wait_for_timeout(1500); assert pg.is_hidden("#setup")
    pg.evaluate("window.JarvisUI.openPane('system')"); pg.click("#setup-again"); pg.wait_for_selector("#setup:not(.hidden)")
    pg.wait_for_function("document.getElementById('setup-name').value === 'Ada'")
    assert pg.is_hidden("#settings") and pg.is_checked("input[name=setup-address][value=name]") and pg.input_value("#setup-name") == "Ada"
    pg.keyboard.press("Escape"); pg.wait_for_selector("#setup", state="hidden")
    # phone width: fits, nothing to scroll sideways
    ph = br.new_context(viewport={"width": 390, "height": 844}).new_page(); ph.on("pageerror", lambda e: errs.append(str(e)))
    ph.goto(f"http://127.0.0.1:{PORT}/"); ph.wait_for_timeout(800); ph.evaluate("window.JarvisSetup.open(false)")
    for step in range(7):
        assert ph.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), step
        assert ph.evaluate("(() => { const r = document.getElementById('setup-next').getBoundingClientRect(); return r.bottom <= innerHeight && r.right <= innerWidth; })()"), step
        if step == 5: ph.screenshot(path=str(tmp / "setup-phone.png"))
        if step < 6: ph.click("#setup-skip") if step else ph.click("#setup-next")
    br.close()
assert not errs, errs
print("setup ok", tmp)
os._exit(0)

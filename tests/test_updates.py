"""The updater: Jarvis notices a new release, shows a banner with what's new, and “Update and restart” downloads the changed
files, installs new packages, restarts and says what changed. Also the Updates section and the setup button in Settings."""
import json, os, sys, tempfile, threading, time, http.client, importlib.util, shutil, subprocess
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote
tmp = Path(tempfile.mkdtemp())
from testlib import stage
sys.path.insert(0, ".")

def put(base, rel, data):
    p = base / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data if isinstance(data, bytes) else data.encode())

snap = {}
def snapshot(ref, files):
    d = tmp / ("repo-" + ref.replace("/", "_")); (d / "tools").mkdir(parents=True, exist_ok=True)
    shutil.copy("filecheck.py", d / "filecheck.py"); shutil.copy("tools/make_manifest.py", d / "tools" / "make_manifest.py")
    for rel, txt in files.items(): put(d, rel, txt)
    assert subprocess.run([sys.executable, "tools/make_manifest.py"], cwd=d, capture_output=True).returncode == 0
    snap[ref] = d
snapshot("v2026.11.20", {"app/extra.py": "one\n", "requirements.txt": "psutil\n"})
REL = {"tag": "v2026.11.20", "body": "First one"}
COMMITS = {"main": "b" * 40}
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, data, code=200):
        self.send_response(code); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        path = unquote(self.path)
        if path.startswith("/api/repos/"):
            if path.endswith("/releases/latest"):
                return self.send(json.dumps({"tag_name": REL["tag"], "name": "Jarvis " + REL["tag"][1:], "body": REL["body"]}).encode())
            if "/compare/" in path:
                return self.send(json.dumps({"commits": [{"commit": {"message": "Faster answers\n\nmore"}}, {"commit": {"message": "Update manifest [skip ci]"}}, {"commit": {"message": "A new game"}}]}).encode())
            if "/commits/" in path:
                ref = path.rsplit("/", 1)[1]
                return self.send(COMMITS.get(ref, "").encode(), 200 if ref in COMMITS else 404)
            return self.send(b"[]")
        parts = path.lstrip("/").split("/", 3)
        d = snap.get(parts[2]); f = d / parts[3] if d else None
        if not f or not f.is_file(): return self.send(b"", 404)
        self.send(f.read_bytes())
gh = ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=gh.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{gh.server_address[1]}"

os.environ["JARVIS_NO_SETUP"] = "1"
spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)
S.filecheck.RAW_BASE, S.filecheck.API_BASE = BASE, BASE + "/api"
root = tmp / "jarvis"; stage(root)
for rel in ("app/extra.py", "requirements.txt", "filecheck.py", "tools/make_manifest.py"): put(root, rel, (snap["v2026.11.20"] / rel).read_bytes())
put(root, "data/filecheck.json", json.dumps({"channel": "releases"})); put(root, "data/version.json", json.dumps({"version": "2026.11.20", "tag": "v2026.11.20"}))
S.ROOT = root
pips, restarts = [], []
def fake_pip():
    pips.append(1); S.PACKAGES.update(state="installing")
    threading.Timer(0.8, lambda: S.PACKAGES.update(state="done")).start()
S.packages_install_in_background = fake_pip
def fake_restart():
    restarts.append(1)
    def back():
        time.sleep(1.0); S.STARTED_AT = time.time(); S.UPDATE_STATE.update(install="", files=[], todo=0)
    threading.Thread(target=back, daemon=True).start()
S.restart_jarvis = fake_restart
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start(); PORT = app.server_address[1]
def call(path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=30)
    c.request("POST" if body is not None else "GET", path, json.dumps(body) if body is not None else None, {"Content-Type": "application/json"})
    r = c.getresponse(); return r.status, json.loads(r.read() or b"{}")

# ---------- nothing new, then a new release ----------
st, d = call("/api/updates?check=1"); assert st == 200 and not d["available"] and d["version"] == "2026.11.20" and d["channel"] == "releases" and d["checked"], d
assert call("/api/updates", {"install": True})[0] == 400, "nothing to install"
snapshot("v2026.11.27", {"app/extra.py": "two\n", "app/new.py": "new\n", "requirements.txt": "psutil\npypdf\n"})
REL.update(tag="v2026.11.27", body="## What's Changed\n* Faster answers by @someone in https://github.com/x/y/pull/1\n* A new game\n\n**Full Changelog**: https://github.com/x/y/compare/a...b")
S.filecheck.LATEST.clear()
st, d = call("/api/updates?check=1")
assert d["available"] and d["new_version"] == "2026.11.27" and d["count"] == 3 and d["signature"], d
assert d["notes"]["lines"] == ["Faster answers", "A new game"], d["notes"]

# ---------- the page: banner, what's new, later ----------
from playwright.sync_api import sync_playwright
errs = []
with sync_playwright() as pw:
    br = pw.chromium.launch()
    pg = br.new_context(viewport={"width": 1280, "height": 860}).new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{PORT}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload()
    pg.wait_for_selector("#update-banner:not(.hidden)")
    assert pg.text_content("#ub-title") == "A new version of Jarvis is ready." and pg.text_content("#ub-sub") == "Version 2026.11.27"
    assert pg.is_hidden("#ub-list"); pg.click("#ub-notes"); assert pg.is_visible("#ub-list") and pg.text_content("#ub-list li") == "Faster answers"
    pg.screenshot(path=str(tmp / "banner.png"))
    pg.click("#ub-later"); assert pg.is_hidden("#update-banner")
    pg.reload(); pg.wait_for_timeout(1500); assert pg.is_hidden("#update-banner"), "later: not again for this version"
    # Settings > Jarvis & updates: version, what's new, update button; the setup button right under it
    pg.evaluate("window.JarvisUI.openPane('system')"); pg.wait_for_selector("#upd-install:not(.hidden)")
    assert pg.text_content("#upd-version") == "2026.11.20" and "A new version of Jarvis is ready." in pg.text_content("#upd-status") and "Version 2026.11.27" in pg.text_content("#upd-status")
    assert pg.is_visible("#upd-notes-box") and pg.is_visible("#setup-again") and pg.text_content("#setup-again") == "▶ Run the first-start setup again"
    order = pg.evaluate("[...document.querySelectorAll('#pane-system .settings-section')].slice(0,3).map(s => s.id || s.querySelector('h2').textContent)")
    assert order[:2] == ["updates-section", "setup-section"], order
    pg.screenshot(path=str(tmp / "section.png"))
    # update and restart, from Settings
    pg.click("#upd-install")
    pg.wait_for_selector("#update-banner.done", timeout=20000)            # the page reloaded on the new Jarvis
    assert pg.text_content("#ub-title") == "Jarvis was updated." and pg.text_content("#ub-sub") == "Version 2026.11.27"
    assert pips == [1] and restarts == [1]
    assert (root / "app/extra.py").read_text() == "two\n" and (root / "app/new.py").read_text() == "new\n" and (root / "requirements.txt").read_text() == "psutil\npypdf\n"
    assert json.loads((root / "data/version.json").read_text())["version"] == "2026.11.27"
    pg.wait_for_timeout(500); assert not (root / "data/update-done.json").exists(), "said once"
    pg.click("#ub-later"); assert pg.is_hidden("#update-banner")
    pg.reload(); pg.wait_for_timeout(1500); assert pg.is_hidden("#update-banner")
    # the setup button opens the first-start guide
    pg.evaluate("window.JarvisUI.openPane('system')"); pg.click("#setup-again"); pg.wait_for_selector("#setup:not(.hidden)")
    pg.keyboard.press("Escape")
    # phone width: the banner fits
    ph = br.new_context(viewport={"width": 390, "height": 844}).new_page(); ph.on("pageerror", lambda e: errs.append(str(e)))
    REL.update(tag="v2026.12.01", body="* Something else"); snapshot("v2026.12.01", {"app/extra.py": "three\n", "app/new.py": "new\n", "requirements.txt": "psutil\npypdf\n"})
    S.filecheck.LATEST.clear(); call("/api/updates?check=1")
    ph.goto(f"http://127.0.0.1:{PORT}/"); ph.wait_for_selector("#update-banner:not(.hidden)")
    assert ph.evaluate("(() => { const r = document.getElementById('update-banner').getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth && r.bottom <= innerHeight; })()")
    assert ph.evaluate("document.documentElement.scrollWidth <= innerWidth")
    ph.screenshot(path=str(tmp / "banner-phone.png"))
    br.close()
assert not errs, errs

# ---------- a copy that follows main: what's new is the list of changes since its last update ----------
S.filecheck.SHAS.clear(); put(root, "data/filecheck.json", json.dumps({"channel": "main"})); put(root, "data/version.json", json.dumps({"commit": "a" * 40}))
snapshot("main", {"app/extra.py": "main\n", "app/new.py": "new\n", "requirements.txt": "psutil\npypdf\n"})
st, d = call("/api/updates?check=1"); assert d["available"] and d["new_version"] == "" and d["notes"]["lines"] == ["A new game", "Faster answers"], d
print("updates ok", tmp)
os._exit(0)

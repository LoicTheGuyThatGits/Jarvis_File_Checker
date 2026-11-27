"""Crash safety on the page: the safe-mode banner (why, what went wrong, Start normally), the Settings button, the crash log,
and a damaged settings file that is put aside instead of stopping Jarvis."""
import json, os, sys, tempfile, threading, time, http.client, importlib.util
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp = Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
D = tmp / "data"; D.mkdir(exist_ok=True)
(D / "settings.json").write_text('{"language": "en", oops', encoding="utf-8")          # damaged
sys.path.insert(0, "app")
spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT = tmp
S.SETTINGS_LOADED_FROM = None; S.load_settings()
kept = list(D.glob("settings.damaged-*.json"))
assert len(kept) == 1 and kept[0].read_text() == '{"language": "en", oops' and not (D / "settings.json").exists() and S.SETTINGS == {}
assert S.STARTUP_NOTICES and "damaged" in S.STARTUP_NOTICES[0]
# the crash log keeps what went wrong
S.install_crash_hooks()
def boom(): raise RuntimeError("the wake word thread fell over")
th = threading.Thread(target=boom, name="wake"); th.start(); th.join()
log = (D / "crash.log").read_text(); assert "the wake word thread fell over" in log and "In thread wake" in log
S.SAFE.update({"on": True, "reason": "crashes", "at": time.time()})
restarts = []
def fake_restart():
    restarts.append(1)
    def back():
        time.sleep(0.8); S.SAFE.clear(); S.STARTED_AT = time.time()
    threading.Thread(target=back, daemon=True).start()
S.restart_jarvis = fake_restart
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start(); PORT = app.server_address[1]
def call(path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=30)
    c.request("POST" if body is not None else "GET", path, json.dumps(body) if body is not None else None, {"Content-Type": "application/json"})
    r = c.getresponse(); return r.status, json.loads(r.read() or b"{}")
st, d = call("/api/safe"); assert d["safe"] and d["reason"] == "crashes" and "fell over" in d["crash"] and d["notices"], d

from playwright.sync_api import sync_playwright
errs = []
with sync_playwright() as pw:
    br = pw.chromium.launch()
    pg = br.new_context(viewport={"width": 1280, "height": 860}).new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{PORT}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload()
    pg.wait_for_selector("#safe-banner:not(.hidden)")
    assert pg.text_content("#sb-title") == "Safe mode" and pg.text_content("#sb-text").startswith("Jarvis kept stopping, so it started in safe mode.")
    assert "damaged" in pg.text_content("#sb-text")
    assert pg.is_hidden("#sb-more"); pg.click("#sb-details"); assert "fell over" in pg.text_content("#sb-crash")
    pg.screenshot(path=str(tmp / "safe.png"))
    pg.evaluate("window.JarvisUI.openPane('system')"); assert pg.text_content("#safe-restart") == "Start normally"
    pg.evaluate("document.getElementById('settings-close').click()")
    pg.click("#sb-normal")
    pg.wait_for_function("document.getElementById('sb-title').textContent === 'Restarting Jarvis…'")
    pg.wait_for_load_state("load"); pg.wait_for_timeout(2500)
    assert restarts == [1] and not (D / "safe-mode.json").exists()
    # not in safe mode now: the one-time notice is still said, once
    assert pg.is_visible("#safe-banner") and pg.text_content("#sb-title") == "Note" and pg.is_visible("#sb-ok") and pg.is_hidden("#sb-normal")
    pg.click("#sb-ok"); pg.wait_for_timeout(300); assert pg.is_hidden("#safe-banner")
    pg.reload(); pg.wait_for_timeout(1500); assert pg.is_hidden("#safe-banner"), "said once"
    # Settings: restart in safe mode
    pg.evaluate("window.JarvisUI.openPane('system')"); assert pg.text_content("#safe-restart") == "Restart in safe mode"
    pg.click("#safe-restart"); pg.wait_for_timeout(1500)
    assert json.loads((D / "safe-mode.json").read_text())["reason"] == "asked" and restarts == [1, 1]
    br.close()
assert not errs, errs
print("safe ok", tmp)
os._exit(0)

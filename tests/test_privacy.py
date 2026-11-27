"""Settings > Your data: what Jarvis keeps (with sizes), what leaves the PC, deleting one group, and deleting everything."""
import json, os, sys, tempfile, threading, time, http.client, importlib.util
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp = Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
D = tmp / "data"; D.mkdir(exist_ok=True)
def put(rel, text):
    p = tmp / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text, encoding="utf-8")
put("data/notes.json", json.dumps([{"text": "locker code"}])); put("data/documents/index.json", "{}")
put("data/memory.json", json.dumps({"items": [{"text": "likes chess"}]}))
put("data/history/2026-11.jsonl", '{"role":"user","content":"hi"}\n' * 20)
put("data/planner.json", "{}"); put("data/grades.json", "{}"); put("data/telegram.json", json.dumps({"token": "123:abc"}))
put("data/settings.json", json.dumps({"location": {"name": "Lyon", "region": "", "country": "France", "lat": 45.7, "lon": 4.8}, "setup_done": "x"}))
put("data/file-backups/20261120/app/server.py", "old"); put("workspace/snake/index.html", "<p>snake</p>")

sys.path.insert(0, "app")
spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT = tmp
restarts = []
def fake_restart():
    restarts.append(1)
    def back():
        time.sleep(0.8); S.STARTED_AT = time.time(); S.SETTINGS_LOADED_FROM = None
    threading.Thread(target=back, daemon=True).start()
S.restart_jarvis = fake_restart
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start(); PORT = app.server_address[1]
def call(path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=30)
    c.request("POST" if body is not None else "GET", path, json.dumps(body) if body is not None else None, {"Content-Type": "application/json"})
    r = c.getresponse(); return r.status, json.loads(r.read() or b"{}")

st, d = call("/api/privacy"); assert st == 200, d
g = {x["key"]: x for x in d["groups"]}
assert g["notes"]["files"] == 2 and g["chats"]["files"] == 1 and g["chats"]["bytes"] > 500 and g["projects"]["files"] == 1 and g["logs"]["files"] == 1, g
assert g["school"]["files"] == 1 and g["training"]["files"] == 0
o = {x["key"]: x for x in d["outside"]}
assert o["weather"]["on"] and o["telegram"]["on"] and not o["mail"]["on"] and not o["spotify"]["on"] and not o["phone"]["on"], o
assert o["search"]["on"] and o["search"]["when"] == "Only when you ask"
assert call("/api/privacy/delete", {"keys": ["nope"]})[0] == 400 and call("/api/privacy/delete", {"keys": []})[0] == 400

from playwright.sync_api import sync_playwright
errs = []
with sync_playwright() as pw:
    br = pw.chromium.launch()
    pg = br.new_context(viewport={"width": 1280, "height": 860}).new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{PORT}/")
    pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off');"
                "localStorage.setItem('jarvis-chats-v1', JSON.stringify([{id:'a',title:'one',messages:[]},{id:'b',title:'two',messages:[]}]))")
    pg.reload(); pg.wait_for_timeout(800)
    pg.evaluate("window.JarvisUI.openPane('privacy')"); pg.wait_for_selector("#privacy-groups .privacy-group")
    assert pg.locator("#privacy-outside li").count() == 11 and pg.locator("#privacy-outside li.on").count() == 4   # weather, search, telegram, updates
    rows = pg.locator("#privacy-groups .privacy-group"); assert rows.count() == 13
    notes = pg.locator(".privacy-group:has(button[data-key=notes])")
    assert "2 files" in notes.inner_text(), notes.inner_text()
    assert pg.is_disabled("button[data-key=training]"), "nothing kept: nothing to delete"
    assert "2 chats" in pg.locator(".privacy-group:has(button[data-key=browser])").inner_text()
    pg.screenshot(path=str(tmp / "privacy.png"), full_page=True)
    # one group: needs a second click
    pg.click("button[data-key=notes]"); assert pg.text_content("button[data-key=notes]") == "Click again to delete"
    assert (D / "notes.json").exists(), "not yet"
    pg.click("button[data-key=notes]")
    pg.wait_for_function("document.getElementById('privacy-status').textContent.indexOf('Restarting') >= 0")
    pg.wait_for_load_state("load"); pg.wait_for_timeout(2500)
    assert not (D / "notes.json").exists() and not (D / "documents").exists() and (D / "memory.json").exists() and (tmp / "workspace/snake/index.html").exists()
    assert restarts == [1]
    # the chats in this browser
    pg.evaluate("window.JarvisUI.openPane('privacy')"); pg.wait_for_selector("button[data-key=browser]")
    pg.click("button[data-key=browser]"); pg.click("button[data-key=browser]"); pg.wait_for_load_state("load"); pg.wait_for_timeout(1000)
    assert pg.evaluate("localStorage.getItem('jarvis-chats-v1')") in (None, "[]"), "browser chats gone"
    # everything: then Jarvis starts like new, with the setup guide
    os.environ.pop("JARVIS_NO_SETUP", None)
    pg.evaluate("window.JarvisUI.openPane('privacy')"); pg.wait_for_selector("#privacy-all")
    pg.click("#privacy-all"); assert pg.text_content("#privacy-all") == "Click again to delete"
    pg.click("#privacy-all")
    pg.wait_for_selector("#setup:not(.hidden)", timeout=20000)
    left = sorted(p.relative_to(tmp).as_posix() for p in tmp.rglob("*") if p.is_file() and p.parts[len(tmp.parts)] in ("data", "workspace"))
    assert all(x.startswith("data/") and x.split("/")[1] in ("settings.json", "address.txt") or x == "data/settings.json" for x in left) or not left, left
    assert not (tmp / "workspace").exists() and not (D / "memory.json").exists() and not (D / "telegram.json").exists() and not (D / "history").exists()
    assert pg.evaluate("localStorage.getItem('jarvis-brief-mode')") is None, "the page's own choices were cleared too"
    br.close()
assert not errs, errs
print("privacy ok", tmp)
os._exit(0)

"""Clipboard history: what is kept (and the secrets that never are), the chat commands, the card with Copy buttons, Settings,
and that it stays at the PC and out of the saved chats."""
import json, os, sys, tempfile, threading, time, http.client, importlib.util
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp = Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0, "app")
import cliphistory as ch

# ---------- what is kept ----------
for secret in ("Tr0ub4dor&3x", "hunter2!Secret", "481357", "123 456", "4111 1111 1111 1111", "CH93 0076 2011 6238 5295 7",
               "sk-proj-abcdefghijklmnopqrstuvwx", "ghp_abcdefghijklmnopqrstuvwxyz0123456789", "123456789:AAH7abcdefghijklmnopqrstuvwxyz01234",
               "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcDEF123", "password: lemon tree 42", "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08", "  "):
    assert ch.looks_secret(secret), secret
for fine in ("Meet at the station at 5", "https://example.com/Some-Page?id=42", "loic@example.com", r"C:\Users\Admin\Desktop\report.docx",
             "Photosynthesis turns light into chemical energy.", "Hello!", "def add(a, b):\n    return a + b", "Zürich HB", "Mitochondria", "12.5 kg"):
    assert not ch.looks_secret(fine), fine
assert ch.command("what did I copy?") == {"do": "list"} and ch.command("show my clipboard") == {"do": "list"} and ch.command("clipboard history") == {"do": "list"}
assert ch.command("put back what I copied before") == {"do": "back", "index": 2, "paste": False}
assert ch.command("paste what I copied before") == {"do": "back", "index": 2, "paste": True}
assert ch.command("Jarvis, can you copy back number 3 please") == {"do": "back", "index": 3, "paste": False}
assert ch.command("put back the third one") == {"do": "back", "index": 3, "paste": False}
assert ch.command("paste the previous one") == {"do": "back", "index": 2, "paste": True}
assert ch.command("clear my clipboard history") == {"do": "clear"} and ch.command("forget what I copied") == {"do": "clear"}
assert ch.command("stop remembering what I copy") == {"do": "off"} and ch.command("turn on clipboard history") == {"do": "on"}
for other in ("copy this file to my desktop", "paste the text into Word", "what is a clipboard?", "remember that my bike is blue", "put back the milk"):
    assert ch.command(other) is None, other

# the watcher: only new copies, secrets and private (password manager) copies skipped, newest first, no doubles, at most 25
board = {"seq": 1, "text": "already there", "private": False}; written = []
C = ch.ClipHistory(lambda: board["text"], lambda: board["seq"], lambda: board["private"], tmp / "data" / "clipboard.json", lambda t: written.append(t) or True)
C.poll(); assert [e["text"] for e in C.items()] == ["already there"]
def copy(text, private=False):
    board.update(seq=board["seq"] + 1, text=text, private=private); C.poll()
copy("first note"); copy("Tr0ub4dor&3x"); copy("bank login", private=True); copy("second note"); copy("first note"); C.poll()
assert [e["text"] for e in C.items()] == ["first note", "second note", "already there"], C.items()
for k in range(30): copy(f"line {k} of my essay")
assert len(C.items()) == ch.LIMIT and C.items()[0]["text"] == "line 29 of my essay"
copy("x" * 5000); assert C.items()[0]["cut"] and len(C.items()[0]["text"]) == ch.KEEP_CHARS
C.set_enabled(False); assert C.items() == [] and not C.enabled; copy("not kept when off"); assert C.items() == []
C.set_enabled(True); copy("kept again"); assert C.items()[0]["text"] == "kept again"
assert not any(tmp.joinpath("data").glob("*clip*hist*")) and json.loads((tmp / "data" / "clipboard.json").read_text()) == {"enabled": True}, "only on/off is saved"

# ---------- in the server ----------
spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT = tmp
(tmp / "data" / "clipboard.json").unlink()
S.CLIP = ch.ClipHistory(lambda: None, lambda: 0, config_path=tmp / "data" / "clipboard.json", write_text=lambda t: written.append(t) or True)
for t in ("the first thing", "an address: 12 Rue du Lac, Genève", "the newest thing"):
    S.CLIP.add(t)
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start(); PORT = app.server_address[1]
def call(path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=30)
    c.request("POST" if body is not None else "GET", path, json.dumps(body) if body is not None else None, {"Content-Type": "application/json"})
    r = c.getresponse(); return r.status, json.loads(r.read() or b"{}")
def say(text, **extra):
    return call("/api/chat", {"messages": [{"role": "user", "content": text}], **extra})[1]
d = say("what did I copy?")
assert [e["text"] for e in d["clipboard"]] == ["the newest thing", "an address: 12 Rue du Lac, Genève", "the first thing"] and "Genève" not in d["reply"], d
d = say("put back what I copied before"); assert written[-1] == "an address: 12 Rue du Lac, Genève" and "Ctrl+V" in d["reply"] and "Genève" not in d["reply"]
d = say("put back number 9"); assert "only have 3" in d["reply"]
d = say("what did I copy?", source="telegram"); assert "stays at the PC" in d["reply"] and "clipboard" not in d
st, d = call("/api/clipboard"); assert st == 200 and d["enabled"] and len(d["items"]) == 3
st, d = call("/api/clipboard", {"copy": d["items"][2]["id"]}); assert st == 200 and written[-1] == "the first thing"
st, d = call("/api/clipboard", {"copy": 999}); assert st == 404

from playwright.sync_api import sync_playwright
errs = []
with sync_playwright() as pw:
    br = pw.chromium.launch()
    pg = br.new_context(viewport={"width": 1280, "height": 900}).new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{PORT}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off');localStorage.removeItem('jarvis-chats-v1')"); pg.reload()
    pg.fill("#message", "what did I copy?"); pg.keyboard.press("Enter"); pg.wait_for_selector(".clip-card")
    assert pg.locator(".clip-card .clip-text").all_inner_texts() == ["the newest thing", "an address: 12 Rue du Lac, Genève", "the first thing"]
    pg.screenshot(path=str(tmp / "clip.png"))
    pg.locator(".clip-card button").nth(1).click(); pg.wait_for_function("document.querySelectorAll('.clip-card button')[1].textContent==='Copied'")
    assert written[-1] == "an address: 12 Rue du Lac, Genève"
    saved = pg.evaluate("localStorage.getItem('jarvis-chats-v1')"); assert "Genève" not in saved and "newest thing" not in saved, "copied texts stay out of saved chats"
    # Settings
    pg.evaluate("window.JarvisUI.openPane('keys')"); pg.wait_for_function("document.querySelectorAll('#clip-list li').length===3")
    assert pg.is_checked("#clip-enabled")
    pg.locator("#clip-list li").first.locator("button", has_text="×").click(); pg.wait_for_function("document.querySelectorAll('#clip-list li').length===2")
    pg.click("#clip-clear"); pg.wait_for_function("document.querySelector('#clip-list').textContent.includes('Nothing copied')")
    pg.uncheck("#clip-enabled"); pg.wait_for_timeout(400); assert json.loads((tmp / "data" / "clipboard.json").read_text()) == {"enabled": False}
    pg.wait_for_function("document.querySelector('#clip-list').textContent.includes('off')")
    br.close()
d = say("what did I copy?"); assert "off" in d["reply"]
assert not errs, errs
print("clipboard ok", tmp)
os._exit(0)

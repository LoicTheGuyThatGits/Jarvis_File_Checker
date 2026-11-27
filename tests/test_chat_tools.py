"""Chat comfort: edit your last message, try an answer again (also after an error), and pin, rename, delete or clear
chats with an Undo."""
import json, os, sys, tempfile, threading, time, importlib.util
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
tmp = Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
asked, state = [], {"n": 0, "fail": False}
class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps({"object": "list", "data": [{"id": "llama3.2:3b"}]}).encode())
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        asked.append(next(m["content"] for m in reversed(body["messages"]) if m["role"] == "user").split("[End of context]")[-1].strip())
        if state["fail"]:
            self.send_response(500); self.end_headers(); self.wfile.write(b'{"error":"busy"}'); return
        state["n"] += 1; text = f"Answer {state['n']}, sir."
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        self.wfile.write(("data: " + json.dumps({"choices": [{"delta": {"content": text}}]}) + "\n\n").encode())
        self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()
fake = ThreadingHTTPServer(("127.0.0.1", 0), Fake); threading.Thread(target=fake.serve_forever, daemon=True).start()
for k in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL", "JARVIS_CLOUD_API_KEY", "JARVIS_PROVIDER"): os.environ.pop(k, None)
os.environ["JARVIS_LOCAL_BASE_URL"] = f"http://127.0.0.1:{fake.server_address[1]}/v1"
sys.path.insert(0, "app")
spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT = tmp
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start(); PORT = app.server_address[1]

from playwright.sync_api import sync_playwright
errs = []
HIST = "JSON.parse(localStorage.getItem('jarvis-chats-v1')).find(c=>c.id===localStorage.getItem('jarvis-current-chat-v1')).messages"
def last_answer(pg): return pg.locator("#conversation .message-row.assistant .bubble").last.inner_text()
def idle(pg): pg.wait_for_function("document.querySelector('.send-button').textContent!=='Stop'"); pg.wait_for_timeout(150)
with sync_playwright() as pw:
    br = pw.chromium.launch()
    pg = br.new_context(viewport={"width": 1280, "height": 900}).new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{PORT}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off');localStorage.removeItem('jarvis-chats-v1')"); pg.reload()
    pg.fill("#message", "hello"); pg.keyboard.press("Enter"); idle(pg)
    assert last_answer(pg) == "Answer 1, sir."
    h = pg.evaluate(HIST); assert h[-1].get("retry") == 1 and len(h) == 2, h
    assert pg.locator(".message-row.user .msg-tool").inner_text() == "✎ Edit"
    pg.click(".message-row.assistant .msg-tool:has-text('Try again')"); idle(pg)
    assert last_answer(pg) == "Answer 2, sir." and pg.locator(".message-row").count() == 2 and asked[-1] == "hello"
    h = pg.evaluate(HIST); assert [m["content"] for m in h] == ["hello", "Answer 2, sir."], h
    # ↑ in the empty box edits the last message; Esc gives up
    pg.focus("#message"); pg.keyboard.press("ArrowUp"); assert pg.input_value("#message") == "hello" and pg.is_visible("#edit-bar")
    pg.keyboard.press("Escape"); assert pg.input_value("#message") == "" and pg.is_hidden("#edit-bar")
    pg.click(".message-row.user .msg-tool"); assert pg.input_value("#message") == "hello"
    pg.fill("#message", "hello there"); pg.keyboard.press("Enter"); idle(pg)
    h = pg.evaluate(HIST); assert [m["content"] for m in h] == ["hello there", "Answer 3, sir."] and asked[-1] == "hello there", h
    pg.screenshot(path=str(tmp / "tools.png"))
    # a built-in command's answer is not asked again (it would do it twice)
    pg.fill("#message", "what time is it?"); pg.keyboard.press("Enter"); idle(pg)
    assert pg.locator(".msg-tool:has-text('Try again')").count() == 0 and not pg.evaluate(HIST)[-1].get("retry")
    # after an error, Try again sends the same message again
    state["fail"] = True; pg.fill("#message", "tell me a joke"); pg.keyboard.press("Enter"); idle(pg)
    assert "couldn't complete" in last_answer(pg)
    state["fail"] = False; pg.click(".msg-tool:has-text('Try again')"); idle(pg)
    assert last_answer(pg) == "Answer 4, sir." and asked[-1] == "tell me a joke" and "couldn't complete" not in pg.inner_text("#conversation")
    assert [m["content"] for m in pg.evaluate(HIST)].count("tell me a joke") == 1

    # ---------- the chat list ----------
    chats = [{"id": "a1", "title": "Banana bread", "messages": [{"role": "user", "content": "bake"}, {"role": "assistant", "content": "Mash, sir."}]},
             {"id": "b2", "title": "Python help", "messages": [{"role": "user", "content": "lists"}, {"role": "assistant", "content": "They build lists."}]},
             {"id": "c3", "title": "Weather", "messages": [{"role": "user", "content": "sunny?"}, {"role": "assistant", "content": "No idea, sir."}]}]
    pg.evaluate("c=>{localStorage.setItem('jarvis-chats-v1',JSON.stringify(c));localStorage.setItem('jarvis-current-chat-v1','c3')}", chats); pg.reload(); pg.wait_for_timeout(300)
    titles = lambda: pg.locator("#chat-list .chat-item .chat-title").all_inner_texts()
    assert titles() == ["Weather", "Python help", "Banana bread"]
    row = pg.locator("#chat-list .chat-row").nth(2); row.hover(); row.locator(".chat-pin").click()
    assert titles() == ["Banana bread", "Weather", "Python help"] and pg.locator(".chat-row.pinned").count() == 1
    pg.reload(); pg.wait_for_timeout(300); assert titles()[0] == "Banana bread", "a pin is kept"
    row = pg.locator("#chat-list .chat-row").nth(2); row.hover(); row.locator(".chat-rename").click()
    pg.fill(".chat-rename-box", "  Python list tricks "); pg.keyboard.press("Enter"); assert titles()[2] == "Python list tricks"
    pg.locator("#chat-list .chat-item").nth(1).dblclick(); pg.fill(".chat-rename-box", "nope"); pg.keyboard.press("Escape"); assert titles()[1] == "Weather"
    # delete with undo (no "are you sure?" box)
    pg.on("dialog", lambda d: (errs.append("dialog: " + d.message), d.dismiss()))
    row = pg.locator("#chat-list .chat-row").nth(1); row.hover(); row.locator(".chat-del").click()
    assert titles() == ["Banana bread", "Python list tricks"] and pg.is_visible("#undo-toast") and pg.text_content("#undo-text") == "Chat deleted."
    assert "Answer" not in pg.inner_text("#conversation") and "No idea" not in pg.inner_text("#conversation")
    pg.click("#undo-button"); assert titles() == ["Banana bread", "Weather", "Python list tricks"] and pg.is_hidden("#undo-toast")
    assert "No idea, sir." in pg.inner_text("#conversation"), "the chat that was open comes back open"
    pg.click("#clear-chat"); assert pg.locator("#conversation .message-row").count() == 0 and pg.text_content("#undo-text") == "Chat cleared."
    pg.click("#undo-button"); assert "No idea, sir." in pg.inner_text("#conversation") and titles()[1] == "Weather"
    pg.click("#delete-chat"); assert "Weather" not in titles(); pg.wait_for_timeout(8300); assert pg.is_hidden("#undo-toast")
    assert len(pg.evaluate("JSON.parse(localStorage.getItem('jarvis-chats-v1'))")) == 2
    # French: the buttons speak French
    pg.evaluate("fetch('/api/language',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ui:'fr'})})"); pg.wait_for_timeout(300)
    pg.reload(); pg.wait_for_function("document.documentElement.lang === 'fr'"); pg.wait_for_timeout(300)
    tip = pg.locator("#chat-list .chat-del").first.get_attribute("title"); assert tip != "Delete this chat", tip
    br.close()
assert not errs, errs
print("chat tools ok", tmp)
os._exit(0)

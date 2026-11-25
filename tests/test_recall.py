import json, os, sys, re, tempfile, threading, time, http.client, importlib.util
from datetime import datetime, timedelta
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
tmp = Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0, "app")
import recall as R, french as fr

# ---------- the history and its search ----------
h = R.History(tmp / "h")
now = time.time()
h.add("My friend Luca recommended Outer Wilds, he says it's the best game he played this year", "Outer Wilds is a lovely space exploration game, sir.", "app", now - 20 * 86400)
h.add("what's the weather tomorrow", "Sunny and 12 degrees, sir.", "phone", now - 19 * 86400)
h.add("Remind me to buy a present for Mia", "Done, sir.", "telegram", now - 10 * 86400)
h.add("Mon ami Noah m'a conseillé le livre Dune", "Un grand classique, monsieur.", "app", now - 5 * 86400)
h.add("I have a game against Lancy on Saturday with my football team", "Good luck, sir.", "app", now - 2 * 86400)
h.add("very old message about Luca", "ok", "app", now - 500 * 86400)
hit = h.search("what was that game Luca recommended?")
assert hit and hit[0]["user"].startswith("My friend Luca recommended Outer Wilds"), hit
assert h.search("le livre que Noah m'a conseillé")[0]["user"].startswith("Mon ami Noah"), "French, accents folded"
assert h.search("Mia's present")[0]["source"] == "telegram"
assert h.search("the the and") == [] and h.search("quantum chromodynamics") == []
assert h.stats()["count"] == 6
assert h.prune(365) == 1 and h.stats()["count"] == 5, "months older than the limit go"
assert h.delete_matching("Mia") == 1 and h.stats()["count"] == 4
# learning
assert R.worth_learning("My friend Luca recommended Outer Wilds") and R.worth_learning("j'adore le jeu Celeste, c'est mon préféré")
for no in ("open notepad", "what's the weather tomorrow", "set a timer for 5 minutes", "hi"):
    assert not R.worth_learning(no), no
facts = R.parse_facts("- My friend Luca recommended the game Outer Wilds.\n- My PIN is 481357.\n- My email is someone@example.com\n- My phone code is 4471 2231 22\nI live at 12 Rue du Lac\nMy sister Mia plays the violin")
assert facts == ["My friend Luca recommended the game Outer Wilds.", "My sister Mia plays the violin."], facts
assert R.parse_facts("NONE") == [] and R.parse_facts("") == []
assert not R.safe_fact("My password is hunter2.") and not R.safe_fact("My bank card is blue.") and R.safe_fact("I support FC Basel.")
assert R.similar("My friend Luca recommended Outer Wilds.", "Luca, my friend, recommended Outer Wilds") > 0.7
assert R.is_recall("what was that game Luca recommended?") and R.is_recall("tu te souviens du livre ?") and not R.is_recall("open notepad")
items = [{"id": "1", "text": "My dog is called Rex."}, {"id": "2", "text": "My friend Luca recommended Outer Wilds."}, {"id": "3", "text": "I like my coffee black."}]
assert [i["id"] for i in R.rank(items, "should I play the game Luca told me about")] == ["2"]
# French
for f, e in (("qu'est-ce que tu as appris sur moi", "what have you learned about me"), ("cherche dans mes conversations Outer Wilds", "search my chats for Outer Wilds"),
             ("oublie ce que je t'ai dit sur Luca", "forget what I said about Luca"), ("arrête d'apprendre de mes conversations", "stop learning from my chats"),
             ("qu'est-ce que tu sais sur Luca", "what do you know about Luca")):
    assert fr.to_english(f) == e, (f, fr.to_english(f))

# ---------- through the server, with a pretend AI model ----------
seen = []
class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"]))); seen.append(body)
        system = "\n".join(m["content"] for m in body["messages"] if isinstance(m["content"], str))
        if not body.get("stream"):
            text = ("My friend Luca recommended the game Outer Wilds.\nMy PIN is 481357." if system.startswith("You keep a personal assistant's long-term memory") else "ok")
            raw = json.dumps({"choices": [{"message": {"content": text}}]}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw); return
        text = "It was Outer Wilds, sir: Luca recommended it." if "Excerpts from earlier conversations" in system else "Sounds good, sir."
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        self.wfile.write(("data: " + json.dumps({"choices": [{"delta": {"content": text}}]}) + "\n\n").encode()); self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()
fake = ThreadingHTTPServer(("127.0.0.1", 0), Fake); threading.Thread(target=fake.serve_forever, daemon=True).start()
os.environ["OPENAI_BASE_URL"] = f"http://127.0.0.1:{fake.server_address[1]}/v1"; os.environ["OPENAI_API_KEY"] = "ollama"
spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT = tmp
S.ensure_ollama = lambda base: None
S.LEARN_IDLE = 0
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start(); port = app.server_address[1]
def call(method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30); c.request(method, path, json.dumps(body) if body is not None else None, {"Content-Type": "application/json", **(headers or {})})
    r = c.getresponse(); return r.status, json.loads(r.read())
def chat(text, **kw):
    st, d = call("POST", "/api/chat", {"messages": [{"role": "user", "content": text}], "stream": False, **kw}); assert st == 200, d; return d["reply"]
def wait(cond, secs=15):
    end = time.time() + secs
    while time.time() < end:
        if cond(): return True
        time.sleep(0.2)
    return False
assert chat("My friend Luca recommended Outer Wilds, I think I'll try it this weekend") == "Sounds good, sir."
assert wait(lambda: any(i.get("source") == "learned" for i in S.load_memory())), "learned in the background"
learned = [i for i in S.load_memory() if i.get("source") == "learned"]
assert [i["text"] for i in learned] == ["My friend Luca recommended the game Outer Wilds."] and learned[0]["origin"].startswith("My friend Luca"), learned
assert "481357" not in (tmp / "data" / "memory.json").read_text(), "a PIN is never kept"
assert S.history_obj().stats()["count"] == 1
# the same news again: not stored twice
S.learn_now("Luca recommended Outer Wilds to me", "ok"); assert len([i for i in S.load_memory() if i.get("source") == "learned"]) == 1
# a commands' answer is kept in the history too; a routine's is not
chat("set a timer for 5 minutes"); assert S.history_obj().stats()["count"] == 2
chat("what time is it", source="routine"); assert S.history_obj().stats()["count"] == 2
# a new chat: what was that game?
r = chat("what was that game Luca recommended?")
system = "\n".join(m["content"] for m in seen[-1]["messages"] if isinstance(m["content"], str))
assert r == "It was Outer Wilds, sir: Luca recommended it." and "My friend Luca recommended Outer Wilds, I think I'll try it" in system, system
assert "picked up about the user in earlier chats" in system and "My friend Luca recommended the game Outer Wilds." in system
r = chat("search my chats for Outer Wilds"); assert r.startswith("In our chats about “Outer Wilds”, sir:") and "Today you said: “My friend Luca" in r, r
r = chat("what have you learned about me"); assert "My friend Luca recommended the game Outer Wilds." in r, r
r = chat("what do you know about Luca"); assert r.startswith("About “Luca”, sir:") and "From our chats:" in r, r
r = chat("when did I talk about the ski trip"); assert r == "I found nothing about “the ski trip” in our chats, sir.", r
# explicit memory works as before, and wins over a learned copy
assert "Noted" in chat("remember that my dog is called Rex")
assert S.memory_prompt_block(True, "walk the dog").startswith("Things the user has asked you to remember")
# forgetting
r = chat("forget what I said about Luca"); assert r.startswith("Forgotten, sir:") and "1 memory" in r, r
assert not S.history_obj().search("Luca Outer Wilds") and not [i for i in S.load_memory() if "Luca" in i["text"]]
# pausing learning, and the history switch
assert "stopped learning" in chat("stop learning from my chats")
n = len(S.LEARN_QUEUE); chat("My sister Mia plays the violin in an orchestra"); time.sleep(1)
assert not [i for i in S.load_memory() if "Mia" in i["text"]]
assert "again" in chat("start learning from my chats")
st, d = call("POST", "/api/memory/settings", {"history": False}); assert st == 200 and d["settings"]["history"] is False
before = S.history_obj().stats()["count"]; chat("my favourite band is Daft Punk"); assert S.history_obj().stats()["count"] == before
assert "switched off" in chat("search my chats for Daft Punk")
call("POST", "/api/memory/settings", {"history": True, "keep_days": 90})
st, d = call("POST", "/api/memory/settings", {"keep_days": 2}); assert st == 400
# the page's API
st, d = call("GET", "/api/memory"); assert d["settings"] == {"learn": True, "history": True, "keep_days": 90} and d["history"]["count"] >= 2 and "learned" in d, d
mid = [i for i in d["items"] if "Rex" in i["text"]][0]["id"]
st, d = call("POST", "/api/memory/edit", {"id": mid, "text": "My dog is called Rex and he is a beagle."}); assert any(i["text"].endswith("beagle.") for i in d["items"])
st, d = call("GET", "/api/memory/search?q=" + "timer"); assert st == 200 and d["history"] and d["history"][0]["user"] == "set a timer for 5 minutes", d
S.phone_link.save(S.data_path("phone.json"), {"enabled": True, "code": "ABCDEFGH23"}); S.phone_link.is_loopback = lambda a: False
st, d = call("POST", "/api/memory/history/clear", {}, {"X-Jarvis-Token": "ABCDEFGH23"}); assert st == 403, "only at the PC"
st, d = call("POST", "/api/memory/settings", {"learn": False}, {"X-Jarvis-Token": "ABCDEFGH23"}); assert st == 403
S.phone_link.is_loopback = lambda a: True

# ---------- the settings page ----------
S.memory_add("My friend Noah likes chess.", "learned", "Noah is really into chess these days")
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_context(viewport={"width": 1280, "height": 900}).new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(600)
    pg.evaluate("window.JarvisUI.openPane('memory')"); pg.wait_for_selector("#memory-list .mem-learned")
    li = pg.locator("#memory-list .mem-learned", has_text="Noah"); assert li.locator(".mem-tag").text_content() == "learned"
    assert li.locator(".tool-text").get_attribute("title") == "From: “Noah is really into chess these days”"
    assert pg.is_checked("#mem-learn") and pg.is_checked("#mem-history") and pg.input_value("#mem-keep") == "90"
    assert pg.text_content("#mem-stats").startswith("Messages in the history:")
    pg.once("dialog", lambda dlg: dlg.accept("My friend Noah loves chess and plays at a club."))
    li.locator(".mem-edit").click()
    pg.wait_for_function("document.querySelector('#memory-list').textContent.includes('plays at a club')")
    assert [i for i in S.load_memory() if "club" in i["text"]][0]["source"] == "you", "corrected: now yours"
    pg.fill("#mem-search", "timer"); pg.click("#mem-search-go"); pg.wait_for_selector("#mem-results .mem-hit")
    assert "set a timer" in pg.text_content("#mem-results")
    pg.uncheck("#mem-learn"); pg.wait_for_timeout(300); assert S.memory_settings()["learn"] is False
    pg.check("#mem-learn"); pg.select_option("#mem-keep", "365"); pg.wait_for_timeout(300); assert S.memory_settings()["keep_days"] == 365
    pg.click("#mem-history-clear"); assert pg.text_content("#mem-history-clear") == "Click again to delete every chat"
    pg.click("#mem-history-clear"); pg.wait_for_function("document.querySelector('#mem-stats').textContent === 'No chats in the history yet.'")
    assert S.history_obj().stats()["count"] == 0
    call("POST", "/api/language", {"ui": "fr"}); pg.reload(); pg.wait_for_function("document.documentElement.lang === 'fr'"); pg.evaluate("window.JarvisUI.openPane('memory')"); pg.wait_for_timeout(400)
    assert pg.text_content("#recall-title") == "Mémoire entre les conversations", pg.text_content("#recall-title")
    assert "plays at a club" in pg.text_content("#memory-list"), "your memories are never translated"
    call("POST", "/api/language", {"ui": "auto"})
    assert not errs, errs
    b.close()
print("recall ok"); os._exit(0)

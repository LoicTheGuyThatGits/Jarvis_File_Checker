import json, os, sys, tempfile, threading, http.client, importlib.util, random
from datetime import datetime, date, timedelta
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp = Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0, "app")
import study as SM, planner as P, french as fr

cards = iter([("What is the powerhouse of the cell?", "The mitochondria."), ("What carries oxygen in the blood?", "Red blood cells (haemoglobin)."),
              ("What is the capital of Peru?", "Lima."), ("What is H2O?", "Water."), ("What gas do plants take in?", "Carbon dioxide.")])
def ask(system, user):
    if "mark a student's answer" in system:
        return "WRONG - not quite."
    q, a = next(cards)
    return f"QUESTION: {q}\nANSWER: {a}"
st = SM.Study(tmp / "study.json", ask, lambda topic: ["Cells have mitochondria."], P.Planner(tmp / "planner.json"), random.Random(1))
today = date.today()

assert st.command("how many cards are due").startswith("Your flashcard deck is empty, sir.")
assert st.command("review my cards").startswith("Your flashcard deck is empty")
# ---------- a flashcard session fills the deck ----------
assert st.command("flashcards on cells with 3 cards").startswith("Flashcards on cells, 3 cards.")
assert st.command("got it") .startswith("Good.")
st.command("show answer"); assert st.command("again").startswith("I will keep it for review.")
r = st.command("got it"); assert "Cards finished, sir: 2 of 3 right." in r and "These cards are in your deck now" in r, r
deck = {c["q"]: c for c in st.load()["deck"]}
assert deck["What is the powerhouse of the cell?"]["box"] == 1 and deck["What is the powerhouse of the cell?"]["due"] == (today + timedelta(days=3)).isoformat()
assert deck["What carries oxygen in the blood?"]["box"] == 0 and deck["What carries oxygen in the blood?"]["due"] == (today + timedelta(days=1)).isoformat()
assert len(deck) == 3
# a missed quiz question goes into the deck too
st.command("quiz me on peru with 1 question"); r = st.command("Cusco")
assert "Not quite" in r and len(st.load()["deck"]) == 4 and st.load()["missed"], r
# ---------- adding your own ----------
assert st.command("add a flashcard: capital of Switzerland | Bern").startswith("Added to your deck, sir: “capital of Switzerland” → Bern. It comes up for review tomorrow.")
assert st.command("add a flashcard: What is 7 x 8? 56").startswith("Added to your deck, sir: “What is 7 x 8?” → 56.")
assert st.command("add a flashcard: hi").startswith("Give the question and the answer")
assert len(st.load()["deck"]) == 6
# ---------- reviews ----------
assert st.command("how many cards are due").startswith("Nothing to review today, sir: 6 cards in your deck, 0 well learned. The next ones are due on")
data = st.load()
for c in data["deck"]:
    c["due"] = today.isoformat() if c["q"] != "What is 7 x 8?" else c["due"]
st.save(data)
assert st.command("what's due").startswith("5 cards to review today, sir: 6 cards in your deck")
r = st.command("review my cards"); assert r.startswith("Review: 5 cards due.") and "Card 1/5:" in r, r
first = st.session["current"]["q"]
assert st.command("got it").startswith("Good. Back in")
c = next(c for c in st.load()["deck"] if c["q"] == first); assert c["box"] >= 1 and c["due"] > today.isoformat() and c["reviews"] == 1
second = st.session["current"]["q"]
r = st.command("again"); assert "It comes back tomorrow." in r
c = next(c for c in st.load()["deck"] if c["q"] == second); assert c["box"] == 0 and c["due"] == (today + timedelta(days=1)).isoformat() and c["lapses"] >= 1
third = st.session["current"]["q"]
assert st.command("delete this card").startswith("Removed from your deck.") and all(c["q"] != third for c in st.load()["deck"])
r = st.command("stop"); assert "2 still due today." in r, r
r = st.command("review my cards"); assert r.startswith("Review: 2 cards due."), r
st.command("got it"); r = st.command("got it"); assert "Nothing else is due today." in r, r
assert st.command("how many cards are due").startswith("Nothing to review today")
# intervals grow: 1 → 3 → 7 → 14 → 30 → 60
st.deck_add("Q grow?", "A", "t")
for want in (3, 7, 14, 30, 60, 60):
    c = st.deck_update("Q grow?", True); assert c["due"] == (today + timedelta(days=want)).isoformat(), (want, c)
assert st.deck_update("Q grow?", False)["box"] == 0
assert st.deck_stats()["learned"] >= 0 and st.deck_remove("Q grow?") and not st.deck_remove("nothing like this")
# the review session never adds to the "missed" list and old commands still work
assert st.command("my study stats").startswith("You have done")
# ---------- French ----------
for q, want in {"révise mes cartes": "review my cards", "combien de cartes à réviser aujourd'hui": "how many cards are due",
                "ajoute une carte : capitale du Pérou | Lima": "add a flashcard: capitale du Pérou | Lima"}.items():
    assert fr.to_english(q, datetime.now()) == want, (q, fr.to_english(q, datetime.now()))

# ---------- in the server ----------
spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT = tmp
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start(); port = app.server_address[1]
def call(method, path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30); c.request(method, path, json.dumps(body) if body is not None else None, {"Content-Type": "application/json"})
    r = c.getresponse(); return r.status, json.loads(r.read())
chat = lambda text: call("POST", "/api/chat", {"messages": [{"role": "user", "content": text}], "stream": False})[1]["reply"]
assert chat("add a flashcard: capital of Italy | Rome").startswith("Added to your deck")
st_, d = call("POST", "/api/study/deck", {"add": {"q": "capital of Spain", "a": "Madrid"}}); assert st_ == 200 and d["deck"]["total"] == 2 and len(d["cards"]) == 2
st_, d = call("POST", "/api/study/deck", {"add": {"q": "x", "a": ""}}); assert st_ == 400
s_ = S.study_obj(); data = s_.load()
for c in data["deck"]:
    c["due"] = date.today().isoformat()
s_.save(data)
assert "You have 2 flashcards to review today" in S.build_briefing(weather=False, system=False)["text"]
r = chat("review my cards"); assert r.startswith("Review: 2 cards due."), r
assert chat("got it").startswith("Good. Back in 3 days.")
st_, d = call("GET", "/api/study"); assert d["deck"]["due"] == 1 and d["active"]
chat("stop")
# ---------- the page ----------
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_context(viewport={"width": 1280, "height": 900}).new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(500)
    pg.evaluate("window.JarvisUI.openPane('notes')"); pg.wait_for_function("document.querySelector('#deck-stats').textContent.length > 0")
    assert pg.text_content("#deck-stats").startswith("1 card due today, 2 in the deck") and pg.text_content("#deck-summary") == "Cards (2)"
    pg.fill("#deck-q", "capital of France"); pg.fill("#deck-a", "Paris"); pg.click("#deck-add")
    pg.wait_for_function("document.querySelector('#deck-summary').textContent === 'Cards (3)'")
    pg.click("#deck-summary"); pg.locator("#deck-list li", has_text="capital of France").locator("button").click()
    pg.wait_for_function("document.querySelector('#deck-summary').textContent === 'Cards (2)'")
    pg.click("#deck-review"); pg.wait_for_function("document.body.innerText.includes('Review: 1 card due')", timeout=15000)
    assert not errs, errs
    b.close()
print("deck ok"); os._exit(0)

import json, os, sys, tempfile, threading, http.client, importlib.util
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp = Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0, "app")
import replies as R

CASES = {
    "It is 13:04, sir.": "Il est 13:04, monsieur.",
    "Today is Tuesday 24 November 2026, sir.": "Nous sommes le mardi 24 novembre 2026, monsieur.",
    "Timer set for 1 hour and 30 minutes, sir.": "Minuteur réglé sur 1 heure et 30 minutes, monsieur.",
    "Alarm set for tomorrow at 6:45 AM, sir.": "Réveil réglé demain à 06:45, monsieur.",
    "Very good, sir. I will remind you tomorrow at 6:00 PM: “call mum”.": "Très bien, monsieur. Je vous le rappellerai demain à 18:00 : “call mum”.",
    "Added “buy bread” to your to-do list, due Friday, sir.": "J'ai ajouté “buy bread” à votre liste de tâches, pour vendredi, monsieur.",
    "Noted, sir: Maths: exercises 4 to 7, due Monday (your next lesson).": "C'est noté, monsieur : Maths: exercises 4 to 7, pour lundi (votre prochain cours).",
    "I have no open Histoire homework, sir.": "Je n'ai pas de devoirs d'Histoire en cours, monsieur.",
    "Tomorrow:\n• 08:15: Maths\n• Due tomorrow: revise": "Demain :\n• 08:15: Maths\n• Pour demain : revise",
    "Added Maths to your timetable, sir: Mondays and Thursdays, 08:15–09:00 in B12.": "J'ai ajouté Maths à votre horaire, monsieur : le lundi et le jeudi, 08:15–09:00, salle B12.",
    "No revision session is running, sir. Say “start revision” to begin one.": "Aucune séance de révision en cours, monsieur. Dites « commence ma révision » pour en lancer une.",
    "Leave in 15 min, at 07:36, sir: the bus 47 from Laconnex, village at 07:41, on time, at Genève, Bel-Air at 08:05. First lesson: Maths at 08:15.":
        "Partez dans 15 min, à 07:36, monsieur : le bus 47 de Laconnex, village à 07:41, à l'heure, à Genève, Bel-Air à 08:05. Premier cours : Maths à 08:15.",
}
for en, fr in CASES.items():
    assert R.to_french(en) == fr, (en, R.to_french(en))
assert R.to_french("Here is something nobody wrote a pattern for, sir.") is None, "unknown: the AI model translates it"
assert R.to_french("Timer set for 10 minutes, sir. Something unknown.") is None, "all or nothing"
assert R.to_french("Noted: “remember the meeting tomorrow at 6:00 PM”, sir.") == "C'est noté : “remember the meeting tomorrow at 6:00 PM”, monsieur.", "what you wrote is never changed"

# ---------- in the server: French requests answered at once, without the AI model ----------
spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT = tmp
asked = []
S.ai_translate = lambda text, code: asked.append(text) or "TRADUIT PAR L'IA"
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start()
def chat(text):
    c = http.client.HTTPConnection("127.0.0.1", app.server_address[1], timeout=30)
    c.request("POST", "/api/chat", json.dumps({"messages": [{"role": "user", "content": text}], "stream": False}), {"Content-Type": "application/json"})
    return json.loads(c.getresponse().read())["reply"]
assert chat("mets un minuteur de 10 minutes") == "Minuteur réglé sur 10 minutes, monsieur." and not asked
assert chat("quelle heure est-il ?").startswith("Il est ") and not asked
assert chat("ajoute acheter du pain à ma liste") == "J'ai ajouté “acheter du pain” à votre liste de tâches, monsieur." and not asked
assert chat("set a timer for 5 minutes") == "Timer set for 5 minutes, sir.", "English stays English"
r = chat("comment va mon pc"); assert r == "TRADUIT PAR L'IA" and asked, (r, "an answer without a pattern still goes to the AI model")
# Jarvis set to speak French: its own messages are French too
seen = []
class Q:
    def put(self, e): seen.append(e)
S.SUBSCRIBERS.append(Q())
S.publish_event({"type": "proactive", "id": "x", "text": "Focus session done, sir: 25 min. That makes 25 min today. Take a 5 minute break.", "chat": True})
assert seen[-1]["text"].startswith("Focus session done"), "English while Jarvis speaks English"
S.set_language("fr")
S.publish_event({"type": "proactive", "id": "y", "text": "Focus session done, sir: 25 min. That makes 25 min today. Take a 5 minute break.", "chat": True})
assert seen[-1]["text"] == "Séance de concentration terminée, monsieur : 25 min. Cela fait 25 min aujourd'hui. Faites une pause de 5 minutes.", seen[-1]
print("replies ok"); os._exit(0)

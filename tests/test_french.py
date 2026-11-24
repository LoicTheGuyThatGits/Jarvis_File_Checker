import json, os, sys, tempfile, threading, http.client, importlib.util
from datetime import datetime
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0,"app")
import french as f
n=datetime(2026,11,16,13,0)
# ---- dates and durations ----
for q,want in [("demain à 18h","tomorrow at 18:00"),("demain matin","tomorrow morning"),("ce soir","tonight"),("lundi prochain à 9h30","next monday at 9:30am"),("le 3 décembre à 9h","3 december at 9:00am"),
               ("le 1er mars","1 march"),("le 20","20/11/2026"),("le 5","5/12/2026"),("pour vendredi","by friday"),("dans 20 minutes","in 20 minutes"),("dans une heure et demie","in 1 hours 30 minutes"),
               ("après-demain","the day after tomorrow"),("à midi","at 12:00"),("vendredi soir","friday at 19:00"),("le 12/12 à 20h","12/12 at 20:00"),("aujourd'hui","today"),("dans 3 jours","in 3 days")]:
    assert f.when(q,n)==want, (q,f.when(q,n))
for q in ("bientôt","un de ces jours","demain peut-être","",): assert f.when(q,n) is None, q
for q,want in [("10 minutes","10 minutes"),("1h30","1 hours 30 minutes"),("une demi-heure","30 minutes"),("un quart d'heure","15 minutes"),("deux heures","2 hours"),("45 secondes","45 seconds"),("une minute","1 minute")]:
    assert f.duration(q)==want, (q,f.duration(q))
assert f.duration("longtemps") is None
assert f.split_when("appeler maman demain à 18h",n)==("appeler maman","tomorrow at 18:00") and f.split_when("acheter du pain",n)==("acheter du pain","")
# ---- commands ----
CASES=[("ajoute acheter du pain à ma liste","add task: acheter du pain"),("Jarvis, peux-tu ajouter acheter du pain à ma liste s'il te plaît ?","add task: acheter du pain"),
 ("ajoute une tâche : rendre le projet d'art pour vendredi","add task: rendre le projet d'art by friday"),("mets réviser les maths sur ma to-do list demain","add task: réviser les maths tomorrow"),
 ("qu'est-ce que j'ai à faire ?","show my to-do list"),("montre-moi ma liste de tâches","show my to-do list"),("j'ai fini le devoir d'histoire","I did my histoire homework"),
 ("qu'est-ce que j'ai demain ?","show my calendar for tomorrow"),("suis-je libre samedi après-midi","show my calendar for saturday"),("montre mon agenda","show my calendar for today"),
 ("ajoute dentiste mardi à 16h à mon agenda","schedule dentiste tuesday at 16:00"),("j'ai un rendez-vous chez le dentiste le 20 à 15h30","schedule rendez-vous chez le dentiste 20/11/2026 at 15:30"),
 ("rappelle-moi d'appeler maman demain à 18h","remind me to appeler maman tomorrow at 18:00"),("rappelle-moi dans 20 minutes de sortir le gâteau","remind me to sortir le gâteau in 20 minutes"),
 ("fais-moi penser à prendre mon sac de sport lundi matin","remind me to prendre mon sac de sport monday at 9:00am"),("mets un minuteur de 10 minutes","set a timer for 10 minutes"),("minuteur 1h30","set a timer for 1 hours 30 minutes"),
 ("réveille-moi demain à 6h45","wake me up tomorrow at 6:45am"),("annule le minuteur","cancel all timers"),("note que le code du cadenas est 4471","take a note: le code du cadenas est 4471"),
 ("cherche dans mes notes le code wifi","search my notes for le code wifi"),("montre mes notes","show my notes"),("interroge-moi sur la révolution française","quiz me on la révolution française"),
 ("fais-moi des fiches sur le cycle de l'eau","flashcards on le cycle de l'eau"),("récap de ma journée","evening recap"),("fais-moi le point","briefing"),("quel temps fait-il ?","what's the weather"),
("j'ai un contrôle de physique le 20","my physique exam is on 20/11/2026"),("mon examen de maths est le 3 décembre à 9h","my maths exam is on 3 december at 9:00am"),
 ("quand sont mes examens","exam countdown"),("planifie mes révisions","plan my revision"),("je veux me concentrer pendant 25 minutes sur les maths","focus for 25 minutes on maths"),("pomodoro","start a focus session"),
 ("arrête la concentration","stop focus"),("mets Daft Punk sur spotify","play Daft Punk on spotify"),("vérifie les mises à jour","check for updates"),("oui, mets à jour","yes, update"),
 ("quels appareils sont connectés au wifi","what devices are on my wifi"),("pourquoi le wifi est si lent","why is my wifi slow"),("cherche partout le code wifi","search everything for le code wifi"),
 ("comment va mon pc","pc health report"),("annule ça","undo that")]
for q,want in CASES: assert f.to_english(q,n)==want, (q,f.to_english(q,n))
# things that are not commands stay with the chat model
for q in ["explique la photosynthèse","je cherche un cadeau pour ma mère","qu'est-ce que tu penses de ce film","raconte-moi une blague","add milk to my to-do list","j'ai faim","c'est quoi un trou noir",
          "j'ai fini par comprendre","rappelle-moi ce qu'est un verbe","note de musique la plus aiguë ?","mets-toi à ma place","planifie","what's the weather","", "x"*400]:
    assert f.to_english(q,n) is None, (q,f.to_english(q,n))
# ---- through the server: the English command runs, the answer comes back in French ----
spec=importlib.util.spec_from_file_location("srv","app/server.py"); S=importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT=tmp
S.PLANNER_CACHE["path"]=None
said=[]; S.ai_translate=lambda text,code:(said.append((text,code)) or "[fr] "+text)
app=ThreadingHTTPServer(("127.0.0.1",0),S.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def chat(text):
    c=http.client.HTTPConnection("127.0.0.1",port); c.request("POST","/api/chat",json.dumps({"messages":[{"role":"user","content":text}],"stream":False}),{"Content-Type":"application/json"}); return json.loads(c.getresponse().read())
d=chat("ajoute acheter du pain à ma liste"); assert d["reply"]=="J'ai ajouté “acheter du pain” à votre liste de tâches, monsieur.", d   # written in French directly (replies.py)
assert [t["text"] for t in S.planner_obj().public()["tasks"]]==["acheter du pain"]
d=chat("ajoute une tâche : rendre le projet d'art pour vendredi"); t=[t for t in S.planner_obj().public()["tasks"] if "projet" in t["text"]][0]; assert t["due"] and datetime.fromtimestamp(t["due"]).weekday()==4, t
d=chat("qu'est-ce que j'ai à faire ?"); assert "acheter du pain" in d["reply"] and "projet d'art" in d["reply"]
d=chat("j'ai fini le projet d'art"); assert [t for t in S.planner_obj().public()["tasks"] if "projet" in t["text"]][0]["done"] is True, d
d=chat("planifie une réunion avec Léa demain à 14h"); ev=S.planner_obj().public()["events"]; assert len(ev)==1 and "Léa" in ev[0]["title"] and datetime.fromtimestamp(ev[0]["start"]).hour==14, (d,ev)
d=chat("qu'est-ce que j'ai demain ?"); assert "Léa" in d["reply"], d
d=chat("rappelle-moi d'appeler maman dans 2 heures"); assert len(S.reminders_active())==1 and "appeler maman" in json.dumps(S.reminders_active()[0],ensure_ascii=False).lower(), (d,S.reminders_active())
d=chat("réveille-moi demain à 6h45"); assert d["reply"]=="Réveil réglé demain à 06:45, monsieur.", d
d=chat("mets un minuteur de 10 minutes"); assert len(S.reminders_active())==3, d
d=chat("note que le code du cadenas est 4471"); assert any("4471" in x["text"] for x in S.notes_obj().load()), d
d=chat("cherche dans mes notes le cadenas"); assert "4471" in d["reply"], d
d=chat("récap de ma journée"); assert d["reply"].startswith(("[fr] ","Voici votre journée")) and ("Tomorrow" in d["reply"] or "Demain" in d["reply"]), d
assert all(code=="fr" for _,code in said)
# English commands are not translated
n0=len(said); d=chat("add milk to my to-do list"); assert not d["reply"].startswith("[fr]") and len(said)==n0
# if translating fails the English answer is still given
S.ai_translate=lambda text,code:None; d=chat("montre mes notes"); assert "4471" in d["reply"], d
print("french ok"); os._exit(0)

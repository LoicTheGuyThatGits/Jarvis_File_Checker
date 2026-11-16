import json, os, sys, tempfile, threading, http.client, importlib.util
from datetime import datetime, timedelta
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0,"app")
import search_all as sa
for q,want in [("search everything for the wifi code","wifi code"),("where did I see the locker number","locker number"),("find the dentist anywhere","dentist"),("do I have anything about the science fair","science fair"),
               ("look everywhere for tulip","tulip"),("search all my stuff for Léa","Léa"),("find everything about physics","physics"),("Jarvis, where did I write down the bike lock code?","bike lock code")]:
    assert sa.query_of(q)==want, (q,sa.query_of(q))
for q in ("search for cats","where did I go wrong","search my notes for wifi","do I have anything to do today","find everything","where is Paris","search the internet for cats","everything is fine",""):
    assert sa.query_of(q) is None, q
now=datetime(2026,11,16,13,0)
planner={"tasks":[{"text":"Buy a bike lock","due":now.timestamp()+86400,"done":False},{"text":"Hand in physics homework","due":None,"done":True},{"text":"Call grandma","due":None,"done":False}],
         "events":[{"title":"Physics test","start":now.timestamp()+4*86400},{"title":"Dentist","start":now.timestamp()-86400}]}
notes=[{"text":"the bike lock code is 4471","created":1},{"text":"wifi at grandma's is tulip42","created":2}]
find=lambda q:[n for n in notes if sa.matches(q,n["text"])]
r=sa.search("bike lock",planner,find,lambda q:[{"text":"My bike is blue"}],lambda q:[{"name":"manual.pdf","text":"To open the bike lock turn the dial"}],now)
assert [n["text"] for n in r["notes"]]==["the bike lock code is 4471"] and [t["text"] for t in r["tasks"]]==["Buy a bike lock"] and r["events"]==[] and len(r["memory"])==1 and len(r["documents"])==1
txt=sa.report("bike lock",r,now); assert "in 4 places" in txt and "Notes:\n• the bike lock code is 4471" in txt and "• Buy a bike lock (due Tue 17 Nov)" in txt and "manual.pdf: To open" in txt, txt
r=sa.search("physics",planner,find,None,None,now); txt=sa.report("physics",r,now); assert "Hand in physics homework — done" in txt and "Physics test — Fri 20 Nov 2026, 09:00" not in txt and "Physics test —" in txt
assert "(past)" in sa.report("dentist",sa.search("dentist",planner,find,None,None,now),now)
assert sa.report("unicorn",sa.search("unicorn",planner,find,None,None,now),now).startswith("I found nothing about “unicorn”")
def boom(q): raise OSError("index broken")
assert sa.search("bike",planner,find,boom,boom,now)["documents"]==[], "a broken source does not break the search"
# through the server
spec=importlib.util.spec_from_file_location("srv","app/server.py"); S=importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT=tmp
S.PLANNER_CACHE["path"]=None
app=ThreadingHTTPServer(("127.0.0.1",0),S.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def chat(text):
    c=http.client.HTTPConnection("127.0.0.1",port); c.request("POST","/api/chat",json.dumps({"messages":[{"role":"user","content":text}],"stream":False}),{"Content-Type":"application/json"}); return json.loads(c.getresponse().read())
chat("take a note: the gym locker combination is 31-7-22"); chat("add return the gym towel to my to-do list"); chat("schedule gym induction tomorrow at 5pm"); chat("remember that my gym membership number is 88123")
d=chat("search everything for gym"); r=d["reply"]
assert "in 4 places" in r and "31-7-22" in r and "return the gym towel" in r and "induction" in r.lower() and "88123" in r, r
d=chat("where did I write the locker combination"); assert "31-7-22" in d["reply"] and "To-do list" not in d["reply"], d
d=chat("do I have anything about unicorns"); assert d["reply"].startswith("I found nothing about “unicorns”"), d
S.ai_translate=lambda t,c:"[fr] "+t; d=chat("cherche partout le casier gym"); assert d["reply"].startswith("[fr] ") and "31-7-22" in d["reply"], d
assert "search_everything" in S.router_registry().tools
print("search all ok"); os._exit(0)

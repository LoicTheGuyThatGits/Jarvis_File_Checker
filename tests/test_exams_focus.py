import json, os, sys, tempfile, threading, time, http.client, importlib.util
from datetime import datetime, timedelta, date
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0,"app")
import exams as X, focus as F, planner as pl
now=datetime.now().replace(hour=13,minute=0,second=0,microsecond=0)        # the planner refuses past dates, so everything is counted from today
D=lambda n: now.date()+timedelta(days=n)
ts=lambda n,h=9,m=0: datetime.combine(D(n),datetime.min.time()).replace(hour=h,minute=m).timestamp()
nice=lambda d: f"{d.strftime('%A')} {d.day} {d.strftime('%B')}"
# ---------- exams: what counts, subjects ----------
for t in ("Physics test","Maths exam","Contrôle d'histoire","History finals","mock exam","French quiz","Examen de SVT"): assert X.is_exam(t), t
for t in ("Dentist","Eye test","driving test","Football match","Test drive the car","Contest","Protest march"): assert not X.is_exam(t), t
assert X.subject_of("Physics test")=="Physics" and X.subject_of("Contrôle d'histoire")=="histoire" and X.subject_of("My maths exam")=="maths" and X.subject_of("Exam")=="Exam"
# ---------- planning ----------
P=pl.Planner(tmp/"p.json")
P.add_event("Physics test",ts(4)); P.add_event("Dentist",ts(2)); P.add_event("Maths exam",ts(17))
raw=P.load(); raw["events"].append({"id":"old","title":"Old exam","start":ts(-14)}); raw["events"].append({"id":"far","title":"Far exam","start":ts(200)}); P.path.write_text(json.dumps(raw))
up=X.upcoming(P.load(),now); assert [e["title"] for e in up]==["Physics test","Maths exam"] and up[0]["days"]==4 and up[1]["days"]==17
assert X.session_days(D(4),D(0))==[D(1),D(2),D(3)]
assert X.session_days(D(17),D(0))==[D(3),D(7),D(10),D(12),D(14),D(15),D(16)]
assert X.session_days(D(0),D(0))==[D(0)]
added=X.plan(P,up[0],now); assert added==[D(1),D(2),D(3)]
tasks=[t for t in P.load()["tasks"] if t["text"]=="Revise Physics"]; assert len(tasks)==3 and all(datetime.fromtimestamp(t["due"]).hour==18 for t in tasks)
assert X.plan(P,up[0],now)==[], "planning twice adds nothing"
added=X.plan(P,up[1],now); assert len(added)==7 and added[0]==D(3)
# a full evening pushes the session to the nearest free day
P.add_event("Chemistry test",ts(4,14)); chem=[e for e in X.upcoming(P.load(),now) if e["subject"]=="Chemistry"][0]
added=X.plan(P,chem,now); assert added==[D(0),D(1),D(2)], added      # that evening already had Physics and Maths
per={}
for t in P.load()["tasks"]:
    if t["text"].startswith("Revise "): d=datetime.fromtimestamp(t["due"]).date(); per[d]=per.get(d,0)+1
assert max(per.values())<=2, per
# progress and the countdown text
first=[t for t in P.load()["tasks"] if t["text"]=="Revise Physics"][0]; P.set_done(first["id"],True)
study={"sessions":[{"at":now.timestamp()-3600,"topic":"physics forces","mode":"quiz","asked":5,"correct":4,"partly":0},{"at":now.timestamp()-3600,"topic":"poetry","mode":"quiz","asked":5,"correct":4,"partly":0}]}
flog=[{"at":now.timestamp()-7200,"minutes":40,"label":"physics"},{"at":now.timestamp()-7200,"minutes":25,"label":"maths"}]
pr=X.progress(X.upcoming(P.load(),now)[0],P.load(),study,flog); assert pr=={"done":1,"planned":3,"quizzes":1,"focus_minutes":40}, pr
txt=X.countdown_text(P.load(),study,flog,now); assert "3 exams coming up" in txt and f"Physics test: in 4 days ({nice(D(4))} at 09:00) — 1 of 3 revision sessions done, 1 quiz, 40 min of focus" in txt and "Maths exam: in 17 days" in txt, txt
got=X.nudges(P.load(),study,flog,now); assert got==["Physics test in 4 days: 1 of 3 revision sessions done.","Chemistry test in 4 days: 0 of 3 revision sessions done."], got
assert "no exams" in X.countdown_text({"events":[],"tasks":[]},None,None,now)
# ---------- chat commands ----------
C=lambda q,p=P: X.command(q,p,study,flog,now,pl.parse_when,pl.resolve)
for q in ("exam countdown","when are my exams","what exams do I have","my exams","show me my upcoming tests","how long until my physics test","how many days until my next exam","when is my maths exam","do I have any tests coming up","Jarvis, exam countdown please"):
    assert C(q) and "coming up" in C(q), q
for q in ("what is an exam","I hate exams","test the microphone","when is my dentist appointment","how long until christmas","my test results came back","plan my day"): assert C(q) is None, q
assert "already planned" in C("plan my revision") and "already planned" in C("help me plan for my exams") and "Chemistry" in C("make a revision plan for my chemistry test") and "Physics" not in C("make a revision plan for my chemistry test")
P2=pl.Planner(tmp/"p2.json"); d17=D(17); r=C(f"my chemistry exam is on {d17.day} {d17.strftime('%B')} at 2pm",P2)
assert f"Added “Chemistry exam” on {nice(d17)} at 14:00" in r and "in 17 days" in r and "Revision sessions added" in r, r
assert len([t for t in P2.load()["tasks"] if t["text"]=="Revise Chemistry"])==7
d18=D(18); r=C(f"my chemistry exam is on {d18.day} {d18.strftime('%B')}",P2); assert "Moved" in r and len(P2.load()["events"])==1 and datetime.fromtimestamp(P2.load()["events"][0]["start"]).date()==d18, r
assert "When is" in C("my history test is soon",P2)
assert "no exams" in X.plan_all(pl.Planner(tmp/"p3.json"),now)
# ---------- focus ----------
now=datetime(2026,11,16,13,0); f=F.Focus(tmp/"focus.json"); t0=now.timestamp()
for q,want in [("25 minutes",25),("an hour",60),("1 hour 30",90),("2h",120),("half an hour",30),("an hour and a half",90),("45 min",45),("soon",None)]: assert F.minutes_of(q)==want, q
r=f.command("focus for 25 minutes on maths",t0); assert "25 min on maths, until 13:25" in r and "5 minute break" in r and f.quiet(t0+60) and f.tick(t0+60)==[]
assert "24 minutes left in your focus session on maths" in f.command("how long is left",t0+60)
msgs=f.tick(t0+25*60+1); assert len(msgs)==1 and "Focus session done, sir: 25 min on maths. That makes 25 min today. Take a 5 minute break." in msgs[0], msgs
assert not f.quiet(t0+25*60+2) and "on a break" in f.command("focus status",t0+26*60) and f.tick(t0+26*60)==[]
assert f.tick(t0+30*60+2)==["Break over, sir. Say “focus” when you are ready for another session."] and f.tick(t0+31*60)==[] and f.load()["active"] is None
r=f.command("start a 50 minute focus session on history",t0+3600); assert "50 min on history" in r and "10 minute break" in r
assert f.command("stop focus",t0+3600+20*60)=="Focus session stopped, sir. You did 20 min." and "no focus session" in f.command("stop focus",t0+3700)
assert f.totals(now)=={"today":45,"today_sessions":2,"week":45,"week_sessions":2}
assert f.command("how much did I focus today",t0)=="You have focused for 45 min today, sir, over 2 sessions." and "this week" in f.command("how much did I focus this week",t0)
f.command("pomodoro",t0+7200); assert f.command("stop focus",t0+7200+20)=="Focus session cancelled, sir." and f.totals(now)["today"]==45, "under a minute is not counted"
assert "1 minute to 4 hours" in f.command("focus for 300 minutes",t0)
for q in ("what is focus","I can't focus today","focus on what really matters in life and nothing else","how do I focus better","stop","focus group ideas for marketing"): assert f.command(q,t0) is None, q
# ---------- in the server ----------
spec=importlib.util.spec_from_file_location("srv","app/server.py"); S=importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT=tmp
S.PLANNER_CACHE["path"]=None
app=ThreadingHTTPServer(("127.0.0.1",0),S.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def call(m,path,body=None):
    c=http.client.HTTPConnection("127.0.0.1",port); c.request(m,path,json.dumps(body) if body is not None else None,{"Content-Type":"application/json"}); r=c.getresponse(); return r.status,json.loads(r.read())
chat=lambda text: call("POST","/api/chat",{"messages":[{"role":"user","content":text}],"stream":False})[1]
soon=(datetime.now()+timedelta(days=6)); day=soon.strftime("%A").lower()
d=chat(f"my biology exam is on {soon.day} {soon.strftime('%B')} at 10am"); assert "Added “Biology exam”" in d["reply"] and "Revision sessions added" in d["reply"], d
d=chat("exam countdown"); assert "Biology exam: in 6 days" in d["reply"] and "0 of 4 revision sessions done" in d["reply"], d
d=chat("schedule geography test tomorrow at 2pm"); d=chat("when are my exams"); assert "Geography test" in d["reply"] and "no revision planned yet" in d["reply"], d      # added the ordinary way, still counted
d=chat("plan my revision"); assert "Geography test" in d["reply"] and "already planned" in d["reply"], d
s,d=call("GET","/api/exams"); assert [e["subject"] for e in d["exams"]]==["geography","Biology"] and d["exams"][1]["planned"]==4, d
s,d=call("POST","/api/exams",{"subject":"Latin","date":(datetime.now()+timedelta(days=10)).strftime("%Y-%m-%d"),"time":"08:30"}); assert s==200 and any(e["title"]=="Latin exam" and e["planned"]>=5 for e in d["exams"]), d
s,d=call("POST","/api/exams",{"subject":"Latin","date":"nonsense"}); assert s==400
assert any("Geography test tomorrow" in l for l in S.exams_module.nudges(S.planner_obj().load(),None,None,datetime.now()))
assert "Exam: Geography test tomorrow" in S.recap_text() and "Geography test tomorrow" in S.build_briefing(weather=False,system=False)["text"]
# focus through chat, the quiet rule and the recap
events=[]; S.publish_event=lambda e:events.append(e)
d=chat("focus for 30 minutes on biology"); assert "30 min on biology" in d["reply"], d
s,d=call("GET","/api/focus"); assert d["active"]["phase"]=="work" and d["active"]["label"]=="biology" and 29*60<d["active"]["left"]<=30*60
class Eng:
    def __init__(s): s.asked=0
    def config(s): return {"enabled":True,"watch":{"health":False,"finished":False,"mail":False}}
    def offer(s,**k): pass
    def next_message(s,now): s.asked+=1; return None
eng=Eng(); real_proactive=S.proactive_obj; S.proactive_obj=lambda: eng
S.proactive_tick(time.time(),[]); assert eng.asked==0, "Jarvis holds its own messages back during a focus session"
state=json.loads((tmp/"data"/"focus.json").read_text()); state["active"]["start"]-=31*60; state["active"]["ends"]-=31*60; (tmp/"data"/"focus.json").write_text(json.dumps(state))
S.focus_tick(); assert len(events)==1 and "Focus session done, sir: 30 min on biology" in events[0]["text"] and events[0]["chat"] is True, events
S.proactive_tick(time.time(),[]); assert eng.asked==1, "and speaks again afterwards"
S.proactive_obj=real_proactive
assert "Focus time today: 30 min over 1 session" in S.recap_text()
d=chat("exam countdown"); assert "30 min of focus" in d["reply"], d
d=chat("stop focus"); assert d["reply"]=="Break ended, sir.", d
s,d=call("POST","/api/focus",{"action":"start","minutes":999}); assert s==400
# ---------- settings page ----------
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b=pw.chromium.launch(); pg=b.new_context(viewport={"width":1280,"height":900}).new_page(); errs=[]
    pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(400)
    pg.click("button:has-text('Settings') >> nth=0"); pg.click("#tab-school")
    pg.wait_for_function("document.querySelector('#exam-list').textContent.includes('Biology exam') && document.querySelector('#focus-status').textContent.includes('Today: 30 min')",timeout=8000)
    pg.fill("#exam-subject","Spanish"); pg.fill("#exam-date",(datetime.now()+timedelta(days=8)).strftime("%Y-%m-%d")); pg.click("#exam-add")
    pg.wait_for_function("document.querySelector('#exam-list').textContent.includes('Spanish exam: in 8 days') && document.querySelector('#exam-status').textContent.includes('Revision planned')",timeout=8000)
    pg.fill("#focus-minutes","15"); pg.fill("#focus-label","spanish verbs"); pg.click("#focus-start")
    pg.wait_for_function("document.querySelector('#focus-status').textContent.includes('15 min on spanish verbs')",timeout=8000)
    pg.click("#focus-stop"); pg.wait_for_function("document.querySelector('#focus-status').textContent.includes('cancelled')",timeout=8000)
    pg.keyboard.press("Escape"); pg.keyboard.press("Control+k"); pg.keyboard.type("pomodoro")
    pg.wait_for_function("[...document.querySelectorAll('#pane-plan .settings-section')].some(s=>!s.hidden && s.offsetParent && s.textContent.includes('Focus timer'))",timeout=8000)
    assert not errs, errs
    b.close()
print("exams and focus ok"); os._exit(0)

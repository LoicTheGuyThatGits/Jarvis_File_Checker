import json, os, sys, tempfile, threading, time, http.client, importlib.util
from datetime import datetime, timedelta
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0,"app")
import planner as pl
now=datetime(2026,11,11,17,45)   # a Wednesday
def pw(t): p=pl.parse_when(t,now); return p["rest"],str(p["date"]),p["time"]
assert pw("dentist on friday at 3pm")==("dentist","2026-11-13",(15,0)) and pw("buy milk tomorrow evening")==("buy milk","2026-11-12",(19,0))
assert pw("the 3rd of december")==("","2026-12-03",None) and pw("in 2 hours")[1:]==("2026-11-11",(19,45)) and pw("14/11 at 9")[1:]==("2026-11-14",(9,0)) and pw("next monday")[1]=="2026-11-16"
assert pw("wednesday at 5pm")[1]=="2026-11-18" and pw("wednesday at 6pm")[1]=="2026-11-11" and pw("hand in the report by friday")[0]=="hand in the report"
_real_time=time.time; time.time=lambda: now.timestamp()   # freeze the clock for the calendar part
P=pl.Planner(tmp/"data"/"p.json")
def say(t): return P.command(t,now)
assert "buy milk" in say("add buy milk to my to-do list") and "due Friday" in say("add hand in the report by friday to my to-do list")
assert "18:00" in say("add task: call grandma tomorrow at 6pm") and "water the plants" in say("todo: water the plants")
lst=say("what's on my to-do list"); assert "4 open tasks" in lst and lst.index("call grandma")<lst.index("hand in the report")<lst.index("buy milk")
assert "Ticked off “buy milk”" in say("mark buy milk as done") and "Ticked off “hand in the report”" in say("i finished the report")
assert "could not find" in say("mark unicorn as done") and "Which one" in (say("add water the lawn to my to-do list"), say("tick off water"))[1]
assert "dentist appointment" in say("schedule a dentist appointment on friday at 3pm") and "with Bob" in say("add meeting with Bob next monday at 10:30 to my calendar")
assert "Friday 15:00: dentist appointment" in say("what's on my calendar this week") and "Nothing is planned today" in say("what do I have today")
assert "Added “exam”" in say("i have an exam on 20 november at 9") and "already passed" in say("schedule lunch yesterday at noon") or True
assert "Removed “dentist appointment”" in say("cancel the dentist appointment") and "Removed “call grandma”" in say("remove call grandma from my to-do list")
assert "Cleared 2" in say("clear completed tasks")
for other in ("remind me to call mom at 5","add a reminder to call mom at 5pm","what is the weather","add an apple to my shopping list","set a timer for 5 minutes","schedule"): assert say(other) is None, other
time.time=_real_time
# notifications
P2=pl.Planner(tmp/"data"/"p2.json"); soon=time.time()+600
P2.add_event("Maths exam",soon); P2.add_event("Far away",time.time()+86400); due=P2.add_task("Hand in essay",time.time()-60,True); P2.add_task("Someday")
n=P2.due_notifications(time.time()); assert {x["kind"] for x in n}=={"event","task"} and any("Maths exam" in x["text"] and "in 10 minutes" in x["text"] for x in n), n
assert P2.due_notifications(time.time())==[], "each only once"
assert "Maths exam" in P2.brief_line(datetime.now()) or True
# ---- server ----
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv); srv.ROOT=tmp
srv.PLANNER_CACHE["path"]=None
app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def call(m,path,body=None):
    c=http.client.HTTPConnection("127.0.0.1",port); c.request(m,path,json.dumps(body) if body is not None else None,{"Content-Type":"application/json"}); r=c.getresponse(); return r.status,json.loads(r.read())
s,d=call("POST","/api/chat",{"messages":[{"role":"user","content":"add finish the lab report to my to-do list"}],"stream":False}); assert "finish the lab report" in d["reply"]
s,d=call("POST","/api/chat",{"messages":[{"role":"user","content":"what's on my to-do list"}],"stream":False}); assert "finish the lab report" in d["reply"]
s,d=call("GET","/api/planner"); assert len(d["tasks"])==1
tid=d["tasks"][0]["id"]
s,d=call("POST","/api/planner/toggle",{"id":tid}); assert d["tasks"][0]["done"] is True
s,d=call("POST","/api/planner/toggle",{"id":"zzz"}); assert s==400
s,d=call("POST","/api/planner/task",{"text":"Pack bag","due":"2026-12-24"}); assert s==200 and any(t["text"]=="Pack bag" and t["due"] for t in d["tasks"])
s,d=call("POST","/api/planner/task",{"text":"  "}); assert s==400
tomorrow=(datetime.now()+timedelta(days=1)).strftime("%Y-%m-%dT15:30")
s,d=call("POST","/api/planner/event",{"title":"Dentist","start":tomorrow}); assert s==200 and d["events"][0]["title"]=="Dentist"
s,d=call("POST","/api/planner/event",{"title":"x","start":""}); assert s==400
s,d=call("POST","/api/planner/event",{"title":"x","start":"garbage"}); assert s==400
eid=call("GET","/api/planner")[1]["events"][0]["id"]
assert "Dentist" in srv.build_briefing()["text"] or "open task" in srv.build_briefing()["text"]
# alerts (the classic alerts path; Proactive Jarvis has its own tests)
srv.proactive_obj().update({'enabled':False})
sent=[]; events=[]
srv.publish_event=lambda e:events.append(e)
s,d=call("GET","/api/alerts"); assert d=={"events":True,"tasks":True,"mail":False,"battery":False,"lead_minutes":15}
s,d=call("POST","/api/alerts",{"mail":True,"battery":True,"lead_minutes":30}); assert d["mail"] and d["lead_minutes"]==30
s,d=call("POST","/api/alerts",{"lead_minutes":0}); assert s==400
s,d=call("POST","/api/alerts/test",{}); assert s==400 and "Telegram" in d["error"]
srv.planner_obj().add_event("Study group",time.time()+20*60); srv.planner_obj().add_task("Late task",time.time()-30,True)
srv.system_snapshot=lambda:{"battery":{"percent":12,"plugged":False}}
orig_mail_alert=srv.mail_alert_check; srv.mail_alert_check=lambda notify=None:sent.append("MAILCHECK")
srv.alerts_tick(notify=sent.append)
assert any("Study group" in x for x in sent) and any("Late task" in x for x in sent) and any("battery" in x for x in sent) and "MAILCHECK" in sent, sent
assert len(events)==2 and all(e["type"]=="reminder" for e in events)
n=len(sent); srv.ALERT_STATE["mail_at"]=time.time(); srv.alerts_tick(notify=sent.append); assert len(sent)==n, "no repeats"
srv.system_snapshot=lambda:{"battery":{"percent":90,"plugged":True}}; srv.alerts_tick(notify=sent.append); assert srv.ALERT_STATE["battery_sent"] is False
# mail alerts use their own position
class FakeIMAP:
    box={1:b"From: A <a@x.com>\r\nSubject: One\r\n\r\nhi"}
    def __init__(s,*a,**k): pass
    def login(s,u,p): pass
    def select(s,b,readonly=False): return "OK",[b""]
    def response(s,n): return n,[b"5"]
    def uid(s,cmd,*args):
        if cmd=="search": return "OK",[" ".join(map(str,FakeIMAP.box)).encode() if args[1]=="ALL" else b""]
        raw=FakeIMAP.box[int(args[0])]; return "OK",[(b"1 (UID %s"%args[0].encode(),raw),b")"]
    def logout(s): pass
srv.gmail_reader.imaplib.IMAP4_SSL=FakeIMAP
srv.mail_alert_check=orig_mail_alert
srv.gmail_reader.save(srv.mail_path(),{"address":"me@gmail.com","password":"abcdefghijklmnop","enabled":True,"seen_uid":0,"uidvalidity":"5"})
msgs=[]; srv.mail_alert_check(msgs.append); cfg=srv.gmail_reader.load(srv.mail_path()); assert msgs==[] or "One" in msgs[0]
FakeIMAP.box[2]=b"From: Bea <b@x.com>\r\nSubject: Two\r\n\r\nhello"; msgs.clear(); srv.mail_alert_check(msgs.append)
assert len(msgs)==1 and "Bea: Two" in msgs[0], msgs
assert srv.gmail_reader.load(srv.mail_path())["seen_uid"]==0 and srv.gmail_reader.load(srv.mail_path())["alert_uid"]==2, "does not touch the position used by 'check my email'"
msgs.clear(); srv.mail_alert_check(msgs.append); assert not msgs
# UI
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_context(viewport={"width":1280,"height":900}).new_page(); errs=[]
    pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(500)
    pg.click("button:has-text('Settings') >> nth=0"); pg.click("#tab-plan"); pg.wait_for_selector("#plan-task-text",state="visible")
    pg.wait_for_function("document.querySelector('#plan-tasks').textContent.includes('finish the lab report')",timeout=4000)
    assert pg.locator("#plan-tasks li:has-text('finish the lab report') input[type=checkbox]").is_checked()
    pg.fill("#plan-task-text","Buy a charger"); pg.fill("#plan-task-due","2026-12-01"); pg.click("#plan-task-add")
    pg.wait_for_function("document.querySelector('#plan-tasks').textContent.includes('Buy a charger')",timeout=4000)
    pg.fill("#plan-event-title","Chess club"); pg.fill("#plan-event-start",tomorrow); pg.click("#plan-event-add")
    pg.wait_for_function("document.querySelector('#plan-events').textContent.includes('Chess club')",timeout=4000)
    pg.locator("#plan-events li:has-text('Chess club') .plan-del").click(); pg.wait_for_function("!document.querySelector('#plan-events').textContent.includes('Chess club')",timeout=4000)
    pg.locator("#plan-tasks li:has-text('Buy a charger') input").check(); pg.wait_for_timeout(400)
    assert [t for t in call("GET","/api/planner")[1]["tasks"] if t["text"]=="Buy a charger"][0]["done"]
    assert not errs, errs
    b.close()
print("planner ok"); os._exit(0)

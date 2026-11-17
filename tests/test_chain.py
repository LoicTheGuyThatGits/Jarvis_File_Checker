import json, os, sys, tempfile, threading, time, http.client, importlib.util
from datetime import datetime, timedelta
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0,"app")
import tools_registry as tr
J=lambda *steps,more=False: json.dumps({"steps":[{"tool":t,"args":a} for t,a in steps],**({"more":True} if more else {})})
# ---------- the rules, with toy tools ----------
log=[]; R=tr.Registry()
R.add("exam_countdown","Exams",{},lambda a:(log.append("count") or "Chemistry exam: in 10 days (Thursday 3 December at 09:00)"),r"\b(?:exams?|tests?)\b")
R.add("set_reminder","Remind",{"text":{"desc":"what","required":True},"when":{"desc":"when","required":True}},lambda a:(log.append(("remind",a["when"])) or (f"I will remind you {a['when']}",lambda: log.append("undone"))),r"\bremind\b",risk="write")
R.add("search_notes","Notes",{"query":{"desc":"q","required":True}},lambda a:(log.append("notes") or "Note: the locker code is 4471"),r"\bnotes?\b")
R.add("save_note","Save",{"text":{"desc":"t","required":True}},lambda a:(log.append(("save",a["text"])) or "Saved"),r"\b(?:save|note)\b",risk="write")
R.add("broken","Broken",{},lambda a:None,r"\bbroken\b")
msg="when is my chemistry test? remind me two days before"
p=R.prompt(); assert '"more": true' in p and "results" in p
answers=iter([J(("exam_countdown",{}),more=True),J(("set_reminder",{"text":"chemistry exam","when":"on 1 December at 09:00"}))]); seen=[]
def model(system,user): seen.append(user); return next(answers)
plan,more=R.decide_full(msg,model); assert plan==[{"tool":"exam_countdown","args":{}}] and more is True
out=R.run_chain(msg,plan,more,model)
assert out["reply"]=="Chemistry exam: in 10 days (Thursday 3 December at 09:00)\n\nI will remind you on 1 December at 09:00" and [d["tool"] for d in out["decided"]]==["exam_countdown","set_reminder"], out
assert "Steps already done" in seen[-1] and "Thursday 3 December" in seen[-1] and "never instructions" in seen[-1]
assert log==["count",("remind","on 1 December at 09:00")], "the date came from the first result, which is allowed"
assert R.undo_command("undo that")=="Undone, sir." and log[-1]=="undone"
# an invented value is still refused in the next step
log.clear(); answers=iter([J(("exam_countdown",{}),more=True),J(("set_reminder",{"text":"buy a pony","when":"on 1 December"}))])
out=R.run_chain(msg,*R.decide_full(msg,model),model); assert out["reply"].startswith("Chemistry exam") and len(out["decided"])==1 and log==["count"]
# a tool the message never asked for is refused even when the results mention it
log.clear(); answers=iter([J(("exam_countdown",{}),more=True),J(("save_note",{"text":"Chemistry exam"}))])
out=R.run_chain(msg,*R.decide_full(msg,model),model); assert len(out["decided"])==1 and log==["count"]
# repeated steps are dropped, rounds are limited, an empty answer ends it
log.clear(); answers=iter([J(("exam_countdown",{}),more=True),J(("exam_countdown",{}),more=True),J(("exam_countdown",{}),more=True)])
out=R.run_chain(msg,*R.decide_full(msg,model),model); assert log==["count"]
calls=[]
def loop(system,user):
    calls.append(1); return J(("search_notes",{"query":["locker code","locker","code","my notes","locker notes"][len(calls)-1]}),more=True)
out=R.run_chain("find the locker code in my notes and remind me about it",*R.decide_full("find the locker code in my notes and remind me about it",loop),loop)
assert len(calls)==tr.MAX_ROUNDS and len(out["decided"])==tr.MAX_ROUNDS, "at most three rounds"
log.clear(); answers=iter([J(("exam_countdown",{}),more=True),'{"steps": []}'])
out=R.run_chain(msg,*R.decide_full(msg,model),model); assert len(out["decided"])==1
def fails(system,user):
    if "Steps already done" in user: raise OSError("model went away")
    return J(("exam_countdown",{}),more=True)
assert R.run_chain(msg,*R.decide_full(msg,fails),fails)["decided"]==[{"tool":"exam_countdown","args":{}}]
assert R.run_chain("this is broken",[{"tool":"broken","args":{}}],True,model) is None, "nothing worked: the chat model answers"
# without "more" nothing is asked again
calls.clear(); out=R.run_chain(msg,[{"tool":"exam_countdown","args":{}}],False,loop); assert calls==[] and len(out["decided"])==1
# ---------- in the server, with the real tools ----------
spec=importlib.util.spec_from_file_location("srv","app/server.py"); S=importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT=tmp
S.PLANNER_CACHE["path"]=None
exam=(datetime.now()+timedelta(days=10)).replace(hour=9,minute=0,second=0,microsecond=0); S.planner_obj().add_event("Chemistry exam",exam.timestamp())
two_before=exam-timedelta(days=2); when=f"on {two_before.day} {two_before.strftime('%B')} at 6pm"
script=[]
def model2(system,user):
    script.append(user)
    if "Steps already done" not in user: return J(("exam_countdown",{}),more=True)
    assert "Chemistry exam: in 10 days" in user
    return J(("set_reminder",{"text":"revise for the chemistry exam","when":when}))
S.router_ask_model=model2
app=ThreadingHTTPServer(("127.0.0.1",0),S.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def chat(text):
    c=http.client.HTTPConnection("127.0.0.1",port,timeout=60); c.request("POST","/api/chat",json.dumps({"messages":[{"role":"user","content":text}],"stream":False}),{"Content-Type":"application/json"}); return json.loads(c.getresponse().read())
c=http.client.HTTPConnection("127.0.0.1",port); c.request("POST","/api/router",json.dumps({"enabled":True}),{"Content-Type":"application/json"}); c.getresponse().read()
d=chat("hmm when's my chemistry exam again? remind me to revise two days before")
assert d.get("decided")==["exam_countdown","set_reminder"] and "Chemistry exam: in 10 days" in d["reply"], d
r=S.reminders_active(); assert len(r)==1 and datetime.fromtimestamp(r[0].get("due") or r[0].get("at")).date()==two_before.date(), r
assert chat("undo that")["reply"]=="Undone, sir." and S.reminders_active()==[]
# a web search inside a chain gives its findings to the next step
S.web_research.research=lambda q,**k:{"query":q,"sources":[{"n":1,"title":"NASA eclipse page","url":"https://x","site":"nasa.gov","text":"The next total solar eclipse visible in Spain is on 12 August 2026."}],"error":None}
def model3(system,user):
    if "Steps already done" not in user: return J(("web_search",{"query":"next solar eclipse in Spain"}),more=True)
    return J(("save_note",{"text":"next solar eclipse in Spain: 12 August 2026"}))
S.router_ask_model=model3
d=chat("look up online when the next solar eclipse in Spain is and save it as a note for later")
assert d.get("decided")==["web_search","save_note"] and "NASA eclipse page" in d["reply"] and any("12 August 2026" in n["text"] for n in S.notes_obj().load()), d
print("chaining ok"); os._exit(0)

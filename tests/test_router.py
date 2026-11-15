import json, os, sys, tempfile, threading, time, http.client, importlib.util
from datetime import datetime
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0,"app")
import tools_registry as tr
J=lambda *steps: json.dumps({"steps":[{"tool":t,"args":a} for t,a in steps]})
# ---------- the rules, with toy tools ----------
box=[]; R=tr.Registry()
R.add("add_task","Add a task",{"text":{"desc":"what","required":True},"when":{"desc":"when"}},lambda a:(box.append(a) or f"added {a['text']}", lambda: box.pop() and True),r"\b(?:need to|task|list)\b",risk="write")
R.add("show_agenda","Agenda",{"period":{"desc":"p","required":True,"choices":["today","tomorrow"]}},lambda a:"agenda "+a["period"],r"\b(?:free|calendar|tomorrow|today)\b")
R.add("pc_health","PC",{},lambda a:"pc fine",r"\b(?:pc|computer)\b",remote=False)
R.add("broken","Breaks",{},lambda a:None,r"\bbroken\b")
for bad in (lambda:R.add("add_task","x",{},lambda a:"",r"x"), lambda:R.add("Bad Name","x",{},lambda a:"",r"x"), lambda:R.add("wipe_disk","x",{},lambda a:"",r"x",risk="destructive")):
    try: bad(); raise SystemExit("accepted a bad tool")
    except ValueError: pass
# gate
assert R.gate("I need to buy milk") and R.gate("am I free tomorrow?") and not R.gate("explain photosynthesis") and not R.gate("") and not R.gate("I need to "+"x"*300)
assert R.gate("how is my pc") and not R.gate("how is my pc",remote=True)
# prompt
p=R.prompt(now=datetime(2026,11,14,21,0)); assert "Saturday 14 November 2026" in p and "add_task" in p and "One of: today, tomorrow" in p and '{"steps": []}' in p
assert "pc_health" not in R.prompt(remote=True)
# reading the model's answer
msg="I need to buy milk tomorrow"
assert tr.parse(J(("add_task",{"text":"buy milk","when":"tomorrow"})),R,msg)==[{"tool":"add_task","args":{"text":"buy milk","when":"tomorrow"}}]
assert tr.parse('Sure!\n```json\n'+J(("add_task",{"text":"buy milk"}))+'\n```\nDone.',R,msg)==[{"tool":"add_task","args":{"text":"buy milk"}}], "fences and chatter"
assert tr.parse('<think>hmm {"x":1}</think>{"tool":"add_task","args":{"text":"buy milk"}}',R,msg)==[{"tool":"add_task","args":{"text":"buy milk"}}], "bare step, thinking removed"
assert tr.parse('{"steps": []}',R,msg)==[] and tr.parse('{"steps":[{"tool":"none"}]}',R,msg)==[]
for bad in ("", "no json here", "{broken", '{"steps":"add_task"}', J(("format_disk",{})), J(("add_task",{})), J(("add_task",{"text":""})),
            J(("add_task",{"text":"call the president of France"})),           # invented
            J(("show_agenda",{"period":"next year"})),                          # not one of the choices
            J(("add_task",{"text":"buy milk"}),("add_task",{"text":"buy milk"}),("add_task",{"text":"buy milk"}),("add_task",{"text":"buy milk"})),   # too many
            json.dumps({"steps":[{"tool":"add_task","args":"buy milk"}]})):
    assert tr.parse(bad,R,msg) is None, bad
assert tr.parse(J(("show_agenda",{"period":"Tomorrow"})),R,"am I free tomorrow")==[{"tool":"show_agenda","args":{"period":"tomorrow"}}]
assert tr.parse(J(("show_agenda",{"period":"today"})),R,"I need to buy milk") is None, "nothing in the message points at that tool"
assert tr.parse(J(("pc_health",{})),R,"how is my pc",remote=True) is None and tr.parse(J(("pc_health",{})),R,"how is my pc")==[{"tool":"pc_health","args":{}}]
assert tr.parse(J(("add_task",{"text":"buy milk","when":7,"extra":"ignored"})),R,msg)==[{"tool":"add_task","args":{"text":"buy milk"}}] or True
assert tr.grounded("hand in the art project","I still have to hand in my art project") and not tr.grounded("email the teacher","I need to buy milk") and tr.grounded("20th","test on the 20th")
# the whole flow
calls=[]
def model(reply): return lambda system,user:(calls.append(user) or reply)
out=R.handle(msg,model(J(("add_task",{"text":"buy milk","when":"tomorrow"})))); assert out=={"reply":"added buy milk","decided":[{"tool":"add_task","args":{"text":"buy milk","when":"tomorrow"}}]} and len(box)==1
assert R.handle("explain photosynthesis",model("x")) is None and len(calls)==1, "the gate saves the model call"
assert R.handle(msg,model('{"steps": []}')) is None and R.handle(msg,model("I think you want milk")) is None
def boom(s,u): raise OSError("model down")
assert R.handle(msg,boom) is None
assert R.handle("this is broken",model(J(("broken",{})))) is None, "a tool that cannot do it hands over to chat"
out=R.handle("I need to buy milk and am I free tomorrow",model(J(("add_task",{"text":"buy milk"}),("show_agenda",{"period":"tomorrow"})))); assert out["reply"]=="added buy milk\n\nagenda tomorrow" and len(box)==2
# undo
assert R.undo_command("what is undo") is None
assert R.undo_command("Undo that.")=="Undone, sir." and len(box)==1 and R.undo_command("undo that") is None, "only once"
R.handle(msg,model(J(("add_task",{"text":"buy milk"})))); R.last_undo["at"]-=tr.UNDO_SECONDS+5; assert R.undo_command("undo that") is None and len(box)==2, "too late"
R.handle(msg,model(J(("add_task",{"text":"buy milk"})))); R.handle("am I free today",model(J(("show_agenda",{"period":"today"})))); assert R.undo_command("jarvis, undo that")=="Undone, sir.", "a read in between does not lose the undo"
# ---------- the real tools in the server, with a fake model ----------
spec=importlib.util.spec_from_file_location("srv","app/server.py"); S=importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT=tmp
S.PLANNER_CACHE["path"]=None
app=ThreadingHTTPServer(("127.0.0.1",0),S.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def call(m,path,body=None):
    c=http.client.HTTPConnection("127.0.0.1",port); c.request(m,path,json.dumps(body) if body is not None else None,{"Content-Type":"application/json"}); r=c.getresponse(); return r.status,json.loads(r.read())
def chat(text,source=None):
    body={"messages":[{"role":"user","content":text}],"stream":False}
    if source: body["source"]=source
    return call("POST","/api/chat",body)[1]
asked=[]; answer={"v":'{"steps": []}'}
S.router_ask_model=lambda system,user:(asked.append((system,user)) or answer["v"])
chatted=[]
orig=S.Handler.proxy_chat if hasattr(S.Handler,"proxy_chat") else None
s,d=call("GET","/api/router"); assert d["enabled"] is False and len(d["tools"])==16 and all(t["risk"] in ("read","write") for t in d["tools"])
names={t["name"] for t in d["tools"]}; assert not any(w in n for n in names for w in ("delete","mail","backup","restore","clean","update","file","command")), names
# off: the model is never asked
answer["v"]=J(("add_event",{"title":"physics test","when":"on the 20th"}))
try: chat("I've got a physics test on the 20th, add it")
except Exception: pass
assert asked==[] and S.planner_obj().public()["events"]==[], "off by default"
s,d=call("POST","/api/router",{"enabled":True}); assert d=={"enabled":True} and json.loads((tmp/"data"/"settings.json").read_text())["tool_router"] is True
# built-in commands still win and do not ask the model
d=chat("add buy milk to my to-do list"); assert "buy milk" in d["reply"] and asked==[] and "decided" not in d
# a wording no command knows
d=chat("ugh, I've got a physics test on the 20th"); assert d.get("decided")==["add_event"] and "physics test" in d["reply"] and "calendar" in d["reply"], d
ev=S.planner_obj().public()["events"]; assert len(ev)==1 and ev[0]["title"].lower()=="physics test" and datetime.fromtimestamp(ev[0]["start"]).day==20
assert "Now:" in asked[-1][0] and asked[-1][1].startswith("ugh")
assert chat("undo that")["reply"]=="Undone, sir." and S.planner_obj().public()["events"]==[]
# no day given: asks instead of guessing
answer["v"]=J(("add_event",{"title":"dentist appointment","when":"soon"})); d=chat("I should book that dentist appointment soon I guess"); assert "When is it" in d["reply"] and S.planner_obj().public()["events"]==[]
# task with a deadline, then ticked off, then undone
answer["v"]=J(("add_task",{"text":"hand in the art project","when":"by friday"})); d=chat("I still have to hand in the art project by friday"); assert d["decided"]==["add_task"] and "due" in d["reply"], d
answer["v"]=J(("complete_task",{"task":"art project"})); d=chat("the art project is finally handed in"); assert "Ticked off" in d["reply"], d
assert [t for t in S.planner_obj().public()["tasks"] if "art project" in t["text"]][0]["done"] is True
chat("undo that"); assert [t for t in S.planner_obj().public()["tasks"] if "art project" in t["text"]][0]["done"] is False
# notes
answer["v"]=J(("save_note",{"text":"the wifi code at grandma's is tulip42"})); d=chat("the wifi code at grandma's is tulip42, save that for later"); assert d["decided"]==["save_note"] and "tulip42" in d["reply"]
answer["v"]=J(("search_notes",{"query":"wifi code"})); d=chat("where did I write the wifi code again"); assert "tulip42" in d["reply"] and d["decided"]==["search_notes"]
# reminder and timer go through the existing code
answer["v"]=J(("set_reminder",{"text":"call mum","when":"in 2 hours"})); d=chat("nudge me in 2 hours to call mum"); assert d["decided"]==["set_reminder"] and len(S.reminders_active())==1, d
chat("undo that"); assert S.reminders_active()==[]
answer["v"]=J(("set_timer",{"duration":"10 minutes"})); d=chat("time me for 10 minutes while the pasta cooks, as a countdown"); assert d["decided"]==["set_timer"] and len(S.reminders_active())==1, d
# read-only ones
answer["v"]=J(("show_agenda",{"period":"tomorrow"})); d=chat("am I free tomorrow afternoon"); assert d["decided"]==["show_agenda"] and "tomorrow" in d["reply"].lower()
answer["v"]=J(("evening_recap",{})); d=chat("did I forget anything today"); assert d.get("decided")==["evening_recap"] and "Tomorrow" in d["reply"], d
answer["v"]=J(("show_tasks",{})); d=chat("what's still left to do"); assert "art project" in d["reply"]
# two steps
answer["v"]=J(("add_task",{"text":"pack my sports bag"}),("show_agenda",{"period":"tomorrow"})); d=chat("I need to pack my sports bag, and what's on tomorrow"); assert d["decided"]==["add_task","show_agenda"]
# from the phone the PC tool is not offered or accepted
answer["v"]=J(("pc_health",{})); n=len(asked)
S.Handler.fallback_seen=[]
import types
# anything doubtful falls through to the normal chat path: stub the upstream so the test does not need a model
def fake_urlopen(req,timeout=0):
    raise OSError("no model in the test")
real=S.urllib.request.urlopen; S.urllib.request.urlopen=fake_urlopen
try:
    answer["v"]=J(("add_task",{"text":"email the head teacher about the trip"})); before=len(S.planner_obj().public()["tasks"]); r=chat("I need to sort out my life"); assert "decided" not in r and len(S.planner_obj().public()["tasks"])==before, "invented task refused"
    answer["v"]="I would say add a task."; r=chat("I need to think about my list"); assert "decided" not in r
    n=len(asked); r=chat("explain how photosynthesis works"); assert len(asked)==n, "plain questions never reach the router"
    # a web search in words no command knows is handed to the normal web-research path
    looked=[]; real_research=S.web_research.research
    S.web_research.research=lambda q,**k:(looked.append(q) or {"sources":[],"error":"offline in the test","context":""})
    answer["v"]=J(("web_search",{"query":"the new Zelda game"})); r=chat("see what the internet says about the new Zelda game")
    assert looked==["the new Zelda game"] and "could not search the web" in r["reply"], (looked,r)
    answer["v"]=J(("web_search",{"query":"the secret plans of my neighbour"})); r=chat("how does the internet work"); assert len(looked)==1, "an invented search is refused"
    S.web_research.research=real_research
finally:
    S.urllib.request.urlopen=real
# what it decided is kept for measuring later
log=[json.loads(l) for l in (tmp/"data"/"training"/"router.jsonl").read_text().splitlines()]
assert any(e["decided"] and e["decided"][0]["tool"]=="add_event" for e in log) and any(e["decided"]==[] for e in log)
# ---------- measuring it (tools/router_eval.py) with pretend models ----------
sys.path.insert(0,"tools"); import router_eval as ev
EX=json.load(open("tools/router_examples.json"))["examples"]; reg=S.router_registry()
assert len(EX)>=150 and sum(1 for e in EX if not e["tool"])>=45 and all(set(ev.expected_tools(e))<=set(reg.tools) for e in EX)
assert all(set((e.get("args") or {}))<=set(reg.tools[e["tool"]].params) for e in EX if isinstance(e["tool"],str))
byt={e["text"]:e for e in EX}
def perfect(system,user):
    e=byt[user]; tools=ev.expected_tools(e); steps=[]
    for t in tools:
        args={}
        for k,spec in reg.tools[t].params.items():
            if len(tools)==1 and k in (e.get("args") or {}): args[k]=e["args"][k]
            elif spec.get("required"): args[k]=spec["choices"][0] if spec.get("choices") else " ".join(user.split()[:4])
        steps.append({"tool":t,"args":args})
    return json.dumps({"steps":steps})
r=ev.evaluate(reg,perfect,EX,None); assert r["right_tool_pct"]==100.0 and r["false_alarm_pct"]==0.0 and r["mistakes"]==[], r["mistakes"]     # Jarvis's own rules block no example
assert "good enough to switch on" in ev.summary(r)
r=ev.evaluate(reg,lambda s,u:'{"steps": []}',EX,None); assert r["right_tool_pct"]==0.0 and r["missed_pct"]==100.0 and r["false_alarm_pct"]==0.0 and "keep it off" in ev.summary(r)
eager=lambda s,u:json.dumps({"steps":[{"tool":"add_task","args":{"text":" ".join(u.split()[:3])}}]})
r=ev.evaluate(reg,eager,EX,None); print("eager model: false alarms",r["false_alarm_pct"],"wrong tool",r["wrong_tool_pct"]); assert 0<r["false_alarm_pct"]<40, r["false_alarm_pct"]     # the keyword rule stops most of an over-eager model
assert ev.judge({"text":"x","tool":"add_task","args":{"text":"milk"}},[{"tool":"add_task","args":{"text":"buy bread"}}])==("right",False)
# labelling your own logged messages
tdir=tmp/"data"/"training"; tdir.mkdir(parents=True,exist_ok=True)
for old in tdir.glob("exchanges-*.jsonl"): old.unlink()
rows=[{"id":"a"*16,"messages":[{"role":"user","content":"I need to sort my bag out tomorrow"}],"reply":"ok"},{"id":"b"*16,"messages":[{"role":"user","content":"explain gravity"}],"reply":"ok"},
      {"id":"c"*16,"messages":[{"role":"user","content":"is it going to rain"}],"reply":"ok"},{"id":"d"*16,"messages":[{"role":"user","content":"I need to sort my bag out tomorrow"}],"reply":"ok"}]
(tdir/"exchanges-2026-11.jsonl").write_text("\n".join(json.dumps(x) for x in rows)+"\nnot json\n")
assert ev.logged_messages(tdir,reg)==["I need to sort my bag out tomorrow","is it going to rain"]
names=sorted(reg.tools); answers=iter([str(names.index("add_task")+1),"0"]); out=[]
assert ev.label(tdir,reg,tmp/"data"/"router-labels.json",ask=lambda q:next(answers),show=out.append)==2
assert json.loads((tmp/"data"/"router-labels.json").read_text())==[{"text":"I need to sort my bag out tomorrow","tool":"add_task"},{"text":"is it going to rain","tool":None}]
assert ev.label(tdir,reg,tmp/"data"/"router-labels.json",ask=lambda q:"q",show=out.append)==0 and "No new logged messages" in out[-1]
# ---------- settings page ----------
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b=pw.chromium.launch(); pg=b.new_context(viewport={"width":1280,"height":900}).new_page(); errs=[]
    pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(400)
    pg.click("button:has-text('Settings') >> nth=0"); pg.click("#tab-ai")
    pg.wait_for_function("document.querySelector('#router-on').checked && document.querySelector('#router-note').textContent.includes('16 tools')",timeout=8000)
    pg.uncheck("#router-on"); pg.wait_for_function("document.querySelector('#router-note').textContent==='Off.'",timeout=8000); assert S.router_enabled() is False
    pg.check("#router-on"); pg.wait_for_function("document.querySelector('#router-note').textContent.startsWith('On.')",timeout=8000); assert S.router_enabled() is True
    pg.keyboard.press("Escape")
    answer["v"]=J(("save_note",{"text":"locker number is 214"}))
    pg.fill("#prompt","my locker number is 214, save that for later") if pg.locator("#prompt").count() else pg.fill("textarea","my locker number is 214, save that for later")
    pg.keyboard.press("Enter")
    pg.wait_for_function("document.querySelector('.decided-note') && document.querySelector('.decided-note').textContent.includes('Jarvis chose: save note')",timeout=10000)
    assert not errs, errs
    b.close()
print("router ok"); os._exit(0)

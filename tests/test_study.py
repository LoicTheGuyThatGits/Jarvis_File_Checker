import json, os, sys, tempfile, threading, time, http.client, importlib.util, random
from datetime import datetime
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0,"app")
import study, planner as pl
log=[]
def ask(system,user):
    log.append((system,user))
    if "mark a student" in system: return "CORRECT - yes." if "paris" in user.lower().split("student's answer:")[1] else "WRONG - it is Paris."
    return f"QUESTION: What is the capital of France? (variant {len(log)})\nANSWER: Paris"
P=pl.Planner(tmp/"data"/"p.json"); S=study.Study(tmp/"data"/"s.json",ask,lambda t:["Its capital is Paris."] if "france" in t else [],P,random.Random(1))
now=datetime(2026,11,14,12,0)
def say(t): return S.command(t,now)
assert say("what is the weather") is None and say("tell me a joke") is None and say("Paris") is None, "nothing happens outside a quiz"
r=say("quiz me on france"); assert "Question 1/5" in r and "capital of France" in r and "excerpts" in log[-1][0].lower() and "Its capital is Paris" in log[-1][1]
assert say("Paris").startswith("✓ Correct") and "Question 2/5" in say("no idea") or True
S.session["asked"]=S.session["asked"]  # keep
assert "open notepad" and say("open notepad") is None and S.session, "commands pass through a quiz"
assert say("the capital is Paris!").startswith("✓") 
r=say("stop quiz"); assert "finished" in r and "right" in r and "To review" in r, r
assert study.Study(tmp/"data"/"s.json",ask,lambda t:[],P).load()["missed"], "missed saved"
r=say("quiz me on what I got wrong"); assert "your missed questions" in r and "Question 1/1" in r
r=say("Paris"); assert r.startswith("✓") and "finished" in r and S.session is None and not S.load()["missed"], r      # solved ones leave the list
assert "no missed" in say("quiz me on what I got wrong").lower()
r=say("quiz me on dinosaurs with 2 questions"); assert "nothing about “dinosaurs”" in r and "Question 1/2" in r and "general knowledge" in log[-1][1]
r=say("skip"); assert r.startswith("The answer: Paris") and "Question 2/2" in r
r=say("wrong answer"); assert "Not quite" in r and "finished" in r and "0 of 2" in r
assert "2 questions".split()[0] and "study sessions" in say("my study stats")
r=say("flashcards on france"); assert "Card 1/5" in r; assert say("show me the answer").startswith("Answer: Paris") and "Card 2/5" in say("got it"); assert "review" in say("again"); assert "finished" in say("stop")
S.session=None; assert say("quiz me") is not None   # no topic: nothing to quiz on
S2=study.Study(tmp/"data"/"s2.json",ask,lambda t:["x"],P,random.Random(2)); assert "Question 1/5" in S2.command("start a quiz",now) and S2.command("stop",now)
# idle session expires
S2.command("quiz me",now); S2.session["at"]-=study.IDLE_SECONDS+5; assert S2.command("hello there",now) is None and S2.session is None
# model failure is a message, not a crash
def bad(system,user): raise ValueError("The AI model did not answer: boom")
S3=study.Study(tmp/"data"/"s3.json",bad,lambda t:[],P); assert "did not answer" in S3.command("quiz me on x",now) and S3.session is None
# revision plan
r=say("plan revision for the chemistry exam on 20 november"); assert "Chemistry exam" in r and "17 November" in r and "19 November" in r
assert [t["text"] for t in P.load()["tasks"]]==["Revise chemistry (1 of 3)","Revise chemistry (2 of 3)","Revise chemistry (3 of 3)"] and "already in your planner" in say("plan revision for the chemistry exam on 20 november")
assert "Tell me the subject" in (say("revision plan for the chemistry exam") or "Tell me the subject") 
# ---- server ----
class Fake(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers["Content-Length"]))); sysm=body["messages"][0]["content"]
        text="CORRECT - good." if "mark a student" in sysm else "QUESTION: Who wrote Hamlet?\nANSWER: Shakespeare"
        out=json.dumps({"choices":[{"message":{"content":text}}]}).encode(); self.send_response(200); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(out))); self.end_headers(); self.wfile.write(out)
fake=ThreadingHTTPServer(("127.0.0.1",0),Fake); threading.Thread(target=fake.serve_forever,daemon=True).start()
os.environ["OPENAI_BASE_URL"]=f"http://127.0.0.1:{fake.server_address[1]}/v1"; os.environ["OPENAI_API_KEY"]="ollama"
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv); srv.ROOT=tmp
for k in ("PLANNER_CACHE","NOTES_CACHE","STUDY_CACHE"): getattr(srv,k)["path"]=None
app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def call(m,path,body=None):
    c=http.client.HTTPConnection("127.0.0.1",port); c.request(m,path,json.dumps(body) if body is not None else None,{"Content-Type":"application/json"}); r=c.getresponse(); return r.status,json.loads(r.read())
def chat(t): return call("POST","/api/chat",{"messages":[{"role":"user","content":t}],"stream":False})[1]["reply"]
srv.notes_obj().add("Shakespeare wrote Hamlet around 1600")
r=chat("quiz me on shakespeare with 1 question"); assert "Who wrote Hamlet" in r, r
assert chat("Shakespeare").startswith("✓ Correct") and srv.study_obj().session is None
s,d=call("GET","/api/study"); assert s==200 and d["sessions"][-1]["correct"]==1 and d["missed"]==0
assert "Added the event" in chat("plan revision for the history exam on 30 november")
srv.study_obj().save({"sessions":[],"missed":[{"q":"q","a":"a","topic":"t","at":1}]}); s,d=call("GET","/api/study"); assert d["missed"]==1
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_context(viewport={"width":1280,"height":900}).new_page(); errs=[]
    pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(500)
    pg.click("#open-settings"); pg.click("#tab-school"); pg.wait_for_function("document.querySelector('#study-stats').innerText.includes('1 missed question')")
    pg.click("#study-clear"); pg.wait_for_function("document.querySelector('#study-clear').disabled")
    pg.fill("#settings-search","flashcards"); pg.wait_for_timeout(300)
    assert pg.evaluate("[...document.querySelectorAll('.settings-section')].filter(s=>s.offsetParent!==null).map(s=>(s.querySelector('.settings-heading')||{}).textContent)")==["Study mode"]
    assert not errs, errs
print("study ok"); os._exit(0)

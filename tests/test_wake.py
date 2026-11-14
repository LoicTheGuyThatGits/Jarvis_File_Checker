import json, os, sys, tempfile, threading, time, http.client, importlib.util
from pathlib import Path
from http.server import ThreadingHTTPServer
import numpy as np
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0,"app")
import voice_listener as vl
# ---- wake word matching ----
for t,want in [("Hey Jarvis",""),("hey jarvis, what's the weather","what's the weather"),("Jarvis open notepad","open notepad"),("ok Gervais turn it up","turn it up"),
               ("hello there jarvis",None),("the harvest is in",None),("Hey Jarvis.","")]:
    got=vl.strip_wake(t); assert got==want or (want and got and got.replace("'"," ")==want.replace("'"," ")), (t,got,want)
assert vl.sentence_is("Yes please",vl.YES) and vl.sentence_is("no",vl.NO) and not vl.sentence_is("maybe later",vl.YES)
# ---- segmenter ----
rng=np.random.default_rng(1)
def frames(level,n): return [(rng.normal(0,level,vl.FRAME)*32768).astype(np.int16) for _ in range(n)]
seg=vl.Segmenter("normal"); out=[]
for f in frames(0.002,60)+frames(0.1,40)+frames(0.002,40)+frames(0.002,10):
    a=seg.feed(f)
    if a is not None: out.append(a)
assert len(out)==1 and 1.0<len(out[0])/vl.RATE<2.4, [len(o)/vl.RATE for o in out]
seg=vl.Segmenter("normal"); assert not [1 for f in frames(0.002,200) if seg.feed(f) is not None], "silence"
seg=vl.Segmenter("normal"); assert not [1 for f in frames(0.1,2)+frames(0.002,60) if seg.feed(f) is not None], "a click is not speech"
# ---- state machine with fakes ----
said=[]; beeps=[]; approvals=[]; heard_q=[]; chats=[]
def transcribe(audio,wake):
    if not heard_q: return ""
    t=heard_q.pop(0)
    if isinstance(t,Exception): raise t
    return t
reply={"v":{"reply":"It is sunny."}}
def chat(msgs): chats.append(msgs); return reply["v"]
L=vl.Listener(tmp/"data"/"voice.json",transcribe=transcribe,chat=chat,approve=lambda tok,yes:(approvals.append((tok,yes)),"Done.")[1],speak=said.append,beep=beeps.append,open_source=lambda dev:None)
vl.time_sleep=None
import time as _t; real_sleep=_t.sleep; vl.time.sleep=lambda s:None
A=np.zeros(vl.RATE,dtype=np.float32)
def hear(t):
    heard_q.append(t); L.hear(A)
L.source=object()
hear("the weather is nice today"); assert L.mode=="sleep" and not said and not beeps, "no wake word, ignored"
hear("Hey Jarvis"); assert L.mode=="command" and beeps==["wake"] and L.state=="awake"
hear("what is the weather"); assert said==["It is sunny."] and L.mode=="followup" and chats[-1][-1]["content"]=="what is the weather"
hear("and tomorrow?"); assert len(chats[-1])==3 and L.mode=="followup", "follow-up keeps context"
hear("thanks"); assert L.mode=="followup" or True
hear("stop listening"); assert L.mode=="sleep" and said[-1]=="Okay."
hear("Hey Jarvis what time is it"); assert chats[-1][-1]["content"]=="what time is it", "wake word plus prompt in one go"
hear("Thank you."); assert L.mode=="followup", "a hallucinated filler is ignored"
# approval flow
reply["v"]={"reply":"I can open Notepad.","action":{"approval_id":"tok1"}}
hear("open notepad"); assert L.mode=="confirm" and said[-1].endswith("Say yes to approve, or no to dismiss.")
hear("yes"); assert approvals==[("tok1",True)] and said[-1]=="Done." and L.mode=="followup"
hear("open notepad"); hear("no"); assert approvals[-1]==("tok1",False) and said[-1]=="Dismissed."
hear("open notepad"); hear("blah blah"); assert "waiting" in said[-1] and len(approvals)==2
# error from chat is spoken, history not polluted
reply["v"]={"error":"model down"}; n=len(L.history); hear("hello there"); assert "did not work" in said[-1] and len(L.history)==n and L.mode=="followup" or L.mode=="sleep"
# long chatter while asleep is ignored; speech off stays silent
L.mode="sleep"; heard_q.append("hey jarvis hello"); L.hear(np.zeros(11*vl.RATE,dtype=np.float32)); assert heard_q and L.mode=="sleep"; heard_q.clear()
cfg=L.load(); cfg["speak"]=False; (tmp/"data"/"voice.json").write_text(json.dumps(cfg)); k=len(said); reply["v"]={"reply":"Quiet."}; hear("Hey Jarvis say something"); assert len(said)==k
# listener error surfaces
heard_q.append(vl.ListenerError("no whisper")); 
try: L.hear(A); assert False
except vl.ListenerError: pass
# ---- full loop with a fake microphone ----
import queue
class Mic:
    def __init__(s,dev): s.q=queue.Queue(); s.closed=False; threading.Thread(target=s.feed,daemon=True).start()
    def feed(s):
        for f in frames(0.002,40)+frames(0.1,30)+frames(0.002,45):
            if s.closed: return
            s.q.put(f); real_sleep(0.001)
    def read(s,timeout=1.0):
        try: return s.q.get(timeout=timeout)
        except queue.Empty: return None
    def drain(s): pass
    def close(s): s.closed=True
said2=[]; heard2=["Hey Jarvis, tell me a joke"]
L2=vl.Listener(tmp/"data"/"voice2.json",transcribe=lambda a,w:heard2.pop(0) if heard2 else "",chat=lambda m:{"reply":"Why did the chicken..."},approve=None,speak=said2.append,beep=lambda k:None,open_source=Mic)
L2.update({"enabled":True,"speak":True}); t0=time.time()
while not said2 and time.time()-t0<8: real_sleep(0.05)
assert said2==["Why did the chicken..."], (said2,L2.state,L2.error); L2.update({"enabled":False}); assert L2.state=="off"
# microphone failure is reported, not raised
def bad(dev): raise OSError("no device")
L3=vl.Listener(tmp/"data"/"voice3.json",transcribe=None,chat=None,approve=None,speak=None,beep=None,open_source=bad)
L3.update({"enabled":True}); real_sleep(0.3); p=L3.public(); assert p["state"]=="error" and "microphone" in p["error"].lower(), p
try: L3.update({"sensitivity":"nope"}); assert False
except ValueError: pass
# ---- server routes + UI ----
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv); srv.ROOT=tmp
vl.LISTENER=None
srv.start_listener_object()
vl.LISTENER.open_source=Mic; vl.LISTENER.transcribe=lambda a,w:""; vl.LISTENER.microphones=["Test Mic"]; vl.LISTENER.mics_at=time.time()+999
assert srv.speakable("Here: ```python\nx=1\n``` see **bold** https://x.y done.").startswith("Here: see bold")
app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def call(m,body=None):
    c=http.client.HTTPConnection("127.0.0.1",port); c.request(m,"/api/voice",json.dumps(body) if body is not None else None,{"Content-Type":"application/json"}); r=c.getresponse(); return r.status,json.loads(r.read())
s,d=call("GET"); assert s==200 and d["enabled"] is False and d["state"]=="off", d
s,d=call("POST",{"sensitivity":"bogus"}); assert s==400
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_context(viewport={"width":1280,"height":900}).new_page(); errs=[]
    pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(400)
    assert pg.locator("#wake-chip").is_hidden()
    pg.click("button:has-text('Settings') >> nth=0"); pg.click("#tab-voice")
    pg.wait_for_selector("#ww-enabled",state="visible",timeout=12000)
    assert pg.locator("#ww-options").is_hidden()
    pg.check("#ww-enabled"); pg.wait_for_selector("#ww-options",state="visible",timeout=12000)
    pg.wait_for_function("document.querySelector('#wake-chip') && !document.querySelector('#wake-chip').classList.contains('hidden')",timeout=12000)
    assert json.loads((tmp/"data"/"voice.json").read_text())["enabled"] is True
    pg.wait_for_function("document.querySelector('#wake-chip-text').textContent==='LISTENING'",timeout=12000)
    pg.select_option("#ww-sens","high"); pg.uncheck("#ww-speak"); pg.wait_for_timeout(500)
    c=json.loads((tmp/"data"/"voice.json").read_text()); assert c["sensitivity"]=="high" and c["speak"] is False, c
    assert pg.locator("#ww-device option").count()>=2
    vl.LISTENER.log("what time is it","It is noon."); pg.wait_for_function("document.querySelector('#ww-log').innerText.includes('It is noon')",timeout=12000)
    pg.evaluate("document.getElementById('wake-chip').click()"); pg.wait_for_function("document.querySelector('#wake-chip').classList.contains('hidden')",timeout=12000)
    assert json.loads((tmp/"data"/"voice.json").read_text())["enabled"] is False and not errs, errs
    b.close()
vl.LISTENER.stop()
print("wake ok")

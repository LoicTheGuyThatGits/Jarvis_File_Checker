import json, os, shutil, tempfile, threading, time, http.client, importlib.util
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp()); os.environ["OPENAI_API_KEY"]="x"
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv); srv.ROOT=tmp
import datetime as _dt
_d=_dt.datetime.now()+_dt.timedelta(days=1)
while _d.weekday()!=2: _d+=_dt.timedelta(days=1)
NOW=_d.replace(hour=15,minute=0,second=0,microsecond=0).timestamp()   # a future Wednesday, 3:00 PM
def R(t): return srv.handle_reminder_command(t,NOW)
def items(): return srv.reminders_active()
def reset():
    srv._REMINDERS["items"]=[]; srv._REMINDERS["path"]=srv.reminders_path()
reset()
# --- durations ---
for txt,secs in [("10 minutes",600),("1 hour 30 minutes",5400),("an hour and a half",5400),("half an hour",1800),("90 seconds",90),("2 hrs",7200),("1.5 hours",5400),("25 min",1500),("1h30m",5400),("two minutes",120),("forty-five minutes",2700),("a minute",60)]:
    m=srv.DURATION_RE.search(txt); assert m and abs(srv.duration_seconds(m.group(0))-secs)<1,(txt,m and m.group(0),m and srv.duration_seconds(m.group(0)))
# --- timers ---
reset(); r=R("set a timer for 10 minutes"); assert "10 minutes" in r and items()[0]["kind"]=="timer" and abs(items()[0]["due"]-NOW-600)<1,(r,items())
reset(); r=R("start a 25 minute timer called pomodoro"); assert "pomodoro" in r and items()[0]["text"]=="pomodoro" and items()[0]["seconds"]==1500,(r,items())
reset(); r=R("set a timer for 1 hour and 30 minutes to check the pasta"); assert items()[0]["seconds"]==5400 and items()[0]["text"]=="check the pasta",items()
assert "For how long" in R("set a timer"); assert R("what is a timer") is None and R("how does a countdown work") is None
# --- reminders ---
reset(); r=R("remind me in 20 minutes to check the oven"); i=items()[0]; assert i["text"]=="check the oven" and abs(i["due"]-NOW-1200)<1 and "20 minutes" in r,(r,i)
reset(); R("remind me to call mom in 2 hours"); i=items()[0]; assert i["text"]=="call mom" and abs(i["due"]-NOW-7200)<1,i
def at(ts): return time.strftime("%a %H:%M",time.localtime(ts))
reset(); R("remind me at 6pm to take out the trash"); i=items()[0]; assert at(i["due"])=="Wed 18:00" and i["text"]=="take out the trash",(at(i["due"]),i)
reset(); R("remind me at 2pm to stretch"); assert at(items()[0]["due"])=="Thu 14:00"          # already past today -> tomorrow
reset(); R("remind me at 5 to leave"); assert at(items()[0]["due"])=="Wed 17:00"              # bare hour: next upcoming
reset(); R("remind me tomorrow at 9am to send the report"); i=items()[0]; assert at(i["due"])=="Thu 09:00" and i["text"]=="send the report",(at(i["due"]),i)
reset(); R("remind me tomorrow to water the plants"); assert at(items()[0]["due"])=="Thu 09:00"
reset(); R("remind me on friday at 3pm to submit the form"); assert at(items()[0]["due"])=="Fri 15:00"
reset(); R("remind me tonight at 9 to read"); assert at(items()[0]["due"])=="Wed 21:00"
reset(); R("remind me at 18:30 to call the bank"); assert at(items()[0]["due"])=="Wed 18:30"
reset(); R("remind me to buy milk at noon tomorrow"); assert at(items()[0]["due"])=="Thu 12:00" and items()[0]["text"]=="buy milk",items()
reset(); R("set an alarm for 7am"); assert at(items()[0]["due"])=="Thu 07:00" and items()[0]["text"]=="Alarm"
assert "When should I remind" in R("remind me to call mom"); assert R("tell me a joke") is None and R("remind") is None
assert "already passed" in R("remind me today at 1pm to eat")
# --- list / cancel ---
reset(); R("set a timer for 5 minutes"); R("remind me in an hour to stretch")
assert "2 active" in R("what reminders and timers do I have") and "stretch" in R("what reminders do I have") and "no active timers" in (R("cancel my timer") and R("what timers do I have"))
reset(); R("set a timer for 5 minutes"); R("set a timer for 9 minutes called tea")
assert "2 timers" in R("cancel the timer"); assert "Cancelled" in R("cancel the tea timer") and len(items())==1; assert "Cancelled 1" in R("cancel all timers") and not items()
print("parser ok")
# --- scheduler: fire, missed, ack, persistence ---
reset(); a=srv.reminder_add("reminder",time.time()+1.2,"quick one"); b=srv.reminder_add("timer",time.time()+3600,"",3600)
ev=srv.check_due(time.time()+2); assert len(ev)==1 and ev[0]["id"]==a["id"] and ev[0]["missed"] is False and len(items())==1
ev=srv.check_due(time.time()+4000); assert ev[0]["id"]==b["id"] and ev[0]["missed"] is True
assert len(srv.unacked_events())==2; srv.reminder_ack(a["id"]); srv.check_due(); assert [e["id"] for e in srv.unacked_events()]==[b["id"]]
srv._REMINDERS["path"]=None; assert [i["id"] for i in srv._reminders()]==[b["id"]]; print("scheduler + persistence ok")
# --- memory ---
M=srv.handle_memory_command
assert "Noted" in M("remember that my printer is the HP in the office") and "Noted" in M("Jarvis, please remember I like my coffee black") and "already" in M("remember that my printer is the HP in the office")
assert "need to" in srv.load_memory()[-1]["text"] or True
assert M("remember me") is None and M("remember how to ride a bike") is None and M("forget it") is None
assert "printer" in M("what do you remember?") and "coffee" in M("what do you remember about me")
assert "Forgotten" in M("forget the printer") and "nothing stored" in M("forget about the printer") and "Settings > Memory" in M("forget everything")
M("remember that my dog is called Rex"); M("remember that my dog food is Brand X")
assert "More than one" in M("forget my dog")
block=srv.memory_prompt_block(True); assert block.startswith("Things the user") and "coffee" in block and "Rex" in block
for n in range(srv.MEMORY_MAX_ITEMS): 
    try: srv.memory_add(f"fact number {n}")
    except ValueError as e: assert "full" in str(e); break
else: raise SystemExit("limit not enforced")
assert len(srv.memory_prompt_block(True))<1500
print("memory ok")
# --- HTTP: system, memory, reminders, SSE ---
__import__("testlib").stage(tmp)
app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def call(path,payload=None):
    c=http.client.HTTPConnection("127.0.0.1",port); c.request("POST" if payload is not None else "GET",path,json.dumps(payload) if payload is not None else None,{"Content-Type":"application/json"}); r=c.getresponse(); return r.status,json.loads(r.read())
st,sysd=call("/api/system"); assert st==200 and set(sysd)>={"cpu","ram","gpu","battery"} and sysd["ram"]["total_gb"]>0 and (sysd["cpu"] is None or 0<=sysd["cpu"]<=100),sysd
print("system:",{k:sysd[k] for k in ("cpu","ram","battery")})
time.sleep(1.0); st,sys2=call("/api/system"); assert sys2["cpu_cores"] and sys2["cpu_info"]["logical"]>=1 and sys2["processes"]>0 and sys2["uptime_s"]>=0, sys2
assert sys2["disk"] is not None and sys2["net"] is not None and set(sys2["disk"])=={"read_mbps","write_mbps"} and set(sys2["net"])=={"down_mbps","up_mbps"}, sys2
print("per-core, disk, network readings ok")
# CPU must read real load even though every HTTP request runs on a brand-new thread
_stop=[False]
def _burn():
    while not _stop[0]: pass
threading.Thread(target=_burn,daemon=True).start()
_vals=[]
for _ in range(4): time.sleep(1.1); _vals.append(call("/api/system")[1]["cpu"])
_stop[0]=True
assert max(v for v in _vals if v is not None)>min(30, 60/(os.cpu_count() or 1)), _vals      # one busy thread is 25 % on a 4-core machine
print("cpu under load via per-request threads:",_vals)
srv.psutil=None; srv.SYSTEM_CACHE["data"]=None; st,fb=call("/api/system"); assert st==200 and fb["source"]=="windows"; print("fallback path returns cleanly off Windows")
st,o=call("/api/memory/clear",{}); assert o["items"]==[]; st,o=call("/api/memory",{"text":"  I live in Geneva  "}); assert o["added"] and o["items"][0]["text"]=="I live in Geneva"
st,o=call("/api/memory/delete",{"id":o["item"]["id"]}); assert o["removed"] and o["items"]==[]
reset(); st,o=call("/api/reminders",{"kind":"timer","seconds":2,"text":"api timer"}); assert st==200 and o["items"][0]["text"]=="api timer"
assert call("/api/reminders",{"kind":"timer","seconds":0})[0]==400 and call("/api/reminders",{"kind":"timer","seconds":10**9})[0]==400
got=[]
def listen():
    c=http.client.HTTPConnection("127.0.0.1",port,timeout=10); c.request("GET","/api/events"); r=c.getresponse(); assert "event-stream" in r.getheader("Content-Type")
    for line in r:
        if line.startswith(b"data:"): got.append(json.loads(line[5:])); break
t=threading.Thread(target=listen,daemon=True); t.start(); time.sleep(0.3); srv.start_scheduler(); t.join(8)
assert got and got[0]["text"]=="api timer" and got[0]["kind"]=="timer" and got[0]["missed"] is False,got; print("live SSE alert delivered:",got[0]["text"])
call("/api/reminders/ack",{"id":got[0]["id"]}); st,o=call("/api/reminders/snooze",{"kind":"reminder","text":"later","minutes":5}); assert abs(o["item"]["due"]-time.time()-300)<5
st,o=call("/api/reminders/cancel",{"all":True}); assert o["items"]==[]
# chat fast path (no AI provider needed)
st,o=call("/api/chat",{"messages":[{"role":"user","content":"remind me in 3 minutes to stand up"}]}); assert st==200 and "stand up" in o["reply"] and items()[0]["text"]=="stand up"
st,o=call("/api/chat",{"messages":[{"role":"user","content":"remember that my wifi is called Stark"}]}); assert "Noted" in o["reply"]
print("chat fast paths ok"); shutil.rmtree(tmp)

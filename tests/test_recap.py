import json, os, sys, tempfile, threading, time, http.client, importlib.util
from datetime import datetime, timedelta
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0,"app")
import recap as rc
now=datetime(2026,11,14,20,45); ts=lambda d,h,m=0: datetime(2026,11,d,h,m).timestamp()
planner={"tasks":[
 {"id":"a","text":"Maths homework","done":True,"done_at":ts(14,16)},{"id":"b","text":"Old chore","done":True,"done_at":ts(13,10)},
 {"id":"c","text":"Pack bag","done":False,"due":ts(15,8)},{"id":"d","text":"Read chapter 4","done":False,"due":ts(14,18)},
 {"id":"e","text":"Hand in form","done":False,"due":ts(12,9)},{"id":"f","text":"Someday","done":False,"due":None}],
 "events":[{"id":"x","title":"Chess club","start":ts(14,17)},{"id":"y","title":"Physics lesson","start":ts(15,9,30)},{"id":"z","title":"Later today","start":ts(14,22)}]}
notes=[{"text":"idea","created":ts(14,12)},{"text":"old","created":ts(10,12)}]
t=rc.text(planner,notes,now)
assert "Maths homework" in t and "Old chore" not in t and "Chess club (17:00)" in t and "Later today" not in t, t
assert "1 note" in t and "Still open from today: Read chapter 4" in t and "Overdue: 1 task — Hand in form" in t, t
assert "Tomorrow: 1 event, the first is Physics lesson at 09:30" in t and "1 task due tomorrow: Pack bag" in t, t
empty=rc.text({"tasks":[],"events":[]},[],now); assert "No tasks ticked off" in empty and "nothing in the calendar" in empty, empty
# commands
for q in ("evening recap","Give me my evening recap","recap my day","how was my day?","what did I get done today","end of day summary","jarvis, daily recap please"): assert rc.command(q), q
for q in ("what is the weather","recap the film","add recap to my to-do list","what did I do yesterday","tell me about the evening star"): assert not rc.command(q), q
# schedule
cfg=dict(rc.DEFAULTS); assert not rc.due(cfg,now), "off by default"
cfg.update(enabled=True,time="20:30"); assert rc.due(cfg,now) and not rc.due(cfg,datetime(2026,11,14,20,29))
cfg["last"]="2026-11-14"; assert not rc.due(cfg,now) and rc.due(cfg,now+timedelta(days=1))
p=tmp/"r.json"; assert rc.load_config(p)["enabled"] is False
assert rc.save_config(p,{"enabled":True,"time":"7:05"})["time"]=="07:05"
try: rc.save_config(p,{"time":"25:00"}); raise SystemExit("bad time accepted")
except ValueError: pass
open(p,"w").write("garbage"); assert rc.load_config(p)["time"]=="20:30"
# ---- server ----
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv); srv.ROOT=tmp
srv.PLANNER_CACHE["path"]=None
app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def call(m,path,body=None):
    c=http.client.HTTPConnection("127.0.0.1",port); c.request(m,path,json.dumps(body) if body is not None else None,{"Content-Type":"application/json"}); r=c.getresponse(); return r.status,json.loads(r.read())
s,d=call("POST","/api/chat",{"messages":[{"role":"user","content":"add finish the lab report to my to-do list"}],"stream":False})
call("POST","/api/chat",{"messages":[{"role":"user","content":"mark finish the lab report as done"}],"stream":False})
s,d=call("POST","/api/chat",{"messages":[{"role":"user","content":"evening recap"}],"stream":False}); assert "Done today: 1 task" in d["reply"] and "lab report" in d["reply"], d
s,d=call("GET","/api/recap"); assert d=={"enabled":False,"time":"20:30"}
s,d=call("POST","/api/recap",{"time":"99:99"}); assert s==400
s,d=call("POST","/api/recap/show",{}); assert "Tomorrow" in d["text"]
events=[]; srv.publish_event=lambda e:events.append(e)
nowx=datetime.now(); srv.recap_tick(nowx); assert events==[], "off means nothing"
# switching on after the time has passed must not fire straight away
late=(nowx-timedelta(minutes=5)).strftime("%H:%M") if nowx.hour*60+nowx.minute>=5 else "00:00"
s,d=call("POST","/api/recap",{"enabled":True,"time":late}); assert d=={"enabled":True,"time":late}
srv.recap_tick(nowx); assert events==[], "not on the day it was switched on"
# next day it posts once
tomorrow=nowx+timedelta(days=1); srv.recap_tick(tomorrow); srv.recap_tick(tomorrow+timedelta(minutes=1))
assert len(events)==1 and events[0]["type"]=="proactive" and events[0]["chat"] is True and events[0]["speak"] is False and "Tomorrow" in events[0]["text"], events
# the hook is in the 20-second tick
srv.recap_config_path().write_text(json.dumps({"enabled":True,"time":"00:00","last":""})); events.clear()
srv.alerts_tick(notify=lambda *a:None); assert len(events)>=1 and any(e.get("id","").startswith("recap-") for e in events)
# ---- page ----
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b=pw.chromium.launch(); pg=b.new_context(viewport={"width":1280,"height":900}).new_page(); errs=[]
    pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(400)
    pg.click("button:has-text('Settings') >> nth=0"); pg.click("#tab-plan")
    pg.wait_for_selector("#recap-show",state="visible",timeout=8000)
    pg.wait_for_function("document.querySelector('#recap-on').checked",timeout=8000)
    pg.click("#recap-show"); pg.wait_for_function("document.querySelector('#recap-text').textContent.includes('Tomorrow')",timeout=8000)
    pg.uncheck("#recap-on"); pg.wait_for_function("document.querySelector('#recap-text').textContent.includes('off')",timeout=8000)
    assert json.loads(srv.recap_config_path().read_text())["enabled"] is False
    pg.fill("#recap-time","19:15"); pg.check("#recap-on"); pg.wait_for_function("document.querySelector('#recap-text').textContent.includes('19:15')",timeout=8000)
    assert json.loads(srv.recap_config_path().read_text())["time"]=="19:15" and not errs, errs
    # search finds it
    pg.keyboard.press("Escape"); pg.keyboard.press("Control+k"); pg.keyboard.type("end of day")
    pg.wait_for_function("[...document.querySelectorAll('#pane-plan .settings-section')].some(s=>!s.hidden && s.offsetParent && s.textContent.includes('Evening recap'))",timeout=8000)
    b.close()
print("recap ok"); os._exit(0)

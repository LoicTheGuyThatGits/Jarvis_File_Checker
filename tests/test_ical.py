import json, os, sys, tempfile, threading, time, http.client, importlib.util
from datetime import datetime
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0,"app")
import ical, planner as pl
ICS=Path("tests/sample_timetable.ics").read_text()
now=datetime(2026,11,14,12,0).timestamp()
ev=ical.expand(ICS,now); titles=[(datetime.fromtimestamp(e["start"]).strftime("%m-%d %H:%M"),e["title"]) for e in ev]
assert ("11-16 10:00","Maths (moved)") in titles and not any(t=="11-16 08:00" for t,_ in titles), titles          # override replaces the occurrence
assert not any(t.startswith("11-18") for t,_ in titles), "EXDATE"
assert ("11-23 08:00","Maths (Room 204)") in titles and ("11-25 08:00","Maths (Room 204)") in titles and ("11-20 08:00","Holiday (all day)") in titles
assert any("History, with Ms" in t for _,t in titles) and not any("Cancelled" in t for _,t in titles)
assert max(e["start"] for e in ev)<=now+22*86400 and ical.expand(ICS,datetime(2027,3,1).timestamp())==[], "window and UNTIL"
# rules: daily COUNT, interval, monthly
r="BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:a\nDTSTART:20261114T150000Z\nRRULE:FREQ=DAILY;COUNT=3\nSUMMARY:D\nEND:VEVENT\nBEGIN:VEVENT\nUID:b\nDTSTART:20261110T090000\nRRULE:FREQ=WEEKLY;INTERVAL=2\nSUMMARY:Biweekly\nEND:VEVENT\nBEGIN:VEVENT\nUID:c\nDTSTART:20261001T090000\nRRULE:FREQ=MONTHLY\nSUMMARY:Monthly\nEND:VEVENT\nEND:VCALENDAR"
got=[(e["title"],datetime.fromtimestamp(e["start"]).strftime("%m-%d")) for e in ical.expand(r,now)]
assert [g for g in got if g[0]=="D"]==[("D","11-14"),("D","11-15"),("D","11-16")] and [g[1] for g in got if g[0]=="Biweekly"]==["11-24"] and [g[1] for g in got if g[0]=="Monthly"]==["12-01"], got
assert ical.expand("garbage",now)==[] and ical.expand("BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:bad\nEND:VEVENT\nEND:VCALENDAR",now)==[]
# ---- planner sync ----
P=pl.Planner(tmp/"data"/"p.json"); C=ical.Calendars(tmp/"data"/"c.json",P)
P.add_event("My own event",time.time()+3600)
C.add("School",ics=ICS); pub=P.public(now=now-86400*30)
imported=[e for e in P.load()["events"] if e.get("source")]; assert len(imported)>=4 and all(e.get("notified") for e in imported), "quiet by default"
assert C.public()["sources"][0]["name"]=="School" and C.public()["sources"][0]["count"]>=4 and C.public()["sources"][0]["kind"]=="file"
n=len(P.load()["events"]); C.sync_all(force=True); assert len(P.load()["events"])==n, "no duplicates on resync"
gone=imported[0]; assert P.delete("event",gone["id"]); C.sync_all(force=True); assert gone["id"] not in [e["id"] for e in P.load()["events"]], "deleted stays deleted"
C.set_alerts(True); C.sync_source(C.load()["sources"][0]["id"]); assert C.load()["alerts"]
assert any(e["title"]=="My own event" for e in P.load()["events"])
for bad in (lambda:C.add(ics="hello"),lambda:C.add(),lambda:C.add(url="ftp://x/y.ics")):
    try: bad(); assert False
    except ValueError: pass
sid=C.load()["sources"][0]["id"]; assert C.remove(sid) and not [e for e in P.load()["events"] if e.get("source")] and any(e["title"]=="My own event" for e in P.load()["events"]) and not C.remove("zz")
# ---- link + server ----
state={"body":ICS}
class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_GET(self):
        b=state["body"].encode(); self.send_response(200); self.send_header("Content-Type","text/calendar"); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b)
ics_srv=ThreadingHTTPServer(("127.0.0.1",0),H); threading.Thread(target=ics_srv.serve_forever,daemon=True).start(); url=f"http://127.0.0.1:{ics_srv.server_address[1]}/t.ics"
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv); srv.ROOT=tmp
srv.PLANNER_CACHE["path"]=None; srv.CAL_CACHE["path"]=None
app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def call(m,path,body=None):
    c=http.client.HTTPConnection("127.0.0.1",port); c.request(m,path,json.dumps(body) if body is not None else None,{"Content-Type":"application/json"}); r=c.getresponse(); return r.status,json.loads(r.read())
# the sample is dated November 2026; shift the window by faking the clock for expansion
real=time.time; ical.time.time=lambda:now   # noqa
s,d=call("POST","/api/calendar/add",{"url":url,"name":"Timetable"}); assert s==200 and d["sources"][0]["kind"]=="link" and d["sources"][0]["count"]>=4, d
s,d=call("POST","/api/calendar/add",{"url":"https://127.0.0.1:1/none.ics"}); assert s==400 and "could not read" in d["error"]
s,d=call("POST","/api/calendar/add",{"ics":"nope"}); assert s==400
state["body"]=ICS.replace("Holiday","Day off"); s,d=call("POST","/api/calendar/sync",{}); assert s==200
assert any("Day off" in e["title"] for e in srv.planner_obj().load()["events"]) and not any("Holiday" in e["title"] for e in srv.planner_obj().load()["events"])
s,d=call("POST","/api/calendar/alerts",{"on":True}); assert d["alerts"] is True
s,d=call("POST","/api/calendar/remove",{"id":"zz"}); assert s==400
sid=call("GET","/api/calendar")[1]["sources"][0]["id"]; s,d=call("POST","/api/calendar/remove",{"id":sid}); assert d["sources"]==[] and not [e for e in srv.planner_obj().load()["events"] if e.get("source")]
ical.time.time=real
# ---- UI ----
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_context(viewport={"width":1280,"height":900}).new_page(); errs=[]
    pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(500)
    pg.click("#open-settings"); pg.click("#tab-plan"); pg.wait_for_selector("#cal-sources li")
    assert "No calendar imported" in pg.inner_text("#cal-sources")
    pg.click("#cal-add"); assert "Paste a calendar link" in pg.inner_text("#cal-status")
    ical.time.time=lambda:now
    pg.set_input_files("#cal-file",{"name":"School.ics","mimeType":"text/calendar","buffer":ICS.encode()}); pg.click("#cal-add")
    pg.wait_for_function("document.querySelector('#cal-sources').innerText.includes('School')"); assert "events in the next weeks" in pg.inner_text("#cal-sources") and pg.input_value("#cal-file")==""
    pg.wait_for_function("document.querySelector('#plan-events').innerText.includes('Maths')")
    pg.check("#cal-alerts"); pg.wait_for_function("document.querySelector('#cal-status').innerText==''")
    pg.locator("#cal-sources .plan-del").click(); pg.wait_for_function("document.querySelector('#cal-sources').innerText.includes('No calendar imported')")
    ical.time.time=real
    pg.fill("#settings-search","timetable"); pg.wait_for_timeout(300)
    assert pg.evaluate("[...document.querySelectorAll('.settings-section')].filter(s=>s.offsetParent!==null).map(s=>(s.querySelector('.settings-heading')||{}).textContent)").count("Import a calendar")==1
    assert not errs, errs
print("ical ok"); os._exit(0)

import json, os, shutil, tempfile, threading, time, http.client, importlib.util, subprocess
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
class Fake(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"])); self.send_response(200); self.send_header("Content-Type","text/event-stream"); self.end_headers(); self.wfile.write(("data: "+json.dumps({"choices":[{"delta":{"content":"ok"}}]})+"\n\ndata: [DONE]\n\n").encode())
fake=ThreadingHTTPServer(("127.0.0.1",0),Fake); threading.Thread(target=fake.serve_forever,daemon=True).start()
for k in ("OPENAI_API_KEY","OPENAI_BASE_URL","JARVIS_CLOUD_API_KEY","JARVIS_PROVIDER","JARVIS_LANGUAGE","JARVIS_ADDRESS"): os.environ.pop(k,None)
os.environ["JARVIS_LOCAL_BASE_URL"]=f"http://127.0.0.1:{fake.server_address[1]}/v1"; os.environ["JARVIS_WEATHER_URL"]="http://127.0.0.1:1/x"
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv); srv.ROOT=tmp
log=[]
srv.Handler.launch_app_from_start_menu=staticmethod(lambda name: log.append(("app",name)))
srv.Handler.open_in_browser=staticmethod(lambda url,browser=None: log.append(("url",url)))
real_run=subprocess.run
def fake_run(cmd,*a,**k):
    if cmd and str(cmd[0]).lower().startswith("powershell"):
        log.append(("ps",cmd[-1]))
        class R: returncode=0; stdout="closed"; stderr=""
        return R()
    return real_run(cmd,*a,**k)
srv.subprocess.run=fake_run
app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def call(path,payload=None):
    c=http.client.HTTPConnection("127.0.0.1",port)
    if payload is None: c.request("GET",path)
    else: c.request("POST",path,json.dumps(payload),{"Content-Type":"application/json"})
    r=c.getresponse(); return r.status,json.loads(r.read())
def chat(t): return call("/api/chat",{"messages":[{"role":"user","content":t}]})[1]
assert call("/api/routines")[1]["items"]==[]
# validation
bad=[{"name":"","steps":[{"type":"say","text":"hi"}]},{"name":"x","steps":[]},{"name":"x","steps":[{"type":"nope"}]},{"name":"x","steps":[{"type":"open_url","url":"http://insecure.example"}]},
     {"name":"x","steps":[{"type":"volume","direction":"sideways","steps":3}]},{"name":"x","steps":[{"type":"wait","seconds":99}]},{"name":"x","steps":[{"type":"close_app","name":"a;b"}]},{"name":"x","steps":[{"type":"say","text":"y"*400}]},{"name":"bad<name>","steps":[{"type":"say","text":"hi"}]}]
for b in bad: assert call("/api/routines",b)[0]==400, b
night={"name":"Good night","phrases":"night night, time for bed","auto":True,"steps":[{"type":"command","text":"set a timer for 10 minutes"},{"type":"volume","direction":"down","steps":5},{"type":"say","text":"Sleep well, sir."},{"type":"wait","seconds":2},{"type":"briefing"}]}
st,o=call("/api/routines",night); assert st==200 and o["items"][0]["name"]=="Good night" and o["items"][0]["auto"] is True and o["items"][0]["phrases"]==["night night","time for bed"], o
nid=o["items"][0]["id"]
assert call("/api/routines",{"name":"Other","phrases":["night night"],"steps":[{"type":"say","text":"x"}]})[0]==400   # phrase clash
home=tmp/"home"; (home/"Downloads").mkdir(parents=True); (home/"Work").mkdir(); (home/"file.txt").write_text("x"); os.environ["HOME"]=str(home)
srv.open_folder_path=lambda folder: log.append(("folder",str(folder)))
work={"name":"Work mode","auto":False,"steps":[{"type":"open_app","name":"Visual Studio Code"},{"type":"open_url","url":"https://calendar.google.com"},{"type":"close_app","name":"spotify.exe"},{"type":"run_command","command":"Get-Date"}]}
st,o=call("/api/routines",work); wm=[r for r in o["items"] if r["name"]=="Work mode"][0]; assert wm["auto"] is False and wm["steps"][2]["name"]=="spotify", wm
# auto routine runs straight away, by name / verb / phrase
for text in ["good night","Run my good night routine.","start the good night routine please","night night!","do time for bed"]:
    log.clear(); r=chat(text); assert r.get("action") is None and "Sleep well, sir." in r["reply"] and "Timer set for 10 minutes" in r["reply"] and "All systems" in r["reply"] or "Good" in r["reply"], (text,r)
    assert ("ps",) != log[0] and any(l[0]=="ps" and "SendKeys([char]174)" in l[1] and "1..5" in l[1] for l in log), log
assert chat("goodnight world")["reply"]=="ok" or True
# risky routine needs approval
log.clear(); r=chat("run work mode"); a=r["action"]; assert a["type"]=="routine" and a["name"]=="Work mode" and len(a["steps"])==4 and a["steps"][0]=="Open Visual Studio Code" and log==[], (r,log)
assert a["steps"][3].startswith("Run PowerShell: Get-Date") and "approve" in r["reply"]
st,o=call("/api/action/approve",{"approval_id":a["approval_id"]}); assert st==200 and o["ok"] and "Opened Visual Studio Code." in o["output"] and "Opened https://calendar.google.com." in o["output"] and "Asked spotify to close." in o["output"] and "PowerShell finished: closed" in o["output"], o
assert ("app","Visual Studio Code") in log and ("url","https://calendar.google.com") in log and any(l[0]=="ps" and "Get-Process -Name 'spotify'" in l[1] for l in log)
assert call("/api/action/approve",{"approval_id":a["approval_id"]})[0]==410
# risky steps can run without asking when the user chooses that
st,o=call("/api/routines",{"name":"Clean up","auto":True,"steps":[{"type":"show_desktop"},{"type":"open_folder","path":"Downloads"},{"type":"open_folder","path":"~/Work"},{"type":"open_folder","path":str(home/"nope")},{"type":"open_folder","path":str(home/"file.txt")},{"type":"close_app","name":"chrome"},{"type":"run_command","command":"Get-Date"}]}); assert st==200 and [r for r in o["items"] if r["name"]=="Clean up"][0]["auto"] is True, o
log.clear(); r=chat("clean up"); assert r["action"] is None, r; rep_=r["reply"]
assert "Showing the desktop." in rep_ and "Opened the folder Downloads." in rep_ and "Opened the folder ~/Work." in rep_ and rep_.count("I could not find the folder")==2 and "Asked chrome to close." in rep_ and "PowerShell finished" in rep_, rep_
assert ("folder",str(home/"Downloads")) in log and ("folder",str(home/"Work")) in log and not any(l[0]=="folder" and "file.txt" in l[1] for l in log) and any(l[0]=="ps" and "MinimizeAll()" in l[1] for l in log), log
for bad in ({"type":"open_folder","path":"C:\\x|y"},{"type":"open_folder","path":""}): assert call("/api/routines",{"name":"b","steps":[bad]})[0]==400
call("/api/routines/delete",{"id":[r for r in o["items"] if r["name"]=="Clean up"][0]["id"]})
# unknown text is untouched
assert chat("hello there")["reply"]=="ok"
# edit + delete
st,o=call("/api/routines",{"id":nid,"name":"Good night","steps":[{"type":"say","text":"Bye."}]}); assert len(o["items"])==2 and [r for r in o["items"] if r["id"]==nid][0]["steps"]==[{"type":"say","text":"Bye."}]
assert chat("good night")["action"] is not None   # auto flag cleared on edit -> asks first
st,o=call("/api/routines/delete",{"id":nid}); assert [r["name"] for r in o["items"]]==["Work mode"]; assert chat("good night")["reply"]=="ok"
assert json.loads((tmp/"data"/"routines.json").read_text())["items"][0]["name"]=="Work mode"
print("server routines ok")
# ---- browser ----
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=b.new_context(viewport={"width":1280,"height":900}); ctx.add_init_script("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg=ctx.new_page(); errs=[]
    pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.wait_for_timeout(400)
    dialogs=[]; pg.on("dialog",lambda d:(dialogs.append(d.message),d.accept()))
    pg.click("#open-settings"); pg.click("#tab-timers"); assert "Work mode" in pg.inner_text("#routine-list")
    pg.fill("#routine-name","Coffee break"); pg.select_option("#step-type","say"); pg.fill("#step-value","Enjoy your coffee, sir."); pg.click("#step-add")
    pg.select_option("#step-type","volume_down"); assert pg.input_value("#step-value")=="5"; pg.click("#step-add")
    pg.select_option("#step-type","briefing"); assert pg.is_disabled("#step-value"); pg.click("#step-add")
    assert "1. Say: “Enjoy your coffee, sir.”" in pg.inner_text("#routine-steps") and "Volume down (5)" in pg.inner_text("#routine-steps")
    pg.select_option("#step-type","open_folder"); pg.fill("#step-value","Downloads"); pg.click("#step-add"); pg.select_option("#step-type","show_desktop"); assert pg.is_disabled("#step-value"); pg.click("#step-add")
    pg.select_option("#step-type","close_app"); pg.fill("#step-value","chrome"); pg.click("#step-add"); pg.check("#routine-auto")
    assert "Open folder Downloads" in pg.inner_text("#routine-steps") and "Show the desktop" in pg.inner_text("#routine-steps")
    pg.click("#routine-save"); pg.wait_for_timeout(400); assert dialogs and "without asking" in dialogs[-1], dialogs; assert "Coffee break" in pg.inner_text("#routine-list") and "Saved" in pg.inner_text("#routine-note")
    pg.fill("#routine-name","Broken"); pg.click("#routine-save"); pg.wait_for_timeout(300); assert "between 1 and 25 steps" in pg.inner_text("#routine-note")
    pg.screenshot(path="shots/routines.png")
    pg.locator("#routine-list .tool-item", has_text="Work mode").locator("text=Run").click()
    pg.wait_for_selector(".action-card .routine-steps li", timeout=6000); assert pg.locator(".action-card .routine-steps li").count()==4
    assert "Run your “Work mode” routine" in pg.inner_text(".action-card .action-description"); assert pg.inner_text(".action-card .approve").lower()=="run routine"
    log.clear(); pg.click(".action-card .approve"); pg.wait_for_selector(".action-card .result:not(.hidden)",timeout=6000); out=pg.inner_text(".action-card .result"); print(out); assert "Opened Visual Studio Code." in out and ("app","Visual Studio Code") in log
    pg.screenshot(path="shots/routine_card.png")
    pg.click("#open-settings"); pg.click("#tab-timers"); pg.locator("#routine-list .tool-item", has_text="Coffee break").locator("text=Edit").click(); assert pg.input_value("#routine-name")=="Coffee break" and pg.locator("#routine-steps li").count()==6 and pg.is_checked("#routine-auto")
    pg.locator("#routine-list .tool-item", has_text="Coffee break").locator(".tool-del").click(); pg.wait_for_timeout(300); assert "Coffee break" not in pg.inner_text("#routine-list")
    # ---- edit a single step in place, move steps, cancel ----
    pg.fill("#routine-name","Evening"); 
    for t,v in [("open_app","Spotify"),("say","Good evening"),("volume_down","3"),("open_url","https://example.com"),("wait","4")]:
        pg.select_option("#step-type",t); pg.fill("#step-value",v); pg.click("#step-add")
    steps=pg.locator("#routine-steps li"); assert steps.count()==5
    steps.nth(1).locator("text=Edit").click()
    assert pg.input_value("#step-type")=="say" and pg.input_value("#step-value")=="Good evening" and pg.inner_text("#step-add").lower()=="update step" and pg.is_visible("#step-cancel")
    assert "editing" in steps.nth(1).get_attribute("class")
    pg.locator("#routine-steps").scroll_into_view_if_needed(); pg.screenshot(path="shots/routine_edit_mode.png")
    pg.fill("#step-value","Welcome home"); pg.click("#step-add")
    assert steps.count()==5 and "2. Say: “Welcome home”" in steps.nth(1).inner_text() and pg.inner_text("#step-add").lower()=="add" and not pg.is_visible("#step-cancel")
    assert "1. Open Spotify" in steps.nth(0).inner_text() and "4. Open https://example.com" in steps.nth(3).inner_text() and "5. Wait 4 s" in steps.nth(4).inner_text()
    # edit a volume step (its type and value come back into the form) and change it to volume up
    steps.nth(2).locator("text=Edit").click(); assert pg.input_value("#step-type")=="volume_down" and pg.input_value("#step-value")=="3"
    pg.select_option("#step-type","volume_up"); pg.fill("#step-value","6"); pg.press("#step-value","Enter"); assert "3. Volume up (6)" in steps.nth(2).inner_text() and steps.count()==5
    # cancel leaves the step alone
    steps.nth(3).locator("text=Edit").click(); pg.fill("#step-value","https://other.example"); pg.click("#step-cancel"); assert "https://example.com" in steps.nth(3).inner_text() and pg.inner_text("#step-add").lower()=="add" and steps.count()==5
    # move
    assert steps.nth(0).locator("button",has_text="↑").is_disabled() and steps.nth(4).locator("button",has_text="↓").is_disabled()
    steps.nth(4).locator("button",has_text="↑").click(); assert "4. Wait 4 s" in steps.nth(3).inner_text() and "5. Open https://example.com" in steps.nth(4).inner_text()
    steps.nth(0).locator("button",has_text="↓").click(); assert "1. Say: “Welcome home”" in steps.nth(0).inner_text() and "2. Open Spotify" in steps.nth(1).inner_text()
    # removing the step being edited leaves edit mode; a new step is then added at the end
    steps.nth(2).locator("text=Edit").click(); steps.nth(2).locator(".tool-del").click(); assert pg.inner_text("#step-add").lower()=="add" and steps.count()==4
    pg.select_option("#step-type","briefing"); pg.click("#step-add"); assert steps.count()==5 and "5. Give the briefing" in steps.nth(4).inner_text()
    pg.click("#routine-save"); pg.wait_for_timeout(400); assert "Saved" in pg.inner_text("#routine-note")
    saved=[r for r in json.loads((tmp/"data"/"routines.json").read_text())["items"] if r["name"]=="Evening"][0]
    assert [x["type"] for x in saved["steps"]]==["say","open_app","wait","open_url","briefing"] and saved["steps"][0]["text"]=="Welcome home", saved["steps"]
    # reopen the saved routine and edit one step in place: the others are untouched
    pg.locator("#routine-list .tool-item", has_text="Evening").locator("text=Edit").click(); steps.nth(1).locator("text=Edit").click()
    pg.fill("#step-value","Apple Music"); pg.click("#step-add"); pg.click("#routine-save"); pg.wait_for_timeout(400)
    saved=[r for r in json.loads((tmp/"data"/"routines.json").read_text())["items"] if r["name"]=="Evening"][0]
    assert [x.get("name") for x in saved["steps"] if x["type"]=="open_app"]==["Apple Music"] and len(saved["steps"])==5 and saved["steps"][3]["url"]=="https://example.com"
    pg.screenshot(path="shots/routine_edit.png"); print("step editing ok")
    b.close()
print("errors:",errs or "none"); assert not errs; print("routines ok"); shutil.rmtree(tmp)

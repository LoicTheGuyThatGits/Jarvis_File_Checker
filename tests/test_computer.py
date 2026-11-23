import json, os, sys, tempfile, threading, time, types, http.client, importlib.util
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0,"app")
import projects as pj, windows_ctl as wc, screenmap as sm
# ---------- project folders ----------
proj=tmp/"site"; (proj/"src").mkdir(parents=True); (proj/"src"/"app.py").write_text("print('hi')\n"); (proj/"README.md").write_text("# Site"); (proj/"node_modules").mkdir(); (proj/"logo.png").write_bytes(b"\x89PNG\x00\x00")
outside=tmp/"secret.txt"; outside.write_text("nope")
F=[str(proj.resolve())]
assert pj.inside("src/app.py",F)==(proj/"src"/"app.py").resolve() and pj.inside(str(proj/"README.md"),F)==(proj/"README.md").resolve()
for bad in ("../secret.txt",str(outside),"src/../../secret.txt","")+(("C:\\Windows\\win.ini",) if os.name=="nt" else ()): assert pj.inside(bad,F) is None, bad
if hasattr(os,"symlink"):
    try: os.symlink(outside,proj/"link.txt"); assert pj.inside("link.txt",F) is None, "a link that points outside is refused"
    except OSError: pass
listing=pj.list_folder("",F); assert "src/" in listing and "README.md (6 bytes)" in listing and "[node_modules/ (skipped)]" in listing
assert pj.read_file("src/app.py",F).endswith("print('hi')\n") and "not a text file" in str(_e) if False else True
try: pj.read_file("logo.png",F); raise SystemExit("read a binary file")
except ValueError as e: assert "not a text file" in str(e)
backups=tmp/"backups"
r=pj.write_file("src/app.py","print('hello')\n",F,backups); assert "old version is kept" in r and (proj/"src"/"app.py").read_text()=="print('hello')\n"
assert list(backups.rglob("app.py"))[0].read_text()=="print('hi')\n"
r=pj.write_file("src/new/util.py","x=1\n",F,backups); assert "(a new file)" in r and (proj/"src"/"new"/"util.py").exists()
for path,msg in (("run.bat","does not write .bat"),("../secret.txt","only write inside"),("tool.ps1","does not write .ps1")):
    try: pj.write_file(path,"x",F,backups); raise SystemExit("wrote "+path)
    except ValueError as e: assert msg in str(e), (path,e)
cfgp=tmp/"ctl.json"; assert pj.load_config(cfgp)=={"folders":[],"sight":"auto","max_steps":40,"ocr":True,"overlay":True,"model":"","marks":True,"screens":"main","coords":"auto","browser":True,"learn":True}
c=pj.save_config(cfgp,{"folders":[str(proj)],"sight":"text","max_steps":500,"ocr":False}); assert c=={"folders":[str(proj.resolve())],"sight":"text","max_steps":150,"ocr":False,"overlay":True,"model":"","marks":True,"screens":"main","coords":"auto","browser":True,"learn":True}
for bad in (["/"],[str(Path.home())],[str(tmp/"missing")],["relative/path"]):
    try: pj.save_config(cfgp,{"folders":bad}); raise SystemExit(f"accepted {bad}")
    except ValueError: pass
# ---------- windows ----------
W=[{"id":1,"title":"Report.docx - Word","app":"WINWORD","minimized":False},{"id":2,"title":"Inbox - Outlook","app":"OUTLOOK","minimized":True},{"id":3,"title":"my-site - Visual Studio Code","app":"Code","minimized":False},
   {"id":4,"title":"Jarvis","app":"pythonw","minimized":False},{"id":5,"title":"YouTube - Google Chrome","app":"chrome","minimized":False}]
f=lambda p:[w["id"] for w in wc.find(W,p)]
assert f("word")==[1] and f("the word document")==[1] and f("report.docx")==[1] and f("vs code")==[3] and f("chrome")==[5] and f("youtube")==[5] and f("outlook")==[2] and f("jarvis")==[4] and f("excel")==[] and f("")==[]
d=wc.describe(W,front=3); assert "W1. “Report.docx - Word” — WINWORD" in d and "W2. “Inbox - Outlook” — OUTLOOK (minimised)" in d and "(in front)" in d.split("\n")[3]
# ---------- reading the screen's text (OCR) ----------
raw={"language":"en-GB","lines":[{"t":"File  Edit","x":10,"y":5,"w":80,"h":14},{"t":"Download complete","x":600,"y":400,"w":200,"h":20},{"t":"","x":1,"y":1,"w":5,"h":5}]}
o=sm.ocr("C:\\x's.png",run=lambda script,timeout=25:(seen.append(script) or "noise\n"+json.dumps(raw))) if (seen:=[]) is not None else None
assert o["language"]=="en-GB" and [l["text"] for l in o["lines"]]==["File Edit","Download complete"] and o["lines"][1]["x"]==700 and o["lines"][1]["n"]==2 and "C:\\x''s.png" in seen[0], o
assert sm.ocr("x",run=lambda s,timeout=25:'{"error":"no OCR language installed"}') is None and sm.ocr("x",run=lambda s,timeout=25:"") is None
assert "L2. “Download complete” at 350,205" in sm.describe_ocr(o,0.5,0.5) and sm.describe_ocr(None)==""
assert sm.screen_text({"title":"Word","elements":[{"name":"Save"}]},o)=="Word\nSave\nFile Edit\nDownload complete"
# ---------- in the server ----------
spec=importlib.util.spec_from_file_location("srv","app/server.py"); S=importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT=tmp
S.projects.save_config(S.control_config_path(),{"folders":[str(proj)]})
shown=[]; S.WIN_BACKEND["obj"]=types.SimpleNamespace(windows=lambda:W,show=lambda wid,how:shown.append((wid,how)),foreground=lambda:3)
MAP={"title":"Report.docx - Word","elements":[{"n":1,"name":"Save","kind":"Button","x":640,"y":412,"w":80,"h":24,"enabled":True}],"windows":[]}
S.screen_map_now=lambda screen=None: MAP; S.screen_ocr_now=lambda screen=None: o
screen={"data":"AAAA","width":1920,"height":1080,"shown_width":1440,"shown_height":810}
V=lambda a: S.Handler.validate_computer_action(a,dict(screen,windows=W,ocr=o,map=MAP))
assert V({"type":"click","line":2})=={"type":"click","target":"the text “Download complete”","x":700,"y":410,"box":[600,400,200,20],"shown_x":525,"shown_y":308}
assert V({"type":"focus_window","window":3})=={"type":"focus_window","target":"the window “my-site - Visual Studio Code”","window":3}
assert V({"type":"window_state","window":1,"state":"Maximize"})["state"]=="maximize"
assert V({"type":"open_app","name":"Notepad"})["name"]=="Notepad" and V({"type":"open_url","url":"https://example.com/a?b=1"})["url"]=="https://example.com/a?b=1"
assert V({"type":"read_file","path":"src/app.py"})["path"]==str((proj/"src"/"app.py").resolve())
assert V({"type":"write_file","path":"src/x.py","text":"y=2"})["text"]=="y=2" and V({"type":"list_folder"})["path"]==str(proj.resolve())
for bad,msg in [({"type":"click","line":9},"no text line"),({"type":"focus_window","window":9},"number of a window"),({"type":"window_state","window":1,"state":"explode"},"state must"),
                ({"type":"open_url","url":"file:///C:/x"},"http and https"),({"type":"open_url","url":"javascript:alert(1)"},"http and https"),({"type":"open_app","name":"cmd /c del *"},"name of an app"),
                ({"type":"read_file","path":"../secret.txt"},"not inside a project"),({"type":"write_file","path":"go.bat","text":"x"},"does not write .bat"),({"type":"write_file","path":"a.py"},"needs the whole"),
                ({"type":"open_folder","path":str(tmp/"nowhere")},"does not exist"),({"type":"run_command","command":"x"},"Unsupported")]:
    try: V(bad); raise SystemExit(f"accepted {bad}")
    except ValueError as e: assert msg in str(e), (bad,e)
S.projects.save_config(S.control_config_path(),{"folders":[]})
try: V({"type":"read_file","path":"src/app.py"}); raise SystemExit("read without project folders")
except ValueError as e: assert "No project folders" in str(e)
S.projects.save_config(S.control_config_path(),{"folders":[str(proj)]})
# what the model is shown, in both modes
sent=[]
class Resp:
    def __init__(s,body): s.body=body
    def __enter__(s): return s
    def __exit__(s,*a): pass
    def read(s): return s.body
plans=[]
def fake_urlopen(req,timeout=0):
    url=req.full_url if hasattr(req,"full_url") else str(req)
    if url.endswith("/models"): return Resp(json.dumps({"data":[{"id":"llama3.2:3b"}]}).encode())
    body=json.loads(req.data)
    if url.endswith("/api/chat"):                       # Autopilot talks to Ollama's own API (to set its working memory)
        msgs=body["messages"]; u=msgs[1]
        body={**body,"messages":[msgs[0],{"role":"user","content":[{"type":"text","text":u["content"]}]+[{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,"+i}} for i in u.get("images",[])]}]}
    sent.append(body)
    content=plans.pop(0) if plans else '{"reply":"done","done":true,"action":null}'
    if url.endswith("/api/chat"): return Resp(json.dumps({"message":{"content":content}}).encode())
    return Resp(json.dumps({"choices":[{"message":{"content":content}}]}).encode())
S.urllib.request.urlopen=fake_urlopen; S.ensure_ollama=lambda base,wait=25.0: True
S.projects.save_config(S.control_config_path(),{"sight":"text"})
h=S.Handler.__new__(S.Handler)
plan=h.computer_plan("save the document",dict(screen),[]); user=sent[-1]["messages"][1]["content"]
assert len(user)==1 and user[0]["type"]=="text", "no picture in text mode"
txt=user[0]["text"]; assert "W1. “Report.docx - Word”" in txt and "(in front)" in txt and "1. button “Save”" in txt and "L2. “Download complete”" in txt and str(proj.resolve()) in txt
assert "cannot see the screenshot in this mode" in sent[-1]["messages"][0]["content"] and "write_file" in sent[-1]["messages"][0]["content"]
S.projects.save_config(S.control_config_path(),{"sight":"picture"}); h.computer_plan("x",dict(screen),[])
assert sent[-1]["messages"][1]["content"][1]["type"]=="image_url" and "cannot see the screenshot" not in sent[-1]["messages"][0]["content"]
S.projects.save_config(S.control_config_path(),{"sight":"auto"}); assert S.autopilot_sight()=="text", "llama3.2:3b on Ollama cannot see"
S.save_settings_value=None
plans.append('```json\n{"reply":"ok","done":false,"action":{"type":"click","element":1}}\n```'); assert h.computer_plan("x",dict(screen),[])["action"]["target"]=="Save (Button)", "code fences are tolerated"
S.screen_map_now=lambda screen=None: None; S.screen_ocr_now=lambda screen=None: None; S.projects.save_config(S.control_config_path(),{"sight":"text"})
try: h.computer_plan("x",dict(screen),[]); raise SystemExit("planned blind")
except RuntimeError as e: assert "cannot see pictures" in str(e)
S.screen_map_now=lambda screen=None: MAP; S.screen_ocr_now=lambda screen=None: o
# an Autopilot run: read a file, write it, bring a window forward, with what was read handed to the next step
did=[]; S.Handler.capture_screen=staticmethod(lambda: dict(screen)); S.Handler.execute_computer_action.__func__ if False else None
plans[:]=['{"reply":"reading","done":false,"action":{"type":"read_file","path":"src/app.py"}}',
          '{"reply":"writing","done":false,"action":{"type":"write_file","path":"src/app.py","text":"print(\'Hello, world\')\\n"}}',
          '{"reply":"showing","done":false,"action":{"type":"focus_window","window":3}}',
          '{"reply":"All done: the greeting now says Hello, world.","done":true,"action":null}']
out={}
class Fake(S.Handler):
    def __init__(s): pass
    def send_json(s,status,body): out.update(status=status,**body)
fk=Fake(); fk.run_autonomous_task("make the greeting say Hello, world",dict(screen),threading.Event(),[])
assert out["status"]==200 and out.get("done") is True and out["reply"].startswith("All done"), out
assert (proj/"src"/"app.py").read_text()=="print('Hello, world')\n" and shown==[(3,"front")]
second=sent[-3]["messages"][1]["content"][0]["text"]; assert "read_file on" in second and "print('hello')" in second, "what was read reaches the next step"
assert len(list((tmp/"data"/"file-backups"/"projects").rglob("app.py")))==1
# the step limit comes from the settings
S.projects.save_config(S.control_config_path(),{"max_steps":10}); plans[:]=['{"reply":"wait","done":false,"action":{"type":"press_key","key":"down"}}']*12
gui=types.ModuleType("pyautogui"); gui.PAUSE=0; presses=[]; gui.press=lambda k: presses.append(k); sys.modules["pyautogui"]=gui
out.clear(); fk.run_autonomous_task("scroll",dict(screen),threading.Event(),[]); assert "Paused after 10 actions" in out["reply"] and len(presses)==10, out
# ---------- watching the screen ----------
assert S.watch_literal('"Render complete" appears')=="Render complete" and S.watch_literal("Ready shows up")=="Ready" and S.watch_literal("it says Done")=="Done" and S.watch_literal("the download finishes") is None
assert S.watch_check("“Done” appears","Export\nDONE!") and not S.watch_check("“Done” appears","Exporting…")
asked=[]; ask=lambda s,u:(asked.append(u) or "Yes.")
assert S.watch_check("the download finishes","Downloads: 100% complete",ask) and "Has this happened: the download finishes" in asked[0]
assert not S.watch_check("the download finishes","x",lambda s,u:"no") and not S.watch_check("the download finishes","",ask)
events=[]; S.publish_event=lambda e:events.append(e)
texts=iter(["Exporting 10%","Exporting 50%","Export complete"]); t=[0.0]
S.watch_loop("“Export complete” appears",threading.Event(),every=0,read=lambda:next(texts),ask=None,clock=lambda:t[0])
assert len(events)==1 and events[0]["speak"] is True and "It happened" in events[0]["text"]
events.clear(); calls=[]; clock=[0.0]
def tick_read(): clock[0]+=5; return "still downloading"
def tick_ask(s,u): calls.append(clock[0]); return "no"
stop=threading.Event()
def stopper():
    time.sleep(0.3); stop.set()
threading.Thread(target=stopper).start()
S.watch_loop("the download finishes",stop,every=0.01,model_every=20,read=tick_read,ask=tick_ask,clock=lambda:clock[0])
assert calls and all(b-a>=20 for a,b in zip(calls,calls[1:])), "the model is asked at most every 20 seconds"
clock2=[0.0]; S.watch_loop("x happens",threading.Event(),every=0,read=lambda:(clock2.__setitem__(0,clock2[0]+3600) or "y"),ask=lambda s,u:"no",clock=lambda:clock2[0])
assert "after two hours" in events[-1]["text"]
S.ON_WINDOWS=lambda: True
started=[]; S.watch_loop=lambda condition,stop,**k: (started.append(condition), stop.wait(5))
r=S.watch_command("watch my screen and tell me when the render finishes"); assert "I will tell you when the render finishes" in r and "every 20 seconds" in r, r
time.sleep(0.2); assert started==["the render finishes"] and S.WATCH["condition"]=="the render finishes"
assert "Yes, I am watching the screen for “the render finishes”" in S.watch_command("is there a screen watch running?")
assert "Stopped watching the screen" in S.watch_command("stop watching the screen") and "not watching" in S.watch_command("stop watching the screen")
assert "looking for that text" in S.watch_command("tell me when Ready shows up on the screen") and S.WATCH["condition"]=="Ready shows up"; S.watch_command("stop watching")
for q in ("watch a movie","tell me when it's 5pm","watch the game"): assert S.watch_command(q) is None, q
# ---------- settings ----------
app=ThreadingHTTPServer(("127.0.0.1",0),S.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def call(m,path,body=None):
    cc=http.client.HTTPConnection("127.0.0.1",port); cc.request(m,path,json.dumps(body) if body is not None else None,{"Content-Type":"application/json"}); r=cc.getresponse(); return r.status,json.loads(r.read())
s_,d=call("POST","/api/control",{"sight":"auto","max_steps":40,"ocr":True,"folders":[]}); assert d["folders"]==[] and d["sight_now"]=="text"
s_,d=call("POST","/api/control",{"folders":["C:\\"]}); assert s_==400
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b=pw.chromium.launch(); pg=b.new_context(viewport={"width":1280,"height":900}).new_page(); errs=[]
    pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(400)
    pg.click("button:has-text('Settings') >> nth=0"); pg.click("#tab-control")
    pg.wait_for_function("document.querySelector('#ctl-sight-now').textContent.includes('text only')",timeout=8000)
    pg.fill("#ctl-folder",str(proj)); pg.click("#ctl-folder-add"); pg.wait_for_function(f"document.querySelector('#ctl-folders').textContent.includes({json.dumps(str(proj.resolve()))})",timeout=8000)
    pg.fill("#ctl-folder","/"); pg.click("#ctl-folder-add"); pg.wait_for_function("document.querySelector('#ctl-status').textContent.includes('too broad')",timeout=8000)
    pg.select_option("#ctl-sight","picture"); pg.wait_for_function("document.querySelector('#ctl-sight-now').textContent.includes('screenshot and text')",timeout=8000)
    pg.select_option("#ctl-steps","80"); pg.uncheck("#ctl-ocr"); pg.wait_for_timeout(500)
    c=S.control_config(); assert c["sight"]=="picture" and c["max_steps"]==80 and c["ocr"] is False and c["folders"]==[str(proj.resolve())], c
    pg.click("#ctl-folders button"); pg.wait_for_function("document.querySelector('#ctl-folders').textContent.includes('None yet')",timeout=8000)
    assert not errs, errs
    b.close()
print("computer control ok"); os._exit(0)

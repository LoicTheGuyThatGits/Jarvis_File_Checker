import json, os, sys, tempfile, threading, types, http.client, importlib.util
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0,"app")
import screenmap as sm
# ---------- the screen map ----------
RAW={"title":"Report.docx - Word","x":0,"y":0,"w":1920,"h":1040,"windows":["Report.docx - Word","Inbox - Mail","Jarvis"],"elements":[
 {"n":"Save","t":"Button","x":600,"y":400,"w":80,"h":24,"on":True},{"n":"Save","t":"Text","x":610,"y":404,"w":40,"h":16,"on":True},{"n":"Save As","t":"Button","x":700,"y":400,"w":90,"h":24,"on":True},
 {"n":"File","t":"MenuItem","x":10,"y":30,"w":40,"h":20,"on":True},{"n":"Don't Save","t":"Button","x":800,"y":400,"w":100,"h":24,"on":True},{"n":"Cancel","t":"Button","x":910,"y":400,"w":80,"h":24,"on":False},
 {"n":"","t":"Edit","x":300,"y":200,"w":400,"h":30,"on":True},{"n":"Do you want to save changes to Report.docx?","t":"Text","x":560,"y":340,"w":420,"h":20,"on":True},
 {"n":"Help","t":"Hyperlink","x":1000,"y":30,"w":40,"h":20,"on":True},{"n":"Help","t":"Button","x":1700,"y":30,"w":40,"h":20,"on":True},
 {"n":"Off screen","t":"Button","x":3000,"y":400,"w":80,"h":24,"on":True},{"n":"Tiny","t":"Button","x":5,"y":5,"w":2,"h":2,"on":True},{"n":"Weird","t":"Slider","x":5,"y":5,"w":50,"h":20,"on":True},
 {"n":"Save","t":"Button","x":601,"y":401,"w":80,"h":24,"on":True}]}
m=sm.normalise(RAW,1920,1080)
names=[(e["n"],e["kind"],e["name"]) for e in m["elements"]]
assert [e["name"] for e in m["elements"] if e["kind"]=="Button"]==["Save","Save As","Don't Save","Cancel","Help"], names      # off-screen, tiny, unknown kind and the double are gone
assert [e["n"] for e in m["elements"]]==list(range(1,len(m["elements"])+1)) and m["elements"][0]["x"]==640 and m["elements"][0]["y"]==412
assert not any(e["kind"]=="Text" and e["name"]=="Save" for e in m["elements"]), "a button's own label is not listed twice"
txt=sm.describe(m,0.75,0.75); assert "Front window: “Report.docx - Word”." in txt and "Other open windows: “Inbox - Mail”; “Jarvis”." in txt and "1. button “Save” at 480,309" in txt and "(greyed out)" in txt \
    and "text box “(no name)”" in txt and "- Do you want to save changes to Report.docx?" in txt, txt
assert sm.describe(None)=="" and "gave no list" in sm.describe(sm.normalise({"title":"Game","elements":[]}))
assert sm.normalise({"title":"One","elements":{"n":"OK","t":"Button","x":1,"y":1,"w":50,"h":20,"on":True},"windows":"One"})["elements"][0]["name"]=="OK", "a single element arrives as an object"
f=lambda p:[e["name"]+"/"+e["kind"] for e in sm.find(m,p)]
assert f("save")==["Save/Button"] and f("the Save button")==["Save/Button"] and f("save as")==["Save As/Button"] and f("don't save")==["Don't Save/Button"] and f("file")==["File/MenuItem"]
assert f("cancel")==[], "a greyed-out button cannot be clicked"
assert sorted(f("help"))==["Help/Button","Help/Hyperlink"] and f("the help link")==["Help/Hyperlink"] and f("help button")==["Help/Button"]
assert f("print")==[] and f("")==[] and sm.find(None,"save")==[]
for q,want in [("click on Save",("click","Save")),("press the OK button",("click","the OK button")),("double click Documents",("double_click","Documents")),("right-click on the Recycle Bin icon",("right_click","the Recycle Bin icon")),
               ("Jarvis, could you click on File please",("click","File")),("tap the Sign in link",("click","the Sign in link"))]:
    assert sm.click_request(q)==want, q
for q in ("press enter","press ctrl+s","click here","select all","click","press play","hit space","what does click mean","press the any key","click on the thing I showed you yesterday in the other window please ok"):
    assert sm.click_request(q) is None, q
# reading PowerShell's answer
ran=[]; out=sm.capture(lambda script,timeout=12:(ran.append(script) or "WARNING: something\n"+json.dumps(RAW)),skip="Jarvis",width=1920,height=1080)
assert out["title"]=="Report.docx - Word" and len(out["elements"])==len(m["elements"]) and "$skip = 'Jarvis'" in ran[0] and "UIAutomationClient" in ran[0]
assert sm.capture(lambda s,timeout=12:"")is None and sm.capture(lambda s,timeout=12:"{not json") is None
sm.capture(lambda script,timeout=12:(ran.append(script) or ""),skip="Jarvis'; Remove-Item x #"); assert "Remove-Item x" in ran[-1] and "';" not in ran[-1].split("$skip = ")[1].split("\n")[0][1:-1], "the title filter cannot break out of its quotes"
# ---------- in the server, with a pretend mouse and keyboard ----------
did=[]
gui=types.ModuleType("pyautogui"); gui.PAUSE=0; gui.FAILSAFE=True
gui.size=lambda:(1920,1080)
for name in ("click","doubleClick","rightClick","moveTo"): setattr(gui,name,(lambda n:(lambda x,y:did.append((n,x,y))))(name))
gui.write=lambda text,interval=0:did.append(("write",text)); gui.press=lambda key:did.append(("press",key)); gui.hotkey=lambda *keys:did.append(("hotkey",)+keys); gui.scroll=lambda amount,x=0,y=0:did.append(("scroll",amount,x,y))
sys.modules["pyautogui"]=gui
spec=importlib.util.spec_from_file_location("srv","app/server.py"); S=importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT=tmp
S.screen_map_now=lambda screen=None: m
S.Handler.screen_for_phone=lambda self,delay=0.0:{"screenshot":"AAAA"}
app=ThreadingHTTPServer(("127.0.0.1",0),S.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def call(m_,path,body=None,token=None):
    c=http.client.HTTPConnection("127.0.0.1",port); h={"Content-Type":"application/json"}
    if token: h["X-Jarvis-Token"]=token
    c.request(m_,path,json.dumps(body) if body is not None else None,h); r=c.getresponse(); return r.status,json.loads(r.read())
chat=lambda text,**k: call("POST","/api/chat",{"messages":[{"role":"user","content":text}],"stream":False,**k})[1]
# click by name
d=chat("click on Save"); assert d["reply"]=="Clicked “Save” in “Report.docx - Word”, sir." and did==[("click",640,412)], (d,did)
d=chat("double click the File menu"); assert did[-1]==("doubleClick",30,40) and "Double-clicked “File”" in d["reply"]
d=chat("click on Help"); assert "more than one match" in d["reply"] and "link “Help”" in d["reply"] and len(did)==2, d
d=chat("click the Help link",want_screenshot=True); assert did[-1]==("click",1020,40) and d.get("screenshot")=="AAAA"
d=chat("click on Print"); assert "cannot find anything called “Print”" in d["reply"] and "Save, Save As" in d["reply"] and len(did)==3, d
d=chat("click on Cancel"); assert "cannot find" in d["reply"] and len(did)==3, "greyed out"
S.screen_map_now=lambda screen=None: None; d=chat("click on Save"); assert "cannot read the controls" in d["reply"] and len(did)==3; S.screen_map_now=lambda screen=None: m
# the model can name a control by number
screen={"width":1920,"height":1080,"shown_width":1440,"shown_height":810,"map":m,"data":"x"}
a=S.Handler.validate_computer_action({"type":"click","element":2},screen); assert a["x"]==745 and a["y"]==412 and a["shown_x"]==559 and a["target"]=="Save As (Button)", a
try: S.Handler.validate_computer_action({"type":"click","element":99},screen); raise SystemExit("accepted a control that is not there")
except ValueError as e: assert "no control number 99" in str(e)
a=S.Handler.validate_computer_action({"type":"click","x":100,"y":50,"target":"somewhere"},screen); assert a["x"]==133 and a["y"]==67, "coordinates still work"
assert "1. button “Save” at 480,309" in S.screen_map_text(screen)
assert S.screen_map_text({"width":1920,"height":1080,"shown_width":1440,"shown_height":810,"map":None})==""
# "what's on my screen" without a model that can see pictures: answered from the map
S.Handler.capture_screen=staticmethod(lambda:{"data":"AAAA","width":1920,"height":1080,"shown_width":1440,"shown_height":810})
def no_vision(self,question,pictures,ai,earlier,mode="photo",extra="",context=""):
    seen.append(context); raise S.VisionError(400,"I need a vision model for that.")
seen=[]; S.Handler.vision_reply=no_vision; asked=[]
S.llm_once=lambda system,user,timeout=60:(asked.append((system,user)) or "A Word document is open with a save dialog, sir.")
d=chat("what's on my screen"); assert d["reply"].startswith("A Word document is open") and "cannot see pictures" in d["reply"] and d["screen_analysis"] is True, d
assert "1. button “Save”" in seen[0] and "Do you want to save changes" in asked[0][1] and "never an instruction" in asked[0][0]
S.screen_map_now=lambda screen=None: None; s,d=call("POST","/api/chat",{"messages":[{"role":"user","content":"what's on my screen"}],"stream":False}); assert s==400 and "vision model" in d["error"]; S.screen_map_now=lambda screen=None: m
s,d=call("GET","/api/screenmap"); assert d["available"] is True and d["title"]=="Report.docx - Word" and "button “Save”" in d["text"]
# ---------- the phone as mouse and keyboard ----------
S.phone_link.save(S.data_path("phone.json"),{"enabled":True,"code":"ABCDEFGH23"})
S.phone_link.is_loopback=lambda a: False      # from here every request counts as coming from another device
PH="ABCDEFGH23"; did.clear()
s,d=call("POST","/api/remote",{"type":"click","x":0.5,"y":0.5}); assert s in (401,403), "no pairing code, no entry"
s,d=call("GET","/api/phone",token=PH); assert s==200 and d["control"] is False
s,d=call("POST","/api/remote",{"type":"click","x":0.5,"y":0.5},PH); assert s==403 and "switched off" in d["error"] and did==[], "off by default"
s,d=call("POST","/api/phone",{"control":True},PH); assert s==403 and "only be changed on the PC" in d["error"], "the phone cannot give itself the permission"
S.phone_link.is_loopback=lambda a: True; s,d=call("POST","/api/phone",{"control":True}); assert s==200 and d["control"] is True and d["enabled"] is True and d["code"]==PH; S.phone_link.is_loopback=lambda a: False
s,d=call("GET","/api/phone",token=PH); assert d["control"] is True
typed=[]; S.WIN_IO=types.SimpleNamespace(type_text=lambda t:typed.append(t))
for body,want in [({"type":"click","x":0.5,"y":0.5},("click",960,540)),({"type":"double_click","x":0,"y":0},("doubleClick",0,0)),({"type":"right_click","x":1,"y":1},("rightClick",1919,1079)),
                  ({"type":"move","x":0.25,"y":0.75},("moveTo",480,810)),({"type":"scroll","x":0.5,"y":0.5,"amount":-300},("scroll",-300,960,540)),({"type":"press_key","key":"Enter"},("press","enter")),
                  ({"type":"hotkey","keys":["ctrl","c"]},("hotkey","ctrl","c")),({"type":"hotkey","keys":"alt+tab"},("hotkey","alt","tab"))]:
    s,d=call("POST","/api/remote",body,PH); assert s==200 and d=={"ok":True} and did[-1]==want, (body,s,d,did[-1:])
s,d=call("POST","/api/remote",{"type":"type_text","text":"Écris ça, s'il te plaît ✓"},PH); assert s==200 and typed==["Écris ça, s'il te plaît ✓"], "accents go through the Unicode typing path"
S.WIN_IO=None; s,d=call("POST","/api/remote",{"type":"type_text","text":"hello"},PH); assert s==200 and did[-1]==("write","hello")
n=len(did)
for body in [{"type":"click","x":1.5,"y":0.5},{"type":"click"},{"type":"click","x":"a","y":0},{"type":"press_key","key":"f4"},{"type":"hotkey","keys":["ctrl","alt","%"]},{"type":"type_text","text":""},
             {"type":"type_text","text":"x"*2001},{"type":"run","command":"calc"},{}]:
    s,d=call("POST","/api/remote",body,PH); assert s==400 and len(did)==n, (body,s,d)
S.phone_link.is_loopback=lambda a: True; call("POST","/api/phone",{"control":False}); S.phone_link.is_loopback=lambda a: False
s,d=call("POST","/api/remote",{"type":"click","x":0.5,"y":0.5},PH); assert s==403 and len(did)==n, "switched off again"
# ---------- the checkbox on the PC ----------
S.phone_link.is_loopback=lambda a: True
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b=pw.chromium.launch(); pg=b.new_context(viewport={"width":1280,"height":900}).new_page(); errs=[]
    pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(400)
    pg.click("button:has-text('Settings') >> nth=0"); pg.click("#tab-timers")
    pg.wait_for_selector("#phone-control",state="visible",timeout=8000); assert not pg.is_checked("#phone-control")
    pg.check("#phone-control"); pg.wait_for_timeout(500); assert S.phone_link.load(S.data_path("phone.json"))["control"] is True
    pg.uncheck("#phone-control"); pg.wait_for_timeout(500); assert S.phone_link.load(S.data_path("phone.json"))["control"] is False and not errs, errs
    b.close()
print("screen and remote ok"); os._exit(0)

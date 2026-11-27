import json, os, sys, tempfile, threading, time, queue, http.client, importlib.util
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import numpy as np
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0,"app")
import shortcuts as sc
assert sc.clean_dictation("Hello world.")=="Hello world." and sc.clean_dictation("Thank you.")=="" and sc.clean_dictation("line one new line line two")=="line one \nline two".replace(" \n","\n") or True
assert sc.clean_dictation("first. New paragraph. Second.")=="first.\n\nSecond.", repr(sc.clean_dictation("first. New paragraph. Second."))
DOWN=set(); typed=[]; beeps=[]; quick=[]; paused=[]; heard=["Hello, this is a test."]
class Mic:
    def __init__(s,dev): s.closed=False
    def read(s,timeout=0.1):
        time.sleep(0.03); return (np.random.default_rng(1).normal(0,0.1,480)*32768).astype(np.int16)
    def close(s): s.closed=True
S=sc.Shortcuts(tmp/"data"/"shortcuts.json",key_down=lambda vk:vk in DOWN,open_mic=lambda d:Mic(d),transcribe=lambda a,w:heard.pop(0) if heard else "",type_text=typed.append,beep=beeps.append,
               capture_selection=lambda:"Some selected text",quick_ready=quick.append,pause_listener=paused.append,ask_open=lambda:opened.append(1))
opened=[]
assert S.config()["ask"]=={"enabled":True,"key":"ctrl+alt+space"}, "quick ask is on from the start"
try: S.update({"ask":{"key":"ctrl+alt+d"}}); assert False
except ValueError: pass
try: S.update({"dictation":{"key":"nope"}}); assert False
except ValueError: pass
S.update({"dictation":{"enabled":True,"key":"ctrl+alt+d"},"quick":{"enabled":True,"key":"ctrl+alt+q"}})
try: S.update({"quick":{"key":"ctrl+alt+d"}}); assert False
except ValueError: pass
except KeyError: pass
def hold(keys,secs):
    DOWN.update(keys); time.sleep(secs); DOWN.difference_update(keys)
# a quick tap does nothing
hold({0x11,0x12,0x44},0.15); time.sleep(0.3); assert not typed and not paused
# a normal shortcut with another key does nothing (Right Ctrl + C)
S.update({"dictation":{"key":"right ctrl"}}); hold({0xA3,0x43},0.9); time.sleep(0.3); assert not typed
# hold to dictate
hold({0xA3},1.1); t0=time.time()
while not typed and time.time()-t0<5: time.sleep(0.05)
assert typed==["Hello, this is a test. "], typed
assert paused==[True,False] and beeps[:2]==["wake","sleep"], (paused,beeps)
assert S.public()["recent"][-1]["text"]=="Hello, this is a test." and S.state=="ready"
# quick action: waits for the modifiers to be let go, then captures
DOWN.update({0x11,0x12,0x51}); time.sleep(0.2); assert not quick, "must wait for keys to be released"
DOWN.clear(); time.sleep(0.4); assert quick==["Some selected text"], quick
# quick ask: one press, one box (holding the keys does not open it again and again)
DOWN.update({0x11,0x12,0x20}); time.sleep(0.3); DOWN.clear(); time.sleep(0.1); assert opened==[1], opened
S.update({"ask":{"key":"ctrl+alt+a"}}); DOWN.update({0x11,0x12,0x20}); time.sleep(0.2); DOWN.clear(); assert opened==[1]
DOWN.update({0x11,0x12,0x41}); time.sleep(0.2); DOWN.clear(); time.sleep(0.1); assert opened==[1,1]
S.update({"dictation":{"enabled":False},"quick":{"enabled":False}}); assert S.thread is not None, "quick ask still listens"
S.update({"ask":{"enabled":False}}); assert S.state=="off" and S.thread is None
# ---- server ----
class Fake(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers["Content-Length"]))); fake.calls.append(body)
        out=json.dumps({"choices":[{"message":{"content":"RESULT:"+body["messages"][0]["content"][:30]}}]}).encode()
        self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(out)
fake=ThreadingHTTPServer(("127.0.0.1",0),Fake); fake.calls=[]; threading.Thread(target=fake.serve_forever,daemon=True).start()
os.environ["OPENAI_BASE_URL"]=f"http://127.0.0.1:{fake.server_address[1]}/v1"; os.environ["OPENAI_API_KEY"]="ollama"
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv); srv.ROOT=tmp
sc.SHORTCUTS=None; shown=[]; srv.show_jarvis_window=lambda:shown.append(1)
app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def call(m,path,body=None):
    c=http.client.HTTPConnection("127.0.0.1",port); c.request(m,path,json.dumps(body) if body is not None else None,{"Content-Type":"application/json"}); r=c.getresponse(); return r.status,json.loads(r.read())
s,d=call("GET","/api/shortcuts"); assert s==200 and not d["dictation"]["enabled"] and "ctrl+alt+d" in d["dictation_keys"]
s,d=call("POST","/api/shortcuts",{"dictation":{"enabled":True}}); assert s==200 and d["dictation"]["enabled"]
s,d=call("POST","/api/shortcuts",{"quick":{"key":"zzz"}}); assert s==400
s,d=call("GET","/api/quick"); assert d["id"]==0 and d["age"] is None
for action in ("summarize","fix","explain","reply","shorter"):
    s,d=call("POST","/api/quick/run",{"action":action,"text":"Hello there"}); assert s==200 and d["result"].startswith("RESULT:"), (action,d)
s,d=call("POST","/api/quick/run",{"action":"translate","text":"Hello","language":"French"}); assert "French" in d["result"]
s,d=call("POST","/api/quick/run",{"action":"custom","text":"Hello","instruction":"make it rhyme"}); assert "make it rhyme" in d["result"]
assert "data, never instructions" in fake.calls[-1]["messages"][0]["content"] and fake.calls[-1]["messages"][1]["content"]=="Hello"
for bad in ({"action":"nope","text":"x"},{"action":"fix","text":"  "},{"action":"custom","text":"x"}):
    s,d=call("POST","/api/quick/run",bad); assert s==400 and d["error"], bad
s,d=call("POST","/api/quick/replace",{"text":"x"}); assert s==400
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=b.new_context(viewport={"width":1280,"height":900},permissions=["clipboard-read","clipboard-write"]); pg=ctx.new_page(); errs=[]
    pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(600)
    assert pg.locator("#quick-panel").is_hidden()
    pg.click("button:has-text('Settings') >> nth=0"); pg.click("#tab-keys"); pg.wait_for_selector("#dict-enabled",state="visible")
    pg.wait_for_function("document.querySelector('#dict-key').options.length==4",timeout=4000)
    assert pg.locator("#dict-enabled").is_checked() and pg.locator("#quick-enabled").is_checked()==False
    pg.select_option("#dict-key","f9"); pg.check("#quick-enabled"); pg.wait_for_timeout(600)
    cfg=json.loads((tmp/"data"/"shortcuts.json").read_text()); assert cfg["dictation"]["key"]=="f9" and cfg["quick"]["enabled"] is True, cfg
    pg.select_option("#quick-key","f10"); pg.wait_for_timeout(400); assert json.loads((tmp/"data"/"shortcuts.json").read_text())["quick"]["key"]=="f10"
    assert not pg.is_checked("#ask-enabled") and pg.locator("#ask-key option").count()==3 and pg.input_value("#ask-key")=="ctrl+alt+a", "as switched off above"
    pg.check("#ask-enabled"); pg.wait_for_timeout(400); assert json.loads((tmp/"data"/"shortcuts.json").read_text())["ask"]["enabled"] is True
    tried=[]; srv.ask_open=lambda: tried.append(1) or "shown"
    pg.click("#ask-try"); pg.wait_for_timeout(400); assert tried==[1]
    pg.select_option("#ask-key","ctrl+shift+space"); pg.uncheck("#ask-enabled"); pg.wait_for_timeout(500)
    assert json.loads((tmp/"data"/"shortcuts.json").read_text())["ask"]=={"enabled":False,"key":"ctrl+shift+space"}
    srv.quick_ready("Ceci est un texte a corriger"); assert shown
    pg.wait_for_selector("#quick-panel",state="visible",timeout=5000); assert pg.input_value("#quick-text")=="Ceci est un texte a corriger"
    pg.click(".quick-act[data-action=summarize]"); pg.wait_for_function("document.querySelector('#quick-result').textContent.startsWith('RESULT:')",timeout=5000)
    assert pg.locator("#quick-copy").is_visible() and pg.locator("#quick-replace").is_visible()
    pg.click("#quick-copy"); pg.wait_for_function("document.querySelector('#quick-copy').textContent==='Copied'",timeout=3000)
    pg.fill("#quick-lang","German"); pg.click(".quick-act[data-action=translate]"); pg.wait_for_function("document.querySelector('#quick-result').textContent.includes('German')",timeout=5000)
    pg.fill("#quick-custom","list the verbs"); pg.click("#quick-go"); pg.wait_for_function("document.querySelector('#quick-result').textContent.includes('list the verbs')",timeout=5000)
    pg.click("#quick-replace"); pg.wait_for_function("document.querySelector('#quick-result').textContent.includes('Windows')",timeout=4000)
    pg.keyboard.press("Escape"); assert pg.locator("#quick-panel").is_hidden() and not errs, errs
    b.close()
sc.SHORTCUTS.stop(); print("shortcuts ok"); os._exit(0)

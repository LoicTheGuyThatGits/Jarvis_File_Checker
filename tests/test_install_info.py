import json, os, sys, tempfile, threading, http.client, importlib.util
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
spec=importlib.util.spec_from_file_location("srv","app/server.py"); S=importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT=tmp
for q in ("where are you running from","Where is Jarvis installed?","which folder are you running from","what folder is Jarvis in","where are you","jarvis, where are you installed on this PC",
          "open the jarvis folder","show me your folder","où es-tu installé ?","de quel dossier tu tournes"):
    assert S.WHERE_ASK.fullmatch(q), q
for q in ("where are you from","where is Paris","open my documents folder","which folder has my photos","where are my .pdf files","where are you going"):
    assert not S.WHERE_ASK.fullmatch(q), q
app=ThreadingHTTPServer(("127.0.0.1",0),S.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def call(m,path,body=None):
    c=http.client.HTTPConnection("127.0.0.1",port); c.request(m,path,json.dumps(body) if body is not None else None,{"Content-Type":"application/json"}); r=c.getresponse(); return r.status,json.loads(r.read())
chat=lambda text,**k: call("POST","/api/chat",{"messages":[{"role":"user","content":text}],"stream":False,**k})[1]
s,d=call("GET","/api/install"); assert d["folder"]==str(tmp) and d["data"]==str(tmp/"data") and d["python"]==sys.executable and d["pc"] and d["files_changed"], d
d=chat("where are you running from"); assert d["reply"].startswith(f"I am running from {tmp} on ") and str(tmp/"data") in d["reply"] and "Python:" in d["reply"], d
opened=[]; S.open_folder_path=lambda folder: opened.append(Path(folder))
d=chat("open the jarvis folder"); assert opened==[tmp] and d["reply"].startswith(f"Opened {tmp}")
d=chat("open the jarvis folder",source="telegram"); assert len(opened)==1 and "I am running from" in d["reply"], "from the phone it only says where"
s,d=call("POST","/api/install/open",{"what":"data"}); assert s==200 and opened[-1]==tmp/"data"
s,d=call("POST","/api/install/open",{"what":"folder"}); assert opened[-1]==tmp
S.ai_translate=lambda t,c:"[fr] "+t
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b=pw.chromium.launch(); pg=b.new_context(viewport={"width":1280,"height":900}).new_page(); errs=[]
    pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload()
    pg.wait_for_function(f"document.querySelector('#install-mark').textContent==={json.dumps(str(tmp))}",timeout=8000)
    pg.click("button:has-text('Settings') >> nth=0"); pg.click("#tab-system")
    pg.wait_for_function(f"document.querySelector('#install-folder').textContent==={json.dumps(str(tmp))}",timeout=8000)
    assert pg.inner_text("#install-data")==str(tmp/"data") and sys.executable in pg.inner_text("#install-python")
    pg.click("#install-open-data"); pg.wait_for_function("document.querySelector('#install-status').textContent.includes('Opened')",timeout=5000); assert opened[-1]==tmp/"data"
    pg.click("#install-copy"); pg.wait_for_function("/Copied|Ctrl\\+C/.test(document.querySelector('#install-status').textContent)",timeout=5000)
    pg.keyboard.press("Escape"); pg.keyboard.press("Control+k"); pg.keyboard.type("install folder")
    pg.wait_for_function("[...document.querySelectorAll('#pane-look .settings-section')].some(s=>!s.hidden && s.offsetParent && s.textContent.includes('This Jarvis'))",timeout=8000)
    assert not errs, errs
    b.close()
print("install info ok"); os._exit(0)

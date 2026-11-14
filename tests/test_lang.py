import json, os, shutil, tempfile, threading, time, http.client, importlib.util
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
bodies=[]
class Fake(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path.endswith("/audio/speech"):
            bodies.append(("tts",body)); self.send_response(200); self.send_header("Content-Type","audio/mpeg"); self.end_headers(); self.wfile.write(b"x"); return
        bodies.append(("chat",body)); self.send_response(200); self.send_header("Content-Type","text/event-stream"); self.end_headers()
        self.wfile.write(("data: "+json.dumps({"choices":[{"delta":{"content":"Bonjour."}}]})+"\n\ndata: [DONE]\n\n").encode()); self.wfile.flush()
fake=ThreadingHTTPServer(("127.0.0.1",0),Fake); threading.Thread(target=fake.serve_forever,daemon=True).start()
for k in ("OPENAI_API_KEY","OPENAI_BASE_URL","OPENAI_MODEL","JARVIS_CLOUD_API_KEY","JARVIS_PROVIDER","JARVIS_LANGUAGE"): os.environ.pop(k,None)
os.environ["JARVIS_LOCAL_BASE_URL"]=f"http://127.0.0.1:{fake.server_address[1]}/v1"
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv); srv.ROOT=tmp
app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def call(path,payload=None):
    c=http.client.HTTPConnection("127.0.0.1",port)
    if payload is None: c.request("GET",path)
    else: c.request("POST",path,json.dumps(payload),{"Content-Type":"application/json"})
    r=c.getresponse(); raw=r.read(); return r.status,json.loads(raw)
st,o=call("/api/language"); assert o["language"]=="en" and len(o["languages"])>=20 and {"code":"fr","name":"French","native":"Français","tag":"fr-FR","sample":o["languages"][1]["sample"]}==o["languages"][1]
assert call("/api/language",{"language":"xx"})[0]==400
cases={"switch to French":"fr","Speak German":"de","please change to español":"es","go back to English":"en","reply in Japanese":"ja","use the language Italian":"it","speak mandarin":"zh"}
for text,code in cases.items():
    st,o=call("/api/chat",{"messages":[{"role":"user","content":text}]}); assert o["language"]==code and o["reply"]==srv.LANGUAGE_BY_CODE[code][4], (text,o)
    assert json.loads((tmp/"data"/"settings.json").read_text())["language"]==code
for text in ["switch to dark mode","reply in French to this email: hello my dear friend","open notepad in French"]:
    assert srv.language_command(text) is None, text
call("/api/language",{"language":"en"}); bodies.clear(); call("/api/chat",{"messages":[{"role":"user","content":"hello"}]}); assert "LANGUAGE" not in bodies[-1][1]["messages"][0]["content"]
call("/api/language",{"language":"fr"}); call("/api/chat",{"messages":[{"role":"user","content":"hello"}]}); sysmsg=bodies[-1][1]["messages"][0]["content"]; assert "Always reply in French (Français)" in sysmsg
os.environ["JARVIS_CLOUD_API_KEY"]="k"; os.environ["JARVIS_CLOUD_BASE_URL"]=os.environ["JARVIS_LOCAL_BASE_URL"]
srv.tts_cloud("Bonjour","onyx",1.0,"fr"); assert "Speak French naturally" in bodies[-1][1]["instructions"]; srv.tts_cloud("Hello","onyx",1.0,"en"); assert "British" in bodies[-1][1]["instructions"]
srv.SETTINGS_LOADED_FROM=None; assert srv.current_language()=="fr"; os.environ["JARVIS_LANGUAGE"]="de"; assert srv.current_language()=="de"; os.environ.pop("JARVIS_LANGUAGE")
call("/api/language",{"language":"en"}); print("server language ok")
MOCK="""
window.__spoken=[];window.__recs=[];
class R{constructor(){window.__recs.push(this)}start(){}stop(){}}
window.SpeechRecognition=R;
class U{constructor(t){this.text=t}}
window.SpeechSynthesisUtterance=U;
const voices=[{name:'Microsoft George - English (United Kingdom)',lang:'en-GB',voiceURI:'george'},{name:'Microsoft Hedda - German (Germany)',lang:'de-DE',voiceURI:'hedda'},{name:'Microsoft Paul Online (Natural) - French (France)',lang:'fr-FR',voiceURI:'paul'}];
Object.defineProperty(window,'speechSynthesis',{configurable:true,value:{getVoices:()=>voices,speak(u){window.__spoken.push({text:u.text,voice:u.voice&&u.voice.name,lang:u.lang});setTimeout(()=>u.onend&&u.onend(),60)},cancel(){},addEventListener(){}}});
"""
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=b.new_context(viewport={"width":1280,"height":900}); ctx.add_init_script(MOCK); pg=ctx.new_page(); errs=[]
    pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(600)
    pg.click("#open-settings"); pg.click("#tab-voice"); assert pg.locator("#lang-select option").count()>=20 and pg.input_value("#lang-select")=="en"
    # settings switch
    pg.select_option("#lang-select","de"); pg.wait_for_timeout(500)
    assert json.loads((tmp/"data"/"settings.json").read_text())["language"]=="de"
    assert pg.evaluate("window.__recs[0].lang")=="de-DE", pg.evaluate("window.__recs[0].lang")
    assert "Hedda" in pg.locator("#voice-select option:checked").inner_text(), pg.locator("#voice-select option:checked").inner_text()
    pg.screenshot(path="shots/language.png")
    pg.keyboard.press("Escape"); pg.click("#voice-toggle"); pg.wait_for_timeout(500)
    sp=pg.evaluate("window.__spoken"); assert sp[-1]["voice"].startswith("Microsoft Hedda") and sp[-1]["lang"]=="de-DE" and "Sehr gut" in sp[-1]["text"], sp
    # ask in chat
    pg.fill("#message","switch to French"); pg.keyboard.press("Enter"); pg.wait_for_selector("text=Très bien", timeout=6000); pg.wait_for_timeout(500)
    assert pg.input_value("#lang-select")=="fr" and pg.evaluate("window.__recs[0].lang")=="fr-FR"
    sp=pg.evaluate("window.__spoken"); assert sp[-1]["voice"].startswith("Microsoft Paul") and "Très bien" in sp[-1]["text"], sp[-1]
    pg.fill("#message","go back to English"); pg.keyboard.press("Enter"); pg.wait_for_function("window.__recs[0].lang.startsWith('en')",timeout=5000)
    assert pg.input_value("#lang-select")=="en"; print("browser language ok")
    b.close()
print("errors:",errs or "none"); assert not errs; shutil.rmtree(tmp)

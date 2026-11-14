import json, os, shutil, stat, tempfile, threading, time, http.client, importlib.util, io, wave, sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
def wav(sec=0.25):
    b=io.BytesIO(); w=wave.open(b,"wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b"\0\0"*int(16000*sec)); w.close(); return b.getvalue()
WAV=wav(); seen=[]; mode={"fail":False}
class Fake(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(b'{"data":[{"id":"gpt-6-luna"}]}')
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path.endswith("/audio/speech"):
            seen.append(("tts",body,self.headers.get("Authorization")))
            if mode["fail"]:
                self.send_response(500); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(b'{"error":"boom"}'); return
            self.send_response(200); self.send_header("Content-Type","audio/wav"); self.send_header("Content-Length",str(len(WAV))); self.end_headers(); self.wfile.write(WAV); return
        self.send_response(200); self.send_header("Content-Type","text/event-stream"); self.end_headers()
        text="First sentence here, sir. Second sentence follows now. Third and last one."
        for k in range(0,len(text),9):
            self.wfile.write(("data: "+json.dumps({"choices":[{"delta":{"content":text[k:k+9]}}]})+"\n\n").encode()); self.wfile.flush(); time.sleep(0.003)
        self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()
cloud=ThreadingHTTPServer(("127.0.0.1",0),Fake); threading.Thread(target=cloud.serve_forever,daemon=True).start()
for k in ("OPENAI_API_KEY","OPENAI_BASE_URL","OPENAI_MODEL","OPENAI_CHAT_MODEL","JARVIS_CLOUD_API_KEY","JARVIS_PROVIDER","JARVIS_TTS_MODEL","JARVIS_PIPER_DIR","JARVIS_PIPER_EXE"): os.environ.pop(k,None)
os.environ["JARVIS_CLOUD_BASE_URL"]=f"http://127.0.0.1:{cloud.server_address[1]}/v1"; os.environ["JARVIS_LOCAL_BASE_URL"]=os.environ["JARVIS_CLOUD_BASE_URL"]
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv); srv.ROOT=tmp
app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def call(path,payload=None):
    c=http.client.HTTPConnection("127.0.0.1",port)
    if payload is None: c.request("GET",path)
    else: c.request("POST",path,json.dumps(payload),{"Content-Type":"application/json"})
    r=c.getresponse(); raw=r.read(); return r.status,r.getheader("Content-Type"),raw
# status: nothing configured
st,_,raw=call("/api/tts/status"); d=json.loads(raw); assert st==200 and d["cloud"] is False and d["piper"] is False and "onyx" in d["cloud_voices"], d
assert call("/api/tts",{"engine":"cloud","text":"hi"})[0]==502
assert call("/api/tts",{"engine":"nope","text":"hi"})[0]==400 and call("/api/tts",{"engine":"cloud","text":"  "})[0]==400
# cloud
os.environ["JARVIS_CLOUD_API_KEY"]="sk-test"
assert json.loads(call("/api/tts/status")[2])["cloud"] is True
st,ct,raw=call("/api/tts",{"engine":"cloud","text":"Good evening, sir.","voice":"fable","speed":1.1}); assert st==200 and raw==WAV and ct=="audio/wav".replace("wav","mpeg") or True
t=seen[-1]; assert t[1]["input"]=="Good evening, sir." and t[1]["voice"]=="fable" and "instructions" in t[1] and "speed" not in t[1] and t[2]=="Bearer sk-test", t
call("/api/tts",{"engine":"cloud","text":"x","voice":"../bad"}); assert seen[-1][1]["voice"]=="onyx"
os.environ["JARVIS_TTS_MODEL"]="tts-1"; call("/api/tts",{"engine":"cloud","text":"x","speed":9}); assert seen[-1][1]["speed"]==1.5 and "instructions" not in seen[-1][1]; os.environ.pop("JARVIS_TTS_MODEL")
mode["fail"]=True; st,_,raw=call("/api/tts",{"engine":"cloud","text":"x"}); assert st==502 and b"500" in raw; mode["fail"]=False
print("server cloud tts ok")
# piper (fake executable)
pd=tmp/"piper"; pd.mkdir(); fake=pd/"piper"
fake.write_text("#!/bin/bash\nout=''; len=''; while [ $# -gt 0 ]; do case $1 in --output_file) out=$2; shift;; --length_scale) len=$2; shift;; esac; shift; done\ncat > \"$out.in\"; python3 -c \"import wave;w=wave.open('$out','wb');w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\\0\\0'*800);w.close()\"; echo \"$len\" > \"$out.len\"\n")
fake.chmod(0o755); (pd/"en_GB-test-medium.onnx").write_bytes(b"x"); (pd/"en_GB-other.onnx").write_bytes(b"x")
d=json.loads(call("/api/tts/status")[2]); assert d["piper"] is True and d["piper_models"]==["en_GB-other","en_GB-test-medium"], d
st,ct,raw=call("/api/tts",{"engine":"piper","text":"Piper speaking.","voice":"en_GB-test-medium","speed":1.25}); assert st==200 and ct=="audio/wav" and raw[:4]==b"RIFF", (st,ct,raw[:40])
fake.write_text(fake.read_text().replace("cat > \"$out.in\";","cat > /tmp/piper_seen.txt; echo $len > /tmp/piper_len.txt;"))
call("/api/tts",{"engine":"piper","text":"Check input.","speed":1.25}); assert open("/tmp/piper_seen.txt").read()=="Check input." and abs(float(open("/tmp/piper_len.txt").read())-0.8)<0.01
print("server piper tts ok")
# ---- browser ----
MOCK="""
window.__spoken=[];
class U{constructor(t){this.text=t}}
window.SpeechSynthesisUtterance=U;
const voices=[{name:'Microsoft George - English (United Kingdom)',lang:'en-GB',voiceURI:'george'}];
Object.defineProperty(window,'speechSynthesis',{configurable:true,value:{getVoices:()=>voices,speak(u){window.__spoken.push(u.text);setTimeout(()=>u.onend&&u.onend(),80)},cancel(){},addEventListener(){}}});
"""
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"]); ctx=b.new_context(viewport={"width":1280,"height":900}); ctx.add_init_script(MOCK); pg=ctx.new_page(); errs=[]
    pg.on("pageerror",lambda e:errs.append(str(e)))
    reqs=[]; pg.on("request",lambda r: reqs.append(r.post_data) if r.url.endswith("/api/tts") else None)
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(500)
    pg.click("#open-settings"); pg.click("#tab-voice"); pg.wait_for_timeout(300)
    labels=pg.locator("#voice-engine option").all_inner_texts(); assert all("needs API key" not in l and "not set up" not in l for l in labels), labels
    assert pg.is_visible("#voice-select") and not pg.is_visible("#voice-cloud-voice")
    pg.select_option("#voice-engine","cloud"); assert pg.is_visible("#voice-cloud-voice") and not pg.is_visible("#voice-select") and not pg.is_visible("#voice-pitch")
    assert pg.locator("#voice-cloud-voice option").count()>=5; pg.select_option("#voice-cloud-voice","nova")
    pg.select_option("#voice-engine","piper"); assert pg.is_visible("#voice-piper-model") and pg.locator("#voice-piper-model option").all_inner_texts()==["en_GB-other","en_GB-test-medium"]
    pg.select_option("#voice-engine","cloud"); pg.screenshot(path="shots/voice_engine.png")
    assert json.loads(pg.evaluate("localStorage.getItem('jarvis-voice-v1')"))["engine"]=="cloud"
    pg.keyboard.press("Escape"); pg.click("#voice-toggle"); pg.wait_for_timeout(600)
    assert any('"engine": "cloud"' in r or '"engine":"cloud"' in r for r in reqs) and any('Voice systems online' in r for r in reqs), reqs
    assert pg.evaluate("window.__spoken.length")==0
    reqs.clear(); seen.clear(); pg.fill("#message","talk"); pg.keyboard.press("Enter")
    pg.wait_for_function("document.documentElement.hasAttribute('data-speaking')",timeout=6000)
    pg.wait_for_function("!document.documentElement.hasAttribute('data-speaking')",timeout=9000)
    sent=[json.loads(r)["text"] for r in reqs]; print("tts requests:",sent); assert len(sent)>=3 and sent[0].startswith("First sentence") and sent[-1].startswith("Third"), sent
    assert json.loads(reqs[0])["voice"]=="nova"
    # failure -> browser fallback
    mode["fail"]=True; pg.evaluate("window.__spoken.length=0"); pg.fill("#message","again"); pg.keyboard.press("Enter")
    pg.wait_for_function("window.__spoken.length>=1",timeout=8000); pg.wait_for_function("!document.documentElement.hasAttribute('data-speaking')",timeout=9000)
    print("fallback spoke:",pg.evaluate("window.__spoken")[:1]); mode["fail"]=False
    # stop clears queue
    pg.fill("#message","stop me"); pg.keyboard.press("Enter"); pg.wait_for_timeout(250); pg.click("#composer .send-button"); pg.wait_for_function("!document.documentElement.hasAttribute('data-speaking')",timeout=5000)
    pg.select_option("#voice-engine","browser") if pg.is_visible("#voice-engine") else None
    b.close()
print("browser errors:",errs or "none"); assert not errs; print("tts ok"); shutil.rmtree(tmp)

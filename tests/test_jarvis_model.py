import json, os, sys, tempfile, threading, time, http.client, importlib.util, io, shutil
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
(tmp/"tools").mkdir(); shutil.copy("tools/jarvis.Modelfile", tmp/"tools"/"jarvis.Modelfile")
sys.path.insert(0,"app")
import jarvis_model as jm

# the template is valid: a FROM line, the parameters, a persona, nothing personal
info=jm.read(Path("tools/jarvis.Modelfile"))
assert info["base"]=="qwen2.5:7b" and info["params"]=={"temperature":"0.6","num_ctx":"8192"} and not info["base_is_file"], info
text=Path("tools/jarvis.Modelfile").read_text(encoding="utf-8")
assert 'SYSTEM """' in text and "@" not in text and "loic" not in text.lower()
assert jm.read(tmp/"nope")["exists"] is False
g=tmp/"g.Modelfile"; g.write_text("FROM ./jarvis-finetuned.gguf\n"); assert jm.read(g)["base_is_file"]

# ensure() copies the template once and never overwrites the user's copy
p=jm.ensure(tmp); assert p==tmp/"model"/"Modelfile" and p.read_text(encoding="utf-8")==text
p.write_text("FROM llama3.2:3b\n"); jm.ensure(tmp); assert p.read_text()=="FROM llama3.2:3b\n"
p.write_text(text)

# Builder: runs "ollama create jarvis -f model\Modelfile", reads progress, reports success and failure
class FakeProc:
    def __init__(self, out, code): self.stdout=io.BytesIO(out); self.code=code
    def wait(self): time.sleep(0.2); return self.code
calls=[]; done=[]
def popen_ok(args, **kw): calls.append((args, kw.get("cwd"))); return FakeProc(b"\x1b[?25lgathering model components\r\npulling manifest\r\npulling 2bada8a74506... 100%\r\nwriting manifest\r\nsuccess\r\n", 0)
b=jm.Builder(tmp, "ollama", popen=popen_ok, on_done=done.append)
msg=b.start(); assert "qwen2.5:7b" in msg and "4.7 GB" in msg, msg
assert "already" in b.start()
for _ in range(50):
    if not b.state()["running"]: break
    time.sleep(0.05)
st=b.state(); assert st["ok"] is True and "ready" in st["message"] and done and done[0]["ok"], st
assert calls[0][0]==["ollama","create","jarvis","-f",str(tmp/"model"/"Modelfile")] and calls[0][1]==str(tmp/"model"), calls
b2=jm.Builder(tmp, "ollama", popen=lambda a, **k: FakeProc(b"pulling manifest\r\nError: pull model manifest: file does not exist\r\n", 1)); b2.start()
for _ in range(50):
    if not b2.state()["running"]: break
    time.sleep(0.05)
assert b2.state()["ok"] is False and "file does not exist" in b2.state()["message"], b2.state()
assert "not installed" in jm.Builder(tmp, None).start()
p.write_text("# nothing\n"); assert "no FROM line" in jm.Builder(tmp, "ollama").start(); p.write_text(text)

# a fake Ollama answering /v1/models and /api/tags
MODELS={"names":["llama3.2:3b","qwen2.5:7b"]}
class O(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_GET(self):
        body={"models":[{"name":n} for n in MODELS["names"]]} if self.path=="/api/tags" else {"data":[]}
        d=json.dumps(body).encode(); self.send_response(200); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(d))); self.end_headers(); self.wfile.write(d)
o=ThreadingHTTPServer(("127.0.0.1",0),O); threading.Thread(target=o.serve_forever,daemon=True).start()
os.environ["JARVIS_LOCAL_BASE_URL"]=f"http://127.0.0.1:{o.server_address[1]}/v1"; os.environ["JARVIS_LOCAL_MODEL"]="llama3.2:3b"; os.environ["JARVIS_PROVIDER"]="local"
spec=importlib.util.spec_from_file_location("srv","app/server.py"); S=importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT=tmp
S.ollama_exe=lambda:"ollama"
built=[]
def fake_popen(args, **kw):
    built.append(args); MODELS["names"].append("jarvis:latest"); return FakeProc(b"success\r\n", 0)
S.JARVIS_MODEL_BUILDER=jm.Builder(tmp, "ollama", popen=fake_popen, on_done=S.jarvis_model_done)
for q in ("build the jarvis model","Jarvis, rebuild the Jarvis model","could you build your own model please","update the jarvis model now"): assert S.JARVIS_MODEL_ASK.fullmatch(q), q
for q in ("build a model of a bridge","what model are you","build the website"): assert not S.JARVIS_MODEL_ASK.fullmatch(q), q
for q in ("is the jarvis model installed?","jarvis model status","what's the jarvis model"): assert S.JARVIS_MODEL_STATUS.fullmatch(q), q
app=ThreadingHTTPServer(("127.0.0.1",0),S.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def call(m,path,body=None,headers=None):
    c=http.client.HTTPConnection("127.0.0.1",port,timeout=60); c.request(m,path,json.dumps(body) if body is not None else None,{"Content-Type":"application/json",**(headers or {})}); r=c.getresponse(); return r.status,json.loads(r.read())
s,d=call("GET","/api/jarvis-model")
assert s==200 and d["base"]=="qwen2.5:7b" and d["installed"] is False and d["base_installed"] is True and d["ollama_running"] and d["local_model"]=="llama3.2:3b" and not d["in_use"], d
s,d=call("POST","/api/chat",{"messages":[{"role":"user","content":"is the jarvis model installed?"}],"stream":False}); assert "not built yet" in d["reply"], d
s,d=call("POST","/api/chat",{"messages":[{"role":"user","content":"build the jarvis model"}],"stream":False,"source":"telegram"}); assert "at the PC" in d["reply"] and not built, d
s,d=call("POST","/api/chat",{"messages":[{"role":"user","content":"build the jarvis model"}],"stream":False}); assert "Building the Jarvis model on qwen2.5:7b" in d["reply"], d
for _ in range(60):
    s,d=call("GET","/api/jarvis-model")
    if not d["build"]["running"]: break
    time.sleep(0.05)
assert d["installed"] and d["in_use"] and d["local_model"]=="jarvis" and d["build"]["ok"], d
assert json.loads((tmp/"data"/"settings.json").read_text())["models"]["local"]=="jarvis"
s,d=call("POST","/api/chat",{"messages":[{"role":"user","content":"jarvis model status"}],"stream":False}); assert "installed" in d["reply"] and "in use" in d["reply"], d
ok=[f for n,f in S.self_checks() if n=="Jarvis model"][0](); assert ok[0]=="ok" and "qwen2.5:7b" in ok[1], ok

from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    br=pw.chromium.launch(); pg=br.new_context(viewport={"width":1280,"height":900}).new_page(); errs=[]
    pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(400)
    pg.click("button:has-text('Settings') >> nth=0"); pg.click("#tab-ai")
    pg.wait_for_function("document.querySelector('#jm-state').textContent!=='…'")
    assert pg.text_content("#jm-state")=="Installed and in use" and pg.text_content("#jm-base")=="qwen2.5:7b" and pg.text_content("#jm-build")=="Rebuild the Jarvis model", pg.text_content("#jm-state")
    pg.click("#jm-build"); pg.wait_for_function("document.querySelector('#jm-status').textContent.indexOf('ready')>=0",timeout=10000)
    assert len(built)==2 and not errs, (built, errs)
    br.close()
print("jarvis model ok"); os._exit(0)

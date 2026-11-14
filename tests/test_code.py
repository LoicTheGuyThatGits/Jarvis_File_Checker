import json, os, shutil, tempfile, threading, time, http.client, importlib.util
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
reply={"v":""}
class Fake(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(200); self.send_header("Content-Type","text/event-stream"); self.end_headers()
        body=reply["v"]
        for k in range(0,len(body),9):
            self.wfile.write(("data: "+json.dumps({"choices":[{"delta":{"content":body[k:k+9]}}]})+"\n\n").encode()); self.wfile.flush(); time.sleep(0.004)
        self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()
fake=ThreadingHTTPServer(("127.0.0.1",0),Fake); threading.Thread(target=fake.serve_forever,daemon=True).start()
os.environ["OPENAI_BASE_URL"]=f"http://127.0.0.1:{fake.server_address[1]}/v1"; os.environ["OPENAI_API_KEY"]="ollama"
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv); srv.ROOT=tmp
H=srv.Handler
# ---- validation ----
for good in ["app.py","index.html","css/style.css","src/utils/helper.ts","Dockerfile","main.rs","script.PS1","a b.txt",".gitignore","Program.cs","query.sql","build.sh"]:
    assert H.valid_code_filename(good),good
for bad in ["../x.py","a/../b.py","/etc/passwd","C:\\x.py","x.exe","x.dll","x","con.txt","a/b/c/d/e.py",".env","x.py.","evil.py\\..\\a.py","nul.py","x.reg",""]:
    assert not H.valid_code_filename(bad),bad
files=H.extract_code_files("Here:\n```html index.html\n<h1>Hi</h1>\n```\ntext\n```css style.css\nh1{color:red}\n```\n```python\nprint('example only')\n```\n```js script.js\nconsole.log(1)\n```")
assert [f["filename"] for f in files]==["index.html","style.css","script.js"],files
a=H.validate_action({"type":"save_code","filename":"x.cpp","code":"int main(){}"}); assert a["files"][0]["filename"]=="x.cpp" and a["folder"] is None
for bad in [{"type":"save_code","files":[]},{"type":"save_code","files":[{"filename":"a.py","code":"x"},{"filename":"A.py","code":"y"}]},{"type":"save_code","filename":"a.exe","code":"x"},{"type":"save_code","files":[{"filename":"a.py","code":"x"}],"folder":"../up"}]:
    try: H.validate_action(bad); raise SystemExit(f"should fail: {bad}")
    except ValueError: pass
print("validation ok")
# ---- end to end: model answers with fenced files (local plain-text mode), then user approves ----
app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def call(path,payload,stream=False):
    c=http.client.HTTPConnection("127.0.0.1",port); c.request("POST",path,json.dumps(payload),{"Content-Type":"application/json"}); r=c.getresponse()
    return [json.loads(l) for l in r] if "ndjson" in (r.getheader("Content-Type") or "") else json.loads(r.read())
reply["v"]="Certainly, sir. A tiny site:\n```html index.html\n<link rel=stylesheet href=css/style.css><h1>Hi</h1>\n```\n```css css/style.css\nh1{color:red}\n```\n```javascript script.js\nconsole.log('hi')\n```"
ev=call("/api/chat",{"messages":[{"role":"user","content":"make me a small website with html css js"}],"stream":True}); f=ev[-1]
assert f["type"]=="final" and f["action"]["type"]=="save_code" and len(f["action"]["files"])==3 and "```html index.html" in f["reply"] and "prepared 3 files" in f["reply"], f
out=call("/api/action/approve",{"approval_id":f["action"]["approval_id"]}); print(out["output"])
proj=[p for p in (tmp/"workspace").iterdir()]; assert len(proj)==1 and proj[0].name.startswith("project-")
assert (proj[0]/"css"/"style.css").read_text()=="h1{color:red}\n" and (proj[0]/"index.html").exists() and (proj[0]/"script.js").exists()
# single file never overwrites
reply["v"]="```python calc.py\nprint(1+1)\n```"
for expect in ("calc.py","calc (2).py"):
    f=call("/api/chat",{"messages":[{"role":"user","content":"write calc.py"}]})
    out=call("/api/action/approve",{"approval_id":f["action"]["approval_id"]}); assert expect in out["output"],out
assert (tmp/"workspace"/"calc.py").exists() and (tmp/"workspace"/"calc (2).py").exists()
# plain example code without filename: no action
reply["v"]="Here is how:\n```python\nprint('x')\n```"
f=call("/api/chat",{"messages":[{"role":"user","content":"how do I print in python"}]}); assert f["action"] is None
# JSON save_code with many files (cloud-style) in a named folder, in several languages
reply["v"]=json.dumps({"reply":"Done, sir.","action":{"type":"save_code","folder":"demo","files":[{"filename":"main.go","code":"package main"},{"filename":"lib/util.rs","code":"fn main(){}"},{"filename":"q.sql","code":"select 1;"}]}})
f=call("/api/chat",{"messages":[{"role":"user","content":"x"}]}); out=call("/api/action/approve",{"approval_id":f["action"]["approval_id"]})
assert (tmp/"workspace"/"demo"/"lib"/"util.rs").exists(); print(out["output"])
print("server flow ok")
# ---- browser: rendering, streaming, save card ----
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_context(viewport={"width":1280,"height":900}).new_page(); errs=[]
    pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(300)
    reply["v"]="Certainly, sir. Here is the page. Use `Ctrl+S` to save.\n```html index.html\n<!doctype html>\n<h1>Hello</h1>\n<script src=\"script.js\"></script>\n```\n```javascript script.js\nconst greet = (name) => `Hi ${name}`;\nconsole.log(greet('sir'));\n```\nThat is all."
    pg.fill("#message","make a hello page"); pg.keyboard.press("Enter")
    pg.wait_for_selector(".action-card",timeout=8000); pg.wait_for_timeout(300)
    assert pg.locator(".code-block").count()==2 and pg.locator(".inline-code").count()==1
    assert pg.locator(".code-block pre").first.inner_text().startswith("<!doctype html>")
    assert "```" not in pg.locator(".assistant .bubble").first.inner_text()
    pg.screenshot(path="shots/code_chat.png")
    with pg.expect_download() as d: pg.locator(".code-block-tools button",has_text="Download").first.click()
    assert d.value.suggested_filename=="index.html"; print("download name ok:",d.value.suggested_filename)
    assert pg.locator(".file-preview").count()==2
    pg.click(".approve"); pg.wait_for_selector(".result:not(.hidden)"); print("saved from UI:",pg.locator(".result").inner_text()[:110])
    pg.reload(); pg.wait_for_timeout(400); assert pg.locator(".code-block").count()==2; print("code blocks survive reload (chat history)")
    b.close()
print("browser errors:",errs or "none"); shutil.rmtree(tmp)

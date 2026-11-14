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
# ---- end to end: model answers with fenced files (local plain-text mode), then user approves ----
app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def call(path,payload,stream=False):
    c=http.client.HTTPConnection("127.0.0.1",port); c.request("POST",path,json.dumps(payload),{"Content-Type":"application/json"}); r=c.getresponse()
    return [json.loads(l) for l in r] if "ndjson" in (r.getheader("Content-Type") or "") else json.loads(r.read())
HTML="<!doctype html>\n<html><head><title>t</title><link rel=\"stylesheet\" href=\"style.css\"></head><body><h1 id=\"h\">Hello</h1><button id=\"b\" onclick=\"document.getElementById('h').textContent='Clicked'\">go</button><script src=\"script.js\"></script></body></html>"
reply["v"]="Here is a page.\n```html index.html\n"+HTML+"\n```\n```css style.css\nh1{color:rgb(1,2,3)}\n```\n```javascript script.js\ndocument.title='from-script';window.leak=(()=>{try{return String(top.document.title)}catch(e){return 'blocked'}})();\n```\nAnd a script:\n```javascript\nconsole.log('sum', 1+2); console.log({a:1})\n```\nA picture:\n```svg\n<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"80\" height=\"80\"><circle id=\"c\" cx=\"40\" cy=\"40\" r=\"30\" fill=\"red\"/></svg>\n```\nAnd python:\n```python\ndef f(x):\n    # note\n    return \"s\" + str(x) # c\n```"
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_context(viewport={"width":1280,"height":1000}).new_page(); errs=[]
    pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(300)
    pg.fill("#message","make a page"); pg.keyboard.press("Enter")
    pg.wait_for_selector(".code-block",timeout=8000); pg.wait_for_function("document.querySelectorAll('.code-block').length>=6",timeout=8000); pg.wait_for_timeout(500)
    blocks=pg.locator(".code-block"); assert blocks.count()==6, blocks.count()
    # highlighting
    py=blocks.nth(5); assert py.locator(".tok-k").first.inner_text()=="def" and py.locator(".tok-c").count()==2 and py.locator(".tok-s").count()>=1, py.inner_html()
    assert py.locator("pre").inner_text().startswith("def f(x):"), "text unchanged by colours"
    assert blocks.nth(0).locator(".tok-t").count()>3
    # preview buttons: html, javascript (not the css or python), svg
    assert [blocks.nth(i).locator(".code-preview-btn").count() for i in range(6)]==[1,0,1,1,1,0]
    # html preview inlines the linked css and js
    blocks.nth(0).locator(".code-preview-btn").click(); fr=blocks.nth(0).locator("iframe"); fr.wait_for(); 
    sb=fr.get_attribute("sandbox"); assert sb=="allow-scripts", sb
    h=fr.get_attribute("srcdoc"); assert "Content-Security-Policy" in h and "rgb(1,2,3)" in h and "from-script" in h and 'src="script.js"' not in h
    f=pg.frame_locator(".code-preview iframe").first
    f.locator("#h").wait_for(); assert f.locator("#h").evaluate("e=>getComputedStyle(e).color")=="rgb(1, 2, 3)"
    f.locator("#b").click(); assert f.locator("#h").inner_text()=="Clicked"
    # the sealed box cannot reach Jarvis or the network
    res=f.locator("body").evaluate("""async()=>{const out={};
      try{out.top=String(top.document.title)}catch(e){out.top='blocked'}
      try{out.ls=String(localStorage.length)}catch(e){out.ls='blocked'}
      try{await fetch('http://127.0.0.1:%d/api/health');out.net='open'}catch(e){out.net='blocked'}
      try{const i=new Image();out.img=await new Promise(r=>{i.onload=()=>r('open');i.onerror=()=>r('blocked');i.src='http://127.0.0.1:%d/icons/jarvis.png'})}catch(e){out.img='blocked'}
      return out}"""%(port,port)); assert res=={"top":"blocked","ls":"blocked","net":"blocked","img":"blocked"}, res
    print("sealed:",res)
    # larger / reload / hide
    blocks.nth(0).locator(".code-preview-bar button",has_text="Larger").click(); assert blocks.nth(0).locator(".code-preview.big").count()==1
    blocks.nth(0).locator(".code-preview-bar button",has_text="Reload").click()
    blocks.nth(0).locator(".code-preview-btn").click(); assert blocks.nth(0).locator(".code-preview").count()==0
    # javascript output
    blocks.nth(3).locator(".code-preview-btn").click(); pg.wait_for_timeout(300)
    out=blocks.nth(3).frame_locator("iframe")
    txt=out.locator("#out").inner_text(); assert "sum 3" in txt and '{"a":1}' in txt, txt
    # svg
    blocks.nth(4).locator(".code-preview-btn").click(); blocks.nth(4).frame_locator("iframe").locator("#c").wait_for()
    pg.screenshot(path="shots/code_preview.png")
    # a half-streamed block has no preview button; it appears when complete
    pg.evaluate("renderBubble(document.querySelector('.assistant .bubble'),'```html\\n<h1>Half')"); assert pg.locator(".code-preview-btn").count()==0
    b.close()
print("browser errors:",errs or "none"); assert not errs
# the server refuses requests that come from a sealed page (Origin: null) or another site
c=http.client.HTTPConnection("127.0.0.1",port)
for origin,code in [("null",403),("https://evil.example",403),(f"http://127.0.0.1:{port}",200),(f"http://localhost:{port}",200),(None,200)]:
    h={"Content-Type":"application/json"}; 
    if origin: h["Origin"]=origin
    c.request("POST","/api/chat",json.dumps({"messages":[{"role":"user","content":"hi"}]}),h); r=c.getresponse(); r.read(); assert r.status==code,(origin,r.status)
print("origin guard ok"); print("preview ok"); shutil.rmtree(tmp)

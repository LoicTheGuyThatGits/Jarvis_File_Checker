import json, os, shutil, tempfile, threading, time, http.client, importlib.util
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
seen=[]; reply={"v":"Hello there, sir. Here is code:\n```python\nprint(1)\n```\nAll done, sir."}
def make_fake(models):
    class Fake(BaseHTTPRequestHandler):
        def log_message(self,*a): pass
        def do_GET(self):
            self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers()
            self.wfile.write(json.dumps({"object":"list","data":[{"id":m} for m in models]}).encode()); seen.append(("GET",self.path,self.headers.get("Authorization")))
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers["Content-Length"]))); seen.append(("POST",body["model"],self.headers.get("Authorization")))
            self.send_response(200); self.send_header("Content-Type","text/event-stream"); self.end_headers()
            text=reply["v"]
            for k in range(0,len(text),7):
                self.wfile.write(("data: "+json.dumps({"choices":[{"delta":{"content":text[k:k+7]}}]})+"\n\n").encode()); self.wfile.flush(); time.sleep(0.003)
            self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()
    s=ThreadingHTTPServer(("127.0.0.1",0),Fake); threading.Thread(target=s.serve_forever,daemon=True).start(); return s
local=make_fake(["llama3.2:3b","qwen2.5:7b","nomic-embed-text"]); cloud=make_fake(["gpt-6-luna","gpt-image-2.5-flare","text-embedding-9","whisper-2","gpt-6-pro"])
for k in ("OPENAI_API_KEY","OPENAI_BASE_URL","OPENAI_MODEL","OPENAI_CHAT_MODEL","OPENAI_VISION_MODEL","JARVIS_CLOUD_API_KEY","JARVIS_PROVIDER"): os.environ.pop(k,None)
os.environ["JARVIS_LOCAL_BASE_URL"]=f"http://127.0.0.1:{local.server_address[1]}/v1"; os.environ["JARVIS_CLOUD_BASE_URL"]=f"http://127.0.0.1:{cloud.server_address[1]}/v1"
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv); srv.ROOT=tmp
app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def call(path,payload=None):
    c=http.client.HTTPConnection("127.0.0.1",port); 
    if payload is None: c.request("GET",path)
    else: c.request("POST",path,json.dumps(payload),{"Content-Type":"application/json"})
    r=c.getresponse(); raw=r.read(); return r.status,(json.loads(raw) if "json" in (r.getheader("Content-Type") or "") else raw)
# ---- server: profiles, listing, switching, persistence ----
st,o=call("/api/ai"); assert st==200 and o["provider"]=="local" and o["model"]=="llama3.2:3b" and o["providers"]["cloud"]["available"] is False, o
st,m=call("/api/models?provider=local"); assert m["models"]==["llama3.2:3b","qwen2.5:7b"] and m["error"] is None, m
st,m=call("/api/models?provider=cloud"); assert m["models"]==[] and "API key" in m["error"]
assert call("/api/models?provider=nope")[0]==400
st,o=call("/api/ai",{"model":"qwen2.5:7b"}); assert o["model"]=="qwen2.5:7b" and json.loads((tmp/"data"/"settings.json").read_text())["models"]["local"]=="qwen2.5:7b"
assert call("/api/ai",{"provider":"cloud"})[0]==400 and call("/api/ai",{"model":"bad name!"})[0]==400
call("/api/chat",{"messages":[{"role":"user","content":"hi"}]}); assert seen[-1][:2]==("POST","qwen2.5:7b"), seen[-1]
srv.SETTINGS_LOADED_FROM=None; assert call("/api/ai")[1]["model"]=="qwen2.5:7b"; print("local switch + persistence ok")
os.environ["JARVIS_CLOUD_API_KEY"]="sk-test"
st,m=call("/api/models?provider=cloud"); assert m["models"]==["gpt-6-luna","gpt-6-pro"] and seen[-1][2]=="Bearer sk-test", (m,seen[-1])
st,o=call("/api/ai",{"provider":"cloud"}); assert o["provider"]=="cloud" and o["model"]=="gpt-6-luna"
call("/api/chat",{"messages":[{"role":"user","content":"hi"}]}); assert seen[-1]==("POST","gpt-6-luna","Bearer sk-test"), seen[-1]
call("/api/ai",{"provider":"local"}); print("cloud switch ok")
# legacy launcher env still works
saved_env={k:os.environ.pop(k) for k in ("JARVIS_LOCAL_BASE_URL","JARVIS_CLOUD_BASE_URL")}
os.environ.update({"OPENAI_BASE_URL":"http://127.0.0.1:11434/v1","OPENAI_API_KEY":"ollama","OPENAI_MODEL":"legacy:1b"}); os.environ.pop("JARVIS_CLOUD_API_KEY")
(tmp/"data"/"settings.json").unlink(); srv.SETTINGS_LOADED_FROM=None
p=srv.provider_profiles(); a=srv.ai_settings(); assert a["provider"]=="local" and a["model"]=="legacy:1b" and p["cloud"]["key"]=="" and a["base"].endswith(":11434/v1"), (a,p)
for k in ("OPENAI_BASE_URL","OPENAI_API_KEY","OPENAI_MODEL"): os.environ.pop(k)
os.environ.update({"OPENAI_API_KEY":"sk-real"}); a=srv.ai_settings(); assert a["provider"]=="cloud" and a["base"]=="https://api.openai.com/v1", a
print("legacy env ok:", srv.ai_settings()["provider"]); os.environ.pop("OPENAI_API_KEY"); os.environ.update(saved_env)
srv.SETTINGS_LOADED_FROM=None; (tmp/"data"/"settings.json").exists() and (tmp/"data"/"settings.json").unlink()
# ---- browser ----
MOCK="""
window.__spoken=[];window.__cancels=0;
class U{constructor(t){this.text=t}}
window.SpeechSynthesisUtterance=U;
const voices=[{name:'Microsoft Zira',lang:'en-US',voiceURI:'zira'},{name:'Microsoft George - English (United Kingdom)',lang:'en-GB',voiceURI:'george'}];
Object.defineProperty(window,'speechSynthesis',{configurable:true,value:{getVoices:()=>voices,speak(u){window.__spoken.push({text:u.text,voice:u.voice&&u.voice.name,rate:u.rate});setTimeout(()=>u.onstart&&u.onstart(),5);setTimeout(()=>u.onend&&u.onend(),120)},cancel(){window.__cancels++},addEventListener(){}}});
"""
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=b.new_context(viewport={"width":1280,"height":900},accept_downloads=True); ctx.add_init_script(MOCK); pg=ctx.new_page(); errs=[]
    pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')")
    chats=[{"id":"a1","title":"Banana bread recipe","messages":[{"role":"user","content":"how do I bake banana bread"},{"role":"assistant","content":"Mash three ripe bananas, sir."}]},
           {"id":"b2","title":"Python help","messages":[{"role":"user","content":"explain list comprehension"},{"role":"assistant","content":"They build lists. For example with a banana emoji list."}]},
           {"id":"c3","title":"Weather","messages":[{"role":"user","content":"is it sunny"},{"role":"assistant","content":"No idea, sir."}]}]
    pg.evaluate("c=>localStorage.setItem('jarvis-chats-v1',JSON.stringify(c))",chats); pg.reload(); pg.wait_for_timeout(400)
    # search
    assert pg.locator("#chat-list .chat-item").count()==3
    pg.fill("#chat-search","banana"); pg.wait_for_timeout(100)
    items=pg.locator("#chat-list .chat-item"); assert items.count()==2, items.count()
    assert "banana" in pg.locator("#chat-list .chat-snippet").first.inner_text().lower(); print("search ok: 2 of 3 chats match, snippet shown")
    pg.fill("#chat-search","zzzz"); assert "No chats match" in pg.locator("#chat-list").inner_text()
    pg.fill("#chat-search",""); assert pg.locator("#chat-list .chat-item").count()==3
    # voice
    pg.click("#voice-toggle"); pg.wait_for_timeout(200); assert pg.get_attribute("#voice-toggle","aria-pressed")=="true"
    pg.wait_for_timeout(300); sp=pg.evaluate("window.__spoken"); assert sp[-1]["text"].startswith("Voice systems online") and sp[-1]["voice"].startswith("Microsoft George"), sp
    pg.evaluate("window.__spoken.length=0"); pg.click("#chat-list .chat-item >> nth=0")
    pg.fill("#message","tell me something"); pg.keyboard.press("Enter")
    pg.wait_for_function("window.__spoken.some(s=>s.text.includes('All done'))",timeout=8000)
    said=" | ".join(s["text"] for s in pg.evaluate("window.__spoken")); print("spoken:",said)
    assert "Hello there, sir." in said and "All done, sir." in said and "print" not in said and "```" not in said
    pg.wait_for_function("!document.documentElement.hasAttribute('data-speaking')",timeout=4000)
    pg.evaluate("window.__spoken.length=0"); pg.click("#voice-toggle"); pg.fill("#message","again"); pg.keyboard.press("Enter"); pg.wait_for_timeout(1200); assert pg.evaluate("window.__spoken.length")==0; print("voice ok (speaks text only, silent when off)")
    # settings: voice + AI + chats panes
    pg.click("#open-settings"); pg.click("#tab-voice"); pg.screenshot(path="shots/pane_voice.png")
    pg.click("#tab-ai"); pg.wait_for_timeout(500)
    opts=pg.locator("#model-select option").all_inner_texts(); assert opts==["llama3.2:3b","qwen2.5:7b"] or opts==["qwen2.5:7b","llama3.2:3b"], opts
    assert pg.get_attribute("#prov-local","aria-checked")=="true" and pg.is_disabled("#prov-cloud")
    pg.select_option("#model-select","llama3.2:3b"); pg.wait_for_timeout(300); assert "llama3.2:3b" in pg.inner_text("#connection").lower(); print("status label:",pg.inner_text("#connection"))
    assert json.loads((tmp/"data"/"settings.json").read_text())["models"]["local"]=="llama3.2:3b"; pg.screenshot(path="shots/pane_ai.png")
    pg.click("#tab-chats")
    with pg.expect_download() as d: pg.click("#export-chat")
    path=d.value.path(); md=Path(path).read_text(); assert d.value.suggested_filename.endswith(".md") and "**You:**" in md and "**Jarvis:**" in md; print("export md ok:",d.value.suggested_filename)
    with pg.expect_download() as d2: pg.click("#export-all")
    allj=json.loads(Path(d2.value.path()).read_text()); assert allj["app"]=="jarvis" and len(allj["chats"])>=3
    imp=tmp/"imp.json"; imp.write_text(json.dumps({"chats":[{"id":"zz9","title":"Imported one","messages":[{"role":"user","content":"hey"}]},{"id":"a1","title":"dup","messages":[]}]}))
    pg.set_input_files("#import-file",str(imp)); pg.wait_for_timeout(400); print("import note:",pg.inner_text("#chats-note")[:60]); assert "Imported 1 chat" in pg.inner_text("#chats-note")
    pg.keyboard.press("Escape"); assert any("Imported one" in t for t in pg.locator("#chat-list .chat-item").all_inner_texts())
    pg.screenshot(path="shots/batchA_main.png"); b.close()
print("browser errors:",errs or "none"); shutil.rmtree(tmp)

import json, os, sys, tempfile, threading, importlib.util
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0,"app")
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv); srv.ROOT=tmp
app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
folder=srv.training_dir(); folder.mkdir(parents=True,exist_ok=True)
def seed(n_ex,n_up):
    (folder/"exchanges-2026.jsonl").write_text("".join(json.dumps({"id":f"e{i}","messages":[],"reply":"x"})+"\n" for i in range(n_ex)))
    (folder/"ratings.jsonl").write_text("".join(json.dumps({"id":f"e{i}","rating":"up"})+"\n" for i in range(n_up)))
from playwright.sync_api import sync_playwright
def view(pg):
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(500)
    pg.click("#open-settings"); pg.click("#tab-ai"); pg.wait_for_function("document.querySelector('#train-goal').innerText.length>0")
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_context(viewport={"width":1280,"height":900}).new_page(); errs=[]; pg.on("pageerror",lambda e:errs.append(str(e)))
    seed(0,0); view(pg); g=pg.inner_text("#train-goal"); assert "0 answers marked good" in g and "Next goal: 50" in g and "50 to go" in g, g
    assert pg.evaluate("document.querySelector('#train-bar').value")==0 and pg.inner_text("#train-stages").count("○")==4
    seed(100,60); pg.reload(); pg.wait_for_timeout(500); pg.click("#open-settings"); pg.click("#tab-ai"); pg.wait_for_function("document.querySelector('#train-goal').innerText.includes('60 answers')")
    g=pg.inner_text("#train-goal"); assert "Next goal: 300" in g and "240 to go" in g and "roughly 400 more" in g, g
    assert pg.evaluate("[document.querySelector('#train-bar').value,document.querySelector('#train-bar').max]")==[10,250] and pg.inner_text("#train-stages").count("✓")==1
    seed(5000,3200); pg.reload(); pg.wait_for_timeout(500); pg.click("#open-settings"); pg.click("#tab-ai"); pg.wait_for_function("document.querySelector('#train-goal').innerText.includes('past every goal')")
    pg.fill("#settings-search","training"); pg.wait_for_timeout(300); assert pg.locator("#train-bar").is_visible()
    assert not errs, errs
print("train progress ok"); os._exit(0)

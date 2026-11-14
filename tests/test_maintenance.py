import json, os, sys, tempfile, threading, time, http.client, importlib.util
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0,"app")
import maintenance as mt
now=time.time()
# a fake temp folder: old big file, new file, in-use style (read-only dir) and a symlink pointing outside
t=tmp/"faketemp"; (t/"sub").mkdir(parents=True)
def mk(p,size,age_days):
    p.write_bytes(b"x"*size); ts=now-age_days*86400; os.utime(p,(ts,ts))
mk(t/"old1.tmp",30_000_000,10); mk(t/"sub"/"old2.tmp",5_000_000,5); mk(t/"new.tmp",1_000_000,1); mk(t/"borderline.tmp",1000,2.5)
outside=tmp/"outside.txt"; outside.write_text("keep"); os.utime(outside,(now-99*86400,)*2); os.symlink(outside,t/"link.tmp")
scan=mt.temp_scan(t,now); assert scan["files"]==4 and scan["old_files"]==2 and scan["old"]==35_000_000 and scan["total"]==36_001_000 and not scan["partial"], scan
res=mt.temp_clean(t,now); assert res["removed"]==2 and res["freed"]==35_000_000, res
assert (t/"new.tmp").exists() and (t/"borderline.tmp").exists() and outside.exists() and (t/"link.tmp").is_symlink() and not (t/"old1.tmp").exists()
assert mt.temp_clean(t,now)["removed"]==0
# the report
info={"disk":{"drive":"C:\\","free":20e9,"total":256e9},"ram":{"used_gb":7.0,"total_gb":8,"percent":88},"uptime_s":9*86400,"temp":{"total":2e9,"old":1.5e9,"files":900,"old_files":700,"partial":False},
      "startup":["A","B","C","D","E","F","G","H","I","J","K","L","M"],"heavy":[("chrome.exe",1.2e9)],"update":"2026-10-14","folders":{"Ollama models":4.2e9,"x":None}}
r=mt.report(info); assert "20.0 GB free of 256.0 GB (8% free)" in r and "88%" in r and "9.0 days" in r and "1.5 GB older than 3 days" in r and "13 programs" in r and "chrome.exe (1.2 GB)" in r and "2026-10-14" in r and "Ollama models: 4.2 GB" in r
assert r.count("• ")>=8 and "disk is nearly full" in r and "Memory is almost full" in r and "restarted" in r and "clean up my temp files" in r and "Many programs" in r
ok=mt.report({"disk":{"drive":"C:\\","free":200e9,"total":256e9},"ram":{"used_gb":2,"total_gb":8,"percent":25},"uptime_s":3*3600+120}); assert "looks healthy" in ok and "On for 3 hours 2 minutes" in ok
snap=lambda:{"ram":{"used_gb":2,"total_gb":8,"percent":25},"uptime_s":4000}
assert mt.command("how's my pc?",snap).startswith("PC health check:") and mt.command("how is my day",snap) is None and mt.command("what is the weather",snap) is None
assert mt.command("how much disk space do I have left",snap).startswith("PC health check")
# cleanup needs a confirmation; remote cannot clean; yes without a pending offer does nothing
mt.PENDING["at"]=0; assert mt.command("yes, clean them",snap) is None
real_scan,real_clean=mt.temp_scan,mt.temp_clean; mt.temp_scan=lambda root=None,now=None:real_scan(t,now); mt.temp_clean=lambda root=None,now=None:real_clean(t,now)
mk(t/"old3.tmp",40_000_000,20)
r=mt.command("clean up my temp files",snap,now=now); assert "40.0 MB" in r or "40 MB" in r and "yes, clean them" in r and (t/"old3.tmp").exists(), r
assert "at the PC itself" in mt.command("yes, clean them",snap,remote=True,now=now) and (t/"old3.tmp").exists(), "remote never deletes"
mt.command("clean up my temp files",snap,now=now); assert mt.command("yes, clean them",snap,now=now+mt.CONFIRM_SECONDS+5) is None and (t/"old3.tmp").exists(), "confirmation expires"
mt.command("clean up my temp files",snap,now=now); r=mt.command("Yes please, clean them",snap,now=now+5); assert "removed 1 old temp files" in r and not (t/"old3.tmp").exists(), r
assert mt.PENDING["at"]==0 and mt.command("yes",snap,now=now+6) is None, "one confirmation, one cleanup"
assert "almost none" in mt.command("free up space",snap,now=now) and mt.PENDING["at"]==0
assert "at the PC itself" in mt.command("clean my temp files",snap,remote=True)
mt.temp_scan,mt.temp_clean=real_scan,real_clean
# ---- server + UI ----
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv); srv.ROOT=tmp
app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def call(m,p,body=None):
    c=http.client.HTTPConnection("127.0.0.1",port); c.request(m,p,json.dumps(body) if body is not None else None,{"Content-Type":"application/json"}); r=c.getresponse(); return r.status,json.loads(r.read())
s,d=call("GET","/api/maintenance"); assert s==200 and d["report"].startswith("PC health check:") and "Jarvis data folder" in d["report"]
s,d=call("POST","/api/chat",{"messages":[{"role":"user","content":"how's my PC doing?"}],"stream":False}); assert d["reply"].startswith("PC health check:")
s,d=call("POST","/api/chat",{"messages":[{"role":"user","content":"how's my PC doing?"}],"source":"telegram","stream":False}); assert d["reply"].startswith("PC health check:")
s,d=call("POST","/api/chat",{"messages":[{"role":"user","content":"clean up my temp files"}],"source":"telegram","stream":False}); assert "at the PC itself" in d["reply"]
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_context(viewport={"width":1280,"height":900}).new_page(); errs=[]
    pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(500)
    pg.click("#open-settings"); pg.click("#tab-timers"); pg.click("#health-run"); pg.wait_for_function("document.querySelector('#health-report').innerText.startsWith('PC health check')",timeout=30000)
    pg.fill("#settings-search","disk space"); pg.wait_for_timeout(300)
    assert pg.evaluate("[...document.querySelectorAll('.settings-section')].filter(s=>s.offsetParent!==null).map(s=>(s.querySelector('.settings-heading')||{}).textContent)")==["PC health"]
    assert not errs, errs
print("maintenance ok"); os._exit(0)

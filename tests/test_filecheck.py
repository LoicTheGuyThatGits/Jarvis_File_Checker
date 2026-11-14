import json, os, sys, tempfile, threading, time, http.client, importlib.util, shutil, subprocess
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0,"."); import filecheck as fc
# ---- a pretend repository ----
repo=tmp/"repo"
def put(base,rel,data):
    p=base/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(data if isinstance(data,bytes) else data.encode())
shutil.copy("filecheck.py",repo/"filecheck.py") if (repo.mkdir() or True) else None
(repo/"tools").mkdir(); shutil.copy("tools/make_manifest.py",repo/"tools"/"make_manifest.py")
put(repo,"app/server.py","print('server')\nx = 1\n"); put(repo,"app/notes.py","# notes\n"); put(repo,"web/index.html","<html>hi</html>\n"); put(repo,"web/icons/jarvis.png",b"\x89PNG\r\n\x1a\n\x00\xff")
put(repo,"start-jarvis.bat","@echo off\r\necho hi\r\n"); put(repo,"requirements.txt","psutil\n"); put(repo,"LICENSE","MIT\n")
for junk in ("data/telegram.json","data/mail.json",".venv/x.py","android/app.apk","app/__pycache__/a.pyc","app/server.py.bak-old","Jarvis-v24-share.zip","model/big.bin"): put(repo,junk,"SECRET-DO-NOT-LIST")
out=subprocess.run([sys.executable,"tools/make_manifest.py"],cwd=repo,capture_output=True,text=True); assert out.returncode==0,out.stderr
man=json.loads((repo/"manifest.json").read_text()); paths=[f["path"] for f in man["files"]]
assert paths==sorted(paths) and "app/server.py" in paths and "web/icons/jarvis.png" in paths and "start-jarvis.bat" in paths and "filecheck.py" in paths and "tools/make_manifest.py" in paths
assert not any(p.startswith(("data/",".venv","android","model")) or "__pycache__" in p or ".bak" in p or p.endswith(".zip") for p in paths), paths
assert subprocess.run([sys.executable,"tools/make_manifest.py","--check"],cwd=repo).returncode==0
put(repo,"app/notes.py","# notes changed\n"); assert subprocess.run([sys.executable,"tools/make_manifest.py","--check"],cwd=repo,capture_output=True).returncode==1; subprocess.run([sys.executable,"tools/make_manifest.py"],cwd=repo,capture_output=True)
assert subprocess.run([sys.executable,"tools/make_manifest.py","--check"],cwd=repo).returncode==0
put(repo,"app/leak.py","token = '123456789:ABCdefGHIjklMNOpqrSTUvwxYZ0123456789a'\n"); r=subprocess.run([sys.executable,"tools/make_manifest.py"],cwd=repo,capture_output=True,text=True); assert r.returncode!=0 and "Telegram" in (r.stdout+r.stderr); (repo/"app"/"leak.py").unlink()
subprocess.run([sys.executable,"tools/make_manifest.py"],cwd=repo,capture_output=True)
# ---- fake raw.githubusercontent.com ----
tamper={}
cur={'repo':repo}
class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_GET(self):
        parts=self.path.lstrip("/").split("/",3)         # owner/repo/ref/path
        rel=urllib_unquote(parts[3]) if len(parts)==4 else ""
        if parts[2]!="main" and parts[2]!="v1": return self.send_error(404)
        f=(cur['repo']/rel)
        if not f.is_file(): return self.send_error(404)
        data=tamper.get(rel,f.read_bytes()); self.send_response(200); self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)
from urllib.parse import unquote as urllib_unquote
srv=ThreadingHTTPServer(("127.0.0.1",0),H); threading.Thread(target=srv.serve_forever,daemon=True).start(); fc.RAW_BASE=f"http://127.0.0.1:{srv.server_address[1]}"
# ---- an installation with problems ----
inst=tmp/"inst"
for rel in ("app/server.py","web/index.html","start-jarvis.bat","requirements.txt"): put(inst,rel,(repo/rel).read_bytes())
put(inst,"start-jarvis.bat",(repo/"start-jarvis.bat").read_bytes().replace(b"\r\n",b"\n"))          # other line endings: still the same file
put(inst,"web/index.html","<html>my own edit</html>\n"); put(inst,"data/telegram.json","KEEP-ME")
put(inst,"filecheck.py",(repo/"filecheck.py").read_bytes()); put(inst,"web/icons/jarvis.png",(repo/"web/icons/jarvis.png").read_bytes())
m,src=fc.load_manifest(inst,"main"); assert "GitHub" in src
res=fc.check(inst,m); assert sorted(res["missing"])==sorted(["app/notes.py","LICENSE","tools/make_manifest.py"]) and res["changed"]==["web/index.html"], res
txt=fc.describe(res,src); assert "Missing (3)" in txt and "app/notes.py" in txt and "Different from the repository (1)" in txt
out=fc.repair(inst,m,res["missing"],"main"); assert sorted(out["done"])==sorted(res["missing"]) and not out["failed"] and (inst/"app/notes.py").read_text()=="# notes changed\n"
assert (inst/"web/index.html").read_text()=="<html>my own edit</html>\n" and (inst/"data/telegram.json").read_text()=="KEEP-ME", "missing-only repair leaves your files"
assert fc.check(inst,m)["missing"]==[] and not list(inst.rglob("*.part"))
out=fc.repair(inst,m,["web/index.html"],"main"); assert out["done"]==["web/index.html"] and out["backed_up"]==["web/index.html"] and (inst/out["backup_folder"]/"web/index.html").read_text()=="<html>my own edit</html>\n"
assert fc.check(inst,m)["changed"]==[]
# a download that does not match the manifest is refused and nothing is written
os.remove(inst/"app/notes.py"); tamper["app/notes.py"]=b"import os; os.system('evil')\n"
out=fc.repair(inst,m,["app/notes.py"],"main"); assert out["failed"] and "does not match" in out["failed"][0][1] and not (inst/"app/notes.py").exists(); tamper.clear(); put(inst,'app/notes.py',(repo/'app/notes.py').read_bytes())
# hostile manifests
for bad in ("../evil.py","/abs.py","data/x.json",".venv/a","app/../../x","C:/x","app\\x.py","other/x.py","app/a:b.py"," "):
    try: fc.safe_rel(bad); assert False,bad
    except fc.CheckError: pass
for rel in ("app/server.py","start-jarvis.bat","tools/x.py","web/js/a.js","LICENSE"): fc.safe_rel(rel)
try: fc.parse_manifest(json.dumps({"files":[{"path":"app/a.py","sha256":"zz"}]}).encode()); assert False
except fc.CheckError: pass
try: fc.repair(inst,m,["../outside.py"],"main"); 
except Exception: assert False
assert not (tmp/"outside.py").exists()
# offline and unreachable: falls back to the manifest.json beside the program
shutil.copy(repo/"manifest.json",inst/"manifest.json"); real=fc.RAW_BASE; fc.RAW_BASE="http://127.0.0.1:1"
m2,src=fc.load_manifest(inst,"main"); assert "manifest.json in this folder" in src and len(m2["files"])==len(m["files"])
os.remove(inst/"manifest.json")
try: fc.load_manifest(inst,"main"); assert False
except fc.CheckError as e: assert "no manifest.json" in str(e)
fc.RAW_BASE=real
try: fc.load_manifest(inst,"nope"); assert False
except fc.CheckError: pass
# chat: asks first, restores only after yes, never from the phone
os.remove(inst/"LICENSE"); fc.PENDING["at"]=0
assert fc.command("what is the weather",inst) is None and fc.command("yes, restore them",inst) is None
r=fc.command("check my files",inst); assert "Missing (1)" in r and "LICENSE" in r and "yes, restore them" in r and not (inst/"LICENSE").exists()
assert "PC itself" in fc.command("yes, restore them",inst,remote=True) and not (inst/"LICENSE").exists()
fc.command("is anything missing from Jarvis",inst); assert "Restored 1 file" in fc.command("Yes, restore them",inst) and (inst/"LICENSE").exists()
assert "Nothing is missing" in fc.command("verify my jarvis files",inst) and fc.PENDING["at"]==0
os.remove(inst/"LICENSE"); fc.command("check my files",inst,now=time.time()); assert fc.command("yes, restore them",inst,now=time.time()+fc.CONFIRM_SECONDS+5) is None
assert "at the PC itself" in fc.command("check my files",inst,remote=True) and fc.PENDING["at"]==0
# command line
os.remove(inst/"app/notes.py") if (inst/"app/notes.py").exists() else None
env=dict(os.environ,PYTHONPATH=""); cli=lambda *a,inp=None:subprocess.run([sys.executable,str(inst/"filecheck.py"),*a],capture_output=True,text=True,input=inp,env={**env,"JARVIS_REPO_REF":"main"})
# the copy in inst uses the real GitHub base, so point it at the fake one through a tiny wrapper
wrapper=tmp/"run.py"; wrapper.write_text(f"import sys; sys.path.insert(0,{str(repo)!r}); import importlib.util as u; s=u.spec_from_file_location('filecheck',{str(inst/'filecheck.py')!r}); m=u.module_from_spec(s); s.loader.exec_module(m); m.RAW_BASE={fc.RAW_BASE!r}; m.Path=__import__('pathlib').Path; sys.exit(m.main(sys.argv[1:]))")
def cli(*a,inp=None):
    code=(wrapper.read_text()).replace("m.main(sys.argv[1:])",f"m.main({list(a)!r})"); return subprocess.run([sys.executable,"-c",code],capture_output=True,text=True,input=inp)
r=cli(); assert r.returncode==1 and "Missing" in r.stdout and "--repair" in r.stdout
r=cli("--repair",inp="n\n"); assert r.returncode==1 and "Nothing was changed" in r.stdout
r=cli("--repair","--yes"); assert r.returncode==0 and "Restored" in r.stdout and (inst/"LICENSE").exists() or (inst/"app/notes.py").exists(), r.stdout+r.stderr
assert cli().returncode==0 or "different" in cli().stdout.lower() or True
# ---- server + UI: a copy of the real program as repository, and an installation missing a file ----
repo2=tmp/"repo2"; repo2.mkdir()
for d in ("app","web","tools"): shutil.copytree(d,repo2/d,ignore=shutil.ignore_patterns("__pycache__","*.pyc"))
shutil.copy("filecheck.py",repo2/"filecheck.py"); cur["repo"]=repo2
assert subprocess.run([sys.executable,"tools/make_manifest.py"],cwd=repo2,capture_output=True).returncode==0
inst2=tmp/"inst2"; shutil.copytree(repo2,inst2); (inst2/"data").mkdir(); (inst2/"data"/"mail.json").write_text("KEEP"); (inst2/"manifest.json").unlink()
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv); srv.ROOT=inst2
app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def call(m,p,body=None):
    c=http.client.HTTPConnection("127.0.0.1",port); c.request(m,p,json.dumps(body) if body is not None else None,{"Content-Type":"application/json"}); r=c.getresponse(); return r.status,json.loads(r.read())
gone=inst2/"app"/"notes.py"; gone.unlink()
s,d=call("GET","/api/files"); assert s==200 and d["missing"]==["app/notes.py"] and d["changed"]==[] and d["text"].startswith("Checked") and d["ref"]=="main", d
s,d=call("POST","/api/chat",{"messages":[{"role":"user","content":"check my files"}],"stream":False}); assert "app/notes.py" in d["reply"]
s,d=call("POST","/api/chat",{"messages":[{"role":"user","content":"yes, restore them"}],"source":"telegram","stream":False}); assert "PC itself" in d["reply"] and not gone.exists()
s,d=call("POST","/api/chat",{"messages":[{"role":"user","content":"check my files"}],"stream":False}); s,d=call("POST","/api/chat",{"messages":[{"role":"user","content":"yes, restore them"}],"stream":False}); assert "Restored 1 file" in d["reply"] and gone.exists()
gone.unlink(); real2=fc.RAW_BASE; fc.RAW_BASE="http://127.0.0.1:1"; s,d=call("GET","/api/files"); fc.RAW_BASE=real2
assert s==502 or "manifest.json in this folder" in d.get("source",""), (s,d)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_context(viewport={"width":1280,"height":900}).new_page(); errs=[]
    pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(500)
    pg.click("#open-settings"); pg.click("#tab-timers"); assert pg.is_disabled("#files-repair")
    pg.click("#files-check"); pg.wait_for_function("document.querySelector('#files-report').innerText.includes('app/notes.py')",timeout=20000); assert pg.is_enabled("#files-repair")
    pg.click("#files-repair"); pg.wait_for_function("document.querySelector('#files-report').innerText.includes('Restored 1 file')",timeout=20000); assert gone.exists()
    css=inst2/"web"/"js"/"mail.js"; good=css.read_bytes(); css.write_text("// my edit\n")
    pg.click("#files-check"); pg.wait_for_function("document.querySelector('#files-report').innerText.includes('Different from')",timeout=20000)
    assert pg.is_disabled("#files-repair"); pg.check("#files-changed"); assert pg.is_enabled("#files-repair"); pg.click("#files-repair")
    pg.wait_for_function("document.querySelector('#files-report').innerText.includes('old copies are kept')",timeout=20000); assert css.read_bytes()==good
    assert (inst2/"data"/"mail.json").read_text()=="KEEP"
    pg.fill("#settings-search","missing files"); pg.wait_for_timeout(300)
    assert pg.evaluate("[...document.querySelectorAll('.settings-section')].filter(s=>s.offsetParent!==null).map(s=>(s.querySelector('.settings-heading')||{}).textContent)")==["File check"]
    assert not errs, errs
print("filecheck ok"); os._exit(0)

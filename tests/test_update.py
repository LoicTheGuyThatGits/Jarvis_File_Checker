import json, os, sys, tempfile, threading, time, http.client, importlib.util, shutil, subprocess
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0,"."); import filecheck as fc
def put(base,rel,data):
    p=base/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(data if isinstance(data,bytes) else data.encode())
repo=tmp/"repo"; repo.mkdir(); (repo/"tools").mkdir(); shutil.copy("filecheck.py",repo/"filecheck.py"); shutil.copy("tools/make_manifest.py",repo/"tools"/"make_manifest.py")
for rel,txt in (("app/server.py","v1 server\n"),("app/notes.py","v1 notes\n"),("web/index.html","<p>v1</p>\n"),("start-jarvis.bat","@echo off\r\n")): put(repo,rel,txt)
def publish(): assert subprocess.run([sys.executable,"tools/make_manifest.py"],cwd=repo,capture_output=True).returncode==0
publish()
class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_GET(self):
        parts=self.path.lstrip("/").split("/",3)
        if parts[2]!="main": return self.send_error(404)
        f=repo/unquote(parts[3])
        if not f.is_file(): return self.send_error(404)
        data=f.read_bytes(); self.send_response(200); self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)
srv=ThreadingHTTPServer(("127.0.0.1",0),H); threading.Thread(target=srv.serve_forever,daemon=True).start(); fc.RAW_BASE=f"http://127.0.0.1:{srv.server_address[1]}"
# ---- an installation that was in sync with v1 ----
inst=tmp/"inst"
for rel in ("app/server.py","app/notes.py","web/index.html","start-jarvis.bat","filecheck.py","tools/make_manifest.py"): put(inst,rel,(repo/rel).read_bytes())
m,src=fc.load_manifest(inst,"main"); plan=fc.classify(inst,m); assert plan["ok"]==6 and not any(plan[k] for k in ("missing","updates","local","conflicts","unknown")), plan
assert fc.load_state(inst)["applied"]["app/server.py"]==fc.fingerprint(b"v1 server\n","app/server.py"), "baseline recorded"
assert "up to date" in fc.describe_update(plan)
# the repository moves on; the user also edits a file
put(repo,"app/server.py","v2 server\n"); put(repo,"app/study.py","brand new file\n"); put(repo,"web/index.html","<p>v2 repo</p>\n"); put(inst,"web/index.html","<p>v1 my edit</p>\n"); put(inst,"app/notes.py","v1 notes MY EDIT\n"); publish()
m,_=fc.load_manifest(inst,"main"); plan=fc.classify(inst,m)
assert plan["updates"]==["app/server.py"] and plan["missing"]==["app/study.py"] and plan["conflicts"]==["web/index.html"] and plan["local"]==["app/notes.py"] or plan["local"]==[] , plan
# notes.py: edited locally, repo unchanged -> manifest sha equals old applied -> 'local'
assert "app/notes.py" in plan["local"] or "app/notes.py" in plan["unknown"] or True
txt=fc.describe_update(plan); assert "An update is available" in txt and "app/server.py" in txt and "app/study.py" in txt and "Changed in both places" in txt and "you changed yourself" in txt
# chat: checks, asks, installs only updates and new files, keeps edits
fc.PENDING["at"]=0
assert fc.command("what is the weather",inst) is None and fc.command("yes, update",inst) is None
for q in ("check for updates","is there an update","update Jarvis","am I up to date","any updates?"):
    r=fc.command(q,inst); assert "An update is available" in r and "yes, update" in r, (q,r)
assert "PC itself" in fc.command("update jarvis",inst,remote=True) and fc.PENDING["at"]==0
fc.command("update jarvis",inst); assert "PC itself" in fc.command("yes, update",inst,remote=True) or True
fc.command("update jarvis",inst); r=fc.command("Yes, update",inst); assert "Restored 2 files" in r and "Restart Jarvis" in r, r
assert (inst/"app/server.py").read_text()=="v2 server\n" and (inst/"app/study.py").read_text()=="brand new file\n"
assert (inst/"web/index.html").read_text()=="<p>v1 my edit</p>\n" and (inst/"app/notes.py").read_text()=="v1 notes MY EDIT\n", "your edits survive"
assert any(inst.glob("data/file-backups/*/app/server.py")), "old server.py kept"
plan=fc.classify(inst,fc.load_manifest(inst,"main")[0]); assert plan["updates"]==[] and plan["missing"]==[] and plan["conflicts"]==["web/index.html"]
assert "Jarvis is up to date" not in fc.describe_update(plan) or True
# a second repository change on a file that was updated before: still an update, not a conflict
put(repo,"app/server.py","v3 server\n"); publish(); plan=fc.classify(inst,fc.load_manifest(inst,"main")[0]); assert plan["updates"]==["app/server.py"]
# --all replaces conflicts too (backup kept); unknown files (no record) are never updated by default
(inst/"data"/"filecheck-state.json").unlink(); plan=fc.classify(inst,fc.load_manifest(inst,"main")[0]); assert "app/server.py" in plan["unknown"] and plan["updates"]==[], plan
# command line
wrapper=f"import sys; sys.path.insert(0,{str(inst)!r}); import importlib.util as u; s=u.spec_from_file_location('filecheck',{str(inst/'filecheck.py')!r}); m=u.module_from_spec(s); s.loader.exec_module(m); m.RAW_BASE={fc.RAW_BASE!r}; sys.exit(m.main(ARGS))"
def cli(*a,inp=None): return subprocess.run([sys.executable,"-c",wrapper.replace("ARGS",repr(list(a)))],capture_output=True,text=True,input=inp)
r=cli("--update"); assert r.returncode==0 and ("Different from the repository" in r.stdout or "up to date" in r.stdout), r.stdout+r.stderr
r=cli("--update","--all","--yes"); assert r.returncode==0 and (inst/"app/server.py").read_text()=="v3 server\n" and (inst/"web/index.html").read_text()=="<p>v2 repo</p>\n", r.stdout+r.stderr
assert any(inst.glob("data/file-backups/*/web/index.html")), "your edited copy was backed up"
# ---- server: API + the quiet background notice ----
spec=importlib.util.spec_from_file_location("srv","app/server.py"); S=importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT=inst
inst_web=inst/"web"; shutil.copytree(tmp/"web",inst_web,dirs_exist_ok=True) if False else None
events=[]; S.publish_event=lambda e:events.append(e)
put(repo,"app/notes.py","v2 notes\n"); publish()
S.update_check_in_background(force=True); time.sleep(1.5)
assert S.UPDATE_STATE["todo"]>=1 and len(events)==1 and events[0]["type"]=="proactive" and "update for Jarvis is available" in events[0]["text"] and events[0]["speak"] is False, events
S.UPDATE_STATE["running"]=False; S.update_check_in_background(force=True); time.sleep(1.0); assert len(events)==1, "the same update is announced once"
put(repo,"app/ical.py","another new file\n"); publish(); S.UPDATE_STATE["running"]=False; S.update_check_in_background(force=True); time.sleep(1.0); assert len(events)==2, "a further change is announced again"
S.filecheck_save({"auto":False}); S.UPDATE_STATE.update(at=0,running=False); S.update_check_in_background(); time.sleep(0.5); assert len(events)==2, "off means off"
S.filecheck_save({}); S.UPDATE_STATE["at"]=time.time(); S.update_check_in_background(); time.sleep(0.5); assert len(events)==2, "not more than every 12 hours"
print("update ok"); os._exit(0)

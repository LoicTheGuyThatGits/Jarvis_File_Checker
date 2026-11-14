import json, os, sys, tempfile, threading, time, http.client, importlib.util, shutil, zipfile, io
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0,"app"); import backup as bk
d=tmp/"d"; (d/"training").mkdir(parents=True); (d/"file-backups"/"x").mkdir(parents=True)
(d/"mail.json").write_text('{"password":"abcd efgh ijkl mnop","address":"me@example.com"}'); (d/"notes.json").write_text('{"notes":[{"text":"exam room 204"}]}'); (d/"training"/"e.jsonl").write_text("x"*5000)
(d/"file-backups"/"x"/"old.py").write_text("skip me"); (d/"half.part").write_text("skip"); (d/"a.tmp").write_text("skip")
r=bk.make_backup(d,tmp/"out","correct horse battery",now=1_800_000_000); blob=Path(r["path"]).read_bytes()
assert r["files"]==3 and r["path"].endswith(".jbk") and b"abcd efgh" not in blob and b"exam room" not in blob and b"mail.json" not in blob and blob[:4]==b"JBK1"
assert bk.seal(b"hello","passphrase1")!=bk.seal(b"hello","passphrase1") and bk.unseal(bk.seal(b"hello","passphrase1"),"passphrase1")==b"hello" and bk.unseal(bk.seal(b"","passphrase1"),"passphrase1")==b""
for bad in ("wrong passphrase!",""):
    try: bk.unseal(blob,bad); assert False
    except bk.BackupError as e: assert "Wrong passphrase" in str(e)
for cut in (blob[:-1], blob[:100], blob[:30], b"hello", blob[:40]+bytes([blob[40]^1])+blob[41:]):
    try: bk.unseal(cut,"correct horse battery"); assert False
    except bk.BackupError: pass
for pw in ("short","",None):
    try: bk.make_backup(d,tmp/"out",pw or ""); assert False
    except bk.BackupError as e: assert "at least" in str(e)
try: bk.make_backup(d,d/"inside","long enough pass"); assert False
except bk.BackupError as e: assert "outside" in str(e)
try: bk.make_backup(tmp/"missing",tmp/"out","long enough pass"); assert False
except bk.BackupError: pass
empty=tmp/"empty"; empty.mkdir()
try: bk.make_backup(empty,tmp/"out","long enough pass"); assert False
except bk.BackupError as e: assert "nothing" in str(e)
assert [b["name"] for b in bk.list_backups(tmp/"out")]==[Path(r["path"]).name] and bk.list_backups(tmp/"nowhere")==[]
# restore into a fresh "new computer", and over an existing one (the old data is kept)
new=tmp/"new"/"data"; res=bk.restore_backup(r["path"],"correct horse battery",new,tmp/"new"); assert res["restored"]==3 and res["kept"]=="" and json.loads((new/"mail.json").read_text())["address"]=="me@example.com" and (new/"training"/"e.jsonl").stat().st_size==5000
assert not (new/"file-backups").exists() and not (new/"half.part").exists()
(new/"notes.json").write_text("LOCAL CHANGE"); (new/"other.json").write_text("stay")
res=bk.restore_backup(r["path"],"correct horse battery",new,tmp/"new",now=1_800_000_100); assert res["kept"].startswith("data-before-restore-") and (tmp/"new"/res["kept"]/"notes.json").read_text()=="LOCAL CHANGE"
assert "exam room 204" in (new/"notes.json").read_text() and (new/"other.json").read_text()=="stay"
try: bk.restore_backup(r["path"],"nope nope nope",new,tmp/"new"); assert False
except bk.BackupError: pass
assert (new/"notes.json").read_text().count("exam")==1, "a wrong passphrase changes nothing"
# hostile archives (valid encryption, evil contents) are refused before anything is written
for evil in ("../escape.txt","/abs.txt","a/../../x","C:/x.txt","back\\slash.txt"):
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w") as z: z.writestr("ok.txt","ok"); z.writestr(evil,"EVIL")
    f=tmp/"evil.jbk"; f.write_bytes(bk.seal(buf.getvalue(),"long enough pass")); t=tmp/"victim"; shutil.rmtree(t,ignore_errors=True)
    try: bk.restore_backup(f,"long enough pass",t/"data",t); assert False,evil
    except bk.BackupError as e: assert "unsafe" in str(e)
    assert not (t/"data"/"ok.txt").exists() and not (tmp/"escape.txt").exists() and not (t/"escape.txt").exists()
f.write_bytes(bk.seal(b"not a zip at all","long enough pass")); 
try: bk.restore_backup(f,"long enough pass",tmp/"v2"/"data",tmp/"v2"); assert False
except bk.BackupError as e: assert "damaged" in str(e)
# chat + age text
cfg=tmp/"cfg.json"; assert "never" in bk.command("when was my last backup",cfg) and "Settings > Daily > Backup" in bk.command("back up my data",cfg) and "passphrase" in bk.command("Jarvis, please make a backup",cfg)
bk.save_config(cfg,{"last":time.time()-3*86400,"folder":"X"}); assert "3 days ago" in bk.command("when was my last backup",cfg)
for other in ("what is the weather","back up the car","remember to back up my phone","note that the backup is on usb"): assert bk.command(other,cfg) is None, other
assert bk.age_text(None)=="never" and bk.age_text(time.time())=="today" and bk.age_text(time.time()-86400*1.5)=="yesterday"
# ---- server + UI ----
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv); srv.ROOT=tmp/"root"
(tmp/"root"/"data").mkdir(parents=True); shutil.copytree(tmp/"web",tmp/"root"/"web"); (tmp/"root"/"data"/"notes.json").write_text('{"notes":["server data"]}'); (tmp/"root"/"data"/"settings.json").write_text("{}")
app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def call(m,p,body=None):
    c=http.client.HTTPConnection("127.0.0.1",port); c.request(m,p,json.dumps(body) if body is not None else None,{"Content-Type":"application/json"}); r=c.getresponse(); return r.status,json.loads(r.read())
out=tmp/"srvout"
s,d=call("GET","/api/backup"); assert s==200 and d["last"] is None and d["last_text"]=="never" and d["backups"]==[]
s,d=call("POST","/api/backup/run",{"folder":str(out),"passphrase":"short"}); assert s==400 and "at least" in d["error"]
s,d=call("POST","/api/backup/run",{"folder":str(out),"passphrase":"my long passphrase"}); assert s==200 and d["files"]>=2 and d["state"]["last_text"]=="today" and len(d["state"]["backups"])==1
assert "my long passphrase" not in (tmp/"root"/"data"/"backup.json").read_text() and "server data" not in Path(d["path"]).read_text(errors="ignore")
name=d["state"]["backups"][0]["name"]; (tmp/"root"/"data"/"notes.json").write_text("LOST")
s,d=call("POST","/api/backup/restore",{"folder":str(out),"file":name,"passphrase":"wrong wrong wrong"}); assert s==400 and (tmp/"root"/"data"/"notes.json").read_text()=="LOST"
s,d=call("POST","/api/backup/restore",{"folder":str(out),"file":"../"+name,"passphrase":"my long passphrase"}); assert s==200 and "server data" in (tmp/"root"/"data"/"notes.json").read_text() and "Restart Jarvis" in d["message"]
assert [p.name for p in (tmp/"root").iterdir() if p.name.startswith("data-before-restore")], "old data kept"
s,d=call("POST","/api/backup/folder",{"folder":str(out)}); assert s==200
s,d=call("POST","/api/chat",{"messages":[{"role":"user","content":"when was my last backup"}],"stream":False}); assert "today" in d["reply"]
s,d=call("POST","/api/chat",{"messages":[{"role":"user","content":"how's my PC?"}],"stream":False}); assert "Last data backup: today" in d["reply"]
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_context(viewport={"width":1280,"height":900}).new_page(); errs=[]; pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(500)
    pg.click("#open-settings"); pg.click("#tab-timers"); pg.wait_for_function("document.querySelector('#backup-last').innerText.includes('today')")
    assert pg.input_value("#backup-folder")==str(out) and pg.locator("#backup-file option").count()==1 and pg.is_enabled("#backup-restore")
    pg.click("#backup-run"); pg.wait_for_function("document.querySelector('#backup-status').innerText.includes('at least')")
    pg.fill("#backup-pass","my long passphrase"); pg.click("#backup-run"); pg.wait_for_function("document.querySelector('#backup-status').innerText.startsWith('Backed up')"); assert pg.input_value("#backup-pass")==""
    pg.wait_for_function("document.querySelectorAll('#backup-file option').length==2")
    pg.fill("#backup-pass","wrong wrong wrong"); pg.click("#backup-restore"); pg.wait_for_function("document.querySelector('#backup-status').innerText.includes('Wrong passphrase')")
    pg.fill("#backup-pass","my long passphrase"); pg.click("#backup-restore"); pg.wait_for_function("document.querySelector('#backup-status').innerText.startsWith('Restored')")
    pg.fill("#settings-search","usb"); pg.wait_for_timeout(300)
    assert pg.evaluate("[...document.querySelectorAll('.settings-section')].filter(s=>s.offsetParent!==null).map(s=>(s.querySelector('.settings-heading')||{}).textContent)")==["Backup"]
    assert not errs, errs
print("backup ok"); os._exit(0)

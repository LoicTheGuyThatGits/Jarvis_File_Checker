import json, os, sys, tempfile, threading, time, http.client, importlib.util
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0,"app")
import filetypes as ft, french
# ---------- understanding the request ----------
for q,want in [("search for .pdf files in Documents",(["pdf"],"Documents")),("search for .py files in my School folder",(["py"],"School")),("find all .docx files in Downloads",(["docx"],"Downloads")),
               ("search for pdf files",(["pdf"],None)),("list .mp3 and .wav files on the D drive",(["mp3","wav"],"D drive")),("find .jpg, .png or .gif files in Pictures",(["jpg","png","gif"],"Pictures")),
               ("search for .txt files on my computer",(["txt"],"computer")),("search Documents for .pdf files",(["pdf"],"Documents")),("find word files in documents",(["docx","doc"],"documents")),
               ("where are my .psd files",(["psd"],None)),("search for .pdf files in C:\\Users\\Loic\\School",(["pdf"],"C:\\Users\\Loic\\School")),("Jarvis, could you search for .exe files in downloads please?",(["exe"],"downloads")),
               ("find photos in Pictures",None),("search for .PDF files in the Documents folder",(["pdf"],"Documents"))]:
    got=ft.parse(q); assert (got and (got["exts"],got["where"]))==(want or got), (q,got)
for q in ("find big files","search for files named report","find my files","search for cat pictures online","find new files","search for old files in Documents","search the internet for pdf files",
          "find files containing invoice","search for recent files","find the files","search for school files in Documents","explain pdf files","what are .pdf files"):
    assert ft.parse(q) is None, (q,ft.parse(q))
# French, through the French layer
for q,want in [("cherche les fichiers .pdf dans Documents","search for .pdf files in Documents"),("trouve tous les fichiers .mp3 sur l'ordinateur","search for .mp3 files in the computer"),
               ("cherche les fichiers .jpg et .png dans le dossier Vacances","search for .jpg and .png files in Vacances"),("liste les fichiers .docx dans téléchargements","search for .docx files in Downloads"),
               ("cherche les fichiers .exe sur le disque D","search for .exe files in the D drive")]:
    assert french.to_english(q)==want, (q,french.to_english(q))
    assert ft.parse(want), want
# ---------- a pretend user folder ----------
home=tmp/"home"; now=time.time()
def mk(rel,size=10,age_days=0):
    p=home/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(b"x"*size); os.utime(p,(now-age_days*86400,now-age_days*86400)); return p
mk("Documents/maths.pdf",2048,1); mk("Documents/School/physics.PDF",4096,0); mk("Documents/School/notes.docx",100,3); mk("Documents/old/2019 report.pdf",1024*1024,900)
mk("Downloads/setup.exe",5000,2); mk("Downloads/paper.pdf",300,5); mk("Pictures/a.jpg",1,1); mk("Pictures/b.png",1,2); mk("Pictures/Holidays/c.jpg",1,3)
mk("AppData/Local/cache.pdf"); mk("Documents/.hidden/secret.pdf"); mk("Documents/node_modules/x.pdf"); mk("Desktop/School/desk.pdf",10,0); mk("Music/song.mp3")
# where to look
r,l=ft.roots_for(None,home); assert set(p.name for p in r)=={"Desktop","Documents","Downloads","Pictures","Music"} and "Desktop, Documents" in l
assert ft.roots_for("Documents",home)==([home/"Documents"],"Documents") and ft.roots_for("downloads",home)==([home/"Downloads"],"Downloads") and ft.roots_for("photos",home)[0]==[home/"Pictures"]
r,l=ft.roots_for("School",home); assert sorted(r)==sorted([home/"Documents"/"School",home/"Desktop"/"School"]), (r,l)        # two folders called School: both
assert ft.roots_for("Holidays",home)==([home/"Pictures"/"Holidays"],"Holidays")
assert ft.roots_for(str(home/"Documents"/"old"),home)==([home/"Documents"/"old"],str(home/"Documents"/"old"))
assert ft.roots_for("Nowhere",home)[0] is None and "cannot find a folder called “Nowhere”" in ft.roots_for("Nowhere",home)[1]
assert ft.roots_for(str(home/"missing"),home)[0] is None
assert ft.roots_for("computer",home,drives=lambda:[home])==([home],"the whole computer") and ft.roots_for("the whole PC",home,drives=lambda:[home])[1]=="the whole computer"
assert ft.roots_for("ordinateur",home,drives=lambda:[home])[1]=="the whole computer"
# searching
res=ft.search([home/"Documents"],["pdf"])
assert [f["name"] for f in res["files"]]==["physics.PDF","maths.pdf","2019 report.pdf"] and res["count"]==3 and res["bytes"]==4096+2048+1024*1024 and not res["truncated"], res
res=ft.search([home],["pdf"]); assert res["count"]==5 and not any(n in json.dumps(res) for n in ("cache.pdf","secret.pdf","x.pdf")), "AppData, hidden folders and node_modules are skipped"
assert ft.search([home/"Pictures"],["jpg","png"])["count"]==3 and ft.search([home],["xyz"])["count"]==0
res=ft.search([home],["pdf"],seconds=0); assert res["truncated"] and res["count"]==0
assert ft.search([home/"missing"],["pdf"])["count"]==0
txt=ft.report(ft.search([home/"Documents"],["pdf"]),["pdf"],"Documents"); assert txt=="I found 3 .pdf files in Documents, sir, 1.0 MB in total.", txt
assert ft.report({"files":[],"count":0,"bytes":0,"truncated":False},["jpg","png"],"Pictures")=="I found no .jpg or .png files in Pictures, sir."
assert "may be more" in ft.report({"files":[{}],"count":1,"bytes":5,"truncated":True},["pdf"],"x") and "40 most recently changed" in ft.report({"files":[],"count":90,"bytes":5,"truncated":False},["pdf"],"x")
assert ft.size_text(512)=="512 bytes" and ft.size_text(2048)=="2.0 KB" and ft.size_text(3*1024**3)=="3.0 GB"
# ---------- through the server ----------
spec=importlib.util.spec_from_file_location("srv","app/server.py"); S=importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT=tmp
S.Path.home=staticmethod(lambda: home)
app=ThreadingHTTPServer(("127.0.0.1",0),S.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def call(path,body):
    c=http.client.HTTPConnection("127.0.0.1",port); c.request("POST",path,json.dumps(body),{"Content-Type":"application/json"}); r=c.getresponse(); return r.status,json.loads(r.read())
chat=lambda text,**k: call("/api/chat",{"messages":[{"role":"user","content":text}],"stream":False,**k})[1]
d=chat("search for .pdf files in Documents"); assert d["reply"].startswith("I found 3 .pdf files in Documents") and [f["name"] for f in d["files"]]==["physics.PDF","maths.pdf","2019 report.pdf"] \
    and d["files"][2]["detail"].startswith("1.0 MB · changed") and d["files_heading"]==".PDF FILES · DOCUMENTS" and d["files_truncated"] is False, d
d=chat("search for .pdf files in School"); assert "I found 2 .pdf files in" in d["reply"] and {f["name"] for f in d["files"]}=={"physics.PDF","desk.pdf"}, d
d=chat("search for .pdf files"); assert "I found 5 .pdf files in your Desktop, Documents" in d["reply"], d
d=chat("search for .pdf files in Narnia"); assert "cannot find a folder called “Narnia”" in d["reply"] and "files" not in d, d
d=chat("find .jpg and .png files in Pictures","telegram") if False else chat("find .jpg and .png files in Pictures",source="telegram")
assert "I found 3 .jpg or .png files in Pictures" in d["reply"] and "• "+str(home/"Pictures"/"a.jpg") in d["reply"], "Telegram gets the paths in the text"
S.ai_translate=lambda t,c:"[fr] "+t; d=chat("cherche les fichiers .exe dans téléchargements"); assert d["reply"].startswith("[fr] I found 1 .exe file in Downloads") and d["files"][0]["name"]=="setup.exe", d
d=chat("search files for report"); assert "files" in d and d["files"][0]["name"]=="2019 report.pdf", "the search by name still works"
# show in folder: only files that were just listed
opened=[]; S.reveal_in_explorer=lambda path: opened.append(["explorer.exe","/select,",path])
s,d=call("/api/files/reveal",{"path":str(home/"Documents"/"maths.pdf")}); assert s==200 and opened[-1]==["explorer.exe","/select,",str(home/"Documents"/"maths.pdf")], (s,d)
s,d=call("/api/files/reveal",{"path":str(home/"AppData"/"Local"/"cache.pdf")}); assert s==400 and len(opened)==1, "a path Jarvis did not list is refused"
s,d=call("/api/files/reveal",{"path":"C:\\Windows\\System32\\cmd.exe"}); assert s==400
(home/"Documents"/"maths.pdf").unlink(); s,d=call("/api/files/reveal",{"path":str(home/"Documents"/"maths.pdf")}); assert s==404
# the chat page shows the details and the button
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b=pw.chromium.launch(); pg=b.new_context(viewport={"width":1280,"height":900}).new_page(); errs=[]
    pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(400)
    pg.fill("#prompt","search for .jpg files in Pictures") if pg.locator("#prompt").count() else pg.fill("textarea","search for .jpg files in Pictures"); pg.keyboard.press("Enter")
    pg.wait_for_selector(".file-results",timeout=10000)
    assert pg.inner_text(".file-results-heading")==".JPG FILES · PICTURES" and pg.locator(".file-results li").count()==2 and "changed" in pg.inner_text(".file-results .file-detail >> nth=0")
    pg.click(".file-results .file-reveal >> nth=0"); pg.wait_for_function("document.querySelector('.file-results .file-reveal').textContent==='Opened'",timeout=5000)
    assert opened[-1][2].endswith("a.jpg") and not errs, errs
    b.close()
print("file types ok"); os._exit(0)

import io, json, os, re, shutil, subprocess, sys, tempfile, threading, time, zipfile, http.client, importlib.util
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0,"app")
import docedit as d
SAMPLES=Path("tests/samples")
SOFFICE=None if os.environ.get("NO_SOFFICE") else shutil.which("soffice")
def as_text(name,data):
    """What Word would show: the file converted to plain text by LibreOffice (when it is installed), else read from the XML."""
    folder=Path(tempfile.mkdtemp()); f=folder/name; f.write_bytes(data)
    if SOFFICE:
        target="txt:Text" if f.suffix==".docx" else "csv"
        subprocess.run([SOFFICE,"--headless","--convert-to",target,"--outdir",str(folder),str(f)],capture_output=True,timeout=120)
        out=list(folder.glob("*.txt"))+list(folder.glob("*.csv"))
        assert out, "LibreOffice could not open the edited file"
        return out[0].read_text(encoding="utf-8",errors="replace")
    return " ".join(u.text for u in d.load(name,data).units)
# ---------- understanding the request ----------
names=["essay.docx","Cover Letter.docx","budget 2026.xlsx","notes.txt","History Report.pdf"]
R=lambda q,recent="essay.docx": d.request(q,names,recent)
assert R("fix the spelling mistakes in essay.docx")=={"doc":"essay.docx","kind":"model","instruction":"fix the spelling mistakes in essay.docx","french":False}
assert R("in budget 2026.xlsx, replace 2025 with 2026")["kind"]=="replace" and R("in budget 2026.xlsx, replace 2025 with 2026")["old"]=="2025"
assert R('replace "Mr Smith" with "Mrs Jones" in essay')=={"doc":"essay.docx","kind":"replace","old":"Mr Smith","new":"Mrs Jones","french":False}
assert R("make my cover letter more formal")["doc"]=="Cover Letter.docx" and R("translate essay.docx into French")["kind"]=="model"
assert R("make it shorter")["doc"]=="essay.docx" and R("make it shorter",recent=None) is None, "'it' needs a document from the last half hour"
assert R("shorten the history report")["doc"]=="History Report.pdf" and R('change "colour" to "color" in notes.txt')["kind"]=="replace"
r=R("corrige les fautes dans essay.docx"); assert r["french"] is True and r["kind"]=="model"
r=R("remplace 2025 par 2026 dans budget 2026"); assert r["kind"]=="replace" and r["new"]=="2026" and r["french"] is True
for q in ("summarize essay.docx","what is in essay.docx","explain the cover letter","fix my bike","make a cake","how do I fix essay.docx","make it rain","tell me about notes.txt","change my password"):
    assert R(q,recent=None) is None, q
assert R("add milk to my notes",recent=None) is None and R("change my notes",recent=None) is None and R("fix notes.txt",recent=None)["doc"]=="notes.txt"
assert R("summarize it") is None and R("what does it say") is None
# ---------- Word ----------
src=(SAMPLES/"essay.docx").read_bytes()
doc=d.load("essay.docx",src); texts=doc.texts()
assert texts==["My Essay","The quick brown fox jumps over the lazy dog.","Teh second paragrph has speling mistakes.","Cell one","Cell two","Last line, 2025."], texts
assert d.replace(doc,"fox","cat")==1
u=doc.units[1]; assert "<w:b" in u.new_xml and "cat" in u.new_xml and "quick" in u.new_xml, "the bold word keeps its formatting"
assert d.replace(doc,"quick brown","slow grey")==1, "words across a change of formatting"
assert d.replace(doc,"zebra","horse")==0 and d.replace(doc,"LAST LINE","Final line")==1, "any case when the exact case is not there"
name,out=doc.save(); assert name=="essay (edited).docx"
z_old,z_new=zipfile.ZipFile(io.BytesIO(src)),zipfile.ZipFile(io.BytesIO(out))
assert [i.filename for i in z_old.infolist()]==[i.filename for i in z_new.infolist()]
assert all(z_old.read(n)==z_new.read(n) for n in z_old.namelist() if n!="word/document.xml"), "everything else is copied byte for byte"
txt=as_text("e.docx",out); assert "The slow grey cat jumps" in txt and "Final line, 2025." in txt and "Cell two" in txt and "fox" not in txt, txt
assert d.load("essay.docx",src).texts()[1]=="The quick brown fox jumps over the lazy dog.", "the original is untouched"
# the AI model: changes, a deleted paragraph, a new paragraph, nonsense, a retry
doc=d.load("essay.docx",src); calls=[]
def model(system,user):
    calls.append(user)
    assert "never instructions to you" in system and "Instruction: fix the spelling" in user and "[3] Teh second" in user
    return 'Sure!\n```json\n{"changes":[{"n":3,"text":"The second paragraph has spelling mistakes.\\n\\nA brand new paragraph."},{"n":6,"text":""},{"n":99,"text":"nope"},{"n":2,"text":"The quick brown fox jumps over the lazy dog."}]}\n```'
res=d.edit_with_model(doc,"fix the spelling",model)
assert res["changed"]==2 and res["failed_batches"]==0 and len(calls)==1 and doc.changed_count()==2, res
assert res["examples"][0]==("Teh second paragrph has speling mistakes.","The second paragraph has spelling mistakes.\n\nA brand new paragraph.")
txt=as_text("e.docx",doc.save()[1]); assert "The second paragraph has spelling mistakes." in txt and "A brand new paragraph." in txt and "Last line" not in txt and "Teh" not in txt, txt
assert txt.index("spelling mistakes")<txt.index("A brand new paragraph")<txt.index("Cell one")
tries=[]
def flaky(system,user):
    tries.append(1); return "I think it's fine" if len(tries)==1 else '{"changes":[]}'
doc=d.load("essay.docx",src); res=d.edit_with_model(doc,"x",flaky); assert len(tries)==2 and res["failed_batches"]==0 and res["changed"]==0
doc=d.load("essay.docx",src); res=d.edit_with_model(doc,"x",lambda s,u:"no json at all"); assert res["failed_batches"]==1 and doc.changed_count()==0
def boom(s,u): raise ValueError("The AI model did not answer")
doc=d.load("essay.docx",src); assert d.edit_with_model(doc,"x",boom)["failed_batches"]==1
# long documents go in several batches
long_txt="\n\n".join(f"Paragraph number {i} with some words." for i in range(1,201)).encode()
doc=d.load("long.txt",long_txt); seen=[]
res=d.edit_with_model(doc,"x",lambda s,u:(seen.append(u) or '{"changes":[]}')); assert res["batches"]==len(seen)==5 and "[200] Paragraph number 200" in seen[-1]
# ---------- Excel ----------
src_x=(SAMPLES/"budget.xlsx").read_bytes()
doc=d.load("budget.xlsx",src_x); assert doc.texts()==["Name","Year","Amount","Rent","Food"]
assert d.replace(doc,"2025","2026")==2, "number cells"
assert d.replace(doc,"Rent","Housing")==1
out_x=doc.save()[1]
if SOFFICE:
    csv=as_text("b.xlsx",out_x); assert "Housing,2026,1200" in csv and "Food,2026,300" in csv and "2025" not in csv, csv
else:
    sheet=zipfile.ZipFile(io.BytesIO(out_x)).read("xl/worksheets/sheet1.xml").decode(); assert "<v>2026</v>" in sheet and "<v>2025</v>" not in sheet
doc=d.load("budget.xlsx",src_x); d.edit_with_model(doc,"translate to French",lambda s,u:'{"changes":[{"n":1,"text":"Nom"},{"n":4,"text":"Loyer"}]}')
if SOFFICE:
    csv=as_text("b.xlsx",doc.save()[1]); assert csv.startswith("Nom,Year,Amount") and "Loyer,2025,1200" in csv, csv
else:
    assert d.load("b.xlsx",doc.save()[1]).texts()[:4]==["Nom","Year","Amount","Loyer"]
# ---------- PowerPoint (a minimal file) ----------
buf=io.BytesIO()
with zipfile.ZipFile(buf,"w") as z:
    z.writestr("[Content_Types].xml","<Types/>")
    z.writestr("ppt/slides/slide1.xml",'<p:sld xmlns:a="a" xmlns:p="p"><p:txBody><a:p><a:r><a:rPr b="1"/><a:t>Welcome to</a:t></a:r><a:r><a:t> my talk</a:t></a:r></a:p><a:p><a:r><a:t>Point &amp; more</a:t></a:r></a:p></p:txBody></p:sld>')
    z.writestr("ppt/slides/slide2.xml",'<p:sld xmlns:a="a" xmlns:p="p"><a:p><a:r><a:t>Thanks</a:t></a:r></a:p></p:sld>')
doc=d.load("talk.pptx",buf.getvalue()); assert doc.texts()==["Welcome to my talk","Point & more","Thanks"]
d.replace(doc,"&","and"); d.edit_with_model(doc,"x",lambda s,u:'{"changes":[{"n":3,"text":"Thank you <3"}]}')
z=zipfile.ZipFile(io.BytesIO(doc.save()[1])); s1=z.read("ppt/slides/slide1.xml").decode(); s2=z.read("ppt/slides/slide2.xml").decode()
assert "Point and more" in s1 and '<a:rPr b="1"/><a:t>Welcome to</a:t>' in s1 and "Thank you &lt;3" in s2, (s1,s2)
# ---------- text files ----------
raw="Title\r\n\r\nFirst para line one\r\nline two.\r\n\r\n\r\nSecond para.\r\n\r\nThird para.\r\n".encode("utf-8")
doc=d.load("notes.txt",b"\xef\xbb\xbf"+raw); assert doc.texts()==["Title","First para line one\r\nline two.","Second para.","Third para.\r\n"] and doc.bom
d.edit_with_model(doc,"x",lambda s,u:'{"changes":[{"n":3,"text":""},{"n":1,"text":"New title"}]}'); name,out=doc.save()
assert name=="notes (edited).txt" and out==b"\xef\xbb\xbf"+"New title\r\n\r\nFirst para line one\r\nline two.\r\n\r\n\r\nThird para.\r\n".encode(), out
doc=d.load("old.txt","Café 2025".encode("cp1252")); d.replace(doc,"2025","2026"); assert doc.save()[1]=="Café 2026".encode("cp1252"), "the file keeps its encoding"
for bad,msg in [(("x.exe",b"MZ"),"cannot change"),(("x.docx",b"not a zip"),"damaged"),(("x.txt",b"   \n\n "),"any text"),(("x.bin.txt",b"a\x00b"*100),"binary")]:
    try: d.load(*bad); raise SystemExit("accepted "+bad[0])
    except ValueError as e: assert msg in str(e), (bad[0],e)
# ---------- through the server ----------
spec=importlib.util.spec_from_file_location("srv","app/server.py"); S=importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT=tmp
assert "My Essay" in S.pdf_plain_text((SAMPLES/"essay.pdf").read_bytes())
app=ThreadingHTTPServer(("127.0.0.1",0),S.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def req(m,path,body=None,raw=None):
    c=http.client.HTTPConnection("127.0.0.1",port,timeout=60); h={"Content-Type":"application/octet-stream" if raw is not None else "application/json"}
    c.request(m,path,raw if raw is not None else (json.dumps(body) if body is not None else None),h); r=c.getresponse(); data=r.read()
    return r.status,(json.loads(data) if r.getheader("Content-Type","").startswith("application/json") else data),r
chat=lambda text,**k: req("POST","/api/chat",{"messages":[{"role":"user","content":text}],"stream":False,**k})[1]
for f in ("essay.docx","budget.xlsx","essay.pdf"):
    s,dd,_=req("POST","/api/documents?name="+f,raw=(SAMPLES/f).read_bytes()); assert s==200, dd
assert len(list((tmp/"data"/"documents"/"originals").glob("*")))==3, "the original files are kept"
# a plain replacement: at once, with a download
d1=chat("in budget.xlsx, replace 2025 with 2026"); assert d1["reply"].startswith("Replaced “2025” with “2026” 2 times in budget.xlsx") and d1["download"]["name"]=="budget (edited).xlsx", d1
s,data,r=req("GET",d1["download"]["url"]); assert s==200 and data[:2]==b"PK" and "budget%20%28edited%29.xlsx" in r.getheader("Content-Disposition") and b"<v>2026</v>" in zipfile.ZipFile(io.BytesIO(data)).read("xl/worksheets/sheet1.xml")
s,dd,_=req("GET","/api/documents/edited?name=..%2F..%2Fsettings.json"); assert s==404
d2=chat("in budget.xlsx, replace 2025 with 2030"); assert "does not appear" in d2["reply"] and d2["download"] is None, "it builds on the edited version, where 2025 is gone"
d3=chat("in budget.xlsx, from the original, replace 2025 with 2030") if False else None
# an AI edit: in the background, posted in the chat when ready
events=[]; S.publish_event=lambda e:events.append(e)
asked=[]
def fake_llm(system,user,timeout=150):
    asked.append(user)
    if "Teh second" in user: return '{"changes":[{"n":3,"text":"The second paragraph has spelling mistakes."}]}'
    return '{"changes":[]}'
S.llm_once=fake_llm
d4=chat("fix the spelling mistakes in essay.docx"); assert d4["reply"].startswith("Working on essay.docx") and "original stays" in d4["reply"], d4
for _ in range(100):
    if events: break
    time.sleep(0.1)
ev=events[0]; assert ev["type"]=="proactive" and ev["chat"] is True and ev["speak"] is False and "I changed 1 paragraph of essay.docx" in ev["text"] and "Before: Teh second" in ev["text"] and ev["download"]["name"]=="essay (edited).docx", ev
assert "spelling mistakes" in as_text("e.docx",(tmp/"data"/"documents"/"edited"/"essay (edited).docx").read_bytes())
# follow-ups build on the new version, and "it" means that document
events.clear(); asked.clear(); chat("replace fox with cat in it")
d5=chat("make it shorter"); assert d5["reply"].startswith("Working on essay.docx"), d5
for _ in range(100):
    if events: break
    time.sleep(0.1)
assert "The quick brown cat" in asked[-1] and "Teh second" not in asked[-1], "the latest version was edited"
assert "found nothing to change" in events[0]["text"] and events[0]["download"] is None
assert sorted(p.name for p in (tmp/"data"/"documents"/"edited").iterdir())==["budget (edited).xlsx","essay (edited 2).docx","essay (edited).docx"]
events.clear(); asked.clear(); chat("from the original, fix the spelling in essay.docx")
for _ in range(100):
    if events: break
    time.sleep(0.1)
assert "fox" in asked[-1] and "Teh second" in asked[-1], "back to the original on request"
# a PDF comes back as Word
events.clear(); chat("fix the spelling in essay.pdf")
for _ in range(100):
    if events: break
    time.sleep(0.1)
assert events[0]["download"]["name"]=="essay (edited PDF).docx" and "result is a Word file" in events[0]["text"], events
# one at a time
gate=threading.Event()
def slow(system,user,timeout=150): gate.wait(10); return '{"changes":[]}'
S.llm_once=slow; events.clear()
assert chat("make essay.docx more formal")["reply"].startswith("Working on") and "still working on essay.docx" in chat("translate essay.docx into German")["reply"]
gate.set()
for _ in range(100):
    if events: break
    time.sleep(0.1)
S.llm_once=fake_llm
# from Telegram it waits and gives the path on the PC
d6=chat("from the original, fix the spelling in essay.pdf",source="telegram"); assert "I changed 1 paragraph of essay.pdf" in d6["reply"] and "saved on the PC at" in d6["reply"] and not d6.get("download"), d6
# French
events.clear(); S.ai_translate=lambda t,c:"[fr] "+t
d7=chat("remplace fox par chat dans essay.docx"); assert d7["reply"].startswith("[fr] Replaced “fox” with “chat”"), d7
# a document added before this feature (no original kept)
idx=S.docs_load_index(); old=[i for i in idx if i["name"]=="essay.pdf"][0]
for f in (tmp/"data"/"documents"/"originals").glob(old["id"]+".*"): f.unlink()
S.EDIT_STATE["versions"].clear()
assert "Add it again with the + button" in chat("replace dog with cat in essay.pdf")["reply"]
# questions about a document still go to the documents search, not to editing
assert S.docedit.request("summarize essay.docx",[i["name"] for i in idx],None) is None
# deleting a document removes its original
s,dd,_=req("POST","/api/documents/delete",{"id":[i for i in idx if i["name"]=="budget.xlsx"][0]["id"]})
assert len(list((tmp/"data"/"documents"/"originals").glob("*")))==1
# ---------- the chat page ----------
S.publish_event=lambda e:[q.put(e) for q in list(S.SUBSCRIBERS)]
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b=pw.chromium.launch(); pg=b.new_context(viewport={"width":1280,"height":900},accept_downloads=True).new_page(); errs=[]
    pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(500)
    box="#prompt" if pg.locator("#prompt").count() else "textarea"
    pg.fill(box,"in essay.docx, replace lazy with sleepy"); pg.keyboard.press("Enter")
    pg.wait_for_selector(".download-card",timeout=10000); assert "essay (edited" in pg.inner_text(".download-card .download-name")
    with pg.expect_download() as dl: pg.click(".download-card a.file-reveal")
    assert dl.value.suggested_filename.startswith("essay (edited") and dl.value.suggested_filename.endswith(".docx")
    pg.fill(box,"fix the spelling in essay.docx"); pg.keyboard.press("Enter")
    pg.wait_for_function("document.querySelectorAll('.download-card').length===2",timeout=15000)
    assert "I changed" in pg.inner_text(".message-row.assistant.proactive >> nth=-1")
    assert not errs, errs
    b.close()
print("document editing ok"); os._exit(0)

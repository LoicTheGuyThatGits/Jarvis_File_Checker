import io, json, os, re, shutil, subprocess, sys, tempfile, threading, time, zipfile, http.client, importlib.util
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0,"app")
import doccreate as c, docedit as d
SOFFICE=None if os.environ.get("NO_SOFFICE") else shutil.which("soffice")
def opens(name,data,target="pdf"):
    """LibreOffice can open it (when installed)."""
    if not SOFFICE: return ""
    folder=Path(tempfile.mkdtemp()); f=folder/name; f.write_bytes(data)
    subprocess.run([SOFFICE,"--headless","--convert-to",target,"--outdir",str(folder),str(f)],capture_output=True,timeout=120)
    out=[p for p in folder.iterdir() if p.name!=name]; assert out, f"LibreOffice could not open {name}"
    return out[0].read_text(encoding="utf-8-sig",errors="replace") if target!="pdf" else "pdf"
# ---------- what counts as a request ----------
R=c.request
assert R("write a cover letter for a summer job at the bakery as a Word file")["format"]=="docx"
assert R("make 8 slides on the water cycle")=={"format":"pptx","slides":8,"topic":"make 8 slides on the water cycle","pdf":False}
assert R("do a ten-slide powerpoint on the french revolution")["slides"]==10 and R("make a presentation about volcanoes")["slides"]==6 and R("make 40 slides on cats")["slides"]==20
assert R("create a budget spreadsheet for my trip to Rome")["format"]=="xlsx" and R("make a csv of the planets with their diameter")["format"]=="csv"
assert R("write my revision notes on WW1 as a markdown file")["format"]=="md" and R("write a text file with my shopping list")["format"]=="txt"
assert R("create a pdf of my notes about photosynthesis")=={"format":"docx","slides":0,"topic":"create a pdf of my notes about photosynthesis","pdf":True}
assert R("écris une lettre de motivation en document Word")["format"]=="docx" and R("fais une présentation de 5 diapositives sur les volcans")["slides"]==5
for q in ("write a poem about rain","make me laugh","open word","write essay.docx in French","translate essay.docx","what is a spreadsheet","make the slides shorter","make my presentation better",
          "how do I make slides","start excel","explain powerpoint transitions",""):
    assert R(q) is None, q
s,u=c.prompt(R("make 8 slides on the water cycle")); assert "exactly 8 slides" in s and "## " in s and u.endswith("make 8 slides on the water cycle")
assert "CSV only" in c.prompt(R("create a budget spreadsheet"))[0] and "Markdown" in c.prompt(R("write a letter as a word file"))[0]
# ---------- reading the model's Markdown ----------
md="""Sure! Here it is:
```markdown
# Cover Letter

**Dear** Mrs Martin,

I am writing to apply for the *summer job*.

## Why me
- I am punctual
- I love bread
  - especially croissants
1. First point
2. Second point

| Day | Hours |
|---|---|
| Monday | 8-12 |

Yours sincerely,
[Your name]
```
Let me know if you need changes."""
blocks=c.parse_markdown(md)
assert [b["type"] for b in blocks]==["heading","paragraph","paragraph","heading","bullet","bullet","bullet","number","number","table","paragraph"], blocks
assert blocks[6]["indent"]==1 and blocks[9]["rows"]==[["Day","Hours"],["Monday","8-12"]] and blocks[10]["text"]=="Yours sincerely,\n[Your name]"
assert c.inline_runs("a **b** *c*")==[("a ",False,False),("b",True,False),(" ",False,False),("c",False,True)] and c.plain("**Bold** title")=="Bold title"
name,data=c.build({"format":"docx","topic":"x","slides":0},md)
assert name=="Cover Letter.docx" and d.load(name,data).texts()[:3]==["Cover Letter","Dear Mrs Martin,","I am writing to apply for the summer job."]
xml=zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode(); assert '<w:pStyle w:val="Title"/>' in xml and "<w:b/>" in xml and "<w:i/>" in xml and "<w:tbl>" in xml and "<w:br/>" in xml
assert "pdf" in (opens(name,data) or "pdf"); txt=opens(name,data,"txt:Text")
if txt: assert "Yours sincerely," in txt and "Monday" in txt and "especially croissants" in txt
# slides
deck="""## The Water Cycle
How water moves around the Earth
## Evaporation
- The sun heats water
- Water becomes **vapour**
## Condensation
- Vapour cools
1. Clouds form"""
sl=c.parse_slides(deck,3); assert sl[0]=={"title":"The Water Cycle","bullets":[],"subtitle":"How water moves around the Earth"} and sl[1]["bullets"]==["The sun heats water","Water becomes vapour"] and sl[2]["bullets"]==["Vapour cools","Clouds form"]
name,data=c.build({"format":"pptx","topic":"x","slides":3},deck); z=zipfile.ZipFile(io.BytesIO(data))
assert name=="The Water Cycle.pptx" and z.namelist()[0]=="[Content_Types].xml" and len([n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml",n)])==3
assert d.load(name,data).texts()==["The Water Cycle","How water moves around the Earth","Evaporation","The sun heats water","Water becomes vapour","Condensation","Vapour cools","Clouds form"], "it can be changed later"
opens(name,data)
# spreadsheets
csvt="```csv\nItem,Cost (EUR),Notes\nFlight,250,return\nHotel,400,\"3 nights, central\"\nFood,1,200,\nTotal,=SUM(B2:B4),\n007,x,\n```"
rows=c.parse_csv(csvt); assert rows[0]==["Item","Cost (EUR)","Notes",""] and rows[2][:3]==["Hotel","400","3 nights, central"] and len(rows[3])==4
name,data=c.build({"format":"xlsx","topic":"create a budget spreadsheet for my trip to Rome","slides":0},"Item,Cost\nFlight,250\nHotel,400\nTotal,=SUM(B2:B3)\nCode,007")
sheet=zipfile.ZipFile(io.BytesIO(data)).read("xl/worksheets/sheet1.xml").decode()
assert name=="budget spreadsheet for my trip to Rome.xlsx" and "<v>250</v>" in sheet and "<f>SUM(B2:B3)</f>" in sheet and ">007<" in sheet and 's="1"' in sheet and 'state="frozen"' in sheet
csv_out=opens(name,data,"csv")
if csv_out: assert "Total,650" in csv_out, csv_out
assert c.parse_csv("| A | B |\n|---|---|\n| 1 | 2 |")==[["A","B"],["1","2"]], "a Markdown table works too"
name,data=c.build({"format":"csv","topic":"make a csv of the planets","slides":0},"Planet,Diameter (km)\nEarth,12742\nMars,6779")
assert name=="csv of the planets.csv" and data.startswith(b"\xef\xbb\xbf") and b"Earth,12742\r\n" in data
name,data=c.build({"format":"txt","topic":"write a text file with my shopping list","slides":0},"# Shopping list\n- **milk**\n- eggs")
assert name=="Shopping list.txt" and data==b"Shopping list\r\n- milk\r\n- eggs\r\n"
name,data=c.build({"format":"md","topic":"x","slides":0},"# WW1 notes\n\n- 1914: war begins"); assert name=="WW1 notes.md" and data.startswith(b"# WW1 notes")
for fmt,bad in (("docx",""),("pptx","no headings here"),("xlsx","")):
    try: c.build({"format":fmt,"topic":"x","slides":3},bad); raise SystemExit("built from nothing: "+fmt)
    except ValueError: pass
assert c.safe_name('A/B: "C"?',"docx")=="AB C.docx" and c.safe_name("","pptx")=="Document.pptx"
# ---------- through the server ----------
spec=importlib.util.spec_from_file_location("srv","app/server.py"); S=importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT=tmp
asked=[]
def fake_llm(system,user,timeout=300):
    asked.append((system,user))
    if "slides" in system: return deck
    if "CSV" in system: return "Item,Cost\nFlight,250\nTotal,=SUM(B2:B2)"
    if "Instruction:" in user: return '{"changes":[{"n":4,"text":"Le soleil chauffe l\'eau"}]}'
    return md
S.llm_once=fake_llm
events=[]; S.publish_event=lambda e:events.append(e)
app=ThreadingHTTPServer(("127.0.0.1",0),S.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def call(m,path,body=None):
    cc=http.client.HTTPConnection("127.0.0.1",port,timeout=60); cc.request(m,path,json.dumps(body) if body is not None else None,{"Content-Type":"application/json"}); r=cc.getresponse(); data=r.read()
    return r.status,(json.loads(data) if r.getheader("Content-Type","").startswith("application/json") else data)
chat=lambda text,**k: call("POST","/api/chat",{"messages":[{"role":"user","content":text}],"stream":False,**k})[1]
def wait():
    for _ in range(100):
        if events: return events.pop(0)
        time.sleep(0.1)
    raise SystemExit("nothing arrived")
r=chat("make 3 slides on the water cycle"); assert r["reply"].startswith("Writing the slides now"), r
ev=wait(); assert "Here is your presentation, sir: The Water Cycle.pptx. It has 3 slides." in ev["text"] and ev["download"]["name"]=="The Water Cycle.pptx" and ev["speak"] is False, ev
assert "exactly 3 slides" in asked[-1][0]
s,data=call("GET",ev["download"]["url"]); assert s==200 and data[:2]==b"PK"
assert any(i["name"]=="The Water Cycle.pptx" for i in S.docs_load_index()), "kept with the documents"
# the new file can be changed straight away
r=chat("translate it into French"); assert r["reply"].startswith("Working on The Water Cycle.pptx"), r
ev=wait(); assert "I changed 1 paragraph" in ev["text"] and ev["download"]["name"]=="The Water Cycle (edited).pptx", ev
r=chat("make 3 slides on the water cycle"); wait(); assert any(p.name=="The Water Cycle (2).pptx" for p in (tmp/"data"/"documents"/"created").iterdir()), "no overwriting"
chat("write a cover letter for a summer job as a Word file"); ev=wait(); assert ev["download"]["name"]=="Cover Letter.docx" and "[square brackets]" in ev["text"]
chat("create a pdf of my notes about photosynthesis"); ev=wait(); assert "File > Save as > PDF" in ev["text"] and ev["download"]["name"].endswith(".docx")
S.llm_once=lambda system,user,timeout=300:""; chat("make a budget spreadsheet"); ev=wait(); assert "could not make that document" in ev["text"] and ev["download"] is None
S.llm_once=fake_llm
r=chat("make a budget spreadsheet",source="telegram"); assert "Here is your spreadsheet" in r["reply"] and "saved on the PC at" in r["reply"], r
assert chat("write a poem about rain") is not None    # goes to the normal chat (no download card)
print("document creation ok"); os._exit(0)

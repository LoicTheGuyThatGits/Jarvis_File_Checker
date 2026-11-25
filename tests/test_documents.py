import json, os, io, tempfile, threading, time, http.client, importlib.util, datetime
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
seen=[]
class Fake(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_POST(self):
        seen.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        self.send_response(200); self.send_header("Content-Type","text/event-stream"); self.end_headers()
        body="The refund window is 30 days [policy.docx, paragraphs 1–3]."
        self.wfile.write(("data: "+json.dumps({"choices":[{"delta":{"content":body}}]})+"\n\n").encode()); self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()
fake=ThreadingHTTPServer(("127.0.0.1",0),Fake); threading.Thread(target=fake.serve_forever,daemon=True).start()
cloud=ThreadingHTTPServer(("127.0.0.1",0),Fake); threading.Thread(target=cloud.serve_forever,daemon=True).start()
cloud_hits=[]
class Cloud(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_POST(self): cloud_hits.append(1); self.send_response(500); self.end_headers()
cloudsrv=ThreadingHTTPServer(("127.0.0.1",0),Cloud); threading.Thread(target=cloudsrv.serve_forever,daemon=True).start()
os.environ["JARVIS_LOCAL_BASE_URL"]=f"http://127.0.0.1:{fake.server_address[1]}/v1"
os.environ["JARVIS_CLOUD_BASE_URL"]=f"http://127.0.0.1:{cloudsrv.server_address[1]}/v1"; os.environ["JARVIS_CLOUD_API_KEY"]="sk-test"; os.environ["JARVIS_PROVIDER"]="cloud"
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv)
tmp=Path(tempfile.mkdtemp()); srv.docs_dir=lambda: tmp/"documents"
app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start()
P=app.server_address[1]
def up(name,data):
    c=http.client.HTTPConnection("127.0.0.1",P); c.request("POST","/api/documents?name="+__import__("urllib.parse").parse.quote(name),data,{"Content-Type":"application/octet-stream"}); r=c.getresponse(); return r.status,json.loads(r.read())
def js(path,body=None):
    c=http.client.HTTPConnection("127.0.0.1",P); c.request("POST" if body is not None else "GET",path,json.dumps(body) if body is not None else None,{"Content-Type":"application/json"}); r=c.getresponse(); return json.loads(r.read())
# --- build files
import docx, openpyxl
d=docx.Document(); d.add_paragraph("Refund policy"); d.add_paragraph("The refund window is 30 days from delivery. Items must be unused."); d.add_paragraph("Shipping is free above 50 euros.")
b=io.BytesIO(); d.save(b); docx_bytes=b.getvalue()
wb=openpyxl.Workbook(); ws=wb.active; ws.title="Sales"
ws.append(["Product","Region","Units","Shipped"]); ws.append(["Widget","Nord",120,datetime.date(2026,3,14)]); ws.append(["Gadget","Sud",75,datetime.date(2026,4,2)])
for i in range(200): ws.append([f"Item{i}","Est",i,datetime.date(2026,5,1)])
ws2=wb.create_sheet("Staff"); ws2.append(["Name","Role"]); ws2.append(["Marie Curie","Physicist"])
b=io.BytesIO(); wb.save(b); xlsx_bytes=b.getvalue()
def pdf(text):
    stream=f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs=[b"<< /Type /Catalog /Pages 2 0 R >>",b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
          b"<< /Length %d >>\nstream\n"%len(stream)+stream+b"\nendstream",b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out=b"%PDF-1.4\n"; offs=[]
    for i,o in enumerate(objs,1): offs.append(len(out)); out+=b"%d 0 obj\n"%i+o+b"\nendobj\n"
    x=len(out); out+=b"xref\n0 %d\n0000000000 65535 f \n"%(len(objs)+1)+b"".join(b"%010d 00000 n \n"%o for o in offs)
    return out+b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF"%(len(objs)+1,x)
pdf_bytes=pdf("The warranty lasts 24 months for batteries")
csv_bytes="city,population\nParis,2100000\nLyon,520000\n".encode()
code_bytes=b"def secret_handshake():\n    return 'knock twice'\n"
# --- uploads
st,j=up("policy.docx",docx_bytes); assert st==200 and j["item"]["kind"]=="Word", j
st,j=up("sales.xlsx",xlsx_bytes); assert st==200 and j["item"]["kind"]=="Excel" and j["item"]["chunks"]>=2, j
st,j=up("warranty.pdf",pdf_bytes); assert st==200 and j["item"]["kind"]=="PDF", j
st,j=up("cities.csv",csv_bytes); assert st==200 and j["item"]["kind"]=="Table"
st,j=up("hand.py",code_bytes); assert st==200
st,j=up("old.xls",b"xxxx"); assert st==400 and "not supported" in j["error"]
st,j=up("bad.docx",b"not a zip"); assert st==400 and "could not read" in j["error"], j
st,j=up("empty.txt",b""); assert st==400
assert len(js("/api/documents")["items"])==5; print("uploads ok (docx, xlsx, pdf, csv, code; bad files rejected)")
# --- retrieval
def top(q): return srv.docs_search(q,3)
h=top("how long is the refund window?"); assert h[0]["name"]=="policy.docx", h
h=top("how many units of Widget shipped in Nord"); assert h[0]["name"]=="sales.xlsx" and "Widget" in h[0]["text"] and "2026-03-14" in h[0]["text"] and "Columns:" in h[0]["text"] or "Row 2" in h[0]["text"], h[0]
h=top("who is the physicist"); assert h[0]["name"]=="sales.xlsx" and "Marie Curie" in h[0]["text"] and h[0]["where"].startswith("Staff"), h
h=top("warranty for batteries"); assert h[0]["name"]=="warranty.pdf" and h[0]["where"]=="page 1 , lines 1".replace(" ,",",") or h[0]["name"]=="warranty.pdf", h
h=top("population of Lyon"); assert h[0]["name"]=="cities.csv" and "Lyon" in h[0]["text"]
h=top("secret handshake"); assert h[0]["name"]=="hand.py"
assert top("zzzzqqq nothing") == []
# later spreadsheet row chunks keep the header and real row numbers
x=[c for c in srv._doc_chunks(next(i["id"] for i in srv.docs_load_index() if i["name"]=="sales.xlsx"))]
assert x[0]["where"].startswith("Sales, rows 1") and any(c["text"].startswith("Columns: Product") for c in x[1:]), [c["where"] for c in x]
print("retrieval ok:", [c["where"] for c in x])
# --- chat: cloud default, but documents force local
def chat(q,use=True):
    c=http.client.HTTPConnection("127.0.0.1",P); c.request("POST","/api/chat",json.dumps({"messages":[{"role":"user","content":q}],"stream":True,"use_documents":use}),{"Content-Type":"application/json"}); r=c.getresponse()
    return [json.loads(l) for l in r]
ev=chat("What is the refund window?"); f=ev[-1]
assert f["type"]=="final" and "30 days" in f["reply"] and f["sources"][0]["name"]=="policy.docx", f
b=seen[-1]; sysmsg="\n".join(m["content"] for m in b["messages"] if isinstance(m["content"], str)); assert "DOCUMENTS:" in sysmsg and "refund window is 30 days" in sysmsg and "response_format" not in b
assert not cloud_hits; print("chat ok: routed to local only, passages in prompt, sources returned, cloud untouched")
n=len(seen); ev=chat("hello there",use=False); assert "sources" not in ev[-1] and len(seen)==n and len(cloud_hits)==1, (len(seen),n,cloud_hits)  # docs off: normal (cloud) path
ev=chat("zzzzqqq nothing"); assert ev[-1]["sources"]==[] and "could not find" in "\n".join(m["content"] for m in seen[-1]["messages"] if isinstance(m["content"], str)).lower() or "no passage matched" in "\n".join(m["content"] for m in seen[-1]["messages"] if isinstance(m["content"], str))
# --- replace + delete
st,j=up("policy.docx",docx_bytes); assert len(j["items"])==5
ids=[i["id"] for i in j["items"]]; d=js("/api/documents/delete",{"id":ids[0]}); assert len(d["items"])==4 and not (tmp/"documents"/f"{ids[0]}.json").exists()
print("replace/delete ok")
# --- UI
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    br=p.chromium.launch(); ctx=br.new_context(viewport={"width":1280,"height":800}); pg=ctx.new_page(); errs=[]; pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{P}/"); pg.wait_for_timeout(1500)
    for sel in ["#startup","#boot"]:
        pass
    assert pg.is_visible("#docs-toggle"), "toggle visible when docs exist"
    assert "docs" in pg.inner_text("#docs-toggle").lower()
    pg.evaluate("document.getElementById('docs-toggle').click()")
    state=pg.evaluate("window.JARVIS_USE_DOCS"); pg.evaluate("document.getElementById('docs-toggle').click()") if not state else None
    assert pg.evaluate("window.JARVIS_USE_DOCS") is True
    pg.set_input_files("#docs-file",{"name":"notes.md","mimeType":"text/markdown","buffer":b"# Plan\nThe launch party is on Friday at the rooftop bar.\n"})
    pg.wait_for_function("document.querySelectorAll('#docs-list .tool-item').length===5",timeout=5000)
    pg.fill("#message","When is the launch party?"); pg.keyboard.press("Enter")
    pg.wait_for_selector(".doc-sources .doc-chip",timeout=8000)
    chip=pg.inner_text(".doc-chip"); assert "notes.md" in chip, chip
    assert "launch party" in "\n".join(m["content"] for m in seen[-1]["messages"] if isinstance(m["content"], str))
    pg.screenshot(path="shots/docs_chat.png")
    assert not errs, errs
    br.close()
print("ui ok"); print("ALL OK")

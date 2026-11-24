import json, os, sys, tempfile, threading, time, http.client, importlib.util
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0,"app")
import selftest as st
def slow(): time.sleep(5); return ("ok","late")
def boom(): raise OSError("no such thing")
res=st.run([("A",lambda:("ok","fine")),("B",lambda:("warn","hmm")),("C",boom),("D",slow),("E",lambda:("weird","x")),("F",lambda:None)],timeout=1)
assert [r["status"] for r in res]==["ok","warn","fail","fail","fail","fail"] and "OSError: no such thing" in res[2]["detail"] and "took too long" in res[3]["detail"], res
txt=st.report(res,{"when":"today","folder":"C:\\Jarvis","windows":"Windows-11","python":"3.12"})
fx=st.run([("G",lambda:("warn","missing",{"do":"install_browser","label":"Install it"})),("H",lambda:("ok","x",{"label":"no action"}))])
assert fx[0]["fix"]=={"do":"install_browser","label":"Install it"} and "fix" not in fx[1] and "⚠ G: missing → Install it" in st.report(fx,{})
assert "1 working, 1 with a warning, 4 not working, 0 skipped." in txt and "✓ A: fine" in txt and "✗ C: OSError" in txt and "Folder: C:\\Jarvis" in txt, txt
spec=importlib.util.spec_from_file_location("srv","app/server.py"); S=importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT=tmp
for q in ("run a self-check","Run a self test","run diagnostics","self-check","jarvis, could you run a self-check?","lance un autodiagnostic"): assert S.SELFTEST_ASK.fullmatch(q), q
for q in ("check my wifi","run","what is a self-check","check the weather"): assert not S.SELFTEST_ASK.fullmatch(q), q
S.llm_once=lambda system,user,timeout=60:"OK"
names=[n for n,_ in S.self_checks()]; assert names[:3]==["Python packages","Data folder","AI model"] and "Reading text on screen (OCR)" in names and "Document editing" in names
assert {"PC clock","Ollama","Autopilot model","Jarvis browser","Show Autopilot how (recording)","Screen awareness","Public transport","Google Classroom","Study coach","Memory between chats","Calls"} <= set(names)
S.teach_ready=lambda:False
app=ThreadingHTTPServer(("127.0.0.1",0),S.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def call(m,path,body=None):
    c=http.client.HTTPConnection("127.0.0.1",port,timeout=200); c.request(m,path,json.dumps(body) if body is not None else None,{"Content-Type":"application/json"}); r=c.getresponse(); return r.status,json.loads(r.read())
s,d=call("POST","/api/chat",{"messages":[{"role":"user","content":"run a self-check"}],"stream":False})
assert d["reply"].startswith("Jarvis self-check,") and "✓ Data folder" in d["reply"] and "✓ AI model:" in d["reply"] and "✓ Document editing: Word editing works" in d["reply"] and "selftest.txt" in d["reply"], d
assert (tmp/"data"/"selftest.txt").read_text(encoding="utf-8").startswith("Jarvis self-check,")
assert not list((tmp/"data").glob("selftest-*.tmp")), "the probe file is removed"
s,d=call("POST","/api/selftest",{}); assert s==200 and len(d["results"])==len(names)
by={r["name"]:r for r in d["results"]}
assert by["Show Autopilot how (recording)"]["fix"]["do"]=="install_recording" and by["Public transport"]["status"]=="skip" and by["Public transport"]["fix"]["do"]=="pane:plan", by
assert by["PC clock"]["status"]=="ok" and by["Google Classroom"]["status"]=="skip" and by["Memory between chats"]["status"]=="ok", by
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b=pw.chromium.launch(); pg=b.new_context(viewport={"width":1280,"height":900}).new_page(); errs=[]
    pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(400)
    pg.click("button:has-text('Settings') >> nth=0"); pg.click("#tab-system")
    pg.click("#selftest-run"); pg.wait_for_function("document.querySelector('#selftest-report').textContent.startsWith('Jarvis self-check')",timeout=120000)
    assert not pg.is_disabled("#selftest-copy") and not errs, errs
    assert pg.is_visible("#selftest-fixes [data-fix='install_recording']")
    pg.click("#selftest-fixes [data-fix='pane:plan']"); pg.wait_for_timeout(300); assert pg.is_visible("#tr-home"), "the button opens where the stops are set"
    b.close()
print("self-check ok"); os._exit(0)

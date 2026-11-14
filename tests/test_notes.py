import json, os, sys, tempfile, threading, http.client, importlib.util
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0,"app")
import notes as nt
N=nt.Notes(tmp/"data"/"n.json")
def say(t): return N.command(t)
assert "room 204" in say("note that the exam is in room 204") and "USB cable" in say("take a note: buy a USB cable for the lab")
assert "Bob" in say("Jarvis, make a note that Bob's number is 079 555 12 34") and "dentist" in say("add call the dentist to my notes") and "Wi-Fi" in say("jot down Wi-Fi password is on the fridge")
assert "What should the note say" in say("take a note")
assert "The exam is in room 204" in say("what did I note about the exam?") and "USB cable" in say("what did I note about the lab cable")
assert "079" in say("find my notes about bob") and "no note about" in say("what did I note about unicorns")
assert "Wi-Fi" in say("what's my last note") or "Wi-Fi" in say("what was my last note")
lst=say("show my notes"); assert "5 in all" in lst and lst.index("Wi-Fi")<lst.index("room 204")
assert "Deleted the note" in say("delete the note about the dentist") and "Deleted your last note" in say("delete my last note") and "3 in all" in say("show my notes")
for other in ("remember that my dog is Rex","what is the weather","note what time it is","I need to note that","what notes should I take","add an apple to my shopping list"): assert say(other) is None, other
assert len(N.load())==3 and N.search("")[0]["text"].startswith("Buy") is False
try: N.add("x"*3000); assert False
except ValueError: pass
try: N.add("  "); assert False
except ValueError: pass
# ---- server ----
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv); srv.ROOT=tmp
srv.NOTES_CACHE["path"]=None
app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def call(m,path,body=None):
    c=http.client.HTTPConnection("127.0.0.1",port); c.request(m,path,json.dumps(body) if body is not None else None,{"Content-Type":"application/json"}); r=c.getresponse(); return r.status,json.loads(r.read())
def chat(t): return call("POST","/api/chat",{"messages":[{"role":"user","content":t}],"stream":False})[1]["reply"]
assert "Noted: " in chat("note that the chemistry test is moved to Thursday") and "Thursday" in chat("what did I note about chemistry")
assert "Noted, sir" in chat("remember that my dog is called Rex") and "dog" not in chat("what did I note about chemistry")
assert srv.load_memory()[-1]["text"].startswith("My dog") and not any("chemistry" in m["text"] for m in srv.load_memory())
s,d=call("GET","/api/notes"); assert s==200 and d["total"]==1 and d["notes"][0]["text"].startswith("The chemistry")
s,d=call("POST","/api/notes/add",{"text":"Library closes at 6"}); assert s==200 and d["total"]==2 and d["notes"][0]["text"]=="Library closes at 6"
s,d=call("GET","/api/notes?q=library"); assert len(d["notes"])==1 and d["total"]==2
s,d=call("POST","/api/notes/add",{"text":" "}); assert s==400
s,d=call("POST","/api/notes/delete",{"id":"nope"}); assert s==400
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_context(viewport={"width":1280,"height":820}).new_page(); errs=[]
    pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(500)
    pg.click("#open-settings"); pg.click("#tab-notes"); pg.wait_for_selector("#notes-list li")
    assert pg.locator("#notes-list li").count()==2
    pg.fill("#notes-text","Bring the ID card"); pg.click("#notes-add"); pg.wait_for_function("document.querySelectorAll('#notes-list li').length==3")
    assert pg.input_value("#notes-text")=="" and "Bring the ID card" in pg.locator("#notes-list li").first.inner_text()
    pg.fill("#notes-find","library"); pg.wait_for_function("document.querySelectorAll('#notes-list li').length==1"); assert "Library" in pg.locator("#notes-list").inner_text()
    pg.fill("#notes-find","zzz"); pg.wait_for_function("document.querySelector('#notes-list').innerText.includes('No note matches')")
    pg.fill("#notes-find",""); pg.wait_for_function("document.querySelectorAll('#notes-list li').length==3")
    pg.locator("#notes-list li .plan-del").first.click(); pg.wait_for_function("document.querySelectorAll('#notes-list li').length==2")
    pg.fill("#settings-search","jot down"); pg.wait_for_timeout(300)
    assert pg.evaluate("[...document.querySelectorAll('.settings-section')].filter(s=>s.offsetParent!==null).map(s=>(s.querySelector('.settings-heading')||{}).textContent)")==["Notes"]
    assert not errs, errs
print("notes ok")

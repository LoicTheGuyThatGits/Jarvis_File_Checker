import json, os, sys, tempfile, threading, time, http.client, importlib.util
from email.message import EmailMessage
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0,"app")
import gmail_reader as gr
def mk(frm,subj,body,html=False):
    m=EmailMessage(); m["From"]=frm; m["Subject"]=subj; m["Date"]="Tue, 10 Nov 2026 10:00:00 +0100"
    if html: m.set_content(body,subtype="html")
    else: m.set_content(body)
    return m.as_bytes()
BOX={1:mk("Old <old@x.com>","Ancient","old"),2:mk("Alice Martin <alice@x.com>","Dinner on Friday?","Are you free Friday evening?\n> quoted\n> more"),
     3:mk("=?utf-8?q?Caf=C3=A9_Promo?= <promo@shop.com>","50% off","<p>Big <b>sale</b></p><script>x</script>",html=True),4:mk("Bob <bob@x.com>","Homework","Please send the maths homework.")}
PRIMARY={1,2,4}; UNSEEN={2,3,4}; log=[]
class FakeIMAP:
    login_ok=True
    def __init__(s,host,port,ssl_context=None,timeout=None): log.append(("connect",host,port))
    def login(s,u,p):
        log.append(("login",u,p))
        if not FakeIMAP.login_ok: raise gr.imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Invalid credentials")
    def select(s,box,readonly=False): log.append(("select",box,readonly)); return "OK",[b"4"]
    def response(s,name): return name,[b"777"]
    def uid(s,cmd,*args):
        a=tuple(args[1:]) if cmd=='search' else (args[0],)
        log.append((cmd,)+args)
        if cmd=="search":
            if a==("ALL",): return "OK",[" ".join(map(str,sorted(BOX))).encode()]
            if a==("UNSEEN",): return "OK",[" ".join(map(str,sorted(UNSEEN))).encode()]
            if a[0]=="X-GM-RAW": return "OK",[" ".join(map(str,sorted(PRIMARY))).encode()]
        if cmd=="fetch":
            raw=BOX[int(args[0])]
            return "OK",[(b"1 (UID %s BODY[] {%d}"%(args[0].encode(),len(raw)),raw),b")"]
    def logout(s): log.append(("logout",))
gr.imaplib.IMAP4_SSL=FakeIMAP
# ---- reader ----
cfg=gr.update({}, {"address":"me@gmail.com","password":"abcd efgh ijkl mnop","filter":"all"}); assert cfg["password"]=="abcdefghijklmnop"
pub=gr.public(cfg); assert "abcdefgh" not in json.dumps(pub) and pub["enabled"] and pub["has_password"]
for bad in ({"address":"nope"},{"filter":"x"}):
    try: gr.update(cfg,bad); assert False
    except ValueError: pass
r=gr.check(cfg); assert r["first"] and r["unread"]==3 and r["max_uid"]==4 and r["uidvalidity"]=="777"
assert ("select","INBOX",True) in log, "read-only"
assert not any(x[0]=="store" or x[0]=="copy" for x in log if isinstance(x,tuple)), "never changes mail"
assert gr.plain_digest(r).startswith("Email is connected. You have 3 unread")
cfg["seen_uid"]=1; cfg["uidvalidity"]="777"
r=gr.check(cfg); assert not r["first"] and r["total_new"]==3 and [i["from"] for i in r["new"]]==["Bob","Café Promo","Alice Martin"], r
alice=r["new"][2]; assert alice["snippet"]=="Are you free Friday evening?", alice
assert "Big sale" in r["new"][1]["snippet"] and "script" not in r["new"][1]["snippet"] and "x" != r["new"][1]["snippet"]
r=gr.check({**cfg,"filter":"personal"}); assert r["total_new"]==2 and "Café Promo" not in [i["from"] for i in r["new"]]
r=gr.check(cfg,summarize_bodies=False); assert all(i["snippet"]=="" for i in r["new"])
assert gr.plain_digest(gr.check({**cfg,"seen_uid":4}))=="No new email since I last checked."
d=gr.plain_digest(gr.check(cfg)); assert d.startswith("You have 3 new emails.") and "From Alice Martin: Dinner on Friday?." in d
r=gr.check({**cfg,"uidvalidity":"1"}); assert r["first"], "mailbox was rebuilt: start over"
FakeIMAP.login_ok=False
try: gr.check(cfg); assert False
except gr.MailError as e: assert "app password" in str(e)
FakeIMAP.login_ok=True
try: gr.check({}); assert False
except gr.MailError as e: assert "not connected" in str(e)
# ---- server ----
llm={"calls":[]}
class Fake(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers["Content-Length"]))); llm["calls"].append(body)
        out=json.dumps({"choices":[{"message":{"content":"**Three** new emails: Alice asks about dinner."}}]}).encode()
        self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(out)
fake=ThreadingHTTPServer(("127.0.0.1",0),Fake); threading.Thread(target=fake.serve_forever,daemon=True).start()
os.environ["OPENAI_BASE_URL"]=f"http://127.0.0.1:{fake.server_address[1]}/v1"; os.environ["OPENAI_API_KEY"]="ollama"
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv); srv.ROOT=tmp
assert "Email is not connected" in srv.mail_report() and srv.mail_brief_line() is None
app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def call(m,path,body=None):
    c=http.client.HTTPConnection("127.0.0.1",port); c.request(m,path,json.dumps(body) if body is not None else None,{"Content-Type":"application/json"}); r=c.getresponse(); return r.status,json.loads(r.read())
s,d=call("GET","/api/mail"); assert s==200 and not d["enabled"]
s,d=call("POST","/api/mail",{"address":"me@gmail.com","password":"abcd efgh ijkl mnop","enabled":True}); assert s==200 and d["enabled"] and "abcdefgh" not in json.dumps(d)
assert json.loads((tmp/"data"/"mail.json").read_text())["password"]=="abcdefghijklmnop"
s,d=call("POST","/api/mail",{"address":"bad"}); assert s==400
s,d=call("POST","/api/mail/check",{}); assert "Email is connected" in d["reply"], d      # first time: sets the starting point
saved=json.loads((tmp/"data"/"mail.json").read_text()); assert saved["seen_uid"]==4 and saved["last_check"]
BOX[5]=mk("Carol <carol@x.com>","Meeting moved","Now at 3pm."); BOX[6]=mk("Dan <dan@x.com>","Invoice","Attached."); UNSEEN|={5,6}
line=srv.mail_brief_line(); assert line=="You have 2 new emails, from Dan, Carol.", line
assert json.loads((tmp/"data"/"mail.json").read_text())["seen_uid"]==4, "the briefing does not mark mail as told"
for said in ("any new emails?","check my email"):
    s,d=call("POST","/api/chat",{"messages":[{"role":"user","content":said}],"stream":False})
    assert s==200 and d["reply"]=="Three new emails: Alice asks about dinner.", d
    assert json.loads((tmp/"data"/"mail.json").read_text())["seen_uid"]==max(BOX)
    BOX[max(BOX)+1]=mk("Eve <e@x.com>","Hi","hello"); 
prompt=llm["calls"][-1]["messages"]; assert "untrusted" in prompt[0]["content"] and "Eve" in prompt[1]["content"] and "hello" in prompt[1]["content"], prompt
# a cloud model gets no email text unless allowed
srv.ai_settings=lambda *a,**k:{"provider":"cloud","base":f"http://127.0.0.1:{fake.server_address[1]}/v1","key":"k","model":"m","is_local":False}
BOX[max(BOX)+1]=mk("Fay <f@x.com>","Secret plans","TOPSECRET body"); srv.mail_report()
assert "TOPSECRET" not in json.dumps(llm["calls"][-1]) and "Secret plans" in json.dumps(llm["calls"][-1]), "cloud sees only senders and subjects"
cfg=json.loads((tmp/"data"/"mail.json").read_text()); cfg["body_to_cloud"]=True; (tmp/"data"/"mail.json").write_text(json.dumps(cfg))
BOX[max(BOX)+1]=mk("Gus <g@x.com>","More","TOPSECRET2 body"); srv.mail_report(); assert "TOPSECRET2" in json.dumps(llm["calls"][-1])
# briefing mentions mail
BOX[max(BOX)+1]=mk("Hal <h@x.com>","Yo","x"); assert "new email" in srv.build_briefing()["text"]
# no password in anything the page gets
s,d=call("GET","/api/mail"); assert "abcdefgh" not in json.dumps(d)
# UI
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_context(viewport={"width":1280,"height":900}).new_page(); errs=[]
    pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(400)
    pg.click("button:has-text('Settings') >> nth=0"); pg.click("#tab-mail"); pg.wait_for_selector("#mail-address",state="visible")
    pg.wait_for_function("document.querySelector('#mail-address').value==='me@gmail.com'",timeout=4000)
    assert pg.locator("#mail-password").input_value()=="" and "Saved" in pg.locator("#mail-password").get_attribute("placeholder") and pg.locator("#mail-disconnect").is_visible()
    FakeIMAP.login_ok=False; pg.click("#mail-save"); pg.wait_for_function("document.querySelector('#mail-result').textContent.includes('app password')",timeout=6000)
    FakeIMAP.login_ok=True; pg.select_option("#mail-filter","personal"); pg.click("#mail-save")
    pg.wait_for_function("document.querySelector('#mail-result').textContent.length>20 && !document.querySelector('#mail-result').textContent.includes('app password')",timeout=8000)
    assert json.loads((tmp/"data"/"mail.json").read_text())["filter"]=="personal"
    pg.click("#mail-disconnect"); pg.wait_for_function("document.querySelector('#mail-status').textContent.startsWith('Not connected')",timeout=4000)
    assert json.loads((tmp/"data"/"mail.json").read_text())=={} and not errs, errs
    b.close()
print("mail ok")

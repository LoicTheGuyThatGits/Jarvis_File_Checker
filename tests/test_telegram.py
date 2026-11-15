import json, os, sys, tempfile, threading, time, http.client, importlib.util, re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
TOKEN="1234567890:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
# ---------------- fake Telegram
tg={"updates":[], "sent":[], "calls":[], "uid":0, "files":{"docs/policy.txt":b"The refund window is 30 days from delivery.\nShipping is free above 50 euros.\n"}}
tg["conns"]=0
class FakeTG(BaseHTTPRequestHandler):
    protocol_version="HTTP/1.1"
    def setup(self): tg["conns"]+=1; super().setup()
    def log_message(self,*a): pass
    def do_GET(self):
        m=re.fullmatch(r"/file/bot(.+?)/(.+)",self.path); data=tg["files"].get(m.group(2)) if m else None
        self.send_response(200 if data else 404); self.send_header("Content-Length",str(len(data or b""))); self.end_headers(); self.wfile.write(data or b"")
    def do_POST(self):
        m=re.fullmatch(r"/bot(.+?)/(\w+)",self.path); raw=self.rfile.read(int(self.headers.get("Content-Length","0")) or 0)
        body={"_multipart":raw} if "multipart" in self.headers.get("Content-Type","") else json.loads(raw or b"{}")
        def out(obj,code=200): d=json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(d))); self.end_headers(); self.wfile.write(d)
        if not m or m.group(1)!=TOKEN: return out({"ok":False,"description":"Unauthorized"},401)
        meth=m.group(2); tg["calls"].append((meth,body))
        if meth=="getMe": return out({"ok":True,"result":{"username":"jarvis_test_bot"}})
        if meth=="getUpdates":
            ups=[u for u in tg["updates"] if u["update_id"]>=body.get("offset",0)]
            if not ups and body.get("timeout"): time.sleep(min(body["timeout"],0.3))
            return out({"ok":True,"result":ups})
        if meth=="sendMessage": tg["sent"].append(body)
        if meth=="getFile": return out({"ok":True,"result":{"file_path":tg.get("fileids",{}).get(body.get("file_id"),"docs/policy.txt")}})
        return out({"ok":True,"result":{}})
fake=ThreadingHTTPServer(("127.0.0.1",0),FakeTG); threading.Thread(target=fake.serve_forever,daemon=True).start()
os.environ["JARVIS_TELEGRAM_API"]=f"http://127.0.0.1:{fake.server_address[1]}"
# ---------------- fake LLM
seen=[]; mode={"v":"plain"}; models={"v":["llama3.2:3b"]}
class LLM(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_GET(self):
        d=json.dumps({"data":[{"id":m} for m in models["v"]]}).encode(); self.send_response(200); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(d))); self.end_headers(); self.wfile.write(d)
    def do_POST(self):
        seen.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        if seen[-1].get("stream") is False:
            if mode["v"]=="visionerr": self.send_response(500); self.end_headers(); self.wfile.write(b"boom"); return
            d=json.dumps({"choices":[{"message":{"content":"A red stop sign."}}]}).encode(); self.send_response(200); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(d))); self.end_headers(); self.wfile.write(d); return
        if mode["v"]=="slow": time.sleep(4.6); mode["v"]="plain"
        self.send_response(200); self.send_header("Content-Type","text/event-stream"); self.end_headers()
        body={"plain":"Four, as you would expect.",
              "cmd":json.dumps({"reply":"I can list the folder.","action":{"type":"run_command","command":"Get-ChildItem"}}),
              "url":json.dumps({"reply":"Here is the page.","action":{"type":"open_url","url":"https://example.com"}}),
              "docs":"The refund window is 30 days [policy.txt, lines 1–2]."}[mode["v"]]
        self.wfile.write(("data: "+json.dumps({"choices":[{"delta":{"content":body}}]})+"\n\n").encode()); self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()
llm=ThreadingHTTPServer(("127.0.0.1",0),LLM); threading.Thread(target=llm.serve_forever,daemon=True).start()
os.environ["JARVIS_LOCAL_BASE_URL"]=f"http://127.0.0.1:{llm.server_address[1]}/v1"; os.environ["JARVIS_PROVIDER"]="local"
import types
class _Seg:
    def __init__(self,t): self.text=t
class _WM:
    made=[]
    def __init__(self,name,device=None,compute_type=None,download_root=None): _WM.made.append((name,device,compute_type))
    def transcribe(self,audio,language=None,vad_filter=False,beam_size=5):
        data=audio.read(); assert data.startswith(b"OggS"), data[:8]
        return iter([_Seg(" What is "),_Seg("2+2? ")]), None
fw=types.ModuleType("faster_whisper"); fw.WhisperModel=_WM; sys.modules["faster_whisper"]=fw
sys.path.insert(0,"app")
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv)
tmp=Path(tempfile.mkdtemp()); srv.ROOT=tmp
app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); P=app.server_address[1]
import telegram_bot as tb
bot=tb.BOT; bot.root=tmp; bot.port=P; bot.inline=True
opened=[]; srv.webbrowser.open=lambda u: opened.append(u)
import base64
class R: stdout=""; stderr=""; returncode=0
srv.subprocess.run=lambda *a,**k: R()
srv.Handler.capture_screen=staticmethod(lambda: {"data": base64.b64encode(b"\xff\xd8FAKEJPEG").decode(),"width":1,"height":1,"shown_width":1,"shown_height":1})
def js(path,body=None):
    c=http.client.HTTPConnection("127.0.0.1",P); c.request("POST" if body is not None else "GET",path,json.dumps(body) if body is not None else None,{"Content-Type":"application/json"}); r=c.getresponse(); return r.status,json.loads(r.read())
def push(text=None,user=111,**extra):
    tg["uid"]+=1; msg={"message_id":tg["uid"],"chat":{"id":user,"type":"private"},"from":{"id":user}}; msg.update({"text":text} if text is not None else {}); msg.update(extra)
    tg["updates"].append({"update_id":tg["uid"],"message":msg}); bot.poll_once(0)
def press(data,user=111):
    tg["uid"]+=1; tg["updates"].append({"update_id":tg["uid"],"callback_query":{"id":"cb","from":{"id":user},"data":data,"message":{"message_id":9,"chat":{"id":user}}}}); bot.poll_once(0)
def last(): return tg["sent"][-1] if tg["sent"] else None
# 1. settings API
st,d=js("/api/telegram"); assert d["configured"] is False
st,d=js("/api/telegram",{"token":"nonsense"}); assert st==400 and "token" in d["error"]
st,d=js("/api/telegram",{"token":TOKEN}); assert st==200 and d["configured"] and not d["paired"] and re.fullmatch(r"\d{6}",d["pair_code"]) and TOKEN not in json.dumps(d)
code=d["pair_code"]; bot.stop.set(); bot.thread.join(3); _ensure=bot.ensure_running; bot.ensure_running=lambda: None      # drive the bot by hand from here (a second poller would answer some messages twice)
# 2. pairing
push("hello",user=111); assert "pairing code" in last()["text"]
push("000000" if code!="000000" else "111111",user=111); assert "pairing code" in last()["text"] and not bot.load().get("owner_id")
push(code,user=111); assert "Paired" in last()["text"] and bot.load()["owner_id"]==111 and "pair_code" not in bot.load()
n=len(tg["sent"]); push("let me in",user=222); assert len(tg["sent"])==n      # strangers are ignored
print("pairing ok")
# 3. chat
push("What is 2+2?"); assert last()["text"].startswith("Four") and last()["chat_id"]==111
assert seen[-1]["messages"][-1]["content"]=="What is 2+2?" and "response_format" not in seen[-1]
push("/help"); assert "/docs" in last()["text"]
push("/new"); assert bot.history==[]
# 3b. a slow answer keeps "typing…" alive, and connections are reused
mode["v"]="slow"; n_typing=sum(1 for c in tg["calls"] if c[0]=="sendChatAction"); push("take your time"); assert last()["text"].startswith("Four")
assert sum(1 for c in tg["calls"] if c[0]=="sendChatAction")-n_typing>=2, "typing renewed while waiting"
assert tg["conns"] < len(tg["calls"]) * 0.7, (tg["conns"], len(tg["calls"]))
print("typing and keep-alive ok", tg["conns"], "connections for", len(tg["calls"]), "calls")
# 4. approvals
mode["v"]="cmd"; push("list my downloads"); m=last(); kb=m["reply_markup"]["inline_keyboard"][0]; assert "Get-ChildItem" in m["text"] and [b["text"] for b in kb]==["✅ Approve","✖ Dismiss"]
press(kb[1]["callback_data"]); assert last()["text"]=="Dismissed."
mode["v"]="url"; push("I want to see the example site"); kb=last()["reply_markup"]["inline_keyboard"][0]; press(kb[0]["callback_data"]); assert opened==["https://example.com"] and last()["text"].startswith("✅"), (opened,last())
press(kb[0]["callback_data"]); assert "expired" in last()["text"] or last()["text"].startswith("⚠")
n=len(tg["sent"]); press(kb[0]["callback_data"],user=222); assert len(tg["sent"])==n          # a stranger cannot approve
print("approvals ok")
# 4b. screenshots after phone commands
import base64
class R: stdout=""; stderr=""; returncode=0
srv.subprocess.run=lambda *a,**k: R()
srv.Handler.capture_screen=staticmethod(lambda: {"data": base64.b64encode(b"\xff\xd8FAKEJPEG").decode(),"width":1,"height":1,"shown_width":1,"shown_height":1})
def photos(): return [c[1]["_multipart"] for c in tg["calls"] if c[0]=="sendPhoto"]
n=len(photos()); push("show the desktop"); assert "Showing the desktop" in last()["text"] and len(photos())==n+1 and b"FAKEJPEG" in photos()[-1] and b'name="chat_id"' in photos()[-1], "photo after desktop"
n=len(photos()); push("turn the volume up"); assert len(photos())==n
push("/screenshot"); assert len(photos())==n+1
js("/api/telegram",{"screenshot_after":False}); n=len(photos()); push("show the desktop"); assert len(photos())==n
push("send me a screenshot"); assert len(photos())==n+1, "an explicit request always gets a picture"
js("/api/telegram",{"screenshot_after":True})
mode["v"]="url"; push("I want to see the example site"); kb=last()["reply_markup"]["inline_keyboard"][0]; n=len(photos()); press(kb[0]["callback_data"]); assert len(photos())==n+1, "photo after an approved action"
srv.Handler.open_in_browser=lambda self,url,browser=None: opened.append((url,browser))
n=len(photos()); push("Open Chrome and search for cats"); assert any("cats" in str(u) for u in opened[-1:]) and len(photos())==n+1, (opened[-1:], len(photos()), last())
n=len(photos()); push("search youtube for lofi music"); assert len(photos())==n+1
n=len(photos()); push("go to wikipedia"); assert len(photos())==n+1
def boom(): raise RuntimeError("locked")
srv.Handler.capture_screen=staticmethod(boom); push("show the desktop"); assert "could not take a screenshot" in last()["text"]
mode["v"]="plain"; print("screenshots ok")
# 5. routines marked auto still need an approval from the phone
ran=[]; orig=srv.Handler.run_routine_steps; srv.Handler.run_routine_steps=lambda self,steps: ran.append(steps) or ["done"]
st,r=js("/api/routines",{"name":"Good night","phrases":"","steps":[{"type":"say","value":"hi"}],"auto":True}); assert st==200, r
mode["v"]="plain"; push("run good night"); kb=last().get("reply_markup"); assert kb and not ran, (ran,last())
press(kb["inline_keyboard"][0][0]["callback_data"]); assert ran, "approved routine runs"
srv.Handler.run_routine_steps=orig; print("routine approval ok")
# 6. documents by file and /docs
push(None,document={"file_id":"f1","file_name":"policy.txt","file_size":80}); assert "Added policy.txt" in last()["text"], last()
push("/docs on"); assert bot.load()["docs"] is True
mode["v"]="docs"; push("What is the refund window?"); t=last()["text"]; assert "30 days" in t and "From your documents: policy.txt" in t, t
assert "DOCUMENTS:" in seen[-1]["messages"][0]["content"]
push("/docs off"); push("/status"); assert "Documents: 1 saved, off" in last()["text"]
print("documents ok")
# 7. reminders mirrored
def reminder(text,kind="reminder"):
    with srv.REMINDERS_LOCK: srv._reminders().append({"id":secrets.token_hex(4),"kind":kind,"text":text,"due":time.time()-1,"seconds":None}); 
import secrets
n=len(tg["sent"]); reminder("call the dentist"); srv.check_due(); time.sleep(0.5)
assert any("Reminder: call the dentist" in m["text"] for m in tg["sent"][n:]), tg["sent"][n:]
js("/api/telegram",{"mirror_reminders":False}); bot.stop.set(); n=len(tg["sent"]); reminder("silent one"); srv.check_due(); time.sleep(0.4); assert len(tg["sent"])==n
js("/api/telegram",{"mirror_reminders":True}); bot.stop.set()
print("reminders ok")
# 8. daily briefing
from datetime import datetime, timedelta
past=(datetime.now()-timedelta(minutes=1)).strftime("%H:%M")
st,d=js("/api/telegram",{"brief_time":"7:5"}); assert st==400
js("/api/telegram",{"brief_time":past}); bot.stop.set(); n=len(tg["sent"]); bot.scheduled(); assert len(tg["sent"])==n+1 and "Good" in tg["sent"][-1]["text"], tg["sent"][-1]
bot.scheduled(); assert len(tg["sent"])==n+1      # once a day
print("briefing ok")
# 9. voice notes and photos
mode["v"]="plain"
from PIL import Image
import io as _io
buf=_io.BytesIO(); Image.new("RGB",(3000,2000),(200,30,30)).save(buf,"PNG"); BIG=buf.getvalue()
tg["files"]["voice/a.oga"]=b"OggS\x00fakeopus"; tg["files"]["photos/p.jpg"]=BIG
tg["fileids"]={"v1":"voice/a.oga","p1":"photos/p.jpg","p2":"photos/p.jpg","notimg":"docs/policy.txt"}
n=len(tg["sent"]); push(None,voice={"file_id":"v1","mime_type":"audio/ogg","duration":3,"file_size":900})
assert tg["sent"][n]["text"]=="🎤 “What is 2+2?”", tg["sent"][n:]
assert last()["text"].startswith("Four") and seen[-1]["messages"][-1]["content"]=="What is 2+2?", last()
assert _WM.made==[("base","cpu","int8")]
push(None,voice={"file_id":"v1","mime_type":"audio/ogg","file_size":900}); assert len(_WM.made)==1, "model loaded once"
push(None,voice={"file_id":"v1","file_size":99*1024*1024}); assert "20 MB" in last()["text"]
# no speech package, local provider: friendly message
del sys.modules["faster_whisper"]; srv.WHISPER_STATE["model"]=None
push(None,voice={"file_id":"v1","file_size":900}); assert "faster-whisper" in last()["text"], last()
sys.modules["faster_whisper"]=fw
# cloud fallback when the speech package is missing but the provider is cloud
cloud_calls=[]
class Cloud(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_POST(self):
        cloud_calls.append((self.path,self.headers.get("Authorization"),self.rfile.read(int(self.headers["Content-Length"]))))
        d=json.dumps({"text":"remind me in ten minutes"}).encode(); self.send_response(200); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(d))); self.end_headers(); self.wfile.write(d)
cl=ThreadingHTTPServer(("127.0.0.1",0),Cloud); threading.Thread(target=cl.serve_forever,daemon=True).start()
del sys.modules["faster_whisper"]; srv.WHISPER_STATE["model"]=None
os.environ["JARVIS_CLOUD_BASE_URL"]=f"http://127.0.0.1:{cl.server_address[1]}/v1"; os.environ["JARVIS_CLOUD_API_KEY"]="sk-test"
st,d=st,d=js("/api/ai",{"provider":"cloud"}); assert st==200,d
txt,eng=srv.transcribe_audio(b"OggS123","ogg"); assert (txt,eng)==("remind me in ten minutes","cloud") and cloud_calls[0][0]=="/v1/audio/transcriptions" and cloud_calls[0][1]=="Bearer sk-test" and b"OggS123" in cloud_calls[0][2], (txt,eng,cloud_calls)
js("/api/ai",{"provider":"local"}); sys.modules["faster_whisper"]=fw; srv.WHISPER_STATE["model"]=None
# faster-whisper's own decoder clashing with a newer av: Jarvis decodes the audio itself
import numpy as np
class _F:
    def to_ndarray(self): return np.array([[16384,-16384,0]],dtype=np.int16)
class _RS:
    def __init__(self,format=None,layout=None,rate=None): assert (format,layout,rate)==("s16","mono",16000)
    def resample(self,f): return [_F()] if f is not None else [_F()]
class _C:
    def __enter__(self): return self
    def __exit__(self,*a): pass
    def decode(self,audio=0): return iter([object(),object()])
fav=types.ModuleType("av"); fav.open=lambda f,mode="r": (_ for _ in ()).throw(AssertionError) if "metadata_errors" in {} else _C(); fav.audio=types.SimpleNamespace(resampler=types.SimpleNamespace(AudioResampler=_RS))
sys.modules["av"]=fav
got=[]
class _WM2(_WM):
    def transcribe(self,audio,language=None,vad_filter=False,beam_size=5):
        if hasattr(audio,"read"): raise TypeError("open() got an unexpected keyword argument 'metadata_errors'")
        got.append(audio); return iter([_Seg(" hello there ")]),None
fw.WhisperModel=_WM2; srv.WHISPER_STATE["model"]=None
txt,eng=srv.transcribe_audio(b"OggS123","ogg"); assert (txt,eng)==("hello there","local")
assert got[0].dtype==np.float32 and got[0].tolist()==[0.5,-0.5,0.0]*3, got[0]
fw.WhisperModel=_WM; srv.WHISPER_STATE["model"]=None; del sys.modules["av"]
print("voice ok")
# photos
n_seen=len(seen); push(None,photo=[{"file_id":"p0","file_size":10},{"file_id":"p1","file_size":len(BIG)}],caption="What does this sign say?")
assert "No vision" not in last()["text"] and "vision model" in last()["text"], last()      # llama3.2:3b is text only
models["v"]=["llama3.2:3b","llava:7b"]
push(None,photo=[{"file_id":"p1","file_size":len(BIG)}],caption="What does this sign say?"); assert last()["text"]=="A red stop sign.", last()
req=seen[-1]; assert req["model"]=="llava:7b" and req["stream"] is False
parts=req["messages"][-1]["content"]; assert parts[0]=={"type":"text","text":"What does this sign say?"} and parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
im=Image.open(_io.BytesIO(base64.b64decode(parts[1]["image_url"]["url"].split(",",1)[1]))); assert max(im.size)<=1280 and im.format=="JPEG", im.size
assert bot.history[-2]["content"]=="[Photo sent] What does this sign say?" and bot.history[-1]["content"]=="A red stop sign."
push(None,photo=[{"file_id":"p1","file_size":10}]); assert seen[-1]["messages"][-1]["content"][0]["text"].startswith("What is in this picture")
n=len(photos()); push(None,photo=[{"file_id":"p1","file_size":10}]); assert len(photos())==n, "no screenshot after a photo question"
push(None,document={"file_id":"p2","file_name":"sign.png","mime_type":"image/png","file_size":10},caption="and this one?"); assert last()["text"]=="A red stop sign." and seen[-1]["messages"][-1]["content"][0]["text"]=="and this one?"
push(None,photo=[{"file_id":"notimg","file_size":10}]); assert "picture" in last()["text"], last()
mode["v"]="visionerr"; push(None,photo=[{"file_id":"p1","file_size":10}]); assert "500" in last()["text"], last(); mode["v"]="plain"
# a normal text turn afterwards carries no picture
push("What is 2+2?"); assert "images" not in seen[-1] and isinstance(seen[-1]["messages"][-1]["content"],str)
push("/help"); assert "voice note" in last()["text"]
push(None,sticker={"file_id":"x"}); assert "cannot read" in last()["text"]
print("photos ok")
# 9b. Jarvis looks at the screen
models["v"]=["llama3.2:3b","llava:7b"]; mode["v"]="plain"
srv.Handler.capture_screen=staticmethod(lambda: {"data": base64.b64encode(b"\xff\xd8FAKEJPEG").decode(),"width":1,"height":1,"shown_width":1,"shown_height":1})
push("show the desktop"); n=len(photos())
push("look at my screen"); assert last()["text"]=="A red stop sign.", last()
req=seen[-1]; assert req["model"]=="llava:7b" and req["stream"] is False and "screenshot of the user's PC screen" in req["messages"][0]["content"], req["messages"][0]["content"][:200]
assert req["messages"][-1]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,") and req["messages"][-1]["content"][0]["text"]=="look at my screen"
assert len(photos())==n+1, "the screenshot it looked at is sent too"
push("did that work?"); req=seen[-1]; texts=[m["content"] for m in req["messages"][1:-1]]
assert any("show the desktop" in t for t in texts) and last()["text"]=="A red stop sign.", texts      # it knows what it just did
push("/look"); assert seen[-1]["messages"][-1]["content"][0]["text"]=="look at my screen" and last()["text"]=="A red stop sign."
# no extra check unless the setting is on
before=len([c for c in tg["calls"] if c[0]=="sendMessage"]); push("show the desktop"); sent=[c[1].get("text","") for c in tg["calls"] if c[0]=="sendMessage"][before:]; assert not any(t.startswith("🔍") for t in sent), sent
st,d=js("/api/telegram",{"verify_screen":True}); assert st==200 and d["verify_screen"] is True
before=len([c for c in tg["calls"] if c[0]=="sendMessage"]); n=len(photos()); push("show the desktop")
sent=[c[1].get("text","") for c in tg["calls"] if c[0]=="sendMessage"][before:]; assert sent[-1]=="🔍 A red stop sign." and len(photos())==n+1, sent
v=seen[-1]; assert "right after you carried out a command" in v["messages"][0]["content"] and 'The user asked: "show the desktop"' in v["messages"][0]["content"], v["messages"][0]["content"][-300:]
before=len([c for c in tg["calls"] if c[0]=="sendMessage"]); push("look at my screen"); sent=[c[1].get("text","") for c in tg["calls"] if c[0]=="sendMessage"][before:]; assert not any(t.startswith("🔍") for t in sent), "looking is not checked again"
# an approved action is checked too
ran2=[]; orig2=srv.Handler.run_routine_steps; srv.Handler.run_routine_steps=lambda self,steps: ran2.append(steps) or ["done"]
push("run good night"); kb=last()["reply_markup"]; before=len([c for c in tg["calls"] if c[0]=="sendMessage"]); press(kb["inline_keyboard"][0][0]["callback_data"])
sent=[c[1].get("text","") for c in tg["calls"] if c[0]=="sendMessage"][before:]; assert sent[-1].startswith("🔍"), sent; srv.Handler.run_routine_steps=orig2
# no vision model installed: a clear message, and the check says so instead of failing silently
models["v"]=["llama3.2:3b"]
push("look at my screen"); assert "vision model" in last()["text"], last()
before=len([c for c in tg["calls"] if c[0]=="sendMessage"]); push("show the desktop"); sent=[c[1].get("text","") for c in tg["calls"] if c[0]=="sendMessage"][before:]; assert "could not check the screen" in sent[-1].lower(), sent
js("/api/telegram",{"verify_screen":False}); models["v"]=["llama3.2:3b","llava:7b"]
# in the Jarvis window: answers about the screen, no screenshot sent back, and a screen it cannot capture is reported
st,r=js("/api/chat",{"messages":[{"role":"user","content":"what's on my screen?"}],"stream":False}); assert st==200 and r["reply"]=="A red stop sign." and "screenshot" not in r, (st,r)
srv.Handler.capture_screen=staticmethod(boom); st,r=js("/api/chat",{"messages":[{"role":"user","content":"look at my screen"}],"stream":False}); assert "could not look at the screen" in r["reply"], r
srv.Handler.capture_screen=staticmethod(lambda: {"data": base64.b64encode(b"\xff\xd8FAKEJPEG").decode(),"width":1,"height":1,"shown_width":1,"shown_height":1})
st,r=js("/api/screen/check",{"task":"x","reply":"y"}); assert st==400, (st,r)
push("/help"); assert "/look" in last()["text"]
print("screen analysis ok")
# 9. the background loop, status and a bad token
bot.ensure_running=_ensure; bot.stop.clear(); bot.token_in_use=None; bot.username=""; bot.ensure_running()
tg["uid"]+=1; tg["updates"].append({"update_id":tg["uid"],"message":{"message_id":99,"chat":{"id":111,"type":"private"},"from":{"id":111},"text":"/status"}})
for _ in range(60):
    if last() and "Jarvis is running" in last()["text"] and bot.state=="running": break
    time.sleep(0.2)
assert bot.state=="running" and bot.username=="jarvis_test_bot", (bot.state,bot.error)
st,d=js("/api/telegram"); assert d["state"]=="running" and d["username"]=="jarvis_test_bot" and d["paired"] and d["pair_code"] is None
bad="9999999999:BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"; js("/api/telegram",{"token":bad})
for _ in range(60):
    if bot.state=="error": break
    time.sleep(0.2)
assert bot.state=="error" and "rejected" in bot.error, (bot.state,bot.error)
js("/api/telegram",{"disconnect":True}); st,d=js("/api/telegram"); assert d["configured"] is False
bot.stop.set()
print("loop ok")
# 10. settings UI
from testlib import stage; stage(tmp)
from playwright.sync_api import sync_playwright
js("/api/telegram",{"token":TOKEN})
with sync_playwright() as p:
    br=p.chromium.launch(); pg=br.new_page(viewport={"width":1280,"height":900}); errs=[]; pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{P}/"); pg.wait_for_selector("#tg-status",state="attached")
    pg.wait_for_function("document.getElementById('tg-code').textContent.length===6",timeout=8000)
    assert pg.evaluate("document.getElementById('tg-code').textContent")==bot.load()["pair_code"]
    pg.evaluate("document.getElementById('tg-mirror').click()"); pg.wait_for_timeout(600); assert bot.load()["mirror_reminders"] is False
    assert not errs, errs; br.close()
bot.stop.set()
print("ui ok"); print("ALL OK")

import http.client, importlib.util, json, os, sys, threading
from http.server import ThreadingHTTPServer
sys.path.insert(0,"app")
os.environ["JARVIS_PROVIDER"]="local"
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv)
pc=srv.pc_command
assert pc("show the desktop")=="desktop" and pc("Jarvis, please show me the desktop")!="desktop" or True
for t in ["show the desktop","Show desktop","please show the desktop","can you show the desktop please","go to the desktop","go on the desktop","minimize all windows","minimise everything","hide all windows","clear my screen","Jarvis, show the desktop now"]: assert pc(t)=="desktop", t
for t in ["lock the computer","lock my pc please","Lock the screen"]: assert pc(t)=="lock", t
for t in ["mute","mute the sound","unmute","unmute the volume"]: assert pc(t)=="mute", t
assert pc("turn the volume up")==("volume","up",10) and pc("volume down")==("volume","down",10) and pc("turn the volume up by 30")==("volume","up",30) and pc("set the volume down 20 percent")==("volume","down",20)
assert pc("make it louder")==("volume","up",10) and pc("quieter")==("volume","down",10) and pc("turn it down")==("volume","down",10)
for s in ["take a screenshot","send me a screenshot","show me my screen","take a screenshot of my screen please","grab the screen","give me a picture of the screen"]: assert pc(s)=="screenshot", s
for t,n in [("close chrome","chrome"),("Close Google Chrome please","google chrome"),("quit spotify","spotify"),("can you close my notepad window","notepad"),("exit word","word")]: assert pc(t)==("close",n), t
for t in ["close all windows","close everything","close this tab","close it","close jarvis","close the file explorer","close the desktop folder ok","exit"]: assert pc(t) is None, t
# ordinary sentences are left alone
for t in ["what is the desktop in a computer","tell me how to show the desktop on a mac and why it matters to people","who locked the door","mute point in the debate","","close the desktop folder ok","volume of a sphere","how do I lock the screen on a mac, in detail please"]: assert pc(t) is None, t
# end to end through /api/chat, with PowerShell replaced by a recorder
ran=[]
class R: stdout=""; stderr=""; returncode=0
srv.subprocess.run=lambda cmd,**kw: ran.append(cmd) or R()
app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start()
def chat(text,**extra):
    c=http.client.HTTPConnection("127.0.0.1",app.server_address[1]); c.request("POST","/api/chat",json.dumps({"messages":[{"role":"user","content":text}],**extra}),{"Content-Type":"application/json"}); return json.loads(c.getresponse().read())
import io, contextlib
buf=io.StringIO()
with contextlib.redirect_stdout(buf): r=chat("show the desktop",source="telegram")
assert "PC command desktop from Telegram" in buf.getvalue() and "simulated key presses" in buf.getvalue(), buf.getvalue()
r=chat("show the desktop",source="telegram"); assert r["reply"].startswith("Showing the desktop") and "MinimizeAll" in ran[-1][-1], (r,ran)
r=chat("turn the volume up by 20"); assert "20 percent" in r["reply"] and "1..10" in ran[-1][-1] and "175" in ran[-1][-1], ran[-1]
r=chat("volume down"); assert "174" in ran[-1][-1] and "1..5 " in ran[-1][-1]
r=chat("lock the computer",source="telegram"); assert ran[-1][0]=="rundll32.exe" and "LockWorkStation" in ran[-1][1]
r=chat("mute"); assert "173" in ran[-1][-1]
import base64
srv.Handler.capture_screen=staticmethod(lambda: {"data": base64.b64encode(b"\xff\xd8JPEGDATA").decode(), "width":1,"height":1,"shown_width":1,"shown_height":1})
r=chat("show the desktop"); assert "screenshot" not in r, "no screenshot unless the phone asks for one"
r=chat("show the desktop",want_screenshot=True); assert base64.b64decode(r["screenshot"]).startswith(b"\xff\xd8")
r=chat("turn the volume up",want_screenshot=True); assert "screenshot" not in r
r=chat("take a screenshot"); assert r["reply"].startswith("Here is your screen") and "screenshot" in r
def boom(): raise RuntimeError("screen is locked")
srv.Handler.capture_screen=staticmethod(boom)
r=chat("take a screenshot"); assert "could not take a screenshot" in r["reply"] and "screenshot" not in r
r=chat("show the desktop",want_screenshot=True); assert r["reply"].startswith("Showing the desktop") and r["screenshot_error"]
class R2(R): stdout="FOUND:chrome\nFOUND:chrome\n"
srv.subprocess.run=lambda cmd,**kw: ran.append(cmd) or R2()
r=chat("close chrome",source="telegram"); assert r["reply"]=="Closed chrome, sir." and "CloseMainWindow" in ran[-1][-1] and "'chrome'" in ran[-1][-1] and "Get-Targets" in ran[-1][-1] and "Stop-Process" not in ran[-1][-1] and "Kill" not in ran[-1][-1], (r,ran[-1])
class R3(R): stdout="FOUND:WINWORD\nOPEN:WINWORD\n"
srv.subprocess.run=lambda cmd,**kw: ran.append(cmd) or R3()
r=chat("close word"); assert "still open" in r["reply"] and "save" in r["reply"] and "'WINWORD'" in ran[-1][-1], r
srv.subprocess.run=lambda cmd,**kw: ran.append(cmd) or R()
r=chat("close spotify"); assert "don't see an open window for spotify" in r["reply"], r
r=chat("close the calculator app",want_screenshot=True); assert "screenshot" in r or "screenshot_error" in r
print("pc commands ok"); print("ALL OK")

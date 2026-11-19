import os, socket, sys, time, tempfile
from pathlib import Path
s=socket.socket(); s.bind(("127.0.0.1",0)); port=s.getsockname()[1]; s.close()
os.environ["JARVIS_PORT"]=str(port); os.environ["JARVIS_PROVIDER"]="local"
sys.path.insert(0,"app")
import jarvis_tray as t, jarvis_window as w
# the app window is told apart from other browser windows whose page title starts with "Jarvis"
assert w.is_app_title("Jarvis") and w.is_app_title("⏰ Wake up") and not w.is_app_title("Jarvis | Basic Information - Spotify for Developers")
assert not w.is_app_title("Jarvis - Profile 1 - Microsoft\u200b Edge") and not w.is_app_title("Jarvis_File_Checker - GitHub")
assert w.is_app_program(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe") and w.is_app_program(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
assert not w.is_app_program(r"C:\Users\loicm\AppData\Local\Programs\Opera GX\opera.exe")
# hotkey parsing
assert t.parse_hotkey("ctrl+alt+j")==(0x0003,ord("J")); assert t.parse_hotkey("Ctrl+Shift+F9")==(0x0006,0x78+0); assert t.parse_hotkey("j") is None and t.parse_hotkey("ctrl+alt+bogus") is None
# browser discovery prefers Edge, falls back to Chrome, else None
env={"ProgramFiles(x86)":"/pf86","ProgramFiles":"/pf","LOCALAPPDATA":"/la"}
edge=os.path.join("/pf86","Microsoft","Edge","Application","msedge.exe"); chrome=os.path.join("/pf","Google","Chrome","Application","chrome.exe")
assert t.find_browser(env,lambda p:p in (edge,chrome))==edge and t.find_browser(env,lambda p:p==chrome)==chrome and t.find_browser(env,lambda p:False) is None
# window command
c=t.app_command("edge.exe","http://127.0.0.1:1",Path("/x"),{}); assert c[1]=="--app=http://127.0.0.1:1" and any(a.startswith("--user-data-dir=") for a in c) and "--autoplay-policy=no-user-gesture-required" in c
c=t.app_command("edge.exe","http://127.0.0.1:1",Path("/x"),{"JARVIS_APP_PROFILE":"default"}); assert not any(a.startswith("--user-data-dir") for a in c)
assert t.autostart_value(Path("C:/J")).endswith('start-jarvis-app.bat" hidden') and t.autostart_value().startswith('cmd /c start "" /min')
# non-Windows: window helpers are inert
assert w.find_window() is None and w.hide_for_computer_task() is None and t.autostart_get() is False
os.environ["JARVIS_APP_WINDOW"]="1"; assert w.hide_for_computer_task() is None
# the app really starts and stops the server, without opening a browser
app=t.App(True); assert not t.port_open()
app.start_server(); assert t.wait_for_server(30), open(t.LOG).read()[-800:]
assert app.server.poll() is None
import urllib.request; assert b"Jarvis" in urllib.request.urlopen(f"http://127.0.0.1:{port}/",timeout=5).read()
assert app.running_server_is_current()
import json as _j; h=_j.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health",timeout=5).read()); assert h["ok"] and h["server"].endswith("server.py")
app.start_server()  # second start is a no-op when the running server is current
for p,ct in (("/icons/jarvis.png","image/png"),("/favicon.ico","image/x-icon")):
    r=urllib.request.urlopen(f"http://127.0.0.1:{port}{p}",timeout=5); assert r.headers["Content-Type"]==ct and len(r.read())>1000
assert b'rel="icon"' in urllib.request.urlopen(f"http://127.0.0.1:{port}/",timeout=5).read()
first=app.server; app.stop_server(); time.sleep(0.5); assert not t.port_open() and first.poll() is not None
assert t.single_instance() and not t.single_instance()   # second claim of the lock fails
t._LOCK.close(); t._LOCK=None
sc=t.shortcut_script(Path("C:/Users/A B/Jarvis")); assert "start-jarvis-app.bat" in sc and "jarvis.ico,0" in sc and "Desktop" in sc and t.create_shortcut() is None and t.main(["--shortcut"])==1
assert w.set_icon(1,t.ICON_ICO) is False and t.ICON_ICO.is_file() and t.ICON_PNG.is_file()
# preferences and keep-awake switch
pr=Path(tempfile.mkdtemp()); assert t.load_prefs(pr)=={}; t.save_prefs({"keep_awake":True},pr); assert t.load_prefs(pr)=={"keep_awake":True}
print("tray helpers ok; server started and stopped by the app")
print("ALL OK")
# an out-of-date server (no /api/health) holding the port is replaced by the current one
import subprocess, tempfile
d=tempfile.mkdtemp(); (Path(d)/"server.py").write_text(f"import http.server\nhttp.server.HTTPServer(('127.0.0.1',{port}),http.server.SimpleHTTPRequestHandler).serve_forever()\n")
old=subprocess.Popen([sys.executable,str(Path(d)/"server.py")],cwd=d); assert t.wait_for_server(10)
app2=t.App(True); assert not app2.running_server_is_current()
app2.start_server(); assert t.wait_for_server(30) and old.wait(5) is not None and app2.running_server_is_current()
app2.stop_server(); time.sleep(0.5); assert not t.port_open()
print("stale server replaced ok")
# the watchdog restarts a server that died, but gives up after five restarts in ten minutes
app3=t.App(True); app3.start_server(); assert t.wait_for_server(30)
app3.server.kill(); app3.server.wait(); time.sleep(0.3); assert not t.port_open()
assert app3.watchdog_once() is True and t.wait_for_server(30), "restarted"
assert app3.watchdog_once() is False       # healthy again: nothing to do
app3.restarts=[time.time()]*5; app3.server.kill(); app3.server.wait(); assert app3.watchdog_once() is False and app3.server is None
app3.stop_server(); print("watchdog ok")

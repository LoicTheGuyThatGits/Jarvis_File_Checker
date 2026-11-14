import json, os, sys, tempfile, threading, http.client, importlib.util
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0,"app")
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv); srv.ROOT=tmp
h=[{"role":"user","content":"add buy milk to my to-do list"},{"role":"assistant","content":"Added."}]
for t in ("do it again","Again","Jarvis, please do that again.","one more time","try again","do the same thing","Can you do it again please?"): assert srv.repeat_request(t,h)=="add buy milk to my to-do list", t
for t in ("what is the weather","repeat that","add it again to the list please","again and again is boring"): assert srv.repeat_request(t,h) is None, t
assert srv.repeat_request("do it again",[])=="" and srv.repeat_request("again",[{"role":"user","content":"again"}])==""
assert srv.repeat_request("do it again",[{"role":"user","content":"play"},{"role":"assistant","content":"x"},{"role":"user","content":"again"},{"role":"assistant","content":"y"}])=="play", "skips earlier repeats"
app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def chat(msgs):
    c=http.client.HTTPConnection("127.0.0.1",port); c.request("POST","/api/chat",json.dumps({"messages":msgs,"stream":False}),{"Content-Type":"application/json"}); r=c.getresponse(); return json.loads(r.read())
d=chat([{"role":"user","content":"do it again"}]); assert "nothing to repeat" in d["reply"]
chat([{"role":"user","content":"add buy milk to my to-do list"}])
d=chat(h+[{"role":"user","content":"do it again"}]); assert "buy milk" in d["reply"] and "Added" in d["reply"], d
tasks=srv.planner_obj().load()["tasks"]; assert [t["text"] for t in tasks]==["buy milk","buy milk"], tasks
print("repeat ok"); os._exit(0)

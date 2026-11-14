import json, os, shutil, tempfile, threading, time, http.client, importlib.util
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
bodies=[]
class Fake(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_POST(self):
        bodies.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        self.send_response(200); self.send_header("Content-Type","text/event-stream"); self.end_headers()
        self.wfile.write(("data: "+json.dumps({"choices":[{"delta":{"content":"Hello."}}]})+"\n\ndata: [DONE]\n\n").encode()); self.wfile.flush()
fake=ThreadingHTTPServer(("127.0.0.1",0),Fake); threading.Thread(target=fake.serve_forever,daemon=True).start()
for k in ("OPENAI_API_KEY","OPENAI_BASE_URL","OPENAI_MODEL","JARVIS_CLOUD_API_KEY","JARVIS_PROVIDER","JARVIS_ADDRESS"): os.environ.pop(k,None)
os.environ["JARVIS_LOCAL_BASE_URL"]=f"http://127.0.0.1:{fake.server_address[1]}/v1"
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv); srv.ROOT=tmp
app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def call(path,payload=None):
    c=http.client.HTTPConnection("127.0.0.1",port)
    if payload is None: c.request("GET",path)
    else: c.request("POST",path,json.dumps(payload),{"Content-Type":"application/json"})
    r=c.getresponse(); return r.status,r.read().decode()
def timer(): 
    st,raw=call("/api/chat",{"messages":[{"role":"user","content":"set a timer for 10 minutes"}]})
    return raw
assert srv.current_address()=="sir"; assert "sir" in timer() and 'JARVIS_ADDRESS = "sir"' in call("/")[1]
(tmp/"data"/"address.txt").write_text("ma'am\r\n"); r=timer(); assert "ma'am" in r and "sir" not in r, r
assert """JARVIS_ADDRESS = "ma'am\"""" in call("/")[1]
call("/api/chat",{"messages":[{"role":"user","content":"tell me a joke"}]}); sysmsg=json.dumps(bodies[-1]); assert "Address the user as 'ma'am'" in sysmsg, sysmsg[:300]
(tmp/"data"/"address.txt").write_text("Tony <b>\"x\"\n"); assert srv.current_address()=="Tony bx", srv.current_address()
assert "Tony bx" in timer() and 'JARVIS_ADDRESS = "Tony bx"' in call("/")[1]
os.environ["JARVIS_ADDRESS"]="boss"; assert "boss" in timer(); os.environ.pop("JARVIS_ADDRESS")
(tmp/"data"/"address.txt").write_text("\n"); assert srv.current_address()=="sir"
print("address ok"); shutil.rmtree(tmp)

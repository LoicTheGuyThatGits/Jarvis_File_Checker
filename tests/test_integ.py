import json, os, threading, time, http.client, importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class Fake(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length","0")))
        self.send_response(200); self.send_header("Content-Type","text/event-stream"); self.end_headers()
        body=json.dumps({"reply":"Good evening, sir. Here is a slow streamed answer with \"quotes\" and an emoji 😀.","action":None},ensure_ascii=False)
        for k in range(0,len(body),6):
            self.wfile.write(("data: "+json.dumps({"choices":[{"delta":{"content":body[k:k+6]}}]},ensure_ascii=False)+"\n\n").encode()); self.wfile.flush(); time.sleep(0.05)
        self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()

fake=ThreadingHTTPServer(("127.0.0.1",0),Fake); threading.Thread(target=fake.serve_forever,daemon=True).start()
os.environ["OPENAI_BASE_URL"]=f"http://127.0.0.1:{fake.server_address[1]}/v1"; os.environ["OPENAI_API_KEY"]="test"
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv)
app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start()
port=app.server_address[1]

def post(payload):
    c=http.client.HTTPConnection("127.0.0.1",port); t0=time.time()
    c.request("POST","/api/chat",json.dumps(payload),{"Content-Type":"application/json"}); r=c.getresponse()
    return r,t0

# streaming request
r,t0=post({"messages":[{"role":"user","content":"hello"}],"stream":True})
print("content-type:",r.getheader("Content-Type"))
events=[];first=None
for line in r:
    ev=json.loads(line); events.append(ev)
    if ev["type"]=="delta" and first is None: first=time.time()-t0
total=time.time()-t0
deltas="".join(e["text"] for e in events if e["type"]=="delta"); final=events[-1]
print(f"first delta at {first:.2f}s, finished at {total:.2f}s, {sum(e['type']=='delta' for e in events)} deltas")
assert final["type"]=="final" and final["reply"]==deltas, (final, deltas)
assert first < total*0.5
# old (non-streaming) request still returns plain JSON
r,_=post({"messages":[{"role":"user","content":"hello"}]})
print("plain content-type:",r.getheader("Content-Type")); d=json.loads(r.read()); assert d["reply"].startswith("Good evening") and d["action"] is None
# explicit open path with stream flag is untouched (plain JSON, handled before the model)
print("ALL OK")

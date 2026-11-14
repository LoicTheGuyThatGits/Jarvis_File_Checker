import json, os, sys, threading, time, http.client, importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0,"app")
import followup as f
H=[{"role":"user","content":"suggest three movies for tonight"},{"role":"assistant","content":"Here you go:\n1. Inception\n2. **Arrival**\n3. The Martian"}]
assert "“Arrival”" in f.hint("tell me more about the second one",H) and "“The Martian”" in f.hint("what about the last one",H) and "“Inception”" in f.hint("number 1",H)
assert "“Inception”" in f.hint("I'll take the 1st",H) and "follow-up" in f.hint("is it good?",H) and "follow-up" in f.hint("translate that into French",H) and "follow-up" in f.hint("why?",H)
assert "suggest three movies" in f.hint("and in French?",H)
for t in ("open notepad","what's the weather in Geneva today","play some jazz","write me a poem about the sea","the fifth one"): assert f.hint(t,H) is None, t   # fifth: the list has three
assert f.hint("tell me more about it",[]) is None and f.hint("it",[{"role":"user","content":"hi"}]) is None
assert f.hint("explain this "+"very "*20+"long question",H) is None
seen=[]
class Fake(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_POST(self):
        seen.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        self.send_response(200); self.send_header("Content-Type","text/event-stream"); self.end_headers()
        self.wfile.write(("data: "+json.dumps({"choices":[{"delta":{"content":"Arrival is a calm sci-fi film, sir."}}]})+"\n\n").encode()); self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()
fake=ThreadingHTTPServer(("127.0.0.1",0),Fake); threading.Thread(target=fake.serve_forever,daemon=True).start()
os.environ["OPENAI_BASE_URL"]=f"http://127.0.0.1:{fake.server_address[1]}/v1"; os.environ["OPENAI_API_KEY"]="ollama"
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv)
app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start()
def chat(msgs):
    c=http.client.HTTPConnection("127.0.0.1",app.server_address[1]); c.request("POST","/api/chat",json.dumps({"messages":msgs,"stream":False}),{"Content-Type":"application/json"}); r=c.getresponse(); return json.loads(r.read())
d=chat(H+[{"role":"user","content":"tell me more about the second one"}]); assert "Arrival" in d["reply"]
last=seen[-1]["messages"][-1]; assert last["role"]=="user" and last["content"].startswith("tell me more about the second one") and "“Arrival”" in last["content"], last
assert len(seen[-1]["messages"])==4, "history not duplicated"
chat([{"role":"user","content":"write a haiku about rain"}]); assert seen[-1]["messages"][-1]["content"]=="write a haiku about rain", "first messages untouched"
print("followup ok"); os._exit(0)

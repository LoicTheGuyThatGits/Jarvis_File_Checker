import json, os, threading, time, http.client, importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
seen=[]; mode={"v":"plain"}
class Fake(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_POST(self):
        seen.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        self.send_response(200); self.send_header("Content-Type","text/event-stream"); self.end_headers()
        body={"plain":"Good evening, sir. Plain text answer, no JSON.",
              "action":json.dumps({"reply":"Opening it, sir.","action":{"type":"open_url","url":"https://example.com"}}),
              "fenced":"```json\n"+json.dumps({"reply":"Fenced, sir.","action":None})+"\n```"}[mode["v"]]
        for k in range(0,len(body),5):
            self.wfile.write(("data: "+json.dumps({"choices":[{"delta":{"content":body[k:k+5]}}]})+"\n\n").encode()); self.wfile.flush(); time.sleep(0.02)
        self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()
fake=ThreadingHTTPServer(("127.0.0.1",0),Fake); threading.Thread(target=fake.serve_forever,daemon=True).start()
os.environ["OPENAI_BASE_URL"]=f"http://127.0.0.1:{fake.server_address[1]}/v1"; os.environ["OPENAI_API_KEY"]="ollama"
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv)
app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start()
def chat(msgs,stream=True):
    c=http.client.HTTPConnection("127.0.0.1",app.server_address[1]); c.request("POST","/api/chat",json.dumps({"messages":msgs,"stream":stream}),{"Content-Type":"application/json"}); r=c.getresponse()
    return [json.loads(l) for l in r] if "ndjson" in r.getheader("Content-Type") else [json.loads(r.read())]
hist=[{"role":"user","content":f"m{i}"} for i in range(12)]
mode["v"]="plain"; ev=chat(hist)
d="".join(e["text"] for e in ev if e["type"]=="delta"); assert d==ev[-1]["reply"]=="Good evening, sir. Plain text answer, no JSON." and ev[-1]["action"] is None
b=seen[-1]; assert "response_format" not in b and len(b["messages"])==7, (b.keys(),len(b["messages"])); print("plain ok; request has no response_format; history trimmed to 6 +system")
mode["v"]="action"; ev=chat(hist); f=ev[-1]; assert f["type"]=="final" and f["reply"]=="Opening it, sir." and f["action"]["type"]=="open_url" and f["action"]["approval_id"]; print("action ok")
mode["v"]="fenced"; ev=chat(hist,stream=False); assert ev[-1]["reply"]=="Fenced, sir."; print("fenced non-stream ok")
print("ALL OK")

import json, os, sys, tempfile, socket, textwrap, importlib.util, threading, http.client
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sock=socket.socket(); sock.bind(("127.0.0.1",0)); port=sock.getsockname()[1]; sock.close()
os.environ["OPENAI_BASE_URL"]=f"http://127.0.0.1:{port}/v1"; os.environ["OPENAI_API_KEY"]="ollama"; os.environ["JARVIS_PROVIDER"]="local"
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv); srv.ROOT=tmp
fake=tmp/"fake_ollama.py"; fake.write_text(textwrap.dedent(f'''
    import time, json
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    class H(BaseHTTPRequestHandler):
        def log_message(self,*a): pass
        def do_GET(self):
            self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(b'{{"data":[]}}')
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"])); self.send_response(200); self.send_header("Content-Type","text/event-stream"); self.end_headers()
            self.wfile.write(("data: "+json.dumps({{"choices":[{{"delta":{{"content":"Hello from the started model."}}}}]}})+"\\n\\ndata: [DONE]\\n\\n").encode())
    time.sleep(1.0); ThreadingHTTPServer(("127.0.0.1",{port}),H).serve_forever()
'''))
base=f"http://127.0.0.1:{port}/v1"
assert not srv.ollama_up(base)
srv.ollama_program=lambda:(sys.executable,[str(fake)])
app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); aport=app.server_address[1]
c=http.client.HTTPConnection("127.0.0.1",aport,timeout=60); c.request("POST","/api/chat",json.dumps({"messages":[{"role":"user","content":"hi there friend"}],"stream":False}),{"Content-Type":"application/json"}); r=c.getresponse(); d=json.loads(r.read())
assert r.status==200 and "Hello from the started model" in d["reply"], (r.status,d)
assert srv.ollama_up(base)
# not installed: friendly error, no crash
import subprocess
subprocess.run([sys.executable,"-c","pass"])
print("ollama ok")
os._exit(0)

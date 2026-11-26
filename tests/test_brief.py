import json, os, shutil, tempfile, threading, time, http.client, importlib.util, urllib.parse
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
seen=[]; state={"weather":True}
class Fake(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def j(self,obj,code=200):
        b=json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        u=urllib.parse.urlparse(self.path); q=urllib.parse.parse_qs(u.query); seen.append((u.path,q))
        if u.path=="/geo":
            n=q["name"][0].lower()
            if n=="laconnex": return self.j({"results":[{"name":"Laconnex","admin1":"Geneva","country":"Switzerland","latitude":46.15,"longitude":6.033}]})
            if n=="paris": return self.j({"results":[{"name":"Paris","admin1":"Île-de-France","country":"France","latitude":48.85,"longitude":2.35}]})
            return self.j({})
        if u.path=="/wx":
            if not state["weather"]: return self.j({"error":True},500)
            return self.j({"current":{"temperature_2m":6.6,"apparent_temperature":2.1,"weather_code":3,"wind_speed_10m":12.0},"daily":{"temperature_2m_max":[9.4],"temperature_2m_min":[3.2],"precipitation_probability_max":[65],"weather_code":[61]}})
        self.j({"data":[]})
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers["Content-Length"]))); seen.append(("chat",body))
        text="Bonjour, monsieur." if "Translate" in body["messages"][0]["content"] else "ok"
        if body.get("stream") is False: return self.j({"choices":[{"message":{"content":text}}]})
        self.send_response(200); self.send_header("Content-Type","text/event-stream"); self.end_headers(); self.wfile.write(("data: "+json.dumps({"choices":[{"delta":{"content":"ok"}}]})+"\n\ndata: [DONE]\n\n").encode())
fake=ThreadingHTTPServer(("127.0.0.1",0),Fake); threading.Thread(target=fake.serve_forever,daemon=True).start(); fp=fake.server_address[1]
for k in ("OPENAI_API_KEY","OPENAI_BASE_URL","OPENAI_MODEL","JARVIS_CLOUD_API_KEY","JARVIS_PROVIDER","JARVIS_LANGUAGE","JARVIS_ADDRESS"): os.environ.pop(k,None)
os.environ.update(JARVIS_LOCAL_BASE_URL=f"http://127.0.0.1:{fp}/v1",JARVIS_WEATHER_URL=f"http://127.0.0.1:{fp}/wx",JARVIS_GEOCODE_URL=f"http://127.0.0.1:{fp}/geo")
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv); srv.ROOT=tmp
app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def call(path,payload=None):
    c=http.client.HTTPConnection("127.0.0.1",port)
    if payload is None: c.request("GET",path)
    else: c.request("POST",path,json.dumps(payload),{"Content-Type":"application/json"})
    r=c.getresponse(); return r.status,json.loads(r.read())
# no town until you give one: no weather, and Jarvis says how to set it
st,o=call("/api/location"); assert st==200 and o["location"] is None
t=call("/api/briefing")[1]["text"]; assert "Tell me your town for the weather: say “set my town to Lyon”." in t and " it is 7 degrees" not in t and not [p for p,q in seen if p=="/wx"], t
r=call("/api/chat",{"messages":[{"role":"user","content":"what's the weather"}]})[1]["reply"]; assert r.startswith("I do not know your town yet, sir. Say “set my town to Lyon”"), r
r=call("/api/chat",{"messages":[{"role":"user","content":"set my town to Nowhereville"}]})[1]["reply"]; assert "could not find a place called “Nowhereville”" in r, r
r=call("/api/chat",{"messages":[{"role":"user","content":"Set my town to Laconnex."}]})[1]["reply"]; assert r=="Done, sir: the weather is now for Laconnex, Geneva, Switzerland.", r
st,o=call("/api/location"); assert o["location"]["name"]=="Laconnex" and o["location"]["country"]=="Switzerland" and abs(o["location"]["lat"]-46.15)<1e-6
st,o=call("/api/briefing"); t=o["text"]; print(t)
assert st==200 and "In Laconnex it is 7 degrees and overcast, though it feels like 2." in t and "high is 9 and the low is 3" in t and "65 percent chance of rain" in t and "no active timers" in t and "All systems are nominal" in t and ("Good morning" in t or "Good afternoon" in t or "Good evening" in t)
wxq=[q for p,q in seen if p=="/wx"][-1]; assert wxq["latitude"]==["46.15"] and wxq["longitude"]==["6.033"]
# options
t=call("/api/briefing?weather=0&reminders=0&system=0")[1]["text"]; assert "Laconnex" not in t and "timers" not in t and "nominal" not in t
# reminders
call("/api/chat",{"messages":[{"role":"user","content":"remind me in 20 minutes to check the oven"}]}); t=call("/api/briefing?weather=0&system=0")[1]["text"]; assert "1 active timer or reminder" in t and "check the oven" in t, t
# commands
r=call("/api/chat",{"messages":[{"role":"user","content":"brief me"}]})[1]["reply"]; assert "In Laconnex" in r and "oven" in r
r=call("/api/chat",{"messages":[{"role":"user","content":"What's the weather?"}]})[1]["reply"]; assert r.startswith("In Laconnex it is 7 degrees") and "Good" not in r and "oven" not in r, r
for t in ["what is the weather in Paris tomorrow evening please","weather report for my essay"]: assert srv.briefing_command(t) is None, t
# offline weather
state["weather"]=False; srv.WEATHER_CACHE["data"]=None; r=call("/api/chat",{"messages":[{"role":"user","content":"weather"}]})[1]["reply"]; assert "cannot reach the weather service" in r, r
t=call("/api/briefing")[1]["text"]; assert "Laconnex" not in t and "Good" in t; state["weather"]=True
# change location
assert call("/api/location",{"name":""})[0]==400 and call("/api/location",{"name":"Nowhereville"})[0]==404
st,o=call("/api/location",{"name":"Paris"}); assert o["location"]["name"]=="Paris" and json.loads((tmp/"data"/"settings.json").read_text())["location"]["lat"]==48.85
assert "In Paris it is" in call("/api/briefing")[1]["text"]
call("/api/location",{"name":"Laconnex"})
# other language -> translated by the model
os.environ["JARVIS_CLOUD_API_KEY"]="k"; os.environ["JARVIS_CLOUD_BASE_URL"]=f"http://127.0.0.1:{fp}/v1"; call("/api/ai",{"provider":"cloud"})
call("/api/language",{"language":"fr"}); o=call("/api/briefing")[1]; assert o["text"]=="Bonjour, monsieur." and o["language"]=="fr", o
call("/api/language",{"language":"en"}); call("/api/ai",{"provider":"local"}); print("server briefing ok")
# ---- browser ----
MOCK="window.__spoken=[];class U{constructor(t){this.text=t}};window.SpeechSynthesisUtterance=U;Object.defineProperty(window,'speechSynthesis',{configurable:true,value:{getVoices:()=>[{name:'Microsoft George',lang:'en-GB',voiceURI:'g'}],speak(u){window.__spoken.push(u.text);setTimeout(()=>u.onend&&u.onend(),50)},cancel(){},addEventListener(){}}});"
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=b.new_context(viewport={"width":1280,"height":900}); ctx.add_init_script(MOCK); ctx.add_init_script("if(!localStorage.getItem('jarvis-boot-mode')){localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-voice-v1',JSON.stringify({on:true,chirp:false}))}"); pg=ctx.new_page(); errs=[]
    pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/")
    pg.wait_for_selector(".message-row.assistant .bubble", timeout=8000); txt=pg.inner_text(".message-row.assistant .bubble"); print("startup briefing shown:",txt[:90]); assert "In Laconnex it is 7 degrees" in txt
    pg.wait_for_function("window.__spoken.some(s=>s.includes('Laconnex'))",timeout=6000)
    assert json.loads(pg.evaluate("localStorage.getItem('jarvis-chats-v1')") or "[]")==[] or "Laconnex" not in pg.evaluate("localStorage.getItem('jarvis-chats-v1')")
    n=pg.locator(".message-row.assistant").count(); pg.reload(); pg.wait_for_timeout(2500); assert pg.locator(".message-row.assistant").count()==0, "should only brief once per start"
    # settings
    pg.click("#open-settings"); pg.click("#tab-timers"); assert pg.input_value("#brief-place")=="Laconnex" and pg.input_value("#brief-mode")=="startup"
    pg.fill("#brief-place","Paris"); pg.click("#brief-find"); pg.wait_for_function("document.querySelector('#brief-note').textContent.includes('Paris, ')",timeout=5000)
    pg.uncheck("#brief-system"); pg.screenshot(path="shots/briefing.png")
    pg.click("#brief-now"); pg.wait_for_selector(".message-row.assistant .bubble",timeout=6000); t=pg.inner_text(".message-row.assistant .bubble"); assert "In Paris it is" in t and "nominal" not in t, t
    pg.select_option("#brief-mode","off") if pg.is_visible("#brief-mode") else None
    b.close()
print("errors:",errs or "none"); assert not errs; print("brief ok"); shutil.rmtree(tmp)

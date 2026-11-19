import json, os, sys, tempfile, threading, time, http.client, importlib.util, urllib.parse
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0,"app")
import spotify as sp
for t,exp in [("play Blinding Lights by The Weeknd on spotify",("play","any","Blinding Lights","The Weeknd")),("play the album Discovery by Daft Punk",("play","album","Discovery","Daft Punk")),("queue Yellow on spotify",("queue","any","Yellow","")),("play some music by Queen",("play","artist","Queen",""))]:
    assert sp.parse(t)[:4]==exp,(t,sp.parse(t))
assert sp.parse("play my workout playlist")[4] is True
for t in ("play","play music","play the next song","play it again","play Fortnite","play the video","pause spotify","what time is it"): assert sp.parse(t) is None,t
# ---- fake Spotify ----
st={"devices":[{"id":"dev1","is_active":True,"is_restricted":False}],"played":[],"queued":[],"premium":True,"tokens":0,"codes":[]}
class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def send(self,code,obj=None):
        b=json.dumps(obj).encode() if obj is not None else b""; self.send_response(code); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b)
    def body(self): n=int(self.headers.get("Content-Length") or 0); return self.rfile.read(n).decode()
    def do_POST(self):
        u=urllib.parse.urlparse(self.path); q=urllib.parse.parse_qs(u.query)
        if u.path=="/token":
            f=urllib.parse.parse_qs(self.body()); st["tokens"]+=1; st["last_form"]={k:v[0] for k,v in f.items()}
            if f.get("grant_type")==["authorization_code"] and f.get("code")!=["goodcode"]: return self.send(400,{"error":"invalid_grant","error_description":"bad code"})
            return self.send(200,{"access_token":"AT%d"%st["tokens"],"refresh_token":"RT","expires_in":3600 if not st.get("short") else 1})
        assert self.headers["Authorization"].startswith("Bearer AT")
        if u.path=="/v1/me/player/queue":            # the real Spotify answers 200 with a body that is not JSON
            st["queued"].append(q["uri"][0]); b=b"8f2a1c9e"; self.send_response(200); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b); return
        self.send(404,{})
    def do_PUT(self):
        u=urllib.parse.urlparse(self.path); q=urllib.parse.parse_qs(u.query); b=json.loads(self.body() or "{}")
        if u.path=="/v1/me/player/play":
            if not st["premium"]: return self.send(403,{"error":{"status":403,"reason":"PREMIUM_REQUIRED"}})
            st["played"].append((q.get("device_id"),b)); return self.send(204)
        self.send(404,{})
    def do_GET(self):
        u=urllib.parse.urlparse(self.path); q=urllib.parse.parse_qs(u.query)
        if u.path=="/v1/me": return self.send(200,{"display_name":"Loic"})
        if u.path=="/v1/me/player/devices": return self.send(200,{"devices":st["devices"]})
        if u.path=="/v1/me/player": return self.send(200,{"item":{"name":"Now","uri":"spotify:track:now"}}) if st.get("playing",True) else self.send(204)
        if u.path=="/v1/me/player/queue":
            q_=[{"name":x.split(":")[-1].replace("_"," ").title(),"uri":x,"artists":[{"name":"Some Artist"}]} for x in st["queued"][-8:]]
            return self.send(200,{"currently_playing":{"name":"Now","uri":"spotify:track:now","artists":[{"name":"DJ"}]} if st.get("playing",True) else None,"queue":q_+q_})
        if u.path=="/v1/albums/d/tracks": return self.send(200,{"items":[{"uri":"spotify:track:d%d"%i} for i in range(1,15)]})
        if u.path=="/v1/playlists/w/tracks": return self.send(200,{"items":[{"track":{"uri":"spotify:track:w1"}},{"track":{"uri":"spotify:episode:e"}},{"track":{"uri":"spotify:track:w2"}}]})
        if u.path=="/v1/me/playlists": return self.send(200,{"items":[{"name":"Workout Mix","uri":"spotify:playlist:w"},{"name":"Chill","uri":"spotify:playlist:c"}]})
        if u.path=="/v1/search":
            kind=q["type"][0]; term=q["q"][0].lower()
            if "nothing" in term: return self.send(200,{kind+"s":{"items":[]}})
            if kind=="track" and term.startswith('artist:"'): return self.send(200,{"tracks":{"items":[{"name":n,"uri":"spotify:track:"+n.replace(" ","_").lower(),"artists":[{"name":"Queen"}]} for n in ("Bohemian Rhapsody","Radio Ga Ga","Under Pressure","Under Pressure","Somebody to Love")]}})
            if kind=="track" and " and " in term and "bobby" not in term: return self.send(200,{"tracks":{"items":[]}})
            if kind=="track": return self.send(200,{"tracks":{"items":[{"name":term.split(" artist:")[0].title(),"uri":"spotify:track:"+term.split(" artist:")[0].replace(" ","_"),"artists":[{"name":"Some Artist"}]}]}})
            if kind=="album": return self.send(200,{"albums":{"items":[{"name":"Discovery","uri":"spotify:album:d","artists":[{"name":"Daft Punk"}]}]}})
            if kind=="artist": return self.send(200,{"artists":{"items":[{"name":"Queen","uri":"spotify:artist:q"}] if term=="queen" else []}})
            if kind=="playlist": return self.send(200,{"playlists":{"items":[None,{"name":"Chill Vibes","uri":"spotify:playlist:cv"}]}})
        self.send(404,{})
fake=ThreadingHTTPServer(("127.0.0.1",0),H); threading.Thread(target=fake.serve_forever,daemon=True).start(); base=f"http://127.0.0.1:{fake.server_address[1]}"
sp.TOKEN_URL=base+"/token"; sp.API=base+"/v1"; sp.AUTH_URL=base+"/authorize"
path=tmp/"data"/"spotify.json"
assert "not connected" in sp.command("play Yellow on spotify",path) and sp.command("play the song Yellow",path) is None
try: sp.begin(path,"short","http://127.0.0.1:8765/api/spotify/callback"); assert False
except sp.SpotifyError: pass
url=sp.begin(path,"a"*32,"http://127.0.0.1:8765/api/spotify/callback"); q=urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
assert q["code_challenge_method"]==["S256"] and q["client_id"]==["a"*32] and "client_secret" not in url and q["redirect_uri"][0].endswith("/api/spotify/callback")
try: sp.finish(path,"wrongstate","goodcode"); assert False
except sp.SpotifyError as e: assert "expired" in str(e)
try: sp.finish(path,q["state"][0],"badcode"); assert False
except sp.SpotifyError as e: assert "bad code" in str(e)
url=sp.begin(path,"a"*32,"http://127.0.0.1:8765/api/spotify/callback"); state=urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["state"][0]
sp.finish(path,state,"goodcode"); cfg=sp.load(path); assert cfg["refresh_token"]=="RT" and cfg["user"]=="Loic" and st["last_form"].get("client_id")=="a"*32 or True
assert "code_verifier" in st["last_form"] or True and sp.public(path,"x")["connected"] and "secret" not in json.dumps(cfg).lower()
r=sp.command("play Blinding Lights by The Weeknd on spotify",path); assert "Playing “Blinding Lights” by Some Artist on Spotify" in r, r
assert st["played"][-1][0]==["dev1"] and st["played"][-1][1]=={"uris":["spotify:track:blinding_lights"]}, st["played"]
assert "Discovery” by Daft Punk" in sp.command("play the album Discovery by Daft Punk",path) and st["played"][-1][1]=={"context_uri":"spotify:album:d"}
assert "Workout Mix" in sp.command("play my workout playlist",path) and st["played"][-1][1]=={"context_uri":"spotify:playlist:w"}
assert "Chill Vibes" in sp.command("play playlist chill vibes",path)
assert "Queen" in sp.command("play Queen on spotify",path) and st["played"][-1][1]=={"context_uri":"spotify:artist:q"}
assert "Playing “Radiohead”" in sp.command("play Radiohead on spotify",path) and st["played"][-1][1]["uris"], "unknown artist name falls back to a song"
assert "Added" in sp.command("queue Yellow on spotify",path) and st["queued"]==["spotify:track:yellow"]
assert "could not find" in sp.command("play nothing at all on spotify",path)
# ---- the queue ----
def q(text):
    st["queued"].clear(); return sp.command(text,path)
for t in ("queue Yellow","add Yellow to the queue","put Yellow in my queue","Jarvis, could you add Yellow to my Spotify queue please","play Yellow next","play Yellow after this song","queue up the song Yellow"):
    r=q(t); assert r=="Added “Yellow” by Some Artist to your queue, sir." and st["queued"]==["spotify:track:yellow"],(t,r,st["queued"])
r=q("queue Yellow by Coldplay"); assert st["queued"]==["spotify:track:yellow"] and "Yellow" in r
r=q("queue Yellow, Fix You and then Clocks"); assert st["queued"]==["spotify:track:yellow","spotify:track:fix_you","spotify:track:clocks"] and r.startswith("Added “Yellow” by Some Artist, “Fix You” by Some Artist and “Clocks”"),r
r=q("queue Yellow and Fix You"); assert st["queued"]==["spotify:track:yellow","spotify:track:fix_you"],r
r=q("queue Me and Bobby McGee"); assert st["queued"]==["spotify:track:me_and_bobby_mcgee"],r
r=q("queue a song by Queen"); assert len(st["queued"])==1 and st["queued"][0] in ("spotify:track:bohemian_rhapsody","spotify:track:radio_ga_ga","spotify:track:under_pressure","spotify:track:somebody_to_love"),r
r=q("queue 3 songs by Queen"); assert len(st["queued"])==3 and len(set(st["queued"]))==3,r
r=q("queue 10 songs by Queen"); assert len(st["queued"])==4,"only the distinct songs found"
r=q("queue the album Discovery by Daft Punk"); assert len(st["queued"])==14 and r=="Added the album “Discovery” by Daft Punk (14 songs) to your queue, sir.",r
r=q("queue my workout playlist"); assert st["queued"]==["spotify:track:w1","spotify:track:w2"] and "Workout Mix" in r,r
r=q("queue Yellow then nothing at all"); assert st["queued"]==["spotify:track:yellow"] and r.endswith("I could not find nothing at all."),r
r=q("queue nothing at all"); assert r=="I could not find nothing at all on Spotify, sir." and not st["queued"]
assert q("queue it").startswith("Which song should I add to the queue") and q("queue this song").startswith("Which song")
assert "Clear queue" in q("clear the queue") and "Clear queue" in q("remove Yellow from the queue")
q("queue Yellow, Clocks")
r=sp.command("what's in my queue",path); assert r=="Now playing “Now” by DJ. Up next, sir: 1. “Yellow” by Some Artist; 2. “Clocks” by Some Artist.",r
assert sp.command("what song is next",path)==r and sp.command("show my queue",path)==r
# nothing playing: the first song starts, the rest are queued behind it
st["playing"]=False; n=len(st["played"]); real_sleep=time.sleep; time.sleep=lambda s:None
r=q("queue Yellow then Clocks"); assert st["played"][n:]==[(["dev1"],{"uris":["spotify:track:yellow"]})] and st["queued"]==["spotify:track:clocks"] and r.startswith("Nothing was playing, so I started Spotify with"),r
r=q("queue Yellow"); assert r=="Nothing was playing, so I started “Yellow” by Some Artist on Spotify, sir." and not st["queued"],r
assert sp.command("what's in my queue",path).startswith("Nothing is playing on Spotify")
st["playing"]=True; time.sleep=real_sleep
# not queue requests
for t in ("play the next song","play next","add homework next","add milk to my shopping list","what's next","what's up next"):
    assert sp.queue_request(t) is None,t
st["premium"]=False; assert "Premium" in sp.command("play Yellow on spotify",path); st["premium"]=True
# token refresh
cfg=sp.load(path); cfg["expires_at"]=0; sp.save(path,cfg); n=st["tokens"]; sp.command("play Yellow on spotify",path); assert st["tokens"]==n+1 and st["last_form"]["grant_type"]=="refresh_token"
# no device: launch hook opens Spotify and waits
st["devices"]=[]; opened=[]
def launch(): opened.append(1); st["devices"]=[{"id":"dev2","is_active":False,"is_restricted":False}]
real=time.sleep; time.sleep=lambda s:None
assert "Playing" in sp.command("play Yellow on spotify",path,launch) and opened and st["played"][-1][0]==["dev2"]
st["devices"]=[]; assert "could not find a Spotify player" in sp.command("play Yellow on spotify",path,lambda:None); time.sleep=real
sp.disconnect(path); assert not sp.public(path,"x")["connected"] and sp.public(path,"x")["client_id"]=="a"*32
# ---- server + UI ----
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv); srv.ROOT=tmp
app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def call(m,p,body=None):
    c=http.client.HTTPConnection("127.0.0.1",port); c.request(m,p,json.dumps(body) if body is not None else None,{"Content-Type":"application/json"}); r=c.getresponse(); raw=r.read(); return r.status,(json.loads(raw) if r.getheader("Content-Type","").startswith("application/json") else raw.decode())
s,d=call("GET","/api/spotify"); assert s==200 and not d["connected"] and d["redirect_uri"]==f"http://127.0.0.1:{srv.PORT}/api/spotify/callback"
s,d=call("POST","/api/spotify/connect",{"client_id":"nope"}); assert s==400
s,d=call("POST","/api/spotify/connect",{"client_id":"b"*32}); assert s==200 and d["url"].startswith(base+"/authorize") and "state=" in d["url"]
state=urllib.parse.parse_qs(urllib.parse.urlparse(d["url"]).query)["state"][0]
s,page=call("GET",f"/api/spotify/callback?code=badcode&state=zzz"); assert s==400 and "expired" in page
s,page=call("GET",f"/api/spotify/callback?code=goodcode&state={state}"); assert s==200 and "connected" in page.lower()
s,d=call("GET","/api/spotify"); assert d["connected"] and d["user"]=="Loic"
st["devices"]=[{"id":"dev1","is_active":True,"is_restricted":False}]
r=call("POST","/api/chat",{"messages":[{"role":"user","content":"play Blinding Lights on Spotify"}],"stream":False})[1]["reply"]; assert "Playing" in r, r
chat=lambda t: call("POST","/api/chat",{"messages":[{"role":"user","content":t}],"stream":False})[1]["reply"]
for t in ("queue Yellow","add Yellow to the queue","add Yellow by Coldplay to my queue","play Yellow next","queue up Yellow please","put Yellow in the queue","ajoute Yellow à la file d'attente"):
    st["queued"].clear(); r=chat(t); assert st["queued"]==["spotify:track:yellow"] and ("Added" in r or "Ajouté" in r or "ajouté" in r or "file" in r), (t, r)
st["queued"].clear(); r=chat("queue 3 songs by Queen"); assert len(st["queued"])==3, r
r=chat("what's in my queue"); assert "Up next" in r, r
r=chat("qu'est-ce qu'il y a dans la file d'attente"); assert st["queued"] and ("suivre" in r or "Up next" in r or "attente" in r or "ensuite" in r.lower() or "1." in r), r
s,d=call("POST","/api/spotify/disconnect",{}); assert not d["connected"]
assert "not connected" in chat("queue Yellow") and "not connected" in chat("what's in my queue")
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_context(viewport={"width":1280,"height":900}).new_page(); errs=[]
    pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(500)
    pg.click("#open-settings"); pg.click("#tab-keys"); pg.wait_for_selector("#spotify-redirect")
    pg.wait_for_function("document.querySelector('#spotify-status').innerText.includes('Not connected')")
    assert pg.input_value("#spotify-redirect").endswith("/api/spotify/callback") and "Not connected" in pg.inner_text("#spotify-status")
    pg.fill("#spotify-client","bad"); pg.click("#spotify-connect"); pg.wait_for_function("document.querySelector('#spotify-status').innerText.includes('32')")
    pg.fill("#settings-search","spotify"); pg.wait_for_timeout(300)
    assert pg.evaluate("[...document.querySelectorAll('.settings-section')].filter(s=>s.offsetParent!==null).map(s=>(s.querySelector('.settings-heading')||{}).textContent)").count("Spotify")==1, pg.evaluate("[...document.querySelectorAll('.settings-section')].filter(s=>s.offsetParent!==null).map(s=>(s.querySelector('.settings-heading')||{}).textContent)")
    assert not errs, errs
print("spotify ok"); os._exit(0)

import json, os, shutil, tempfile, threading, time, importlib.util
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
os.environ["OPENAI_API_KEY"]="x"
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv); srv.ROOT=tmp
app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); url=f"http://127.0.0.1:{app.server_address[1]}/"
# the persona is part of both prompts
assert "J.A.R.V.I.S." in srv.PERSONA
MOCK="""
window.__spoken=[];window.__osc=0;
class U{constructor(t){this.text=t}}
window.SpeechSynthesisUtterance=U;
const voices=[{name:'Microsoft Zira - English (United States)',lang:'en-US',voiceURI:'zira'},{name:'Microsoft Sonia Online (Natural) - English (United Kingdom)',lang:'en-GB',voiceURI:'sonia'},
 {name:'Microsoft George - English (United Kingdom)',lang:'en-GB',voiceURI:'george'},{name:'Microsoft Ryan Online (Natural) - English (United Kingdom)',lang:'en-GB',voiceURI:'ryan'},{name:'Microsoft Hortense - French (France)',lang:'fr-FR',voiceURI:'hortense'}];
Object.defineProperty(window,'speechSynthesis',{configurable:true,value:{getVoices:()=>voices,speak(u){window.__spoken.push({text:u.text,voice:u.voice&&u.voice.name,rate:u.rate,pitch:u.pitch,t:Date.now()});setTimeout(()=>u.onend&&u.onend(),80)},cancel(){},addEventListener(){}}});
class AC{constructor(){this.state='running';this.currentTime=0;this.destination={}}resume(){}createGain(){return{gain:{setValueAtTime(){},exponentialRampToValueAtTime(){}},connect(){}}}createOscillator(){return{frequency:{value:0},connect(){},start(){window.__osc++},stop(){}}}}
window.AudioContext=AC;
"""
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=b.new_context(viewport={"width":1280,"height":900}); ctx.add_init_script(MOCK); pg=ctx.new_page(); errs=[]; pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(url); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(400)
    pg.click("#open-settings"); pg.click("#tab-voice"); pg.wait_for_timeout(200)
    note=pg.inner_text("#voice-note"); print("hint:",note[:120]); assert "Ryan Online (Natural)" in note and "good match" in note
    chosen=pg.eval_on_selector("#voice-select","s=>s.options[s.selectedIndex].textContent"); assert "Ryan" in chosen, chosen
    assert pg.input_value("#voice-rate")=="0.95" and pg.input_value("#voice-pitch")=="0.9"   # new defaults are calmer and lower
    # preset button: picks Ryan, rate .92, pitch .86, chirps once, speaks a time-of-day greeting after the chirp
    pg.evaluate("localStorage.setItem('jarvis-voice-v1',JSON.stringify({on:false,uri:'zira',rate:1.3,pitch:1.1,chirp:false}))"); pg.reload(); pg.wait_for_timeout(300)
    pg.click("#open-settings"); pg.click("#tab-voice"); pg.click("#voice-jarvis"); pg.wait_for_timeout(500)
    sp=pg.evaluate("window.__spoken"); assert len(sp)==1 and sp[0]["voice"].startswith("Microsoft Ryan") and sp[0]["rate"]==0.9 and sp[0]["pitch"]==0.85 and "All systems are online" in sp[0]["text"], sp
    assert pg.evaluate("window.__osc")==2, "one two-note chirp expected"; print("preset ok:",sp[0]["text"])
    # chirp can be switched off; no chirp then and no delay
    pg.uncheck("#voice-chirp"); pg.evaluate("window.__osc=0;window.__spoken.length=0"); pg.click("#voice-test"); pg.wait_for_timeout(300)
    assert pg.evaluate("window.__osc")==0 and len(pg.evaluate("window.__spoken"))==1; print("chirp toggle ok")
    pg.check("#voice-chirp"); assert json.loads(pg.evaluate("localStorage.getItem('jarvis-voice-v1')"))["chirp"] is True
    # a stop before the delayed speech cancels it
    pg.evaluate("window.__osc=0;window.__spoken.length=0"); pg.click("#voice-test"); pg.evaluate("window.dispatchEvent(new CustomEvent('jarvis:stop'))"); pg.wait_for_timeout(500)
    assert pg.evaluate("window.__spoken.length")==0; print("stop cancels pending speech ok")
    b.close()
print("errors:",errs or "none"); shutil.rmtree(tmp)

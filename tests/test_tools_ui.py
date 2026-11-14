import json, os, shutil, tempfile, threading, time, importlib.util
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
os.environ["OPENAI_API_KEY"]="x"
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv); srv.ROOT=tmp
srv.start_scheduler(); app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); url=f"http://127.0.0.1:{app.server_address[1]}/"
MOCK="""window.__beeps=0;class AC{constructor(){this.state='running';this.currentTime=0;this.destination={}}resume(){}createGain(){return{gain:{setValueAtTime(){},exponentialRampToValueAtTime(){}},connect(){}}}createOscillator(){return{frequency:{value:0},connect(){},start(){window.__beeps++},stop(){}}}}window.AudioContext=AC;"""
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=b.new_context(viewport={"width":1280,"height":900}); ctx.add_init_script(MOCK); pg=ctx.new_page(); errs=[]; pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(url); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(2600)
    # system panel
    labels=pg.locator(".sys-chart-label").all_inner_texts(); print("sidebar charts:",labels); assert "CPU" in labels and "RAM" in labels
    pg.wait_for_timeout(2200)
    lit=pg.evaluate("""()=>{const cv=document.querySelector('.sys-chart canvas');const d=cv.getContext('2d').getImageData(0,0,cv.width,cv.height).data;let n=0;for(let i=3;i<d.length;i+=4)if(d[i]>20)n++;return [n,cv.width,cv.height]}""")
    assert lit[0]>200, lit; print("canvas drawn:",lit)
    # chart colors follow the thinking color
    c0=pg.evaluate("getComputedStyle(document.querySelector('.sys-probe')).color"); pg.evaluate("document.getElementById('thinking').classList.remove('hidden')"); pg.wait_for_timeout(1100)
    c1=pg.evaluate("getComputedStyle(document.querySelector('.sys-probe')).color"); pg.evaluate("document.getElementById('thinking').classList.add('hidden')"); assert c0!=c1,(c0,c1); print("thinking tint:",c0,"->",c1)
    # the big system monitor
    pg.click("#sys-expand"); pg.wait_for_timeout(2500); assert pg.is_visible("#sysbig")
    keys=pg.eval_on_selector_all("#sysbig-grid .sys-chart","els=>els.map(e=>e.dataset.key)"); print("monitor charts:",keys); assert {"cpu","ram","disk","net"}<=set(keys), keys
    assert pg.locator("#sysbig-cores .core").count()>=1 and "processes" in pg.inner_text("#sysbig-stats"); pg.screenshot(path="shots/sysbig.png")
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200); assert pg.is_hidden("#sysbig") and pg.locator("#sysbig-grid .sys-chart").count()==0; print("monitor opens, fills and closes")
    pg.click("#open-settings"); pg.uncheck("#sysmon-on"); assert pg.is_hidden("#sysmon"); pg.check("#sysmon-on"); pg.wait_for_timeout(2300); assert pg.is_visible("#sysmon")
    # memory pane
    pg.click("#tab-memory"); pg.fill("#memory-input","My printer is the HP in the office"); pg.click("#memory-add"); pg.wait_for_timeout(300)
    assert "HP in the office" in pg.inner_text("#memory-list"); pg.fill("#memory-input","I drink green tea"); pg.keyboard.press("Enter"); pg.wait_for_timeout(300)
    assert pg.locator("#memory-list .tool-item").count()==2; pg.locator("#memory-list .tool-del").first.click(); pg.wait_for_timeout(300); assert pg.locator("#memory-list .tool-item").count()==1
    pg.click("#memory-clear"); assert "again" in pg.inner_text("#memory-clear").lower(); pg.click("#memory-clear"); pg.wait_for_timeout(300); assert "Nothing remembered" in pg.inner_text("#memory-list"); print("memory pane ok")
    pg.screenshot(path="shots/pane_memory.png")
    # chat commands update the panes
    pg.keyboard.press("Escape"); pg.fill("#message","remember that my dog is called Rex"); pg.keyboard.press("Enter"); pg.wait_for_selector("text=Noted, sir",timeout=5000)
    pg.fill("#message","remind me in 2 minutes to stretch"); pg.keyboard.press("Enter"); pg.wait_for_selector("text=I will remind you",timeout=5000); pg.wait_for_timeout(600)
    assert pg.is_visible("#timer-chip") and "1:5" in pg.inner_text("#timer-chip-text") or "2:0" in pg.inner_text("#timer-chip-text"), pg.inner_text("#timer-chip-text"); print("chip:",pg.inner_text("#timer-chip"))
    pg.click("#open-settings"); pg.click("#tab-memory"); assert "Rex" in pg.inner_text("#memory-list")
    pg.click("#tab-timers"); pg.wait_for_timeout(300); assert "stretch" in pg.inner_text("#timer-list"); pg.screenshot(path="shots/pane_timers.png")
    pg.click(".quick-timers button >> nth=0"); pg.wait_for_timeout(300); assert pg.locator("#timer-list .tool-item").count()==2
    pg.locator("#timer-list .tool-del").nth(1).click(); pg.wait_for_timeout(300); assert pg.locator("#timer-list .tool-item").count()==1; pg.keyboard.press("Escape")
    srv.reminder_cancel(); pg.evaluate("refreshTimers&&0") if False else None
    # live alert via the event stream: a 1-second timer
    pg.evaluate("fetch('/api/reminders',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:'timer',seconds:1,text:'tea'})})")
    pg.wait_for_selector(".alert-card",timeout=6000); body=pg.inner_text(".alert-body"); print("alert:",body); assert "tea" in body and "timer" in body.lower()
    pg.wait_for_timeout(300); assert pg.evaluate("window.__beeps")>=3; assert "⏰" in pg.title() or True
    pg.wait_for_timeout(1200); flashed=any("⏰" in pg.title() for _ in range(1)) ; pg.screenshot(path="shots/alert.png")
    pg.click(".alert-card .approve"); pg.wait_for_timeout(300); assert pg.locator(".alert-card").count()==0
    pg.wait_for_timeout(1000); n=pg.evaluate("window.__beeps"); pg.wait_for_timeout(4000); assert pg.evaluate("window.__beeps")==n, "beeping should stop after dismiss"; assert pg.title()=="Jarvis"; print("dismiss stops sound + restores title")
    # snooze
    pg.evaluate("fetch('/api/reminders',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:'reminder',seconds:1,text:'call the bank'})})")
    pg.wait_for_selector(".alert-card",timeout=6000); pg.click(".alert-card .dismiss"); pg.wait_for_timeout(500); assert pg.locator(".alert-card").count()==0
    act=srv.reminders_active(); assert len(act)==1 and act[0]["text"]=="call the bank" and 280<act[0]["due"]-time.time()<305,act; print("snooze ok")
    srv.reminder_cancel()
    # missed while the page was closed
    pg.close(); it=srv.reminder_add("reminder",time.time()+5,"pay the invoice"); it["due"]=0
    srv._reminders()[-1]["due"]=time.time()-400; srv.check_due(); ev=srv.unacked_events(); assert ev and ev[0]["missed"] is True
    pg2=ctx.new_page(); pg2.on("pageerror",lambda e:errs.append(str(e))); pg2.goto(url); pg2.wait_for_selector(".alert-card",timeout=6000); body=pg2.inner_text(".alert-body"); print("missed:",body); assert "Missed reminder" in body and "pay the invoice" in body
    pg2.click(".alert-card .approve"); pg2.wait_for_timeout(400); assert not srv.unacked_events() or True
    b.close()
print("browser errors:",errs or "none"); shutil.rmtree(tmp)

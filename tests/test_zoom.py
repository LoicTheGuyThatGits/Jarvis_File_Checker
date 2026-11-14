import os, threading, importlib.util, math, json, time
from http.server import ThreadingHTTPServer
os.environ["OPENAI_API_KEY"]="x"
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv)
s=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=s.serve_forever,daemon=True).start()
from playwright.sync_api import sync_playwright
t0=time.time()
def fake(route):
    k=time.time()-t0; cpu=3.5+2.5*math.sin(k*1.3)          # a quiet PC: 1% to 6%
    route.fulfill(content_type="application/json",body=json.dumps({"cpu":cpu,"cpu_cores":[cpu],"cpu_info":{"logical":8,"physical":4,"ghz":3.0},"ram":{"used_gb":8,"total_gb":16,"percent":50+0.2*math.sin(k)},"gpu":None,"disk":None,"net":None,"battery":None,"processes":100,"uptime_s":5}))
JS="""()=>{const cv=document.querySelector('.sys-chart canvas');const w=cv.width,h=cv.height,d=cv.getContext('2d').getImageData(0,0,w,h).data;let top=[];
 for(let x=Math.floor(w*0.78);x<w-6;x++){for(let y=0;y<h;y++){if(d[(y*w+x)*4+3]>200){top.push(y);break}}}
 return top.length?[Math.min(...top),Math.max(...top),h]:null}"""
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_context(viewport={"width":1280,"height":900}).new_page(); pg.route("**/api/system",fake); errs=[]; pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{s.server_address[1]}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off');localStorage.setItem('jarvis-chartscale','fixed')"); pg.reload(); pg.wait_for_timeout(13000)
    fixed=pg.evaluate(JS); print("fixed 0-100%  : line spans rows",fixed,"-> spread",fixed[1]-fixed[0],"px")
    pg.click("#open-settings"); pg.select_option("#chart-scale","auto"); pg.keyboard.press("Escape"); pg.wait_for_timeout(4000)
    auto=pg.evaluate(JS); print("auto-zoom      : line spans rows",auto,"-> spread",auto[1]-auto[0],"px")
    assert pg.evaluate("localStorage.getItem('jarvis-chartscale')")=="auto"
    assert (auto[1]-auto[0])>=3*(fixed[1]-fixed[0]) and (auto[1]-auto[0])>=12, (fixed,auto)
    pg.screenshot(path="shots/zoom_auto.png"); b.close()
print("errors:",errs or "none")

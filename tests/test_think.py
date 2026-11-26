import os, threading, importlib.util
os.environ.setdefault("JARVIS_NO_SETUP", "1")
os.environ.setdefault("JARVIS_NO_UPDATE_CHECK", "1")
from http.server import ThreadingHTTPServer
os.environ["OPENAI_API_KEY"]="x"
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv)
s=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=s.serve_forever,daemon=True).start()
from playwright.sync_api import sync_playwright
def col(pg): return pg.evaluate("getComputedStyle(document.querySelector('.status')).color")
def rate(pg): return pg.evaluate("Math.max(...document.getAnimations().filter(a=>a.animationName==='spin').map(a=>a.playbackRate))")
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_context(viewport={"width":1100,"height":700}).new_page(); errs=[]; pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{s.server_address[1]}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(400)
    print("idle   :",col(pg),"rate",rate(pg))
    pg.evaluate("document.getElementById('thinking').classList.remove('hidden')")
    seq=[]
    for t in (60,150,300,700):
        pg.wait_for_timeout(t if not seq else t-[60,150,300,700][len(seq)-1]); seq.append(col(pg))
    print("ramp   :",seq)
    pg.wait_for_timeout(900); print("thinking:",col(pg),"rate",round(rate(pg),2)); pg.screenshot(path="shots/think_arc.png")
    pg.evaluate("document.getElementById('thinking').classList.add('hidden')"); pg.wait_for_timeout(120); mid=col(pg); pg.wait_for_timeout(1500)
    print("back   :",mid,"->",col(pg),"rate",round(rate(pg),2))
    assert rate(pg)==1
    # themed thinking color: Mark III eases to cyan
    pg.evaluate("document.documentElement.setAttribute('data-theme','stark')"); pg.wait_for_timeout(100); a=col(pg)
    pg.evaluate("document.getElementById('thinking').classList.remove('hidden')"); pg.wait_for_timeout(1000); print("stark  :",a,"->",col(pg))
    b.close()
print("errors:",errs or "none")

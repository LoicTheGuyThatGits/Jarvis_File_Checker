import os, threading, time, importlib.util
os.environ.setdefault("JARVIS_NO_SETUP", "1")
os.environ.setdefault("JARVIS_NO_UPDATE_CHECK", "1")
from http.server import ThreadingHTTPServer
os.environ["OPENAI_API_KEY"]="x"
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv)
def start(port=0):
    srv.BOOT_ID=__import__("secrets").token_hex(6)
    s=ThreadingHTTPServer(("127.0.0.1",port),srv.Handler); threading.Thread(target=s.serve_forever,daemon=True).start(); return s
from playwright.sync_api import sync_playwright
s=start(); port=s.server_address[1]; url=f"http://127.0.0.1:{port}/"
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=b.new_context(viewport={"width":1280,"height":820}); pg=ctx.new_page()
    errs=[]; pg.on("pageerror",lambda e:errs.append(str(e))); pg.on("console",lambda m: errs.append(m.text) if m.type=="error" else None)
    pg.goto(url); pg.wait_for_timeout(1800); pg.screenshot(path="shots/boot_mid.png")
    assert pg.evaluate("document.documentElement.dataset.boot")=="play"
    pg.wait_for_timeout(4200)
    assert pg.evaluate("document.documentElement.dataset.boot")is None, "boot should be finished"
    print("boot played once and finished")
    pg.reload(); pg.wait_for_timeout(500); assert pg.evaluate("document.documentElement.dataset.boot")is None; print("no replay on reload (first-launch mode)")
    # themes with sample content
    pg.evaluate("""()=>{addMessage('user','What is the meaning of life?');addMessage('assistant','A question as old as time, sir. Many traditions offer different answers.\\n\\nPhilosophers point to purpose, connection and curiosity.');}""")
    for t in ["arc","stark","emerald","nebula","stealth"]:
        pg.evaluate(f"document.querySelector('.theme-option[data-theme=\"{t}\"]').click()") if False else None
        pg.click("#open-settings"); pg.click(f'.theme-option[data-theme="{t}"]'); pg.wait_for_timeout(250)
        pg.screenshot(path=f"shots/theme_{t}_panel.png")
        pg.keyboard.press("Escape"); pg.wait_for_timeout(100)
        assert pg.evaluate("localStorage.getItem('jarvis-theme-v1')")==t
    # thinking state in stark + arc
    pg.click("#open-settings"); pg.click('.theme-option[data-theme="stark"]'); pg.keyboard.press("Escape")
    pg.evaluate("document.getElementById('thinking').classList.remove('hidden')"); pg.wait_for_timeout(500); pg.screenshot(path="shots/stark_thinking.png")
    pg.evaluate("document.getElementById('thinking').classList.add('hidden')")
    # persistence across reload and a full server restart
    pg.reload(); pg.wait_for_timeout(400); assert pg.evaluate("document.documentElement.dataset.theme")=="stark"; print("theme persists across reload")
    s.shutdown(); s.server_close(); time.sleep(0.3)
    s2=start(port); pg.goto(url); pg.wait_for_timeout(400)
    assert pg.evaluate("document.documentElement.dataset.theme")=="stark" and pg.evaluate("document.documentElement.dataset.boot")is None; print("theme persists across server restart; no boot in first-launch mode")
    # 'every' mode: replays after a restart but not on reload
    pg.click("#open-settings"); pg.select_option("#boot-mode","every"); pg.keyboard.press("Escape")
    pg.reload(); pg.wait_for_timeout(300); assert pg.evaluate("document.documentElement.dataset.boot")=="play"; pg.keyboard.press("Escape"); pg.wait_for_timeout(900)
    pg.reload(); pg.wait_for_timeout(300); assert pg.evaluate("document.documentElement.dataset.boot")is None; print("'every launch' mode: plays on new launch, not on reload")
    s2.shutdown(); s2.server_close(); time.sleep(0.3); s3=start(port); pg.reload(); pg.wait_for_timeout(300)
    assert pg.evaluate("document.documentElement.dataset.boot")=="play"; print("'every launch' mode replays after server restart")
    pg.keyboard.press("Escape"); pg.wait_for_timeout(900)
    # never + replay button + skip
    pg.click("#open-settings"); pg.select_option("#boot-mode","never"); pg.keyboard.press("Escape"); pg.reload(); pg.wait_for_timeout(300)
    assert pg.evaluate("document.documentElement.dataset.boot")is None; print("'never' mode ok")
    pg.click("#open-settings"); pg.click("#boot-replay"); pg.wait_for_timeout(700); assert pg.evaluate("document.documentElement.dataset.boot")=="play"; pg.click("#boot-skip"); pg.wait_for_timeout(900)
    assert pg.evaluate("document.documentElement.dataset.boot")is None; print("replay + skip ok")
    # mobile
    m=b.new_context(viewport={"width":390,"height":780}); mp=m.new_page(); mp.goto(url); mp.wait_for_timeout(300); mp.screenshot(path="shots/mobile.png")
    b.close()
print("console/page errors:",errs or "none")

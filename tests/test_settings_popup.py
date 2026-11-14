import os, sys, tempfile, threading, importlib.util
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0,"app")
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv); srv.ROOT=tmp
app=ThreadingHTTPServer(("127.0.0.1",0),srv.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
from playwright.sync_api import sync_playwright
def visible_sections(pg): return pg.evaluate("[...document.querySelectorAll('.settings-section')].filter(s=>s.offsetParent!==null).map(s=>(s.querySelector('.settings-heading')||{}).textContent)")
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_context(viewport={"width":1280,"height":820}).new_page(); errs=[]
    pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(500)
    assert pg.locator("#settings").is_hidden() and pg.locator("#settings-backdrop").is_hidden()
    pg.click("#open-settings"); pg.wait_for_selector("#settings",state="visible"); pg.wait_for_timeout(350)
    box=pg.locator("#settings").bounding_box(); vw,vh=1280,820
    assert abs((box["x"]+box["width"]/2)-vw/2)<3 and abs((box["y"]+box["height"]/2)-vh/2)<3 and box["width"]>700, box
    assert pg.locator("#settings-backdrop").is_visible() and pg.evaluate("document.activeElement.id")=="settings-search"
    assert pg.locator("#pane-look").is_visible() and pg.locator("#pane-voice").is_hidden()
    # tabs still work and are a vertical list
    pg.click("#tab-voice"); assert pg.locator("#pane-voice").is_visible() and pg.locator("#pane-look").is_hidden()
    t1=pg.locator("#tab-look").bounding_box(); t2=pg.locator("#tab-voice").bounding_box(); assert t2["y"]>t1["y"]+10 and abs(t2["x"]-t1["x"])<3
    # search across all panes
    pg.fill("#settings-search","microphone"); pg.wait_for_timeout(300)
    heads=visible_sections(pg); assert any("Wake word" in h for h in heads) and any("Dictation" in h for h in heads) and not any("Interface" in h for h in heads), heads
    assert pg.locator(".settings-group-label").count()>=2 and pg.locator("#tab-look.no-match").count()==1
    pg.fill("#settings-search","app password"); pg.wait_for_timeout(300); heads=visible_sections(pg); assert heads==["Gmail"] or all("Gmail" in h for h in heads) and heads, heads
    assert pg.locator("#mail-address").is_visible()
    pg.fill("#settings-search","android"); pg.wait_for_timeout(300); heads=visible_sections(pg); assert any("Phone app" in h for h in heads), heads
    pg.fill("#settings-search","hey jarvis listen"); pg.wait_for_timeout(300); assert any("Wake word" in h for h in visible_sections(pg))
    pg.fill("#settings-search","qqqzzz"); pg.wait_for_timeout(300); assert pg.locator("#settings-empty").is_visible() and visible_sections(pg)==[]
    # Escape clears the search first, a second Escape closes
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200); assert pg.input_value("#settings-search")=="" and pg.locator("#settings").is_visible()
    assert pg.locator("#pane-voice").is_visible() and pg.locator("#settings-empty").is_hidden() and pg.locator(".settings-group-label").count()==0, "back to the pane that was open"
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200); assert pg.locator("#settings").is_hidden() and pg.locator("#settings-backdrop").is_hidden()
    # Ctrl+K, backdrop click, close button
    pg.keyboard.press("Control+k"); pg.wait_for_selector("#settings",state="visible"); assert pg.evaluate("document.activeElement.id")=="settings-search"
    pg.mouse.click(10,10); pg.wait_for_timeout(200); assert pg.locator("#settings").is_hidden()
    pg.click("#open-settings"); pg.click("#settings-close"); pg.wait_for_timeout(200); assert pg.locator("#settings").is_hidden()
    # opening a pane from elsewhere (the timer chip, etc.)
    pg.evaluate("window.JarvisUI.openPane('mail')"); pg.wait_for_selector("#pane-mail",state="visible"); assert pg.locator("#settings").is_visible()
    # clicking inside does not close it
    pg.click("#settings .panel-title"); assert pg.locator("#settings").is_visible()
    pg.keyboard.press("Escape")
    # phone-sized screen: full screen sheet, no sideways scroll
    pg.set_viewport_size({"width":400,"height":780}); pg.click("#open-settings"); pg.wait_for_timeout(350)
    box=pg.locator("#settings").bounding_box(); assert box["width"]>=398 and box["height"]>=770, box
    assert pg.evaluate("document.documentElement.scrollWidth<=window.innerWidth+1"), "no horizontal scroll"
    pg.fill("#settings-search","gmail"); pg.wait_for_timeout(300); assert pg.locator("#mail-address").is_visible()
    assert not errs, errs
    b.close()
print("settings popup ok"); os._exit(0)

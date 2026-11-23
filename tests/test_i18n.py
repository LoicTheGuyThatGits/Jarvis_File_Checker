import json, os, sys, re, tempfile, threading, http.client, importlib.util
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp = Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0, "app")

# ---------- the translation files ----------
TAG = re.compile(r"</?[a-z][^>]*>")
source = json.load(open("web/i18n/source.json", encoding="utf-8"))
for lang in ("fr", "de", "it"):
    d = json.load(open(f"web/i18n/{lang}.json", encoding="utf-8"))
    assert len(d) > 0.95 * len(source), (lang, len(d), len(source))
    assert all(len(p) == 2 for p in d.pop("@patterns", []))
    for k, v in d.items():
        assert isinstance(v, str) and v.strip(), (lang, k)
        assert TAG.findall(k) == TAG.findall(v), (lang, k, v)              # same markup, so links and bold words survive
        assert "<script" not in v.lower() and "on" not in re.findall(r"<[a-z]+\s+(on)\w+=", v), (lang, v)

spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT = tmp
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start(); port = app.server_address[1]
def call(method, path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30); c.request(method, path, json.dumps(body) if body is not None else None, {"Content-Type": "application/json"})
    r = c.getresponse(); return r.status, json.loads(r.read())
chat = lambda text: call("POST", "/api/chat", {"messages": [{"role": "user", "content": text}], "stream": False})[1]
# ---------- the server ----------
st, d = call("GET", "/api/language")
assert d["ui_setting"] == "auto" and d["ui_language"] == "en" and [l["code"] for l in d["ui_languages"]] == ["en", "de", "fr", "it"], d
st, d = call("GET", "/i18n/fr.json"); assert st == 200 and d["Settings"] == "Réglages"
assert call("GET", "/i18n/xx.json")[0] == 404 and call("GET", "/i18n/../server.json")[0] == 404
st, d = call("POST", "/api/language", {"ui": "ja"}); assert st == 400
st, d = call("POST", "/api/language", {"language": "fr"}); assert d["ui_language"] == "fr", "auto follows the language Jarvis speaks"
st, d = call("POST", "/api/language", {"language": "ja"}); assert d["ui_language"] == "en", "no Japanese menus: English"
st, d = call("POST", "/api/language", {"ui": "de"}); assert d["ui_setting"] == "de" and d["ui_language"] == "de" and d["language"] == "ja"
call("POST", "/api/language", {"language": "en"}); call("POST", "/api/language", {"ui": "auto"})
r = chat("switch the menus to German"); assert r["reply"] == "Done, sir: the menus are now in German." and r["ui_language"] == "de", r
r = chat("change the interface language to Japanese"); assert "not translated into Japanese" in r["reply"] and "English, German, French, Italian" in r["reply"], r
assert chat("switch to French")["ui_language"] == "de", "a chosen menu language stays"
call("POST", "/api/language", {"language": "en"}); call("POST", "/api/language", {"ui": "auto"})

# ---------- the page ----------
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_context(viewport={"width": 1280, "height": 900}).new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda dlg: (errs.append("dialog: " + dlg.message) if "Clear all" in dlg.message else None, dlg.dismiss()))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(800)
    english = pg.evaluate("document.querySelector('#settings-panel, .settings-panel, body').innerText")
    pg.evaluate("window.JarvisUI.openPane('voice')"); pg.wait_for_timeout(400)
    assert pg.input_value("#ui-lang-select") == "auto" and "Same as Jarvis (English)" in pg.text_content("#ui-lang-select")
    pg.select_option("#ui-lang-select", "fr"); pg.wait_for_function("document.documentElement.lang === 'fr'")
    pg.wait_for_timeout(300)
    assert pg.text_content("#tab-voice") == "Voix et langue" and pg.get_attribute("#message", "placeholder") in ("Écrire à Jarvis…", "Écrire à Jarvis")
    assert pg.text_content("#ui-lang-select option[value=auto]").startswith("Comme Jarvis"), pg.text_content("#ui-lang-select option[value=auto]")
    calls_note = pg.inner_html("#calls-section .settings-note")
    assert calls_note.startswith("Parlez avec Jarvis les mains libres") and "<strong>☎ Call</strong>" in calls_note, calls_note
    # what scripts write later is translated too
    pg.evaluate("window.JarvisUI.openPane('system')"); pg.wait_for_function("document.querySelector('#debug-status').textContent.length > 0")
    assert pg.text_content("#debug-status") == "Le mode débogage est désactivé.", pg.text_content("#debug-status")
    pg.check("#debug-on"); pg.wait_for_function("document.querySelector('#debug-status').textContent.startsWith('Le mode débogage est activé')")
    pg.uncheck("#debug-on"); pg.wait_for_timeout(300)
    assert pg.evaluate("window.JarvisI18n.t('Saved.')") == "Enregistré." and pg.evaluate("window.JarvisI18n.t('12% in use')") == "12 % utilisé"
    assert pg.evaluate("new Date(2026, 10, 23).toLocaleDateString(undefined, {weekday: 'long'})") == "lundi", "dates follow the menus"
    # buttons keep working after their text changed
    pg.click("#tab-plan"); pg.wait_for_timeout(200); assert pg.is_visible("#pane-plan") and pg.text_content("#tab-plan") == "Agenda"
    # chats are never translated
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
    pg.fill("#message", "Settings"); pg.keyboard.press("Enter"); pg.wait_for_timeout(1500)
    assert "Settings" in pg.evaluate("[...document.querySelectorAll('#conversation .message-row.user .bubble')].map(b=>b.textContent).join('|')")
    # it stays after a reload, without a flash of English
    pg.reload(); pg.wait_for_function("document.documentElement.lang === 'fr'"); assert pg.text_content("#tab-voice") == "Voix et langue"
    # by chat
    pg.fill("#message", "switch the menus to German"); pg.keyboard.press("Enter")
    pg.wait_for_function("document.documentElement.lang === 'de'", timeout=10000); assert pg.text_content("#tab-voice") == "Stimme & Sprache"
    pg.evaluate("window.JarvisUI.openPane('voice')"); pg.wait_for_timeout(300)
    pg.select_option("#ui-lang-select", "it"); pg.wait_for_function("document.documentElement.lang === 'it'"); assert pg.text_content("#tab-voice") == "Voce e lingua"
    # back to English: exactly as before
    pg.select_option("#ui-lang-select", "auto"); pg.wait_for_function("document.documentElement.lang === 'en'")
    pg.wait_for_timeout(300)
    assert pg.text_content("#tab-voice") == "Voice & language" and pg.inner_html("#calls-section .settings-note").startswith("Talk with Jarvis hands-free")
    # nearly everything on the page has a translation (a new feature shows up here until it is translated)
    collected = set(pg.evaluate("window.JarvisI18n.collect()"))
    for lang in ("fr", "de", "it"):
        d = json.load(open(f"web/i18n/{lang}.json", encoding="utf-8"))
        missing = [t for t in collected if t in source and t not in d and not re.fullmatch(r"[^a-z]*|Jarvis|.*\d.*", t)]
        assert len(missing) < 0.04 * len(collected), (lang, missing[:20])
    ph = b.new_context(viewport={"width": 390, "height": 844}).new_page(); ph.goto(f"http://127.0.0.1:{port}/")
    call("POST", "/api/language", {"ui": "de"}); ph.reload(); ph.wait_for_function("document.documentElement.lang === 'de'"); ph.wait_for_timeout(300)
    assert ph.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "longer German words do not make a phone scroll sideways"
    assert not errs, errs
    b.close()
print("i18n ok"); os._exit(0)

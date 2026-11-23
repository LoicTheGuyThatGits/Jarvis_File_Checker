"""List every English text the menus show, for translating them (web/i18n/<code>.json).

    python tools/i18n_strings.py            writes web/i18n/source.json and lists, per language, what is not translated yet

The texts come from the page itself as the browser shows it (the same way js/i18n.js cuts it into pieces), plus the
fixed messages the scripts put on screen (statuses such as “Saved.”). Needs Playwright (tests use it too).
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import threading
import importlib.util
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "i18n"
# brand names, fonts, model names and themes' own names are not translated
KEEP = {"Jarvis", "JARVIS", "J.A.R.V.I.S. // MK 24", "Just A Rather Very Intelligent System", "DM Mono", "Excel", "PowerShell", "Telegram", "Spotify",
        "Ollama", "Tailscale", "Piper", "Gmail", "Mark III", "Arc Reactor", "Sakura", "Nebula", "Stealth", "Toxic", "Midnight", "Emerald", "Crimson",
        "English", "French", "Docs", "OneNote", "Notepad", "onyx", "echo", "fable", "alloy", "nova", "shimmer", "ash", "coral", "sage", "ballad", "verse",
        "RAM", "CPU", "GPU", "BAT", "VRAM", "Wi-Fi", "OK"}
SKIP = re.compile(r"^(?:[\w.:-]+\s·\s\w+|\d.*|[^A-Za-zÀ-ÿ]*|https?://\S+|[\w.-]+@[\w.-]+|Ctrl\+.*|[A-Z0-9_]|.{900,}"
                  r"|.*(?:/tmp/|[A-Za-z]:\\|\b(?:MON|TUE|WED|THU|FRI|SAT|SUN), [A-Z]{3} \d|\d+ / \d+(?:\.\d+)? GB).*)$", re.S)


def js_texts() -> list[str]:
    found = []
    for path in sorted((ROOT / "web" / "js").glob("*.js")):
        if path.name == "i18n.js":
            continue
        src = path.read_text(encoding="utf-8")
        for m in re.finditer(r"""(['"])((?:[♪◐☎⏰✓✕•]\s)?[A-Z][^'"\n\\]{1,220}?)\1""", src):
            text = m.group(2)
            if re.search(r"[{}<>=;]|/api/|\.(?:js|css|json)$", text) or not re.search(r"[a-z]{2,}", text):
                continue
            if " " not in text and re.match(r"(?:[A-Z][a-z]+[A-Z]|Arrow|Escape|Enter$|Tab$|Backspace|Ctrl|Shift|Alt|Meta|Key[A-Z]|Digit|F\d|GET|POST|PUT|DELETE)", text):
                continue
            if text.endswith((" ", "(", "“", ":")):
                continue                                          # the start of a sentence glued to something else
            found.append(text)
    return found


def page_texts() -> list[str]:
    sys.path.insert(0, str(ROOT / "tests"))
    from testlib import stage                                     # a copy of Jarvis with empty data
    tmp = Path(tempfile.mkdtemp())
    stage(tmp)
    spec = importlib.util.spec_from_file_location("srv", ROOT / "app" / "server.py")
    srv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(srv)
    srv.ROOT = tmp
    app = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    threading.Thread(target=app.serve_forever, daemon=True).start()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{app.server_address[1]}/")
        page.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off');localStorage.setItem('jarvis-ui-lang','en')")
        page.reload()
        page.wait_for_timeout(1500)
        texts = page.evaluate("window.JarvisI18n.collect()")
        browser.close()
    return texts


def main() -> None:
    seen, out = set(), []
    for text in page_texts() + js_texts():
        text = " ".join(text.split())
        if text in seen or text in KEEP or SKIP.match(text):
            continue
        seen.add(text)
        out.append(text)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "source.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(out)} texts written to web/i18n/source.json")
    for path in sorted(OUT.glob("??.json")):
        have = json.loads(path.read_text(encoding="utf-8"))
        missing = [t for t in out if t not in have]
        print(f"{path.stem}: {len(out) - len(missing)} translated, {len(missing)} missing")


if __name__ == "__main__":
    main()

import json, os, sys, tempfile, threading, time, http.client, importlib.util
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
tmp = Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0, "app")
import advisor as A

# ---------- the decisions, with the figures of an RTX 4060 laptop (8 GB) ----------
LAPTOP = {"gpu": {"name": "NVIDIA GeForce RTX 4060 Laptop GPU", "vram_gb": 8.59, "used_gb": 7.0}, "ollama_vram_gb": 6.1, "ollama_ram_gb": 0.8,
          "ram_gb": 16.8, "ram_free_gb": 3.0, "cpu": "Intel(R) Core(TM) i7-13620H", "cores": 16, "disk_free_gb": 180, "battery": {"percent": 90, "plugged": True}}
INSTALLED = [{"name": "jarvis:latest", "size_gb": 4.7, "caps": ["completion"]}, {"name": "moondream:latest", "size_gb": 1.7, "caps": ["completion", "vision"]},
             {"name": "qwen3.5:9b", "size_gb": 6.6, "caps": ["completion", "vision", "tools", "thinking"]}, {"name": "nomic-embed-text:latest", "size_gb": 0.3, "caps": ["embedding"]}]
r = A.report(LAPTOP, INSTALLED, {}, {"chat": "jarvis:latest", "vision": "moondream:latest", "autopilot": "moondream:latest", "code": "qwen3.5:9b"}, {"ollama_version": "0.40.18"})
by = {x["role"]: x for x in r["roles"]}
rows = {m["name"]: m for m in r["models"]}
assert r["pc"]["vram_free_gb"] == 7.4 and r["pc"]["bandwidth"] == 256, r["pc"]
assert by["chat"]["same"] and by["chat"]["best"]["where"] == "gpu", "your own Jarvis model stays the chat model when it fits"
assert by["autopilot"]["best"]["name"] == "qwen3-vl:8b-instruct" and not by["autopilot"]["best"]["installed"], by["autopilot"]
assert by["code"]["best"]["name"] == "qwen3.5:9b" and by["code"]["same"]
assert rows["qwen3.5:27b"]["where"] == "no" and rows["qwen3.5:4b"]["where"] == "gpu" and rows["qwen3.5:4b"]["tps"] > rows["qwen3.5:9b"]["tps"]
assert "nomic-embed-text:latest" not in rows, "embedding models do no jobs"
assert any("Only one of these models fits" in a for a in r["advice"]) and "Too big for this PC: " in r["text"]
# another program fills the card: the 9B no longer fits whole
busy = {**LAPTOP, "gpu": {**LAPTOP["gpu"], "used_gb": 8.3}, "ollama_vram_gb": 6.1}
rb = A.report(busy, INSTALLED, {}, {"code": "qwen3.5:9b"}, {})
cb = {x["role"]: x for x in rb["roles"]}["code"]
assert {m["name"]: m for m in rb["models"]}["qwen3.5:9b"]["where"] == "split" and "does not fit on the graphics card" in cb["note"], cb
assert any("Other programs use 2.2 GB" in a for a in rb["advice"]), rb["advice"]
# a measurement replaces the estimate and calibrates the card
rm = A.report(LAPTOP, INSTALLED, {"jarvis:latest": {"tps": 41.0, "gpu": 1.0}}, {}, {})
assert {m["name"]: m for m in rm["models"]}["jarvis:latest"]["measured"] and rm["pc"]["bandwidth_source"] == "measured"
# no graphics card: small models on the processor
cpu = A.report({**LAPTOP, "gpu": None, "ram_free_gb": 10}, [], {}, {}, {})
assert all(m["where"] in ("cpu", "no") for m in cpu["models"]) and not cpu["features"][0]["ok"]
assert A.ASK.search("what models can my pc run?") and A.ASK.search("Jarvis, what's the best model for my laptop") and not A.ASK.search("what model are you")

# ---------- in the server, with a fake Ollama ----------
GEN = []
class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def reply(self, obj):
        raw = json.dumps(obj).encode(); self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        if self.path == "/api/tags":
            return self.reply({"models": [{"name": m["name"], "size": int(m["size_gb"] * 1e9), "digest": m["name"]} for m in INSTALLED]})
        if self.path == "/api/ps":
            return self.reply({"models": [{"name": "jarvis:latest", "size": 5.2e9, "size_vram": 5.2e9}]})
        if self.path == "/api/version":
            return self.reply({"version": "0.40.18"})
        return self.reply({"data": [{"id": m["name"]} for m in INSTALLED]})
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/api/show":
            return self.reply({"capabilities": next(m["caps"] for m in INSTALLED if m["name"] == body["model"])})
        if self.path == "/api/generate":
            GEN.append(body)
            return self.reply({"response": "The sun rises.", "eval_count": 96, "eval_duration": int(2.4e9), "load_duration": int(3e9), "prompt_eval_duration": int(1e8)})
        if self.path == "/api/pull":
            self.send_response(200); self.end_headers(); self.wfile.write(b'{"status":"success"}\n'); return
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        self.wfile.write(("data: " + json.dumps({"choices": [{"delta": {"content": "Hello, sir."}}]}) + "\n\n").encode()); self.wfile.write(b"data: [DONE]\n\n")
fake = ThreadingHTTPServer(("127.0.0.1", 0), Fake); threading.Thread(target=fake.serve_forever, daemon=True).start()
os.environ["OPENAI_BASE_URL"] = f"http://127.0.0.1:{fake.server_address[1]}/v1"; os.environ["OPENAI_API_KEY"] = "ollama"
spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT = tmp
S.ensure_ollama = lambda base, wait=25.0: True
S._gpu_snapshot = lambda: {"name": "NVIDIA GeForce RTX 4060 Laptop GPU", "mem_total_mb": 8188, "mem_used_mb": 5800, "util": 3, "temp_c": 50}
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start(); port = app.server_address[1]
def call(m, path, body=None, h=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=60); c.request(m, path, json.dumps(body) if body is not None else None, {"Content-Type": "application/json", **(h or {})})
    r = c.getresponse(); return r.status, json.loads(r.read())
(tmp / "data" / "settings.json").write_text(json.dumps({"provider": "local", "models": {"local": "jarvis:latest"}}))
S.SETTINGS_LOADED_FROM = None
st, d = call("GET", "/api/advisor"); assert st == 200, d
roles = {x["role"]: x for x in d["roles"]}
assert d["pc"]["gpu"].startswith("NVIDIA GeForce RTX 4060 Laptop GPU") and roles["chat"]["current"] == "jarvis:latest" and roles["chat"]["same"], roles["chat"]
assert roles["vision"]["current"] == "qwen3.5:9b", "pictures go to qwen3.5 now that it is known to see"
st, d = call("POST", "/api/advisor", {"apply": {"role": "autopilot", "model": "qwen3.5:9b"}}); assert st == 200 and d["message"] == "Autopilot now uses qwen3.5:9b." and S.control_config()["model"] == "qwen3.5:9b"
st, d = call("POST", "/api/advisor", {"apply": {"role": "vision", "model": "moondream:latest"}}); assert st == 200 and S.vision_model_for(S.ai_settings("chat", "local")) == "moondream:latest"
st, d = call("POST", "/api/advisor", {"apply": {"role": "code", "model": "qwen3.5:9b"}}); assert S.coder_settings()["model"] == "qwen3.5:9b"
assert call("POST", "/api/advisor", {"apply": {"role": "code", "model": "qwen3.5:27b"}})[0] == 400, "not installed: download first"
assert call("POST", "/api/advisor", {"pull": "evil/model:latest"})[0] == 400, "only recommended models are downloaded from here"
st, d = call("POST", "/api/advisor", {"measure": ["jarvis:latest", "qwen3.5:9b"]}); assert st == 200
for _ in range(50):
    if not S.ADVISOR["measure"]["running"]: break
    time.sleep(0.1)
m = S.advisor_measured(); assert m["jarvis:latest"]["tps"] == 40.0 and m["jarvis:latest"]["gpu"] == 1.0 and m["jarvis:latest"]["load_s"] == 3.0, m
assert GEN[1]["think"] is False and "think" not in GEN[0] and GEN[-1] == {"model": "jarvis:latest", "keep_alive": "30m"}, "the chat model is loaded back after the test"
# chat, phone, self-check
st, d = call("POST", "/api/chat", {"messages": [{"role": "user", "content": "what models can my pc run?"}], "stream": False})
assert d["reply"].startswith("This PC: NVIDIA GeForce RTX 4060 Laptop GPU (9 GB)") and "Autopilot" in d["reply"], d["reply"]
S.phone_link.save(S.data_path("phone.json"), {"enabled": True, "code": "ABCDEFGH23"}); S.phone_link.is_loopback = lambda a: False
assert call("POST", "/api/advisor", {"measure": True}, {"X-Jarvis-Token": "ABCDEFGH23"})[0] == 403
S.phone_link.is_loopback = lambda a: True
check = dict(S.self_checks())["Best models for this PC"]()
assert check[0] in ("ok", "warn") and (check[0] == "ok" or check[2]["do"] == "pane:ai"), check

# ---------- the page ----------
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_context(viewport={"width": 1280, "height": 900}).new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(500)
    pg.evaluate("window.JarvisUI.openPane('ai')"); pg.wait_for_selector("#adv-roles .adv-role")
    assert "NVIDIA GeForce RTX 4060 Laptop GPU" in pg.text_content("#adv-pc") and pg.locator("#adv-roles .adv-role").count() == 4
    assert "measured" in pg.text_content("#adv-roles"), pg.text_content("#adv-roles")
    card = pg.locator("#adv-roles .adv-role", has_text="Autopilot")
    assert "Download (6.2 GB)" in card.text_content(), card.text_content()
    pg.click("#adv-roles .adv-role:has-text('Pictures') button"); pg.wait_for_function("document.querySelector('#adv-status').textContent.includes('Pictures now uses')")
    assert pg.locator("#adv-models tbody tr").count() >= 8 and "too big" not in pg.text_content("#adv-models")
    pg.set_viewport_size({"width": 390, "height": 800}); pg.wait_for_timeout(200)
    assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "fits a phone screen"
    assert not errs, errs
    b.close()
print("advisor ok"); os._exit(0)

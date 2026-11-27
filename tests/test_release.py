"""Releases: an installed Jarvis updates to the newest published release (not to every change), remembers its version,
installs new packages after an update and restarts. Also checks the installer's own files."""
import json, os, re, sys, tempfile, threading, time, http.client, importlib.util, shutil, subprocess
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote
tmp = Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0, "."); import filecheck as fc

def put(base, rel, data):
    p = base / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data if isinstance(data, bytes) else data.encode())

# two snapshots of the repository: the release v2026.11.20, and main a little later
snap = {}
for ref, files in (("v2026.11.20", {"app/server.py": "release server\n", "requirements.txt": "psutil\n"}),
                   ("main", {"app/server.py": "main server\n", "requirements.txt": "psutil\npypdf\n"})):
    d = tmp / ("repo-" + ref); (d / "tools").mkdir(parents=True)
    shutil.copy("filecheck.py", d / "filecheck.py"); shutil.copy("tools/make_manifest.py", d / "tools" / "make_manifest.py")
    for rel, txt in files.items(): put(d, rel, txt)
    assert subprocess.run([sys.executable, "tools/make_manifest.py"], cwd=d, capture_output=True).returncode == 0
    snap[ref] = d
RELEASES = {"latest": "v2026.11.20"}
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, data, code=200):
        self.send_response(code); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        if self.path.startswith("/api/repos/"):
            if self.path.endswith("/releases/latest"):
                return self.send(json.dumps({"tag_name": RELEASES["latest"]}).encode()) if RELEASES["latest"] else self.send(b'{"message":"Not Found"}', 404)
            return self.send(b"", 404)
        parts = self.path.lstrip("/").split("/", 3)
        d = snap.get(unquote(parts[2]))
        f = d / unquote(parts[3]) if d else None
        if not f or not f.is_file(): return self.send(b"", 404)
        self.send(f.read_bytes())
srv = ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
fc.RAW_BASE = f"http://127.0.0.1:{srv.server_address[1]}"; fc.API_BASE = fc.RAW_BASE + "/api"

# ---------- the file checker ----------
inst = tmp / "inst"; put(inst, "filecheck.py", (snap["main"] / "filecheck.py").read_bytes()); put(inst, "tools/make_manifest.py", (snap["main"] / "tools/make_manifest.py").read_bytes())
assert fc.channel_for(inst) == "main" and fc.ref_for(inst) == "main" and fc.installed_version(inst) == "", "a copy from before follows main, as it did"
put(inst, "data/filecheck.json", json.dumps({"channel": "releases"}))
assert fc.channel_for(inst) == "releases" and fc.ref_for(inst) == "v2026.11.20"
m, src = fc.load_manifest(inst, "v2026.11.20"); assert src == "the GitHub release v2026.11.20", src
plan = fc.classify(inst, m); assert sorted(plan["missing"]) == ["app/server.py", "requirements.txt"], plan
out = fc.apply_update(inst, m, plan["missing"], "v2026.11.20")
assert not out["failed"] and out["packages"] and out["restart"] and (inst / "app/server.py").read_text() == "release server\n"
assert fc.installed_version(inst) == "2026.11.20" and json.loads((inst / "data/version.json").read_text())["tag"] == "v2026.11.20"
# main moved on, but no new release: nothing to update
m, _ = fc.load_manifest(inst, fc.ref_for(inst)); plan = fc.classify(inst, m); assert not plan["missing"] and not plan["updates"], plan
assert "up to date" in fc.describe_update(plan, "the GitHub release v2026.11.20")
# no release published at all: back to main
fc.LATEST.clear(); RELEASES["latest"] = None; assert fc.ref_for(inst) == "main"
fc.LATEST.clear(); RELEASES["latest"] = "v2026.11.20"
# a partial update does not claim the version; a branch never is a version
fc.record_version(inst, "main"); fc.record_version(inst, "a" * 40); assert fc.installed_version(inst) == "2026.11.20"
put(inst, "data/version.json", "{}"); out = fc.apply_update(inst, m, [], "v2026.11.20"); assert fc.installed_version(inst) == "2026.11.20", "nothing left to do: on that release"

# ---------- in the server ----------
os.environ["JARVIS_NO_SETUP"] = "1"
spec = importlib.util.spec_from_file_location("srv", "app/server.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)
S.filecheck.RAW_BASE, S.filecheck.API_BASE = fc.RAW_BASE, fc.API_BASE
root = tmp / "srv"; root.mkdir(); put(root, "app/server.py", "release server\n"); put(root, "requirements.txt", "psutil\n")
S.ROOT = root
pip_calls, restarts = [], []
S.packages_install_in_background = lambda: pip_calls.append(1)
S.restart_jarvis = lambda: restarts.append(1)
app = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); threading.Thread(target=app.serve_forever, daemon=True).start(); PORT = app.server_address[1]
def call(path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=30)
    c.request("POST" if body is not None else "GET", path, json.dumps(body) if body is not None else None, {"Content-Type": "application/json"})
    r = c.getresponse(); return r.status, json.loads(r.read() or b"{}")
st, d = call("/api/install"); assert d["channel"] == "main" and d["version"] == "", d
st, d = call("/api/files/channel", {"channel": "nightly"}); assert st == 400
st, d = call("/api/files/channel", {"channel": "releases"}); assert st == 200 and d["ref"] == "v2026.11.20", d
st, d = call("/api/files/update"); assert d["channel"] == "releases" and d["ref"] == "v2026.11.20" and "release v2026.11.20" in d["text"], d
st, d = call("/api/files/channel", {"channel": "main"}); st, d = call("/api/files/update")
assert d["updates"] == [] and "app/server.py" in d["unknown"] + d["updates"] + d["conflicts"] or d["ref"] == "main", d
st, d = call("/api/files/repair", {"mode": "update", "changed": True}); assert st == 200 and d["packages"] and d["restart"] and pip_calls == [1], d
assert (root / "requirements.txt").read_text() == "psutil\npypdf\n" and d["version"] == "", "main has no version"
st, d = call("/api/restart", {}); assert st == 200 and restarts == [1]

# ---------- the installer's files ----------
ps = Path("tools/setup-jarvis.ps1").read_text(encoding="utf-8")
assert ps.isascii(), "Windows PowerShell 5 reads scripts without a byte order mark as ANSI"
for need in ("-Releases", "version.json", "filecheck.json", "requirements.txt", "Python.Python.3.12", "Get-AuthenticodeSignature", "exit 3"):
    assert need in ps, need
iss = Path("installer/jarvis.iss").read_bytes()
assert iss.startswith(b"\xef\xbb\xbf"), "Inno Setup reads non-English text right only with a byte order mark"
iss = iss.decode("utf-8-sig")
langs = re.findall(r'^Name: "(\w+)"; MessagesFile', iss, re.M)
assert len(langs) == 10 and "en" in langs
for key in ("Needs", "Autostart", "Voice", "Repair", "SafeMode", "Working", "Failed", "KeepData"):
    have = re.findall(rf"^(\w+)\.{key}=", iss, re.M)
    assert sorted(have) == sorted(langs), (key, have)
for src in re.findall(r'Source: "\.\.\\([^"*]+)"', iss):
    assert Path(src).exists(), src
assert "PrivilegesRequired=lowest" in iss and "{localappdata}\\Programs\\Jarvis" in iss and "uninsneveruninstall" in iss
# what the installer copies is what the updater knows: no file it needs is left out of the list
listed = {f["path"] for f in json.loads(Path("manifest.json").read_text())["files"]}
assert "tools/setup-jarvis.ps1" in listed and "filecheck.py" in listed and "requirements.txt" in listed
wf = Path(".github/workflows/release.yml").read_text()
assert "installer\\jarvis.iss" in wf and "gh release create" in wf and "make_manifest.py --check" in wf
print("release ok")
os._exit(0)

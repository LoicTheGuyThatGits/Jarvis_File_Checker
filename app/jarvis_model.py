"""The "jarvis" model in Ollama: a base model (qwen2.5:7b by default) with Jarvis's settings and persona built in.

Your own copy of the recipe is model\\Modelfile (change its FROM line to move to another base model, or to a fine-tuned
GGUF file later). Updates never overwrite it; the template it starts from is tools\\jarvis.Modelfile.

    read(path)                  {"exists", "base", "params", "base_is_file"}
    ensure(root)                makes model\\Modelfile from the template when it is missing; returns its path
    Builder(root, exe).start()  runs "ollama create jarvis -f model\\Modelfile" in the background (it downloads the base model
                                first when needed); .state() says how far it got
"""
from __future__ import annotations

import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

NAME = "jarvis"
TEMPLATE = Path("tools") / "jarvis.Modelfile"
LOCAL = Path("model") / "Modelfile"


def read(path: Path) -> dict:
    p = Path(path)
    if not p.is_file():
        return {"exists": False, "base": "", "params": {}, "base_is_file": False}
    text = p.read_text(encoding="utf-8", errors="replace")
    base = ""
    params = {}
    for line in text.splitlines():
        s = line.strip()
        m = re.match(r"FROM\s+(\S+)", s, re.I)
        if m and not base:
            base = m.group(1)
        m = re.match(r"PARAMETER\s+(\w+)\s+(.+)", s, re.I)
        if m:
            params[m.group(1)] = m.group(2).strip()
    return {"exists": True, "base": base, "params": params, "base_is_file": base.startswith((".", "/", "\\")) or base.lower().endswith(".gguf")}


def ensure(root: Path) -> Path:
    local = Path(root) / LOCAL
    if not local.is_file():
        template = Path(root) / TEMPLATE
        if not template.is_file():
            raise FileNotFoundError("tools\\jarvis.Modelfile is missing. Run repair-jarvis.bat.")
        local.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(template, local)
    return local


PROGRESS = re.compile(r"(pulling[^\r\n]*?|verifying[^\r\n]*|writing[^\r\n]*|using existing layer[^\r\n]*|creating[^\r\n]*|success|gathering[^\r\n]*|parsing[^\r\n]*)", re.I)


class Builder:
    def __init__(self, root: Path, exe: str | None, popen=subprocess.Popen, on_done=None):
        self.root, self.exe, self.popen, self.on_done = Path(root), exe, popen, on_done
        self.lock = threading.Lock()
        self._state = {"running": False, "step": "", "ok": None, "message": "", "started": 0.0, "finished": 0.0}

    def state(self) -> dict:
        with self.lock:
            return dict(self._state)

    def _set(self, **kw) -> None:
        with self.lock:
            self._state.update(kw)

    def start(self) -> str:
        with self.lock:
            if self._state["running"]:
                return "The Jarvis model is already being built."
        if not self.exe:
            return "Ollama is not installed. Get it from https://ollama.com/download, then try again."
        try:
            path = ensure(self.root)
        except FileNotFoundError as exc:
            return str(exc)
        info = read(path)
        if not info["base"]:
            return "model\\Modelfile has no FROM line, so I do not know which base model to use."
        self._set(running=True, step="starting", ok=None, message="", started=time.time(), finished=0.0)
        threading.Thread(target=self._run, args=(path, info), daemon=True).start()
        size = " (qwen2.5:7b is about 4.7 GB the first time)" if info["base"].startswith("qwen2.5:7b") else ""
        return f"Building the Jarvis model on {info['base']}. Ollama downloads the base model first if it is not there yet{size}; this can take a while."

    def _run(self, path: Path, info: dict) -> None:
        try:
            proc = self.popen([self.exe, "create", NAME, "-f", str(path)], cwd=str(path.parent), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            tail = b""
            while True:
                chunk = proc.stdout.read(256)
                if not chunk:
                    break
                tail = (tail + chunk)[-2000:]
                text = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", tail.decode("utf-8", errors="replace"))
                found = PROGRESS.findall(text)
                if found:
                    self._set(step=re.sub(r"\s+", " ", found[-1]).strip()[:120])
            code = proc.wait()
            text = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", tail.decode("utf-8", errors="replace"))
            if code == 0:
                self._set(running=False, ok=True, step="done", message=f"The Jarvis model is ready (built on {info['base']}). It is used whenever the local model is chosen.", finished=time.time())
            else:
                last = [l.strip() for l in re.split(r"[\r\n]+", text) if l.strip()][-1:] or ["no details"]
                self._set(running=False, ok=False, step="failed", message=f"Building the Jarvis model failed: {last[0][:200]}", finished=time.time())
        except Exception as exc:
            self._set(running=False, ok=False, step="failed", message=f"Building the Jarvis model failed: {exc}", finished=time.time())
        if self.on_done:
            try:
                self.on_done(self.state())
            except Exception:
                pass

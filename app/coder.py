"""Jarvis Code: the AI model works on a project folder like a careful developer, and looks at what it built in a browser.

The loop, one model answer at a time:
    the model reads files (with line numbers), changes them with small find/replace edits (or writes new files),
    Jarvis opens the page in a hidden browser after every change and gives back the errors (console, uncaught
    exceptions, missing files), the visible text and a screenshot, and the model fixes what is wrong; then DONE.
    Python and JavaScript files can be run too, but only after you allow it (each time, or always for that project).

What the model answers with (one or more, in one answer):
    READ path [from-to]     LIST [folder]     FIND text
    WRITE path + ```whole new file```        EDIT path + ```<<<<<<< FIND / ======= / >>>>>>> REPLACE```
    CHECK [page.html] [then click #start; press ArrowUp; type #name Bob; wait 500]
    RUN file.py [args] | RUN tests          DONE what was done, for the user

Safety: files only inside the project folder (no "..", no links out), no .exe/.bat/.ps1 and the like, every change can
be undone, and pages are served from their own address (127.0.0.2), so a page the model wrote cannot use Jarvis's
own controls (requests from another address are refused by Jarvis).
"""
from __future__ import annotations

import base64
import difflib
import mimetypes
import os
import queue
import re
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".idea", ".vscode", "Library", "Temp", "obj", "bin", ".mypy_cache", ".pytest_cache"}
BLOCKED_WRITE = {".exe", ".dll", ".msi", ".bat", ".cmd", ".ps1", ".psm1", ".vbs", ".vbe", ".wsf", ".scr", ".lnk", ".reg", ".com", ".pif", ".hta", ".jar", ".sys"}
WEB_PAGES = (".html", ".htm")
READ_LINES = 400
FILE_LIMIT = 300_000
SNAPSHOT_CHARS = 14_000
OBSERVATION_CHARS = 12_000
BUDGET_CHARS = 38_000
RUN_TIMEOUT = 30
COMMANDS = ("READ", "LIST", "FIND", "WRITE", "EDIT", "CHECK", "RUN", "DONE")
CMD_LINE = re.compile(r"^[ \t>*#`-]*(READ|LIST|FIND|SEARCH|WRITE|CREATE|EDIT|CHECK|RUN|DONE)\b[*`:]*[ \t]*(.*)$")
FIND_MARK = re.compile(r"^\s*<{5,}\s*(?:FIND|SEARCH|ORIGINAL)?\s*$", re.I)
MID_MARK = re.compile(r"^\s*={5,}\s*$")
END_MARK = re.compile(r"^\s*>{5,}\s*(?:REPLACE|UPDATED)?\s*$", re.I)
NUMBERED = re.compile(r"^\s*\d+\s?\|\s?")

SYSTEM = """You are the coder inside Jarvis, working on the project folder below for the user. Work like a careful senior developer:
- Look before you change: read the files you will change. You get files with line numbers ("12| text"); the numbers are not part of the file.
- Change only what is needed, with EDIT blocks. Copy the FIND lines exactly from the file (without the line numbers), with enough lines to be unique. Use WRITE only for a new file or a very small one.
- After you change a web page, Jarvis opens it in a browser by itself and sends you the errors, the visible text and a screenshot. Read them. Fix every error, then check again. Use CHECK with steps to try buttons and keys (games, forms).
- Keep it simple: plain HTML, CSS and JavaScript (no build tools, no frameworks to install) unless the project already uses something else. Link files with relative paths (css/style.css).
- Never write passwords, keys or personal data into files. Programs cannot read keyboard input when Jarvis runs them; test with arguments or tests instead.
- When the task is finished and the last check is clean, answer DONE with two or three sentences for the user: what you did and how to use it.

Answer with one short line of what you are doing, then one or more commands, exactly in this form:
READ path            (or READ path 40-120 for part of a long file)
LIST folder          (LIST alone: the whole project)
FIND some text       (searches every file)
WRITE path
```
the whole new file
```
EDIT path
```
<<<<<<< FIND
exact lines from the file
=======
the new lines
>>>>>>> REPLACE
```
(several FIND/REPLACE pairs may follow in the same block, top to bottom)
CHECK page.html then click #start; press ArrowRight; type #name Bob; wait 500
RUN main.py arg      (Python or JavaScript file; RUN tests runs the tests; the user is asked first)
DONE what you did, for the user
Do not explain code at length and do not show code outside WRITE and EDIT blocks."""


class CoderError(Exception):
    pass


# ---------------- the project folder ----------------
def safe_path(root: Path, rel: str, write: bool = False) -> Path:
    rel = str(rel or "").strip().strip("`'\"").replace("\\", "/")
    rel = re.sub(r"^(?:\./)+|^/+", "", rel)
    rel = "" if rel in (".", "") else rel
    root = Path(root).resolve()
    p = (root / rel).resolve() if rel else root
    if p != root and root not in p.parents:
        raise CoderError(f"{rel} is outside the project folder.")
    if write:
        if p.suffix.lower() in BLOCKED_WRITE:
            raise CoderError(f"Jarvis Code does not write {p.suffix} files (programs Windows would run directly).")
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts[:-1]):
            raise CoderError(f"{rel} is inside a folder Jarvis Code leaves alone.")
    return p


def rel_of(root: Path, p: Path) -> str:
    return p.resolve().relative_to(Path(root).resolve()).as_posix()


def is_text(p: Path) -> bool:
    try:
        with open(p, "rb") as f:
            return b"\x00" not in f.read(4000)
    except OSError:
        return False


def read_text(p: Path) -> str:
    data = p.read_bytes()
    if len(data) > FILE_LIMIT:
        raise CoderError(f"{p.name} is larger than 300 KB; Jarvis Code reads smaller files only.")
    if b"\x00" in data[:4000]:
        raise CoderError(f"{p.name} is not a text file.")
    return data.decode("utf-8-sig", errors="replace").replace("\r\n", "\n")


def write_text(p: Path, text: str) -> None:
    crlf = False
    if p.exists():
        try:
            crlf = b"\r\n" in p.read_bytes()[:20000]
        except OSError:
            pass
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text.replace("\n", "\r\n") if crlf else text, encoding="utf-8", newline="")


def walk(root: Path, limit: int = 300) -> list[Path]:
    root = Path(root).resolve()
    out: list[Path] = []
    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        depth = len(Path(folder).relative_to(root).parts)
        if depth >= 5:
            dirs[:] = []
        for name in sorted(files):
            out.append(Path(folder) / name)
            if len(out) >= limit:
                return out
    return out


def size_text(n: int) -> str:
    return f"{n} B" if n < 1024 else f"{n / 1024:.1f} KB" if n < 1024 * 1024 else f"{n / 1048576:.1f} MB"


def tree(root: Path) -> str:
    files = walk(root)
    if not files:
        return "(the folder is empty: a new project)"
    lines = [f"{rel_of(root, p)} ({size_text(p.stat().st_size)})" for p in files]
    return "\n".join(lines) + ("\n… (more files not listed)" if len(files) >= 300 else "")


def numbered(text: str, start: int = 1, end: int | None = None) -> str:
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    end = min(end or len(lines), len(lines))
    width = len(str(end))
    return "\n".join(f"{n:>{width}}| {lines[n - 1]}" for n in range(max(1, start), end + 1))


def main_page(root: Path) -> str | None:
    if (Path(root) / "index.html").is_file():
        return "index.html"
    pages = [p for p in walk(root) if p.suffix.lower() in WEB_PAGES]
    return rel_of(root, pages[0]) if pages else None


def snapshot(root: Path) -> str:
    """Small projects are given whole at the start (saves the model a turn per file)."""
    texts, total = [], 0
    for p in walk(root, 60):
        if not is_text(p) or p.stat().st_size > 40_000:
            continue
        try:
            t = read_text(p)
        except CoderError:
            continue
        total += len(t)
        if total > SNAPSHOT_CHARS:
            return ""
        texts.append(f"[{rel_of(root, p)}]\n{numbered(t)}")
    return "\n\n".join(texts)


def find_in(root: Path, needle: str, limit: int = 40) -> str:
    needle = needle.strip().strip("\"'`")
    if not needle:
        raise CoderError("FIND needs some text to look for.")
    hits = []
    low = needle.lower()
    for p in walk(root):
        if not is_text(p):
            continue
        try:
            lines = read_text(p).split("\n")
        except CoderError:
            continue
        for n, line in enumerate(lines, 1):
            if low in line.lower():
                hits.append(f"{rel_of(root, p)}:{n}| {line.strip()[:160]}")
                if len(hits) >= limit:
                    return "\n".join(hits) + "\n… (more not shown)"
    return "\n".join(hits) or f"“{needle}” is in no file."


# ---------------- find/replace edits ----------------
def _indent(s: str) -> str:
    return s[: len(s) - len(s.lstrip())]


def _clean_block(lines: list[str]) -> list[str]:
    """Drop line numbers the model copied from READ ("12| text"), when every line has them."""
    body = [l for l in lines if l.strip()]
    if body and all(NUMBERED.match(l) for l in body):
        return [NUMBERED.sub("", l, count=1) for l in lines]
    return lines


def apply_edit(text: str, find: str, replace: str) -> tuple[str, int]:
    """Returns the new text and the first changed line. Exact match first; then line by line ignoring indentation and
    trailing spaces (and the replacement is re-indented to fit). Raises CoderError with a hint when it is not found."""
    find_lines = _clean_block(find.split("\n"))
    repl_lines = _clean_block(replace.split("\n"))
    find, replace = "\n".join(find_lines), "\n".join(repl_lines)
    if not find.strip():
        if not text.strip():
            return replace + ("\n" if replace and not replace.endswith("\n") else ""), 1
        raise CoderError("FIND is empty. To add lines, FIND the lines next to where they go and repeat them in REPLACE with the new lines.")
    count = text.count(find)
    if count == 1:
        return text.replace(find, replace, 1), text[: text.index(find)].count("\n") + 1
    if count > 1:
        raise CoderError(f"The FIND text is in the file {count} times. Include a few more lines around it so it is unique.")
    # line by line, ignoring indentation
    while find_lines and not find_lines[0].strip():
        find_lines.pop(0)
    while find_lines and not find_lines[-1].strip():
        find_lines.pop()
    lines = text.split("\n")
    want = [l.strip() for l in find_lines]
    n = len(want)
    spots = [i for i in range(len(lines) - n + 1) if [l.strip() for l in lines[i:i + n]] == want]
    if len(spots) > 1:
        raise CoderError(f"Those lines are in the file {len(spots)} times. Include a few more lines around them so they are unique.")
    if len(spots) == 1:
        i = spots[0]
        given = _indent(next(l for l in find_lines if l.strip()))
        actual = _indent(next(l for l in lines[i:i + n] if l.strip()))
        new = repl_lines
        while new and not new[0].strip() and find_lines and find_lines[0].strip():
            new = new[1:]
        if actual != given:
            if actual.startswith(given):
                pad = actual[len(given):]
                new = [pad + l if l.strip() else l for l in new]
            elif given.startswith(actual):
                cut = len(given) - len(actual)
                new = [l[cut:] if l[:cut].strip() == "" else l.lstrip() for l in new]
        return "\n".join(lines[:i] + new + lines[i + n:]), i + 1
    # not there: show the closest lines, so the next try can copy them
    first = want[0] if want else ""
    best, score = None, 0.0
    for i, l in enumerate(lines):
        r = difflib.SequenceMatcher(None, l.strip(), first).ratio()
        if r > score:
            best, score = i, r
    hint = ""
    if best is not None and score > 0.5:
        hint = "\nThe closest lines in the file are:\n" + numbered("\n".join(lines), best + 1, min(len(lines), best + max(n, 3) + 2))
    raise CoderError("The FIND lines are not in the file (they must match the file exactly; READ it again to copy them)." + hint)


def edit_pairs(block: str) -> list[tuple[str, str]]:
    pairs, state, find, repl = [], None, [], []
    for line in block.split("\n"):
        if FIND_MARK.match(line):
            state, find, repl = "find", [], []
        elif MID_MARK.match(line) and state == "find":
            state = "repl"
        elif END_MARK.match(line) and state == "repl":
            pairs.append(("\n".join(find), "\n".join(repl)))
            state = None
        elif state == "find":
            find.append(line)
        elif state == "repl":
            repl.append(line)
    if state == "repl":                       # the closing marker was forgotten at the very end
        pairs.append(("\n".join(find), "\n".join(repl)))
    return pairs


def diff_text(before: str | None, after: str, name: str) -> tuple[str, int, int]:
    a = (before or "").split("\n")
    b = after.split("\n")
    lines = list(difflib.unified_diff(a, b, "a/" + name, "b/" + name, lineterm="", n=2))[2:]
    plus = sum(1 for l in lines if l.startswith("+"))
    minus = sum(1 for l in lines if l.startswith("-"))
    if len(lines) > 220:
        lines = lines[:220] + [f"… ({len(lines) - 220} more lines)"]
    return "\n".join(lines), plus, minus


# ---------------- reading the model's answer ----------------
def _path_arg(s: str) -> str:
    s = s.strip().strip("`'\"*:").strip()
    return s.split()[0].strip("`'\"*:") if s else ""


def _looks_like_path(s: str) -> bool:
    s = s.strip().strip("`*'\":")
    return bool(re.fullmatch(r"[\w./\\ -]{1,120}\.[A-Za-z0-9]{1,8}", s)) and " " not in s.strip()


def _fence(lines: list[str], i: int) -> tuple[str, str, int] | None:
    """The fenced block starting at or after line i (blank lines skipped): (info, body, index after it)."""
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines) or not lines[i].lstrip().startswith("```"):
        return None
    info = lines[i].strip()[3:].strip()
    closes = [j for j in range(i + 1, len(lines)) if lines[j].strip() == "```"]
    if not closes:
        return info, "\n".join(lines[i + 1:]), len(lines)
    for j in closes:                          # the closing fence is the one followed by the end or by the next command
        k = j + 1
        while k < len(lines) and not lines[k].strip():
            k += 1
        if k >= len(lines) or CMD_LINE.match(lines[k]) or lines[k].lstrip().startswith("```") or _looks_like_path(lines[k]):
            return info, "\n".join(lines[i + 1:j]), j + 1
    j = closes[-1]
    return info, "\n".join(lines[i + 1:j]), j + 1


def parse(reply: str) -> tuple[str, list[dict]]:
    lines = (reply or "").replace("\r\n", "\n").split("\n")
    # some models wrap their whole answer in one fence
    thought, cmds, i = [], [], 0
    while i < len(lines):
        line = lines[i]
        m = CMD_LINE.match(line)
        if m:
            word, arg = m.group(1).upper(), m.group(2).strip()
            word = {"SEARCH": "FIND", "CREATE": "WRITE"}.get(word, word)
            if word in ("WRITE", "EDIT"):
                fence = _fence(lines, i + 1)
                path = _path_arg(arg)
                if fence is None:
                    cmds.append({"cmd": word, "path": path, "error": f"{word} {path} needs the file text in a ``` block right under it."})
                    i += 1
                    continue
                info, body, i = fence
                if not path:
                    path = next((t for t in reversed(info.split()) if "." in t), "")
                cmds.append({"cmd": word, "path": path, "body": body})
                continue
            if word == "DONE":
                rest = [arg] + [l for l in lines[i + 1:] if not CMD_LINE.match(l)]
                cmds.append({"cmd": "DONE", "text": "\n".join(rest).strip()})
                i = next((j for j in range(i + 1, len(lines)) if CMD_LINE.match(lines[j])), len(lines))
                continue
            if word == "READ":
                m2 = re.match(r"(.+?)(?:[ :]+(\d+)\s*[-–]\s*(\d+))?\s*$", arg)
                cmds.append({"cmd": "READ", "path": _path_arg(m2.group(1) if m2 else arg), "from": int(m2.group(2)) if m2 and m2.group(2) else None,
                             "to": int(m2.group(3)) if m2 and m2.group(3) else None})
            elif word == "LIST":
                cmds.append({"cmd": "LIST", "path": _path_arg(arg)})
            elif word == "FIND":
                cmds.append({"cmd": "FIND", "text": arg})
            elif word == "CHECK":
                page, steps = "", arg
                first = arg.split()[0] if arg.split() else ""
                if first.lower().strip("`'\"").endswith(WEB_PAGES):
                    page, steps = first.strip("`'\""), arg[len(first):]
                steps = re.sub(r"^\s*(?:then|:|,|-)\s*", "", steps, flags=re.I)
                cmds.append({"cmd": "CHECK", "page": page, "steps": [s.strip() for s in re.split(r"[;\n]|,\s*(?=(?:click|press|type|wait|scroll)\b)", steps) if s.strip()]})
            elif word == "RUN":
                cmds.append({"cmd": "RUN", "args": arg.strip("`")})
            i += 1
            continue
        # an EDIT written the aider way: a path line, then a fence with SEARCH/REPLACE markers
        if line.lstrip().startswith("```"):
            fence = _fence(lines, i)
            info, body, after = fence
            if any(FIND_MARK.match(l) for l in body.split("\n")):
                prev = next((lines[j] for j in range(i - 1, -1, -1) if lines[j].strip()), "")
                path = _path_arg(prev) if _looks_like_path(prev) else next((t for t in reversed(info.split()) if "." in t), "")
                if thought and _looks_like_path(thought[-1]):
                    thought.pop()
                cmds.append({"cmd": "EDIT", "path": path, "body": body})
            i = after
            continue
        if line.strip():
            thought.append(line.strip())
        i += 1
    return " ".join(thought)[:400], cmds


# ---------------- pages on their own address ----------------
class PreviewServer:
    """Serves project folders read-only at http://127.0.0.2:<port>/p/<token>/… . Another address than Jarvis's, so a page
    cannot send commands to Jarvis (Jarvis refuses requests from other addresses). If 127.0.0.2 is not available, it uses
    127.0.0.1 with a sandbox header, which seals the page the same way."""

    def __init__(self):
        self.roots: dict[str, Path] = {}
        self.httpd = None
        self.base = ""
        self.sealed = False
        self.lock = threading.Lock()

    def start(self) -> str:
        with self.lock:
            if self.httpd:
                return self.base
            owner = self

            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *a):
                    pass

                def do_HEAD(self):
                    self.do_GET(head=True)

                def do_GET(self, head=False):
                    parts = unquote(urlparse(self.path).path).split("/", 3)
                    root = owner.roots.get(parts[2]) if len(parts) > 2 and parts[1] == "p" else None
                    if root is None:
                        return self.reply(404, b"Not found", "text/plain")
                    rel = parts[3] if len(parts) > 3 else ""
                    try:
                        p = safe_path(root, rel)
                    except CoderError:
                        return self.reply(403, b"Outside the project", "text/plain")
                    if p.is_dir():
                        p = p / "index.html"
                    if not p.is_file():
                        if p.name == "favicon.ico":
                            return self.reply(204, b"", "image/x-icon")
                        return self.reply(404, b"Not found", "text/plain")
                    kind = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
                    if kind.startswith("text/") or kind in ("application/javascript", "application/json"):
                        kind += "; charset=utf-8"
                    if p.suffix.lower() in (".js", ".mjs"):
                        kind = "text/javascript; charset=utf-8"
                    self.reply(200, p.read_bytes(), kind, head)

                def reply(self, code, body, kind, head=False):
                    self.send_response(code)
                    self.send_header("Content-Type", kind)
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    if owner.sealed:
                        self.send_header("Content-Security-Policy", "sandbox allow-scripts allow-forms allow-modals allow-pointer-lock allow-popups")
                    self.end_headers()
                    if not head and code != 204:
                        self.wfile.write(body)

            for host, sealed in (("127.0.0.2", False), ("127.0.0.1", True)):
                try:
                    self.httpd = ThreadingHTTPServer((host, 0), Handler)
                    self.httpd.daemon_threads = True
                    self.sealed = sealed
                    self.base = f"http://{host}:{self.httpd.server_address[1]}"
                    break
                except OSError:
                    continue
            if not self.httpd:
                raise CoderError("Could not start the page preview.")
            threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
            return self.base

    def url(self, root: Path, page: str = "") -> str:
        base = self.start()
        root = Path(root).resolve()
        token = next((t for t, r in self.roots.items() if r == root), None)
        if token is None:
            token = secrets.token_hex(6)
            self.roots[token] = root
        return f"{base}/p/{token}/" + "/".join(unquote(x) for x in (page or "").replace("\\", "/").split("/") if x)


# ---------------- a hidden browser to look at the pages ----------------
class BrowserWorker:
    """Playwright in its own thread (its objects must stay in the thread that made them). Edge or Chrome as installed,
    else Playwright's own Chromium; hidden; a fresh tab for each check, so nothing is left over between checks."""

    def __init__(self):
        self.q: queue.Queue = queue.Queue()
        self.thread = None
        self.pw = None
        self.browser = None
        self.idle_since = time.time()

    def _loop(self):
        while True:
            try:
                fn, box, done = self.q.get(timeout=120)
            except queue.Empty:
                if self.browser and time.time() - self.idle_since > 300:      # closed after five quiet minutes
                    self._close()
                continue
            try:
                box["result"] = fn()
            except Exception as exc:
                box["error"] = exc
            self.idle_since = time.time()
            done.set()

    def _call(self, fn, timeout=90):
        if not self.thread or not self.thread.is_alive():
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()
        box, done = {}, threading.Event()
        self.q.put((fn, box, done))
        if not done.wait(timeout):
            raise CoderError("The browser did not answer.")
        if "error" in box:
            raise box["error"]
        return box["result"]

    def _open(self):
        if self.browser:
            return
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            raise CoderError("Looking at pages needs Playwright: Settings > Computer control > Install browser control.")
        self.pw = sync_playwright().start()
        last = None
        # Windows: the Edge that is already installed (nothing to download); elsewhere Playwright's own Chromium first
        for channel in (("msedge", "chrome", None) if os.name == "nt" else (None, "chrome", "msedge")):
            try:
                self.browser = self.pw.chromium.launch(headless=True, timeout=30000, **({"channel": channel} if channel else {}))
                return
            except Exception as exc:
                last = exc
        self._close()
        raise CoderError(f"No browser could be started for the check ({str(last)[:160]}).")

    def _close(self):
        for obj, how in ((self.browser, "close"), (self.pw, "stop")):
            try:
                if obj:
                    getattr(obj, how)()
            except Exception:
                pass
        self.browser = self.pw = None

    def close(self):
        if self.thread and self.thread.is_alive():
            try:
                self._call(self._close, 20)
            except Exception:
                pass

    def check(self, url: str, steps: list[str] | None = None, size: tuple[int, int] = (1024, 700)) -> dict:
        return self._call(lambda: self._check(url, steps or [], size))

    def _check(self, url: str, steps: list[str], size) -> dict:
        self._open()
        base = url.split("/p/")[0]
        prefix = url[: url.index("/p/") + 3 + 12 + 1] if "/p/" in url else base
        short = lambda u: (u or "").replace(prefix, "").replace(base, "")
        errors, warnings, failed = [], [], []
        ctx = self.browser.new_context(viewport={"width": size[0], "height": size[1]})
        try:
            page = ctx.new_page()

            def console(m):
                if m.type in ("error", "warning") and len(errors) + len(warnings) < 30:
                    loc = m.location or {}
                    where = f" ({short(loc.get('url'))}:{loc.get('lineNumber', 0) + 1})" if loc.get("url") else ""
                    if m.type == "error" and "Failed to load resource" in m.text:
                        return                                   # said better by the response below
                    (errors if m.type == "error" else warnings).append(f"{m.text[:300]}{where}")

            def pageerror(e):
                stack = str(getattr(e, "stack", "") or "")
                at = re.search(r"at .*?\((.*?):(\d+):\d+\)|at (\S+?):(\d+):\d+", stack)
                where = f" ({short(at.group(1) or at.group(3))}:{at.group(2) or at.group(4)})" if at else ""
                errors.append(f"Uncaught {getattr(e, 'name', '') or 'Error'}: {getattr(e, 'message', str(e))[:300]}{where}")

            page.on("console", console)
            page.on("pageerror", pageerror)
            page.on("requestfailed", lambda r: failed.append(f"could not load {short(r.url)}"))
            page.on("response", lambda r: failed.append(f"{r.status} for {short(r.url)} (missing or wrong path?)") if r.status >= 400 and not r.url.endswith("favicon.ico") else None)
            try:
                page.goto(url, wait_until="load", timeout=15000)
            except Exception as exc:
                errors.append(f"The page did not load: {str(exc).splitlines()[0][:200]}")
            page.wait_for_timeout(700)
            done, step_errors = [], []
            for step in steps[:12]:
                try:
                    self._step(page, step)
                    done.append(step)
                except Exception as exc:
                    why = str(exc).splitlines()[0][:200]
                    if "Timeout" in why:
                        why = "nothing on the page matches that (or it is hidden or covered)"
                    step_errors.append(f"{step}: {why}")
                page.wait_for_timeout(250)
            shot = base64.b64encode(page.screenshot(type="jpeg", quality=70)).decode("ascii")
            info = page.evaluate("""() => {
                const b = document.body; if (!b) return {text: '', things: 0, title: document.title};
                const seen = [...document.querySelectorAll('canvas,svg,img,video,input,button')].filter(e => { const r = e.getBoundingClientRect(); return r.width > 4 && r.height > 4; }).length;
                return {text: b.innerText || '', things: seen, title: document.title, wide: document.documentElement.scrollWidth > innerWidth + 4};
            }""")
            text = re.sub(r"\n{3,}", "\n\n", str(info.get("text") or "")).strip()
            gone = {f.split(" for ", 1)[1].split(" (")[0] for f in failed if " for " in f}
            failed = [f for f in failed if not (f.startswith("could not load ") and f[len("could not load "):] in gone)]

            def once(items):
                out = []
                for x in items:
                    n = items.count(x)
                    y = f"{x} ({n}×)" if n > 1 else x
                    if y not in out:
                        out.append(y)
                return out
            errors, warnings, failed = once(errors), once(warnings), once(failed)
            return {"url": url, "title": info.get("title") or "", "errors": errors, "warnings": warnings, "failed": failed[:15], "steps": done,
                    "step_errors": step_errors, "text": text[:2000], "blank": not text and not info.get("things"), "wide": bool(info.get("wide")), "shot": shot}
        finally:
            try:
                ctx.close()
            except Exception:
                pass

    @staticmethod
    def _step(page, step: str):
        m = re.match(r"(\w+)\s*(.*)$", step.strip())
        word, rest = (m.group(1).lower(), m.group(2).strip()) if m else ("", "")
        if word == "click":
            target = rest.strip("\"'`")
            if re.match(r"^[#.\[]|^[a-z]+[#.\[:]|^(?:button|canvas|a|input|body)$", target):
                page.click(target, timeout=3000)
            else:
                page.get_by_text(target, exact=False).first.click(timeout=3000)
        elif word == "press":
            for key in rest.split():
                page.keyboard.press(key.strip("\"'`"))
        elif word == "type":
            sel, _, text = rest.partition(" ")
            if re.match(r"^[#.\[]|^[a-z]+[#.\[]", sel):
                page.fill(sel, text.strip("\"'"), timeout=3000)
            else:
                page.keyboard.type(rest.strip("\"'"))
        elif word == "wait":
            page.wait_for_timeout(min(5000, int(re.sub(r"\D", "", rest) or 500)))
        elif word == "scroll":
            page.mouse.wheel(0, int(re.sub(r"[^\d-]", "", rest) or 600))
        else:
            raise CoderError("unknown step (use click, press, type, wait or scroll)")


def check_text(c: dict, page: str) -> str:
    out = [f"Page {page} in the browser" + (f" (title “{c['title']}”)" if c.get("title") else "") + ":"]
    if c.get("steps"):
        out.append("Did: " + "; ".join(c["steps"]))
    problems = c["errors"] + c["failed"] + c.get("step_errors", [])
    out.append(("Errors:\n- " + "\n- ".join(problems)) if problems else "No errors.")
    if c["warnings"]:
        out.append("Warnings:\n- " + "\n- ".join(c["warnings"][:8]))
    if c.get("blank"):
        out.append("The page looks empty (no text, no pictures, no canvas).")
    if c.get("wide"):
        out.append("The page is wider than the window (a sideways scrollbar).")
    if c.get("text"):
        out.append("Visible text:\n" + c["text"][:1500])
    return "\n".join(out)


# ---------------- running a program (after you allow it) ----------------
def run_command(root: Path, args: str, timeout: int = RUN_TIMEOUT) -> dict:
    parts = args.split()
    if parts and parts[0].lower() in ("python", "python3", "py", "node"):
        parts = parts[1:]
    if not parts:
        raise CoderError("RUN needs a file: RUN main.py")
    env = {k: v for k, v in os.environ.items() if not re.search(r"KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL", k, re.I)}
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    if parts[0].lower() in ("tests", "test", "pytest"):
        cmd = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider"]
        shown = "the tests"
    else:
        target = safe_path(root, parts[0])
        if not target.is_file():
            raise CoderError(f"There is no file {parts[0]}.")
        ext = target.suffix.lower()
        if ext == ".py":
            cmd = [sys.executable, str(target)]
        elif ext in (".js", ".mjs", ".cjs"):
            import shutil
            node = shutil.which("node")
            if not node:
                raise CoderError("Node.js is not installed, so JavaScript files cannot be run here (web pages are checked in the browser instead).")
            cmd = [node, str(target)]
        else:
            raise CoderError("Jarvis Code runs Python (.py) and JavaScript (.js) files only.")
        cmd += parts[1:]
        shown = rel_of(root, target)

    def go(c):
        try:
            p = subprocess.run(c, cwd=str(root), capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL, env=env,
                               encoding="utf-8", errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return p.returncode, (p.stdout or "") + (p.stderr or "")
        except subprocess.TimeoutExpired as exc:
            out = (exc.stdout or "") + (exc.stderr or "")
            out = out.decode("utf-8", "replace") if isinstance(out, bytes) else out
            return None, out + f"\n(stopped after {timeout} s)"

    code, out = go(cmd)
    if shown == "the tests" and "No module named pytest" in out:
        code, out = go([sys.executable, "-m", "unittest", "discover", "-v"])
    out = out.strip()
    if len(out) > 4000:
        out = out[:1200] + "\n…\n" + out[-2600:]
    return {"code": code, "out": out, "shown": shown}


# ---------------- one task ----------------
class Session:
    """One task on one project. llm(messages, on_text) -> answer; check(url, steps) -> dict (BrowserWorker.check);
    preview: PreviewServer. The loop runs in its own thread (start()); public() is what the page shows."""

    def __init__(self, root: Path, task: str, *, llm, check, preview: PreviewServer, backup_root: Path, vision: bool = False,
                 max_turns: int = 30, trusted: bool = False, notify=None, model: str = ""):
        self.root = Path(root).resolve()
        self.task = task.strip()
        self.llm, self.check_fn, self.preview = llm, check, preview
        self.backup_root = Path(backup_root) / time.strftime("%Y%m%d-%H%M%S")
        self.vision, self.max_turns, self.trusted, self.notify, self.model = vision, max_turns, trusted, notify or (lambda *a: None), model
        self.id = secrets.token_hex(4)
        self.status = "working"
        self.turn = 0
        self.log: list[dict] = []
        self.live = ""
        self.last_check: dict | None = None
        self.page = main_page(self.root)
        self.changes: list[dict] = []              # undo: {"path", "before" (None: the file was new)}
        self.summary = ""
        self.error = ""
        self.pending: dict | None = None
        self._decision = threading.Event()
        self._answer = ""
        self.stopping = False
        self.started = time.time()
        self.lock = threading.Lock()
        self.thread: threading.Thread | None = None
        self.dirty = False                          # a page changed since the last check

    # ----- what the page sees -----
    def add(self, kind: str, title: str, detail: str = "", ok: bool = True) -> None:
        with self.lock:
            self.log.append({"n": len(self.log) + 1, "kind": kind, "title": title, "detail": detail[:20000], "ok": ok, "at": time.time()})
            if len(self.log) > 300:
                self.log = self.log[-300:]

    def public(self, since: int = 0, shot_at: float = 0) -> dict:
        with self.lock:
            log = [e for e in self.log if e["n"] > since]
        c = self.last_check
        return {"id": self.id, "status": self.status, "task": self.task, "project": str(self.root), "name": self.root.name, "turn": self.turn,
                "max_turns": self.max_turns, "log": log, "live": self.live[-6000:], "summary": self.summary, "error": self.error, "model": self.model,
                "pending": self.pending, "changed": sorted({c["path"] for c in self.changes}), "can_undo": bool(self.changes),
                "page": self.page, "preview": self.preview.url(self.root, self.page or "") if self.page else "",
                "check": {k: c[k] for k in ("url", "title", "errors", "warnings", "failed", "step_errors", "blank", "shot", "at") if k in c and (k != "shot" or c.get("at", 0) > shot_at)} if c else None}

    # ----- control -----
    def start(self) -> None:
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stopping = True
        self._answer = "no"
        self._decision.set()

    def decide(self, answer: str) -> None:
        self._answer = answer
        self._decision.set()

    def undo_last(self) -> str:
        if self.status in ("working", "waiting"):
            raise CoderError("Stop the task first.")
        if not self.changes:
            raise CoderError("There is nothing to undo.")
        ch = self.changes.pop()
        p = safe_path(self.root, ch["path"])
        if ch["before"] is None:
            if p.exists():
                p.unlink()
        else:
            write_text(p, ch["before"])
        self.add("undo", f"Undid the change to {ch['path']}")
        self.last_check = None
        return ch["path"]

    def undo_all(self) -> int:
        n = 0
        while self.changes:
            self.undo_last()
            n += 1
        return n

    # ----- doing the commands -----
    def _save(self, rel: str, text: str) -> tuple[str, int, int]:
        p = safe_path(self.root, rel, write=True)
        if p.is_dir():
            raise CoderError(f"{rel} is a folder.")
        if len(text.encode("utf-8")) > FILE_LIMIT:
            raise CoderError("That is more than 300 KB.")
        before = read_text(p) if p.exists() else None
        if before == text:
            return "", 0, 0
        if before is not None:
            backup = self.backup_root / rel
            if not backup.exists():
                backup.parent.mkdir(parents=True, exist_ok=True)
                backup.write_text(before, encoding="utf-8")
        write_text(p, text)
        self.changes.append({"path": rel_of(self.root, p), "before": before})
        if p.suffix.lower() in WEB_PAGES + (".css", ".js", ".mjs", ".json", ".svg"):
            self.dirty = True
            if not self.page and p.suffix.lower() in WEB_PAGES:
                self.page = main_page(self.root)
        return diff_text(before, text, rel_of(self.root, p))

    def _do(self, c: dict) -> tuple[str, bool]:
        """One command → (what the model is told, ok)."""
        if c.get("error"):
            self.add("error", c["error"], ok=False)
            return c["error"], False
        cmd = c["cmd"]
        try:
            if cmd == "READ":
                p = safe_path(self.root, c["path"])
                if p.is_dir():
                    return f"{c['path']} is a folder:\n" + tree(p), True
                if not p.is_file():
                    raise CoderError(f"There is no file {c['path']}." + (" (LIST shows the files.)" if self.root.exists() else ""))
                text = read_text(p)
                total = text.count("\n") + (0 if text.endswith("\n") else 1)
                a = c.get("from") or 1
                b = c.get("to") or min(total, a + READ_LINES - 1)
                more = f"\n(lines {a}-{b} of {total}; READ {c['path']} {b + 1}-{min(total, b + READ_LINES)} for more)" if b < total else ""
                self.add("read", f"Read {rel_of(self.root, p)}" + (f" (lines {a}–{b})" if a > 1 or b < total else ""))
                return numbered(text, a, b) + more, True
            if cmd == "LIST":
                p = safe_path(self.root, c["path"])
                self.add("list", f"Listed {c['path'] or 'the project'}")
                return tree(p), True
            if cmd == "FIND":
                found = find_in(self.root, c["text"])
                self.add("find", f"Searched for “{c['text'].strip()[:60]}”", found)
                return found, True
            if cmd == "WRITE":
                if not c["path"]:
                    raise CoderError("WRITE needs a file name: WRITE css/style.css")
                body = c["body"]
                d, plus, minus = self._save(c["path"], body + ("" if body.endswith("\n") else "\n"))
                if not d:
                    return f"{c['path']} already had exactly that text.", True
                self.add("write", f"Wrote {c['path']} (+{plus} −{minus})", d)
                return f"Wrote {c['path']} ({body.count(chr(10)) + 1} lines).", True
            if cmd == "EDIT":
                p = safe_path(self.root, c["path"], write=True)
                if not c["path"] or not p.is_file():
                    raise CoderError(f"There is no file {c['path'] or '(no name given)'} to edit. Use WRITE for a new file.")
                pairs = edit_pairs(c["body"])
                if not pairs:
                    raise CoderError("EDIT needs <<<<<<< FIND, the old lines, =======, the new lines, >>>>>>> REPLACE.")
                text = read_text(p)
                firsts = []
                for n, (f, r) in enumerate(pairs, 1):
                    try:
                        text, line = apply_edit(text, f, r)
                        firsts.append(line)
                    except CoderError as exc:
                        raise CoderError((f"Change {n} of {len(pairs)}: " if len(pairs) > 1 else "") + str(exc) +
                                         (f" (changes 1–{n - 1} were not saved either)" if n > 1 else ""))
                d, plus, minus = self._save(c["path"], text)
                if not d:
                    return f"{c['path']}: the new text is the same as the old one.", True
                self.add("edit", f"Edited {c['path']} (+{plus} −{minus})", d)
                lines = text.split("\n")
                a = max(1, min(firsts) - 3)
                b = min(len(lines), max(firsts) + max(len(r.split("\n")) for _, r in pairs) + 3)
                return f"Edited {c['path']}. It now reads (lines {a}-{b}):\n{numbered(text, a, b)}", True
            if cmd == "CHECK":
                page = c.get("page") or self.page
                if not page:
                    raise CoderError("There is no web page (.html) in the project to check.")
                return self._check(page, c.get("steps") or []), True
            if cmd == "RUN":
                return self._run_program(c["args"]), True
        except CoderError as exc:
            self.add("error", f"{cmd} {c.get('path') or c.get('args') or ''}: {exc}".replace("  ", " ")[:300], str(exc), ok=False)
            return f"{cmd} failed: {exc}", False
        except OSError as exc:
            self.add("error", f"{cmd} failed: {exc}", ok=False)
            return f"{cmd} failed: {exc}", False
        return "", True

    def _check(self, page: str, steps: list[str]) -> str:
        p = safe_path(self.root, page)
        if not p.is_file():
            raise CoderError(f"There is no page {page}.")
        page = rel_of(self.root, p)
        self.page = page
        url = self.preview.url(self.root, page)
        c = self.check_fn(url, steps)
        c["at"] = time.time()
        self.last_check = c
        self.dirty = False
        problems = len(c["errors"]) + len(c["failed"]) + len(c.get("step_errors", []))
        self.add("check", f"Looked at {page} in the browser: " + (f"{problems} error{'s' if problems != 1 else ''}" if problems else "no errors")
                 + (" (empty page)" if c.get("blank") else ""), check_text(c, page), ok=not problems and not c.get("blank"))
        return check_text(c, page)

    def _run_program(self, args: str) -> str:
        if not self.trusted:
            self.pending = {"id": secrets.token_hex(3), "command": args}
            self.status = "waiting"
            self.add("ask", f"Waiting for your OK to run {args}")
            self.notify("ask", f"Jarvis Code is waiting for your OK to run {args} in {self.root.name}.")
            self._decision.clear()
            self._decision.wait(900)
            answer, self.pending = self._answer if self._decision.is_set() else "no", None
            self.status = "working"
            if self.stopping:
                raise CoderError("stopped")
            if answer == "always":
                self.trusted = True
            elif answer != "yes":
                self.add("run", f"You said no to running {args}", ok=False)
                return f"The user did not allow running {args}. Check the code another way, or finish."
        r = run_command(self.root, args)
        ok = r["code"] == 0
        self.add("run", f"Ran {r['shown']}: " + ("finished" if ok else "stopped after the time limit" if r["code"] is None else f"exit code {r['code']}"), r["out"], ok=ok)
        return f"Ran {r['shown']} (exit code {r['code']}):\n{r['out'] or '(no output)'}"

    # ----- the conversation with the model -----
    def _intro(self) -> str:
        snap = snapshot(self.root)
        parts = [f"The user's task: {self.task}", f"Project folder: {self.root.name}", "Files:\n" + tree(self.root)]
        if snap:
            parts.append("Their contents (with line numbers):\n" + snap)
        elif walk(self.root, 1):
            parts.append("The project is too big to show whole: READ the files you need.")
        if self.page:
            parts.append(f"The main page is {self.page}. After you change it (or its CSS/JS), Jarvis opens it in the browser and tells you what it sees.")
        return "\n\n".join(parts)

    @staticmethod
    def _short(m: dict) -> dict:
        """An older message, made small: code in answers becomes “…”, results keep their first lines."""
        text = m["content"]
        if m["role"] == "assistant":
            text = re.sub(r"```.*?```", "```…```", text, flags=re.S)
        else:
            text = "\n".join(l for l in text.split("\n")[:6]) + ("\n…" if text.count("\n") > 6 else "")
        return {"role": m["role"], "content": text}

    def _messages(self, history: list[dict]) -> list[dict]:
        msgs = [dict(m) for m in history]
        for m in msgs[:-1]:
            m.pop("images", None)
        total = sum(len(m["content"]) for m in msgs)
        i = 2
        while total > BUDGET_CHARS and i < len(msgs) - 4:
            before = len(msgs[i]["content"])
            msgs[i] = self._short(msgs[i])
            total -= before - len(msgs[i]["content"])
            i += 1
        return msgs

    def _on_text(self, piece: str) -> None:
        self.live += piece
        if self.stopping:
            raise CoderError("stopped")

    def _run(self) -> None:
        history = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": self._intro()}]
        idle, pushed, failed_edits = 0, False, 0
        self.add("start", f"Task: {self.task}", f"Project: {self.root}")
        try:
            while self.turn < self.max_turns and not self.stopping:
                self.turn += 1
                self.live = ""
                reply = self.llm(self._messages(history), self._on_text)
                self.live = ""
                if self.stopping:
                    break
                history.append({"role": "assistant", "content": reply})
                thought, cmds = parse(reply)
                if thought:
                    self.add("think", thought)
                if not cmds:
                    idle += 1
                    if idle >= 2:
                        self.summary = reply.strip()[:1200]
                        self.status = "done"
                        break
                    history.append({"role": "user", "content": "Answer with commands (READ, EDIT, WRITE, CHECK, RUN or DONE), in the form shown at the start."})
                    continue
                idle = 0
                results, done, checked = [], None, False
                for c in cmds:
                    if self.stopping:
                        break
                    if c["cmd"] == "DONE":
                        done = c
                        continue
                    text, ok = self._do(c)
                    checked = checked or c["cmd"] == "CHECK"
                    if c["cmd"] in ("EDIT", "WRITE"):
                        failed_edits = 0 if ok else failed_edits + 1
                    results.append(f"[{c['cmd']} {c.get('path') or c.get('page') or c.get('args') or c.get('text') or ''}]".replace(" ]", "]") + "\n" + text)
                if self.stopping:
                    break
                if self.dirty and self.page and not checked:
                    try:
                        results.append(f"[CHECK {self.page}] (automatic, after your changes)\n" + self._check(self.page, []))
                        checked = True
                    except CoderError as exc:
                        results.append(f"[CHECK] could not be done: {exc}")
                        self.dirty = False
                if done is not None:
                    c = self.last_check
                    bad = c and (c["errors"] or c["failed"] or c.get("step_errors") or c.get("blank"))
                    if bad and not pushed and self.page:
                        pushed = True
                        results.append("Before you finish: the last check of the page still shows problems (above). Fix them, or answer DONE again if they do not matter.")
                    else:
                        self.summary = done["text"] or "Done."
                        self.status = "done"
                        self.add("done", self.summary)
                        break
                if failed_edits >= 2:
                    results.append("Your edits keep failing. READ the file again, then copy the FIND lines exactly from it (a few lines are enough), or WRITE the whole file if it is small.")
                obs = "\n\n".join(results)
                if len(obs) > OBSERVATION_CHARS:
                    obs = obs[:OBSERVATION_CHARS] + "\n… (cut: READ smaller parts)"
                msg = {"role": "user", "content": obs + f"\n\n(step {self.turn} of {self.max_turns})"}
                if checked and self.vision and self.last_check and self.last_check.get("shot"):
                    msg["content"] += "\nThe screenshot of the page is attached: look at it too (layout, colours, anything cut off or missing)."
                    msg["images"] = [self.last_check["shot"]]
                history.append(msg)
            else:
                if not self.stopping:
                    self.status = "out_of_steps"
                    self.summary = f"I used all {self.max_turns} steps without finishing. What changed is kept (you can undo it); ask again to continue."
        except CoderError as exc:
            if not self.stopping:
                self.status, self.error = "error", str(exc)
        except Exception as exc:
            self.status, self.error = "error", f"{type(exc).__name__}: {exc}"[:400]
        if self.stopping:
            self.status = "stopped"
            self.summary = self.summary or "Stopped. What changed so far is kept (you can undo it)."
        self.live = ""
        if self.status == "error":
            self.add("error", self.error, ok=False)
        files = sorted({c["path"] for c in self.changes})
        self.notify("end", (self.summary or self.error or "Finished.") + (f" Changed: {', '.join(files[:8])}." if files else ""))

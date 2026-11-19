"""MCP (Model Context Protocol): let Jarvis use tools that other programs offer, such as a GitHub, Notion, maps or file server.

A server is either a program Jarvis starts and talks to through its input and output ("command", for example
`npx -y @modelcontextprotocol/server-filesystem C:\\Users\\Me\\Documents` or `uvx mcp-server-fetch`), or a web address
("http", for example https://api.githubcopilot.com/mcp/ with an `Authorization: Bearer …` header). Servers are listed in
data/mcp.json, which stays on this PC (it may hold tokens).

Each tool a server offers becomes a Smart-commands tool, so the AI model can pick it when your message mentions the server
(its name, or the trigger words you give it). Every call shows an approval card first, unless you ticked "run without asking"
for that tool. What a tool returns is data from another program: it is summarised for you and never followed as instructions.

    Server(config)        .connect() .tools() .call(name, arguments) .close()     one server
    Manager(path)         .config() .save(...) .remove(name) .connect_all() .status() .find(registry_name) .call(...)
"""
from __future__ import annotations

import json
import os
import queue
import re
import shlex
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

PROTOCOL = "2025-06-18"
CLIENT = {"name": "Jarvis", "version": "1.0"}
MAX_SERVERS, MAX_TOOLS_PER_SERVER, MAX_RESULT = 8, 40, 12000
NAME_RE = re.compile(r"[A-Za-z][\w -]{0,23}")


class MCPError(Exception):
    pass


def slug(text: str, n: int) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", (text or "").lower())).strip("_")[:n] or "x"


def result_text(result: dict) -> str:
    """The text of a tools/call result (text parts, and a note for anything else)."""
    if not isinstance(result, dict):
        return str(result)[:MAX_RESULT]
    parts = []
    for item in result.get("content") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text":
            parts.append(str(item.get("text") or ""))
        elif item.get("type") == "resource" and isinstance(item.get("resource"), dict):
            parts.append(str(item["resource"].get("text") or f"[a resource: {item['resource'].get('uri', '')}]"))
        else:
            parts.append(f"[{item.get('type', 'something')} not shown]")
    if not parts and result.get("structuredContent") is not None:
        parts.append(json.dumps(result["structuredContent"], ensure_ascii=False))
    text = "\n".join(p for p in parts if p).strip()
    return text[:MAX_RESULT] + ("…" if len(text) > MAX_RESULT else "")


class Server:
    def __init__(self, config: dict, popen=subprocess.Popen, opener=urllib.request.urlopen, timeout: float = 30):
        self.config = config
        self.name = config["name"]
        self.popen, self.opener, self.timeout = popen, opener, timeout
        self.lock = threading.Lock()
        self.proc = None
        self.replies: dict = {}
        self.counter = 0
        self.session_id = None
        self.listed: list[dict] = []
        self.error = ""
        self.connected = False

    # ---------------- transports ----------------
    def _next_id(self) -> int:
        self.counter += 1
        return self.counter

    def _start_process(self) -> None:
        cmd = self.config.get("command") or ""
        args = cmd if isinstance(cmd, list) else shlex.split(cmd, posix=os.name != "nt")
        args = [a.strip('"') for a in args]
        if not args:
            raise MCPError("No command to start.")
        env = {**os.environ, **{str(k): str(v) for k, v in (self.config.get("env") or {}).items()}}
        try:
            self.proc = self.popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, cwd=self.config.get("cwd") or None,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), shell=False)
        except OSError as exc:
            raise MCPError(f"Could not start {args[0]}: {exc}") from None
        self.replies = {}
        proc = self.proc

        def read() -> None:
            try:
                for raw in iter(proc.stdout.readline, b""):
                    try:
                        msg = json.loads(raw.decode("utf-8", errors="replace"))
                    except ValueError:
                        continue                       # servers sometimes print other things
                    self._incoming(msg, lambda reply: self._write(reply))
            except Exception:
                pass
            for q in list(self.replies.values()):
                q.put(None)
        threading.Thread(target=read, daemon=True).start()

    def _write(self, msg: dict) -> None:
        if self.proc is None or self.proc.poll() is not None:
            raise MCPError("The server is not running.")
        self.proc.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
        self.proc.stdin.flush()

    def _incoming(self, msg: dict, send) -> None:
        if not isinstance(msg, dict):
            return
        if "id" in msg and ("result" in msg or "error" in msg) and "method" not in msg:
            q = self.replies.get(msg["id"])
            if q:
                q.put(msg)
        elif "id" in msg and "method" in msg:              # a request from the server: answer ping, decline the rest
            try:
                if msg["method"] == "ping":
                    send({"jsonrpc": "2.0", "id": msg["id"], "result": {}})
                else:
                    send({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": "Jarvis does not support that."}})
            except Exception:
                pass

    def _http(self, msg: dict, want_reply: bool) -> dict | None:
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": PROTOCOL,
                   **{str(k): str(v) for k, v in (self.config.get("headers") or {}).items()}}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        req = urllib.request.Request(self.config["url"], data=json.dumps(msg).encode("utf-8"), headers=headers, method="POST")
        try:
            with self.opener(req, timeout=self.timeout) as resp:
                sid = resp.headers.get("Mcp-Session-Id")
                if sid:
                    self.session_id = sid
                kind = (resp.headers.get("Content-Type") or "").lower()
                if not want_reply:
                    return None
                if "text/event-stream" in kind:
                    data_lines = []
                    for raw in resp:
                        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                        if line.startswith("data:"):
                            data_lines.append(line[5:].lstrip())
                        elif not line and data_lines:
                            try:
                                got = json.loads("\n".join(data_lines))
                            except ValueError:
                                got = None
                            data_lines = []
                            if isinstance(got, dict) and got.get("id") == msg.get("id") and ("result" in got or "error" in got):
                                return got
                    if data_lines:
                        try:
                            got = json.loads("\n".join(data_lines))
                            if isinstance(got, dict) and got.get("id") == msg.get("id"):
                                return got
                        except ValueError:
                            pass
                    raise MCPError("The server's answer ended without a reply.")
                body = resp.read().decode("utf-8", errors="replace")
                got = json.loads(body) if body.strip() else None
                if isinstance(got, list):
                    got = next((g for g in got if isinstance(g, dict) and g.get("id") == msg.get("id")), None)
                return got
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise MCPError("The server refused the sign-in (check the token in its headers).") from None
            if exc.code == 404 and self.session_id:
                self.session_id = None
                raise MCPError("The server forgot this session; reconnect.") from None
            raise MCPError(f"The server answered with error {exc.code}.") from None
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise MCPError(f"Could not reach the server: {exc}") from None

    def request(self, method: str, params: dict | None = None, timeout: float | None = None) -> dict:
        msg = {"jsonrpc": "2.0", "id": self._next_id(), "method": method}
        if params is not None:
            msg["params"] = params
        if self.config.get("type") == "http":
            got = self._http(msg, True)
        else:
            q: queue.Queue = queue.Queue()
            self.replies[msg["id"]] = q
            try:
                self._write(msg)
                got = q.get(timeout=timeout or self.timeout)
            except queue.Empty:
                raise MCPError(f"The server did not answer {method} in time.") from None
            except (OSError, ValueError) as exc:
                raise MCPError(f"The server stopped: {exc}") from None
            finally:
                self.replies.pop(msg["id"], None)
        if got is None:
            raise MCPError("The server stopped.")
        if "error" in got:
            err = got["error"] if isinstance(got["error"], dict) else {"message": str(got["error"])}
            raise MCPError(str(err.get("message") or "error")[:300])
        return got.get("result") or {}

    def notify(self, method: str, params: dict | None = None) -> None:
        msg = {"jsonrpc": "2.0", "method": method, **({"params": params} if params is not None else {})}
        if self.config.get("type") == "http":
            try:
                self._http(msg, False)
            except MCPError:
                pass
        else:
            self._write(msg)

    # ---------------- the protocol ----------------
    def connect(self) -> list[dict]:
        with self.lock:
            self.close_locked()
            try:
                if self.config.get("type") != "http":
                    self._start_process()
                init = self.request("initialize", {"protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": CLIENT}, timeout=60)
                self.notify("notifications/initialized")
                tools, cursor = [], None
                for _ in range(10):
                    page = self.request("tools/list", {"cursor": cursor} if cursor else {})
                    tools += [t for t in page.get("tools") or [] if isinstance(t, dict) and t.get("name")]
                    cursor = page.get("nextCursor")
                    if not cursor or len(tools) >= MAX_TOOLS_PER_SERVER:
                        break
                self.listed = tools[:MAX_TOOLS_PER_SERVER]
                self.info = init.get("serverInfo") or {}
                self.connected, self.error = True, ""
                return self.listed
            except MCPError as exc:
                self.error, self.connected = str(exc), False
                self.close_locked()
                raise

    def tools(self) -> list[dict]:
        return list(self.listed)

    def call(self, name: str, arguments: dict) -> tuple[str, bool]:
        """(text of the result, True when the tool said it failed)."""
        if not self.connected or (self.config.get("type") != "http" and (self.proc is None or self.proc.poll() is not None)):
            self.connect()
        with self.lock:
            result = self.request("tools/call", {"name": name, "arguments": arguments}, timeout=120)
        return result_text(result), bool(result.get("isError"))

    def close_locked(self) -> None:
        proc, self.proc = self.proc, None
        self.connected = False
        if proc is not None:
            try:
                proc.stdin.close()
            except Exception:
                pass
            try:
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        if self.config.get("type") == "http" and self.session_id:
            self.session_id = None

    def close(self) -> None:
        with self.lock:
            self.close_locked()


# ---------------- the list of servers ----------------
def clean_config(raw: dict) -> dict:
    name = re.sub(r"\s+", " ", str(raw.get("name") or "")).strip()
    if not NAME_RE.fullmatch(name):
        raise ValueError("Give the server a short name (letters, digits, spaces, up to 24), for example GitHub.")
    kind = "http" if raw.get("type") == "http" else "command"
    out = {"name": name, "type": kind, "enabled": raw.get("enabled", True) is not False}
    if kind == "http":
        url = str(raw.get("url") or "").strip()
        if not re.fullmatch(r"https?://[^\s]+", url):
            raise ValueError("Give the server's web address, starting with https://.")
        if url.startswith("http://") and not re.match(r"http://(?:localhost|127\.0\.0\.1|\[::1\])(?::\d+)?/", url):
            raise ValueError("Use https:// for a server on the internet (http:// only for this PC).")
        out["url"] = url
    else:
        cmd = str(raw.get("command") or "").strip()
        if not cmd or len(cmd) > 1000:
            raise ValueError("Give the command that starts the server, for example: npx -y @modelcontextprotocol/server-filesystem C:\\Users\\Me\\Documents")
        out["command"] = cmd
    for key in ("headers", "env"):
        val = raw.get(key) or {}
        if isinstance(val, str):
            pairs = {}
            for line in val.splitlines():
                sep = ":" if key == "headers" else "="
                if sep in line:
                    k, v = line.split(sep, 1)
                    if k.strip():
                        pairs[k.strip()] = v.strip()
            val = pairs
        out[key] = {str(k)[:80]: str(v)[:2000] for k, v in dict(val).items()}
    words = raw.get("words") or ""
    words = [w.strip() for w in (words.split(",") if isinstance(words, str) else words) if str(w).strip()][:8]
    out["words"] = [w[:30] for w in words]
    out["tools"] = {str(k): {"use": bool(v.get("use", True)), "auto": bool(v.get("auto", False))} for k, v in (raw.get("tools") or {}).items() if isinstance(v, dict)}
    return out


class Manager:
    def __init__(self, path: Path, popen=subprocess.Popen, opener=urllib.request.urlopen):
        self.path = Path(path)
        self.popen, self.opener = popen, opener
        self.lock = threading.RLock()
        self.servers: dict[str, Server] = {}
        self.names: dict[str, tuple[str, str]] = {}           # registry name -> (server, tool)

    def config(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        out = []
        for raw in (data.get("servers") if isinstance(data, dict) else None) or []:
            try:
                out.append(clean_config(raw))
            except (ValueError, TypeError):
                continue
        return out

    def _write(self, servers: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"servers": servers}, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def save(self, raw: dict, replace: str | None = None) -> dict:
        """Adds or changes a server. Secret values sent back as "••••" keep what was stored."""
        with self.lock:
            servers = self.config()
            old = next((s for s in servers if s["name"].lower() == replace.lower()), None) if replace else None
            for key in ("headers", "env"):
                val = raw.get(key)
                if isinstance(val, str) and old:
                    lines = []
                    for line in val.splitlines():
                        sep = ":" if key == "headers" else "="
                        if sep in line:
                            k, v = line.split(sep, 1)
                            if v.strip().startswith("••••") and k.strip() in old[key]:
                                v = old[key][k.strip()]
                            lines.append(f"{k.strip()}{sep} {v.strip()}" if key == "headers" else f"{k.strip()}={v.strip()}")
                    raw = {**raw, key: "\n".join(lines)}
            if old and "tools" not in raw:
                raw = {**raw, "tools": old.get("tools", {})}
            cfg = clean_config(raw)
            others = [s for s in servers if s is not old]
            if any(s["name"].lower() == cfg["name"].lower() for s in others):
                raise ValueError("Another server already has that name.")
            if not old and len(servers) >= MAX_SERVERS:
                raise ValueError(f"You can connect up to {MAX_SERVERS} servers.")
            servers = [cfg if s is old else s for s in servers] if old else servers + [cfg]
            self._write(servers)
            stale = self.servers.pop((old or cfg)["name"], None)
            if stale:
                stale.close()
            return cfg

    def set_tool(self, server: str, tool: str, use: bool | None = None, auto: bool | None = None) -> None:
        with self.lock:
            servers = self.config()
            s = next((s for s in servers if s["name"] == server), None)
            if not s:
                raise ValueError("Unknown server.")
            t = s["tools"].setdefault(tool, {"use": True, "auto": False})
            if use is not None:
                t["use"] = bool(use)
            if auto is not None:
                t["auto"] = bool(auto)
            self._write(servers)

    def remove(self, name: str) -> bool:
        with self.lock:
            servers = self.config()
            keep = [s for s in servers if s["name"] != name]
            self._write(keep)
            gone = self.servers.pop(name, None)
            if gone:
                gone.close()
            return len(keep) != len(servers)

    def connect(self, name: str) -> Server:
        cfg = next((s for s in self.config() if s["name"] == name), None)
        if not cfg:
            raise ValueError("Unknown server.")
        with self.lock:
            server = self.servers.get(name)
            if server is None or server.config != cfg:
                if server:
                    server.close()
                server = Server(cfg, self.popen, self.opener)
                self.servers[name] = server
        try:
            server.connect()
        except MCPError:
            pass
        return server

    def connect_all(self) -> None:
        for cfg in self.config():
            if cfg["enabled"]:
                self.connect(cfg["name"])

    def close_all(self) -> None:
        with self.lock:
            for s in self.servers.values():
                s.close()
            self.servers.clear()

    def status(self) -> list[dict]:
        out = []
        for cfg in self.config():
            server = self.servers.get(cfg["name"])
            tools = []
            for t in (server.tools() if server else []):
                pref = cfg["tools"].get(t["name"], {})
                ann = t.get("annotations") or {}
                tools.append({"name": t["name"], "description": str(t.get("description") or "")[:300], "use": pref.get("use", True), "auto": pref.get("auto", False),
                              "read_only": ann.get("readOnlyHint") is True, "usable": usable(t)})
            masked = {k: {kk: ("••••" + vv[-4:] if len(vv) > 8 else "••••") for kk, vv in cfg[k].items()} for k in ("headers", "env")}
            out.append({**{k: v for k, v in cfg.items() if k not in ("headers", "env")}, **masked, "connected": bool(server and server.connected),
                        "error": server.error if server else "", "tool_list": tools})
        return out

    def registry_tools(self) -> list[dict]:
        """What to give Smart commands: [{name, server, tool, description, params, keywords, auto}]."""
        out, names = [], {}
        for cfg in self.config():
            server = self.servers.get(cfg["name"])
            if not cfg["enabled"] or not server or not server.connected:
                continue
            words = [cfg["name"]] + cfg["words"]
            keywords = r"\b(?:" + "|".join(re.escape(w) for w in words if w) + r")\b"
            for t in server.tools():
                pref = cfg["tools"].get(t["name"], {})
                if not pref.get("use", True) or not usable(t):
                    continue
                base = f"mcp_{slug(cfg['name'], 8)}_{slug(t['name'], 18)}"[:31]
                name, n = base, 2
                while name in names:
                    name = f"{base[:28]}_{n}"
                    n += 1
                names[name] = (cfg["name"], t["name"])
                out.append({"name": name, "server": cfg["name"], "tool": t["name"], "description": f"[{cfg['name']}] " + str(t.get("description") or t["name"])[:300],
                            "params": params_of(t), "keywords": keywords, "auto": pref.get("auto", False), "schema": t.get("inputSchema") or {}})
        with self.lock:
            self.names = names
        return out

    def find(self, registry_name: str) -> tuple[str, str] | None:
        return self.names.get(registry_name)

    def call(self, server: str, tool: str, arguments: dict) -> tuple[str, bool]:
        s = self.servers.get(server)
        if s is None:
            s = self.connect(server)
        try:
            return s.call(tool, arguments)
        except MCPError as exc:
            return f"{server} could not do that: {exc}", True


SCALAR = {"string", "integer", "number", "boolean"}


def usable(tool: dict) -> bool:
    """A tool Jarvis can fill in: every required argument is text, a number, a yes/no or a choice."""
    schema = tool.get("inputSchema") or {}
    props = schema.get("properties") or {}
    for key in schema.get("required") or []:
        p = props.get(key) or {}
        kind = p.get("type")
        if isinstance(kind, list):
            kind = next((k for k in kind if k != "null"), "string")
        if kind not in SCALAR and not p.get("enum"):
            return False
    return True


def params_of(tool: dict) -> dict:
    schema = tool.get("inputSchema") or {}
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    out = {}
    for key, p in list(props.items())[:12]:
        if not isinstance(p, dict):
            continue
        kind = p.get("type")
        if isinstance(kind, list):
            kind = next((k for k in kind if k != "null"), "string")
        if kind not in SCALAR and not p.get("enum"):
            continue
        spec = {"desc": (str(p.get("description") or key)[:160] + f" ({kind or 'text'})"), "required": key in required}
        if p.get("enum"):
            spec["choices"] = [str(c) for c in p["enum"]][:20]
        elif kind in ("integer", "number", "boolean"):
            spec["free"] = False
            if kind == "boolean":
                spec["choices"] = ["true", "false"]
        out[key] = spec
    return out


def typed_args(args: dict, schema: dict) -> dict:
    """Smart commands gives every value as text; the server wants its own types."""
    props = (schema or {}).get("properties") or {}
    out = {}
    for key, value in args.items():
        kind = (props.get(key) or {}).get("type")
        if isinstance(kind, list):
            kind = next((k for k in kind if k != "null"), "string")
        try:
            if kind == "integer":
                out[key] = int(float(str(value).replace(",", ".")))
            elif kind == "number":
                out[key] = float(str(value).replace(",", "."))
            elif kind == "boolean":
                out[key] = str(value).strip().lower() in ("true", "yes", "1", "on")
            else:
                out[key] = str(value)
        except ValueError:
            out[key] = str(value)
    return out

"""Debug mode: a record of what happened while Jarvis answered one message.

When debug mode is on, every chat request gets a trace: the message, a French rewrite, which built-in command caught it, what
Smart commands asked the model and what it answered, each tool and MCP call with its result, web searches, documents and
memory put in the prompt, the model call itself (model, prompt size, time to the first word, total time, the instructions),
the model's thinking, and its raw answer. The trace goes back with the reply (and is shown under it) and the last 50 are
kept in memory for Settings. Nothing is written to disk.

    start(message, source)      begin a trace for this thread
    step(kind, text, detail)    add a line (detail: long text shown folded, such as a prompt)
    active()                    the trace being recorded on this thread, or None
    finish(answered_by)         end it; returns {"steps", "total_ms", ...} and keeps it in recent()
    traced(name, fn)            wraps a matcher so a non-empty result is recorded as "caught by <name>"
    ThinkSplitter               separates <think>…</think> from the visible answer while it streams in
"""
from __future__ import annotations

import collections
import threading
import time

_local = threading.local()
RECENT: collections.deque = collections.deque(maxlen=50)
LOCK = threading.Lock()
MAX_STEPS, MAX_DETAIL = 120, 40000


def start(message: str, source: str = "page") -> dict:
    trace = {"id": f"{time.time():.3f}", "at": time.strftime("%H:%M:%S"), "message": str(message)[:2000], "source": source or "page",
             "started": time.time(), "steps": [], "answered_by": None}
    _local.trace = trace
    step("message", f"Message from {trace['source']}: “{trace['message'][:300]}”")
    return trace


def active() -> dict | None:
    return getattr(_local, "trace", None)


def step(kind: str, text: str, detail: str | None = None) -> None:
    trace = active()
    if trace is None or len(trace["steps"]) >= MAX_STEPS:
        return
    entry = {"ms": round((time.time() - trace["started"]) * 1000), "kind": kind, "text": str(text)[:1000]}
    if detail:
        entry["detail"] = str(detail)[:MAX_DETAIL]
    trace["steps"].append(entry)


def answered(by: str) -> None:
    trace = active()
    if trace is not None and not trace["answered_by"]:
        trace["answered_by"] = by


def finish(status: int = 200, reply: str | None = None, error: str | None = None) -> dict | None:
    trace = active()
    if trace is None:
        return None
    _local.trace = None
    if error:
        step_into(trace, "error", error[:1000])
    trace["total_ms"] = round((time.time() - trace["started"]) * 1000)
    trace["status"] = status
    if not trace["answered_by"]:
        trace["answered_by"] = "the AI model" if any(s["kind"] == "model" for s in trace["steps"]) else "nothing (no reply)" if error else "Jarvis"
    if reply:
        trace["reply"] = reply[:2000]
    out = {k: v for k, v in trace.items() if k != "started"}
    with LOCK:
        RECENT.appendleft(out)
    return out


def step_into(trace: dict, kind: str, text: str, detail: str | None = None) -> None:
    entry = {"ms": round((time.time() - trace["started"]) * 1000), "kind": kind, "text": str(text)[:1000]}
    if detail:
        entry["detail"] = str(detail)[:MAX_DETAIL]
    trace["steps"].append(entry)


def recent() -> list[dict]:
    with LOCK:
        return list(RECENT)


def clear() -> None:
    with LOCK:
        RECENT.clear()


def short(value, n: int = 300) -> str:
    text = value if isinstance(value, str) else repr(value)
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def traced(name: str, fn):
    """A matcher (a built-in command check) that records when it catches the message."""
    def wrapper(*args, **kwargs):
        result = fn(*args, **kwargs)
        if result and active() is not None:
            step("command", f"Caught by {name}", short(result, 4000))
            answered(name)
        return result
    wrapper.__name__ = getattr(fn, "__name__", name)
    wrapper.__wrapped__ = fn
    return wrapper


class ThinkSplitter:
    """Feed the streamed text; get back only what is outside <think>…</think> (or <thinking>…</thinking>).
    The thinking itself collects in .thinking. Tags split across pieces are handled."""
    OPEN = ("<think>", "<thinking>")
    CLOSE = ("</think>", "</thinking>")

    def __init__(self) -> None:
        self.inside = False
        self.buf = ""
        self.thinking: list[str] = []
        self.seen_text = False

    def feed(self, piece: str) -> str:
        self.buf += piece
        out = []
        while self.buf:
            if self.inside:
                ends = [(self.buf.find(c), c) for c in self.CLOSE if self.buf.find(c) >= 0]
                if ends:
                    i, tag = min(ends)
                    self.thinking.append(self.buf[:i])
                    self.buf = self.buf[i + len(tag):]
                    self.inside = False
                    continue
                keep = max((len(c) - 1 for c in self.CLOSE), default=0)
                if len(self.buf) > keep:
                    self.thinking.append(self.buf[:-keep])
                    self.buf = self.buf[-keep:]
                return "".join(out)
            starts = [(self.buf.find(o), o) for o in self.OPEN if self.buf.find(o) >= 0]
            if starts:
                i, tag = min(starts)
                out.append(self.buf[:i])
                self.buf = self.buf[i + len(tag):]
                self.inside = True
                continue
            # a tag may be starting at the end: hold back anything that could be the start of "<think"
            hold = 0
            for o in self.OPEN:
                for k in range(min(len(o) - 1, len(self.buf)), 0, -1):
                    if self.buf.endswith(o[:k]):
                        hold = max(hold, k)
                        break
            out.append(self.buf[: len(self.buf) - hold])
            self.buf = self.buf[len(self.buf) - hold:]
            break
        text = "".join(out)
        if not self.seen_text:
            text = text.lstrip()             # the blank lines after </think> are not part of the answer
        if text:
            self.seen_text = True
        return text

    def flush(self) -> str:
        rest, self.buf = self.buf, ""
        if self.inside:
            self.thinking.append(rest)
            return ""
        return rest if self.seen_text else rest.lstrip()

    def thought(self) -> str:
        return "".join(self.thinking).strip()

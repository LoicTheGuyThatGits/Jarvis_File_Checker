"""The tool-using brain: when no built-in command matched, let the AI model pick one of Jarvis's tools.

This file holds the rules only (no network, no model, no Windows calls) so it can be tested on its own:

  Registry.add(...)                      server.py registers each tool with the function that carries it out
  Registry.gate(text)                    cheap check: could this message be about a tool at all?
  Registry.prompt(remote, now)           the instructions for the model (the tool list and the JSON to answer with)
  parse(reply, registry, message, remote)  the model's answer, checked: known tools, valid arguments, nothing invented
  Registry.handle(text, ask_model, remote, now)  the whole thing; returns {"reply", "decided"} or None

Safety: only tools registered here can run, destructive ones are never registered, anything the model gets wrong
(bad JSON, unknown tool, missing or made-up arguments) falls back to a normal chat answer, and each change
(a task, an event, a note) can be taken back with "undo that" for ten minutes.
"""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime

MAX_STEPS = 3
MAX_MESSAGE = 240           # longer messages are conversation, not a command
UNDO_SECONDS = 600
UNDO_RE = re.compile(r"(?:(?:hey\s+)?jarvis[,.:]?\s+)?(?:please\s+)?(?:undo|revert|take\s+back)\s+(?:that|this|it|the\s+last\s+(?:one|thing|action|change))(?:\s+please)?", re.I)
STOP = set("a an the my me i to of on in at for and or with is are be do it that this please you your can could would will "
           "some any up about from by as so then also just have has had not no yes".split())


def content_words(text: str) -> list[str]:
    return [w for w in re.findall(r"[^\W_]+", str(text).lower()) if len(w) > 2 and w not in STOP]


def grounded(value: str, message: str) -> bool:
    """True when most of the words of an argument really are in what the person wrote (the model did not invent them)."""
    need = content_words(value)
    if not need:
        return bool(str(value).strip())
    have = content_words(message)
    hit = sum(1 for w in need if any(w == h or (len(w) > 3 and len(h) > 3 and (w.startswith(h[:4]) and h.startswith(w[:4]))) for h in have))
    return hit * 2 >= len(need)


class Tool:
    def __init__(self, name, description, params, run, keywords, risk="read", remote=True, example=""):
        self.name, self.description, self.params, self.run = name, description, params, run
        self.keywords = re.compile(keywords, re.I)
        self.risk, self.remote, self.example = risk, remote, example


class Registry:
    def __init__(self) -> None:
        self.tools: dict[str, Tool] = {}
        self.lock = threading.Lock()
        self.last_undo: dict | None = None     # {"at", "label", "undo"}

    def add(self, name: str, description: str, params: dict, run, keywords: str, risk: str = "read", remote: bool = True, example: str = "") -> None:
        """params: {name: {"desc": str, "required": bool, "choices": [..], "free": bool}}. free = words must come from the message.
        run(args: dict) -> str | (str, undo_callable) | None. risk: "read" or "write" (destructive tools are not allowed here)."""
        if not re.fullmatch(r"[a-z][a-z0-9_]{2,30}", name) or name in self.tools:
            raise ValueError("bad or repeated tool name: " + name)
        if risk not in ("read", "write"):
            raise ValueError("only read and write tools can be given to the model")
        self.tools[name] = Tool(name, description, params, run, keywords, risk, remote, example)

    def available(self, remote: bool = False) -> list[Tool]:
        return [t for t in self.tools.values() if t.remote or not remote]

    def gate(self, text: str, remote: bool = False) -> bool:
        t = (text or "").strip()
        if not t or len(t) > MAX_MESSAGE or t.count("\n") > 2:
            return False
        return any(tool.keywords.search(t) for tool in self.available(remote))

    def prompt(self, remote: bool = False, now: datetime | None = None) -> str:
        now = now or datetime.now()
        lines = []
        for tool in self.available(remote):
            args = []
            for key, spec in tool.params.items():
                choice = " One of: " + ", ".join(spec["choices"]) + "." if spec.get("choices") else ""
                args.append(f'    "{key}" ({"required" if spec.get("required") else "optional"}): {spec["desc"]}{choice}')
            lines.append(f"- {tool.name}: {tool.description}" + ("\n" + "\n".join(args) if args else "\n    (no arguments)")
                         + (f"\n    Example: {tool.example}" if tool.example else ""))
        return (
            "You decide whether a message to the assistant Jarvis asks for one of its tools. You do not answer the message.\n"
            f"Now: {now.strftime('%A %d %B %Y, %H:%M')}.\n\nTools:\n" + "\n".join(lines) + "\n\n"
            "Reply with JSON only, in exactly this shape:\n"
            '{"steps": [{"tool": "<tool name>", "args": {"<argument>": "<value>"}}]}\n\n'
            "Rules:\n"
            '- If the message is a general question, an opinion, small talk, or anything no tool does, reply {"steps": []}. When unsure, reply {"steps": []}.\n'
            "- Use a tool only when the person wants that thing done or looked up for themselves now. A tool with no arguments is the right answer whenever the message asks for what it reports, however it is worded.\n"
            "- Questions about the world in general, other places, other people, the past, or how something works are not for tools.\n"
            "- Copy argument values from the message in the person's own words. Never invent names, tasks or times.\n"
            '- For times and dates copy the words as written ("tomorrow at 5pm", "the 20th", "in 2 hours"). Do not work out dates yourself.\n'
            f"- Usually one step. At most {MAX_STEPS}, only when the message asks for several things.\n"
            "- All argument values are text."
        )

    def decide(self, text: str, ask_model, remote: bool = False, now: datetime | None = None) -> list[dict] | None:
        """Which tools the model picks for this message, checked, without running anything. None or [] means: just chat."""
        if not self.gate(text, remote):
            return None
        try:
            raw = ask_model(self.prompt(remote, now), text.strip())
        except Exception:
            return None
        return parse(raw, self, text, remote)

    # ---- carrying it out ----
    def handle(self, text: str, ask_model, remote: bool = False, now: datetime | None = None) -> dict | None:
        """ask_model(system, user) -> the model's reply text. Returns {"reply", "decided"} or None (answer as normal chat)."""
        steps = self.decide(text, ask_model, remote, now)
        if not steps:
            return None
        replies, decided, undos = [], [], []
        for step in steps:
            tool = self.tools[step["tool"]]
            try:
                out = tool.run(step["args"])
            except ValueError as exc:
                out = str(exc)
            except Exception:
                out = None
            undo = None
            if isinstance(out, tuple):
                out, undo = out
            if not out:
                if not replies:
                    return None           # the first tool could not do it: let the chat model answer instead
                break
            replies.append(str(out))
            decided.append({"tool": tool.name, "args": step["args"]})
            if undo:
                undos.append(undo)
        with self.lock:
            if undos:
                self.last_undo = {"at": time.time(), "undo": undos, "label": ", ".join(d["tool"].replace("_", " ") for d in decided)}
            elif any(self.tools[d["tool"]].risk == "write" for d in decided):
                self.last_undo = None
        return {"reply": "\n\n".join(replies), "decided": decided}

    def undo_command(self, text: str) -> str | None:
        """'undo that' after the model changed something. None when the message is not an undo request or there is nothing to undo."""
        if not UNDO_RE.fullmatch((text or "").strip().rstrip(".!? ")):
            return None
        with self.lock:
            last, self.last_undo = self.last_undo, None
        if not last or time.time() - last["at"] > UNDO_SECONDS:
            return None
        done = 0
        for undo in reversed(last["undo"]):
            try:
                done += 1 if undo() is not False else 0
            except Exception:
                pass
        return "Undone, sir." if done else "I could not undo that, sir. It may have changed since."


def extract_json(reply: str):
    """The first JSON object in the model's answer (models like to wrap it in ``` or add a sentence)."""
    text = str(reply or "")
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    start = text.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                esc = (ch == "\\") and not esc
                if ch == '"' and not esc:
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except ValueError:
                        break
        start = text.find("{", start + 1)
    return None


def parse(reply: str, registry: Registry, message: str, remote: bool = False) -> list[dict] | None:
    """The checked plan, [] for 'no tool', or None when the answer cannot be trusted. Any doubt means None."""
    data = extract_json(reply)
    if not isinstance(data, dict):
        return None
    steps = data.get("steps")
    if steps is None and isinstance(data.get("tool"), str):      # a single step without the wrapper
        steps = [data]
    if not isinstance(steps, list) or len(steps) > MAX_STEPS:
        return None
    allowed = {t.name: t for t in registry.available(remote)}
    plan = []
    for step in steps:
        if not isinstance(step, dict) or step.get("tool") in (None, "", "none"):
            return None if steps and len(steps) > 1 else []
        tool = allowed.get(str(step.get("tool")))
        raw = step.get("args", step.get("arguments", {}))
        if tool is None or not isinstance(raw, dict):
            return None
        args = {}
        for key, spec in tool.params.items():
            value = raw.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                value = str(int(value)) if float(value).is_integer() else str(value)
            value = re.sub(r"\s+", " ", value).strip()[:300] if isinstance(value, str) else ""
            if not value:
                if spec.get("required"):
                    return None
                continue
            if spec.get("choices"):
                match = next((c for c in spec["choices"] if c.lower() == value.lower()), None)
                if match is None:
                    if spec.get("required"):
                        return None
                    continue
                value = match
            elif spec.get("free", True) and not grounded(value, message):
                return None                                     # the model made it up
            args[key] = value
        if not tool.keywords.search(message):
            return None                                         # nothing in the message points at this tool
        plan.append({"tool": tool.name, "args": args})
    return plan

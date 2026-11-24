"""Teaching Autopilot by showing it: you do a task once while Jarvis watches your clicks and typing, and the steps become
a way Autopilot follows the next time you ask for that task (procedures.py, “What Autopilot learned”).

What is kept: where you clicked (the button or box under the mouse, by its name, and the window), what you typed, the keys
and shortcuts you pressed, and the windows you switched to. Typing into a password box, or in a window about passwords
or private browsing, is never kept (it becomes “type your password”). Recording stops with Ctrl+Shift+F9, “stop
recording”, the Stop button in Settings, or by itself after 10 minutes.

    Recorder(task, ctx)   .click(x, y, button, double) .key(name, char, mods) .scroll(dy) .steps() .done
ctx: {"front": () -> (title, app), "element_at": (x, y) -> {"name", "kind"} | None}
"""
from __future__ import annotations

import re
import threading
import time

MAX_SECONDS = 600
MAX_STEPS = 60
SECRET = re.compile(r"password|passcode|mot de passe|passwort|kennwort|\bpin\b|\bcode\b|secret|login|sign in|connexion|anmelden|"
                    r"inprivate|incognito|private browsing|navigation privée|keepass|bitwarden|1password|lastpass", re.I)
NAMED = {"enter": "Enter", "return": "Enter", "tab": "Tab", "esc": "Esc", "escape": "Esc", "backspace": "Backspace", "delete": "Delete",
         "up": "Up", "down": "Down", "left": "Left", "right": "Right", "page_up": "Page Up", "page_down": "Page Down", "home": "Home", "end": "End",
         "f1": "F1", "f2": "F2", "f3": "F3", "f4": "F4", "f5": "F5", "f6": "F6", "f7": "F7", "f8": "F8", "f10": "F10", "f11": "F11", "f12": "F12", "space": "Space"}


class Recorder:
    def __init__(self, task: str, ctx: dict, now=time.time):
        self.task = " ".join((task or "").split())[:200]
        self.ctx, self.now = ctx, now
        self.started = now()
        self.items: list[dict] = []
        self.typing: dict | None = None
        self.last_window = None
        self.secret_until = 0.0
        self.done = False
        self.lock = threading.Lock()

    # ---- what happens ----
    def _window(self) -> tuple[str, str]:
        try:
            title, app = self.ctx["front"]()
        except Exception:
            title, app = "", ""
        return title or "", app or ""

    def _note_window(self) -> tuple[str, str]:
        title, app = self._window()
        if title and title != self.last_window:
            if self.last_window is not None:
                self._flush()
                self._add({"type": "window", "title": title, "app": app})
            self.last_window = title
        return title, app

    def _add(self, item: dict) -> None:
        if len(self.items) < MAX_STEPS:
            self.items.append(item)

    def _flush(self) -> None:
        if self.typing:
            t = self.typing
            self.typing = None
            if t["secret"]:
                self._add({"type": "type", "secret": True, "where": t["where"]})
            elif t["text"].strip():
                self._add({"type": "type", "text": t["text"], "where": t["where"]})

    def _timeout(self) -> bool:
        if self.now() - self.started > MAX_SECONDS:
            self.done = True
        return self.done

    def click(self, x: int, y: int, button: str = "left", double: bool = False) -> None:
        with self.lock:
            if self._timeout():
                return
            title, app = self._note_window()
            self._flush()
            el = None
            try:
                el = self.ctx["element_at"](x, y)
            except Exception:
                el = None
            if double and self.items and self.items[-1]["type"] == "click" and self.items[-1].get("x") == x and self.items[-1].get("y") == y:
                self.items[-1]["double"] = True
                return
            item = {"type": "click", "button": button, "double": double, "x": x, "y": y, "window": title,
                    "name": (el or {}).get("name", "")[:80], "kind": (el or {}).get("kind", "")}
            if SECRET.search(item["name"]) or SECRET.search(title):
                self.secret_until = self.now() + 120           # what is typed next goes into a password box
            self._add(item)

    def key(self, name: str = "", char: str = "", mods: tuple = ()) -> bool:
        """Returns True when it was the stop shortcut (Ctrl+Shift+F9)."""
        with self.lock:
            mods = tuple(m for m in mods if m in ("ctrl", "alt", "shift", "win"))
            if name == "f9" and "ctrl" in mods and "shift" in mods:
                self._flush()
                self.done = True
                return True
            if self._timeout():
                return False
            title, _ = self._note_window()
            secret = bool(SECRET.search(title)) or self.now() < self.secret_until
            if char and not (set(mods) - {"shift"}):
                if not self.typing:
                    self.typing = {"text": "", "secret": False, "where": title}
                self.typing["secret"] = self.typing["secret"] or secret
                if not self.typing["secret"]:
                    self.typing["text"] += char
                return False
            if name == "backspace" and self.typing and not self.typing["secret"]:
                self.typing["text"] = self.typing["text"][:-1]
                return False
            if name in ("shift", "ctrl", "alt", "win", "") and not char:
                return False
            self._flush()
            label = NAMED.get(name, (char or name).upper() if len(char or name) == 1 else name.capitalize())
            names = [{"ctrl": "Ctrl", "alt": "Alt", "win": "Win"}[m] for m in mods if m != "shift"]
            if "shift" in mods and (names or len(label) > 1):
                names.append("Shift")
            combo = "+".join(names + [label])
            if secret and name in ("enter", "return", "tab"):
                self.secret_until = 0                          # the password is done
            self._add({"type": "key", "combo": combo, "window": title})
            return False

    def scroll(self, dy: int) -> None:
        with self.lock:
            if self._timeout():
                return
            title, _ = self._note_window()
            self._flush()
            way = "down" if dy < 0 else "up"
            if self.items and self.items[-1]["type"] == "scroll" and self.items[-1]["way"] == way:
                self.items[-1]["times"] += 1
                return
            self._add({"type": "scroll", "way": way, "times": 1, "window": title})

    def finish(self) -> list[str]:
        with self.lock:
            self._flush()
            self.done = True
        return self.steps()

    # ---- in words, for Autopilot ----
    def steps(self) -> list[str]:
        out = []
        for i in self.items:
            if i["type"] == "window":
                out.append(f"Switch to the window “{i['title'][:80]}”" + (f" ({i['app']})" if i.get("app") else ""))
            elif i["type"] == "click":
                verb = "Double-click" if i.get("double") else "Right-click" if i.get("button") == "right" else "Click"
                what = f"“{i['name']}”" + (f" ({i['kind']})" if i.get("kind") else "") if i.get("name") else "the spot at about the same place on the screen"
                out.append(f"{verb} {what}" + (f" in “{i['window'][:60]}”" if i.get("window") else ""))
            elif i["type"] == "type":
                out.append("Type the user's password (not recorded: ask the user to type it)" if i.get("secret") else f"Type “{i['text'][:200]}”")
            elif i["type"] == "key":
                out.append(f"Press {i['combo']}")
            elif i["type"] == "scroll":
                out.append(f"Scroll {i['way']}" + (f" ({i['times']} times)" if i["times"] > 1 else "") + (f" in “{i['window'][:60]}”" if i.get("window") else ""))
        return out


START = re.compile(r"(?:(?:hey\s+)?jarvis[,.:]?\s+)?(?:please\s+)?(?:watch\s+me(?:\s+while\s+i|\s+as\s+i)?|let\s+me\s+show\s+you(?:\s+how)?|i(?:'ll|\s+will)\s+show\s+you(?:\s+how)?|"
                   r"learn\s+(?:this|how)\s+from\s+me(?:\s*:)?|record\s+(?:me|what\s+i\s+do)(?:\s+while\s+i)?)\s*:?\s*(?:to\s+|how\s+to\s+|do\s+|doing\s+)?(?P<task>.{3,180}?)[.!]?", re.I)
STOP = re.compile(r"(?:(?:hey\s+)?jarvis[,.:]?\s+)?(?:stop\s+(?:the\s+)?recording|i'?m\s+done(?:\s+showing\s+you)?|that'?s\s+(?:it|all)|done\s+showing\s+you|finished\s+showing\s+you|"
                  r"cancel\s+(?:the\s+)?recording)[.!]?", re.I)

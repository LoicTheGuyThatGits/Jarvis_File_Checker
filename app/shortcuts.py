"""Global shortcuts for Jarvis (Windows): hold-to-talk dictation into any app, and quick actions on the selected text.

The keyboard, microphone, clipboard and typing are passed in by the server, so this file only holds the logic.
Dictation: hold the key, speak, let go; Jarvis types what you said where the cursor is. Speech is recognised locally.
Quick actions: press the key with text selected (or copied); Jarvis opens a small panel to summarise, translate, fix or explain it.
Quick ask: press the key anywhere and a small Jarvis box opens over the app you are in (on by default).
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

try:
    import numpy as np
except ImportError:
    np = None

RATE = 16000
HOLD_DELAY = 0.4                    # the key must be held this long before dictation starts, so normal shortcuts (Ctrl+C) never trigger it
MAX_RECORD = 90.0
MIN_AUDIO = 0.4
DICTATION_KEYS = {"ctrl+alt+d": (0x11, 0x12, 0x44), "right ctrl": (0xA3,), "f9": (0x78,), "f8": (0x77,)}
QUICK_KEYS = {"ctrl+alt+q": (0x11, 0x12, 0x51), "ctrl+alt+e": (0x11, 0x12, 0x45), "f10": (0x79,)}
ASK_KEYS = {"ctrl+alt+space": (0x11, 0x12, 0x20), "ctrl+shift+space": (0x11, 0x10, 0x20), "ctrl+alt+a": (0x11, 0x12, 0x41)}
KEY_LABELS = {"ctrl+alt+d": "Ctrl+Alt+D", "right ctrl": "Right Ctrl", "f9": "F9", "f8": "F8", "ctrl+alt+q": "Ctrl+Alt+Q", "ctrl+alt+e": "Ctrl+Alt+E", "f10": "F10",
              "ctrl+alt+space": "Ctrl+Alt+Space", "ctrl+shift+space": "Ctrl+Shift+Space", "ctrl+alt+a": "Ctrl+Alt+A"}
SECTIONS = (("dictation", DICTATION_KEYS), ("quick", QUICK_KEYS), ("ask", ASK_KEYS))
MODIFIERS = (0x10, 0x11, 0x12, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5)
SPOKEN_COMMANDS = ((re.compile(r"\b(?:new paragraph)\b[.,]?\s*", re.I), "\n\n"), (re.compile(r"\b(?:new line|next line)\b[.,]?\s*", re.I), "\n"))
HALLUCINATIONS = {"thank you", "thanks", "thanks for watching", "you", "bye", "uh", "um", "hmm"}


def load(path: Path) -> dict:
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cfg = {}
    return cfg if isinstance(cfg, dict) else {}


def clean_dictation(text: str) -> str:
    text = (text or "").strip()
    if re.sub(r"[^a-z ]", "", text.lower()).strip() in HALLUCINATIONS:
        return ""
    for pattern, replacement in SPOKEN_COMMANDS:
        text = pattern.sub(replacement, text)
    text = re.sub(r"[ \t]+\n", "\n", text)                # no trailing space before a line break
    return text.strip(" ") if text.strip() else ""


class Shortcuts:
    def __init__(self, config_path: Path, *, key_down, open_mic, transcribe, type_text, beep, capture_selection, quick_ready, pause_listener=lambda on: None, device=lambda: None, ask_open=lambda: None):
        self.config_path = config_path
        self.key_down, self.open_mic, self.transcribe, self.type_text, self.beep = key_down, open_mic, transcribe, type_text, beep
        self.capture_selection, self.quick_ready, self.pause_listener, self.device = capture_selection, quick_ready, pause_listener, device
        self.ask_open = ask_open
        self.state, self.error = "off", ""
        self.recent: list[dict] = []
        self.stop_flag = threading.Event()
        self.thread: threading.Thread | None = None

    # ---- settings ----
    def config(self) -> dict:
        try:
            stamp = self.config_path.stat().st_mtime_ns
        except OSError:
            stamp = None
        cached = getattr(self, "_cached", None)
        if cached and cached[0] == stamp and stamp is not None:   # the loop asks 50 times a second; read the file only when it changed
            return json.loads(cached[1])
        out = self._read_config()
        self._cached = (stamp, json.dumps(out))
        return out

    def _read_config(self) -> dict:
        cfg = load(self.config_path)
        dictation = cfg.get("dictation") if isinstance(cfg.get("dictation"), dict) else {}
        quick = cfg.get("quick") if isinstance(cfg.get("quick"), dict) else {}
        ask = cfg.get("ask") if isinstance(cfg.get("ask"), dict) else {}
        return {"dictation": {"enabled": dictation.get("enabled") is True, "key": dictation.get("key") if dictation.get("key") in DICTATION_KEYS else "ctrl+alt+d"},
                "quick": {"enabled": quick.get("enabled") is True, "key": quick.get("key") if quick.get("key") in QUICK_KEYS else "ctrl+alt+q"},
                "ask": {"enabled": ask.get("enabled") is not False, "key": ask.get("key") if ask.get("key") in ASK_KEYS else "ctrl+alt+space"}}

    def public(self) -> dict:
        cfg = self.config()
        return {**cfg, "state": self.state, "error": self.error, "recent": self.recent[-5:],
                "dictation_keys": {k: KEY_LABELS[k] for k in DICTATION_KEYS}, "quick_keys": {k: KEY_LABELS[k] for k in QUICK_KEYS},
                "ask_keys": {k: KEY_LABELS[k] for k in ASK_KEYS}}

    def update(self, payload: dict) -> dict:
        cfg = self.config()
        for section, keys in SECTIONS:
            part = payload.get(section)
            if not isinstance(part, dict):
                continue
            if "key" in part:
                if part["key"] not in keys:
                    raise ValueError("That shortcut is not one of the choices.")
                cfg[section]["key"] = part["key"]
            if "enabled" in part:
                cfg[section]["enabled"] = part["enabled"] is True
        if cfg["dictation"]["enabled"] and cfg["quick"]["enabled"] and set(DICTATION_KEYS[cfg["dictation"]["key"]]) & set(QUICK_KEYS[cfg["quick"]["key"]]) == set(DICTATION_KEYS[cfg["dictation"]["key"]]):
            raise ValueError("Dictation and quick actions cannot use the same shortcut.")
        if cfg["dictation"]["enabled"] and cfg["ask"]["enabled"] and set(DICTATION_KEYS[cfg["dictation"]["key"]]) <= set(ASK_KEYS[cfg["ask"]["key"]]):
            raise ValueError("Dictation and quick ask cannot use the same keys.")
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        self._cached = None
        self.sync()
        return self.public()

    # ---- lifecycle ----
    def sync(self) -> None:
        cfg = self.config()
        wanted = cfg["dictation"]["enabled"] or cfg["quick"]["enabled"] or cfg["ask"]["enabled"]
        alive = self.thread is not None and self.thread.is_alive()
        if wanted and not alive:
            if np is None and cfg["dictation"]["enabled"]:
                self.state, self.error = "error", "Dictation needs the numpy package. Run install-jarvis.bat again."
                return
            self.stop_flag.clear()
            self.state, self.error = "ready", ""
            self.thread = threading.Thread(target=self.run, name="jarvis-shortcuts", daemon=True)
            self.thread.start()
        elif not wanted and alive:
            self.stop()
        elif not wanted:
            self.state = "off"

    def stop(self) -> None:
        self.stop_flag.set()
        if self.thread and self.thread.is_alive() and self.thread is not threading.current_thread():
            self.thread.join(timeout=5)
        self.thread, self.state = None, "off"

    def combo_down(self, combo) -> bool:
        return all(self.key_down(vk) for vk in combo)

    def run(self) -> None:
        held_since: float | None = None
        quick_was = ask_was = False
        while not self.stop_flag.is_set():
            time.sleep(0.02)
            cfg = self.config()
            try:
                if cfg["ask"]["enabled"]:
                    down = self.combo_down(ASK_KEYS[cfg["ask"]["key"]])
                    if down and not ask_was:
                        self.ask()
                    ask_was = down
                if cfg["quick"]["enabled"]:
                    down = self.combo_down(QUICK_KEYS[cfg["quick"]["key"]])
                    if down and not quick_was:
                        self.quick()
                    quick_was = down
                if cfg["dictation"]["enabled"]:
                    combo = DICTATION_KEYS[cfg["dictation"]["key"]]
                    if self.combo_down(combo):
                        held_since = held_since or time.time()
                        others = any(self.key_down(v) for v in range(0x30, 0x5B) if v not in combo)
                        if others:
                            held_since = time.time() + 9999                # another key joined: this is a normal shortcut, not dictation
                        elif time.time() - held_since >= HOLD_DELAY:
                            self.dictate(combo)
                            held_since = None
                    else:
                        held_since = None
            except Exception as exc:
                print(f"[jarvis] shortcuts: {type(exc).__name__}: {exc}")
                self.state = "ready"

    # ---- actions ----
    def ask(self) -> None:
        try:
            self.ask_open()
        except Exception as exc:
            self.error = f"The quick-ask window did not open: {exc}"
            print(f"[jarvis] quick ask: {type(exc).__name__}: {exc}")

    def quick(self) -> None:
        self.state = "quick"
        try:
            for _ in range(100):                            # wait for the modifier keys to be let go, or Ctrl+C would arrive as Ctrl+Alt+C
                if not any(self.key_down(v) for v in MODIFIERS):
                    break
                time.sleep(0.02)
            text = (self.capture_selection() or "").strip()
            if text:
                self.quick_ready(text[:8000])
            else:
                self.beep("sleep")
        finally:
            self.state = "ready"

    def dictate(self, combo) -> None:
        self.state = "recording"
        self.pause_listener(True)
        frames: list = []
        mic = None
        try:
            mic = self.open_mic(self.device())
            self.beep("wake")
            started = time.time()
            while self.combo_down(combo) and time.time() - started < MAX_RECORD and not self.stop_flag.is_set():
                frame = mic.read(0.1)
                if frame is not None:
                    frames.append(frame)
        except Exception as exc:
            self.state, self.error = "ready", f"I could not use the microphone: {exc}"
            return
        finally:
            if mic:
                try:
                    mic.close()
                except Exception:
                    pass
            self.pause_listener(False)
        self.state = "typing"
        try:
            if not frames:
                return
            audio = np.concatenate([f.astype(np.float32) / 32768.0 for f in frames])
            if len(audio) < MIN_AUDIO * RATE:
                return
            self.beep("sleep")
            text = clean_dictation(self.transcribe(audio, False))
            if text:
                self.type_text(text + ("" if text.endswith("\n") else " "))
                self.recent.append({"time": time.strftime("%H:%M"), "text": text[:200]})
                del self.recent[:-20]
                self.error = ""
        except Exception as exc:
            self.error = str(exc)[:300]
        finally:
            self.state = "ready"


SHORTCUTS: Shortcuts | None = None

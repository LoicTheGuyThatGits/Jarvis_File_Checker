"""Calls: talking with Jarvis out loud, hands-free, like a phone call.

Two directions:
  you call Jarvis      place(device)            the call starts at once; Jarvis says hello and listens
  Jarvis calls you     ring(reason, opening)    the Jarvis window (and the phone app) ring; answer(id) starts the call,
                                                 and Jarvis speaks `opening` first. Nobody answers in time (or you decline):
                                                 on_missed(call) runs, so the server can send the message to Telegram.

The talking itself happens in the page (speech recognition, the chat, the voice); this keeps the state every device
agrees on: what is ringing, who answered, when it ended. Phones that cannot keep a page open wait with wait(),
a long poll that returns as soon as something rings.

Settings live in data/calls.json: on (Jarvis may call you), ring_pc, ring_phone, telegram_fallback, ring_seconds.
"""
from __future__ import annotations

import json
import secrets
import threading
import time
from pathlib import Path

DEFAULTS = {"on": True, "ring_pc": True, "ring_phone": True, "telegram_fallback": True, "ring_seconds": 40}
SILENT_AFTER = 150          # an active call whose page stopped sending heartbeats for this long has ended
HISTORY = 30


class CallError(Exception):
    pass


class Calls:
    def __init__(self, path: Path, clock=time.time) -> None:
        self.path = Path(path)
        self.clock = clock
        self.cond = threading.Condition()
        self.calls: dict[str, dict] = {}
        self.history: list[dict] = []
        self.version = 0
        self.boot = secrets.token_hex(4)       # changes when Jarvis restarts, so a phone knows its "since" is stale
        self.waiting = 0                       # phones waiting in wait() right now
        self.publish = lambda event: None     # set by the server: sends an event to open pages and the phone app
        self.on_missed = lambda call: None     # set by the server: the Telegram fallback

    # ---------- settings ----------
    def settings(self) -> dict:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        out = dict(DEFAULTS)
        if isinstance(raw, dict):
            for key, default in DEFAULTS.items():
                value = raw.get(key)
                if isinstance(default, bool) and isinstance(value, bool):
                    out[key] = value
                elif not isinstance(default, bool) and isinstance(value, int) and not isinstance(value, bool):
                    out[key] = value
        out["ring_seconds"] = max(15, min(90, int(out["ring_seconds"])))
        return out

    def update(self, changes: dict) -> dict:
        cfg = self.settings()
        for key in ("on", "ring_pc", "ring_phone", "telegram_fallback"):
            if key in changes:
                if not isinstance(changes[key], bool):
                    raise ValueError(f"{key} must be true or false.")
                cfg[key] = changes[key]
        if "ring_seconds" in changes:
            try:
                seconds = int(changes["ring_seconds"])
            except (TypeError, ValueError):
                raise ValueError("The ringing time must be a number of seconds.")
            if not 15 <= seconds <= 90:
                raise ValueError("Let it ring between 15 and 90 seconds.")
            cfg["ring_seconds"] = seconds
        if not cfg["ring_pc"] and not cfg["ring_phone"]:
            raise ValueError("Choose at least one place to ring: this PC or the phone.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        return cfg

    # ---------- state ----------
    @staticmethod
    def public(call: dict) -> dict:
        return {k: v for k, v in call.items() if not k.startswith("_")}

    def current(self) -> list[dict]:
        with self.cond:
            return [self.public(c) for c in self.calls.values() if c["state"] in ("ringing", "active")]

    def recent(self) -> list[dict]:
        with self.cond:
            return [self.public(c) for c in self.history]

    def get(self, call_id: str) -> dict:
        with self.cond:
            call = self.calls.get(str(call_id))
            if not call:
                raise CallError("That call has already ended.")
            return self.public(call)

    def _changed(self, call: dict, extra: dict | None = None) -> None:
        self.version += 1
        self.cond.notify_all()
        event = {"type": "call", **self.public(call), **(extra or {})}
        try:
            self.publish(event)
        except Exception:
            pass

    def _finish(self, call: dict, state: str) -> None:
        call["state"] = state
        call["ended"] = self.clock()
        if call.get("answered"):
            call["seconds"] = round(call["ended"] - call["answered"])
        self.calls.pop(call["id"], None)
        self.history.insert(0, dict(call))
        del self.history[HISTORY:]

    # ---------- you call Jarvis ----------
    def place(self, device: str) -> dict:
        now = self.clock()
        with self.cond:
            for call in list(self.calls.values()):         # one call at a time: a new one replaces an old one left open
                if call["state"] == "active":
                    self._finish(call, "ended")
                    self._changed(call)
            call = {"id": secrets.token_hex(5), "direction": "to_jarvis", "state": "active", "device": device, "created": now, "answered": now,
                    "seen": now, "reason": "", "opening": ""}
            self.calls[call["id"]] = call
            self._changed(call)
            return self.public(call)

    # ---------- Jarvis calls you ----------
    def ring(self, reason: str, opening: str, targets: list[str] | None = None) -> dict:
        """Ring the devices. When you are already on a call, Jarvis says it there instead (state stays "active", "said" is set)."""
        cfg = self.settings()
        if not cfg["on"]:
            raise CallError("Calls from Jarvis are switched off in Settings > Phone & Telegram > Calls.")
        targets = [t for t in (targets or ["pc", "phone"]) if (t == "pc" and cfg["ring_pc"]) or (t == "phone" and cfg["ring_phone"])]
        if not targets:
            raise CallError("Jarvis is not allowed to ring any device. Turn on the PC or the phone in Settings > Phone & Telegram > Calls.")
        now = self.clock()
        with self.cond:
            busy = next((c for c in self.calls.values() if c["state"] == "active"), None)
            if busy:
                self._changed(busy, {"say": opening})
                return {**self.public(busy), "said": opening}
            for call in list(self.calls.values()):          # a newer ring replaces one still ringing
                if call["state"] == "ringing":
                    self._finish(call, "replaced")
                    self._changed(call)
            call = {"id": secrets.token_hex(5), "direction": "to_you", "state": "ringing", "targets": targets, "created": now,
                    "ring_until": now + cfg["ring_seconds"], "reason": str(reason)[:200], "opening": str(opening)[:1500], "device": ""}
            self.calls[call["id"]] = call
            self._changed(call)
            return self.public(call)

    def answer(self, call_id: str, device: str) -> dict:
        with self.cond:
            call = self.calls.get(str(call_id))
            if not call:
                raise CallError("That call has already ended.")
            if call["state"] != "ringing":
                if call.get("device") == device:
                    return self.public(call)
                raise CallError("That call was already answered on the " + ("phone" if call.get("device") == "phone" else "PC") + ".")
            now = self.clock()
            call.update(state="active", device=device, answered=now, seen=now)
            self._changed(call)
            return self.public(call)

    def decline(self, call_id: str, device: str = "") -> dict:
        with self.cond:
            call = self.calls.get(str(call_id))
            if not call or call["state"] != "ringing":
                raise CallError("That call is not ringing any more.")
            call["device"] = device
            self._finish(call, "declined")
            self._changed(call)
            done = dict(call)
        self._missed(done)
        return self.public(done)

    def hangup(self, call_id: str) -> dict:
        with self.cond:
            call = self.calls.get(str(call_id))
            if not call:
                raise CallError("That call has already ended.")
            ringing = call["state"] == "ringing"
            self._finish(call, "cancelled" if ringing else "ended")
            self._changed(call)
            return self.public(call)

    def heartbeat(self, call_id: str) -> dict:
        with self.cond:
            call = self.calls.get(str(call_id))
            if not call:
                raise CallError("That call has already ended.")
            call["seen"] = self.clock()
            return self.public(call)

    def tick(self, now: float | None = None) -> list[dict]:
        """Ringing too long → missed; an active call nobody is on any more → ended. Returns the calls that just ended."""
        now = self.clock() if now is None else now
        ended, missed = [], []
        with self.cond:
            for call in list(self.calls.values()):
                if call["state"] == "ringing" and now >= call["ring_until"]:
                    self._finish(call, "missed")
                    self._changed(call)
                    missed.append(dict(call))
                elif call["state"] == "active" and now - call.get("seen", now) > SILENT_AFTER:
                    self._finish(call, "ended")
                    self._changed(call)
                    ended.append(dict(call))
        for call in missed:
            self._missed(call)
        return missed + ended

    def _missed(self, call: dict) -> None:
        if call.get("direction") == "to_you" and self.settings()["telegram_fallback"]:
            try:
                self.on_missed(call)
            except Exception:
                pass

    # ---------- the phone's long poll ----------
    def wait(self, since: int, timeout: float = 50.0) -> dict:
        """Returns at once when the state changed after `since`, otherwise when something changes or after `timeout`."""
        deadline = time.time() + max(0.0, min(timeout, 120.0))
        with self.cond:
            self.waiting += 1
            try:
                while self.version == since:            # a "since" from before a restart (bigger or smaller) returns at once
                    left = deadline - time.time()
                    if left <= 0:
                        break
                    self.cond.wait(left)
                return {"version": self.version, "boot": self.boot, "ring_seconds": self.settings()["ring_seconds"], "calls": [self.public(c) for c in self.calls.values() if c["state"] in ("ringing", "active")]}
            finally:
                self.waiting -= 1


def opening_for(text: str, now_struct=None, address: str = "sir") -> str:
    """What Jarvis says first when it calls you for a reminder or an alarm."""
    now_struct = now_struct or time.localtime()
    clock = time.strftime("%H:%M", now_struct)
    t = (text or "").strip().rstrip(".")
    if not t or t.lower() in ("reminder", "call", "call me"):
        return f"Hello, {address}. You asked me to call you at {clock}. What can I do for you?"
    if t.lower() in ("wake up", "alarm", "wake me up"):
        part = "morning" if now_struct.tm_hour < 12 else "afternoon" if now_struct.tm_hour < 18 else "evening"
        return f"Good {part}, {address}. It is {clock}, time to wake up."
    return f"Hello, {address}. You asked me to call you: {t}."

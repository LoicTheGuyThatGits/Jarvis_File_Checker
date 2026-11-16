"""Focus timer: a block of work followed by a short break, with the minutes kept so the day can be added up.

    Focus(path).start(minutes, label, now)   "focus for 25 minutes on maths"
    .tick(now)        -> messages to show when the work block or the break ends
    .quiet(now)       -> True while a work block runs (Jarvis holds back its own messages)
    .totals(now)      -> minutes and sessions today and this week
    .command(text, now)
"""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_MINUTES, DEFAULT_BREAK = 25, 5
KEEP = 2000
DURATION = re.compile(r"(\d{1,3})\s*(?:-\s*)?(hours?|hrs?|h|minutes?|mins?|m)\b(?:\s*(?:and\s+)?(\d{1,2})\s*(?:minutes?|mins?|m)?\b)?|(an?|one|half\s+an?)\s+(hour)(?:\s+and\s+a\s+half)?", re.I)


def minutes_of(text: str) -> int | None:
    m = DURATION.search(text or "")
    if not m:
        return None
    if m.group(4):
        whole = m.group(0).lower()
        return 30 if whole.startswith("half") else 90 if "and a half" in whole else 60
    n = int(m.group(1))
    if m.group(2).lower().startswith("h"):
        return n * 60 + int(m.group(3) or 0)
    return n


def span(minutes: int) -> str:
    h, m = divmod(int(minutes), 60)
    return (f"{h} h {m:02d}" if m else f"{h} h") if h else f"{m} min"


class Focus:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock = threading.Lock()

    def load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data = data if isinstance(data, dict) else {}
        if not isinstance(data.get("log"), list):
            data["log"] = []
        if not isinstance(data.get("active"), dict):
            data["active"] = None
        return data

    def save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    # ---- the session ----
    def start(self, minutes: int | None = None, label: str = "", now: float | None = None, rest: int | None = None) -> str:
        now = time.time() if now is None else now
        minutes = DEFAULT_MINUTES if not minutes else int(minutes)
        if not 1 <= minutes <= 240:
            raise ValueError("A focus session can last from 1 minute to 4 hours, sir.")
        rest = (DEFAULT_BREAK if minutes < 50 else 10) if rest is None else max(0, min(60, int(rest)))
        label = re.sub(r"\s+", " ", label or "").strip(" .,")[:60]
        with self.lock:
            data = self.load()
            replaced = data["active"] and data["active"].get("phase") == "work"
            if replaced:
                self._log(data, now)
            data["active"] = {"phase": "work", "start": now, "ends": now + minutes * 60, "minutes": minutes, "break": rest, "label": label}
            self.save(data)
        until = datetime.fromtimestamp(now + minutes * 60).strftime("%H:%M")
        return (f"Focus session started, sir: {span(minutes)}" + (f" on {label}" if label else "") + f", until {until}. "
                + (f"Then a {rest} minute break. " if rest else "") + "I will keep quiet until then. Say “stop focus” to end it early.")

    def _log(self, data: dict, now: float) -> int:
        a = data["active"]
        done = int(min(now, a["ends"]) - a["start"]) // 60
        if done >= 1:
            data["log"].append({"at": a["start"], "minutes": done, "label": a.get("label", "")})
            data["log"] = data["log"][-KEEP:]
        return done

    def stop(self, now: float | None = None) -> str:
        now = time.time() if now is None else now
        with self.lock:
            data = self.load()
            a = data["active"]
            if not a:
                return "There is no focus session running, sir."
            done = self._log(data, now) if a["phase"] == "work" else 0
            data["active"] = None
            self.save(data)
        if a["phase"] == "break":
            return "Break ended, sir."
        return f"Focus session stopped, sir. You did {span(done)}." if done else "Focus session cancelled, sir."

    def tick(self, now: float | None = None) -> list[str]:
        now = time.time() if now is None else now
        with self.lock:
            data = self.load()
            a = data["active"]
            if not a or now < a["ends"]:
                return []
            if a["phase"] == "work":
                done = self._log(data, now)
                total = sum(l["minutes"] for l in data["log"] if l["at"] >= datetime.combine(datetime.fromtimestamp(now).date(), datetime.min.time()).timestamp())
                if a.get("break"):
                    data["active"] = {**a, "phase": "break", "start": a["ends"], "ends": a["ends"] + a["break"] * 60}
                else:
                    data["active"] = None
                self.save(data)
                return [f"Focus session done, sir: {span(done)}" + (f" on {a['label']}" if a.get("label") else "") + f". That makes {span(total)} today. "
                        + (f"Take a {a['break']} minute break." if a.get("break") else "")]
            data["active"] = None
            self.save(data)
            return ["Break over, sir. Say “focus” when you are ready for another session."]

    def quiet(self, now: float | None = None) -> bool:
        a = self.load()["active"]
        return bool(a and a.get("phase") == "work" and (time.time() if now is None else now) < a["ends"])

    def totals(self, now: datetime | None = None) -> dict:
        now = now or datetime.now()
        day0 = datetime.combine(now.date(), datetime.min.time())
        week0 = day0 - timedelta(days=now.weekday())
        log = self.load()["log"]
        today = [l for l in log if l["at"] >= day0.timestamp()]
        week = [l for l in log if l["at"] >= week0.timestamp()]
        return {"today": sum(l["minutes"] for l in today), "today_sessions": len(today), "week": sum(l["minutes"] for l in week), "week_sessions": len(week)}

    def public(self, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        a = self.load()["active"]
        active = {"phase": a["phase"], "label": a.get("label", ""), "minutes": a["minutes"], "left": max(0, int(a["ends"] - now))} if a and now < a["ends"] + 60 else None
        return {"active": active, **self.totals(datetime.fromtimestamp(now))}

    def status_text(self, now: float | None = None) -> str:
        now = time.time() if now is None else now
        a = self.load()["active"]
        if not a or now >= a["ends"]:
            return "There is no focus session running, sir."
        left = max(1, round((a["ends"] - now) / 60))
        return (f"{left} minute{'s' if left != 1 else ''} left in your focus session" + (f" on {a['label']}" if a.get("label") else "") + ", sir."
                if a["phase"] == "work" else f"You are on a break, sir: {left} minute{'s' if left != 1 else ''} left.")

    def stats_text(self, week: bool, now: datetime | None = None) -> str:
        t = self.totals(now)
        minutes, sessions, word = (t["week"], t["week_sessions"], "this week") if week else (t["today"], t["today_sessions"], "today")
        if not minutes:
            return f"No focus sessions {word} yet, sir."
        return f"You have focused for {span(minutes)} {word}, sir, over {sessions} session{'s' if sessions != 1 else ''}."

    # ---- chat ----
    def command(self, text: str, now: float | None = None) -> str | None:
        t = re.sub(r"\s+", " ", (text or "").strip())
        t = re.sub(r"^(?:(?:hey\s+)?jarvis[,.:]?\s+)?(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?)?", "", t, flags=re.I)
        t = re.sub(r"\s*(?:please|for me|now)?\s*[.!?]*$", "", t, flags=re.I).strip()
        if not t or len(t) > 140:
            return None
        low = t.lower()
        word = r"(?:focus(?:ing)?|pomodoro|deep\s+work|concentration|study)"
        if re.fullmatch(rf"(?:stop|end|cancel|quit|finish|exit|leave)\s+(?:the\s+|my\s+|this\s+)?(?:{word}|focus\s+mode)(?:\s+(?:session|timer|mode|block))?|stop\s+focusing", low):
            return self.stop(now)
        if re.fullmatch(rf"how\s+(?:long|much\s+time|many\s+minutes)\s+(?:is\s+|are\s+)?(?:left|remaining|to\s+go)(?:\s+(?:in|on|of)\s+(?:my\s+|the\s+)?{word}(?:\s+(?:session|timer))?)?|{word}\s+status|am\s+i\s+(?:still\s+)?focusing", low):
            return self.status_text(now)
        m = re.fullmatch(rf"(?:how\s+(?:much|long)\s+(?:did|have)\s+i\s+(?:focus(?:ed)?|stud(?:y|ied)|work(?:ed)?)|(?:my\s+)?{word}\s+(?:stats|statistics|time|total|minutes))(?:\s+(today|this\s+week|so\s+far))?", low)
        if m:
            return self.stats_text((m.group(1) or "") == "this week", datetime.fromtimestamp(now) if now else None)
        m = (re.fullmatch(rf"(?:start|begin|do|run|set|launch)\s+(?:a\s+|an\s+|my\s+|the\s+)?(?:(.+?)\s+)?(?:{word})(?:\s+(?:session|timer|mode|block))?(?:\s+(?:of|for)\s+(.+?))?(?:\s+on\s+(.+))?", t, re.I)
             or re.fullmatch(rf"(?:let'?s\s+|i\s+(?:want|need)\s+to\s+|time\s+to\s+)?(focus|concentrate|pomodoro|focus\s+mode|deep\s+work)(?:\s+for\s+(.+?))?(?:\s+on\s+(.+))?", t, re.I))
        if not m:
            return None
        first, length, label = m.group(1), m.group(2), m.group(3)
        if first and first.lower() in ("focus", "concentrate", "pomodoro", "focus mode", "deep work"):
            first = None
        if label and len(label.split()) > 5:
            return None                    # "focus on what really matters in life" is talk, not a timer
        minutes = minutes_of(length or "") or minutes_of(first or "")
        if (length and minutes is None) or (first and minutes is None):
            return None
        try:
            return self.start(minutes, label or "", now)
        except ValueError as exc:
            return str(exc)

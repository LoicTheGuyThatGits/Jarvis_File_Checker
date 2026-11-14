"""Calendar and to-do list for Jarvis, stored in data/planner.json on this PC.

Understands plain English: "add buy milk to my to-do list", "schedule a dentist appointment on Friday at 3pm",
"what's on my calendar tomorrow", "mark buy milk as done". Times are the PC's local time.
"""
from __future__ import annotations

import json
import re
import secrets
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = {m: i + 1 for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"])}
MONTHS.update({"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12})
MAX_TASKS, MAX_EVENTS = 300, 300
MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))
DAY_RE = "|".join(WEEKDAYS)


FILLER = {"on", "at", "by", "for", "due", "before", "until", "from", "the", "to", "that", "is", "called", "named", "in", "next", "this", "of", "and"}


def _clean(text: str) -> str:
    parts = re.sub(r"\s+", " ", text).strip(" ,.;:-").split(" ")
    while parts and parts[0].lower().strip(",.;:") in FILLER - {"in", "next", "this", "of", "and"}:
        parts.pop(0)
    while parts and parts[-1].lower().strip(",.;:") in FILLER:
        parts.pop()
    return " ".join(parts).strip(" ,.;:-")


def parse_when(text: str, now: datetime) -> dict:
    """Pulls a date and a time out of a sentence. {'rest': text without them, 'date': date|None, 'time': (h, m)|None}."""
    work = " " + text + " "
    day: date | None = None
    clock: tuple[int, int] | None = None

    def take(pattern: str, flags=re.I):
        nonlocal work
        m = re.search(pattern, work, flags)
        if m:
            work = work[:m.start()] + " " + work[m.end():]
        return m

    # ---- time of day ----
    m = take(r"\b(?:at\s+)?(\d{1,2})\s*[:h.]\s*(\d{2})\s*(am|pm)?\b")
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if m.group(3):
            h = h % 12 + (12 if m.group(3).lower() == "pm" else 0)
        if h < 24 and mi < 60:
            clock = (h, mi)
    if clock is None:
        m = take(r"\bat\s+(\d{1,2})\s*(am|pm)\b") or take(r"\b(\d{1,2})\s*(am|pm)\b")
        if m:
            h = int(m.group(1)) % 12 + (12 if m.group(2).lower() == "pm" else 0)
            clock = (h, 0)
    if clock is None:
        m = take(r"\b(?:at\s+)?(noon|midday|midnight)\b")
        if m:
            clock = (0, 0) if m.group(1).lower() == "midnight" else (12, 0)
    if clock is None:
        m = take(r"\bat\s+(\d{1,2})\b(?!\s*(?:st|nd|rd|th|/|:))")
        if m and 1 <= int(m.group(1)) <= 12:
            h = int(m.group(1))
            clock = (h + 12 if 1 <= h <= 7 else h, 0)               # "at 5" means 5 pm; "at 9" means 9 am
        elif m:
            work = work[:m.start()] + m.group(0) + work[m.start():]
    # ---- parts of the day ----
    m = take(r"\b(this\s+)?(morning|afternoon|evening|tonight)\b")
    if m:
        word = m.group(2).lower()
        if clock is None:
            clock = {"morning": (9, 0), "afternoon": (15, 0), "evening": (19, 0), "tonight": (20, 0)}[word]
        if day is None and (m.group(1) or word == "tonight"):
            day = now.date()
    # ---- date ----
    if take(r"\bday after tomorrow\b"):
        day = now.date() + timedelta(days=2)
    elif take(r"\btomorrow\b"):
        day = now.date() + timedelta(days=1)
    elif take(r"\btoday\b"):
        day = now.date()
    else:
        m = take(r"\bin\s+(\d{1,3})\s*(minutes?|mins?|hours?|hrs?|days?|weeks?|months?)\b")
        if m:
            n, unit = int(m.group(1)), m.group(2).lower()
            if unit.startswith("min") or unit.startswith("h"):
                target = now + (timedelta(minutes=n) if unit.startswith("min") else timedelta(hours=n))
                day, clock = target.date(), (target.hour, target.minute)
            elif unit.startswith("d"):
                day = now.date() + timedelta(days=n)
            elif unit.startswith("w"):
                day = now.date() + timedelta(weeks=n)
            else:
                day = now.date() + timedelta(days=30 * n)
    if day is None:
        m = take(rf"\b(?:(next|this|on)\s+)?({DAY_RE})\b")
        if m:
            target = WEEKDAYS.index(m.group(2).lower())
            ahead = (target - now.weekday()) % 7
            if ahead == 0 and (m.group(1) or "").lower() == "next":
                ahead = 7
            elif ahead == 0 and clock and (clock[0], clock[1]) <= (now.hour, now.minute) and (m.group(1) or "").lower() != "this":
                ahead = 7
            day = now.date() + timedelta(days=ahead)
    if day is None and take(r"\bnext week\b"):
        day = now.date() + timedelta(days=7 - now.weekday())
    if day is None:
        m = take(rf"\b(?:on\s+)?(\d{{1,2}})(?:st|nd|rd|th)?(?:\s+of)?\s+({MONTH_RE})\b(?:\s+(\d{{4}}))?") 
        if m:
            d, mon, year = int(m.group(1)), MONTHS[m.group(2).lower()], int(m.group(3) or now.year)
        else:
            m = take(rf"\b(?:on\s+)?({MONTH_RE})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(\d{{4}}))?")
            d, mon, year = (int(m.group(2)), MONTHS[m.group(1).lower()], int(m.group(3) or now.year)) if m else (0, 0, 0)
        if m:
            try:
                day = date(year, mon, d)
                if day < now.date() and not (m.group(3) if m.lastindex and m.lastindex >= 3 else None):
                    day = date(year + 1, mon, d)
            except ValueError:
                day = None
    if day is None:
        m = take(r"\b(?:on\s+)?(\d{4})-(\d{2})-(\d{2})\b") or take(r"\b(?:on\s+)?(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
        if m:
            try:
                if len(m.group(1)) == 4:
                    day = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                else:
                    year = int(m.group(3)) + (2000 if m.group(3) and len(m.group(3)) == 2 else 0) if m.group(3) else now.year
                    day = date(year, int(m.group(2)), int(m.group(1)))              # day first, as in Europe
                    if day < now.date() and not m.group(3):
                        day = date(year + 1, int(m.group(2)), int(m.group(1)))
            except ValueError:
                day = None
    return {"rest": _clean(work), "date": day, "time": clock}


def resolve(parsed: dict, now: datetime) -> tuple[float | None, bool]:
    """(timestamp, has_time). A time alone means today, or tomorrow when it has passed. A date alone is 08:00 that day."""
    day, clock = parsed["date"], parsed["time"]
    if day is None and clock is None:
        return None, False
    if day is None:
        day = now.date()
        if datetime.combine(day, datetime.min.time().replace(hour=clock[0], minute=clock[1])) <= now:
            day += timedelta(days=1)
    stamp = datetime(day.year, day.month, day.day, *(clock or (8, 0)))
    return stamp.timestamp(), clock is not None


def say_day(day: date, today: date) -> str:
    delta = (day - today).days
    if delta == 0:
        return "today"
    if delta == 1:
        return "tomorrow"
    if 1 < delta < 7:
        return day.strftime("%A")
    return f"{day.strftime('%A')} {day.day} {day.strftime('%B')}"


def say_when(ts: float, has_time: bool, now: datetime) -> str:
    when = datetime.fromtimestamp(ts)
    out = say_day(when.date(), now.date())
    return f"{out} at {when.strftime('%H:%M')}" if has_time else out


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if len(w) > 2 and w not in {"the", "and", "for", "from", "task", "tasks", "todo", "list", "event", "meeting", "my"}}


class Planner:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()

    # ---- storage ----
    def load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data = data if isinstance(data, dict) else {}
        for key in ("tasks", "events"):
            if not isinstance(data.get(key), list):
                data[key] = []
        return data

    def save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def public(self, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        with self.lock:
            data = self.load()
        tasks = sorted(data["tasks"], key=lambda t: (t.get("done", False), t.get("due") or 9e12, t.get("created", 0)))
        events = sorted([e for e in data["events"] if e.get("start", 0) >= now - 3600], key=lambda e: e["start"])
        return {"tasks": tasks, "events": events, "now": now}

    # ---- tasks ----
    def add_task(self, text: str, due: float | None = None, has_time: bool = False) -> dict:
        text = re.sub(r"\s+", " ", str(text)).strip()[:200]
        if not text:
            raise ValueError("The task needs some text.")
        with self.lock:
            data = self.load()
            if len([t for t in data["tasks"] if not t.get("done")]) >= MAX_TASKS:
                raise ValueError("That is too many open tasks. Finish or delete some first.")
            task = {"id": secrets.token_hex(4), "text": text, "due": due, "has_time": bool(has_time and due), "done": False, "created": time.time()}
            data["tasks"].append(task)
            self.save(data)
            return task

    def set_done(self, task_id: str, done: bool | None = None) -> dict | None:
        with self.lock:
            data = self.load()
            for task in data["tasks"]:
                if task.get("id") == task_id:
                    task["done"] = (not task.get("done")) if done is None else done
                    task["done_at"] = time.time() if task["done"] else None
                    self.save(data)
                    return task
        return None

    def delete(self, kind: str, item_id: str) -> bool:
        key = "tasks" if kind == "task" else "events"
        with self.lock:
            data = self.load()
            if key == "events":                       # a deleted imported event must not come back with the next import
                gone = next((i for i in data["events"] if i.get("id") == item_id and i.get("source")), None)
                if gone:
                    data["hidden"] = (data.get("hidden") or [])[-500:] + [item_id]
            keep = [i for i in data[key] if i.get("id") != item_id]
            if len(keep) == len(data[key]):
                return False
            data[key] = keep
            self.save(data)
            return True

    def sync_external(self, source: str, items: list[dict], quiet: bool = True) -> None:
        """Replace the events imported from one calendar source. Events already known keep their state (a reminder is never sent twice)."""
        with self.lock:
            data = self.load()
            hidden = set(data.get("hidden") or [])
            old = {e["id"]: e for e in data["events"] if e.get("source") == source}
            data["events"] = [e for e in data["events"] if e.get("source") != source]
            now = time.time()
            for it in items:
                if it["id"] in hidden:
                    continue
                ev = old.get(it["id"]) or {"id": it["id"], "created": now, "source": source}
                ev.update({"title": it["title"], "start": float(it["start"]), "source": source})
                if it["id"] not in old and (quiet or it.get("all_day") or it["start"] < now):
                    ev["notified"] = True          # imported events only alert you when you turned that on
                data["events"].append(ev)
            self.save(data)

    def clear_done(self) -> int:
        with self.lock:
            data = self.load()
            keep = [t for t in data["tasks"] if not t.get("done")]
            removed = len(data["tasks"]) - len(keep)
            data["tasks"] = keep
            self.save(data)
            return removed

    # ---- events ----
    def add_event(self, title: str, start: float) -> dict:
        title = re.sub(r"\s+", " ", str(title)).strip()[:200]
        if not title:
            raise ValueError("The event needs a title.")
        if not (time.time() - 86400 <= start <= time.time() + 5 * 366 * 86400):
            raise ValueError("That date is out of range.")
        with self.lock:
            data = self.load()
            if len([e for e in data["events"] if not e.get("source")]) >= MAX_EVENTS:
                raise ValueError("That is too many events. Delete some old ones first.")
            event = {"id": secrets.token_hex(4), "title": title, "start": float(start), "created": time.time()}
            data["events"].append(event)
            self.save(data)
            return event

    def find(self, kind: str, hint: str, open_only: bool = True) -> list[dict]:
        """Items whose words overlap the hint most (all with the best score)."""
        wanted = words(hint)
        with self.lock:
            data = self.load()
        pool = [t for t in data["tasks"] if not (open_only and t.get("done"))] if kind == "task" else [e for e in data["events"] if e.get("start", 0) >= time.time() - 86400]
        scored = [(len(wanted & words(i.get("text") or i.get("title") or "")), i) for i in pool]
        scored = [(s, i) for s, i in scored if s and (s == len(wanted) or s >= 2 or len(wanted) == 1)]
        best = max((s for s, _ in scored), default=0)
        return [i for s, i in scored if s == best] if best else []

    # ---- notifications ----
    def due_notifications(self, now: float, lead: float = 15 * 60) -> list[dict]:
        """Things to tell the person now: events starting within `lead` seconds and tasks that have come due. Each is returned once."""
        out = []
        with self.lock:
            data = self.load()
            changed = False
            for event in data["events"]:
                if not event.get("notified") and event["start"] - lead <= now <= event["start"] + 600:
                    event["notified"] = changed = True
                    minutes = max(0, round((event["start"] - now) / 60))
                    when = datetime.fromtimestamp(event["start"]).strftime("%H:%M")
                    out.append({"kind": "event", "id": event["id"], "title": event["title"], "start": event["start"],
                                "text": f"{event['title']} at {when}" + (f" (in {minutes} minute{'s' if minutes != 1 else ''})" if minutes > 0 else " (now)")})
            for task in data["tasks"]:
                if task.get("due") and not task.get("done") and not task.get("notified") and task["due"] <= now <= task["due"] + 86400:
                    task["notified"] = changed = True
                    out.append({"kind": "task", "id": task["id"], "title": task["text"], "due": task["due"], "text": f"Task due: {task['text']}"})
            if changed:
                self.save(data)
        return out

    # ---- spoken summaries ----
    def agenda_text(self, start: datetime, end: datetime, now: datetime, label: str) -> str:
        with self.lock:
            data = self.load()
        events = sorted([e for e in data["events"] if start.timestamp() <= e["start"] < end.timestamp()], key=lambda e: e["start"])
        tasks = [t for t in data["tasks"] if not t.get("done") and t.get("due") and start.timestamp() <= t["due"] < end.timestamp()]
        if not events and not tasks:
            return f"Nothing is planned {label}, sir."
        lines = [f"{label.capitalize()}:"]
        for e in events:
            when = datetime.fromtimestamp(e["start"])
            lines.append(f"• {say_day(when.date(), now.date()).capitalize()} {when.strftime('%H:%M')}: {e['title']}" if (end - start).days > 1 else f"• {when.strftime('%H:%M')}: {e['title']}")
        for t in tasks:
            lines.append(f"• Due {say_when(t['due'], t.get('has_time'), now)}: {t['text']}")
        return "\n".join(lines)

    def tasks_text(self, now: datetime) -> str:
        with self.lock:
            data = self.load()
        open_tasks = sorted([t for t in data["tasks"] if not t.get("done")], key=lambda t: (t.get("due") or 9e12, t.get("created", 0)))
        if not open_tasks:
            return "Your to-do list is empty, sir."
        lines = [f"You have {len(open_tasks)} open task{'s' if len(open_tasks) != 1 else ''}:"]
        for t in open_tasks[:15]:
            lines.append(f"• {t['text']}" + (f" ({say_when(t['due'], t.get('has_time'), now)})" if t.get("due") else ""))
        if len(open_tasks) > 15:
            lines.append(f"… and {len(open_tasks) - 15} more.")
        return "\n".join(lines)

    def brief_line(self, now: datetime) -> str | None:
        start = datetime.combine(now.date(), datetime.min.time())
        with self.lock:
            data = self.load()
        today = sorted([e for e in data["events"] if start.timestamp() <= e["start"] < (start + timedelta(days=1)).timestamp() and e["start"] >= now.timestamp() - 1800], key=lambda e: e["start"])
        open_tasks = [t for t in data["tasks"] if not t.get("done")]
        due_today = [t for t in open_tasks if t.get("due") and t["due"] < (start + timedelta(days=1)).timestamp()]
        parts = []
        if today:
            first = datetime.fromtimestamp(today[0]["start"])
            parts.append(f"You have {len(today)} event{'s' if len(today) != 1 else ''} today, the next one is {today[0]['title']} at {first.strftime('%H:%M')}.")
        if due_today:
            parts.append(f"{len(due_today)} task{'s are' if len(due_today) != 1 else ' is'} due today.")
        elif open_tasks:
            parts.append(f"You have {len(open_tasks)} open task{'s' if len(open_tasks) != 1 else ''}.")
        return " ".join(parts) or None

    # ---- commands ----
    def command(self, text: str, now: datetime | None = None) -> str | None:
        now = now or datetime.now()
        t = re.sub(r"\s+", " ", (text or "").strip())
        t = re.sub(r"^(?:(?:hey\s+)?jarvis[,.:]?\s+)?(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?)?", "", t, flags=re.I)
        t = re.sub(r"\s*(?:please|for me)?\s*[.!?]*$", "", t, flags=re.I).strip()
        if not t or len(t) > 300:
            return None
        low = t.lower()
        lst = r"(?:my\s+|the\s+)?(?:to-?\s?do(?:s|\s+list)?|task(?:s|\s+list)?|to\s+do\s+list|checklist)"
        cal = r"(?:my\s+|the\s+)?(?:calendar|agenda|schedule|diary|planner)"
        # ---- show the to-do list ----
        if re.fullmatch(rf"(?:what(?:'s| is)(?: on)?|show(?: me)?|list|read(?: out)?|tell me|open|check|give me|see)\s+{lst}|what\s+(?:tasks|to-?dos?)\s+do\s+i\s+have|what\s+do\s+i\s+(?:still\s+)?(?:have\s+to|need\s+to)\s+do|{lst}", low):
            return self.tasks_text(now)
        # ---- show the calendar ----
        m = re.fullmatch(rf"(?:what(?:'s| is)(?: on)?|show(?: me)?|read(?: out)?|tell me|check|give me|see)\s+{cal}(?:\s+(?:for\s+)?(today|tomorrow|this week|next week|the week|this weekend|on [a-z]+day|[a-z]+day))?"
                         rf"|what\s+(?:do|have)\s+i\s+(?:have\s+)?(?:got\s+)?(?:planned\s+|on\s+)?(today|tomorrow|this week|next week|on [a-z]+day|[a-z]+day)"
                         rf"|what(?:'s| is)\s+(?:happening|planned|up|on)\s+(today|tomorrow|this week|next week|on [a-z]+day|[a-z]+day)"
                         rf"|(?:what(?:'s| is)\s+)?{cal}\s+(today|tomorrow|this week)|my\s+(?:calendar|agenda|schedule|diary|planner)", low)
        if m:
            when = next((g for g in m.groups() if g), "today").replace("on ", "")
            return self.agenda_for(when, now)
        # ---- mark done ----
        m = (re.fullmatch(rf"(?:mark|tick|check|cross)(?: off)?\s+(.+?)\s+(?:as\s+)?(?:done|complete|completed|finished)(?:\s+(?:in|on|from)\s+{lst})?", t, re.I)
             or re.fullmatch(rf"(?:tick|check|cross)\s+off\s+(.+?)(?:\s+(?:from|on|in)\s+{lst})?", t, re.I)
             or re.fullmatch(rf"(?:i(?:'ve| have)?\s+)?(?:finished|completed|done with|did)\s+(.+?)(?:\s+(?:from|on|in)\s+{lst})?", t, re.I)
             or re.fullmatch(rf"(?:complete|finish)\s+(?:the\s+)?(?:task\s+)?(.+)", t, re.I))
        if m and not re.fullmatch(r"(?:it|that|this|everything|all)", m.group(1).strip(), re.I) and not re.match(r"(?:i|you|we|he|she|they|it|anyone|someone)\b", m.group(1).strip(), re.I):   # "did I forget anything" is a question
            return self.done_by_hint(m.group(1))
        # ---- remove ----
        if re.fullmatch(r"(?:clear|delete|remove)\s+(?:all\s+)?(?:my\s+|the\s+)?(?:done|completed|finished)\s+(?:tasks|to-?dos|items)", low):
            n = self.clear_done()
            return f"Cleared {n} finished task{'s' if n != 1 else ''}, sir." if n else "There are no finished tasks to clear, sir."
        m = (re.fullmatch(rf"(?:remove|delete|cancel|drop|scrap)\s+(.+?)\s+from\s+{lst}", t, re.I) or re.fullmatch(r"(?:remove|delete|cancel|drop)\s+(?:the\s+)?(?:task|to-?do)\s+(.+)", t, re.I))
        if m:
            return self.remove_by_hint("task", m.group(1))
        m = (re.fullmatch(rf"(?:remove|delete|cancel|drop)\s+(.+?)\s+from\s+{cal}", t, re.I) or re.fullmatch(r"(?:remove|delete|cancel|drop)\s+(?:the\s+|my\s+)?(?:event|meeting|appointment)\s+(.+)", t, re.I)
             or re.fullmatch(r"(?:cancel|delete|remove)\s+(?:the\s+|my\s+)?(.+?\s+(?:appointment|meeting|event|lesson|class|exam))", t, re.I))
        if m:
            return self.remove_by_hint("event", m.group(1))
        # ---- add to the calendar ----
        m = (re.fullmatch(rf"(?:schedule|book|add|put|create|set up|plan)\s+(?:a\s+|an\s+|the\s+)?(?:new\s+)?(?:event\s*:\s*)?(.+?)(?:\s+(?:to|in|on)\s+{cal})?", t, re.I)
             or re.fullmatch(r"i\s+have\s+(?:a\s+|an\s+|my\s+)?((?:meeting|appointment|exam|test|lesson|class|interview|concert|match|game|trip|dentist|doctor|haircut|training|practice|party|birthday|flight|presentation)\b.*)", t, re.I))
        if m and not re.search(rf"\b{lst}\b", low) and not re.search(r"\b(?:task|to-?do|reminder|timer|alarm)\b", low):
            parsed = parse_when(m.group(1), now)
            stamp, has_time = resolve(parsed, now)
            if stamp and parsed["rest"]:
                if not has_time:
                    stamp = datetime.fromtimestamp(stamp).replace(hour=9).timestamp()
                if stamp < now.timestamp() - 60:
                    return "That time has already passed, sir. Tell me a future date."
                try:
                    event = self.add_event(parsed["rest"], stamp)
                except ValueError as exc:
                    return str(exc)
                return f"Added “{event['title']}” to your calendar for {say_when(stamp, True, now)}, sir."
        # ---- add a task ----
        m = (re.fullmatch(rf"(?:add|put|create|write(?: down)?|note(?: down)?|new)\s+(?:a\s+|an\s+)?(?:new\s+)?(?:task|to-?do|item)?\s*:?\s*(.+?)\s+(?:to|on|in|onto)\s+{lst}", t, re.I)
             or re.fullmatch(r"(?:add|create|new)\s+(?:a\s+)?(?:task|to-?do)\s*:?\s*(.+)", t, re.I)
             or re.fullmatch(r"(?:to-?do|task)\s*:\s*(.+)", t, re.I)
             or re.fullmatch(r"(?:i\s+(?:need|have|must|should)\s+to|don't let me forget to|put on my list(?: that i need to)?)\s+(.+?)\s+(?:on|to|in)\s+(?:my\s+)?(?:list|to-?do)", t, re.I))
        if m:
            parsed = parse_when(m.group(1), now)
            stamp, has_time = resolve(parsed, now)
            body = parsed["rest"] or m.group(1).strip()
            try:
                task = self.add_task(body, stamp, has_time)
            except ValueError as exc:
                return str(exc)
            return f"Added “{task['text']}” to your to-do list" + (f", due {say_when(stamp, has_time, now)}" if stamp else "") + ", sir."
        return None

    def agenda_for(self, word: str, now: datetime) -> str:
        today = datetime.combine(now.date(), datetime.min.time())
        word = word.strip().lower()
        if word == "tomorrow":
            return self.agenda_text(today + timedelta(days=1), today + timedelta(days=2), now, "tomorrow")
        if word in ("this week", "the week"):
            return self.agenda_text(today, today + timedelta(days=7 - now.weekday()), now, "this week")
        if word == "next week":
            start = today + timedelta(days=7 - now.weekday())
            return self.agenda_text(start, start + timedelta(days=7), now, "next week")
        if word == "this weekend":
            start = today + timedelta(days=(5 - now.weekday()) % 7)
            return self.agenda_text(start, start + timedelta(days=2), now, "this weekend")
        if word in WEEKDAYS:
            ahead = (WEEKDAYS.index(word) - now.weekday()) % 7
            start = today + timedelta(days=ahead)
            return self.agenda_text(start, start + timedelta(days=1), now, f"on {word.capitalize()}")
        return self.agenda_text(today, today + timedelta(days=1), now, "today")

    def done_by_hint(self, hint: str) -> str:
        hits = self.find("task", hint)
        if not hits:
            return f"I could not find an open task like “{hint.strip()}”, sir."
        if len(hits) > 1:
            return "Which one, sir? " + "; ".join(h["text"] for h in hits[:4])
        self.set_done(hits[0]["id"], True)
        return f"Ticked off “{hits[0]['text']}”, sir."

    def remove_by_hint(self, kind: str, hint: str) -> str:
        hits = self.find(kind, hint, open_only=False)
        if not hits:
            return f"I could not find a {kind} like “{hint.strip()}”, sir."
        if len(hits) > 1:
            return "Which one, sir? " + "; ".join((h.get("text") or h.get("title")) for h in hits[:4])
        self.delete(kind, hits[0]["id"])
        return f"Removed “{hits[0].get('text') or hits[0].get('title')}”, sir."


PLANNER: Planner | None = None

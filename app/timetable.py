"""The weekly school timetable: "what's my next class?", "when do I finish today?", "what do I need to bring tomorrow?"

Lessons are kept in data/timetable.json: a weekday, a start and end time, the subject, and optionally a room and what to bring.
(A timetable that comes as an iCal link is imported into the calendar instead; see ical.py.) Lessons do not happen during your
holidays: any countdown with a first and last day whose name is a holiday ("Christmas vacation") counts as days off.

    Timetable(path)                                  .lessons() .add(...) .remove(subject, day) .set_bring(subject, items) .config() .set_config(...)
    lessons_on(tt, day, off)                         the lessons of one day, in order ([] on a day off)
    next_lesson(tt, now, off, subject=None)          (lesson, start datetime) or None
    command(text, tt, now, off, extras)              the reply, or None when the message is not about the timetable
    evening_note(tt, now, off, extras)               the "for tomorrow" message, or None
"""
from __future__ import annotations

import json
import re
import secrets
import threading
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MAX_LESSONS = 120
DEFAULT_LENGTH = 45                      # minutes, when only a start time is given
DAY_WORD = r"(?:mon|tues?|wed(?:nes)?|thu(?:rs?)?|fri|sat(?:ur)?|sun)(?:day)?s?"
TIME_WORD = r"\d{1,2}(?:[:.h]\d{2})?\s*(?:am|pm)?"
LESSON = r"(?:class(?:es)?|lessons?|periods?|courses?|subjects?)"


def fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", (text or "").lower()) if not unicodedata.combining(c))


def subject_key(text: str) -> str:
    t = re.sub(rf"\b(?:my|the|a|an|next|{LESSON}|de|cours|du|le|la|les)\b", " ", fold(text))
    t = re.sub(r"\bmath\b", "maths", t)
    return re.sub(r"\s+", " ", re.sub(r"[^\w ]", " ", t)).strip()


def parse_clock(text: str) -> str | None:
    m = re.fullmatch(r"(\d{1,2})(?:[:.h](\d{2}))?\s*(am|pm)?", (text or "").strip().lower())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if m.group(3) == "pm" and h < 12:
        h += 12
    if m.group(3) == "am" and h == 12:
        h = 0
    return f"{h:02d}:{mi:02d}" if 0 <= h <= 23 and 0 <= mi <= 59 else None


def parse_days(text: str) -> list[int]:
    t = text.lower()
    if re.search(r"\bweek\s*days?\b|\bschool\s+days?\b|\bevery\s+day\b", t):
        return list(range(5))
    return sorted({i for i, d in enumerate(DAYS) if re.search(rf"\b{d[:3].lower()}", t)})


def minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def plus(hhmm: str, mins: int) -> str:
    total = min(23 * 60 + 59, minutes(hhmm) + mins)
    return f"{total // 60:02d}:{total % 60:02d}"


def say_day(day: date, today: date) -> str:
    if day == today:
        return "today"
    if day == today + timedelta(days=1):
        return "tomorrow"
    if 0 < (day - today).days < 7:
        return "on " + DAYS[day.weekday()]
    return f"on {DAYS[day.weekday()]} {day.day} {day.strftime('%B')}"


def span(mins: int) -> str:
    if mins < 60:
        return f"{mins} minute{'s' if mins != 1 else ''}"
    h, m = divmod(mins, 60)
    return f"{h} hour{'s' if h != 1 else ''}" + (f" and {m} minute{'s' if m != 1 else ''}" if m else "")


def where(lesson: dict) -> str:
    return f" in {lesson['room']}" if lesson.get("room") else ""


class Timetable:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock = threading.Lock()

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data = data if isinstance(data, dict) else {}
        lessons = []
        for it in data.get("lessons") or []:
            try:
                if 0 <= int(it["day"]) <= 6 and parse_clock(it["start"]) and parse_clock(it["end"]) and str(it["subject"]).strip():
                    lessons.append({"id": str(it.get("id") or secrets.token_hex(4)), "day": int(it["day"]), "start": parse_clock(it["start"]), "end": parse_clock(it["end"]),
                                    "subject": str(it["subject"]).strip()[:40], "room": str(it.get("room") or "").strip()[:20], "bring": str(it.get("bring") or "").strip()[:120]})
            except (KeyError, TypeError, ValueError):
                continue
        prep = data.get("prep") if isinstance(data.get("prep"), dict) else {}
        return {"lessons": lessons, "prep": {"on": prep.get("on", True) is not False, "time": parse_clock(str(prep.get("time") or "")) or "19:00"},
                "last_note": str(data.get("last_note") or "")}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def lessons(self) -> list[dict]:
        with self.lock:
            return sorted(self._load()["lessons"], key=lambda l: (l["day"], l["start"]))

    def config(self) -> dict:
        with self.lock:
            return self._load()["prep"]

    def set_config(self, on: bool | None = None, at: str | None = None) -> dict:
        with self.lock:
            data = self._load()
            if on is not None:
                data["prep"]["on"] = bool(on)
            if at is not None:
                clock = parse_clock(at)
                if not clock:
                    raise ValueError("Give the time as HH:MM, for example 19:00.")
                data["prep"]["time"] = clock
            self._save(data)
            return data["prep"]

    def mark_note(self, day: str) -> bool:
        """True the first time it is called for a day (so the evening message is sent once)."""
        with self.lock:
            data = self._load()
            if data["last_note"] == day:
                return False
            data["last_note"] = day
            self._save(data)
            return True

    def add(self, day: int, start: str, end: str | None, subject: str, room: str = "", bring: str = "") -> tuple[dict, bool]:
        """(the lesson, True when it replaced the lesson at the same day and time)."""
        subject = re.sub(r"\s+", " ", str(subject)).strip(" .,;:")[:40]
        start_c = parse_clock(start)
        end_c = parse_clock(end) if end else (plus(start_c, DEFAULT_LENGTH) if start_c else None)
        if not subject:
            raise ValueError("The lesson needs a subject.")
        if not 0 <= int(day) <= 6:
            raise ValueError("Pick a day from Monday to Sunday.")
        if not start_c or not end_c:
            raise ValueError("Give the start and end times as HH:MM, for example 08:15 and 09:00.")
        if minutes(end_c) <= minutes(start_c):
            raise ValueError("The lesson must end after it starts.")
        with self.lock:
            data = self._load()
            same = [l for l in data["lessons"] if l["day"] == int(day) and l["start"] == start_c]
            data["lessons"] = [l for l in data["lessons"] if l not in same]
            if len(data["lessons"]) >= MAX_LESSONS:
                raise ValueError(f"The timetable can hold {MAX_LESSONS} lessons.")
            keep_bring = same[0]["bring"] if same and subject_key(same[0]["subject"]) == subject_key(subject) else ""
            lesson = {"id": same[0]["id"] if same else secrets.token_hex(4), "day": int(day), "start": start_c, "end": end_c, "subject": subject,
                      "room": re.sub(r"\s+", " ", str(room or "")).strip()[:20], "bring": (str(bring or "").strip() or keep_bring)[:120]}
            data["lessons"].append(lesson)
            self._save(data)
            return lesson, bool(same)

    def remove(self, subject_or_id: str, day: int | None = None) -> list[dict]:
        with self.lock:
            data = self._load()
            key = subject_key(subject_or_id)
            gone = [l for l in data["lessons"] if l["id"] == subject_or_id or (key and subject_key(l["subject"]) == key and (day is None or l["day"] == day))]
            data["lessons"] = [l for l in data["lessons"] if l not in gone]
            self._save(data)
            return gone

    def set_bring(self, subject: str, items: str) -> list[dict]:
        with self.lock:
            data = self._load()
            hit = [l for l in data["lessons"] if subject_key(l["subject"]) == subject_key(subject)]
            items = re.sub(r"\b(?:my|mon|ma|mes)\s+", "", re.sub(r"\s+", " ", items)).strip(" .")[:120]
            for l in hit:
                l["bring"] = items
            self._save(data)
            return hit


# ---------------- reading the timetable ----------------
def lessons_on(tt: Timetable, day: date, off=None) -> list[dict]:
    if off and off(day):
        return []
    return [l for l in tt.lessons() if l["day"] == day.weekday()]


def at(day: date, hhmm: str) -> datetime:
    h, m = hhmm.split(":")
    return datetime(day.year, day.month, day.day, int(h), int(m))


def next_lesson(tt: Timetable, now: datetime, off=None, subject: str | None = None) -> tuple[dict, datetime] | None:
    key = subject_key(subject) if subject else None
    for ahead in range(0, 60):
        day = now.date() + timedelta(days=ahead)
        for l in lessons_on(tt, day, off):
            if at(day, l["start"]) > now and (key is None or subject_key(l["subject"]) == key or (key and key in subject_key(l["subject"]).split())):
                return l, at(day, l["start"])
    return None


def current_lesson(tt: Timetable, now: datetime, off=None) -> dict | None:
    return next((l for l in lessons_on(tt, now.date(), off) if at(now.date(), l["start"]) <= now < at(now.date(), l["end"])), None)


def day_text(tt: Timetable, day: date, now: datetime, off=None) -> str:
    when = say_day(day, now.date())
    reason = off(day) if off else None
    if reason:
        return f"No lessons {when}, sir: it is the {reason}."
    ls = lessons_on(tt, day, off)
    if not ls:
        return f"No lessons {when}, sir."
    lines = [f"{when[:1].upper() + when[1:]}, {len(ls)} lesson{'s' if len(ls) != 1 else ''}, from {ls[0]['start']} to {ls[-1]['end']}:"]
    lines += [f"• {l['start']}–{l['end']} {l['subject']}{where(l)}" for l in ls]
    return "\n".join(lines)


def week_text(tt: Timetable) -> str:
    ls = tt.lessons()
    if not ls:
        return EMPTY
    lines = ["Your timetable, sir:"]
    for d in range(7):
        day = [l for l in ls if l["day"] == d]
        if day:
            lines.append(f"{DAYS[d]}: " + ", ".join(f"{l['start']} {l['subject']}" for l in day))
    return "\n".join(lines)


def bring_text(lessons: list[dict]) -> str:
    items = [f"{l['bring']} ({l['subject']})" for l in lessons if l.get("bring")]
    seen, out = set(), []
    for i in items:
        if i.lower() not in seen:
            seen.add(i.lower())
            out.append(i)
    return ", ".join(out)


EMPTY = ("Your timetable is empty, sir. Add lessons in Settings > Planner > Timetable, or say, for example, "
         "“add maths every Monday from 8:15 to 9:00 in room B12”. If your school gives you an iCal link, import it under Calendars instead.")

WHEN_WORD = r"(today|tomorrow|this\s+morning|this\s+afternoon|on\s+\w+day|\w+day)"
CLEAN = r"^(?:(?:hey\s+)?jarvis[,.:]?\s+)?(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?)?(?:tell\s+me\s+)?"


def which_day(word: str | None, now: datetime) -> date:
    w = (word or "today").lower().replace("on ", "").strip()
    if w in ("today", "this morning", "this afternoon"):
        return now.date()
    if w == "tomorrow":
        return now.date() + timedelta(days=1)
    for i, d in enumerate(DAYS):
        if w.startswith(d[:3].lower()):
            return now.date() + timedelta(days=(i - now.weekday()) % 7)
    return now.date()


def command(text: str, tt: Timetable, now: datetime | None = None, off=None, extras=None) -> str | None:
    now = now or datetime.now()
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = re.sub(CLEAN, "", t, flags=re.I)
    t = re.sub(r"\s*(?:please|for me)?\s*[.!?]*$", "", t, flags=re.I).strip()
    if not t or len(t) > 200:
        return None
    low = t.lower()
    # ---- adding lessons ----
    m = (re.fullmatch(rf"(?:add|put)\s+(?P<subj>[^,]+?)\s+(?:to\s+my\s+timetable\s+)?(?:every|on)\s+(?P<days>{DAY_WORD}(?:\s*(?:,|and|&)\s*{DAY_WORD})*|weekdays?|school\s+days)\s+"
                      rf"(?:from\s+|at\s+)?(?P<start>{TIME_WORD})(?:\s*(?:to|until|till|-|–)\s*(?P<end>{TIME_WORD}))?(?:\s+in\s+(?:room\s+)?(?P<room>[\w.-]+))?(?:\s+(?:to|in)\s+my\s+timetable)?", t, re.I)
         or re.fullmatch(rf"i\s+have\s+(?P<subj>[^,]+?)\s+every\s+(?P<days>{DAY_WORD}(?:\s*(?:,|and|&)\s*{DAY_WORD})*)\s+(?:from\s+|at\s+)?(?P<start>{TIME_WORD})"
                         rf"(?:\s*(?:to|until|till|-|–)\s*(?P<end>{TIME_WORD}))?(?:\s+in\s+(?:room\s+)?(?P<room>[\w.-]+))?", t, re.I))
    if m and not re.search(r"\b(?:reminder|timer|alarm|task|event|countdown|routine|to-?do|meeting|appointment)\b", m.group("subj"), re.I) and len(m.group("subj")) <= 40:
        days = parse_days(m.group("days"))
        subject = re.sub(rf"^(?:a\s+|an\s+|my\s+)?|\s+{LESSON}$", "", m.group("subj").strip(), flags=re.I)
        subject = subject[:1].upper() + subject[1:]
        if not days:
            return None
        try:
            added = [tt.add(d, m.group("start"), m.group("end"), subject, m.group("room") or "") for d in days]
        except ValueError as exc:
            return str(exc)
        l = added[0][0]
        names = [DAYS[d] + "s" for d in days]
        on = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
        note = "" if m.group("end") else f" It ends at {l['end']}; say “add {subject} every {DAYS[days[0]]} from {l['start']} to …” to change that."
        return f"Added {subject} to your timetable, sir: {on}, {l['start']}–{l['end']}{where(l)}.{note}"
    m = re.fullmatch(r"(?:for|on|in)\s+(?P<subj>[^,]+?)\s*,?\s+(?:days?\s+)?(?:i\s+(?:need|have|must|should)\s+to\s+|i\s+must\s+|always\s+)?(?:bring|take|pack)\s+(?P<items>.+)", t, re.I)
    if m:
        hit = tt.set_bring(m.group("subj"), m.group("items"))
        if hit:
            return f"Noted, sir: for {hit[0]['subject']} you bring {hit[0]['bring']}. I will remind you the evening before."
    m = re.fullmatch(rf"(?:remove|delete|take)\s+(?:the\s+|my\s+)?(?:(?P<day>{DAY_WORD})(?:'s)?\s+)?(?P<subj>.+?)(?:\s+{LESSON})?(?:\s+(?:on\s+)?(?P<day2>{DAY_WORD}))?\s+(?:out\s+of|from|off)\s+(?:my\s+|the\s+)?timetable", t, re.I)
    if m:
        day = parse_days(m.group("day") or m.group("day2") or "")
        gone = tt.remove(m.group("subj"), day[0] if day else None)
        if not gone:
            return f"There is no {m.group('subj')} in your timetable, sir."
        return f"Removed {len(gone)} {gone[0]['subject']} lesson{'s' if len(gone) != 1 else ''} from your timetable, sir."
    # ---- questions ----
    if re.fullmatch(r"(?:show|read|what(?:'s| is))(?:\s+me)?\s+(?:my|the)\s+(?:whole\s+|full\s+)?(?:school\s+)?timetable(?:\s+for\s+the\s+week)?|my\s+timetable", low):
        return week_text(tt)
    lessons_exist = bool(tt.lessons())
    m = re.fullmatch(rf"(?:what(?:'s| is)|which\s+is)\s+(?:my\s+|the\s+)?next\s+{LESSON}|what\s+{LESSON}\s+(?:do\s+i\s+have|have\s+i\s+got|is)\s+next|what(?:'s| is)\s+next\s+(?:at|in)\s+school|(?:my\s+)?next\s+{LESSON}|where\s+is\s+my\s+next\s+{LESSON}|where\s+do\s+i\s+have\s+to\s+go\s+next", low)
    if m:
        if not lessons_exist:
            return EMPTY
        cur = current_lesson(tt, now, off)
        nxt = next_lesson(tt, now, off)
        if nxt is None:
            return "No more lessons are coming up, sir."
        l, start = nxt
        mins = int((start - now).total_seconds() // 60)
        when = f"in {span(mins)}" if start.date() == now.date() else f"{say_day(start.date(), now.date())} at {l['start']}"
        head = f"You are in {cur['subject']} until {cur['end']}. Next is " if cur else "Your next class is "
        tail = f" at {l['start']}{where(l)}, {when}" if start.date() == now.date() else f"{where(l)}, {when}"
        out = f"{head}{l['subject']}{tail}, sir."
        return out
    m = re.fullmatch(rf"when\s+(?:is|do\s+i\s+have)\s+(?:my\s+)?(?:next\s+)?(?P<subj>.+?)(?:\s+{LESSON})?(?:\s+next|\s+again)?", t, re.I)
    if m and lessons_exist and not re.search(r"\b(?:exam|test|appointment|meeting|holiday|vacation|birthday)s?\b", m.group("subj"), re.I):
        nxt = next_lesson(tt, now, off, m.group("subj"))
        if nxt:
            l, start = nxt
            return f"Your next {l['subject']} lesson is {say_day(start.date(), now.date())} at {l['start']}{where(l)}, sir."
        if any(subject_key(m.group("subj")) in subject_key(x["subject"]).split() or subject_key(x["subject"]) == subject_key(m.group("subj")) for x in tt.lessons()):
            return f"There is no {m.group('subj')} lesson in the coming weeks, sir."
        return None
    m = re.fullmatch(rf"what\s+(?:{LESSON}|school)\s+(?:do\s+i\s+have|have\s+i\s+got|is\s+there)\s+{WHEN_WORD}|what(?:'s| is)\s+(?:my\s+)?(?:school\s+)?timetable\s+(?:for\s+)?{WHEN_WORD}|(?:my\s+)?{LESSON}\s+{WHEN_WORD}|what\s+(?:{LESSON}\s+)?do\s+i\s+have\s+(?:at\s+school\s+){WHEN_WORD}", low)
    if m:
        if not lessons_exist:
            return EMPTY
        word = next((g for g in m.groups() if g), "today")
        return day_text(tt, which_day(word, now), now, off)
    m = re.fullmatch(rf"(?:when|what\s+time)\s+(?:does\s+school\s+(?:start|begin)|do\s+i\s+(?:start|begin)(?:\s+school)?|is\s+my\s+first\s+{LESSON})\s*{WHEN_WORD}?", low)
    if m:
        if not lessons_exist:
            return EMPTY
        day = which_day(m.group(1), now)
        ls = lessons_on(tt, day, off)
        if not ls:
            return day_text(tt, day, now, off)
        return f"You start {say_day(day, now.date())} at {ls[0]['start']} with {ls[0]['subject']}{where(ls[0])}, sir."
    m = re.fullmatch(rf"(?:when|what\s+time)\s+(?:does\s+school\s+(?:end|finish)|do\s+i\s+(?:finish|end|get\s+out)(?:\s+school)?|is\s+my\s+last\s+{LESSON})\s*{WHEN_WORD}?", low)
    if m:
        if not lessons_exist:
            return EMPTY
        day = which_day(m.group(1), now)
        ls = lessons_on(tt, day, off)
        if not ls:
            return day_text(tt, day, now, off)
        end = at(day, ls[-1]["end"])
        left = f", in {span(int((end - now).total_seconds() // 60))}" if day == now.date() and end > now else ""
        return f"You finish {say_day(day, now.date())} at {ls[-1]['end']}, after {ls[-1]['subject']}{left}, sir."
    m = re.fullmatch(rf"what\s+(?:do\s+i\s+(?:need|have)\s+to|should\s+i|must\s+i)\s+(?:bring|take|pack)(?:\s+(?:to\s+school|for\s+school))?\s*{WHEN_WORD}?|what\s+(?:to\s+)?(?:bring|pack)\s+{WHEN_WORD}", low)
    if m:
        if not lessons_exist:
            return EMPTY
        day = which_day(next((g for g in m.groups() if g), "tomorrow"), now)
        ls = lessons_on(tt, day, off)
        if not ls:
            return day_text(tt, day, now, off)
        items = bring_text(ls)
        due = (extras or {}).get("due", lambda d: [])(day)
        return (f"For {say_day(day, now.date()).replace('on ', '')}: bring {items}, sir." if items else f"Nothing special to bring {say_day(day, now.date())}, sir; just your usual things.") + \
               (" Due then: " + "; ".join(due) + "." if due else "")
    return None


def evening_note(tt: Timetable, now: datetime, off=None, extras=None) -> str | None:
    """'For tomorrow, sir: you start at 08:15 with Maths in B12 and finish at 15:30. Bring: …. Test: …. Due: ….'"""
    day = now.date() + timedelta(days=1)
    ls = lessons_on(tt, day, off)
    if not ls:
        return None
    parts = [f"For tomorrow, sir: you start at {ls[0]['start']} with {ls[0]['subject']}{where(ls[0])} and finish at {ls[-1]['end']} ({len(ls)} lesson{'s' if len(ls) != 1 else ''})."]
    items = bring_text(ls)
    if items:
        parts.append(f"Bring: {items}.")
    extras = extras or {}
    tests = extras.get("tests", lambda d: [])(day)
    if tests:
        parts.append("Test" + ("s" if len(tests) > 1 else "") + " tomorrow: " + "; ".join(tests) + ".")
    due = extras.get("due", lambda d: [])(day)
    if due:
        parts.append("Due tomorrow: " + "; ".join(due) + ".")
    return " ".join(parts)


def brief_line(tt: Timetable, now: datetime, off=None) -> str | None:
    ls = [l for l in lessons_on(tt, now.date(), off) if at(now.date(), l["end"]) > now]
    if not ls:
        return None
    first = ls[0]
    return f"School today: {len(ls)} lesson{'s' if len(ls) != 1 else ''} until {ls[-1]['end']}, starting with {first['subject']}{where(first)} at {first['start']}."

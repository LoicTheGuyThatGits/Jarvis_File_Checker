"""Homework, tied to your timetable: "maths homework: exercises 4 to 7, for next lesson" lands on your next maths lesson.

Homework lives in the planner as tasks, so it shows up in the to-do list, the morning briefing and the evening note
("Due tomorrow: Maths: exercises 4 to 7"). Each one carries a "homework" field: {"subject", "source": "chat" or
"classroom", "id": the Classroom id, "link"}.

    parse_add(text)                         {"subject", "what", "when"} or None
    due_for(subject, when, now, ctx)        (timestamp, day) or (None, reason)
    command(text, planner, now, ctx)        the reply, or None when the message is not about homework
    pending(planner)                        open homework, soonest first
    sync(planner, items, subject_of)        Classroom assignments in → the ones that are new

ctx is a dict: "next_lesson": (subject, after datetime) -> (lesson, start datetime) or None,
"subjects": () -> known subject names, "parse_when": planner.parse_when.
"""
from __future__ import annotations

import re
import secrets
import time
import unicodedata
from datetime import date, datetime, timedelta

# subject names in French and German, so "devoirs de français" finds "French" in the timetable (and the other way round)
ALIASES = {"math": "maths", "mathematics": "maths", "mathematiques": "maths", "mathe": "maths", "mathematik": "maths", "francais": "french",
           "franzosisch": "french", "allemand": "german", "deutsch": "german", "anglais": "english", "englisch": "english", "histoire": "history",
           "geschichte": "history", "geographie": "geography", "geo": "geography", "biologie": "biology", "bio": "biology", "chimie": "chemistry",
           "chemie": "chemistry", "physique": "physics", "physik": "physics", "musique": "music", "musik": "music", "sport": "pe", "eps": "pe",
           "gym": "pe", "physical education": "pe", "education physique": "pe", "italien": "italian", "italienisch": "italian", "espagnol": "spanish",
           "spanisch": "spanish", "latin": "latin", "latein": "latin", "informatique": "computer science", "informatik": "computer science",
           "economie": "economics", "philosophie": "philosophy", "arts visuels": "art", "dessin": "art", "kunst": "art"}
DAYNAME = r"(?:mon|tues|wednes|thurs|fri|satur|sun)day"
MONTH = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
WHEN = (r"(?:(?:the\s+|my\s+)?next\s+(?:(?P<wsub>[a-zà-ÿ][\w'’ .-]{0,25}?)\s+)?(?:lesson|class|period|course)|next\s+time|next\s+week|tomorrow|today|"
        rf"the\s+day\s+after\s+tomorrow|(?:next\s+|this\s+|on\s+)?{DAYNAME}|(?:the\s+)?\d{{1,2}}(?:st|nd|rd|th)?(?:\s+(?:of\s+)?{MONTH})?|"
        rf"{MONTH}\s+\d{{1,2}}(?:st|nd|rd|th)?|"
        r"\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?|\d{4}-\d{2}-\d{2}|in\s+\d{1,2}\s+days?)")
SUBJ = r"[a-zà-ÿ][\w'’ .&-]{0,30}?"
TRAIL_WHEN = re.compile(rf"[,;]?\s*\(?(?:for|due(?:\s+on)?|by|until|before|on)\s+(?P<when>{WHEN})\)?\s*[.!]?$", re.I)
HW = r"(?:homework|home\s*work|assignment)"


def fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", (text or "").lower()) if not unicodedata.combining(c))


def key(name: str) -> str:
    t = re.sub(r"[^\w ]", " ", fold(name))
    t = re.sub(r"\b(?:my|the|a|an|de|du|des|le|la|les|l|cours|lesson|class)\b", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return ALIASES.get(t, t)


def canonical(name: str, known: list[str]) -> str:
    """The subject as your timetable spells it ("maths" → "Mathematics"), or the words given, capitalised."""
    k = key(name)
    if not k:
        return ""
    for s in known or []:
        if key(s) == k:
            return s
    for s in known or []:                                   # "bio" for "Biology", "maths" in "3M Maths"
        ks = key(s)
        if len(k) >= 3 and (ks.startswith(k) or k in ks.split()):
            return s
    clean = re.sub(r"\s+", " ", name).strip(" .,:;")
    return clean[:1].upper() + clean[1:]


def _is_when(text: str) -> bool:
    return bool(re.fullmatch(WHEN, (text or "").strip(), re.I))


def parse_add(text: str) -> dict | None:
    """“maths homework: exercises 4 to 7, for next lesson”, “homework for French: learn the vocab for Thursday”,
    “I have history homework for tomorrow: read pages 40 to 45”, “add homework: essay for Friday”."""
    t = re.sub(r"\s+", " ", (text or "").strip()).rstrip(".!")
    t = re.sub(r"^(?:(?:hey\s+)?jarvis[,.:]?\s+)?(?:please\s+)?(?:(?:can|could)\s+you\s+)?(?:note\s+(?:that\s+)?|write\s+down\s+|add\s+(?:a\s+|some\s+|new\s+)?|new\s+)?", "", t, flags=re.I)
    m = re.fullmatch(rf"(?:(?:i\s+(?:have|got|'ve\s+got)|there\s+is|there's)\s+(?:some\s+|a\s+|an\s+)?)?(?:(?P<s1>{SUBJ})\s+)?{HW}"
                     rf"(?:\s+(?:for|in)\s+(?P<s2>{SUBJ}))?(?:\s+(?:for|due|by)\s+(?P<w1>{WHEN}))?(?:\s*[:,–-]\s*|\s+to\s+do\s*:?\s*)(?P<what>.+)", t, re.I)
    if not m:
        m = re.fullmatch(rf"(?:i\s+(?:have|got|'ve\s+got)|there\s+is|there's)\s+(?:some\s+|a\s+|an\s+)?(?P<s1>{SUBJ})\s+{HW}(?P<s2>)(?:\s+(?:for|due|by)\s+(?P<w1>{WHEN}))(?P<what>)", t, re.I)
    if not m:
        return None
    s1, s2, when, what = (m.group("s1") or "").strip(), (m.group("s2") or "").strip(), (m.group("w1") or "").strip(), (m.group("what") or "").strip()
    if s1 and re.fullmatch(r"(?:my|the|some|new|a|an|any|no|what|which|did|done)", s1, re.I):
        s1 = ""
    if re.match(r"(?:what|which|show|list|any|do|did|how)\b", s1, re.I):
        return None                                          # a question about homework, not new homework
    if s2 and _is_when(s2):
        when, s2 = when or s2, ""
    tail = TRAIL_WHEN.search(what)
    if tail and tail.start() > 0:
        when, what = when or tail.group("when"), what[:tail.start()].strip(" ,;")
    elif tail and tail.start() == 0:
        when, what = when or tail.group("when"), ""
    subject = s1 or s2
    nm = re.match(r"(?:the\s+|my\s+)?next\s+(.+?)\s+(?:lesson|class|period|course)$", when, re.I)
    if nm and not re.fullmatch(r"(?:lesson|class|period|course)", nm.group(1), re.I):
        subject = subject or nm.group(1)
        when = "next lesson"
    return {"subject": subject, "what": what.strip(" .,;"), "when": when}


def due_for(subject: str, when: str, now: datetime, ctx: dict) -> tuple[float | None, object]:
    """The moment homework is due. Unknown → (None, the question to ask)."""
    w = (when or "").strip().lower()
    nl = ctx.get("next_lesson")
    if not w or re.fullmatch(r"(?:the\s+|my\s+)?next\s+(?:lesson|class|period|course|time)", w):
        if not subject:
            return None, "Which subject is it for, sir? For example “maths homework: exercises 4 to 7, for next lesson”."
        found = nl(subject, now) if nl else None
        if not found:
            return None, f"{subject} is not in your timetable, sir, so I do not know when the next lesson is. Tell me the day: “… for Thursday”."
        return found[1].timestamp(), found[1].date()
    if w == "next week":
        monday = (now + timedelta(days=7 - now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        found = nl(subject, monday) if (nl and subject) else None
        if found and found[1].date() < (monday + timedelta(days=7)).date():
            return found[1].timestamp(), found[1].date()
        return monday.replace(hour=8).timestamp(), monday.date()
    m = re.fullmatch(r"in\s+(\d{1,2})\s+days?", w)
    if m:
        day = now.date() + timedelta(days=int(m.group(1)))
    else:
        pw = ctx.get("parse_when")
        parsed = pw(re.sub(r"^the\s+(\d)", r"\1", w), now) if pw else {"date": None}
        day = parsed.get("date")
        if day is None:
            m = re.fullmatch(r"(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?", w)
            if m:                                             # "for the 20th": this month, or next month when it has passed
                try:
                    day = now.date().replace(day=int(m.group(1)))
                    if day < now.date():
                        day = (now.date().replace(day=1) + timedelta(days=32)).replace(day=int(m.group(1)))
                except ValueError:
                    day = None
    if day is None:
        return None, "For when, sir? For example “… for next lesson”, “… for Thursday” or “… for 3 December”."
    if day < now.date():
        return None, "That day has already passed, sir."
    if subject and nl:                                        # at the start of that day's lesson, when there is one
        found = nl(subject, datetime.combine(day, datetime.min.time()))
        if found and found[1].date() == day:
            return found[1].timestamp(), day
    return datetime.combine(day, datetime.min.time()).replace(hour=8).timestamp(), day


def say_day(day: date, today: date) -> str:
    diff = (day - today).days
    if diff == 0:
        return "today"
    if diff == 1:
        return "tomorrow"
    if 1 < diff < 7:
        return day.strftime("%A")
    return day.strftime("%A %d %B").replace(" 0", " ")


def pending(planner, include_done: bool = False) -> list[dict]:
    tasks = [t for t in planner.load()["tasks"] if isinstance(t.get("homework"), dict) and (include_done or not t.get("done"))]
    return sorted(tasks, key=lambda t: (t.get("done", False), t.get("due") or 9e12))


def add(planner, subject: str, what: str, due: float | None, source: str = "chat", ext_id: str = "", link: str = "") -> dict:
    text = (f"{subject}: {what}" if subject and what else what or (f"{subject} homework" if subject else "Homework"))[:200]
    with planner.lock:
        data = planner.load()
        task = {"id": secrets.token_hex(4), "text": text, "due": due, "has_time": False, "done": False, "created": time.time(),
                "notified": True,                              # the evening note and the briefing tell you; no extra alarm when it is due
                "homework": {"subject": subject, "what": what, "source": source, "id": ext_id, "link": link}}
        data["tasks"].append(task)
        planner.save(data)
    return task


def _line(t: dict, now: datetime) -> str:
    due = t.get("due")
    when = ("no due date" if not due else ("late: was due " if datetime.fromtimestamp(due).date() < now.date() else "") + say_day(datetime.fromtimestamp(due).date(), now.date()))
    src = " (Classroom)" if t["homework"].get("source") == "classroom" else ""
    return f"• {when.capitalize() if not when.startswith('late') else when.capitalize()}: {t['text']}{src}"


def _find(planner, subject: str, known: list[str]) -> list[dict]:
    items = pending(planner)
    if not subject:
        return items
    k = key(canonical(subject, known))
    return [t for t in items if key(t["homework"].get("subject") or "") == k or k in key(t["text"]).split()]


def command(text: str, planner, now: datetime | None = None, ctx: dict | None = None) -> str | None:
    now = now or datetime.now()
    ctx = ctx or {}
    known = list(ctx.get("subjects", lambda: [])())
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = re.sub(r"^(?:(?:hey\s+)?jarvis[,.:]?\s+)?(?:please\s+)?(?:(?:can|could)\s+you\s+)?", "", t, flags=re.I).rstrip(" ?.!")
    low = t.lower()
    if not re.search(r"\bhome\s*work|\bassignments?\b", low):
        return None
    # ---- what is there ----
    m = re.fullmatch(rf"(?:(?:what|which|any)\s+{HW}s?\s*(?:do\s+i\s+(?:have|still\s+have)|is\s+(?:there|left|due)|have\s+i\s+got|(?:is|are)\s+(?:due|left))?|"
                     rf"(?:show(?:\s+me)?|list|read(?:\s+me)?)?\s*(?:my|the|all(?:\s+my)?)\s+{HW}s?|{HW}s?|do\s+i\s+have\s+(?:any\s+)?{HW}s?)"
                     rf"(?:\s+(?:for|in|due|on)\s+(?P<filter>.+?)|\s+(?P<filter2>today|tomorrow|this\s+week|next\s+week))?", low)
    if m:
        items, flt = pending(planner), (m.group("filter") or m.group("filter2") or "").strip()
        label = ""
        if flt:
            if re.fullmatch(r"tomorrow|today|this\s+week|next\s+week|(?:on\s+)?" + DAYNAME, flt):
                if flt == "this week":
                    end = now.date() + timedelta(days=7 - now.weekday())
                    items, label = [i for i in items if i.get("due") and datetime.fromtimestamp(i["due"]).date() < end], " this week"
                elif flt == "next week":
                    a = now.date() + timedelta(days=7 - now.weekday())
                    items, label = [i for i in items if i.get("due") and a <= datetime.fromtimestamp(i["due"]).date() < a + timedelta(days=7)], " next week"
                else:
                    day = (ctx.get("parse_when") or (lambda s, n: {"date": None}))(flt, now).get("date")
                    items = [i for i in items if i.get("due") and datetime.fromtimestamp(i["due"]).date() == day]
                    label = " for " + say_day(day, now.date()) if day else ""
            else:
                subject = canonical(flt, known)
                items, label = _find(planner, flt, known), f" in {subject}"
        if not items:
            return f"No homework{label}, sir." if label else "You have no homework left, sir."
        head = f"Homework{label}, sir:" if label else f"Your homework, sir ({len(items)}):"
        return head + "\n" + "\n".join(_line(i, now) for i in items[:15])
    # ---- done, removed ----
    m = re.fullmatch(rf"(?:i\s+)?(?:did|have\s+done|'ve\s+done|finished|completed|handed\s+in|turned\s+in|am\s+done\s+with|'m\s+done\s+with)\s+(?:my\s+|the\s+)?(?P<s>{SUBJ})?\s*{HW}|"
                     rf"mark\s+(?:my\s+|the\s+)?(?P<s2>{SUBJ})?\s*{HW}\s+(?:as\s+)?(?:done|finished)|(?:my\s+|the\s+)?(?P<s3>{SUBJ})\s+{HW}\s+(?:is\s+)?(?:done|finished)", low)
    if m:
        subject = (m.group("s") or m.group("s2") or m.group("s3") or "").strip()
        subject = "" if re.fullmatch(r"my|the|all|all\s+my|all\s+the", subject) else subject
        found = _find(planner, subject, known)
        if not found:                                         # a plain to-do such as “devoir d'histoire”, added before homework existed
            k = key(canonical(subject, known)) if subject else ""
            plain = [x for x in planner.load()["tasks"] if not x.get("done") and not isinstance(x.get("homework"), dict)
                     and re.search(r"homework|devoir|hausaufgabe|compit", fold(x.get("text", ""))) and (not k or k in key(x.get("text", "")).split()
                                                                                                     or any(ALIASES.get(w) == k for w in key(x.get("text", "")).split()))]
            if len(plain) == 1:
                planner.set_done(plain[0]["id"], True)
                return f"Well done, sir. Marked as done: {plain[0]['text']}."
            return f"I have no open {canonical(subject, known) + ' ' if subject else ''}homework, sir."
        if len(found) > 1 and not subject and not re.search(r"\ball\b", low):
            return "Which one, sir? " + "; ".join(i["text"] for i in found[:5]) + "."
        done = found if re.search(r"\ball\b", low) else found[:1]
        for i in done:
            planner.set_done(i["id"], True)
        return ("Well done, sir. Marked as done: " + "; ".join(i["text"] for i in done) + ".")
    m = re.fullmatch(rf"(?:remove|delete|cancel|forget)\s+(?:my\s+|the\s+)?(?P<s>{SUBJ})?\s*{HW}", low)
    if m:
        found = _find(planner, (m.group("s") or "").strip(), known)
        if not found:
            return "There is no such homework, sir."
        planner.delete("task", found[0]["id"])
        return f"Removed: {found[0]['text']}."
    # ---- new homework ----
    p = parse_add(t)
    if not p:
        return None
    subject = canonical(p["subject"], known) if p["subject"] else ""
    if not p["what"] and not subject:
        return None
    due, day = due_for(subject, p["when"], now, ctx)
    if due is None:
        return str(day)
    task = add(planner, subject, p["what"], due)
    when = say_day(day, now.date())
    lesson = " (your next lesson)" if not p["when"] or re.search(r"next\s+(?:lesson|class|period|course|time)", p["when"], re.I) else ""
    return f"Noted, sir: {task['text']}, due {when}{lesson}."


def sync(planner, items: list[dict], subject_of) -> list[dict]:
    """Classroom assignments [{id, course, title, due, link, done}] into the planner. Returns the ones that were not there before.
    A Classroom item you ticked off in Jarvis stays ticked off; one that disappeared from Classroom (and is not done) goes."""
    new = []
    with planner.lock:
        data = planner.load()
        mine = {t["homework"]["id"]: t for t in data["tasks"] if isinstance(t.get("homework"), dict) and t["homework"].get("source") == "classroom"}
        seen = set()
        for it in items:
            seen.add(it["id"])
            subject = subject_of(it.get("course") or "")
            text = (f"{subject}: {it['title']}" if subject else it["title"])[:200]
            task = mine.get(it["id"])
            if task is None:
                if it.get("done"):
                    continue
                task = {"id": secrets.token_hex(4), "created": time.time(), "has_time": False, "done": False, "notified": True,
                        "homework": {"source": "classroom", "id": it["id"]}}
                data["tasks"].append(task)
                new.append(task)
            task.update({"text": text, "due": it.get("due")})
            task["homework"].update({"subject": subject, "what": it["title"], "link": it.get("link", ""), "course": it.get("course", "")})
            if it.get("done") and not task.get("done"):
                task["done"], task["done_at"] = True, time.time()
        data["tasks"] = [t for t in data["tasks"] if not (isinstance(t.get("homework"), dict) and t["homework"].get("source") == "classroom"
                                                         and t["homework"].get("id") not in seen and not t.get("done"))]
        planner.save(data)
    return new

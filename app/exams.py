"""Exam countdown and revision planner.

An exam is simply a calendar event whose title says so ("Physics test", "Maths exam", "Contrôle d'histoire"), so
exams added any way (by a command, in Settings, by Smart commands, from an imported calendar) all count.
Revision sessions are ordinary to-do tasks called "Revise <subject>", spread over the days that are left.

    upcoming(planner_data, now)                      the exams ahead, soonest first
    plan(planner, exam, now)                         adds the missing revision tasks for one exam
    countdown_text(...)                              "Physics test: in 4 days (Friday 20 November) - 1 of 3 revision sessions done"
    nudges(...)                                      short lines for the briefing and the evening recap
    command(text, planner, study_data, focus_log, now)   the chat commands
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

EXAM_WORD = (r"exams?|tests?|quiz(?:zes)?|finals?|mid-?terms?|mocks?|assessments?|examen|examens|contrôles?|controles?|interros?|interrogations?|épreuves?|epreuves?|"
             r"partiels?|évaluations?|evaluations?|bac|brevet")
EXAM_RE = re.compile(rf"\b(?:{EXAM_WORD})\b", re.I)
NOT_EXAM = re.compile(r"\b(?:eye|blood|driving|covid|hearing|drug|pregnancy|speed|sound|mic|microphone)\s+tests?\b|\btest\s+(?:drive|flight|match)\b", re.I)
OFFSETS = (14, 10, 7, 5, 3, 2, 1)        # days before the exam on which to revise: closer together as it approaches
HORIZON_DAYS = 120
REVISE = "Revise "


def is_exam(title: str) -> bool:
    return bool(EXAM_RE.search(title or "")) and not NOT_EXAM.search(title or "")


def subject_of(title: str) -> str:
    """'Physics test' -> 'Physics';  'Contrôle d'histoire' -> 'histoire';  'Exam' -> 'Exam'."""
    s = EXAM_RE.sub(" ", title or "")
    s = re.sub(r"\b(?:the|my|a|an|de|du|des|d|en|le|la|les|l|mon|ma|on|for|in|of)\b|['’]", " ", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" ,.-:")
    return s or (title or "").strip() or "exam"


def upcoming(planner_data: dict, now: datetime) -> list[dict]:
    out = []
    for event in planner_data.get("events", []):
        start = event.get("start") or 0
        if is_exam(event.get("title", "")) and now.timestamp() <= start <= now.timestamp() + HORIZON_DAYS * 86400:
            when = datetime.fromtimestamp(start)
            out.append({"id": event["id"], "title": event["title"][:1].upper() + event["title"][1:], "subject": subject_of(event["title"]), "start": start, "days": (when.date() - now.date()).days})
    return sorted(out, key=lambda e: e["start"])


def _same(subject: str, text: str) -> bool:
    """Does this task / quiz topic / focus label belong to the subject?"""
    a = {w for w in re.findall(r"[^\W\d_]{3,}", subject.lower())}
    b = {w for w in re.findall(r"[^\W\d_]{3,}", (text or "").lower())}
    return bool(a) and bool(a & b)


def revision_tasks(planner_data: dict, exam: dict) -> list[dict]:
    return [t for t in planner_data.get("tasks", []) if t.get("text", "").startswith(REVISE) and _same(exam["subject"], t["text"][len(REVISE):])
            and (not t.get("due") or t["due"] <= exam["start"])]


def progress(exam: dict, planner_data: dict, study_data: dict | None = None, focus_log: list | None = None) -> dict:
    tasks = revision_tasks(planner_data, exam)
    since = exam["start"] - 30 * 86400
    quizzes = [s for s in (study_data or {}).get("sessions", []) if s.get("at", 0) >= since and _same(exam["subject"], s.get("topic", ""))]
    minutes = sum(int(f.get("minutes", 0)) for f in (focus_log or []) if f.get("at", 0) >= since and _same(exam["subject"], f.get("label", "")))
    return {"done": sum(1 for t in tasks if t.get("done")), "planned": len(tasks), "quizzes": len(quizzes), "focus_minutes": minutes}


def session_days(exam_day: date, today: date) -> list[date]:
    days = [exam_day - timedelta(days=o) for o in OFFSETS if exam_day - timedelta(days=o) >= today]
    return days or [today]


def plan(planner, exam: dict, now: datetime, hour: int = 18, per_day: int = 2) -> list[date]:
    """Adds the revision tasks this exam still lacks. Returns the days that were added (empty when the plan is already there)."""
    data = planner.load()
    exam_day = datetime.fromtimestamp(exam["start"]).date()
    mine = {datetime.fromtimestamp(t["due"]).date() for t in revision_tasks(data, exam) if t.get("due")}
    load: dict[date, int] = {}
    for t in data.get("tasks", []):
        if t.get("text", "").startswith(REVISE) and t.get("due") and not t.get("done"):
            d = datetime.fromtimestamp(t["due"]).date()
            load[d] = load.get(d, 0) + 1
    added = []
    for day in session_days(exam_day, now.date()):
        if day in mine:
            continue
        if load.get(day, 0) >= per_day:                    # that evening is full: the nearest free day before the exam instead
            options = sorted((d for d in (now.date() + timedelta(days=i) for i in range((exam_day - now.date()).days + 1))
                              if d not in mine and load.get(d, 0) < per_day and (d < exam_day or exam_day == now.date())), key=lambda d: abs((d - day).days))
            if not options:
                continue
            day = options[0]
        at = datetime.combine(day, datetime.min.time()).replace(hour=hour)
        if at <= now:
            at = now + timedelta(hours=1)
            if at.timestamp() >= exam["start"]:
                continue
        planner.add_task(f"{REVISE}{exam['subject']}", at.timestamp(), True)
        mine.add(day)
        load[day] = load.get(day, 0) + 1
        added.append(day)
    return sorted(added)


def _in_days(days: int) -> str:
    return "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days"


def line(exam: dict, prog: dict) -> str:
    when = datetime.fromtimestamp(exam["start"])
    text = f"{exam['title']}: {_in_days(exam['days'])} ({when.strftime('%A')} {when.day} {when.strftime('%B')}"
    text += (f" at {when.strftime('%H:%M')})" if (when.hour, when.minute) != (0, 0) else ")")
    bits = []
    if prog["planned"]:
        bits.append(f"{prog['done']} of {prog['planned']} revision session{'s' if prog['planned'] != 1 else ''} done")
    else:
        bits.append("no revision planned yet")
    if prog["quizzes"]:
        bits.append(f"{prog['quizzes']} quiz{'zes' if prog['quizzes'] != 1 else ''}")
    if prog["focus_minutes"]:
        bits.append(f"{prog['focus_minutes']} min of focus")
    return text + " — " + ", ".join(bits)


def countdown_text(planner_data: dict, study_data: dict | None, focus_log: list | None, now: datetime) -> str:
    exams = upcoming(planner_data, now)
    if not exams:
        return "You have no exams or tests in your calendar, sir. Tell me one, for example “my chemistry exam is on 3 December at 9am”."
    lines = [f"You have {len(exams)} exam{'s' if len(exams) != 1 else ''} coming up, sir:"]
    lines += ["• " + line(e, progress(e, planner_data, study_data, focus_log)) for e in exams[:10]]
    if any(not progress(e, planner_data)["planned"] for e in exams):
        lines.append("Say “plan my revision” and I will spread revision sessions over the days left.")
    return "\n".join(lines)


def nudges(planner_data: dict, study_data: dict | None, focus_log: list | None, now: datetime, within: int = 7) -> list[str]:
    out = []
    for e in upcoming(planner_data, now):
        if e["days"] <= within:
            p = progress(e, planner_data, study_data, focus_log)
            out.append(f"{e['title']} {_in_days(e['days'])}: " + (f"{p['done']} of {p['planned']} revision sessions done" if p["planned"] else "no revision planned yet") + ".")
    return out[:4]


def _when(x) -> str:
    """A day, or (from the study coach) a day and a time."""
    text = f"{x.strftime('%a')} {x.day} {x.strftime('%b')}"
    return text + (f" {x.strftime('%H:%M')}" if isinstance(x, datetime) else "")


def plan_all(planner, now: datetime, only: str = "", plan_fn=None) -> str:
    exams = [e for e in upcoming(planner.load(), now) if not only or _same(only, e["subject"]) or _same(only, e["title"])]
    if not exams:
        return (f"I found no exam about “{only}” in your calendar, sir." if only
                else "You have no exams or tests in your calendar, sir. Tell me one first, for example “my chemistry exam is on 3 December at 9am”.")
    lines, any_added = [], False
    for e in exams:
        days = (plan_fn or plan)(planner, e, now)
        if days:
            any_added = True
            lines.append(f"• {e['title']} ({_in_days(e['days'])}): revision on " + ", ".join(_when(d) for d in days) + ".")
        else:
            lines.append(f"• {e['title']} ({_in_days(e['days'])}): already planned.")
    head = (("Revision planned, sir, in your free time:" if plan_fn else "Revision planned, sir. The sessions are on your to-do list at 18:00:")
            if any_added else "Your revision is already planned, sir:")
    return head + "\n" + "\n".join(lines) + ("\nSay “quiz me on …” or “focus for 25 minutes on …” when you sit down to revise." if any_added else "")


CLEAN_START = r"^(?:(?:hey\s+)?jarvis[,.:]?\s+)?(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?)?"
WORD = r"(?:exams?|tests?|finals?|mid-?terms?|mocks?|quiz(?:zes)?)"


def command(text: str, planner, study_data: dict | None = None, focus_log: list | None = None, now: datetime | None = None, parse_when=None, resolve=None,
            plan_fn=None) -> str | None:
    now = now or datetime.now()
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = re.sub(CLEAN_START, "", t, flags=re.I)
    t = re.sub(r"\s*(?:please|for me)?\s*[.!?]*$", "", t, flags=re.I).strip()
    if not t or len(t) > 200:
        return None
    low = t.lower()
    if re.fullmatch(rf"(?:exam|test)s?\s+countdown|countdown\s+(?:to|for|of)\s+(?:my\s+)?{WORD}|(?:what|which|when)\s+(?:are|{WORD}\s+do\s+i\s+have)(?:\s+my)?(?:\s+(?:next|upcoming))?(?:\s+{WORD})?(?:\s+coming\s+up)?"
                    rf"|(?:show|list|tell\s+me|give\s+me)(?:\s+me)?\s+(?:my\s+|the\s+)?(?:upcoming\s+|next\s+)?{WORD}|(?:my\s+)?(?:upcoming\s+|next\s+)?{WORD}"
                    rf"|how\s+(?:long|many\s+days|much\s+time)\s+(?:until|till|before|do\s+i\s+have\s+(?:until|before|left\s+(?:until|before)))\s+(?:my\s+|the\s+)?(?:next\s+)?(?:.+\s+)?{WORD}"
                    rf"|when\s+(?:is|are)\s+(?:my\s+|the\s+)?(?:next\s+)?(?:.+\s+)?{WORD}|do\s+i\s+have\s+(?:any\s+)?{WORD}(?:\s+(?:coming\s+up|soon|this\s+week|next\s+week))?", low) \
            and re.search(rf"\b{WORD}\b", low) and not re.match(r"(?:what|which)\s+are\s*$", low):
        return countdown_text(planner.load(), study_data, focus_log, now)
    m = re.fullmatch(rf"(?:plan|schedule|organi[sz]e|sort\s+out|set\s+up|make|create|build)\s+(?:me\s+)?(?:(?:a|my|the)\s+)?revision(?:\s+(?:plan|schedule|timetable|sessions))?"
                     rf"(?:\s+for\s+(?:all\s+)?(?:my|the)\s+(?:(.+?)\s+)?{WORD})?|help\s+me\s+(?:plan|prepare|revise|study)\s+for\s+(?:all\s+)?my\s+{WORD}"
                     rf"|plan\s+(?:for\s+)?(?:all\s+)?my\s+{WORD}", low)
    if m:
        return plan_all(planner, now, (m.group(1) or "").strip() if m.lastindex else "", plan_fn)
    m = re.fullmatch(rf"(?:my|the|our)\s+(.+?)\s+({WORD})\s+(?:is|will\s+be|takes\s+place|happens|got\s+moved\s+to)\s+(.+)", t, re.I)
    if m and parse_when and resolve:
        subject, word = m.group(1).strip(), m.group(2).lower().rstrip("s") or "exam"
        parsed = parse_when(re.sub(r"^(?:on|at)\s+(?=\D)", "on ", m.group(3)), now)
        if parsed.get("date") is None or parsed.get("rest", "").strip():
            return f"When is the {subject} {word}, sir? Tell me the day, for example “my {subject} {word} is on 3 December at 9am”."
        if parsed.get("time") is None:
            parsed = {**parsed, "time": (9, 0)}
        stamp, _ = resolve(parsed, now)
        if stamp < now.timestamp():
            return "That date has already passed, sir."
        title = f"{subject[:1].upper() + subject[1:]} {word}"
        existing = [e for e in planner.load().get("events", []) if e.get("title", "").lower() == title.lower() and e.get("start", 0) >= now.timestamp()]
        if existing:
            planner.delete("event", existing[0]["id"])            # the date changed: keep one entry
        event = planner.add_event(title, stamp)
        exam = {"id": event["id"], "title": title, "subject": subject_of(title), "start": stamp, "days": (datetime.fromtimestamp(stamp).date() - now.date()).days}
        days = (plan_fn or plan)(planner, exam, now)
        when = datetime.fromtimestamp(stamp)
        reply = f"{'Moved' if existing else 'Added'} “{title}” {'to' if existing else 'on'} {when.strftime('%A')} {when.day} {when.strftime('%B')} at {when.strftime('%H:%M')}, sir: {_in_days(exam['days'])}."
        if days:
            reply += ("\nRevision sessions planned in your free time: " + ", ".join(_when(d) for d in days) + "." if plan_fn else
                      "\nRevision sessions added to your to-do list for " + ", ".join(_when(d) for d in days) + " at 18:00.")
        return reply
    return None

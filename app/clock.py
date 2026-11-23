"""The date and the time, read from this PC's clock (an AI model does not know them and tends to guess a year it was trained in).

    command(text, now, parse_when)   "what time is it", "what's the date", "what day is it tomorrow", "what week is it",
                                     "what day is 25 December" ... or None when the message is not such a question
    prompt_line(now)                 one line for the AI model's instructions, so its own answers use the real date too
"""
from __future__ import annotations

import re
import time
from datetime import date, datetime, timedelta

CLEAN = re.compile(r"^(?:(?:hey|ok|okay|yo)\s+)?(?:jarvis[,.:]?\s+)?(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?)?"
                   r"(?:(?:tell|give)\s+me\s+|do\s+you\s+know\s+|i\s+(?:want|need)\s+to\s+know\s+)?", re.I)
NOW = r"(?:\s+(?:now|right\s+now|currently|at\s+the\s+moment|here|exactly|please))*"
TIME = re.compile(rf"(?:what(?:'s|\s+is)\s+the\s+(?:current\s+|exact\s+)?time|what\s+time\s+(?:is\s+it|it\s+is)|(?:the\s+)?(?:current\s+|exact\s+)?time|"
                  rf"what\s+time\s+do\s+we\s+have|how\s+late\s+is\s+it|what(?:'s|\s+is)\s+the\s+clock\s+saying){NOW}", re.I)
DAYWORD = r"(?:today|tomorrow|yesterday|the\s+day\s+after\s+tomorrow|the\s+day\s+before\s+yesterday)"
DATE = re.compile(rf"(?:what(?:'s|\s+is)\s+(?:the\s+|today'?s\s+)?(?:current\s+)?date|(?:the\s+|today'?s\s+)?(?:current\s+)?date|"
                  rf"what\s+(?:day|date)\s+(?:is\s+it|it\s+is|is\s+today|are\s+we|is\s+this)|which\s+day\s+(?:is\s+it|is\s+today|are\s+we)|what(?:'s|\s+is)\s+today|"
                  rf"what(?:'s|\s+is)\s+the\s+date\s+(?:today|{DAYWORD})|what\s+(?:day|date)\s+(?:is|was|will\s+it\s+be|will\s+be)\s+(?:it\s+)?{DAYWORD}|"
                  rf"what\s+(?:day|date)\s+(?:is\s+it|was\s+it|will\s+it\s+be)\s+{DAYWORD}|{DAYWORD}(?:'s)?\s+date)"
                  rf"(?:\s+today)?{NOW}", re.I)
MONTH = re.compile(rf"(?:what|which)\s+month\s+(?:is\s+it|are\s+we\s+in|is\s+this){NOW}", re.I)
YEAR = re.compile(rf"(?:what|which)\s+year\s+(?:is\s+it|are\s+we\s+in|is\s+this){NOW}|what(?:'s|\s+is)\s+the\s+(?:current\s+)?year{NOW}", re.I)
WEEK = re.compile(rf"(?:what|which)\s+week\s+(?:number\s+)?(?:is\s+it|are\s+we\s+in|is\s+this)|what(?:'s|\s+is)\s+the\s+(?:current\s+)?week\s+number|week\s+number{NOW}", re.I)
BOTH = re.compile(rf"what(?:'s|\s+is)\s+the\s+(?:date\s+and\s+(?:the\s+)?time|time\s+and\s+(?:the\s+)?date)|date\s+and\s+time|time\s+and\s+date{NOW}", re.I)
WEEKDAY_OF = re.compile(r"(?:what|which)\s+day(?:\s+of\s+the\s+week)?\s+(?:is|was|will\s+be|falls\s+on)\s+(?P<d>.+?)(?:\s+(?:on|this\s+year|next\s+year))?", re.I)


def long_date(d: date) -> str:
    return f"{d.strftime('%A')} {d.day} {d.strftime('%B')} {d.year}"


def prompt_line(now: datetime | None = None) -> str:
    now = now or datetime.now()
    offset = time.strftime("%z")
    tz = f"UTC{offset[:3]}:{offset[3:]}" if offset else "local time"
    return (f"Right now, by the clock of the user's PC, it is {long_date(now.date())}, {now.strftime('%H:%M')} ({tz}), week {now.isocalendar()[1]}. "
            "Use this for anything about today's date, the time, the year or how long ago or until something is; never assume another date.")


def _rel(word: str, today: date) -> tuple[date, str]:
    w = re.sub(r"\s+", " ", word.lower())
    shift = {"today": 0, "tomorrow": 1, "yesterday": -1, "the day after tomorrow": 2, "the day before yesterday": -2}[w]
    return today + timedelta(days=shift), w


def command(text: str, now: datetime | None = None, parse_when=None) -> str | None:
    now = now or datetime.now()
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = CLEAN.sub("", t).strip().rstrip(" ?.!,")
    t = re.sub(r",?\s*(?:sir|jarvis|please)$", "", t, flags=re.I).strip()
    if not t or len(t) > 80:
        return None
    if BOTH.fullmatch(t):
        return f"It is {now.strftime('%H:%M')} on {long_date(now.date())}, sir."
    if TIME.fullmatch(t):
        return f"It is {now.strftime('%H:%M')}, sir."
    m = DATE.fullmatch(t)
    if m:
        rel = re.search(r"the\s+day\s+after\s+tomorrow|the\s+day\s+before\s+yesterday|tomorrow|yesterday", t, re.I)
        if rel:
            day, word = _rel(rel.group(0), now.date())
            verb = "is" if word == "today" else "was" if "yesterday" in word else "will be"
            return f"{word[0].upper() + word[1:]} {verb} {long_date(day)}, sir."
        return f"Today is {long_date(now.date())}, sir."
    if MONTH.fullmatch(t):
        return f"It is {now.strftime('%B')} {now.year}, sir."
    if YEAR.fullmatch(t):
        return f"It is {now.year}, sir."
    if WEEK.fullmatch(t):
        return f"It is week {now.isocalendar()[1]} of {now.isocalendar()[0]}, sir."
    m = WEEKDAY_OF.fullmatch(t)
    if m and parse_when:
        what = m.group("d").strip()
        if re.fullmatch(DAYWORD, what, re.I):
            day, word = _rel(what, now.date())
            return f"{word[0].upper() + word[1:]} {'is' if word == 'today' else 'was' if 'yesterday' in word else 'will be'} a {day.strftime('%A')}, sir."
        try:
            parsed = parse_when(what, now)
        except Exception:
            return None
        day = parsed.get("date") if isinstance(parsed, dict) else None
        if day is None or (parsed.get("rest") or "").strip(" ,.the"):
            return None
        if re.search(r"\bwas\b", t, re.I) and day > now.date() and not re.search(r"\b(?:19|20)\d{2}\b", what):
            try:
                day = day.replace(year=day.year - 1)              # “what day was 1 November”: the last one
            except ValueError:
                pass
        verb = "is" if day == now.date() else "was" if day < now.date() else "will be"
        return f"{day.day} {day.strftime('%B')} {day.year} {verb} a {day.strftime('%A')}, sir."
    return None

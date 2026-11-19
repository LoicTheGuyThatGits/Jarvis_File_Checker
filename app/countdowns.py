"""Countdowns: "how many days until the Christmas vacation?"

Your own countdowns are kept in data/countdowns.json: a name and a day ("my birthday on 3 March"), or a first and last day for
a holiday ("the Christmas vacation from 19 December to 4 January"). A question finds, in this order: one of your countdowns,
a well-known day (Christmas, New Year, Easter, Halloween, the weekend…), an event in your calendar ("my dentist appointment"),
or a plain date ("25 December", "Friday").

    Countdowns(path)                 .items(today) .add(name, start, end, mine) .remove(name)
    parse_add(text, now, parse_when) {"name", "start", "end", "mine"} for an "add a countdown" sentence, or an error message
    command(text, store, events, now, parse_when)   the reply, or None when the message is not about countdowns
"""
from __future__ import annotations

import json
import re
import secrets
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

MAX_ITEMS = 100
KEEP_AFTER_DAYS = 30            # a countdown that ended more than this long ago is forgotten
HOLIDAY_WORDS = r"(?:vacations?|holidays?|hols|break|half[- ]term|vacances|ski\s+week|spring\s+break|summer|term)"
SYNONYMS = {"holiday": "vacation", "holidays": "vacation", "vacations": "vacation", "hols": "vacation", "break": "vacation", "vacances": "vacation",
            "xmas": "christmas", "noël": "christmas", "noel": "christmas", "pâques": "easter", "paques": "easter", "anniversaire": "birthday",
            "bday": "birthday", "b-day": "birthday", "été": "summer", "ete": "summer", "toussaint": "autumn", "fall": "autumn", "février": "february",
            "trip": "trip", "voyage": "trip", "nouvel": "new", "an": "year", "years": "year"}
STOP = {"the", "my", "our", "a", "an", "of", "de", "la", "le", "les", "des", "du", "d", "l", "mes", "mon", "ma", "to", "for", "next", "this", "day", "s"}
CLEAN_START = r"^(?:(?:hey\s+)?jarvis[,.:]?\s+)?(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?)?(?:tell\s+me\s+)?"


def tokens(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[^\W_]+(?:'[^\W_]+)?", (text or "").lower()):
        w = re.sub(r"'s$", "", w)
        w = SYNONYMS.get(w, w)
        if w and w not in STOP:
            out.append(w)
    return out


def easter(year: int) -> date:
    """Western Easter Sunday (the anonymous Gregorian algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


# well-known days: (words that name it, how it is said, the date in a given year)
KNOWN_DAYS = [
    (("christmas", "eve"), "Christmas Eve", lambda y: date(y, 12, 24)),
    (("christmas",), "Christmas", lambda y: date(y, 12, 25)),
    (("boxing",), "Boxing Day", lambda y: date(y, 12, 26)),
    (("new", "year", "eve"), "New Year's Eve", lambda y: date(y, 12, 31)),
    (("new", "year"), "New Year's Day", lambda y: date(y, 1, 1)),
    (("easter",), "Easter", easter),
    (("valentine",), "Valentine's Day", lambda y: date(y, 2, 14)),
    (("halloween",), "Halloween", lambda y: date(y, 10, 31)),
]


def say_date(d: date) -> str:
    return f"{d.strftime('%A')} {d.day} {d.strftime('%B')}" + ("" if d.year == date.today().year or d.year == date.today().year + 1 and d.month < date.today().month else f" {d.year}")


def plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def spoken(name: str, mine: bool) -> str:
    """'the Christmas vacation', 'your birthday', 'Easter', "Lucas's party"."""
    if mine:
        return "your " + name
    if "'" in name or (name[:1].isupper() and len(name.split()) == 1):
        return name
    return "the " + name


def cap(text: str) -> str:
    return text[:1].upper() + text[1:]


PROPER = {"christmas": "Christmas", "easter": "Easter", "halloween": "Halloween", "valentine's": "Valentine's", "valentines": "Valentine's", "xmas": "Christmas",
          "noël": "Noël", "noel": "Noël", "pâques": "Pâques", "toussaint": "Toussaint", "new year": "New Year", "new year's": "New Year's"}


def tidy_name(name: str) -> str:
    """'christmas holidays' -> 'Christmas holidays'; other words are kept as they were typed."""
    out = re.sub(r"\bnew year(?:'s)?\b", lambda m: PROPER[m.group(0).lower()], name, flags=re.I)
    return re.sub(r"[^\W\d_]+(?:'s)?", lambda m: PROPER.get(m.group(0).lower(), m.group(0)), out)


PLURAL_WORDS = ("holidays", "vacations", "hols", "vacances", "exams", "finals", "holidays,")


def plural_name(name: str) -> bool:
    last = (name.split() or [""])[-1]
    return any(w.lower() in PLURAL_WORDS for w in name.split()) or (last.endswith("s") and last.islower() and not last.endswith(("ss", "'s")) and last not in ("christmas", "paris"))


def be(name: str, present: str = "is") -> str:
    return {"is": "are", "has": "have", "was": "were"}[present] if plural_name(name) else present


class Countdowns:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock = threading.Lock()

    def _load(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            items = data.get("items") if isinstance(data, dict) else None
        except (OSError, ValueError):
            items = None
        out = []
        for it in items or []:
            try:
                start = date.fromisoformat(it["start"])
                end = date.fromisoformat(it["end"]) if it.get("end") else None
                out.append({"id": str(it.get("id") or secrets.token_hex(4)), "name": str(it["name"])[:60], "start": start, "end": end, "mine": bool(it.get("mine"))})
            except (KeyError, TypeError, ValueError):
                continue
        return out

    def _save(self, items: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"items": [{"id": i["id"], "name": i["name"], "start": i["start"].isoformat(), "end": i["end"].isoformat() if i["end"] else None,
                                              "mine": i["mine"]} for i in items]}, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def items(self, today: date | None = None) -> list[dict]:
        """Soonest first; ones that ended more than a month before `today` are left out. Only those that ended more than a month
        before the real date are deleted from the file (asking about a day in the future must not delete anything)."""
        today = today or date.today()
        real = date.today()
        with self.lock:
            items = self._load()
            keep = [i for i in items if (i["end"] or i["start"]) >= real - timedelta(days=KEEP_AFTER_DAYS)]
            if len(keep) != len(items):
                self._save(keep)
        shown = [i for i in keep if (i["end"] or i["start"]) >= today - timedelta(days=KEEP_AFTER_DAYS)]
        return sorted(shown, key=lambda i: (i["start"], i["name"].lower()))

    def add(self, name: str, start: date, end: date | None = None, mine: bool = False) -> tuple[dict, bool]:
        """(the countdown, True when it replaced one with the same name)."""
        name = re.sub(r"\s+", " ", name).strip(" .,:;-")[:60]
        if not name:
            raise ValueError("A countdown needs a name.")
        if end is not None and end < start:
            raise ValueError("The last day is before the first day.")
        with self.lock:
            items = self._load()
            same = [i for i in items if set(tokens(i["name"])) == set(tokens(name))]
            items = [i for i in items if i not in same]
            if end is None and same and same[0]["end"] and same[0]["end"] >= start:
                end = same[0]["end"]                                   # "the holidays start on 19 December": the last day stays
            if len(items) >= MAX_ITEMS:
                raise ValueError(f"You already have {MAX_ITEMS} countdowns; remove some first.")
            item = {"id": same[0]["id"] if same else secrets.token_hex(4), "name": same[0]["name"] if same else tidy_name(name), "start": start, "end": end,
                    "mine": same[0]["mine"] if same else mine}
            items.append(item)
            self._save(items)
        return item, bool(same)

    def remove(self, name_or_id: str) -> dict | None:
        with self.lock:
            items = self._load()
            hit = next((i for i in items if i["id"] == name_or_id), None) or best(name_or_id, items)
            if hit is None:
                return None
            self._save([i for i in items if i["id"] != hit["id"]])
            return hit


def best(target: str, items: list[dict]) -> dict | None:
    """The countdown a phrase means: the same words first, then one whose name contains all the words asked about."""
    want = set(tokens(target))
    if not want:
        return None
    exact = [i for i in items if set(tokens(i["name"])) == want]
    if exact:
        return exact[0]
    part = [i for i in items if want <= set(tokens(i["name"])) or set(tokens(i["name"])) <= want]
    return part[0] if len(part) == 1 else (sorted(part, key=lambda i: i["start"])[0] if part else None)


EXTRA_OK = {"sunday", "monday", "morning", "night"}            # "Easter Sunday", "Christmas morning"; "Christmas vacation" is not Christmas


def known_day(target: str, today: date) -> dict | None:
    want = set(tokens(target))
    for words, name, when in KNOWN_DAYS:
        if set(words) <= want and want - set(words) <= EXTRA_OK:
            day = when(today.year)
            if day < today:
                day = when(today.year + 1)
            return {"name": name, "start": day, "end": None, "mine": False, "proper": True}
    if want == {"weekend"}:
        return {"name": "weekend", "start": today + timedelta(days=(5 - today.weekday()) % 7), "end": today + timedelta(days=(6 - today.weekday()) % 7), "mine": False}
    return None


def calendar_event(target: str, events: list[dict], now: datetime) -> dict | None:
    want = set(tokens(target)) - {"appointment", "event", "meeting"} or set(tokens(target))
    if not want:
        return None
    hits = [e for e in events if e.get("start", 0) >= now.timestamp() - 3600 and want <= set(tokens(e.get("title", "")))]
    if not hits:
        return None
    e = min(hits, key=lambda e: e["start"])
    when = datetime.fromtimestamp(e["start"])
    return {"name": e["title"], "start": when.date(), "end": None, "mine": False, "at": when, "event": True}


def find(target: str, items: list[dict], events: list[dict], now: datetime, parse_when=None) -> dict | None:
    today = now.date()
    want = set(tokens(target))
    mine = [i for i in items if (i["end"] or i["start"]) >= today]
    for i in mine:
        if set(tokens(i["name"])) == want:
            return i
    day = known_day(target, today)
    if day:
        return day
    hit = best(target, mine)
    if hit:
        return hit
    hit = calendar_event(target, events, now)
    if hit:
        return hit
    if parse_when:
        parsed = parse_when(target, now)
        if parsed.get("date") and not parsed.get("rest", "").strip():
            return {"name": say_date(parsed["date"]), "start": parsed["date"], "end": None, "mine": False, "proper": True, "plain": True}
    return best(target, items)                                          # one that has already passed: say so


def answer(found: dict, now: datetime, unit: str = "days", style: str = "until") -> str:
    """'31 days until the Christmas vacation, sir: it starts on Saturday 19 December and lasts until Monday 4 January.'"""
    today = now.date()
    name = found["name"] if found.get("proper") or found.get("event") else spoken(found["name"], found.get("mine", False))
    if found.get("event"):
        name = "“" + found["name"] + "”"
    start, end = found["start"], found.get("end")
    days = (start - today).days
    if end and start <= today <= end:
        left = (end - today).days
        if found["name"] == "weekend":
            return "It is the weekend, sir." + (" Tomorrow is Sunday." if left else " Enjoy what is left of it.")
        if left == 0:
            return f"Today is the last day of {name}, sir."
        return f"{cap(name)} {be(name)} on now, sir: {plural(left, 'more day')} after today, until {say_date(end)}."
    if days < 0:
        return f"{cap(name)} {be(name, 'was')} on {say_date(end or start)}; {'they have' if plural_name(name) else 'it has'} passed, sir."
    at = found.get("at")
    if at is not None and 0 <= (at - now).total_seconds() < 36 * 3600 and (at.hour, at.minute) != (8, 0):
        mins = int((at - now).total_seconds() // 60)
        span = f"{plural(mins // 60, 'hour')} and {plural(mins % 60, 'minute')}" if mins >= 60 else plural(mins, "minute")
        return f"{cap(name)} is in {span}, sir, at {at.strftime('%H:%M')}" + (" today." if at.date() == today else " tomorrow.")
    clock = f" at {at.strftime('%H:%M')}" if at is not None and (at.hour, at.minute) != (8, 0) else ""
    if found["name"] == "weekend":
        return "The weekend starts tomorrow, sir." if days == 1 else f"{plural(days, 'day')} until the weekend, sir."
    if days == 0:
        return f"{cap(name)} {be(name)} today{clock}, sir." if not found.get("plain") else "That is today, sir."
    if days == 1:
        return f"{cap(name)} {be(name)} tomorrow{clock}, sir." if not found.get("plain") else "That is tomorrow, sir."
    if style == "when" and not found.get("plain"):
        if end:
            return f"{cap(name)} {be(name)} from {say_date(start)} to {say_date(end)}, sir: {'they start' if plural_name(name) else 'it starts'} in {days} days."
        return f"{cap(name)} {be(name)} on {say_date(start)}{clock}, sir: in {days} days."
    if unit == "weeks":
        w, r = divmod(days, 7)
        head = f"{plural(w, 'week')}" + (f" and {plural(r, 'day')}" if r else "") + f" ({days} days)"
    elif unit == "months":
        head = f"About {plural(round(days / 30.44), 'month')} ({days} days)" if days >= 45 else f"{days} days"
    elif unit == "sleeps":
        head = plural(days, "sleep")
    else:
        head = f"{days} days"
    head += f" until {name}, sir"
    if found.get("plain"):
        return head + "."
    if end:
        return f"{head}: {'they start' if plural_name(name) else 'it starts'} on {say_date(start)} and {'last' if plural_name(name) else 'lasts'} until {say_date(end)}."
    extra = f" That is {plural(days // 7, 'week')} and {plural(days % 7, 'day')}." if unit == "days" and days >= 21 and days % 7 else (f" That is exactly {plural(days // 7, 'week')}." if unit == "days" and days >= 21 else "")
    return f"{head}: {say_date(start)}{clock}.{extra}"


# ---------------- understanding the messages ----------------
QUESTION = re.compile(
    r"(?:how\s+many\s+(?P<unit>days|weeks|months|sleeps)|how\s+long)\s+(?:is\s+(?:it|there)\s+|are\s+there\s+(?:still\s+)?|(?:do|have)\s+(?:i|we)\s+(?:got\s+|have\s+|still\s+have\s+)?(?:left\s+)?|remain\s+|(?:are\s+)?left\s+|to\s+go\s+)?"
    r"(?:left\s+|to\s+go\s+)?(?:until|till|til|'til|before|to)\s+(?P<target>.+)"
    r"|(?P<unit2>days|weeks)\s+(?:left\s+)?(?:until|till|to|before)\s+(?P<target2>.+)"
    r"|countdown\s+(?:to|until|for)\s+(?P<target3>.+)"
    r"|how\s+many\s+days\s+(?:are\s+)?left\s+(?:of|in)\s+(?P<target4>.+)", re.I)
WHEN = re.compile(r"when\s+(?:is|are|does|do)\s+(?P<target>.+?)(?:\s+(?:start|starts|begin|begins|happen))?", re.I)
ADD = re.compile(
    r"(?:add|create|make|set(?:\s+up)?|start|put|new)\s+(?:me\s+)?(?:a\s+|an\s+)?count\s*-?\s*down\s*(?:for|to|until|till|:)?\s+(?P<a>.+)"
    r"|count\s*down\s+(?:to|until|till)\s+(?P<b>.+)"
    r"|add\s+(?P<c>.+?)\s+to\s+(?:my\s+|the\s+)?countdowns?"
    rf"|(?P<d>(?:my\s+|the\s+|our\s+)?[\w' -]*?\b{HOLIDAY_WORDS}\b[\w' -]*?)\s+(?:is|are|will\s+be|runs?|go(?:es)?|starts?|begins?|will\s+start|start(?:s)?\s+on)\s+(?P<dwhen>(?:on\s+|from\s+|the\s+|in\s+)?.*\d.*)", re.I)
LIST = re.compile(r"(?:(?:show|list|read|give|tell)(?:\s+me)?\s+(?:all\s+)?(?:my|the)\s+countdowns|(?:my|all\s+(?:my\s+)?|the)\s+countdowns|countdowns|what\s+countdowns\s+do\s+i\s+have|what\s+am\s+i\s+counting\s+down\s+to)", re.I)
REMOVE = re.compile(r"(?:delete|remove|cancel|clear|drop|forget)\s+(?:the\s+|my\s+)?(?:countdown\s+(?:for|to|until)\s+(?P<a>.+)|(?P<b>.+?)\s+countdown)", re.I)


def clean(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = re.sub(CLEAN_START, "", t, flags=re.I)
    return re.sub(r"\s*(?:please|for me)?\s*[.!?]*$", "", t, flags=re.I).strip()


def strip_name(name: str) -> tuple[str, bool]:
    n = re.sub(r"\s+", " ", name).strip(" ,.;:-\"'“”")
    mine = bool(re.match(r"(?:my|mes|mon|ma)\s+", n, re.I))
    n = re.sub(r"^(?:my|the|our|a|an|les|la|le|mes|mon|ma|nos|notre)\s+|^l['’]", "", n, flags=re.I).strip()
    n = re.sub(r"\s+(?:countdown|starts?|begins?)$", "", n, flags=re.I).strip()
    return n, mine


def example(name: str, mine: bool) -> str:
    """A sentence the user could say to add this countdown."""
    who = "my " if mine else "the "
    if re.search(HOLIDAY_WORDS, name, re.I):
        low = name.lower()
        span = "19 December to 4 January" if "christmas" in low or "noël" in low else "4 July to 21 August" if "summer" in low or "été" in low else "13 February to 21 February"
        return f"add a countdown for {who}{tidy_name(name)} from {span}"
    return f"add a countdown for {who}{tidy_name(name)} on 3 March"


def parse_add(text: str, now: datetime, parse_when) -> dict | str | None:
    """{"name", "start", "end", "mine"}, or a sentence saying what is missing, or None when this is not an add request."""
    t = clean(text)
    m = ADD.fullmatch(t)
    if not m:
        return None
    if m.group("d"):
        rest = m.group("d") + " " + m.group("dwhen")
    else:
        rest = m.group("a") or m.group("b") or m.group("c")
    if re.fullmatch(r"(?:for\s+)?(?:\d+|an?|one|half)\b.*\b(?:seconds?|secs?|minutes?|mins?|hours?|hrs?)", rest.strip(), re.I):
        return None                                                     # "start a countdown for 10 minutes" is a timer
    name, start, end = None, None, None
    one_date = r"(?:\d{1,2}(?:st|nd|rd|th)?\s+[a-z]+|[a-z]+\s+\d{1,2}(?:st|nd|rd|th)?|\d{1,2}/\d{1,2}(?:/\d{2,4})?|\d{4}-\d{2}-\d{2})"
    rng = (re.search(r"\bfrom\s+(?P<s>.+?)\s+(?:to|until|till|through|thru|-|–|—)\s+(?P<e>.+)$", rest, re.I)
           or re.search(rf"(?P<s>\b{one_date})\s*(?:to|until|till|through|thru|-|–|—)\s*(?P<e>.+)$", rest, re.I))
    if rng:
        first, second = parse_when(rng.group("s"), now), parse_when(rng.group("e"), now)
        if first.get("date") and not first.get("rest", "").strip() and second.get("date") and not second.get("rest", "").strip():
            start, end = first["date"], second["date"]
            if end < start:
                try:
                    end = end.replace(year=end.year + 1)
                except ValueError:
                    end = end + timedelta(days=365)
            name = re.sub(r"\s+(?:is|are|runs?|goes|starts?|begins?|on|from)\s*$", "", rest[:rng.start()].strip(" ,:;-"), flags=re.I)
    if start is None:
        parsed = parse_when(rest, now)
        start = parsed.get("date")
        name = parsed.get("rest", "")
        if start is None and parsed.get("time") and not name.strip():
            return None                                                 # "set a countdown for 5pm": a timer
        name = re.sub(r"\s+(?:is|are|runs?|goes|starts?|begins?|on|at)\s*$", "", name.strip(), flags=re.I)
    name, mine = strip_name(name or "")
    if not name:
        return "What is the countdown for, sir? For example: “add a countdown for the Christmas vacation from 19 December to 4 January”."
    if start is None:
        return f"When is {spoken(tidy_name(name), mine)}, sir? For example: “{example(name, mine)}”."
    return {"name": name, "start": start, "end": end, "mine": mine}


def command(text: str, store: Countdowns, events: list[dict], now: datetime | None = None, parse_when=None) -> str | None:
    now = now or datetime.now()
    t = clean(text)
    if not t or len(t) > 200:
        return None
    if LIST.fullmatch(t):
        items = [i for i in store.items(now.date()) if (i["end"] or i["start"]) >= now.date()]
        if not items:
            return "You have no countdowns yet, sir. Add one with, for example, “add a countdown for the Christmas vacation from 19 December to 4 January”."
        return "Your countdowns, sir:\n" + "\n".join("- " + answer(i, now).replace(", sir", "") for i in items)
    m = REMOVE.fullmatch(t)
    if m:
        name = (m.group("a") or m.group("b") or "").strip()
        if not name or re.fullmatch(r"(?:the\s+)?(?:timer|alarm|reminder)s?", name, re.I):
            return None
        gone = store.remove(name)
        if gone is None:
            return None if not store.items(now.date()) else f"I have no countdown called “{strip_name(name)[0]}”, sir. Say “my countdowns” to see them."
        return f"Removed the countdown for {spoken(gone['name'], gone['mine'])}, sir."
    if parse_when is not None:
        req = parse_add(t, now, parse_when)
        if isinstance(req, str):
            return req
        if req:
            if (req["end"] or req["start"]) < now.date():
                return "That date has already passed, sir."
            item, replaced = store.add(req["name"], req["start"], req["end"], req["mine"])
            head = f"{'Updated' if replaced else 'Added'} the countdown for {spoken(item['name'], item['mine'])}, sir. "
            return head + answer(item, now).replace(", sir", "", 1)
    m = QUESTION.fullmatch(t)
    if m:
        target = m.group("target") or m.group("target2") or m.group("target3") or m.group("target4")
        unit = (m.group("unit") or m.group("unit2") or "days").lower()
        ongoing = bool(m.group("target4"))
        target = re.sub(r"\s+(?:starts?|begins?|is|are|comes?|arrives?|from\s+now|from\s+today)$", "", target.strip(), flags=re.I)
        if re.search(r"\b(?:exams?|tests?|finals?|mocks?)\b", target, re.I) and not best(target, store.items(now.date())):
            return None                                                # the exam countdown answers those
        found = find(target, store.items(now.date()), events, now, parse_when)
        if found is None:
            if m.group("unit") or m.group("unit2") or m.group("target3"):
                name, mine = strip_name(target)
                return f"I do not have a date for {spoken(tidy_name(name), mine)}, sir. Tell me when it is, for example: “{example(name, mine)}”."
            return None                                                # "how long until …" about something else: the AI answers
        if ongoing and not (found.get("end") and found["start"] <= now.date() <= found["end"]):
            if found["start"] > now.date():
                said = spoken(found["name"], found.get("mine", False))
                return f"{cap(said)} {be(said, 'has')} not started yet, sir. " + answer(found, now, unit).replace(", sir", "", 1)
        return answer(found, now, unit)
    m = WHEN.fullmatch(t)
    if m:
        items = store.items(now.date())
        target = m.group("target")
        want = set(tokens(target))
        hit = next((i for i in items if set(tokens(i["name"])) == want), None) or best(target, items)
        found = hit or known_day(target, now.date())
        if found is None:
            return None                                                 # the calendar or the AI answers
        return answer(found, now, style="when")
    return None


def soon(store: Countdowns, now: datetime, within: int = 7) -> list[str]:
    """Lines for the morning briefing: countdowns that start within a week (and the last day of one that is on)."""
    out, today = [], now.date()
    for i in store.items(today):
        name = spoken(i["name"], i["mine"])
        days = (i["start"] - today).days
        verb = "start" if plural_name(name) else "starts"
        if days == 0:
            out.append(f"{cap(name)} {verb} today.")
        elif 0 < days <= within:
            out.append(f"{cap(name)} {verb} {'tomorrow' if days == 1 else f'in {days} days'}.")
        elif i["end"] and i["end"] == today and days < 0:
            out.append(f"Today is the last day of {name}.")
    return out


def public(store: Countdowns, now: datetime) -> list[dict]:
    """For the page: each countdown with its days left and its sentence."""
    today = now.date()
    out = []
    for i in store.items(today):
        days = (i["start"] - today).days
        on = bool(i["end"] and i["start"] <= today <= i["end"])
        out.append({"id": i["id"], "name": i["name"], "start": i["start"].isoformat(), "end": i["end"].isoformat() if i["end"] else None, "mine": i["mine"],
                    "days": days, "on": on, "left": (i["end"] - today).days if on else None, "past": (i["end"] or i["start"]) < today,
                    "text": answer(i, now).replace(", sir", "", 1)})
    return out

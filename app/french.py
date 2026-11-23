"""French commands: rewrites a French request into the English command Jarvis's built-in commands understand.

    to_english("rappelle-moi d'appeler maman demain à 18h")  ->  "remind me to appeler maman tomorrow at 18:00"
    to_english("explique la photosynthèse")                  ->  None   (not a command: the chat model answers it)

Only the command words and the date words are translated; what you want noted, added or searched stays as you
wrote it. Anything that is not clearly one of the known commands is left alone.
"""
from __future__ import annotations

import re
from datetime import datetime

DAYS = {"lundi": "monday", "mardi": "tuesday", "mercredi": "wednesday", "jeudi": "thursday", "vendredi": "friday", "samedi": "saturday", "dimanche": "sunday"}
MONTHS = {"janvier": "january", "février": "february", "fevrier": "february", "mars": "march", "avril": "april", "mai": "may", "juin": "june", "juillet": "july",
          "août": "august", "aout": "august", "septembre": "september", "octobre": "october", "novembre": "november", "décembre": "december", "decembre": "december"}
NUMBERS = {"un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "quinze": 15, "vingt": 20,
           "vingt-cinq": 25, "trente": 30, "quarante": 40, "quarante-cinq": 45, "cinquante": 50, "soixante": 60}
NUM = r"(\d+|" + "|".join(sorted(NUMBERS, key=len, reverse=True)) + r")"
UNITS = [(r"secondes?|sec|s", "seconds"), (r"minutes?|min|mn", "minutes"), (r"heures?|h", "hours"), (r"jours?|j", "days"), (r"semaines?", "weeks")]
MONTH_RE = "|".join(MONTHS)
DAY_RE = "|".join(DAYS)
# words that start a date or time, used to split "what" from "when"
WHEN_START = (rf"(?:aujourd['’]hui|demain|après[- ]demain|apres[- ]demain|ce\s+(?:soir|matin|midi|week-?end)|cet(?:te)?\s+(?:après-midi|apres-midi|aprèm|nuit|semaine)|"
              rf"(?:pour\s+|avant\s+|d['’]ici\s+|jusqu['’]à\s+)?(?:(?:ce\s+|le\s+)?(?:{DAY_RE})\b|le\s+\d{{1,2}}(?:er)?\b|la\s+semaine\s+prochaine|demain|aujourd['’]hui|ce\s+soir)|"
              rf"(?:à|a|vers)\s+(?:\d{{1,2}}\s*(?:h|heures?|:)|midi|minuit)|dans\s+{NUM}\s|dans\s+(?:une?\s+)?(?:demi|quart)|\d{{1,2}}(?:er)?\s+(?:{MONTH_RE})\b|le\s+\d{{1,2}}/)")


def number(word: str) -> int:
    return int(word) if word.isdigit() else NUMBERS[word.lower()]


def duration(text: str) -> str | None:
    """'10 minutes', 'une heure et demie', 'un quart d'heure', '1h30' -> English, or None."""
    t = text.strip().lower()
    m = re.fullmatch(r"(\d{1,2})\s*h\s*(\d{1,2})", t)
    if m:
        return f"{int(m.group(1))} hours {int(m.group(2))} minutes"
    if re.fullmatch(r"(?:une?\s+)?demi[- ]heure", t):
        return "30 minutes"
    if re.fullmatch(r"(?:un\s+)?quart\s+d['’]heure", t):
        return "15 minutes"
    if re.fullmatch(r"trois\s+quarts?\s+d['’]heure", t):
        return "45 minutes"
    m = re.fullmatch(rf"{NUM}\s*heures?\s+et\s+(?:demie?|quart)", t)
    if m:
        return f"{number(m.group(1))} hours {30 if 'demi' in t else 15} minutes"
    parts, rest = [], t
    while rest:
        m = None
        for pattern, unit in UNITS:
            m = re.match(rf"{NUM}\s*(?:{pattern})\b\s*(?:et\s+|,\s*)?", rest)
            if m:
                parts.append(f"{number(m.group(1))} {unit if number(m.group(1)) != 1 else unit[:-1]}")
                rest = rest[m.end():]
                break
        if not m:
            return None
    return " ".join(parts) or None


def clock(hour: int, minute: int = 0) -> str:
    """French times are on the 24-hour clock; '6:45am' and '18:00' cannot be misread in English."""
    return f"{hour or 12}:{minute:02d}am" if hour < 12 else f"{hour}:{minute:02d}"


def when(text: str, now: datetime | None = None) -> str | None:
    """French date/time words -> the English ones the planner reads. None when something is not understood."""
    now = now or datetime.now()
    t = " " + re.sub(r"\s+", " ", text.strip().lower()) + " "
    out: list[str] = []
    by = bool(re.match(r" (?:pour|avant|d['’]ici|jusqu['’]à) ", t))
    t = re.sub(r"^ (?:pour|avant|d['’]ici|jusqu['’]à) ", " ", t)
    m = re.search(rf" dans (.+?)(?= (?:à|a|vers) |$| $)", t)
    if m and duration(m.group(1).strip()):
        out.append("in " + duration(m.group(1).strip()))
        t = t.replace(m.group(0), " ", 1)
    table = [(r"après[- ]demain|apres[- ]demain", "the day after tomorrow"), (r"demain matin", "tomorrow morning"), (r"demain (?:après-midi|apres-midi|aprèm)", "tomorrow at 15:00"),
             (r"demain soir", "tomorrow evening"), (r"demain", "tomorrow"), (r"ce soir|cette nuit", "tonight"), (r"ce matin", "today at 9:00am"), (r"ce midi", "today at 12:00"),
             (r"cet(?:te)? (?:après-midi|apres-midi|aprèm)", "today at 15:00"), (r"aujourd['’]hui", "today"), (r"la semaine prochaine", "next week"),
             (r"cette semaine", "this week"), (r"ce week-?end", "this weekend")]
    for pattern, english in table:
        if re.search(rf" (?:{pattern}) ", t):
            out.append(english)
            t = re.sub(rf" (?:{pattern}) ", " ", t, count=1)
            break
    m = re.search(rf" (?:le )?(\d{{1,2}})(?:er)? ({MONTH_RE})(?: (\d{{4}}))? ", t)
    if m:
        out.append(f"{int(m.group(1))} {MONTHS[m.group(2)]}" + (f" {m.group(3)}" if m.group(3) else ""))
        t = t.replace(m.group(0), " ", 1)
    m = re.search(r" (?:le )?(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))? ", t)
    if m:
        out.append(f"{int(m.group(1))}/{int(m.group(2))}" + (f"/{m.group(3)}" if m.group(3) else ""))
        t = t.replace(m.group(0), " ", 1)
    m = re.search(rf" (?:ce |le )?({DAY_RE})( prochain)?(?: (matin|soir|après-midi|apres-midi))? ", t)
    if m:
        out.append(("next " if m.group(2) else "") + DAYS[m.group(1)] + {"matin": " at 9:00am", "soir": " at 19:00", "après-midi": " at 15:00", "apres-midi": " at 15:00", None: ""}[m.group(3)])
        t = t.replace(m.group(0), " ", 1)
    m = re.search(r" le (\d{1,2})(?:er)? ", t)
    if m and 1 <= int(m.group(1)) <= 31:                    # "le 20": this month, or the next one when that day has passed
        day, month, year = int(m.group(1)), now.month, now.year
        for _ in range(3):
            try:
                if datetime(year, month, day).date() >= now.date():
                    out.append(f"{day}/{month}/{year}")
                    break
            except ValueError:
                pass
            month, year = (1, year + 1) if month == 12 else (month + 1, year)
        t = t.replace(m.group(0), " ", 1)
    m = re.search(r" (?:à|a|vers|pour) (\d{1,2}) ?(?:h|heures?|:) ?(\d{2})? ", t) or re.search(r" (\d{1,2}) ?h ?(\d{2})? ", t)
    if m and int(m.group(1)) < 24:
        out.append("at " + clock(int(m.group(1)), int(m.group(2) or 0)))
        t = t.replace(m.group(0), " ", 1)
    else:
        m = re.search(r" (?:à |a |vers )?(midi|minuit) ", t)
        if m:
            out.append("at 12:00" if m.group(1) == "midi" else "at 12:00am")
            t = t.replace(m.group(0), " ", 1)
    if t.strip() or not out:
        return None
    return ("by " if by and not out[0].startswith(("in ", "at ")) else "") + " ".join(out)


def split_when(text: str, now: datetime | None = None) -> tuple[str, str]:
    """('appeler maman', 'tomorrow at 18:00') from 'appeler maman demain à 18h'. The date part is '' when there is none."""
    t = text.strip()
    for m in re.finditer(rf"(?:^|\s){WHEN_START}", t, re.IGNORECASE):
        english = when(t[m.start():], now)
        if english:
            return t[:m.start()].strip(" ,"), english
    return t, ""


POLITE_START = (r"^(?:(?:hey\s+|dis\s+|ok\s+)?jarvis[,.:!]?\s+)?(?:s['’]il\s+(?:te|vous)\s+pla[iî]t[,.]?\s+)?"
                r"(?:(?:est-ce\s+que\s+)?(?:tu\s+)?(?:peux|pourrais|veux)(?:-tu)?(?:\s+bien)?\s+|j['’]aimerais\s+que\s+tu\s+|il\s+faudrait\s+)?")
POLITE_END = r"\s*,?\s*(?:s['’]il\s+(?:te|vous)\s+pla[iî]t|stp|svp|merci(?:\s+beaucoup)?|pour\s+moi)?\s*[.!?]*$"
LIST = r"(?:(?:ma|la|une)\s+)?(?:liste(?:\s+de\s+(?:tâches|taches|choses\s+à\s+faire))?|to-?do(?:\s+list)?|tâches|taches|choses\s+à\s+faire)"
CAL = r"(?:(?:mon|l['’]|le|un)\s*)?(?:agenda|calendrier|planning|emploi\s+du\s+temps)"
VERB_ADD = r"(?:ajoute[rz]?|mets?|mettre|rajoute[rz]?|note[rz]?|inscri[ste]|inscrire)"


def _place(text: str) -> str:
    """French place names for the file search: 'ordinateur' -> 'the computer', 'téléchargements' -> 'Downloads', a folder name stays as it is."""
    t = text.strip()
    low = t.lower()
    if re.fullmatch(r"(?:tout\s+)?(?:l['’]\s*|mon\s+)?ordi(?:nateur)?|partout|(?:tous\s+)?(?:les\s+)?disques", low):
        return "the computer"
    m = re.fullmatch(r"(?:le\s+)?(?:disque|lecteur)\s+([a-z])(?::)?", low)
    if m:
        return f"the {m.group(1).upper()} drive"
    return {"bureau": "Desktop", "téléchargements": "Downloads", "telechargements": "Downloads", "images": "Pictures", "vidéos": "Videos", "videos": "Videos",
            "musique": "Music", "documents": "Documents"}.get(low, t)


def _task(m, now):
    what, date = split_when(m.group(1), now)
    if not date and m.lastindex and m.lastindex >= 2 and m.group(2):
        date = when(m.group(2), now) or ""
        if not date:
            return None
    return f"add task: {what} {date}".strip() if what else None


def _event(m, now):
    what, date = split_when(m.group(1), now)
    return f"schedule {what} {date}" if what and date else None


def _remind(m, now):
    what, date = split_when(re.sub(r"^(?:de\s+|d['’]|à\s+|que\s+je\s+dois\s+|qu['’]il\s+faut\s+|pour\s+)", "", m.group(1), flags=re.I), now)
    return f"remind me to {what} {date}" if what and date else None


def _remind_first(m, now):
    date = when(m.group(1), now)
    what = re.sub(r"^(?:de\s+|d['’]|que\s+je\s+dois\s+)", "", m.group(2), flags=re.I)
    return f"remind me to {what} {date}" if date else None


def _timer(m, now):
    span = duration(m.group(1))
    return f"set a timer for {span}" if span else None


def _countdown_text(text: str, now) -> str | None:
    """'les vacances de Noël du 19 décembre au 4 janvier' -> 'add a countdown for les vacances de Noël from 19 december to 4 january'."""
    text = text.strip(" ,.")
    if duration(text):
        return None                                           # "un compte à rebours de 10 minutes" is a timer
    for start in re.finditer(r"\b(?:du|de)\s+", text):              # "les vacances de Noël du 19 au 23 décembre": the "du" that starts a date
        r = re.compile(r"(?:du|de)\s+(.+?)\s+(?:au|à|a|jusqu['’]au)\s+(.+)$").match(text, start.start())
        if not r:
            continue
        first, last = r.group(1).strip(), r.group(2).strip()
        e = when(last, now)
        if re.fullmatch(r"\d{1,2}(?:er)?", first):
            mm = re.search(rf"({MONTH_RE})", last)
            first = f"{first} {mm.group(1)}" if mm else first
        st = when(first, now)
        if st and e:
            return f"add a countdown for {text[:start.start()].strip()} from {st} to {e}"
    name, english = split_when(text, now)
    if english:
        return f"add a countdown for {name} on {english}"
    return f"add a countdown for {text}"


def _countdown(m, now):
    return _countdown_text(m.group(1), now)


def _countdown_statement(m, now):
    return _countdown_text(m.group(1) + " " + m.group(2), now)


def _fr_grade_rest(rest: str | None) -> str:
    rest = (rest or "").lower()
    out = ""
    if re.search(r"coef(?:ficient)?\s*2|double", rest):
        out += ", counts double"
    if "hier" in rest:
        out += " yesterday"
    return out


FR_DAY = r"(demain|aujourd['’]hui|ce\s+matin|cet\s+après-midi|lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)"


def fr_day(word: str | None) -> str:
    w = (word or "").lower().replace("’", "'")
    if not w:
        return ""
    if w == "demain":
        return " tomorrow"
    if w.startswith("aujourd") or w.startswith("ce matin") or w.startswith("cet"):
        return " today"
    return " on " + DAYS.get(w, w)


FR_UNITS = {"jours": "days", "semaines": "weeks", "mois": "months", "dodos": "sleeps", "temps": "days"}
FAMOUS = r"(?:vacances|noël|noel|pâques|paques|nouvel\s+an|réveillon|reveillon|anniversaire|halloween|saint[- ]valentin|week-?end|rentrée|rentree)"


def _agenda(m, now):
    period = when(m.group(1), now) if m.group(1) else "today"
    if not period:
        return None
    period = re.sub(r"\s+at\s+\d{1,2}:\d{2}$|\s+(?:morning|evening)$", "", period)      # the calendar is read per day
    period = {"tonight": "today"}.get(period, period)
    return f"show my calendar for {period}" if re.fullmatch(r"today|tomorrow|this week|next week|this weekend|(?:next )?[a-z]+day", period) else None


def _alarm(m, now):
    date = when(m.group(1), now)
    return f"wake me up {date}" if date else None


def _call(m, now):
    rest = (m.group(1) or "").strip(" ,")
    if not rest or re.fullmatch(r"(?:maintenant|tout\s+de\s+suite|vite)", rest, re.I):
        return "call me"
    if re.fullmatch(r"(?:avec|et\s+(?:lis|donne)[- ]moi)\s+(?:le|mon)\s+(?:briefing|point\s+du\s+matin)", rest, re.I):
        return "call me with the briefing"
    purpose = ""
    p = re.search(r"\s*,?\s*pour\s+(?:me\s+)?(?:r[ée]veiller|lever)\b.*$", rest, re.I)
    if p:
        purpose, rest = " to wake me up", rest[:p.start()]
    else:
        p = re.search(r"\s*,?\s*pour\s+(?:me\s+rappeler\s+(?:de\s+|d['’]|que\s+)?)?(.+)$", rest, re.I)
        if p:
            purpose, rest = " to " + p.group(1).strip(), rest[:p.start()]
    date = when(rest, now)
    return f"call me {date}{purpose}" if date else None


def _wake_call(m, now):
    date = when(m.group(1) or m.group(2) or "", now)
    return f"call me {date} to wake me up" if date else None


def _focus(m, now):
    span = duration(m.group(1)) if m.group(1) else ""
    if m.group(1) and not span:
        return None
    return ("focus for " + span if span else "start a focus session") + (f" on {m.group(2)}" if m.group(2) else "")


def _exam(m, now):
    date = when(m.group(2), now)
    return f"my {m.group(1)} exam is {'on ' if not date.startswith(('tomorrow', 'today', 'next', 'the day')) else ''}{date}" if date else None


EXAM = r"(?:examen|exam|contrôle|controle|interro(?:gation)?|épreuve|epreuve|test|partiel|devoir\s+surveillé|ds|évaluation|evaluation|éval|eval)"
HW_SUBJ = r"[a-zà-ÿ][\w'’ .&-]{0,30}?"
HW_WHEN = r"(?:le\s+)?prochain\s+cours|la\s+prochaine\s+fois|demain|après[- ]demain|apres[- ]demain|la\s+semaine\s+prochaine|(?:ce\s+|le\s+)?(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)(?:\s+prochain)?|le\s+\d{1,2}(?:er)?(?:\s+[a-zéû]+)?|\d{1,2}[./]\d{1,2}"


def _hw_when(text, now):
    if not text:
        return ""
    if re.search(r"prochain\s+cours|prochaine\s+fois", text):
        return "next lesson"
    return when(text, now) or ""


def _homework(m, now):
    due = _hw_when(m.group(2) or m.group(4), now)
    if (m.group(2) or m.group(4)) and not due:
        return None
    return f"{m.group(1).strip()} homework: {m.group(3).strip()}" + (f", for {due}" if due else "")


def _hw_list(day, subject, now):
    if day:
        due = _hw_when(day, now)
        return f"what homework do I have for {due}" if due and due != "next lesson" else None
    return f"what homework do I have in {subject.strip()}" if subject else "my homework"


# (pattern on the cleaned sentence, English command or a function building it)
RULES: list[tuple[str, object]] = [
    # --- homework ---
    (rf"(?:j['’]ai\s+)?(?:des\s+|mes\s+|les\s+)?devoirs?\s+(?:de\s+|d['’]|en\s+)({HW_SUBJ})(?:\s+(?:pour|à\s+rendre(?:\s+pour)?)\s+({HW_WHEN}))?\s*[:,–-]\s*(.+?)"
     rf"(?:\s*,?\s+(?:pour|à\s+rendre(?:\s+pour)?)\s+({HW_WHEN}))?", _homework),
    (rf"(?:qu['’]est-ce\s+que\s+j['’]ai|j['’]ai\s+quoi|quels?(?:\s+sont)?)\s+(?:comme\s+)?(?:mes\s+)?devoirs(?:\s+(?:pour|à\s+rendre(?:\s+pour)?)\s+({HW_WHEN})|\s+(?:de\s+|d['’]|en\s+)({HW_SUBJ}))?|"
     rf"(?:est-ce\s+que\s+)?j['’]ai\s+des\s+devoirs(?:\s+(?:pour|à\s+rendre(?:\s+pour)?)\s+({HW_WHEN})|\s+(?:de\s+|d['’]|en\s+)({HW_SUBJ}))?|(?:montre(?:-moi)?\s+|liste\s+)?mes\s+devoirs",
     lambda m, now: _hw_list(m.group(1) or m.group(3), m.group(2) or m.group(4), now)),
    (rf"j['’]ai\s+(?:fini|terminé|termine|fait|rendu)\s+(?:mes|mon|le|les)\s+devoirs?(?:\s+(?:de\s+|d['’]|en\s+)({HW_SUBJ}))?|(?:mes\s+)?devoirs?\s+(?:de\s+|d['’]|en\s+)({HW_SUBJ})\s+(?:sont\s+|est\s+)?(?:fini|faits?|terminés?)",
     lambda m, now: f"I did my {(m.group(1) or m.group(2) or '').strip() + ' ' if (m.group(1) or m.group(2)) else ''}homework"),
    (rf"(?:supprime[rz]?|efface[rz]?|enlève|enleve)\s+(?:mes|mon|le|les)\s+devoirs?\s+(?:de\s+|d['’]|en\s+)({HW_SUBJ})", lambda m, now: f"remove my {m.group(1)} homework"),
    (r"(?:vérifie|verifie|regarde|synchronise)\s+(?:google\s+)?classroom|(?:quoi\s+de\s+neuf|du\s+nouveau|des\s+nouveaux\s+devoirs)\s+sur\s+(?:google\s+)?classroom", "check classroom"),
    # --- the date and the time ---
    (r"(?:quelle\s+heure\s+(?:est-il|il\s+est|est\s+il)|il\s+est\s+quelle\s+heure|tu\s+as\s+l['’]heure|c['’]est\s+quelle\s+heure|l['’]heure)(?:\s+(?:maintenant|actuellement|là))?", "what time is it"),
    (r"(?:quelle\s+est\s+la\s+date|c['’]est\s+quoi\s+la\s+date|quelle\s+date\s+(?:sommes-nous|on\s+est|est-on)|on\s+est\s+(?:le\s+combien|quel\s+jour|quelle\s+date)|"
     r"quel\s+jour\s+(?:sommes-nous|on\s+est|est-on|est-ce|c['’]est|nous\s+sommes)|la\s+date)(?:\s+(?:d['’]aujourd['’]hui|aujourd['’]hui))?", "what's the date"),
    (r"(?:on\s+sera\s+quel\s+jour|quel\s+jour\s+(?:on\s+sera|serons-nous|sera-t-on|ce\s+sera))\s+demain|demain\s+(?:on\s+est|c['’]est|ce\s+sera)\s+quel\s+jour|quelle\s+(?:est\s+la\s+)?date\s+demain", "what's the date tomorrow"),
    (r"(?:on\s+était|c['’]était)\s+quel\s+jour\s+hier|hier\s+(?:on\s+était|c['’]était)\s+quel\s+jour", "what day was it yesterday"),
    (r"(?:en\s+)?quelle\s+année\s+(?:sommes-nous|on\s+est|est-on|est-ce)|on\s+est\s+en\s+quelle\s+année", "what year is it"),
    (r"(?:en\s+)?quel\s+mois\s+(?:sommes-nous|on\s+est|est-on)|on\s+est\s+en\s+quel\s+mois", "what month is it"),
    (r"(?:quelle|on\s+est\s+(?:en|à\s+la))\s+semaine(?:\s+(?:sommes-nous|on\s+est|est-on))?|(?:quel\s+est\s+le\s+)?numéro\s+de\s+(?:la\s+)?semaine", "what week is it"),
    (r"(?:quel|c['’]est\s+quel)\s+jour\s+(?:de\s+la\s+semaine\s+)?(?:le|tombe\s+le)\s+(\d{1,2}(?:er)?\s+\w+)",
     lambda m, now: (lambda d: f"what day is {d}" if d else None)(when("le " + m.group(1), now))),
    # --- memory between chats ---
    (r"qu['’]est-ce\s+que\s+tu\s+as\s+appris\s+sur\s+moi|(?:qu['’]as-tu|tu\s+as\s+appris\s+quoi)\s+(?:appris\s+)?sur\s+moi", "what have you learned about me"),
    (r"(?:cherche|recherche|regarde)\s+(?:dans\s+)?(?:mes|nos)\s+(?:conversations|discussions|chats|messages)\s+(?:pour\s+|si\s+on\s+a\s+parlé\s+de\s+)?(.+)",
     lambda m, now: f"search my chats for {m.group(1)}"),
    (r"quand\s+(?:est-ce\s+que\s+)?(?:j['’]ai|on\s+a|avons-nous|ai-je)\s+parlé\s+(?:de\s+|d['’]|du\s+|des\s+)(.+)", lambda m, now: f"when did I talk about {m.group(1)}"),
    (r"oublie\s+(?:tout\s+)?ce\s+que\s+(?:je\s+t['’]ai\s+dit|j['’]ai\s+dit|on\s+a\s+dit)\s+(?:sur|à\s+propos\s+de|de|d['’])\s*(.+)", lambda m, now: f"forget what I said about {m.group(1)}"),
    (r"(?:arrête|arrete)\s+d['’]apprendre(?:\s+(?:de|sur)\s+(?:mes\s+conversations|moi|nos\s+conversations))?", "stop learning from my chats"),
    (r"(?:recommence|continue)\s+(?:à|a)\s+apprendre(?:\s+(?:de|sur)\s+(?:mes\s+conversations|moi|nos\s+conversations))?", "start learning from my chats"),
    (r"qu['’]est-ce\s+que\s+tu\s+(?:sais|te\s+rappelles)\s+(?:sur|de|d['’]|à\s+propos\s+de)\s*(.+)", lambda m, now: "what do you know about " + ("me" if m.group(1).strip().lower() in ("moi", "moi-même") else m.group(1))),
    # --- the study coach ---
    (r"(?:commence[rz]?|démarre[rz]?|demarre[rz]?|lance[rz]?)\s+(?:ma\s+|la\s+|une\s+)?(?:séance\s+de\s+|seance\s+de\s+)?révision(?:\s+(?:de|d['’]|en)\s*(.+))?|on\s+révise(?:\s+(?:la|les|le|l['’])?\s*(.+))?|c['’]est\s+l['’]heure\s+de\s+réviser",
     lambda m, now: "start revision" + (f" on {m.group(1) or m.group(2)}" if (m.group(1) or m.group(2)) else "")),
    (r"j['’]ai\s+(?:fini|terminé|termine)\s+(?:de\s+réviser|ma\s+révision|la\s+révision|ma\s+séance)|(?:arrête[rz]?|arrete[rz]?|termine[rz]?)\s+(?:la|ma)\s+révision", "done revising"),
    (r"c['’](?:était|etait)\s+(?:très\s+|trop\s+|plutôt\s+|assez\s+|vraiment\s+|super\s+)?(facile|simple|dur|difficile|compliqué|ok|bien|correct|moyen)|(?:ça|ca)\s+(?:allait|a\s+été|s['’]est\s+bien\s+passé)",
     lambda m, now: "it was " + {"facile": "easy", "simple": "easy", "dur": "hard", "difficile": "hard", "compliqué": "hard"}.get((m.group(1) or "").lower(), "ok")),
    (r"(?:montre(?:-moi)?\s+|affiche\s+)?(?:mon|le)\s+(?:planning|plan|programme)\s+de\s+révisions?|quand\s+(?:est-ce\s+que\s+je\s+révise|dois-je\s+réviser|je\s+révise)|(?:mes|les)\s+(?:prochaines\s+)?(?:séances\s+de\s+)?révisions\s+prévues", "show my revision plan"),
    (r"je\s+(?:ne\s+)?(?:peux|pourrai)\s+pas\s+réviser\s+(?:aujourd['’]hui|ce\s+soir)|(?:saute|annule|déplace|deplace|repousse)\s+(?:la\s+)?révision\s+(?:d['’]aujourd['’]hui|de\s+ce\s+soir)", "I can't revise today"),
    (r"(?:re-?planifie[rz]?|refais|recalcule)\s+(?:mes|les|mon\s+planning\s+de)\s+révisions?", "replan my revision"),
    (r"(?:mon\s+|le\s+)?(?:résumé|resume|aperçu|apercu|bilan|programme)\s+de\s+(?:la|ma)\s+semaine|(?:comment\s+se\s+présente|à\s+quoi\s+ressemble)\s+ma\s+semaine|ma\s+semaine",
     "weekly overview"),
    (r"(?:fais|fait|crée|cree|transforme)(?:[- ]moi)?\s+(?:des\s+)?(?:fiches|flashcards|cartes)\s+(?:avec|à\s+partir\s+de|a\s+partir\s+de|de)\s+(?:cette\s+photo|ces\s+photos|ceci|ça|ca|cette\s+page|ces\s+notes)",
     "make flashcards from this"),
    (r"(?:fais|fait|crée|cree)(?:[- ]moi)?\s+(?:des\s+)?(?:fiches|flashcards|cartes)\s+(?:avec|à\s+partir\s+de|a\s+partir\s+de|de)\s+mes\s+notes\s+(?:de|d['’]|sur|en)\s*(.+)|transforme\s+mes\s+notes\s+(?:de|d['’]|sur)\s*(.+?)\s+en\s+(?:fiches|flashcards|cartes)",
     lambda m, now: f"make flashcards from my notes on {m.group(1) or m.group(2)}"),
    # --- files of a type on this PC (before the other searches) ---
    (r"(?:cherche[rz]?|trouve[rz]?|liste[rz]?|montre)(?:[- ]moi)?\s+(?:tous\s+|toutes\s+)?(?:les|des|mes)\s+fichiers\s+(\.?[a-z0-9]{1,10}(?:\s*(?:,|et|ou)\s*\.?[a-z0-9]{1,10})*)"
     r"(?:\s+(?:dans|sur|de)\s+(?:le\s+dossier\s+|mon\s+dossier\s+|le\s+|la\s+|les\s+|mon\s+|ma\s+|mes\s+|l['’])?(.+?))?",
     lambda m, now: f"search for {re.sub(r'\s+(?:et|ou)\s+', ' and ', m.group(1))} files" + (f" in {_place(m.group(2))}" if m.group(2) else "")),
    # --- to-do list ---
    (rf"{VERB_ADD}\s+(.+?)\s+(?:à|a|sur|dans)\s+{LIST}(?:\s+(.+))?", _task),
    (rf"(?:ajoute[rz]?|crée[rz]?|cree[rz]?|nouvelle)\s+(?:une\s+)?(?:tâche|tache)\s*:?\s*(.+)", _task),
    (r"(?:tâche|tache|à\s+faire)\s*:\s*(.+)", _task),
    (rf"(?:montre|affiche|lis|donne|dis)(?:[- ]moi)?\s+{LIST}|(?:qu['’]est-ce\s+qu(?:e\s+j['’]ai|['’]il\s+me\s+reste)|que\s+me\s+reste-t-il|qu['’]ai-je)\s+à\s+faire|quelles\s+sont\s+mes\s+(?:tâches|taches)|{LIST}", "show my to-do list"),
    (rf"(?:coche[rz]?|marque[rz]?|valide[rz]?)\s+(.+?)(?:\s+comme\s+(?:fait|faite|terminée?|finie?))?(?:\s+(?:dans|sur|de)\s+{LIST})?", lambda m, now: f"mark {m.group(1)} as done"),
    (r"j['’]ai\s+(?:fini|terminé|termine|fait)\s+(?:de\s+)?((?:le|la|les|l['’]|mon|ma|mes|ce|cette|ces)\s*.+)", lambda m, now: f"mark {m.group(1)} as done"),
    (rf"(?:supprime[rz]?|enlève|enleve[rz]?|retire[rz]?|efface[rz]?)\s+(.+?)\s+(?:de|dans)\s+{LIST}", lambda m, now: f"remove {m.group(1)} from my to-do list"),
    (r"(?:supprime[rz]?|enlève|enleve[rz]?|retire[rz]?|efface[rz]?)\s+(?:la\s+)?(?:tâche|tache)\s+(.+)", lambda m, now: f"delete the task {m.group(1)}"),
    # --- calendar ---
    (rf"(?:qu['’]est-ce\s+que\s+j['’]ai|qu['’]ai-je|j['’]ai\s+quoi|qu['’]est-ce\s+qu['’]il\s+y\s+a)(?:\s+(?:de\s+)?prévu)?(?:\s+(?:dans|sur|à)\s+{CAL})?\s+(.+)", _agenda),
    (rf"(?:montre|affiche|lis|donne|dis)(?:[- ]moi)?\s+{CAL}(?:\s+(?:de|d['’]|pour)\s*(.+))?", _agenda),
    (rf"{CAL}\s+(?:de|d['’]|pour)\s*(.+)", _agenda),
    (r"(?:suis-je|est-ce\s+que\s+je\s+suis)\s+(?:libre|dispo(?:nible)?|occupée?)\s+(.+)", _agenda),
    (rf"(?:ajoute[rz]?|mets?|planifie[rz]?|programme[rz]?|note[rz]?|inscri[ste])\s+(?:un\s+|une\s+|le\s+|la\s+|l['’]|mon\s+|ma\s+)?(.+?)\s+(?:à|a|dans|sur)\s+{CAL}", _event),
    (r"(?:planifie[rz]?|programme[rz]?)\s+(?:un\s+|une\s+|le\s+|la\s+|l['’]|mon\s+|ma\s+)?(.+)", _event),
    (r"j['’]ai\s+(?:un\s+|une\s+|mon\s+|ma\s+)?((?:rendez-vous|rdv|réunion|reunion|cours|match|entraînement|entrainement|dentiste|médecin|medecin|docteur|coiffeur|concert|anniversaire|fête|fete|sortie|voyage|vol|présentation|presentation|exposé|expose)\b.+)", _event),
    (r"(?:annule[rz]?|supprime[rz]?)\s+(?:le\s+|la\s+|l['’]|mon\s+|ma\s+)?((?:rendez-vous|rdv|réunion|reunion|cours|événement|evenement)\b.*)", lambda m, now: f"cancel the event {m.group(1)}"),
    # --- exams and revision ---
    (rf"j['’]ai\s+(?:un\s+|une\s+|mon\s+|ma\s+)?{EXAM}\s+(?:de\s+|d['’]|en\s+)(.+?)\s+((?:{WHEN_START}).*)", _exam),
    (rf"(?:mon\s+|ma\s+|l['’]|le\s+)?{EXAM}\s+(?:de\s+|d['’]|en\s+)(.+?)\s+(?:est|a\s+lieu|aura\s+lieu|c['’]est|tombe)\s+(.+)", _exam),
    (rf"(?:quand\s+(?:sont|est-ce\s+que\s+sont)\s+mes\s+{EXAM}s?|mes\s+{EXAM}s?|compte\s+à\s+rebours(?:\s+des\s+{EXAM}s?)?|(?:combien\s+de\s+(?:jours|temps)\s+(?:avant|jusqu['’]à)|c['’]est\s+quand)\s+(?:mes?\s+|mon\s+|ma\s+|les?\s+|l['’])?(?:prochains?\s+)?{EXAM}s?.*)", "exam countdown"),
    (rf"(?:planifie[rz]?|organise[rz]?|prépare[rz]?|prepare[rz]?|fais)(?:[- ]moi)?\s+(?:un\s+planning\s+de\s+|un\s+plan\s+de\s+|mes?\s+|les\s+)?révisions?(?:\s+pour\s+mes\s+{EXAM}s?)?", "plan my revision"),
    # --- grades ---
    (r"(?:j['’]ai\s+(?:eu|obtenu|fait|pris)|j['’]ai)\s+(?:un\s+|une\s+)?(\d{1,3}(?:[.,]\d{1,2})?)(?:\s+sur\s+(\d{1,3}))?\s+(?:en|à|au|a)\s+(?:l['’]|la\s+|le\s+)?([^,]+?)(\s*(?:,|\s)\s*(?:coefficient\s*2|coef\s*2|qui\s+compte\s+double|compte\s+double|double|hier).*)?",
     lambda m, now: f"I got a {m.group(1)}" + (f"/{m.group(2)}" if m.group(2) else "") + f" in {m.group(3)}" + _fr_grade_rest(m.group(4))),
    (r"(?:quelle\s+est\s+|c['’]est\s+quoi\s+)?ma\s+moyenne\s+(?:en|de|d['’]|à|a)\s*(.+)|(?:comment\s+je\s+m['’]en\s+sors|où\s+j['’]en\s+suis)\s+en\s+(.+)",
     lambda m, now: f"what's my average in {m.group(1) or m.group(2)}"),
    (r"(?:(?:montre|donne|affiche)(?:[- ]moi)?\s+)?(?:mes|toutes\s+mes)\s+(?:moyennes|résultats|resultats|notes\s+(?:scolaires|d['’]école|de\s+l['’]école|du\s+semestre|du\s+trimestre|de\s+classe))|ma\s+moyenne\s+(?:générale|generale)|quelle\s+est\s+ma\s+moyenne(?:\s+générale)?", "my grades"),
    (r"(?:il\s+me\s+faut\s+combien|qu['’]est-ce\s+qu['’]il\s+me\s+faut|quelle\s+note\s+(?:il\s+me\s+faut|me\s+faut-il))\s+(?:au|à\s+mon|a\s+mon)\s+prochain\s+(?:test|contrôle|controle|examen)\s+(?:de|d['’]|en)\s*(.+?)\s+pour\s+(?:avoir|garder|atteindre)\s+(?:une\s+moyenne\s+de\s+|un\s+|une\s+)?(\d{1,3}(?:[.,]\d{1,2})?)",
     lambda m, now: f"what do I need on the next {m.group(1)} test to get {m.group(2).replace(',', '.')}"),
    (r"(?:il\s+me\s+faut\s+combien|qu['’]est-ce\s+qu['’]il\s+me\s+faut)\s+(?:en|pour\s+réussir\s+(?:en\s+)?)\s*(.+?)\s+pour\s+(?:avoir|garder|atteindre)\s+(?:une\s+moyenne\s+de\s+|un\s+|une\s+)?(\d{1,3}(?:[.,]\d{1,2})?)",
     lambda m, now: f"what do I need on the next {m.group(1)} test to get {m.group(2).replace(',', '.')}"),
    (r"(?:supprime|efface|enlève|enleve|annule)\s+ma\s+dernière\s+note|(?:supprime|efface|enlève|enleve|annule)\s+ma\s+derniere\s+note", "remove my last grade"),
    (r"(?:commence[rz]?|nouveau|nouvelle)\s+(?:un\s+|une\s+)?(?:nouveau\s+|nouvelle\s+)?(?:semestre|trimestre|année\s+scolaire)", "start a new term"),
    # --- the timetable ---
    (r"(?:c['’]est\s+quoi|quel\s+est|c['’]est\s+quel)\s+(?:mon\s+)?prochain\s+cours|(?:mon\s+)?prochain\s+cours|j['’]ai\s+quoi\s+(?:comme\s+cours\s+)?(?:après|ensuite|maintenant)|(?:où|ou)\s+est\s+mon\s+prochain\s+cours", "what's my next class"),
    (rf"(?:qu['’]est-ce\s+que\s+j['’]ai|j['’]ai\s+quoi|quels?\s+cours\s+(?:j['’]ai|ai-je|est-ce\s+que\s+j['’]ai))\s+(?:comme\s+cours\s+)?(?:à\s+l['’]école\s+)?{FR_DAY}",
     lambda m, now: "what classes do I have" + fr_day(m.group(1))),
    (rf"(?:à|a)\s+quelle\s+heure\s+(?:je\s+commence|est-ce\s+que\s+je\s+commence|commence\s+l['’]école|commencent\s+les\s+cours)(?:\s+l['’]école)?\s*{FR_DAY}?",
     lambda m, now: "when do I start" + fr_day(m.group(1))),
    (rf"(?:à|a)\s+quelle\s+heure\s+(?:je\s+finis|je\s+termine|est-ce\s+que\s+je\s+finis|finit\s+l['’]école|finissent\s+les\s+cours)(?:\s+l['’]école)?\s*{FR_DAY}?",
     lambda m, now: "when do I finish" + fr_day(m.group(1))),
    (rf"(?:qu['’]est-ce\s+que\s+je\s+dois|je\s+dois|il\s+faut)\s+(?:prendre|apporter|emporter|amener)(?:\s+quoi)?(?:\s+à\s+l['’]école)?\s*{FR_DAY}?",
     lambda m, now: "what do I need to bring" + (fr_day(m.group(1)) or " tomorrow")),
    (r"quand\s+(?:est|ai-je|j['’]ai|est-ce\s+que\s+j['’]ai)\s+(?:mon\s+)?(?:prochain\s+)?cours\s+(?:de\s+|d['’])(.+)", lambda m, now: f"when is my next {m.group(1)} class"),
    (r"(?:(?:montre|affiche|lis|donne)(?:[- ]moi)?\s+)?(?:mon|l['’])\s*(?:emploi\s+du\s+temps|horaire)(?:\s+de\s+la\s+semaine)?", "show my timetable"),
    # --- countdowns ("how many days until the Christmas vacation") ---
    (r"(?:ajoute[rz]?|crée[rz]?|cree[rz]?|mets?|lance[rz]?|fais|démarre[rz]?|demarre[rz]?)(?:[- ]moi)?\s+(?:un\s+)?compte\s+à\s+rebours\s+(?:pour|jusqu['’]à|jusqu['’]au|avant|de|des|du)\s+(.+)", _countdown),
    (r"((?:les\s+|mes\s+|nos\s+)?vacances\b.*?|(?:mon\s+|l['’])\s*anniversaire)\s+(?:sont|est|commencent|commence|tombent?|vont\s+être|va\s+être|c['’]est|ont\s+lieu|a\s+lieu)\s+((?:du|le|de)\s+.+|\d.+)", _countdown_statement),
    (r"combien\s+(?:de\s+)?(jours|semaines|mois|dodos)\s+(?:(?:il\s+)?(?:me\s+|nous\s+)?reste(?:-t-il)?\s+|restent\s+|encore\s+)?(?:avant|jusqu['’]à|jusqu['’]au|jusqu['’]aux|d['’]ici)\s+(.+)",
     lambda m, now: f"how many {FR_UNITS[m.group(1)]} until {m.group(2)}"),
    (r"combien\s+de\s+jours\s+(?:(?:il\s+)?(?:me\s+)?reste(?:-t-il)?\s+)?(?:de|des|du|pendant\s+les?)\s+(.+)", lambda m, now: f"how many days left of {m.group(1)}"),
    (r"dans\s+combien\s+de\s+(jours|semaines|temps)\s+(?:c['’]est|sont|est|commencent?|arrivent?|tombe|a\s+lieu|ont\s+lieu)\s+(.+)", lambda m, now: f"how many {FR_UNITS[m.group(1)]} until {m.group(2)}"),
    (rf"(?:c['’]est\s+quand|quand\s+(?:est|sont|commencent?|tombe|a\s+lieu|ont\s+lieu|c['’]est))\s+((?:les?\s+|la\s+|l['’]|mes\s+|mon\s+|ma\s+)?.*{FAMOUS}.*)", lambda m, now: f"when is {m.group(1)}"),
    (r"(?:(?:montre|affiche|donne|lis)(?:[- ]moi)?\s+)?(?:mes|les|tous\s+mes)\s+comptes?\s+à\s+rebours", "my countdowns"),
    (r"(?:supprime[rz]?|enlève|enleve[rz]?|retire[rz]?|efface[rz]?|annule[rz]?)\s+(?:le\s+)?compte\s+à\s+rebours\s+(?:pour|de|des|du|d['’])\s*(.+)", lambda m, now: f"remove the countdown for {m.group(1)}"),
    # --- reminders, timers, alarms ---
    (r"rappelle[- ]moi\s+((?:demain|ce\s+soir|dans\s+|à\s+|a\s+\d|vers\s+|lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche|le\s+\d).*?)\s+(de\s+.+|d['’].+|que\s+je\s+dois\s+.+)", _remind_first),
    (r"(?:rappelle[- ]moi|fais[- ]moi\s+penser|n['’]oublie\s+pas\s+de\s+me\s+rappeler|préviens[- ]moi|previens[- ]moi)\s+(.+)", _remind),
    (r"(?:mets?|lance[rz]?|démarre[rz]?|demarre[rz]?|règle[rz]?|regle[rz]?|programme[rz]?|crée[rz]?)\s+(?:un\s+|le\s+)?(?:minuteur|chrono(?:mètre)?|timer|compte\s+à\s+rebours|minuterie)\s+(?:de\s+|d['’]|pour\s+|sur\s+)(.+)", _timer),
    (r"(?:minuteur|minuterie|chrono|timer)\s+(?:de\s+|d['’]|pour\s+)?(.+)", _timer),
    (r"(?:r[ée]veille)[- ]moi\s+(?:avec|par)\s+un\s+(?:coup\s+de\s+fil|appel)\s+(.+)|(?:r[ée]veille)[- ]moi\s+(.+?)\s+(?:avec|par)\s+un\s+(?:coup\s+de\s+fil|appel)", _wake_call),
    (r"(?:appelle|téléphone|telephone)[- ]moi(?:\s+(.+))?", _call),
    (r"(?:annule|supprime)\s+(?:mon|l['’]|mes|les)\s*appels?(?:\s+(?:de\s+r[ée]veil|prévus?))?|ne\s+m['’]appelle\s+pas", "cancel my calls"),
    (r"quand\s+(?:vas-tu|est-ce\s+que\s+tu\s+vas|tu\s+vas)\s+m['’]appeler|(?:quels|mes)\s+appels\s+(?:prévus|de\s+r[ée]veil)", "when will you call me"),
    (r"raccroche|arrête\s+de\s+(?:m['’]appeler|sonner)", "hang up"),
    (r"(?:réveille[- ]moi|reveille[- ]moi|mets?\s+(?:un\s+|une\s+|le\s+)?(?:réveil|reveil|alarme)\s+(?:pour\s+|à\s+)?)\s*(.+)", _alarm),
    (r"(?:quels?\s+(?:sont\s+)?(?:mes\s+)?(?:rappels|minuteurs)(?:\s+(?:en\s+cours|actifs))?|mes\s+rappels)", "what reminders do i have"),
    (r"(?:annule[rz]?|arrête[rz]?|arrete[rz]?|stoppe[rz]?|supprime[rz]?)\s+(?:le\s+|mon\s+|tous\s+les\s+|tous\s+mes\s+)?(minuteurs?|chronos?|timers?|rappels?|alarmes?|réveils?)", lambda m, now: "cancel all " + ("timers" if re.match(r"min|chr|tim", m.group(1), re.I) else "alarms" if re.match(r"al|r[ée]v", m.group(1), re.I) else "reminders")),
    # --- notes ---
    (r"(?:cherche[rz]?|trouve[rz]?|regarde[rz]?)(?:[- ]moi)?\s+(?:dans\s+mes\s+notes\s+(.+)|(.+?)\s+dans\s+mes\s+notes)", lambda m, now: f"search my notes for {re.sub(r'^(?:ce que j.ai (?:écrit|noté) sur |sur |à propos de |pour )', '', m.group(1) or m.group(2), flags=re.I)}"),
    (r"(?:qu['’]est-ce\s+que\s+j['’]ai|qu['’]ai-je)\s+(?:noté|note|écrit|ecrit)\s+(?:sur|à\s+propos\s+de|concernant|pour)\s+(.+)", lambda m, now: f"search my notes for {m.group(1)}"),
    (r"(?:montre|affiche|lis|donne)(?:[- ]moi)?\s+mes\s+(?:dernières\s+)?notes|mes\s+notes", "show my notes"),
    (r"(?:supprime[rz]?|efface[rz]?)\s+(?:ma\s+|la\s+)?dernière\s+note", "delete my last note"),
    (r"(?:prends?|prendre)\s+(?:une\s+)?note\s*(?::|,|que|de)?\s*(.+)", lambda m, now: f"take a note: {m.group(1)}"),
    (r"note[rz]?\s*(?:que|:|,)\s*(.+)", lambda m, now: f"take a note: {m.group(1)}"),
    (r"(?:ajoute[rz]?|mets?)\s+(.+?)\s+(?:à|a|dans)\s+mes\s+notes", lambda m, now: f"take a note: {m.group(1)}"),
    # --- study ---
    (r"(?:interroge[rz]?[- ]moi|teste[rz]?[- ]moi|pose[rz]?[- ]moi\s+des\s+questions|fais[- ]moi\s+(?:un\s+)?(?:quiz|quizz|test|qcm))(?:\s+(?:sur|à\s+propos\s+de|de|d['’])\s*(.+))?", lambda m, now: "quiz me" + (f" on {m.group(1)}" if m.group(1) else "")),
    (r"(?:ajoute[rz]?|crée[rz]?|cree[rz]?|fais)(?:[- ]moi)?\s+une\s+(?:carte|fiche|flashcard)\s*:?\s*(.+?)\s*(\||=|->|→)\s*(.+)", lambda m, now: f"add a flashcard: {m.group(1)} | {m.group(3)}"),
    (r"(?:révise[rz]?|revise[rz]?|réviser|reviser)\s+(?:mes|les)\s+(?:cartes|fiches|flashcards)(?:\s+du\s+jour|\s+d['’]aujourd['’]hui)?|(?:mes\s+)?(?:cartes|fiches)\s+à\s+réviser|révision\s+des\s+(?:cartes|fiches)", "review my cards"),
    (r"combien\s+(?:de|d['’])\s*(?:cartes|fiches|flashcards)\s+(?:à\s+réviser|j['’]ai\s+à\s+réviser|sont\s+à\s+réviser)(?:\s+aujourd['’]hui)?|mon\s+(?:paquet|deck)(?:\s+de\s+cartes)?", "how many cards are due"),
    (r"(?:fais[- ]moi\s+(?:des\s+)?|crée[rz]?\s+(?:des\s+)?|des\s+)?(?:fiches|flashcards|cartes)(?:\s+de\s+révisions?)?(?:\s+(?:sur|de|d['’])\s*(.+))?", lambda m, now: "flashcards" + (f" on {m.group(1)}" if m.group(1) else "")),
    (r"(?:arrête[rz]?|arrete[rz]?|stoppe[rz]?|termine[rz]?)\s+(?:le\s+)?(?:quiz|quizz|test|les\s+fiches)", "stop the quiz"),
    # --- focus ---
    (rf"(?:concentration|focus|mode\s+(?:concentration|focus)|pomodoro|je\s+(?:veux\s+|vais\s+)?(?:me\s+concentre[rs]?|travaille[rs]?|révise[rs]?|revise[rs]?))(?:\s+(?:pendant|pour|de)\s+(.+?))?(?:\s+(?:sur|en)\s+(?:les?\s+|la\s+|l['’])?(.+))?", _focus),
    (r"(?:lance[rz]?|démarre[rz]?|demarre[rz]?|commence[rz]?)\s+(?:une\s+)?(?:session\s+de\s+)?(?:concentration|focus|pomodoro|travail)(?:\s+(?:de|pendant|pour)\s+(.+?))?(?:\s+(?:sur|en)\s+(?:les?\s+|la\s+|l['’])?(.+))?", _focus),
    (r"(?:arrête[rz]?|arrete[rz]?|stoppe[rz]?|termine[rz]?|fin\s+de)\s+(?:la\s+|le\s+|ma\s+)?(?:session\s+de\s+)?(?:concentration|focus|pomodoro|session)", "stop focus"),
    (r"combien\s+de\s+temps\s+(?:me\s+)?reste(?:-t-il)?(?:\s+(?:de|dans\s+(?:la|ma))\s+(?:concentration|focus|session))?", "how long is left in my focus session"),
    (r"combien\s+(?:de\s+temps\s+)?(?:ai-je|j['’]ai)\s+(?:travaillé|révisé|revise|été\s+concentrée?)\s+(aujourd['’]hui|cette\s+semaine)", lambda m, now: "how much did I focus " + ("today" if m.group(1).startswith("auj") else "this week")),
    # --- day, weather, briefing ---
    (r"(?:(?:fais[- ]moi\s+(?:le|un)\s+)?(?:récap|recap|résumé|resume|bilan)(?:itulatif)?\s+de\s+(?:ma|la)\s+journée|comment\s+s['’]est\s+passée\s+ma\s+journée|qu['’]est-ce\s+que\s+j['’]ai\s+fait\s+aujourd['’]hui)", "evening recap"),
    (r"(?:fais[- ]moi\s+(?:le|un)\s+)?(?:briefing|brief|point(?:\s+du\s+(?:jour|matin))?|topo)|quoi\s+de\s+neuf", "briefing"),
    (r"(?:quel\s+temps\s+fait-il|il\s+fait\s+quel\s+temps|quel\s+temps\s+(?:il\s+)?fait|(?:donne[- ]moi\s+|c['’]est\s+quoi\s+|quelle\s+est\s+)?la\s+météo|météo|meteo)(?:\s+(?:aujourd['’]hui|dehors|maintenant))?", "what's the weather"),
    # --- search everything, network ---
    (r"(?:cherche[rz]?|trouve[rz]?)(?:[- ]moi)?\s+(.+?)\s+(?:partout|dans\s+(?:toutes\s+)?mes\s+(?:affaires|données|donnees|fichiers|documents))", lambda m, now: f"search everything for {m.group(1)}"),
    (r"(?:cherche[rz]?|trouve[rz]?)(?:[- ]moi)?\s+partout\s+(.+)", lambda m, now: f"search everything for {m.group(1)}"),
    (r"où\s+(?:est-ce\s+que\s+j['’]ai|ai-je)\s+(?:vu|mis|noté|écrit|parlé\s+de)\s+(.+)", lambda m, now: f"where did I see {m.group(1)}"),
    (r"(?:quels?\s+(?:sont\s+les\s+)?appareils\s+(?:sont\s+)?(?:connectés|branchés)?(?:\s+(?:au|sur\s+le|à\s+mon)\s+(?:wi-?fi|réseau|reseau))?|qui\s+est\s+(?:connecté\s+)?(?:sur|à)\s+(?:mon|le)\s+(?:wi-?fi|réseau|reseau)|(?:montre|liste)(?:[- ]moi)?\s+les\s+appareils(?:\s+(?:du|sur\s+le)\s+(?:wi-?fi|réseau|reseau))?)", "what devices are on my wifi"),
    (r"(?:pourquoi\s+(?:est-ce\s+que\s+)?(?:le\s+|mon\s+)?(?:wi-?fi|internet|réseau|reseau|la\s+connexion)\s+(?:est|rame)\s*(?:si\s+|aussi\s+|tellement\s+)?(?:lente?|mauvaise?)?|(?:le\s+|mon\s+)?(?:wi-?fi|internet|la\s+connexion)\s+(?:est\s+(?:très\s+|trop\s+|super\s+)?lente?|rame|lag(?:ue)?)|(?:vérifie[rz]?|verifie[rz]?|teste[rz]?|analyse[rz]?)\s+(?:le\s+|mon\s+|ma\s+)?(?:wi-?fi|connexion|réseau|reseau|internet))", "why is my wifi slow"),
    # --- the screen ---
    (r"(?:surveille[rz]?|regarde[rz]?)\s+(?:mon\s+|l['’])écran\s+(?:et\s+)?(?:dis|préviens|previens|avertis)[- ]moi\s+(?:quand|dès\s+que|si)\s+(.+)", lambda m, now: f"watch my screen and tell me when {m.group(1)}"),
    (r"(?:arrête[rz]?|arrete[rz]?)\s+de\s+surveiller\s+(?:mon\s+|l['’])écran", "stop watching the screen"),
    (r"double[- ]?clique[rz]?\s+sur\s+(?:le\s+bouton\s+|le\s+lien\s+|l['’]onglet\s+)?(.+)", lambda m, now: f"double click {m.group(1)}"),
    (r"(?:clic\s+droit|clique[rz]?\s+droit)\s+sur\s+(.+)", lambda m, now: f"right click {m.group(1)}"),
    (r"(?:clique[rz]?|appuie[rz]?)\s+sur\s+le\s+bouton\s+(.+)", lambda m, now: f"click the {m.group(1)} button"),
    (r"clique[rz]?\s+sur\s+(?:le\s+lien\s+|l['’]onglet\s+|le\s+menu\s+)?(.+)", lambda m, now: f"click on {m.group(1)}"),
    (r"(?:qu['’]est-ce\s+qu['’]il\s+y\s+a|qu['’]y\s+a-t-il|c['’]est\s+quoi)\s+(?:sur|à)\s+(?:mon\s+|l['’])écran|regarde[rz]?\s+(?:mon\s+|l['’])écran", "what's on my screen"),
    # --- music ---
    (r"(?:qu['’]est-ce\s+qu['’]il\s+y\s+a|qu['’]y\s+a-t-il|c['’]est\s+quoi|montre(?:[- ]moi)?)\s+(?:dans\s+)?(?:la|ma)\s+file(?:\s+d['’]attente)?(?:\s+(?:sur|de)\s+spotify)?|(?:quelle\s+est|c['’]est\s+quoi)\s+la\s+(?:prochaine|chanson\s+suivante)(?:\s+chanson|\s+musique)?|quelle\s+(?:chanson|musique)\s+(?:vient\s+)?(?:après|ensuite)", "what's in my queue"),
    (r"(?:vide[rz]?|efface[rz]?)\s+(?:la|ma)\s+file(?:\s+d['’]attente)?", "clear the queue"),
    (r"(?:mets?|ajoute[rz]?)\s+(?:une|des|quelques|(\d+))\s+(?:chansons?|musiques?|titres?)\s+(?:de|du\s+groupe)\s+(.+?)\s+(?:à|a|dans)\s+(?:la|ma)\s+file(?:\s+d['’]attente)?", lambda m, now: f"queue {m.group(1) or 'a few'} songs by {m.group(2)}"),
    (r"(?:ajoute[rz]?|rajoute[rz]?|mets?|mettre)\s+(.+?)\s+(?:à|a|dans)\s+(?:la|ma)\s+file(?:\s+d['’]attente)?(?:\s+(?:sur|de)\s+spotify)?", lambda m, now: "queue " + re.sub(r"\s+(?:puis|ensuite|et\s+après)\s+", " then ", re.sub(r"\s+(?:de|du\s+groupe|par)\s+(?=[A-Z])", " by ", m.group(1)))),
    (r"(?:mets?|joue[rz]?)\s+(.+?)\s+(?:juste\s+)?(?:après|ensuite)(?:\s+(?:celle-ci|cette\s+chanson|ça))?", lambda m, now: "play " + re.sub(r"\s+(?:de|du\s+groupe|par)\s+(?=[A-Z])", " by ", m.group(1)) + " next"),
    (r"(?:mets?|joue[rz]?|lance[rz]?|écoute[rz]?)\s+(?:mes|les)\s+(?:titres|chansons|sons|musiques)\s+(?:likés|likées|aimés|aimées|favoris|préférés|préférées|sauvegardés)(?:\s+en\s+(?:aléatoire|mode\s+aléatoire))?(?:\s+sur\s+spotify)?|(?:mets?|joue[rz]?|lance[rz]?)\s+mes\s+(?:coups\s+de\s+c(?:œ|oe)ur|likes|favoris)(?:\s+en\s+(?:aléatoire|mode\s+aléatoire))?(?:\s+sur\s+spotify)?",
     lambda m, now: "play my liked songs" + (" on shuffle" if "aléatoire" in m.group(0).lower() else "")),
    (r"(?:mets?|joue[rz]?|lance[rz]?)\s+(.+?)\s+sur\s+spotify", lambda m, now: f"play {m.group(1)} on spotify"),
    # --- updates, backup, PC health ---
    (r"(?:vérifie[rz]?|verifie[rz]?|cherche[rz]?)\s+(?:les\s+|s['’]il\s+y\s+a\s+des\s+)?mises?\s+à\s+jour|(?:y\s+a-t-il|il\s+y\s+a)\s+(?:une|des)\s+mises?\s+à\s+jour", "check for updates"),
    (r"oui,?\s+(?:mets?\s+à\s+jour|installe(?:[- ]les?)?)", "yes, update"),
    (r"(?:à\s+)?quand\s+(?:date|remonte)\s+ma\s+dernière\s+sauvegarde|c['’]était\s+quand\s+ma\s+dernière\s+sauvegarde", "when was my last backup"),
    (r"(?:comment\s+va\s+(?:mon|le)\s+(?:pc|ordi(?:nateur)?)|état\s+(?:du|de\s+mon)\s+(?:pc|ordi(?:nateur)?)|(?:vérifie[rz]?|verifie[rz]?|analyse[rz]?)\s+(?:mon|le)\s+(?:pc|ordi(?:nateur)?)|bilan\s+(?:du|de\s+mon)\s+(?:pc|ordi(?:nateur)?))", "pc health report"),
    (r"(?:annule(?:[rz])?\s+(?:ça|ca|cela)|défais\s+(?:ça|ca))", "undo that"),
]
COMPILED = [(re.compile(p, re.IGNORECASE), build) for p, build in RULES]
FRENCH_HINT = re.compile(r"[éèêàùçôîûë]|\b(?:cartes|fiches|paquet|combien|quand|vacances|rebours|cours|prochain|quoi|horaire|prendre|commence|finis|moyenne|notes?|eu|semestre|moi|mes|mon|ma|une?|les?|des|du|est|sur|dans|pour|quel(?:le)?s?|qu['’]|j['’]|d['’]|l['’]|ajoute|mets|cherche|rappelle|montre|oui|minuteur|minuterie|chrono|pomodoro|concentration|agenda|calendrier|appareils|fichiers|clique[rz]?|clic|écran|surveille[rz]?|coche|note[rz]?|fiches|planifie|interroge|raccroche|appelle|appel|appels|devoirs?|classroom)\b", re.I)


def to_english(text: str, now: datetime | None = None) -> str | None:
    """The English command for a French request, or None when it is not one of the known commands."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t or len(t) > 300 or not FRENCH_HINT.search(t):
        return None
    core = re.sub(POLITE_START, "", t, flags=re.IGNORECASE)
    core = re.sub(POLITE_END, "", core, flags=re.IGNORECASE).strip()
    if not core:
        return None
    for pattern, build in COMPILED:
        m = pattern.fullmatch(core)
        if m:
            out = build if isinstance(build, str) else build(m, now or datetime.now())
            if out:
                return re.sub(r"\s+", " ", out).strip()
    return None

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


def _focus(m, now):
    span = duration(m.group(1)) if m.group(1) else ""
    if m.group(1) and not span:
        return None
    return ("focus for " + span if span else "start a focus session") + (f" on {m.group(2)}" if m.group(2) else "")


def _exam(m, now):
    date = when(m.group(2), now)
    return f"my {m.group(1)} exam is {'on ' if not date.startswith(('tomorrow', 'today', 'next', 'the day')) else ''}{date}" if date else None


EXAM = r"(?:examen|exam|contrôle|controle|interro(?:gation)?|épreuve|epreuve|test|partiel|devoir\s+surveillé|ds|évaluation|evaluation|éval|eval)"
# (pattern on the cleaned sentence, English command or a function building it)
RULES: list[tuple[str, object]] = [
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
    # --- reminders, timers, alarms ---
    (r"rappelle[- ]moi\s+((?:demain|ce\s+soir|dans\s+|à\s+|a\s+\d|vers\s+|lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche|le\s+\d).*?)\s+(de\s+.+|d['’].+|que\s+je\s+dois\s+.+)", _remind_first),
    (r"(?:rappelle[- ]moi|fais[- ]moi\s+penser|n['’]oublie\s+pas\s+de\s+me\s+rappeler|préviens[- ]moi|previens[- ]moi)\s+(.+)", _remind),
    (r"(?:mets?|lance[rz]?|démarre[rz]?|demarre[rz]?|règle[rz]?|regle[rz]?|programme[rz]?|crée[rz]?)\s+(?:un\s+|le\s+)?(?:minuteur|chrono(?:mètre)?|timer|compte\s+à\s+rebours|minuterie)\s+(?:de\s+|d['’]|pour\s+|sur\s+)(.+)", _timer),
    (r"(?:minuteur|minuterie|chrono|timer)\s+(?:de\s+|d['’]|pour\s+)?(.+)", _timer),
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
    (r"double[- ]?clique[rz]?\s+sur\s+(?:le\s+bouton\s+|le\s+lien\s+|l['’]onglet\s+)?(.+)", lambda m, now: f"double click {m.group(1)}"),
    (r"(?:clic\s+droit|clique[rz]?\s+droit)\s+sur\s+(.+)", lambda m, now: f"right click {m.group(1)}"),
    (r"(?:clique[rz]?|appuie[rz]?)\s+sur\s+le\s+bouton\s+(.+)", lambda m, now: f"click the {m.group(1)} button"),
    (r"clique[rz]?\s+sur\s+(?:le\s+lien\s+|l['’]onglet\s+|le\s+menu\s+)?(.+)", lambda m, now: f"click on {m.group(1)}"),
    (r"(?:qu['’]est-ce\s+qu['’]il\s+y\s+a|qu['’]y\s+a-t-il|c['’]est\s+quoi)\s+(?:sur|à)\s+(?:mon\s+|l['’])écran|regarde[rz]?\s+(?:mon\s+|l['’])écran", "what's on my screen"),
    # --- music ---
    (r"(?:mets?|joue[rz]?|lance[rz]?)\s+(.+?)\s+sur\s+spotify", lambda m, now: f"play {m.group(1)} on spotify"),
    # --- updates, backup, PC health ---
    (r"(?:vérifie[rz]?|verifie[rz]?|cherche[rz]?)\s+(?:les\s+|s['’]il\s+y\s+a\s+des\s+)?mises?\s+à\s+jour|(?:y\s+a-t-il|il\s+y\s+a)\s+(?:une|des)\s+mises?\s+à\s+jour", "check for updates"),
    (r"oui,?\s+(?:mets?\s+à\s+jour|installe(?:[- ]les?)?)", "yes, update"),
    (r"(?:à\s+)?quand\s+(?:date|remonte)\s+ma\s+dernière\s+sauvegarde|c['’]était\s+quand\s+ma\s+dernière\s+sauvegarde", "when was my last backup"),
    (r"(?:comment\s+va\s+(?:mon|le)\s+(?:pc|ordi(?:nateur)?)|état\s+(?:du|de\s+mon)\s+(?:pc|ordi(?:nateur)?)|(?:vérifie[rz]?|verifie[rz]?|analyse[rz]?)\s+(?:mon|le)\s+(?:pc|ordi(?:nateur)?)|bilan\s+(?:du|de\s+mon)\s+(?:pc|ordi(?:nateur)?))", "pc health report"),
    (r"(?:annule(?:[rz])?\s+(?:ça|ca|cela)|défais\s+(?:ça|ca))", "undo that"),
]
COMPILED = [(re.compile(p, re.IGNORECASE), build) for p, build in RULES]
FRENCH_HINT = re.compile(r"[éèêàùçôîû]|\b(?:moi|mes|mon|ma|une?|les?|des|du|est|sur|dans|pour|quel(?:le)?s?|qu['’]|j['’]|d['’]|l['’]|ajoute|mets|cherche|rappelle|montre|oui|minuteur|minuterie|chrono|pomodoro|concentration|agenda|calendrier|appareils|clique[rz]?|clic|écran|coche|note[rz]?|fiches|planifie|interroge)\b", re.I)


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

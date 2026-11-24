"""Jarvis's own answers, said in French without asking the AI model.

Built-in commands answer in English (“Timer set for 10 minutes, sir.”). For a French request, the answer used to go to the
AI model for translation: slow on a local model, and sometimes odd. Here the usual answers are written in French directly,
from patterns: a line is translated only when every sentence in it is known, and an answer only when every line is.
Anything else returns None and the AI model translates it as before.

What you wrote yourself (in quotes “…”, task names, subjects, stops) is never changed.

    to_french(text) -> str | None
"""
from __future__ import annotations

import re

DAYS = {"monday": "lundi", "tuesday": "mardi", "wednesday": "mercredi", "thursday": "jeudi", "friday": "vendredi", "saturday": "samedi", "sunday": "dimanche"}
DAYS_SHORT = {"mon": "lun.", "tue": "mar.", "wed": "mer.", "thu": "jeu.", "fri": "ven.", "sat": "sam.", "sun": "dim."}
MONTHS = {"january": "janvier", "february": "février", "march": "mars", "april": "avril", "may": "mai", "june": "juin", "july": "juillet",
          "august": "août", "september": "septembre", "october": "octobre", "november": "novembre", "december": "décembre"}
MONTHS_SHORT = {"jan": "janv.", "feb": "févr.", "mar": "mars", "apr": "avr.", "may": "mai", "jun": "juin", "jul": "juil.", "aug": "août",
                "sep": "sept.", "oct": "oct.", "nov": "nov.", "dec": "déc."}
UNITS = {"second": ("seconde", "secondes"), "minute": ("minute", "minutes"), "hour": ("heure", "heures"), "day": ("jour", "jours"), "week": ("semaine", "semaines"),
         "min": ("min", "min"), "h": ("h", "h")}
WORDS = {"today": "aujourd'hui", "tomorrow": "demain", "yesterday": "hier", "tonight": "ce soir", "this morning": "ce matin",
         "the day after tomorrow": "après-demain", "next week": "la semaine prochaine", "this week": "cette semaine", "now": "maintenant",
         "late": "en retard", "no date": "sans date", "on time": "à l'heure", "direct": "direct"}
QUOTE = re.compile(r"“[^”]*”")


def _clock(m: re.Match) -> str:
    h, mi, ap = int(m.group(1)), m.group(2), m.group(3).upper()
    if ap == "PM" and h != 12:
        h += 12
    if ap == "AM" and h == 12:
        h = 0
    return f"{h:02d}:{mi}"


def when(text: str) -> str:
    """Dates, times and durations: “tomorrow at 6:00 PM” → “demain à 18:00”, “Thursday 3 December” → “jeudi 3 décembre”."""
    t = text
    t = re.sub(r"\b(\d{1,2}):(\d{2})\s*([AP]M)\b", _clock, t, flags=re.I)
    t = re.sub(r"\bon (\w+) (\d{1,2})\b(?= at|$|,|\))", lambda m: f"le {m.group(2)} {MONTHS.get(m.group(1).lower(), m.group(1))}" if m.group(1).lower() in MONTHS else m.group(0), t)
    t = re.sub(r"\b(\d+) (second|minute|hour|day|week|min|h)s?\b", lambda m: f"{m.group(1)} {UNITS[m.group(2)][int(m.group(1)) != 1]}", t)
    t = re.sub(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)s\b", lambda m: "le " + DAYS[m.group(1).lower()], t, flags=re.I)
    t = re.sub(r"\bnext (monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", lambda m: DAYS[m.group(1).lower()] + " prochain", t, flags=re.I)
    for en, fr in sorted(WORDS.items(), key=lambda kv: -len(kv[0])):
        t = re.sub(rf"\b{en}\b", fr, t, flags=re.I)
    t = re.sub(r"\b(" + "|".join(DAYS) + r")\b", lambda m: DAYS[m.group(1).lower()], t, flags=re.I)
    t = re.sub(r"\b(" + "|".join(MONTHS) + r")\b", lambda m: MONTHS[m.group(1).lower()], t, flags=re.I)
    t = re.sub(r"\b(" + "|".join(DAYS_SHORT) + r")\b(?=\s+\d)", lambda m: DAYS_SHORT[m.group(1).lower()], t, flags=re.I)
    t = re.sub(r"(?<=\d )(" + "|".join(MONTHS_SHORT) + r")\b", lambda m: MONTHS_SHORT[m.group(1).lower()], t, flags=re.I)
    t = re.sub(r"\b(lun\.|mar\.|mer\.|jeu\.|ven\.|sam\.|dim\.) (\d{1,2}:\d{2})", r"\1 \2", t)
    t = re.sub(r"\bin (\d+ (?:secondes?|minutes?|heures?|jours?|semaines?|min|h)(?: (?:and|et) \d+ \w+)?)", r"dans \1", t)
    t = re.sub(r"\b(\d+ \w+) and (\d+ \w+)\b", r"\1 et \2", t)
    t = re.sub(r"\bon ((?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\b)", r"\1", t)
    t = re.sub(r"\bat (\d{1,2}:\d{2})", r"à \1", t)
    t = re.sub(r"\buntil (\d{1,2}:\d{2})", r"jusqu'à \1", t)
    t = re.sub(r"\b(\d+) min late\b", r"\1 min de retard", t)
    t = re.sub(r"\bon ((?:lun|mar|mer|jeu|ven|sam|dim)\.)", r"le \1", t)
    t = re.sub(r"\((mon|tue|wed|thu|fri|sat|sun)\)", lambda m: "(" + DAYS_SHORT[m.group(1).lower()] + ")", t, flags=re.I)
    t = t.replace(" and ", " et ").replace("..", ".")
    return t


def _q(text: str) -> str:
    """Translate around the quoted parts, never inside them."""
    parts, last, out = list(QUOTE.finditer(text)), 0, []
    for m in parts:
        out.append(when(text[last:m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(when(text[last:]))
    return "".join(out)


def de(word: str) -> str:
    """“de maths”, “d'histoire”."""
    return ("d'" if re.match(r"[aeiouyhàâéèêîôûAEIOUYHÉÈ]", word or "") else "de ") + word


def _n(n: str, one: str, many: str) -> str:
    return f"{n} {one if n == '1' else many}"


# (pattern on one sentence, French) — {1}, {2}… are the groups; {w1} the group with its dates and times translated
S = [
    # time and date
    (r"It is (\d{1,2}:\d{2}), sir\.", "Il est {1}, monsieur."),
    (r"It is (\d{1,2}:\d{2}) on (.+), sir\.", "Il est {1}, le {w2}, monsieur."),
    (r"Today is (.+), sir\.", "Nous sommes le {w1}, monsieur."),
    (r"Tomorrow will be (.+), sir\.", "Demain, nous serons le {w1}, monsieur."),
    (r"Yesterday was (.+), sir\.", "Hier, nous étions le {w1}, monsieur."),
    (r"The day after tomorrow will be (.+), sir\.", "Après-demain, nous serons le {w1}, monsieur."),
    (r"It is (\d{4}), sir\.", "Nous sommes en {1}, monsieur."),
    (r"It is (\w+) (\d{4}), sir\.", "Nous sommes en {w1} {2}, monsieur."),
    (r"It is week (\d+) of (\d{4}), sir\.", "C'est la semaine {1} de {2}, monsieur."),
    (r"(\d{1,2}) (\w+) (\d{4}) (is|was|will be) a (\w+), sir\.", lambda g: f"Le {g[1]} {when(g[2])} {g[3]} {'est' if g[4] == 'is' else 'était' if g[4] == 'was' else 'sera'} un {when(g[5])}, monsieur."),
    # timers, alarms, reminders
    (r"Timer set for (.+?)(?: — (.+))?, sir\.", lambda g: f"Minuteur réglé sur {when(g[1])}" + (f" — {g[2]}" if g[2] else "") + ", monsieur."),
    (r"Alarm set for (.+), sir\.", "Réveil réglé {w1}, monsieur."),
    (r"Very good, sir\.", "Très bien, monsieur."),
    (r"I will remind you (.+?): (“.*”)\.", "Je vous le rappellerai {w1} : {2}."),
    (r"I will remind you to (.+) (\S+ at \d{1,2}:\d{2}|today|tomorrow|.+?), sir\.", "Je vous rappellerai de {1} {w2}, monsieur."),
    (r"You have no active timers or reminders, sir\.", "Vous n'avez aucun minuteur ni rappel en cours, monsieur."),
    (r"You have no active timers or reminders\.", "Vous n'avez aucun minuteur ni rappel en cours."),
    (r"You have no active (timer|reminder|alarm)s, sir\.", lambda g: {"timer": "Vous n'avez aucun minuteur en cours, monsieur.", "reminder": "Vous n'avez aucun rappel en cours, monsieur.", "alarm": "Vous n'avez aucun réveil en cours, monsieur."}[g[1]]),
    (r"Cancelled (\d+) (timer|reminder|alarm)s?, sir\.", lambda g: f"{g[1]} {dict(timer='minuteur', reminder='rappel', alarm='réveil')[g[2]]}{'s' if g[1] != '1' else ''} annulé{'s' if g[1] != '1' else ''}, monsieur."),
    (r"For how long, sir\?", "Pour combien de temps, monsieur ?"),
    (r"For example: (“.*”)\.", "Par exemple : {1}."),
    # notes, tasks, calendar
    (r"Noted: (“.*”), sir\.", "C'est noté : {1}, monsieur."),
    (r"Added (“.*”) to your to-do list, sir\.", "J'ai ajouté {1} à votre liste de tâches, monsieur."),
    (r"Added (“.*”) to your to-do list, due (.+), sir\.", "J'ai ajouté {1} à votre liste de tâches, pour {w2}, monsieur."),
    (r"Added (“.*”) to your calendar for (.+), sir\.", "J'ai ajouté {1} à votre agenda pour {w2}, monsieur."),
    (r"You have (\d+) open tasks?:", lambda g: f"Vous avez {g[1]} tâche{'s' if g[1] != '1' else ''} en cours :"),
    (r"You have no open tasks, sir\.", "Vous n'avez aucune tâche en cours, monsieur."),
    (r"You have no notes yet, sir\.", "Vous n'avez pas encore de notes, monsieur."),
    (r"Say (“note that …”) to save one\.", "Dites « note que … » pour en garder une."),
    (r"I found no note about (“.*”), sir\.", "Je n'ai trouvé aucune note sur {1}, monsieur."),
    (r"(Today|Tomorrow|Yesterday):", lambda g: when(g[1]).capitalize() + " :"),
    (r"On (\w+):", lambda g: when(g[1]).capitalize() + " :"),
    (r"That time has already passed, sir\.", "Cette heure est déjà passée, monsieur."),
    (r"Tell me a future date\.", "Donnez-moi une date à venir."),
    (r"That date has already passed, sir\.", "Cette date est déjà passée, monsieur."),
    # focus
    (r"Focus session started, sir: (\d+) min(?: on (.+?))?, until (\d{1,2}:\d{2})\.", lambda g: f"Séance de concentration lancée, monsieur : {g[1]} min" + (f" sur {g[2]}" if g[2] else "") + f", jusqu'à {g[3]}."),
    (r"Then a (\d+) minute break\.", "Puis {1} minutes de pause."),
    (r"I will keep quiet until then\.", "Je ne vous dérange pas d'ici là."),
    (r"Say (“stop focus”) to end it early\.", "Dites « arrête la concentration » pour l'arrêter avant."),
    (r"Focus session cancelled, sir\.", "Séance de concentration annulée, monsieur."),
    # homework
    (r"Noted, sir: (.+), due (.+?)( \(your next lesson\))?\.", lambda g: f"C'est noté, monsieur : {g[1]}, pour {when(g[2])}" + (" (votre prochain cours)" if g[3] else "") + "."),
    (r"Your homework, sir \((\d+)\):", "Vos devoirs, monsieur ({1}) :"),
    (r"Homework for (.+), sir:", "Devoirs pour {w1}, monsieur :"),
    (r"Homework (this week|next week), sir:", lambda g: f"Devoirs {when(g[1])}, monsieur :"),
    (r"No homework (.+), sir\.", "Pas de devoirs {w1}, monsieur."),
    (r"You have no homework, sir\.", "Vous n'avez pas de devoirs, monsieur."),
    (r"Well done, sir\. Marked as done: (.+)\.", "Bravo, monsieur. C'est fait : {1}."),
    (r"Removed: (.+)\.", "Supprimé : {1}."),
    (r"I have no open (.+) homework, sir\.", lambda g: f"Je n'ai pas de devoirs {de(g[1])} en cours, monsieur."),
    (r"I have no open homework, sir\.", "Je n'ai pas de devoirs en cours, monsieur."),
    # study coach
    (r"No revision session is running, sir\.", "Aucune séance de révision en cours, monsieur."),
    (r"Say “start revision” to begin one\.", "Dites « commence ma révision » pour en lancer une."),
    (r"There is no revision planned for today, sir\.", "Aucune révision n'est prévue aujourd'hui, monsieur."),
    (r"Revision started, sir: (.+) for (\d+) minutes, until (\d{1,2}:\d{2}) \(session (\d+) of (\d+) before the (.+?) (on .+|today|tomorrow)\)\.",
     lambda g: f"Révision lancée, monsieur : {g[1]} pendant {g[2]} minutes, jusqu'à {g[3]} (séance {g[4]} sur {g[5]} avant {g[6]} " + ("le " + when(g[7][3:]) if g[7].startswith("on ") else when(g[7])) + ")."),
    (r"Warm-up first\.", "D'abord un échauffement."),
    (r"Well done, sir: (.+) session (\d+) of (\d+), (\d+) to go before the test\.", "Bravo, monsieur : séance {2} sur {3} de {1}, encore {4} avant le test."),
    (r"Well done, sir: (.+) session (\d+) of (\d+), the last one before the test\.", "Bravo, monsieur : séance {2} sur {3} de {1}, la dernière avant le test."),
    (r"How was it: easy, OK or hard\?", "C'était comment : facile, correct ou dur ?"),
    (r"Noted, sir\. The plan stays as it is\.", "C'est noté, monsieur. Le programme reste le même."),
    (r"Good, sir\. I dropped the (.+) session: (\d+) left before the test\.", "Bien, monsieur. J'ai enlevé la séance de {w1} : il en reste {2} avant le test."),
    (r"Then a bit more practice, sir: I added a (.+) session (.+)\.", "Alors un peu plus d'entraînement, monsieur : j'ai ajouté une séance de {1} {w2}."),
    (r"Your revision plan, sir \((\d+) sessions?\):", lambda g: f"Votre programme de révision, monsieur ({_n(g[1], 'séance', 'séances')}) :"),
    (r"Revision on (.+) done, sir: session (\d+) of (\d+)\.", "Révision de {1} terminée, monsieur : séance {2} sur {3}."),
    # transport
    (r"From (.+?) to (.+?)(, to arrive by (\d{1,2}:\d{2})|, from (\d{1,2}:\d{2}))?, sir:", lambda g: f"De {g[1]} à {g[2]}" + (f", pour arriver avant {g[4]}" if g[4] else f", à partir de {g[5]}" if g[5] else "") + ", monsieur :"),
    (r"Next departures from (.+), sir:", "Prochains départs de {1}, monsieur :"),
    (r"I found no connection from (.+) to (.+), sir\.", "Je n'ai trouvé aucune correspondance de {1} à {2}, monsieur."),
    (r"Leave (in .+?, at \d{1,2}:\d{2}|now \(\d{1,2}:\d{2}\)), sir: the (.+?) from (.+?) at (\d{1,2}:\d{2})(, on time| \(\d+ min late\)), at (.+?) at (\d{1,2}:\d{2})\.",
     lambda g: f"Partez {when(g[1]).replace('now', 'maintenant')}, monsieur : le {when(g[2])} de {g[3]} à {g[4]}{when(g[5])}, à {g[6]} à {g[7]}."),
    (r"First lesson: (.+) at (\d{1,2}:\d{2})\.", "Premier cours : {1} à {2}."),
    (r"Tomorrow, leave at (\d{1,2}:\d{2}), sir: the (.+?) from (.+?) at (\d{1,2}:\d{2}), at (.+?) at (\d{1,2}:\d{2}), for (.+) at (\d{1,2}:\d{2})\.",
     "Demain, partez à {1}, monsieur : le {w2} de {3} à {4}, à {5} à {6}, pour {7} à {8}."),
    (r"Tell me your home stop and your school stop first, sir: Settings > Planner > Public transport\.",
     "Indiquez-moi d'abord votre arrêt de maison et celui de l'école, monsieur : Réglages > Agenda > Transports publics."),
    (r"I could not reach the Swiss timetable \(transport\.opendata\.ch\)\.", "Je n'arrive pas à joindre l'horaire suisse (transport.opendata.ch)."),
    (r"Is the internet connection up\?", "La connexion internet marche-t-elle ?"),
    (r"From which stop, sir\?", "Depuis quel arrêt, monsieur ?"),
    (r"From where, sir\?", "Depuis où, monsieur ?"),
    (r"For example (“.*”), or set your home stop in Settings > Planner > Public transport\.", "Par exemple {1}, ou indiquez votre arrêt de maison dans Réglages > Agenda > Transports publics."),
    (r"Say (“.*”), or set your home stop in Settings > Planner > Public transport\.", "Dites {1}, ou indiquez votre arrêt de maison dans Réglages > Agenda > Transports publics."),
    # memory
    (r"I do not remember anything about (“.*”), sir\.", "Je ne me souviens de rien sur {1}, monsieur."),
    (r"I found nothing about (“.*”) in our chats, sir\.", "Je n'ai rien trouvé sur {1} dans nos conversations, monsieur."),
    (r"I have nothing about (“.*”), sir\.", "Je n'ai rien sur {1}, monsieur."),
    (r"Forgotten, sir: (\d+) messages? from our chats and (\d+) memor(?:y|ies) about (“.*”)\.",
     lambda g: f"Oublié, monsieur : {_n(g[1], 'message', 'messages')} de nos conversations et {_n(g[2], 'souvenir', 'souvenirs')} sur {g[3]}."),
    (r"I have stopped learning from our chats, sir\.", "J'ai arrêté d'apprendre de nos conversations, monsieur."),
    (r"What I already learned stays until you delete it in Settings > Memory\.", "Ce que j'ai déjà appris reste jusqu'à ce que vous le supprimiez dans Réglages > Mémoire."),
    # weather
    (r"I cannot reach the weather service for (.+) right now, sir\.", "Je n'arrive pas à joindre la météo pour {1} pour le moment, monsieur."),
    # timetable, exams, the day
    (r"Added (.+) to your timetable, sir: (.+?), (\d{1,2}:\d{2})–(\d{1,2}:\d{2})( in .+)?\.", lambda g: f"J'ai ajouté {g[1]} à votre horaire, monsieur : {when(g[2]).replace('Mondays', 'le lundi')}, {g[3]}–{g[4]}" + (f", salle{g[5][3:]}" if g[5] else "") + "."),
    (r"Added (“.*”) on (.+?) at (\d{1,2}:\d{2}), sir: in (\d+) days?\.", lambda g: f"J'ai ajouté {g[1]} le {when(g[2])} à {g[3]}, monsieur : dans {_n(g[4], 'jour', 'jours')}."),
    (r"Added (“.*”) on (.+?) at (\d{1,2}:\d{2}), sir: (tomorrow|today)\.", lambda g: f"J'ai ajouté {g[1]} le {when(g[2])} à {g[3]}, monsieur : {when(g[4])}."),
    (r"Revision sessions planned in your free time: (.+)\.", "Séances de révision prévues dans votre temps libre : {w1}."),
    (r"Revision planned again, sir, around your timetable and plans:", "Révisions replanifiées, monsieur, autour de votre horaire et de vos plans :"),
    (r"Your revision is already planned, sir:", "Vos révisions sont déjà planifiées, monsieur :"),
    (r"You have no exams or tests in your calendar, sir\.", "Vous n'avez aucun examen ni test dans votre agenda, monsieur."),
    (r"Tell me one, for example (“.*”)\.", "Dites-m'en un, par exemple {1}."),
    (r"Here is your day, (\w+):", "Voici votre journée, {w1} :"),
    (r"Tomorrow: nothing in the calendar yet\.", "Demain : rien dans l'agenda pour l'instant."),
    (r"(\d+) tasks? due tomorrow: (.+)\.", lambda g: f"{_n(g[1], 'tâche', 'tâches')} pour demain : {g[2]}."),
    (r"Good (morning|afternoon|evening), sir\.", lambda g: ("Bonjour" if g[1] != "evening" else "Bonsoir") + ", monsieur."),
    (r"It is (\d{1,2}:\d{2}) on (\w+) (\d{1,2}) (\w+)\.", lambda g: f"Il est {g[1]}, le {when(g[2])} {g[3]} {when(g[4])}."),
    (r"You have (\d+) open tasks?\.", lambda g: f"Vous avez {_n(g[1], 'tâche', 'tâches')} en cours."),
    (r"All systems are nominal\.", "Tous les systèmes sont opérationnels."),
    (r"Your week ahead, sir \((.+)\):", "Votre semaine, monsieur ({w1}) :"),
    (r"Spotify is not connected yet, sir\.", "Spotify n'est pas encore connecté, monsieur."),
    (r"Settings > Shortcuts > Spotify explains the three steps\.", "Réglages > Raccourcis > Spotify explique les trois étapes."),
    (r"I found no notes about (“.*”)\.", "Je n'ai trouvé aucune note sur {1}."),
    (r"Paste the text, or send a photo of your notes\.", "Collez le texte, ou envoyez une photo de vos notes."),
    (r"I have not picked up anything from our chats yet, sir\.", "Je n'ai encore rien retenu de nos conversations, monsieur."),
    (r"Learning is paused \(Settings > Memory\)\.", "L'apprentissage est en pause (Réglages > Mémoire)."),
    (r"You have no flashcards for (.+) yet\.", lambda g: f"Vous n'avez pas encore de fiches {de(g[1])}."),
    (r"Send a photo of your notes and say (“.*”), or say “quiz me on (.+)” to warm up\.", "Envoyez une photo de vos notes en disant « fais des fiches avec cette photo », ou dites « interroge-moi sur {2} » pour vous échauffer."),
    (r"Send a photo of your notes with (“.*”), or say (“.*”), sir\.", "Envoyez une photo de vos notes en disant « fais des fiches avec cette photo », ou dites « fais des fiches avec mes notes de biologie », monsieur."),
    # messages Jarvis sends by itself
    (r"Time to revise (.+), sir: (\d+) minutes, session (\d+) of (\d+) before the (.+?) (on .+|today|tomorrow)\.",
     lambda g: f"C'est l'heure de réviser {g[1]}, monsieur : {g[2]} minutes, séance {g[3]} sur {g[4]} avant {g[5]} " + ("le " + when(g[6][3:]) if g[6].startswith("on ") else when(g[6])) + "."),
    (r"Say “start revision” and I will warm you up with your flashcards first\.", "Dites « commence ma révision » et je vous échauffe d'abord avec vos fiches."),
    (r"You missed a revision session, sir, so I moved it: (.+) \((.+)\) → (.+)\.", "Vous avez manqué une séance de révision, monsieur, je l'ai donc déplacée : {1} ({w2}) → {w3}."),
    (r"Change of plan: the (\d{1,2}:\d{2}) is cancelled or too late now\.", "Changement de programme : celui de {1} est supprimé ou arrive trop tard maintenant."),
    (r"Your (.+) is late, so you have a little longer\.", "Votre {w1} est en retard, vous avez donc un peu plus de temps."),
    (r"Heads up, sir: the (\d{1,2}:\d{2}) is now (\d+) min late, but you still make it\.", "Attention, monsieur : celui de {1} a maintenant {2} min de retard, mais vous arrivez à temps."),
    (r"New on Classroom, sir: (.+)\.", lambda g: "Nouveau sur Classroom, monsieur : " + re.sub(r", due (\w+)", lambda m: ", pour " + when(m.group(1)), g[1]) + "."),
    (r"Focus session done, sir: (.+?)( on (.+))?\.", lambda g: f"Séance de concentration terminée, monsieur : {when(g[1])}" + (f" sur {g[3]}" if g[3] else "") + "."),
    (r"That makes (.+) today\.", "Cela fait {w1} aujourd'hui."),
    (r"Take a (\d+) minute break\.", "Faites une pause de {1} minutes."),
    (r"Break over, sir\.", "Fin de la pause, monsieur."),
    (r"Say “focus” when you are ready for another session\.", "Dites « concentration » quand vous êtes prêt pour une autre séance."),
    (r"Focus session stopped, sir\.", "Séance de concentration arrêtée, monsieur."),
    (r"You did (.+)\.", "Vous avez fait {w1}."),
    # showing Autopilot how
    (r"Go ahead, sir: I am watching how you (.+)\.", "Allez-y, monsieur : je regarde comment vous faites : {1}."),
    (r"Do it the way you normally would; I note your clicks, typing and keys \(never passwords\)\.",
     "Faites-le comme d'habitude ; je note vos clics, ce que vous tapez et les touches (jamais les mots de passe)."),
    (r"Press Ctrl\+Shift\+F9 or say “stop recording” when you are done\.", "Appuyez sur Ctrl+Maj+F9 ou dites « arrête l'enregistrement » quand vous avez fini."),
    (r"I did not see any clicks or typing, sir, so there is nothing to learn\.", "Je n'ai vu aucun clic ni rien de tapé, monsieur, il n'y a donc rien à apprendre."),
    (r"Try again with “watch me …”\.", "Réessayez avec « regarde-moi faire … »."),
    (r"Recording cancelled, sir\.", "Enregistrement annulé, monsieur."),
    (r"Nothing was kept\.", "Rien n'a été gardé."),
    (r"Showing me how to do something works at the PC only, sir\.", "Me montrer comment faire quelque chose ne fonctionne qu'au PC, monsieur."),
    (r"I am already watching you (.+)\.", "Je vous regarde déjà ({1})."),
    (r"Press Ctrl\+Shift\+F9 or say “stop recording” first\.", "Appuyez d'abord sur Ctrl+Maj+F9 ou dites « arrête l'enregistrement »."),
    # the usual politeness
    (r"Done, sir\.", "C'est fait, monsieur."),
    (r"Of course, sir\.", "Bien sûr, monsieur."),
]
COMPILED = [(re.compile(p, re.S), r) for p, r in S]


def _fill(rule, m: re.Match) -> str:
    g = [m.group(0)] + list(m.groups())
    if callable(rule):
        return rule(g)

    def sub(x: re.Match) -> str:
        w, i = x.group(1), int(x.group(2))
        v = g[i] or ""
        return when(v) if w else v
    return re.sub(r"\{(w?)(\d)\}", sub, rule)


def sentences(line: str) -> list[str]:
    """Cut a line after “. ”, “? ” or “! ” outside quotes and brackets."""
    out, depth, start, inq = [], 0, 0, False
    for i, ch in enumerate(line):
        if ch == "“":
            inq = True
        elif ch == "”":
            inq = False
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch in ".?!" and not inq and depth == 0 and i + 1 < len(line) and line[i + 1] == " " and not re.search(r"\b(?:e\.g|i\.e|No|vs)$", line[start:i]):
            out.append(line[start:i + 1].strip())
            start = i + 2
    if line[start:].strip():
        out.append(line[start:].strip())
    return out


def sentence(s: str) -> str | None:
    for rx, rule in COMPILED:
        m = rx.fullmatch(s)
        if m:
            return _fill(rule, m)
    return None


def bullet(line: str) -> str:
    """A list item: dates, times and the small words translated; what you wrote stays."""
    body = line[1:].strip()
    body = re.sub(r"^Due (today|tomorrow): ", lambda m: f"Pour {when(m.group(1))} : ", body)
    body = re.sub(r"^(Today|Tomorrow|Yesterday|Mon|Tue|Wed|Thu|Fri|Sat|Sun|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)(?=[ :])",
                  lambda m: when(m.group(1)).capitalize(), body)
    body = re.sub(r"\(for the (.+?) (on .+|today|tomorrow)\)", lambda m: f"(pour {m.group(1)} " + ("le " + when(m.group(2)[3:]) if m.group(2).startswith("on ") else when(m.group(2))) + ")", body)
    body = re.sub(r"^(.+?) on ((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday) \d{1,2} \w+): ", lambda m: f"{m.group(1)} le {when(m.group(2))} : ", body)
    body = re.sub(r"^(.+?) \(in (\d+) days?\): already planned\.", lambda m: f"{m.group(1)} (dans {_n(m.group(2), 'jour', 'jours')}) : déjà planifié.", body)
    body = re.sub(r"^Coming after that: (.+?) on ", r"Ensuite : \1 le ", body)
    body = re.sub(r"^Coming after that: ", "Ensuite : ", body)
    body = re.sub(r"^Revision: (\d+) sessions?: ", lambda m: f"Révisions : {_n(m.group(1), 'séance', 'séances')} : ", body)
    body = re.sub(r"^Homework: (\d+) due: ", lambda m: f"Devoirs : {m.group(1)} à rendre : ", body)
    body = re.sub(r"^Tests: ", "Tests : ", body)
    body = re.sub(r"^Flashcards: (\d+) due; say “review my cards”\.", lambda m: f"Fiches : {m.group(1)} à revoir ; dites « révise mes fiches ».", body)
    body = re.sub(r"\((\d+) of (\d+) revision sessions done\)", r"(\1 séances de révision sur \2 faites)", body)
    body = re.sub(r"^No tasks ticked off today\.", "Aucune tâche cochée aujourd'hui.", body)
    body = re.sub(r"\(due ", "(pour ", body)
    body = re.sub(r", (\d+) min \(", r", \1 min (", body)
    body = re.sub(r"\btowards\b", "direction", body)
    body = re.sub(r"\barrives\b", "arrive à", body)
    body = re.sub(r"\bplatform\b", "voie", body)
    body = re.sub(r"\b(\d) changes?\b", lambda m: f"{m.group(1)} changement{'s' if m.group(1) != '1' else ''}", body)
    body = re.sub(r"\bbus (\w+)", r"bus \1", body)
    body = re.sub(r"\bcancelled\b", "supprimé", body)
    return "• " + _q(body)


def to_french(text: str) -> str | None:
    if not text or not text.strip():
        return None
    out = []
    for line in text.split("\n"):
        if not line.strip():
            out.append(line)
            continue
        if line.lstrip().startswith(("•", "- ")):
            out.append(bullet(line.lstrip().replace("- ", "• ", 1) if line.lstrip().startswith("- ") else line.lstrip()))
            continue
        done = []
        for s in sentences(line):
            fr = sentence(s)
            if fr is None:
                return None                         # one unknown sentence: the AI model translates the whole answer
            done.append(fr)
        out.append(" ".join(done))
    return "\n".join(out)

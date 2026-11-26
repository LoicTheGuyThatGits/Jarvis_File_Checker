"""Grades: "I got a 5 in maths", "what's my average in French?", "what do I need on the next maths test to keep a 4.5?"

Grades are kept in data/grades.json with their subject, weight (a test that counts double has weight 2), date and an optional
note. Until one is chosen, the scale follows the country of your town: Swiss (1 to 6, 6 best, 4 to pass, report cards
rounded to the half point), France (0-20), Germany (1-6, 1 best), otherwise percent; your own can be set too. "Start a new term" makes averages start fresh (older grades stay).

    Grades(path)                       .data() .add(...) .remove(id) .set_scale(...) .new_term(day)
    command(text, store, now, known_subjects, parse_when)   the reply, or None when the message is not about grades
    summary(store)                     averages for the page
"""
from __future__ import annotations

import json
import re
import secrets
import threading
import time
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

PRESETS = {
    "swiss": {"name": "Swiss (1–6, 6 best)", "min": 1.0, "max": 6.0, "pass": 4.0, "higher_better": True, "round": 0.5},
    "france": {"name": "France (0–20)", "min": 0.0, "max": 20.0, "pass": 10.0, "higher_better": True, "round": 0.5},
    "germany": {"name": "Germany (1–6, 1 best)", "min": 1.0, "max": 6.0, "pass": 4.0, "higher_better": False, "round": 0.5},
    "percent": {"name": "Percent (0–100)", "min": 0.0, "max": 100.0, "pass": 50.0, "higher_better": True, "round": 1.0},
}
MAX_GRADES = 1000
NUM = r"\d{1,3}(?:[.,]\d{1,2})?"
KIND = r"(?:test|exam|quiz|essay|presentation|oral|project|homework|assignment|evaluation|dictation|vocab(?:ulary)?\s+test|contr[ôo]le|examen|exposé|expose|travail|devoir)"


def fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", (text or "").lower()) if not unicodedata.combining(c))


def subject_key(text: str) -> str:
    t = re.sub(rf"\b(?:my|the|a|an|next|in|de|du|la|le|les|en|cours|class|lesson|{KIND}s?)\b", " ", fold(text))
    t = re.sub(r"\bmath\b|\bmathematics\b|\bmathematiques\b", "maths", t)
    return re.sub(r"\s+", " ", re.sub(r"[^\w ]", " ", t)).strip()


def num(text: str) -> float:
    return float(str(text).replace(",", "."))


def fmt(x: float | None) -> str:
    if x is None:
        return "–"
    return f"{x:.2f}".rstrip("0").rstrip(".")


def plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


class Grades:
    def __init__(self, path: Path, default="swiss"):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.default = default                     # a preset name, or a function giving one (the country of your town)

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data = data if isinstance(data, dict) else {}
        scale = data.get("scale") if isinstance(data.get("scale"), dict) else {}
        first = self.default() if callable(self.default) else self.default
        first = first if first in PRESETS else "percent"
        base = dict(PRESETS[first], preset=first)
        try:
            merged = {"preset": str(scale.get("preset") or first), "min": float(scale.get("min", base["min"])), "max": float(scale.get("max", base["max"])),
                      "pass": float(scale.get("pass", base["pass"])), "higher_better": scale.get("higher_better", True) is not False,
                      "round": float(scale.get("round", base["round"]))}
        except (TypeError, ValueError):
            merged = {k: base[k] for k in ("preset", "min", "max", "pass", "higher_better", "round")}
        grades = []
        for g in data.get("grades") or []:
            try:
                grades.append({"id": str(g.get("id") or secrets.token_hex(4)), "subject": str(g["subject"])[:40], "value": float(g["value"]),
                               "weight": float(g.get("weight") or 1), "date": date.fromisoformat(str(g["date"])).isoformat(), "note": str(g.get("note") or "")[:60],
                               "added": float(g.get("added") or 0)})
            except (KeyError, TypeError, ValueError):
                continue
        term = str(data.get("term_start") or "")
        try:
            term_ts = float(data.get("term_ts") or 0)
        except (TypeError, ValueError):
            term_ts = 0.0
        return {"scale": merged, "grades": grades, "term_start": term if re.fullmatch(r"\d{4}-\d{2}-\d{2}", term) else "", "term_ts": term_ts}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def data(self) -> dict:
        with self.lock:
            return self._load()

    def scale(self) -> dict:
        return self.data()["scale"]

    def current(self) -> list[dict]:
        """The grades of this term (all of them when no term was started)."""
        d = self.data()
        return [g for g in d["grades"] if not d["term_ts"] or g["added"] >= d["term_ts"]]

    def add(self, subject: str, value: float, weight: float = 1.0, day: date | None = None, note: str = "") -> dict:
        subject = re.sub(r"\s+", " ", str(subject)).strip(" .,:;")[:40]
        if not subject:
            raise ValueError("Which subject is the grade for?")
        with self.lock:
            data = self._load()
            sc = data["scale"]
            if not sc["min"] <= value <= sc["max"]:
                raise ValueError(f"A grade must be between {fmt(sc['min'])} and {fmt(sc['max'])} on your scale.")
            if not 0 < weight <= 10:
                raise ValueError("The weight must be between 0 and 10 (1 is normal, 2 counts double).")
            if len(data["grades"]) >= MAX_GRADES:
                raise ValueError("That is a lot of grades; remove some old ones first.")
            known = next((g["subject"] for g in data["grades"] if subject_key(g["subject"]) == subject_key(subject)), None)
            grade = {"id": secrets.token_hex(4), "subject": known or (subject[:1].upper() + subject[1:]), "value": round(float(value), 2), "weight": float(weight),
                     "date": (day or date.today()).isoformat(), "note": re.sub(r"\s+", " ", note or "").strip()[:60], "added": time.time()}
            data["grades"].append(grade)
            self._save(data)
            return grade

    def remove(self, grade_id: str) -> dict | None:
        with self.lock:
            data = self._load()
            hit = next((g for g in data["grades"] if g["id"] == grade_id), None)
            if hit:
                data["grades"] = [g for g in data["grades"] if g["id"] != grade_id]
                self._save(data)
            return hit

    def set_scale(self, preset: str | None = None, **custom) -> dict:
        with self.lock:
            data = self._load()
            if preset in PRESETS:
                data["scale"] = {k: PRESETS[preset][k] for k in ("min", "max", "pass", "higher_better", "round")}
                data["scale"]["preset"] = preset
            else:
                try:
                    lo, hi, ps = float(custom["min"]), float(custom["max"]), float(custom["pass"])
                except (KeyError, TypeError, ValueError):
                    raise ValueError("Give the lowest grade, the highest grade and the pass mark.") from None
                if not lo < hi or not lo <= ps <= hi:
                    raise ValueError("The pass mark must lie between the lowest and the highest grade.")
                data["scale"] = {"preset": "custom", "min": lo, "max": hi, "pass": ps, "higher_better": custom.get("higher_better", True) is not False,
                                 "round": float(custom.get("round") or 0) if float(custom.get("round") or 0) >= 0 else 0.0}
            outside = [g for g in data["grades"] if not data["scale"]["min"] <= g["value"] <= data["scale"]["max"]]
            if outside:
                raise ValueError(f"{plural(len(outside), 'grade')} would fall outside that scale (for example {fmt(outside[0]['value'])} in {outside[0]['subject']}). Remove them first.")
            self._save(data)
            return data["scale"]

    def new_term(self, day: date | None = None) -> str:
        with self.lock:
            data = self._load()
            data["term_start"] = (day or date.today()).isoformat()
            data["term_ts"] = time.time()
            self._save(data)
            return data["term_start"]


# ---------------- arithmetic ----------------
def average(grades: list[dict]) -> float | None:
    w = sum(g["weight"] for g in grades)
    return sum(g["value"] * g["weight"] for g in grades) / w if w else None


def rounded(x: float | None, sc: dict) -> float | None:
    if x is None or not sc.get("round"):
        return x
    step = sc["round"]
    return round(round(x / step) * step, 2)


def passing(x: float, sc: dict) -> bool:
    return x >= sc["pass"] if sc["higher_better"] else x <= sc["pass"]


def by_subject(grades: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for g in sorted(grades, key=lambda g: g["date"]):          # same day: in the order they were entered
        out.setdefault(g["subject"], []).append(g)
    return out


def needed(grades: list[dict], target: float, weight: float, sc: dict) -> float:
    """The grade the next test (of this weight) must have so the average reaches the target."""
    w = sum(g["weight"] for g in grades)
    s = sum(g["value"] * g["weight"] for g in grades)
    return (target * (w + weight) - s) / weight


def summary(store: Grades) -> dict:
    sc = store.scale()
    subjects = []
    for name, gs in sorted(by_subject(store.current()).items(), key=lambda kv: kv[0].lower()):
        avg = average(gs)
        subjects.append({"subject": name, "average": round(avg, 2), "rounded": rounded(avg, sc), "count": len(gs), "passing": passing(avg, sc),
                         "grades": [{"id": g["id"], "value": g["value"], "weight": g["weight"], "date": g["date"], "note": g["note"]} for g in gs]})
    avgs = [s["average"] for s in subjects]
    overall = sum(avgs) / len(avgs) if avgs else None
    d = store.data()
    return {"scale": sc, "presets": {k: v["name"] for k, v in PRESETS.items()}, "subjects": subjects, "term_start": d["term_start"],
            "overall": round(overall, 2) if overall is not None else None, "earlier": len(d["grades"]) - len(store.current())}


# ---------------- understanding messages ----------------
CLEAN = r"^(?:(?:hey\s+)?jarvis[,.:]?\s+)?(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?)?(?:tell\s+me\s+)?"
WEIGHT_WORDS = [(r"\b(?:triple|counts?\s+(?:three\s+times|triple)|weight\s*3|x\s*3|coefficient\s*3)\b", 3.0),
                (r"\b(?:double|counts?\s+(?:twice|double)|weight\s*2|x\s*2|coefficient\s*2|coef\s*2)\b", 2.0),
                (r"\b(?:half|counts?\s+half|weight\s*0[.,]5|x\s*0[.,]5)\b", 0.5)]


def weight_in(text: str) -> float:
    for rx, w in WEIGHT_WORDS:
        if re.search(rx, text, re.I):
            return w
    return 1.0


def canonical(subject: str, store: Grades, known: list[str]) -> str:
    key = subject_key(subject)
    for name in [g["subject"] for g in store.data()["grades"]] + list(known or []):
        if subject_key(name) == key:
            return name
    s = subject.strip()
    return s[:1].upper() + s[1:]


def subject_line(name: str, gs: list[dict], sc: dict) -> str:
    gs = sorted(gs, key=lambda g: g["date"])
    avg = average(gs)
    r = rounded(avg, sc)
    marks = ", ".join(fmt(g["value"]) + (" (double)" if g["weight"] == 2 else " (half)" if g["weight"] == 0.5 else f" (×{fmt(g['weight'])})" if g["weight"] != 1 else "") for g in gs)
    rnd = f" (rounds to {fmt(r)})" if r is not None and abs(r - avg) > 1e-9 else ""
    low = "" if passing(avg, sc) else f", just under {fmt(sc['pass'])}" if r is not None and passing(r, sc) else f", below {fmt(sc['pass'])}"
    return f"{name}: {fmt(round(avg, 2))}{rnd}{low}, from {plural(len(gs), 'grade')}: {marks}"


def command(text: str, store: Grades, now: datetime | None = None, known: list[str] | None = None, parse_when=None) -> str | None:
    now = now or datetime.now()
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = re.sub(CLEAN, "", t, flags=re.I)
    t = re.sub(r"\s*(?:please)?\s*[.!?]*$", "", t, flags=re.I).strip()
    if not t or len(t) > 200:
        return None
    sc = store.scale()
    # ---- adding ----
    m = (re.fullmatch(rf"(?:i\s+)?(?:just\s+)?(?:got|get|received|scored|had|have)\s+(?:a\s+|an\s+)?(?P<v>{NUM})(?:\s*(?:/|out\s+of)\s*(?P<of>\d{{1,3}}))?\s+(?:in|on|for|at)\s+(?:my\s+|the\s+|a\s+|an\s+)?(?P<subj>[^,]+?)(?P<rest>(?:\s+(?:{KIND}|test|exam)s?)?(?:[\s,]+.*)?)", t, re.I)
         or re.fullmatch(rf"(?:add|record|log|save|note)\s+(?:a\s+|an\s+|my\s+)?(?:grade|mark|note)\s+(?:of\s+)?(?P<v>{NUM})(?:\s*(?:/|out\s+of)\s*(?P<of>\d{{1,3}}))?\s+(?:in|for|to)\s+(?:my\s+|the\s+)?(?P<subj>[^,]+?)(?P<rest>(?:\s+(?:{KIND}|test|exam)s?)?(?:[\s,]+.*)?)", t, re.I)
         or re.fullmatch(rf"(?:add|record|log|save)\s+(?:a\s+|an\s+)?(?P<v>{NUM})(?:\s*(?:/|out\s+of)\s*(?P<of>\d{{1,3}}))?\s+(?:in|for|to)\s+(?:my\s+|the\s+)?(?P<subj>[^,]+?)(?P<rest>(?:\s+(?:{KIND}|test|exam)s?)?(?:[\s,]+.*)?)", t, re.I))
    if m and not re.search(r"\b(?:minutes?|hours?|seconds?|days?|weeks?|euros?|francs?|chf|dollars?|points?\s+in\s+(?:fortnite|the\s+game))\b", t, re.I):
        subj = re.sub(rf"\s+(?:{KIND}|test|exam)s?$", "", m.group("subj").strip(), flags=re.I)
        if len(subj) > 30 or not re.search(r"[^\W\d_]", subj) or re.search(r"\b(?:row|a\s+row|total|life|my\s+head)\b", subj, re.I):
            return None
        rest = m.group("rest") or ""
        kind = re.search(rf"\b{KIND}\b", rest + " " + m.group("subj"), re.I)
        value = num(m.group("v"))
        conv = ""
        if m.group("of"):
            out_of = int(m.group("of"))
            if not 0 < out_of <= 500 or value > out_of:
                return f"{fmt(value)} out of {out_of} does not add up, sir."
            share = value / out_of
            value = sc["min"] + (sc["max"] - sc["min"]) * (share if sc["higher_better"] else 1 - share)
            value = round(value, 2)
            conv = f" ({fmt(num(m.group('v')))}/{out_of} on your {fmt(sc['min'])}–{fmt(sc['max'])} scale)"
        day = now.date()
        if parse_when and rest.strip():
            when = parse_when(rest, now)
            if when.get("date") and when["date"] <= now.date():
                day = when["date"]
        if re.search(r"\byesterday\b|\bhier\b", rest, re.I):
            day = now.date() - timedelta(days=1)
        weight = weight_in(rest)
        name = canonical(subj, store, known or [])
        try:
            g = store.add(name, value, weight, day, kind.group(0).lower() if kind else "")
        except ValueError as exc:
            return str(exc)
        gs = by_subject(store.current()).get(g["subject"], [])
        avg = average(gs)
        head = f"Recorded {fmt(g['value'])}{conv} in {g['subject']}" + (" (counts double)" if weight == 2 else " (counts half)" if weight == 0.5 else f" (×{fmt(weight)})" if weight != 1 else "") + ", sir. "
        if len(gs) == 1:
            return head + f"It is your first {g['subject']} grade this term."
        r = rounded(avg, sc)
        tail = f"Your {g['subject']} average is now {fmt(round(avg, 2))}" + (f" (rounds to {fmt(r)})" if r is not None and abs(r - avg) > 1e-9 else "") + f", from {plural(len(gs), 'grade')}."
        if not passing(avg, sc):
            tail += f" That is just under {fmt(sc['pass'])}." if r is not None and passing(r, sc) else f" That is below {fmt(sc['pass'])}."
        return head + tail
    # ---- what do I need ----
    m = (re.fullmatch(rf"what\s+(?:grade\s+|mark\s+)?do\s+i\s+need\s+(?:on|in|for|at)\s+(?:my\s+|the\s+)?(?:next\s+)?(?P<subj>.+?)(?:\s+(?:{KIND}|test|exam))?\s+(?:to\s+(?:get|have|keep|reach|stay\s+(?:at|above)|end\s+(?:up\s+)?with|pass|get\s+back\s+to)|for)\s*(?:an?\s+|at\s+least\s+)?(?:average\s+(?:of\s+)?)?(?P<target>{NUM})?(?:\s+(?:average|overall))?(?P<rest>.*)", t, re.I)
         or re.fullmatch(rf"what\s+(?:grade\s+)?do\s+i\s+need\s+to\s+(?P<pass>pass)\s+(?:in\s+)?(?P<subj>.+?)(?P<rest>(?:\s+.*)?)", t, re.I))
    if m:
        name = canonical(m.group("subj"), store, known or [])
        gs = [g for g in store.current() if subject_key(g["subject"]) == subject_key(name)]
        target = num(m.group("target")) if m.groupdict().get("target") else sc["pass"]
        if not sc["min"] <= target <= sc["max"]:
            return f"{fmt(target)} is not on your {fmt(sc['min'])}–{fmt(sc['max'])} scale, sir."
        weight = weight_in(m.group("rest") or "")
        if not gs:
            return f"You have no {name} grades yet this term, sir, so the next one simply needs to be {fmt(target)} or {'better' if sc['higher_better'] else 'lower'}."
        x = needed(gs, target, weight, sc)
        w_txt = " (if it counts double)" if weight == 2 else " (if it counts half)" if weight == 0.5 else ""
        now_avg = fmt(round(average(gs), 2))
        best, worst = (sc["max"], sc["min"]) if sc["higher_better"] else (sc["min"], sc["max"])
        if (x > sc["max"] and sc["higher_better"]) or (x < sc["min"] and not sc["higher_better"]):
            reach = (sum(g["value"] * g["weight"] for g in gs) + best * weight) / (sum(g["weight"] for g in gs) + weight)
            return f"Even a {fmt(best)} on the next {name} test{w_txt} would only bring your average from {now_avg} to {fmt(round(reach, 2))}, sir, so {fmt(target)} is out of reach with one test."
        if (x <= sc["min"] and sc["higher_better"]) or (x >= sc["max"] and not sc["higher_better"]):
            return f"Your {name} average is {now_avg}, sir: even a {fmt(worst)} on the next test{w_txt} keeps it at {fmt(target)} {'or above' if sc['higher_better'] else 'or better'}."
        need = f"at least {fmt(round(x + 0.004, 2))}" if sc["higher_better"] else f"{fmt(round(x - 0.004, 2))} or better"
        return f"You need {need} on the next {name} test{w_txt} to bring your average from {now_avg} to {fmt(target)}, sir."
    # ---- averages ----
    m = (re.fullmatch(r"(?:what(?:'s| is| are)\s+)?(?:my\s+)?(?:average|averages|mean|grade\s+average|gpa)\s+(?:in|for|of)\s+(?P<subj>.+)", t, re.I)
         or re.fullmatch(r"(?:what(?:'s| is)\s+)?my\s+(?P<subj>.+?)\s+(?:average|grades?|marks?|mean)", t, re.I)
         or re.fullmatch(r"how\s+am\s+i\s+doing\s+in\s+(?P<subj>.+)", t, re.I)
         or re.fullmatch(r"(?:show|list|read|what\s+are)(?:\s+me)?\s+my\s+(?P<subj>.+?)\s+(?:grades?|marks?)", t, re.I))
    if m and not re.fullmatch(r"(?:overall|general|total|all|whole|full|school|report\s+card)", m.group("subj").strip(), re.I):
        name = canonical(m.group("subj"), store, known or [])
        gs = [g for g in store.current() if subject_key(g["subject"]) == subject_key(name)]
        if not gs:
            if not store.current() and not re.search(r"\b(?:average|grades?|marks?)\b", t, re.I):
                return None
            return f"You have no {name} grades yet this term, sir. Tell me one with, for example, “I got a 5 in {name}”."
        return subject_line(name, gs, sc) + "."
    if re.fullmatch(r"(?:what(?:'s| is| are)\s+)?(?:show\s+(?:me\s+)?|list\s+)?(?:my\s+)?(?:grades|marks|averages|overall\s+average|general\s+average|average|report\s+card)(?:\s+so\s+far|\s+this\s+term)?|how\s+are\s+my\s+grades|how\s+am\s+i\s+doing\s+at\s+school", t, re.I):
        groups = by_subject(store.current())
        if not groups:
            return "You have no grades yet this term, sir. Say, for example, “I got a 5 in maths” (or “a 5.5 on the French test, counts double”)."
        lines = [subject_line(n, gs, sc) for n, gs in sorted(groups.items(), key=lambda kv: kv[0].lower())]
        avgs = [average(gs) for gs in groups.values()]
        overall = sum(avgs) / len(avgs)
        low = [n for n, gs in groups.items() if not passing(average(gs), sc)]
        head = f"Your averages this term, sir (overall {fmt(round(overall, 2))}):"
        tail = (f"\nBelow {fmt(sc['pass'])}: " + ", ".join(sorted(low)) + ".") if low else ""
        return head + "\n" + "\n".join("• " + l for l in lines) + tail
    # ---- removing, terms ----
    if re.fullmatch(r"(?:delete|remove|undo|cancel|scrap)\s+(?:my\s+|the\s+)?(?:last|latest|previous)\s+(?:grade|mark)", t, re.I):
        all_g = store.data()["grades"]
        if not all_g:
            return "There are no grades to remove, sir."
        last = all_g[-1]
        store.remove(last["id"])
        return f"Removed the {fmt(last['value'])} in {last['subject']}, sir."
    m = re.fullmatch(rf"(?:delete|remove)\s+(?:the|my)\s+(?P<v>{NUM})\s+(?:in|from|for)\s+(?:my\s+)?(?P<subj>.+?)(?:\s+(?:grades?|{KIND}))?", t, re.I)
    if m:
        hits = [g for g in store.data()["grades"] if abs(g["value"] - num(m.group("v"))) < 1e-9 and subject_key(g["subject"]) == subject_key(m.group("subj"))]
        if not hits:
            return f"I cannot find a {m.group('v')} in {m.group('subj')}, sir."
        store.remove(hits[-1]["id"])
        return f"Removed the {fmt(hits[-1]['value'])} in {hits[-1]['subject']} ({hits[-1]['date']}), sir."
    if re.fullmatch(r"(?:start|begin)\s+(?:a\s+)?new\s+(?:term|semester|school\s+year|year|trimester)", t, re.I):
        day = store.new_term(now.date())
        return f"New term started on {day}, sir: averages now count only the grades you add from now on. Your earlier grades are kept."
    return None

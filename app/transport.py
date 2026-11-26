"""Swiss public transport: connections, departures and the trip to school, with live delays.

Data from transport.opendata.ch (the Swiss public transport timetable, free, no account). Every train, tram, bus and boat
in Switzerland is there, with the delays the operators report.

    “when's my next train to Geneva?”, “next bus to Zürich HB”, “how do I get to Lausanne by 5pm?”,
    “connections from Bern to Geneva at 7:30”, “departures from Lausanne”, “next departures”,
    “when should I leave for school?”, “is my bus late?”

The trip to school: with a home stop and a school stop in Settings, Jarvis works out each school morning which connection
gets you there in time for your first lesson (minus the walk and a margin), tells you when to leave, checks again for
delays before you go, and tells you (or calls you, if you want) when you have to leave earlier.

    Transport(path)                    settings and the morning's plan (data/transport.json)
    connections(frm, to, when, arrive) the API, cut down to what Jarvis says
    command(text, store, now, ctx)     chat
    tick(store, now, ctx)              messages for the morning trip
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

API = "https://transport.opendata.ch/v1"
DEFAULTS = {"home": "", "school": "", "walk_home": 5, "walk_school": 5, "margin": 5, "morning": True, "notice": 15, "call": False}
KIND = {"B": "bus", "BUS": "bus", "NFB": "bus", "KB": "bus", "T": "tram", "TRAM": "tram", "NFT": "tram", "M": "metro", "BAT": "boat", "BAV": "boat", "FUN": "funicular",
        "PB": "cable car", "GB": "cable car", "LB": "cable car"}
RECHECK = (45, 25, 12)           # minutes before leaving at which the morning connection is looked at again


class TransportError(Exception):
    pass


def _get(route: str, params: dict) -> dict:
    url = API + route + "?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Jarvis (personal assistant)"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise TransportError("The timetable service is busy. Try again in a minute, sir.")
        raise TransportError(f"The timetable service answered with an error ({exc.code}).")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise TransportError("I could not reach the Swiss timetable (transport.opendata.ch). Is the internet connection up?") from exc
    except ValueError:
        raise TransportError("The timetable service sent something I could not read.")


def station(name: str) -> dict | None:
    """The best matching stop: {"id", "name"}."""
    name = (name or "").strip()
    if not name:
        return None
    d = _get("/locations", {"query": name, "type": "station"})
    for s in d.get("stations") or []:
        if s.get("id") and s.get("name"):
            return {"id": str(s["id"]), "name": s["name"]}
    return None


def line_name(journey: dict | None) -> str:
    if not journey:
        return "walk"
    cat, num = str(journey.get("category") or "").strip(), str(journey.get("number") or "").strip()
    kind = KIND.get(cat.upper())
    if kind:
        return f"{kind} {num}".strip()
    name = str(journey.get("name") or "").strip()
    if cat and num and not num.isdigit():
        return num if num.startswith(cat) else f"{cat} {num}"
    return f"{cat}{num}" if cat in ("S", "SN", "R") and num.isdigit() else (name or f"{cat} {num}".strip() or "train")


def _ts(stop: dict, key: str) -> float | None:
    v = stop.get(key + "Timestamp")
    if v:
        return float(v)
    raw = stop.get(key)
    if raw:
        try:
            return datetime.strptime(raw[:19], "%Y-%m-%dT%H:%M:%S").timestamp()
        except ValueError:
            return None
    return None


def _real(stop: dict, key: str) -> tuple[float | None, int]:
    """(the expected time, the delay in minutes): the prognosis when there is one."""
    planned = _ts(stop, key)
    prog = (stop.get("prognosis") or {}).get(key)
    delay = int(stop.get("delay") or 0)
    if prog:
        try:
            expected = datetime.strptime(prog[:19], "%Y-%m-%dT%H:%M:%S").timestamp()
            if planned:
                delay = max(delay, round((expected - planned) / 60))
            return expected, delay
        except ValueError:
            pass
    return (planned + delay * 60 if planned else None), delay


def _conn(c: dict) -> dict:
    frm, to = c.get("from") or {}, c.get("to") or {}
    dep, dep_delay = _real(frm, "departure")
    arr, arr_delay = _real(to, "arrival")
    legs = []
    for s in c.get("sections") or []:
        j = s.get("journey")
        if not j:
            continue
        sd, sa = s.get("departure") or {}, s.get("arrival") or {}
        legs.append({"line": line_name(j), "to": str(j.get("to") or ""), "from": (sd.get("station") or {}).get("name", ""),
                     "dep": _ts(sd, "departure"), "platform": sd.get("platform") or "", "arr_at": (sa.get("station") or {}).get("name", "")})
    cancelled = any(bool((s.get("journey") or {}).get("isCancelled")) for s in c.get("sections") or [])
    return {"from": (frm.get("station") or {}).get("name", ""), "to": (to.get("station") or {}).get("name", ""), "dep_planned": _ts(frm, "departure"),
            "dep": dep, "arr": arr, "delay": dep_delay, "arr_delay": arr_delay, "platform": frm.get("platform") or "", "transfers": int(c.get("transfers") or 0),
            "legs": legs, "cancelled": cancelled}


def connections(frm: str, to: str, when: datetime | None = None, arrive: bool = False, limit: int = 4) -> list[dict]:
    params = {"from": frm, "to": to, "limit": limit}
    if when:
        params.update(date=when.strftime("%Y-%m-%d"), time=when.strftime("%H:%M"))
        if arrive:
            params["isArrivalTime"] = 1
    d = _get("/connections", params)
    return [_conn(c) for c in d.get("connections") or []]


def departures(stop: str, limit: int = 8, when: datetime | None = None) -> tuple[str, list[dict]]:
    params = {"station": stop, "limit": limit}
    if when:
        params["datetime"] = when.strftime("%Y-%m-%d %H:%M")
    d = _get("/stationboard", params)
    out = []
    for b in d.get("stationboard") or []:
        st = b.get("stop") or {}
        dep, delay = _real(st, "departure")
        out.append({"line": line_name(b), "to": str(b.get("to") or ""), "dep": dep, "delay": delay, "platform": st.get("platform") or "",
                    "planned": _ts(st, "departure")})
    return ((d.get("station") or {}).get("name") or stop), out


# ---------------- saying it ----------------
def hm(ts: float | None) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M") if ts else "?"


def mins(n: int) -> str:
    if n < 60:
        return f"{n} min"
    return f"{n // 60} h {n % 60:02d}" if n % 60 else f"{n // 60} h"


def delay_text(n: int) -> str:
    return "on time" if n <= 0 else f"{n} min late"


def describe(c: dict, now: float | None = None) -> str:
    now = time.time() if now is None else now
    first = c["legs"][0] if c["legs"] else {"line": "train", "to": "", "platform": ""}
    head = f"{first['line']}" + (f" towards {first['to']}" if first.get("to") else "")
    plat = f", platform {c['platform']}" if c.get("platform") and "bus" not in first["line"] and "tram" not in first["line"] else ""
    when = hm(c["dep"])
    left = round((c["dep"] - now) / 60) if c.get("dep") else None
    soon = f" (in {mins(left)})" if left is not None and 0 <= left <= 90 else ""
    late = f", {c['delay']} min late" if c.get("delay", 0) > 0 else ""
    changes = "direct" if not c["transfers"] else f"{c['transfers']} change{'s' if c['transfers'] != 1 else ''}"
    if c.get("cancelled"):
        return f"{when}: {head} — cancelled"
    return f"{when}{soon}: {head}{plat}{late}, arrives {hm(c['arr'])} ({changes})"


class Transport:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock = threading.RLock()

    def load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data = data if isinstance(data, dict) else {}
        data["settings"] = {**DEFAULTS, **(data.get("settings") if isinstance(data.get("settings"), dict) else {})}
        if not isinstance(data.get("trip"), dict):
            data["trip"] = {}
        return data

    def save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def settings(self) -> dict:
        return self.load()["settings"]

    def set_settings(self, values: dict, lookup=None) -> dict:
        with self.lock:
            data = self.load()
            cfg = data["settings"]
            for k in ("home", "school"):
                if k in values:
                    v = re.sub(r"\s+", " ", str(values[k] or "")).strip()[:80]
                    if v and lookup:
                        found = lookup(v)
                        if not found:
                            raise ValueError(f"I found no stop called “{v}”.")
                        v = found["name"]
                    cfg[k] = v
            for k, lo, hi in (("walk_home", 0, 60), ("walk_school", 0, 60), ("margin", 0, 60), ("notice", 0, 120)):
                if k in values:
                    try:
                        n = int(values[k])
                    except (TypeError, ValueError):
                        raise ValueError("Use whole minutes.")
                    if not lo <= n <= hi:
                        raise ValueError(f"Choose between {lo} and {hi} minutes.")
                    cfg[k] = n
            for k in ("morning", "call"):
                if k in values:
                    cfg[k] = bool(values[k])
            data["trip"] = {}                                  # the morning plan is worked out again
            self.save(data)
            return cfg


# ---------------- the trip to school ----------------
def school_target(now: datetime, cfg: dict, ctx: dict) -> tuple[datetime, dict] | None:
    """When you must be at the school stop today: the first lesson minus the walk and the margin."""
    lessons = ctx["lessons"](now.date()) if ctx.get("lessons") else []
    if not lessons:
        return None
    first = min(lessons, key=lambda l: l["start"])
    h, m = (int(x) for x in first["start"].split(":"))
    start = datetime.combine(now.date(), datetime.min.time()).replace(hour=h, minute=m)
    return start - timedelta(minutes=cfg["walk_school"] + cfg["margin"]), {**first, "at": start}


def pick(conns: list[dict], deadline: float) -> dict | None:
    """The latest connection that still arrives in time (not cancelled)."""
    ok = [c for c in conns if not c.get("cancelled") and c.get("arr") and c["arr"] <= deadline and c.get("dep")]
    return max(ok, key=lambda c: c["dep"]) if ok else None


def plan_trip(cfg: dict, now: datetime, ctx: dict, fetch=None) -> dict | None:
    fetch = fetch or connections
    target = school_target(now, cfg, ctx)
    if not target:
        return None
    by, lesson = target
    conns = fetch(cfg["home"], cfg["school"], by, True, 5)
    c = pick(conns, by.timestamp())
    if not c:
        return {"date": now.date().isoformat(), "by": by.timestamp(), "lesson": lesson["subject"], "lesson_at": lesson["at"].timestamp(), "conn": None, "leave": None}
    return {"date": now.date().isoformat(), "by": by.timestamp(), "lesson": lesson["subject"], "lesson_at": lesson["at"].timestamp(), "conn": c,
            "leave": c["dep"] - cfg["walk_home"] * 60, "told": False, "checks": []}


def trip_text(trip: dict, cfg: dict, now: float, lead: str = "") -> str:
    c = trip["conn"]
    left = round((trip["leave"] - now) / 60)
    when = f"in {mins(left)}, at {hm(trip['leave'])}" if left > 0 else f"now ({hm(trip['leave'])})"
    late = f" ({delay_text(c['delay'])})" if c.get("delay", 0) > 0 else ", on time"
    return (lead + f"Leave {when}, sir: the {c['legs'][0]['line'] if c['legs'] else 'train'} from {c['from']} at {hm(c['dep'])}{late}, "
            f"at {c['to']} at {hm(c['arr'])}. First lesson: {trip['lesson']} at {hm(trip['lesson_at'])}.")


def tick(store: Transport, now: datetime, ctx: dict, fetch=None) -> list[dict]:
    """[{text, urgent}] for the morning trip. Looks things up at most a few times each morning."""
    with store.lock:
        data = store.load()
        cfg, trip = data["settings"], data["trip"]
        if not (cfg["morning"] and cfg["home"] and cfg["school"]):
            return []
        today = now.date().isoformat()
        out = []
        target = school_target(now, cfg, ctx)
        if not target or now > target[1]["at"]:
            return []
        if trip.get("date") != today:
            if now < target[0] - timedelta(hours=3):               # worked out three hours before you have to be there
                return []
            try:
                trip = plan_trip(cfg, now, ctx, fetch) or {}
            except TransportError:
                return []
            data["trip"] = trip
            store.save(data)
            if trip and not trip.get("conn"):
                out.append({"text": f"I found no connection from {cfg['home']} that gets you to {cfg['school']} by {hm(trip['by'])} for {trip['lesson']}, sir. "
                                    "Check the timetable, or leave as early as you can.", "urgent": False})
            return out
        if not trip.get("conn"):
            return []
        ts = now.timestamp()
        # look again before leaving: delays, cancellations
        for m in RECHECK:
            if trip["leave"] - m * 60 <= ts < trip["leave"] and m not in trip["checks"]:
                trip["checks"].append(m)
                try:
                    fresh = plan_trip(cfg, now, ctx, fetch)
                except TransportError:
                    break
                if fresh and fresh.get("conn"):
                    old = trip
                    moved = (fresh["leave"] - old["leave"]) / 60
                    fresh.update(told=old.get("told"), checks=old["checks"])
                    if moved <= -2:
                        why = f"the {hm(old['conn']['dep_planned'])} is cancelled or too late now"
                        out.append({"text": trip_text(fresh, cfg, ts, f"Change of plan: {why}. "), "urgent": True})
                        fresh["told"] = True
                    elif moved >= 2 and old.get("told"):
                        out.append({"text": trip_text(fresh, cfg, ts, f"Your {fresh['conn']['legs'][0]['line'] if fresh['conn']['legs'] else 'train'} is late, so you have a little longer. "), "urgent": False})
                    elif fresh["conn"].get("delay", 0) > old["conn"].get("delay", 0) and old.get("told"):
                        out.append({"text": f"Heads up, sir: the {hm(fresh['conn']['dep_planned'])} is now {fresh['conn']['delay']} min late, but you still make it.", "urgent": False})
                    trip = fresh
                elif fresh and not fresh.get("conn"):
                    out.append({"text": f"Careful, sir: no connection gets you to {cfg['school']} on time any more. Leave as soon as you can; "
                                        f"your first lesson, {trip['lesson']}, is at {hm(trip['lesson_at'])}.", "urgent": True})
                    trip = {**trip, "conn": None}
                break
        # time to get ready
        if trip.get("conn") and not trip.get("told") and trip["leave"] - cfg["notice"] * 60 <= ts <= trip["leave"] + 120:
            trip["told"] = True
            out.append({"text": trip_text(trip, cfg, ts), "urgent": False})
        data["trip"] = trip
        store.save(data)
        return out


def brief_line(store: Transport, now: datetime) -> str:
    trip = store.load()["trip"]
    if trip.get("date") != now.date().isoformat() or not trip.get("conn") or trip["leave"] < now.timestamp():
        return ""
    c = trip["conn"]
    return f"To be on time for {trip['lesson']}, leave at {hm(trip['leave'])} for the {hm(c['dep'])} {c['legs'][0]['line'] if c['legs'] else 'train'} from {c['from']}."


# ---------------- in the chat ----------------
CLEAN = re.compile(r"^(?:(?:hey\s+)?jarvis[,.:]?\s+)?(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?)?(?:(?:tell|show)\s+me\s+)?", re.I)
VEHICLE = r"(?:trains?|bus(?:es)?|trams?|metros?|boats?|connections?|transport|ride|way)"
NEXT_TO = re.compile(rf"(?:when(?:'s|\s+is|\s+does|\s+do)\s+(?:the\s+|my\s+)?next|what(?:'s|\s+is)\s+the\s+next|the\s+next|next|(?:the\s+)?(?:next\s+)?{VEHICLE}\s+(?:times?\s+)?)?\s*"
                     rf"(?:{VEHICLE})?\s*(?:times?\s+)?(?:from\s+(?P<frm>.+?)\s+)?(?:to|for|towards|into)\s+(?P<to>.+?)"
                     rf"(?:\s+from\s+(?P<frm2>.+?))?(?:\s+(?P<mode>at|around|after|by|before|leaving\s+at|arriving\s+(?:by|at|before))\s+(?P<when>.+?))?"
                     rf"(?:\s+(?:leave|go|depart|come|run))?", re.I)
HOW_TO = re.compile(r"how\s+(?:do|can|should)\s+i\s+get\s+(?:from\s+(?P<frm>.+?)\s+)?to\s+(?P<to>.+?)(?:\s+from\s+(?P<frm2>.+?))?"
                    r"(?:\s+(?P<mode>at|around|after|by|before)\s+(?P<when>.+?))?(?:\s+by\s+(?:train|bus|public\s+transport))?", re.I)
DEPS = re.compile(r"(?:next\s+|upcoming\s+)?departures(?:\s+(?:from|at)\s+(?P<s>.+?))?|what\s+(?:leaves|departs|goes)\s+(?:from\s+)?(?P<s2>.+?)(?:\s+(?:next|now|soon))?|"
                  r"(?:the\s+)?(?:station\s*board|departure\s+board)(?:\s+(?:for|at|of)\s+(?P<s3>.+?))?", re.I)
SCHOOL = re.compile(r"when\s+(?:should|do|must)\s+i\s+(?:leave|go|set\s+off)(?:\s+(?:for|to)\s+school)?(?:\s+(?:today|tomorrow|this\s+morning))?|"
                    r"(?:is|are)\s+my\s+(?:bus|train|tram|connection)\s+(?:late|delayed|on\s+time)|how(?:'s|\s+is)\s+my\s+(?:trip|journey|way)\s+to\s+school|"
                    r"my\s+(?:trip|journey|way)\s+to\s+school|(?:will|do)\s+i\s+make\s+it\s+(?:to\s+school\s+)?on\s+time", re.I)


def _place(text: str, cfg: dict) -> str:
    t = (text or "").strip(" ?.!,")
    t = re.sub(r"^(?:the\s+)?(?:station\s+of\s+|stop\s+)?", "", t, flags=re.I)
    if re.fullmatch(r"(?:home|my\s+home|my\s+place|the\s+house|my\s+house)", t, re.I):
        return cfg["home"]
    if re.fullmatch(r"(?:school|my\s+school|college|the\s+school)", t, re.I):
        return cfg["school"]
    return re.sub(r"\s+(?:station|stop|please|now|today)$", "", t, flags=re.I).strip()


def _when(text: str, now: datetime, parse_when) -> datetime | None:
    if not text or not parse_when:
        return None
    t = re.sub(r"^(?:at|around|after)\s+", "", text.strip(), flags=re.I)
    if not re.search(r"\d|noon|midnight|morning|evening|afternoon|tonight|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday", t, re.I):
        return None
    p = parse_when(t if re.search(r"\b(?:at|on|tomorrow|today|tonight|\w+day)\b", t, re.I) else "at " + t, now)
    if not isinstance(p, dict) or (p.get("date") is None and p.get("time") is None):
        return None
    d = p.get("date") or now.date()
    h, m = p.get("time") or (8, 0)
    return datetime.combine(d, datetime.min.time()).replace(hour=h, minute=m)


def command(text: str, store: Transport, now: datetime | None = None, ctx: dict | None = None, fetch=None, board=None) -> str | None:
    now, ctx = now or datetime.now(), ctx or {}
    fetch, board = fetch or connections, board or departures
    t = CLEAN.sub("", re.sub(r"\s+", " ", (text or "").strip())).strip().rstrip(" ?.!")
    if not t or len(t) > 160:
        return None
    cfg = store.settings()
    try:
        if SCHOOL.fullmatch(t):
            if not (cfg["home"] and cfg["school"]):
                return "Tell me your home stop and your school stop first, sir: Settings > Planner > Public transport."
            day = now
            if re.search(r"tomorrow", t, re.I) or not school_target(now, cfg, ctx) or now > school_target(now, cfg, ctx)[1]["at"]:
                day = datetime.combine(now.date() + timedelta(days=1), datetime.min.time()).replace(hour=6)
                if not school_target(day, cfg, ctx):
                    return "You have no lessons today or tomorrow, sir."
            trip = plan_trip(cfg, day, ctx, fetch)
            if not trip:
                return "You have no lessons that day, sir."
            if not trip.get("conn"):
                return f"No connection gets you from {cfg['home']} to {cfg['school']} by {hm(trip['by'])}, sir."
            if day.date() != now.date():
                c = trip["conn"]
                return (f"Tomorrow, leave at {hm(trip['leave'])}, sir: the {c['legs'][0]['line'] if c['legs'] else 'train'} from {c['from']} at {hm(c['dep'])}, "
                        f"at {c['to']} at {hm(c['arr'])}, for {trip['lesson']} at {hm(trip['lesson_at'])}.")
            return trip_text(trip, cfg, now.timestamp())
        m = DEPS.fullmatch(t)
        if m and not re.search(r"\bto\b", t, re.I):
            where = _place(m.group("s") or m.group("s2") or m.group("s3") or "", cfg) or cfg["home"]
            if not where:
                return "From which stop, sir? For example “departures from Bern”, or set your home stop in Settings > Planner > Public transport."
            name, rows = board(where, 8)
            rows = [r for r in rows if r.get("dep") and r["dep"] >= now.timestamp() - 60]
            if not rows:
                return f"Nothing leaves {name} soon, sir."
            return f"Next departures from {name}, sir:\n" + "\n".join(
                f"• {hm(r['dep'])}{' (' + delay_text(r['delay']) + ')' if r['delay'] > 0 else ''}: {r['line']} to {r['to']}" + (f", platform {r['platform']}" if r['platform'] else "")
                for r in rows[:8])
        m = HOW_TO.fullmatch(t) or NEXT_TO.fullmatch(t)
        if m and (m.re is HOW_TO or re.search(rf"\b(?:{VEHICLE}|next|connections?)\b", t, re.I)):
            to = _place(m.group("to"), cfg)
            frm = _place(m.group("frm") or m.group("frm2") or "", cfg) or cfg["home"]
            if not to or re.search(r"\b(?:my\s+(?:next|first)\s+(?:class|lesson)|sleep|bed|work\s+on)\b", to, re.I):
                return None
            if not re.search(rf"\b(?:{VEHICLE})\b", t, re.I) and to not in (cfg["home"], cfg["school"]):
                if not (ctx.get("lookup") or station)(to):        # “how do I get to level 3?” is not about a bus
                    return None
            if not frm:
                return f"From where, sir? Say “next train from Bern to {to}”, or set your home stop in Settings > Planner > Public transport."
            mode = (m.group("mode") or "").lower()
            when = _when(m.group("when") or "", now, ctx.get("parse_when"))
            if m.group("when") and when is None:
                return None
            arrive = bool(mode) and ("by" in mode or "before" in mode or "arriv" in mode)
            conns = [c for c in fetch(frm, to, when or now, arrive, 4) if c.get("dep")]
            if not arrive:
                conns = [c for c in conns if c["dep"] >= (when or now).timestamp() - 60]
            if not conns:
                return f"I found no connection from {frm} to {to}, sir."
            if arrive and when:
                conns = [c for c in conns if c.get("arr") and c["arr"] <= when.timestamp()] or conns
                conns = sorted(conns, key=lambda c: -c["dep"])[:3][::-1]
            a, b = conns[0]["from"] or frm, conns[0]["to"] or to
            head = f"From {a} to {b}" + (f", to arrive by {when.strftime('%H:%M')}" if arrive and when else f", from {when.strftime('%H:%M')}" if when else "") + ", sir:"
            return head + "\n" + "\n".join("• " + describe(c, now.timestamp()) for c in conns[:4])
    except TransportError as exc:
        return str(exc)
    return None

"""Calendar import: read an .ics file or an iCal link (school timetable, Google Calendar, Outlook ...) into the Jarvis planner.

Only the next few weeks are imported; the link is read again every few hours so changes show up. Jarvis never changes the calendar it reads from.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

try:
    from zoneinfo import ZoneInfo
except Exception:                      # very old Python
    ZoneInfo = None

WINDOW_DAYS, PAST_HOURS, MAX_SOURCES, MAX_ICS_BYTES, REFRESH_SECONDS = 21, 12, 5, 4_000_000, 4 * 3600
DAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


def unfold(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        elif raw.strip():
            lines.append(raw)
    return lines


def unescape(value: str) -> str:
    return re.sub(r"\\([nN,;\\])", lambda m: "\n" if m.group(1) in "nN" else m.group(1), value).strip()


def split_prop(line: str):
    """'DTSTART;TZID=Europe/Zurich:20261116T080000' -> ('DTSTART', {'TZID': 'Europe/Zurich'}, '20261116T080000')"""
    in_quote, cut = False, -1
    for i, ch in enumerate(line):
        if ch == '"':
            in_quote = not in_quote
        elif ch == ":" and not in_quote:
            cut = i
            break
    if cut < 0:
        return None
    head, value = line[:cut], line[cut + 1:]
    parts = head.split(";")
    params = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k.upper()] = v.strip('"')
    return parts[0].upper(), params, value


def parse_time(value: str, params: dict):
    """-> (datetime, all_day). Aware for UTC / TZID values, naive (local wall time) otherwise."""
    value = value.strip()
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
        return datetime.strptime(value[:8], "%Y%m%d"), True
    m = re.fullmatch(r"(\d{8})T(\d{6})(Z?)", value)
    if not m:
        raise ValueError("bad date " + value)
    dt = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    if m.group(3):
        return dt.replace(tzinfo=timezone.utc), False
    tzid = params.get("TZID")
    if tzid and ZoneInfo:
        try:
            return dt.replace(tzinfo=ZoneInfo(tzid)), False
        except Exception:
            pass
    return dt, False


def stamp(dt: datetime) -> float:
    return dt.timestamp()          # naive = local time, aware = exact instant


def parse_events(text: str) -> list[dict]:
    """Every VEVENT as {uid, summary, location, start (datetime), all_day, rrule, exdates, recurrence_id, cancelled}."""
    events, cur = [], None
    for line in unfold(text):
        up = line.upper()
        if up == "BEGIN:VEVENT":
            cur = {"exdates": [], "rrule": None, "recurrence_id": None, "cancelled": False, "summary": "", "location": "", "uid": "", "start": None, "all_day": False}
            continue
        if up == "END:VEVENT":
            if cur and cur["start"] is not None:
                events.append(cur)
            cur = None
            continue
        if cur is None:
            continue
        prop = split_prop(line)
        if not prop:
            continue
        name, params, value = prop
        try:
            if name == "DTSTART":
                cur["start"], cur["all_day"] = parse_time(value, params)
            elif name == "SUMMARY":
                cur["summary"] = unescape(value)
            elif name == "LOCATION":
                cur["location"] = unescape(value)
            elif name == "UID":
                cur["uid"] = value.strip()
            elif name == "STATUS":
                cur["cancelled"] = value.strip().upper() == "CANCELLED"
            elif name == "RRULE":
                cur["rrule"] = dict(p.split("=", 1) for p in value.split(";") if "=" in p)
            elif name == "EXDATE":
                for v in value.split(","):
                    cur["exdates"].append(parse_time(v, params)[0])
            elif name == "RECURRENCE-ID":
                cur["recurrence_id"] = parse_time(value, params)[0]
        except ValueError:
            continue
    return events


def occurrences(ev: dict, lo: float, hi: float) -> list[datetime]:
    """Start times of one event between the two timestamps (recurrence rules expanded, simple ones only)."""
    start, rule = ev["start"], ev["rrule"]
    if not rule:
        return [start] if lo <= stamp(start) <= hi else []
    freq = rule.get("FREQ", "").upper()
    interval = max(1, int(rule.get("INTERVAL", "1") or 1))
    count = int(rule["COUNT"]) if rule.get("COUNT", "").isdigit() else None
    until = None
    if rule.get("UNTIL"):
        try:
            u, _ = parse_time(rule["UNTIL"], {})
            until = stamp(u) if u.tzinfo else stamp(u) + (86399 if len(rule["UNTIL"]) == 8 else 0)
        except ValueError:
            pass
    byday = [d[-2:].upper() for d in rule.get("BYDAY", "").split(",") if d[-2:].upper() in DAYS]
    out, made, step = [], 0, 0
    tz, t = start.tzinfo, start.time()
    d0 = start.date()

    def make(day: date):
        dt = datetime.combine(day, t)
        return dt.replace(tzinfo=tz) if tz else dt

    def candidates(n: int):
        if freq == "DAILY":
            yield make(d0 + timedelta(days=n * interval))
        elif freq == "WEEKLY":
            monday = d0 - timedelta(days=d0.weekday()) + timedelta(weeks=n * interval)
            for wd in (sorted(DAYS.index(x) for x in byday) if byday else [d0.weekday()]):
                yield make(monday + timedelta(days=wd))
        elif freq == "MONTHLY":
            month = d0.month - 1 + n * interval
            try:
                yield make(date(d0.year + month // 12, month % 12 + 1, d0.day))
            except ValueError:
                return
        elif freq == "YEARLY":
            try:
                yield make(date(d0.year + n * interval, d0.month, d0.day))
            except ValueError:
                return

    if freq not in ("DAILY", "WEEKLY", "MONTHLY", "YEARLY"):
        return [start] if lo <= stamp(start) <= hi else []
    for n in range(0, 4000):
        batch = [c for c in candidates(n) if stamp(c) >= stamp(start)]
        if not batch and n > 0 and freq in ("MONTHLY", "YEARLY") and False:
            break
        for dt in batch:
            if count is not None and made >= count:
                return out
            if until is not None and stamp(dt) > until:
                return out
            made += 1
            if stamp(dt) > hi:
                return out
            if stamp(dt) >= lo:
                out.append(dt)
        if count is None and until is None and batch and stamp(batch[0]) > hi:
            return out
    return out


def expand(text: str, now: float | None = None) -> list[dict]:
    """The events in the import window: [{uid, title, start (timestamp), all_day}] sorted by time."""
    now = time.time() if now is None else now
    lo, hi = now - PAST_HOURS * 3600, now + WINDOW_DAYS * 86400
    events = parse_events(text)
    overridden = {(e["uid"], stamp(e["recurrence_id"])) for e in events if e["recurrence_id"] is not None}
    out = []
    for ev in events:
        if ev["cancelled"]:
            continue
        title = ev["summary"] or "Event"
        if ev["location"]:
            title += " (" + ev["location"].split("\n")[0][:40] + ")"
        if ev["all_day"]:
            title += " (all day)"
        skip = {stamp(x) for x in ev["exdates"]}
        starts = [ev["start"]] if ev["recurrence_id"] is not None else occurrences(ev, lo - 86400 if ev["all_day"] else lo, hi)
        for dt in starts:
            ts = stamp(dt)
            if ev["recurrence_id"] is None and (ts in skip or (ev["uid"], ts) in overridden):
                continue
            if ev["all_day"]:
                ts += 8 * 3600
            if lo <= ts <= hi:
                out.append({"uid": ev["uid"] or title, "title": title[:200], "start": ts, "all_day": ev["all_day"]})
    out.sort(key=lambda e: e["start"])
    return out[:600]


def event_id(source_id: str, uid: str, start: float) -> str:
    return hashlib.sha1(f"{source_id}|{uid}|{int(start)}".encode()).hexdigest()[:8]


# ---------------- sources (data/calendar.json) ----------------
class Calendars:
    def __init__(self, path: Path, planner):
        self.path, self.planner = path, planner
        self.lock = threading.RLock()

    def load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data = data if isinstance(data, dict) else {}
        if not isinstance(data.get("sources"), list):
            data["sources"] = []
        data["alerts"] = bool(data.get("alerts", False))
        return data

    def save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def public(self) -> dict:
        data = self.load()
        return {"alerts": data["alerts"], "max": MAX_SOURCES, "sources": [
            {"id": s["id"], "name": s["name"], "kind": "link" if s.get("url") else "file", "synced": s.get("synced"), "count": s.get("count", 0), "error": s.get("error", "")}
            for s in data["sources"]]}

    def fetch(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("The link must start with https:// (or webcal://).")
        req = urllib.request.Request(url, headers={"User-Agent": "Jarvis-calendar-import"})
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read(MAX_ICS_BYTES + 1)
        if len(raw) > MAX_ICS_BYTES:
            raise ValueError("That calendar file is too big.")
        return raw.decode("utf-8", errors="replace")

    def add(self, name: str = "", url: str = "", ics: str = "") -> dict:
        url, ics = (url or "").strip(), (ics or "")
        if url.lower().startswith("webcal://"):
            url = "https://" + url[9:]
        if not url and not ics.strip():
            raise ValueError("Paste a calendar link or choose an .ics file.")
        if len(ics) > MAX_ICS_BYTES:
            raise ValueError("That calendar file is too big.")
        with self.lock:
            data = self.load()
            if len(data["sources"]) >= MAX_SOURCES:
                raise ValueError(f"You can import up to {MAX_SOURCES} calendars. Remove one first.")
            text = ics
            if url:
                try:
                    text = self.fetch(url)
                except ValueError:
                    raise
                except Exception as exc:
                    raise ValueError("I could not read that link: " + str(exc)[:120])
            if "BEGIN:VCALENDAR" not in text.upper():
                raise ValueError("That does not look like a calendar (.ics) file.")
            src = {"id": secrets.token_hex(3), "name": (name or "").strip()[:60] or (urlparse(url).hostname if url else "Calendar file"), "url": url, "ics": "" if url else text, "synced": None, "count": 0, "error": ""}
            data["sources"].append(src)
            self.save(data)
        self.sync_source(src["id"], text)
        return self.public()

    def remove(self, source_id: str) -> bool:
        with self.lock:
            data = self.load()
            keep = [s for s in data["sources"] if s["id"] != source_id]
            if len(keep) == len(data["sources"]):
                return False
            data["sources"] = keep
            self.save(data)
        self.planner.sync_external(source_id, [], quiet=True)
        return True

    def set_alerts(self, on: bool) -> None:
        with self.lock:
            data = self.load()
            data["alerts"] = bool(on)
            self.save(data)

    def sync_source(self, source_id: str, text: str | None = None, now: float | None = None) -> int:
        with self.lock:
            data = self.load()
            src = next((s for s in data["sources"] if s["id"] == source_id), None)
            if not src:
                return 0
            try:
                if text is None:
                    text = self.fetch(src["url"]) if src.get("url") else src.get("ics", "")
                items = expand(text, now)
                self.planner.sync_external(source_id, [{"id": event_id(source_id, i["uid"], i["start"]), "title": i["title"], "start": i["start"], "all_day": i["all_day"]} for i in items], quiet=not data["alerts"])
                src["count"], src["error"] = len(items), ""
            except Exception as exc:
                src["error"] = str(exc)[:160] or "Could not read the calendar."
            src["synced"] = time.time() if now is None else now
            self.save(data)
            return src["count"]

    def sync_all(self, force: bool = False, now: float | None = None) -> None:
        now = time.time() if now is None else now
        for s in self.load()["sources"]:
            if force or not s.get("synced") or now - s["synced"] >= REFRESH_SECONDS:
                self.sync_source(s["id"], now=now)

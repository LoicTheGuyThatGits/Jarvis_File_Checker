"""Evening recap: a short look back at the day and ahead at tomorrow, built only from what Jarvis already holds
(planner tasks and events, notes). No network or model calls, so it is quick and private.

  text(planner_data, notes, now)  ->  the recap
  due(config, now)                ->  True once a day, after the chosen time, when switched on
  command(text)                   ->  True when the person asked for it in chat
"""
from __future__ import annotations

import json
import re
from datetime import datetime, time as dtime, timedelta
from pathlib import Path

DEFAULTS = {"enabled": False, "time": "20:30", "last": ""}
ASK = re.compile(
    r"^(?:please\s+)?(?:(?:give|show|read|get)\s+me\s+)?(?:an?\s+|my\s+|the\s+)?"
    r"(?:evening|end[- ]of[- ]day|daily|day)\s+(?:recap|summary|review|wrap[- ]?up)"
    r"|^(?:please\s+)?(?:recap|summari[sz]e|review|wrap\s+up)\s+(?:my|the)\s+day"
    r"|^how\s+was\s+my\s+day|^what\s+did\s+i\s+(?:get\s+done|achieve|finish|do)\s+today", re.I)


def load_config(path: Path) -> dict:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    cfg = dict(DEFAULTS)
    if isinstance(raw, dict):
        cfg["enabled"] = bool(raw.get("enabled", False))
        cfg["last"] = str(raw.get("last", ""))[:10]
        if _clock(raw.get("time")) is not None:
            cfg["time"] = str(raw["time"]).strip()
    return cfg


def save_config(path: Path, update: dict) -> dict:
    cfg = load_config(path)
    if "enabled" in update:
        cfg["enabled"] = bool(update["enabled"])
    if "time" in update:
        if _clock(update["time"]) is None:
            raise ValueError("Use a time like 20:30.")
        cfg["time"] = f"{_clock(update['time']) // 60:02d}:{_clock(update['time']) % 60:02d}"
    if "last" in update:
        cfg["last"] = str(update["last"])[:10]
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    tmp.replace(p)
    return cfg


def _clock(value) -> int | None:
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(value or ""))
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def due(cfg: dict, now: datetime) -> bool:
    """True when it is switched on, the time has come and today's has not been given yet."""
    if not cfg.get("enabled") or cfg.get("last") == now.date().isoformat():
        return False
    at = _clock(cfg.get("time"))
    return at is not None and now.hour * 60 + now.minute >= at


def command(text: str) -> bool:
    t = re.sub(r"^(?:(?:hey\s+)?jarvis[,.:]?\s+)", "", (text or "").strip(), flags=re.I).rstrip(".!? ")
    return bool(t) and len(t) < 70 and bool(ASK.search(t))


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def text(planner: dict, notes: list[dict], now: datetime) -> str:
    start = datetime.combine(now.date(), dtime.min)
    day0, day1, day2 = start.timestamp(), (start + timedelta(days=1)).timestamp(), (start + timedelta(days=2)).timestamp()
    tasks, events = planner.get("tasks", []), planner.get("events", [])
    done = [t for t in tasks if t.get("done") and day0 <= (t.get("done_at") or 0) < day1]
    held = sorted([e for e in events if day0 <= e["start"] <= now.timestamp()], key=lambda e: e["start"])
    open_tasks = [t for t in tasks if not t.get("done")]
    late = [t for t in open_tasks if t.get("due") and t["due"] < day0]
    tomorrow = sorted([e for e in events if day1 <= e["start"] < day2], key=lambda e: e["start"])
    due_tomorrow = [t for t in open_tasks if t.get("due") and day1 <= t["due"] < day2]
    today_notes = [n for n in notes if day0 <= n.get("created", 0) < day1]
    lines = [f"Here is your day, {now.strftime('%A')}:"]
    if done:
        lines.append(f"• Done today: {_plural(len(done), 'task')} — " + "; ".join(t["text"] for t in done[:5]) + ("…" if len(done) > 5 else "") + ".")
    else:
        lines.append("• No tasks ticked off today.")
    if held:
        lines.append("• Happened today: " + "; ".join(f"{e['title']} ({datetime.fromtimestamp(e['start']).strftime('%H:%M')})" for e in held[:5]) + ".")
    if today_notes:
        lines.append(f"• You saved {_plural(len(today_notes), 'note')} today.")
    left_today = [t for t in open_tasks if t.get("due") and day0 <= t["due"] < day1]
    if left_today:
        lines.append("• Still open from today: " + "; ".join(t["text"] for t in left_today[:5]) + ".")
    if late:
        lines.append(f"• Overdue: {_plural(len(late), 'task')} — " + "; ".join(t["text"] for t in late[:4]) + ("…" if len(late) > 4 else "") + ".")
    lines.append("")
    if tomorrow:
        first = datetime.fromtimestamp(tomorrow[0]["start"]).strftime("%H:%M")
        lines.append(f"Tomorrow: {_plural(len(tomorrow), 'event')}, the first is {tomorrow[0]['title']} at {first}.")
    else:
        lines.append("Tomorrow: nothing in the calendar yet.")
    if due_tomorrow:
        lines.append(f"{_plural(len(due_tomorrow), 'task')} due tomorrow: " + "; ".join(t["text"] for t in due_tomorrow[:4]) + ".")
    if len(open_tasks) and not due_tomorrow:
        lines.append(f"You have {_plural(len(open_tasks), 'open task')} in total.")
    return "\n".join(lines)

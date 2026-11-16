"""Search across everything Jarvis holds for you: notes, to-do list, calendar, things you asked it to remember, and your documents.

    query_of(text)                   the search words when the message asks for such a search, else None
    search(query, planner_data, notes_search, memory_find, docs_search, now)  ->  {"notes": [...], "tasks": [...], ...}
    report(query, results, now)      the answer text
"""
from __future__ import annotations

import re
from datetime import datetime

STOP = set("a an the my me i to of on in at for and or with is are was were be do did it that this about from by as have has had where what when which who any some all".split())
CLEAN_START = r"^(?:(?:hey\s+)?jarvis[,.:]?\s+)?(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?)?"
EVERY = r"(?:everything|everywhere|anywhere|all\s+(?:of\s+)?my\s+(?:stuff|things|data|files)|my\s+(?:stuff|things)|all\s+of\s+it|the\s+lot)"
PATTERNS = [
    rf"(?:search|look|check|go)\s+(?:through\s+|in\s+|across\s+)?{EVERY}\s+for\s+(.+)",
    rf"(?:search|look)\s+{EVERY}\s*:\s*(.+)",
    rf"(?:search|look|find|check)\s+(?:for\s+)?(.+?)\s+(?:in|across|through)?\s*{EVERY}",
    r"where\s+(?:did|have)\s+i\s+(?:see|seen|put|write|written|save|saved|note|noted|mention|mentioned|store|stored|keep|kept|read)\s+(?:down\s+)?(?:something\s+about\s+|anything\s+about\s+|that\s+thing\s+about\s+)?(.+)",
    r"(?:do|did)\s+i\s+have\s+(?:anything|something|any\s+info(?:rmation)?)\s+(?:about|on|regarding|for|mentioning)\s+(.+)",
    r"(?:what|anything)\s+do\s+i\s+have\s+(?:about|on|regarding)\s+(.+)",
    r"find\s+(?:everything|anything|all)\s+(?:about|on|regarding|mentioning|related\s+to)\s+(.+)",
]


def words(text: str) -> list[str]:
    return [w for w in re.findall(r"[^\W_]+", (text or "").lower()) if w not in STOP and len(w) > 1]


def query_of(text: str) -> str | None:
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = re.sub(CLEAN_START, "", t, flags=re.I)
    t = re.sub(r"\s*(?:please|for me|again)?\s*[.!?]*$", "", t, flags=re.I).strip()
    if not t or len(t) > 200:
        return None
    for pattern in PATTERNS:
        m = re.fullmatch(pattern, t, re.I)
        if m:
            q = re.sub(r"^(?:the|my|a|an|that|this)\s+", "", m.group(1).strip(" \"'“”"), flags=re.I)
            return q if words(q) else None
    return None


def matches(query: str, text: str) -> int:
    """How many of the query's words are in the text (a word also counts when one starts with the other, like 'exam'/'exams')."""
    have = words(text)
    return sum(1 for w in words(query) if any(w == h or (len(w) > 3 and len(h) > 3 and (h.startswith(w) or w.startswith(h))) for h in have))


def best(query: str, items: list, text_of, limit: int = 5) -> list:
    need = len(words(query))
    scored = [(matches(query, text_of(i)), n, i) for n, i in enumerate(items)]
    scored = [s for s in scored if s[0]]
    if not scored:
        return []
    top = max(s[0] for s in scored)
    return [i for hits, _, i in sorted(scored, key=lambda s: (-s[0], -s[1])) if hits == top or hits >= need][:limit]


def search(query: str, planner_data: dict, notes_search=None, memory_find=None, docs_search=None, now: datetime | None = None) -> dict:
    out = {"notes": [], "tasks": [], "events": [], "memory": [], "documents": []}
    if notes_search:
        out["notes"] = [n for n in notes_search(query) if matches(query, n.get("text", ""))][:5]
    out["tasks"] = best(query, planner_data.get("tasks", []), lambda t: t.get("text", ""))
    out["events"] = best(query, planner_data.get("events", []), lambda e: e.get("title", ""))
    if memory_find:
        try:
            out["memory"] = [m for m in memory_find(query) if matches(query, m.get("text", ""))][:5]
        except Exception:
            pass
    if docs_search:
        try:
            out["documents"] = [d for d in docs_search(query) if matches(query, d.get("text", "") + " " + d.get("name", ""))][:4]
        except Exception:
            pass
    return out


def _short(text: str, n: int = 160) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def report(query: str, results: dict, now: datetime | None = None) -> str:
    now = now or datetime.now()
    total = sum(len(v) for v in results.values())
    if not total:
        return f"I found nothing about “{query}” in your notes, to-do list, calendar, memory or documents, sir."
    places = sum(1 for v in results.values() if v)
    lines = [f"I found “{query}” in {places} place{'s' if places != 1 else ''}, sir:"]
    if results["notes"]:
        lines.append("Notes:")
        lines += [f"• {_short(n['text'])}" for n in results["notes"]]
    if results["tasks"]:
        lines.append("To-do list:")
        for t in results["tasks"]:
            due = f" (due {datetime.fromtimestamp(t['due']).strftime('%a %d %b')})" if t.get("due") else ""
            lines.append(f"• {_short(t['text'])}{due}{' — done' if t.get('done') else ''}")
    if results["events"]:
        lines.append("Calendar:")
        for e in results["events"]:
            when = datetime.fromtimestamp(e["start"])
            lines.append(f"• {_short(e['title'])} — {when.strftime('%a %d %b %Y, %H:%M')}{' (past)' if when < now else ''}")
    if results["memory"]:
        lines.append("Things you asked me to remember:")
        lines += [f"• {_short(m['text'])}" for m in results["memory"]]
    if results["documents"]:
        lines.append("Documents:")
        lines += [f"• {d.get('name', 'document')}: {_short(d.get('text', ''), 200)}" for d in results["documents"]]
    return "\n".join(lines)

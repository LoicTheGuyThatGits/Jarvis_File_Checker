"""Quick notes for Jarvis, stored in data/notes.json on this PC.

"note that the exam is in room 204" saves a note; "what did I note about the exam" finds it again.
Notes are for things to look up later. What Jarvis should always know about you ("remember that ...") is the separate memory.
"""
from __future__ import annotations

import json
import re
import secrets
import threading
import time
from datetime import datetime
from pathlib import Path

MAX_NOTES, MAX_LENGTH = 2000, 2000
STOP = {"the", "and", "for", "from", "that", "this", "with", "about", "was", "were", "are", "have", "has", "what", "did", "note", "notes", "noted", "my", "any", "all", "you", "your", "its", "into"}


def keywords(text: str) -> set[str]:
    return {w for w in re.findall(r"[^\W_]+", text.lower()) if len(w) > 2 and w not in STOP}


def when(ts: float, now: float | None = None) -> str:
    d, today = datetime.fromtimestamp(ts), datetime.fromtimestamp(now or time.time())
    days = (today.date() - d.date()).days
    if days == 0:
        return "today"
    if days == 1:
        return "yesterday"
    if 1 < days < 7:
        return d.strftime("%A")
    return d.strftime("%d %b") if d.year == today.year else d.strftime("%d %b %Y")


class Notes:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()

    def load(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        items = data.get("notes") if isinstance(data, dict) else None
        return [n for n in (items or []) if isinstance(n, dict) and isinstance(n.get("text"), str) and n.get("id")]

    def save(self, items: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"notes": items}, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def add(self, text: str) -> dict:
        text = re.sub(r"[ \t]+", " ", str(text)).strip()
        if not text:
            raise ValueError("The note needs some text.")
        if len(text) > MAX_LENGTH:
            raise ValueError(f"That note is too long (the limit is {MAX_LENGTH} characters).")
        text = text[0].upper() + text[1:]
        with self.lock:
            items = self.load()
            if len(items) >= MAX_NOTES:
                raise ValueError("That is too many notes. Delete some old ones first.")
            note = {"id": secrets.token_hex(4), "text": text, "created": time.time()}
            items.append(note)
            self.save(items)
            return note

    def delete(self, note_id: str) -> bool:
        with self.lock:
            items = self.load()
            keep = [n for n in items if n["id"] != note_id]
            if len(keep) == len(items):
                return False
            self.save(keep)
            return True

    def search(self, query: str, limit: int = 50) -> list[dict]:
        """Notes containing all the words of the query; when none do, the ones matching the most words. Newest first."""
        items = self.load()
        wanted = keywords(query)
        if not wanted:
            return list(reversed(items))[:limit]
        scored = []
        for note in items:
            have = keywords(note["text"]) | {w for w in re.findall(r"[^\W_]+", note["text"].lower())}
            hits = sum(1 for w in wanted if w in have or any(h.startswith(w) or w.startswith(h) for h in have if len(h) > 3 and len(w) > 3))
            if hits:
                scored.append((hits, note["created"], note))
        if not scored:
            return []
        best = max(s[0] for s in scored)
        return [n for h, _, n in sorted(scored, key=lambda s: (-s[0], -s[1])) if h == best or h >= len(wanted)][:limit]

    def public(self, query: str = "") -> dict:
        return {"notes": self.search(query) if query.strip() else list(reversed(self.load())), "total": len(self.load())}

    # ---- spoken commands ----
    def command(self, text: str) -> str | None:
        t = re.sub(r"\s+", " ", (text or "").strip())
        t = re.sub(r"^(?:(?:hey\s+)?jarvis[,.:]?\s+)?(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?)?", "", t, flags=re.I)
        t = re.sub(r"\s*(?:please|for me)?\s*[.!?]*$", "", t, flags=re.I).strip()
        if not t or len(t) > 2500:
            return None
        low = t.lower()
        # ---- delete ----
        if re.fullmatch(r"(?:delete|remove|erase|scrap)\s+(?:my\s+|the\s+)?(?:last|latest|previous)\s+note", low):
            items = self.load()
            if not items:
                return "You have no notes, sir."
            self.delete(items[-1]["id"])
            return f"Deleted your last note: “{items[-1]['text'][:80]}”, sir."
        m = re.fullmatch(r"(?:delete|remove|erase)\s+(?:my\s+|the\s+)?note\s+(?:about|on|regarding|that says|saying)\s+(.+)", t, re.I)
        if m:
            hits = self.search(m.group(1))
            if not hits:
                return f"I found no note about “{m.group(1).strip()}”, sir."
            if len(hits) > 1:
                return "Which one, sir? " + " | ".join(h["text"][:60] for h in hits[:4])
            self.delete(hits[0]["id"])
            return f"Deleted the note: “{hits[0]['text'][:80]}”, sir."
        # ---- find ----
        m = (re.fullmatch(r"what\s+(?:did|have)\s+i\s+(?:note|noted|write|wrote|written|jot|jotted|save|saved)(?:\s+down)?(?:\s+(?:about|on|regarding|for|concerning))?\s+(.+)", t, re.I)
             or re.fullmatch(r"(?:find|search|look\s+up|show|read|get|check|pull\s+up)(?:\s+(?:me|for))?\s+(?:my\s+|the\s+)?notes?\s+(?:about|on|for|regarding|containing|with|mentioning)\s+(.+)", t, re.I)
             or re.fullmatch(r"search\s+(?:my\s+)?notes?\s+for\s+(.+)", t, re.I)
             or re.fullmatch(r"what\s+(?:are|were)\s+my\s+notes\s+(?:about|on|for|regarding)\s+(.+)", t, re.I)
             or re.fullmatch(r"(?:do\s+i\s+have|did\s+i\s+(?:make|take|write))\s+(?:a\s+|any\s+)?notes?\s+(?:about|on|for|regarding)\s+(.+)", t, re.I))
        if m:
            return self.found(m.group(1))
        if re.fullmatch(r"(?:what\s+(?:was|is)|what's|read|show|tell\s+me)\s+(?:me\s+)?my\s+(?:last|latest|previous)\s+note", low):
            items = self.load()
            return "You have no notes, sir." if not items else f"Your last note ({when(items[-1]['created'])}): {items[-1]['text']}"
        if re.fullmatch(r"(?:show|list|read|open|see|what\s+are|what's\s+in|give\s+me|check)(?:\s+me)?\s+(?:my\s+|the\s+)?(?:recent\s+|latest\s+|last\s+)?notes|my\s+notes|what\s+notes\s+do\s+i\s+have", low):
            items = self.load()
            if not items:
                return "You have no notes yet, sir. Say “note that …” to save one."
            lines = [f"• {when(n['created'])}: {n['text'][:140]}" for n in reversed(items[-8:])]
            return f"Your latest notes ({len(items)} in all):\n" + "\n".join(lines)
        # ---- add ----
        m = (re.fullmatch(r"(?:take|make|add|save|write|jot|create)\s+(?:down\s+)?(?:a\s+|another\s+|new\s+)*(?:quick\s+|short\s+)?note\s*(?:that|:|-|,|saying|says|to\s+self)?\s*(.*)", t, re.I)
             or re.fullmatch(r"note(?:\s+down)?\s*(?:that|:|-|,)\s*(.+)", t, re.I)
             or re.fullmatch(r"(?:note\s+down|jot\s+down|jot|write\s+down|write\s+this\s+down)\s*:?\s+(.+)", t, re.I)
             or re.fullmatch(r"add\s+(.+?)\s+to\s+(?:my\s+)?notes", t, re.I))
        if m:
            body = m.group(1).strip(" :-,")
            if not body:
                return "What should the note say, sir? Say “note that …”."
            if re.match(r"(?:what|how|when|where|why|who|whether|if|do you|did you|me\s+(?:what|how|when|where|why|who))\b", body, re.I):
                return None
            try:
                self.add(body)
            except ValueError as exc:
                return str(exc)
            return f"Noted: “{body[:100]}{'…' if len(body) > 100 else ''}”, sir."
        return None

    def found(self, query: str) -> str:
        hits = self.search(query)
        if not hits:
            return f"I found no note about “{query.strip()}”, sir."
        lines = [f"• {when(n['created'])}: {n['text'][:200]}" for n in hits[:5]]
        more = f"\n…and {len(hits) - 5} more." if len(hits) > 5 else ""
        return (f"{len(hits)} note{'s' if len(hits) != 1 else ''} about “{query.strip()}”:\n" if len(hits) > 1 else "Found it:\n") + "\n".join(lines) + more

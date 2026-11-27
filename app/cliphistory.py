"""Clipboard history: the last texts you copied, so you can get an earlier one back ("paste what I copied before").

Kept in memory only: nothing is written to disk, it is gone when Jarvis stops, it is never sent to the phone or Telegram, and
it is never given to the AI model. Texts that look like secrets are not kept at all: passwords (one word mixing letters,
digits and signs), codes and PINs (4 to 8 digits), card and account numbers, keys and tokens, and anything a password manager
marks as private on the clipboard.

    CLIP = ClipHistory(read_text, sequence, is_private, path, write_text)   the clipboard calls come from the server (Windows)
    CLIP.start() / CLIP.stop()                            watch the clipboard in a thread (twice a second)
    CLIP.items()                                          newest first: [{"id", "text", "at", "cut"}]
    command(text) -> dict | None                          what a chat message asks of the history
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

LIMIT = 25
KEEP_CHARS = 4000

_KEY_PREFIX = re.compile(r"^(?:sk-|sk_live_|sk_test_|rk_live_|pk_live_|ghp_|gho_|ghs_|ghu_|github_pat_|glpat-|xox[abposr]-|AKIA|ASIA|AIza|ya29\.|npm_|hf_|shpat_|EAAC)", re.I)
_TELEGRAM_TOKEN = re.compile(r"^\d{6,12}:[\w-]{30,}$")
_JWT = re.compile(r"^eyJ[\w-]+\.[\w-]+\.[\w-]+$")
_IBAN = re.compile(r"^[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){10,30}$")
_DIGITS = re.compile(r"^[\d\s.-]+$")


def looks_secret(text: str) -> bool:
    """True for what must never be kept: passwords, codes, card numbers, keys and tokens."""
    t = (text or "").strip()
    if not t:
        return True
    if "-----BEGIN" in t and "PRIVATE KEY" in t:
        return True
    if re.search(r"(?i)\b(password|passwort|mot de passe|passwd|pwd)\s*[:=]\s*\S", t):
        return True
    one = re.sub(r"\s", "", t)
    if _DIGITS.match(t):
        digits = re.sub(r"\D", "", t)
        if 4 <= len(digits) <= 8 or 12 <= len(digits) <= 19:      # codes and PINs; card numbers
            return True
    if _IBAN.match(t.upper()) and t.upper() == t:
        return True
    if " " in t or "\n" in t:
        return False                                              # sentences, lists, addresses: kept
    if _KEY_PREFIX.match(t) or _TELEGRAM_TOKEN.match(t) or _JWT.match(t):
        return True
    if re.match(r"^[a-z][a-z0-9+.-]*://", t, re.I) or re.match(r"^[\w.+-]+@[\w-]+\.[\w.-]+$", t):
        return False                                              # web addresses and e-mail addresses: kept
    if re.match(r"^[A-Za-z]:\\", t) or t.startswith("/") or t.startswith("~"):
        return False                                              # file paths
    kinds = sum(bool(re.search(p, one)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^\w]"))
    if 8 <= len(one) <= 128 and kinds >= 3 and not re.fullmatch(r"[A-Za-z]+[.,!?]?", one):
        return True                                               # one word mixing letters, digits and signs: a password
    if len(one) >= 24 and re.fullmatch(r"[A-Za-z0-9+/=_-]+", one) and re.search(r"\d", one) and re.search(r"[A-Za-z]", one):
        return True                                               # a long key, hash or token
    return False


class ClipHistory:
    def __init__(self, read_text, sequence, is_private=lambda: False, config_path: Path | None = None, write_text=lambda text: False):
        self.read_text, self.sequence, self.is_private, self.write_text = read_text, sequence, is_private, write_text
        self.config_path = config_path
        self.entries: list[dict] = []
        self.lock = threading.Lock()
        self.last_seq = None
        self.next_id = 1
        self.skipped = 0
        self.stop_flag = threading.Event()
        self.thread: threading.Thread | None = None

    # ---- on or off (on unless switched off) ----
    @property
    def enabled(self) -> bool:
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8")).get("enabled") is not False
        except (OSError, ValueError, AttributeError):
            return True

    def set_enabled(self, on: bool) -> None:
        if self.config_path:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_path.write_text(json.dumps({"enabled": bool(on)}), encoding="utf-8")
        if not on:
            self.clear()

    # ---- the list ----
    def add(self, text) -> bool:
        if not isinstance(text, str):
            return False
        text = text.replace("\r\n", "\n").strip("\n")
        if not text.strip() or looks_secret(text):
            self.skipped += 1 if text.strip() else 0
            return False
        cut = len(text) > KEEP_CHARS
        text = text[:KEEP_CHARS]
        with self.lock:
            self.entries = [e for e in self.entries if e["text"] != text]   # copied again: it moves to the top
            self.entries.insert(0, {"id": self.next_id, "text": text, "at": time.time(), "cut": cut})
            self.next_id += 1
            del self.entries[LIMIT:]
        return True

    def items(self) -> list[dict]:
        with self.lock:
            return [dict(e) for e in self.entries]

    def get(self, item_id) -> dict | None:
        with self.lock:
            return next((dict(e) for e in self.entries if e["id"] == item_id), None)

    def remove(self, item_id) -> bool:
        with self.lock:
            before = len(self.entries)
            self.entries = [e for e in self.entries if e["id"] != item_id]
            return len(self.entries) != before

    def clear(self) -> None:
        with self.lock:
            self.entries = []

    def public(self) -> dict:
        return {"enabled": self.enabled, "watching": self.thread is not None and self.thread.is_alive(), "items": self.items(), "limit": LIMIT}

    # ---- watching ----
    def poll(self) -> None:
        if not self.enabled:
            return
        seq = self.sequence()
        if seq == self.last_seq:
            return
        first = self.last_seq is None
        self.last_seq = seq
        if self.is_private():
            return
        text = self.read_text()
        if first and not text:
            return
        self.add(text)

    def run(self) -> None:
        while not self.stop_flag.wait(0.5):
            try:
                self.poll()
            except Exception as exc:                                       # a busy clipboard: try again next time
                print(f"[jarvis] clipboard history: {type(exc).__name__}: {exc}")

    def start(self) -> None:
        if self.thread is None or not self.thread.is_alive():
            self.stop_flag.clear()
            self.thread = threading.Thread(target=self.run, name="jarvis-clipboard", daemon=True)
            self.thread.start()

    def stop(self) -> None:
        self.stop_flag.set()


# ---- what a chat message asks ----
_ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
             "premier": 1, "première": 1, "deuxième": 2, "troisième": 3, "quatrième": 4, "cinquième": 5}
LIST = re.compile(r"(?:what (?:did|have) i (?:just )?cop(?:y|ied)|what i (?:have )?copied|(?:show|list|open)(?: me)?(?: my)? (?:clipboard|clipboard history|copies)"
                  r"|(?:my )?clipboard history|what(?:'s| is) (?:on|in) my clipboard|my clipboard|"
                  r"(?:qu'est-ce que j'ai copié|historique du presse-papiers|mon presse-papiers))\s*[?.!]*", re.I)
CLEAR = re.compile(r"(?:clear|empty|wipe|delete) (?:my )?clipboard history|forget (?:everything |what )?i(?: have)? copied|(?:efface|vide) l'historique du presse-papiers", re.I)
OFF = re.compile(r"(?:stop|don't|do not) (?:remembering|keeping|saving) what i copy|turn off (?:the )?clipboard history|clipboard history off|n'enregistre plus ce que je copie", re.I)
ON = re.compile(r"(?:start )?(?:remember|keep) what i copy(?: again)?|turn on (?:the )?clipboard history|clipboard history on", re.I)
BACK = re.compile(r"(?P<verb>paste|put back|copy back|bring back|give me back|restore|colle|remets)\b(?: me)?\s+(?:"
                  r"(?:what|the thing|the text) i (?:had )?copied (?:before|earlier|previously|before that|just before)"
                  r"|(?:the )?(?P<which>previous|last|earlier|other|(?P<ord>first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)|(?:number|no\.?|#) ?(?P<num>\d{1,2}))(?: one| thing| item| copy| text| clipboard)?(?: i copied)?"
                  r"|ce que j'ai copié avant|l'avant-dernier(?:e)? copie)"
                  r"(?: back)?(?: (?:on|to|onto) (?:the|my) clipboard)?\s*[?.!]*", re.I)


def command(text: str) -> dict | None:
    """{"do": "list"|"clear"|"off"|"on"|"back", "index": n, "paste": bool} for a clipboard request, else None."""
    t = re.sub(r"^(?:jarvis[,!]?\s+)?(?:(?:can|could) you |please )?", "", (text or "").strip(), flags=re.I).rstrip(" ?.!")
    t = re.sub(r"\s+please$", "", t, flags=re.I)
    if CLEAR.fullmatch(t):
        return {"do": "clear"}
    if OFF.fullmatch(t):
        return {"do": "off"}
    if ON.fullmatch(t):
        return {"do": "on"}
    if LIST.fullmatch(t):
        return {"do": "list"}
    m = BACK.fullmatch(t)
    if m:
        index = 2                                                  # "before": the one before what is on the clipboard now
        if m.group("num"):
            index = int(m.group("num"))
        elif m.group("ord"):
            index = _ORDINALS[m.group("ord").lower()]
        elif (m.group("which") or "").lower() == "last":
            index = 1                                              # the newest

        return {"do": "back", "index": max(1, index), "paste": m.group("verb").lower() in ("paste", "colle")}
    return None


def short(text: str, n: int = 70) -> str:
    one = re.sub(r"\s+", " ", text).strip()
    return one if len(one) <= n else one[: n - 1].rstrip() + "…"

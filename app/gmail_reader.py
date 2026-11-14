"""Gmail for Jarvis: read-only. Counts and summarises mail that arrived since you last asked.

Jarvis logs in with an app password over IMAP (imap.gmail.com), opens the inbox read-only (so nothing is marked as read),
and never sends, deletes or moves anything. The address and app password are stored in data/mail.json on this PC.
"""
from __future__ import annotations

import email
import email.header
import email.utils
import html
import imaplib
import json
import re
import socket
import ssl
from pathlib import Path

HOST, PORT = "imap.gmail.com", 993
MAX_LISTED = 25                                 # messages whose sender and subject are read
MAX_BODIES = 10                                 # messages whose first lines are also read
SNIPPET = 400
FILTERS = ("all", "personal")                   # personal = Gmail's Primary tab (no promotions, social, updates, forums)


class MailError(RuntimeError):
    """A problem to show to the person in plain words."""


def load(path: Path) -> dict:
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cfg = {}
    return cfg if isinstance(cfg, dict) else {}


def save(path: Path, cfg: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def public(cfg: dict) -> dict:
    """What the page may see: never the password."""
    return {"address": cfg.get("address") or "", "has_password": bool(cfg.get("password")), "enabled": bool(cfg.get("address") and cfg.get("password") and cfg.get("enabled", True)),
            "filter": cfg.get("filter") if cfg.get("filter") in FILTERS else "all", "summarize": cfg.get("summarize", True) is not False,
            "body_to_cloud": cfg.get("body_to_cloud") is True, "last_check": cfg.get("last_check") or ""}


def update(cfg: dict, payload: dict) -> dict:
    cfg = dict(cfg)
    if "address" in payload:
        address = str(payload["address"] or "").strip()[:200]
        if address and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", address):
            raise ValueError("That does not look like an email address.")
        if address != cfg.get("address"):
            cfg.pop("seen_uid", None)
            cfg.pop("uidvalidity", None)
        cfg["address"] = address
    password = payload.get("password")
    if isinstance(password, str) and password.strip():
        cfg["password"] = re.sub(r"\s+", "", password)[:100]        # Google shows app passwords in groups of four letters with spaces
    if "filter" in payload:
        if payload["filter"] not in FILTERS:
            raise ValueError("Filter must be all or personal.")
        cfg["filter"] = payload["filter"]
    for key in ("summarize", "body_to_cloud", "enabled"):
        if key in payload:
            cfg[key] = payload[key] is True
    return cfg


def _decode(value) -> str:
    try:
        return str(email.header.make_header(email.header.decode_header(value or ""))).strip()
    except Exception:
        return str(value or "").strip()


def _text_of(msg) -> str:
    plain = html_part = ""
    parts = msg.walk() if msg.is_multipart() else [msg]
    for part in parts:
        kind = part.get_content_type()
        if kind not in ("text/plain", "text/html") or part.get_filename():
            continue
        try:
            raw = part.get_payload(decode=True) or b""
            text = raw.decode(part.get_content_charset() or "utf-8", errors="replace")
        except Exception:
            continue
        if kind == "text/plain" and not plain:
            plain = text
        elif kind == "text/html" and not html_part:
            html_part = text
    text = plain or re.sub(r"(?is)<(script|style).*?</\1>|<[^>]+>", " ", html_part)
    text = html.unescape(text)
    text = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(">"))     # drop quoted replies
    return re.sub(r"\s+", " ", text).strip()[:SNIPPET]


def parse_message(raw: bytes, with_body: bool) -> dict:
    msg = email.message_from_bytes(raw)
    name, address = email.utils.parseaddr(_decode(msg.get("From")))
    return {"from": name or address or "someone", "address": address, "subject": _decode(msg.get("Subject")) or "(no subject)",
            "snippet": _text_of(msg) if with_body else ""}


def _connect(cfg: dict, timeout: float = 20):
    if not cfg.get("address") or not cfg.get("password"):
        raise MailError("Email is not connected. Open Settings > Mail and enter your Gmail address and an app password.")
    try:
        M = imaplib.IMAP4_SSL(HOST, PORT, ssl_context=ssl.create_default_context(), timeout=timeout)
    except ssl.SSLError as exc:
        raise MailError(f"I could not make a secure connection to Gmail ({exc.__class__.__name__}). A school or work network that inspects traffic can cause this.")
    except (OSError, socket.timeout) as exc:
        raise MailError(f"I could not reach Gmail ({exc}). Check the internet connection; some school and work networks block mail.")
    try:
        M.login(cfg["address"], cfg["password"])
    except imaplib.IMAP4.error as exc:
        try:
            M.shutdown()
        except Exception:
            pass
        detail = str(exc)
        if "web login" in detail.lower() or "ALERT" in detail:
            raise MailError("Google refused the sign-in. Use an app password (Google Account > Security > 2-Step Verification > App passwords), not your normal password.")
        raise MailError("Gmail refused the address or app password. Check them in Settings > Mail. IMAP must be on in Gmail settings (Forwarding and POP/IMAP).")
    return M


def check(cfg: dict, summarize_bodies: bool = True, timeout: float = 20) -> dict:
    """What arrived since the last position that was saved. Does not change the saved position; the caller does that when the person has been told."""
    M = _connect(cfg, timeout)
    try:
        status, _ = M.select("INBOX", readonly=True)
        if status != "OK":
            raise MailError("I could not open the inbox.")
        validity = ""
        try:
            validity = re.sub(r"\D", "", " ".join(x.decode("ascii", "ignore") for x in (M.response("UIDVALIDITY")[1] or []) if x))
        except Exception:
            pass
        personal = cfg.get("filter") == "personal"

        def uids(*criteria) -> list[int]:
            status, data = M.uid("search", None, *criteria)
            return [int(x) for x in (data[0] or b"").split()] if status == "OK" and data and data[0] else []
        everything = uids("ALL")
        top = max(everything) if everything else 0
        unread = len(uids("UNSEEN"))
        seen = cfg.get("seen_uid")
        if seen is None or (validity and cfg.get("uidvalidity") and cfg["uidvalidity"] != validity):
            return {"first": True, "new": [], "total_new": 0, "unread": unread, "max_uid": top, "uidvalidity": validity}
        fresh = [u for u in everything if u > int(seen)]
        if personal and fresh:
            try:
                keep = set(uids("X-GM-RAW", '"category:primary"'))
                fresh = [u for u in fresh if u in keep]
            except Exception:
                pass                                           # not a Gmail-style server: show everything
        items = []
        for number, uid in enumerate(sorted(fresh, reverse=True)[:MAX_LISTED]):
            with_body = summarize_bodies and number < MAX_BODIES
            status, data = M.uid("fetch", str(uid), "(BODY.PEEK[]<0.30000>)" if with_body else "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            raw = next((part[1] for part in (data or []) if isinstance(part, tuple)), b"")
            if status == "OK" and raw:
                items.append(parse_message(raw, with_body))
        return {"first": False, "new": items, "total_new": len(fresh), "unread": unread, "max_uid": top, "uidvalidity": validity}
    except (imaplib.IMAP4.error, OSError) as exc:
        raise MailError(f"Gmail stopped answering ({exc}).")
    finally:
        try:
            M.logout()
        except Exception:
            pass


def plain_digest(result: dict) -> str:
    """The report without any AI model: counts, then sender and subject."""
    if result.get("first"):
        n = result.get("unread", 0)
        return f"Email is connected. You have {n} unread message{'s' if n != 1 else ''} in total. From now on I will tell you what arrives while you are away."
    total = result["total_new"]
    if not total:
        return "No new email since I last checked."
    lines = [f"You have {total} new email{'s' if total != 1 else ''}."]
    for item in result["new"][:6]:
        lines.append(f"From {item['from']}: {item['subject']}.")
    if total > 6:
        lines.append(f"And {total - 6} more.")
    return " ".join(lines)

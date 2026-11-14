"""Phone link: lets the Jarvis Android app reach this PC over the local network.

Off by default. When it is on, the server also listens on the network (instead of this PC only) and every
request that does not come from this PC must carry the pairing code. Settings are kept in data/phone.json.
"""
from __future__ import annotations

import hmac
import json
import secrets
import socket
import threading
import time
from pathlib import Path

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no 0/O or 1/I, so the code is easy to type on a phone
CODE_LENGTH = 10
MAX_FAILS = 8            # wrong codes from one address before it is locked out
LOCKOUT_SECONDS = 300
_lock = threading.Lock()
_fails: dict[str, list[float]] = {}   # address -> [wrong attempts, locked until]


def new_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    code = str(data.get("code") or "")
    return {"enabled": bool(data.get("enabled")), "code": code if len(code) >= 8 else ""}


def save(path: Path, cfg: dict) -> dict:
    cfg = {"enabled": bool(cfg.get("enabled")), "code": str(cfg.get("code") or "") or new_code()}
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg), encoding="utf-8")
    tmp.replace(path)
    return cfg


def is_loopback(address: str) -> bool:
    return address in ("127.0.0.1", "::1", "::ffff:127.0.0.1")


def addresses() -> list[str]:
    """This PC's addresses on the local network, the most likely one first."""
    found: list[str] = []
    try:   # the address used to reach the network; nothing is actually sent
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("10.255.255.255", 1))
            found.append(probe.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            if info[4][0] not in found:
                found.append(info[4][0])
    except OSError:
        pass
    return [a for a in found if not a.startswith("127.")]


def check(path: Path, address: str, supplied: str | None) -> tuple[bool, int, str]:
    """May a request from another device go through? Answers (allowed, HTTP status, message)."""
    cfg = load(path)
    if not cfg["enabled"] or not cfg["code"]:
        return False, 403, "The phone link is switched off on this PC."
    now = time.time()
    with _lock:
        count, until = _fails.get(address, [0, 0.0])
        if until > now:
            return False, 429, "Too many wrong pairing codes. Try again in a few minutes."
        given = (supplied or "").strip().upper()
        if given and hmac.compare_digest(given.encode(), cfg["code"].encode()):
            _fails.pop(address, None)
            return True, 200, ""
        count += 1
        _fails[address] = [0, now + LOCKOUT_SECONDS] if count >= MAX_FAILS else [count, 0.0]
    return False, 401, "The pairing code is missing or wrong."

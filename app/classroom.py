"""Google Classroom, read only: your assignments come into Jarvis as homework (homework.py).

You make a free Google Cloud project once, turn on the Classroom API, create an OAuth client of type "Desktop app", and paste
its client ID and secret into Settings. Jarvis signs in with your school account in the browser (PKCE), then reads:
your active classes, their assignments (title, due date, link) and whether you have turned each in. It never writes
anything to Classroom. Tokens stay in data/classroom.json.

A school decides which apps may use its Google accounts. When it does not allow this one (common for students under 18),
Google says so on the sign-in page and Jarvis explains that the school's IT can allow it; it is not something to get around.

    public(path, redirect)        what Settings shows
    begin(path, id, secret, redirect) -> the Google sign-in address
    finish(path, state, code)     after the sign-in
    assignments(path, now)        [{id, course, title, due, link, done}]
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://classroom.googleapis.com/v1"
SCOPES = "https://www.googleapis.com/auth/classroom.courses.readonly https://www.googleapis.com/auth/classroom.coursework.me.readonly"
PENDING: dict[str, tuple] = {}
KEEP_DAYS = 14                     # assignments whose due date passed more than this long ago are left out


class ClassroomError(Exception):
    pass


def load(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return data if isinstance(data, dict) else {}


def save(path: Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def public(path: Path, redirect_uri: str) -> dict:
    cfg = load(path)
    return {"client_id": cfg.get("client_id", ""), "has_secret": bool(cfg.get("client_secret")), "connected": bool(cfg.get("refresh_token")),
            "user": cfg.get("user", ""), "redirect_uri": redirect_uri, "last_sync": cfg.get("last_sync"), "last_error": cfg.get("last_error", ""),
            "courses": cfg.get("courses", [])}


def read_client(client_id: str, client_secret: str) -> tuple[str, str]:
    """The ID and secret, typed in or pasted as the whole downloaded JSON file."""
    raw = (client_id or "").strip()
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
            data = data.get("installed") or data.get("web") or data
            raw, client_secret = str(data.get("client_id") or ""), str(data.get("client_secret") or client_secret or "")
        except ValueError:
            raise ClassroomError("That does not look like the downloaded client file. Paste the client ID and secret instead.")
    if not re.fullmatch(r"[\w.-]+\.apps\.googleusercontent\.com", raw):
        raise ClassroomError("The client ID ends in .apps.googleusercontent.com. Copy it from Google Cloud > APIs & Services > Credentials.")
    return raw, (client_secret or "").strip()


def begin(path: Path, client_id: str, client_secret: str, redirect_uri: str) -> str:
    cfg = load(path)
    cid, secret = read_client(client_id, client_secret)
    secret = secret or (cfg.get("client_secret", "") if cfg.get("client_id") == cid else "")
    if not secret:
        raise ClassroomError("The client secret is missing. It is next to the client ID in Google Cloud (or in the downloaded file).")
    verifier, state = secrets.token_urlsafe(64)[:96], secrets.token_urlsafe(16)
    for k in [k for k, v in PENDING.items() if time.time() - v[2] > 600]:
        PENDING.pop(k, None)
    PENDING[state] = (verifier, redirect_uri, time.time())
    cfg.update(client_id=cid, client_secret=secret)
    save(path, cfg)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return AUTH_URL + "?" + urllib.parse.urlencode({"response_type": "code", "client_id": cid, "redirect_uri": redirect_uri, "scope": SCOPES,
                                                    "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true",
                                                    "code_challenge_method": "S256", "code_challenge": challenge, "state": state})


def is_ours(state: str) -> bool:
    return bool(state) and state in PENDING


def explain_error(error: str) -> str:
    e = (error or "").lower()
    if "admin_policy" in e or "org_internal" in e or "disallowed" in e:
        return ("Your school's Google settings do not allow Jarvis to read Classroom. Only the school's IT can allow it "
                "(Google offers to send them a request on the sign-in page). Homework you tell Jarvis still works.")
    if "access_denied" in e:
        return "The sign-in was cancelled, or your school's Google settings did not allow it. Nothing was connected."
    return "Google said: " + error[:120]


def _post_form(fields: dict) -> dict:
    req = urllib.request.Request(TOKEN_URL, data=urllib.parse.urlencode(fields).encode(), method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8", "replace"))
            detail = body.get("error_description") or body.get("error") or ""
        except Exception:
            detail = ""
        if "invalid_grant" in str(detail) or exc.code == 400 and "expired" in str(detail).lower():
            raise ClassroomError("The Classroom sign-in has expired or was withdrawn. Press Connect again in Settings > School.")
        raise ClassroomError("Google refused the sign-in" + (": " + str(detail)[:120] if detail else "."))
    except Exception as exc:
        raise ClassroomError("I could not reach Google: " + str(exc)[:100])


def finish(path: Path, state: str, code: str) -> None:
    pending = PENDING.pop(state or "", None)
    if not pending or time.time() - pending[2] > 600:
        raise ClassroomError("That sign-in link has expired. Press Connect in Jarvis again.")
    cfg = load(path)
    out = _post_form({"grant_type": "authorization_code", "code": code, "redirect_uri": pending[1], "client_id": cfg.get("client_id", ""),
                      "client_secret": cfg.get("client_secret", ""), "code_verifier": pending[0]})
    if not out.get("access_token"):
        raise ClassroomError("Google did not give a sign-in. Try again.")
    cfg.update(access_token=out["access_token"], expires_at=time.time() + int(out.get("expires_in", 3600)) - 60, last_error="")
    if out.get("refresh_token"):
        cfg["refresh_token"] = out["refresh_token"]
    save(path, cfg)
    if not cfg.get("refresh_token"):
        raise ClassroomError("Google did not allow staying signed in. Remove Jarvis from your Google account's third-party access, then connect again.")


def disconnect(path: Path) -> None:
    cfg = load(path)
    save(path, {"client_id": cfg.get("client_id", ""), "client_secret": cfg.get("client_secret", "")})


def token(path: Path) -> str:
    cfg = load(path)
    if not cfg.get("refresh_token"):
        raise ClassroomError("Classroom is not connected. Settings > School > Google Classroom explains how.")
    if cfg.get("access_token") and time.time() < cfg.get("expires_at", 0):
        return cfg["access_token"]
    out = _post_form({"grant_type": "refresh_token", "refresh_token": cfg["refresh_token"], "client_id": cfg.get("client_id", ""),
                      "client_secret": cfg.get("client_secret", "")})
    cfg.update(access_token=out["access_token"], expires_at=time.time() + int(out.get("expires_in", 3600)) - 60)
    save(path, cfg)
    return cfg["access_token"]


def get(path: Path, route: str, params: dict | None = None) -> dict:
    url = API + route + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token(path), "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            raw = r.read().decode("utf-8", "replace")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        try:
            err = json.loads(exc.read().decode("utf-8", "replace")).get("error") or {}
        except Exception:
            err = {}
        msg = str(err.get("message") or "")
        if exc.code == 403 and re.search(r"has not been used|is disabled|SERVICE_DISABLED", msg + json.dumps(err)):
            raise ClassroomError("The Google Classroom API is not turned on in your Google Cloud project. Turn it on in APIs & Services > Library, wait a minute, then sync again.")
        if exc.code in (401, 403):
            raise ClassroomError("Google refused to share your Classroom (" + (msg[:120] or f"error {exc.code}") + "). Your school may not allow apps to read it.")
        raise ClassroomError(f"Classroom answered with an error ({exc.code}).")
    except ClassroomError:
        raise
    except Exception as exc:
        raise ClassroomError("I could not reach Google Classroom: " + str(exc)[:100])


def _paged(path: Path, route: str, field: str, params: dict, limit: int = 300) -> list:
    out, page = [], None
    while len(out) < limit:
        d = get(path, route, {**params, **({"pageToken": page} if page else {})})
        out += d.get(field) or []
        page = d.get("nextPageToken")
        if not page:
            break
    return out


def due_of(work: dict) -> float | None:
    """Classroom gives the due date and time in UTC; without a time it means the end of that day."""
    d = work.get("dueDate") or {}
    if not d.get("year"):
        return None
    t = work.get("dueTime") or {}
    if t:
        moment = datetime(d["year"], d["month"], d["day"], int(t.get("hours", 0)), int(t.get("minutes", 0)), tzinfo=timezone.utc)
        return moment.timestamp()
    return datetime(d["year"], d["month"], d["day"], 23, 59).timestamp()


def assignments(path: Path, now: float | None = None) -> list[dict]:
    now = time.time() if now is None else now
    courses = _paged(path, "/courses", "courses", {"studentId": "me", "courseStates": "ACTIVE", "pageSize": 50}, 60)
    out = []
    for c in courses:
        works = _paged(path, f"/courses/{c['id']}/courseWork", "courseWork", {"pageSize": 50, "orderBy": "updateTime desc"}, 150)
        if not works:
            continue
        subs = _paged(path, f"/courses/{c['id']}/courseWork/-/studentSubmissions", "studentSubmissions", {"userId": "me", "pageSize": 100}, 300)
        state = {s.get("courseWorkId"): s.get("state") for s in subs}
        for w in works:
            if w.get("state", "PUBLISHED") != "PUBLISHED":
                continue
            due = due_of(w)
            if due is not None and due < now - KEEP_DAYS * 86400:
                continue
            out.append({"id": f"{c['id']}/{w['id']}", "course": c.get("name", ""), "title": str(w.get("title") or "Assignment")[:150], "due": due,
                        "link": w.get("alternateLink", ""), "done": state.get(w["id"]) in ("TURNED_IN", "RETURNED")})
    cfg = load(path)
    cfg.update(courses=[c.get("name", "") for c in courses][:40], last_sync=now, last_error="")
    save(path, cfg)
    return out


def note_error(path: Path, message: str) -> None:
    cfg = load(path)
    cfg["last_error"] = message[:300]
    save(path, cfg)

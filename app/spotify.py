"""Spotify control: "play Blinding Lights on Spotify", "play the album Discovery by Daft Punk", "queue Bohemian Rhapsody".

Jarvis uses Spotify's official Web API with a login you approve in your browser (PKCE: no password and no client secret are ever stored here).
Playing a chosen song needs Spotify Premium. You make a free "app" at developer.spotify.com/dashboard and paste its Client ID in Settings.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

AUTH_URL, TOKEN_URL, API = "https://accounts.spotify.com/authorize", "https://accounts.spotify.com/api/token", "https://api.spotify.com/v1"
SCOPES = "user-modify-playback-state user-read-playback-state user-read-currently-playing playlist-read-private"
PENDING: dict = {}          # state -> (verifier, redirect_uri, made_at)


class SpotifyError(ValueError):
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
    return {"client_id": cfg.get("client_id", ""), "connected": bool(cfg.get("refresh_token")), "user": cfg.get("user", ""), "redirect_uri": redirect_uri}


def begin(path: Path, client_id: str, redirect_uri: str) -> str:
    client_id = (client_id or "").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{32}", client_id):
        raise SpotifyError("The Client ID is 32 letters and digits. Copy it from your app on developer.spotify.com/dashboard.")
    verifier = secrets.token_urlsafe(64)[:96]
    state = secrets.token_urlsafe(16)
    for k in [k for k, v in PENDING.items() if time.time() - v[2] > 600]:
        PENDING.pop(k, None)
    PENDING[state] = (verifier, redirect_uri, time.time())
    cfg = load(path)
    cfg["client_id"] = client_id
    save(path, cfg)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return AUTH_URL + "?" + urllib.parse.urlencode({"response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri, "scope": SCOPES,
                                                    "code_challenge_method": "S256", "code_challenge": challenge, "state": state})


def _post_form(url: str, fields: dict) -> dict:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode(), method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8", "replace")).get("error_description") or ""
        except Exception:
            detail = ""
        raise SpotifyError("Spotify refused the login" + (": " + detail[:120] if detail else "."))
    except Exception as exc:
        raise SpotifyError("I could not reach Spotify: " + str(exc)[:100])


def finish(path: Path, state: str, code: str) -> None:
    pending = PENDING.pop(state or "", None)
    if not pending or time.time() - pending[2] > 600:
        raise SpotifyError("That login link has expired. Press Connect in Jarvis again.")
    cfg = load(path)
    out = _post_form(TOKEN_URL, {"grant_type": "authorization_code", "code": code, "redirect_uri": pending[1], "client_id": cfg.get("client_id", ""), "code_verifier": pending[0]})
    store_tokens(path, cfg, out)
    try:
        me = Client(path).call("GET", "/me")
        cfg = load(path)
        cfg["user"] = str(me.get("display_name") or me.get("id") or "")[:60]
        save(path, cfg)
    except SpotifyError:
        pass


def store_tokens(path: Path, cfg: dict, out: dict) -> None:
    if not out.get("access_token"):
        raise SpotifyError("Spotify did not give a login. Try again.")
    cfg["access_token"], cfg["expires_at"] = out["access_token"], time.time() + int(out.get("expires_in", 3600)) - 60
    if out.get("refresh_token"):
        cfg["refresh_token"] = out["refresh_token"]
    save(path, cfg)


def disconnect(path: Path) -> None:
    cfg = load(path)
    save(path, {"client_id": cfg.get("client_id", "")})


class Client:
    def __init__(self, path: Path, launch=None):
        self.path, self.launch = Path(path), launch

    def token(self) -> str:
        cfg = load(self.path)
        if not cfg.get("refresh_token"):
            raise SpotifyError("Spotify is not connected, sir. Connect it in Settings > Shortcuts > Spotify.")
        if cfg.get("access_token") and time.time() < cfg.get("expires_at", 0):
            return cfg["access_token"]
        out = _post_form(TOKEN_URL, {"grant_type": "refresh_token", "refresh_token": cfg["refresh_token"], "client_id": cfg.get("client_id", "")})
        store_tokens(self.path, cfg, out)
        return load(self.path)["access_token"]

    def call(self, method: str, route: str, params: dict | None = None, body: dict | None = None):
        url = API + route + ("?" + urllib.parse.urlencode(params) if params else "")
        data = json.dumps(body).encode() if body is not None else (b"" if method in ("POST", "PUT") else None)
        req = urllib.request.Request(url, data=data, method=method, headers={"Authorization": "Bearer " + self.token(), "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.read().decode("utf-8", "replace")
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as exc:
            try:
                err = json.loads(exc.read().decode("utf-8", "replace")).get("error") or {}
            except Exception:
                err = {}
            reason = err.get("reason", "") if isinstance(err, dict) else ""
            if exc.code == 401:
                raise SpotifyError("Spotify logged me out. Connect it again in Settings.")
            if exc.code == 403 and reason == "PREMIUM_REQUIRED":
                raise SpotifyError("Spotify only lets other programs play songs for Premium accounts, sir.")
            if exc.code == 404 and reason == "NO_ACTIVE_DEVICE":
                raise SpotifyError("NO_DEVICE")
            if exc.code == 429:
                raise SpotifyError("Spotify says to slow down. Try again in a moment.")
            raise SpotifyError(f"Spotify answered with an error ({exc.code}).")
        except SpotifyError:
            raise
        except Exception as exc:
            raise SpotifyError("I could not reach Spotify: " + str(exc)[:100])

    # ---- playback ----
    def device(self, wait: float = 8.0) -> str | None:
        """An id to play on: the active device, else the first one; opens the Spotify app when there is none."""
        for attempt in range(2):
            devices = self.call("GET", "/me/player/devices").get("devices") or []
            usable = [d for d in devices if not d.get("is_restricted")]
            if usable:
                return next((d["id"] for d in usable if d.get("is_active")), usable[0]["id"])
            if attempt == 0 and self.launch:
                self.launch()
                end = time.time() + wait
                while time.time() < end:
                    time.sleep(1)
                    if (self.call("GET", "/me/player/devices").get("devices") or []):
                        break
        return None

    def play(self, uri: str, kind: str) -> None:
        dev = self.device()
        if not dev:
            raise SpotifyError("I could not find a Spotify player, sir. Open Spotify on this PC or your phone once, then ask again.")
        body = {"uris": [uri]} if kind == "track" else {"context_uri": uri}
        try:
            self.call("PUT", "/me/player/play", {"device_id": dev}, body)
        except SpotifyError as exc:
            if str(exc) == "NO_DEVICE":
                raise SpotifyError("Spotify has no active player. Press play once in the Spotify app, then ask again.")
            raise

    def queue(self, uri: str) -> None:
        dev = self.device()
        if not dev:
            raise SpotifyError("I could not find a Spotify player, sir. Open Spotify first.")
        self.call("POST", "/me/player/queue", {"uri": uri, "device_id": dev})

    def search(self, kind: str, query: str):
        out = self.call("GET", "/search", {"q": query, "type": kind, "limit": 5})
        return (out.get(kind + "s") or {}).get("items") or []

    def my_playlist(self, name: str):
        want = re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()
        best = None
        for item in (self.call("GET", "/me/playlists", {"limit": 50}).get("items") or []):
            have = re.sub(r"[^a-z0-9 ]", "", (item or {}).get("name", "").lower()).strip()
            if have == want:
                return item
            if want and want in have and best is None:
                best = item
        return best


def _name(item: dict, kind: str) -> str:
    if kind in ("track", "album"):
        artists = ", ".join(a.get("name", "") for a in (item.get("artists") or [])[:2])
        return f"“{item.get('name', '?')}”" + (f" by {artists}" if artists else "")
    return f"“{item.get('name', '?')}”"


def parse(text: str):
    """(action, kind, title, artist, own_playlist) for "play ... on Spotify" style requests, else None."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = re.sub(r"^(?:(?:hey\s+)?jarvis[,.:]?\s+)?(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?)?", "", t, flags=re.I)
    t = re.sub(r"\s*(?:please|for me|now)?\s*[.!?]*$", "", t, flags=re.I).strip()
    if not t or len(t) > 160:
        return None
    mentions = bool(re.search(r"\bspotify\b", t, re.I))
    t = re.sub(r"^spotify[,:]?\s+", "", t, flags=re.I)
    t = re.sub(r"\s+(?:on|in|with|using|through|via)\s+spotify$", "", t, flags=re.I).strip()
    m = re.fullmatch(r"(play|queue|add|put)\s+(.+)", t, re.I)
    if not m:
        m = re.fullmatch(r"(?:let'?s\s+)?(listen)\s+to\s+(.+)", t, re.I)
    if not m:
        return None
    verb, rest = m.group(1).lower(), m.group(2).strip()
    action = "queue" if verb in ("queue", "add", "put") else "play"
    if action == "queue":
        rest = re.sub(r"\s+(?:to|in|on)\s+(?:the\s+|my\s+)?(?:queue|up next)$", "", rest, flags=re.I)
        if rest.lower() == m.group(2).lower() and not mentions:
            return None
    rest = re.sub(r"^(?:me\s+)?(?:some\s+)?", "", rest, flags=re.I)
    kind, own = None, False
    mk = re.match(r"(?:the\s+|a\s+|my\s+)?(song|track|album|playlist|artist|band|music by|songs by|something by)\s+(?:called\s+|named\s+)?(.+)", rest, re.I)
    if mk:
        word = mk.group(1).lower()
        kind = {"song": "track", "track": "track", "album": "album", "playlist": "playlist", "artist": "artist", "band": "artist", "music by": "artist", "songs by": "artist", "something by": "artist"}[word]
        rest = mk.group(2).strip()
    else:
        mp = re.fullmatch(r"my\s+(.+?)\s+playlist", rest, re.I)
        if mp:
            kind, rest, own = "playlist", mp.group(1), True
    if kind is None and not mentions:
        return None
    if re.fullmatch(r"(?:it|that|this|music|something|a song|songs|the music|again|me something|the song|a track|anything)?", rest, re.I) or not rest:
        return None
    if kind is None and re.fullmatch(r"(?:the\s+)?(?:next|previous|last)\b.*", rest, re.I):
        return None
    title, artist = rest, ""
    if kind in ("track", "album", None):
        mb = re.fullmatch(r"(.+?)\s+by\s+(.+)", rest, re.I)
        if mb:
            title, artist = mb.group(1).strip(), mb.group(2).strip()
    return action, kind or "any", title.strip(), artist.strip(), own


def command(text: str, path: Path, launch=None) -> str | None:
    parsed = parse(text)
    if not parsed:
        return None
    action, kind, title, artist, own = parsed
    if not load(path).get("refresh_token"):
        return "Spotify is not connected yet, sir. Settings > Shortcuts > Spotify explains the three steps." if re.search(r"spotify", text, re.I) else None
    client = Client(path, launch)
    if kind == "any" and (artist or action == "queue"):
        kind = "track"
    try:
        if kind == "playlist":
            item = client.my_playlist(title)
            if not item:
                found = client.search("playlist", title)
                item = next((x for x in found if x), None)
        elif kind == "artist":
            item = next((x for x in client.search("artist", title) if x), None)
        elif kind == "any":                      # "play Taylor Swift on Spotify": an artist when the name matches exactly, else a song
            norm = lambda x: re.sub(r"[^a-z0-9]", "", (x or "").lower())
            artists = [x for x in client.search("artist", title) if x]
            if artists and norm(artists[0].get("name")) == norm(title) and action == "play":
                item, kind = artists[0], "artist"
            else:
                item, kind = next((x for x in client.search("track", title) if x), None), "track"
        else:
            q = title + (f" artist:{artist}" if artist else "")
            item = next((x for x in client.search(kind, q) if x), None)
            if not item and artist:
                item = next((x for x in client.search(kind, f"{title} {artist}") if x), None)
        if not item:
            return f"I could not find {title}" + (f" by {artist}" if artist else "") + " on Spotify, sir."
        uri = item["uri"]
        if action == "queue":
            if kind not in ("track",):
                return "I can only queue single songs, sir."
            client.queue(uri)
            return f"Added {_name(item, kind)} to your queue, sir."
        client.play(uri, "track" if kind == "track" else "context")
        return f"Playing {_name(item, kind)} on Spotify, sir."
    except SpotifyError as exc:
        return str(exc)

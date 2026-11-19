"""Spotify control: "play Blinding Lights on Spotify", "play the album Discovery by Daft Punk", "queue Bohemian Rhapsody".

The queue: "queue Yellow", "add Yellow by Coldplay to the queue", "play Fix You next", "queue Yellow, Fix You and then Clocks",
"queue a song by Queen", "queue 3 songs by Queen", "queue the album Discovery", "queue my workout playlist", "what's in my queue".

Jarvis uses Spotify's official Web API with a login you approve in your browser (PKCE: no password and no client secret are ever stored here).
Playing a chosen song needs Spotify Premium. You make a free "app" at developer.spotify.com/dashboard and paste its Client ID in Settings.
"""
from __future__ import annotations

import base64
import random
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

    def queue_many(self, uris: list[str]) -> bool:
        """Add songs to the queue. When nothing is playing (Spotify then has no queue), the first one starts playing and the
        rest are queued behind it. Returns True when playback had to be started."""
        dev = self.device()
        if not dev:
            raise SpotifyError("I could not find a Spotify player, sir. Open Spotify on this PC or your phone, then ask again.")
        started = False
        playing = self.call("GET", "/me/player") or {}
        if not playing.get("item"):
            self.play(uris[0], "track")
            uris, started = uris[1:], True
            time.sleep(0.4)                                  # Spotify needs a moment before the new queue accepts songs
        for uri in uris:
            try:
                self.call("POST", "/me/player/queue", {"uri": uri, "device_id": dev})
            except SpotifyError as exc:
                if str(exc) == "NO_DEVICE":
                    raise SpotifyError("Spotify has no active player. Press play once in the Spotify app, then ask again.")
                raise
        return started

    def upcoming(self) -> dict:
        return self.call("GET", "/me/player/queue") or {}

    def album_tracks(self, album: dict, limit: int = 50) -> list[str]:
        album_id = str(album.get("id") or album.get("uri", "").rsplit(":", 1)[-1])
        out = self.call("GET", f"/albums/{album_id}/tracks", {"limit": min(limit, 50)})
        return [t["uri"] for t in (out.get("items") or []) if t and t.get("uri")][:limit]

    def playlist_tracks(self, playlist: dict, limit: int = 30) -> list[str]:
        pl_id = str(playlist.get("id") or playlist.get("uri", "").rsplit(":", 1)[-1])
        out = None
        for route in (f"/playlists/{pl_id}/tracks", f"/playlists/{pl_id}/items"):
            try:
                out = self.call("GET", route, {"limit": min(limit, 50)})
                break
            except SpotifyError:
                out = None
        if out is None:
            raise SpotifyError("Spotify would not give me the songs of that playlist, sir. (It does not share its own made-for-you playlists.)")
        uris = []
        for entry in out.get("items") or []:
            track = (entry or {}).get("track") or (entry or {}).get("item") or {}
            if track.get("uri", "").startswith("spotify:track:"):
                uris.append(track["uri"])
        return uris[:limit]

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


VAGUE = re.compile(r"(?:it|that|this|these|them|music|something|anything|a song|songs|the music|the song|a track|this song|that song|this one|that one|the next song|next|one|more|some more|some music|more music|again)", re.I)
NUMBERS = {"a": 1, "one": 1, "an": 1, "two": 2, "a couple of": 2, "a couple": 2, "couple of": 2, "three": 3, "a few": 3, "few": 3, "some": 3, "four": 4,
           "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
NEXT_WORDS = r"(?:next|up next|right after this(?:\s+one|\s+song|\s+track)?|after this(?:\s+one|\s+song|\s+track)?|after (?:the |this )?(?:current|present) (?:song|track)|after that)"


def _clean(text: str):
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = re.sub(r"^(?:(?:hey\s+|ok\s+|okay\s+)?jarvis[,.:]?\s+)?(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?)?(?:(?:i\s+want\s+(?:you\s+)?to|i'?d\s+like\s+(?:you\s+)?to)\s+)?", "", t, flags=re.I)
    t = re.sub(r"\s*(?:,?\s*please|for me|now|thanks|thank you)?\s*[.!?]*$", "", t, flags=re.I).strip()
    mentions = bool(re.search(r"\bspotify\b", t, re.I))
    t = re.sub(r"^spotify[,:]?\s+", "", t, flags=re.I)
    t = re.sub(r"\s+(?:on|in|with|using|through|via)\s+spotify$", "", t, flags=re.I).strip()
    return t, mentions


def _queue_item(piece: str):
    """One thing to queue: {"kind": track|artist|album|playlist, "title", "artist", "count", "own"}, or None when too vague."""
    p = piece.strip().strip("\"“”'").strip()
    p = re.sub(r"^(?:also|and|then|and then)\s+", "", p, flags=re.I).strip()
    if not p or VAGUE.fullmatch(p):
        return None
    nums = "|".join(sorted((re.escape(k) for k in NUMBERS), key=len, reverse=True))
    m = re.fullmatch(rf"(?:(\d{{1,2}}|{nums})\s+)?(?:more\s+)?(?:songs?|tracks?|tunes?|things?)\s+(?:by|from)\s+(.+)", p, re.I) \
        or re.fullmatch(r"()(?:something|anything)\s+(?:by|from)\s+(.+)", p, re.I)
    if m:
        word = (m.group(1) or "").lower()
        count = int(word) if word.isdigit() else NUMBERS.get(word, 1)
        return {"kind": "artist", "title": m.group(2).strip(), "artist": "", "count": max(1, min(count, 10)), "own": False}
    m = re.fullmatch(r"(?:the\s+|an\s+|my\s+)?album\s+(?:called\s+|named\s+)?(.+)", p, re.I)
    if m:
        mb = re.fullmatch(r"(.+?)\s+by\s+(.+)", m.group(1), re.I)
        return {"kind": "album", "title": (mb.group(1) if mb else m.group(1)).strip(), "artist": (mb.group(2) if mb else "").strip(), "count": 0, "own": False}
    m = re.fullmatch(r"my\s+(.+?)\s+playlist", p, re.I)
    if m:
        return {"kind": "playlist", "title": m.group(1).strip(), "artist": "", "count": 0, "own": True}
    m = re.fullmatch(r"(?:the\s+|my\s+|a\s+)?playlist\s+(?:called\s+|named\s+)?(.+)", p, re.I)
    if m:
        return {"kind": "playlist", "title": m.group(1).strip(), "artist": "", "count": 0, "own": False}
    p = re.sub(r"^(?:the\s+|a\s+)?(?:song|track|tune)\s+(?:called\s+|named\s+)?", "", p, flags=re.I).strip()
    if not p or VAGUE.fullmatch(p):
        return None
    mb = re.fullmatch(r"(.+?)\s+by\s+(.+)", p, re.I)
    return {"kind": "track", "title": (mb.group(1) if mb else p).strip().strip("\"“”'"), "artist": (mb.group(2) if mb else "").strip(), "count": 1, "own": False}


def queue_request(text: str):
    """What a queue request asks for: {"op": "add", "items": [...], "explicit": bool}, {"op": "show"}, {"op": "clear"}, or None.
    "explicit" is True when the words alone make it clear this is about the music queue (so Jarvis can answer
    "Spotify is not connected" instead of letting the message go to the AI)."""
    t, mentions = _clean(text)
    if not t or len(t) > 220:
        return None
    low = t.lower()
    q = r"(?:the\s+|my\s+)?(?:spotify\s+|music\s+|song\s+|play\s+)?(?:queue|up next|play queue)"
    if re.fullmatch(rf"(?:what'?s|what\s+is|what\s+are|show(?:\s+me)?|list|read(?:\s+me)?|tell\s+me)\s+(?:in\s+|on\s+)?{q}|"
                    rf"(?:what'?s|what\s+is|what\s+are)\s+(?:in|on|next\s+in|next\s+on|coming\s+up\s+in|left\s+in)\s+{q}|"
                    r"(?:what'?s|what\s+is|which)\s+(?:the\s+)?(?:next|following)\s+(?:song|track)|(?:what|which)\s+(?:song|track)\s+(?:is|comes|plays)\s+(?:next|after\s+this(?:\s+one)?)|"
                    r"what(?:'s|\s+is|\s+are)?\s+(?:queued|in\s+the\s+queue)(?:\s+up)?|what\s+(?:songs?|tracks?)\s+(?:are|is)\s+(?:queued|coming\s+up|next)(?:\s+up)?|"
                    r"what'?s\s+(?:coming\s+up|up\s+next|playing\s+next)", low) and (re.search(r"queue|song|track", low) or mentions):
        return {"op": "show"}
    if re.fullmatch(rf"(?:clear|empty|wipe|reset|delete|remove\s+everything\s+(?:from|in))\s+{q}|remove\s+.+\s+from\s+{q}|take\s+.+\s+(?:off|out\s+of)\s+{q}", low):
        return {"op": "clear"}
    body, explicit = None, False
    m = re.fullmatch(rf"queue(?:\s+up)?\s+(.+?)(?:\s+{NEXT_WORDS})?(?:\s+(?:to|in|on)\s+{q})?", t, re.I)
    if m:
        body, explicit = m.group(1), True
    if body is None:
        m = re.fullmatch(rf"(?:add|put|stick|throw|pop|chuck|place|get)\s+(.+?)\s+(?:to|in|into|on|onto|at\s+the\s+end\s+of)\s+{q}(?:\s+{NEXT_WORDS})?", t, re.I)
        if m:
            body, explicit = m.group(1), True
    if body is None:
        m = re.fullmatch(rf"(play|put\s+on|throw\s+on|add|put|stick)\s+(.+?)\s+{NEXT_WORDS}", t, re.I)
        if m and (mentions or m.group(1).lower() in ("play", "put on", "throw on")) and not re.fullmatch(r"(?:the\s+)?(?:next|previous|last)?\s*(?:song|track|one)?", m.group(2), re.I):
            body, explicit = m.group(2), mentions
    if body is None:
        return None
    pieces = [x for x in re.split(r"\s*,\s*(?:and\s+then\s+|and\s+|then\s+)?|\s+and\s+then\s+|\s+then\s+|\s+followed\s+by\s+|\s*;\s*", body, flags=re.I) if x.strip()]
    items = [_queue_item(x) for x in pieces]
    if not pieces or any(i is None for i in items):
        return {"op": "vague", "explicit": explicit} if explicit else None
    return {"op": "add", "items": items, "explicit": explicit}


def _norm(x: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (x or "").lower())


def _find_track(client, title: str, artist: str):
    q = title + (f" artist:{artist}" if artist else "")
    found = [x for x in client.search("track", q) if x]
    if not found and artist:
        found = [x for x in client.search("track", f"{title} {artist}") if x]
    return found[0] if found else None


def _queue_command(req: dict, client) -> str:
    if req["op"] == "show":
        out = client.upcoming()
        now, nxt = out.get("currently_playing"), [x for x in (out.get("queue") or []) if x]
        if not now and not nxt:
            return "Nothing is playing on Spotify right now, sir, so there is no queue."
        seen, names = set(), []
        for item in nxt:                                     # Spotify repeats the queue to fill the list: show each song once
            if item.get("uri") in seen:
                break
            seen.add(item.get("uri"))
            names.append(_name(item, "track"))
        head = f"Now playing {_name(now, 'track')}." if now else ""
        if not names:
            return (head + " " if head else "") + "Nothing is queued after it, sir."
        shown = names[:6]
        more = f", and {len(names) - 6} more" if len(names) > 6 else ""
        return (head + " " if head else "") + "Up next, sir: " + "; ".join(f"{i + 1}. {n}" for i, n in enumerate(shown)) + more + "."
    if req["op"] == "clear":
        return ("Spotify does not let other programs remove songs from the queue, sir. In the Spotify app, open the queue "
                "(the list icon next to the volume) and press “Clear queue”, or remove single songs there.")
    if req["op"] == "vague":
        return "Which song should I add to the queue, sir? For example “queue Yellow by Coldplay”."
    uris, names, missing = [], [], []
    for it in req["items"]:
        kind, title, artist = it["kind"], it["title"], it["artist"]
        if kind == "track":
            item = _find_track(client, title, artist)
            # "queue Yellow and Fix You": one title, unless Spotify has a song with that whole name
            if " and " in f" {title.lower()} " and not artist and (not item or _norm(title) not in _norm(item.get("name"))):
                parts = [x for x in re.split(r"\s+and\s+", title, flags=re.I) if x.strip()]
                found = [(x, _find_track(client, x, "")) for x in parts]
                if all(f for _, f in found):
                    for _, f in found:
                        uris.append(f["uri"]); names.append(_name(f, "track"))
                    continue
            if not item:
                missing.append(title + (f" by {artist}" if artist else ""))
                continue
            uris.append(item["uri"]); names.append(_name(item, "track"))
        elif kind == "artist":
            artists = [x for x in client.search("artist", title) if x]
            who = artists[0]["name"] if artists else title
            tracks = [x for x in client.search("track", f'artist:"{who}"') if x]
            tracks = [x for x in tracks if any(_norm(a.get("name")) == _norm(who) for a in (x.get("artists") or []))] or tracks
            if not tracks:
                missing.append(f"songs by {title}")
                continue
            picks, seen = [], set()
            for x in random.sample(tracks, len(tracks)):
                if _norm(x.get("name")) not in seen:
                    seen.add(_norm(x.get("name"))); picks.append(x)
                if len(picks) >= it["count"]:
                    break
            for x in picks:
                uris.append(x["uri"]); names.append(_name(x, "track"))
        elif kind == "album":
            q = title + (f" artist:{artist}" if artist else "")
            album = next((x for x in client.search("album", q) if x), None)
            if not album:
                missing.append(f"the album {title}")
                continue
            got = client.album_tracks(album)
            uris += got; names.append(f"the album {_name(album, 'album')} ({len(got)} songs)")
        else:
            pl = client.my_playlist(title) if it["own"] else None
            pl = pl or next((x for x in client.search("playlist", title) if x), None)
            if not pl:
                missing.append(f"the playlist {title}")
                continue
            got = client.playlist_tracks(pl)
            uris += got; names.append(f"the playlist {_name(pl, 'playlist')} ({len(got)} songs)")
    if not uris:
        return "I could not find " + " or ".join(missing) + " on Spotify, sir." if missing else "There was nothing to add, sir."
    started = client.queue_many(uris)
    what = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    if started:
        text = f"Nothing was playing, so I started {what} on Spotify, sir." if len(uris) == 1 else f"Nothing was playing, so I started Spotify with {what}, sir."
    else:
        text = f"Added {what} to your queue, sir."
    if missing:
        text += " I could not find " + " or ".join(missing) + "."
    return text


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
    req = queue_request(text)
    if req:
        if not load(path).get("refresh_token"):
            return "Spotify is not connected yet, sir. Settings > Shortcuts > Spotify explains the three steps." if req.get("explicit") or req["op"] != "add" and re.search(r"queue|spotify", text, re.I) else None
        try:
            return _queue_command(req, Client(path, launch))
        except SpotifyError as exc:
            return str(exc)
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

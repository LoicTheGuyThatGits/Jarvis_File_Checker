"""Talk to Jarvis from your phone through a Telegram bot.

Jarvis asks Telegram for new messages (long polling), so no port, tunnel or public address is needed. Only the
paired owner is answered. Each message goes through Jarvis's own /api/chat on this PC, so timers, memory, documents,
the weather, routines and the rest all work. Actions that change things wait for an Approve button.
Settings live in data/telegram.json: {"token", "owner_id", "pair_code", "mirror_reminders", "brief_time", "docs"}.
"""
import base64
import http.client
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
try:                       # trust the certificates Windows trusts (school, company and antivirus networks that inspect secure traffic install their own)
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

API = (os.environ.get("JARVIS_TELEGRAM_API") or "https://api.telegram.org").rstrip("/")
PORT = int(os.environ.get("JARVIS_PORT", "8765"))
MAX_TEXT = 4000
HELP = ("I'm Jarvis. Send me a message and I'll answer it, just like in the app.\n\n"
        "/docs on|off  answer from your saved documents\n/screenshot  see your screen now\n/look  Jarvis looks at your screen and tells you what it sees\n/mail  what new email arrived\n/todo  your to-do list\n/agenda  today and what is coming up\n/new  start a fresh conversation\n/status  how things are\n"
        "You can also send me a voice note, a photo (add a question as the caption), or a PDF, Word, Excel or text file to add to your documents.")


def split_text(text: str, limit: int = MAX_TEXT) -> list[str]:
    text, parts = (text or "").strip() or "…", []
    while len(text) > limit:
        cut = max(text.rfind("\n", 0, limit), text.rfind(". ", 0, limit) + 1, limit // 2)
        parts.append(text[:cut].rstrip()); text = text[cut:].lstrip()
    return parts + [text]


def describe_action(action: dict) -> str:
    kind = action.get("type")
    if kind == "run_command":
        return "run this PowerShell command on your PC:\n" + str(action.get("command", ""))[:1500]
    if kind == "open_url":
        return "open " + str(action.get("url", ""))
    if kind == "open_app":
        return "open " + str(action.get("name", "an app"))
    if kind == "generate_image":
        return "create an image: " + str(action.get("prompt", ""))[:500]
    if kind == "save_code":
        names = [f.get("filename", "?") for f in (action.get("files") or [])] or [action.get("filename", "a file")]
        return "save " + ", ".join(names[:12])
    if kind == "routine":
        return "run a routine"
    return "do this: " + str(kind)


class TelegramBot:
    def __init__(self, root: Path = ROOT, port: int = PORT):
        self.root, self.port = Path(root), port
        self.lock = threading.RLock()
        self.history: list[dict] = []
        self.offset = 0
        self.state, self.error, self.username = "off", "", ""
        self.stop = threading.Event()
        self.thread = None
        self.last_brief = ""
        self.token_in_use = None
        self.inline = False                                  # tests set this to handle updates synchronously
        self.pool: list = []
        self.pool_lock = threading.Lock()
        self.chat_lock = threading.Lock()

    # ---- config
    @property
    def path(self) -> Path:
        return self.root / "data" / "telegram.json"

    def load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            cfg = data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            cfg = {}
        if not cfg.get("token") and os.environ.get("JARVIS_TELEGRAM_TOKEN"):
            cfg["token"] = os.environ["JARVIS_TELEGRAM_TOKEN"]
        return cfg

    def save(self, cfg: dict) -> None:
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
            tmp.replace(self.path)

    def public(self) -> dict:
        cfg = self.load()
        paired = bool(cfg.get("owner_id"))
        return {"configured": bool(cfg.get("token")), "paired": paired, "state": self.state, "error": self.error, "username": self.username,
                "pair_code": None if paired or not cfg.get("token") else cfg.get("pair_code"),
                "mirror_reminders": cfg.get("mirror_reminders", True) is not False, "screenshot_after": cfg.get("screenshot_after", True) is not False, "verify_screen": cfg.get("verify_screen") is True, "brief_time": cfg.get("brief_time") or "", "docs": bool(cfg.get("docs"))}

    def update(self, payload: dict) -> dict:
        with self.lock:
            cfg = self.load()
            token = str(payload.get("token") or "").strip()
            if token:
                if not re.fullmatch(r"\d{5,}:[A-Za-z0-9_-]{20,}", token):
                    raise ValueError("That does not look like a bot token. It looks like 123456789:ABC-DEF… from BotFather.")
                if token != cfg.get("token"):
                    cfg.update({"token": token, "owner_id": None, "pair_code": f"{secrets.randbelow(10**6):06d}"})
            if payload.get("disconnect") is True:
                cfg = {k: v for k, v in cfg.items() if k not in ("token", "owner_id", "pair_code")}
            if payload.get("unpair") is True and cfg.get("token"):
                cfg.update({"owner_id": None, "pair_code": f"{secrets.randbelow(10**6):06d}"})
            if "mirror_reminders" in payload:
                cfg["mirror_reminders"] = payload["mirror_reminders"] is True
            if "screenshot_after" in payload:
                cfg["screenshot_after"] = payload["screenshot_after"] is True
            if "verify_screen" in payload:
                cfg["verify_screen"] = payload["verify_screen"] is True
            if "brief_time" in payload:
                value = str(payload["brief_time"] or "").strip()
                if value and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
                    raise ValueError("Use a time like 07:30.")
                cfg["brief_time"] = value
            if cfg.get("token") and not cfg.get("owner_id") and not cfg.get("pair_code"):
                cfg["pair_code"] = f"{secrets.randbelow(10**6):06d}"
            self.save(cfg)
        self.ensure_running()
        return self.public()

    # ---- Telegram calls (kept-alive connections: a fresh TLS handshake per call adds a noticeable delay)
    def _connect(self, timeout: float):
        parts = urllib.parse.urlsplit(API)
        factory = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
        return factory(parts.netloc, timeout=timeout)

    def call(self, method: str, params: dict | None = None, timeout: float = 35) -> dict:
        return self._post(method, json.dumps(params or {}).encode(), "application/json", timeout)

    def send_photo(self, chat_id, jpeg: bytes, caption: str = "") -> None:
        boundary = "----jarvis" + secrets.token_hex(8)
        parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n']
        if caption:
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n')
        head = "".join(parts) + f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="screen.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'
        body = head.encode() + jpeg + f"\r\n--{boundary}--\r\n".encode()
        try:
            self._post("sendPhoto", body, f"multipart/form-data; boundary={boundary}", 60)
        except Exception as exc:
            print(f"[jarvis] telegram photo failed: {exc}")
            self.send(chat_id, "I took the screenshot but could not send it: " + str(exc)[:200])

    def send_screenshot(self, chat_id, data: dict) -> None:
        if data.get("screenshot"):
            import base64
            try:
                self.send_photo(chat_id, base64.b64decode(data["screenshot"]), "Your screen right now")
            except ValueError:
                pass
        elif data.get("screenshot_error"):
            self.send(chat_id, "I could not take a screenshot: " + data["screenshot_error"] + " (the screen may be locked)")

    def _post(self, method: str, body: bytes, content_type: str, timeout: float) -> dict:
        token = self.load().get("token")
        if not token:
            raise RuntimeError("no token")
        base = urllib.parse.urlsplit(API).path.rstrip("/")
        for attempt in (0, 1):
            with self.pool_lock:
                conn = self.pool.pop() if self.pool else None
            reused = conn is not None
            if conn is None:
                conn = self._connect(timeout)
            conn.timeout = timeout
            if conn.sock:
                conn.sock.settimeout(timeout)
            try:
                conn.request("POST", f"{base}/bot{token}/{method}", body=body, headers={"Content-Type": content_type})
                response = conn.getresponse()
                raw = response.read()
            except (http.client.HTTPException, ConnectionError, OSError):
                conn.close()
                if reused and attempt == 0:
                    continue                                   # the idle connection had been closed; try a new one
                raise
            with self.pool_lock:
                if len(self.pool) < 4:
                    self.pool.append(conn)
                else:
                    conn.close()
            try:
                data = json.loads(raw.decode("utf-8"))
            except ValueError:
                data = {}
            if response.status >= 400:
                raise TelegramError(response.status, data.get("description") or response.reason)
            return data
        raise RuntimeError("unreachable")

    def send(self, chat_id, text: str, buttons: list | None = None) -> None:
        parts = split_text(text)
        for i, part in enumerate(parts):
            params = {"chat_id": chat_id, "text": part}
            if buttons and i == len(parts) - 1:
                params["reply_markup"] = {"inline_keyboard": [buttons]}
            try:
                self.call("sendMessage", params, timeout=20)
            except Exception as exc:
                print(f"[jarvis] telegram send failed: {exc}")

    def notify(self, text: str) -> bool:
        cfg = self.load()
        if cfg.get("owner_id") and cfg.get("token"):
            self.send(cfg["owner_id"], text)
            return True
        return False

    def notify_reminder(self, event: dict) -> None:
        cfg = self.load()
        if cfg.get("mirror_reminders", True) is False or not cfg.get("owner_id"):
            return
        text = (event.get("text") or "").strip()
        if event.get("kind") == "timer":
            body = f"⏱ Timer finished: {text}" if text else "⏱ Your timer has finished."
        else:
            body = f"⏰ Reminder: {text}" if text else "⏰ Reminder."
        if event.get("missed"):
            body += " (this one came due while Jarvis was off)"
        threading.Thread(target=self.notify, args=(body,), daemon=True).start()

    # ---- Jarvis calls (loopback)
    def jarvis(self, path: str, payload: dict | None = None, raw: bytes | None = None, timeout: float = 180) -> dict:
        url = f"http://127.0.0.1:{self.port}{path}"
        if raw is not None:
            req = urllib.request.Request(url, data=raw, headers={"Content-Type": "application/octet-stream"}, method="POST")
        elif payload is not None:
            req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
        else:
            req = urllib.request.Request(url)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                return json.loads(exc.read().decode("utf-8"))
            except Exception:
                return {"error": f"Jarvis answered {exc.code}"}

    # ---- handling updates
    def handle_update(self, update: dict) -> None:
        cfg = self.load()
        if "callback_query" in update:
            self.handle_callback(update["callback_query"], cfg)
            return
        message = update.get("message") or update.get("edited_message")
        if not message or (message.get("chat") or {}).get("type") != "private":
            return
        sender = (message.get("from") or {}).get("id")
        chat_id = message["chat"]["id"]
        owner = cfg.get("owner_id")
        text = (message.get("text") or "").strip()
        if not owner:
            code = cfg.get("pair_code")
            candidate = re.sub(r"^/start\s*", "", text).strip()
            if code and candidate == code:
                cfg["owner_id"] = sender
                cfg.pop("pair_code", None)
                self.save(cfg)
                self.send(chat_id, "Paired. Good to meet you. Send me anything, or /help.")
            else:
                self.send(chat_id, "Hello. To connect me, open Jarvis on your PC (Settings > Daily > Telegram) and send me the 6-digit pairing code shown there.")
            return
        if sender != owner:
            print(f"[jarvis] telegram: ignored a message from user {sender}")
            return
        document = message.get("document")
        if document and str(document.get("mime_type") or "").startswith("image/"):
            self.handle_photo(chat_id, document, (message.get("caption") or "").strip(), cfg)
            return
        if document:
            self.handle_document(chat_id, document)
            return
        if message.get("photo"):
            self.handle_photo(chat_id, message["photo"][-1], (message.get("caption") or "").strip(), cfg)
            return
        if message.get("voice") or message.get("audio"):
            self.handle_voice(chat_id, message.get("voice") or message["audio"], cfg)
            return
        if not text:
            self.send(chat_id, "I can read text, voice notes, photos and files. I cannot read that kind of message.")
            return
        if text.lower().split("@")[0] == "/screenshot":
            self.chat(chat_id, "take a screenshot", cfg)
            return
        if text.lower().split("@")[0] == "/todo":
            self.chat(chat_id, "what's on my to-do list", cfg)
            return
        if text.lower().split("@")[0] == "/agenda":
            self.chat(chat_id, "what's on my calendar this week", cfg)
            return
        if text.lower().split("@")[0] == "/mail":
            self.chat(chat_id, "check my email", cfg)
            return
        if text.lower().split("@")[0] == "/look":
            self.chat(chat_id, "look at my screen", cfg)
            return
        if text.startswith("/"):
            self.handle_command(chat_id, text, cfg)
            return
        self.chat(chat_id, text, cfg)

    def handle_command(self, chat_id, text: str, cfg: dict) -> None:
        command, _, arg = text.partition(" ")
        command = command.split("@")[0].lower()
        arg = arg.strip().lower()
        if command in ("/start", "/help"):
            self.send(chat_id, HELP)
        elif command == "/new":
            self.history.clear()
            self.send(chat_id, "Fresh start.")
        elif command == "/docs":
            if arg in ("on", "off"):
                cfg["docs"] = arg == "on"
                self.save(cfg)
                self.send(chat_id, "I'll answer from your documents." if arg == "on" else "Back to normal answers.")
            else:
                self.send(chat_id, f"Documents are {'on' if cfg.get('docs') else 'off'}. Use /docs on or /docs off.")
        elif command == "/status":
            info = self.jarvis("/api/documents")
            count = len(info.get("items") or [])
            self.send(chat_id, f"Jarvis is running on your PC.\nDocuments: {count} saved, {'on' if cfg.get('docs') else 'off'}.\nReminders mirrored here: {'yes' if cfg.get('mirror_reminders', True) is not False else 'no'}.\nDaily briefing: {cfg.get('brief_time') or 'off'}.")
        else:
            self.send(chat_id, "I don't know that command. Try /help.")

    def typing_while(self, chat_id, done: threading.Event) -> None:
        """Telegram shows 'typing…' for about 5 seconds per request, so keep renewing it until the reply is ready."""
        while not done.is_set():
            try:
                self.call("sendChatAction", {"chat_id": chat_id, "action": "typing"}, timeout=10)
            except Exception:
                pass
            done.wait(4)

    def chat(self, chat_id, text: str, cfg: dict, images: list | None = None) -> None:
        started = time.time()
        done = threading.Event()
        threading.Thread(target=self.typing_while, args=(chat_id, done), daemon=True).start()
        try:
            with self.chat_lock:                               # one conversation turn at a time
                self.chat_turn(chat_id, text, cfg, started, images)
        finally:
            done.set()

    def chat_turn(self, chat_id, text: str, cfg: dict, started: float, images: list | None = None) -> None:
        # a photo is remembered in the conversation as a note; the picture itself only goes with this one request
        self.history.append({"role": "user", "content": ("[Photo sent] " + text).strip() if images else text})
        del self.history[:-12]
        messages = [*self.history[:-1], {"role": "user", "content": text}] if images else self.history
        payload = {"messages": messages, "source": "telegram", "use_documents": bool(cfg.get("docs")), "want_screenshot": cfg.get("screenshot_after", True) is not False, "stream": False}
        if images:
            payload["images"] = images
        data = self.jarvis("/api/chat", payload, timeout=420 if images else 180)
        print(f"[jarvis] telegram: answer ready after {time.time() - started:.1f}s")
        if data.get("error"):
            self.history.pop()
            self.send(chat_id, "Sorry, that did not work: " + str(data["error"])[:600])
            return
        reply = str(data.get("reply") or "I do not have a response for that.")
        self.history.append({"role": "assistant", "content": reply})
        if data.get("files"):
            reply += "\n\nFound on your PC:\n" + "\n".join(f"- {f.get('path') or f.get('name')}" for f in data["files"][:10])
        sources = data.get("sources")
        if sources and any(isinstance(s, dict) and s.get("url") for s in sources):      # web research: numbered links
            reply += "\n\nSources:\n" + "\n".join(f"[{s.get('n', i + 1)}] {s['name']}\n{s['url']}" for i, s in enumerate(sources) if s.get("url"))
        elif sources:
            reply +="\n\nFrom your documents: " + "; ".join(dict.fromkeys(f"{s['name']} ({s['where']})" for s in sources))
        action = data.get("action")
        if isinstance(action, dict) and action.get("approval_id"):
            token = action["approval_id"]
            reply += "\n\nI'd like to " + describe_action(action)
            self.send(chat_id, reply, [{"text": "✅ Approve", "callback_data": "ok:" + token}, {"text": "✖ Dismiss", "callback_data": "no:" + token}])
        else:
            self.send(chat_id, reply)
        self.send_screenshot(chat_id, data)
        if cfg.get("verify_screen") and data.get("screenshot") and not images and not data.get("screen_analysis"):
            self.verify_screen(chat_id, text, reply, data["screenshot"])

    def verify_screen(self, chat_id, task: str, reply: str, screenshot: str) -> None:
        """Have Jarvis look at the screenshot it just took and say whether the command worked."""
        try:
            with self.while_typing(chat_id):
                result = self.jarvis("/api/screen/check", {"task": task, "reply": reply, "image": screenshot}, timeout=420)
        except Exception as exc:
            self.send(chat_id, f"I could not check the screen: {exc}")
            return
        if result.get("error"):
            self.send(chat_id, "I could not check the screen: " + str(result["error"])[:500])
        elif result.get("reply"):
            self.send(chat_id, "🔍 " + str(result["reply"]))

    def handle_callback(self, query: dict, cfg: dict) -> None:
        sender = (query.get("from") or {}).get("id")
        message = query.get("message") or {}
        chat_id = (message.get("chat") or {}).get("id")
        try:
            self.call("answerCallbackQuery", {"callback_query_id": query.get("id")}, timeout=10)
        except Exception:
            pass
        if not cfg.get("owner_id") or sender != cfg["owner_id"]:
            return
        choice, _, token = str(query.get("data") or "").partition(":")
        if choice == "ok":
            result = self.jarvis("/api/action/approve", {"approval_id": token, "want_screenshot": cfg.get("screenshot_after", True) is not False})
            out = result.get("error") or result.get("output") or result.get("reply") or "Done."
            self.send(chat_id, ("✅ " if not result.get("error") else "⚠ ") + str(out)[:3500])
            self.send_screenshot(chat_id, result)
            if cfg.get("verify_screen") and result.get("screenshot") and not result.get("error"):
                self.verify_screen(chat_id, str(message.get("text") or "")[:300], str(out), result["screenshot"])
        elif choice == "no":
            self.jarvis("/api/action/dismiss", {"approval_id": token})
            self.send(chat_id, "Dismissed.")
        try:
            self.call("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message.get("message_id"), "reply_markup": {"inline_keyboard": []}}, timeout=10)
        except Exception:
            pass

    def fetch_file(self, file_id: str) -> bytes:
        info = self.call("getFile", {"file_id": file_id}, timeout=20)["result"]
        token = self.load()["token"]
        with urllib.request.urlopen(f"{API}/file/bot{token}/{info['file_path']}", timeout=60) as response:
            return response.read()

    def while_typing(self, chat_id):
        """Keep 'typing…' showing in the chat while something slow runs: `with self.while_typing(chat_id): ...`"""
        bot = self

        class Typing:
            def __enter__(self):
                self.done = threading.Event()
                threading.Thread(target=bot.typing_while, args=(chat_id, self.done), daemon=True).start()
            def __exit__(self, *exc):
                self.done.set()
        return Typing()

    def handle_voice(self, chat_id, voice: dict, cfg: dict) -> None:
        if (voice.get("file_size") or 0) > 20 * 1024 * 1024:
            self.send(chat_id, "Telegram only lets bots download files up to 20 MB.")
            return
        ext = "ogg" if voice.get("mime_type") in (None, "audio/ogg") else (str(voice.get("file_name") or "").rsplit(".", 1)[-1] or "mp3")
        try:
            with self.while_typing(chat_id):
                data = self.fetch_file(voice["file_id"])
                result = self.jarvis("/api/transcribe?ext=" + urllib.parse.quote(ext), raw=data, timeout=420)
        except Exception as exc:
            self.send(chat_id, f"I could not fetch that voice note: {exc}")
            return
        text = str(result.get("text") or "").strip()
        if result.get("error"):
            self.send(chat_id, "I could not understand that voice note: " + str(result["error"])[:600])
        elif not text:
            self.send(chat_id, "I could not make out any words in that voice note.")
        else:
            self.send(chat_id, "🎤 “" + text + "”")
            self.chat(chat_id, text, cfg)

    def handle_photo(self, chat_id, photo: dict, caption: str, cfg: dict) -> None:
        if (photo.get("file_size") or 0) > 20 * 1024 * 1024:
            self.send(chat_id, "Telegram only lets bots download files up to 20 MB.")
            return
        try:
            with self.while_typing(chat_id):
                data = self.fetch_file(photo["file_id"])
        except Exception as exc:
            self.send(chat_id, f"I could not fetch that photo: {exc}")
            return
        self.chat(chat_id, caption, cfg, images=[base64.b64encode(data).decode("ascii")])

    def handle_document(self, chat_id, document: dict) -> None:
        name = document.get("file_name") or "document"
        if (document.get("file_size") or 0) > 20 * 1024 * 1024:
            self.send(chat_id, "Telegram only lets bots download files up to 20 MB.")
            return
        try:
            data = self.fetch_file(document["file_id"])
            result = self.jarvis("/api/documents?name=" + urllib.parse.quote(name), raw=data, timeout=120)
        except Exception as exc:
            self.send(chat_id, f"I could not fetch that file: {exc}")
            return
        if result.get("error"):
            self.send(chat_id, f"I could not read {name}: {result['error']}")
        else:
            self.send(chat_id, f"Added {name} to your documents ({result['item']['chunks']} passages). Use /docs on to ask questions about them.")

    # ---- scheduled messages
    def scheduled(self, now: datetime | None = None) -> None:
        cfg = self.load()
        wanted = cfg.get("brief_time")
        if not wanted or not cfg.get("owner_id"):
            return
        now = now or datetime.now()
        today = now.strftime("%Y-%m-%d")
        hour, minute = map(int, wanted.split(":"))
        due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if self.last_brief != today and due <= now and (now - due).total_seconds() < 3 * 3600:
            self.last_brief = today
            data = self.jarvis("/api/briefing", timeout=60)
            if data.get("text"):
                self.notify(data["text"])

    # ---- the loop
    def poll_once(self, wait: int = 25) -> int:
        result = self.call("getUpdates", {"offset": self.offset, "timeout": wait, "allowed_updates": ["message", "callback_query"]}, timeout=wait + 10)
        updates = result.get("result") or []
        for update in updates:
            self.offset = max(self.offset, update["update_id"] + 1)
            if self.inline:
                self.guarded(update)
            else:
                threading.Thread(target=self.guarded, args=(update,), daemon=True).start()
        return len(updates)

    def guarded(self, update: dict) -> None:
        try:
            self.handle_update(update)
        except Exception as exc:
            print(f"[jarvis] telegram handler error: {exc}")

    def run(self) -> None:
        backoff = 3
        while not self.stop.is_set():
            cfg = self.load()
            if not cfg.get("token"):
                self.state, self.error = "off", ""
                self.stop.wait(2)
                continue
            if cfg["token"] != self.token_in_use:
                self.token_in_use, self.offset, self.history = cfg["token"], 0, []
                self.state, self.error = "connecting", ""
            try:
                if not self.username:
                    me = self.call("getMe", timeout=15)["result"]
                    self.username = me.get("username", "")
                self.state, self.error, backoff = "running", "", 3
                self.poll_once()
                self.scheduled()
            except TelegramError as exc:
                if exc.code == 401:
                    self.state, self.error, self.username = "error", "Telegram rejected this token. Create a new one with BotFather (/token) and enter it again.", ""
                    self.stop.wait(10)
                elif exc.code == 409:
                    self.state, self.error = "error", "Another program is already reading this bot's messages."
                    self.stop.wait(15)
                else:
                    self.state, self.error = "error", f"Telegram error {exc.code}: {exc}"
                    self.stop.wait(backoff); backoff = min(backoff * 2, 60)
            except Exception as exc:
                self.state, self.error = "error", explain_connection_error(exc)
                print(f"[jarvis] telegram: {self.error}")
                self.stop.wait(backoff); backoff = min(backoff * 2, 60)

    def ensure_running(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.stop.clear()
        self.thread = threading.Thread(target=self.run, daemon=True, name="telegram")
        self.thread.start()


def explain_connection_error(exc: Exception) -> str:
    """Say why Telegram could not be reached, with the likely cause."""
    reason = f"{type(exc).__name__}: {exc}"[:180]
    low = reason.lower()
    if "certificate" in low or "ssl" in low:
        hint = ("This network or a security program (school, company, antivirus, VPN) inspects secure connections. "
                "Run in the Jarvis folder: .venv\\Scripts\\python.exe -m pip install truststore   then restart Jarvis. Also check the computer's date and time.")
    elif "getaddrinfo" in low or "name or service" in low or "11001" in low or "resolution" in low:
        hint = "The name api.telegram.org cannot be looked up. This network may block Telegram, or its DNS is down."
    elif "timed out" in low or "10060" in low or "unreachable" in low:
        hint = "Something is blocking api.telegram.org: a firewall, an antivirus (allow .venv\\Scripts\\python.exe) or this network (work, school, hotel Wi-Fi)."
    elif "10061" in low or "refused" in low or "10054" in low or "reset" in low or "10013" in low:
        hint = "The connection was refused or cut: a firewall or antivirus is probably blocking Jarvis's Python from the internet."
    else:
        hint = "Check the internet connection, any firewall or antivirus, and whether this network allows Telegram."
    return f"Cannot reach Telegram ({reason}). {hint}"


class TelegramError(Exception):
    def __init__(self, code: int, description: str):
        super().__init__(description)
        self.code = code


BOT = TelegramBot()


def start() -> None:
    BOT.ensure_running()

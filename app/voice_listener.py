"""Always-on listening for Jarvis: say "Hey Jarvis", then what you want.

Everything stays on this PC: the microphone is read in memory only, speech is turned into text by the local Whisper
model (never a cloud service, because this hears everything said near the microphone), and nothing is recorded to disk.

Flow:  sleeping --"Hey Jarvis ..."--> awake --prompt--> thinking --answer spoken--> follow-up window --silence--> sleeping
Actions that need approval are asked out loud; say "yes" to approve or "no" to dismiss.
"""
from __future__ import annotations

import collections
import difflib
import json
import queue
import re
import threading
import time
import unicodedata
from pathlib import Path

try:
    import numpy as np
except ImportError:                         # reported as a clear message when listening is switched on
    np = None

RATE = 16000
FRAME = 480                                 # 30 ms of audio
SENSITIVITY = {"low": (0.020, 4.0), "normal": (0.012, 3.0), "high": (0.007, 2.2)}   # (smallest loudness that counts, times the room noise)
WAKE_WINDOW = 8.0                           # seconds to wait for the prompt after the wake word alone
FOLLOW_WINDOW = 6.0                         # seconds the follow-up window stays open after an answer
CONFIRM_WINDOW = 10.0
HALLUCINATIONS = {"thank you", "thanks", "thanks for watching", "you", "bye", "okay", "ok", "uh", "um", "hmm", "so", "yeah"}
YES = {"yes", "yeah", "yep", "yup", "approve", "approved", "confirm", "confirmed", "sure", "ok", "okay", "go ahead", "do it", "please do", "affirmative"}
NO = {"no", "nope", "cancel", "dismiss", "stop", "deny", "don't", "do not", "negative", "never mind", "nevermind"}
SLEEP_WORDS = re.compile(r"^(?:(?:ok(?:ay)? )?(?:stop listening|go to sleep|that'?s all|that is all|never ?mind|cancel that|thanks?(?: jarvis)?|thank you(?: jarvis)?|goodbye|bye(?: jarvis)?))[.! ]*$", re.I)


class ListenerError(RuntimeError):
    """A problem that makes listening impossible (for example the speech package is missing); shown in Settings."""


def plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ]", " ", text)).strip()


GREETINGS = {"hey", "hi", "ok", "okay", "hello", "yo", "hay", "eh", "a", "oh", "he"}
ALIASES = {"gervais", "jervis", "jarvas", "jarvice", "charvis", "yarvis", "garvis", "darvis", "jarves", "jarvus", "jervas", "javis"}   # how Whisper tends to hear it


def strip_wake(text: str) -> str | None:
    """None when the sentence does not start with the wake word; otherwise what was said after it ("" for the wake word alone)."""
    words = plain(text).split()
    for i, w in enumerate(words[:3]):
        if all(x in GREETINGS for x in words[:i]) and len(w) >= 4 and (w in ALIASES or difflib.SequenceMatcher(None, w, "jarvis").ratio() >= 0.74):
            return " ".join(words[i + 1:])
        if w not in GREETINGS:
            break
    return None


def sentence_is(text: str, choices: set) -> bool:
    t = plain(text)
    w = t.split()
    return bool(w) and (t in choices or w[0] in choices or any(t.startswith(c + " ") for c in choices if " " in c))


class Segmenter:
    """Cuts the microphone stream into utterances: starts after ~0.1 s of speech, ends after 0.8 s of quiet (or 12 s)."""

    def __init__(self, sensitivity: str = "normal"):
        self.floor, self.mult = SENSITIVITY.get(sensitivity, SENSITIVITY["normal"])
        self.noise = 0.004
        self.pre: collections.deque = collections.deque(maxlen=10)
        self.reset()

    def reset(self) -> None:
        self.buf: list = []
        self.active, self.voiced, self.silence = False, 0, 0

    def feed(self, frame):
        x = frame.astype(np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(x * x))) if len(x) else 0.0
        voiced = rms > max(self.floor, self.noise * self.mult)
        if not self.active:
            self.pre.append(x)
            if voiced:
                self.voiced += 1
            else:
                self.voiced = 0
                self.noise = min(0.05, 0.98 * self.noise + 0.02 * rms)
            if self.voiced >= 3:
                self.active, self.buf, self.silence = True, list(self.pre), 0
            return None
        self.buf.append(x)
        self.silence = 0 if voiced else self.silence + 1
        if self.silence >= 27 or len(self.buf) >= 400:
            audio = np.concatenate(self.buf)
            self.reset()
            return audio if len(audio) >= int(0.45 * RATE) else None
        return None


class MicSource:
    """The real microphone through sounddevice (16 kHz mono)."""

    def __init__(self, device=None):
        import sounddevice as sd
        self.q: queue.Queue = queue.Queue(maxsize=1500)

        def callback(indata, _frames, _time, _status):
            try:
                self.q.put_nowait(indata[:, 0].copy())
            except queue.Full:
                pass
        self.stream = sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=FRAME, device=device, callback=callback)
        self.stream.start()

    def read(self, timeout: float = 1.0):
        try:
            return self.q.get(timeout=timeout)
        except queue.Empty:
            return None

    def drain(self) -> None:
        try:
            while True:
                self.q.get_nowait()
        except queue.Empty:
            pass

    def close(self) -> None:
        try:
            self.stream.stop()
            self.stream.close()
        except Exception:
            pass


def load_device(config_path) -> str:
    try:
        return str(json.loads(Path(config_path).read_text(encoding="utf-8")).get("device") or "")
    except (OSError, ValueError, AttributeError):
        return ""


def list_microphones() -> list[str]:
    try:
        import sounddevice as sd
        names = []
        for d in sd.query_devices():
            if d.get("max_input_channels", 0) > 0 and d["name"] not in names:
                names.append(d["name"])
        return names
    except Exception:
        return []


class Listener:
    def __init__(self, config_path: Path, *, transcribe, chat, approve, speak, beep, open_source=MicSource):
        self.config_path = config_path
        self.transcribe, self.chat, self.approve, self.speak, self.beep, self.open_source = transcribe, chat, approve, speak, beep, open_source
        self.lock = threading.Lock()
        self.state, self.error, self.mode, self.deadline = "off", "", "sleep", 0.0
        self.events: list[dict] = []
        self.history: list[dict] = []
        self.last_active = 0.0
        self.pending: str | None = None
        self.stop_flag = threading.Event()
        self.thread: threading.Thread | None = None
        self.source = None
        self.microphones: list[str] = []
        self.mics_at = 0.0
        self.paused = False                         # set while dictation records, so the two do not both transcribe the same speech

    # ---- settings ----
    def load(self) -> dict:
        try:
            cfg = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cfg = {}
        return cfg if isinstance(cfg, dict) else {}

    def public(self) -> dict:
        cfg = self.load()
        if time.time() - self.mics_at > 30 and self.state in ("off", "error"):
            self.microphones, self.mics_at = list_microphones(), time.time()
        return {"enabled": cfg.get("enabled") is True, "state": self.state, "error": self.error, "sensitivity": cfg.get("sensitivity") if cfg.get("sensitivity") in SENSITIVITY else "normal",
                "speak": cfg.get("speak", True) is not False, "followup": cfg.get("followup", True) is not False, "device": cfg.get("device") or "",
                "microphones": self.microphones, "events": self.events[-10:]}

    def update(self, payload: dict) -> dict:
        cfg = self.load()
        if "sensitivity" in payload:
            if payload["sensitivity"] not in SENSITIVITY:
                raise ValueError("Sensitivity must be low, normal or high.")
            cfg["sensitivity"] = payload["sensitivity"]
        for key in ("speak", "followup"):
            if key in payload:
                cfg[key] = payload[key] is True
        if "device" in payload:
            cfg["device"] = str(payload["device"] or "")[:200]
        if "enabled" in payload:
            cfg["enabled"] = payload["enabled"] is True
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        restart = any(k in payload for k in ("enabled", "device", "sensitivity"))
        if restart:
            self.stop()
            if cfg.get("enabled"):
                self.start()
        return self.public()

    # ---- lifecycle ----
    def start(self) -> None:
        if not self.load().get("enabled") or (self.thread and self.thread.is_alive()):
            return
        if np is None:
            self.state, self.error = "error", "Listening needs the numpy package. Run install-jarvis.bat again."
            return
        self.stop_flag.clear()
        self.state, self.error, self.mode = "starting", "", "sleep"
        self.thread = threading.Thread(target=self.run, name="jarvis-listener", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_flag.set()
        if self.thread and self.thread.is_alive() and self.thread is not threading.current_thread():
            self.thread.join(timeout=5)
        self.thread = None
        if self.source:
            try:
                self.source.close()
            except Exception:
                pass
            self.source = None
        self.state, self.mode = "off", "sleep"

    def run(self) -> None:
        cfg = self.load()
        try:
            self.source = self.open_source(cfg.get("device") or None)
        except ImportError:
            self.state, self.error = "error", "Microphone support is not installed. Run install-jarvis.bat again."
            return
        except Exception as exc:
            self.state, self.error = "error", f"I could not open the microphone: {exc}. In Windows, check Settings > Privacy & security > Microphone, and allow desktop apps to use it."
            return
        segmenter = Segmenter(cfg.get("sensitivity") or "normal")
        self.state = "listening"
        print("[jarvis] listening for the wake word")
        while not self.stop_flag.is_set():
            frame = self.source.read(0.5)
            if self.paused:
                segmenter.reset()
                continue
            if self.mode != "sleep" and time.time() > self.deadline:
                self.to_sleep(announce=self.mode == "command")
                segmenter.reset()
            if frame is None:
                continue
            audio = segmenter.feed(frame)
            if audio is None:
                continue
            try:
                self.hear(audio)
            except ListenerError as exc:
                self.state, self.error = "error", str(exc)
                break
            except Exception as exc:
                print(f"[jarvis] listener: {type(exc).__name__}: {exc}")
                self.to_sleep()
            segmenter.reset()
        if self.state == "error" and self.source:
            self.source.close()
            self.source = None

    # ---- conversation ----
    def to_sleep(self, announce: bool = False) -> None:
        self.mode, self.pending = "sleep", None
        self.state = "listening" if self.source else "off"
        if announce:
            self.beep("sleep")

    def hear(self, audio) -> None:
        wake = self.mode == "sleep"
        if wake and len(audio) > 10 * RATE:
            return                                          # a long stretch of talk (TV, a conversation) is not a wake word
        self.state = "heard" if not wake else self.state
        text = (self.transcribe(audio, wake) or "").strip()
        if not text:
            self.state = "listening" if self.mode == "sleep" else "awake"
            return
        if wake:
            rest = strip_wake(text)
            if rest is None:
                return
            self.beep("wake")
            self.last_active = time.time()
            if len(rest.split()) >= 2:
                self.process(rest)
            else:
                self.mode, self.deadline, self.state = "command", time.time() + WAKE_WINDOW, "awake"
            return
        rest = strip_wake(text)
        if rest is not None and rest:
            text = rest
        if plain(text) in HALLUCINATIONS and len(text.split()) <= 3 and self.mode != "confirm":
            self.state = "awake"
            return
        if self.mode == "confirm":
            self.confirm(text)
        elif SLEEP_WORDS.match(text.strip()):
            self.say("Okay.")
            self.to_sleep()
        else:
            self.process(text)

    def say(self, text: str) -> None:
        cfg = self.load()
        if cfg.get("speak", True) is False:
            return
        self.state = "speaking"
        try:
            self.speak(text)
        finally:
            time.sleep(0.4)
            if self.source and hasattr(self.source, "drain"):
                self.source.drain()                         # drop whatever the microphone heard while Jarvis was talking

    def log(self, heard: str, reply: str) -> None:
        self.events.append({"time": time.strftime("%H:%M"), "heard": heard, "reply": reply})
        del self.events[:-30]

    def process(self, text: str) -> None:
        self.state = "thinking"
        if time.time() - self.last_active > 600:
            self.history = []
        self.last_active = time.time()
        self.history.append({"role": "user", "content": text})
        del self.history[:-12]
        data = self.chat(list(self.history))
        if data.get("error"):
            self.history.pop()
            reply = "Sorry, that did not work: " + str(data["error"])[:200]
        else:
            reply = str(data.get("reply") or "I do not have a response for that.")
            self.history.append({"role": "assistant", "content": reply})
        action = data.get("action")
        approval = action.get("approval_id") if isinstance(action, dict) else None
        self.log(text, reply)
        self.say(reply + (" Say yes to approve, or no to dismiss." if approval else ""))
        if approval:
            self.pending, self.mode, self.deadline, self.state = approval, "confirm", time.time() + CONFIRM_WINDOW, "awake"
        elif self.load().get("followup", True) is not False and not data.get("error"):
            self.mode, self.deadline, self.state = "followup", time.time() + FOLLOW_WINDOW, "awake"
        else:
            self.to_sleep()

    def confirm(self, text: str) -> None:
        token, self.pending = self.pending, None
        if sentence_is(text, YES) and not sentence_is(text, NO):
            self.state = "thinking"
            out = self.approve(token, True)
            self.log("yes", out)
            self.say(out)
        elif sentence_is(text, NO):
            self.approve(token, False)
            self.log("no", "Dismissed.")
            self.say("Dismissed.")
        else:
            self.say("I will leave that waiting. You can approve it in the Jarvis window.")
        if self.load().get("followup", True) is not False:
            self.mode, self.deadline, self.state = "followup", time.time() + FOLLOW_WINDOW, "awake"
        else:
            self.to_sleep()


LISTENER: Listener | None = None

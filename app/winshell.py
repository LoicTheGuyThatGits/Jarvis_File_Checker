"""One PowerShell that stays running, so reading the screen does not start a new PowerShell every time.

Starting powershell.exe and loading UI Automation or the OCR engine takes one to two seconds; asking a PowerShell that is
already running, with all that loaded, takes a fraction of that. Autopilot looks at the screen several times a step.

    shell = Shell()
    text = shell.run(script, timeout)   the script's output as text ("" when it failed or took too long), like screenmap.default_run
    shell.state()                       {"running", "calls", "broken", "last_ms"}
    shell.close()

The first call starts the helper and checks it answers. A call that takes too long kills it (the next call starts a fresh
one). It closes itself after `idle` seconds without use and is restarted after `max_calls` calls, so it never holds memory for
long. If it cannot be started or does not answer the first check, every call goes to `fallback` (a fresh PowerShell each time,
the old way) for the rest of the run.
"""
from __future__ import annotations

import base64
import queue
import subprocess
import threading
import time

# Runs inside the helper: read "<id> <base64 script>" lines, run each script, answer "@@JARVIS <id> <base64 output>".
LOOP = r'''
$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$reader = [Console]::In
while ($true) {
  $line = $reader.ReadLine()
  if ($line -eq $null -or $line -eq 'quit') { break }
  $parts = $line.Split(' ', 2)
  if ($parts.Count -lt 2) { continue }
  $out = ''
  try {
    $code = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($parts[1]))
    $out = (& ([ScriptBlock]::Create($code)) 2>$null | Out-String)
  } catch { $out = '' }
  [Console]::Out.WriteLine('@@JARVIS ' + $parts[0] + ' ' + [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes([string]$out)))
  [Console]::Out.Flush()
}
'''
MARK = b"@@JARVIS "


def powershell_command(exe: str = "powershell.exe") -> list[str]:
    encoded = base64.b64encode(LOOP.encode("utf-16-le")).decode("ascii")
    return [exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded]


class Shell:
    def __init__(self, command: list[str] | None = None, fallback=None, idle: float = 180, max_calls: int = 300, popen=subprocess.Popen, start_timeout: float = 15):
        self.command = command or powershell_command()
        self.fallback = fallback
        self.idle, self.max_calls, self.popen, self.start_timeout = idle, max_calls, popen, start_timeout
        self.lock = threading.Lock()
        self.proc = None
        self.lines: queue.Queue = queue.Queue()
        self.counter = 0
        self.calls = 0
        self.broken = False
        self.checked = False
        self.last_used = 0.0
        self.last_ms = None
        self._closer = None

    # ---------------- starting and stopping ----------------
    def _start(self) -> None:
        self.lines = queue.Queue()
        self.proc = self.popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.calls = 0
        proc, lines = self.proc, self.lines

        def read():
            try:
                for raw in iter(proc.stdout.readline, b""):
                    if raw.startswith(MARK):
                        lines.put(raw[len(MARK):].strip())
            except Exception:
                pass
            lines.put(None)                                   # the helper ended
        threading.Thread(target=read, daemon=True).start()
        if self._closer is None:
            self._closer = threading.Thread(target=self._close_when_idle, daemon=True)
            self._closer.start()

    def _kill(self) -> None:
        proc, self.proc = self.proc, None
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.stdin.write(b"quit\n")
                proc.stdin.flush()
        except Exception:
            pass
        try:
            proc.stdin.close()                                 # closed even when the pipe is already broken
        except Exception:
            pass
        try:
            proc.wait(timeout=1)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def close(self) -> None:
        with self.lock:
            self._kill()

    def _close_when_idle(self) -> None:
        while True:
            time.sleep(min(15.0, max(0.05, self.idle / 4)))
            if self.proc is not None and time.time() - self.last_used > self.idle and self.lock.acquire(blocking=False):
                try:
                    if self.proc is not None and time.time() - self.last_used > self.idle:
                        self._kill()
                finally:
                    self.lock.release()

    def state(self) -> dict:
        return {"running": self.proc is not None and self.proc.poll() is None, "calls": self.calls, "broken": self.broken, "last_ms": self.last_ms}

    # ---------------- asking ----------------
    def _ask(self, script: str, timeout: float) -> str | None:
        """The output, or None when the helper is gone or too slow (it is then killed)."""
        if self.proc is None or self.proc.poll() is not None or self.calls >= self.max_calls:
            self._kill()
            self._start()
        self.counter += 1
        ident = str(self.counter).encode()
        try:
            self.proc.stdin.write(ident + b" " + base64.b64encode(script.encode("utf-8")) + b"\n")
            self.proc.stdin.flush()
        except Exception:
            self._kill()
            return None
        self.calls += 1
        end = time.time() + timeout
        while True:
            left = end - time.time()
            if left <= 0:
                self._kill()
                return None
            try:
                item = self.lines.get(timeout=left)
            except queue.Empty:
                continue
            if item is None:
                self._kill()
                return None
            got, _, data = item.partition(b" ")
            if got != ident:
                continue                                       # an answer to an earlier call that timed out
            try:
                return base64.b64decode(data).decode("utf-8", errors="replace")
            except Exception:
                return ""

    def run(self, script: str, timeout: float = 12) -> str:
        with self.lock:
            if not self.broken:
                started = time.time()
                try:
                    if not self.checked:
                        self.checked = True
                        if (self._ask("'ok'", self.start_timeout) or "").strip() != "ok":
                            self.broken = True
                            self._kill()
                            print("[jarvis] the screen-reading helper did not start; using a fresh PowerShell each time")
                    if not self.broken:
                        out = self._ask(script, timeout)
                        self.last_used = time.time()
                        self.last_ms = round((time.time() - started) * 1000)
                        return out or ""
                except OSError:
                    self.broken = True
                    self._kill()
        return self.fallback(script, timeout) if self.fallback else ""

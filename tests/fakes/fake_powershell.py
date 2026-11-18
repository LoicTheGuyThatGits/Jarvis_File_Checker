"""Stands in for the screen-reading helper's PowerShell in tests: the same line protocol, a few made-up commands."""
import base64, os, sys, time
for line in sys.stdin.buffer:
    line = line.strip()
    if line == b"quit":
        break
    ident, _, data = line.partition(b" ")
    code = base64.b64decode(data).decode("utf-8")
    if code == "'ok'":
        out = "ok\r\n"
    elif code.startswith("SLEEP "):
        time.sleep(float(code[6:])); out = "slept"
    elif code == "PID":
        out = str(os.getpid())
    elif code == "EXIT":
        sys.exit(0)
    elif code.startswith("ECHO "):
        out = code[5:]
    else:
        out = ""
    sys.stdout.buffer.write(b"some other output\n@@JARVIS " + ident + b" " + base64.b64encode(out.encode("utf-8")) + b"\n")
    sys.stdout.buffer.flush()

"""Choose how Jarvis addresses you. Run by install-jarvis.bat; you can also run it any time: py set-address.py"""
import re
import sys
from pathlib import Path


def clean(value):
    text = re.sub(r"[^\w' .\-]", "", value or "", flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()[:24]


def main():
    name = clean(" ".join(sys.argv[1:])) if len(sys.argv) > 1 else clean(input("What should Jarvis call you? "))
    name = name or "sir"
    folder = Path(__file__).resolve().parent.parent / "data"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "address.txt").write_text(name + "\n", encoding="utf-8")
    print(f"Jarvis will call you: {name}")


if __name__ == "__main__":
    main()

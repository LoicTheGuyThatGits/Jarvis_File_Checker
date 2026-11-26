import os, shutil
os.environ.setdefault("JARVIS_NO_SETUP", "1")      # the first-run guide would cover the page in every other test
from pathlib import Path
SRC = Path("web")
def stage(tmp):
    """Copy the page into tmp/web the way a real install lays it out, and make tmp/data."""
    tmp = Path(tmp)
    shutil.copytree(SRC, tmp / "web", dirs_exist_ok=True)
    (tmp / "data").mkdir(exist_ok=True)

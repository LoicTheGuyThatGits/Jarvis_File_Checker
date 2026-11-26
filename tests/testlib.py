import os, shutil
os.environ.setdefault("JARVIS_NO_SETUP", "1")      # the first-run guide would cover the page in every other test
os.environ.setdefault("JARVIS_NO_UPDATE_CHECK", "1")   # nor should a look at GitHub put an update banner over it
from pathlib import Path
SRC = Path("web")
def stage(tmp):
    """Copy the page into tmp/web the way a real install lays it out, and make tmp/data."""
    tmp = Path(tmp)
    shutil.copytree(SRC, tmp / "web", dirs_exist_ok=True)
    (tmp / "data").mkdir(exist_ok=True)

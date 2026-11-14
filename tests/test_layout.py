import importlib.util, os, sys, tempfile, json
from pathlib import Path
os.environ["JARVIS_PORT"]="0" if False else os.environ.get("JARVIS_PORT","8791")
sys.path.insert(0,"app")
spec=importlib.util.spec_from_file_location("srv","app/server.py"); srv=importlib.util.module_from_spec(spec); spec.loader.exec_module(srv)
real=Path("app/server.py").resolve().parent.parent
assert srv.ROOT==real and (real/"web"/"index.html").is_file() and (real/"app"/"server.py").is_file()
# every file the server can serve exists in web/
for url,(rel,ct) in srv.STATIC_FILES.items(): assert srv.web_path(rel).is_file(), (url,rel)
html=(real/"web"/"index.html").read_text(encoding="utf-8")
import re
for ref in re.findall(r'(?:src|href)="(/[^"]+)"',html): assert ref in srv.STATIC_FILES, ref
# old flat files move into data/ once, never overwrite
tmp=Path(tempfile.mkdtemp()); srv.ROOT=tmp
(tmp/"settings.json").write_text('{"a":1}'); (tmp/"memory.json").write_text('[1]'); (tmp/"address.txt").write_text("ma'am\n")
(tmp/"documents").mkdir(); (tmp/"documents"/"index.json").write_text('{"items":[]}')
(tmp/"data").mkdir(); (tmp/"data"/"routines.json").write_text("new"); (tmp/"routines.json").write_text("old")
srv.migrate_legacy_data()
d=tmp/"data"
assert json.loads((d/"settings.json").read_text())=={"a":1} and (d/"memory.json").exists() and (d/"address.txt").read_text().startswith("ma'am") and (d/"documents"/"index.json").exists()
assert not (tmp/"settings.json").exists() and not (tmp/"documents").exists()
assert (d/"routines.json").read_text()=="new" and (tmp/"routines.json").read_text()=="old"      # existing data wins
assert srv.current_address()=="ma'am" and srv.load_settings()["a"]==1
# tray profile folder moves too
import jarvis_tray as t
(tmp/"app-profile").mkdir(); (tmp/"app-profile"/"x").write_text("1")
assert t.profile_dir(tmp)==tmp/"data"/"app-profile" and (tmp/"data"/"app-profile"/"x").exists() and not (tmp/"app-profile").exists()
assert t.ROOT==real and t.LOG==real/"data"/"jarvis.log" and t.ICON_ICO.is_file()
print("layout ok"); print("ALL OK")

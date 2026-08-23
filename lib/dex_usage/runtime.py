from __future__ import annotations
import json, os, tempfile, time
from datetime import datetime, timezone
from pathlib import Path
from . import PROVIDERS, SCHEMA
from . import claude, gemini, openai

def cache_dir(home:Path|None=None)->Path:
    configured=os.environ.get("DEX_USAGE_CACHE_DIR") or os.environ.get("XDG_CACHE_HOME")
    return (Path(configured).expanduser()/"dex-usage" if configured and not os.environ.get("DEX_USAGE_CACHE_DIR") else Path(configured).expanduser() if configured else (home or Path.home())/".cache/dex-usage")
def cache_path(home:Path|None=None)->Path:return cache_dir(home)/"usage.json"
def atomic_write(path:Path,value:dict)->None:
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700); fd,raw=tempfile.mkstemp(prefix=".usage.",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:json.dump(value,stream,separators=(",",":"));stream.write("\n")
        os.chmod(raw,0o600);os.replace(raw,path);os.chmod(path,0o600)
    finally:
        if os.path.exists(raw):os.unlink(raw)
def refresh(home:Path|None=None,timeout:float=5.0)->dict:
    home=home or Path.home(); data={"schema_version":SCHEMA,"captured_at":datetime.now(timezone.utc).isoformat().replace("+00:00","Z")}
    for name,adapter in {"claude":claude.collect,"openai":openai.collect,"gemini":gemini.collect}.items():
        try:data[name]=adapter(home,timeout)
        except Exception:data[name]={"alert_level":"unknown"}
    atomic_write(cache_path(home),data);return data
def read_cache(home:Path|None=None)->dict|None:
    path=cache_path(home)
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size>1024*1024:return None
        value=json.loads(path.read_text());return value if isinstance(value,dict) and value.get("schema_version")==SCHEMA else None
    except (OSError,json.JSONDecodeError):return None
def is_fresh(data:dict|None,max_age:int=300)->bool:
    if not data:return False
    try:return time.time()-datetime.fromisoformat(data["captured_at"].replace("Z","+00:00")).timestamp() <= max_age
    except (KeyError,TypeError,ValueError):return False
def render(data:dict|None)->str:
    labels={"claude":"C","openai":"O","gemini":"G"}; parts=[]
    for name in PROVIDERS:
        row=data.get(name,{}) if data else {}; value=row.get("remaining_percent"); parts.append(f"{labels[name]}:{value:g}%" if isinstance(value,(int,float)) else f"{labels[name]}:?")
    return "usage " + " ".join(parts)

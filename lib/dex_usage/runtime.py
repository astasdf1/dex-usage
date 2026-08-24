from __future__ import annotations
import json, os, tempfile, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from . import LEGACY_SCHEMAS, PROVIDERS, SCHEMA
from . import antigravity, claude, openai

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
def refresh(home:Path|None=None,timeout:float=10.0)->dict:
    home=home or Path.home(); previous=read_cache(home); data={"schema_version":SCHEMA,"captured_at":datetime.now(timezone.utc).isoformat().replace("+00:00","Z")}
    adapters={"claude":claude.collect,"openai":openai.collect,"antigravity":antigravity.collect}
    with ThreadPoolExecutor(max_workers=len(adapters),thread_name_prefix="dex-usage") as pool:
      futures={name:pool.submit(adapter,home,timeout) for name,adapter in adapters.items()}
      for name in adapters:
        try:collected=futures[name].result(timeout=timeout+.5)
        except Exception:collected={"alert_level":"unknown"}
        old=previous.get(name) if isinstance(previous,dict) else None
        if not _has_known_usage(collected) and _has_known_usage(old):
            collected=dict(old); collected["stale"] = True
        data[name]=collected
    atomic_write(cache_path(home),data);return data
def _has_known_usage(value:object)->bool:
    if not isinstance(value,dict):return False
    if isinstance(value.get("remaining_percent"),(int,float)):return True
    windows=value.get("windows")
    return isinstance(windows,dict) and any(isinstance(item,dict) and isinstance(item.get("remaining_percent"),(int,float)) for item in windows.values())
def read_cache(home:Path|None=None)->dict|None:
    path=cache_path(home)
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size>1024*1024:return None
        value=json.loads(path.read_text());return value if isinstance(value,dict) and value.get("schema_version") in ({SCHEMA}|LEGACY_SCHEMAS) else None
    except (OSError,json.JSONDecodeError):return None
def is_fresh(data:dict|None,max_age:int=300)->bool:
    if not data:return False
    try:return time.time()-datetime.fromisoformat(data["captured_at"].replace("Z","+00:00")).timestamp() <= max_age
    except (KeyError,TypeError,ValueError):return False
def _window_text(value:object)->str:
    if not isinstance(value,dict):return "?"
    if value.get("status")=="unsupported":return "unsupported"
    remaining=value.get("remaining_percent"); reset=value.get("reset_time")
    if not isinstance(remaining,(int,float)):return "?"
    return f"{remaining:g}%/{_reset_text(reset)}"

def _reset_text(value:object,now:float|None=None)->str:
    if not isinstance(value,str) or not value:return "?"
    try:
        seconds=max(0,datetime.fromisoformat(value.replace("Z","+00:00")).timestamp()-(time.time() if now is None else now))
    except ValueError:return "?"
    if seconds < 3600:return f"{max(1,int((seconds+59)//60))}m"
    if seconds < 86400:return f"{int(seconds//3600)}h"
    return f"{int(seconds//86400)}d"
def render(data:dict|None)->str:
    labels={"claude":"C","openai":"O","antigravity":"A"}; parts=[]
    for name in PROVIDERS:
        item=data.get(name,{}) if data else {}; windows=item.get("windows") if isinstance(item,dict) else None
        label=labels[name]+("~" if isinstance(item,dict) and item.get("stale") else "")
        if name == "antigravity":
            readiness = item.get("readiness") if isinstance(item,dict) else None
            if isinstance(windows,dict):parts.append(f"{label} 5h:{_window_text(windows.get('five_hour'))} 7d:{_window_text(windows.get('one_week'))}")
            else:parts.append(f"{label} {'ready' if readiness == 'ready' else '?'} quota:?")
        elif isinstance(windows,dict):
            parts.append(f"{label} 5h:{_window_text(windows.get('five_hour'))} 7d:{_window_text(windows.get('one_week'))}")
        else:
            legacy=item.get("remaining_percent") if isinstance(item,dict) else None
            suffix=f" legacy:{legacy:g}%" if isinstance(legacy,(int,float)) else ""
            parts.append(f"{label} 5h:? 7d:?{suffix}")
    return "usage " + " | ".join(parts)

def render_detailed(data:dict|None)->str:
    lines=[render(data)]
    for name in PROVIDERS:
        item=data.get(name,{}) if data else {}; windows=item.get("windows") if isinstance(item,dict) else None
        if name == "antigravity":
            readiness=item.get("readiness") if isinstance(item,dict) else None
            if isinstance(windows,dict):lines.append(f"antigravity: readiness={readiness or 'unknown'}; 5-hour={_window_text(windows.get('five_hour'))}; 1-week={_window_text(windows.get('one_week'))}; source=experimental TUI capture")
            else:lines.append(f"antigravity: readiness={readiness or 'unknown'}; quota=unknown (TUI capture unavailable)")
            continue
        if not isinstance(windows,dict):
            lines.append(f"{name}: 5-hour=unknown; 1-week=unknown (legacy cache has no named windows)")
            continue
        lines.append(f"{name}: 5-hour={_window_text(windows.get('five_hour'))}; 1-week={_window_text(windows.get('one_week'))}")
    return "\n".join(lines)

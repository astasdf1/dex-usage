from __future__ import annotations

import json, math, os, re, shlex, shutil, subprocess, tempfile, time, unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

QUOTA_TTL_SECONDS = 1800
CAPTURE_TIMEOUT_SECONDS = 10.0
ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")

def _collector_enabled(home: Path) -> bool:
    """The TUI collector is opt-in: setup records consent, env may disable it."""
    override=os.environ.get("DEX_USAGE_ANTIGRAVITY_TUI")
    if override is not None:return override.strip().lower() in {"1","true","yes","on"}
    path=Path(os.environ.get("CLAUDE_CONFIG_DIR",home/".claude"))/"dex-usage/statusline-config.json"
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size>16384:return False
        value=json.loads(path.read_text(encoding="utf-8"))
        return isinstance(value,dict) and value.get("antigravity_tui_quota") is True
    except (OSError,json.JSONDecodeError):return False

def _quota_path(home: Path) -> Path:
    configured=os.environ.get("DEX_USAGE_CACHE_DIR")
    return (Path(configured).expanduser() if configured else home/".cache/dex-usage")/"antigravity-quota.json"

def _read_quota(home: Path) -> dict|None:
    path=_quota_path(home)
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size>16384:return None
        value=json.loads(path.read_text(encoding="utf-8"));epoch=value.get("captured_epoch") if isinstance(value,dict) else None
        if value.get("schema")!="dex.antigravity.quota.v1" or not isinstance(epoch,(int,float)) or not math.isfinite(epoch):return None
        clean={}
        for name in ("five_hour","one_week"):
            item=value.get("windows",{}).get(name) if isinstance(value.get("windows"),dict) else None
            percent=item.get("remaining_percent") if isinstance(item,dict) else None
            if not isinstance(percent,(int,float)) or isinstance(percent,bool) or not math.isfinite(percent) or not 0<=percent<=100:return None
            clean_item={"remaining_percent":percent}
            reset=item.get("reset_time")
            if isinstance(reset,str) and len(reset)<=64:clean_item["reset_time"]=reset
            clean[name]=clean_item
        return {"schema":"dex.antigravity.quota.v1","captured_epoch":epoch,"windows":clean}
    except (OSError,json.JSONDecodeError):return None

def _normalized_quota(value:object)->dict:
    """Return the complete persistence allowlist or reject the value."""
    if not isinstance(value,dict):raise ValueError("invalid quota cache")
    epoch=value.get("captured_epoch")
    if value.get("schema")!="dex.antigravity.quota.v1" or isinstance(epoch,bool) or not isinstance(epoch,(int,float)) or not math.isfinite(epoch):raise ValueError("invalid quota cache")
    windows=value.get("windows")
    if not isinstance(windows,dict):raise ValueError("invalid quota cache")
    clean={}
    for name in ("five_hour","one_week"):
        item=windows.get(name);percent=item.get("remaining_percent") if isinstance(item,dict) else None
        if isinstance(percent,bool) or not isinstance(percent,(int,float)) or not math.isfinite(percent) or not 0<=percent<=100:raise ValueError("invalid quota cache")
        normalized={"remaining_percent":percent}
        reset=item.get("reset_time")
        if isinstance(reset,str) and len(reset)<=64:normalized["reset_time"]=reset
        clean[name]=normalized
    return {"schema":"dex.antigravity.quota.v1","captured_epoch":epoch,"windows":clean}

def _write_quota(home: Path,value: dict)->None:
    value=_normalized_quota(value)
    path=_quota_path(home);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,raw=tempfile.mkstemp(prefix=".antigravity-quota.",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:json.dump(value,stream,separators=(",",":"));stream.write("\n")
        os.chmod(raw,0o600);os.replace(raw,path);os.chmod(path,0o600)
    finally:
        if os.path.exists(raw):os.unlink(raw)

def _reset_from(text:str,now:datetime)->str|None:
    units={"m":60,"minute":60,"minutes":60,"min":60,"mins":60,"h":3600,"hour":3600,"hours":3600,"hr":3600,"hrs":3600,"d":86400,"day":86400,"days":86400}
    parts=re.findall(r"(?i)(\d+(?:\.\d+)?)\s*(minutes?|mins?|hours?|hrs?|days?|[mhd])\b",text)
    if not parts:return None
    seconds=sum(float(amount)*units[word.lower()] for amount,word in parts[:3])
    return (now+timedelta(seconds=seconds)).isoformat().replace("+00:00","Z")

def _clean_screen(raw:str)->str:
    text=unicodedata.normalize("NFKC",ANSI.sub("",raw).replace("\r","\n"));lines=[];previous=None
    for line in (re.sub(r"\s+"," ",re.sub(r"[\x00-\x08\x0b-\x1f\x7f]","",row).strip()) for row in text.splitlines()):
        if line and line!=previous:lines.append(line);previous=line
    return "\n".join(lines)

def parse_quota_screen(raw:str,now:datetime|None=None)->dict|None:
    """Extract only explicitly named English 5-hour/weekly windows; fail closed otherwise."""
    now=now or datetime.now(timezone.utc);lines=_clean_screen(raw).splitlines();windows={}
    labels={"five_hour":re.compile(r"(?i)\b(?:5|five)[ -]?(?:hour|hr)s?\b"),"one_week":re.compile(r"(?i)\b(?:7[ -]?(?:day|d)|one[ -]?week|weekly|week)\b")}
    for index,line in enumerate(lines):
        for name,label in labels.items():
            if name in windows or not label.search(line):continue
            candidate=line
            percent_pattern=r"(?i)(\d{1,3}(?:\.\d+)?)\s*%\s*(remaining|left|available|used|consumed)"
            for following in lines[index+1:index+4]:
                if any(other.search(following) for other in labels.values()):break
                candidate += " " + following
                if re.search(percent_pattern,candidate):break
            match=re.search(r"(?i)(\d{1,3}(?:\.\d+)?)\s*%\s*(remaining|left|available)",candidate)
            if match:remaining=float(match.group(1))
            else:
                match=re.search(r"(?i)(\d{1,3}(?:\.\d+)?)\s*%\s*(used|consumed)",candidate)
                if match:remaining=100.0-float(match.group(1))
                elif re.search(r"(?i)\bquota\s+available\b",candidate):remaining=100.0
                else:continue
            if not 0<=remaining<=100:continue
            item={"remaining_percent":int(remaining) if remaining.is_integer() else remaining}
            reset_match=re.search(r"(?i)(?:reset(?:s|ting)?|refresh(?:es|ing)?)(?:\s+in|\s*:)?\s*([^|,;]+)",candidate)
            if reset_match:
                reset=_reset_from(reset_match.group(1),now)
                if reset:item["reset_time"]=reset
            windows[name]=item
    return windows if set(windows)=={"five_hour","one_week"} else None

def _tmux_run(command:list[str],args:list[str],env:dict[str,str],deadline:float,check:bool=False)->subprocess.CompletedProcess[str]:
    remaining=deadline-time.monotonic()
    if remaining<=0:raise TimeoutError("quota collector deadline exceeded")
    return subprocess.run(command+args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          env=env,text=True,timeout=max(.2,remaining),check=check)

def _capture_screen(command:list[str],env:dict[str,str],deadline:float)->str:
    result=_tmux_run(command,["capture-pane","-p","-J","-S","-240","-t","quota:0.0"],env,deadline)
    return result.stdout if result.returncode==0 else ""

def _wait_until_ready(command:list[str],env:dict[str,str],deadline:float)->None:
    """Wait through agy's isolated-directory trust prompt and initial paint."""
    trust_accepted=False
    while time.monotonic()<deadline:
        screen=_capture_screen(command,env,deadline)
        if not trust_accepted and "Do you trust the contents of this project?" in screen:
            _tmux_run(command,["send-keys","-t","quota:0.0","Enter"],env,deadline,check=True)
            trust_accepted=True
        elif "? for shortcuts" in screen:
            return
        time.sleep(min(.2,max(.02,deadline-time.monotonic())))
    raise TimeoutError("Antigravity TUI did not become ready")

def _open_slash_command(command:list[str],env:dict[str,str],deadline:float,slash_command:str)->bool:
    # C-u clears only the editor input. Unlike a blind Escape/Enter sequence it
    # cannot accept an unrelated modal choice. Wait for the exact command-menu
    # entry before selecting it; `/quota` is retained only as a compatibility
    # fallback for agy builds that expose that spelling.
    _tmux_run(command,["send-keys","-t","quota:0.0","C-u"],env,deadline,check=True)
    _tmux_run(command,["send-keys","-t","quota:0.0","-l",slash_command],env,deadline,check=True)
    suggestion_deadline=min(deadline,time.monotonic()+1.5)
    while time.monotonic()<suggestion_deadline:
        lines=_clean_screen(_capture_screen(command,env,deadline)).splitlines()
        if any(line.startswith(f"> {slash_command} ") for line in lines):
            _tmux_run(command,["send-keys","-t","quota:0.0","Enter"],env,deadline,check=True)
            return True
        time.sleep(min(.1,max(.02,suggestion_deadline-time.monotonic())))
    return False

def _capture_quota(executable:str,timeout:float)->dict:
    tmux=shutil.which("tmux")
    if not tmux:raise RuntimeError("tmux_missing")
    deadline=time.monotonic()+min(max(timeout,1.0),CAPTURE_TIMEOUT_SECONDS)
    with tempfile.TemporaryDirectory(prefix="dex-agy-quota-") as raw:
        base=Path(raw);socket=base/"tmux.sock";command=[tmux,"-S",str(socket)];env=os.environ.copy();env["TERM"]="xterm-256color"
        try:
            _tmux_run(command,["new-session","-d","-x","140","-y","50","-s","quota","-c",str(base),shlex.quote(executable)],env,deadline,check=True)
            _wait_until_ready(command,env,deadline)
            for slash_command in ("/usage","/quota"):
                if not _open_slash_command(command,env,deadline,slash_command):continue
                command_deadline=min(deadline,time.monotonic()+max(.5,(deadline-time.monotonic())/2))
                while time.monotonic()<command_deadline:
                    time.sleep(min(.35,max(.05,command_deadline-time.monotonic())))
                    parsed=parse_quota_screen(_capture_screen(command,env,deadline))
                    if parsed:return parsed
            raise TimeoutError("quota screen not parseable before deadline")
        finally:
            try:subprocess.run(command+["kill-server"],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=1,check=False)
            except (OSError,subprocess.SubprocessError):pass

def collect(home:Path,timeout:float):
    started=time.monotonic();budget=min(max(timeout,1.0),CAPTURE_TIMEOUT_SECONDS)
    executable=shutil.which("agy");result={"alert_level":"unknown","readiness":"unknown","quota_status":"unavailable"}
    if not executable:result["readiness"]="not_installed";return result
    def remaining_budget(cap:float)->float:
        remaining=budget-(time.monotonic()-started)
        if remaining<=0:raise TimeoutError("collector deadline exceeded")
        return min(cap,remaining)
    try:
        help_result=subprocess.run([executable,"--help"],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=remaining_budget(2),check=False)
        flags=set(re.findall(r"(?<![\w-])--[a-z][a-z-]*",help_result.stdout+help_result.stderr))
        if help_result.returncode or not {"--print","--print-timeout","--sandbox"}.issubset(flags):result["readiness"]="unsupported_cli";return result
        auth=subprocess.run([executable,"models"],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=remaining_budget(5),check=False)
        auth_text=(auth.stdout+"\n"+auth.stderr).lower();logged_out=any(token in auth_text for token in ("not logged in","unauthenticated","login required","please log in","authentication required"))
        result["readiness"]="ready" if auth.returncode==0 and not logged_out else "not_authenticated"
        if result["readiness"]!="ready":return result
    except (OSError,TimeoutError,subprocess.TimeoutExpired):result["readiness"]="probe_failed";return result
    if not _collector_enabled(home):result["quota_status"]="disabled";return result
    cached=_read_quota(home);age=time.time()-float(cached.get("captured_epoch",0)) if cached else float("inf")
    def apply_windows(status:str,windows:dict,stale:bool=False):
        result.update({"quota_status":status,"windows":windows,"remaining_percent":min(item["remaining_percent"] for item in windows.values())})
        if stale:result["stale"]=True
    if cached and 0<=age<=QUOTA_TTL_SECONDS:apply_windows("available",cached["windows"]);return result
    try:
        windows=_capture_quota(executable,remaining_budget(10))
        cached={"schema":"dex.antigravity.quota.v1","captured_epoch":time.time(),"windows":windows};_write_quota(home,cached);result.update({"quota_status":"available","windows":windows})
        result["remaining_percent"]=min(item["remaining_percent"] for item in windows.values())
    except (OSError,RuntimeError,TimeoutError,ValueError,subprocess.SubprocessError):
        if cached:apply_windows("stale",cached["windows"],True)
    return result

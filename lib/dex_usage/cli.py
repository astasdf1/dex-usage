from __future__ import annotations
import argparse,json,os,shlex,shutil,stat,subprocess,sys,tempfile,time
from pathlib import Path
from . import VERSION
from .runtime import cache_path,is_fresh,read_cache,refresh,render,render_detailed

MARKER="DEX_USAGE_STATUSLINE_V1"
def settings_path(home:Path)->Path:return Path(os.environ.get("CLAUDE_CONFIG_DIR",home/".claude"))/"settings.json"
def managed_dir(home:Path)->Path:return settings_path(home).parent/"dex-usage"
def managed_runner(home:Path)->Path:return managed_dir(home)/"statusline.py"
def state_path(home:Path)->Path:return managed_dir(home)/"statusline-config.json"
def sync_managed_runner(plugin_root:Path,home:Path)->bool:
    """Refresh only our durable runner after a marketplace update.

    This deliberately does not rewrite settings.json or saved user status-line
    composition. It is safe to run on every SessionStart.
    """
    path=settings_path(home); settings=load_object(path) if path.exists() else {}; status=settings.get("statusLine")
    command=status.get("command","") if isinstance(status,dict) else ""
    target=managed_runner(home); source=plugin_root/"scripts/statusline.py"
    if MARKER not in command or str(target) not in command:return False
    if target.is_symlink() or target.parent.is_symlink() or source.is_symlink() or not source.is_file():return False
    target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,raw=tempfile.mkstemp(prefix=".statusline.",dir=target.parent)
    try:
        with os.fdopen(fd,"wb") as stream:stream.write(source.read_bytes())
        os.chmod(raw,0o700);os.replace(raw,target)
    finally:
        if os.path.exists(raw):os.unlink(raw)
    return True
def load_object(path:Path)->dict:
    if not path.exists():return {}
    try:value=json.loads(path.read_text());return value if isinstance(value,dict) else {}
    except (OSError,json.JSONDecodeError):raise RuntimeError(f"invalid JSON: {path}")
def setup(plugin_root:Path,home:Path,dry_run:bool=False)->int:
    path=settings_path(home)
    if path.is_symlink() or path.parent.is_symlink():
        print(f"CONFLICT: refusing symbolic-link settings path: {path}; no changes made",file=sys.stderr);return 2
    settings=load_object(path);existing=settings.get("statusLine");runner=managed_runner(home);command=f"python3 {shlex.quote(str(runner))}"
    if isinstance(existing,dict) and MARKER in str(existing.get("command","")):
        saved=state_path(home) if str(runner) in str(existing.get("command","")) else cache_path(home).parent/"statusline-config.json"
        compose=load_object(saved).get("previous") if saved.exists() else None
        if compose is not None and not isinstance(compose,dict):compose=None
    else:compose=None
    if compose is None and existing is not None and not (isinstance(existing,dict) and MARKER in str(existing.get("command",""))):
        if not isinstance(existing,dict) or existing.get("type")!="command" or not isinstance(existing.get("command"),str):
            print("CONFLICT: existing statusLine is not a composable command; no changes made",file=sys.stderr);return 2
        compose=existing
    target=state_path(home)
    if target.is_symlink() or target.parent.is_symlink():
        print(f"CONFLICT: refusing symbolic-link statusline state path: {target}; no changes made",file=sys.stderr);return 2
    status=dict(existing) if isinstance(existing,dict) and MARKER in str(existing.get("command","")) else dict(compose or {})
    status.update({"type":"command","command":f"{command} # {MARKER}"})
    status.setdefault("refreshInterval",30)
    print(json.dumps({"settings":str(path),"statusLine":status,"composesExisting":bool(compose)},ensure_ascii=False))
    if dry_run:return 0
    target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    source_runner=plugin_root/"scripts/statusline.py"
    try:
        source_fd=os.open(source_runner,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
        if not stat.S_ISREG(os.fstat(source_fd).st_mode):
            os.close(source_fd);print(f"CONFLICT: bundled status-line runner is not a regular file: {source_runner}",file=sys.stderr);return 2
    except OSError as exc:
        print(f"CONFLICT: bundled status-line runner is missing or unsafe: {source_runner}: {exc}",file=sys.stderr);return 2
    runner_fd,runner_raw=tempfile.mkstemp(prefix=".statusline.",dir=target.parent)
    try:
        with os.fdopen(runner_fd,"wb") as stream:
            with os.fdopen(source_fd,"rb") as source:shutil.copyfileobj(source,stream)
        os.chmod(runner_raw,0o700);os.replace(runner_raw,runner)
    finally:
        if os.path.exists(runner_raw):os.unlink(runner_raw)
    state_fd,state_raw=tempfile.mkstemp(prefix=".statusline-config.",dir=target.parent)
    try:
        with os.fdopen(state_fd,"w",encoding="utf-8") as stream:stream.write(json.dumps({"previous":compose})+"\n")
        os.chmod(state_raw,0o600);os.replace(state_raw,target)
    finally:
        if os.path.exists(state_raw):os.unlink(state_raw)
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        backup=path.with_name(f"{path.name}.dex-usage.{time.time_ns()}.bak")
        with backup.open("xb") as stream:stream.write(path.read_bytes())
        os.chmod(backup,0o600)
    settings["statusLine"]=status
    fd,raw=tempfile.mkstemp(prefix=".settings.dex-usage.",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:stream.write(json.dumps(settings,ensure_ascii=False,indent=2)+"\n")
        os.chmod(raw,0o600);os.replace(raw,path)
    finally:
        if os.path.exists(raw):os.unlink(raw)
    return 0
def uninstall(home:Path,dry_run:bool=False)->int:
    path=settings_path(home);settings=load_object(path);existing=settings.get("statusLine")
    owned=managed_dir(home);owned_files=(owned/"statusline.py",owned/"statusline-config.json")
    if owned.is_symlink() or any(child.is_symlink() for child in owned_files):
        print(f"CONFLICT: refusing symbolic-link managed path: {owned}; no changes made",file=sys.stderr);return 2
    if not (isinstance(existing,dict) and MARKER in str(existing.get("command","")) and str(managed_runner(home)) in str(existing.get("command",""))):
        if state_path(home).exists():
            print("CONFLICT: statusLine changed after dex-usage setup; no changes made",file=sys.stderr);return 2
        print("not configured; no changes made");return 0
    state=load_object(state_path(home)) if state_path(home).exists() else {};previous=state.get("previous")
    if previous is not None and not isinstance(previous,dict):
        print("CONFLICT: invalid saved statusLine; no changes made",file=sys.stderr);return 2
    if owned.exists() and any(child.name not in {"statusline.py","statusline-config.json"} for child in owned.iterdir()):
        print(f"CONFLICT: unexpected file in managed directory: {owned}; no changes made",file=sys.stderr);return 2
    print(json.dumps({"settings":str(path),"restoreStatusLine":previous},ensure_ascii=False))
    if dry_run:return 0
    if previous is None:settings.pop("statusLine",None)
    else:settings["statusLine"]=previous
    fd,raw=tempfile.mkstemp(prefix=".settings.dex-usage.",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:stream.write(json.dumps(settings,ensure_ascii=False,indent=2)+"\n")
        os.chmod(raw,0o600);os.replace(raw,path)
    finally:
        if os.path.exists(raw):os.unlink(raw)
    for child in owned_files:
        child.unlink(missing_ok=True)
    try:owned.rmdir()
    except FileNotFoundError:pass
    return 0
def doctor(home:Path)->int:
    data=read_cache(home);path=settings_path(home);settings=load_object(path) if path.exists() else {};status=settings.get("statusLine");command=status.get("command","") if isinstance(status,dict) else "";managed=MARKER in command
    healthy=not managed or (str(managed_runner(home)) in command and managed_runner(home).is_file() and not managed_runner(home).is_symlink() and state_path(home).is_file() and not state_path(home).is_symlink())
    print(f"dex-usage {VERSION}");print(f"python: {sys.version.split()[0]}");print(f"cache: {cache_path(home)} ({'fresh' if is_fresh(data) else 'missing/stale'})");print(f"statusline: {'healthy' if managed and healthy else 'not configured' if not managed else 'STALE/BROKEN: rerun setup'}");print(render_detailed(data));return 0 if healthy else 2
def statusline(home:Path)->int:
    raw=sys.stdin.buffer.read(2*1024*1024);prefix=""
    config=state_path(home)
    try:
        previous=json.loads(config.read_text()).get("previous")
        if isinstance(previous,dict) and isinstance(previous.get("command"),str):
            result=subprocess.run(previous["command"],input=raw,shell=True,capture_output=True,timeout=1,check=False);prefix=result.stdout.decode(errors="replace").strip()
    except (OSError,ValueError,subprocess.TimeoutExpired,json.JSONDecodeError):pass
    own=render(read_cache(home));print(f"{prefix} | {own}" if prefix else own);return 0
def main(plugin_root:Path,argv=None)->int:
    parser=argparse.ArgumentParser(prog="dex-usage");parser.add_argument("--home",type=Path,default=Path.home());parser.add_argument("--version",action="version",version=VERSION);sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("usage-all");sub.add_parser("refresh");sub.add_parser("doctor");p=sub.add_parser("setup");p.add_argument("--dry-run",action="store_true");u=sub.add_parser("uninstall");u.add_argument("--dry-run",action="store_true");sub.add_parser("statusline");sub.add_parser("hook-startup");sub.add_parser("hook-warm")
    args=parser.parse_args(argv);home=args.home.expanduser()
    if args.command=="refresh":print(json.dumps(refresh(home),ensure_ascii=False,indent=2));return 0
    if args.command=="usage-all":
        data=read_cache(home)
        if not data:data=refresh(home)
        print(json.dumps(data,ensure_ascii=False,indent=2));return 0
    if args.command=="hook-warm":
        if not is_fresh(read_cache(home)):refresh(home)
        return 0
    if args.command=="hook-startup":
        # SessionStart itself has an 8-second hard stop. Keeping each provider
        # below that budget preserves the previous atomically-written cache if
        # Claude Code terminates this refresh at the hook deadline.
        sync_managed_runner(plugin_root,home)
        refresh(home,timeout=2.0)
        return 0
    if args.command=="statusline":return statusline(home)
    if args.command=="setup":return setup(plugin_root,home,args.dry_run)
    if args.command=="uninstall":return uninstall(home,args.dry_run)
    return doctor(home)

#!/usr/bin/env python3
"""Durable cache-only DEX status-line runner installed into user config."""
from __future__ import annotations
import json, os, subprocess, sys, time
from datetime import datetime
from pathlib import Path

SCHEMAS = {"dex.provider_usage_cache.v1", "dex.provider_usage_cache.v2", "dex.provider_usage_cache.v3"}

def config_dir(home: Path) -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR", home / ".claude")) / "dex-usage"

def cache_path(home: Path) -> Path:
    explicit = os.environ.get("DEX_USAGE_CACHE_DIR")
    if explicit:
        return Path(explicit).expanduser() / "usage.json"
    xdg = os.environ.get("XDG_CACHE_HOME")
    return (Path(xdg).expanduser() if xdg else home / ".cache") / "dex-usage/usage.json"

def render(home: Path) -> str:
    try:
        path = cache_path(home)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
            raise ValueError
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or data.get("schema_version") not in SCHEMAS:
            raise ValueError
    except (OSError, ValueError, json.JSONDecodeError):
        data = {}
    def reset_text(value):
        if not isinstance(value, str) or not value: return "?"
        try: seconds=max(0,datetime.fromisoformat(value.replace("Z","+00:00")).timestamp()-time.time())
        except ValueError: return "?"
        if seconds < 3600: return f"{max(1,int((seconds+59)//60))}m"
        if seconds < 86400: return f"{int(seconds//3600)}h"
        return f"{int(seconds//86400)}d"
    def display(value):
        if not isinstance(value, dict): return "?"
        if value.get("status") == "unsupported": return "unsupported"
        remaining, reset = value.get("remaining_percent"), value.get("reset_time")
        if not isinstance(remaining, (int, float)): return "?"
        return f"{remaining:g}%/{reset_text(reset)}"
    parts = []
    for name, label in (("claude", "C"), ("openai", "O"), ("antigravity", "A")):
        item = data.get(name, {}) if isinstance(data.get(name), dict) else {}
        label = label + ("~" if item.get("stale") else "")
        windows = item.get("windows")
        if name == "antigravity":
            if isinstance(windows, dict):
                parts.append(f"{label} 5h:{display(windows.get('five_hour'))} 7d:{display(windows.get('one_week'))}")
            else:
                parts.append(f"{label} {'ready' if item.get('readiness') == 'ready' else '?'} quota:?")
        elif isinstance(windows, dict):
            parts.append(f"{label} 5h:{display(windows.get('five_hour'))} 7d:{display(windows.get('one_week'))}")
        else:
            value = item.get("remaining_percent")
            legacy = f" legacy:{value:g}%" if isinstance(value, (int, float)) else ""
            parts.append(f"{label} 5h:? 7d:?{legacy}")
    return "usage " + " | ".join(parts)

def main() -> int:
    home = Path.home()
    raw = sys.stdin.buffer.read(2 * 1024 * 1024)
    prefix = ""
    try:
        state = json.loads((config_dir(home) / "statusline-config.json").read_text())
        previous = state.get("previous")
        if isinstance(previous, dict) and isinstance(previous.get("command"), str):
            result = subprocess.run(previous["command"], input=raw, shell=True, capture_output=True, timeout=1, check=False)
            prefix = result.stdout.decode(errors="replace").strip()
    except (OSError, ValueError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    own = render(home)
    print(f"{prefix} | {own}" if prefix else own)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

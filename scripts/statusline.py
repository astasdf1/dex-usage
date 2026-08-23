#!/usr/bin/env python3
"""Durable cache-only DEX status-line runner installed into user config."""
from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path

SCHEMA = "dex.provider_usage_cache.v1"

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
        if not isinstance(data, dict) or data.get("schema_version") != SCHEMA:
            raise ValueError
    except (OSError, ValueError, json.JSONDecodeError):
        data = {}
    parts = []
    for name, label in (("claude", "C"), ("openai", "O"), ("gemini", "G")):
        value = data.get(name, {}).get("remaining_percent") if isinstance(data.get(name), dict) else None
        parts.append(f"{label}:{value:g}%" if isinstance(value, (int, float)) else f"{label}:?")
    return "usage " + " ".join(parts)

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

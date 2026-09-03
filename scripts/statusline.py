#!/usr/bin/env python3
"""Durable cache-only DEX status-line runner installed into user config."""
from __future__ import annotations
import json, os, subprocess, sys, time
from datetime import datetime
from pathlib import Path

SCHEMAS = {"dex.provider_usage_cache.v1", "dex.provider_usage_cache.v2", "dex.provider_usage_cache.v3"}
CONTEXT_TAIL = 1024 * 1024
CONTEXT_FIELDS = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
DEFAULT_CONTEXT_LIMIT = 200_000
LONG_CONTEXT_LIMIT = 1_000_000

def compact(value: int) -> str:
    if value >= 1_000_000: return f"{value / 1_000_000:g}M"
    if value >= 1000: return f"{value // 1000}k"
    return str(value)

def context_tokens(transcript: Path) -> int | None:
    """Tokens carried by the newest request recorded in this session's transcript.

    Only the tail is read so a long session does not slow the status line down,
    and sidechain rows are skipped because a subagent's context is not this
    session's.
    """
    try:
        if transcript.is_symlink() or not transcript.is_file(): return None
        size = transcript.stat().st_size
        with transcript.open("rb") as stream:
            if size > CONTEXT_TAIL: stream.seek(size - CONTEXT_TAIL)
            lines = stream.read(CONTEXT_TAIL).split(b"\n")
    except OSError:
        return None
    if size > CONTEXT_TAIL: lines = lines[1:]
    for line in reversed(lines):
        if not line.strip(): continue
        try: row = json.loads(line)
        except (ValueError, UnicodeDecodeError): continue
        if not isinstance(row, dict) or row.get("isSidechain"): continue
        message = row.get("message")
        usage = message.get("usage") if isinstance(message, dict) else None
        if not isinstance(usage, dict): continue
        total = sum(value for value in (usage.get(name) for name in CONTEXT_FIELDS)
                    if isinstance(value, int) and not isinstance(value, bool) and value > 0)
        if total > 0: return total
    return None

def context_limit(payload: dict, used: int) -> int:
    override = os.environ.get("DEX_USAGE_CONTEXT_LIMIT", "")
    if override.isdigit() and int(override) > 0: return int(override)
    model = payload.get("model")
    identifier = model.get("id") if isinstance(model, dict) else None
    limit = LONG_CONTEXT_LIMIT if isinstance(identifier, str) and "1m" in identifier.lower() else DEFAULT_CONTEXT_LIMIT
    # A model id that omits the long-context marker must still report honestly
    # rather than show more than 100% of a limit that was guessed too low.
    if limit < LONG_CONTEXT_LIMIT and (used > limit or payload.get("exceeds_200k_tokens")):
        limit = LONG_CONTEXT_LIMIT
    return limit

def context_segment(payload: object) -> str | None:
    """Render context consumption, or nothing when the transcript is unreadable."""
    if not isinstance(payload, dict): return None
    transcript = payload.get("transcript_path")
    if not isinstance(transcript, str) or not transcript: return None
    try: used = context_tokens(Path(transcript).expanduser())
    except (OSError, ValueError): return None
    if used is None: return None
    limit = context_limit(payload, used)
    return f"ctx {compact(used)}/{compact(limit)} ({round(100 * used / limit)}%)"


def config_dir(home: Path) -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR", home / ".claude")) / "dex-usage"

def cache_path(home: Path) -> Path:
    explicit = os.environ.get("DEX_USAGE_CACHE_DIR")
    if explicit:
        return Path(explicit).expanduser() / "usage.json"
    xdg = os.environ.get("XDG_CACHE_HOME")
    return (Path(xdg).expanduser() if xdg else home / ".cache") / "dex-usage/usage.json"

def render(home: Path, payload: object = None) -> str:
    try:
        path = cache_path(home)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
            raise ValueError
        data = json.loads(path.read_text(encoding="utf-8"))
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
    context = context_segment(payload)
    if context: parts.append(context)
    return "usage " + " | ".join(parts)

def main() -> int:
    home = Path.home()
    raw = sys.stdin.buffer.read(2 * 1024 * 1024)
    prefix = ""
    try:
        state = json.loads((config_dir(home) / "statusline-config.json").read_text(encoding="utf-8"))
        previous = state.get("previous")
        if isinstance(previous, dict) and isinstance(previous.get("command"), str):
            result = subprocess.run(previous["command"], input=raw, shell=True, capture_output=True, timeout=1, check=False)
            prefix = result.stdout.decode(errors="replace").strip()
    except (OSError, ValueError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    try: payload = json.loads(raw.decode("utf-8", errors="replace"))
    except (ValueError, json.JSONDecodeError): payload = None
    own = render(home, payload)
    print(f"{prefix} | {own}" if prefix else own)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

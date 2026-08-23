from __future__ import annotations
import getpass, time
from pathlib import Path
from .common import command_available, config_home, keychain_json, read_json, request_json, row
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
def collect(home: Path, timeout: float):
    if not command_available("claude"): return row(None)
    creds = keychain_json("Claude Code-credentials", getpass.getuser()) or keychain_json("Claude Code-credentials") or read_json(config_home(home, "CLAUDE_CONFIG_DIR", ".claude") / ".credentials.json")
    nested = creds.get("claudeAiOauth", creds) if isinstance(creds, dict) else {}
    access = nested.get("accessToken") or nested.get("access_token"); refresh = nested.get("refreshToken") or nested.get("refresh_token"); expires = nested.get("expiresAt") or nested.get("expires_at")
    if not isinstance(access, str) or not access: return row(None)
    if isinstance(expires, (int, float)) and (expires if expires > 10_000_000_000 else expires * 1000) <= time.time() * 1000 + 60_000:
        if not isinstance(refresh, str) or not refresh: return row(None)
        token = request_json("https://platform.claude.com/v1/oauth/token", headers={}, timeout=timeout, approved_hosts=frozenset({"platform.claude.com"}), form={"grant_type":"refresh_token","refresh_token":refresh,"client_id":CLIENT_ID})
        access = token.get("access_token") if token else None
        if not isinstance(access, str) or not access: return row(None)
    payload = request_json("https://api.anthropic.com/api/oauth/usage", headers={"Authorization":f"Bearer {access}","anthropic-beta":"oauth-2025-04-20"}, timeout=timeout, approved_hosts=frozenset({"api.anthropic.com"}))
    candidates = [row(100-float(bucket["utilization"]), bucket.get("resets_at")) for key in ("five_hour","seven_day") if payload and isinstance((bucket:=payload.get(key)), dict) and isinstance(bucket.get("utilization"),(int,float))]
    return min(candidates, key=lambda x:x["remaining_percent"]) if candidates else row(None)

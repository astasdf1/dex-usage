from __future__ import annotations

import json, math, os, shutil, subprocess, urllib.error, urllib.parse, urllib.request
from pathlib import Path
from typing import Any

def read_json(path: Path) -> dict[str, Any] | None:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024: return None
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, UnicodeError, json.JSONDecodeError): return None

def keychain_json(service: str, account: str | None = None) -> dict[str, Any] | None:
    security = Path("/usr/bin/security")
    if not security.is_file(): return None
    args = [str(security), "find-generic-password", "-s", service]
    if account: args += ["-a", account]
    args.append("-w")
    try:
        result = subprocess.run(args, text=True, capture_output=True, timeout=2, check=False)
        if result.returncode or len(result.stdout) > 1024 * 1024: return None
        value = json.loads(result.stdout)
        return value if isinstance(value, dict) else None
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError): return None

class ApprovedHostRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, approved_hosts: frozenset[str]) -> None:
        super().__init__(); self.approved_hosts = approved_hosts
    def redirect_request(self, req: urllib.request.Request, fp: Any, code: int, msg: str, headers: Any, newurl: str):
        destination = urllib.parse.urlsplit(newurl)
        if destination.scheme != "https" or destination.hostname not in self.approved_hosts:
            raise urllib.error.HTTPError(req.full_url, code, "refusing credentialed redirect outside approved HTTPS hosts", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def request_json(url: str, *, headers: dict[str, str], timeout: float, approved_hosts: frozenset[str], form=None, body=None):
    origin = urllib.parse.urlsplit(url)
    if origin.scheme != "https" or origin.hostname not in approved_hosts: return None
    data = None; request_headers = dict(headers)
    if form is not None:
        data = urllib.parse.urlencode(form).encode("ascii"); request_headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body, separators=(",", ":")).encode(); request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=request_headers, method="POST" if data else "GET")
    try:
        with urllib.request.build_opener(ApprovedHostRedirectHandler(approved_hosts)).open(request, timeout=timeout) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024: return None
        value = json.loads(raw); return value if isinstance(value, dict) else None
    except (OSError, ValueError, urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError): return None

def row(remaining: object, reset: object = None) -> dict[str, Any]:
    if isinstance(remaining, bool) or not isinstance(remaining, (int, float)) or not math.isfinite(remaining):
        return {"alert_level": "unknown"}
    remaining = min(100.0, max(0.0, float(remaining)))
    result = {"alert_level": "exhausted" if remaining <= 0 else "critical" if remaining <= 10 else "warning" if remaining <= 30 else "ok", "remaining_percent": int(remaining) if remaining.is_integer() else remaining}
    if isinstance(reset, str) and len(reset) <= 120: result["reset_time"] = reset
    return result

def config_home(home: Path, env_name: str, suffix: str) -> Path:
    configured = os.environ.get(env_name)
    return Path(configured).expanduser() if configured else home / suffix

def command_available(name: str) -> bool:
    """Require the provider CLI as well as credentials for a known result."""
    return shutil.which(name) is not None

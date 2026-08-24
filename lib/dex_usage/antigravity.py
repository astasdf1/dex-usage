from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


def collect(home: Path, timeout: float):
    """Report agy readiness only; never substitute another product's quota."""
    executable = shutil.which("agy")
    result = {"alert_level": "unknown", "readiness": "unknown", "quota_status": "unavailable"}
    if not executable:
        result["readiness"] = "not_installed"
        return result
    try:
        help_result = subprocess.run([executable, "--help"], stdin=subprocess.DEVNULL,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True, timeout=timeout, check=False)
        flags = set(re.findall(r"(?<![\w-])--[a-z][a-z-]*", help_result.stdout + help_result.stderr))
        if help_result.returncode or not {"--print", "--print-timeout", "--sandbox"}.issubset(flags):
            result["readiness"] = "unsupported_cli"
            return result
        auth = subprocess.run([executable, "models"], stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, timeout=timeout, check=False)
        text = (auth.stdout + "\n" + auth.stderr).lower()
        logged_out = any(token in text for token in ("not logged in", "unauthenticated", "login required", "please log in", "authentication required"))
        result["readiness"] = "ready" if auth.returncode == 0 and not logged_out else "not_authenticated"
    except (OSError, subprocess.TimeoutExpired):
        result["readiness"] = "probe_failed"
    return result

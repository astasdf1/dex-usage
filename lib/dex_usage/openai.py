from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from .common import command_available, config_home, keychain_json, read_json, request_json, row
def collect(home: Path, timeout: float):
    if not command_available("codex"): return row(None)
    config=config_home(home,"CODEX_HOME",".codex"); auth=read_json(config/"auth.json") or keychain_json("Codex Auth",str(config)); tokens=auth.get("tokens",{}) if isinstance(auth,dict) else {}
    access=tokens.get("access_token") if isinstance(tokens,dict) else None; account=(tokens.get("account_id") if isinstance(tokens,dict) else None) or (auth.get("account_id") if auth else None)
    if not isinstance(access,str) or not access:return row(None)
    headers={"Authorization":f"Bearer {access}","Accept":"application/json","User-Agent":"codex-cli"}
    if isinstance(account,str) and account:headers["ChatGPT-Account-Id"]=account
    payload=request_json("https://chatgpt.com/backend-api/wham/usage",headers=headers,timeout=timeout,approved_hosts=frozenset({"chatgpt.com"})); root=payload.get("rate_limit_status",payload) if payload else {}; limits=root.get("rate_limit",root) if isinstance(root,dict) else {}; candidates=[]
    for key in ("primary_window","secondary_window"):
        value=limits.get(key) if isinstance(limits,dict) else None
        if not isinstance(value,dict):continue
        remaining=value.get("remaining_percent",value.get("remainingPercent")); used=value.get("used_percent",value.get("usedPercent"))
        if remaining is None and isinstance(used,(int,float)):remaining=100-used
        reset=value.get("reset_at",value.get("resets_at",value.get("resetsAt")))
        if isinstance(reset,(int,float)):reset=datetime.fromtimestamp(reset,timezone.utc).isoformat().replace("+00:00","Z")
        item=row(remaining,reset)
        if "remaining_percent" in item:candidates.append(item)
    return min(candidates,key=lambda x:x["remaining_percent"]) if candidates else row(None)

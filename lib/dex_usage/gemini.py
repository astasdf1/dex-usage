from __future__ import annotations
import os,time
from pathlib import Path
from .common import command_available,read_json,request_json,row
def collect(home:Path,timeout:float):
    if not command_available("gemini"):return row(None)
    candidates=[]; cli_home=os.environ.get("GEMINI_CLI_HOME")
    if cli_home:candidates += [Path(cli_home)/".gemini/oauth_creds.json",Path(cli_home)/"oauth_creds.json"]
    candidates.append(home/".gemini/oauth_creds.json"); creds=next((v for p in candidates if (v:=read_json(p))),None); access=creds.get("access_token") if creds else None; expires=creds.get("expiry_date") if creds else None
    if not isinstance(access,str) or not access or (isinstance(expires,(int,float)) and expires <= time.time()*1000+300_000):return row(None)
    project=os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT_ID"); headers={"Authorization":f"Bearer {access}"}; host=frozenset({"cloudcode-pa.googleapis.com"})
    details=request_json("https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist",headers=headers,timeout=timeout,approved_hosts=host,body={"cloudaicompanionProject":project,"metadata":{"ideType":"IDE_UNSPECIFIED","platform":"PLATFORM_UNSPECIFIED","pluginType":"GEMINI","duetProject":project}}); project=project or (details.get("cloudaicompanionProject") if details else None)
    if not isinstance(project,str) or not project:return row(None)
    quota=request_json("https://cloudcode-pa.googleapis.com/v1internal:retrieveUserQuota",headers=headers,timeout=timeout,approved_hosts=host,body={"project":project}); known=[]
    for bucket in quota.get("buckets",[]) if quota else []:
        if isinstance(bucket,dict) and bucket.get("tokenType") in (None,"","REQUESTS") and isinstance(bucket.get("remainingFraction"),(int,float)):known.append(row(bucket["remainingFraction"]*100,bucket.get("resetTime")))
    return min(known,key=lambda x:x["remaining_percent"]) if known else row(None)

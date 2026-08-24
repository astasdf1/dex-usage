#!/usr/bin/env python3
"""Create a teammate-safe tar.gz containing only the plugin folder."""
from __future__ import annotations
import argparse,gzip,os,tarfile,tempfile
from pathlib import Path
from release_inventory import open_regular_nofollow,validate_source_tree

EXECUTABLES={Path("bin/dex-usage"),Path("scripts/dex_usage.py")}

def main()->int:
    parser=argparse.ArgumentParser();parser.add_argument("--out",type=Path,default=Path("dist/dex-usage-1.4.0.tar.gz"));args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];out=args.out.expanduser().absolute();out.parent.mkdir(parents=True,exist_ok=True)
    try:out.relative_to(root)
    except ValueError:pass
    else:parser.error("--out must be outside the plugin source directory")
    with tempfile.NamedTemporaryFile(dir=out.parent,delete=False) as tmp:raw=Path(tmp.name)
    try:
        with raw.open("wb") as output, gzip.GzipFile(filename="",mode="wb",fileobj=output,mtime=0) as compressed:
            with tarfile.open(fileobj=compressed,mode="w") as archive:
                try:inventory=validate_source_tree(root)
                except ValueError as exc:parser.error(str(exc))
                for path,relative in inventory:
                    fd=open_regular_nofollow(path)
                    with os.fdopen(fd,"rb") as stream:
                        info=archive.gettarinfo(str(path),arcname=str(Path("dex-usage")/relative));info.mode=0o755 if relative in EXECUTABLES else 0o644;info.uid=info.gid=0;info.uname=info.gname="";info.mtime=0;archive.addfile(info,stream)
        raw.replace(out)
    finally:
        raw.unlink(missing_ok=True)
    print(out);return 0
if __name__=="__main__":raise SystemExit(main())

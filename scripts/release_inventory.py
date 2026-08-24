"""Strict release inventory shared by folder and tar installers."""
from __future__ import annotations
import os, stat
from pathlib import Path

RELEASE_FILES = (
    ".claude-plugin/marketplace.json",
    ".claude-plugin/plugin.json",
    "NOTICE.md",
    "README.md",
    "bin/dex-usage",
    "hooks/hooks.json",
    "lib/dex_usage/__init__.py",
    "lib/dex_usage/claude.py",
    "lib/dex_usage/cli.py",
    "lib/dex_usage/common.py",
    "lib/dex_usage/antigravity.py",
    "lib/dex_usage/openai.py",
    "lib/dex_usage/runtime.py",
    "scripts/dex_usage.py",
    "scripts/statusline.py",
    "skills/doctor/SKILL.md",
    "skills/refresh/SKILL.md",
    "skills/setup/SKILL.md",
    "skills/usage-all/SKILL.md",
)

def validate_source_tree(root: Path) -> list[tuple[Path, Path]]:
    """Reject every link/special node, then return the exact regular-file allowlist."""
    for directory, names, files in os.walk(root, topdown=True, followlinks=False):
        for name in names + files:
            path = Path(directory) / name
            mode = os.lstat(path).st_mode
            if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise ValueError(f"source contains link or special file: {path.relative_to(root)}")
    inventory = []
    for relative in RELEASE_FILES:
        path = root / relative
        try:
            mode = os.lstat(path).st_mode
        except OSError as exc:
            raise ValueError(f"missing release file: {relative}") from exc
        if not stat.S_ISREG(mode):
            raise ValueError(f"release file is not a regular file: {relative}")
        inventory.append((path, Path(relative)))
    return inventory

def open_regular_nofollow(path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise ValueError(f"release file changed type while opening: {path}")
    return fd

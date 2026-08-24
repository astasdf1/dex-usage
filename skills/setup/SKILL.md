---
name: setup
description: Safely opt in to the DEX usage status line while preserving an existing command status line.
disable-model-invocation: true
allowed-tools: Bash
---

First run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/dex_usage.py" setup --dry-run` and show the proposed settings change. Only after the user explicitly confirms, run the same command without `--dry-run`. The setup composes an existing command status line and enables the local Antigravity TUI quota collector only when an installed `agy` passes a non-interactive login/readiness probe. Missing or logged-out `agy` leaves it disabled without failing setup. Setup never installs `agy` or logs in, and it refuses unsupported/conflicting status-line configurations; never replace one silently. A previously explicit persisted disable remains disabled; `DEX_USAGE_ANTIGRAVITY_TUI=0` also disables TUI collection.

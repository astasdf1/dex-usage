---
name: setup
description: Safely opt in to the DEX usage status line while preserving an existing command status line.
disable-model-invocation: true
allowed-tools: Bash
---

First run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/dex_usage.py" setup --dry-run` and show the proposed settings change. Only after the user explicitly confirms, run the same command without `--dry-run`. The setup composes an existing command status line and refuses unsupported/conflicting configurations; never replace one silently.

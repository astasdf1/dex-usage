---
name: refresh
description: Refresh the DEX provider usage cache now.
disable-model-invocation: true
allowed-tools: Bash
---

Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/dex_usage.py" refresh`. Report the cache result without exposing credential files or tokens.

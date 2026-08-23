---
name: doctor
description: Diagnose the local DEX usage plugin, providers, cache, and status line.
disable-model-invocation: true
allowed-tools: Bash
---

Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/dex_usage.py" doctor`. Verify that the reported status line is healthy and uses the durable user-owned runner rather than a marketplace cache path. Treat missing or logged-out providers as disabled/unknown, not errors. If removal is requested, preview and then run the CLI `uninstall` command. Also recommend Claude Code's built-in `/doctor` for plugin-schema diagnostics.

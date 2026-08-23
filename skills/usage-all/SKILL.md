---
name: usage-all
description: Show cached or freshly collected Claude, Codex, and Gemini usage.
disable-model-invocation: true
allowed-tools: Bash
---

Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/dex_usage.py" usage-all` and present the result as a compact table. Explain that `?`/`unknown` means the corresponding CLI is absent, logged out, or its usage endpoint is unavailable; it is not a plugin failure.

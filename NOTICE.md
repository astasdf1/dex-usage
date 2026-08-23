# Provenance and update ownership

- Collector origin: DEX-2 `scripts/flowdesk_usage_snapshot`, copied as an owned standalone payload on 2026-08-21. That collector adapts behavioral logic and schema conventions from FlowDesk at immutable revision `d0cb3b69c332fad01fec4db4486ebda176f5a07b`; no FlowDesk code is bundled.
- Current owner and updater: DEX-2 maintainers. No runtime linkage to the origin path exists.
- Provider endpoints and credential layouts are compatibility adapters for the corresponding local CLIs; provider absence/login failure is represented as `unknown`.
- Claude Code plugin layout, `${CLAUDE_PLUGIN_ROOT}`, async hooks, skills, marketplace, and status-line input follow official Anthropic Claude Code documentation.
- The plugin contains no FlowDesk, Node, npm, or MCP dependency.

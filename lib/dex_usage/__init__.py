"""DEX-owned standalone provider-usage collector and cache runtime.

Update ownership: DEX-2 maintainers. The adapters were copied from the verified
scripts/flowdesk_usage_snapshot payload and are intentionally owned here so the
plugin never depends on FlowDesk or files outside its installation directory.
"""

VERSION = "1.1.1"
SCHEMA = "dex.provider_usage_cache.v2"
LEGACY_SCHEMAS = frozenset({"dex.provider_usage_cache.v1"})
PROVIDERS = ("claude", "openai", "gemini")

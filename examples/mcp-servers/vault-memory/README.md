# vault-memory MCP server

A stdio MCP server that exposes semantic + recency search over
an Obsidian-style vault to any MCP-aware agent (Claude Code,
Codex, Cursor, Hermes).

## Tools

| Tool | Purpose |
|------|---------|
| `mem_search` | Keyword search across vault notes. |
| `mem_semantic_search` | Vector search via ChromaDB. |
| `mem_get` | Read a specific note by path. |
| `mem_recent` | Most-recently-modified notes. |
| `mem_list_memory` | Enumerate the auto-memory directory. |

All output passes through `privacy_filter.py.safe_redact()`,
which strips Dutch IBAN/BSN/KvK/BTW patterns and a configurable
list of names.

## Wiring

Add to your agent's MCP config (Claude Code example):

```bash
claude mcp add vault-memory \
  --scope user \
  -- python3 <path-to-this-dir>/mem_mcp_server.py
```

For Codex, see `~/.codex/config.toml`. For Hermes, `~/.hermes/config.yaml`.

## Adapting

- Set `VAULT_ROOT` env var to point at your vault.
- Extend `privacy_filter.py` with patterns relevant to your jurisdiction
  (e.g. SSN for US, NIN for UK).
- The semantic search backend assumes ChromaDB at `<vault>/.chroma`;
  swap for any vector store with minimal changes.

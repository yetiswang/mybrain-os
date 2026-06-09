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

For Codex CLI, add to `~/.codex/config.toml`:

```toml
[mcp_servers.vault-memory]
command = "python3"
args = ["<path-to-this-dir>/mem_mcp_server.py"]
```

For Hermes, add to `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  vault-memory:
    command: python3
    args:
      - <path-to-this-dir>/mem_mcp_server.py
```

## Adapting

- Set `VAULT_ROOT` env var to point at your vault.
- Extend `privacy_filter.py` with patterns relevant to your jurisdiction
  (e.g. SSN for US, NIN for UK).
- The semantic search backend shells out to a `vault-search` CLI
  (any binary that takes a query and returns JSON hits will do).
  In the original author's setup this is a thin ChromaDB wrapper;
  point `VAULT_SEARCH_BIN` at your own implementation.

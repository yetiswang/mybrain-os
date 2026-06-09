# vault-kg MCP server (skeleton)

The vault-kg server exposes a nightly-built property graph of
your vault to any MCP-aware agent. Full implementation is
project-specific and not included in this repo.

## What it does (architecture)

1. A launchd job runs nightly (e.g. 03:30) and walks the vault,
   extracting entities (people, projects, concepts, papers) and
   relations (mentions, citations, attendances).
2. The graph is written to a SQLite property-graph schema.
3. A stdio MCP server exposes query tools to agents:
   - `kg_neighbors(entity)`: adjacent entities + relation types
   - `kg_bridges(a, b)`: paths between two entities
   - `kg_capability_gap(theme)`: entities present in one cluster
     but missing in another
   - `kg_cooling_decisions(window)`: decisions whose follow-up
     chains have gone quiet

## Why it's a skeleton

The graph schema, extraction rules, and query archetypes are
heavily project-specific. Generalising would dilute what makes
it useful. If you want to build your own, the architecture above
is the entire design. The value is in tuning queries to your
own questions, not in a generic graph library.

See `docs/02-multiagent-model.md` in this repo for how vault-kg
fits into the cross-agent MCP layer.

# The knowledge wiki

Andrej Karpathy wrote that LLMs are best understood as compilers: the human writes source (notes, papers, observations), and the model compiles it into something faster to query. The original is at https://x.com/karpathy/status/1882534525400137823. That idea is the foundation of how I structure my research knowledge.

My domain spans self-driving labs, advanced multimodal characterisation, and AI for materials science. The literature is large and grows weekly. No model holds all of it in working memory across sessions. So I maintain a compiled wiki. The agent builds it. I read it. Neither crosses into the other's layer.

This document describes the architecture. The actual wiki content is confidential and lives in my private vault. What ships in this repo is `examples/commands/paper-ingest.md`, the ritual that builds the wiki.

## The three-layer architecture

```
┌─────────────────────────────────────────────────────┐
│  Layer 1: Human-owned sources (raw/)                │
│  Zotero library (PDFs + metadata) · Clippings ·     │
│  Web fetches · Vault notes                          │
├─────────────────────────────────────────────────────┤
│  Layer 2: Extraction pipeline                       │
│  zotero_extract.py → JSON per paper                 │
│  /paper-ingest ritual → agent processes each paper  │
├─────────────────────────────────────────────────────┤
│  Layer 3: LLM-owned compiled wiki (wiki/)           │
│  Concepts · Papers · Groups · Index · Log           │
│  Agent writes freely; human reads via Obsidian      │
└─────────────────────────────────────────────────────┘
```

**Layer 1** is my reading activity. Papers live in Zotero (local SQLite plus PDF storage). Clippings come from web articles, conference notes, or ad-hoc sessions. I add items to Zotero; I never edit the wiki directly.

**Layer 2** is the extraction pipeline. A Python script reads Zotero's SQLite database, extracts metadata and full text from PDFs via pymupdf, and writes one JSON file per paper. The `/paper-ingest` ritual processes each JSON: it compiles a paper note, identifies or creates concept notes, creates or updates group notes (one per research group or PI), and maintains bidirectional wikilinks. For batches larger than five papers, it dispatches parallel subagents.

**Layer 3** is the compiled wiki the agent owns. It lives in the vault under `wiki/` and is browsable as a knowledge graph in Obsidian. The agent rewrites any file here freely on every ingest pass. The human reads it, follows wikilinks, and queries it with `/domain-ask`. Neither opens the other's layer in edit mode.

## The four entity types

```markdown
| Entity | Filename pattern | What's in it |
|--------|------------------|--------------|
| **Paper** | `YYYY-FirstAuthor-ShortTitle.md` | TLDR, claims, methods, relevance, data gaps, wikilinks. |
| **Concept** | `Descriptive-Name.md` | Definition, state of the art, key papers, counterarguments, strategic relevance. |
| **Group** | `PI-Institution.md` | Focus, publications, infrastructure, competitive/collaborative notes. |
| **Radar entry** | `YYYY-MM-radar.md` | Periodic strategic digest, signals scored by impact. |
```

Each has YAML frontmatter for programmatic filtering: maturity level, confidence score, relationship tag, source count. That makes the wiki queryable beyond full-text search once it grows past a few dozen entries.

## The ownership rule

The clearest rule: I curate what to read; the agent compiles what it means. I never open a wiki file in edit mode. The agent never touches the Zotero library. Both layers stay independent: the agent restructures the wiki freely on every ingest; I read or ignore anything in it. No merge conflicts, no version negotiation.

## Why this scales

The extraction pipeline turns PDFs into JSON. A paper that costs 10,000 tokens as a raw PDF might fit in 1,500 as extracted metadata plus key passages. That compounds across several hundred papers.

A state file tracks which Zotero keys have been processed. The next ingest only touches new papers, so cost stays proportional to new reading, not total library size.

Because every paper note links to its concepts and groups (and vice versa), the wiki grows more useful as it grows larger. `/domain-ask` Q&A traverses it: a question about a concept finds the relevant papers, which point to the groups working on it, which point back to other concepts. A flat list of summaries cannot do that.

## What is and is not in this repo

The actual wiki content is confidential. My compiled domain knowledge carries strategic intelligence about research groups, funding landscapes, and competitive positioning that I do not publish. What ships here is the pattern: `examples/commands/paper-ingest.md` (the ritual), the extraction pipeline (referenced, not included), and this document (the architecture). Build your own wiki on top.

## Adapting

Four steps. Define your domains (2-4 tags that scope your strategic interest, used in every entity's frontmatter). Connect your sources (point the extraction script at your Zotero library, or rewrite the loader for a different reference manager). Adjust the schemas (frontmatter fields, relevance categories, entity sections). Set strategic context: the "Relevance to my work" section in each paper note is what lifts the wiki above a bibliography. Without it, you have summaries. With it, you have a position.

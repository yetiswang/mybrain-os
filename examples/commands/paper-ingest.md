---
description: Ingest papers from Zotero and Clippings into the domain knowledge wiki
---

# /paper-ingest

Ingest research papers into the domain knowledge wiki (`10-Research/wiki/`). Compiles each paper into structured notes and updates the concept graph.

## Arguments

`$ARGUMENTS` can be:
- Empty → batch mode: process all new papers from Zotero + Clippings
- A Zotero item key (8 chars, e.g., `ABC12345`) → process that specific paper
- A DOI (e.g., `10.1038/...`) → search Zotero for that DOI, or fetch from web
- A URL → fetch and process from web

## Step 1: Determine intake source

**If no arguments (batch mode):**

1a. Run the Zotero extraction script to find new papers:

```bash
python3 <watcher-dir>/zotero_extract.py --since "LAST_SYNC" --output-dir "<vault>/10-Research/raw/zotero/"
```

Where `LAST_SYNC` comes from `<watcher-dir>/domain-expert-state.json` field `last_zotero_sync`. If null, use `--list-only` first to show the user how many papers exist and ask how far back to go.

1b. Scan `Clippings/` for files with tag `clippings` that are research papers (have DOI, or academic-looking title/authors). Skip non-research clips.

1c. Read the state file to get `processed_zotero_keys` and `processed_clippings`. Filter out already-processed items.

1d. Show the user a summary: "Found X new Zotero papers, Y new clippings. Process all?" Wait for confirmation if >10 papers.

**If argument provided:**

- Zotero key → `python3 <watcher-dir>/zotero_extract.py --keys "KEY" --output-dir "<vault>/10-Research/raw/zotero/"`
- DOI → search Zotero SQLite first (`python3 -c "..."` to query by DOI field), then extract. If not in Zotero, use WebFetch to get the paper.
- URL → use WebFetch to get the paper content.

## Step 2: Process each paper

For each paper, read the source material:
- **Zotero papers:** Read the JSON file from `10-Research/raw/zotero/<key>.json`. This contains title, authors, abstract, DOI, tags, collections, and full_text (extracted from PDF).
- **Clippings:** Read the markdown file from `Clippings/`.
- **Web fetched:** Read from the fetched content.

**Token efficiency rule:** Read ONE paper at a time. Process it fully (Steps 2a-2e), then move to the next. Do not load multiple papers into context simultaneously.

For batches of >5 papers, dispatch a subagent per paper using the Agent tool. Each subagent gets:
- The paper JSON/markdown content
- The current wiki index (`10-Research/wiki/index.md`)
- A list of existing concept note filenames (from `ls 10-Research/wiki/concepts/`)
- A list of existing group note filenames (from `ls 10-Research/wiki/groups/`)
- Instructions to write output files and report what was created/updated

### 2a: Compile paper note

Write `10-Research/wiki/papers/YYYY-FirstAuthor-ShortTitle.md` using this template:

```yaml
---
type: paper
title: "<exact title>"
authors: ["First Author", "Second Author"]
year: YYYY
doi: "<https://doi.org/DOI or null>"
citekey: "<zotero key>"
source: zotero | clipping | web
domains: [SDL, characterisation, AI]  # which of the 3 domains this paper belongs to
confidence: 0.9
source_count: 1
compiled: YYYY-MM-DD
last_confirmed: YYYY-MM-DD
tags: [paper]
---

## TLDR
One sentence: what is the main contribution.

## Key Claims
- Claim 1
- Claim 2

## Methods
What techniques, instruments, algorithms, or frameworks were used.

## Relevance to <MyProject>
- **SDL:** (if relevant) how this relates to Pillar 1
- **Characterisation:** (if relevant) how this relates to Pillar 2
- **AI Core:** (if relevant) how this relates to Pillar 3

## Data Gaps
What this paper does not address, leaves unclear, or claims without strong evidence.

## Connections
- [[Concept-Name]]: relationship
- [[Group-Name]]: authoring group
```

### 2b: Identify concepts

From the paper content, identify:
- Key concepts (methods, techniques, frameworks, phenomena)
- Map each to one of: SDL, characterisation, AI (or multiple)
- Check if a concept note already exists in `10-Research/wiki/concepts/`

### 2c: Create or update concept notes

**If concept note exists:** Read it, then append this paper to `## Key Papers`, update `## State of the Art` if the paper adds new information, bump `source_count` in frontmatter, update `last_confirmed`.

**If concept is new:** Create `10-Research/wiki/concepts/Concept-Name.md`:

```yaml
---
type: concept
domain: [SDL]
maturity: emerging | established | mature
confidence: 0.7  # lower for single-source concepts
source_count: 1
aliases: []
compiled: YYYY-MM-DD
last_confirmed: YYYY-MM-DD
---

## TLDR
One sentence.

## Definition
One paragraph.

## State of the Art
Current understanding based on available sources.

## Key Papers
- [[YYYY-FirstAuthor-ShortTitle]]: what this paper contributes

## Key Groups
- [[PI-Institution]]: if identifiable

## Related Concepts
- [[Other-Concept]]: relationship

## Counterarguments & Limitations
Known criticisms or open questions.

## <MyProject> Relevance
Strategic implications for the three pillars.
```

### 2d: Create or update group notes

If the paper's authors are from identifiable research groups not yet in `10-Research/wiki/groups/`, create a group note. If the group exists, add this paper to `## Key Publications`.

Group note template at `10-Research/wiki/groups/PI-Institution.md`:

```yaml
---
type: research-group
pi: "PI Name"
institution: "University"
domains: [SDL]
relationship: watch  # default; upgrade to collaborator/competitor as evidence grows
confidence: 0.7
source_count: 1
compiled: YYYY-MM-DD
last_confirmed: YYYY-MM-DD
---

## Focus
Research focus areas.

## Key Publications
- [[YYYY-FirstAuthor-ShortTitle]]

## Infrastructure
Known platforms, instruments, or facilities (if mentioned in papers).

## Strategic Notes
Any competitive or collaborative relevance to <MyProject>.
```

### 2e: Update bidirectional links

Ensure all wikilinks are bidirectional:
- Paper → Concept (in `## Connections`) and Concept → Paper (in `## Key Papers`)
- Paper → Group (in `## Connections`) and Group → Paper (in `## Key Publications`)
- Concept → Concept (in `## Related Concepts`): both directions

## Step 3: Post-processing

After all papers are processed:

3a. **Regenerate `10-Research/wiki/index.md`:** Read all files in `wiki/concepts/`, `wiki/papers/`, `wiki/groups/`, `wiki/radar/`. Rebuild the index with counts, confidence scores, and domain groupings.

3b. **Append to `10-Research/wiki/log.md`:** Log entry with timestamp, source (Zotero/Clippings), papers created, concepts created/updated, groups created/updated.

3c. **Move processed clippings:** Move research clippings from `Clippings/` to `10-Research/raw/clippings/`.

3d. **Update state file:** Add processed Zotero keys and clipping filenames to `<watcher-dir>/domain-expert-state.json`. Update `last_zotero_sync` to current datetime. Update counts.

## Step 4: Report

Output to terminal:
```
Paper ingest complete.
- Papers processed: N (M from Zotero, K from Clippings)
- Concepts created: X
- Concepts updated: Y
- Groups created: Z
- Wiki now has: P papers, C concepts, G groups
```

## Rules

- **Token efficiency:** Read one paper at a time. For >5 papers, use subagents.
- **Never edit raw/ sources** (except moving clippings into raw/clippings/).
- **Wiki is LLM-owned:** Write freely to wiki/. The user does not edit these files.
- **Confidence scores:** Single-source concepts get 0.7. Multi-source get 0.8-0.95 depending on agreement. Review papers and established methods get 0.9+.
- **Domain classification:** Every paper and concept must be tagged with at least one domain (SDL, characterisation, AI).
- **Filename conventions:** Papers: `YYYY-FirstAuthor-ShortTitle.md`. Concepts: `Descriptive-Name.md` (PascalCase with hyphens). Groups: `PI-Institution.md`.

# Commands: slash command rituals

Four hand-picked rituals from a larger set. Each is a Claude
Code slash command (`.md` file in `.claude/commands/`).

| File | Trigger | What it does |
|------|---------|--------------|
| `goodmorning.md` | morning | Today's calendar + priority actions + project risks. |
| `5pmsummary.md` | end of day | 11-step ritual: from setup (Step 0) through digest write (Step 10). Fetches Mail/Calendar/Notes, writes meeting notes, updates stakeholders + Dashboard + projects, archives inbox, writes digest. |
| `reflect.md` | weekly | Read 7 days of diary + meetings, synthesise patterns, update two pattern files. |
| `paper-ingest.md` | on demand | Ingest papers from Zotero into the LLM-owned knowledge wiki. |

## Adapting

These commands assume:
- An Obsidian vault at `<vault>` with conventions documented in `CLAUDE.md`.
- AppleScript helpers in `<watcher-dir>` for fetching from Apple Mail/Calendar/Notes.
- A Dashboard markdown file as your single source of truth for open actions.

Replace placeholders with your own paths, then adopt one command
at a time. `goodmorning.md` is the cheapest to start with.

# Hooks — Claude Code lifecycle integration

Each script here is wired into a Claude Code lifecycle hook in
`settings.local.json`. Together they protect the system from
self-edits, classify incoming messages for routing, validate
vault writes, inject dynamic context at session start, and
mark context-compaction events.

| File | Hook event | Purpose |
|------|------------|---------|
| `protect-system-files.sh` | PreToolUse(Write,Edit) | Block writes to protected files (hooks, CLAUDE.md, etc). Self-protecting. |
| `classify-message.py` | UserPromptSubmit | Inject routing hints when the user mentions a stakeholder, decision, or project. |
| `validate-write.sh` | PostToolUse(Write,Edit) on `*.md` | Advisory frontmatter + wikilink check. |
| `session-start.sh` | SessionStart | Inject the latest end-of-day digest + project status. |
| `pre-compact.sh` | PreCompact | Save a marker before context compaction. |

## Adapting

- `classify-message.py`: populate `STAKEHOLDER_NAMES` with the names
  you want the router to detect.
- `protect-system-files.sh`: edit the `PROTECTED_HARD_BLOCK` and
  `PROTECTED_WARN` arrays at the top to match your own critical files.
- `validate-write.sh`: tune the frontmatter fields and minimum
  wikilink-density threshold to your vault conventions.

These hooks reference placeholder values you'll need to replace with your own:

| Placeholder | What to substitute |
|---|---|
| `<vault>` | Path to your Obsidian vault |
| `<watcher-dir>` | Path to your scripts/state directory |
| `<MyProject>` | Your main project's name and folder |
| `<github-org>` | Your GitHub org or user |
| `<project-domain>` | Your project's public-facing domain |
| `<funder-programme>` | Your funder or programme reference |
| `<peer-network>` | Your peer/community network name |
| `<my-institution>` / `<my-institute>` | Your institution name |
| `<email-domain>` | Your institutional email domain |
| `<hashed-vault-path>` | The Claude Code projects-dir hash for your vault (find via `claude project list`) |

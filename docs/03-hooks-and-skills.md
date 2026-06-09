# Hooks and slash commands

Claude Code exposes lifecycle hooks: scripts that run at defined points in a session, before or after the agent takes an action. They let you intercept tool calls, inject context at startup, and validate writes before they land. Combined with slash commands, which are multi-step orchestration scripts the agent executes on demand, hooks turn Claude Code from a general assistant into a vault-aware operator that follows your conventions without being reminded.

## The five hooks

| Hook | Lifecycle event | Purpose |
|------|----------------|---------|
| `protect-system-files.sh` | PreToolUse(Write, Edit) | Block edits to critical files. Self-protecting. |
| `classify-message.py` | UserPromptSubmit | Inject routing hints when the user names a stakeholder, project, or decision. |
| `validate-write.sh` | PostToolUse(Write, Edit) on `*.md` | Advisory frontmatter + wikilink check. |
| `session-start.sh` | SessionStart | Inject the latest digest + project status into every new session. |
| `pre-compact.sh` | PreCompact | Save a marker before context compaction. |

These five cover three concerns: protection (the agent should not overwrite its own rules), routing (the agent should follow vault conventions without being told), and context (the agent should know what's happening in your life when it shows up). Each hook handles one concern. Nothing overlaps.

## The self-protecting hook

`protect-system-files.sh` intercepts every Write and Edit call and checks the target path against a protected list: the hook itself, CLAUDE.md, and any other files whose overwrite would break the setup. The hook exits with a non-zero code, which Claude Code treats as a block. The agent will sometimes try to "fix" a configuration file that looks incomplete, and without protection it can corrupt its own rules. Protection must live in the hook, not in a prompt instruction, because prompt instructions don't survive context compaction. See `examples/hooks/protect-system-files.sh`.

## Classification

`classify-message.py` runs on every user message before the agent processes it. It scans for routing signals: stakeholder names, project keywords, decision verbs, and diary indicators. On a match, it injects a brief system reminder pointing the agent at the relevant files. The user writes naturally; the agent gets a nudge. The example in `examples/hooks/classify-message.py` ships with an empty `STAKEHOLDER_NAMES` list because that list is per-user. Populate it with people you mention regularly and the classifier will route meeting-note creation, stakeholder updates, and dashboard pushes without prompting.

## Validation

`validate-write.sh` fires after any Write or Edit to a `*.md` file. It checks that the frontmatter fields required by the folder convention are present and that notes longer than 300 characters contain at least one wikilink. It prints warnings but never blocks. The goal is to catch structural drift early. See `examples/hooks/validate-write.sh`.

## Session-start context

`session-start.sh` fires once at the beginning of every session. It reads the latest end-of-day digest, a short project status summary, and the dashboard's open action count, then injects all three into session context. The agent walks in knowing what happened yesterday and what's open today. Without this, the first few exchanges are spent re-establishing context. With it, "what should I prioritize this morning?" gets a grounded answer immediately. See `examples/hooks/session-start.sh`.

## Slash commands as rituals

Slash commands sit on top of hooks. A command is a Markdown file that describes a multi-step procedure: read these files, call these MCP tools, write these outputs, check these conditions. The examples in `examples/commands/` include `goodmorning.md` (morning briefing from calendar and overnight digest), `5pmsummary.md` (the 11-step end-of-day ritual covering email, meetings, stakeholders, and dashboard), `reflect.md` (weekly synthesis across diary and project files), and `paper-ingest.md` (Zotero metadata into the research wiki).

The value of a command over an ad-hoc prompt is consistency. The `5pmsummary` runs the same 11 steps every weekday, in the same order, writing to the same files. If the agent skips a step or improvises the output structure, the digest breaks and downstream scripts break too. The command encodes the ritual so the agent cannot drift. The same output shape every time is what makes it useful input to the next day's `goodmorning`.

## Adapting

Start with `examples/hooks/session-start.sh`. It is the lowest-friction hook: it only reads files and injects text, and it makes every session immediately more useful. Once you have a few files you care about protecting, add `protect-system-files.sh`. Per-file guidance is in `examples/hooks/README.md`; command stubs are in `examples/commands/README.md`.

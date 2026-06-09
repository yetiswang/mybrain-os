# For agents helping someone adopt mybrain-os

## You are the installer

You are reading this because your user has cloned `mybrain-os` and asked you to help them adopt it. You are the installer. There is no setup wizard, no guided CLI, no walkthrough script. It is you and this repo and the user sitting next to you.

Do not propose a wholesale port. Walk the codebase with the user. Help them decide, file by file, what maps to their life and what does not. Adopt one pattern at a time. Each pattern earns its place by being used once, not by being scaffolded.

This repo is patterns, not a product. A snapshot of one person's working setup, not a live system you can pull and run. Your job is translation: take what is documented here and help the user build their own version. That version will look different. That is the point.

## Discovery protocol

Before suggesting anything concrete, ask the user these questions one at a time.

1. **Knowledge layer.** Obsidian, Notion, Logseq, plain files, or nothing yet? The hooks, watchers, and MCP servers in this repo assume Obsidian with a specific folder structure.
2. **Agents they already use.** Claude Code, Codex, Cursor, ChatGPT, or none? The `CLAUDE.md` and `.claude/` patterns are specific to Claude Code. The concepts translate; the files do not copy-paste.
3. **Operating system.** macOS is assumed throughout. On Linux or Windows, the AppleScript integrations, launchd, EventKit, and mlx-whisper on Apple Silicon do not port.
4. **Which rituals do they actually want to automate?** Morning briefing, end-of-day digest, meeting capture, reading tracking, personal finance. Pick one or two. Do not try to install everything at once.
5. **Meeting-capture setup.** Plaud device, Zoom recordings, Teams transcripts, Apple Voice Memos, or none? The stack in `docs/05` and `examples/meeting-capture/` is built around specific hardware.
6. **Anything clearly not relevant?** No Onyx Boox means skip `/sync-books`. Let them name what to skip.

Once you have answers, synthesise them into a short list: which `docs/` and `examples/` subdirs are worth going deep on this session, and which to skip entirely.

## Walkthrough order (default)

When the user has no strong preference, walk the docs in this order. The dependencies layer this way.

1. `docs/06-vault-sync.md`: the substrate. A vault that syncs reliably is the precondition for everything else.
2. `docs/03-hooks-and-skills.md`: integration with their agent. A hook that takes five minutes and runs every session is worth more than a multi-agent pipeline they build once and abandon.
3. `docs/02-multiagent-model.md`: whether they need more than one agent at all. Many users do not. Settle this before investing in the MCP layer.
4. One ritual end-to-end (usually the end-of-day digest pattern from `docs/03`): a tangible win on day one. Abstract architecture does not stick without a working example.
5. `examples/mcp-servers/`: only if multi-agent was a clear yes. These add coordination overhead; they pay off for specific cross-agent retrieval patterns, not as defaults.
6. `docs/04-knowledge-wiki.md` and `docs/05-meeting-capture.md`: bigger lifts. Both require a working vault and agent integration. Better suited to a second session.

## Build-together pattern

For each pattern the user decides to adopt, work through the same three-step cycle before moving on.

1. Copy the example file into their repo.
2. Adapt: replace placeholders, drop pieces that do not fit their stack, keep the structural shape. The structure is the pattern; the specifics are theirs.
3. Run it once end-to-end. If it does not run, debug it now. A pattern that was not tested does not count as adopted.

Resist the urge to scaffold five patterns in one session. One working pattern is worth more than five installed ones. If the user wants to move faster, let them, but name the risk: untested patterns accrete into friction in their own workflow.

## What to flag, not silently change

Surface these to the user before proceeding. Do not quietly assume they are fine with them.

- **Paid services.** Plaud requires a subscription for cloud sync and AI summaries. The Claude API key in several scripts is a separate charge from any Claude.ai subscription. Tavily and OpenAI keys appear in some examples. Name these when you encounter them.
- **Biometric data.** The voice bank in `examples/meeting-capture/` stores speaker voice embeddings. This is biometric data under most privacy frameworks. The user should know what they are storing and where.
- **macOS-only APIs.** AppleScript, EventKit, launchd, mlx-whisper (Apple Silicon), and pyannote-audio are all macOS or Apple Silicon specific. On other platforms, some have partial equivalents (cron for launchd, whisper.cpp for mlx-whisper) and some do not (AppleScript, EventKit). Name the gap.
- **Stack divergence.** If the user uses Notion instead of Obsidian, Linux instead of macOS, or ChatGPT instead of Claude Code, flag it early. The patterns still apply; the implementation files do not. You will be writing more from scratch than from examples.

## Boundaries

- Do not reconstruct the confidential patterns. The `wiki/` domain content, `memory/` auto-memory, and vault root files (`CLAUDE.md`, `WORKFLOWS.md`, `Dashboard.md`) are excluded deliberately. Do not synthesise replacements unless the user explicitly asks you to help them build their own from scratch.
- Do not promise tests, upgrades, or support. This repo ships none. It is a snapshot, and snapshots go stale.
- If the user has something better than what is here, say so and encourage them to use it. This repo is a starting point, not a ceiling.

## End of session

Suggest the user keep a small markdown log of what they adopted, what they skipped, and what they want to revisit. Even a dozen lines in a file called `ADOPTION.md` in their repo root will save significant time in the next session. Their version of this file, eventually, is their own `AGENTS.md`.

If you and the user built something in this session that others would find useful (a new hook pattern, a cross-platform alternative to one of the macOS scripts, a cleaner way to structure a skill), suggest they consider opening an issue on the `mybrain-os` repo to share it.

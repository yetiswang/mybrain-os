# Overview

## What this is

A personal operating system for a knowledge worker. The vault is the substrate: a folder of Obsidian markdown files. Around it orbit agents, background scripts, MCP servers, lifecycle hooks, and daily rituals. Nothing here is a product. It is a set of patterns I've built over two years, running as research infrastructure manager at TU/e while leading a national AI-driven materials discovery initiative. The patterns are the point, not the stack.

## Why one vault, not many tools

Plaintext is durable. The markdown files in this vault will open in any editor, on any machine, in twenty years. Every SaaS tool I've tried eventually loses data through format lock-in, sunsets, or pricing changes. A folder of `.md` files doesn't. That's the first reason to anchor everything here.

The second reason is agents. I run Claude Code for interactive sessions, Codex CLI as a second opinion, and Hermes for nightly synthesis. If each agent keeps its own memory, they diverge. When all three write to and read from one vault, they stay in sync without coordination overhead. Wikilinks let the knowledge form a graph that grows by use. The vault is also in iCloud for device sync, and git-mirrored every 30 minutes because iCloud doesn't provide versioned history.

## The layers

**Vault.** Obsidian markdown files in iCloud, git-mirrored automatically. The only storage that matters. Every other layer reads from or writes to here.

**Agents.** Claude Code drives interactive sessions (this repo is its working context). Codex CLI handles second-opinion review and parallelisable execution tasks. Hermes runs nightly to synthesise across sessions. Each plays to its strengths. See `docs/02-multiagent-model.md`.

**MCP servers.** Shared memory accessible to all three agents. `vault-memory` handles semantic and recency search. `vault-kg` is a property graph rebuilt nightly from the vault. `plaud-db` indexes meeting transcripts. `zotero` exposes the reference library. All agents call the same four servers. See `examples/mcp-servers/`.

**Hooks and commands.** Claude Code lifecycle integration. A session-start hook injects today's summary and project status. A validate-write hook checks frontmatter on new notes. A classify-message hook routes incoming context. Slash commands like `/5pmsummary` and `/reflect` are executable skill files. See `docs/03-hooks-and-skills.md`.

**Watchers.** macOS launchd background scripts that run without me. One auto-commits the vault to git every 30 minutes. Another scans for new books and updates a catalog. Another syncs project documents from Dropbox. They're small Python and bash scripts, not services. See `examples/watchers/`.

**Capture pipeline.** Audio from a Plaud Note Pro recorder goes through mlx-whisper transcription, pyannote-audio speaker diarisation, and a voice-bank matcher that labels speakers by voice profile. The result is a structured meeting note in the vault. Runs locally on Apple Silicon in about six times real-time. See `docs/05-meeting-capture.md`.

**Rituals.** `/goodmorning` pulls calendar, prioritises the day, flags risks. `/5pmsummary` processes email, writes meeting notes, updates stakeholder files, prunes the dashboard. `/reflect` reads recent diary entries and project files, then surfaces patterns. These are the daily and weekly heartbeat. See `examples/commands/`.

## What this repo gives you

Patterns, not a product. This is a snapshot from June 2026. Fork what fits your stack, ignore what doesn't. The suggested path is to adopt one pattern at a time by describing it to your own agent and letting the agent implement it for your setup. That friction is deliberate. Install-with-a-script skips the thinking. Adopt-with-an-agent forces you to decide whether the pattern actually fits your life before you commit to it. Start with `AGENTS.md`.

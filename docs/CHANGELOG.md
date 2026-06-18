# Changelog

Snapshot semantics. See the README's "Getting started" section.
Each entry: date, summary, private-repo reference (for the author's
own tracking; readers can ignore).

## v0.1.1 (2026-06-18)

Adds an office-automation pattern group, drawn from a real team-directory workflow.

- New doc: `docs/07-office-automation.md` — tracking a shared spreadsheet, generating directory cards.
- New `examples/office/`: `xlsx_change_monitor.py` (snapshot/diff/attributed change-log for a workbook several people edit online), `pptx_card_from_form.py` (a form entry into a slide card by mirroring a template slide + clipped-circle photo), `pptx_stamp_updated.py` (idempotent "Updated ..." title-slide stamp).
- README "Core patterns" grid gains an Office automation tile.

Private-repo reference: team-directory automation (profile cards + shared-sheet monitor + deck auto-stamp), 2026-06-17 to 2026-06-18.

## v0.1.0 (2026-06-09)

First public snapshot. Includes:

- 7 docs: overview, multiagent model, hooks, skills, knowledge wiki, meeting capture, this changelog.
- 5 Claude Code lifecycle hooks (`examples/hooks/`).
- 4 slash-command rituals (`examples/commands/`): `5pmsummary`, `reflect`, `goodmorning`, `paper-ingest`.
- 3 MCP server examples (`examples/mcp-servers/`): `vault-memory` (full), `vault-kg` (skeleton), `plaud-db`.
- 7 AppleScript / EventKit Swift patterns (`examples/applescript/`) for Mail, Calendar, Notes.
- 3 Python scripts + vocab example for the local Plaud to mlx-whisper + pyannote + voice-bank pipeline (`examples/meeting-capture/`).
- 3 launchd watcher patterns + plist template (`examples/watchers/`).
- 3 helper scripts (Rabobank importer, market data fetcher, voice memo transcriber).
- `AGENTS.md`: vendor-neutral agent-led installer.
- 51 files total across all examples.

Private-repo reference: auto-backup commit window around 2026-06-09 18:36 CEST.

# 06. Vault Sync: iCloud + Git Mirror

The least glamorous layer and the most foundational. The vault is the substrate every other piece in this OS sits on. If the substrate is fragile, the whole stack is fragile.

## The vault

My notes live in Obsidian, stored as plaintext markdown on iCloud. I picked Obsidian for three reasons: the files open in any editor, so nothing I write today is hostage to a company staying alive; wikilinks let the knowledge graph form by use rather than by design; and local-first means the tool works on a plane. Two folders carry the daily load: the working set of active notes and `00-Inbox`, the catch-all for anything that hasn't found a permanent home yet.

## Why git on top of iCloud

iCloud syncs. iCloud does not version. A silent corruption, a regrettable agent edit, or an accidental `rm` leaves no audit trail. The first time you lose a file you didn't realise was important, you understand why versioning matters independently of sync.

A private GitHub repo mirrors the vault. An auto-commit script runs every 30 minutes via launchd: `git add -A`, commit with a timestamp, push. The result is per-30-minute snapshots going back indefinitely. Not pretty history, but useful history. When something goes wrong, I can find the last intact state of any file without guessing.

## The pattern

1. Vault location: `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/<vault-name>/`.
2. Create a private GitHub repo (e.g., `<your-handle>/mybrain-vault`).
3. Initialise git inside the vault: `git init && git remote add origin git@github.com:<you>/mybrain-vault.git`.
4. `.gitignore` excludes the heavy files: `.obsidian/workspace*`, your attachments folder if it holds audio or video, `.DS_Store`.
5. Install `commit-vault.sh` (in `examples/watchers/`) and the launchd plist (in `examples/watchers/com.example.watcher.plist`).
6. Store a fine-grained PAT scoped to the one private repo at a chmod-600 file like `<watcher-dir>/github-token` and read it from there. Do not hardcode credentials in the script.
7. Load the launchd job: `launchctl load ~/Library/LaunchAgents/com.example.watcher.plist`.

## What this protects against

- iCloud sync corruption (it happens, silently).
- Accidental deletes by you or by an agent running a write operation it shouldn't have.
- Local disk failure where the remote is the only copy.
- A bad regex edit that touched 200 notes you didn't mean to touch.

## Recovery example

```bash
# Find when a note was last seen intact
git log -- path/to/lost-note.md
# Restore it from any earlier commit
git checkout HEAD~50 -- path/to/lost-note.md
```

Per-30-min cadence means the worst-case loss is 30 minutes of edits, which you can usually retype.

## Adapting

The example files are `examples/watchers/commit-vault.sh` and `examples/watchers/com.example.watcher.plist`. If you're on Linux, swap launchd for systemd timers or cron. If you're not on Obsidian, the same pattern works for any note tool that stores files on disk.

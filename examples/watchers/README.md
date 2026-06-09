# Watchers — launchd background patterns

Background scripts managed by macOS launchd. Each watcher
maintains its own state file (not tracked in any git repo —
state is ephemeral).

## Files

| File | Cadence | What it does |
|------|---------|--------------|
| `watch-roadmaps.sh` | every 8h | Detect changes in a Dropbox project folder, sync to vault, drop an inbox alert. |
| `watch-books.py` | weekly | Scan a books folder for new files, append to a master catalog, infer category from path. |
| `commit-vault.sh` | every 30 min | Auto-commit + push your vault to a private GitHub mirror (provides versioning iCloud lacks). |
| `com.example.watcher.plist` | (template) | Generic launchd plist template — replace `<USER>` and `<PATH>` with your values. |

## Installing a watcher

```bash
# Edit the plist
sed -i '' "s|<USER>|$USER|g; s|<PATH>|$HOME/path/to/script.sh|g" \
  com.example.watcher.plist

# Copy to LaunchAgents
cp com.example.watcher.plist ~/Library/LaunchAgents/

# Load it
launchctl load ~/Library/LaunchAgents/com.example.watcher.plist

# Check it's loaded
launchctl list | grep com.example
```

## The auto-commit pattern

`commit-vault.sh` runs every 30 min on a private GitHub mirror
of the vault. It catches the case where iCloud sync silently
loses or corrupts a file — git history is the safety net. Use
a dedicated PAT scoped to one repo, store at
`<watcher-dir>/github-token` (chmod 600).

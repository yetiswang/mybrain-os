#!/usr/bin/env bash
# Auto-commit vault and watcher scripts on change.
# Runs every 30 min via launchd. No-ops when nothing changed.

set -euo pipefail

VAULT="<vault>"
INFRA="<watcher-dir>"
STAMP=$(date '+%Y-%m-%d %H:%M')

commit_repo() {
  local dir="$1"
  local label="$2"
  cd "$dir"
  git add -A
  if ! git diff --staged --quiet; then
    git commit -m "${label}: auto-backup ${STAMP}"
    git push
    echo "[commit-vault] committed ${label}"
  fi
}

commit_repo "$VAULT"  "vault"
commit_repo "$INFRA"  "infra"

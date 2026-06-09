#!/usr/bin/env bash
# Watches a Dropbox project folder for new or modified files
# and creates an inbox note in the Obsidian vault when changes are detected.

WATCH_DIR="<dropbox>/InfrastructureStrategy/Roadmaps"
VAULT_INBOX="<vault>/00-Inbox"
VAULT_ARCHIVE="<vault>/90-Archive/Inbox"
VAULT_PROJECTS="<vault>/30-Projects"
STATE_FILE="<watcher-dir>/roadmaps-state.txt"
TOKEN_FILE="<watcher-dir>/github-token"
REPO_DIR="$WATCH_DIR/ProjectDocuments/<funder-programme>_project_charter"
STATUS_FILE="$VAULT_INBOX/roadmaps-watcher-status.md"

# Sync targets: Dropbox source → Vault destination
SYNC_SRC="$WATCH_DIR/ProjectDocuments/<MyProject>.md"
SYNC_DST="$VAULT_PROJECTS/<MyProject>/<MyProject>.md"

# --- Pull latest from Overleaf via GitHub ---
if [ -f "$TOKEN_FILE" ] && [ -d "$REPO_DIR/.git" ]; then
  TOKEN=$(grep GITHUB_TOKEN "$TOKEN_FILE" | cut -d= -f2)
  if [ -n "$TOKEN" ] && [ "$TOKEN" != "paste_new_token_here" ]; then
    REMOTE_URL="https://${TOKEN}@github.com/<github-org>/<funder-programme>_project_charter.git"
    git -C "$REPO_DIR" remote set-url origin "$REMOTE_URL" 2>/dev/null
    git -C "$REPO_DIR" pull --quiet 2>/dev/null
  fi
fi

# Build current state: relative path + mtime for all non-hidden files
CURRENT_STATE=$(find "$WATCH_DIR" \
  -not -path '*/.git/*' \
  -not -name '.DS_Store' \
  -not -name '*.aux' \
  -not -name '*.log' \
  -not -name '*.out' \
  -not -name '*.nav' \
  -not -name '*.snm' \
  -not -name '*.toc' \
  -not -name 'compile.log' \
  -type f \
  -exec stat -f "%m %N" {} \; 2>/dev/null | sort)

# If no state file yet, just save current state and exit silently
if [ ! -f "$STATE_FILE" ]; then
  if [ -n "$CURRENT_STATE" ]; then
    echo "$CURRENT_STATE" > "$STATE_FILE"
  fi
  exit 0
fi

PREV_STATE=$(cat "$STATE_FILE")

if [ "$CURRENT_STATE" = "$PREV_STATE" ]; then
  # No changes — update heartbeat and exit
  TIMESTAMP=$(date +"%Y-%m-%d %H:%M")
  cat > "$STATUS_FILE" <<HEARTBEAT
---
type: watcher-status
tags: [watcher]
---

# Roadmaps Watcher — Last Run

**Status:** no changes
**Last run:** ${TIMESTAMP}
HEARTBEAT
  exit 0
fi

# Find what changed
NEW_FILES=""
MODIFIED_FILES=""

while IFS= read -r line; do
  MTIME=$(echo "$line" | awk '{print $1}')
  FPATH=$(echo "$line" | awk '{$1=""; print substr($0,2)}')
  REL_PATH="${FPATH#$WATCH_DIR/}"

  PREV_LINE=$(echo "$PREV_STATE" | grep -F "$FPATH")
  if [ -z "$PREV_LINE" ]; then
    NEW_FILES="${NEW_FILES}\n- \`${REL_PATH}\`"
  else
    PREV_MTIME=$(echo "$PREV_LINE" | awk '{print $1}')
    if [ "$MTIME" != "$PREV_MTIME" ]; then
      MODIFIED_FILES="${MODIFIED_FILES}\n- \`${REL_PATH}\`"
    fi
  fi
done <<< "$CURRENT_STATE"

# Save new state (only if non-empty, to avoid wiping state if find fails)
if [ -n "$CURRENT_STATE" ]; then
  echo "$CURRENT_STATE" > "$STATE_FILE"
fi

# Bidirectional merge of <MyProject>.md between Dropbox and vault
BASE_FILE="<watcher-dir>/<MyProject>-base.md"
MERGE_NOTE=""

if [ -f "$SYNC_SRC" ] && [ -f "$SYNC_DST" ]; then
  if [ -f "$BASE_FILE" ]; then
    SRC_SAME=$(diff -q "$BASE_FILE" "$SYNC_SRC" > /dev/null 2>&1 && echo yes || echo no)
    DST_SAME=$(diff -q "$BASE_FILE" "$SYNC_DST" > /dev/null 2>&1 && echo yes || echo no)
    if [ "$SRC_SAME" = "no" ] && [ "$DST_SAME" = "yes" ]; then
      # Only Dropbox changed
      cp "$SYNC_SRC" "$SYNC_DST"
      cp "$SYNC_SRC" "$BASE_FILE"
      MERGE_NOTE="<MyProject>.md: Dropbox → vault"
    elif [ "$SRC_SAME" = "yes" ] && [ "$DST_SAME" = "no" ]; then
      # Only vault changed
      cp "$SYNC_DST" "$SYNC_SRC"
      cp "$SYNC_DST" "$BASE_FILE"
      MERGE_NOTE="<MyProject>.md: vault → Dropbox"
    elif [ "$SRC_SAME" = "no" ] && [ "$DST_SAME" = "no" ]; then
      # Both changed — attempt 3-way merge (vault | base | dropbox)
      MERGED=$(diff3 -m "$SYNC_DST" "$BASE_FILE" "$SYNC_SRC" 2>/dev/null)
      if echo "$MERGED" | grep -q "^<<<<<<<"; then
        MERGE_NOTE="<MyProject>.md: MERGE CONFLICT — resolve manually in both Dropbox and vault copies"
      else
        echo "$MERGED" > "$SYNC_SRC"
        echo "$MERGED" > "$SYNC_DST"
        cp "$SYNC_SRC" "$BASE_FILE"
        MERGE_NOTE="<MyProject>.md: auto-merged (both sides had changes)"
      fi
    fi
  else
    # No base yet — bootstrap from Dropbox as source of truth
    cp "$SYNC_SRC" "$SYNC_DST"
    cp "$SYNC_SRC" "$BASE_FILE"
    MERGE_NOTE="<MyProject>.md: initial sync (Dropbox → vault)"
  fi
elif [ -f "$SYNC_SRC" ]; then
  cp "$SYNC_SRC" "$SYNC_DST"
  cp "$SYNC_SRC" "$BASE_FILE"
  MERGE_NOTE="<MyProject>.md: initial sync (Dropbox → vault)"
elif [ -f "$SYNC_DST" ]; then
  cp "$SYNC_DST" "$SYNC_SRC"
  cp "$SYNC_DST" "$BASE_FILE"
  MERGE_NOTE="<MyProject>.md: initial sync (vault → Dropbox)"
fi

# Only create note if something actually changed
if [ -z "$NEW_FILES" ] && [ -z "$MODIFIED_FILES" ] && [ -z "$MERGE_NOTE" ]; then
  exit 0
fi

TIMESTAMP=$(date +"%Y-%m-%d %H:%M")
NOTE_FILE="$VAULT_INBOX/roadmaps-updates.md"

mkdir -p "$VAULT_ARCHIVE"
for OLD_NOTE in "$VAULT_INBOX"/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]-roadmaps-update.md; do
  [ -e "$OLD_NOTE" ] || continue
  mv "$OLD_NOTE" "$VAULT_ARCHIVE/"
done

if [ ! -f "$NOTE_FILE" ]; then
  cat > "$NOTE_FILE" <<EOF
---
type: watch-log
source: roadmaps-watcher
tags: [inbox, watch-log]
---

# Roadmaps Updates Log

EOF
fi

printf "\n## %s\n" "$TIMESTAMP" >> "$NOTE_FILE"

if [ -n "$MERGE_NOTE" ]; then
  printf "\n### Sync\n- %s\n" "$MERGE_NOTE" >> "$NOTE_FILE"
fi

if [ -n "$MODIFIED_FILES" ]; then
  printf "\n### Modified\n$(echo -e "$MODIFIED_FILES")\n" >> "$NOTE_FILE"
fi

if [ -n "$NEW_FILES" ]; then
  printf "\n### New files\n$(echo -e "$NEW_FILES")\n" >> "$NOTE_FILE"
fi

echo "" >> "$NOTE_FILE"
echo "> Detected at ${TIMESTAMP}" >> "$NOTE_FILE"

# Always update heartbeat status file
cat > "$STATUS_FILE" <<HEARTBEAT
---
type: watcher-status
tags: [watcher]
---

# Roadmaps Watcher — Last Run

**Status:** changes detected
**Last run:** ${TIMESTAMP}
**Alert note:** [[roadmaps-updates]]
HEARTBEAT

#!/usr/bin/env bash
# PreToolUse hook: protect core infrastructure files from accidental writes.
# Reads JSON from stdin: {"tool_name": "Write", "tool_input": {"file_path": "..."}, ...}
# Exit 0 = allow, 1 = warn (advisory), 2 = block (hard reject).

set -euo pipefail

VAULT="<vault>"
WATCHER_DIR="$HOME/.local/share/vault-watcher"

# Parse input
INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_name',''))" 2>/dev/null || echo "")
FILE_PATH=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path',''))" 2>/dev/null || echo "")

# Only check Write and Edit
if [[ "$TOOL_NAME" != "Write" && "$TOOL_NAME" != "Edit" ]]; then
    exit 0
fi

if [[ -z "$FILE_PATH" ]]; then
    exit 0
fi

# --- HARD BLOCK (exit 2) ---
# Edit the PROTECTED_PATHS array at the top to match your own critical files.
# Each entry is a path prefix (or exact path) relative to $VAULT or $HOME.
# Use the full expanded prefix as the patterns below show.

PROTECTED_HARD_BLOCK=(
    "$VAULT/.claude/hooks/"          # Hook scripts (includes this file — self-protecting)
    "$VAULT/.claude/settings.local.json"  # Hook configuration and permissions
    "$VAULT/CLAUDE.md"               # Project instructions governing Claude's behaviour
    "$WATCHER_DIR/*.py"              # Watcher Python scripts
    "$WATCHER_DIR/*.sh"              # Watcher shell scripts
)

for pattern in "${PROTECTED_HARD_BLOCK[@]}"; do
    # Glob-match: strip trailing /* for prefix checks, or exact-match for single files
    if [[ "$pattern" == *"/*.py" || "$pattern" == *"/*.sh" ]]; then
        dir="${pattern%/*}"
        ext="${pattern##*.}"
        if [[ "$FILE_PATH" == "$dir/"*".$ext" ]]; then
            echo "[BLOCKED] Cannot modify watcher script: $(basename "$FILE_PATH"). Watcher scripts are protected infrastructure. Edit manually outside Claude."
            exit 2
        fi
    elif [[ "$pattern" == *"/" ]]; then
        if [[ "$FILE_PATH" == "$pattern"* ]]; then
            echo "[BLOCKED] Cannot modify hook script: $(basename "$FILE_PATH"). Hook scripts are protected infrastructure. Edit manually outside Claude."
            exit 2
        fi
    else
        if [[ "$FILE_PATH" == "$pattern" ]]; then
            name=$(basename "$FILE_PATH")
            case "$name" in
                settings.local.json)
                    echo "[BLOCKED] Cannot modify settings.local.json. Contains hook configuration and permissions. Edit manually outside Claude."
                    ;;
                CLAUDE.md)
                    echo "[BLOCKED] Cannot modify CLAUDE.md. This governs Claude's behavior in this vault. Edit manually outside Claude."
                    ;;
                *)
                    echo "[BLOCKED] Cannot modify protected file: $name. Edit manually outside Claude."
                    ;;
            esac
            exit 2
        fi
    fi
done

# --- ADVISORY WARN (exit 1) ---
# Edit the PROTECTED_PATHS_WARN array to match files that warrant a warning but not a hard block.

PROTECTED_WARN=(
    "$VAULT/.claude/commands/*.md"   # Slash command definitions
    "$VAULT/30-Projects/<MyProject>/<MyProject>.md"  # Critical project file — replace <MyProject>
)

for pattern in "${PROTECTED_WARN[@]}"; do
    if [[ "$pattern" == *"/*.md" ]]; then
        dir="${pattern%/*}"
        if [[ "$FILE_PATH" == "$dir/"*.md ]]; then
            echo "[WARNING] Modifying slash command: $(basename "$FILE_PATH"). Proceed only if explicitly asked for this change."
            exit 1
        fi
    else
        if [[ "$FILE_PATH" == "$pattern" ]]; then
            echo "[WARNING] Modifying <MyProject> project file. Only append to Change Log or update Status at a Glance."
            exit 1
        fi
    fi
done

exit 0

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

# Hook scripts (includes this file — self-protecting)
if [[ "$FILE_PATH" == "$VAULT/.claude/hooks/"* ]]; then
    echo "[BLOCKED] Cannot modify hook script: $(basename "$FILE_PATH"). Hook scripts are protected infrastructure. Edit manually outside Claude."
    exit 2
fi

# Hook configuration
if [[ "$FILE_PATH" == "$VAULT/.claude/settings.local.json" ]]; then
    echo "[BLOCKED] Cannot modify settings.local.json. Contains hook configuration and permissions. Edit manually outside Claude."
    exit 2
fi

# Project instructions
if [[ "$FILE_PATH" == "$VAULT/CLAUDE.md" ]]; then
    echo "[BLOCKED] Cannot modify CLAUDE.md. This governs Claude's behavior in this vault. Edit manually outside Claude."
    exit 2
fi

# Vault watcher scripts
if [[ "$FILE_PATH" == "$WATCHER_DIR/"*.py || "$FILE_PATH" == "$WATCHER_DIR/"*.sh ]]; then
    echo "[BLOCKED] Cannot modify watcher script: $(basename "$FILE_PATH"). Watcher scripts are protected infrastructure. Edit manually outside Claude."
    exit 2
fi

# --- ADVISORY WARN (exit 1) ---

# Slash command definitions
if [[ "$FILE_PATH" == "$VAULT/.claude/commands/"*.md ]]; then
    echo "[WARNING] Modifying slash command: $(basename "$FILE_PATH"). Proceed only if explicitly asked for this change."
    exit 1
fi

# Critical project file
if [[ "$FILE_PATH" == "$VAULT/30-Projects/<MyProject>/<MyProject>.md" ]]; then
    echo "[WARNING] Modifying <MyProject> project file. Only append to Change Log or update Status at a Glance."
    exit 1
fi

exit 0

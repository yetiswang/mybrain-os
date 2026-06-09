#!/usr/bin/env bash
# PostToolUse hook: validate vault .md writes for frontmatter and wikilinks.
# Reads JSON from stdin: {"tool_name": "Write", "tool_input": {"file_path": "..."}, ...}
# Prints warnings to stdout. Always exits 0 (advisory, never blocking).

set -euo pipefail

VAULT="<vault>"

# Parse input
INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_name',''))" 2>/dev/null || echo "")
FILE_PATH=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path',''))" 2>/dev/null || echo "")

# Only validate Write/Edit on .md files inside the vault
if [[ "$TOOL_NAME" != "Write" && "$TOOL_NAME" != "Edit" ]]; then
    exit 0
fi

if [[ ! "$FILE_PATH" == "$VAULT"/* ]] || [[ ! "$FILE_PATH" == *.md ]]; then
    exit 0
fi

# Skip non-content files
BASENAME=$(basename "$FILE_PATH")
if [[ "$BASENAME" == "MEMORY.md" || "$BASENAME" == "CLAUDE.md" || "$BASENAME" == "Dashboard.md" ]]; then
    exit 0
fi

# Check file exists and is readable
if [[ ! -f "$FILE_PATH" ]]; then
    exit 0
fi

WARNINGS=""

# Check frontmatter exists
if ! head -1 "$FILE_PATH" | grep -q "^---$"; then
    WARNINGS="${WARNINGS}[Vault QA] Missing YAML frontmatter in ${BASENAME}. "
fi

# Check specific frontmatter fields based on folder
REL_PATH="${FILE_PATH#$VAULT/}"

if [[ "$REL_PATH" == 20-Work/Meetings/* ]]; then
    for field in "type:" "date:" "people:"; do
        if ! grep -q "^$field" "$FILE_PATH" 2>/dev/null; then
            WARNINGS="${WARNINGS}[Vault QA] Meeting note ${BASENAME} missing: ${field%:}. "
        fi
    done
fi

if [[ "$REL_PATH" == 20-Work/Stakeholders/* ]]; then
    for field in "name:" "org:" "relationship:"; do
        if ! grep -q "^$field" "$FILE_PATH" 2>/dev/null; then
            WARNINGS="${WARNINGS}[Vault QA] Stakeholder file ${BASENAME} missing: ${field%:}. "
        fi
    done
fi

if [[ "$REL_PATH" == 40-Life/Hypomnemata/* ]]; then
    for field in "date:" "type:"; do
        if ! grep -q "^$field" "$FILE_PATH" 2>/dev/null; then
            WARNINGS="${WARNINGS}[Vault QA] Diary entry ${BASENAME} missing: ${field%:}. "
        fi
    done
fi

# Check wikilinks for files > 300 chars (content after frontmatter)
CONTENT_LENGTH=$(awk '/^---$/{if(++c==2){found=1;next}} found{print}' "$FILE_PATH" 2>/dev/null | wc -c | tr -d ' ')
if [[ "$CONTENT_LENGTH" -gt 300 ]]; then
    if ! grep -q '\[\[.*\]\]' "$FILE_PATH" 2>/dev/null; then
        WARNINGS="${WARNINGS}[Vault QA] ${BASENAME} has ${CONTENT_LENGTH} chars but no wikilinks. Consider linking to related notes. "
    fi
fi

if [[ -n "$WARNINGS" ]]; then
    echo "$WARNINGS"
fi

exit 0

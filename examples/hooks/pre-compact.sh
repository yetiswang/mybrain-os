#!/usr/bin/env bash
# PreCompact hook: save a compaction marker and remind Claude to preserve key context.
# Creates a timestamped file in 90-Archive/Sessions/ and prints a reminder to stdout.

set -euo pipefail

SESSIONS_DIR="<vault>/90-Archive/Sessions"
TIMESTAMP=$(date +%Y-%m-%d-%H%M%S)
MARKER_FILE="${SESSIONS_DIR}/${TIMESTAMP}-compact.md"

mkdir -p "$SESSIONS_DIR"

cat > "$MARKER_FILE" << EOF
---
type: session-compact
date: $(date +%Y-%m-%d)
time: $(date +%H:%M:%S)
---

# Context compaction at ${TIMESTAMP}

Session was compacted at this time. Key context should have been preserved by Claude before compaction.
EOF

# Retain only the 30 most recent session files
ls -t "$SESSIONS_DIR"/*.md 2>/dev/null | tail -n +31 | xargs rm -f 2>/dev/null || true

echo "[Pre-compact] Session marker saved. Before compaction, ensure key decisions, action items, and stakeholder context from this session are written to vault notes (not just held in conversation memory). Consider running /sexit to save agentic activity to 98-Context/Agentic-Log.md before context is lost."

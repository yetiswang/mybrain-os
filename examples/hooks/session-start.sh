#!/usr/bin/env bash
# SessionStart hook: inject dynamic vault context into Claude's session.

set -euo pipefail

VAULT="<vault>"
TODAY=$(date +%Y-%m-%d)

echo "[Session context — ${TODAY}]"

# ── 1. Current State (always) ─────────────────────────────────────────────
CURRENT_STATE="$VAULT/98-Context/Current-State.md"
if [[ -f "$CURRENT_STATE" ]]; then
    echo ""
    echo "Current State:"
    awk '/^---$/{if(++c==2){found=1;next}} found{print}' "$CURRENT_STATE"
fi

# ── 2. Projects Overview (always) ─────────────────────────────────────────
PROJECTS_OVERVIEW="$VAULT/98-Context/Projects-Overview.md"
if [[ -f "$PROJECTS_OVERVIEW" ]]; then
    echo ""
    echo "Projects Overview:"
    awk '/^---$/{if(++c==2){found=1;next}} found{print}' "$PROJECTS_OVERVIEW"
fi

# ── 3. Workflow command index (always) ────────────────────────────────────
echo ""
echo "Available slash commands:"
cat <<'EOF'
  /5pmsummary       — daily email/meeting digest + vault update
  /goodmorning      — morning briefing: calendar, priorities, risks
  /reflect          — weekly pattern synthesis (me + work patterns)
  /transcribe       — transcribe today's Voice Memos → vault
  /deep-research    — structured landscape investigation (outline→execute→report)
  /domain-radar     — monthly strategic literature sweep
  /domain-ask       — grounded Q&A from wiki knowledge
  /domain-lint      — wiki structural health check
  /paper-ingest     — Zotero paper ingestion → wiki
  /weixin-discover  — subscribe to WeChat 公众号 feeds
  /weixin-ingest    — compile new WeChat articles → wiki
  /email-search     — search 40K email archive (SQLite)
  /email-story      — relationship narrative from email archive
  /home-finance     — weekly finance update (Rabobank + market data)
  /sync-books       — Boox reading progress → My Books.md
  /vault-audit      — vault health: orphans, stale items, frontmatter
  /file-query       — research a question from vault, file answer to inbox
  /journal-reply    — append thoughtful reply to today's diary entry
  /sexit            — session exit: snapshot current state
EOF

# ── 4. <MyProject> status + strategic context ──────────────────────────
PROJECT_FILE="$VAULT/30-Projects/<MyProject>/<MyProject>.md"
if [[ -f "$PROJECT_FILE" ]]; then
    echo ""
    echo "<MyProject> — Status at a Glance:"
    awk '/^## Status at a Glance/,/^---/' "$PROJECT_FILE" | head -20

    echo ""
    echo "<MyProject> — Key Strategic Context:"
    awk '/^## Key Strategic Context/,/^---/' "$PROJECT_FILE" | head -25
fi

# ── 4b. <peer-network> status + open actions ────────────────────────────────────────
PEER_NETWORK_FILE="$VAULT/30-Projects/<peer-network>.md"
if [[ -f "$PEER_NETWORK_FILE" ]]; then
    echo ""
    echo "<peer-network> — Status at a Glance:"
    awk '/^## Status at a Glance/,/^---/' "$PEER_NETWORK_FILE" | head -15

    echo ""
    echo "<peer-network> — Open Actions:"
    awk '/^## Open Actions/,/^---/' "$PEER_NETWORK_FILE" | grep -E "^\- \[ \]" | head -10
fi

# ── 5. Dashboard open actions ─────────────────────────────────────────────
DASHBOARD="$VAULT/Dashboard.md"
if [[ -f "$DASHBOARD" ]]; then
    TOTAL_OPEN=$(grep -cE "^\- \[ \]" "$DASHBOARD" 2>/dev/null || echo "0")
    OPEN_ACTIONS=$(grep -E "^\- \[ \]" "$DASHBOARD" 2>/dev/null | head -30)
    if [[ -n "$OPEN_ACTIONS" ]]; then
        echo ""
        if [[ "$TOTAL_OPEN" -gt 30 ]]; then
            echo "Open Dashboard actions (showing 30 of ${TOTAL_OPEN} total):"
        else
            echo "Open Dashboard actions (${TOTAL_OPEN} total):"
        fi
        echo "$OPEN_ACTIONS"
    fi
fi

# ── 5b. Stakeholder index (top 20 active) ────────────────────────────────
STAKEHOLDER_INDEX="$VAULT/20-Work/Stakeholders/INDEX.md"
if [[ -f "$STAKEHOLDER_INDEX" ]]; then
    echo ""
    echo "Stakeholders:"
    # Print summary line
    grep -E "^Total:" "$STAKEHOLDER_INDEX" || true
    # Print table header + top 20 active rows
    awk '/^## Active/,/^## /' "$STAKEHOLDER_INDEX" | head -25
fi

# ── 6. Latest 5pm summary — title + highlights only ───────────────────────
LATEST_SUMMARY=$(ls -t "$VAULT/00-Inbox/"*5pm-summary.md 2>/dev/null | head -1)
if [[ -n "$LATEST_SUMMARY" ]]; then
    SUMMARY_DATE=$(basename "$LATEST_SUMMARY" | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}')
    echo ""
    echo "Latest 5pm summary (${SUMMARY_DATE}) — highlights:"
    awk '/^---$/{if(++c==2){found=1;next}} found{print}' "$LATEST_SUMMARY" | head -12
fi

# ── 7. Today's inbox items (filenames) ────────────────────────────────────
TODAY_FILES=$(ls "$VAULT/00-Inbox/${TODAY}"* 2>/dev/null || true)
if [[ -n "$TODAY_FILES" ]]; then
    echo ""
    echo "Today's inbox items:"
    while IFS= read -r f; do
        echo "  $(basename "$f")"
    done <<< "$TODAY_FILES"
fi

# ── 8. Recently modified vault files (last 48h, capped at 10) ─────────────
RECENT_FILES=$(find "$VAULT" -name "*.md" -mtime -2 \
    -not -path "*/00-Inbox/*" \
    -not -path "*/90-Archive/*" \
    -not -path "*/.claude/*" \
    -not -path "*/98-Context/*" \
    -not -path "*/30-Projects/<MyProject>/<MyProject>.md" \
    2>/dev/null | sort | head -10)

if [[ -n "$RECENT_FILES" ]]; then
    echo ""
    echo "Recently modified vault files (last 48h):"
    while IFS= read -r f; do
        RELPATH="${f#$VAULT/}"
        MODTIME=$(date -r "$f" "+%Y-%m-%d %H:%M")
        echo "  [${MODTIME}] ${RELPATH}"
    done <<< "$RECENT_FILES"
fi

# ── 9. Last agentic session ───────────────────────────────────────────────
AGENTIC_LOG="$VAULT/98-Context/Agentic-Log.md"
if [[ -f "$AGENTIC_LOG" ]]; then
    LATEST_BLOCK=$(awk '
        /^---$/ { sep++; if(sep==3) start=1; if(sep==4) exit; next }
        start { print }
    ' "$AGENTIC_LOG")
    if [[ -n "$LATEST_BLOCK" ]]; then
        echo ""
        echo "Last agentic session:"
        echo "$LATEST_BLOCK"
    fi
fi

# ── 10. Latest wiki activity ──────────────────────────────────────────────
WIKI_LOG="$VAULT/10-Research/wiki/log.md"
if [[ -f "$WIKI_LOG" ]]; then
    WIKI_LATEST=$(awk '
        /^## [0-9]{4}-[0-9]{2}-[0-9]{2}/ {
            if (found) exit
            found=1; print; next
        }
        found { print }
    ' "$WIKI_LOG")
    if [[ -n "$WIKI_LATEST" ]]; then
        echo ""
        echo "Latest wiki activity:"
        echo "$WIKI_LATEST" | head -8
    fi
fi

# ── 11. GitHub repo status ───────────────────────────────────────────────
echo ""
echo "GitHub repo status:"

# watcher scripts (in <watcher-dir>/)
VAULT_WATCHER="$HOME/.local/share/vault-watcher"
if [[ -d "$VAULT_WATCHER/.git" ]]; then
    echo "  watcher scripts (<watcher-dir>/):"
    cd "$VAULT_WATCHER"
    git log --oneline -3 2>/dev/null | sed 's/^/    /'
    DIRTY=$(git status --short 2>/dev/null | { grep -v "^??" || true; } | wc -l | tr -d ' ')
    UNTRACKED=$(git status --short 2>/dev/null | { grep "^??" || true; } | wc -l | tr -d ' ')
    if [[ "$DIRTY" -gt 0 ]]; then echo "    ⚠ ${DIRTY} modified/staged file(s)"; fi
    if [[ "$UNTRACKED" -gt 0 ]]; then echo "    · ${UNTRACKED} untracked file(s)"; fi
    cd - > /dev/null
fi

# Adapt this block to your own external sources, or remove if unused.
# <funder-programme>_project_charter (Overleaf ↔ GitHub sync)
CHARTER_DIR="$HOME/Library/CloudStorage/Dropbox/InfrastructureStrategy/Roadmaps/ProjectDocuments/<funder-programme>_project_charter"
if [[ -d "$CHARTER_DIR/.git" ]]; then
    echo "  <funder-programme>_project_charter (Dropbox clone):"
    cd "$CHARTER_DIR"
    git log --oneline -2 2>/dev/null | sed 's/^/    /'
    DIRTY=$(git status --short 2>/dev/null | { grep -v "^??" || true; } | wc -l | tr -d ' ')
    if [[ "$DIRTY" -gt 0 ]]; then echo "    ⚠ ${DIRTY} modified/staged file(s) — pull from Overleaf/GitHub before editing"; fi
    cd - > /dev/null
fi

# <MyProject> + <funder-programme>-presentation (no local clone — GitHub API)
GH=/opt/homebrew/bin/gh
if [[ -x "$GH" ]]; then
    JQ='.sha[0:7] + " " + (.commit.message | split("\n")[0][0:72]) + " (" + .commit.author.date[0:10] + ")"'
    DISCO=$($GH api repos/<github-org>/<MyProject>/commits/main --jq "$JQ" 2>/dev/null || true)
    if [[ -n "$DISCO" ]]; then
        echo "  <MyProject> / <project-domain> (GitHub Pages):"
        echo "    ${DISCO}"
    fi
    PRESENTATION=$($GH api repos/<github-org>/<funder-programme>-presentation/commits/main --jq "$JQ" 2>/dev/null || true)
    if [[ -n "$PRESENTATION" ]]; then
        echo "  <funder-programme>-presentation (GitHub Pages):"
        echo "    ${PRESENTATION}"
    fi
fi

# ── 12. Personal and work patterns (capped at 50 lines each) ─────────────
# Memory dir: ~/.claude/projects/<hashed-vault-path>/memory
# The path hash is derived from your vault's absolute path — check with: claude project list
MEMORY_DIR="$HOME/.claude/projects/<hashed-vault-path>/memory"

ME_PATTERNS="$MEMORY_DIR/me_patterns.md"
WORK_PATTERNS="$MEMORY_DIR/work_patterns.md"

if [[ -f "$ME_PATTERNS" ]]; then
    echo ""
    echo "Personal patterns (recent):"
    awk '/^---$/{if(++c==2){found=1;next}} found{print}' "$ME_PATTERNS" | head -50
fi

if [[ -f "$WORK_PATTERNS" ]]; then
    echo ""
    echo "Work patterns (recent):"
    awk '/^---$/{if(++c==2){found=1;next}} found{print}' "$WORK_PATTERNS" | head -50
fi

exit 0

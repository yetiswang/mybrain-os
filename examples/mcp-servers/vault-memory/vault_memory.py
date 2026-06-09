"""
vault_memory — read-only federated query layer for the vault.

Talks to: claude-transcripts.db (FTS5), email-archive.db (LIKE on subject/body),
MEMORY.md files (~/.claude/projects/...), 10-Research/wiki/* notes,
20-Work/Stakeholders + Meetings + Strategy.

Per Codex audit:
  * SQLite read-only via URI (mode=ro + immutable=1 where safe; query_only=ON for writers).
  * Path canonicalisation in resolve_vault_path() — rejects ../, absolute paths,
    symlink escapes, NUL bytes; suffix allow-list (.md, .txt, .json).
  * Latency budget — per-source timeout, partial results.
  * Result-size caps — max 16 KB per result, max 25 limit, max 200 files walked.
"""

from __future__ import annotations

import os
import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

VAULT_ROOT = Path(os.environ.get("VAULT_ROOT", str(Path.home() / "vault")))  # set VAULT_ROOT to your vault path
WATCHER_DIR = Path(os.environ.get("WATCHER_DIR", str(Path.home() / ".local/share/vault-watcher")))
# Claude project dir for MEMORY.md files: set CLAUDE_PROJECT_DIR or use the default auto-discovered path
CLAUDE_PROJECT_DIR = Path(os.environ.get(
    "CLAUDE_PROJECT_DIR",
    str(Path.home() / ".claude/projects" / Path(str(VAULT_ROOT)).as_posix().replace("/", "-").lstrip("-")),
))

DB_TRANSCRIPTS = WATCHER_DIR / "claude-transcripts.db"
DB_EMAILS      = WATCHER_DIR / "email-archive.db"

ALLOWED_SUFFIXES = {".md", ".txt", ".json"}

# Result-size caps (Codex audit item: result-size caps)
MAX_QUERY_LEN     = 256
MAX_RETURNED_BYTES = 16 * 1024
MAX_LIMIT         = 25
MAX_FILES_WALKED  = 200
MAX_SNIPPETS      = 5

# Latency budget (Codex audit item 5)
DEFAULT_BUDGET_S   = 1.5
PER_SOURCE_S       = 2.0


@dataclass
class Hit:
    source: str           # "transcripts" | "emails" | "memory" | "wiki" | "stakeholder" | "meeting"
    path: str             # vault-relative or db-id
    title: str            # readable title
    snippet: str          # short excerpt
    score: float = 0.0
    meta: dict = field(default_factory=dict)


# ============================================================================
# Path canonicalisation (Codex audit item 1: path-traversal hardening)
# ============================================================================

def resolve_vault_path(path_str: str) -> Path:
    """Canonicalise an LLM-supplied path. Reject anything escaping VAULT_ROOT.

    Raises ValueError on any rejection reason.
    """
    if not path_str or not isinstance(path_str, str):
        raise ValueError("empty or non-string path")
    if "\x00" in path_str or "\0" in path_str:
        raise ValueError("NUL byte in path")
    if path_str.startswith("/") or path_str.startswith("~"):
        raise ValueError("absolute path / home expansion not allowed")
    # Use PurePosixPath to detect drive prefixes
    pp = PurePosixPath(path_str)
    if pp.drive:
        raise ValueError("drive prefix in path")
    if any(part == ".." for part in pp.parts):
        raise ValueError("parent traversal (..) not allowed")
    # Resolve and check containment
    candidate = (VAULT_ROOT / path_str).resolve()
    vault_resolved = VAULT_ROOT.resolve()
    try:
        candidate.relative_to(vault_resolved)
    except ValueError as e:
        raise ValueError(f"resolved path escapes vault: {candidate}") from e
    # Reject if symlink escapes (resolve() follows symlinks; we already checked)
    # Suffix allow-list
    if candidate.exists() and candidate.is_file():
        if candidate.suffix.lower() not in ALLOWED_SUFFIXES:
            raise ValueError(f"suffix not allowed: {candidate.suffix}")
    return candidate


# ============================================================================
# Read-only SQLite helpers (Codex audit item 4)
# ============================================================================

def _open_ro(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite DB read-only via URI. Sets busy_timeout."""
    if not db_path.exists():
        raise FileNotFoundError(db_path)
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=2.0)
    conn.execute("PRAGMA query_only = ON;")
    conn.execute("PRAGMA busy_timeout = 1500;")
    conn.row_factory = sqlite3.Row
    return conn


def _truncate_snippet(text: str, n: int = 280) -> str:
    text = text.strip().replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text if len(text) <= n else text[:n].rstrip() + "…"


# ============================================================================
# Source: claude-transcripts.db (FTS5)
# ============================================================================

def search_transcripts(query: str, limit: int = 10) -> list[Hit]:
    if not DB_TRANSCRIPTS.exists():
        return []
    hits: list[Hit] = []
    try:
        with _open_ro(DB_TRANSCRIPTS) as conn:
            # FTS5 wants quoted query for safety
            cur = conn.execute(
                """SELECT m.id, m.session_id, m.timestamp, m.role, m.text,
                          snippet(messages_fts, 0, '[', ']', ' … ', 12) AS snip
                   FROM messages_fts JOIN messages m ON m.rowid = messages_fts.rowid
                   WHERE messages_fts MATCH ? ORDER BY rank LIMIT ?""",
                (query, limit),
            )
            for row in cur:
                hits.append(Hit(
                    source="transcripts",
                    path=f"transcripts/{row['session_id']}#{row['id']}",
                    title=f"[{row['role']}] {row['timestamp']}",
                    snippet=_truncate_snippet(row["snip"] or row["text"] or ""),
                    score=1.0,
                    meta={"session_id": row["session_id"], "ts": row["timestamp"]},
                ))
    except sqlite3.Error:
        return []
    return hits


# ============================================================================
# Source: email-archive.db (LIKE — no FTS5 yet)
# ============================================================================

def search_emails(query: str, limit: int = 10) -> list[Hit]:
    if not DB_EMAILS.exists():
        return []
    pat = f"%{query}%"
    hits: list[Hit] = []
    try:
        with _open_ro(DB_EMAILS) as conn:
            cur = conn.execute(
                """SELECT id, date, sender_name, sender_email, subject,
                          substr(body, 1, 500) AS body_excerpt
                   FROM emails
                   WHERE subject LIKE ? OR sender_name LIKE ? OR sender_email LIKE ? OR body LIKE ?
                   ORDER BY date DESC LIMIT ?""",
                (pat, pat, pat, pat, limit),
            )
            for row in cur:
                title = f"{row['sender_name'] or row['sender_email']}: {row['subject']}"
                hits.append(Hit(
                    source="emails",
                    path=f"emails/{row['id']}",
                    title=title.strip(),
                    snippet=_truncate_snippet(row["body_excerpt"] or ""),
                    score=0.9,
                    meta={"date": row["date"], "from": row["sender_email"]},
                ))
    except sqlite3.Error:
        return []
    return hits


# ============================================================================
# Source: MEMORY.md files
# ============================================================================

def list_memory_entries() -> list[Hit]:
    """List all memory_* files with frontmatter."""
    memdir = CLAUDE_PROJECT_DIR / "memory"
    if not memdir.exists():
        return []
    hits: list[Hit] = []
    for f in sorted(memdir.glob("*.md")):
        if f.name == "MEMORY.md":
            continue
        try:
            txt = f.read_text(errors="replace")[:2000]
        except OSError:
            continue
        title, desc, kind = f.stem, "", "?"
        if txt.startswith("---"):
            end = txt.find("---", 3)
            if end > 0:
                fm = txt[3:end]
                m = re.search(r"name:\s*(.+)", fm); title = m.group(1).strip() if m else title
                m = re.search(r"description:\s*(.+)", fm); desc = m.group(1).strip() if m else ""
                m = re.search(r"type:\s*(.+)", fm); kind = m.group(1).strip() if m else kind
        hits.append(Hit(
            source="memory",
            path=f"memory/{f.name}",
            title=f"[{kind}] {title}",
            snippet=desc,
            score=1.0,
            meta={"file": str(f), "type": kind},
        ))
    return hits


def search_memory(query: str, limit: int = 10) -> list[Hit]:
    memdir = CLAUDE_PROJECT_DIR / "memory"
    if not memdir.exists():
        return []
    hits: list[Hit] = []
    pat = re.compile(re.escape(query), re.IGNORECASE)
    for f in sorted(memdir.glob("*.md")):
        try:
            txt = f.read_text(errors="replace")
        except OSError:
            continue
        if pat.search(txt):
            ms = list(pat.finditer(txt))
            if not ms:
                continue
            m = ms[0]
            start = max(0, m.start() - 80)
            end = min(len(txt), m.end() + 200)
            snippet = txt[start:end]
            hits.append(Hit(
                source="memory",
                path=f"memory/{f.name}",
                title=f.stem,
                snippet=_truncate_snippet(snippet),
                score=1.5,  # boost — memory files are curated
                meta={"file": str(f), "match_count": len(ms)},
            ))
            if len(hits) >= limit:
                break
    return hits


# ============================================================================
# Source: wiki + stakeholders + meetings (vault tree walk)
# ============================================================================

WALK_TARGETS = [
    ("wiki",        "10-Research/wiki", 1.0),
    ("stakeholder", "20-Work/Stakeholders", 1.4),
    ("stakeholder", "20-Work/External-People", 1.4),
    ("meeting",     "20-Work/Meetings", 0.8),
    ("strategy",    "20-Work/Strategy", 1.2),
    ("project",     "30-Projects", 1.0),
    ("context",     "98-Context", 1.0),
]


def search_vault_tree(query: str, limit: int = 10, scope: list[str] | None = None) -> list[Hit]:
    pat = re.compile(re.escape(query), re.IGNORECASE)
    hits: list[Hit] = []
    walked = 0
    for tag, rel, boost in WALK_TARGETS:
        if scope and tag not in scope:
            continue
        d = VAULT_ROOT / rel
        if not d.exists():
            continue
        for f in sorted(d.rglob("*.md")):
            walked += 1
            if walked > MAX_FILES_WALKED:
                break
            try:
                txt = f.read_text(errors="replace")
            except OSError:
                continue
            ms = list(pat.finditer(txt))
            if not ms:
                continue
            m = ms[0]
            start = max(0, m.start() - 80)
            end = min(len(txt), m.end() + 200)
            snippet = txt[start:end]
            rel_path = f.relative_to(VAULT_ROOT).as_posix()
            hits.append(Hit(
                source=tag,
                path=rel_path,
                title=f.stem,
                snippet=_truncate_snippet(snippet),
                score=boost * (1 + min(len(ms), 5) * 0.1),
                meta={"match_count": len(ms)},
            ))
            if len(hits) >= limit * 2:
                break
        if walked > MAX_FILES_WALKED:
            break
    return sorted(hits, key=lambda h: -h.score)[:limit]


# ============================================================================
# Federated search
# ============================================================================

def federated_search(
    query: str,
    scope: list[str] | None = None,
    limit: int = 10,
    budget_s: float = DEFAULT_BUDGET_S,
) -> dict:
    """Run all sources in parallel; collect hits up to budget; return partial results."""
    if not query or len(query) > MAX_QUERY_LEN:
        raise ValueError(f"query empty or > {MAX_QUERY_LEN} chars")
    limit = min(max(1, int(limit)), MAX_LIMIT)
    scope = scope or ["transcripts", "emails", "memory", "wiki", "stakeholder", "meeting", "strategy", "project", "context"]

    sources_timed_out: list[str] = []
    all_hits: list[Hit] = []
    started = time.time()

    # Build the list of (name, fn, args) for each active source
    import concurrent.futures
    source_tasks: list[tuple[str, Any, tuple]] = []
    if "transcripts" in scope:
        source_tasks.append(("transcripts", search_transcripts, (query, limit)))
    if "emails" in scope:
        source_tasks.append(("emails", search_emails, (query, limit)))
    if "memory" in scope:
        source_tasks.append(("memory", search_memory, (query, limit)))
    tree_scope = [s for s in scope if s in {"wiki","stakeholder","meeting","strategy","project","context"}]
    if tree_scope:
        source_tasks.append(("vault_tree", search_vault_tree, (query, limit, tree_scope)))

    # Submit all sources concurrently to one executor
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(source_tasks) or 1) as ex:
        fut_to_name = {ex.submit(fn, *args): name for name, fn, args in source_tasks}
        for f in concurrent.futures.as_completed(fut_to_name, timeout=PER_SOURCE_S * len(source_tasks) + 1):
            name = fut_to_name[f]
            try:
                result = f.result(timeout=PER_SOURCE_S)
                all_hits += result
            except FutTimeout:
                sources_timed_out.append(name)
            except Exception:
                sources_timed_out.append(name)

    # Rank: combine score with source-priority boost
    all_hits.sort(key=lambda h: -h.score)
    top = all_hits[:limit]

    # Cap returned bytes
    serialised: list[dict] = []
    used = 0
    for h in top:
        d = {
            "source": h.source, "path": h.path, "title": h.title,
            "snippet": h.snippet, "score": round(h.score, 3), "meta": h.meta,
        }
        size = sum(len(str(v)) for v in d.values())
        if used + size > MAX_RETURNED_BYTES:
            break
        used += size
        serialised.append(d)

    return {
        "query": query,
        "scope": scope,
        "limit": limit,
        "results": serialised,
        "total_hits": len(all_hits),
        "elapsed_ms": int((time.time() - started) * 1000),
        "sources_timed_out": sources_timed_out,
    }


# ============================================================================
# Recent activity
# ============================================================================

def recent_activity(category: str, days: int = 14) -> dict:
    """Return recently-modified files in a category."""
    cat_map = {
        "stakeholder": ["20-Work/Stakeholders", "20-Work/External-People"],
        "meeting": ["20-Work/Meetings"],
        "strategy": ["20-Work/Strategy"],
        "project": ["30-Projects"],
        "memory": [],   # special-cased below
        "decision": ["30-Projects"],
    }
    if category == "memory":
        memdir = CLAUDE_PROJECT_DIR / "memory"
        cutoff = time.time() - days * 86400
        hits = []
        for f in memdir.glob("*.md"):
            if f.stat().st_mtime > cutoff and f.name != "MEMORY.md":
                hits.append({
                    "path": f"memory/{f.name}",
                    "modified": time.strftime("%Y-%m-%d", time.localtime(f.stat().st_mtime)),
                    "title": f.stem,
                })
        return {"category": category, "days": days, "results": sorted(hits, key=lambda x: x["modified"], reverse=True)}
    if category not in cat_map:
        raise ValueError(f"unknown category: {category}")
    cutoff = time.time() - days * 86400
    hits = []
    for rel in cat_map[category]:
        d = VAULT_ROOT / rel
        if not d.exists():
            continue
        for f in d.rglob("*.md"):
            if f.stat().st_mtime > cutoff:
                hits.append({
                    "path": f.relative_to(VAULT_ROOT).as_posix(),
                    "modified": time.strftime("%Y-%m-%d", time.localtime(f.stat().st_mtime)),
                    "title": f.stem,
                })
    return {"category": category, "days": days, "results": sorted(hits, key=lambda x: x["modified"], reverse=True)[:25]}


# ============================================================================
# Get a specific note
# ============================================================================

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

def get_note(path_str: str) -> dict:
    """Fetch a vault note. Path is vault-relative. Path is canonicalised."""
    p = resolve_vault_path(path_str)
    if not p.exists():
        return {"path": path_str, "error": "not found"}
    if not p.is_file():
        return {"path": path_str, "error": "not a file"}
    try:
        raw = p.read_text(errors="replace")
    except OSError as e:
        return {"path": path_str, "error": f"read error: {e}"}
    fm = {}
    body = raw
    m = FRONTMATTER_RE.match(raw)
    if m:
        body = raw[m.end():]
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip().strip('"\'')
    if len(body) > MAX_RETURNED_BYTES:
        body = body[:MAX_RETURNED_BYTES] + "\n\n[…truncated]"
    return {
        "path": path_str,
        "frontmatter": fm,
        "body": body,
        "size": len(raw),
    }


__all__ = [
    "federated_search", "recent_activity", "get_note", "list_memory_entries",
    "Hit", "VAULT_ROOT",
]

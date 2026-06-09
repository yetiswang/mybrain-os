#!/usr/bin/env python3.13
"""
mem_mcp_server — stdio MCP server for vault memory.

Exposes 4 read-only tools (mem_search, mem_get, mem_recent, mem_list_memory),
each routed through safe_redact() at the boundary.

Per Codex audit hardening:
  * Whole-object redaction (paths, titles, snippets, frontmatter)
  * Hashed query logging (raw queries never written to log)
  * Logs at 0600, separate operational vs content streams
  * mode='off' removed from public schema
  * Result-size caps applied in vault_memory layer
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

VAULT_CHROMA_BIN = Path.home() / ".local/share/vault-chroma/bin/vault-search"
VAULT_CHROMA_FOLDERS = {"meetings", "stakeholders", "projects", "diary", "5pm-summary"}
SEMANTIC_TIMEOUT = 8.0

# Make local module imports work
sys.path.insert(0, str(Path(__file__).parent))

from privacy_filter import safe_redact, PrivacyConfig, REDACT_SENTINEL
import vault_memory as vm

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

VAULT_AGENT = os.environ.get("VAULT_AGENT", "unknown")
WATCHER_DIR = Path.home() / ".local/share/vault-watcher"
LOG_DIR = WATCHER_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
ACCESS_LOG = LOG_DIR / "mcp_access.log"
REDACT_LOG = LOG_DIR / "privacy_redactions.log"
OP_LOG     = LOG_DIR / "mcp_operational.log"

LOG_SALT = os.environ.get("VAULT_LOG_SALT", "my-vault-salt")  # local salt for query hashing; override via env var

for p in (ACCESS_LOG, REDACT_LOG, OP_LOG):
    if not p.exists():
        p.touch(mode=0o600)
    else:
        try:
            p.chmod(0o600)
        except OSError:
            pass


def _hash_query(q: str) -> str:
    return hashlib.sha256((LOG_SALT + q).encode()).hexdigest()[:16]


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _log_access(tool: str, args: dict, redaction_count: int, status: str, elapsed_ms: int) -> None:
    """Log every MCP call. Query strings are hashed, not stored."""
    safe_args: dict = {}
    for k, v in args.items():
        if isinstance(v, str):
            if k in ("query", "path", "name"):
                safe_args[k + "_hash"] = _hash_query(v)
                safe_args[k + "_len"] = len(v)
            else:
                safe_args[k] = v[:32]
        else:
            safe_args[k] = v
    line = json.dumps({
        "ts": _now(),
        "agent": VAULT_AGENT,
        "tool": tool,
        "args": safe_args,
        "redactions": redaction_count,
        "status": status,
        "elapsed_ms": elapsed_ms,
    }, sort_keys=True) + "\n"
    with ACCESS_LOG.open("a") as f:
        f.write(line)


def _log_redactions(tool: str, log) -> None:
    if not log or not log.redactions:
        return
    counts: dict[str, int] = {}
    for r in log.redactions:
        counts[r.pattern] = counts.get(r.pattern, 0) + 1
    line = json.dumps({
        "ts": _now(),
        "agent": VAULT_AGENT,
        "tool": tool,
        "patterns": counts,
        "total": len(log.redactions),
    }, sort_keys=True) + "\n"
    with REDACT_LOG.open("a") as f:
        f.write(line)


def _log_op(level: str, msg: str) -> None:
    line = json.dumps({"ts": _now(), "agent": VAULT_AGENT, "level": level, "msg": msg}) + "\n"
    with OP_LOG.open("a") as f:
        f.write(line)


# ============================================================================
# MCP server setup
# ============================================================================

server = Server("vault-memory")

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="mem_search",
            description=(
                "Federated search across the vault: claude transcripts (FTS5), "
                "email archive, MEMORY.md files, wiki, stakeholders, meetings, "
                "strategy, projects. Returns ranked hits with provenance. "
                "Output is privacy-filtered (mode=strict by default; "
                "lenient bypasses currency under EUR 1M and allow-listed email domains)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (plain text or FTS5 expression)."},
                    "scope": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["transcripts","emails","memory","wiki","stakeholder","meeting","strategy","project","context"]},
                        "description": "Restrict to listed sources (default: all).",
                    },
                    "limit": {"type": "integer", "minimum": 1, "maximum": 25, "default": 10},
                    "mode": {"type": "string", "enum": ["strict","lenient"], "default": "strict"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="mem_get",
            description=(
                "Fetch a specific vault note by vault-relative path "
                "(e.g. '20-Work/Stakeholders/Jane-Doe.md'). "
                "Path is canonicalised — absolute paths, parent traversal, "
                "and non-vault paths are rejected. Output is privacy-filtered."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Vault-relative path."},
                    "mode": {"type": "string", "enum": ["strict","lenient"], "default": "strict"},
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="mem_recent",
            description=(
                "List recently-modified files in a category. "
                "Categories: stakeholder, meeting, strategy, project, memory."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": ["stakeholder","meeting","strategy","project","memory","decision"]},
                    "days": {"type": "integer", "minimum": 1, "maximum": 90, "default": 14},
                    "mode": {"type": "string", "enum": ["strict","lenient"], "default": "strict"},
                },
                "required": ["category"],
            },
        ),
        Tool(
            name="mem_semantic_search",
            description=(
                "Semantic (meaning-based) search over the vault via the local "
                "ChromaDB index. Indexed scope: meetings, stakeholders, projects, "
                "diary, 5pm-summary. Use this when keyword search (mem_search) "
                "would miss synonyms or paraphrases — e.g. 'the call with the dean "
                "of FNWI' instead of exact names. Output is privacy-filtered."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural-language query."},
                    "k": {"type": "integer", "minimum": 1, "maximum": 25, "default": 5},
                    "folder": {
                        "type": "string",
                        "enum": ["meetings","stakeholders","projects","diary","5pm-summary"],
                        "description": "Optional restriction to one indexed folder.",
                    },
                    "mode": {"type": "string", "enum": ["strict","lenient"], "default": "strict"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="mem_list_memory",
            description=(
                "List all auto-memory entries (user_*, feedback_*, project_*, reference_*) "
                "with their frontmatter (name, type, description). Use this to orient "
                "before querying — it shows what kinds of memory exist."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "enum": ["strict","lenient"], "default": "strict"},
                },
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    started = time.time()
    mode = arguments.get("mode", "strict")
    if mode not in ("strict", "lenient"):
        mode = "strict"
    cfg = None
    try:
        cfg = PrivacyConfig.load()
    except RuntimeError as e:
        _log_op("ERROR", f"privacy config load failed: {e}")
        return [TextContent(type="text", text=json.dumps({"error": "privacy config load failed; aborting"}))]

    raw_result = None
    try:
        if name == "mem_search":
            query = arguments["query"]
            scope = arguments.get("scope")
            limit = int(arguments.get("limit", 10))
            raw_result = vm.federated_search(query, scope=scope, limit=limit)
        elif name == "mem_get":
            path = arguments["path"]
            raw_result = vm.get_note(path)
        elif name == "mem_recent":
            category = arguments["category"]
            days = int(arguments.get("days", 14))
            raw_result = vm.recent_activity(category, days=days)
        elif name == "mem_list_memory":
            entries = vm.list_memory_entries()
            raw_result = {"results": [
                {"source": h.source, "path": h.path, "title": h.title,
                 "snippet": h.snippet, "score": h.score, "meta": h.meta}
                for h in entries
            ], "total": len(entries)}
        elif name == "mem_semantic_search":
            query = arguments["query"]
            k = int(arguments.get("k", 5))
            folder = arguments.get("folder")
            if not VAULT_CHROMA_BIN.exists():
                raw_result = {"results": [], "total": 0,
                              "error": "vault-chroma CLI not found",
                              "expected_at": str(VAULT_CHROMA_BIN)}
            else:
                cmd = [str(VAULT_CHROMA_BIN), query, "-k", str(k), "--json"]
                if folder:
                    if folder not in VAULT_CHROMA_FOLDERS:
                        raw_result = {"results": [], "total": 0,
                                      "error": f"invalid folder: {folder}"}
                        cmd = None
                    else:
                        cmd += ["--folder", folder]
                if cmd is not None:
                    try:
                        proc = subprocess.run(
                            cmd, capture_output=True, text=True,
                            timeout=SEMANTIC_TIMEOUT, check=False
                        )
                        if proc.returncode != 0:
                            raw_result = {"results": [], "total": 0,
                                          "error": "vault-search returned nonzero",
                                          "stderr": proc.stderr.strip()[:500]}
                        else:
                            data = json.loads(proc.stdout) if proc.stdout.strip() else []
                            hits = [
                                {"source": "vault-chroma",
                                 "path": h.get("path", ""),
                                 "title": h.get("heading") or h.get("path", ""),
                                 "snippet": (h.get("text") or "")[:600],
                                 "score": h.get("score", 0.0),
                                 "meta": {"folder": h.get("folder"),
                                          "id": h.get("id")}}
                                for h in (data or [])
                            ]
                            raw_result = {"query": query, "k": k, "folder": folder,
                                          "results": hits, "total": len(hits)}
                    except subprocess.TimeoutExpired:
                        raw_result = {"results": [], "total": 0, "error": "semantic search timed out"}
                    except json.JSONDecodeError as e:
                        raw_result = {"results": [], "total": 0,
                                      "error": f"invalid JSON from vault-search: {e}"}
        else:
            return [TextContent(type="text", text=json.dumps({"error": f"unknown tool: {name}"}))]
    except Exception as e:
        _log_op("ERROR", f"{name}: {type(e).__name__}: {e}")
        elapsed = int((time.time() - started) * 1000)
        _log_access(name, arguments, 0, "error", elapsed)
        return [TextContent(type="text", text=json.dumps({"error": f"tool failed: {type(e).__name__}: {e}"}))]

    # FAIL-CLOSED redaction at boundary (Codex item 10)
    redacted, log = safe_redact(raw_result, mode=mode, config=cfg)
    elapsed = int((time.time() - started) * 1000)
    _log_redactions(name, log)
    if redacted == REDACT_SENTINEL:
        _log_op("ERROR", f"{name}: privacy filter raised: {log.error}")
        _log_access(name, arguments, 0, "redact-failed", elapsed)
        return [TextContent(type="text", text=json.dumps({"error": REDACT_SENTINEL, "detail": log.error}))]

    _log_access(name, arguments, log.count, "ok", elapsed)
    return [TextContent(type="text", text=json.dumps(redacted, default=str))]


async def main():
    _log_op("INFO", f"server starting; agent={VAULT_AGENT} pid={os.getpid()}")
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        _log_op("FATAL", f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
        sys.exit(1)

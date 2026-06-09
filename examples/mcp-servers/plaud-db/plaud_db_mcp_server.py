#!/usr/bin/env python3.13
"""
plaud_db_mcp_server — stdio MCP server exposing a SQLite + FTS5 corpus of
meeting transcripts (produced by the local Plaud -> mlx-whisper -> pyannote
pipeline in examples/meeting-capture/) to any MCP-aware agent.

Tools:
- transcript_search       — FTS5 trigram search across all meeting segments
- transcript_list_meetings— list all ingested meetings (id, date, title, speakers)
- transcript_get_meeting  — pull all segments of a single meeting by id

Point PLAUD_DB_PATH at the SQLite file your ingestion pipeline populates.
Schema is documented inline. Read-only.

Created 2026-06-01 during canonical-DB consolidation.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

CANONICAL_DB = Path(
    os.environ.get("PLAUD_DB_PATH", str(Path.home() / ".local/share/plaud/transcripts.db"))
).expanduser()

AGENT = os.environ.get("PLAUD_DB_AGENT", os.environ.get("VAULT_AGENT", "unknown"))

server = Server("plaud-db")


def _connect() -> sqlite3.Connection:
    if not CANONICAL_DB.exists():
        raise RuntimeError(
            f"Plaud transcripts DB not found at {CANONICAL_DB}. "
            "Set PLAUD_DB_PATH env var to point at your transcripts.db."
        )
    conn = sqlite3.connect(str(CANONICAL_DB))
    conn.row_factory = sqlite3.Row
    return conn


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="transcript_search",
            description=(
                "Full-text trigram search across all locally-ingested Plaud meeting transcripts. "
                "Returns matching segments with speaker label/name and timestamps. "
                "Supports ZH + EN code-switched content via the trigram tokenizer. "
                "Optional: speaker filters to a single speaker; since/until bound the date range."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search string (substring across content)."},
                    "speaker": {"type": "string", "description": "Filter to a speaker by real-name OR speaker label."},
                    "since": {"type": "string", "description": "Inclusive lower-bound date YYYY-MM-DD."},
                    "until": {"type": "string", "description": "Inclusive upper-bound date YYYY-MM-DD."},
                    "limit": {"type": "integer", "default": 30, "description": "Max segments to return (cap 200)."},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="transcript_list_meetings",
            description=(
                "List all ingested meetings in the canonical Plaud corpus. "
                "Reverse-chronological. Useful for quick navigation and verifying coverage."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50, "description": "Max meetings to return (cap 200)."},
                    "since": {"type": "string", "description": "Inclusive lower-bound date YYYY-MM-DD."},
                    "until": {"type": "string", "description": "Inclusive upper-bound date YYYY-MM-DD."},
                },
            },
        ),
        Tool(
            name="transcript_get_meeting",
            description=(
                "Return every segment of a single meeting, ordered by start time. "
                "Use meeting_id from transcript_search results or transcript_list_meetings."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "meeting_id": {"type": "string", "description": "Meeting ID (Plaud file_id or local label)."},
                    "limit": {"type": "integer", "default": 1000, "description": "Max segments (cap 3000)."},
                },
                "required": ["meeting_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "transcript_search":
            out = _search(
                query=arguments["query"],
                speaker=arguments.get("speaker"),
                since=arguments.get("since"),
                until=arguments.get("until"),
                limit=min(arguments.get("limit", 30) or 30, 200),
            )
        elif name == "transcript_list_meetings":
            out = _list_meetings(
                limit=min(arguments.get("limit", 50) or 50, 200),
                since=arguments.get("since"),
                until=arguments.get("until"),
            )
        elif name == "transcript_get_meeting":
            out = _get_meeting(
                meeting_id=arguments["meeting_id"],
                limit=min(arguments.get("limit", 1000) or 1000, 3000),
            )
        else:
            return [TextContent(type="text", text=json.dumps({"error": f"unknown tool: {name}"}))]
        return [TextContent(type="text", text=json.dumps(out, ensure_ascii=False, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e), "type": type(e).__name__}))]


def _search(*, query, speaker, since, until, limit):
    conn = _connect()
    try:
        q = (
            "SELECT m.id AS meeting_id, m.date, m.title, "
            "s.start_ms, s.end_ms, s.speaker_name, s.speaker_label, s.content "
            "FROM segments_fts JOIN segments s ON s.id = segments_fts.rowid "
            "JOIN meetings m ON m.id = s.meeting_id "
            "WHERE segments_fts MATCH ?"
        )
        params = [query]
        if speaker:
            q += " AND (s.speaker_name = ? COLLATE NOCASE OR s.speaker_label = ?)"
            params += [speaker, speaker]
        if since:
            q += " AND m.date >= ?"
            params.append(since)
        if until:
            q += " AND m.date <= ?"
            params.append(until)
        q += " ORDER BY m.date DESC, s.start_ms ASC LIMIT ?"
        params.append(int(limit))
        return [dict(r) for r in conn.execute(q, params).fetchall()]
    finally:
        conn.close()


def _list_meetings(*, limit, since, until):
    conn = _connect()
    try:
        q = (
            "SELECT m.id, m.date, m.title, m.duration_ms, m.language, m.n_speakers, "
            "(SELECT COUNT(*) FROM segments WHERE meeting_id = m.id) AS n_segments, "
            "m.vault_note_path "
            "FROM meetings m"
        )
        conds, params = [], []
        if since: conds.append("m.date >= ?"); params.append(since)
        if until: conds.append("m.date <= ?"); params.append(until)
        if conds: q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY m.date DESC, m.title LIMIT ?"
        params.append(int(limit))
        return [dict(r) for r in conn.execute(q, params).fetchall()]
    finally:
        conn.close()


def _get_meeting(*, meeting_id, limit):
    conn = _connect()
    try:
        m = conn.execute(
            "SELECT id, date, title, duration_ms, language, n_speakers, vault_note_path FROM meetings WHERE id = ?",
            (meeting_id,),
        ).fetchone()
        if not m:
            return {"error": f"meeting_id not found: {meeting_id}"}
        segs = conn.execute(
            "SELECT seg_idx, start_ms, end_ms, speaker_label, speaker_name, content "
            "FROM segments WHERE meeting_id = ? ORDER BY start_ms ASC LIMIT ?",
            (meeting_id, int(limit)),
        ).fetchall()
        spk = conn.execute(
            "SELECT label, real_name, duration_s FROM speakers WHERE meeting_id = ?",
            (meeting_id,),
        ).fetchall()
        return {
            "meeting": dict(m),
            "speakers": [dict(r) for r in spk],
            "segments": [dict(r) for r in segs],
        }
    finally:
        conn.close()


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
